"""Tests for the manual poster generator."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_SUMMARY = (
    "EV/EBITDA compares a company's enterprise value with earnings before interest, taxes, depreciation and amortisation. "
    "It adds market capitalisation and debt, then subtracts cash. Investors use it to compare companies with different financing structures in the same industry. "
    "A high multiple can reflect rich expectations, while a low one may signal weaker growth or value. "
    "The ratio should be read with cash flow, debt, margins and future earnings prospects before judging a company's valuation."
)

SAMPLE_POSTER_JSON = """{
  "title": "EV/EBITDA",
  "subtitle": "What it is & why it matters",
  "summary": "EV/EBITDA compares a company's enterprise value with earnings before interest, taxes, depreciation and amortisation. It adds market capitalisation and debt, then subtracts cash. Investors use it to compare companies with different financing structures in the same industry. A high multiple can reflect rich expectations, while a low one may signal weaker growth or value. The ratio should be read with cash flow, debt, margins and future earnings prospects before judging a company's valuation.",
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

    first_half = " ".join(["First"] * 35)
    second_half = " ".join(["Second"] * 35)

    async def fake_llm(_system, _user):
        return json.dumps({"title": "T", "subtitle": "S", "summary": [first_half, second_half], "sections": [{"heading": "H", "bullets": ["B"]}], "footer": "F"})

    monkeypatch.setattr(poster, "_llm_call", fake_llm)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    result = await poster.generate_poster_from_text("Topic", ["A"])
    assert result["summary"] == f"{first_half}\n\n{second_half}"


def test_validate_poster_rejects_summary_under_min_words():
    from app.x.poster import PosterError, _validate_and_trim

    poster = {
        "title": "T",
        "subtitle": "S",
        "summary": "This is a short summary that does not contain enough words.",
        "sections": [{"heading": "H", "bullets": ["B"]}],
        "footer": "F",
    }

    with pytest.raises(PosterError, match="summary must contain at least"):
        _validate_and_trim(poster)


def test_validate_poster_preserves_paragraph_breaks():
    """A two-paragraph summary keeps its blank line so the poster can render
    the paragraphs separately instead of collapsing them into one block."""
    from app.x.poster import _validate_and_trim

    para1 = "word " * 40 + "end."
    para2 = "more " * 40 + "end."
    poster = {
        "title": "T",
        "subtitle": "S",
        "summary": f"{para1}\n\n   {para2}",
        "sections": [{"heading": "H", "bullets": ["B"]}],
        "footer": "F",
    }

    result = _validate_and_trim(poster)
    assert "\n\n" in result["summary"]
    assert result["summary"].split("\n\n")[1].startswith("more")


def test_validate_poster_trims_summary_over_char_cap():
    from app.x import poster
    from app.x.poster import _validate_and_trim

    poster_dict = {
        "title": "T",
        "subtitle": "S",
        "summary": "This is a sentence about markets. " * 60,
        "sections": [{"heading": "H", "bullets": ["B"]}],
        "footer": "F",
    }

    result = _validate_and_trim(poster_dict)
    assert len(result["summary"]) <= poster.MAX_SUMMARY_CHARS
    # The trim lands on a sentence boundary, never mid-word.
    assert result["summary"].endswith(".")


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
        return json.dumps({"title": "Buy now", "subtitle": "S", "summary": VALID_SUMMARY, "sections": [{"heading": "H", "bullets": ["You should buy this stock now"]}], "footer": "F"})

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
        return json.dumps({"title": "T", "subtitle": "S", "summary": VALID_SUMMARY, "sections": [], "footer": "F"})

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
