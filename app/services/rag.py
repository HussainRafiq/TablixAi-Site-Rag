"""Chunking + BM25 retrieval over extracted pages (lightweight web RAG)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.models import PageDocument, SourceChunk


@dataclass
class TextChunk:
    url: str
    title: str
    text: str
    char_start: int
    char_end: int


_TOKEN = re.compile(r"[a-z0-9]+", re.I)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def chunk_text(text: str, *, size: int = 900, overlap: int = 120) -> list[tuple[int, int, str]]:
    if not text:
        return []
    chunks: list[tuple[int, int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            # prefer break on sentence/whitespace
            window = text[start:end]
            cut = max(window.rfind(". "), window.rfind("\n"), window.rfind(" "))
            if cut > size // 3:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append((start, end, piece))
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_chunks(pages: list[PageDocument]) -> list[TextChunk]:
    out: list[TextChunk] = []
    for page in pages:
        if page.status != "ok" or not page.content:
            continue
        for start, end, piece in chunk_text(page.content):
            out.append(
                TextChunk(
                    url=page.url,
                    title=page.title,
                    text=piece,
                    char_start=start,
                    char_end=end,
                )
            )
    return out


def retrieve(
    query: str,
    pages: list[PageDocument],
    *,
    top_k: int = 8,
) -> list[SourceChunk]:
    chunks = build_chunks(pages)
    if not chunks:
        return []

    corpus = [tokenize(c.text) for c in chunks]
    # guard empty docs
    if all(len(t) == 0 for t in corpus):
        return [
            SourceChunk(
                url=c.url,
                title=c.title,
                snippet=c.text[:400],
                score=0.0,
                char_start=c.char_start,
                char_end=c.char_end,
            )
            for c in chunks[:top_k]
        ]

    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:top_k]

    results: list[SourceChunk] = []
    for i in ranked:
        c = chunks[i]
        results.append(
            SourceChunk(
                url=c.url,
                title=c.title,
                snippet=c.text[:500],
                score=float(scores[i]),
                char_start=c.char_start,
                char_end=c.char_end,
            )
        )
    return results


def format_context(sources: list[SourceChunk]) -> str:
    blocks: list[str] = []
    for idx, s in enumerate(sources, start=1):
        blocks.append(
            f"[{idx}] Title: {s.title}\nURL: {s.url}\nExcerpt:\n{s.snippet}"
        )
    return "\n\n---\n\n".join(blocks)
