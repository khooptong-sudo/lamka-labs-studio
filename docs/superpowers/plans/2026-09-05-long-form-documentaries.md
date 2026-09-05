# Long-Form Documentaries (8–12 min) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Act-structured 20–36-scene documentaries on the proven cinematic path, each act evidence-bounded and gated, merged through the existing render/publish flow.

**Architecture:** New leaf module `app/documentary.py` (outline, act scripting, evidence dealing, merge — no imports from `app.youtube`, so no cycle) drives the existing Shorts machinery per act: same contract validator with scaled bounds, same fact-check task, same timing/frames/render/thumbnails/tags/upload. `generate_youtube_video` gains a `documentary` flag that swaps the scripting front-end only.

**Tech Stack:** Python worker, `app.llm.providers` direct calls (mirrors the existing script-generation pattern, which predates the router), `app.llm.contract` for outline JSON, pytest with seam patching.

**Spec:** `docs/superpowers/specs/2026-09-05-long-form-documentaries-design.md`

## Global Constraints

- Tests must not touch the network, real LLMs, real ffmpeg, or a real DB; patch provider calls, `db.get_config`, and pipeline seams.
- Any act failure aborts the whole run. Never fabricate, never repair, never render a partial documentary.
- Spec refinement (recorded here, rationale below): 3–4 acts × 7–9 scenes (21–36 total) instead of the spec's 5–9/20–30 — 3×5=15 would pass per-act bounds yet breach any 20-scene floor, so the floor must be satisfiable by the smallest legal shape (3×7=21).
- PowerShell 5.1 for shells (no `&&`); pytest as `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`.
- The working tree may hold unrelated uncommitted work: stage ONLY your hunks/files. Depend ONLY on committed code. Do NOT push (Task 4 pushes once).

---

### Task 1: Scaled bounds, pacing, caps, outline route

**Files:**
- Modify: `worker/app/script_quality.py` (keyword bounds), `worker/app/storyboard.py` (pacing), `worker/app/youtube.py` (`MAX_VOICE_CLIPS`, `_research_items`/`_research_packet` split), `worker/app/config.py` (default route), `worker/tests/test_llm_router.py` (defaults assertion)
- Test: `worker/tests/test_script_quality.py` (append), `worker/tests/test_storyboard.py` (append; check file exists first — if absent, put pacing tests in the new `test_documentary.py` from Task 2 instead)

**Interfaces:**
- Consumes: nothing new.
- Produces: `validate_script_structure(script_text, *, min_scenes=4, max_scenes=8, require_hook=True, require_closing=True)`; `PACNG` profile `"documentary"`; `_research_items(story, max_sources=4)`; `_render_packet(items) -> str`; `LLMConfig` default route `"documentary_outline": {"primary": "gemini", "fallback": "openai"}`; `MAX_VOICE_CLIPS = 40`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

(7 scenes × ~9-word lines: hook rule skipped, closing skipped, titles unique —
only the count bounds apply. The first test's 21 scenes carry hook (scene 1)
and closing (scene 21) so defaults for those flags pass.)

```python
def test_documentary_pacing_resolves():
    from app.storyboard import resolve_pacing

    pacing = resolve_pacing("documentary")
    assert (pacing.floor, pacing.soft_ceiling, pacing.lead_in, pacing.tail) == (3.0, 16.0, 0.3, 0.6)


def test_research_items_default_cap_unchanged():
    from app import youtube

    story = {"items": [
        {"title": f"T{i}", "url": f"https://x/{i}", "source_name": "S",
         "published_at": None, "full_text": "body text here"}
        for i in range(10)
    ]}
    assert len(youtube._research_items(story)) == 4
    assert len(youtube._research_items(story, max_sources=12)) == 10
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_script_quality.py -q -k "scaled or optional_per_act"`
Expected: FAIL with `TypeError` (no keyword params yet). The pacing/items tests fail with `AssertionError`/default-cap mismatch as applicable — confirm each red for its own reason before implementing.

- [ ] **Step 3: Implement**

a) `script_quality.py`: add keyword-only params with Shorts defaults, gate the
hook block on `require_hook` and the closing block on `require_closing`:

```python
MIN_DOC_SCENES = 21
MAX_DOC_SCENES = 36
MIN_ACT_SCENES = 7
MAX_ACT_SCENES = 9


def validate_script_structure(
    script_text: str,
    *,
    min_scenes: int = MIN_GENERATED_SCENES,
    max_scenes: int = MAX_GENERATED_SCENES,
    require_hook: bool = True,
    require_closing: bool = True,
) -> list[str]:
```

