# Overnight Autopilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Owner-queued stories render themselves overnight into Drafts; mornings start with review, not setup.

**Architecture:** A nullable flag column (never a status flip), a day-gated interval job reusing `generate_youtube_video` with all guards intact, and a moon toggle in the Inbox. Failure keeps the flag for tomorrow; success clears it. No new providers, no new formats, no publishing.

**Tech Stack:** Python worker (APScheduler interval job, Postgres, existing pipeline), Next.js toggle, pytest with clock injection and seam mocks.

**Spec:** `docs/superpowers/specs/2026-09-05-overnight-autopilot-design.md`

## Global Constraints

- Never mutate `stories.status` for queueing (Inbox-emptying trap). Never auto-publish.
- Tests must not touch the network, GPUs, or (for unit paths) a real DB; inject clocks, mock `generate_youtube_video`.
- PowerShell 5.1 (no `&&`); pytest as `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`; GUI `npx tsc --noEmit`.
- Working tree may hold unrelated uncommitted work: stage ONLY your files/hunks. Depend ONLY on committed code. Do NOT push (Task 3 pushes once).

---

### Task 1: Flag column, picker, nightly job

**Files:**
- Modify: `supabase/migrations/013_autopilot_queue.sql` (new), `worker/app/config.py` (`AutopilotConfig`), `worker/app/scheduler.py` (JobSpec), `worker/app/routes.py` (queue endpoint — or Task 2; keep endpoint in Task 2, job here)
- Create: `worker/app/autopilot.py`
- Test: `worker/tests/test_autopilot.py` (new)

**Interfaces:**
- Consumes: `generate_youtube_video`, `create_job`/`set_stage`/`fail_job`/`finish_job` (jobs.py), `audit_log`, `FRESH_WINDOW_PREDICATE` (db.py), `get_ingest_config` (fresh hours).
- Produces: `fetch_queued(limit, fresh_hours)`, `set_queue_flag(story_id, queued) -> bool`, `clear_queue_flag`, `mark_run_today(today: str)`, `AutopilotConfig` + accessor, `autopilot_overnight_job`.

- [ ] **Step 1: Write the failing tests**

File header for the new test file:

```python
"""Overnight autopilot: pick queued, render, flag correctly. No network, no GPU."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock
```

Then:

```python
"""Overnight autopilot: pick queued, render, flag correctly. No network, no GPU."""

from datetime import datetime, timezone


def test_window_accepts_early_morning_only():
    from app.autopilot import in_window

    assert in_window(datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)) is True
    assert in_window(datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)) is False
    assert in_window(datetime(2026, 9, 5, 1, 59, tzinfo=timezone.utc)) is False


def test_should_run_once_per_day():
    from app.autopilot import should_run_today

    now = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)
    assert should_run_today(None, now) is True
    assert should_run_today("2026-09-05", now) is False
    assert should_run_today("2026-09-04", now) is True


async def test_job_is_quiet_outside_the_window(monkeypatch):
    from app import autopilot

    monkeypatch.setattr(autopilot, "fetch_queued", None)  # must never be reached
    await autopilot.autopilot_overnight_job(
        now=datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc))
    # returns None, touches nothing (fetch_queued broken on purpose)


async def test_success_clears_flag_and_failure_keeps_it(monkeypatch):
    from unittest.mock import AsyncMock

    from app import autopilot

    stories = [
        {"id": "11111111-1111-1111-1111-111111111111", "headline": "A",
         "channel_id": "finance"},
        {"id": "22222222-2222-2222-2222-222222222222", "headline": "B",
         "channel_id": "finance"},
    ]
    monkeypatch.setattr(autopilot, "fetch_queued", AsyncMock(return_value=stories))
    cleared, audits = [], []
    monkeypatch.setattr(autopilot, "clear_queue_flag", AsyncMock(side_effect=lambda sid: cleared.append(str(sid))))
    monkeypatch.setattr(autopilot, "audit_log", AsyncMock(side_effect=lambda **kw: audits.append(kw["action"])))
    monkeypatch.setattr(autopilot, "get_autopilot_config",
                        AsyncMock(return_value=autopilot.AutopilotConfig(max_per_night=5)))
    monkeypatch.setattr(autopilot, "mark_run_today", AsyncMock())
    from app import youtube as _youtube

    async def fake_generate(*, story_id, channel_id, **kwargs):
        if str(story_id).startswith("11"):
            return __import__("uuid").uuid4()
        return None

    monkeypatch.setattr(_youtube, "generate_youtube_video", fake_generate)
    # NOTE: autopilot calls generate via `from app.youtube import generate_youtube_video`
    # imported INSIDE autopilot.py at module top (`from app.youtube import ...` binds
    # at import). Patch `autopilot.generate_youtube_video` instead — simpler and exact:
```

