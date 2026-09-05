"""Autopilot must generate under each story's own channel, or not at all.

The bug these cover: the job read a channel from DEFAULT_YOUTUBE_CHANNEL_ID and
applied it to every pending story, so setting it to `finance` generated a kids
story in the finance voice. Nothing downstream would notice.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels import ChannelConfigError


def _story(channel_id, story_id=None):
    return {
        "id": str(story_id or uuid.uuid4()),
        "headline": "A headline",
        "status": "inbox",
        "channel_id": channel_id,
        "items": [],
    }


@pytest.mark.asyncio
async def test_generates_under_each_storys_own_channel():
    from app import ideation

    finance, kids = _story("finance"), _story("kids")
    gen = AsyncMock(return_value=uuid.uuid4())

    with patch("app.ideation.db.get_pending_stories", AsyncMock(return_value=[finance, kids])), \
            patch("app.ideation.generate_youtube_video", gen):
        await ideation.autopilot_job()

    assert gen.await_count == 2
    used = {c.kwargs["channel_id"] for c in gen.await_args_list}
    assert used == {"finance", "kids"}
    ids = {str(c.kwargs["story_id"]) for c in gen.await_args_list}
    assert ids == {finance["id"], kids["id"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [None, "", "   "])
async def test_story_without_a_channel_is_skipped_not_defaulted(empty, monkeypatch):
    """No env var, no config value, nothing may supply a channel here."""
    from app import ideation

    monkeypatch.setenv("DEFAULT_YOUTUBE_CHANNEL_ID", "finance")

    unassigned = _story(empty)
    assigned = _story("kids")
    gen = AsyncMock(return_value=uuid.uuid4())

    with patch("app.ideation.db.get_pending_stories", AsyncMock(return_value=[unassigned, assigned])), \
            patch("app.ideation.generate_youtube_video", gen):
        await ideation.autopilot_job()

    # The unassigned story is skipped; the assigned one still runs.
    assert gen.await_count == 1
    assert gen.await_args.kwargs["channel_id"] == "kids"
    assert str(gen.await_args.kwargs["story_id"]) == assigned["id"]


@pytest.mark.asyncio
async def test_default_channel_env_var_is_not_read_at_all(monkeypatch):
    """Setting the old env var must not resurrect the default-channel path."""
    from app import ideation

    monkeypatch.setenv("DEFAULT_YOUTUBE_CHANNEL_ID", "finance")
    gen = AsyncMock(return_value=uuid.uuid4())

    with patch("app.ideation.db.get_pending_stories", AsyncMock(return_value=[_story(None)])), \
            patch("app.ideation.generate_youtube_video", gen):
        await ideation.autopilot_job()

    gen.assert_not_awaited()


@pytest.mark.asyncio
async def test_channel_config_error_is_logged_distinctly_and_does_not_stop_the_run():
    """A bad channel config is a configuration fault to go and fix. It must not
    be indistinguishable from a generic generation failure in the log."""
    from app import ideation

    bad, good = _story("typo"), _story("kids")

    async def _gen(*, story_id, channel_id, upload_preference):
        if channel_id == "typo":
            raise ChannelConfigError("unknown channel 'typo'; configured: finance, kids")
        return uuid.uuid4()

    gen = AsyncMock(side_effect=_gen)
    fake_log = MagicMock()

    with patch("app.ideation.db.get_pending_stories", AsyncMock(return_value=[bad, good])), \
            patch("app.ideation.generate_youtube_video", gen), \
            patch("app.ideation.log", fake_log):
        await ideation.autopilot_job()

    events = [c.args[0] for c in fake_log.error.call_args_list if c.args]
    assert "autopilot_channel_config_error" in events
    assert "autopilot_generation_error" not in events

    # The bad story must not take the rest of the batch down with it.
    assert gen.await_count == 2


@pytest.mark.asyncio
async def test_generic_failure_keeps_its_own_event_name():
    from app import ideation

    gen = AsyncMock(side_effect=RuntimeError("render died"))
    fake_log = MagicMock()

    with patch("app.ideation.db.get_pending_stories", AsyncMock(return_value=[_story("finance")])), \
            patch("app.ideation.generate_youtube_video", gen), \
            patch("app.ideation.log", fake_log):
        await ideation.autopilot_job()

    events = [c.args[0] for c in fake_log.error.call_args_list if c.args]
    assert events == ["autopilot_generation_error"]


@pytest.mark.asyncio
async def test_respects_the_per_run_cap(monkeypatch):
    from app import ideation

    monkeypatch.setenv("AUTOPILOT_MAX_DRAFTS_PER_RUN", "2")
    gen = AsyncMock(return_value=uuid.uuid4())
    stories = [_story("finance") for _ in range(5)]

    with patch("app.ideation.db.get_pending_stories", AsyncMock(return_value=stories)), \
            patch("app.ideation.generate_youtube_video", gen):
        await ideation.autopilot_job()

    assert gen.await_count == 2


# ---------------------------------------------------------------------------
# Overnight autopilot: pick queued, render, flag correctly. No network, no GPU.
# (Task 1: worker/app/autopilot.py — flag column, picker, nightly job.)
# ---------------------------------------------------------------------------


def test_window_accepts_early_morning_only():
    from app.autopilot import in_window

    assert in_window(datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)) is True
    assert in_window(datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)) is False
    assert in_window(datetime(2026, 9, 5, 1, 59, tzinfo=timezone.utc)) is False


def test_should_run_once_per_day():
    from app.autopilot import should_run_today

    now = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)
    assert should_run_today(None, now) is True
    assert should_run_today("2026-09-05", now) is False
    assert should_run_today("2026-09-04", now) is True


async def test_job_is_quiet_outside_the_window(monkeypatch):
    from app import autopilot

    monkeypatch.setattr(autopilot, "fetch_queued", None)  # must never be reached
    await autopilot.autopilot_overnight_job(
        now=datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc))
    # returns None, touches nothing (fetch_queued broken on purpose)


async def test_success_clears_flag_and_failure_keeps_it(monkeypatch):
    from app import autopilot
    from app import youtube as youtube_mod
    from app.config import IngestConfig

    stories = [
        {"id": "11111111-1111-1111-1111-111111111111", "headline": "A",
         "channel_id": "finance"},
        {"id": "22222222-2222-2222-2222-222222222222", "headline": "B",
         "channel_id": "finance"},
    ]
    monkeypatch.setattr(autopilot, "fetch_queued", AsyncMock(return_value=stories))
    cleared, audits = [], []
    monkeypatch.setattr(autopilot, "clear_queue_flag", AsyncMock(side_effect=lambda sid: cleared.append(str(sid))))
    monkeypatch.setattr(autopilot, "audit_log", AsyncMock(side_effect=lambda **kw: audits.append(kw["action"])))
    monkeypatch.setattr(autopilot, "get_autopilot_config",
                        AsyncMock(return_value=autopilot.AutopilotConfig(max_per_night=5)))
    monkeypatch.setattr(autopilot, "mark_run_today", AsyncMock())
    # The job reads the raw autopilot row for last_run_date via app.db
    # (function-local `from app import db`). Same story: hermetic unit
    # path, no real DB.
    monkeypatch.setattr("app.db.get_config", AsyncMock(return_value={}))
    # Hermeticity: the plan's block leaves these unpatched, but unit paths
    # must not touch a real DB — seam-mock them (deviation noted in commit).
    monkeypatch.setattr(autopilot, "get_ingest_config",
                        AsyncMock(return_value=IngestConfig()))
    monkeypatch.setattr(autopilot, "set_stage", AsyncMock())

    async def fake_generate(*args, **kwargs):
        story_id = kwargs.get("story_id", args[0] if args else None)
        if str(story_id).startswith("11"):
            return uuid.uuid4()
        return None

    async def fake_job(*args, **kwargs):
        return uuid.uuid4()

    monkeypatch.setattr(youtube_mod, "generate_youtube_video", fake_generate)
    monkeypatch.setattr(autopilot, "create_job", AsyncMock(side_effect=fake_job))
    monkeypatch.setattr(autopilot, "finish_job", AsyncMock())
    monkeypatch.setattr(autopilot, "fail_job", AsyncMock())
    await autopilot.autopilot_overnight_job(
        now=datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc))
    assert cleared == ["11111111-1111-1111-1111-111111111111"]
    assert "autopilot_rendered" in audits and "autopilot_failed" in audits


# ---------------------------------------------------------------------------
# DB-backed picker tests: mirror tests/test_score_db.py (db fixture, same
# seeding shape, same cleanup discipline via conftest).
# ---------------------------------------------------------------------------


async def _seed_queue_story(db, headline: str) -> uuid.UUID:
    from app.db import _fetchval

    async with db.connection() as conn:
        return await _fetchval(
            conn,
            "INSERT INTO stories (headline, status) VALUES (%s, 'inbox') RETURNING id",
            headline,
        )


async def _seed_queue_source(db) -> uuid.UUID:
    from app.db import _fetchval

    async with db.connection() as conn:
        return await _fetchval(
            conn,
            "INSERT INTO sources (kind, url, name, market, active, poll_minutes) "
            "VALUES ('rss', 'https://test.example/feed', 'TEST_source', 'IN', true, 30) "
            "RETURNING id",
        )


async def _seed_queue_item(db, source_id: uuid.UUID, *, published_at: datetime) -> uuid.UUID:
    import json

    from app.db import _fetchval

    async with db.connection() as conn:
        return await _fetchval(
            conn,
            """
            INSERT INTO items (source_id, title, url, published_at, hash, warnings)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            source_id,
            "Test item",
            f"https://test.example/{uuid.uuid4().hex}",
            published_at,
            uuid.uuid4().hex,
            json.dumps([]),
        )


