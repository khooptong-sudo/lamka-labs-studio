"""One call signature over the text providers this deployment actually has.

Gemini, DeepSeek, OpenAI. There is no Anthropic key and no Moonshot key here,
so the blueprint's §8 routing table (Haiku primary, Kimi for variant B) names
models that cannot be called. Adding a provider is: write an adapter, add one
PROVIDERS entry, done — callers route by task name and never see this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Awaitable, Callable

# Substring markers, matched case-insensitively against the exception text.
# Mirrors the classification `youtube.py` already applies to script generation.
RETRYABLE_MARKERS = (
    "429", "500", "502", "503", "504",
    "timeout", "timed out", "overloaded", "unavailable",
)

GEMINI_MODEL = "gemini-flash-latest"
DEEPSEEK_MODEL = "deepseek-chat"
OPENAI_MODEL = "gpt-4o-mini"

REQUEST_TIMEOUT_SECONDS = 90


class ProviderError(RuntimeError):
    """A provider call that failed, carrying its own retry classification."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def is_retryable(exc: Exception) -> bool:
    """Whether the same call is worth trying again against the same provider."""
    if isinstance(exc, ProviderError):
        return exc.retryable
    text = str(exc).lower()
    return any(marker in text for marker in RETRYABLE_MARKERS)


@dataclass(frozen=True)
class Provider:
    name: str
    env_key: str
    call: Callable[[str, str], Awaitable[str]]


async def _call_gemini(system: str, user: str) -> str:
    import asyncio

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def _sync() -> str:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return response.text or ""

    try:
        return await asyncio.to_thread(_sync)
    except Exception as exc:
        # Extract HTTP status from google-genai SDK exceptions.
        # Different error classes expose it under different attributes.
        status_code = None
        if hasattr(exc, "code"):
            status_code = exc.code
        elif hasattr(exc, "response") and hasattr(exc.response, "status_code"):
            status_code = exc.response.status_code

        # Classify by status code if available; otherwise fall back to substring matching.
        if status_code is not None:
            retryable = status_code == 429 or status_code >= 500
            raise ProviderError(str(exc), retryable=retryable) from exc
        else:
            # No status code available; let is_retryable() make the judgement.
            raise


async def _call_openai_compatible(
    *, base_url: str, api_key: str, model: str, system: str, user: str
) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
    if response.status_code >= 400:
        raise ProviderError(
            f"{response.status_code} {response.text[:200]}",
            retryable=response.status_code == 429 or response.status_code >= 500,
        )
    body = response.json()
    return body["choices"][0]["message"]["content"] or ""


async def _call_deepseek(system: str, user: str) -> str:
    return await _call_openai_compatible(
        base_url="https://api.deepseek.com/v1",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        model=DEEPSEEK_MODEL,
        system=system,
        user=user,
    )


async def _call_openai(system: str, user: str) -> str:
    return await _call_openai_compatible(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model=OPENAI_MODEL,
        system=system,
        user=user,
    )


PROVIDERS: dict[str, Provider] = {
    "gemini": Provider("gemini", "GEMINI_API_KEY", _call_gemini),
    "deepseek": Provider("deepseek", "DEEPSEEK_API_KEY", _call_deepseek),
    "openai": Provider("openai", "OPENAI_API_KEY", _call_openai),
}


def available() -> tuple[str, ...]:
    """Provider names whose API key is present and non-empty in the environment.

    Resolved here rather than discovered at call time, so a missing key is a
    routing fact rather than a runtime surprise mid-job.
    """
    return tuple(
        name for name, provider in PROVIDERS.items()
        if os.environ.get(provider.env_key, "").strip()
    )
