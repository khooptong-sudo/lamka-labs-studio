"""Route-level tests for the X publish endpoint (no DB)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_x_publish_returns_tweet_url():
    with patch(
        "app.x.publish.publish_post",
        AsyncMock(return_value={"draft_id": str(uuid4()), "tweet_id": "123", "url": "https://x.com/i/web/status/123"}),
    ):
        resp = client.post("/x/publish", json={"story_id": str(uuid4()), "text": "Hello X."})

    assert resp.status_code == 200
    body = resp.json()
    assert body["tweet_id"] == "123"
    assert body["url"] == "https://x.com/i/web/status/123"


def test_x_publish_rejects_invalid_story_id():
    resp = client.post("/x/publish", json={"story_id": "not-a-uuid", "text": "Hello X."})

    assert resp.status_code == 400
    assert "uuid" in resp.json()["detail"].lower()


def test_x_publish_rejects_empty_text():
    resp = client.post("/x/publish", json={"story_id": str(uuid4()), "text": ""})

    assert resp.status_code == 422


def test_x_publish_rejects_too_long_text():
    resp = client.post("/x/publish", json={"story_id": str(uuid4()), "text": "x" * 281})

    assert resp.status_code == 422


def test_x_publish_returns_400_on_compliance_error():
    from app.x.publish import XComplianceError

    with patch(
        "app.x.publish.publish_post",
        AsyncMock(side_effect=XComplianceError("blocked term: buy")),
    ):
        resp = client.post("/x/publish", json={"story_id": str(uuid4()), "text": "buy now"})

    assert resp.status_code == 400
    assert "blocked term" in resp.json()["detail"]


def test_x_publish_returns_404_on_missing_story():
    from app.x.publish import StoryNotFoundError

    with patch(
        "app.x.publish.publish_post",
        AsyncMock(side_effect=StoryNotFoundError("story not found")),
    ):
        resp = client.post("/x/publish", json={"story_id": str(uuid4()), "text": "Hello X."})

    assert resp.status_code == 404


def test_x_publish_returns_502_on_publish_error():
    from app.x import client as x_client

    with patch(
        "app.x.publish.publish_post",
        AsyncMock(side_effect=x_client.XPublishError("X API error", retryable=False)),
    ):
        resp = client.post("/x/publish", json={"story_id": str(uuid4()), "text": "Hello X."})

    assert resp.status_code == 502
