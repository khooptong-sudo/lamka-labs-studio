# New Channels (History, Science, Mystery) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three new documentary/education channels seedable without touching finance/kids, rendering on both backends with zero pipeline changes.

**Architecture:** Channel defaults live as code constants beside the seed script; a merge function adds missing ids only (existing entries byte-identical, stable order). Resolution, validation, gates, and both render backends are already channel-agnostic — this plan proves that per channel rather than changing it. No migration (config-table data), no GUI changes (selector is dynamic), no taxonomy additions, no feeds.

**Tech Stack:** Python worker, existing `channels.resolve` validation, pytest with `db.get_config` patching for resolve tests and full seam mocking for generation tests.

**Spec:** `docs/superpowers/specs/2026-09-05-new-channels-history-science-mystery-design.md`

## Global Constraints

- New channel defaults are code constants (git-traced); per-report tuning stays in the `config` table, never in code.
- `extra_blocklist` holds only terms NOT in `BASE_BLOCKLIST` (unioned at read time).
- Every `voice_key` must exist in `VOICE_MAP` (`teenage_boy`, `teenage_girl`, `adult_male`, `adult_female`, `news`, `baby`).
- Tests must not touch the network or a real DB; patch `db.get_config` / `db.set_config` and pipeline seams.
- PowerShell 5.1 for shells (no `&&`); pytest as `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`.
- The working tree may hold unrelated uncommitted work: stage ONLY your hunks/files. Depend ONLY on committed code. Do NOT push (Task 2 pushes once).

---

### Task 1: Built-in channels + merge-mode seeding

**Files:**
- Modify: `worker/scripts/seed_channels.py` (append `BUILT_IN_CHANNELS`, `ensure_builtin_channels`, merge `main`; `build_channels_payload` untouched)
- Test: `worker/tests/test_seed_channels.py` (append; legacy tests untouched)

**Interfaces:**
- Consumes: `VOICE_MAP` (voice validation, same `check_voice_key` helper — hoist it to module level so both builders share it), `BASE_BLOCKLIST` (extras filter).
- Produces: `BUILT_IN_CHANNELS: dict[str, dict]`; `ensure_builtin_channels(existing: dict | None) -> dict`.

- [ ] **Step 1: Write the failing tests** (append to `worker/tests/test_seed_channels.py`)

```python
def test_builtin_channels_use_known_voices():
    from app.youtube import VOICE_MAP
    from scripts.seed_channels import BUILT_IN_CHANNELS

    assert set(BUILT_IN_CHANNELS) == {"history", "science", "mystery"}
    for entry in BUILT_IN_CHANNELS.values():
        assert entry["voice_key"] in VOICE_MAP
        assert entry["display_name"].strip()
        assert entry["script_prompt"].strip()


def test_builtin_extras_exclude_base_terms():
    from app.channels import BASE_BLOCKLIST
    from scripts.seed_channels import BUILT_IN_CHANNELS

    for entry in BUILT_IN_CHANNELS.values():
        for term in BASE_BLOCKLIST:
            assert term not in entry["extra_blocklist"]


def test_ensure_adds_missing_and_never_touches_present():
    from scripts.seed_channels import ensure_builtin_channels

    existing = {"finance": {"display_name": "Finance", "voice_key": "adult_male",
                            "script_prompt": "tuned", "extra_blocklist": ["x"]}}
    merged = ensure_builtin_channels(existing)
    assert merged["finance"] == existing["finance"]
    assert set(merged) == {"finance", "history", "science", "mystery"}
    assert list(merged) == ["finance", "history", "science", "mystery"]


def test_ensure_on_empty_returns_builtins_only():
    from scripts.seed_channels import BUILT_IN_CHANNELS, ensure_builtin_channels

    assert ensure_builtin_channels(None) == BUILT_IN_CHANNELS
    assert ensure_builtin_channels({}) == BUILT_IN_CHANNELS


def test_ensure_rejects_a_bad_builtin_voice(monkeypatch):
    import scripts.seed_channels as seed

    monkeypatch.setitem(seed.BUILT_IN_CHANNELS, "broken",
                        {"display_name": "B", "voice_key": "nope",
                         "script_prompt": "p", "extra_blocklist": []})
    try:
        with pytest.raises(ValueError, match="nope"):
            seed.ensure_builtin_channels({})
    finally:
        del seed.BUILT_IN_CHANNELS["broken"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_seed_channels.py -q -k "builtin or ensure"`
Expected: FAIL with `ImportError` (no `BUILT_IN_CHANNELS` yet)

