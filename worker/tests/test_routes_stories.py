import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import IngestConfig
from app.main import app

client = TestClient(app)


def test_stories_passes_order_through_to_get_pending_stories():
    with patch("app.config.get_ingest_config", AsyncMock(return_value=IngestConfig())), \
         patch("app.db.get_pending_stories", AsyncMock(return_value=[])) as mock_get:
        resp = client.get("/stories", params={"order": "score"})

    assert resp.status_code == 200
    mock_get.assert_awaited_once_with(fresh_hours=48, order="score")


def test_stories_defaults_to_recent_order():
    with patch("app.config.get_ingest_config", AsyncMock(return_value=IngestConfig())), \
         patch("app.db.get_pending_stories", AsyncMock(return_value=[])) as mock_get:
        resp = client.get("/stories")

    assert resp.status_code == 200
    mock_get.assert_awaited_once_with(fresh_hours=48, order="recent")


def test_stories_rejects_unknown_order_with_422_not_500():
    with patch("app.config.get_ingest_config", AsyncMock(return_value=IngestConfig())), \
         patch(
             "app.db.get_pending_stories",
             AsyncMock(side_effect=ValueError("unknown order 'bogus'; expected one of ['recent', 'score']")),
         ):
        resp = client.get("/stories", params={"order": "bogus"})

    assert resp.status_code == 422
    assert "unknown order" in resp.json()["detail"]


def test_queue_unknown_story_is_404():
    with patch("app.autopilot.set_queue_flag", AsyncMock(return_value=False)):
        resp = client.patch(f"/stories/{uuid.uuid4()}/queue", json={"queued": True})
    assert resp.status_code == 404


def test_queue_sets_the_flag():
    with patch("app.autopilot.set_queue_flag", AsyncMock(return_value=True)) as setter:
        resp = client.patch(f"/stories/{uuid.uuid4()}/queue", json={"queued": True})
    assert resp.status_code == 200
    assert resp.json()["queued"] is True
    setter.assert_awaited_once()


def test_queue_rejects_non_uuid_story_id_with_400():
    resp = client.patch("/stories/not-a-uuid/queue", json={"queued": True})
    assert resp.status_code == 400
