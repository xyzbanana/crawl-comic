"""
MangAPI — TruyenQQ Parser
Nguồn: truyenqqvip.com (và các mirror)

Cấu trúc HTML:
- Trang truyện:  /truyen-tranh/{slug}.html  hoặc  /{slug}
- Chapter:       /truyen-tranh/{slug}/chap-{n}.html
- Tìm kiếm:     /tim-kiem.html?keyword={q}&page={p}
- Top/new:       /truyen-tranh-moi-nhat/trang-{p}.html
"""
from __future__ import annotations

import re
import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ..core.base_parser import BaseParser
from ..core.http import fetch_html, cache_meta, cache_chapter, cache_list
from ..models.schemas import (
    MangaDetail, MangaCard, ChapterBrief, ChapterPages, Genre, MangaListing
)

logger = logging.getLogger("mangapi.truyenqq")


class TruyenqqParser(BaseParser):
    SOURCE       = "truyenqq"
    BASE_URL     = "https://truyenqqko.com"
    DISPLAY_NAME = "TruyenQQ"

    # ── Search ─────────────────────────────────────────────────────────────

    async def search(self, query: str, page: int = 1) -> list[MangaCard]:
        url = f"{self.BASE_URL}/tim-kiem.html?keyword={quote_plus(query)}&page={page}"
        html = await fetch_html(url, referer=self.BASE_URL, cache_pool=cache_meta)
        soup = BeautifulSoup(html, "lxml")
        return self._parse_card_list(soup)

    # ── Manga detail ───────────────────────────────────────────────────────

    async def get_manga(self, slug: str) -> MangaDetail:
        # TruyenQQ URL dạng /truyen-tranh/slug.html hoặc /slug
        url = f"{self.BASE_URL}/truyen-tranh/{slug}.html"
        try:
            html = await fetch_html(url, referer=self.BASE_URL, cache_pool=cache_meta)
        except RuntimeError:
            # Fallback không có .html
            url = f"{self.BASE_URL}/{slug}"
            html = await fetch_html(url, referer=self.BASE_URL, cache_pool=cache_meta)
        soup = BeautifulSoup(html, "lxml")
        return self._parse_manga_detail(soup, slug, url)

    # ── Chapter pages ──────────────────────────────────────────────────────

    async def get_chapter(self, manga_slug: str, chapter_id: str) -> ChapterPages:
        url = f"{self.BASE_URL}/truyen-tranh/{manga_slug}/chap-{chapter_id}.html"
        html = await fetch_html(
            url,
            referer=self.BASE_URL,
            cache_pool=cache_chapter,
            delay=(0.3, 1.0),
        )
        soup = BeautifulSoup(html, "lxml")
        return self._parse_chapter_pages(soup, manga_slug, chapter_id, url)

    # ── Listing ────────────────────────────────────────────────────────────

    async def get_listing(self, kind: str = "new_update", page: int = 1) -> MangaListing:
        path_map = {
            "new_update": f"/truyen-tranh-moi-nhat/trang-{page}.html",
            "top_day":    f"/top-ngay/trang-{page}.html",
            "top_week":   f"/top-tuan/trang-{page}.html",
            "top_month":  f"/top-thang/trang-{page}.html",
        }
        path = path_map.get(kind, f"/truyen-tranh-moi-nhat/trang-{page}.html")
        url = self.BASE_URL + path
        html = await fetch_html(url, referer=self.BASE_URL, cache_pool=cache_list)
        soup = BeautifulSoup(html, "lxml")
        cards = self._parse_card_list(soup)

        next_btn = soup.select_one(".paging a.next, .pagination .next")
        has_next = next_btn is not None

        return MangaListing(
            source=self.SOURCE,
            kind=kind,
            page=page,
            items=cards,
            has_next=has_next,
        )

    # ── Genres ────────────────────────────────────────────────────────────

    async def get_genres(self) -> list[Genre]:
        html = await fetch_html(self.BASE_URL, referer="", cache_pool=cache_list)
        soup = BeautifulSoup(html, "lxml")
        genres: list[Genre] = []

        for a in soup.select(".megamenu a[href*='the-loai'], nav a[href*='the-loai']"):
            href = a.get("href", "")
            name = a.get_text(strip=True)
            if not name or len(name) < 2:
                continue
            m = re.search(r"the-loai/([^/.\s]+)", href)
            slug = m.group(1) if m else name.lower().replace(" ", "-")
            genres.append(Genre(name=name, slug=slug, url=self._abs(href)))

        return genres

    # ── HTML parsers ───────────────────────────────────────────────────────

    def _parse_card_list(self, soup: BeautifulSoup) -> list[MangaCard]:
        cards: list[MangaCard] = []

        for item in soup.select(".list_grid li, .book_list li, ul.grid li"):
            a_tag = item.select_one("h3 a, .book_name a, .title a")
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            href  = a_tag.get("href", "")
            slug  = self._slug_from_url(href)

            img = item.select_one("img[src], img[data-original]")
            cover = ""
            if img:
                cover = img.get("data-original") or img.get("src") or ""
                cover = self._abs(cover)

            chap_tag = item.select_one(".last_chapter a, .new-chapter a")
            latest = chap_tag.get_text(strip=True) if chap_tag else None

            if slug and title:
                cards.append(MangaCard(
                    source=self.SOURCE,
                    slug=slug,
                    title=title,
                    cover=cover,
                    latest_chapter=latest,
                    url=self.make_url(f"/truyen-tranh/{slug}.html"),
                ))

        return cards

    def _parse_manga_detail(self, soup: BeautifulSoup, slug: str, page_url: str) -> MangaDetail:
        title_tag = soup.select_one(".book_detail h1, h1.title-manga")
        title = title_tag.get_text(strip=True) if title_tag else slug

        # Ảnh bìa
        img = soup.select_one(".book_avatar img, .detail-avatar img")
        cover = ""
        if img:
            cover = img.get("data-original") or img.get("src") or ""
            cover = self._abs(cover)

        # Thông tin
        info = soup.select_one(".book_info, .detail-info")
        authors, genres, status = [], [], "ongoing"

        if info:
            for row in info.select("li, p"):
                text = row.get_text(" ", strip=True)
                if "Tác giả" in text or "Author" in text:
                    authors = [a.get_text(strip=True) for a in row.select("a")]
                elif "Thể loại" in text or "Genre" in text:
                    genres = [a.get_text(strip=True) for a in row.select("a")]
                elif "Tình trạng" in text or "Status" in text:
                    if "Hoàn thành" in text:
                        status = "completed"
                    elif "Tạm dừng" in text:
                        status = "hiatus"

        # Mô tả
        desc_tag = soup.select_one(".book_intro p, .detail-content p")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # Chapter list
        chapters: list[ChapterBrief] = []
        for li in soup.select("#list_chapter li, .list-chapter li"):
            a = li.select_one("a")
            if not a:
                continue
            chap_href  = a.get("href", "")
            chap_title = a.get_text(strip=True)
            chap_id    = self._chapter_id_from_url(chap_href)
            time_tag   = li.select_one(".time-chap, .chapter-time")
            updated_at = time_tag.get_text(strip=True) if time_tag else None
            if chap_id:
                chapters.append(ChapterBrief(
                    id=chap_id,
                    title=chap_title,
                    url=self._abs(chap_href),
                    updated_at=updated_at,
                ))

        return MangaDetail(
            source=self.SOURCE, slug=slug, title=title,
            cover=cover, authors=authors, genres=genres,
            status=status, description=description,
            chapters=chapters,
        )

    def _parse_chapter_pages(
        self, soup: BeautifulSoup, manga_slug: str, chapter_id: str, page_url: str
    ) -> ChapterPages:
        title_tag = soup.select_one(".chapter-title, h1.title-chapter")
        title = title_tag.get_text(strip=True) if title_tag else f"Chapter {chapter_id}"

        pages: list[str] = []
        for img in soup.select(".page-chapter img, #nt_listchapter img, .reading-detail img"):
            src = img.get("data-original") or img.get("data-src") or img.get("src") or ""
            src = src.strip()
            if src and src.startswith("http"):
                pages.append(src)

        return ChapterPages(
            source=self.SOURCE,
            manga_slug=manga_slug,
            chapter_id=chapter_id,
            title=title,
            pages=pages,
            image_headers={"Referer": page_url},
        )

    # ── Utilities ──────────────────────────────────────────────────────────

    def _abs(self, url: str) -> str:
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.BASE_URL + url
        return url

    def _slug_from_url(self, url: str) -> str:
        m = re.search(r"/truyen-tranh/([^/.\s]+)", url)
        if m:
            return m.group(1)
        m = re.search(r"\.com/([^/.\s]+?)(?:\.html)?$", url)
        return m.group(1) if m else ""

    def _chapter_id_from_url(self, url: str) -> str:
        m = re.search(r"/chap-(\d+[\w.-]*)", url)
        return m.group(1) if m else ""