- [ ] **Step 3: Implement** (append to `worker/scripts/seed_channels.py`)

Hoist `check_voice_key` to module level (same body, using `VOICE_MAP`
imported inside the function as today — keep the local import to avoid
slowing every worker boot with the `openai`/`google` SDK chain `app.youtube`
pulls in). `build_channels_payload` keeps working unchanged by calling the
hoisted helper.

```python
BUILT_IN_CHANNELS: dict[str, dict] = {
    "history": {
        "display_name": "History, Explained",
        "voice_key": "news",
        "script_prompt": (
            "You are a measured documentary narrator for a history channel. "
            "Explain what happened, how, and why it mattered, in plain vivid language. "
            "State dates and claims only as supported by the evidence; say plainly "
            "when something is uncertain or disputed instead of smoothing it over. "
            "No present-day moralizing, no extremist glorification, no invented "
            "dialogue presented as fact."
        ),
        "extra_blocklist": [],
    },
    "science": {
        "display_name": "Science & Space",
        "voice_key": "adult_female",
        "script_prompt": (
            "You are a curious, warm explainer of space, physics, and nature for "
            "a general audience. Lead with mechanisms over marvels: how it works, "
            "then why it matters. Never give medical or financial advice, never "
            "promise outcomes, never use miracle language."
        ),
        "extra_blocklist": ["miracle cure", "guaranteed cure", "doctors hate"],
    },
    "mystery": {
        "display_name": "Mysteries & True Crime",
        "voice_key": "adult_male",
        "script_prompt": (
            "You are a sober case-driven narrator for a mystery channel. Lay out "
            "what is known, what is disputed, and what remains unknown. Living "
            "persons are alleged until convicted. Never detail a method an "
            "imitator could use, never glorify a perpetrator, and keep victim "
            "dignity above spectacle in every line."
        ),
        "extra_blocklist": ["how to kill", "graphic autopsy", "glorify the killer"],
    },
}


def ensure_builtin_channels(existing: dict | None) -> dict:
    """Return existing plus every missing built-in channel, validated.

    Present ids are returned untouched (same object values, stable order:
    existing first, additions appended). Raises ValueError on any invalid
    built-in entry — a bad default must fail the seed, never ship.
    """
    merged = dict(existing or {})
    for channel_id, entry in BUILT_IN_CHANNELS.items():
        if channel_id in merged:
            continue
        for field in ("display_name", "voice_key", "script_prompt"):
            if not entry.get(field) or not str(entry[field]).strip():
                raise ValueError(f"built-in channel {channel_id!r} is missing {field!r}")
        merged[channel_id] = {
            "display_name": entry["display_name"],
            "voice_key": check_voice_key(entry["voice_key"]),
            "script_prompt": entry["script_prompt"],
            "extra_blocklist": [t for t in entry.get("extra_blocklist", [])
                                if t not in BASE_BLOCKLIST],
        }
    return merged
```

Merge entrypoint (additive only; the legacy `main()` migration above it is
untouched):

```python
async def ensure_main() -> None:
    """Add missing built-in channels to the live row. Writes only on change."""
    from app.channels import CONFIG_KEY

    existing = await db.get_config(CONFIG_KEY) or {}
    merged = ensure_builtin_channels(existing)
    added = [cid for cid in merged if cid not in existing]
    if not added:
        print(f"{CONFIG_KEY}: already complete ({', '.join(sorted(existing))})")
        return
    await db.set_config(CONFIG_KEY, merged)
    print(f"{CONFIG_KEY}: added {', '.join(added)}; existing entries untouched")
```

Run mode: `python -m scripts.seed_channels ensure` vs default migrate. Extend
the `__main__` block:

```python
if __name__ == "__main__":
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    if len(sys.argv) > 1 and sys.argv[1] == "ensure":
        asyncio.run(ensure_main(), loop_factory=loop_factory)
    else:
        asyncio.run(main(), loop_factory=loop_factory)
```

(`sys` and `asyncio` already imported at seed top.)

