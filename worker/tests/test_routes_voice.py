"""Voice-job route: validation is synchronous, staging is on disk. No DB, no TTS."""

from pathlib import Path
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
    real_write = Path.write_bytes

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
