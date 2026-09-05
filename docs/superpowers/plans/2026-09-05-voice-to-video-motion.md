# Voice-to-Video + Motion Uplift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Owners upload per-scene narration instead of Edge TTS, and cinematic frames move with intent-driven eases over eight camera paths.

**Architecture:** Voice clips land on the exact `assets/voice/NN.mp3` paths synthesis would have written, so probing, timing, and rendering run untouched; a branch in `generate_youtube_video` swaps synthesis for validated ingest. Motion stays deterministic: a pure intent→style map feeds new render params with defaults that reproduce today's output. API-first via a multipart job route mirroring `/youtube/jobs`.

**Tech Stack:** Python worker, ffmpeg/ffprobe (already required), FastAPI multipart (`UploadFile`), pytest with seam patching (never the network, never real ffmpeg in unit tests).

**Spec:** `docs/superpowers/specs/2026-09-05-voice-to-video-motion-design.md`

## Global Constraints

- Tests must not touch the network or real ffmpeg/ffprobe; patch `app.youtube.subprocess.run`, `app.storyboard.probe_duration`, and the router/LLM seams.
- Never substitute: count mismatch, oversize, empty, or unprobable clips abort loud. No silence under owner audio.
- Nothing auto-publishes; no STT layer in this plan.
- PowerShell 5.1 for shells (no `&&`); pytest as `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`.
- The working tree may hold unrelated uncommitted work: stage ONLY your hunks (filtered patch / selective staging). Depend ONLY on committed code — `channels.find_blocked_terms` does not exist at HEAD. Do NOT push (Task 4 pushes once).

---

### Task 1: Voice-clip ingest core

**Files:**
- Modify: `worker/app/youtube.py` (caps, `is_mp3_bytes`, `_ingest_voice_clips`, signature + branch + unprobed guard)
- Test: `worker/tests/test_voice_input.py` (new)

**Interfaces:**
- Consumes: `board.frames[i].voice_filename` (`assets/voice/{index:02d}.mp3`), existing `attach_audio`/`assign_timing`.
- Produces: `is_mp3_bytes(data: bytes) -> bool`; `_ingest_voice_clips(board, video_dir: Path, clip_paths: list[Path]) -> None` (raises `ValueError` on count/size/empty/ffmpeg failure); `MAX_VOICE_CLIP_BYTES = 8*1024*1024`; `MAX_VOICE_CLIPS = 12`; `generate_youtube_video(..., voice_clip_paths: list[Path] | None = None)`.

- [ ] **Step 1: Write the failing tests**

