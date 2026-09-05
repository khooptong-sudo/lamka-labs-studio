# Views-Based Retention Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** YouTube view counts tilt future story scores toward what actually gets watched.

**Architecture:** Owner links video IDs per draft; a nightly job stores stats in the existing `metrics` table; scoring multiplies by a clamped archetype multiplier computed live per batch; a summary endpoint feeds a dashboard band. No migration, no prompt changes.

**Tech Stack:** Python worker (existing analytics fetcher, APScheduler job), Postgres, Next.js band, pytest with seams mocked.

**Spec:** `docs/superpowers/specs/2026-09-05-retention-loop-design.md`

## Global Constraints

- No migration (metrics table reused). No model-prompt changes.
- Missing OAuth creds fail loud in worker logs, render quiet UI ("analytics unavailable").
- Tests never touch YouTube API, network, or (for unit paths) real DB.
- PowerShell 5.1 (no `&&`); pytest as `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`; GUI `npx tsc --noEmit`.
- Working tree may hold unrelated uncommitted work: stage ONLY your files/hunks. Depend ONLY on committed code. Do NOT push (Task 3 pushes once).

---

### Task 1: Link field + stats job + multipliers

**Files:**
- Modify: `worker/app/youtube.py` or `routes.py` (video-id link endpoint — put `PATCH /drafts/{id}/video` next to the thumbnail endpoint, same file), `worker/app/score.py` (multiplier), `worker/app/scheduler.py` (job), `gui/src/app/drafts/page.tsx` (link input)
- Create: `worker/app/video_stats.py` (ID parsing, pull, aggregate)
- Test: `worker/tests/test_video_stats.py` (new)

**Interfaces:**
- Consumes: `get_youtube_analytics` (youtube.py), `metrics` table, drafts body jsonb.
- Produces: `extract_video_id(text) -> str | None`; `compute_multipliers(rows) -> dict[str, float]`; `video_stats_job()`; `multipliers_for_batch() -> dict[str, float]` (one aggregate SQL).

- [ ] **Step 1: Write the failing tests**

```python
"""Retention loop: ID parsing, multiplier math. No network, no DB."""


def test_extract_video_id_accepts_urls_and_bare_ids():
    from app.video_stats import extract_video_id

    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("not a url at all!!") is None
    assert extract_video_id("") is None


def test_multipliers_clamp_and_require_minimums():
    from app.video_stats import compute_multipliers

    rows = [
        {"archetype": "explainer", "views": 1000},
        {"archetype": "explainer", "views": 2000},
        {"archetype": "explainer", "views": 3000},
        {"archetype": "glossary_card", "views": 100},
    ]
    mults = compute_multipliers(rows, min_videos=3)
    assert mults["explainer"] == 1.3  # 2000 avg vs 1525 global → clamped
    assert mults["glossary_card"] == 1.0  # too few videos stays neutral


def test_multipliers_empty_is_neutral():
    from app.video_stats import compute_multipliers

    assert compute_multipliers([]) == {}
```

Check the math before implementing: global avg = (1000+2000+3000+100)/4 = 1525. explainer avg 2000/1525 = 1.31 → clamp 1.3 ✓. (Fix the comment if implementation differs — ratio of archetype avg to global avg of ALL videos.)

```python
async def test_stats_job_skips_quietly_without_creds(monkeypatch):
    import logging

    from app import video_stats

    monkeypatch.setattr(video_stats, "fetch_all_stats", None)  # must never be reached
```

Hmm — simpler: job calls `get_youtube_analytics` which raises on missing creds; assert the job catches, logs, and writes nothing (patch the DB write seam + analytics to raise). Write it against the real structure:

```python
async def test_stats_job_logs_and_skips_without_credentials(monkeypatch, caplog):
    from unittest.mock import AsyncMock

    from app import video_stats

    monkeypatch.setattr(
        video_stats, "get_youtube_analytics",
        AsyncMock(side_effect=RuntimeError("YouTube OAuth credentials are missing")),
    )
    written = []
    monkeypatch.setattr(video_stats, "upsert_video_stats", AsyncMock(side_effect=lambda *a: written.append(a)))
    with caplog.at_level("ERROR"):
        await video_stats.video_stats_job()
    assert written == []
    assert any("credentials" in r.message.lower() for r in caplog.records)
```

