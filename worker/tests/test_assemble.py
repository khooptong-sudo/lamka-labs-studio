"""ffmpeg-direct assembly for motion builds: concat, look overlay, narration mux."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels import Channel
from app.storyboard import Frame, Storyboard

FINANCE = Channel(
    id="finance",
    display_name="Finance",
    voice_key="adult_male",
    script_prompt="A prompt.",
    extra_blocklist=(),
)

GOOD_SCRIPT = (
    "---\ntitle: Real Title\ndescription: A real SEO description.\npreset: adult_male\n---\n\n"
    "# Scene 1 — The hook\nVoiceover: \"City budgets hide one line that explains every pothole.\"\nScene: A street cracking.\n\n"
    "# Scene 2 — The mechanism\nVoiceover: \"The maintenance fund is raided each spring for festivals.\"\nScene: Coins moved between jars.\n\n"
    "# Scene 3 — Why it matters\nVoiceover: \"That is why your street floods while the parade gets louder.\"\nScene: Flood beside a parade.\n\n"
    "# Scene 4 — The takeaway\nVoiceover: \"Read the maintenance line first and budgets finally make sense.\"\nScene: A magnifier on one line.\n"
)


def _board(n=3):
    board = Storyboard(meta={"title": "T"})
    board.frames = []
    for i in range(1, n + 1):
        frame = Frame(
            index=i,
            title=f"Scene {i}",
            voiceover=f"line {i}",
            scene=f"scene {i}",
            duration=5.0,
        )
        frame.start = (i - 1) * 5.0
        frame.voice_offset = 0.25
        board.frames.append(frame)
    return board


def _stage_files(video_dir, board, with_bgm=False, missing_voice=None, missing_clip=None):
    for frame in board.frames:
        clip = video_dir / "assets" / "cinematic" / f"{frame.slug}.mp4"
        if missing_clip != frame.index:
            clip.parent.mkdir(parents=True, exist_ok=True)
            clip.write_bytes(b"x")
        voice = video_dir / frame.voice_filename
        if missing_voice != frame.index:
            voice.parent.mkdir(parents=True, exist_ok=True)
            voice.write_bytes(b"x")
    if with_bgm:
        (video_dir / "bgm.mp3").write_bytes(b"x")


def _command_parts(command):
    inputs = [command[i + 1] for i, flag in enumerate(command) if flag == "-i"]
    graph = command[command.index("-filter_complex") + 1]
    return inputs, graph


def test_command_concat_order_and_voice_delays(tmp_path):
    from app.scene3d.assemble import build_ffmpeg_command

    board = _board(3)
    _stage_files(tmp_path, board)
    command = build_ffmpeg_command(board, tmp_path, with_bgm=False, overlay_path=tmp_path / "overlay.png")

    inputs, graph = _command_parts(command)
    slugs = [f.name for f in tmp_path.rglob("*.mp4") if "cinematic" in str(f)]
    assert len(inputs) == 7  # 3 clips + overlay + 3 voices
    assert inputs[0].endswith(f"{board.frames[0].slug}.mp4")
    assert inputs[1].endswith(f"{board.frames[1].slug}.mp4")
    assert inputs[2].endswith(f"{board.frames[2].slug}.mp4")
    assert inputs[3].endswith("overlay.png")
    assert inputs[4].endswith("01.mp3")
    assert inputs[5].endswith("02.mp3")
    assert inputs[6].endswith("03.mp3")
    assert "concat=n=3:v=1:a=0" in graph
    assert "overlay=0:0" in graph
    # Audio offsets mirror render_index_html: frame.start + frame.voice_offset.
    assert "adelay=250:all=1" in graph  # frame 1: 0 + 0.25s
    assert "adelay=5250:all=1" in graph  # frame 2: 5 + 0.25s
    assert "adelay=10250:all=1" in graph  # frame 3: 10 + 0.25s
    assert "amix=inputs=3:normalize=0" in graph
    assert "volume=" not in graph  # no bgm chain without bgm
    assert "[vo]anull[aout]" in graph
    assert slugs  # staged clips were found
    assert command[command.index("-c:a") + 1] == "aac"
    assert command[command.index("-b:a") + 1] == "192k"
    assert command[-1].replace("\\", "/").endswith("renders/video.mp4")


def test_command_bgm_chain_when_present(tmp_path):
    from app.scene3d.assemble import build_ffmpeg_command

    board = _board(2)
    _stage_files(tmp_path, board, with_bgm=True)
    command = build_ffmpeg_command(board, tmp_path, with_bgm=True, overlay_path=tmp_path / "overlay.png")

    inputs, graph = _command_parts(command)
    assert inputs[-1].endswith("bgm.mp3")
    assert command[command.index("-stream_loop") + 1] == "-1"
    assert "atrim=0:10.000" in graph
    assert "volume=0.35" in graph
    assert "amix=inputs=2:normalize=0" in graph


def test_missing_voice_file_raises(tmp_path):
    from app.scene3d.assemble import build_ffmpeg_command

    board = _board(2)
    _stage_files(tmp_path, board, missing_voice=2)
    with pytest.raises(FileNotFoundError, match="narration missing"):
        build_ffmpeg_command(board, tmp_path, with_bgm=False, overlay_path=tmp_path / "o.png")


def test_missing_clip_file_raises(tmp_path):
    from app.scene3d.assemble import build_ffmpeg_command

    board = _board(2)
    _stage_files(tmp_path, board, missing_clip=1)
    with pytest.raises(FileNotFoundError, match="motion clip missing"):
        build_ffmpeg_command(board, tmp_path, with_bgm=False, overlay_path=tmp_path / "o.png")


def test_bake_overlay_png(tmp_path):
    from app.scene3d.assemble import HEIGHT, WIDTH, bake_overlay_png

    destination = tmp_path / "overlay.png"
    bake_overlay_png(destination)
    assert destination.exists()

    from PIL import Image

    with Image.open(destination) as image:
        assert image.size == (WIDTH, HEIGHT)
        assert image.mode == "RGBA"
        alpha = image.getchannel("A")
        lo, hi = alpha.getextrema()
        assert lo == 0  # fully transparent somewhere (canvas corners)
        assert hi > 0  # glow/vignette paint somewhere


@pytest.mark.asyncio
async def test_assemble_invokes_ffmpeg_and_returns_output(tmp_path):
    from app.scene3d import assemble

    board = _board(2)
    _stage_files(tmp_path, board, with_bgm=True)
    with patch.object(assemble.subprocess, "run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        output = await assemble.assemble_motion_video(board, tmp_path, with_bgm=True)

    assert output == tmp_path / "renders" / "video.mp4"
    run.assert_called_once()
    command = run.call_args.args[0]
    assert command[0] == "ffmpeg"
    assert (tmp_path / assemble.OVERLAY_RELATIVE).exists()


@pytest.mark.asyncio
async def test_assemble_raises_with_stderr_tail(tmp_path):
    from app.scene3d import assemble

    board = _board(2)
    _stage_files(tmp_path, board)
    with patch.object(assemble.subprocess, "run") as run:
        run.return_value = MagicMock(returncode=1, stderr="some ffmpeg error tail")
        with pytest.raises(RuntimeError, match="ffmpeg motion assembly failed"):
            await assemble.assemble_motion_video(board, tmp_path, with_bgm=False)


# ---------------------------------------------------------------------------
# End-to-end dispatch: motion builds skip HyperFrames, off builds keep it
# ---------------------------------------------------------------------------


def _arrange(mocks):
    mock_run, mock_frames, mock_audio, mock_script, mock_record, mock_fetch = mocks
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.return_value = GOOD_SCRIPT
    mock_record.return_value = uuid.uuid4()
    mock_run.return_value = MagicMock(stdout="mocked")
    mock_audio.return_value = []
    mock_frames.return_value = []


_DISPATCH_PATCHES = (
    patch("app.youtube._fetch_story_details"),
    patch("app.youtube._record_youtube_draft"),
    patch("app.youtube._generate_script_for_story"),
    patch("app.youtube._generate_frame_audio"),
    patch("app.youtube._build_frames"),
    patch("app.youtube.subprocess.run"),
    patch("app.youtube.build_thumbnail_variants", new=AsyncMock(return_value={})),
    patch("app.youtube.fact_check_script", AsyncMock(return_value={"verdict": "PASS", "violations": []})),
    patch("app.youtube._research_packet", return_value="packet"),
)


@pytest.mark.asyncio
async def test_motion_build_assembles_with_ffmpeg_not_hyperframes(tmp_path):
    from app import youtube

    mocks = [p.start() for p in _DISPATCH_PATCHES]
    try:
        mock_fetch, mock_record, mock_script, mock_audio, mock_frames, mock_run = mocks[:6]
        _arrange((mock_run, mock_frames, mock_audio, mock_script, mock_record, mock_fetch))

        assemble = AsyncMock(return_value=tmp_path / "renders" / "video.mp4")
        with (
            patch("app.youtube.VIDEOS_DIR", tmp_path),
            patch("app.channels.resolve", AsyncMock(return_value=FINANCE)),
            patch("app.scene3d.assemble.assemble_motion_video", assemble),
        ):
            draft_id = await youtube.generate_youtube_video(
                story_id=uuid.uuid4(),
                channel_id="finance",
                upload_preference="manual",
                backend="cinematic",
                motion="veo",
            )

        assert draft_id is not None
        assemble.assert_awaited_once()
        assert assemble.await_args.args[1].name.startswith("story-")
        assert assemble.await_args.kwargs["with_bgm"] is False
        for call in mock_run.call_args_list:
            argv = call.args[0] if call.args else []
            assert not any("hyperframes" in str(part) for part in argv)
    finally:
        for p in reversed(_DISPATCH_PATCHES):
            p.stop()


@pytest.mark.asyncio
async def test_off_build_keeps_hyperframes_path(tmp_path):
    from app import youtube

    mocks = [p.start() for p in _DISPATCH_PATCHES]
    try:
        mock_fetch, mock_record, mock_script, mock_audio, mock_frames, mock_run = mocks[:6]
        _arrange((mock_run, mock_frames, mock_audio, mock_script, mock_record, mock_fetch))

        assemble = AsyncMock()
        with (
            patch("app.youtube.VIDEOS_DIR", tmp_path),
            patch("app.channels.resolve", AsyncMock(return_value=FINANCE)),
            patch("app.scene3d.assemble.assemble_motion_video", assemble),
        ):
            draft_id = await youtube.generate_youtube_video(
                story_id=uuid.uuid4(),
                channel_id="finance",
                upload_preference="manual",
                backend="cinematic",
                motion=None,
            )

        assert draft_id is not None
        assemble.assert_not_awaited()
        hyperframes_calls = [
            call for call in mock_run.call_args_list
            if call.args and any("hyperframes" in str(part) for part in call.args[0])
        ]
        assert len(hyperframes_calls) == 1
    finally:
        for p in reversed(_DISPATCH_PATCHES):
            p.stop()
