"""Overnight renders of owner-queued stories. Manual publish still required."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from app import youtube
from app.audit import audit_log
from app.config import AutopilotConfig, get_autopilot_config, get_ingest_config
from app.db import FRESH_WINDOW_PREDICATE, _fetchall, get_pool
from app.jobs import create_job, fail_job, finish_job, set_stage

log = structlog.get_logger()

WINDOW_START_HOUR = 2
WINDOW_END_HOUR = 5


def in_window(now: datetime) -> bool:
    return WINDOW_START_HOUR <= now.hour < WINDOW_END_HOUR


def should_run_today(last_run: str | None, now: datetime) -> bool:
    return last_run != now.date().isoformat()


async def fetch_queued(*, limit: int, fresh_hours: int) -> list[dict]:
    """Flagged, fresh, undrafted stories, oldest-queued first."""
    pool = await get_pool()
    async with pool.connection() as conn:
        return await _fetchall(
            conn,
            f"""
            SELECT s.id, s.headline, s.channel_id
              FROM stories s
             WHERE s.autopilot_queued_at IS NOT NULL
               AND ({FRESH_WINDOW_PREDICATE})
               AND NOT EXISTS (
                     SELECT 1 FROM drafts d
                      WHERE d.story_id = s.id AND d.status = 'pending'
                   )
             ORDER BY s.autopilot_queued_at ASC
             LIMIT %s
            """,
            fresh_hours,
            limit,
        )


async def set_queue_flag(story_id: uuid.UUID, queued: bool) -> bool:
    """Set/clear the overnight flag. Returns False when the story is unknown."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute(
            "UPDATE stories SET autopilot_queued_at = CASE WHEN %s THEN now() ELSE NULL END "
            "WHERE id = %s",
            queued, story_id,
        )
        return cursor.rowcount > 0


async def clear_queue_flag(story_id: uuid.UUID) -> None:
    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE stories SET autopilot_queued_at = NULL WHERE id = %s",
            story_id,
        )


async def mark_run_today(today: str) -> None:
    """Remember today's run in the config table (upsert the autopilot row)."""
    from app import db

    current = await db.get_config("autopilot") or {}
    await db.set_config("autopilot", {**current, "last_run_date": today})


async def autopilot_overnight_job(*, now: datetime | None = None) -> None:
    """Render queued stories. Quiet no-op outside the window or repeat days."""
    from app import db

    current = now or datetime.now(timezone.utc)
    if not in_window(current):
        log.debug("autopilot_skipped", reason="outside_window")
        return
    row = await db.get_config("autopilot") or {}
    if not should_run_today(row.get("last_run_date"), current):
        log.debug("autopilot_skipped", reason="already_ran_today")
        return
    ingest_cfg = await get_ingest_config()
    llm_cfg: AutopilotConfig = await get_autopilot_config()
    stories = await fetch_queued(limit=llm_cfg.max_per_night, fresh_hours=ingest_cfg.fresh_news_hours)
    for story in stories:
        job_id = await create_job(kind="short", story_id=story["id"])
        try:
            await set_stage(job_id, "script")
            draft_id = await youtube.generate_youtube_video(
                story_id=story["id"],
                channel_id=story["channel_id"],
                upload_preference="manual",
                backend="cinematic",
                job_id=job_id,
            )
        except Exception as exc:  # noqa: BLE001 — one story must not kill the night
            log.error("autopilot_story_failed", story_id=str(story["id"]), error=str(exc))
            await fail_job(job_id, f"autopilot: {exc}")
            await audit_log(actor="worker", action="autopilot_failed",
                            entity=str(story["id"]), entity_type="story",
                            after={"error": str(exc)})
            continue
        if draft_id is None:
            await fail_job(job_id, "generation aborted by a quality guard; see worker logs")
            await audit_log(actor="worker", action="autopilot_failed",
                            entity=str(story["id"]), entity_type="story",
                            after={"reason": "guard_abort"})
            continue
        await finish_job(job_id, draft_id)
        await clear_queue_flag(story["id"])
        await audit_log(actor="worker", action="autopilot_rendered",
                        entity=str(story["id"]), entity_type="story",
                        after={"draft_id": str(draft_id)})
    await mark_run_today(current.date().isoformat())
