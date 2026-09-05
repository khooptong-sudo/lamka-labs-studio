"""Job cancel: registry math, no DB on the 404 path."""

import concurrent.futures
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cancel_bad_id_is_400():
    assert client.delete("/youtube/jobs/nope").status_code == 400


def test_cancel_unknown_job_is_404():
    resp = client.delete(f"/youtube/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_cancel_finished_job_is_404():
    from app import routes

    jid = uuid.uuid4()
    finished = concurrent.futures.Future()
    finished.set_result(None)
    routes._RUNNING_JOBS[jid] = finished
    try:
        resp = client.delete(f"/youtube/jobs/{jid}")
        assert resp.status_code == 404
    finally:
        routes._RUNNING_JOBS.pop(jid, None)


def test_cancel_live_job_marks_it_cancelled():
    from app import routes

    jid = uuid.uuid4()
    task = MagicMock()
    task.done.return_value = False
    routes._RUNNING_JOBS[jid] = task
    try:
        with patch("app.jobs.fail_job", AsyncMock()) as fail:
            resp = client.delete(f"/youtube/jobs/{jid}")
        assert resp.status_code == 200
        assert resp.json() == {"cancelled": True}
        task.cancel.assert_called_once()
        fail.assert_awaited_once_with(jid, "cancelled by owner")
    finally:
        routes._RUNNING_JOBS.pop(jid, None)
