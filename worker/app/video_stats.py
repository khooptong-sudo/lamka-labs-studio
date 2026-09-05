"""Nightly YouTube stats → archetype multipliers. No migration (metrics table).

Owner links the uploaded video per draft (``body.youtube_video_id``); this job
pulls stats for drafts without a fresh row and upserts one ``metrics`` row per
video (``platform='youtube'``). Scoring reads multipliers live per batch via
:func:`multipliers_for_batch` — nothing is stored, so no weights table can go
stale.

Stdlib logging (not structlog like the rest of the worker) so the
creds-missing path is assertable via caplog.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from app.db import _fetchall, get_pool
from app.youtube import get_youtube_analytics

logger = logging.getLogger(__name__)

VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})")
BARE_ID_RE = re.compile(r"\A[A-Za-z0-9_-]{11}\Z")

MIN_VIDEOS_PER_ARCHETYPE = 3
MIN_MULTIPLIER = 0.7
MAX_MULTIPLIER = 1.3
WINDOW_DAYS = 90


def extract_video_id(text: str) -> str | None:
    """Pull a canonical 11-char YouTube id out of a watch/shorts URL or bare id."""
    if not text:
        return None
    text = text.strip()
    if BARE_ID_RE.match(text):
        return text
    match = VIDEO_ID_RE.search(text)
    return match.group(1) if match else None


def _clamped_ratio(avg: float, overall: float) -> float:
    """Archetype avg vs global avg, clamped to [0.7, 1.3], 2dp. No signal → 1.0."""
    if overall <= 0:
        return 1.0
    return round(min(max(avg / overall, MIN_MULTIPLIER), MAX_MULTIPLIER), 2)


def compute_multipliers(rows: list[dict], min_videos=MIN_VIDEOS_PER_ARCHETYPE) -> dict[str, float]:
    """Per-archetype tilt: archetype-avg / global-avg over ALL video rows.

    Zeros are signal and included. Archetypes with fewer than ``min_videos``
    rows stay neutral at 1.0 (callers also default missing keys to 1.0).
    Empty input → {}.
    """
    if not rows:
        return {}
    by_archetype: dict[str, list[float]] = {}
    for row in rows:
        by_archetype.setdefault(row["archetype"], []).append(row.get("views") or 0)
    all_views = [views for group in by_archetype.values() for views in group]
    global_avg = sum(all_views) / len(all_views)
    multipliers: dict[str, float] = {}
    for archetype, views in by_archetype.items():
        if len(views) < min_videos:
            multipliers[archetype] = 1.0
            continue
        multipliers[archetype] = _clamped_ratio(sum(views) / len(views), global_avg)
    return multipliers


async def upsert_video_stats(draft_id: uuid.UUID, entry: dict[str, Any]) -> None:
    """Replace this draft's youtube metrics row with fresh stats.

    The metrics table carries no unique constraint fitting (draft, platform),
    so this is delete-then-insert — two statements max. API counts arrive as
    strings; absent means 0.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM metrics WHERE draft_id = %s AND platform = 'youtube'",
                (draft_id,),
            )
            await cur.execute(
                """
                INSERT INTO metrics (draft_id, platform, impressions, likes, replies)
                VALUES (%s, 'youtube', %s, %s, %s)
                """,
                (
                    draft_id,
                    int(entry.get("views") or 0),
                    int(entry.get("likes") or 0),
                    int(entry.get("comments") or 0),
                ),
            )


async def video_stats_job() -> None:
    """Pull stats for linked drafts with no fresh row; skip loud on no creds."""
    # Fail fast on missing creds BEFORE any DB work: the fetcher raises
    # RuntimeError when credentials are absent, and the real implementation
    # short-circuits an empty id list with no network call — so this probe is
    # free in prod and keeps the creds-missing path off the database entirely.
    try:
        await get_youtube_analytics([])
    except RuntimeError as exc:
        logger.error("video_stats skipped without writing: youtube credentials error (%s)", exc)
        return

    pool = await get_pool()
    async with pool.connection() as conn:
        pending = await _fetchall(
            conn,
            """
            SELECT d.id AS draft_id, d.body->>'youtube_video_id' AS video_id
              FROM drafts d
             WHERE d.body->>'youtube_video_id' IS NOT NULL
               AND d.body->>'youtube_video_id' <> ''
               AND NOT EXISTS (
                   SELECT 1 FROM metrics m
                    WHERE m.draft_id = d.id
                      AND m.platform = 'youtube'
                      AND m.captured_at >= now() - INTERVAL '7 days'
               )
            """,
        )
    if not pending:
        return

    by_video = {row["video_id"]: row["draft_id"] for row in pending}
    # The fetcher batches ≤50 ids per analytics call; mirror that bound here.
    video_ids = list(by_video)
    for start in range(0, len(video_ids), 50):
        batch = video_ids[start:start + 50]
        try:
            stats = await get_youtube_analytics(batch)
        except RuntimeError as exc:
            logger.error("video_stats skipped without writing: youtube credentials error (%s)", exc)
            return
        for video_id in batch:
            entry = (stats or {}).get(video_id)
            if not entry:
                continue
            await upsert_video_stats(by_video[video_id], entry)