(Assumes `video_stats.get_youtube_analytics` is imported into that namespace —
implement as `from app.youtube import get_youtube_analytics` at module top so
this patch path is real. Same for DB helpers used.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_video_stats.py -q`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `worker/app/video_stats.py`**

```python
"""Nightly YouTube stats → archetype multipliers. No migration (metrics table)."""

VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})")
BARE_ID_RE = re.compile(r"\A[A-Za-z0-9_-]{11}\Z")

MIN_VIDEOS_PER_ARCHETYPE = 3
MIN_MULTIPLIER = 0.7
MAX_MULTIPLIER = 1.3
WINDOW_DAYS = 90


def extract_video_id(text: str) -> str | None: ...
def compute_multipliers(rows: list[dict], *, min_videos=MIN_VIDEOS_PER_ARCHETYPE) -> dict[str, float]: ...
async def video_stats_job() -> None: ...  # drafts with youtube_video_id → analytics → upsert metrics
```

Multiplier rule (exact): global_avg = mean(views) over all rows (rows with
views>0 only? No — include zeros, they are signal); per-archetype avg over
its rows; mult = avg/global clamped to [0.7, 1.3] rounded to 2dp; archetypes
with < min_videos rows are simply absent from the dict (caller treats missing
as 1.0). Empty input → {}.

`video_stats_job`: query drafts with `body->>'youtube_video_id'` set and no
metrics row in 7 days (one SQL); batch ids (≤50 per analytics call, matching
the fetcher); upsert one metrics row per video
(`platform='youtube'`, impressions/views, likes, replies/comments; delete-then-insert
or ON CONFLICT — check metrics unique constraint first: if none fits, delete
prior rows for the draft then insert; keep it to two statements max).
Missing creds (RuntimeError from the fetcher): error log, return, write nothing.

Link endpoint: `PATCH /drafts/{id}/video {video_id: str}` — validate with
`extract_video_id` (400 on garbage), store raw `body.youtube_video_id`... store
the NORMALIZED id or raw input? Store normalized id (canonical, no URL
variants). Return `{id, youtube_video_id}`. Mirror the thumbnail endpoint's
404/400 mapping and its `set_draft_*` db helper pattern.

Score integration in `score_new_job`: after router success, before
`write_score`: fetch multipliers once per batch
(`multiplier_map = await video_stats.multipliers_for_batch()` — one aggregate
SQL: trailing-90d youtube metrics joined drafts→stories, grouped by
content_archetype with counts), `mult = multiplier_map.get(vertical-archetype..., 1.0)`...
key by archetype only (vertical splits too thin at this volume — record this
decision in a comment), `result["score"] = round(result["score"] * mult)`,
include both in the write + audit path exactly as today (no new columns).

GUI drafts YouTube tab: "Link uploaded video" input + save (mono id preview),
reuse CopyField styling; Research dashboard "what's working" band: calls new
`GET /analytics/summary` (per-archetype totals + top 5 by views, pure read of
metrics+drafts+stories) rendered as compact stat chips. tsc clean.

- [ ] **Step 4: Run green + typecheck**

Run worker tests + `cd gui; npx tsc --noEmit`. PASS + clean.

- [ ] **Step 5: Commit**

```bash
git add worker/app/video_stats.py worker/app/routes.py worker/app/db.py worker/app/score.py worker/app/scheduler.py gui/src/app/drafts/page.tsx gui/src/app/page.tsx gui/src/lib/api.ts worker/tests/test_video_stats.py
git commit -m "Tilt story scores toward what gets watched"
```

(Stage only listed hunks if files are mixed; `db.py` only if a helper was added there.)

---

### Task 2: Full verification + record + push

**Files:**
- Modify: `PROGRESS.md` (decision #89)

- [ ] **Step 1: Run the affected suites**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_video_stats.py tests/test_score.py tests/test_youtube.py tests/test_routes_drafts.py -q`
Expected: PASS (DB paths need local Postgres — pre-existing rule)

- [ ] **Step 2: Record and push**

```
| 89 | Views tilt future scores; video IDs linked per draft | retention | Reused metrics table, no migration. Clamped multipliers, 3-video minimums, 90-day window. Manual link step (manual publishing has no callback). |
```

```bash
git add PROGRESS.md
git commit -m "Record retention-loop decision"
git push
```
