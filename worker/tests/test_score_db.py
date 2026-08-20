"""DB-level behaviour of scoring. Requires local Postgres."""

import uuid

import pytest

pytestmark = pytest.mark.integration


async def _seed_story(db, headline: str = "Test story") -> uuid.UUID:
    from app.db import _fetchval

    async with db.connection() as conn:
        return await _fetchval(
            conn,
            "INSERT INTO stories (headline, status) VALUES (%s, 'inbox') RETURNING id",
            headline,
        )


async def _read_story(db, story_id: uuid.UUID) -> dict:
    from app.db import _fetchone

    async with db.connection() as conn:
        return await _fetchone(
            conn,
            "SELECT score, angle, vertical, content_archetype, status "
            "FROM stories WHERE id = %s",
            story_id,
        )


GOOD = {
    "score": 72.0,
    "angle": "The related-party note matters more than the headline number",
    "vertical": "earnings",
    "content_archetype": "filing_walkthrough",
}


async def test_write_score_sets_all_four_columns(db):
    from app.score import write_score

    story_id = await _seed_story(db)
    assert await write_score(story_id, GOOD) is True

    row = await _read_story(db, story_id)
    assert row["score"] == 72.0
    assert row["angle"] == GOOD["angle"]
    assert row["vertical"] == "earnings"
    assert row["content_archetype"] == "filing_walkthrough"


async def test_write_score_leaves_status_alone(db):
    """The load-bearing one. Flipping status would empty the Inbox."""
    from app.score import write_score

    story_id = await _seed_story(db)
    await write_score(story_id, GOOD)

    row = await _read_story(db, story_id)
    assert row["status"] == "inbox"


async def test_write_score_is_idempotent(db):
    from app.score import write_score

    story_id = await _seed_story(db)
    assert await write_score(story_id, GOOD) is True
    # A second pass must not overwrite an existing score.
    assert await write_score(story_id, {**GOOD, "score": 10.0}) is False

    row = await _read_story(db, story_id)
    assert row["score"] == 72.0


async def test_a_scored_story_is_still_returned_by_the_inbox(db):
    """Regression for the hazard this design was written around, and the shape
    of recorded bug #18: a scored story must not vanish from the Inbox."""
    from app.db import get_pending_stories
    from app.score import write_score

    story_id = await _seed_story(db, "Scored but still pending")
    await write_score(story_id, GOOD)

    headlines = [s["headline"] for s in await get_pending_stories(fresh_hours=48)]
    assert "Scored but still pending" in headlines


async def test_fetch_unscored_skips_already_scored_stories(db):
    from app.score import fetch_unscored, write_score

    unscored_id = await _seed_story(db, "Not yet scored")
    scored_id = await _seed_story(db, "Already scored")
    await write_score(scored_id, GOOD)

    found = {s["headline"] for s in await fetch_unscored(limit=25, fresh_hours=48)}
    assert "Not yet scored" in found
    assert "Already scored" not in found


async def test_fetch_unscored_respects_the_batch_limit(db):
    from app.score import fetch_unscored

    for index in range(5):
        await _seed_story(db, f"Story {index}")

    assert len(await fetch_unscored(limit=3, fresh_hours=48)) == 3


async def test_fetch_unscored_includes_manual_ideas_without_items(db):
    """Manual ideas have no linked items. They must still be scored, or they
    sink to the bottom of a score-ordered Inbox forever."""
    from app.score import fetch_unscored

    await _seed_story(db, "Manual idea, no sources")
    found = {s["headline"] for s in await fetch_unscored(limit=25, fresh_hours=48)}
    assert "Manual idea, no sources" in found