async def multipliers_for_batch() -> dict[str, float]:
    """One aggregate SQL: trailing-90d youtube metrics via drafts→stories.

    Returns per-archetype multipliers under the same rule as
    :func:`compute_multipliers` (weighted global mean, 3-video minimum,
    clamped, 2dp). No data → {} and callers score at 1.0.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        groups = await _fetchall(
            conn,
            """
            SELECT COALESCE(d.content_archetype, s.content_archetype) AS archetype,
                   COUNT(*) AS n,
                   AVG(m.impressions)::float8 AS avg_views
              FROM metrics m
              JOIN drafts d ON d.id = m.draft_id
              LEFT JOIN stories s ON s.id = d.story_id
             WHERE m.platform = 'youtube'
               AND m.captured_at >= now() - make_interval(days => %s)
               AND COALESCE(d.content_archetype, s.content_archetype) IS NOT NULL
             GROUP BY 1
            """,
            WINDOW_DAYS,
        )
    total_views = sum(group["avg_views"] * group["n"] for group in groups)
    total_n = sum(group["n"] for group in groups)
    if not total_n:
        return {}
    global_avg = total_views / total_n
    multipliers: dict[str, float] = {}
    for group in groups:
        if group["n"] < MIN_VIDEOS_PER_ARCHETYPE:
            multipliers[group["archetype"]] = 1.0
            continue
        multipliers[group["archetype"]] = _clamped_ratio(group["avg_views"], global_avg)
    return multipliers


async def get_analytics_summary() -> dict[str, Any]:
    """Per-archetype totals + top 5 videos by views. Pure read for the band."""
    pool = await get_pool()
    async with pool.connection() as conn:
        by_archetype = await _fetchall(
            conn,
            """
            SELECT COALESCE(d.content_archetype, s.content_archetype) AS archetype,
                   COUNT(*) AS videos,
                   SUM(m.impressions)::bigint AS total_views,
                   AVG(m.impressions)::float8 AS avg_views
              FROM metrics m
              JOIN drafts d ON d.id = m.draft_id
              LEFT JOIN stories s ON s.id = d.story_id
             WHERE m.platform = 'youtube'
               AND m.captured_at >= now() - make_interval(days => %s)
               AND COALESCE(d.content_archetype, s.content_archetype) IS NOT NULL
             GROUP BY 1
             ORDER BY total_views DESC
            """,
            WINDOW_DAYS,
        )
        top_videos = await _fetchall(
            conn,
            """
            SELECT d.id AS draft_id,
                   d.body->>'youtube_video_id' AS video_id,
                   s.headline AS headline,
                   COALESCE(d.content_archetype, s.content_archetype) AS archetype,
                   m.impressions AS views
              FROM metrics m
              JOIN drafts d ON d.id = m.draft_id
              LEFT JOIN stories s ON s.id = d.story_id
             WHERE m.platform = 'youtube'
             ORDER BY m.impressions DESC
             LIMIT 5
            """,
        )
    total_views = sum(row["avg_views"] * row["videos"] for row in by_archetype)
    total_n = sum(row["videos"] for row in by_archetype)
    global_avg = (total_views / total_n) if total_n else 0
    return {
        "by_archetype": [
            {
                "archetype": row["archetype"],
                "videos": row["videos"],
                "total_views": int(row["total_views"] or 0),
                "avg_views": round(row["avg_views"] or 0, 1),
                "multiplier": (
                    _clamped_ratio(row["avg_views"], global_avg)
                    if row["videos"] >= MIN_VIDEOS_PER_ARCHETYPE
                    else 1.0
                ),
            }
            for row in by_archetype
        ],
        "top_videos": [
            {
                "draft_id": str(row["draft_id"]),
                "video_id": row["video_id"],
                "headline": row["headline"],
                "archetype": row["archetype"],
                "views": int(row["views"] or 0),
            }
            for row in top_videos
        ],
    }


__all__ = [
    "VIDEO_ID_RE",
    "BARE_ID_RE",
    "MIN_VIDEOS_PER_ARCHETYPE",
    "MIN_MULTIPLIER",
    "MAX_MULTIPLIER",
    "WINDOW_DAYS",
    "extract_video_id",
    "compute_multipliers",
    "upsert_video_stats",
    "video_stats_job",
    "multipliers_for_batch",
    "get_analytics_summary",
]