```python
"""Owner narration ingest. No network, no real ffmpeg, no TTS."""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels import Channel
from app.storyboard import Frame, Storyboard


def _board(n=3):
    board = Storyboard(meta={"title": "T", "description": "D"})
    board.frames = [
        Frame(index=i, title=f"S{i}", voiceover=f"line {i}", scene=f"scene {i}")
        for i in range(1, n + 1)
    ]
    return board


def _clip(tmp_path, name, data=b"ID3fake"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _clips(tmp_path, n=3, data=b"ID3x"):
    return [_clip(tmp_path, f"c{i}.mp3", data) for i in range(n)]


def test_is_mp3_bytes_accepts_id3_and_frame_sync():
    from app.youtube import is_mp3_bytes

    assert is_mp3_bytes(b"ID3\x04xxxxxxxx")
    assert is_mp3_bytes(bytes([0xFF, 0xFB]) + b"xxxxxxxx")
    assert not is_mp3_bytes(b"RIFF....WAVE")
    assert not is_mp3_bytes(b"")


async def test_ingest_rejects_a_count_mismatch(tmp_path):
    from app.youtube import _ingest_voice_clips

    board = _board(3)
    with pytest.raises(ValueError, match="expected 3 voice clips, got 2"):
        await _ingest_voice_clips(board, tmp_path, [_clip(tmp_path, "a.mp3"), _clip(tmp_path, "b.mp3")])


async def test_ingest_rejects_an_empty_clip(tmp_path):
    from app.youtube import _ingest_voice_clips

    board = _board(1)
    with pytest.raises(ValueError, match="empty"):
        await _ingest_voice_clips(board, tmp_path, [_clip(tmp_path, "a.mp3", b"")])


async def test_ingest_rejects_an_oversize_clip(tmp_path, monkeypatch):
    from app import youtube
    from app.youtube import _ingest_voice_clips

    monkeypatch.setattr(youtube, "MAX_VOICE_CLIP_BYTES", 10)
    board = _board(1)
    with pytest.raises(ValueError, match="exceeds"):
        await _ingest_voice_clips(board, tmp_path, [_clip(tmp_path, "a.mp3", b"ID3" + b"x" * 20)])


async def test_ingest_writes_mp3_directly_without_ffmpeg(tmp_path):
    from unittest.mock import patch

    from app.youtube import _ingest_voice_clips

    board = _board(2)
    clips = [_clip(tmp_path, "a.mp3", b"ID3one"), _clip(tmp_path, "b.mp3", b"ID3two")]
    with patch("app.youtube.subprocess.run", side_effect=AssertionError("ffmpeg must not run")):
        await _ingest_voice_clips(board, tmp_path, clips)
    assert (tmp_path / "assets" / "voice" / "01.mp3").read_bytes() == b"ID3one"
    assert (tmp_path / "assets" / "voice" / "02.mp3").read_bytes() == b"ID3two"


async def test_ingest_converts_non_mp3_through_ffmpeg(tmp_path):
    from unittest.mock import patch

    from app.youtube import _ingest_voice_clips

    board = _board(1)
    clip = _clip(tmp_path, "a.wav", b"RIFF....WAVE")
    with patch("app.youtube.subprocess.run") as run:
        await _ingest_voice_clips(board, tmp_path, [clip])
    args = run.call_args.args[0]
    assert args[0] == "ffmpeg"
    assert str(tmp_path / "assets" / "voice" / "01.mp3") in args
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_voice_input.py -q`
Expected: FAIL with `ImportError` (no `is_mp3_bytes` in `app.youtube` yet)

- [ ] **Step 3: Implement ingest**

```python
MAX_VOICE_CLIP_BYTES = 8 * 1024 * 1024
MAX_VOICE_CLIPS = 12


def is_mp3_bytes(data: bytes) -> bool:
    """True when bytes are already MP3: ID3 header or frame-sync word."""
    if data[:3] == b"ID3":
        return True
    return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0


async def _ingest_voice_clips(board, video_dir: Path, clip_paths: list[Path]) -> None:
    """Stage owner narration onto each frame's voice path. Raises, never substitutes.

    Clips match scenes by order. MP3 bytes land directly; anything else is
    normalized through ffmpeg (extension never trusted). Probing happens later
    in the shared attach_audio step.
    """
    if len(clip_paths) != len(board.frames):
        raise ValueError(f"expected {len(board.frames)} voice clips, got {len(clip_paths)}")
    voice_dir = video_dir / "assets" / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    for frame, source in zip(board.frames, clip_paths):
        size = source.stat().st_size
        if size == 0:
            raise ValueError(f"voice clip for scene {frame.index} is empty")
        if size > MAX_VOICE_CLIP_BYTES:
            raise ValueError(
                f"voice clip for scene {frame.index} exceeds {MAX_VOICE_CLIP_BYTES} bytes"
            )
        destination = video_dir / frame.voice_filename
        raw = source.read_bytes()
        if is_mp3_bytes(raw):
            destination.write_bytes(raw)
            continue
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(source), str(destination)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
```

`subprocess` is already imported in `youtube.py`. `ffmpeg` missing surfaces as
`FileNotFoundError` from `subprocess.run` — a loud abort, which is correct.

- [ ] **Step 4: Branch the pipeline** (in `generate_youtube_video`)

