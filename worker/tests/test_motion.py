"""Motion pipeline: provider normalization, I2V clients, ffmpeg normalize, renderer, dispatch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.storyboard import Frame, Storyboard


def _board(n=3, direction: str | None = None):
    board = Storyboard(meta={"title": "T"})
    board.direction = direction
    board.frames = [
        Frame(
            index=i,
            title=f"S{i}",
            voiceover=f"line {i}",
            scene=f"scene {i}",
            duration=5.0,
        )
        for i in range(1, n + 1)
    ]
    return board


# ---------------------------------------------------------------------------
# Provider normalization + statuses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["off", "veo", "kling", " VEO ", None, ""])
def test_normalize_motion_provider_accepts_known(provider):
    from app.scene3d.motion import normalize_motion_provider

    expected = "veo" if provider and provider.strip().lower() == "veo" else (provider or "off").strip().lower()
    assert normalize_motion_provider(provider) == expected


def test_normalize_motion_provider_rejects_unknown():
    from app.scene3d.motion import normalize_motion_provider

    with pytest.raises(ValueError, match="unknown motion provider"):
        normalize_motion_provider("runway")


def test_motion_provider_statuses_reflect_env(monkeypatch):
    from app.scene3d import motion

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    statuses = {item["id"]: item for item in motion.motion_provider_statuses()}
    assert statuses["off"]["configured"] is True
    assert statuses["veo"]["configured"] is False
    assert statuses["kling"]["configured"] is False

    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("FAL_KEY", "key")
    statuses = {item["id"]: item for item in motion.motion_provider_statuses()}
    assert statuses["veo"]["configured"] is True
    assert statuses["kling"]["configured"] is True


def test_require_motion_provider_raises_when_unconfigured(monkeypatch):
    from app.scene3d.motion import require_motion_provider

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        require_motion_provider("veo")
    assert require_motion_provider("off") == "off"


def test_generate_motion_clip_dispatches():
    from app.scene3d import motion

    with (
        patch.object(motion, "generate_veo_clip", new=AsyncMock()) as veo,
        patch.object(motion, "generate_kling_clip", new=AsyncMock()) as kling,
    ):
        keyframe = MagicMock()
        import asyncio

        asyncio.run(motion.generate_motion_clip("veo", keyframe, "p", MagicMock()))
        veo.assert_awaited_once()
        asyncio.run(motion.generate_motion_clip("kling", keyframe, "p", MagicMock()))
        kling.assert_awaited_once()
        with pytest.raises(ValueError, match="does not generate clips"):
            asyncio.run(motion.generate_motion_clip("off", keyframe, "p", MagicMock()))


# ---------------------------------------------------------------------------
# normalize_clip — one ffmpeg pass, trim vs loop, audio stripped
# ---------------------------------------------------------------------------


def _run_stub(source_seconds):
    def fake_run(command, *args, **kwargs):
        if command[0] == "ffprobe":
            if source_seconds is None:
                return MagicMock(returncode=1, stdout="")
            return MagicMock(returncode=0, stdout=f"{source_seconds}\n")
        return MagicMock(returncode=0, stderr="")

    return fake_run


@pytest.mark.asyncio
async def test_normalize_clip_trims_longer_source(tmp_path):
    from app.scene3d import motion

    source = tmp_path / "clip.raw.mp4"
    source.write_bytes(b"x")
    destination = tmp_path / "clip.mp4"

    with patch.object(motion.subprocess, "run", side_effect=_run_stub(8.0)) as run:
        await motion.normalize_clip(source, destination, 5.0)

    ffmpeg_call = run.call_args_list[-1]
    command = ffmpeg_call.args[0]
    assert command[0] == "ffmpeg"
    assert "-stream_loop" not in command
    assert "-an" in command
    assert "-t" in command
    assert command[command.index("-t") + 1] == "5.000"
    assert "libx264" in command
    assert "yuv420p" in command
    assert command[command.index("-crf") + 1] == "18"
    assert command[command.index("-preset") + 1] == "slow"
    vf = command[command.index("-vf") + 1]
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in vf
    assert "crop=1080:1920" in vf
    assert "fps=30" in vf
    assert "setsar=1" in vf
    assert command[-1] == str(destination)


@pytest.mark.asyncio
async def test_normalize_clip_loops_shorter_source(tmp_path):
    from app.scene3d import motion

    source = tmp_path / "clip.raw.mp4"
    source.write_bytes(b"x")

    with patch.object(motion.subprocess, "run", side_effect=_run_stub(3.0)) as run:
        await motion.normalize_clip(source, tmp_path / "clip.mp4", 5.0)

    command = run.call_args_list[-1].args[0]
    assert command[command.index("-stream_loop") + 1] == "-1"
    assert "-an" in command


@pytest.mark.asyncio
async def test_normalize_clip_loops_when_probe_fails(tmp_path):
    from app.scene3d import motion

    source = tmp_path / "clip.raw.mp4"
    source.write_bytes(b"x")

    with patch.object(motion.subprocess, "run", side_effect=_run_stub(None)) as run:
        await motion.normalize_clip(source, tmp_path / "clip.mp4", 5.0)

    command = run.call_args_list[-1].args[0]
    assert "-stream_loop" in command


@pytest.mark.asyncio
async def test_normalize_clip_raises_on_ffmpeg_failure(tmp_path):
    from app.scene3d import motion

    source = tmp_path / "clip.raw.mp4"
    source.write_bytes(b"x")

    def failing(command, *args, **kwargs):
        if command[0] == "ffprobe":
            return MagicMock(returncode=0, stdout="8.0\n")
        return MagicMock(returncode=1, stderr="boom")

    with patch.object(motion.subprocess, "run", side_effect=failing):
        with pytest.raises(RuntimeError, match="ffmpeg could not normalize"):
            await motion.normalize_clip(source, tmp_path / "clip.mp4", 5.0)


# ---------------------------------------------------------------------------
# generate_veo_clip — fake genai client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_veo_clip_polls_and_downloads(tmp_path, monkeypatch):
    from app.scene3d import motion

    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png-bytes")
    destination = tmp_path / "clip.raw.mp4"

    pending = SimpleNamespace(done=False, error=None, response=None)
    done = SimpleNamespace(
        done=True,
        error=None,
        response=SimpleNamespace(
            generated_videos=[SimpleNamespace(video=SimpleNamespace(uri="https://files.example/v.mp4"))]
        ),
    )
    client = MagicMock()
    client.models.generate_videos.return_value = pending
    client.operations.get.side_effect = [done]
    client.files.download.return_value = b"mp4-bytes"

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    with patch.object(motion, "_veo_client", return_value=client) as make_client:
        await motion.generate_veo_clip(keyframe, "a prompt", destination)

    make_client.assert_called_once()
    kwargs = client.models.generate_videos.call_args.kwargs
    assert kwargs["model"] == motion.GEMINI_VIDEO_MODEL
    assert kwargs["prompt"] == "a prompt"
    assert kwargs["image"].mime_type == "image/png"
    assert kwargs["image"].image_bytes == b"png-bytes"
    assert kwargs["config"].resolution == "1080p"
    assert kwargs["config"].aspect_ratio == "9:16"
    assert kwargs["config"].number_of_videos == 1
    client.operations.get.assert_called_once_with(pending)
    client.files.download.assert_called_once_with(file="https://files.example/v.mp4")
    assert destination.read_bytes() == b"mp4-bytes"


@pytest.mark.asyncio
async def test_generate_veo_clip_raises_when_operation_errors(tmp_path, monkeypatch):
    from app.scene3d import motion

    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png-bytes")
    client = MagicMock()
    client.models.generate_videos.return_value = SimpleNamespace(
        done=True, error="quota exceeded", response=None
    )
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    with patch.object(motion, "_veo_client", return_value=client):
        with pytest.raises(RuntimeError, match="Veo generation failed"):
            await motion.generate_veo_clip(keyframe, "p", tmp_path / "out.mp4")


@pytest.mark.asyncio
async def test_generate_veo_clip_retries_on_quota_then_succeeds(tmp_path, monkeypatch):
    from app.scene3d import motion

    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png-bytes")
    destination = tmp_path / "clip.raw.mp4"
    done = SimpleNamespace(
        done=True,
        error=None,
        response=SimpleNamespace(
            generated_videos=[SimpleNamespace(video=SimpleNamespace(uri="https://files.example/v.mp4"))]
        ),
    )
    client = MagicMock()
    client.models.generate_videos.side_effect = [
        Exception("429 RESOURCE_EXHAUSTED: quota"),
        done,
    ]
    client.files.download.return_value = b"mp4-bytes"
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(motion, "VEO_RETRY_INITIAL_SECONDS", 0.01)

    with patch.object(motion, "_veo_client", return_value=client):
        await motion.generate_veo_clip(keyframe, "p", destination)

    assert client.models.generate_videos.call_count == 2
    assert destination.read_bytes() == b"mp4-bytes"


@pytest.mark.asyncio
async def test_generate_veo_clip_non_quota_error_reraises_immediately(tmp_path, monkeypatch):
    from app.scene3d import motion

    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png-bytes")
    client = MagicMock()
    client.models.generate_videos.side_effect = ValueError("invalid prompt")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(motion, "VEO_RETRY_INITIAL_SECONDS", 0.01)

    with patch.object(motion, "_veo_client", return_value=client):
        with pytest.raises(ValueError, match="invalid prompt"):
            await motion.generate_veo_clip(keyframe, "p", tmp_path / "out.mp4")

    assert client.models.generate_videos.call_count == 1


# ---------------------------------------------------------------------------
# generate_kling_clip — mocked httpx
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None, content=b"", text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.content = content
        self.text = text

    def json(self):
        return self._json


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.post_calls = []
        self.get_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return _FakeResponse(
            json_body={"status_url": "https://queue.fal.run/status/1", "response_url": "https://queue.fal.run/result/1"}
        )

    async def get(self, url, **kwargs):
        self.get_calls.append(url)
        if "status" in url:
            return _FakeResponse(json_body={"status": "COMPLETED"})
        if "result" in url:
            return _FakeResponse(json_body={"video": {"url": "https://cdn.example/clip.mp4"}})
        return _FakeResponse(content=b"kling-bytes")


@pytest.mark.asyncio
async def test_generate_kling_clip_queue_flow(tmp_path, monkeypatch):
    from app.scene3d import motion

    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png-bytes")
    destination = tmp_path / "clip.raw.mp4"
    monkeypatch.setenv("FAL_KEY", "fal-key")

    fake = _FakeAsyncClient()
    with patch("httpx.AsyncClient", return_value=fake):
        await motion.generate_kling_clip(keyframe, "a prompt", destination)

    url, kwargs = fake.post_calls[0]
    assert url == motion.FAL_KLING_URL
    assert kwargs["headers"]["Authorization"] == "Key fal-key"
    payload = kwargs["json"]
    assert payload["prompt"] == "a prompt"
    assert payload["image_url"].startswith("data:image/png;base64,")
    assert payload["duration"] == "5"
    assert any("status" in u for u in fake.get_calls)
    assert any("cdn.example" in u for u in fake.get_calls)
    assert destination.read_bytes() == b"kling-bytes"


@pytest.mark.asyncio
async def test_generate_kling_clip_requires_fal_key(tmp_path, monkeypatch):
    from app.scene3d import motion

    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FAL_KEY"):
        await motion.generate_kling_clip(tmp_path / "f.png", "p", tmp_path / "o.mp4")


# ---------------------------------------------------------------------------
# Motion prompt + composition renderer contract
# ---------------------------------------------------------------------------


def test_cinematic_motion_prompt_is_short_and_uses_direction():
    from app.scene3d.backend import cinematic_motion_prompt

    board = _board(direction="- Frame-to-motion intent: gentle dolly-in on the guide")
    prompt = cinematic_motion_prompt(board, board.frames[0])
    assert len(prompt) <= 500
    assert "scene 1" in prompt
    assert "gentle dolly-in on the guide" in prompt
    assert prompt.endswith("no text, no captions.")


def test_render_cinematic_motion_frame_contract():
    from app.scene3d.backend import render_cinematic_motion_frame

    html = render_cinematic_motion_frame("shot-1", 6.0, "assets/cinematic/shot-1.mp4", "assets/cinematic/shot-1.png", 2)
    assert html.startswith("<!doctype html>")
    assert 'data-composition-id="shot-1"' in html
    assert 'data-duration="6.0"' in html
    assert 'data-width="1080"' in html
    assert 'data-height="1920"' in html
    assert "<video" in html
    assert 'src="../../assets/cinematic/shot-1.mp4"' in html
    assert 'poster="../../assets/cinematic/shot-1.png"' in html
    assert "muted" in html
    assert 'data-track-index="1"' in html
    assert 'class="video hero-video clip"' in html
    assert 'window.__timelines["shot-1"]' in html
    # Ken Burns hero <img> must NOT be the motion hero.
    assert 'id="shot-1-image"' not in html


# ---------------------------------------------------------------------------
# Dispatch through youtube._build_frames
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_frames_routes_to_cinematic_with_motion(tmp_path):
    from app import youtube
    from app.storyboard import Storyboard

    with patch(
        "app.youtube.build_cinematic_frames", new=AsyncMock(return_value=[])
    ) as cinematic:
        await youtube._build_frames(
            Storyboard(), tmp_path, backend="cinematic", image_provider="gemini", motion="veo"
        )
    cinematic.assert_awaited_once_with(Storyboard(), tmp_path, provider="gemini", motion="veo")


@pytest.mark.asyncio
async def test_build_frames_ignores_motion_on_three_backend(tmp_path):
    from app import youtube
    from app.storyboard import Storyboard

    with patch("app.youtube.build_3d_frames", new=AsyncMock(return_value=[])) as three:
        await youtube._build_frames(Storyboard(), tmp_path, backend="three", motion="veo")
    three.assert_awaited_once()


# ---------------------------------------------------------------------------
# Full cinematic build with motion on and I2V mocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cinematic_build_with_motion_writes_video_compositions(tmp_path):
    from app.scene3d import backend

    board = _board(n=3)
    with (
        patch.object(backend, "require_cinematic_image_provider", return_value="gemini"),
        patch.object(backend, "_generate_cinematic_image", new=AsyncMock()) as gen_image,
        patch.object(backend, "generate_motion_clip", new=AsyncMock()) as gen_clip,
        patch.object(backend, "normalize_clip", new=AsyncMock()) as normalize,
    ):
        await backend.build_cinematic_frames(board, tmp_path, provider="gemini", motion="veo")

    assert gen_image.await_count == 3
    assert gen_clip.await_count == 3
    assert normalize.await_count == 3
    for call in normalize.await_args_list:
        assert call.args[2] == 5.0
    for frame in board.frames:
        html = (tmp_path / "compositions" / "frames" / f"{frame.slug}.html").read_text(encoding="utf-8")
        assert "<video" in html
        assert f"assets/cinematic/{frame.slug}.mp4" in html
        assert f"assets/cinematic/{frame.slug}.png" in html


@pytest.mark.asyncio
async def test_cinematic_build_reuses_normalized_clips_on_retry(tmp_path):
    from app.scene3d import backend

    board = _board(n=3)
    reused = board.frames[0]
    assets = tmp_path / "assets" / "cinematic"
    assets.mkdir(parents=True)
    (assets / f"{reused.slug}.mp4").write_bytes(b"already-normalized")

    with (
        patch.object(backend, "require_cinematic_image_provider", return_value="gemini"),
        patch.object(backend, "_generate_cinematic_image", new=AsyncMock()),
        patch.object(backend, "generate_motion_clip", new=AsyncMock()) as gen_clip,
        patch.object(backend, "normalize_clip", new=AsyncMock()) as normalize,
    ):
        await backend.build_cinematic_frames(board, tmp_path, provider="gemini", motion="veo")

    assert gen_clip.await_count == 2
    assert normalize.await_count == 2


@pytest.mark.asyncio
async def test_cinematic_build_without_motion_keeps_ken_burns(tmp_path):
    from app.scene3d import backend

    board = _board(n=2)
    with (
        patch.object(backend, "require_cinematic_image_provider", return_value="gemini"),
        patch.object(backend, "_generate_cinematic_image", new=AsyncMock()),
        patch.object(backend, "generate_motion_clip", new=AsyncMock()) as gen_clip,
    ):
        await backend.build_cinematic_frames(board, tmp_path, provider="gemini")

    assert gen_clip.await_count == 0
    for frame in board.frames:
        html = (tmp_path / "compositions" / "frames" / f"{frame.slug}.html").read_text(encoding="utf-8")
        assert "<video" not in html
        assert 'class="image hero-image clip"' in html
