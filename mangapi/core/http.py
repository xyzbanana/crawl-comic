"""
MangAPI — HTTP Client
Async httpx client dùng chung, với:
- Fake User-Agent xoay vòng
- Retry tự động (3 lần)
- In-memory cache (TTL 5 phút cho metadata, 30 phút cho chapter)
- Delay ngẫu nhiên chống rate-limit
"""
from __future__ import annotations

import asyncio
import random
import time
import logging
from typing import Any, Optional

import httpx
from cachetools import TTLCache
from fake_useragent import UserAgent

logger = logging.getLogger("mangapi.http")

# ── Cache pools ─────────────────────────────────────────────────────────────
_cache_meta    = TTLCache(maxsize=512,  ttl=300)   # 5 phút — search, manga detail
_cache_chapter = TTLCache(maxsize=256,  ttl=1800)  # 30 phút — chapter pages
_cache_list    = TTLCache(maxsize=128,  ttl=180)   # 3 phút  — top/new listing

# ── User-Agent pool ─────────────────────────────────────────────────────────
try:
    _ua = UserAgent(browsers=["chrome", "firefox", "edge"])
    def random_ua() -> str:
        return _ua.random
except Exception:
    _FALLBACK_UAS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ]
    def random_ua() -> str:
        return random.choice(_FALLBACK_UAS)


def _base_headers(referer: str = "") -> dict[str, str]:
    headers = {
        "User-Agent": random_ua(),
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        headers["Referer"] = referer
    return headers


# ── Main fetch function ─────────────────────────────────────────────────────

async def fetch_html(
    url: str,
    *,
    referer: str = "",
    extra_headers: Optional[dict] = None,
    cache_pool: Optional[TTLCache] = None,
    retries: int = 3,
    delay: tuple[float, float] = (0.5, 1.5),
) -> str:
    """
    Fetch URL và trả về HTML string.
    - cache_pool: truyền _cache_meta / _cache_chapter / _cache_list để cache
    - delay: (min, max) giây sleep ngẫu nhiên trước mỗi request
    """
    # Kiểm tra cache
    if cache_pool is not None and url in cache_pool:
        logger.debug("Cache hit: %s", url)
        return cache_pool[url]

    headers = _base_headers(referer)
    if extra_headers:
        headers.update(extra_headers)

    last_exc: Exception = Exception("Unknown error")

    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
        http2=False,
    ) as client:
        for attempt in range(1, retries + 1):
            # Random delay tránh rate-limit
            await asyncio.sleep(random.uniform(*delay))
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                html = resp.text

                if cache_pool is not None:
                    cache_pool[url] = html

                logger.debug("Fetched %s [%s] attempt=%d", url, resp.status_code, attempt)
                return html

            except httpx.HTTPStatusError as e:
                logger.warning("HTTP %s for %s (attempt %d)", e.response.status_code, url, attempt)
                last_exc = e
                if e.response.status_code in (403, 429):
                    # Chờ lâu hơn nếu bị rate-limit / block
                    await asyncio.sleep(random.uniform(3, 7))
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning("Network error for %s (attempt %d): %s", url, attempt, e)
                last_exc = e

    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts: {last_exc}")


async def fetch_bytes(
    url: str,
    *,
    referer: str = "",
    extra_headers: Optional[dict] = None,
) -> tuple[bytes, str]:
    """Fetch binary (ảnh, file). Trả về (bytes, content_type)."""
    headers = _base_headers(referer)
    if extra_headers:
        headers.update(extra_headers)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content, resp.headers.get("content-type", "image/jpeg")


# ── Cache helpers expose ra ngoài ───────────────────────────────────────────
cache_meta    = _cache_meta
cache_chapter = _cache_chapter
cache_list    = _cache_list
