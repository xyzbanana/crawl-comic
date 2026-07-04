"""
MangAPI — CuuTruyen Parser
Nguồn: cuutruyen.net

CuuTruyen có REST API JSON riêng — không cần parse HTML, ổn định hơn nhiều.

API endpoints:
  Tìm kiếm:      GET /api/v2/mangas?q={query}&page={p}&per_page=20
  Chi tiết:      GET /api/v2/mangas/{id}
  Chapters:      GET /api/v2/mangas/{id}/chapters?page={p}&per_page=9999
  Chapter ảnh:   GET /api/v2/chapters/{chapter_id}
  Listing mới:   GET /api/v2/mangas?sort=uploaded_at&page={p}
  Top:           GET /api/v2/mangas?sort=views&page={p}
"""
from __future__ import annotations

import logging
from typing import Any

from ..core.base_parser import BaseParser
from ..core.http import fetch_html, cache_meta, cache_chapter, cache_list
from ..models.schemas import (
    MangaDetail, MangaCard, ChapterBrief, ChapterPages, Genre, MangaListing
)

import httpx

logger = logging.getLogger("mangapi.cuutruyen")

BASE = "https://cuutruyen.net"
API  = "https://cuutruyen.net/api/v2"

_HEADERS = {
    "Accept": "application/json",
    "Referer": BASE,
    "Origin": BASE,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


async def _api_get(path: str, params: dict | None = None) -> Any:
    """Gọi JSON API của CuuTruyen, trả về dict/list đã parse."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(f"{API}{path}", params=params or {}, headers=_HEADERS)
        resp.raise_for_status()
        return resp.json()


class CuutruyenParser(BaseParser):
    SOURCE       = "cuutruyen"
    BASE_URL     = BASE
    DISPLAY_NAME = "Cứu Truyện"

    # ── Search ─────────────────────────────────────────────────────────────

    async def search(self, query: str, page: int = 1) -> list[MangaCard]:
        data = await _api_get("/mangas", {"q": query, "page": page, "per_page": 20})
        return [self._card(m) for m in data.get("data", [])]

    # ── Manga detail ───────────────────────────────────────────────────────

    async def get_manga(self, slug: str) -> MangaDetail:
        # slug ở đây là manga id (số) hoặc slug text
        # CuuTruyen dùng numeric id trong URL: /mangas/204
        manga_id = slug  # caller truyền vào id hoặc slug
        data = await _api_get(f"/mangas/{manga_id}")
        manga = data.get("data", data)

        # Lấy toàn bộ chapter (per_page lớn để 1 request)
        chap_data = await _api_get(
            f"/mangas/{manga_id}/chapters",
            {"page": 1, "per_page": 9999, "sort": "desc"}
        )
        chapters = [
            ChapterBrief(
                id=str(c["id"]),
                title=c.get("name") or f"Chapter {c.get('number', '')}",
                url=f"{BASE}/mangas/{manga_id}/chapters/{c['id']}",
                updated_at=c.get("uploaded_at", "")[:10] if c.get("uploaded_at") else None,
            )
            for c in chap_data.get("data", [])
        ]

        authors = []
        if manga.get("author"):
            authors = [manga["author"]] if isinstance(manga["author"], str) else manga["author"]

        genres = [t["name"] for t in manga.get("tags", [])]

        status_raw = manga.get("status", "ongoing").lower()
        if "complete" in status_raw or "hoàn" in status_raw:
            status = "completed"
        elif "hiatus" in status_raw or "tạm dừng" in status_raw:
            status = "hiatus"
        else:
            status = "ongoing"

        cover = manga.get("cover_url") or manga.get("cover") or ""

        return MangaDetail(
            source=self.SOURCE,
            slug=str(manga.get("id", slug)),
            title=manga.get("name") or manga.get("title") or str(slug),
            alt_titles=[manga["other_names"]] if manga.get("other_names") else [],
            cover=cover,
            authors=authors,
            genres=genres,
            status=status,
            description=manga.get("description") or "",
            views=str(manga.get("views", "")),
            chapters=chapters,
        )

    # ── Chapter pages ──────────────────────────────────────────────────────

    async def get_chapter(self, manga_slug: str, chapter_id: str) -> ChapterPages:
        data = await _api_get(f"/chapters/{chapter_id}")
        chap = data.get("data", data)

        pages: list[str] = []
        for p in chap.get("pages", []):
            url = p.get("image_url") or p.get("url") or ""
            if url:
                pages.append(url)

        title = chap.get("name") or f"Chapter {chap.get('number', chapter_id)}"

        return ChapterPages(
            source=self.SOURCE,
            manga_slug=manga_slug,
            chapter_id=chapter_id,
            title=title,
            pages=pages,
            image_headers={"Referer": BASE},
        )

    # ── Listing ────────────────────────────────────────────────────────────

    async def get_listing(self, kind: str = "new_update", page: int = 1) -> MangaListing:
        sort_map = {
            "new_update": "uploaded_at",
            "top_day":    "views",
            "top_week":   "views",
            "top_month":  "views",
        }
        sort = sort_map.get(kind, "uploaded_at")
        data = await _api_get("/mangas", {"sort": sort, "page": page, "per_page": 24})
        items = [self._card(m) for m in data.get("data", [])]

        meta = data.get("meta", {})
        has_next = page < meta.get("total_pages", 1)

        return MangaListing(
            source=self.SOURCE,
            kind=kind,
            page=page,
            items=items,
            has_next=has_next,
        )

    # ── Genres ────────────────────────────────────────────────────────────

    async def get_genres(self) -> list[Genre]:
        data = await _api_get("/tags")
        genres = []
        for t in data.get("data", []):
            genres.append(Genre(
                name=t.get("name", ""),
                slug=str(t.get("id", "")),
                url=f"{BASE}/tags/{t.get('id', '')}",
            ))
        return genres

    # ── Helper ────────────────────────────────────────────────────────────

    def _card(self, m: dict) -> MangaCard:
        manga_id = str(m.get("id", ""))
        latest_chap = None
        if m.get("last_chapter"):
            lc = m["last_chapter"]
            latest_chap = lc.get("name") or f"Chapter {lc.get('number', '')}"

        return MangaCard(
            source=self.SOURCE,
            slug=manga_id,
            title=m.get("name") or m.get("title") or "",
            cover=m.get("cover_url") or m.get("cover") or "",
            latest_chapter=latest_chap,
            status=m.get("status", "ongoing"),
            url=f"{BASE}/mangas/{manga_id}",
						)
