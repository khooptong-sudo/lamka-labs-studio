"""Ken Burns zoompan clips: filter geometry, command shape, assembly dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scene3d import kenburns
from app.storyboard import Frame, Storyboard


def _frame(i: int, duration: float = 5.0) -> Frame:
    frame = Frame(index=i, title=f"Scene {i}", voiceover=f"line {i}", scene=f"scene {i}", duration=duration)
    frame.start = (i - 1) * duration
    frame.voice_offset = 0.25
    return frame


def _board(n: int = 3):
    board = Storyboard(meta={"title": "T"})
    board.direction = ""
    board.frames = [_frame(i) for i in range(1, n + 1)]
    return board


# --- filter geometry ---------------------------------------------------------


def test_filter_reproduces_gsap_endpoints():
    # motion_index 1 -> CAMERA_PATHS[0] = (-18, -14, 1.115); boost 0, ease default.
    chain = kenburns.build_kenburns_filter(5.0, 1, "power1.inOut", 0.0)
    assert "zoompan" in chain
    assert "d=150" in chain  # 5s * 30fps
    assert "s=1080x1920" in chain
    assert "fps=30" in chain
    # z starts exactly at 1 (first output frame: on=0) and ends near scale/1.025.
    assert "z='1+0.087805*" in chain
    # Pan is doubled into canvas px and tracks the zooming window; the window
    # moves opposite the GSAP content shift.
    assert "/2+(36.000*" in chain  # pan_x -18 -> window +18 * CANVAS_SCALE 2
    assert "/2+(28.000*" in chain  # pan_y -14 -> window +14 * CANVAS_SCALE 2
    # 2x canvas, cover scale, then the 1.025 margin pre-crop.
    assert "scale=2160:3840:force_original_aspect_ratio=increase" in chain
    assert "crop=2107:3746" in chain


def test_filter_camera_path_wraps_and_boost_shrinks_end_zoom():
    chain = kenburns.build_kenburns_filter(4.0, 9, "sine.inOut", -0.01)
    # index 9 wraps to CAMERA_PATHS[0]; boost lowers the end scale below 1.115/1.025.
    assert "z='1+0.078049*" in chain
    assert "d=120" in chain


def test_ease_variants():
    cos_chain = kenburns.build_kenburns_filter(2.0, 1, "power1.inOut", 0.0)
    assert "cos(PI*on/60)" in cos_chain
    cubic_chain = kenburns.build_kenburns_filter(2.0, 1, "power3.out", 0.0)
    assert "pow" not in cubic_chain  # no comma-bearing functions inside the filter string
    assert "(1-on/60)*(1-on/60)*(1-on/60)" in cubic_chain


def test_short_durations_still_render_one_frame():
    chain = kenburns.build_kenburns_filter(0.01, 1, "power1.inOut", 0.0)
    assert "d=1" in chain


def test_command_shape(tmp_path):
    command = kenburns.build_kenburns_command(
        tmp_path / "in.png", tmp_path / "out.mp4", 5.0, 1, "power1.inOut", 0.0
    )
    assert command[0] == "ffmpeg"
    assert "-frames:v" in command
    assert command[command.index("-frames:v") + 1] == "150"
    assert command[-1].endswith("out.mp4")


# --- clip rendering ----------------------------------------------------------


@pytest.mark.asyncio
async def test_render_clips_missing_png_raises(tmp_path):
    board = _board(2)
    with pytest.raises(FileNotFoundError, match="ken burns keyframe missing"):
        await kenburns.render_kenburns_clips(board, tmp_path, "power1.inOut", 0.0)


@pytest.mark.asyncio
async def test_render_clips_reuses_existing_and_skips_finished(tmp_path):
    from unittest.mock import MagicMock

    board = _board(2)
    assets = tmp_path / "assets" / "cinematic"
    assets.mkdir(parents=True)
    (assets / f"{board.frames[0].slug}.png").write_bytes(b"x")
    (assets / f"{board.frames[1].slug}.png").write_bytes(b"x")
    (assets / f"{board.frames[0].slug}.mp4").write_bytes(b"x")  # already rendered

    with patch.object(kenburns.subprocess, "run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        await kenburns.render_kenburns_clips(board, tmp_path, "power1.inOut", 0.0)

    assert run.call_count == 1  # only the scene without an mp4 rendered
    command = run.call_args.args[0]
    assert board.frames[1].slug in command[-1]


# --- full assembly -----------------------------------------------------------


@pytest.mark.asyncio
async def test_assemble_kenburns_renders_clips_then_motion_assembly(tmp_path):
    from app.scene3d import assemble

    board = _board(2)
    assets = tmp_path / "assets" / "cinematic"
    assets.mkdir(parents=True)
    for frame in board.frames:
        (assets / f"{frame.slug}.png").write_bytes(b"x")
        voice = tmp_path / frame.voice_filename
        voice.parent.mkdir(parents=True, exist_ok=True)
        voice.write_bytes(b"x")

    def fake_render(png_path, destination, duration, motion_index, ease, boost):
        destination.write_bytes(b"x")

    with (
        patch.object(kenburns, "render_kenburns_clip", side_effect=fake_render),
        patch.object(assemble.subprocess, "run") as assemble_run,
    ):
        assemble_run.return_value = MagicMock(returncode=0, stderr="")
        output = await kenburns.assemble_kenburns_video(board, tmp_path, with_bgm=False)

    assert output == tmp_path / "renders" / "video.mp4"
    assert (assets / f"{board.frames[0].slug}.mp4").exists()
    assert (assets / f"{board.frames[1].slug}.mp4").exists()
    assemble_run.assert_called_once()
    assert (tmp_path / assemble.OVERLAY_RELATIVE).exists()


@pytest.mark.asyncio
async def test_assemble_kenburns_raises_with_ffmpeg_tail(tmp_path):
    board = _board(1)
    assets = tmp_path / "assets" / "cinematic"
    assets.mkdir(parents=True)
    (assets / f"{board.frames[0].slug}.png").write_bytes(b"x")

    with patch.object(kenburns.subprocess, "run") as run:
        run.return_value = MagicMock(returncode=1, stderr="zoompan exploded")
        with pytest.raises(RuntimeError, match="ffmpeg ken burns clip failed"):
            await kenburns.assemble_kenburns_video(board, tmp_path, with_bgm=False)
