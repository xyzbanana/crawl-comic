"""
MangAPI — Response Schemas
Chuẩn hoá JSON trả về cho mọi parser / nguồn.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Manga info ──────────────────────────────────────────────────────────────

class ChapterBrief(BaseModel):
    """Thông tin rút gọn của 1 chapter trong danh sách."""
    id: str                         # slug hoặc số chapter, unique trong bộ
    title: str                      # "Chapter 123" hoặc "Chap 123: Tên chap"
    url: str                        # URL đầy đủ đến trang đọc chapter
    updated_at: Optional[str] = None  # ISO string hoặc text hiển thị


class MangaDetail(BaseModel):
    """Thông tin chi tiết 1 bộ truyện."""
    source: str                     # "nettruyen" | "truyenqq" | ...
    slug: str                       # định danh trong URL
    title: str
    alt_titles: list[str] = []
    cover: str                      # URL ảnh bìa
    authors: list[str] = []
    genres: list[str] = []
    status: str = "ongoing"         # "ongoing" | "completed" | "hiatus"
    description: str = ""
    rating: Optional[float] = None
    views: Optional[str] = None
    chapters: list[ChapterBrief] = []


# ── Search result ───────────────────────────────────────────────────────────

class MangaCard(BaseModel):
    """Thẻ truyện xuất hiện trong kết quả tìm kiếm / danh sách."""
    source: str
    slug: str
    title: str
    cover: str
    latest_chapter: Optional[str] = None
    status: Optional[str] = None
    url: str


class SearchResult(BaseModel):
    source: str
    query: str
    page: int = 1
    results: list[MangaCard] = []
    has_next: bool = False


# ── Chapter pages ───────────────────────────────────────────────────────────

class ChapterPages(BaseModel):
    """Danh sách URL ảnh của 1 chapter."""
    source: str
    manga_slug: str
    chapter_id: str
    title: str = ""
    pages: list[str]                # URL ảnh theo thứ tự
    # Header cần thiết để proxy ảnh (referer, cookie...)
    image_headers: dict[str, str] = {}


# ── Genre / category ────────────────────────────────────────────────────────

class Genre(BaseModel):
    name: str
    slug: str
    url: str


# ── Top / listing ───────────────────────────────────────────────────────────

class MangaListing(BaseModel):
    source: str
    kind: str                       # "new_update" | "top_day" | "top_week" | "top_month"
    page: int = 1
    items: list[MangaCard] = []
    has_next: bool = False


# ── API health ───────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    sources: list[str] = []
    version: str = "1.0.0"
