"""Story scoring (P2a).

Turns the P1 reader's output into a ranked editorial queue: every clustered
story gets a 0-100 score, an angle, a vertical, and a content archetype.

Two invariants this module exists to hold:

  1. It never mutates `stories.status`. `db.get_pending_stories` hard-codes
     `WHERE s.status = 'inbox'` and `ideation.py` reads the same Inbox for the
     video path, so flipping status to 'scored' would silently empty both.
     Scored-ness is derived from `score IS NOT NULL`.

  2. It never writes a fabricated score. A score the model did not produce
     silently reorders the owner's editorial queue, which is the scoring
     equivalent of recorded bug #12 (a stub script became a publishable video).
     A story that cannot be scored stays unscored and is retried next cycle.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import structlog

from app.audit import audit_log
from app.config import get_ingest_config, get_llm_config
from app.db import FRESH_WINDOW_PREDICATE, _fetchall, get_pool
from app.llm import contract, router
from app.llm.contract import FieldSpec
from app.llm.router import RouterError
from app.taxonomy import ARCHETYPES, VERTICALS, is_archetype, is_vertical

log = structlog.get_logger()

# Mirrors youtube.py:50 so the two LLM paths fail on the same shape and are
# tunable the same way under a flaky provider.
SCORE_MAX_ATTEMPTS = int(os.environ.get("SCORE_MAX_ATTEMPTS", "4"))


def _is_score(value: Any) -> bool:
    # bool is a subclass of int; True would otherwise pass as a score of 1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 0 <= value <= 100


# Bounds the angle so a runaway model reply can't land a multi-thousand
# character string in the `text` column and then in the Inbox UI.
MAX_ANGLE_LENGTH = 300


def _is_angle(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= MAX_ANGLE_LENGTH


SCORE_SPEC = FieldSpec(validators={
    "score": _is_score,
    "angle": _is_angle,
    "vertical": is_vertical,
    "content_archetype": is_archetype,
})


SYSTEM_PROMPT = f"""You rank finance news stories for an educational X account.

The account's persona is educator, analyst, and commentator. It is NEVER an
adviser. It may name and analyse specific companies. It must never tell anyone
to buy, sell, hold, accumulate, or book profit, never give target prices or
entry and exit levels, and never promise or project returns.

Score a story on how well it can become a compliant, genuinely interesting post
under that persona. Reward stories that can be explained through fundamentals,
filings, mechanics, or history. Penalise stories whose only angle is a price
move plus an implied action, because that angle cannot be written compliantly.

Return ONE JSON object and nothing else. No markdown fence, no commentary.

{{
  "score": <number 0-100>,
  "angle": "<one sentence: the specific editorial angle worth taking>",
  "vertical": "<one of the verticals below>",
  "content_archetype": "<one of the archetypes below>"
}}

Verticals (choose exactly one):
{chr(10).join(f"- {v}" for v in VERTICALS)}

Archetypes (choose exactly one):
{chr(10).join(f"- {a}" for a in ARCHETYPES)}

Both lists are closed. Never invent a value; pick the closest fit."""


def build_user_prompt(headline: str, items: list[dict]) -> str:
    """Render the bounded source packet for one story."""
    if items:
        sources = "\n".join(
            f"- {item['title']} ({item['source_name']})" for item in items
        )
    else:
        sources = "(no linked sources)"
    return f"Headline: {headline}\n\nLinked sources:\n{sources}"


async def fetch_unscored(limit: int, fresh_hours: int) -> list[dict]:
    """Unscored Inbox stories inside the fresh-news window, with their items.

    The window predicate mirrors `db.get_pending_stories` exactly (same
    `FRESH_WINDOW_PREDICATE` constant), including the manual-idea branch (a
    story with no linked items). Divergence between "what the Inbox shows"
    and "what gets scored" would leave manual ideas permanently unscored and
    sinking to the bottom of a score-ordered queue.

    The per-story items query also mirrors `get_pending_stories`' item
    filter (same fresh-window and `date_missing` conditions): the model must
    never reason over source evidence the Inbox hides from the owner.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        stories = await _fetchall(
            conn,
            f"""
            SELECT s.id, s.headline
              FROM stories s
             WHERE s.score IS NULL
               AND s.status = 'inbox'
               AND ({FRESH_WINDOW_PREDICATE})
             ORDER BY s.created_at DESC
             LIMIT %s
            """,
            fresh_hours,
            limit,
        )
        for story in stories:
            story["items"] = await _fetchall(
                conn,
                """
                SELECT i.title, src.name AS source_name
                  FROM items i
                  JOIN story_items si ON i.id = si.item_id
                  JOIN sources src ON i.source_id = src.id
                 WHERE si.story_id = %s
                   AND i.published_at >= now() - make_interval(hours := %s)
                   AND NOT (i.warnings @> '["date_missing"]'::jsonb)
                 ORDER BY i.published_at DESC
                """,
                story["id"],
                fresh_hours,
            )
    return stories


