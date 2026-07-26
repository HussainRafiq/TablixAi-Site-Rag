"""Browserless page fetch + LLM-ready text extraction (Firecrawl/Jina-style)."""

from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.config import Settings
from app.models import PageDocument

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(text: str) -> str:
    text = html_lib.unescape(text or "")
    text = _TAG_RE.sub(" ", text)
    text = text.replace("\ufffd", "")
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
    text = _WS_RE.sub(" ", text).strip()
    return text


def _fallback_extract(html: str, url: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.get_text(strip=True) if soup.title else "") or ""
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "svg"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return _clean_text(title), _clean_text(text)


def _extract(html: str, url: str, max_chars: int) -> tuple[str, str]:
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
        output_format="txt",
    )
    meta = trafilatura.extract_metadata(html, default_url=url)
    title = _clean_text((meta.title if meta and meta.title else "") or "")

    if not extracted or len(extracted.strip()) < 80:
        title2, text = _fallback_extract(html, url)
        title = title or title2
        if not extracted or len(text) > len(extracted or ""):
            extracted = text

    if not title:
        path = urlparse(url).path.rsplit("/", 1)[-1] or url
        title = path

    extracted = _clean_text(extracted)
    if len(extracted) > max_chars:
        extracted = extracted[:max_chars].rsplit(" ", 1)[0] + "…"

    return title, extracted


async def fetch_page(
    client: httpx.AsyncClient,
    url: str,
    settings: Settings,
) -> PageDocument:
    try:
        resp = await client.get(
            url,
            follow_redirects=True,
            timeout=settings.request_timeout,
        )
        resp.raise_for_status()
        content_type = (resp.headers.get("content-type") or "").lower()
        if "html" not in content_type and "text" not in content_type and content_type:
            return PageDocument(
                url=str(resp.url),
                title="",
                content="",
                status="skipped",
                error=f"Unsupported content-type: {content_type}",
            )

        html = resp.text
        title, text = await asyncio.to_thread(
            _extract, html, str(resp.url), settings.max_chars_per_page
        )
        if not text:
            return PageDocument(
                url=str(resp.url),
                title=title,
                content="",
                status="empty",
                error="No extractable text",
            )
        return PageDocument(url=str(resp.url), title=title, content=text, status="ok")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fetch failed for %s: %s", url, exc)
        return PageDocument(
            url=url,
            title="",
            content="",
            status="error",
            error=str(exc),
        )


async def fetch_pages(
    urls: list[str],
    settings: Settings,
    *,
    concurrency: int = 2,
) -> list[PageDocument]:
    # de-dupe while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    sem = asyncio.Semaphore(max(1, concurrency))

    async with httpx.AsyncClient(headers=headers, http2=False) as client:

        async def _one(url: str) -> PageDocument:
            async with sem:
                return await fetch_page(client, url, settings)

        return list(await asyncio.gather(*[_one(url) for url in unique]))
