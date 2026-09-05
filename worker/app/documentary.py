"""Act-structured long-form scripting (8-12 min documentaries).

Leaf module: imports app.llm.providers/contract, app.storyboard,
app.script_quality — never app.youtube (youtube imports this module for the
documentary branch; the reverse would be circular).
"""

from __future__ import annotations

import asyncio
import json  # noqa: F401 — kept for callers that build outline payloads
import re
from dataclasses import dataclass, field

from app.llm import contract, providers
from app.llm.contract import FieldSpec
from app.llm.providers import PROVIDERS, Provider  # noqa: F401 — re-exported for tests/callers
from app.script_quality import (
    MAX_ACT_SCENES, MAX_DOC_SCENES, MIN_ACT_SCENES, MIN_DOC_SCENES,
    validate_script_structure,  # noqa: F401 — re-exported for the documentary branch
)
from app.storyboard import parse_storyboard

PROVIDER_ATTEMPTS = 4
RECAP_CHARS = 500
BRIEF_CHARS = 2000


@dataclass(frozen=True)
class ActPlan:
    title: str
    hook: str
    beats: list[str] = field(default_factory=list)
    sources: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentaryOutline:
    title: str
    acts: list[ActPlan]


def deal_sources(items: list[dict], n_acts: int) -> list[list[dict]]:
    """Round-robin items across acts so coverage spreads instead of front-loading."""
    dealt: list[list[dict]] = [[] for _ in range(n_acts)]
    for index, item in enumerate(items):
        dealt[index % n_acts].append(item)
    return dealt


def validate_outline(payload: object, n_sources: int) -> list[str]:
    """Structural check on an outline payload. Empty means plannable."""
    violations: list[str] = []
    if not isinstance(payload, dict):
        return ["outline is not an object"]
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        violations.append("outline has no title")
    acts = payload.get("acts")
    if not isinstance(acts, list) or not (3 <= len(acts) <= 4):
        return violations + [f"expected 3-4 acts, found {len(acts) if isinstance(acts, list) else acts!r}"]
    for number, act in enumerate(acts, start=1):
        if not isinstance(act, dict):
            violations.append(f"act {number} is not an object")
            continue
        for key in ("title", "hook"):
            if not isinstance(act.get(key), str) or not act[key].strip():
                violations.append(f"act {number} has no {key}")
        beats = act.get("beats")
        if not isinstance(beats, list) or not (MIN_ACT_SCENES <= len(beats) <= MAX_ACT_SCENES):
            found = len(beats) if isinstance(beats, list) else beats
            violations.append(f"act {number}: expected {MIN_ACT_SCENES}-{MAX_ACT_SCENES} beats, found {found!r}")
        sources = act.get("sources")
        if not isinstance(sources, list) or any(
            not isinstance(s, int) or isinstance(s, bool) or not (0 <= s < n_sources) for s in sources
        ):
            violations.append(f"act {number} has out-of-range source indices")
    return violations


OUTLINE_SPEC = FieldSpec(validators={
    "title": lambda v: isinstance(v, str) and bool(v.strip()),
    "acts": lambda v: isinstance(v, list) and 3 <= len(v) <= 4,
})

DOC_OUTLINE_SYSTEM = """You plan an 8-12 minute faceless documentary in 3-4 acts.

Return ONE JSON object and nothing else. No markdown fence, no commentary.

{
  "title": "<documentary title>",
  "acts": [
    {"title": "<act title>", "hook": "<one-line act hook>",
     "beats": ["<7-9 scene beats, each one visual moment>", ...],
     "sources": [<indices into the EVIDENCE list below, 0-based>]}
  ]
}

Rules: 3-4 acts; 7-9 beats per act; every beat filmable as one keyframe;
spread sources across acts (no act claims index >= the evidence count);
act 1 hooks the whole film, the final act closes it."""

DOC_SYSTEM = DOC_OUTLINE_SYSTEM


async def _provider_call(provider: str, system: str, user: str) -> str:
    """One provider call with retries on retryable errors. Raises, never stubs."""
    call = PROVIDERS[provider].call
    for attempt in range(1, PROVIDER_ATTEMPTS + 1):
        try:
            return await call(system, user)
        except Exception as exc:  # noqa: BLE001 — classified below
            if not providers.is_retryable(exc) or attempt == PROVIDER_ATTEMPTS:
                raise
            await asyncio.sleep(2 ** attempt)


