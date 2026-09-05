"""Hook/chapter contract + evidence fact-check for generated scripts.

The validator is pure (boards in, violation strings out) so it stays
unit-testable. The fact-check goes through llm.router.complete_json with the
drafter's provider excluded, so the checker structurally cannot be the
drafter wearing a second hat (P2 L2 cross-model rule).
"""

from __future__ import annotations

import re
from typing import Any

from app.llm import contract, router
from app.llm.contract import FieldSpec
from app.storyboard import parse_storyboard

MIN_GENERATED_SCENES = 4
MAX_GENERATED_SCENES = 8
MIN_DOC_SCENES = 21
MAX_DOC_SCENES = 36
MIN_ACT_SCENES = 7
MAX_ACT_SCENES = 9
MAX_HOOK_WORDS = 25
MIN_CLOSING_WORDS = 5

BANNED_HOOK_OPENERS = ("what if i told you",)

_SENTENCE_END = re.compile(r"[.!?]")


def _first_sentence(text: str) -> str:
    match = _SENTENCE_END.search(text)
    return (text[: match.start()] if match else text).strip().strip("\"'")


def validate_script_structure(
    script_text: str,
    *,
    min_scenes: int = MIN_GENERATED_SCENES,
    max_scenes: int = MAX_GENERATED_SCENES,
    require_hook: bool = True,
    require_closing: bool = True,
) -> list[str]:
    """Return human-readable violations. Empty means the board meets the contract."""
    violations: list[str] = []
    board = parse_storyboard(script_text)
    frames = board.frames

    if not (min_scenes <= len(frames) <= max_scenes):
        violations.append(
            f"expected {min_scenes}-{max_scenes} scenes, found {len(frames)}"
        )
        return violations

    if require_hook:
        hook = _first_sentence(frames[0].voiceover or "")
        words = hook.split()
        if not words:
            violations.append("scene 1 has no hook: opening voiceover is empty")
        else:
            if len(words) > MAX_HOOK_WORDS:
                violations.append(
                    f"hook is {len(words)} words, over the {MAX_HOOK_WORDS}-word limit"
                )
            lowered = hook.lower()
            for opener in BANNED_HOOK_OPENERS:
                if lowered.startswith(opener):
                    violations.append(f"hook uses banned question-bait opener {opener!r}")

    seen_titles: set[str] = set()
    for frame in frames:
        title = (frame.title or "").strip()
        if not title:
            violations.append(f"scene {frame.index} has no chapter title")
        elif title.lower() in seen_titles:
            violations.append(f"duplicate chapter title {title!r}")
        else:
            seen_titles.add(title.lower())

    closing_words = (frames[-1].voiceover or "").split()
    if require_closing and len(closing_words) < MIN_CLOSING_WORDS:
        violations.append("final scene has no closing beat: voiceover is too short to close on")

    return violations


def _is_violations(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        quote = item.get("quote")
        reason = item.get("reason")
        if not isinstance(quote, str) or not quote.strip():
            return False
        if not isinstance(reason, str) or not reason.strip():
            return False
    return True


FACT_CHECK_SPEC = FieldSpec(validators={
    "verdict": lambda v: v in ("PASS", "FLAG", "BLOCK"),
    "violations": _is_violations,
})

FACT_CHECK_SYSTEM = """You fact-check a faceless explainer-video script against its evidence packet.

The packet's SOURCE blocks are the only admissible evidence. Web knowledge, current prices, forecasts, dates, tax thresholds, legal conclusions, or company facts absent from the packet are UNSUPPORTED, however plausible.

Return ONE JSON object and nothing else. No markdown fence, no commentary.

{
  "verdict": "<PASS | FLAG | BLOCK>",
  "violations": [{"quote": "<exact script quote>", "reason": "<what is unsupported and why>"}]
}

- PASS: every factual claim is supported by the packet.
- FLAG: minor softening needed (vague attribution, loose paraphrase) but nothing invented; the human reviewer decides.
- BLOCK: any invented date, price, number, quote, legal/tax conclusion, or a recommendation to buy/sell/hold/accumulate/book profit."""


def build_fact_check_user(script: str, evidence_packet: str) -> str:
    return (
        "EVIDENCE PACKET (only admissible evidence):\n"
        f"{evidence_packet}\n\n"
        "SCRIPT UNDER REVIEW:\n"
        f"{script}"
    )


async def fact_check_script(
    *, script: str, evidence_packet: str, exclude: tuple[str, ...]
) -> dict:
    """Run the `fact_check` task with the drafter excluded. Raises RouterError
    when no non-drafter provider is available — never a silent PASS."""
    return await router.complete_json(
        "fact_check",
        system=FACT_CHECK_SYSTEM,
        user=build_fact_check_user(script, evidence_packet),
        spec=FACT_CHECK_SPEC,
        exclude=exclude,
    )
