import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.channels import Channel
from app.youtube import (
    _apply_cinematic_controls,
    _append_research_sources,
    _ensure_storyboard_metadata,
    generate_youtube_video,
    _get_youtube_credentials,
    _parse_storyboard_frontmatter,
    _research_packet,
)

FINANCE = Channel(
    id="financial-channel",
    display_name="Finance",
    voice_key="adult_male",
    script_prompt="You are a casual, humorous, informative adult male.",
    extra_blocklist=(),
)

# Long enough to clear MIN_SCRIPT_FRAMES. Tests that assert on ratios need a
# script the length guard accepts, otherwise they abort before reaching the
# behaviour under test.
SCRIPT_4_SCENES = (
    "---\ntitle: Test\ndescription: A test description.\npreset: daisy-days\n---\n\n"
    "# Scene 1\nVoiceover: A\n\n"
    "# Scene 2\nVoiceover: B\n\n"
    "# Scene 3\nVoiceover: C\n\n"
    "# Scene 4\nVoiceover: D\n"
)


def test_cinematic_controls_become_part_of_the_continuity_bible():
    storyboard = (
        "---\ntitle: Test\ndescription: A test description.\n---\n\n"
        "# Video direction\nA miniature world with one recurring guide.\n\n"
        "# Scene 1\nVoiceover: Hello\nScene: The guide enters.\n"
    )

    controlled = _apply_cinematic_controls(
        storyboard,
        {
            "shot_scale": "medium close-up",
            "camera_angle": "low angle",
            "camera_movement": "slow push in",
            "lens": "50mm natural perspective",
            "lighting": "soft window light",
            "color_treatment": "cool shadows, warm skin tones",
            "pacing": "measured",
            "motion_intent": "subject-led parallax",
        },
    )

    assert "## Cinematography controls" in controlled
    assert "Camera movement: slow push in" in controlled
    assert "Lens language: 50mm natural perspective" in controlled
    assert controlled.index("## Cinematography controls") < controlled.index("# Scene 1")


def test_absent_cinematic_controls_leave_storyboard_unchanged():
    assert _apply_cinematic_controls(SCRIPT_4_SCENES, None) == SCRIPT_4_SCENES


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube._generate_thumbnail")
async def test_generate_youtube_video_manual(
    mock_thumb, mock_run, mock_frames, mock_audio, mock_script, mock_record, mock_fetch, tmp_path
):
    story_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.return_value = SCRIPT_4_SCENES
    mock_record.return_value = uuid.uuid4()
    mock_run.return_value = MagicMock(stdout="Mocked hyperframes output")
    mock_audio.return_value = []
    mock_frames.return_value = []

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=story_id,
            channel_id="financial-channel",
            upload_preference="manual",
        )

    assert draft_id is not None
    video_dir = tmp_path / f"story-{story_id}"
    assert video_dir.exists()

    mock_record.assert_called_once()
    _, kwargs_rec = mock_record.call_args
    assert kwargs_rec["upload_preference"] == "manual"
    assert kwargs_rec["status"] == "pending"
    assert kwargs_rec["external_id"] is None


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube._generate_thumbnail")
async def test_generate_youtube_video_auto_preference_is_still_pending(
    mock_thumb, mock_run, mock_frames, mock_audio, mock_script, mock_record, mock_fetch, tmp_path
):
    """`upload_preference` no longer selects a publish behaviour.

    It used to write status="published" here, with no video id, for a video
    nobody had uploaded. See tests/test_generation_resilience.py.
    """
    story_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.return_value = SCRIPT_4_SCENES
    mock_record.return_value = uuid.uuid4()
    mock_run.return_value = MagicMock(stdout="Mocked hyperframes output")
    mock_audio.return_value = []
    mock_frames.return_value = []

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        await generate_youtube_video(
            story_id=story_id,
            channel_id="financial-channel",
            upload_preference="auto",
        )

    _, kwargs_rec = mock_record.call_args
    assert kwargs_rec["status"] == "pending"


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube._generate_frame_audio")
# Patch the dispatcher, not a backend: the guard under test is about the
# placeholder ratio, which is the same whichever backend produced the frames.
# Patching a backend directly lets FRAME_BACKEND silently route around the mock
# and fire a live request at whatever the local one talks to.
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
async def test_generation_aborts_when_most_frames_are_placeholders(
    mock_run, mock_frames, mock_audio, mock_script, mock_record, mock_fetch, tmp_path
):
    """Placeholder cards render and pass validation, so nothing downstream would
    notice the video is mostly fallback. It must never reach YouTube."""
    story_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.return_value = SCRIPT_4_SCENES
    mock_record.return_value = uuid.uuid4()
    mock_run.return_value = MagicMock(stdout="Mocked hyperframes output")
    mock_audio.return_value = []
    # Half the frames fell back, e.g. the LLM was rate limited.
    mock_frames.return_value = ["f01-frame", "f02-frame"]

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=story_id,
            channel_id="financial-channel",
            upload_preference="auto",
        )

    assert draft_id is None
    mock_record.assert_not_called()


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
async def test_generation_aborts_when_most_frames_are_silent(
    mock_run, mock_frames, mock_audio, mock_script, mock_record, mock_fetch, tmp_path
):
    """Silence renders and validates exactly like narration, so a mute explainer
    passes every downstream check. It must never reach YouTube."""
    story_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.return_value = SCRIPT_4_SCENES
    mock_record.return_value = uuid.uuid4()
    mock_run.return_value = MagicMock(stdout="Mocked hyperframes output")
    mock_frames.return_value = []
    # Half the lines failed TTS, e.g. the account hit its concurrency limit.
    mock_audio.return_value = ["f01-frame", "f02-frame"]

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=story_id,
            channel_id="financial-channel",
            upload_preference="auto",
        )

    assert draft_id is None
    mock_record.assert_not_called()
    # Aborted before wasting a render on a mute video.
    mock_frames.assert_not_called()


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
async def test_generation_aborts_when_script_generation_fails(
    mock_frames, mock_audio, mock_script, mock_record, mock_fetch, tmp_path
):
    """A failed script must not become a video. This was observed live: Gemini
    returned 503, the caller substituted a one-scene stub, and the pipeline
    reported success on a five second draft."""
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.side_effect = RuntimeError("503 UNAVAILABLE")

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=uuid.uuid4(),
            channel_id="financial-channel",
            upload_preference="auto",
        )

    assert draft_id is None
    mock_record.assert_not_called()
    mock_audio.assert_not_called()
    mock_frames.assert_not_called()


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
async def test_generation_aborts_when_script_is_too_short(
    mock_frames, mock_audio, mock_script, mock_record, mock_fetch, tmp_path
):
    """The placeholder and silence guards are ratios, so a one-frame script
    scores perfectly on both. Length has to be checked on its own."""
    mock_fetch.return_value = {"headline": "Test Story"}
    mock_script.return_value = "---\ntitle: Test\ndescription: A test description.\n---\n\n# Scene 1\nVoiceover: Hello\n"

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=uuid.uuid4(),
            channel_id="financial-channel",
            upload_preference="auto",
        )

    assert draft_id is None
    mock_record.assert_not_called()
    mock_audio.assert_not_called()
    mock_frames.assert_not_called()


