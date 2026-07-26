"""Orchestrates search → fetch → retrieve → synthesize (web RAG pipeline)."""

from __future__ import annotations

import logging

from app.config import Settings
from app.models import Citation, ResearchRequest, ResearchResponse
from app.services.extractor import fetch_pages
from app.services.openrouter import OpenRouterError, chat_completion
from app.services.rag import format_context, retrieve
from app.services.search import search_web, split_sites, url_allowed

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a careful research assistant performing grounded web RAG.
Answer ONLY using the provided source excerpts.
Cite sources inline with [n] markers that match the excerpt numbers.
If the sources are insufficient, say what is missing instead of inventing facts.
Be concise, structured, and specific."""


async def run_research(req: ResearchRequest, settings: Settings) -> ResearchResponse:
    direct_urls, domains = split_sites(req.sites)
    max_pages = min(req.max_results, settings.max_pages)

    candidate_urls: list[str] = list(direct_urls)
    search_hits = []

    if req.search_web:
        # If only full URLs were given and no domains, still allow open web unless
        # sites were provided as a hard allowlist of URLs-only.
        do_search = True
        if req.sites and not domains and direct_urls:
            # User gave only specific endpoints — do not expand via open web
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

    # Cap pages
    candidate_urls = candidate_urls[: max(max_pages, len(direct_urls))]

    pages = (
        await fetch_pages(candidate_urls, settings, concurrency=2)
        if candidate_urls
        else []
    )
    ok_pages = [p for p in pages if p.status == "ok" and p.content]
    failed_pages = [
        {"url": p.url, "status": p.status, "error": p.error}
        for p in pages
        if p.status != "ok"
    ]

    sources = retrieve(req.query, ok_pages, top_k=min(8, max(4, max_pages)))

    answer: str | None = None
    citations: list[Citation] = []
    meta: dict = {
        "searched": bool(search_hits),
        "search_hit_count": len(search_hits),
        "pages_fetched": len(pages),
        "pages_ok": len(ok_pages),
        "page_errors": failed_pages[:10],
        "domains": domains,
        "direct_urls": direct_urls,
        "model": settings.openrouter_model if req.synthesize else None,
    }

    if req.synthesize:
        if not sources:
            detail = ""
            if failed_pages:
                first = failed_pages[0]
                detail = f" First failure: {first.get('status')} {first.get('error')}"
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

            # Build citation list from retrieved sources
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
