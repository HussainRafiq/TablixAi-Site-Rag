import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.models import HealthResponse, ResearchRequest, ResearchResponse
from app.services.research import run_research

router = APIRouter()

# One research job at a time — prevents OOM on ~1GB hosts shared with n8n.
_research_lock = asyncio.Lock()


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        openrouter_configured=bool(settings.openrouter_api_key.strip()),
        model=settings.openrouter_model,
        busy=_research_lock.locked(),
    )


@router.post("/research", response_model=ResearchResponse)
async def research(
    body: ResearchRequest,
    settings: Settings = Depends(get_settings),
) -> ResearchResponse:
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    if body.synthesize and not settings.openrouter_api_key.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "OPENROUTER_API_KEY is missing. Add it to .env "
                "(https://openrouter.ai/keys), or set synthesize=false "
                "to return retrieved sources only."
            ),
        )

    if _research_lock.locked():
        raise HTTPException(
            status_code=429,
            detail=(
                "Another research job is already running. "
                "Retry in a few seconds (server is memory-constrained)."
            ),
        )

    async with _research_lock:
        try:
            return await asyncio.wait_for(
                run_research(body, settings),
                timeout=settings.research_timeout,
            )
        except TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail=(
                    f"Research timed out after {settings.research_timeout:.0f}s. "
                    "Lower max_results or disable synthesize."
                ),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid request values: {exc}",
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=f"Research failed: {type(exc).__name__}: {exc}",
            ) from exc
