"""PATCH /drafts/{id}/thumbnail: thumbnail pick persistence, mocked DB."""

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_set_thumbnail_a_persists_and_returns_pick():
    did = uuid.uuid4()
    with patch(
        "app.db.set_draft_thumbnail_picked", AsyncMock(return_value=True)
    ) as mock_set:
        resp = client.patch(f"/drafts/{did}/thumbnail", json={"picked": "a"})

    assert resp.status_code == 200
    assert resp.json() == {"id": str(did), "thumbnail_picked": "a"}
    mock_set.assert_awaited_once_with(did, "a")


def test_set_thumbnail_b_persists_and_returns_pick():
    did = uuid.uuid4()
    with patch(
        "app.db.set_draft_thumbnail_picked", AsyncMock(return_value=True)
    ) as mock_set:
        resp = client.patch(f"/drafts/{did}/thumbnail", json={"picked": "b"})

    assert resp.status_code == 200
    assert resp.json() == {"id": str(did), "thumbnail_picked": "b"}
    mock_set.assert_awaited_once_with(did, "b")


def test_set_thumbnail_null_clears_pick():
    did = uuid.uuid4()
    with patch(
        "app.db.set_draft_thumbnail_picked", AsyncMock(return_value=True)
    ) as mock_set:
        resp = client.patch(f"/drafts/{did}/thumbnail", json={"picked": None})

    assert resp.status_code == 200
    assert resp.json() == {"id": str(did), "thumbnail_picked": None}
    mock_set.assert_awaited_once_with(did, None)


def test_set_thumbnail_rejects_unknown_value_with_422():
    with patch(
        "app.db.set_draft_thumbnail_picked", AsyncMock(return_value=True)
    ) as mock_set:
        resp = client.patch(f"/drafts/{uuid.uuid4()}/thumbnail", json={"picked": "c"})

    assert resp.status_code == 422
    mock_set.assert_not_awaited()


def test_set_thumbnail_unknown_draft_is_404():
    with patch("app.db.set_draft_thumbnail_picked", AsyncMock(return_value=False)):
        resp = client.patch(f"/drafts/{uuid.uuid4()}/thumbnail", json={"picked": "a"})

    assert resp.status_code == 404


def test_set_thumbnail_bad_id_is_400():
    resp = client.patch("/drafts/nope/thumbnail", json={"picked": "a"})
    assert resp.status_code == 400
