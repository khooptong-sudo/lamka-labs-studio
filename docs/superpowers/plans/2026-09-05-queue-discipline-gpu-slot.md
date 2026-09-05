# Queue Discipline (GPU Slot + Cancel + Anti-Stall) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One GPU holder at a time, owner-cancelable runs, bounded waits, and a progress bar that names every stage.

**Architecture:** A one-line semaphore module (`app/gpu.py`) acquired only around card-touching work; cloud/CPU stages overlap freely. Cancel swaps the anonymous task set for a job→task map plus a DELETE endpoint. Timeouts and stage inserts are small, local, fail-loud changes. No migration, no scheduler rewrite.

**Tech Stack:** Python worker (`asyncio.Semaphore`, `asyncio.Task.cancel`), FastAPI, Playwright-free pytest with seam patching, `tsc` for the GUI mirror.

**Spec:** `docs/superpowers/specs/2026-09-05-queue-discipline-gpu-slot-design.md`

## Global Constraints

- Tests must not touch the network, real ffmpeg, real GPUs, or real subprocesses; patch seams (`app.scene3d.backend.gpu`, `app.youtube.gpu`, `subprocess.run`, providers).
- Never substitute or silently skip: lock acquisition has no timeout; timeouts fail the job loud.
- Do NOT assert on semaphore privates (`_value`, `_waiters`); use a recording stand-in or behavioral ordering.
- PowerShell 5.1 for shells (no `&&`); pytest as `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`; GUI check as `cd gui; npx tsc --noEmit`.
- The working tree may hold unrelated uncommitted work: stage ONLY your hunks. Depend ONLY on committed code. Do NOT push (Task 4 pushes once).

---

### Task 1: GPU slot module + wiring

**Files:**
- Create: `worker/app/gpu.py`
- Modify: `worker/app/youtube.py` (import, local-frames lock, render lock), `worker/app/scene3d/backend.py` (import, cinematic dispatch split)
- Test: `worker/tests/test_gpu_queue.py` (new)

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces: `app.gpu.slot: asyncio.Semaphore(1)`. Call sites use `async with gpu.slot` via `from app import gpu` (patchable as `app.youtube.gpu` / `app.scene3d.backend.gpu`).

- [ ] **Step 1: Write the failing tests**

```python
"""One card, one holder. No GPU, no network, no subprocesses."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _recorder():
    class Recorder:
        def __init__(self):
            self.entries = 0

        async def __aenter__(self):
            self.entries += 1

        async def __aexit__(self, *exc):
            return False

    return Recorder()


async def test_slot_serializes_two_holders():
    from app import gpu

    order: list[str] = []

    async def hold(name: str):
        async with gpu.slot:
            order.append(f"{name}-in")
            await asyncio.sleep(0.01)
            order.append(f"{name}-out")

    await asyncio.gather(hold("a"), hold("b"))
    assert order in (
        ["a-in", "a-out", "b-in", "b-out"],
        ["b-in", "b-out", "a-in", "a-out"],
    )


async def test_local_frame_planning_holds_the_slot(monkeypatch):
    import app.youtube as youtube

    rec = _recorder()
    monkeypatch.setattr(youtube, "gpu", SimpleNamespace(slot=rec))
    monkeypatch.setattr(
        "app.localllm.plan_frame",
        AsyncMock(return_value=({"archetype": "stat_card"}, False)),
    )

    from app.storyboard import Frame, Storyboard

    board = Storyboard(meta={"title": "T", "description": "D"})
    board.frames = [Frame(index=1, title="S1", voiceover="v", scene="s")]
    await youtube._generate_frame_compositions_local(board, __import__("pathlib").Path("."))
    assert rec.entries == 1
```

Normalize the `__import__("pathlib")` to a top-level `from pathlib import Path`
and `tmp_path` when writing the file — and prefer `tmp_path` over `"."` so
the test never writes into the repo. (Compositions land under the given dir;
use `tmp_path` and pass it as `video_dir`.)

