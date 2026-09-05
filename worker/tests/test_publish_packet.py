"""Tags: pure parse/validate plus metadata integration. No network, no DB."""

import pytest

from app.youtube import parse_tags, validate_tags


def test_parse_tags_splits_and_cleans():
    assert parse_tags({"tags": "  markets, ETFs,markets ,"}) == ["markets", "ETFs"]


def test_parse_tags_absent_means_empty():
    assert parse_tags({}) == []
    assert parse_tags({"tags": "   "}) == []


def test_validate_tags_rejects_too_many():
    tags = [f"t{i}" for i in range(13)]
    assert any("12" in v for v in validate_tags(tags, ()))


def test_validate_tags_rejects_an_oversized_tag():
    assert validate_tags(["a" * 61], [])


def test_validate_tags_rejects_duplicates_case_insensitively():
    assert any("duplicate" in v for v in validate_tags(["Markets", "markets"], []))


def test_validate_tags_rejects_a_blocked_term():
    from app.channels import Channel

    finance = Channel(
        id="finance", display_name="Finance", voice_key="adult_male",
        script_prompt="A prompt.", extra_blocklist=("buy",),
    )
    violations = validate_tags(["buy signals"], finance.effective_blocklist)
    assert violations


def test_validate_tags_accepts_a_clean_list():
    assert validate_tags(["markets", "ETFs", "budget 2026"], ()) == []


def test_require_metadata_returns_tags():
    from app.youtube import _require_metadata

    title, description, tags = _require_metadata(
        {"title": "T", "description": "D", "tags": "a, b"}, ()
    )
    assert (title, description, tags) == ("T", "D", ["a", "b"])


def test_require_metadata_defaults_missing_tags_to_empty():
    from app.youtube import _require_metadata

    assert _require_metadata({"title": "T", "description": "D"})[2] == []


def test_require_metadata_raises_on_invalid_tags():
    from app.youtube import _require_metadata

    with pytest.raises(ValueError, match="tags"):
        _require_metadata({"title": "T", "description": "D", "tags": "buy signals"}, ("buy",))
