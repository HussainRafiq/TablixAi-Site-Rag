"""Orchestrates search → fetch → retrieve → synthesize (web RAG pipeline)."""

from __future__ import annotations

import logging

from app.config import Settings
from app.models import Citation, PageDocument, ResearchRequest, ResearchResponse
from app.services.extractor import fetch_pages
from app.services.openrouter import OpenRouterError, chat_completion
from app.services.rag import format_context, retrieve
from app.services.search import SearchHit, search_web, split_sites, url_allowed

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a careful research assistant performing grounded web RAG.
Answer ONLY using the provided source excerpts.
Cite sources inline with [n] markers that match the excerpt numbers.
If the sources are insufficient, say what is missing instead of inventing facts.
Be concise, structured, and specific."""


def _snippet_pages(hits: list[SearchHit]) -> list[PageDocument]:
    """Use search snippets when full-page fetch fails (common under CF / OOM)."""
    pages: list[PageDocument] = []
    for hit in hits:
        text = " ".join(x for x in [hit.title, hit.snippet] if x).strip()
        if len(text) < 40:
            continue
        pages.append(
            PageDocument(
                url=hit.url,
                title=hit.title or hit.url,
                content=text,
                status="ok",
                error="snippet_fallback",
            )
        )
    return pages


async def run_research(req: ResearchRequest, settings: Settings) -> ResearchResponse:
    direct_urls, domains = split_sites(req.sites)
    max_pages = min(req.max_results, settings.max_pages)

    candidate_urls: list[str] = list(direct_urls)
    # Seed domain roots so site-restricted research has a reliable page even if
    # search result URLs fail (Cloudflare, timeouts, etc.).
    for domain in domains:
        candidate_urls.append(f"https://{domain}/")
        candidate_urls.append(f"https://www.{domain}/")

    search_hits: list[SearchHit] = []

    if req.search_web:
        do_search = True
        if req.sites and not domains and direct_urls:
            do_search = False

        if do_search:
            search_hits = search_web(
                req.query,
                max_results=max_pages,
                domains=domains,
            )
            for hit in search_hits:
                if domains and not url_allowed(hit.url, domains):
                    continue
                candidate_urls.append(hit.url)

    # Cap pages (keep seeded + search URLs)
    candidate_urls = candidate_urls[: max(max_pages + len(domains) * 2, len(direct_urls))]

    pages = (
        await fetch_pages(candidate_urls, settings, concurrency=1)
        if candidate_urls
        else []
    )
    ok_pages = [p for p in pages if p.status == "ok" and p.content]
    failed_pages = [
        {"url": p.url, "status": p.status, "error": p.error}
        for p in pages
        if p.status != "ok"
    ]

    used_snippet_fallback = False
    if not ok_pages and search_hits:
        ok_pages = _snippet_pages(search_hits)
        used_snippet_fallback = bool(ok_pages)
        meta_note = "Used search snippets because page fetches failed."
    else:
        meta_note = None

    sources = retrieve(req.query, ok_pages, top_k=min(8, max(4, max_pages)))

    answer: str | None = None
    citations: list[Citation] = []
    meta: dict = {
        "searched": bool(search_hits),
        "search_hit_count": len(search_hits),
        "pages_fetched": len(pages),
        "pages_ok": len([p for p in pages if p.status == "ok" and p.content]),
        "snippet_fallback": used_snippet_fallback,
        "page_errors": failed_pages[:10],
        "domains": domains,
        "direct_urls": direct_urls,
        "model": settings.openrouter_model if req.synthesize else None,
        "note": meta_note,
    }

    if req.synthesize:
        if not sources:
            detail = ""
            if failed_pages:
                first = failed_pages[0]
                detail = f" First failure: {first.get('status')} — {first.get('error')}"
            answer = (
                "No usable content was retrieved from the allowed sites. "
                "Try broader domains, different URLs, or enable web search."
                + detail
            )
        else:
            context = format_context(sources)
            try:
                answer = await chat_completion(
                    settings,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"Question: {req.query}\n\n"
                                f"Sources:\n{context}\n\n"
                                "Write a cited answer."
                            ),
                        },
                    ],
                )
            except OpenRouterError as exc:
                meta["synthesize_error"] = str(exc)
                answer = None

            seen_urls: set[str] = set()
            for idx, s in enumerate(sources, start=1):
                if s.url in seen_urls:
                    continue
                seen_urls.add(s.url)
                citations.append(Citation(index=idx, url=s.url, title=s.title))

    return ResearchResponse(
        query=req.query,
        answer=answer,
        citations=citations,
        sources=sources,
        pages=pages if req.include_raw else [],
        meta=meta,
    )
