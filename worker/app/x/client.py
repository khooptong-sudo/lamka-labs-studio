"""X/Twitter API v2 write client (httpx-only, no tweepy dependency)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import structlog

log = structlog.get_logger()

API_BASE = "https://api.twitter.com/2"
MAX_TWEET_LENGTH = 280
REQUEST_TIMEOUT_SECONDS = 30

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class XPublishError(RuntimeError):
    """A tweet could not be published."""

    def __init__(self, message: str, *, retryable: bool = False, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


def _access_token() -> str:
    token = os.environ.get("FCE_X_ACCESS_TOKEN", "").strip()
    if not token:
        raise XPublishError("FCE_X_ACCESS_TOKEN is not set", retryable=False)
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
    }


def validate_text(text: str) -> None:
    """Refuse text that cannot be a single tweet."""
    if not isinstance(text, str) or not text.strip():
        raise XPublishError("tweet text is required", retryable=False)
    if len(text) > MAX_TWEET_LENGTH:
        raise XPublishError(
            f"tweet text is {len(text)} characters; max is {MAX_TWEET_LENGTH}",
            retryable=False,
        )


def _parse_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text[:500]}

    if response.status_code >= 400:
        raise XPublishError(
            f"X API returned {response.status_code}: {body}",
            retryable=response.status_code in RETRYABLE_STATUSES,
            status_code=response.status_code,
        )

    data = body.get("data") or {}
    tweet_id = data.get("id")
    if not tweet_id:
        raise XPublishError(
            f"X API response missing tweet id: {body}",
            retryable=False,
            status_code=response.status_code,
        )

    return {
        "tweet_id": tweet_id,
        "url": f"https://x.com/i/web/status/{tweet_id}",
        "text": data.get("text", ""),
    }


async def publish_text(text: str) -> dict[str, Any]:
    """Publish a plain-text tweet.

    Returns {"tweet_id": str, "url": str, "text": str}.
    Raises XPublishError on validation or API failure.
    """
    validate_text(text)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{API_BASE}/tweets",
            headers=_headers(),
            json={"text": text},
        )

    return _parse_response(response)


async def publish_with_media(text: str, media_paths: list[Path]) -> dict[str, Any]:
    """Publish a tweet with up to 4 images.

    Media upload (v1.1 chunked upload) requires OAuth 1.0a credentials, which
    are not included in the initial scope. This stub raises a clear error so
    callers know media posts are not yet supported.
    """
    raise XPublishError(
        "media posts are not implemented in this version; provide text only",
        retryable=False,
    )
