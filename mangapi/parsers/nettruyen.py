"""
MangAPI — NetTruyen Parser
Nguồn: nettruyenviet.com (và các mirror cùng cấu trúc HTML)

Cấu trúc HTML tham khảo:
- Trang truyện:  /truyen-tranh/{slug}
- Chapter:       /truyen-tranh/{slug}/chap-{n}
- Tìm kiếm:     /tim-truyen?keyword={q}&page={p}
- Top/new:       /truyen-tranh?page={p}&status=-1&sort=0  (sort=0=mới, 10=top)
"""
from __future__ import annotations

import re
import logging
from urllib.parse import urlencode, quote_plus

from bs4 import BeautifulSoup

from ..core.base_parser import BaseParser
from ..core.http import fetch_html, cache_meta, cache_chapter, cache_list
from ..models.schemas import (
    MangaDetail, MangaCard, ChapterBrief, ChapterPages, Genre, MangaListing
)

logger = logging.getLogger("mangapi.nettruyen")


class NettruyenParser(BaseParser):
    SOURCE       = "nettruyen"
    BASE_URL     = "https://nettruyenviet.com"
    DISPLAY_NAME = "NetTruyen"

    # ── Search ─────────────────────────────────────────────────────────────

    async def search(self, query: str, page: int = 1) -> list[MangaCard]:
        url = f"{self.BASE_URL}/tim-truyen?keyword={quote_plus(query)}&page={page}"
        html = await fetch_html(url, referer=self.BASE_URL, cache_pool=cache_meta)
        soup = BeautifulSoup(html, "lxml")
        return self._parse_card_list(soup)

    # ── Manga detail ───────────────────────────────────────────────────────

    async def get_manga(self, slug: str) -> MangaDetail:
        url = f"{self.BASE_URL}/truyen-tranh/{slug}"
        html = await fetch_html(url, referer=self.BASE_URL, cache_pool=cache_meta)
        soup = BeautifulSoup(html, "lxml")
        return self._parse_manga_detail(soup, slug, url)

    # ── Chapter pages ──────────────────────────────────────────────────────

    async def get_chapter(self, manga_slug: str, chapter_id: str) -> ChapterPages:
        url = f"{self.BASE_URL}/truyen-tranh/{manga_slug}/chap-{chapter_id}"
        html = await fetch_html(
            url,
            referer=self.BASE_URL,
            cache_pool=cache_chapter,
            delay=(0.3, 0.8),
        )
        soup = BeautifulSoup(html, "lxml")
        return self._parse_chapter_pages(soup, manga_slug, chapter_id, url)

    # ── Listing ────────────────────────────────────────────────────────────

    async def get_listing(self, kind: str = "new_update", page: int = 1) -> MangaListing:
        sort_map = {
            "new_update": "0",
            "top_day":    "10",
            "top_week":   "11",
            "top_month":  "12",
        }
        sort = sort_map.get(kind, "0")
        url = f"{self.BASE_URL}/truyen-tranh?page={page}&status=-1&sort={sort}"
        html = await fetch_html(url, referer=self.BASE_URL, cache_pool=cache_list)
        soup = BeautifulSoup(html, "lxml")
        cards = self._parse_card_list(soup)

        # Kiểm tra trang tiếp theo
        next_btn = soup.select_one("li.next a, .pagination .next a")
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

        # Dropdown thể loại thường nằm trong nav
        for a in soup.select(".dropdown-menu a[href*='/tim-truyen']"):
            href = a.get("href", "")
            name = a.get_text(strip=True)
            if not name or len(name) < 2:
                continue
            slug_match = re.search(r"the-loai=([^&]+)", href)
            slug = slug_match.group(1) if slug_match else name.lower()
            genres.append(Genre(name=name, slug=slug, url=self.make_url(href)))

        return genres

    # ── HTML parsers ───────────────────────────────────────────────────────

    def _parse_card_list(self, soup: BeautifulSoup) -> list[MangaCard]:
        cards: list[MangaCard] = []

        # NetTruyen dùng .list-truyen-main-side hoặc .row .item
        items = soup.select(".list-truyen-main-side .row .item, .items .item")

        for item in items:
            # Tiêu đề + link
            a_tag = item.select_one("h3 a, figcaption h3 a, .title a")
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            href  = a_tag.get("href", "")
            slug  = self._slug_from_url(href)

            # Ảnh bìa
            img = item.select_one("img[src], img[data-original]")
            cover = ""
            if img:
                cover = img.get("data-original") or img.get("src") or ""
                cover = self._abs(cover)

            # Chapter mới nhất
            chap_tag = item.select_one(".chapter a, .list-chapter a")
            latest = chap_tag.get_text(strip=True) if chap_tag else None

            # Trạng thái
            status_tag = item.select_one(".label-completed, .status")
            status = "completed" if status_tag and "Hoàn thành" in status_tag.get_text() else "ongoing"

            if slug and title:
                cards.append(MangaCard(
                    source=self.SOURCE,
                    slug=slug,
                    title=title,
                    cover=cover,
                    latest_chapter=latest,
                    status=status,
                    url=self.make_url(f"/truyen-tranh/{slug}"),
                ))

        return cards

    def _parse_manga_detail(self, soup: BeautifulSoup, slug: str, page_url: str) -> MangaDetail:
        # Tiêu đề
        title_tag = soup.select_one("h1.title-detail, h1.manga-info-title, .title-detail")
        title = title_tag.get_text(strip=True) if title_tag else slug

        # Tên khác
        alt_tag = soup.select_one(".other-name")
        alt_titles = [t.strip() for t in alt_tag.get_text().split(";")] if alt_tag else []

        # Ảnh bìa
        img = soup.select_one(".col-image img, .manga-detail img")
        cover = ""
        if img:
            cover = img.get("data-original") or img.get("src") or ""
            cover = self._abs(cover)

        # Tác giả
        authors = [
            a.get_text(strip=True)
            for a in soup.select(".author a, .manga-info-author a")
        ]

        # Thể loại
        genres = [
            a.get_text(strip=True)
            for a in soup.select(".kind a, .manga-info-genre a")
        ]

        # Trạng thái
        status_tag = soup.select_one(".status span:last-child, .manga-info-status")
        status_text = status_tag.get_text(strip=True).lower() if status_tag else ""
        if "hoàn thành" in status_text or "completed" in status_text:
            status = "completed"
        elif "tạm dừng" in status_text or "hiatus" in status_text:
            status = "hiatus"
        else:
            status = "ongoing"

        # Mô tả
        desc_tag = soup.select_one(".detail-content p, .manga-info-description p, #summary")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # Rating
        rating = None
        rate_tag = soup.select_one("[itemprop='ratingValue'], .rate-value")
        if rate_tag:
            try:
                rating = float(rate_tag.get_text(strip=True).replace(",", "."))
            except ValueError:
                pass

        # Lượt xem
        views = None
        view_tag = soup.select_one(".view span:last-child, .manga-info-view")
        if view_tag:
            views = view_tag.get_text(strip=True)

        # Danh sách chapter
        chapters: list[ChapterBrief] = []
        for row in soup.select("#nt_listchapter ul li, .list-chapter li"):
            a = row.select_one("a")
            if not a:
                continue
            chap_href = a.get("href", "")
            chap_title = a.get_text(strip=True)
            chap_id = self._chapter_id_from_url(chap_href)

            time_tag = row.select_one(".no-wrap, .chapter-time")
            updated_at = time_tag.get_text(strip=True) if time_tag else None

            if chap_id:
                chapters.append(ChapterBrief(
                    id=chap_id,
                    title=chap_title,
                    url=self.make_url(chap_href),
                    updated_at=updated_at,
                ))

        return MangaDetail(
            source=self.SOURCE,
            slug=slug,
            title=title,
            alt_titles=[t for t in alt_titles if t],
            cover=cover,
            authors=authors,
            genres=genres,
            status=status,
            description=description,
            rating=rating,
            views=views,
            chapters=chapters,
        )

    def _parse_chapter_pages(
        self, soup: BeautifulSoup, manga_slug: str, chapter_id: str, page_url: str
    ) -> ChapterPages:
        title_tag = soup.select_one(".chapter h2, .reading-detail h1, .chapter-title")
        title = title_tag.get_text(strip=True) if title_tag else f"Chapter {chapter_id}"

        pages: list[str] = []

        # NetTruyen đặt ảnh trong div#nt_listchapter hoặc .page-chapter img
        for img in soup.select(".page-chapter img, .reading-detail img, div[id*='chapter'] img"):
            src = img.get("data-original") or img.get("data-src") or img.get("src") or ""
            src = src.strip()
            if src and src.startswith("http"):
                pages.append(src)

        # Fallback: lấy tất cả ảnh trong vùng đọc
        if not pages:
            for img in soup.select(".vung-doc img, #divImage img"):
                src = img.get("data-original") or img.get("src") or ""
                if src and src.startswith("http"):
                    pages.append(src)

        return ChapterPages(
            source=self.SOURCE,
            manga_slug=manga_slug,
            chapter_id=chapter_id,
            title=title,
            pages=pages,
            # Ảnh NetTruyen cần Referer đúng để không bị 403
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
        m = re.search(r"/truyen-tranh/([^/?\s]+)", url)
        return m.group(1) if m else ""

    def _chapter_id_from_url(self, url: str) -> str:
        m = re.search(r"/chap-(\d+[\w.-]*)", url)
        return m.group(1) if m else ""
