"""Task-to-provider routing with retry, fallback, and a single repair attempt.

Callers name a *task*, never a model. That indirection is what makes decision
#4 ("model router config-driven") real: re-pointing `story_score` at another
provider is a config edit, and no caller changes.

This module is also the seam every test patches. Recorded bug #13: mocking one
layer further down let a backend route around the mock and fire live HTTP.
"""

from __future__ import annotations

import asyncio

import structlog

from app.config import get_llm_config
from app.llm import contract, providers

log = structlog.get_logger()

DEFAULT_MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2


class RouterError(RuntimeError):
    """No provider could satisfy the task. There is no fallback value."""


def _backoff(attempt: int) -> float:
    return BACKOFF_BASE_SECONDS * attempt


async def _resolve(task: str) -> list[str]:
    """Ordered, usable provider names for a task. Empty means unroutable."""
    cfg = await get_llm_config()
    route = cfg.routing.get(task)
    if route is None:
        return []
    have = providers.available()
    chain = [route.get("primary"), route.get("fallback")]
    return [name for name in chain if name and name in have]


async def complete_json(
    task: str,
    *,
    system: str,
    user: str,
    spec: contract.FieldSpec,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict:
    """Run `task` until a provider returns a payload satisfying `spec`.

    Raises RouterError when every routed provider is exhausted. It never
    returns a default, a stub, or a partially-populated dict (decision #41,
    generalized from script generation to every LLM call in the worker).
    """
    chain = await _resolve(task)
    if not chain:
        raise RouterError(f"no available provider for task {task!r}")

    last_error: Exception | None = None

    for provider_name in chain:
        provider = providers.PROVIDERS[provider_name]
        prompt = user
        repaired = False

        for attempt in range(1, max_attempts + 1):
            try:
                raw = await provider.call(system, prompt)
            except Exception as exc:  # noqa: BLE001 — classified immediately below
                last_error = exc
                if not providers.is_retryable(exc):
                    log.warning(
                        "llm_provider_terminal",
                        task=task, provider=provider_name, error=str(exc),
                    )
                    break
                log.warning(
                    "llm_provider_retry",
                    task=task, provider=provider_name, attempt=attempt, error=str(exc),
                )
                await asyncio.sleep(_backoff(attempt))
                continue

            try:
                return contract.parse(raw, spec)
            except contract.ContractError as exc:
                last_error = exc
                if repaired:
                    log.warning(
                        "llm_repair_failed",
                        task=task, provider=provider_name, error=str(exc),
                    )
                    break
                prompt = (
                    f"{user}\n\n"
                    f"Your previous reply was rejected: {exc}\n"
                    f"Return only corrected JSON. No prose, no markdown fence."
                )
                repaired = True

    raise RouterError(
        f"task {task!r} exhausted every provider in {chain}"
    ) from last_error
