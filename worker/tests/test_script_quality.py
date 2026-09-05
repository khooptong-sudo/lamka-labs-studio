"""Validator is pure: boards in, violation strings out. No router, no DB."""

from app import script_quality

GOOD_BOARD = (
    "---\ntitle: Test\ndescription: A test description.\npreset: adult_male\n---\n\n"
    "# Scene 1 — The hook\nVoiceover: \"City budgets hide one line that explains every pothole you hit.\"\n"
    "Scene: A miniature city street cracking open.\n\n"
    "# Scene 2 — The mechanism\nVoiceover: \"The maintenance fund is raided each spring to cover festival spending.\"\n"
    "Scene: Coins lifted from a road jar into a fireworks jar.\n\n"
    "# Scene 3 — Why it matters\nVoiceover: \"That is why your street floods while the parade gets louder each year.\"\n"
    "Scene: Rain pooling on a broken road beside a bright parade.\n\n"
    "# Scene 4 — The takeaway\nVoiceover: \"Read the maintenance line first and the budget finally makes sense.\"\n"
    "Scene: A magnifier resting on one glowing budget line.\n"
)


def test_good_board_passes():
    assert script_quality.validate_script_structure(GOOD_BOARD) == []


def test_too_few_scenes_fails():
    two = "\n\n".join(GOOD_BOARD.split("\n\n")[:4])
    violations = script_quality.validate_script_structure(two)
    assert any("4-8 scenes" in v for v in violations)


def test_missing_chapter_title_fails():
    board = GOOD_BOARD.replace("# Scene 2 — The mechanism", "# Scene 2")
    violations = script_quality.validate_script_structure(board)
    assert any("chapter title" in v for v in violations)


def test_duplicate_chapter_titles_fail():
    board = GOOD_BOARD.replace("# Scene 2 — The mechanism", "# Scene 2 — The hook")
    violations = script_quality.validate_script_structure(board)
    assert any("duplicate" in v for v in violations)


def test_long_hook_fails():
    long_hook = " ".join(["word"] * 26)
    board = GOOD_BOARD.replace(
        "City budgets hide one line that explains every pothole you hit.", long_hook
    )
    violations = script_quality.validate_script_structure(board)
    assert any("hook" in v for v in violations)


def test_question_bait_hook_fails():
    board = GOOD_BOARD.replace(
        "City budgets hide one line that explains every pothole you hit.",
        "What if I told you budgets hide a secret line?",
    )
    violations = script_quality.validate_script_structure(board)
    assert any("hook" in v for v in violations)


def test_missing_closing_beat_fails():
    board = GOOD_BOARD.replace(
        "Read the maintenance line first and the budget finally makes sense.", "Ok."
    )
    violations = script_quality.validate_script_structure(board)
    assert any("closing" in v for v in violations)


"""Fact-check client: router seam patched, never a provider (bug #13)."""

from unittest.mock import AsyncMock

import pytest

from app.llm import contract
from app.llm.router import RouterError

PASS = {"verdict": "PASS", "violations": []}
BLOCK = {"verdict": "BLOCK", "violations": [{"quote": "prices doubled", "reason": "no source supports this"}]}


def test_spec_rejects_an_invented_verdict():
    violations = contract.validate(
        {"verdict": "MAYBE", "violations": []}, script_quality.FACT_CHECK_SPEC
    )
    assert violations == ["field 'verdict' has invalid value 'MAYBE'"]


def test_spec_rejects_a_violation_missing_its_reason():
    payload = {"verdict": "BLOCK", "violations": [{"quote": "x"}]}
    violations = contract.validate(payload, script_quality.FACT_CHECK_SPEC)
    assert any("violations" in v for v in violations)


def test_spec_accepts_a_good_block_payload():
    assert contract.validate(BLOCK, script_quality.FACT_CHECK_SPEC) == []


async def test_fact_check_excludes_the_drafter(monkeypatch):
    complete = AsyncMock(return_value=PASS)
    monkeypatch.setattr("app.llm.router.complete_json", complete)
    result = await script_quality.fact_check_script(
        script="board", evidence_packet="packet", exclude=("gemini",)
    )
    assert result == PASS
    _, kwargs = complete.call_args
    assert kwargs["exclude"] == ("gemini",)
    assert kwargs["system"] and kwargs["user"]


async def test_fact_check_router_exhaustion_raises(monkeypatch):
    monkeypatch.setattr(
        "app.llm.router.complete_json", AsyncMock(side_effect=RouterError("exhausted"))
    )
    with pytest.raises(RouterError):
        await script_quality.fact_check_script(
            script="board", evidence_packet="packet", exclude=("gemini",)
        )


def test_validator_accepts_scaled_bounds():
    from app.script_quality import validate_script_structure

    board = (
        "---\ntitle: T\ndescription: D\n---\n\n"
        + "\n\n".join(
            f"# Scene {i} — Ch{i}\nVoiceover: \"This is a sufficiently long closing-style narration line number {i}.\""
            for i in range(1, 22)
        )
    )
    assert validate_script_structure(board, min_scenes=21, max_scenes=36) == []


def test_validator_scaled_bounds_reject_short_boards():
    from app.script_quality import validate_script_structure

    board = (
        "---\ntitle: T\ndescription: D\n---\n\n"
        "# Scene 1 — A\nVoiceover: \"A sufficiently long opening hook line here.\"\n\n"
        "# Scene 2 — B\nVoiceover: \"A sufficiently long closing line here too.\""
    )
    assert any("21-36" in v for v in validate_script_structure(board, min_scenes=21, max_scenes=36))


def test_validator_hook_and_closing_are_optional_per_act():
    from app.script_quality import validate_script_structure

    board = (
        "---\ntitle: T\ndescription: D\n---\n\n"
        + "\n\n".join(
            f"# Scene {i} — Ch{i}\nVoiceover: \"A fine middle-act narration line number {i} here.\""
            for i in range(1, 8)
        )
    )
    assert validate_script_structure(board, min_scenes=7, max_scenes=9,
                                     require_hook=False, require_closing=False) == []
