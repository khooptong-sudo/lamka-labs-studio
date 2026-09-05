"""New channels resolve and render on both backends. No DB, no network."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.channels import Channel
from scripts.seed_channels import BUILT_IN_CHANNELS, ensure_builtin_channels

CHANNEL_IDS = ["history", "science", "mystery"]

OVERRIDE_BOARD = (
    "---\ntitle: T\ndescription: D\npreset: adult_male\n---\n\n"
    "# Scene 1\nVoiceover: A\n\n# Scene 2\nVoiceover: B\n\n# Scene 3\nVoiceover: C\n"
)


def _config_row():
    base = {
        "finance": {"display_name": "Finance", "voice_key": "adult_male",
                    "script_prompt": "tuned", "extra_blocklist": []},
        "kids": {"display_name": "Kids", "voice_key": "baby",
                 "script_prompt": "tuned", "extra_blocklist": []},
    }
    return ensure_builtin_channels(base)


@pytest.mark.parametrize("channel_id", CHANNEL_IDS)
async def test_new_channel_resolves_with_its_voice_and_union_blocklist(channel_id):
    from app import channels

    with patch("app.db.get_config", AsyncMock(return_value=_config_row())):
        channel = await channels.resolve(channel_id)
    assert isinstance(channel, Channel)
    assert channel.voice_key == BUILT_IN_CHANNELS[channel_id]["voice_key"]
    assert channel.script_prompt == BUILT_IN_CHANNELS[channel_id]["script_prompt"]
    for term in BUILT_IN_CHANNELS[channel_id]["extra_blocklist"]:
        assert term in channel.effective_blocklist


@pytest.mark.parametrize("channel_id", CHANNEL_IDS)
@pytest.mark.parametrize("backend", ["cinematic", "three"])
async def test_new_channel_renders_short_and_film(tmp_path, channel_id, backend):
    from app import channels
    from app.youtube import generate_youtube_video

    with patch("app.db.get_config", AsyncMock(return_value=_config_row())):
        channel = await channels.resolve(channel_id)
    with patch("app.channels.resolve", AsyncMock(return_value=channel)), \
            patch("app.youtube._fetch_story_details", AsyncMock(return_value={"headline": "T"})), \
            patch("app.youtube._record_youtube_draft", AsyncMock(return_value=uuid.uuid4())) as record, \
            patch("app.youtube._generate_frame_audio", AsyncMock(return_value=[])), \
            patch("app.youtube._build_frames", AsyncMock(return_value=[])), \
            patch("app.youtube.subprocess.run"), \
            patch("app.youtube.build_thumbnail_variants", AsyncMock(return_value={})), \
            patch("app.youtube.VIDEOS_DIR", tmp_path):
        draft_id = await generate_youtube_video(
            story_id=uuid.uuid4(),
            channel_id=channel_id,
            backend=backend,
            storyboard_override=OVERRIDE_BOARD,
        )
    assert draft_id is not None
    record.assert_called_once()