```python
async def test_cinematic_comfyui_path_holds_the_slot_but_gemini_does_not(tmp_path, monkeypatch):
    import app.scene3d.backend as backend

    rec = _recorder()
    monkeypatch.setattr(backend, "gpu", SimpleNamespace(slot=rec))
    monkeypatch.setattr(
        backend, "_generate_cinematic_image", AsyncMock()
    )

    from app.storyboard import Frame, Storyboard

    def board():
        b = Storyboard(meta={"title": "T", "description": "D"})
        b.frames = [Frame(index=1, title="S1", voiceover="v", scene="s", duration=5.0)]
        return b

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    await backend.build_cinematic_frames(board(), tmp_path, provider="gemini")
    assert rec.entries == 0

    monkeypatch.setenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    monkeypatch.setenv("COMFYUI_CHECKPOINT_NAME", "test.safetensors")
    await backend.build_cinematic_frames(board(), tmp_path, provider="comfyui")
    assert rec.entries == 1
```

`build_cinematic_frames(board, video_dir, provider)` writes realHTML composition
files under `tmp_path` — local, deterministic, no GPU. `render_archetype` in
the local-frames test is real (pure template). `plan_frame` is patched at its
defining module (`app.localllm.plan_frame`) because `youtube.py` imports it
locally inside the function.

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_gpu_queue.py -q`
Expected: FAIL with `ImportError` (no `app.gpu` yet)

- [ ] **Step 3: Implement the slot and wire the three sites**

`worker/app/gpu.py`:

```python
"""The whole RTX 3070 behind one semaphore.

One worker process owns the card, so an in-process lock is the complete
solution — no distributed coordination. Acquire ONLY around work that touches
the GPU (local Ollama planning, ComfyUI builds, the HyperFrames render).
Cloud and CPU stages stay outside so jobs overlap on everything else.
"""

from __future__ import annotations

import asyncio

slot: asyncio.Semaphore = asyncio.Semaphore(1)
```

`worker/app/youtube.py`: extend line 13 `from app import db` to
`from app import db, gpu`. (Verify `app/__init__.py` tolerates the import —
it only re-exports `db` today; importing the `app.gpu` submodule has no
circularity since `gpu.py` imports nothing from `app`. If the package init
errors, fall back to `from app import gpu` locally inside the two functions.)

a) `_generate_frame_compositions_local`: wrap the per-frame loop section —
from `async with httpx.AsyncClient...` through the `for frame` loop — in
`async with gpu.slot:`. Keep the `log.info` outside. Concretely, indent the
`async with httpx...` block one level under a new `async with gpu.slot:`
line placed right after the docstring, with a comment:
`# One GPU serves one planning request at a time (see app/gpu.py).`

b) HyperFrames render: wrap `proc = await asyncio.to_thread(run_hyperframes)`
as:

```python
        from app import gpu as _gpu  # local alias only if the top import proved circular; else use gpu

        async with gpu.slot:
            proc = await asyncio.to_thread(run_hyperframes)
```

Prefer the top-level import; the local alias is the documented fallback.

`worker/app/scene3d/backend.py`: add `from app import gpu` (same circularity
note; `backend.py` currently imports only scene3d siblings + structlog).
Split `build_cinematic_frames` after the `selected = require...` line:

```python
    if selected == "comfyui":
        async with gpu.slot:
            return await _build_cinematic_frames_inner(board, video_dir, selected, on_frame_complete)
    return await _build_cinematic_frames_inner(board, video_dir, selected, on_frame_complete)
```

moving the existing loop (frames/assets dirs, per-frame generate + compose,
log, `return []`) verbatim into the new
`_build_cinematic_frames_inner(board, video_dir, selected, on_frame_complete)`
defined directly above `build_cinematic_frames`.

