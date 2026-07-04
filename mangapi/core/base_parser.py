"""
MangAPI — Base Parser
Mỗi nguồn (nettruyen, truyenqq...) implement class này.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from ..models.schemas import MangaDetail, MangaCard, ChapterPages, Genre, MangaListing


class BaseParser(ABC):
    SOURCE: str = ""          # "nettruyen" | "truyenqq"
    BASE_URL: str = ""        # "https://nettruyenviet.com"
    DISPLAY_NAME: str = ""    # "NetTruyen"

    # ── Bắt buộc implement ─────────────────────────────────────────────────

    @abstractmethod
    async def search(self, query: str, page: int = 1) -> list[MangaCard]:
        """Tìm kiếm truyện theo từ khoá."""
        ...

    @abstractmethod
    async def get_manga(self, slug: str) -> MangaDetail:
        """Chi tiết bộ truyện + danh sách chapter."""
        ...

    @abstractmethod
    async def get_chapter(self, manga_slug: str, chapter_id: str) -> ChapterPages:
        """URL ảnh của 1 chapter."""
        ...

    @abstractmethod
    async def get_listing(self, kind: str = "new_update", page: int = 1) -> MangaListing:
        """
        Danh sách truyện theo loại:
        - new_update: mới cập nhật
        - top_day / top_week / top_month: bảng xếp hạng
        """
        ...

    # ── Tuỳ chọn override ─────────────────────────────────────────────────

    async def get_genres(self) -> list[Genre]:
        """Danh sách thể loại. Mặc định trả rỗng."""
        return []

    # ── Helper dùng chung ─────────────────────────────────────────────────

    def make_url(self, path: str) -> str:
        return self.BASE_URL.rstrip("/") + "/" + path.lstrip("/")

    def source_tag(self) -> str:
        return self.SOURCE
