# Voice-to-Video + Motion Uplift — Design

**Date:** 2026-09-05
**Status:** Approved, awaiting implementation plan
**Scope:** Piece 3 of the Kutly upgrade. Owner-supplied per-scene narration
plus deterministic motion uplift. API-first (new route); GUI upload control
deferred. No STT, no new provider, no renderer-contract change.

## Problem

Narration has one source: Edge TTS (`_generate_frame_audio`). An owner who
records a better read — their own voice, a hired narrator — has nowhere to
put it; the pipeline would re-synthesize over it. And cinematic motion is one
fixed template over 4 camera paths: correct but samey across every Short.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Clips match scenes by order, never by filename | Filenames lie; `voice_filename` is index-addressed (`assets/voice/NN.mp3`), so position is the only honest key. |
| 2 | Count mismatch or an unprobable clip aborts loud, pre-render | A missing/short clip desyncs every later scene. Same fail-loud family as `MIN_SCRIPT_FRAMES`, never a silent hole. |
| 3 | No silence substitution for owner audio | `_write_silence` exists for TTS flakes. Substituting silence under a human read hides a broken upload as a finished video. |
| 4 | No STT/transcript check in v1 | Owner's board + owner's voice + owner's review — the override philosophy. A transcription judge is a third automated LLM layer (non-goal #4). |
| 5 | Motion reads the existing `- Frame-to-motion intent:` line | The control already ships in the storyboard direction; wiring it into render beats inventing a second knob. Unknown/absent intent falls back to the index cycle. |
| 6 | Bytes accepted at the route, staged to disk before the job starts | Background jobs must not hold request memory; files on disk are re-runnable and auditable. Bad input fails the request (400), never the job. |

## Voice input

`generate_youtube_video(..., voice_clip_paths: list[Path] | None = None)`:

- `None` (default) keeps today's Edge TTS path byte-identical, including the
  silence-ratio gate.
- When given: after board parse + `MIN_SCRIPT_FRAMES`, require
  `len(voice_clip_paths) == len(board.frames)` else abort
  (`voice_clip_count_mismatch`). Write each clip to its frame's
  `voice_filename`: MP3 magic bytes go direct, anything else converts via
  ffmpeg to mp3 (extension never trusted). Then the *existing*
  `attach_audio` + timing flow runs untouched — probing is provider-blind.
- Any `probe_duration` returning `None` aborts (`voice_clip_unprobed`).
  Per-clip cap `MAX_VOICE_CLIP_BYTES` (8 MB) and count cap
  `MAX_VOICE_CLIPS` (12, above the 8-scene contract ceiling); over either
  aborts. `voice_key` is ignored and logged when clips are present.

New route `POST /youtube/jobs/with-voice` (multipart): same fields as
`/youtube/jobs` (form fields, clips as repeated `clips` files in scene
order) plus synchronous validation (story uuid, channel resolve, mode,
image provider, caps, at least one clip) before `create_job`. Files land in
`VIDEOS_DIR / f"voice-upload-{job_id}"` preserving upload order; the
background `run()` passes their paths through. Failures inside `run()` fail
the job exactly like `/youtube/jobs`.

## Motion uplift

- `camera_paths` grows 4 → 8 (same tuple shape, new pans/zooms).
- New pure `motion_style(intent: str) -> tuple[str, float]`: normalizes the
  `- Frame-to-motion intent:` line from `board.direction` (regex, first
  match, case-insensitive) into an ease family —
  subject-led → `power1.inOut`, energetic/bold → `power3.out`,
  gentle/soft/calm → `sine.inOut`, anything else → the index cycle default.
  Returns `(ease, scale_boost)`; boost nudges `camera_scale` ±0.01 by family.
- `render_cinematic_frame(..., motion_ease: str = "power1.inOut", motion_boost: float = 0.0)`
  uses the passed ease in the image tween instead of the hardcoded one.
  Defaults reproduce today's output exactly (existing goldens keep passing).
- `build_cinematic_frames` parses intent once per board, passes the style
  into each frame render. No id/track/timeline change — the HyperFrames
  contract is untouched.

## Testing

- Pure: MP3 magic detect (ID3 + sync-word), intent regex (present/absent/garbage), style mapping incl. fallback, layout goldens for the 8-path cycle.
- Pipeline (seams patched, ffmpeg/ffprobe patched): count mismatch aborts pre-audio; unprobed clip aborts; happy path writes `assets/voice/NN.mp3`, never calls the TTS seam, timing derives from probed durations; caps reject.
- Route: 400 on bad uuid/channel/mode/oversize/zero clips (no job created); 202 stores files in order and the job carries that order.
- Motion goldens: one render per family asserting the ease string in the timeline; default-output test proving byte-identical output for the old call shape.

## Non-goals (later pieces)

- GUI upload control (API + docs in this piece; owner can curl it).
- STT verification, per-word timing, lip-sync.
- Queue concurrency (piece 4), new channels (piece 5), long-form track.

## Files touched

- `worker/app/youtube.py` (voice-clip ingest + branch, caps, route fields)
- `worker/app/routes.py` (new multipart endpoint)
- `worker/app/scene3d/backend.py` (paths, style map, render params)
- `worker/app/storyboard.py` (untouched — probing/timing already provider-blind)
- Tests: new `worker/tests/test_voice_input.py`, `test_motion_style.py` additions in `test_scene3d_backend.py`, route tests in `test_routes_modes.py`