a) Signature: append keyword `voice_clip_paths: list[Path] | None = None` after
`cinematic_controls`. `Path` is already imported.

b) Replace the narration block (`log.info("youtube_audio_generation_started"...)`
through the end of the `if silenced:` block) with:

```python
    using_owner_voice = voice_clip_paths is not None
    if using_owner_voice:
        if len(voice_clip_paths) > MAX_VOICE_CLIPS:
            log.error(
                "youtube_generation_aborted",
                reason="too_many_voice_clips",
                story_id=str(story_id),
                clips=len(voice_clip_paths),
                maximum=MAX_VOICE_CLIPS,
            )
            return None
        if voice_key:
            log.info("youtube_owner_voice_ignores_voice_key", story_id=str(story_id))
        log.info("youtube_audio_owner_voice", video_dir=str(video_dir), frames=len(board.frames))
        await _stage(job_id, "narration", 0, len(board.frames))
        try:
            await _ingest_voice_clips(board, video_dir, voice_clip_paths)
        except Exception as e:
            log.error(
                "youtube_generation_aborted",
                reason="voice_clip_rejected",
                story_id=str(story_id),
                error=str(e)[:200],
            )
            return None
    else:
        <the existing synthesis block verbatim, indented under else>
```

c) After `attach_audio(board, video_dir)` (line ~269), insert:

```python
    if using_owner_voice:
        unprobed = [frame.slug for frame in board.frames if not frame.audio_duration]
        if unprobed:
            log.error(
                "youtube_generation_aborted",
                reason="voice_clip_unprobed",
                story_id=str(story_id),
                slugs=unprobed,
            )
            return None
```

- [ ] **Step 5: Pipeline tests** (append to `worker/tests/test_voice_input.py`)

Top of file: `import uuid` plus `from unittest.mock import AsyncMock, MagicMock, patch`
alongside the existing imports. Override board (3 scenes satisfies
`MIN_SCRIPT_FRAMES`; override boards skip the structure validator; no `tags:`
line means tags default to `[]`):

```python
OVERRIDE_3 = (
    "---\ntitle: T\ndescription: D\npreset: adult_male\n---\n\n"
    "# Scene 1\nVoiceover: A\n\n# Scene 2\nVoiceover: B\n\n# Scene 3\nVoiceover: C\n"
)

FINANCE_VOICE = Channel(
    id="financial-channel", display_name="Finance", voice_key="adult_male",
    script_prompt="A prompt.", extra_blocklist=(),
)
```

`from app.channels import Channel` at the top with the other imports.

```python
def _clips(tmp_path, n=3, data=b"ID3x"):
    paths = []
    for i in range(n):
        clip = tmp_path / f"c{i}.mp3"
        clip.write_bytes(data)
        paths.append(clip)
    return paths


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE_VOICE))
@patch("app.youtube._fetch_story_details", AsyncMock(return_value={"headline": "T"}))
@patch("app.youtube._record_youtube_draft", AsyncMock(return_value=uuid.uuid4()))
@patch("app.youtube._generate_frame_audio", AsyncMock(side_effect=AssertionError("TTS must not run")))
@patch("app.youtube._build_frames", AsyncMock(return_value=[]))
@patch("app.youtube.subprocess.run", MagicMock(return_value=MagicMock(stdout="mocked")))
@patch("app.youtube.build_thumbnail_variants", AsyncMock(return_value={}))
async def test_voice_count_mismatch_aborts_before_audio(
    mock_thumb, mock_run, mock_frames, mock_audio, mock_script_unused, mock_record, mock_fetch, tmp_path
):
```

No — stop. The decorator count must match the parameter list exactly, and an
unused `_generate_script_for_story` patch is not in this list, so write the
decorators to match the params one-for-one, bottom-up (innermost decorator =
first parameter). Full correct test:

