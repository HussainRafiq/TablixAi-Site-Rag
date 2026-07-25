from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.research import router as research_router

app = FastAPI(
    title="Tablix Web RAG",
    description=(
        "Browserless web research API: site-scoped search, content extraction, "
        "BM25 retrieval, and OpenRouter answer synthesis (Tavily/Exa/Firecrawl-style)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(research_router, tags=["research"])


@app.get("/")
async def root():
    return {
        "service": "Tablix Web RAG",
        "docs": "/docs",
        "endpoints": {
            "POST /research": "Query + optional site allowlist → cited research",
            "GET /health": "Health + OpenRouter config status",
        },
    }
