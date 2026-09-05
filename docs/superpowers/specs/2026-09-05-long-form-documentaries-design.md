# Long-Form Documentaries (8–12 min) — Design

**Date:** 2026-09-05
**Status:** Approved, awaiting implementation plan
**Scope:** Final Kutly track. Act-structured 20–30-scene documentaries on the
cinematic backend for history/science/mystery. API-first; no GUI button yet.

## Problem

Everything caps at Shorts length: the script contract enforces 4–8 scenes,
one LLM call writes the whole board, evidence caps at 4 sources, and
`MAX_VOICE_CLIPS` stops at 12. A single call stretched to 30 scenes risks
mid-act truncation — output that renders and validates like a finished
documentary but ends mid-thought.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Outline first, then one call per act with recap | Truncation aborts one act visibly instead of corrupting a whole; recaps keep continuity without a 100k context. |
| 2 | Any act failure aborts the run | No partial documentaries, same family as never-substitute. |
| 3 | Same validator, mode-scaled bounds | One contract, two sizes — no parallel rulebook to drift. |
| 4 | Act evidence = story cluster items split across acts + optional brief | Clustering already groups related coverage; the brief covers what feeds lack (backstory, outcome). |
| 5 | Merged board uses the entire existing downstream | Timing, frames, render, thumbnails, tags, upload, draft — proven by pieces 1–4, reused untouched. |

## Acts

`plan_documentary_outline(story, brief) -> DocumentaryOutline` (JSON via the
LLM router, new `documentary_outline` task): title + 3–4 acts, each with a
hook line, 5–9 scene beats, and the subset of source indices it may claim
from. Outline validation is structural (act count, beat counts, source
indices in range); failure aborts pre-script.

`_generate_act_script(act, outline, recap, bundle, channel, cinematic)`:
same system shape as `_generate_script_for_story` (research rules +
structure contract, act-scoped: scenes headed `# Scene N — <chapter>` with
global N continuing across acts, hook only in act 1, closing beat only in
the final act's last scene) plus the previous act's closing lines as recap
(≤500 chars). Returns the act's scene markdown (no frontmatter except act 1,
which carries title/description/tags for the whole board).

Evidence: `_research_items(story, max_sources=...)` gains the parameter
(default 4 — every existing caller unchanged); the documentary path pulls up
to 12 items and deals them round-robin across acts (even coverage beats
front-loading), each act packet rendered by the existing serializer.
Optional `brief: str` (≤2000 chars, owner-written context) is prepended to
every act packet verbatim and labeled as owner-supplied, never as sourced
fact — the fact-checker treats brief claims as FLAG-at-most, never BLOCK.

## Gates

Per act, in order: structure-validate (long-form bounds) → fact-check
against that act's bundle (existing `fact_check` task, drafter excluded).
BLOCK or exhaustion aborts the run. Merge concatenates act scenes under one
frontmatter + `# Video direction` + research-sources section; the merged
board re-validates whole (chapter uniqueness across acts, 20–30 scenes).

## Render/publish

New mode `documentary` → backend `cinematic` (`MODE_BACKENDS` +
`backend_for_mode`, same raise-on-typo rule). New `documentary` pacing
profile (`floor=3.0, soft_ceiling=16.0, lead_in=0.3, tail=0.6` — narration-led
like explainer, room to breathe like story). `MAX_VOICE_CLIPS` 12 → 40 with
the per-clip byte cap unchanged. Ops note: a 10-minute render wants
`HYPERFRAMES_TIMEOUT_SECONDS` headroom — documented, not raised globally.
Thumbnails, tags, upload.txt, draft body: unchanged.

## Testing

- Pure: outline validation (bad counts, out-of-range source indices),
  round-robin dealing (even split, remainder order), long-form validator
  bounds (19/31 scenes fail, per-act overrun fails, dup chapter across acts
  fails), pacing math on a 25-scene board.
- Pipeline (seams mocked): act-2 failure aborts with nothing rendered;
  merge order and global scene numbering; brief labeled owner-supplied;
  fact-check called once per act with that act's bundle.
- Regression: Shorts bounds and behavior byte-identical (existing suites).

## Non-goals (later)

- 20–30 min, per-topic feeds, GUI documentary button, multi-voice cast,
  chapter markers in metadata, background music scoring.

## Files touched

- `worker/app/youtube.py` (outline, act scripting, merge, mode mapping, caps)
- `worker/app/storyboard.py` (`documentary` pacing profile)
- `worker/app/taxonomy.py` (untouched — verified, not modified)
- `worker/app/routes.py` (`mode` already free-form through `backend_for_mode`)
- Tests: new `worker/tests/test_documentary.py`; existing suites untouched
