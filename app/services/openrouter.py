"""OpenRouter chat client for answer synthesis."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class OpenRouterError(RuntimeError):
    pass


async def chat_completion(
    settings: Settings,
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str:
    if not settings.openrouter_api_key.strip():
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file "
            "(get a key at https://openrouter.ai/keys)."
        )

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tablix.ai",
        "X-Title": "Tablix Web RAG",
    }
    payload: dict[str, Any] = {
        "model": settings.openrouter_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens or settings.openrouter_max_tokens,
    }

    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    timeout = httpx.Timeout(settings.openrouter_timeout)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise OpenRouterError(
                f"OpenRouter error {resp.status_code}: {resp.text[:500]}"
            )
        data = resp.json()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenRouterError(f"Unexpected OpenRouter response: {data}") from exc