Body identical except the count check uses the params and the two blocks are
conditional. All existing callers keep Shorts behavior untouched.

b) `storyboard.py` `PACING_PROFILES`: add
`"documentary": Pacing(floor=3.0, soft_ceiling=16.0, lead_in=0.3, tail=0.6),`
with a comment (narration-led like explainer, room to breathe like story).

c) `youtube.py`: `MAX_VOICE_CLIPS = 40` (route + ingest share the const, so
owner narration works at length with the per-clip byte cap unchanged).
`_research_items(story, max_sources=4)` — replace the constant with the param;
extract `_render_packet(items: list[dict]) -> str` containing the current
SOURCE-block serialization, with `_research_packet(story)` delegating as
`_render_packet(_research_items(story))`.

d) `config.py` `LLMConfig.routing` default: add
`"documentary_outline": {"primary": "gemini", "fallback": "openai"}`.
Update `test_get_llm_config_defaults_when_no_row` in `test_llm_router.py`
to the 3-route dict (precedent: piece-1 and piece-2 did the same).

- [ ] **Step 4: Run green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_script_quality.py tests/test_llm_router.py tests/test_storyboard.py -q`
Expected: PASS (if `test_storyboard.py` is absent, run the first two and note it for Task 2's file placement)

- [ ] **Step 5: Commit**

```bash
git add worker/app/script_quality.py worker/app/storyboard.py worker/app/youtube.py worker/app/config.py worker/tests/test_script_quality.py worker/tests/test_llm_router.py worker/tests/test_storyboard.py
git commit -m "Scale script bounds, pacing, evidence and caps for long-form"
```

(Stage only the listed hunks if files are mixed with unrelated work; omit
`test_storyboard.py` from the add if it does not exist.)

---

### Task 2: Documentary module (outline, acts, merge)

**Files:**
- Create: `worker/app/documentary.py`
- Test: `worker/tests/test_documentary.py` (new; pacing tests land here too if `test_storyboard.py` was absent)

**Interfaces:**
- Consumes: `app.llm.providers` (`PROVIDERS`, `is_retryable`), `app.llm.contract` (`FieldSpec`, `parse`), `app.storyboard.parse_storyboard`, `app.script_quality` (bounds consts, `validate_script_structure`, `fact_check_script`).
- Produces: `DocumentaryOutline` (dataclass: `title`, `acts: list[ActPlan]`; `ActPlan`: `title`, `hook`, `beats: list[str]`, `sources: list[int]`); `validate_outline(payload, n_sources) -> list[str]`; `deal_sources(items, n_acts) -> list[list[dict]]`; `plan_outline(headline, packet, provider) -> DocumentaryOutline`; `generate_act(...) -> str`; `merge_acts(act_markdowns) -> str`; `DOC_SYSTEM`, `OUTLINE_SPEC`.

- [ ] **Step 1: Write the failing tests**

```python
"""Documentary acts: pure planning math, no network, no LLMs."""

import pytest


def _items(n):
    return [{"title": f"T{i}", "url": f"https://x/{i}", "source_name": "S",
             "published_at": None, "excerpt": f"excerpt {i}"} for i in range(n)]


def test_deal_sources_splits_round_robin():
    from app.documentary import deal_sources

    dealt = deal_sources(_items(7), 3)
    assert [[it["title"] for it in act] for act in dealt] == [
        ["T0", "T3", "T6"], ["T1", "T4"], ["T2", "T5"],
    ]


def test_deal_sources_handles_fewer_items_than_acts():
    from app.documentary import deal_sources

    dealt = deal_sources(_items(2), 4)
    assert [len(act) for act in dealt] == [1, 1, 0, 0]


def test_validate_outline_accepts_a_good_plan():
    from app.documentary import validate_outline

    payload = {"title": "T", "acts": [
        {"title": f"A{i}", "hook": f"hook {i}",
         "beats": [f"beat {i}-{j}" for j in range(7)], "sources": [i]}
        for i in range(3)
    ]}
    assert validate_outline(payload, 10) == []