```python
@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE_VOICE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube.build_thumbnail_variants", AsyncMock(return_value={}))
async def test_voice_count_mismatch_aborts_before_audio(
    mock_thumb, mock_run, mock_frames, mock_audio, mock_record, mock_fetch, tmp_path
):
    from app.youtube import generate_youtube_video

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(
            story_id=uuid.uuid4(),
            channel_id="financial-channel",
            storyboard_override=OVERRIDE_3,
            voice_clip_paths=[tmp_path / "only.mp3"],
        ) is None
```

Wait — the clips must exist for the count check? The count check runs before
any file read (`len(clip_paths) != len(board.frames)` first), so nonexistent
paths still abort on count. But to keep the test honest (count, not missing
files, is the trigger), create the single clip file first:

```python
    clip = tmp_path / "only.mp3"
    clip.write_bytes(b"ID3x")
```

then pass `voice_clip_paths=[clip]` against the 3-scene board. `_generate_frame_audio`
needs the no-TTS tripwire: it is patched bare (MagicMock autospec → AsyncMock
for async targets), so give it a side_effect instead:

```python
@patch("app.youtube._generate_frame_audio", AsyncMock(side_effect=AssertionError("TTS must not run")))
```

and assert it was never awaited after the run. But careful: bare `@patch`
without `new` injects the mock as the parameter in bottom-up order. Final,
verified-shape tests (copy verbatim):

```python
@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE_VOICE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_frame_audio", AsyncMock(side_effect=AssertionError("TTS must not run")))
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube.build_thumbnail_variants", AsyncMock(return_value={}))
async def test_voice_count_mismatch_aborts_before_audio(
    mock_thumb, mock_run, mock_frames, mock_audio, mock_record, mock_fetch, tmp_path
):
    from app.youtube import generate_youtube_video

    clip = tmp_path / "only.mp3"
    clip.write_bytes(b"ID3x")
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(
            story_id=uuid.uuid4(),
            channel_id="financial-channel",
            storyboard_override=OVERRIDE_3,
            voice_clip_paths=[clip],
        ) is None
    mock_audio.assert_not_called()


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE_VOICE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_frame_audio", AsyncMock(side_effect=AssertionError("TTS must not run")))
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube.build_thumbnail_variants", AsyncMock(return_value={}))
@patch("app.storyboard.probe_duration", return_value=None)
async def test_voice_unprobed_clip_aborts(
    mock_probe, mock_thumb, mock_run, mock_frames, mock_audio, mock_record, mock_fetch, tmp_path
):
    from app.youtube import generate_youtube_video

    clips = _clips(tmp_path, 3)
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        assert await generate_youtube_video(
            story_id=uuid.uuid4(),
            channel_id="financial-channel",
            storyboard_override=OVERRIDE_3,
            voice_clip_paths=clips,
        ) is None
    mock_audio.assert_not_called()


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE_VOICE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_frame_audio", AsyncMock(side_effect=AssertionError("TTS must not run")))
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube.build_thumbnail_variants", AsyncMock(return_value={}))
@patch("app.storyboard.probe_duration", return_value=4.0)
async def test_voice_happy_path_skips_tts_and_records(
    mock_probe, mock_thumb, mock_run, mock_frames, mock_audio, mock_record, mock_fetch, tmp_path
):
    from app.youtube import generate_youtube_video

    clips = _clips(tmp_path, 3)
    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=uuid.uuid4(),
            channel_id="financial-channel",
            storyboard_override=OVERRIDE_3,
            voice_clip_paths=clips,
        )
    assert draft_id is not None
    mock_audio.assert_not_called()
    mock_record.assert_called_once()
```

Decorator/parameter audit (bottom-up): `probe`→mock_probe (absent in the
first test — its decorator list has no probe patch and no mock_probe param ✓),
`build_thumbnail_variants`→mock_thumb, `subprocess.run`→mock_run,
`_build_frames`→mock_frames, `_generate_frame_audio`→mock_audio,
`_record_youtube_draft`→mock_record, `_fetch_story_details`→mock_fetch,
`resolve` (with `new`)→ not injected, `tmp_path` is the real fixture ✓.
`@patch` with `new=` supplied never injects — that is why `resolve` has no
parameter. `pytest`, `uuid`, `Channel` are top-level imports of the test file.

