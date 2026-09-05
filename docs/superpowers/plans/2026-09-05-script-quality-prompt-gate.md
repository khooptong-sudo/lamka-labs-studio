# Script Quality (Prompt+Gate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce a hook/chapter/closing contract on generated scripts and cross-model fact-check every generated board against its evidence packet before TTS burns a cent.

**Architecture:** New pure module `app/script_quality.py` (validator + fact-check client, no DB/I/O except via the router); one backwards-compatible `exclude` parameter on `router.complete_json` so the checker structurally cannot run on the drafter's provider; wiring inside `generate_youtube_video`'s generated path only (override boards stay byte-intact); aborts return `None` like every existing abort in that function.

**Tech Stack:** Python, FastAPI worker, `app.llm.router.complete_json`, `app.storyboard.parse_storyboard`, `app.audit.audit_log`, pytest with `unittest.mock` (patch the router seam, never providers — bug #13).

**Spec:** `docs/superpowers/specs/2026-09-05-script-quality-prompt-gate-design.md`

## Global Constraints

- Never auto-publish; FLAG continues to human review, BLOCK aborts pre-TTS.
- Never fabricate or repair a script on failure; raise / return `None` with the report attached.
- Tests must not touch the network; patch `app.llm.router.complete_json` (or `app.youtube.fact_check_script` at the pipeline seam), never a provider.
- Frame generation stays sequential; no concurrency changes in this plan.
- PowerShell 5.1 for any owner-facing commands (no `&&`); pytest runs as `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`.
- Do not run the full DB-backed suite while an end-to-end render is in flight (DB tests truncate tables).

---

### Task 1: Router `exclude` parameter

**Files:**
- Modify: `worker/app/llm/router.py`
- Test: `worker/tests/test_llm_router.py` (append; reuse `routed`, `_provider_returning`, `_no_backoff` fixtures)

**Interfaces:**
- Consumes: `get_llm_config()` routing map (unchanged shape).
- Produces: `complete_json(task, *, system, user, spec, max_attempts=4, exclude=())` — `exclude: tuple[str, ...]` filters the resolved chain before any call; empty-after-filter raises `RouterError` naming the exclusion.

- [ ] **Step 1: Write the failing tests**

```python
async def test_exclude_skips_the_named_provider(routed, monkeypatch):
    primary = _provider_returning('{"verdict": "yes"}')
    fallback = _provider_returning('{"verdict": "no"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", primary),
    )
    monkeypatch.setitem(
        providers.PROVIDERS, "deepseek",
        providers.Provider("deepseek", "DEEPSEEK_API_KEY", fallback),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC, exclude=("gemini",))
    assert result == {"verdict": "no"}
    assert len(primary.calls) == 0


async def test_exclude_everything_raises_loudly(routed):
    with pytest.raises(router.RouterError, match="exclud"):
        await router.complete_json(
            "demo", system="s", user="u", spec=SPEC, exclude=("gemini", "deepseek"),
        )
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_llm_router.py -q`
Expected: FAIL with `TypeError: complete_json() got an unexpected keyword argument 'exclude'`

- [ ] **Step 3: Implement `exclude` in the router**

```python
async def _resolve(task: str, exclude: tuple[str, ...] = ()) -> list[str]:
    """Ordered, usable provider names for a task. Empty means unroutable."""
    cfg = await get_llm_config()
    route = cfg.routing.get(task)
    if route is None:
        return []
    if not isinstance(route, dict):
        raise RouterError(f"route for task {task!r} is not a mapping: {route!r}")
    have = providers.available()
    named = [route.get("primary"), route.get("fallback")]
    chain = [name for name in named if name and name in have and name not in exclude]
    skipped = [name for name in named if name and (name not in have or name in exclude)]
    if skipped:
        log.info("llm_routing_decision", task=task, chain=chain, skipped=skipped)
    else:
        log.debug("llm_routing_decision", task=task, chain=chain)
    return chain
```

```python
async def complete_json(
    task: str,
    *,
    system: str,
    user: str,
    spec: contract.FieldSpec,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    exclude: tuple[str, ...] = (),
) -> dict:
    """..."""
    chain = await _resolve(task, exclude)
    if not chain:
        raise RouterError(f"no available provider for task {task!r} after excluding {list(exclude)}")
```

Rest of `complete_json` is untouched.

- [ ] **Step 4: Run router tests green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_llm_router.py -q`
Expected: PASS (all pre-existing tests unaffected — default `exclude=()` preserves the old chain exactly)

- [ ] **Step 5: Commit**

```bash
git add worker/app/llm/router.py worker/tests/test_llm_router.py
git commit -m "Add exclude param to LLM router for cross-model checks"
```

---

### Task 2: `script_quality` module (validator + fact-check client)

**Files:**
- Create: `worker/app/script_quality.py`
- Test: `worker/tests/test_script_quality.py`

**Interfaces:**
- Consumes: `app.storyboard.parse_storyboard`, `app.llm.router.complete_json`, `app.llm.contract.FieldSpec`.
- Produces: `validate_script_structure(script_text: str) -> list[str]`; `fact_check_script(*, script: str, evidence_packet: str, exclude: tuple[str, ...]) -> dict`; `FACT_CHECK_SPEC`, `MIN_GENERATED_SCENES=4`, `MAX_GENERATED_SCENES=8`, `MAX_HOOK_WORDS=25`, `MIN_CLOSING_WORDS=5`.

- [ ] **Step 1: Write the failing validator tests**

```python
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
    two = "\n\n".join(GOOD_BOARD.split("\n\n")[:5])
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_script_quality.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.script_quality'` (or `ImportError` — the module does not exist yet)

- [ ] **Step 3: Implement the validator half of `script_quality.py`**

```python
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
MAX_HOOK_WORDS = 25
MIN_CLOSING_WORDS = 5

BANNED_HOOK_OPENERS = ("what if i told you",)

_SENTENCE_END = re.compile(r"[.!?]")


def _first_sentence(text: str) -> str:
    match = _SENTENCE_END.search(text)
    return (text[: match.start()] if match else text).strip().strip("\"'")


def validate_script_structure(script_text: str) -> list[str]:
    """Return human-readable violations. Empty means the board meets the contract."""
    violations: list[str] = []
    board = parse_storyboard(script_text)
    frames = board.frames

    if not (MIN_GENERATED_SCENES <= len(frames) <= MAX_GENERATED_SCENES):
        violations.append(
            f"expected {MIN_GENERATED_SCENES}-{MAX_GENERATED_SCENES} scenes, found {len(frames)}"
        )
        return violations

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
    if len(closing_words) < MIN_CLOSING_WORDS:
        violations.append("final scene has no closing beat: voiceover is too short to close on")

    return violations
```

- [ ] **Step 4: Run validator tests green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_script_quality.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing fact-check tests (append to same file)**

```python
"""Fact-check client: router seam patched, never a provider (bug #13)."""

from unittest.mock import AsyncMock

import pytest

from app import script_quality
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
```

- [ ] **Step 6: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_script_quality.py -q`
Expected: FAIL with `AttributeError: FACT_CHECK_SPEC` (validator half exists, fact-check half does not)

- [ ] **Step 7: Implement the fact-check half (append to `script_quality.py`)**

```python
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
```

- [ ] **Step 8: Run module tests green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_script_quality.py tests/test_llm_router.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add worker/app/script_quality.py worker/tests/test_script_quality.py
git commit -m "Add script structure validator and cross-model fact-check client"
```

---

### Task 3: Hook/chapter contract in the generation prompt

**Files:**
- Modify: `worker/app/youtube.py` (`_generate_script_for_story` system instruction only)
- Test: `worker/tests/test_youtube.py` (prompt-content assertion; no network)

**Interfaces:**
- Consumes: `channel.script_prompt`, `channel.voice_key` (unchanged).
- Produces: same `str` storyboard markdown, now contract-shaped.

- [ ] **Step 1: Write the failing test (append to `test_youtube.py`)**

```python
def test_script_prompt_carries_the_hook_and_chapter_contract():
    import inspect
    from app import youtube
    source = inspect.getsource(youtube._generate_script_for_story)
    assert "hook" in source.lower()
    assert "4" in source and "8 scenes" in source
    assert "chapter" in source.lower()
    assert "What if I told you" in source
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_youtube.py::test_script_prompt_carries_the_hook_and_chapter_contract -q`
Expected: FAIL (contract text not in the prompt yet)

- [ ] **Step 3: Extend the FORMAT block in `_generate_script_for_story`**

In `worker/app/youtube.py`, inside `system_instruction`, after the `# Scene 1` example lines and before the closing `"""`, insert:

```
STRUCTURE CONTRACT (the validator enforces this; a board that breaks it is discarded):
- 4-8 scenes, each a new visual beat. Heading form: `# Scene N — <chapter>` with a
  unique, non-empty chapter title per scene.
- Scene 1 Voiceover opens with the hook as its first sentence: at most 25 words,
  naming the concrete stake. Never open with "What if I told you…".
- Restate the stake for the viewer roughly every third scene.
- The final scene closes the story (a takeaway or verdict), never a trailing fact.
```

Do not touch RESEARCH RULES, frontmatter shape, or the cinematic direction block.

- [ ] **Step 4: Run prompt test green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_youtube.py::test_script_prompt_carries_the_hook_and_chapter_contract -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/app/youtube.py worker/tests/test_youtube.py
git commit -m "Add hook and chapter contract to script generation prompt"
```

---

### Task 4: Wire the gates into the generated path

**Files:**
- Modify: `worker/app/youtube.py` (`generate_youtube_video` generated branch + import)
- Modify: `worker/app/config.py` (`LLMConfig.routing` default: add `"fact_check": {"primary": "deepseek", "fallback": "openai"}`)
- Test: `worker/tests/test_youtube.py` (gate tests), `worker/tests/test_score.py` untouched

**Interfaces:**
- Consumes: `script_quality.validate_script_structure`, `script_quality.fact_check_script`, `audit_log`, `router.RouterError`.
- Produces: generated path aborts (`None`) on structure violations, RouterError, or BLOCK; FLAG audits and continues; override path untouched.

- [ ] **Step 1: Write the failing gate tests (append to `test_youtube.py`)**

```python
GOOD_CONTRACT_BOARD = (
    "---\ntitle: Test\ndescription: A test description.\npreset: adult_male\n---\n\n"
    "# Scene 1 — The hook\nVoiceover: \"City budgets hide one line that explains every pothole.\"\nScene: A street cracking.\n\n"
    "# Scene 2 — The mechanism\nVoiceover: \"The maintenance fund is raided each spring for festivals.\"\nScene: Coins moved between jars.\n\n"
    "# Scene 3 — Why it matters\nVoiceover: \"That is why your street floods while the parade gets louder.\"\nScene: Flood beside a parade.\n\n"
    "# Scene 4 — The takeaway\nVoiceover: \"Read the maintenance line first and budgets finally make sense.\"\nScene: A magnifier on one line.\n"
)

SHORT_BOARD = (
    "---\ntitle: Test\ndescription: A test description.\n---\n\n"
    "# Scene 1\nVoiceover: A\n\n# Scene 2\nVoiceover: B\n"
)


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube.fact_check_script")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube._generate_thumbnail")
async def test_structurally_invalid_board_aborts_before_audio(
    mock_thumb, mock_run, mock_frames, mock_audio, mock_fact, mock_script, mock_record, mock_fetch, tmp_path
):
    story_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.return_value = SHORT_BOARD
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(story_id=story_id, channel_id="financial-channel") is None
    mock_fact.assert_not_called()
    mock_audio.assert_not_called()


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube.fact_check_script")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube._generate_thumbnail")
async def test_fact_check_block_aborts_before_audio(
    mock_thumb, mock_run, mock_frames, mock_audio, mock_fact, mock_script, mock_record, mock_fetch, tmp_path
):
    story_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.return_value = GOOD_CONTRACT_BOARD
    mock_fact.return_value = {"verdict": "BLOCK", "violations": [{"quote": "x", "reason": "y"}]}
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(story_id=story_id, channel_id="financial-channel") is None
    mock_audio.assert_not_called()
    mock_record.assert_not_called()


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube.fact_check_script")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube._generate_thumbnail")
async def test_fact_check_flag_continues_to_render(
    mock_thumb, mock_run, mock_frames, mock_audio, mock_fact, mock_script, mock_record, mock_fetch, tmp_path
):
    story_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.return_value = GOOD_CONTRACT_BOARD
    mock_fact.return_value = {"verdict": "FLAG", "violations": []}
    mock_audio.return_value = []
    mock_frames.return_value = []
    mock_record.return_value = draft_id
    mock_run.return_value = MagicMock(stdout="Mocked hyperframes output")
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(story_id=story_id, channel_id="financial-channel") == draft_id


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube.fact_check_script")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube._generate_thumbnail")
async def test_fact_check_exhaustion_aborts_loudly(
    mock_thumb, mock_run, mock_frames, mock_audio, mock_fact, mock_script, mock_record, mock_fetch, tmp_path
):
    from app.llm.router import RouterError
    story_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.return_value = GOOD_CONTRACT_BOARD
    mock_fact.side_effect = RouterError("no available provider for task 'fact_check'")
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(story_id=story_id, channel_id="financial-channel") is None
    mock_audio.assert_not_called()
```

Note: `mock_fetch.return_value = {"headline": ...}` has no linked items, so `_research_packet` inside the gate raises `RuntimeError` (no sources) — the gate must compute the packet with `story` as given. These tests therefore need `_research_items`-backed stories OR the gate to reuse the packet the generator already built. To keep the seam honest, the wiring recomputes `_research_packet(story)`; tests patch `app.youtube._research_packet` to return `"packet"` with one extra decorator line per test:

```python
@patch("app.youtube._research_packet", return_value="SOURCE 1\nPublisher: T\nPublished: d\nTitle: t\nURL: u\nArticle excerpt: e")
```

Add that decorator (innermost, first parameter `mock_packet`) to each of the four gate tests above. The fact-check mock then receives a real packet string while `_research_items` never runs.

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_youtube.py -q -k "structurally_invalid or fact_check"`
Expected: FAIL with `AttributeError: module 'app.youtube' has no attribute 'fact_check_script'`

- [ ] **Step 3: Implement the wiring**

In `worker/app/youtube.py`:

a) Top-level import (audit touches only `app.db`; `youtube` already imports it — no cycle):

```python
from app.audit import audit_log
from app.script_quality import fact_check_script, validate_script_structure
```

b) In `generate_youtube_video`, generated branch, replace:

```python
            script_content = _append_research_sources(script_content, story)
```

with:

```python
            script_content = _append_research_sources(script_content, story)
            structure_violations = validate_script_structure(script_content)
            if structure_violations:
                log.error(
                    "youtube_generation_aborted",
                    reason="script_contract_failed",
                    story_id=str(story_id),
                    violations=structure_violations,
                )
                return None
            await _stage(job_id, "fact_check")
            drafter = os.environ.get("SCENE_MODEL_PROVIDER", "gemini").lower()
            evidence_packet = _research_packet(story)
            try:
                verdict = await fact_check_script(
                    script=script_content,
                    evidence_packet=evidence_packet,
                    exclude=(drafter,),
                )
            except Exception as e:
                log.error(
                    "youtube_generation_aborted",
                    reason="fact_check_failed",
                    story_id=str(story_id),
                    error=str(e),
                )
                return None
            if verdict.get("verdict") == "BLOCK":
                await audit_log(
                    actor="worker",
                    action="script_fact_check_blocked",
                    entity=str(story_id),
                    entity_type="story",
                    after={"violations": verdict.get("violations", [])},
                )
                log.error("youtube_generation_aborted", reason="fact_check_blocked", story_id=str(story_id))
                return None
            if verdict.get("verdict") == "FLAG":
                await audit_log(
                    actor="worker",
                    action="script_fact_check_flagged",
                    entity=str(story_id),
                    entity_type="story",
                    after={"violations": verdict.get("violations", [])},
                )
                log.warning("script_fact_check_flagged", story_id=str(story_id))
```

The override branch (`storyboard_override`) is untouched — an editor-reviewed board skips both gates.

c) In `worker/app/config.py`, extend the `LLMConfig.routing` default:

```python
    routing: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "story_score": {"primary": "kimi", "fallback": "openai"},
            "fact_check": {"primary": "deepseek", "fallback": "openai"},
        }
    )