def test_validate_outline_rejects_bad_counts_and_indices():
    from app.documentary import validate_outline

    assert validate_outline({"title": "T", "acts": []}, 4)
    many = {"title": "T", "acts": [
        {"title": "A", "hook": "h", "beats": ["b"] * 7, "sources": []}
        for _ in range(5)
    ]}
    assert validate_outline(many, 4)
    bad_beats = {"title": "T", "acts": [
        {"title": "A", "hook": "h", "beats": ["b"] * 4, "sources": []}
        for _ in range(3)
    ]}
    assert validate_outline(bad_beats, 4)
    bad_idx = {"title": "T", "acts": [
        {"title": "A", "hook": "h", "beats": ["b"] * 7, "sources": [9]}
        for _ in range(3)
    ]}
    assert validate_outline(bad_idx, 4)


def test_validate_outline_rejects_missing_fields():
    from app.documentary import validate_outline

    assert validate_outline({"title": "T"}, 4)
    assert validate_outline({"title": "", "acts": [
        {"title": "A", "hook": "h", "beats": ["b"] * 7, "sources": []}
        for _ in range(3)
    ]}, 4)


async def test_plan_outline_parses_provider_json(monkeypatch):
    from app import documentary

    payload = {"title": "Doc", "acts": [
        {"title": "A", "hook": "h", "beats": ["b"] * 7, "sources": [0]}
    ] * 3}
    import json

    async def fake_call(system, user):
        assert "3-4 acts" in system
        return json.dumps(payload)

    monkeypatch.setitem(
        documentary.PROVIDERS, "gemini",
        documentary.Provider("gemini", "GEMINI_API_KEY", fake_call),
    )
    outline = await documentary.plan_outline(
        headline="Head", packet="packet", provider="gemini", n_sources=4
    )
    assert outline.title == "Doc"
    assert len(outline.acts) == 3


async def test_generate_act_sends_recap_and_bundle(monkeypatch):
    from app import documentary

    seen = {}

    async def fake_call(system, user):
        seen["system"] = system
        seen["user"] = user
        return "# Scene 1 — X\nVoiceover: \"A sufficiently long narration line here.\"\n"

    monkeypatch.setitem(
        documentary.PROVIDERS, "gemini",
        documentary.Provider("gemini", "GEMINI_API_KEY", fake_call),
    )
    act = documentary.ActPlan(title="A", hook="h", beats=["b"] * 7, sources=[0])
    await documentary.generate_act(
        act=act, act_index=1, n_acts=3, recap="PREV CLOSE",
        bundle="SOURCE 1...", channel_prompt="Be sober.",
        provider="gemini", want_hook=False, want_closing=True,
    )
    assert "PREV CLOSE" in seen["user"]
    assert "SOURCE 1..." in seen["user"]
    assert "Be sober." in seen["system"]
```

Notes: `documentary.PROVIDERS` / `documentary.Provider` mean the module does
`from app.llm import providers` and references `providers.PROVIDERS` — or
re-export both names (`from app.llm.providers import PROVIDERS, Provider`).
Either satisfies the tests; the re-export is one line and keeps call sites
short. `validate_outline` bounds: 3–4 acts, 7–9 beats each, title/hook
non-empty, sources are ints in `[0, n_sources)`. Retry policy for provider
calls: up to 4 attempts, retry only `providers.is_retryable(exc)`, else raise
immediately (mirrors the existing script-generation shape).

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_documentary.py -q`
Expected: FAIL with `ImportError` (no `app.documentary` yet)

- [ ] **Step 3: Implement `app/documentary.py`**

```python
"""Act-structured long-form scripting (8-12 min documentaries).

Leaf module: imports app.llm.providers/contract, app.storyboard,
app.script_quality — never app.youtube (youtube imports this module for the
documentary branch; the reverse would be circular).
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from app.llm import contract, providers
from app.llm.contract import FieldSpec
from app.llm.providers import PROVIDERS, Provider  # noqa: F401 — re-exported for tests/callers
from app.script_quality import (
    MAX_ACT_SCENES, MAX_DOC_SCENES, MIN_ACT_SCENES, MIN_DOC_SCENES,
    validate_script_structure,
)
from app.storyboard import parse_storyboard

PROVIDER_ATTEMPTS = 4
RECAP_CHARS = 500
BRIEF_CHARS = 2000
```

Wait — `MIN_DOC_SCENES` etc. do not exist yet; Task 1 creates them. Order the
consts accordingly (Task 2 may assume Task 1 committed).

```python
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
```