- [ ] **Step 6: Run green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_voice_input.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add worker/app/youtube.py worker/tests/test_voice_input.py
git commit -m "Add owner-narration ingest path alongside Edge TTS"
```

---

### Task 2: Multipart voice route

**Files:**
- Modify: `worker/app/routes.py` (extend the fastapi import line, add endpoint)
- Test: `worker/tests/test_routes_voice.py` (new)

**Interfaces:**
- Consumes: `generate_youtube_video(..., voice_clip_paths=...)` (Task 1), `channels.resolve`, `backend_for_mode`, `require_cinematic_image_provider`, `create_job`.
- Produces: `POST /youtube/jobs/with-voice` (multipart) → `{"job_id": ...}` (202) or 400. Bad input fails the request; the job only starts on valid input.

- [ ] **Step 1: Write the failing tests**

```python
"""Voice-job route: validation is synchronous, staging is on disk. No DB, no TTS."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.channels import ChannelConfigError
from app.main import app

client = TestClient(app)

JOB_ID = uuid4()


def _clips(n=2, size=10):
    return [("clips", (f"c{i}.mp3", b"ID3" + b"x" * size, "audio/mpeg")) for i in range(n)]


def test_rejects_a_bad_story_id_before_touching_jobs():
    with patch("app.jobs.create_job", AsyncMock()) as create:
        resp = client.post(
            "/youtube/jobs/with-voice",
            data={"story_id": "nope", "channel_id": "finance"},
            files=_clips(1),
        )
    assert resp.status_code == 400
    create.assert_not_awaited()


def test_rejects_an_unknown_channel():
    with patch(
        "app.channels.resolve",
        AsyncMock(side_effect=ChannelConfigError("unknown channel 'nope'; configured: finance, kids")),
    ), patch("app.jobs.create_job", AsyncMock()) as create:
        resp = client.post(
            "/youtube/jobs/with-voice",
            data={"story_id": str(uuid4()), "channel_id": "nope"},
            files=_clips(1),
        )
    assert resp.status_code == 400
    create.assert_not_awaited()


def test_rejects_zero_clips_and_oversize_clips():
    from app import youtube

    with patch("app.channels.resolve", AsyncMock()), \
            patch("app.jobs.create_job", AsyncMock()) as create:
        resp = client.post(
            "/youtube/jobs/with-voice",
            data={"story_id": str(uuid4()), "channel_id": "finance"},
            files=[],
        )
    assert resp.status_code == 400
    create.assert_not_awaited()

    big = [("clips", ("big.mp3", b"ID3" + b"x" * (youtube.MAX_VOICE_CLIP_BYTES + 1), "audio/mpeg"))]
    with patch("app.channels.resolve", AsyncMock()), \
            patch("app.jobs.create_job", AsyncMock()) as create:
        resp = client.post(
            "/youtube/jobs/with-voice",
            data={"story_id": str(uuid4()), "channel_id": "finance"},
            files=big,
        )
    assert resp.status_code == 400
    create.assert_not_awaited()


def test_accepts_clips_and_stages_them_in_order(tmp_path):
    from app import youtube

    staged: list[str] = []
    real_write = __import__("pathlib").Path.write_bytes

    def spy_write(self, data):
        if "voice-upload-" in str(self):
            staged.append(self.name)
        return real_write(self, data)

    with patch("app.channels.resolve", AsyncMock()), \
            patch("app.jobs.create_job", AsyncMock(return_value=JOB_ID)), \
            patch("app.jobs.finish_job", AsyncMock()), \
            patch("app.jobs.fail_job", AsyncMock()), \
            patch("app.youtube.generate_youtube_video", AsyncMock(return_value=JOB_ID)), \
            patch("app.youtube.VIDEOS_DIR", tmp_path), \
            patch("pathlib.Path.write_bytes", spy_write):
        resp = client.post(
            "/youtube/jobs/with-voice",
            data={"story_id": str(uuid4()), "channel_id": "finance"},
            files=_clips(2),
        )
    assert resp.status_code == 200
    assert resp.json() == {"job_id": str(JOB_ID)}
    assert staged == ["clip-01.mp3", "clip-02.mp3"]
```

Filenames: the route names staged files `clip-{i:02d}{suffix}` from upload
order, so the test asserts order without depending on client filenames.
Normalize the `__import__("pathlib")` into a top-level import when writing
the file. Do NOT assert background completion (response returns before
`run()` finishes).

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_voice.py -q`
Expected: FAIL with 404 (no such route yet)

- [ ] **Step 3: Implement the endpoint** (append after `youtube_job_start` in `routes.py`)

Extend line 21 to:

```python
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
```

```python
@router.post("/youtube/jobs/with-voice")
async def youtube_job_with_voice(
    story_id: str = Form(...),
    channel_id: str = Form(...),
    upload_preference: str = Form("manual"),
    mode: str | None = Form(None),
    storyboard: str | None = Form(None),
    image_provider: str | None = Form(None),
    voice_key: str | None = Form(None),
    clips: list[UploadFile] = File(...),
) -> dict:
    """Voice-to-video: owner narration in, everything else like /youtube/jobs.

    Clips match scenes by upload order. Validation is synchronous (a bad
    request fails here, never as a dead background job); files are staged to
    disk before the job starts so run() holds paths, not request memory.
    """
    import asyncio

    from app import channels
    from app.channels import ChannelConfigError
    from app.jobs import create_job, fail_job, finish_job
    from app.youtube import MAX_VOICE_CLIP_BYTES, MAX_VOICE_CLIPS, VIDEOS_DIR, generate_youtube_video

    try:
        try:
            sid = uuid.UUID(story_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid story_id (must be a uuid)")

        try:
            backend = backend_for_mode(mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if backend == "cinematic":
            from app.scene3d.backend import require_cinematic_image_provider

            try:
                require_cinematic_image_provider(image_provider)
            except (RuntimeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        await channels.resolve(channel_id)
        if voice_key:
            from app.youtube import VOICE_MAP

            if voice_key not in VOICE_MAP:
                raise HTTPException(status_code=400, detail=f"unknown voice key {voice_key!r}")

        if not clips:
            raise HTTPException(status_code=400, detail="at least one voice clip is required")
        if len(clips) > MAX_VOICE_CLIPS:
            raise HTTPException(status_code=400, detail=f"at most {MAX_VOICE_CLIPS} clips")

        payloads: list[tuple[str, bytes]] = []
        for upload in clips:
            raw = await upload.read(MAX_VOICE_CLIP_BYTES + 1)
            if len(raw) > MAX_VOICE_CLIP_BYTES:
                raise HTTPException(status_code=400, detail=f"clip {upload.filename!r} exceeds the size cap")
            if not raw:
                raise HTTPException(status_code=400, detail=f"clip {upload.filename!r} is empty")
            suffix = Path(upload.filename or "").suffix.lower()
            if not suffix or not __import__("re").match(r"^\.[a-z0-9]{1,5}$", suffix):
                suffix = ".audio"
            payloads.append((suffix, raw))

        job_id = await create_job(kind=(mode or "short"), story_id=sid)
        staging = VIDEOS_DIR / f"voice-upload-{job_id}"
        staging.mkdir(parents=True, exist_ok=True)
        clip_paths = []
        for index, (suffix, raw) in enumerate(payloads, start=1):
            path = staging / f"clip-{index:02d}{suffix}"
            path.write_bytes(raw)
            clip_paths.append(path)
    except HTTPException:
        raise
    except ChannelConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def run() -> None:
        try:
            draft_id = await generate_youtube_video(
                story_id=sid,
                channel_id=channel_id,
                upload_preference=upload_preference,
                backend=backend,
                job_id=job_id,
                storyboard_override=storyboard,
                image_provider=image_provider,
                voice_clip_paths=clip_paths,
            )
            if draft_id is None:
                await fail_job(job_id, "generation aborted by a quality guard; see worker logs")
            else:
                await finish_job(job_id, draft_id)
        except Exception as exc:  # noqa: BLE001
            await fail_job(job_id, str(exc))

    task = asyncio.create_task(run())
    _RUNNING_JOBS.add(task)
    task.add_done_callback(_RUNNING_JOBS.discard)

    return {"job_id": str(job_id)}
```

Notes: `uuid`, `Path` are already imported at routes top (lines 17-18).
For `re`: run `Select-String -Pattern "^import re" worker/app/routes.py` — if
absent, add `import re` to the stdlib block; if present, do nothing (no duplicate).
`voice_key` is accepted but only validated, never forwarded (owner voice wins;
the pipeline logs that). `storyboard` passes through as the override.

- [ ] **Step 4: Run route tests green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_voice.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/app/routes.py worker/tests/test_routes_voice.py
git commit -m "Add multipart voice-to-video job route"
```

---

### Task 3: Motion uplift (paths + intent-driven eases)

**Files:**
- Modify: `worker/app/scene3d/backend.py` (8 paths, `motion_intent_of`, `motion_style`, render params, caller threading)
- Test: `worker/tests/test_scene3d_backend.py` (append)

**Interfaces:**
- Consumes: `board.direction` (carries `- Frame-to-motion intent:` from cinematography controls).
- Produces: `motion_intent_of(direction: str) -> str`; `motion_style(intent: str) -> tuple[str, float]` (ease, scale boost); `render_cinematic_frame(..., motion_ease="power1.inOut", motion_boost=0.0)` — defaults reproduce today's output exactly.

- [ ] **Step 1: Write the failing tests**

```python
def test_motion_intent_parses_the_controls_line():
    from app.scene3d.backend import motion_intent_of

    direction = "## Cinematography controls\n- Shot scale: wide\n- Frame-to-motion intent: subject-led parallax\n- Lens: 50mm"
    assert motion_intent_of(direction) == "subject-led parallax"
    assert motion_intent_of("no controls here") == ""
    assert motion_intent_of("") == ""


def test_motion_style_maps_intent_families():
    from app.scene3d.backend import motion_style

    assert motion_style("subject-led parallax") == ("power1.inOut", 0.0)
    assert motion_style("Bold energetic push")[0] == "power3.out"
    assert motion_style("soft calm drift")[0] == "sine.inOut"
    assert motion_style("something unknown") == ("power1.inOut", 0.0)
    assert motion_style("") == ("power1.inOut", 0.0)


def test_render_honors_motion_ease_and_boost():
    from app.scene3d.backend import render_cinematic_frame

    html = render_cinematic_frame("s1", 5.0, "assets/cinematic/s1.png", 1, motion_ease="power3.out", motion_boost=0.01)
    assert 'ease: "power3.out"' in html
    assert "1.125" in html  # 1.115 base scale + 0.01 boost


def test_render_defaults_reproduce_the_old_output():
    from app.scene3d.backend import render_cinematic_frame

    html = render_cinematic_frame("s1", 5.0, "assets/cinematic/s1.png", 1)
    assert 'ease: "power1.inOut"' in html
    assert "1.115" in html


def test_camera_cycle_covers_eight_paths():
    from app.scene3d.backend import render_cinematic_frame

    fifth = render_cinematic_frame("s1", 5.0, "img.png", 5)
    first = render_cinematic_frame("s1", 5.0, "img.png", 1)
    assert fifth != first
    ninth = render_cinematic_frame("s1", 5.0, "img.png", 9)
    assert "1.115" in ninth  # index 9 wraps back to path 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_scene3d_backend.py -q -k "motion or camera_cycle or render_honors or render_defaults"`
Expected: FAIL with `ImportError` / `TypeError` (no `motion_intent_of`, no new params)

- [ ] **Step 3: Implement**

```python
_MOTION_INTENT = re.compile(r"^\s*-\s*Frame-to-motion intent:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def motion_intent_of(direction: str) -> str:
    """First `- Frame-to-motion intent:` line in the direction bible, else ""."""
    match = _MOTION_INTENT.search(direction or "")
    return match.group(1).strip() if match else ""


def motion_style(intent: str) -> tuple[str, float]:
    """Map an intent line to (gsap ease, camera-scale boost). Unknown falls back."""
    lowered = (intent or "").lower()
    if "subject" in lowered:
        return ("power1.inOut", 0.0)
    if "energetic" in lowered or "bold" in lowered or "dynamic" in lowered:
        return ("power3.out", 0.01)
    if "gentle" in lowered or "soft" in lowered or "calm" in lowered or "slow" in lowered:
        return ("sine.inOut", -0.01)
    return ("power1.inOut", 0.0)
```

`re` is already imported in backend.py. Camera paths 4 → 8:

```python
    camera_paths = (
        (-18, -14, 1.115), (16, -10, 1.13), (-12, 15, 1.12), (18, 12, 1.125),
        (-10, 16, 1.14), (14, 14, 1.11), (-16, 8, 1.135), (10, -16, 1.12),
    )
```

(First four tuples byte-identical: indices 1–4 render exactly as before.)

Render signature and image tween:

```python
def render_cinematic_frame(
    slug: str, duration: float, image_src: str, motion_index: int = 1,
    motion_ease: str = "power1.inOut", motion_boost: float = 0.0,
) -> str:
```

In the template, the image tween line becomes:

```
tl.fromTo(\"#{slug}-image\", {{ scale: 1.025, x: 0, y: 0 }}, {{ scale: {camera_scale + motion_boost}, x: {pan_x}, y: {pan_y}, duration: {duration}, ease: \"{motion_ease}\" }}, 0);
```

Scale formatting: `camera_scale + motion_boost` for index 1 default =
1.115 → f-string renders `1.115` ✓; boosted 1.125 → renders `1.125`
(python str(1.115+0.01) == '1.125' — verify in the test run; if float dust
appears, round(..., 3) in the template expression).

Caller in `build_cinematic_frames`, before the loop:

```python
    ease, boost = motion_style(motion_intent_of(board.direction))
```

and the render call gains `ease, boost`:

```python
            render_cinematic_frame(frame.slug, frame.duration, image_src, completed, ease, boost),
```

- [ ] **Step 4: Run backend tests green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_scene3d_backend.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add worker/app/scene3d/backend.py worker/tests/test_scene3d_backend.py
git commit -m "Drive cinematic motion from intent over eight camera paths"
```

---

### Task 4: Full verification + record + push

**Files:**
- Modify: `PROGRESS.md` (decision #78)

- [ ] **Step 1: Run the affected suites**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_voice_input.py tests/test_routes_voice.py tests/test_scene3d_backend.py tests/test_youtube.py tests/test_routes_modes.py tests/test_routes_channel.py tests/test_upload_metadata.py tests/test_generation_resilience.py -q`
Expected: PASS (DB-backed tests need local Postgres; without it they error — pre-existing, unrelated)

- [ ] **Step 2: Record the decision in PROGRESS.md**

```
| 78 | Voice-to-video via ordered per-scene clips; motion from intent over 8 paths | piece-3 | Clips land on synthesis paths so probing/timing run untouched; mismatch/unprobed/oversize abort loud, no silence under owner audio. Intent line selects ease family, unknown falls back. API-first; no GUI upload yet. |
```

- [ ] **Step 3: Commit and push**

```bash
git add PROGRESS.md
git commit -m "Record voice-to-video decision"
git push
```
