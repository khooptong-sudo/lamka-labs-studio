"""Integration tests for the X publish path (uses DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app import db
from app.x import client, publish


@pytest_asyncio.fixture
async def story(db):
    """A minimal story row to hang drafts on."""
    story_id = uuid.uuid4()
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO stories (id, headline, status) VALUES (%s, %s, 'inbox')",
            (story_id, "Test headline"),
        )
    return story_id


@pytest.fixture(autouse=True)
def _mock_audit(monkeypatch):
    """Audit logging is tested elsewhere; isolate the publish path."""
    monkeypatch.setattr(publish.audit, "audit_log", AsyncMock())


@pytest.fixture(autouse=True)
def _set_x_env(monkeypatch):
    monkeypatch.setenv("FCE_X_API_KEY", "api-key")
    monkeypatch.setenv("FCE_X_API_SECRET", "api-secret")
    monkeypatch.setenv("FCE_X_ACCESS_TOKEN", "access-token")
    monkeypatch.setenv("FCE_X_ACCESS_TOKEN_SECRET", "access-token-secret")


@pytest.mark.asyncio
async def test_publish_post_creates_published_draft(story, monkeypatch):
    async def fake_publish(text):
        return {"tweet_id": "abc123", "url": "https://x.com/i/web/status/abc123", "text": text}

    monkeypatch.setattr(client, "publish_text", fake_publish)

    result = await publish.publish_post(story_id=story, text="A compliant post.")

    assert result["tweet_id"] == "abc123"
    assert result["url"] == "https://x.com/i/web/status/abc123"

    draft = await db.get_draft(uuid.UUID(result["draft_id"]))
    assert draft["platform"] == "x"
    assert draft["format"] == "post"
    assert draft["status"] == "published"
    assert draft["published_ids"] == {"x": "abc123"}


@pytest.mark.asyncio
async def test_publish_post_allows_blocked_term_when_guardrails_disabled(story, monkeypatch):
    async def fake_publish(text):
        return {"tweet_id": "abc123", "url": "https://x.com/i/web/status/abc123", "text": text}

    monkeypatch.setattr(client, "publish_text", fake_publish)

    result = await publish.publish_post(story_id=story, text="You should buy this stock now.")
    assert result["tweet_id"] == "abc123"


@pytest.mark.asyncio
async def test_publish_post_allows_sell_term_when_guardrails_disabled(story, monkeypatch):
    async def fake_publish(text):
        return {"tweet_id": "abc123", "url": "https://x.com/i/web/status/abc123", "text": text}

    monkeypatch.setattr(client, "publish_text", fake_publish)

    result = await publish.publish_post(story_id=story, text="Sell everything before the crash.")
    assert result["tweet_id"] == "abc123"


@pytest.mark.asyncio
async def test_publish_post_marks_failed_on_api_error(story, monkeypatch):
    monkeypatch.setenv("FCE_X_ACCESS_TOKEN", "test-token")

    async def fake_publish(_text):
        raise client.XPublishError("X is down", retryable=True, status_code=503)

    monkeypatch.setattr(client, "publish_text", fake_publish)

    with pytest.raises(client.XPublishError, match="X is down"):
        await publish.publish_post(story_id=story, text="A compliant post.")

    drafts = await db.get_drafts()
    assert len(drafts) == 1
    assert drafts[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_publish_post_missing_story():
    with pytest.raises(publish.StoryNotFoundError):
        await publish.publish_post(story_id=uuid.uuid4(), text="A compliant post.")
