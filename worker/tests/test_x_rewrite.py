"""Tests for the manual X/Twitter assistant routes and rewrite helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import IngestConfig
from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# /x/stories
# ---------------------------------------------------------------------------

def test_x_stories_returns_recent_inbox_stories():
    story_id = uuid.uuid4()
    item_id = uuid.uuid4()
    stories = [
        {
            "id": story_id,
            "headline": "Fed holds rates steady",
            "status": "inbox",
            "channel_id": "finance",
            "created_at": "2026-08-20T10:00:00",
            "score": None,
            "angle": None,
            "vertical": None,
            "content_archetype": None,
            "items": [
                {
                    "id": item_id,
                    "title": "Fed holds rates steady at 5.25-5.50%",
                    "url": "https://example.com/fed",
                    "source_name": "Reuters",
                    "published_at": "2026-08-20T09:00:00",
                }
            ],
        }
    ]

    with patch("app.config.get_ingest_config", AsyncMock(return_value=IngestConfig())), \
         patch("app.db.get_pending_stories", AsyncMock(return_value=stories)) as mock_get:
        resp = client.get("/x/stories")

    assert resp.status_code == 200
    mock_get.assert_awaited_once_with(fresh_hours=48, order="recent")
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(story_id)
    assert body[0]["items"][0]["id"] == str(item_id)


# ---------------------------------------------------------------------------
# /x/rewrite
# ---------------------------------------------------------------------------

def test_x_rewrite_returns_post():
    story_id = str(uuid.uuid4())
    with patch(
        "app.x.rewrite.rewrite_story_to_post", AsyncMock(return_value="Markets digest the Fed pause.")
    ) as mock_rewrite:
        resp = client.post("/x/rewrite", json={"story_id": story_id, "tone": "concise"})

    assert resp.status_code == 200
    assert resp.json() == {"post": "Markets digest the Fed pause."}
    mock_rewrite.assert_awaited_once_with(story_id=uuid.UUID(story_id), tone="concise")


def test_x_rewrite_rejects_invalid_story_id():
    resp = client.post("/x/rewrite", json={"story_id": "not-a-uuid"})
    assert resp.status_code == 400
    assert "invalid story_id" in resp.json()["detail"]


def test_x_rewrite_maps_rewrite_error_to_400():
    story_id = str(uuid.uuid4())
    with patch(
        "app.x.rewrite.rewrite_story_to_post",
        AsyncMock(side_effect=Exception("provider returned 300 characters; max is 280")),
    ):
        resp = client.post("/x/rewrite", json={"story_id": story_id})

    assert resp.status_code == 502
    assert "max is 280" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /x/reply
# ---------------------------------------------------------------------------

def test_x_reply_returns_reply():
    with patch(
        "app.x.rewrite.suggest_reply", AsyncMock(return_value="Good question — yield curves reflect expectations, not guarantees.")
    ) as mock_reply:
        resp = client.post(
            "/x/reply",
            json={
                "comment": "What does the yield curve tell us?",
                "post_context": "Markets digest the Fed pause.",
                "tone": "educational",
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {"reply": "Good question — yield curves reflect expectations, not guarantees."}
    mock_reply.assert_awaited_once_with(
        comment_text="What does the yield curve tell us?",
        post_context="Markets digest the Fed pause.",
        tone="educational",
    )


def test_x_reply_rejects_empty_comment():
    from app.x.rewrite import RewriteError

    with patch("app.x.rewrite.suggest_reply", AsyncMock(side_effect=RewriteError("comment text is required"))):
        resp = client.post("/x/reply", json={"comment": "   "})

    assert resp.status_code == 400
    assert "comment text" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# rewrite.py helpers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rewrite_story_to_post_compliance_blocks_advice(monkeypatch):
    from app.x import rewrite

    async def fake_fetch(_story_id):
        return {"headline": "Stock tips", "items": []}

    async def fake_llm(_system, _user):
        return "You should buy this stock now."

    monkeypatch.setattr(rewrite, "_fetch_story_with_items", fake_fetch)
    monkeypatch.setattr(rewrite, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(rewrite.RewriteError, match="blocked term"):
        await rewrite.rewrite_story_to_post(uuid.uuid4())


@pytest.mark.asyncio
async def test_rewrite_story_to_post_truncates_quotes(monkeypatch):
    from app.x import rewrite

    async def fake_fetch(_story_id):
        return {"headline": "Fed pause", "items": []}

    async def fake_llm(_system, _user):
        return '"Markets digest the Fed pause."'

    monkeypatch.setattr(rewrite, "_fetch_story_with_items", fake_fetch)
    monkeypatch.setattr(rewrite, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    result = await rewrite.rewrite_story_to_post(uuid.uuid4())
    assert result == "Markets digest the Fed pause."


@pytest.mark.asyncio
async def test_suggest_reply_enforces_max_length(monkeypatch):
    from app.x import rewrite

    async def fake_llm(_system, _user):
        return "x" * 281

    monkeypatch.setattr(rewrite, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(rewrite.RewriteError, match="max is 280"):
        await rewrite.suggest_reply("What do you think?")
