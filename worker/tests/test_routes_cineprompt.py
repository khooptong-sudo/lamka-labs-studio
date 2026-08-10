import uuid as uuid_module
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.cineprompt import FillError
from app.main import app

client = TestClient(app)


def test_fill_returns_field_state():
    fake_fields = {"genre": "action", "mood": "nostalgic", "pacing": "slow motion"}
    with patch("app.cineprompt.fill_from_scene", AsyncMock(return_value=fake_fields)):
        resp = client.post(
            "/cineprompt/fill",
            json={"description": "a woman in a cramped office at dawn", "mode": "single", "level": "complex"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"fields": fake_fields}


def test_fill_error_returns_422_with_message():
    with patch(
        "app.cineprompt.fill_from_scene",
        AsyncMock(side_effect=FillError("scene-to-prompt failed: too few fields: 2 < 6")),
    ):
        resp = client.post(
            "/cineprompt/fill",
            json={"description": "x", "mode": "single", "level": "complex"},
        )
    assert resp.status_code == 422
    assert "too few fields" in resp.json()["detail"]


def test_fill_requires_description():
    resp = client.post("/cineprompt/fill", json={"mode": "single", "level": "complex"})
    assert resp.status_code == 422


def test_fill_passes_locked_fields_through():
    with patch("app.cineprompt.fill_from_scene", AsyncMock(return_value={})) as mock_fill:
        client.post(
            "/cineprompt/fill",
            json={
                "description": "a scene", "mode": "single", "level": "complex",
                "locked": {"camera_body": "shot on RED V-Raptor"},
            },
        )
    mock_fill.assert_awaited_once_with(
        "a scene", mode="single", level="complex", locked={"camera_body": "shot on RED V-Raptor"},
    )


def test_build_returns_assembled_prompt():
    with patch("app.cineprompt.build_prompt", return_value=["Wide shot. A woman in a cramped office."]):
        resp = client.post(
            "/cineprompt/build",
            json={"mode": "single", "model": "veo", "fields": {"shot_type": "wide shot"}},
        )
    assert resp.status_code == 200
    assert resp.json() == {"prompt": "Wide shot. A woman in a cramped office."}


def test_build_requires_fields():
    resp = client.post("/cineprompt/build", json={"mode": "single", "model": "veo"})
    assert resp.status_code == 422


def test_save_downloads_video_and_returns_id(tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes._VIDEOS_DIR", tmp_path)
    fake_id = uuid_module.uuid4()
    monkeypatch.setattr("app.routes.uuid.uuid4", lambda: fake_id)

    async def fake_get(self, url, **kwargs):
        return httpx.Response(200, content=b"fake video bytes", request=httpx.Request("GET", url))

    with (
        patch("httpx.AsyncClient.get", fake_get),
        patch("app.db.save_cineprompt_generation", AsyncMock(return_value=fake_id)),
    ):
        resp = client.post(
            "/cineprompt/save",
            json={
                "description": "a scene", "mode": "single", "model": "veo",
                "fields": {"genre": "action"}, "prompt": "A scene.",
                "video_url": "https://fal.media/files/abc/output.mp4",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(fake_id)
    saved_path = tmp_path / "cineprompt" / f"{fake_id}.mp4"
    assert saved_path.read_bytes() == b"fake video bytes"


def test_save_returns_502_on_download_failure_and_writes_no_row(tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes._VIDEOS_DIR", tmp_path)

    async def fake_get(self, url, **kwargs):
        raise httpx.ConnectTimeout("timed out", request=httpx.Request("GET", url))

    with (
        patch("httpx.AsyncClient.get", fake_get),
        patch("app.db.save_cineprompt_generation", AsyncMock()) as mock_save,
    ):
        resp = client.post(
            "/cineprompt/save",
            json={
                "description": "a scene", "mode": "single", "model": "veo",
                "fields": {}, "prompt": "A scene.",
                "video_url": "https://fal.media/files/abc/output.mp4",
            },
        )
    assert resp.status_code == 502
    mock_save.assert_not_awaited()
    assert not (tmp_path / "cineprompt").exists() or not any((tmp_path / "cineprompt").iterdir())
