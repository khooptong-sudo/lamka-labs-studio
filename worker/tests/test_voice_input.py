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


OVERRIDE_3 = (
    "---\ntitle: T\ndescription: D\npreset: adult_male\n---\n\n"
    "# Scene 1\nVoiceover: A\n\n# Scene 2\nVoiceover: B\n\n# Scene 3\nVoiceover: C\n"
)

FINANCE_VOICE = Channel(
    id="financial-channel", display_name="Finance", voice_key="adult_male",
    script_prompt="A prompt.", extra_blocklist=(),
)


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


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE_VOICE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_frame_audio", AsyncMock(side_effect=AssertionError("TTS must not run")))
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube.build_thumbnail_variants", AsyncMock(return_value={}))
async def test_voice_count_mismatch_aborts_before_audio(
    mock_run, mock_frames, mock_record, mock_fetch, tmp_path
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
    mock_probe, mock_run, mock_frames, mock_record, mock_fetch, tmp_path
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
    mock_probe, mock_run, mock_frames, mock_record, mock_fetch, tmp_path
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
    mock_record.assert_called_once()