- [ ] **Step 4: Run green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_gpu_queue.py tests/test_scene3d_backend.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/app/gpu.py worker/app/youtube.py worker/app/scene3d/backend.py worker/tests/test_gpu_queue.py
git commit -m "Serialize GPU work behind a single in-process slot"
```

---

### Task 2: Cancel endpoint + render timeout

**Files:**
- Modify: `worker/app/routes.py` (registry, DELETE), `worker/app/youtube.py` (timeout)
- Test: `worker/tests/test_routes_jobs.py` (new), `worker/tests/test_youtube.py` or `test_generation_resilience.py` (timeout test — put it in `test_generation_resilience.py` next to the render-failure test)

**Interfaces:**
- Consumes: `jobs.fail_job`, `asyncio.Task.cancel`.
- Produces: `DELETE /youtube/jobs/{job_id}` → `{"cancelled": true}` or 404; `HYPERFRAMES_TIMEOUT_SECONDS` (default 1200.0) honored by the render.

- [ ] **Step 1: Write the failing tests**

`worker/tests/test_routes_jobs.py`:

```python
"""Job cancel: registry math, no DB on the 404 path."""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cancel_unknown_job_is_404():
    resp = client.delete(f"/youtube/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_cancel_bad_id_is_400():
    assert client.delete("/youtube/jobs/nope").status_code == 400


async def test_cancel_live_job_marks_it_cancelled():
    from app import routes

    jid = uuid.uuid4()
    task = asyncio.create_task(asyncio.sleep(60))
    routes._RUNNING_JOBS[jid] = task
    try:
        with patch("app.jobs.fail_job", AsyncMock()) as fail:
            resp = await asyncio.to_thread(client.delete, f"/youtube/jobs/{jid}")
        assert resp.status_code == 200
        assert resp.json() == {"cancelled": True}
        fail.assert_awaited_once()
        assert fail.await_args.args == (jid, "cancelled by owner")
    finally:
        if not task.done():
            task.cancel()
        routes._RUNNING_JOBS.pop(jid, None)
```

Notes: the test itself is async (TestClient is sync — run `client.delete`
in `to_thread` so as not to deadlock the loop the task lives on... actually
simpler and fully deterministic: make the test SYNC (`def`, no asyncio mark)
and create the task via the client's portal? No — simplest correct shape: the
test function is `def test_...` (sync); create the task with
`asyncio.get_event_loop`? Fragile. Keep the async shape above: `asyncio.sleep`
task on the test loop, endpoint awaits only `fail_job` (mocked) — no deadlock
because TestClient runs the app in a separate portal thread while `task` lives
on the test loop; `task.cancel()` is thread-safe fortuitous... `Task.cancel`
from another thread is NOT safe.

Deterministic alternative honoring the threading truth: make the test sync,
and instead of a real live task, assert the two pure branches (404/400) plus
a registry unit test — register a DONE task object and assert 404 (finished
branch):

```python
def test_cancel_finished_job_is_404():
    from app import routes

    jid = uuid.uuid4()
    done = asyncio.Future()  # never scheduled; done() False... no.
```

A bare `asyncio.Task` requires a loop. Use a completed future instead? The
endpoint calls `task.done()` then `task.cancel()` — a `concurrent.futures.Future`
has both methods! For the finished branch:

```python
def test_cancel_finished_job_is_404():
    import concurrent.futures

    from app import routes

    jid = uuid.uuid4()
    finished = concurrent.futures.Future()
    finished.set_result(None)
    routes._RUNNING_JOBS[jid] = finished
    try:
        resp = client.delete(f"/youtube/jobs/{jid}")
        assert resp.status_code == 404
    finally:
        routes._RUNNING_JOBS.pop(jid, None)
```

And for the live branch, patch at the seam: patch `routes._RUNNING_JOBS`
dict with a recording Mock task? The endpoint does `task.cancel()` (sync) +
`await fail_job(...)`. A `unittest.mock.MagicMock` task: `done()` returns
MagicMock (truthy!) — bad. Configure: `task = MagicMock(); task.done.return_value = False`.
`task.cancel()` sync ✓. `fail_job` patched AsyncMock ✓. Fully deterministic,
no threads, no real tasks:

```python
def test_cancel_live_job_marks_it_cancelled():
    from unittest.mock import MagicMock

    from app import routes

    jid = uuid.uuid4()
    task = MagicMock()
    task.done.return_value = False
    routes._RUNNING_JOBS[jid] = task
    try:
        with patch("app.jobs.fail_job", AsyncMock()) as fail:
            resp = client.delete(f"/youtube/jobs/{jid}")
        assert resp.status_code == 200
        assert resp.json() == {"cancelled": True}
        task.cancel.assert_called_once()
        fail.assert_awaited_once_with(jid, "cancelled by owner")
    finally:
        routes._RUNNING_JOBS.pop(jid, None)
```

USE THE DETERMINISTIC SHAPES (the async/threaded sketches above are
documented anti-patterns — do not implement them). Three tests total:
400, 404-unknown, 404-finished, live-cancel. Four tests.

Timeout test (append in `test_generation_resilience.py`, mirroring
`test_render_failure_is_not_swallowed_by_the_thumbnail_guard`):

```python
@pytest.mark.asyncio
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube.fact_check_script", AsyncMock(return_value={"verdict": "PASS", "violations": []}))
@patch("app.youtube._research_packet", return_value="packet")
async def test_hung_render_fails_loud_on_timeout(
    mock_packet, mock_run, mock_frames, mock_audio, mock_script, mock_record, mock_fetch, tmp_path
):
    """An unbounded render wedges the GPU slot forever. It must abort loud."""
    import subprocess

    from app import youtube

    story_id = uuid.uuid4()
    _arrange((mock_run, mock_frames, mock_audio, mock_script, mock_record, mock_fetch))
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="hyperframes", timeout=1200)

    with patch("app.youtube.VIDEOS_DIR", tmp_path), \
            patch("app.channels.resolve", AsyncMock(return_value=FINANCE)):
        with pytest.raises(Exception, match="timed out"):
            await youtube.generate_youtube_video(
                story_id=story_id, channel_id="finance", upload_preference="manual"
            )

    mock_record.assert_not_called()
