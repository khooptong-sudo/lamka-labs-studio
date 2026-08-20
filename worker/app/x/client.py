"""X/Twitter API v2 write client using OAuth 1.0a user context.

OAuth 1.0a Access Tokens do not expire, which removes the refresh-token
maintenance that OAuth 2.0 user context would require for a server-side bot.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import structlog
from requests_oauthlib import OAuth1Session

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


def _require_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise XPublishError(f"{key} is not set", retryable=False)
    return value


def _oauth1_session() -> OAuth1Session:
    """Build a requests-oauthlib session with the four OAuth 1.0a credentials."""
    return OAuth1Session(
        client_key=_require_env("FCE_X_API_KEY"),
        client_secret=_require_env("FCE_X_API_SECRET"),
        resource_owner_key=_require_env("FCE_X_ACCESS_TOKEN"),
        resource_owner_secret=_require_env("FCE_X_ACCESS_TOKEN_SECRET"),
    )


def validate_text(text: str) -> None:
    """Refuse text that cannot be a single tweet."""
    if not isinstance(text, str) or not text.strip():
        raise XPublishError("tweet text is required", retryable=False)
    if len(text) > MAX_TWEET_LENGTH:
        raise XPublishError(
            f"tweet text is {len(text)} characters; max is {MAX_TWEET_LENGTH}",
            retryable=False,
        )


def _parse_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    if status_code >= 400:
        raise XPublishError(
            f"X API returned {status_code}: {body}",
            retryable=status_code in RETRYABLE_STATUSES,
            status_code=status_code,
        )

    data = body.get("data") or {}
    tweet_id = data.get("id")
    if not tweet_id:
        raise XPublishError(
            f"X API response missing tweet id: {body}",
            retryable=False,
            status_code=status_code,
        )

    return {
        "tweet_id": tweet_id,
        "url": f"https://x.com/i/web/status/{tweet_id}",
        "text": data.get("text", ""),
    }


def _publish_text_sync(text: str) -> dict[str, Any]:
    """Synchronous tweet publish; wrapped in asyncio.to_thread by the caller."""
    session = _oauth1_session()
    response = session.post(
        f"{API_BASE}/tweets",
        json={"text": text},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text[:500]}
    return _parse_response(response.status_code, body)


async def publish_text(text: str) -> dict[str, Any]:
    """Publish a plain-text tweet.

    Returns {"tweet_id": str, "url": str, "text": str}.
    Raises XPublishError on validation or API failure.
    """
    validate_text(text)
    return await asyncio.to_thread(_publish_text_sync, text)


async def publish_with_media(text: str, media_paths: list[Path]) -> dict[str, Any]:
    """Publish a tweet with up to 4 images.

    Media upload (v1.1 chunked upload) is not implemented in this version.
    """
    raise XPublishError(
        "media posts are not implemented in this version; provide text only",
        retryable=False,
    )
