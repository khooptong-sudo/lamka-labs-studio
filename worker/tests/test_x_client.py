"""Tests for the X/Twitter API client."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.x import client


class TestValidateText:
    def test_empty_text_rejected(self):
        with pytest.raises(client.XPublishError, match="required"):
            client.validate_text("")

    def test_whitespace_only_rejected(self):
        with pytest.raises(client.XPublishError, match="required"):
            client.validate_text("   ")

    def test_long_text_rejected(self):
        with pytest.raises(client.XPublishError, match="max is 280"):
            client.validate_text("x" * 281)

    def test_exactly_280_accepted(self):
        client.validate_text("x" * 280)


@pytest.mark.asyncio
@respx.mock
async def test_publish_text_success(monkeypatch):
    monkeypatch.setenv("FCE_X_ACCESS_TOKEN", "test-token")

    route = respx.post("https://api.twitter.com/2/tweets").mock(
        return_value=Response(201, json={"data": {"id": "12345", "text": "hello"}})
    )

    result = await client.publish_text("hello")

    assert result["tweet_id"] == "12345"
    assert result["url"] == "https://x.com/i/web/status/12345"
    assert result["text"] == "hello"
    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-token"
    import json
    assert json.loads(request.content) == {"text": "hello"}


@pytest.mark.asyncio
async def test_publish_text_missing_token(monkeypatch):
    monkeypatch.delenv("FCE_X_ACCESS_TOKEN", raising=False)

    with pytest.raises(client.XPublishError, match="not set"):
        await client.publish_text("hello")


@pytest.mark.asyncio
@respx.mock
async def test_publish_text_api_error_not_retryable(monkeypatch):
    monkeypatch.setenv("FCE_X_ACCESS_TOKEN", "test-token")

    respx.post("https://api.twitter.com/2/tweets").mock(
        return_value=Response(401, json={"errors": [{"message": "Unauthorized"}]})
    )

    with pytest.raises(client.XPublishError) as exc_info:
        await client.publish_text("hello")

    assert exc_info.value.status_code == 401
    assert not exc_info.value.retryable


@pytest.mark.asyncio
@respx.mock
async def test_publish_text_api_rate_limit_is_retryable(monkeypatch):
    monkeypatch.setenv("FCE_X_ACCESS_TOKEN", "test-token")

    respx.post("https://api.twitter.com/2/tweets").mock(
        return_value=Response(429, json={"errors": [{"message": "Too Many Requests"}]})
    )

    with pytest.raises(client.XPublishError) as exc_info:
        await client.publish_text("hello")

    assert exc_info.value.status_code == 429
    assert exc_info.value.retryable


@pytest.mark.asyncio
@respx.mock
async def test_publish_text_missing_id_in_response(monkeypatch):
    monkeypatch.setenv("FCE_X_ACCESS_TOKEN", "test-token")

    respx.post("https://api.twitter.com/2/tweets").mock(
        return_value=Response(201, json={"data": {}})
    )

    with pytest.raises(client.XPublishError, match="missing tweet id"):
        await client.publish_text("hello")
