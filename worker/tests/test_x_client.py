"""Tests for the X/Twitter OAuth 1.0a client."""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest

from app.x import client


def _mock_response(status_code: int, json_body: dict | None = None, text: str = "") -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    if json_body is not None:
        response.json.return_value = json_body
    else:
        response.json.side_effect = Exception("not json")
    response.text = text
    return response


@pytest.fixture(autouse=True)
def _set_x_env(monkeypatch):
    monkeypatch.setenv("FCE_X_API_KEY", "api-key")
    monkeypatch.setenv("FCE_X_API_SECRET", "api-secret")
    monkeypatch.setenv("FCE_X_ACCESS_TOKEN", "access-token")
    monkeypatch.setenv("FCE_X_ACCESS_TOKEN_SECRET", "access-token-secret")


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
async def test_publish_text_success():
    fake_session = MagicMock()
    fake_session.post.return_value = _mock_response(
        HTTPStatus.CREATED,
        {"data": {"id": "12345", "text": "hello"}},
    )

    with patch("app.x.client.OAuth1Session", return_value=fake_session):
        result = await client.publish_text("hello")

    assert result["tweet_id"] == "12345"
    assert result["url"] == "https://x.com/i/web/status/12345"
    assert result["text"] == "hello"
    fake_session.post.assert_called_once_with(
        "https://api.twitter.com/2/tweets",
        json={"text": "hello"},
        timeout=client.REQUEST_TIMEOUT_SECONDS,
    )


@pytest.mark.asyncio
async def test_publish_text_missing_credential(monkeypatch):
    monkeypatch.delenv("FCE_X_ACCESS_TOKEN", raising=False)

    with pytest.raises(client.XPublishError, match="not set"):
        await client.publish_text("hello")


@pytest.mark.asyncio
async def test_publish_text_api_error_not_retryable():
    fake_session = MagicMock()
    fake_session.post.return_value = _mock_response(
        HTTPStatus.UNAUTHORIZED,
        {"errors": [{"message": "Unauthorized"}]},
    )

    with patch("app.x.client.OAuth1Session", return_value=fake_session):
        with pytest.raises(client.XPublishError) as exc_info:
            await client.publish_text("hello")

    assert exc_info.value.status_code == 401
    assert not exc_info.value.retryable


@pytest.mark.asyncio
async def test_publish_text_api_rate_limit_is_retryable():
    fake_session = MagicMock()
    fake_session.post.return_value = _mock_response(
        HTTPStatus.TOO_MANY_REQUESTS,
        {"errors": [{"message": "Too Many Requests"}]},
    )

    with patch("app.x.client.OAuth1Session", return_value=fake_session):
        with pytest.raises(client.XPublishError) as exc_info:
            await client.publish_text("hello")

    assert exc_info.value.status_code == 429
    assert exc_info.value.retryable


@pytest.mark.asyncio
async def test_publish_text_missing_id_in_response():
    fake_session = MagicMock()
    fake_session.post.return_value = _mock_response(
        HTTPStatus.CREATED,
        {"data": {}},
    )

    with patch("app.x.client.OAuth1Session", return_value=fake_session):
        with pytest.raises(client.XPublishError, match="missing tweet id"):
            await client.publish_text("hello")