```

(`FINANCE`, `_arrange`, and imports already exist in that file — mirror the
neighbor test exactly, changing only the side_effect and match.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_jobs.py tests/test_generation_resilience.py::test_hung_render_fails_loud_on_timeout -q`
Expected: FAIL — 404 on the DELETE (no route), `DID NOT RAISE` on the timeout test

- [ ] **Step 3: Implement**

a) `routes.py`: add top-level `import asyncio` (check absence first with
`Select-String -Pattern "^import asyncio" worker/app/routes.py`; stdlib only).
Replace `_RUNNING_JOBS: set = set()` with:

```python
_RUNNING_JOBS: dict = {}
```

Update both registration sites (`task = asyncio.create_task(run())` in
`/youtube/jobs` and `/youtube/jobs/with-voice`):

```python
    _RUNNING_JOBS[job_id] = task
    task.add_done_callback(lambda _t: _RUNNING_JOBS.pop(job_id, None))
```

Add after `youtube_job_status`:

```python
@router.delete("/youtube/jobs/{job_id}")
async def youtube_job_cancel(job_id: str) -> dict:
    """Cancel a live run. A finished/unknown id is 404, never a silent no-op."""
    from app.jobs import fail_job

    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid job_id (must be a uuid)")

    task = _RUNNING_JOBS.get(jid)
    if task is None or task.done():
        raise HTTPException(status_code=404, detail="job not found or already finished")
    task.cancel()
    await fail_job(jid, "cancelled by owner")
    return {"cancelled": True}
```

(`uuid`, `HTTPException` already imported at routes top.)

b) `youtube.py`: module constant near the other env knobs:

```python
HYPERFRAMES_TIMEOUT_SECONDS = float(os.environ.get("HYPERFRAMES_TIMEOUT_SECONDS", "1200"))
```

Render call gains `timeout=HYPERFRAMES_TIMEOUT_SECONDS`; handler gains a branch
before the generic `except Exception`:

```python
        proc = await asyncio.to_thread(run_hyperframes)
        log.info("youtube_rendering_complete")
    except subprocess.TimeoutExpired as e:
        log.error("youtube_rendering_failed", reason="timeout", timeout_seconds=e.timeout)
        raise Exception("youtube rendering timed out")
    except subprocess.CalledProcessError as e:
```

Rest unchanged. (Existing pipeline tests patch `app.youtube.subprocess.run`
 wholesale, so the new kwarg needs no fixture updates.)