- [ ] **Step 4: Run green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_seed_channels.py -q`
Expected: PASS (legacy + new)

- [ ] **Step 5: Commit**

```bash
git add worker/scripts/seed_channels.py worker/tests/test_seed_channels.py
git commit -m "Add built-in history/science/mystery channels with merge seeding"
```

---

### Task 2: Resolve + render matrix, record, push

**Files:**
- Create: `worker/tests/test_new_channels.py`
- Modify: `PROGRESS.md` (decision #80)
- Test: same new file (resolve + generation matrix)

**Interfaces:**
- Consumes: `channels.resolve` (patch `db.get_config`), `generate_youtube_video` (full seam mocks), `BUILT_IN_CHANNELS` (Task 1).
- Produces: proof each channel resolves and renders Short + film; PROGRESS row; push.

- [ ] **Step 1: Write the failing tests**

```python
"""New channels resolve and render on both backends. No DB, no network."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.channels import Channel
from scripts.seed_channels import BUILT_IN_CHANNELS, ensure_builtin_channels

CHANNEL_IDS = ["history", "science", "mystery"]

OVERRIDE_BOARD = (
    "---\ntitle: T\ndescription: D\npreset: adult_male\n---\n\n"
    "# Scene 1\nVoiceover: A\n\n# Scene 2\nVoiceover: B\n\n# Scene 3\nVoiceover: C\n"
)


def _config_row():
    base = {
        "finance": {"display_name": "Finance", "voice_key": "adult_male",
                    "script_prompt": "tuned", "extra_blocklist": []},
        "kids": {"display_name": "Kids", "voice_key": "baby",
                 "script_prompt": "tuned", "extra_blocklist": []},
    }
    return ensure_builtin_channels(base)


@pytest.mark.parametrize("channel_id", CHANNEL_IDS)
async def test_new_channel_resolves_with_its_voice_and_union_blocklist(channel_id):
    from app import channels

    with patch("app.db.get_config", AsyncMock(return_value=_config_row())):
        channel = await channels.resolve(channel_id)
    assert isinstance(channel, Channel)
    assert channel.voice_key == BUILT_IN_CHANNELS[channel_id]["voice_key"]
    assert channel.script_prompt == BUILT_IN_CHANNELS[channel_id]["script_prompt"]
    for term in BUILT_IN_CHANNELS[channel_id]["extra_blocklist"]:
        assert term in channel.effective_blocklist


@pytest.mark.parametrize("channel_id", CHANNEL_IDS)
@pytest.mark.parametrize("backend", ["cinematic", "three"])
async def test_new_channel_renders_short_and_film(tmp_path, channel_id, backend):
    from app import channels
    from app.youtube import generate_youtube_video

    with patch("app.db.get_config", AsyncMock(return_value=_config_row())):
        channel = await channels.resolve(channel_id)
    with patch("app.channels.resolve", AsyncMock(return_value=channel)), \
            patch("app.youtube._fetch_story_details", AsyncMock(return_value={"headline": "T"})), \
            patch("app.youtube._record_youtube_draft", AsyncMock(return_value=uuid.uuid4())) as record, \
            patch("app.youtube._generate_frame_audio", AsyncMock(return_value=[])), \
            patch("app.youtube._build_frames", AsyncMock(return_value=[])), \
            patch("app.youtube.subprocess.run"), \
            patch("app.youtube.build_thumbnail_variants", AsyncMock(return_value={})), \
            patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=uuid.uuid4(),
            channel_id=channel_id,
            backend=backend,
            storyboard_override=OVERRIDE_BOARD,
        )
    assert draft_id is not None
    record.assert_called_once()
```

Notes the implementer must honor: `channels.resolve` reads config through the
`app.db` module attribute at call time, so patching `app.db.get_config` steers
it with no DB. `OVERRIDE_BOARD` skips the structure validator and needs no tags.

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_new_channels.py -q`
Expected: FAIL with `ImportError` (no `BUILT_IN_CHANNELS` — Task 1 not yet in this branch of work... in practice Task 1 is committed first, so expect failures on `ensure_builtin_channels` behavior instead; either red is correct pre-implementation)

- [ ] **Step 3: Run green after Task 1 lands**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_new_channels.py tests/test_seed_channels.py tests/test_youtube.py tests/test_channels.py -q`
Expected: PASS. (If the `db.get_config` patch path is wrong per the note above, the resolve tests fail with a real pool attempt — fix the patch path to mirror `test_db_channel.py`, never touch prod code to fit the test.)

- [ ] **Step 4: Record the decision in PROGRESS.md**

```
| 80 | History/science/mystery channels seeded merge-only; both routes proven per channel | piece-5 | Built-ins in code, merge adds missing ids only. Shared taxonomy untouched. Manual-first; feeds are a follow-up. GUI already dynamic. |
```

- [ ] **Step 5: Commit and push**

```bash
git add worker/tests/test_new_channels.py PROGRESS.md
git commit -m "Prove new channels resolve and render on both routes"
git push
```