Stop — resolve the seam ambiguity now instead of in a comment. Decision: `autopilot.py` does `from app import youtube` (module import) and calls `youtube.generate_youtube_video(...)`; tests patch `app.youtube.generate_youtube_video`. Rewrite the test tail accordingly:

```python
    from app import youtube as youtube_mod

    async def fake_generate(*args, **kwargs):
        story_id = kwargs.get("story_id", args[0] if args else None)
        if str(story_id).startswith("11"):
            import uuid
            return uuid.uuid4()
        return None

    async def fake_job(*args, **kwargs):
        import uuid
        return uuid.uuid4()

    monkeypatch.setattr(youtube_mod, "generate_youtube_video", fake_generate)
    monkeypatch.setattr(autopilot, "create_job", AsyncMock(side_effect=fake_job))
    monkeypatch.setattr(autopilot, "finish_job", AsyncMock())
    monkeypatch.setattr(autopilot, "fail_job", AsyncMock())
    await autopilot.autopilot_overnight_job(
        now=datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc))
    assert cleared == ["11111111-1111-1111-1111-111111111111"]
    assert "autopilot_rendered" in audits and "autopilot_failed" in audits
```

Top-of-file imports for the test file (write once, use everywhere):

```python
"""Overnight autopilot: pick queued, render, flag correctly. No network, no GPU."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
```

(Drop the per-test local imports above in favor of these; `pytest` is needed
for the async tests under the repo's asyncio configuration — mirror
`test_score.py`, which uses bare `async def test_` with no mark.)

`fetch_queued` SQL test (DB-backed): mirror `test_score_db.py` exactly —
`pytestmark = pytest.mark.integration`, the shared `db` fixture, seed 4
stories (`INSERT INTO stories (headline, status) ... 'inbox'`), flag two via
`set_queue_flag`, give one a pending draft row, age one past the fresh
window; assert the picker returns exactly the eligible one, oldest-queued
first, honoring the limit. Same cleanup discipline as that file. These tests
need local Postgres (Docker `fce-db` up); without it they error like the
rest of the integration suite — pre-existing, unrelated.

```python
@pytest.mark.db
async def test_picker_skips_drafted_stale_and_honors_cap():
    # Seed: 1 queued fresh undrafted, 1 queued with pending draft,
    # 1 queued stale (> fresh window), 1 unflagged fresh.
    # fetch_queued(limit=10, fresh_hours=48) returns exactly the first.
```