- [ ] **Step 4: Run green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_jobs.py tests/test_generation_resilience.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/app/routes.py worker/app/youtube.py worker/tests/test_routes_jobs.py worker/tests/test_generation_resilience.py
git commit -m "Add job cancel endpoint and bound the render wait"
```

---

### Task 3: Name the missing stages (worker + GUI)

**Files:**
- Modify: `worker/app/jobs.py` (STAGES), `worker/app/youtube.py` (`thumbnails` emit), `gui/src/components/FilmProgress.tsx` (mirror + labels)
- Test: `worker/tests/test_jobs.py` (extend the existing stage-contract test)

**Interfaces:**
- Consumes: existing `_stage(job_id, ...)` calls.
- Produces: `STAGES = ["queued", "script", "fact_check", "narration", "world", "shots", "render", "thumbnails", "done"]`.

- [ ] **Step 1: Update the existing contract test**

`worker/tests/test_jobs.py::test_stages_are_the_expected_set_in_order` already
asserts the exact list (plus monotonic/unique/unknown-stage tests that stay
valid untouched). Update its expected list to the 9-stage list above — no new
test file; duplicating this contract in a second file is clutter.

**Interfaces:**
- Consumes: existing `_stage(job_id, ...)` calls.
- Produces: `STAGES = ["queued", "script", "fact_check", "narration", "world", "shots", "render", "thumbnails", "done"]`.

- [ ] **Step 1: Write the failing tests**

```python
"""Stage vocabulary is a contract between worker and GUI bar."""

import pytest


def test_stages_name_every_emitted_stage_in_order():
    from app.jobs import STAGES

    assert STAGES == [
        "queued", "script", "fact_check", "narration", "world",
        "shots", "render", "thumbnails", "done",
    ]


async def test_set_stage_rejects_an_unknown_stage_without_touching_the_db(monkeypatch):
    from unittest.mock import AsyncMock

    from app import jobs

    get_pool = AsyncMock(side_effect=AssertionError("DB must not be touched"))
    monkeypatch.setattr(jobs, "get_pool", get_pool)
    with pytest.raises(ValueError, match="unknown stage"):
        await jobs.set_stage(__import__("uuid").uuid4(), "nope")
    get_pool.assert_not_called()
```

Normalize `__import__("uuid")` to top-level `import uuid` when writing the file.

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_jobs_stages.py -q`
Expected: FAIL (STAGES lacks the names; first assert fails)

- [ ] **Step 3: Implement**

a) `jobs.py`: STAGES gains the two names in the positions above.

b) `youtube.py`: the `"fact_check"` emit already exists (piece 1). Add
`await _stage(job_id, "thumbnails")` immediately before the
`await build_thumbnail_variants(...)` call.

c) `FilmProgress.tsx`: STAGES mirror becomes
`["queued", "script", "fact_check", "narration", "world", "shots", "render", "thumbnails", "done"]`
with labels `fact_check: "fact check"` and `thumbnails: "thumbnails"` added to
`STAGE_LABELS`. Nothing else in the component changes (ordering drives the bar).

- [ ] **Step 4: Run green + typecheck**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_jobs_stages.py -q`
Expected: PASS. Then: `cd gui; npx tsc --noEmit` — must be clean (the
`Record<typeof STAGES[number], string>` type fails the build on label drift,
which is the mirror's regression test).

- [ ] **Step 5: Commit**

```bash
git add worker/app/jobs.py worker/app/youtube.py gui/src/components/FilmProgress.tsx worker/tests/test_jobs_stages.py
git commit -m "Name fact-check and thumbnail stages end to end"
```

---

### Task 4: Full verification + record + push

**Files:**
- Modify: `PROGRESS.md` (decision #79)

- [ ] **Step 1: Run the affected suites**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_gpu_queue.py tests/test_routes_jobs.py tests/test_jobs_stages.py tests/test_youtube.py tests/test_generation_resilience.py tests/test_scene3d_backend.py tests/test_routes_voice.py tests/test_routes_channel.py tests/test_script_quality.py -q`
Expected: PASS (DB-backed tests need local Postgres; without it they error — pre-existing, unrelated)

- [ ] **Step 2: Record the decision in PROGRESS.md**

```
| 79 | GPU slot + cancel + render timeout + named stages | piece-4 | One in-process semaphore around Ollama/ComfyUI/render; cloud paths overlap. DELETE cancels live runs. Render bounded at 20 min default. fact_check/thumbnails join STAGES + GUI mirror. No scheduler rewrite. |
```

- [ ] **Step 3: Commit and push**

```bash
git add PROGRESS.md
git commit -m "Record queue-discipline decision"
git push
```