def test_parse_storyboard_frontmatter():
    tmp = Path("/tmp/storyboard_test.md")
    # We can't write to /tmp on Windows; use a temp fixture instead.
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("---\ntitle: Hello\ndescription: World\npreset: adult_male\n---\n\n# Scene 1\n")
        path = Path(f.name)
    try:
        fm = _parse_storyboard_frontmatter(path)
        assert fm["title"] == "Hello"
        assert fm["description"] == "World"
    finally:
        path.unlink(missing_ok=True)


def test_human_outline_gets_upload_metadata_and_scene_heading() -> None:
    from app.storyboard import parse_storyboard

    outline = """Title: Peekaboo Farm! Who's Hiding?

Target Audience: Toddlers (Ages 1-3)
Vibe: Bright, colorful, enthusiastic, and bouncy.

Scene 1: The Red Barn
Visual: A bright red barn door is closed on screen.
Voiceover: Let's play Peekaboo Farm! Who's hiding in the barn?
"""

    normalized = _ensure_storyboard_metadata(outline, fallback_title="Manual storyboard")

    assert 'title: "Peekaboo Farm! Who\'s Hiding?"' in normalized
    assert 'description: "A 3D animated short based on Peekaboo Farm! Who\'s Hiding?' in normalized
    board = parse_storyboard(normalized)
    assert len(board.frames) == 1
    assert board.frames[0].title == "The Red Barn"
    assert board.frames[0].voiceover == "Let's play Peekaboo Farm! Who's hiding in the barn?"


def test_timestamped_human_outline_becomes_renderable_scenes() -> None:
    from app.storyboard import parse_storyboard

    outline = """Title: Sharing Makes Playtime Fun!
Style: Bright, colorful toddler animation

0–5 sec
Visual: A cheerful bunny plays with two colorful toy cars while a bear watches nearby.
Narrator: Bunny has two fun cars! Vroom, vroom!

5–10 sec
Visual: Bear points gently at one car and smiles.
Bear: Can I play too?
Narrator: Bear would like a turn!

10–16 sec
Visual: Bunny happily gives the blue car to Bear.
Bunny: Here you go!
Narrator: Bunny shares! Yay!
"""

    normalized = _ensure_storyboard_metadata(outline, fallback_title="Manual storyboard")
    board = parse_storyboard(normalized)

    assert len(board.frames) == 3
    assert board.frames[0].declared_duration == 5
    assert board.frames[1].declared_duration == 5
    assert board.frames[2].declared_duration == 6
    assert board.frames[1].voiceover == "Bear says, Can I play too? Bear would like a turn!"
    assert board.frames[2].scene == "Bunny happily gives the blue car to Bear."


def test_get_youtube_credentials_missing_token(tmp_path):
    from app.settings import get_settings

    with patch.object(get_settings(), "youtube_token_path", tmp_path / "missing.json"):
        with pytest.raises(RuntimeError):
            _get_youtube_credentials(["https://www.googleapis.com/auth/youtube.upload"])


