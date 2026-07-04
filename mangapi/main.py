"""
MangAPI — FastAPI Backend
Crawl truyện tranh từ NetTruyen, TruyenQQ và các nguồn khác.

Endpoints:
  GET /health
  GET /sources
  GET /manga/search
  GET /manga/{source}/{slug}
  GET /manga/{source}/{slug}/chapters/{chapter_id}
  GET /manga/{source}/listing
  GET /manga/{source}/genres
  GET /proxy/image
"""
from __future__ import annotations

import os
import logging
import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import httpx

from .core.registry import get_parser, list_sources, all_parsers
from .core.http import fetch_bytes, random_ua
from .models.schemas import (
    HealthResponse, SearchResult, MangaDetail,
    MangaListing, ChapterPages, MangaCard, Genre,
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mangapi")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MangAPI",
    description="API crawl truyện tranh từ các nguồn Việt Nam",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_extra = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    *_extra,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
    max_age=86400,
)


# ── Helper ────────────────────────────────────────────────────────────────────

def _source_or_404(source: str):
    try:
        return get_parser(source)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health():
    return HealthResponse(sources=list_sources(), version="1.0.0")


@app.get("/sources", tags=["system"])
async def sources():
    """Danh sách nguồn đang hoạt động."""
    return {
        "sources": [
            {"id": p.SOURCE, "name": p.DISPLAY_NAME, "base_url": p.BASE_URL}
            for p in all_parsers()
        ]
    }


# ── Search ───────────────────────────────────────────────────────────────────

@app.get("/manga/search", response_model=SearchResult, tags=["manga"])
async def search_manga(
    q: str = Query(..., min_length=1, description="Từ khoá tìm kiếm"),
    source: str = Query("nettruyen", description="Nguồn: nettruyen | truyenqq"),
    page: int = Query(1, ge=1),
):
    """
    Tìm kiếm truyện theo tên.

    - **q**: từ khoá
    - **source**: nguồn dữ liệu
    - **page**: trang kết quả (bắt đầu từ 1)
    """
    parser = _source_or_404(source)
    try:
        results = await parser.search(q, page)
    except Exception as e:
        logger.exception("Search error [%s] q=%s", source, q)
        raise HTTPException(status_code=502, detail=f"Lỗi crawl: {e}")

    return SearchResult(source=source, query=q, page=page, results=results)


@app.get("/manga/search/multi", tags=["manga"])
async def search_multi_source(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
):
    """Tìm kiếm đồng thời trên tất cả nguồn."""
    parsers = all_parsers()

    async def _search_one(p):
        try:
            return await p.search(q, page)
        except Exception:
            return []

    results_list = await asyncio.gather(*[_search_one(p) for p in parsers])

    combined: list[MangaCard] = []
    for cards in results_list:
        combined.extend(cards)

    return {"query": q, "page": page, "results": combined}


# ── Manga detail ──────────────────────────────────────────────────────────────

@app.get("/manga/{source}/{slug}", response_model=MangaDetail, tags=["manga"])
async def get_manga(source: str, slug: str):
    """
    Thông tin chi tiết bộ truyện + danh sách chapter.

    - **source**: nguồn (nettruyen / truyenqq)
    - **slug**: slug của truyện trong URL
    """
    parser = _source_or_404(source)
    try:
        return await parser.get_manga(slug)
    except Exception as e:
        logger.exception("Manga detail error [%s] slug=%s", source, slug)
        raise HTTPException(status_code=502, detail=f"Lỗi crawl: {e}")


# ── Chapter pages ─────────────────────────────────────────────────────────────

@app.get("/manga/{source}/{slug}/chapters/{chapter_id}", response_model=ChapterPages, tags=["manga"])
async def get_chapter(source: str, slug: str, chapter_id: str):
    """
    Danh sách URL ảnh của 1 chapter.

    - **chapter_id**: số chapter (ví dụ: `123`, `123.5`)
    - Kèm theo `image_headers` — headers cần thiết để proxy ảnh
    """
    parser = _source_or_404(source)
    try:
        return await parser.get_chapter(slug, chapter_id)
    except Exception as e:
        logger.exception("Chapter error [%s] %s/chap-%s", source, slug, chapter_id)
        raise HTTPException(status_code=502, detail=f"Lỗi crawl: {e}")


# ── Listing ───────────────────────────────────────────────────────────────────

@app.get("/manga/{source}/listing", response_model=MangaListing, tags=["manga"])
async def get_listing(
    source: str,
    kind: str = Query("new_update", description="new_update | top_day | top_week | top_month"),
    page: int = Query(1, ge=1),
):
    """
    Danh sách truyện theo loại.

    - **kind**: `new_update` | `top_day` | `top_week` | `top_month`
    """
    parser = _source_or_404(source)
    try:
        return await parser.get_listing(kind, page)
    except Exception as e:
        logger.exception("Listing error [%s] kind=%s", source, kind)
        raise HTTPException(status_code=502, detail=f"Lỗi crawl: {e}")


# ── Genres ────────────────────────────────────────────────────────────────────

@app.get("/manga/{source}/genres", response_model=list[Genre], tags=["manga"])
async def get_genres(source: str):
    """Danh sách thể loại của nguồn."""
    parser = _source_or_404(source)
    try:
        return await parser.get_genres()
    except Exception as e:
        logger.exception("Genres error [%s]", source)
        raise HTTPException(status_code=502, detail=f"Lỗi crawl: {e}")


# ── Image proxy ───────────────────────────────────────────────────────────────

@app.get("/proxy/image", tags=["proxy"])
async def proxy_image(
    url: str = Query(..., description="URL ảnh gốc từ CDN"),
    referer: str = Query("", description="Referer header (trang chứa ảnh)"),
):
    """
    Proxy ảnh từ CDN về client.
    Cần thiết vì CDN Nettruyen/TruyenQQ kiểm tra Referer — không thể load thẳng từ trình duyệt.

    **Cách dùng:**
    ```
    <img src="/proxy/image?url=https://cdn.nettruyen.../page-1.jpg&referer=https://nettruyenviet.com/..." />
    ```
    """
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="URL không hợp lệ")

    # Whitelist CDN domain để tránh open proxy
    ALLOWED_DOMAINS = [
        "nettruyen", "truyenqq", "truyentranh", "img.",
        "cdn.", "i.imgur", "manganelo", "mangakakalot",
    ]
    if not any(d in url for d in ALLOWED_DOMAINS):
        raise HTTPException(status_code=403, detail="Domain không được phép proxy")

    try:
        content, content_type = await fetch_bytes(
            url,
            referer=referer or url,
            extra_headers={
                "User-Agent": random_ua(),
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
    except Exception as e:
        logger.warning("Proxy image error: %s — %s", url, e)
        raise HTTPException(status_code=502, detail=f"Không thể lấy ảnh: {e}")

    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )
