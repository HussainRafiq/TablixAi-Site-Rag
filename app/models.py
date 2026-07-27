from typing import Any

from pydantic import BaseModel, Field, field_validator


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User research question")
    sites: list[str] = Field(
        default_factory=list,
        description=(
            "Restrict research to these domains or URLs only. "
            "Examples: ['docs.python.org', 'https://example.com/guide']"
        ),
    )
    max_results: int = Field(default=3, ge=1, le=8, description="Max pages to retrieve")
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

    @field_validator("max_results", mode="before")
    @classmethod
    def coerce_max_results(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
        return v

    @field_validator("synthesize", "include_raw", "search_web", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> Any:
        if isinstance(v, str):
            s = v.strip().lower()
            if s in {"true", "1", "yes", "on"}:
                return True
            if s in {"false", "0", "no", "off"}:
                return False
        return v

    @field_validator("sites", mode="before")
    @classmethod
    def coerce_sites(cls, v: Any) -> Any:
        import json
        import re

        if v is None or v == "":
            return []

        if isinstance(v, str):
            s = v.strip()
            # n8n often sends a JSON array as a string: '["tablixai.com"]'
            if (s.startswith("[") and s.endswith("]")) or (
                s.startswith("{") and s.endswith("}")
            ):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        v = parsed
                    elif isinstance(parsed, dict):
                        v = list(parsed.values())
                    else:
                        v = [s]
                except json.JSONDecodeError:
                    # strip brackets/quotes manually
                    inner = s.strip("[]")
                    v = [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
            else:
                v = [p.strip().strip("'\"") for p in s.split(",") if p.strip()]

        if isinstance(v, list):
            cleaned: list[str] = []
            for item in v:
                if item is None:
                    continue
                text = str(item).strip().strip("'\"")
                text = re.sub(r"^\[+|\]+$", "", text).strip().strip("'\"")
                if text:
                    cleaned.append(text)
            return cleaned

        return v


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
    busy: bool = False
