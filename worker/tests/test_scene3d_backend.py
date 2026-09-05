"""Orchestration: retry on rejection, raise rather than substitute."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.scene3d.probes import ProbeStats, ShotVerdict
from app.storyboard import Frame, Storyboard


def _board(n=3):
    board = Storyboard(meta={"title": "T"})
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


def _probes(phash):
    return [
        ProbeStats(t=t, mean_luma=0.4, variance=0.05, phash=phash)
        for t in (0.5, 2.5, 4.5)
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_shots_pass_on_first_attempt(tmp_path):
    from app.scene3d.backend import build_3d_frames

    hashes = iter(["0000000000000001", "00000000000000ff", "000000000000ff00"])
    with (
        patch(
            "app.scene3d.backend.author_world",
            new=AsyncMock(return_value="world"),
        ),
        patch(
            "app.scene3d.backend.author_shot",
            new=AsyncMock(return_value="cam.at(0,1,5);"),
        ),
        patch(
            "app.scene3d.backend.verify_shot",
            new=AsyncMock(
                side_effect=lambda *a, **k: (
                    ShotVerdict(True),
                    _probes(next(hashes)),
                    [],
                )
            ),
        ),
    ):
        failed = await build_3d_frames(_board(), tmp_path)
    assert failed == []


# ---------------------------------------------------------------------------
# Retry on rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_rejected_shot_is_retried_with_the_reason(tmp_path):
    from app.scene3d.backend import build_3d_frames

    verdicts = [
        (ShotVerdict(False, "black frame at t=0.5"), [], []),
        (ShotVerdict(True), _probes("0000000000000001"), []),
        (ShotVerdict(True), _probes("00000000000000ff"), []),
        (ShotVerdict(True), _probes("000000000000ff00"), []),
    ]
    shot = AsyncMock(return_value="cam.at(0,1,5);")
    with (
        patch(
            "app.scene3d.backend.author_world",
            new=AsyncMock(return_value="world"),
        ),
        patch("app.scene3d.backend.author_shot", new=shot),
        patch(
            "app.scene3d.backend.verify_shot",
            new=AsyncMock(side_effect=verdicts),
        ),
    ):
        failed = await build_3d_frames(_board(), tmp_path)
    assert failed == []
    assert (
        shot.await_args_list[1].kwargs["last_error"] == "black frame at t=0.5"
    )


# ---------------------------------------------------------------------------
# Exhausted retries — report, never substitute
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_shot_failing_every_attempt_is_reported_not_substituted(tmp_path):
    from app.scene3d.backend import build_3d_frames

    with (
        patch(
            "app.scene3d.backend.author_world",
            new=AsyncMock(return_value="world"),
        ),
        patch(
            "app.scene3d.backend.author_shot",
            new=AsyncMock(return_value="cam.at(0,1,5);"),
        ),
        patch(
            "app.scene3d.backend.verify_shot",
            new=AsyncMock(
                return_value=(ShotVerdict(False, "uniform fill"), [], [])
            ),
        ),
    ):
        failed = await build_3d_frames(_board(1), tmp_path)
    assert failed == ["f01-s1"]
    # Nothing was written in place of the failed shot.
    assert not list((tmp_path / "compositions" / "frames").glob("*.html"))


# ---------------------------------------------------------------------------
# Repeated camera angle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_repeated_camera_angle_is_rejected(tmp_path):
    """Same failure shape as the 2D archetype-repeat bug, in 3D."""
    from app.scene3d.backend import build_3d_frames

    same = "0f0f0f0f0f0f0f0f"
    with (
        patch(
            "app.scene3d.backend.author_world",
            new=AsyncMock(return_value="world"),
        ),
        patch(
            "app.scene3d.backend.author_shot",
            new=AsyncMock(return_value="cam.at(0,1,5);"),
        ),
        patch(
            "app.scene3d.backend.verify_shot",
            new=AsyncMock(
                return_value=(ShotVerdict(True), _probes(same), [])
            ),
        ),
    ):
        failed = await build_3d_frames(_board(2), tmp_path)
    assert "f02-s2" in failed


# ---------------------------------------------------------------------------
# World failure is fatal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_world_authoring_failure_raises(tmp_path):
    """No world means no film. Never proceed with an invented one."""
    from app.scene3d.author import SceneAuthoringError
    from app.scene3d.backend import build_3d_frames

    with patch(
        "app.scene3d.backend.author_world",
        new=AsyncMock(side_effect=SceneAuthoringError("model returned no code")),
    ):
        with pytest.raises(SceneAuthoringError):
            await build_3d_frames(_board(), tmp_path)


# ---------------------------------------------------------------------------
# Image-led cinematic shorts
# ---------------------------------------------------------------------------


def test_cinematic_frame_is_a_seekable_hyperframes_subcomposition():
    """Image-led scenes retain the exact composition contract of every render."""
    from app.scene3d.backend import render_cinematic_frame

    html = render_cinematic_frame("f01-hook", 4.5, "assets/cinematic/f01-hook.png")

    assert "<template>" in html
    assert 'data-composition-id="f01-hook"' in html
    assert 'window.__timelines["f01-hook"]' in html
    assert 'gsap.timeline({ paused: true })' in html
    assert "assets/cinematic/f01-hook.png" in html


def test_cinematic_prompt_has_safe_stock_and_investing_visual_language():
    from app.scene3d.backend import cinematic_image_prompt

    prompt = cinematic_image_prompt(_board(1), _board(1).frames[0])

    assert "candlestick-shaped city" in prompt
    assert "diversified garden" in prompt
    assert "Never depict a \"winning\" trade" in prompt


def test_comfyui_default_workflow_is_sized_for_the_local_provider(monkeypatch):
    from app.scene3d.backend import _comfyui_workflow

    monkeypatch.setenv("COMFYUI_CHECKPOINT_NAME", "sdxl-test.safetensors")
    monkeypatch.delenv("COMFYUI_WORKFLOW_PATH", raising=False)
    workflow = _comfyui_workflow("A miniature market garden")

    assert workflow["1"]["inputs"]["ckpt_name"] == "sdxl-test.safetensors"
    assert workflow["2"]["inputs"]["text"] == "A miniature market garden"
    assert workflow["4"]["inputs"]["width"] == 768
    assert workflow["4"]["inputs"]["height"] == 1152


def test_comfyui_provider_requires_a_server_and_workflow(monkeypatch):
    from app.scene3d.backend import require_cinematic_image_provider

    monkeypatch.delenv("COMFYUI_BASE_URL", raising=False)
    monkeypatch.delenv("COMFYUI_CHECKPOINT_NAME", raising=False)
    monkeypatch.delenv("COMFYUI_WORKFLOW_PATH", raising=False)

    with pytest.raises(RuntimeError, match="ComfyUI is not ready"):
        require_cinematic_image_provider("comfyui")


def test_gemini_provider_requires_an_api_key(monkeypatch):
    from app.scene3d.backend import require_cinematic_image_provider

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        require_cinematic_image_provider("gemini")


def test_unknown_image_provider_is_rejected():
    from app.scene3d.backend import require_cinematic_image_provider

    with pytest.raises(ValueError, match="unknown cinematic image provider"):
        require_cinematic_image_provider("openai")


@pytest.mark.asyncio
async def test_gemini_image_saves_returned_bytes(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.scene3d import backend

    part = SimpleNamespace(inline_data=SimpleNamespace(mime_type="image/png", data=b"png"))
    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])

    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["model"] == backend.GEMINI_IMAGE_MODEL
            assert kwargs["contents"] == ["a prompt"]
            return response

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "k"
        models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: FakeClient(**kwargs))

    destination = tmp_path / "frame.png"
    await backend._generate_gemini_cinematic_image("a prompt", destination)
    assert destination.read_bytes() == b"png"


@pytest.mark.asyncio
async def test_gemini_image_with_no_image_part_raises(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.scene3d import backend

    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))])

    class FakeClient:
        models = SimpleNamespace(generate_content=lambda **kwargs: response)

        def __init__(self, **kwargs):
            pass

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: FakeClient(**kwargs))

    with pytest.raises(RuntimeError, match="no image data"):
        await backend._generate_gemini_cinematic_image("a prompt", tmp_path / "frame.png")


@pytest.mark.asyncio
async def test_cinematic_backend_writes_one_image_and_composition_per_scene(tmp_path):
    from app.scene3d.backend import build_cinematic_frames

    async def make_image(_prompt, destination, _provider):
        destination.write_bytes(b"png")

    with (
        patch("app.scene3d.backend.require_cinematic_image_provider", return_value="gemini"),
        patch(
            "app.scene3d.backend._generate_cinematic_image",
            new=AsyncMock(side_effect=make_image),
        ) as generate,
    ):
        failed = await build_cinematic_frames(_board(3), tmp_path)

    assert failed == []
    assert generate.await_count == 3
    assert (tmp_path / "assets" / "cinematic" / "f01-s1.png").exists()
    assert (tmp_path / "compositions" / "frames" / "f03-s3.html").exists()


@pytest.mark.asyncio
async def test_gemini_helper_decodes_base64_string_data():
    from types import SimpleNamespace

    from app.scene3d.backend import extract_gemini_image_bytes
    import base64

    part = SimpleNamespace(
        inline_data=SimpleNamespace(mime_type="image/png", data=base64.b64encode(b"png").decode())
    )
    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])
    assert extract_gemini_image_bytes(response) == b"png"


def test_gemini_helper_skips_non_image_parts():
    from types import SimpleNamespace

    from app.scene3d.backend import extract_gemini_image_bytes

    text = SimpleNamespace(text="hello")
    img = SimpleNamespace(inline_data=SimpleNamespace(mime_type="image/jpeg", data=b"jpg"))
    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[text, img]))])
    assert extract_gemini_image_bytes(response) == b"jpg"


def test_gemini_helper_raises_with_no_image_part():
    from types import SimpleNamespace

    import pytest

    from app.scene3d.backend import extract_gemini_image_bytes

    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))])
    with pytest.raises(RuntimeError, match="no image data"):
        extract_gemini_image_bytes(response)
