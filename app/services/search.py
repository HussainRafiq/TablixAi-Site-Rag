"""Browserless web search with optional site allowlist (Tavily/Exa-style scoping)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from ddgs import DDGS

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


def _normalize_host(value: str) -> str:
    value = value.strip().lower()
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    host = parsed.netloc or parsed.path.split("/")[0]
    return host.removeprefix("www.")


def is_url(value: str) -> bool:
    value = value.strip()
    if value.startswith(("http://", "https://")):
        return True
    # bare path-like domain with path
    if "/" in value and "." in value.split("/")[0]:
        return True
    return False


def split_sites(sites: list[str]) -> tuple[list[str], list[str]]:
    """Return (direct_urls, domain_hosts)."""
    urls: list[str] = []
    domains: list[str] = []
    for raw in sites:
        s = raw.strip()
        if not s:
            continue
        if s.startswith(("http://", "https://")):
            urls.append(s)
            continue
        # domain with path treated as URL
        if "/" in s and "." in s.split("/")[0]:
            urls.append(f"https://{s}")
            continue
        # plain domain
        if "." in s and " " not in s:
            domains.append(_normalize_host(s))
            continue
        # fallback: treat as domain hint
        domains.append(_normalize_host(s))
    return urls, domains


def url_allowed(url: str, allowed_domains: list[str]) -> bool:
    if not allowed_domains:
        return True
    host = _normalize_host(url)
    return any(host == d or host.endswith(f".{d}") for d in allowed_domains)


def build_site_query(query: str, domains: list[str]) -> str:
    if not domains:
        return query
    # DuckDuckGo supports site: filters; OR a few domains at a time
    clauses = " OR ".join(f"site:{d}" for d in domains[:8])
    return f"({clauses}) {query}"


def search_web(
    query: str,
    *,
    max_results: int = 8,
    domains: list[str] | None = None,
) -> list[SearchHit]:
    """Run browserless DuckDuckGo search, optionally restricted to domains."""
    domains = domains or []
    q = build_site_query(query, domains)
    hits: list[SearchHit] = []

    try:
        with DDGS() as ddgs:
            results = list(
                ddgs.text(
                    q,
                    max_results=max(max_results * 2, 10),
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Search failed: %s", exc)
        return []

    for item in results:
        url = (item.get("href") or item.get("link") or "").strip()
        if not url:
            continue
        if domains and not url_allowed(url, domains):
            continue
        hits.append(
            SearchHit(
                title=(item.get("title") or "").strip() or url,
                url=url,
                snippet=(item.get("body") or item.get("snippet") or "").strip(),
            )
        )
        if len(hits) >= max_results:
            break

    return hits