async def write_score(story_id: uuid.UUID, result: dict) -> bool:
    """Write all four columns in one UPDATE. Returns whether a row changed.

    `AND score IS NULL` makes this idempotent: a concurrent or repeated run
    cannot overwrite a score that already landed. `status` is deliberately
    absent from the SET clause.

    Re-validates against SCORE_SPEC even though today's only caller already
    validated via `contract.parse`: `stories.vertical` and `content_archetype`
    carry no DB CHECK constraint, so the database is not a second line of
    defence, and this becomes a shared write path once P2b adds a caller.
    """
    violations = contract.validate(result, SCORE_SPEC)
    if violations:
        raise ValueError(f"invalid score payload: {'; '.join(violations)}")

    pool = await get_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            UPDATE stories
               SET score = %s, angle = %s, vertical = %s, content_archetype = %s
             WHERE id = %s AND score IS NULL
            """,
            (
                float(result["score"]),
                result["angle"],
                result["vertical"],
                result["content_archetype"],
                story_id,
            ),
        )
        return cursor.rowcount > 0


async def _safe_multipliers() -> dict[str, float]:
    """Fetch the retention multipliers once per batch. Fails open to {}
    (every archetype scores at neutral 1.0) when the analytics side is
    unreachable: scoring must never fail because stats are unavailable —
    the tilt is advisory, the score is not."""
    try:
        from app import video_stats

        return await video_stats.multipliers_for_batch()
    except Exception as exc:  # noqa: BLE001
        log.warning("score_multipliers_unavailable", error=str(exc))
        return {}


async def score_new_job() -> None:
    """Score a bounded batch of unscored Inbox stories."""
    llm_cfg = await get_llm_config()
    ingest_cfg = await get_ingest_config()

    stories = await fetch_unscored(llm_cfg.score_batch_max, ingest_cfg.fresh_news_hours)
    if not stories:
        return

    multiplier_map = await _safe_multipliers()

    scored = 0
    failed = 0
    for story in stories:
        try:
            result = await router.complete_json(
                "story_score",
                system=SYSTEM_PROMPT,
                user=build_user_prompt(story["headline"], story["items"]),
                spec=SCORE_SPEC,
                max_attempts=SCORE_MAX_ATTEMPTS,
            )
        except RouterError as exc:
            failed += 1
            log.warning("story_score_failed", story_id=str(story["id"]), error=str(exc))
            await audit_log(
                actor="worker",
                action="story_score_failed",
                entity=str(story["id"]),
                entity_type="story",
                after={"error": str(exc)},
            )
            continue

        # Retention loop: tilt the model score toward what actually gets
        # watched. Keyed by archetype ONLY — vertical splits are too thin at
        # this volume to clear the 3-video minimum, so they would all read
        # neutral anyway (recorded decision; revisit when the catalog grows).
        # The write + audit path below is exactly as before: no new columns,
        # the multiplied score is what lands in `stories.score`.
        mult = multiplier_map.get(result["content_archetype"], 1.0)
        result = {**result, "score": round(result["score"] * mult)}

        if await write_score(story["id"], result):
            scored += 1

    log.info("score_new_complete", scored=scored, failed=failed, considered=len(stories))