Outline LLM call (JSON, validated twice — contract then structural):

```python
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
```

(`asyncio` top-level in documentary.py.)

```python
async def plan_outline(headline: str, packet: str, provider: str) -> DocumentaryOutline:
    """Plan acts for one documentary. Raises on any failure."""
    user = f"HEADLINE:\n{headline}\n\nEVIDENCE (indexed 0-based):\n{packet}"
    raw = await _provider_call(provider, DOC_OUTLINE_SYSTEM, user)
    payload = contract.parse(raw, OUTLINE_SPEC)
    n_sources = packet.count("SOURCE ")  # hmm — fragile.
```

No: source count must come from the items, not string counting. Signature:
`plan_outline(headline, packet, provider, n_sources)`. Fix the test above
accordingly — it calls `plan_outline("Head", "packet", "gemini")`. Change the
plan: `plan_outline(*, headline, packet, provider, n_sources)`. Update the
Step-1 test call to keyword form with `n_sources=4`. (Catching my own
inconsistency now, not in review.)

```python
async def plan_outline(*, headline: str, packet: str, provider: str, n_sources: int) -> DocumentaryOutline:
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
```

Act scripting:

```python
def build_act_user(*, act: ActPlan, recap: str, bundle: str, act_index: int, n_acts: int) -> str:
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
        + (f"\nPREVIOUS ACT'S CLOSING (continuity only):\n{recap}\n" if recap else "")
        + f"\nACT EVIDENCE PACKET:\n{bundle}\n"
        + "\n".join(scope)
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
```

Hmm — "continuous global scene numbering as instructed in the brief": the
numbering instruction lives in the user prompt, not the system. Fix: `build_act_user`
takes `first_scene: int` and states `Number the scenes {first}..{last} globally`.
Update signature: `build_act_user(*, act, act_index, n_acts, first_scene, recap, bundle)`.
The Step-1 test calls `generate_act(...)` with act/act_index/n_acts/recap/bundle/channel_prompt/provider/want_hook/want_closing — keep THAT signature and compute `first_scene` inside `generate_act` from... it doesn't know prior counts. Alternative: `generate_documentary` (Task 3) tracks running numbers and passes `first_scene` into `generate_act`. So `generate_act(*, act, act_index, n_acts, first_scene, recap, bundle_text, channel_prompt, provider, want_hook, want_closing)`. Update the Step-1 test call: add `first_scene=1, bundle_text="SOURCE 1..."` — rewrite that test block:

```python
    act = documentary.ActPlan(title="A", hook="h", beats=["b"] * 7, sources=[0])
    await documentary.generate_act(
        act=act, act_index=1, n_acts=3, first_scene=8, recap="PREV CLOSE",
        bundle_text="SOURCE 1...", channel_prompt="Be sober.",
        provider="gemini", want_hook=False, want_closing=True,
    )
    assert "PREV CLOSE" in seen["user"]
    assert "SOURCE 1..." in seen["user"]
    assert "8..14" in seen["user"]
    assert "Be sober." in seen["system"]
```

```python
async def generate_act(
    *, act: ActPlan, act_index: int, n_acts: int, first_scene: int,
    recap: str, bundle_text: str, channel_prompt: str, provider: str,
    want_hook: bool, want_closing: bool,
) -> str:
    """Write one act's scenes. Raises on provider failure."""
    last_scene = first_scene + len(act.beats) - 1
    user = build_act_user(act=act, act_index=act_index, n_acts=n_acts,
                          first_scene=first_scene, recap=recap, bundle=bundle_text)
    hook_rule = "open with the film's hook" if want_hook else "no new hook; continue the film"
    close_rule = "close the whole film in the last scene" if want_closing else "end on forward motion, not a conclusion"
    user += f"\nHOOK RULE: {hook_rule}.\nCLOSING RULE: {close_rule}."
    return await _provider_call(
        provider, build_act_system(channel_prompt=channel_prompt), user,
    )
```

`build_act_user` includes: `Number the scenes {first_scene}..{last_scene} globally (continuous across acts).`

Merge:

```python
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
```

(`import re` top-level in documentary.py.)

Small helpers in the same module:

```python
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
```

Tests to add alongside (same file, same style):

