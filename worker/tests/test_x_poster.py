"""Tests for the manual poster generator."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


SAMPLE_POSTER_JSON = """{
  "title": "EV/EBITDA",
  "subtitle": "What it is & why it matters",
  "summary": "EV/EBITDA compares the total value of a company to its earnings before interest, taxes, depreciation and amortisation. Analysts use it to screen for valuation across companies with different debt loads. A higher ratio can point to overvaluation.",
  "sections": [
    {"heading": "What is it?", "bullets": ["EV = Market Cap + Debt - Cash", "EBITDA = earnings before interest and taxes"]},
    {"heading": "Why use it?", "bullets": ["Useful for comparing valuation over time", "Helps spot overvaluation"]}
  ],
  "footer": "For educational purposes only."
}"""


def test_poster_from_story_returns_poster():
    story_id = str(uuid.uuid4())
    with patch(
        "app.x.poster.generate_poster_from_story",
        AsyncMock(return_value={"title": "T", "subtitle": "S", "summary": ["A"], "sections": [], "footer": "F", "style": "light"}),
    ) as mock_gen:
        resp = client.post("/x/poster/story", json={"story_id": story_id, "style": "dark"})

    assert resp.status_code == 200
    mock_gen.assert_awaited_once_with(story_id=uuid.UUID(story_id), style="dark")


def test_poster_from_story_rejects_invalid_story_id():
    resp = client.post("/x/poster/story", json={"story_id": "not-a-uuid"})
    assert resp.status_code == 400
    assert "invalid story_id" in resp.json()["detail"]


def test_poster_from_text_returns_poster():
    with patch(
        "app.x.poster.generate_poster_from_text",
        AsyncMock(return_value={"title": "T", "subtitle": "S", "summary": ["A"], "sections": [], "footer": "F", "style": "light"}),
    ) as mock_gen:
        resp = client.post(
            "/x/poster/text",
            json={"topic": "CAGR", "bullets": ["Compound growth rate", "Smooths returns"], "style": "dark"},
        )

    assert resp.status_code == 200
    mock_gen.assert_awaited_once_with(topic="CAGR", bullets=["Compound growth rate", "Smooths returns"], style="dark")


def test_poster_from_text_rejects_empty_topic():
    resp = client.post("/x/poster/text", json={"topic": "", "bullets": []})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_poster_from_text_parses_json(monkeypatch):
    from app.x import poster

    async def fake_llm(_system, _user):
        return SAMPLE_POSTER_JSON

    monkeypatch.setattr(poster, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    result = await poster.generate_poster_from_text("EV/EBITDA", ["A", "B"])
    assert result["title"] == "EV/EBITDA"
    assert len(result["sections"]) == 2
    assert result["style"] == "light"
    assert result["summary"].startswith("EV/EBITDA compares")


@pytest.mark.asyncio
async def test_generate_poster_normalises_list_summary(monkeypatch):
    """A provider that returns the old bullet-list shape still yields a paragraph."""
    from app.x import poster

    async def fake_llm(_system, _user):
        return '{"title":"T","subtitle":"S","summary":["First point.","Second point."],"sections":[{"heading":"H","bullets":["B"]}],"footer":"F"}'

    monkeypatch.setattr(poster, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    result = await poster.generate_poster_from_text("Topic", ["A"])
    assert result["summary"] == "First point. Second point."


@pytest.mark.asyncio
async def test_generate_poster_rejects_blank_summary(monkeypatch):
    """An empty string must fail rather than render an empty At a Glance box."""
    from app.x import poster

    async def fake_llm(_system, _user):
        return '{"title":"T","subtitle":"S","summary":"   ","sections":[{"heading":"H","bullets":["B"]}],"footer":"F"}'

    monkeypatch.setattr(poster, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(poster.PosterError, match="missing summary"):
        await poster.generate_poster_from_text("Topic", ["A"])


@pytest.mark.asyncio
async def test_generate_poster_from_text_allows_advice_when_guardrails_disabled(monkeypatch):
    from app.x import poster

    async def fake_llm(_system, _user):
        return '{"title":"Buy now","subtitle":"S","summary":["A"],"sections":[{"heading":"H","bullets":["You should buy this stock now"]}],"footer":"F"}'

    monkeypatch.setattr(poster, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    # Guardrails are currently disabled, so previously-blocked terms pass through.
    result = await poster.generate_poster_from_text("Topic", ["A"])
    assert result["title"] == "Buy now"


@pytest.mark.asyncio
async def test_generate_poster_from_text_rejects_non_object_json(monkeypatch):
    from app.x import poster

    async def fake_llm(_system, _user):
        return "[1, 2, 3]"

    monkeypatch.setattr(poster, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(poster.PosterError, match="did not return JSON"):
        await poster.generate_poster_from_text("Topic", ["A"])


@pytest.mark.asyncio
async def test_generate_poster_from_text_rejects_missing_sections(monkeypatch):
    from app.x import poster

    async def fake_llm(_system, _user):
        return '{"title":"T","subtitle":"S","summary":["A"],"sections":[],"footer":"F"}'

    monkeypatch.setattr(poster, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(poster.PosterError, match="missing sections"):
        await poster.generate_poster_from_text("Topic", ["A"])


@pytest.mark.asyncio
async def test_generate_poster_from_text_rejects_missing_summary(monkeypatch):
    from app.x import poster

    async def fake_llm(_system, _user):
        return '{"title":"T","subtitle":"S","sections":[{"heading":"H","bullets":["B"]}],"footer":"F"}'

    monkeypatch.setattr(poster, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with pytest.raises(poster.PosterError, match="missing summary"):
        await poster.generate_poster_from_text("Topic", ["A"])