@pytest.mark.integration
async def test_picker_skips_drafted_stale_and_honors_cap(db):
    from app.autopilot import fetch_queued, set_queue_flag

    now = datetime.now(timezone.utc)
    source_id = await _seed_queue_source(db)

    fresh_id = await _seed_queue_story(db, "Queued fresh undrafted")
    drafted_id = await _seed_queue_story(db, "Queued with pending draft")
    stale_id = await _seed_queue_story(db, "Queued stale")
    unflagged_id = await _seed_queue_story(db, "Unflagged fresh")

    assert await set_queue_flag(fresh_id, True) is True
    assert await set_queue_flag(drafted_id, True) is True
    assert await set_queue_flag(stale_id, True) is True

    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO drafts (story_id, status) VALUES (%s, 'pending')",
            (drafted_id,),
        )
        stale_item = await _seed_queue_item(
            db, source_id, published_at=now - timedelta(hours=72))
        await conn.execute(
            "INSERT INTO story_items (story_id, item_id) VALUES (%s, %s)",
            (stale_id, stale_item),
        )

    found = await fetch_queued(limit=10, fresh_hours=48)
    assert [str(s["id"]) for s in found] == [str(fresh_id)]
    assert str(unflagged_id) not in {str(s["id"]) for s in found}


@pytest.mark.integration
async def test_picker_orders_oldest_queued_first_and_honors_limit(db):
    from app.autopilot import fetch_queued, set_queue_flag

    first_id = await _seed_queue_story(db, "Queued first")
    second_id = await _seed_queue_story(db, "Queued second")
    await set_queue_flag(first_id, True)
    await set_queue_flag(second_id, True)

    now = datetime.now(timezone.utc)
    async with db.connection() as conn:
        await conn.execute(
            "UPDATE stories SET autopilot_queued_at = %s WHERE id = %s",
            (now - timedelta(hours=2), first_id),
        )
        await conn.execute(
            "UPDATE stories SET autopilot_queued_at = %s WHERE id = %s",
            (now - timedelta(hours=1), second_id),
        )

    found = await fetch_queued(limit=10, fresh_hours=48)
    assert [str(s["id"]) for s in found] == [str(first_id), str(second_id)]
    found_capped = await fetch_queued(limit=1, fresh_hours=48)
    assert [str(s["id"]) for s in found_capped] == [str(first_id)]


@pytest.mark.integration
async def test_set_queue_flag_sets_and_clears(db):
    from app.autopilot import set_queue_flag

    story_id = await _seed_queue_story(db, "Flag flip story")
    assert await set_queue_flag(story_id, True) is True
    assert await set_queue_flag(story_id, False) is True
    assert await set_queue_flag(uuid.uuid4(), True) is False