```python
def test_merge_keeps_first_frontmatter_and_direction_only():
    from app.documentary import merge_acts

    act1 = (
        "---\ntitle: Doc\ndescription: D\n---\n\n"
        "# Video direction\nA dark world.\n\n"
        "# Scene 1 — A\nVoiceover: \"A sufficiently long narration line here.\"\n"
    )
    act2 = (
        "---\ntitle: Other\ndescription: X\n---\n\n"
        "# Video direction\nA bright world.\n\n"
        "# Scene 1 — B\nVoiceover: \"Another sufficiently long narration line.\"\n"
    )
    merged = merge_acts([act1, act2])
    assert merged.count("---") == 2  # one frontmatter block
    assert "A dark world." in merged
    assert "A bright world." not in merged
    assert "# Scene 1 — A" in merged and "# Scene 1 — B" in merged


def test_merge_refuses_empty_input():
    from app.documentary import merge_acts

    with pytest.raises(ValueError):
        merge_acts([])


def test_last_voiceover_returns_the_final_line():
    from app.documentary import last_voiceover

    board = "# Scene 1 — A\nVoiceover: \"First line here.\"\n\n# Scene 2 — B\nVoiceover: \"Second line here.\"\n"
    assert last_voiceover(board) == "Second line here."
    assert last_voiceover("no scenes here") == ""
```

(`import pytest` top-level in the test file — add it in Step 1's file creation;
the earlier blocks use it too.)

- [ ] **Step 4: Run green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_documentary.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/app/documentary.py worker/tests/test_documentary.py
git commit -m "Add documentary act planning, scripting and merge"
```

---

### Task 3: Wiring (mode, branch, brief, gates)

**Files:**
- Modify: `worker/app/youtube.py` (branch + `documentary` flag), `worker/app/routes.py` (`MODE_BACKENDS`, `brief` fields, flag pass-through), `worker/app/storyboard.py` (already done in Task 1 — no-op here)
- Test: `worker/tests/test_documentary.py` (append pipeline tests), `worker/tests/test_routes_modes.py` (append mode test)

**Interfaces:**
- Consumes: Task 2 (`plan_outline`, `generate_act`, `merge_acts`, `validate_outline`), `fact_check_script`, `validate_script_structure` (scaled), `_research_items(max_sources)`, `_render_packet`.
- Produces: `generate_youtube_video(..., documentary: bool = False, brief: str | None = None)`; mode `"documentary"` → cinematic + documentary branch.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_documentary_branch_aborts_when_an_act_fails(tmp_path, monkeypatch):
    from app import documentary
    from app.youtube import generate_youtube_video

    acts = [
        documentary.ActPlan(title="A", hook="h", beats=["b"] * 7, sources=[0]),
        documentary.ActPlan(title="B", hook="h", beats=["b"] * 7, sources=[0]),
        documentary.ActPlan(title="C", hook="h", beats=["b"] * 7, sources=[0]),
    ]
    monkeypatch.setattr(
        documentary, "plan_outline",
        AsyncMock(return_value=documentary.DocumentaryOutline(title="Doc", acts=acts)),
    )

    calls = {"n": 0}

    async def fake_act(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("act provider down")
        return (
            "---\ntitle: Doc\ndescription: D\npreset: adult_male\n---\n\n"
            "# Scene 1 — X\nVoiceover: \"A sufficiently long narration line here.\"\nScene: art.\n"
        )

    monkeypatch.setattr(documentary, "generate_act", fake_act)
    # ... pipeline mocks per the gate-test pattern (resolve FINANCE-like,
    # fetch {"headline": "T", "items": []}, record, audio [], frames [],
    # run, thumb {}, research packet, VIDEOS_DIR) ...
    # assert await generate_youtube_video(..., documentary=True, storyboard_override=None?) is None
```

File header additions for the new tests: `import uuid` top-level, plus
`from unittest.mock import AsyncMock, MagicMock, patch` and
`from app.channels import Channel`. (The pure tests above use local imports;
the pipeline tests below use these top-level ones.)

