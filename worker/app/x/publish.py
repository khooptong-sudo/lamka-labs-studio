"""X/Twitter publish path: validate, draft, post, audit."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import structlog

from app import audit, db
from app.channels import BASE_BLOCKLIST
from app.x import client

log = structlog.get_logger()

PLATFORM = "x"
FORMAT = "post"


class XComplianceError(ValueError):
    """Text violates the channel's immutable compliance/blocklist rules."""


class StoryNotFoundError(ValueError):
    """The referenced story does not exist."""


async def _fetch_story(story_id: uuid.UUID) -> dict[str, Any]:
    pool = await db.get_pool()
    async with pool.connection() as conn:
        row = await db._fetchone(
            conn,
            "SELECT id, headline, status FROM stories WHERE id = %s",
            story_id,
        )
    if row is None:
        raise StoryNotFoundError(f"story {story_id} not found")
    return row


def _check_compliance(text: str) -> None:
    """Apply the same base blocklist used for video scripts.

    X posts are shorter, but the financial-advice prohibition is the same.
    """
    lowered = text.lower()
    blocked = [term for term in BASE_BLOCKLIST if term.lower() in lowered]
    if blocked:
        raise XComplianceError(
            f"text contains blocked term(s): {', '.join(blocked)}"
        )


async def publish_post(
    story_id: uuid.UUID,
    text: str,
    media_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Publish a post to X for a given story.

    Steps:
      1. Story exists.
      2. Text passes blocklist/compliance checks and length rules.
      3. Draft row created as 'pending'.
      4. X API called.
      5. Draft updated to 'published' with tweet id, or 'failed' on error.

    Returns {"draft_id": str, "tweet_id": str, "url": str}.
    """
    story = await _fetch_story(story_id)

    try:
        client.validate_text(text)
        _check_compliance(text)
    except client.XPublishError as exc:
        # Validation failures are caller errors, not publish failures.
        raise XComplianceError(str(exc)) from exc

    draft_id = await db.create_draft(
        story_id=story_id,
        platform=PLATFORM,
        format=FORMAT,
        body={"text": text, "media_paths": [str(p) for p in (media_paths or [])]},
        status="pending",
    )
    log.info("x_draft_created", draft_id=str(draft_id), story_id=str(story_id))

    try:
        if media_paths:
            result = await client.publish_with_media(text, media_paths)
        else:
            result = await client.publish_text(text)
    except client.XPublishError as exc:
        await db.update_draft_published(
            draft_id,
            status="failed",
            published_ids={"error": str(exc)},
        )
        await audit.audit_log(
            actor="system",
            action="x_publish_failed",
            entity=draft_id,
            entity_type="draft",
            before={"text": text},
            after={"error": str(exc), "retryable": exc.retryable},
        )
        log.error("x_publish_failed", draft_id=str(draft_id), error=str(exc))
        raise

    published_ids = {"x": result["tweet_id"]}
    await db.update_draft_published(
        draft_id,
        status="published",
        published_ids=published_ids,
    )
    await audit.audit_log(
        actor="system",
        action="x_publish_succeeded",
        entity=draft_id,
        entity_type="draft",
        before={"text": text, "status": "pending"},
        after={"status": "published", "published_ids": published_ids},
    )
    log.info(
        "x_publish_succeeded",
        draft_id=str(draft_id),
        tweet_id=result["tweet_id"],
    )

    return {
        "draft_id": str(draft_id),
        "tweet_id": result["tweet_id"],
        "url": result["url"],
    }