(Write the seeding with the repo's existing DB fixtures — check
`test_score_db.py` for the pattern first; same pool, same cleanup discipline.
If no clean pattern exists, test the SQL string shape instead: assert the
query contains `autopilot_queued_at IS NOT NULL`, `NOT EXISTS`, the fresh
predicate, `ORDER BY autopilot_queued_at ASC`, and `LIMIT`. Prefer the live
test; fall back to the string test only if the pool is unavailable.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_autopilot.py -q`
Expected: FAIL with `ImportError` (no `app.autopilot`)

- [ ] **Step 3: Implement**

Migration `supabase/migrations/013_autopilot_queue.sql`:

```sql
-- Overnight-autopilot queue flag. NULL = not queued. Status untouched.
ALTER TABLE stories ADD COLUMN IF NOT EXISTS autopilot_queued_at timestamptz;
CREATE INDEX IF NOT EXISTS idx_stories_autopilot_queue ON stories (autopilot_queued_at)
    WHERE autopilot_queued_at IS NOT NULL;
```

`worker/app/config.py` (mirror `IngestConfig` exactly — dataclass + accessor
through `_load` + `__dataclass_fields__` filter):

```python
@dataclass(frozen=True)
class AutopilotConfig:
    max_per_night: int = 3


async def get_autopilot_config() -> AutopilotConfig:
    raw = await _load("autopilot")
    return AutopilotConfig(**{k: v for k, v in raw.items() if k in AutopilotConfig.__dataclass_fields__})
```

(`_load` returns `{}` for a missing row, so defaults apply with no seeding.)

`worker/app/autopilot.py`:

```python
"""Overnight renders of owner-queued stories. Manual publish still required."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from app import youtube
from app.audit import audit_log
from app.config import get_autopilot_config, get_ingest_config
from app.db import FRESH_WINDOW_PREDICATE, _fetchall, get_pool
from app.jobs import create_job, fail_job, finish_job, set_stage

log = structlog.get_logger()

WINDOW_START_HOUR = 2
WINDOW_END_HOUR = 5


def in_window(now: datetime) -> bool:
    return WINDOW_START_HOUR <= now.hour < WINDOW_END_HOUR


def should_run_today(last_run: str | None, now: datetime) -> bool:
    return last_run != now.date().isoformat()


async def fetch_queued(*, limit: int, fresh_hours: int) -> list[dict]:
    """Flagged, fresh, undrafted stories, oldest-queued first."""
    pool = await get_pool()
    async with pool.connection() as conn:
        return await _fetchall(
            conn,
            f"""
            SELECT s.id, s.headline, s.channel_id
              FROM stories s
             WHERE s.autopilot_queued_at IS NOT NULL
               AND ({FRESH_WINDOW_PREDICATE})
               AND NOT EXISTS (
                     SELECT 1 FROM drafts d
                      WHERE d.story_id = s.id AND d.status = 'pending'
                   )
             ORDER BY s.autopilot_queued_at ASC
             LIMIT %s
            """,
            fresh_hours,
            limit,
        )
```

(Verify `FRESH_WINDOW_PREDICATE`'s bind style against `score.fetch_unscored`
— it takes the hours value positionally there; mirror that call exactly. If
the predicate needs different binds, adjust and note it in the commit.)

```python
async def clear_queue_flag(story_id: uuid.UUID) -> None:
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE stories SET autopilot_queued_at = NULL WHERE id = %s",
            story_id,
        )


async def mark_run_today(today: str) -> None:
    """Remember today's run in the config table (upsert the autopilot row)."""
    from app import db

    current = await db.get_config("autopilot") or {}
    await db.set_config("autopilot", {**current, "last_run_date": today})
```

And reading: `get_autopilot_config` returns only `max_per_night`; last run
date comes from `(await db.get_config("autopilot") or {}).get("last_run_date")`.
Keep both in one place — the job reads the raw row once:

```python
async def autopilot_overnight_job(*, now: datetime | None = None) -> None:
    """Render queued stories. Quiet no-op outside the window or repeat days."""
    from app import db

    current = now or datetime.now(timezone.utc)
    if not in_window(current):
        log.debug("autopilot_skipped", reason="outside_window")
        return
    row = await db.get_config("autopilot") or {}
    if not should_run_today(row.get("last_run_date"), current):
        log.debug("autopilot_skipped", reason="already_ran_today")
        return
    ingest_cfg = await get_ingest_config()
    llm_cfg = await get_autopilot_config()
    stories = await fetch_queued(limit=llm_cfg.max_per_night, fresh_hours=ingest_cfg.fresh_news_hours)
    for story in stories:
        job_id = await create_job(kind="short", story_id=story["id"])
        try:
            await set_stage(job_id, "script")
            draft_id = await youtube.generate_youtube_video(
                story_id=story["id"],
                channel_id=story["channel_id"],
                upload_preference="manual",
                backend="cinematic",
                job_id=job_id,
            )
        except Exception as exc:  # noqa: BLE001 — one story must not kill the night
            log.error("autopilot_story_failed", story_id=str(story["id"]), error=str(exc))
            await fail_job(job_id, f"autopilot: {exc}")
            await audit_log(actor="worker", action="autopilot_failed",
                            entity=str(story["id"]), entity_type="story",
                            after={"error": str(exc)})
            continue
        if draft_id is None:
            await fail_job(job_id, "generation aborted by a quality guard; see worker logs")
            await audit_log(actor="worker", action="autopilot_failed",
                            entity=str(story["id"]), entity_type="story",
                            after={"reason": "guard_abort"})
            continue
        await finish_job(job_id, draft_id)
        await clear_queue_flag(story["id"])
        await audit_log(actor="worker", action="autopilot_rendered",
                        entity=str(story["id"]), entity_type="story",
                        after={"draft_id": str(draft_id)})
    await mark_run_today(current.date().isoformat())
```

Notes: `story["channel_id"]` may be None for old rows — `channels.resolve`
raises inside generate → caught → failed + flag kept. Correct behavior, no
special case. `set_stage(job_id, "script")` mirrors the manual path's first
progress update (generate updates the rest itself).

Scheduler (`scheduler.py`, mirroring `score_new` registration): add
`autopilot_overnight` to the specs with the same interval family as the
reader jobs (every 30 min — the day-gate makes frequency cheap; check the
`JobSpec(id=..., minutes=..., fn=...)` shape and the `register_jobs`
async-def invariant: module-level `async def autopilot_overnight_job`
imported, never a lambda).

- [ ] **Step 4: Run green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_autopilot.py tests/test_scheduler.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/app/autopilot.py worker/app/config.py worker/app/scheduler.py supabase/migrations/013_autopilot_queue.sql worker/tests/test_autopilot.py
git commit -m "Add overnight autopilot job for queued stories"
```

---

### Task 2: Queue endpoint + Inbox toggle

**Files:**
- Modify: `worker/app/routes.py` (endpoint), `gui/src/app/page.tsx` (moon toggle per row), `gui/src/lib/api.ts` (client fn)
- Test: `worker/tests/test_routes_stories.py` or append to `test_autopilot.py`? Route tests live near routes — check for an existing stories-route test file first; if none, put them in `test_autopilot.py` under a routes section.

**Interfaces:**
- Consumes: Task 1 (`autopilot_queued_at`).
- Produces: `PATCH /stories/{id}/queue {queued: bool}` → `{id, queued}`; Inbox toggle.

- [ ] **Step 1: Write the failing tests**

```python
def test_queue_sets_and_clears_the_flag():
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, patch

    from app.main import app

    client = TestClient(app)
    story_id = str(__import__("uuid").uuid4())
    with patch("app.db.get_pool", AsyncMock()) as _pool:
        ...
```

No — don't hand-wave the DB seam. Write it against the real helper the
endpoint will call: endpoint calls `set_queue_flag(story_id, queued)` in
`autopilot.py`:

```python
async def set_queue_flag(story_id: uuid.UUID, queued: bool) -> bool:
    """Set/clear the overnight flag. Returns False when the story is unknown."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute(
            "UPDATE stories SET autopilot_queued_at = CASE WHEN %s THEN now() ELSE NULL END "
            "WHERE id = %s",
            (queued, story_id),
        )
        return cursor.rowcount > 0
```

(Add this to Task 1's module — amend Task 1 Files to include it and its test:
`set True then False on a scratch story` is DB-backed; plus a 404 test with a
random uuid. DB tests need local Postgres — expected failure without it,
per repo rule.)

Route tests (TestClient, mirroring `test_routes_channel.py`):

```python
def test_queue_unknown_story_is_404():
    with patch("app.autopilot.set_queue_flag", AsyncMock(return_value=False)):
        resp = client.patch(f"/stories/{uuid.uuid4()}/queue", json={"queued": True})
    assert resp.status_code == 404


def test_queue_sets_the_flag():
    with patch("app.autopilot.set_queue_flag", AsyncMock(return_value=True)) as setter:
        resp = client.patch(f"/stories/{uuid.uuid4()}/queue", json={"queued": True})
    assert resp.status_code == 200
    assert resp.json()["queued"] is True
    setter.assert_awaited_once()
```

Endpoint (routes.py, mirroring the channel-uuid validation pattern):

```python
class StoryQueueRequest(BaseModel):
    queued: bool


@router.patch("/stories/{story_id}/queue")
async def story_queue(story_id: str, req: StoryQueueRequest) -> dict:
    """Queue/unqueue a story for the overnight run. Flag only, never a status flip."""
    from app import autopilot

    try:
        sid = uuid.UUID(story_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid story_id (must be a uuid)")
    if not await autopilot.set_queue_flag(sid, req.queued):
        raise HTTPException(status_code=404, detail="story not found")
    return {"id": str(sid), "queued": req.queued}
```

GUI (`page.tsx` inbox rows + `lib/api.ts`): `setStoryQueued(storyId, queued)`
client fn hitting the endpoint; per-row moon button (`Moon`/`MoonStar`
lucide icon, `aria-pressed`, coral when queued) next to GenerateDraftButton;
queued rows show the marker even before data reload (optimistic state flip
with rollback on error — keep it to a local state patch, no new components).
tsc clean.

- [ ] **Step 2: Run to verify they fail**

Run: route tests → 404 (no route); autopilot helper tests → ImportError.
Two reds, each for its own reason.

- [ ] **Step 3: Implement** (code blocks above verbatim)

- [ ] **Step 4: Run green + typecheck**

Run worker tests, then `cd gui; npx tsc --noEmit`, clean.

- [ ] **Step 5: Commit**

```bash
git add worker/app/autopilot.py worker/app/routes.py gui/src/app/page.tsx gui/src/lib/api.ts worker/tests/test_autopilot.py
git commit -m "Add overnight queue toggle to the Inbox"
```

(Route-test file: if a stories-route test file was created in Step 1 instead
of using test_autopilot.py, add it to this commit explicitly.)

---

### Task 3: Migration apply (both DBs) + suites + record + push

**Files:**
- Modify: `PROGRESS.md` (decision #88)

- [ ] **Step 1: Apply migration 013 locally + VPS, verify column**

Local: `Get-Content supabase/migrations/013_autopilot_queue.sql | docker exec -i fce-db psql -U postgres -d fce -v ON_ERROR_STOP=1`
VPS: commit + push first, pull there, apply with
`sudo -u fce psql -p 5433 -d fce -v ON_ERROR_STOP=1 -f <path>` (file on disk —
no quoting tunnel needed).

- [ ] **Step 2: Run the affected suites**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_autopilot.py tests/test_scheduler.py tests/test_score.py tests/test_youtube.py -q`
Expected: PASS (DB-backed tests need local Postgres; without it they error — pre-existing, unrelated)

- [ ] **Step 3: Record and push**

```
| 88 | Overnight autopilot renders pre-approved picks; mornings start with review | autopilot | Flag column (status untouched), day-gated job, Short-only v1, failure retries tomorrow. Publishing still manual. |
```

```bash
git add PROGRESS.md
git commit -m "Record overnight autopilot decision"
git push
```
