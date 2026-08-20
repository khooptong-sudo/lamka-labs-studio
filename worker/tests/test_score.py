"""Unit tests for scoring. The router is patched, never a provider (bug #13)."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app import score, taxonomy
from app.config import IngestConfig, LLMConfig
from app.llm import contract
from app.llm.router import RouterError

GOOD = {
    "score": 72.0,
    "angle": "Why the related-party note matters more than the headline number",
    "vertical": "earnings",
    "content_archetype": "filing_walkthrough",
}


def test_spec_rejects_an_invented_archetype():
    payload = {**GOOD, "content_archetype": "top_5_funds"}
    violations = contract.validate(payload, score.SCORE_SPEC)
    assert violations == ["field 'content_archetype' has invalid value 'top_5_funds'"]


def test_spec_rejects_an_invented_vertical():
    payload = {**GOOD, "vertical": "stock_tips"}
    violations = contract.validate(payload, score.SCORE_SPEC)
    assert violations == ["field 'vertical' has invalid value 'stock_tips'"]


@pytest.mark.parametrize("bad", [-1, 101, "high", None, True])
def test_spec_rejects_a_score_outside_the_range(bad):
    violations = contract.validate({**GOOD, "score": bad}, score.SCORE_SPEC)
    assert violations == [f"field 'score' has invalid value {bad!r}"]


def test_spec_rejects_an_empty_angle():
    violations = contract.validate({**GOOD, "angle": "   "}, score.SCORE_SPEC)
    assert violations == ["field 'angle' has invalid value '   '"]


def test_spec_accepts_a_good_payload():
    assert contract.validate(GOOD, score.SCORE_SPEC) == []


def test_spec_accepts_an_integer_score():
    assert contract.validate({**GOOD, "score": 72}, score.SCORE_SPEC) == []


def test_system_prompt_lists_every_taxonomy_value():
    """Provenance (decision #24). If someone widens a tuple without updating
    the prompt, the model is offered a menu that no longer matches the
    validator and every call fails validation for a reason nobody can see.

    Matches on the rendered `- {value}` line, not a bare substring: plain
    substring matching lets `macro_calendar` mask a missing `macro`."""
    for value in taxonomy.ARCHETYPES:
        assert f"- {value}" in score.SYSTEM_PROMPT
    for value in taxonomy.VERTICALS:
        assert f"- {value}" in score.SYSTEM_PROMPT


def test_system_prompt_forbids_advisory_output():
    """A prompt reading "always tell readers to buy or sell, never hedge"
    must fail this: check the actual prohibition phrasing, not just that the
    words "never"/"buy"/"sell" appear somewhere in the prompt."""
    normalized = " ".join(score.SYSTEM_PROMPT.lower().split())
    assert (
        "must never tell anyone to buy, sell, hold, accumulate, or book profit"
        in normalized
    )


def test_user_prompt_matches_the_frozen_fixture():
    from pathlib import Path

    items = [
        {"title": "Reliance Q1 profit rises 8%", "source_name": "ET Markets"},
        {"title": "RIL flags higher capex for retail", "source_name": "Mint"},
    ]
    rendered = score.build_user_prompt("Reliance posts Q1 results", items)
    expected = (
        Path(__file__).parent / "fixtures" / "score_prompt_user.txt"
    ).read_text(encoding="utf-8")
    assert rendered == expected


def test_user_prompt_handles_a_story_with_no_items():
    rendered = score.build_user_prompt("A manual idea with no sources", [])
    assert "A manual idea with no sources" in rendered
    assert "(no linked sources)" in rendered


def _patch_config(monkeypatch):
    """score_new_job reads config before it reads stories. Patch both loaders
    to defaults so the job never touches the DB pool in a unit test."""
    monkeypatch.setattr(score, "get_llm_config", AsyncMock(return_value=LLMConfig()))
    monkeypatch.setattr(
        score, "get_ingest_config", AsyncMock(return_value=IngestConfig())
    )


async def test_score_new_job_never_writes_a_fabricated_score(monkeypatch):
    """The module's second invariant, made mechanical: when the router
    exhausts its attempts, write_score must never be called for that story,
    a story_score_failed audit event lands instead, and the loop moves on to
    consider the next story rather than aborting the batch."""
    _patch_config(monkeypatch)
    story_id = uuid.uuid4()
    story = {"id": story_id, "headline": "A failing story", "items": []}

    monkeypatch.setattr(score, "fetch_unscored", AsyncMock(return_value=[story]))
    monkeypatch.setattr(
        score, "complete_json", AsyncMock(side_effect=RouterError("exhausted"))
    )
    write_score = AsyncMock()
    monkeypatch.setattr(score, "write_score", write_score)
    audit_log = AsyncMock()
    monkeypatch.setattr(score, "audit_log", audit_log)

    await score.score_new_job()

    write_score.assert_not_called()
    audit_log.assert_awaited_once()
    kwargs = audit_log.await_args.kwargs
    assert kwargs["action"] == "story_score_failed"
    assert kwargs["entity"] == str(story_id)
    assert kwargs["entity_type"] == "story"


async def test_score_new_job_writes_a_successful_score(monkeypatch):
    """A story the router scores successfully is written exactly once, with
    the validated payload the router returned."""
    _patch_config(monkeypatch)
    story_id = uuid.uuid4()
    story = {"id": story_id, "headline": "A scorable story", "items": []}

    monkeypatch.setattr(score, "fetch_unscored", AsyncMock(return_value=[story]))
    monkeypatch.setattr(score, "complete_json", AsyncMock(return_value=GOOD))
    write_score = AsyncMock(return_value=True)
    monkeypatch.setattr(score, "write_score", write_score)
    audit_log = AsyncMock()
    monkeypatch.setattr(score, "audit_log", audit_log)

    await score.score_new_job()

    write_score.assert_awaited_once_with(story_id, GOOD)
    audit_log.assert_not_called()


async def test_score_new_job_continues_past_a_failure_to_the_next_story(monkeypatch):
    """One story's RouterError must not abort the batch: the next story is
    still scored and written."""
    _patch_config(monkeypatch)
    failing_id = uuid.uuid4()
    ok_id = uuid.uuid4()
    stories = [
        {"id": failing_id, "headline": "Fails", "items": []},
        {"id": ok_id, "headline": "Succeeds", "items": []},
    ]

    monkeypatch.setattr(score, "fetch_unscored", AsyncMock(return_value=stories))
    monkeypatch.setattr(
        score,
        "complete_json",
        AsyncMock(side_effect=[RouterError("exhausted"), GOOD]),
    )
    write_score = AsyncMock(return_value=True)
    monkeypatch.setattr(score, "write_score", write_score)
    monkeypatch.setattr(score, "audit_log", AsyncMock())

    await score.score_new_job()

    write_score.assert_awaited_once_with(ok_id, GOOD)