async def plan_outline(*, headline: str, packet: str, provider: str, n_sources: int) -> DocumentaryOutline:
    """Plan acts for one documentary. Raises on any failure."""
    raw = await _provider_call(
        provider, DOC_OUTLINE_SYSTEM,
        f"HEADLINE:\n{headline}\n\nEVIDENCE (indexed 0-based):\n{packet}",
    )
    payload = contract.parse(raw, OUTLINE_SPEC)
    violations = validate_outline(payload, n_sources)
    if violations:
        raise ValueError(f"unplannable outline: {'; '.join(violations)}")
    return DocumentaryOutline(
        title=payload["title"].strip(),
        acts=[ActPlan(title=a["title"].strip(), hook=a["hook"].strip(),
                      beats=list(a["beats"]), sources=list(a["sources"]))
              for a in payload["acts"]],
    )


def build_act_system(*, channel_prompt: str) -> str:
    return f"""You write ONE act of a faceless documentary. Output ONLY act scenes, no frontmatter.

FORMAT per scene:
# Scene N — <chapter>
Voiceover: "..."
Scene: "..."

Use continuous global scene numbering as instructed in the brief. One scene per
listed beat, in order. Narrate only what the ACT EVIDENCE PACKET supports.

Voice: {channel_prompt}"""


def build_act_user(*, act: ActPlan, act_index: int, n_acts: int, first_scene: int, recap: str, bundle: str) -> str:
    last_scene = first_scene + len(act.beats) - 1
    scope = []
    if act_index == 0:
        scope.append("This is ACT 1: open with the film's hook as the first sentence.")
    if act_index == n_acts - 1:
        scope.append("This is the FINAL act: close the whole film in the last scene.")
    return (
        f"ACT {act_index + 1} OF {n_acts}: {act.title}\n"
        f"Act hook: {act.hook}\n"
        f"Beats in order ({len(act.beats)} scenes, one scene per beat):\n"
        + "".join(f"- {beat}\n" for beat in act.beats)
        + f"Number the scenes {first_scene}..{last_scene} globally (continuous across acts).\n"
        + (f"\nPREVIOUS ACT'S CLOSING (continuity only):\n{recap}\n" if recap else "")
        + f"\nACT EVIDENCE PACKET:\n{bundle}\n"
        + "\n".join(scope)
    )


async def generate_act(
    *, act: ActPlan, act_index: int, n_acts: int, first_scene: int,
    recap: str, bundle_text: str, channel_prompt: str, provider: str,
    want_hook: bool, want_closing: bool,
) -> str:
    """Write one act's scenes. Raises on provider failure."""
    user = build_act_user(act=act, act_index=act_index, n_acts=n_acts,
                          first_scene=first_scene, recap=recap, bundle=bundle_text)
    hook_rule = "open with the film's hook" if want_hook else "no new hook; continue the film"
    close_rule = "close the whole film in the last scene" if want_closing else "end on forward motion, not a conclusion"
    user += f"\nHOOK RULE: {hook_rule}.\nCLOSING RULE: {close_rule}."
    return await _provider_call(
        provider, build_act_system(channel_prompt=channel_prompt), user,
    )


_DIRECTION_HEADING = re.compile(r"^#{1,3}\s*Video direction", re.IGNORECASE)
_FRONTMATTER_BLOCK = re.compile(r"^\s*---\s*\r?\n.*?\r?\n---(?:\s*\r?\n|$)", re.DOTALL)


def merge_acts(act_markdowns: list[str]) -> str:
    """Concatenate act boards: act 1 keeps frontmatter + direction, later acts
    contribute scenes only. Raises on empty input."""
    if not act_markdowns:
        raise ValueError("nothing to merge")
    bodies = []
    for position, markdown in enumerate(act_markdowns):
        text = markdown.strip()
        if position > 0:
            text = _FRONTMATTER_BLOCK.sub("", text, count=1).strip()
            lines = []
            skipping = False
            for line in text.splitlines():
                if _DIRECTION_HEADING.match(line):
                    skipping = True
                    continue
                if skipping and re.match(r"^\s*#{0,3}\s*(?:Frame|Scene)\s*\d+", line, re.IGNORECASE):
                    skipping = False
                if not skipping:
                    lines.append(line)
            text = "\n".join(lines).strip()
        bodies.append(text)
    return "\n\n".join(bodies)


def drafter_provider() -> str:
    """The model family that authors acts (and Shorts scripts)."""
    import os

    return os.environ.get("SCENE_MODEL_PROVIDER", "gemini").lower()


def last_voiceover(board_text: str) -> str:
    """Last non-empty voiceover line, for the next act's recap."""
    lines = [
        frame.voiceover.strip()
        for frame in parse_storyboard(board_text).frames
        if (frame.voiceover or "").strip()
    ]
    return lines[-1] if lines else ""
