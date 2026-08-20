"""Unit tests for scoring. The router is patched, never a provider (bug #13)."""

import pytest

from app import score, taxonomy
from app.llm import contract

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


@pytest.mark.parametrize("bad", [-1, 101, "high", None])
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
    validator and every call fails validation for a reason nobody can see."""
    for value in taxonomy.ARCHETYPES:
        assert value in score.SYSTEM_PROMPT
    for value in taxonomy.VERTICALS:
        assert value in score.SYSTEM_PROMPT


def test_system_prompt_forbids_advisory_output():
    lowered = score.SYSTEM_PROMPT.lower()
    assert "never" in lowered
    assert "buy" in lowered and "sell" in lowered


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