def test_research_packet_keeps_linked_article_evidence_and_bounds_the_excerpt():
    story = {
        "headline": "Regulator update",
        "items": [
            {
                "title": "Official update",
                "url": "https://regulator.example/release",
                "source_name": "Official regulator",
                "published_at": "2026-08-09T00:00:00Z",
                "full_text": "evidence " * 1_000,
            }
        ],
    }

    packet = _research_packet(story)

    assert "Official regulator" in packet
    assert "https://regulator.example/release" in packet
    assert len(packet) < 5_000


def test_research_packet_refuses_headline_only_finance_scripts():
    with pytest.raises(RuntimeError, match="no linked research sources"):
        _research_packet({"headline": "Unsourced idea"})


def test_generated_storyboard_keeps_an_auditable_source_appendix():
    board = _append_research_sources(
        SCRIPT_4_SCENES,
        {
            "items": [
                {
                    "title": "Official update",
                    "url": "https://regulator.example/release",
                    "source_name": "Official regulator",
                }
            ]
        },
    )

    assert "# Research sources" in board
    assert "Official regulator" in board


# ---------------------------------------------------------------------------
# Per-request backend dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_frames_routes_to_three(tmp_path):
    """Per-request backend beats the env default, so both formats run from one worker."""
    from app.storyboard import Storyboard
    from app import youtube

    with patch(
        "app.youtube.build_3d_frames", new=AsyncMock(return_value=[])
    ) as three:
        await youtube._build_frames(Storyboard(), tmp_path, backend="three")
    three.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_frames_routes_to_cinematic_image_backend(tmp_path):
    """The premium portrait route must not ever fall back to the cheap 2D path."""
    from app.storyboard import Storyboard
    from app import youtube

    with patch(
        "app.youtube.build_cinematic_frames", new=AsyncMock(return_value=[])
    ) as cinematic:
        await youtube._build_frames(
            Storyboard(), tmp_path, backend="cinematic", image_provider="comfyui"
        )
    cinematic.assert_awaited_once_with(Storyboard(), tmp_path, provider="comfyui")


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
@patch("app.youtube._generate_thumbnail")
async def test_generation_uses_pasted_storyboard_without_regenerating_script(
    mock_thumb,
    mock_run,
    mock_frames,
    mock_audio,
    mock_script,
    mock_record,
    mock_fetch,
    tmp_path,
):
    story_id = uuid.uuid4()
    mock_fetch.return_value = {"headline": "Existing source story"}
    mock_record.return_value = uuid.uuid4()
    mock_run.return_value = MagicMock(stdout="Mocked hyperframes output")
    mock_audio.return_value = []
    mock_frames.return_value = []

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=story_id,
            channel_id="financial-channel",
            storyboard_override=SCRIPT_4_SCENES,
        )

    assert draft_id is not None
    mock_script.assert_not_called()
    assert (tmp_path / f"story-{story_id}" / "STORYBOARD.md").read_text(encoding="utf-8") == SCRIPT_4_SCENES


@pytest.mark.asyncio
@patch("app.channels.resolve", AsyncMock(return_value=FINANCE))
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._generate_frame_audio")
async def test_pasted_storyboard_cannot_bypass_channel_blocklist(
    mock_audio, mock_fetch, tmp_path
):
    mock_fetch.return_value = {"headline": "Existing source story"}
    unsafe = SCRIPT_4_SCENES.replace("Voiceover: A", "Voiceover: Buy this stock now")

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=uuid.uuid4(),
            channel_id="financial-channel",
            storyboard_override=unsafe,
        )

    assert draft_id is None
    mock_audio.assert_not_called()


@pytest.mark.asyncio
@patch("app.channels.resolve")
@patch("app.youtube._fetch_story_details")
@patch("app.youtube._record_youtube_draft")
@patch("app.youtube._generate_script_for_story")
@patch("app.youtube._generate_frame_audio")
@patch("app.youtube._build_frames")
@patch("app.youtube.subprocess.run")
async def test_generation_aborts_below_min_verified_frames(
    mock_run,
    mock_frames,
    mock_audio,
    mock_script,
    mock_record,
    mock_fetch,
    mock_channels,
    tmp_path,
):
    """An absolute floor. Ratios read a two-frame film with one good shot as 50% fine."""
    mock_fetch.return_value = {"id": "s1", "title": "T", "summary": "S"}
    mock_channels.return_value = FINANCE
    mock_script.return_value = (
        "---\ntitle: T\ndescription: A test film\nformat: 1920x1080\npacing: story\n---\n"
        "# Scene 1\nVoiceover: a\n# Scene 2\nVoiceover: b\n"
        "# Scene 3\nVoiceover: c\n# Scene 4\nVoiceover: d\n"
    )
    mock_audio.return_value = []
    # Two of four shots never passed the gate: only two verified remain.
    mock_frames.return_value = ["f01-frame", "f02-frame"]
    mock_run.return_value = MagicMock(returncode=0)

    with patch("app.youtube.VIDEOS_DIR", tmp_path):
        result = await generate_youtube_video(
            uuid.uuid4(), "ch1", backend="three"
        )

    assert result is None
    mock_record.assert_not_called()
