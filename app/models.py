from typing import Any

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User research question")
    sites: list[str] = Field(
        default_factory=list,
        description=(
            "Restrict research to these domains or URLs only. "
            "Examples: ['docs.python.org', 'https://example.com/guide']"
        ),
    )
    max_results: int = Field(default=6, ge=1, le=20, description="Max pages to retrieve")
    synthesize: bool = Field(
        default=True,
        description="If true, use OpenRouter to produce a cited answer (requires API key)",
    )
    include_raw: bool = Field(
        default=False,
        description="Include full extracted page text in the response",
    )
    search_web: bool = Field(
        default=True,
        description=(
            "If true and sites are domains (not full URLs), run site-restricted web search. "
            "If false, only fetch the provided URLs."
        ),
    )


class SourceChunk(BaseModel):
    url: str
    title: str
    snippet: str
    score: float = 0.0
    char_start: int | None = None
    char_end: int | None = None


class PageDocument(BaseModel):
    url: str
    title: str
    content: str
    status: str = "ok"
    error: str | None = None


class Citation(BaseModel):
    index: int
    url: str
    title: str


class ResearchResponse(BaseModel):
    query: str
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    sources: list[SourceChunk] = Field(default_factory=list)
    pages: list[PageDocument] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    openrouter_configured: bool
    model: str