```python
DOC_FINANCE = Channel(
    id="financial-channel", display_name="Finance", voice_key="adult_male",
    script_prompt="Be sober.", extra_blocklist=(),
)


def _doc_act_board(start, n=7):
    scenes = "\n\n".join(
        f"# Scene {i} — Ch{i}\n"
        f"Voiceover: \"A sufficiently long narration line for scene {i} here.\"\n"
        f"Scene: art {i}."
        for i in range(start, start + n)
    )
    return f"---\ntitle: Doc\ndescription: D\npreset: adult_male\n---\n\n{scenes}"


def _doc_acts():
    from app import documentary

    return [
        documentary.ActPlan(title="A", hook="h", beats=["b"] * 7, sources=[0]),
        documentary.ActPlan(title="B", hook="h", beats=["b"] * 7, sources=[1]),
        documentary.ActPlan(title="C", hook="h", beats=["b"] * 7, sources=[2]),
    ]


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=DOC_FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story", AsyncMock(side_effect=AssertionError("shorts path must not run")))
@patch("app.youtube._generate_frame_audio", AsyncMock(return_value=[]))
@patch("app.youtube._build_frames", AsyncMock(return_value=[]))
@patch("app.youtube.subprocess.run")
@patch("app.youtube.build_thumbnail_variants", AsyncMock(return_value={}))
@patch("app.youtube.fact_check_script", AsyncMock(return_value={"verdict": "PASS", "violations": []}))
@patch("app.youtube._research_packet", return_value="packet")
async def test_documentary_branch_aborts_when_an_act_fails(
    mock_packet, mock_fact, mock_thumb, mock_run, mock_frames, mock_audio, mock_record, mock_fetch, tmp_path, monkeypatch
):
    from app import documentary
    from app.youtube import generate_youtube_video

    monkeypatch.setattr(
        documentary, "plan_outline",
        AsyncMock(return_value=documentary.DocumentaryOutline(title="Doc", acts=_doc_acts())),
    )
    calls = {"n": 0}

    async def fake_act(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("act provider down")
        return _doc_act_board(1)

    monkeypatch.setattr(documentary, "generate_act", fake_act)
    mock_fetch.return_value = {"headline": "T", "items": [
        {"title": "T0", "url": "https://x/0", "source_name": "S", "published_at": None, "full_text": "body"},
    ]}
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(
            story_id=uuid.uuid4(), channel_id="financial-channel",
            documentary=True, brief="owner notes",
        ) is None
    assert calls["n"] == 2
    mock_record.assert_not_called()


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=DOC_FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story", AsyncMock(side_effect=AssertionError("shorts path must not run")))
@patch("app.youtube._generate_frame_audio", AsyncMock(return_value=[]))
@patch("app.youtube._build_frames", AsyncMock(return_value=[]))
@patch("app.youtube.subprocess.run")
@patch("app.youtube.build_thumbnail_variants", AsyncMock(return_value={}))
@patch("app.youtube.fact_check_script", AsyncMock(return_value={"verdict": "PASS", "violations": []}))
@patch("app.youtube._research_packet", return_value="packet")
async def test_documentary_happy_path_merges_and_records(
    mock_packet, mock_fact, mock_thumb, mock_run, mock_frames, mock_audio, mock_record, mock_fetch, tmp_path, monkeypatch
):
    from app import documentary
    from app.youtube import generate_youtube_video

    monkeypatch.setattr(
        documentary, "plan_outline",
        AsyncMock(return_value=documentary.DocumentaryOutline(title="Doc", acts=_doc_acts())),
    )
    boards = [_doc_act_board(1), _doc_act_board(8), _doc_act_board(15)]
    monkeypatch.setattr(
        documentary, "generate_act",
        AsyncMock(side_effect=list(boards)),
    )
    story_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "T", "items": [
        {"title": "T0", "url": "https://x/0", "source_name": "S", "published_at": None, "full_text": "body"},
    ]}
    mock_record.return_value = uuid.uuid4()
    mock_run.return_value = MagicMock(stdout="mocked")
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=story_id, channel_id="financial-channel",
            documentary=True, brief="owner notes",
        )
    assert draft_id is not None
    assert mock_fact.await_count == 3
    board_text = (tmp_path / f"story-{story_id}" / "STORYBOARD.md").read_text(encoding="utf-8")
    assert board_text.count("# Scene") == 21
    assert board_text.count("---") == 2  # one frontmatter block


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=DOC_FINANCE))
@patch("app.youtube._fetch_story_details",
       AsyncMock(return_value={"headline": "T", "items": []}))
async def test_documentary_needs_evidence_or_brief(mock_fetch, tmp_path):
    from app.youtube import generate_youtube_video

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(
            story_id=uuid.uuid4(), channel_id="financial-channel", documentary=True,
        ) is None
```

