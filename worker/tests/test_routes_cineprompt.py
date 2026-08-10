from unittest.mock import AsyncMock, patch

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