```

`deepseek` first because the drafter defaults to `gemini` — the default chain is cross-model without any ops action. Deployments whose `llm` config row already exists must add the route once:

```sql
UPDATE config SET value = jsonb_set(value, '{routing,fact_check}', '{"primary": "deepseek", "fallback": "openai"}') WHERE key = 'llm';
```

- [ ] **Step 4: Update the legacy `SCRIPT_4_SCENES` fixture**

The generated-path tests that return `SCRIPT_4_SCENES` from the mocked generator now trip the validator (no chapter titles). Rewrite it contract-shaped, keeping four scenes:

```python
SCRIPT_4_SCENES = (
    "---\ntitle: Test\ndescription: A test description.\npreset: daisy-days\n---\n\n"
    "# Scene 1 — The hook\nVoiceover: \"City budgets hide one line that explains every pothole.\"\nScene: A street cracking.\n\n"
    "# Scene 2 — The mechanism\nVoiceover: \"The maintenance fund is raided each spring for festivals.\"\nScene: Coins moved between jars.\n\n"
    "# Scene 3 — Why it matters\nVoiceover: \"That is why your street floods while the parade gets louder.\"\nScene: Flood beside a parade.\n\n"
    "# Scene 4 — The takeaway\nVoiceover: \"Read the maintenance line first and budgets finally make sense.\"\nScene: A magnifier on one line.\n"
)
```

Those same tests must also patch the new gates: add to every generated-path test in `test_youtube.py` (and any in `test_generation_resilience.py` / `test_upload_metadata.py` that drives `generate_youtube_video` without an override):

```python
@patch("app.youtube.fact_check_script", AsyncMock(return_value={"verdict": "PASS", "violations": []}))
@patch("app.youtube._research_packet", return_value="packet")
```

with matching extra parameters (innermost decorator = first parameter).

- [ ] **Step 5: Run the affected suites green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_youtube.py tests/test_script_quality.py tests/test_llm_router.py tests/test_generation_resilience.py tests/test_upload_metadata.py tests/test_storyboard.py -q`
Expected: PASS. If any other generated-path test trips the validator, give its board chapter titles (same treatment as Step 4) — never weaken the validator to fit a fixture.