Decorator/parameter audit (bottom-up, `new=` never injects): `fact_check_script`
(new) and `_generate_script_for_story` (new) and `resolve` (new) take no
parameters; the rest map `research_packet`→mock_packet, `fact`→mock_fact
(absent in abort test? no — present in both: order is
research_packet, fact, thumb, run, frames, audio, record, fetch, then
`tmp_path`, then `monkeypatch` fixture). In the abort test the parameter list
is `(mock_packet, mock_fact, mock_thumb, mock_run, mock_frames, mock_audio,
mock_record, mock_fetch, tmp_path, monkeypatch)` — bottom-up: research→packet,
fact→fact, thumb→thumb, run→run, frames→frames, audio→audio, record→record,
fetch→fetch, resolve skipped ✓, tmp_path + monkeypatch are fixtures ✓.
The `needs_evidence` test: decorators resolve(new) + fetch(new) only, params
`(mock_fetch, tmp_path)` — WAIT, both supply `new=`, so NEITHER injects; the
params would be unfillable. Fix: `mock_fetch` must come from a bare patch.
Use `@patch("app.youtube._fetch_story_details")` (bare → injects) with
`mock_fetch.return_value = ...` set in the body:

```python
@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=DOC_FINANCE))
@patch("app.youtube._fetch_story_details")
async def test_documentary_needs_evidence_or_brief(mock_fetch, tmp_path):
    from app.youtube import generate_youtube_video

    mock_fetch.return_value = {"headline": "T", "items": []}
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(
            story_id=uuid.uuid4(), channel_id="financial-channel", documentary=True,
        ) is None
```

USE THIS CORRECTED FORM (bare fetch patch, return set in body).

Mode test (append to `test_routes_modes.py`):

```python
def test_documentary_selects_the_image_led_cinematic_backend():
    assert backend_for_mode("documentary") == "cinematic"
```

