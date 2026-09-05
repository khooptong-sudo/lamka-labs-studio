# Queue Discipline (GPU Slot + Cancel + Anti-Stall) — Design

**Date:** 2026-09-05
**Status:** Approved, awaiting implementation plan
**Scope:** Piece 4 of the Kutly upgrade. Serialize GPU work, cancel stuck
runs, bound unbounded waits, speak the two missing stages. No scheduler
rewrite, no DB migration, no faster single renders.

## Problem

Every `/youtube/jobs` POST spawns a bare `asyncio.create_task` with no
knowledge of the others. Two Shorts at once drive Ollama, ComfyUI, and
Chromium concurrently into one 8 GB RTX 3070 — the card that already
thermalled once. There is no cancel (the registry is an anonymous set), the
HyperFrames render `subprocess.run` has no timeout, and piece 1's
`"fact_check"` stage never reaches the GUI: `set_stage` raises `ValueError`
for it and `_stage` swallows that as a warning.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | In-process `asyncio.Semaphore(1)` in a new `app/gpu.py` | One worker process owns the card; a mutex is the whole solution. A distributed lock would be generality nothing runs on. |
| 2 | Lock Ollama planning, ComfyUI builds, and the HyperFrames render — nothing else | Script/fact-check/TTS/thumbnails are cloud/CPU and overlap freely; that overlap IS the throughput win. Gemini image path skips the slot (cloud, no card). |
| 3 | Cancel via a job→task registry + `DELETE /youtube/jobs/{id}` | A wedged GPU holder blocks every later job; the owner needs a hammer. try/finally everywhere the slot is held so cancel releases it. |
| 4 | Render timeout, env-knobbed, default 20 min | ComfyUI already bounds itself (300 s); the render is the unbounded one. Timeout fails the job loud through the existing render-failure path. |
| 5 | `STAGES` gains `fact_check` and `thumbnails` in order; GUI mirror updated | The GUI bar draws from ordering; inserting is the documented deliberate change. Both call sites (`_stage`) start working instead of warning. |

## Slot

```python
# app/gpu.py
slot: asyncio.Semaphore(1)  # the whole card, one holder
```

- `_generate_frame_compositions_local`: `async with gpu.slot` around the body
  (one acquisition per job; frames inside stay sequential as today).
- `build_cinematic_frames`: acquire only when the resolved provider is
  `"comfyui"` (Gemini path never touches the card).
- HyperFrames render in `youtube.py`: `async with gpu.slot` around the
  `to_thread(run_hyperframes)` call.
- Cancellation while holding releases via the context manager; while waiting
  raises before acquiring. No timeout on acquisition — queue order is
  arrival order and a holder always finishes or fails loudly.

## Cancel

`routes.py`: `_RUNNING_JOBS: set` → `dict[uuid.UUID, asyncio.Task]`
(two registration sites: `/youtube/jobs`, `/youtube/jobs/with-voice`).
`DELETE /youtube/jobs/{job_id}`: unknown id or finished task → 404;
live task → `task.cancel()`, `await fail_job(job_id, "cancelled by owner")`,
return `{"cancelled": true}`. The pipeline's existing `except` in `run()`
records cancellation through the normal fail path if the task dies first —
last writer wins, both say stopped.

## Anti-stall

`HYPERFRAMES_TIMEOUT_SECONDS` (default 1200) → `timeout=` on the render
`subprocess.run`. `TimeoutExpired` joins `CalledProcessError` in the
existing handler (same "youtube rendering failed" abort). Thumbnail
Playwright screenshots stay best-effort (already non-blocking by design).

## Stages

`jobs.STAGES`: `["queued", "script", "fact_check", "narration", "world",
"shots", "render", "thumbnails", "done"]`. Pipeline emits
`_stage(job_id, "thumbnails")` around `build_thumbnail_variants`
(`"fact_check"` is already emitted). `FilmProgress.tsx` mirror + labels
(`fact_check` → "fact check", `thumbnails` → "thumbnails"). Unknown-stage
`ValueError` stays — it caught this exact drift once already.

## Testing

- Slot serializes: two contenders never co-hold (instrumented critical
  section, one event loop); cloud/Gemini path never acquires (assert
  `slot._value` untouched… no — assert via a wrapped slot lock counter, not
  privates: patch `app.gpu.slot` with a recording semaphore).
- Cancel: live job → 404-free cancel, `fail_job` called with the reason,
  slot released for the next holder; unknown id → 404.
- Timeout: hung render (patchedlk `subprocess.run` side_effect=TimeoutExpired)
  fails the run through the render-failure path.
- Stages: `set_stage` accepts the two new names in order; GUI mirror test?
  GUI has no test runner configured for this — mirror verified by `tsc`
  (types: `Record<typeof STAGES[number], string>` fails to compile on drift).
- Regression: full affected suites; TTS/synthesis concurrency unchanged.

## Non-goals (later pieces)

- DB queue table, priorities, FIFO guarantees beyond arrival order,
  multi-worker locking, per-render latency work, GUI queue list page,
  new channels (piece 5), long-form track.

## Files touched

- New: `worker/app/gpu.py`
- `worker/app/youtube.py` (slot around render; `thumbnails` stage emit; render timeout)
- `worker/app/scene3d/backend.py` (slot around local planning + ComfyUI builds)
- `worker/app/routes.py` (task registry, DELETE endpoint)
- `worker/app/jobs.py` (STAGES insert)
- `gui/src/components/FilmProgress.tsx` (mirror + labels)
- Tests: new `worker/tests/test_gpu_queue.py`; route cancel tests in `test_routes_voice.py` or new `test_routes_jobs.py`
