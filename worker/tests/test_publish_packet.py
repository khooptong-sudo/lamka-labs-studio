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


def test_art_prompt_carries_title_hook_and_bible_and_bans_text():
    from app.youtube import build_thumbnail_art_prompt

    prompt = build_thumbnail_art_prompt(title="T", hook="H", bible="B", mood="calm")
    assert "T" in prompt and "H" in prompt and "B" in prompt
    assert "no words" in prompt.lower()
    assert "16:9" in prompt


def test_art_prompt_moods_differ_between_variants():
    from app.youtube import build_thumbnail_art_prompt

    a = build_thumbnail_art_prompt(title="T", hook="H", bible="B", mood="calm daylight")
    b = build_thumbnail_art_prompt(title="T", hook="H", bible="B", mood="dramatic dusk")
    assert a != b


def test_thumbnail_layouts_differ():
    from app.youtube import _thumbnail_html

    assert _thumbnail_html(layout="top-band", title="T", background=None) != _thumbnail_html(
        layout="bottom-band", title="T", background=None
    )


def test_thumbnail_html_embeds_the_title():
    from app.youtube import _thumbnail_html

    assert "My Title" in _thumbnail_html(layout="top-band", title="My Title", background=None)


@pytest.mark.asyncio
async def test_variant_falls_back_to_legacy_card_when_art_fails(tmp_path):
    from unittest.mock import AsyncMock, patch

    from app.youtube import build_thumbnail_variants

    composed = []

    async def fake_compose(*, layout, title, background, output):
        composed.append((layout, background))
        output.write_bytes(b"jpg")

    with patch("app.youtube._generate_gemini_thumbnail_art", AsyncMock(side_effect=RuntimeError("down"))), \
            patch("app.youtube._compose_thumbnail", AsyncMock(side_effect=fake_compose)):
        built = await build_thumbnail_variants(title="T", hook="H", bible="B", video_dir=tmp_path)

    assert set(built) == {"a", "b"}
    assert all(background is None for _, background in composed)


@pytest.mark.asyncio
async def test_builder_never_raises_when_everything_fails(tmp_path):
    from unittest.mock import AsyncMock, patch

    from app.youtube import build_thumbnail_variants

    with patch("app.youtube._generate_gemini_thumbnail_art", AsyncMock(side_effect=RuntimeError("down"))), \
            patch("app.youtube._compose_thumbnail", AsyncMock(side_effect=FileNotFoundError("no playwright"))):
        assert await build_thumbnail_variants(title="T", hook="H", bible="B", video_dir=tmp_path) == {}