- [ ] **Step 6: Commit**

```bash
git add worker/app/youtube.py worker/app/config.py worker/tests/test_youtube.py worker/tests/test_generation_resilience.py worker/tests/test_upload_metadata.py
git commit -m "Wire script contract and fact-check gates into video pipeline"
```

---

### Task 5: Full suite + ops note

**Files:**
- Modify: `PROGRESS.md` (one row: script-quality gates live; fact_check route default + required SQL for existing deployments)

**Interfaces:** none (verification + docs).

- [ ] **Step 1: Run the full worker suite**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`
Expected: all green. DB-backed tests need local Postgres (`docker compose up -d db` from repo root); without it, DB tests error — that is pre-existing and expected, not a gate failure. Compare against the pre-change baseline, not against zero.

- [ ] **Step 2: Record the decision in PROGRESS.md**

Append to the decisions log table:

```
| 75 | Script contract + fact-check gate on the generated path; override boards skip both | quality-first | Hook/chapters/closing enforced by a pure validator; BLOCK aborts pre-TTS, FLAG audits and continues; drafter excluded via router so the checker is never the drafter |
```

And note the required ops action for the VPS (`llm` config row needs the `fact_check` route; the SQL from Task 4 Step 3c).

- [ ] **Step 3: Commit and push**

```bash
git add PROGRESS.md
git commit -m "Record script-quality gate decision and VPS ops note"
git push
```