(Plus `MODE_BACKENDS` completeness is covered by the existing
`test_every_declared_mode_is_resolvable`.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_documentary.py -q -k "branch or mode"`
Expected: FAIL with `TypeError` (no `documentary` flag / branch yet)

- [ ] **Step 3: Implement the branch (fall-through, not a helper)**

No `_generate_documentary_video` helper — that would duplicate the 200-line
shared tail. Instead, the existing scripting conditional becomes three arms
that all set `script_content`, then fall through to the untouched shared tail
(metadata → parse → MIN guard → audio → frames → render → thumbnails →
draft). Convert `if storyboard_override... else...` into:

```python
    if documentary:
        from app import documentary as doc
        from app.script_quality import (
            MAX_ACT_SCENES, MAX_DOC_SCENES, MIN_ACT_SCENES, MIN_DOC_SCENES,
        )

        if storyboard_override and storyboard_override.strip():
            script_content = _ensure_storyboard_metadata(
                storyboard_override,
                fallback_title=str(story.get("headline") or "Manual storyboard"),
            )
            violations = validate_script_structure(
                script_content, min_scenes=MIN_DOC_SCENES, max_scenes=MAX_DOC_SCENES,
            )
            if violations:
                log.error(
                    "youtube_generation_aborted",
                    reason="documentary_contract_failed",
                    story_id=str(story_id),
                    violations=violations,
                )
                return None
        else:
            if not (story.get("items") or (brief or "").strip()):
                log.error(
                    "youtube_generation_aborted",
                    reason="documentary_needs_evidence",
                    story_id=str(story_id),
                )
                return None
            try:
                items = _research_items(story, max_sources=12)
                drafter = doc.drafter_provider()
                outline = await doc.plan_outline(
                    headline=str(story.get("headline") or "Untitled"),
                    packet=_render_packet(items),
                    provider=drafter,
                    n_sources=len(items),
                )
                dealt = doc.deal_sources(items, len(outline.acts))
                act_markdowns = []
                first_scene = 1
                recap = ""
                for index, act in enumerate(outline.acts):
                    bundle = _render_packet(dealt[index])
                    if brief and brief.strip():
                        bundle = (
                            "OWNER BRIEF (context, not sourced fact — "
                            "dispute claims are FLAG, not BLOCK):\n"
                            f"{brief.strip()}\n\n{bundle}"
                        )
                    text = await doc.generate_act(
                        act=act, act_index=index, n_acts=len(outline.acts),
                        first_scene=first_scene, recap=recap, bundle_text=bundle,
                        channel_prompt=channel.script_prompt, provider=drafter,
                        want_hook=index == 0,
                        want_closing=index == len(outline.acts) - 1,
                    )
                    violations = validate_script_structure(
                        text, min_scenes=MIN_ACT_SCENES, max_scenes=MAX_ACT_SCENES,
                        require_hook=index == 0,
                        require_closing=index == len(outline.acts) - 1,
                    )
                    if violations:
                        raise ValueError(
                            f"act {index + 1} failed contract: {'; '.join(violations)}"
                        )
                    verdict = await fact_check_script(
                        script=text, evidence_packet=bundle, exclude=(drafter,),
                    )
                    if verdict.get("verdict") == "BLOCK":
                        await audit_log(
                            actor="worker", action="script_fact_check_blocked",
                            entity=str(story_id), entity_type="story",
                            after={"violations": verdict.get("violations", []),
                                   "act": index + 1},
                        )
                        log.error(
                            "youtube_generation_aborted", reason="fact_check_blocked",
                            story_id=str(story_id), act=index + 1,
                        )
                        return None
                    if verdict.get("verdict") == "FLAG":
                        log.warning(
                            "script_fact_check_flagged",
                            story_id=str(story_id), act=index + 1,
                        )
                    recap = doc.last_voiceover(text)[-doc.RECAP_CHARS:]
                    act_markdowns.append(text)
                    first_scene += len(parse_storyboard(text).frames)
                script_content = doc.merge_acts(act_markdowns)
                script_content = _append_research_sources(script_content, story)
                violations = validate_script_structure(
                    script_content, min_scenes=MIN_DOC_SCENES, max_scenes=MAX_DOC_SCENES,
                )
                if violations:
                    raise ValueError(
                        f"merged board failed contract: {'; '.join(violations)}"
                    )
            except Exception as e:
                log.error(
                    "youtube_generation_aborted", reason="documentary_act_failed",
                    story_id=str(story_id), error=str(e)[:200],
                )
                return None
    elif storyboard_override and storyboard_override.strip():
```

(`validate_script_structure`, `fact_check_script`, `audit_log`,
`parse_storyboard`, `_ensure_storyboard_metadata`, `_append_research_sources`,
`_research_items`, `_render_packet`, `os`, `log` are all already in scope in
`generate_youtube_video`. `RECAP_CHARS` lives in documentary.py alongside
`drafter_provider()`. The pre-existing `if storyboard_override...` becomes the
`elif`, and its `else` (Shorts scripting) is untouched — the rest of the
function, from `_apply_cinematic_controls` through the draft record, runs
unchanged for all three arms. Tags default to `[]` when act 1 carries none.)

`routes.py`: `MODE_BACKENDS` gains `"documentary": "cinematic"`. Both job
endpoints pass the flag: `documentary=(req.mode == "documentary")` for
`/youtube/jobs`; with-voice endpoint has `mode` form field too — pass the
same expression. `YouTubeJobRequest` gains `brief: str | None =
Field(default=None, max_length=2000)`; with-voice gains `brief: str | None =
Form(default=None, max_length=2000)`. Pass `brief=` through in
both `run()` closures.

- [ ] **Step 4: Run green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_documentary.py tests/test_routes_modes.py tests/test_youtube.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/app/youtube.py worker/app/routes.py worker/tests/test_documentary.py worker/tests/test_routes_modes.py
git commit -m "Wire documentary mode through the cinematic pipeline"
```

---

### Task 4: Full verification + record + push

**Files:**
- Modify: `PROGRESS.md` (decision #81)

- [ ] **Step 1: Run the affected suites**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_documentary.py tests/test_script_quality.py tests/test_routes_modes.py tests/test_youtube.py tests/test_upload_metadata.py tests/test_generation_resilience.py tests/test_storyboard.py tests/test_llm_router.py tests/test_score.py tests/test_channels.py tests/test_seed_channels.py -q`
Expected: PASS (DB-backed tests need local Postgres; without it they error — pre-existing, unrelated)

- [ ] **Step 2: Record the decision in PROGRESS.md**

```
| 81 | Long-form as acts on the cinematic path; per-act gates, merged render | long-form | Outline→acts→merge; 3-4×7-9 scenes (21-36). Same validator scaled, same fact-check per act. New mode + pacing, brief labeled owner-supplied. API-first. |
```

- [ ] **Step 3: Commit and push**

```bash
git add PROGRESS.md
git commit -m "Record long-form decision"
git push
```
