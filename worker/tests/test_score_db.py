"""DB-level behaviour of scoring. Requires local Postgres."""

import json
import uuid
from datetime import datetime, timedelta, timezone

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


async def _seed_source(db) -> uuid.UUID:
    """Mirrors tests/test_db.py::_seed_source."""
    from app.db import _fetchval

    async with db.connection() as conn:
        return await _fetchval(
            conn,
            "INSERT INTO sources (kind, url, name, market, active, poll_minutes) "
            "VALUES ('rss', 'https://test.example/feed', 'TEST_source', 'IN', true, 30) "
            "RETURNING id",
        )


async def _seed_item(
    db,
    source_id: uuid.UUID,
    *,
    title: str = "Test item",
    published_at: datetime | None = None,
    warnings: list[str] | None = None,
) -> uuid.UUID:
    """Mirrors tests/test_db.py::_seed_item, with published_at/warnings control
    for exercising the fresh-window predicate directly."""
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
            title,
            f"https://test.example/{uuid.uuid4().hex}",
            published_at or datetime.now(timezone.utc),
            uuid.uuid4().hex,
            json.dumps(warnings or []),
        )


async def _link_story_item(db, story_id: uuid.UUID, item_id: uuid.UUID) -> None:
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO story_items (story_id, item_id) VALUES (%s, %s)",
            (story_id, item_id),
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

    await _seed_story(db, "Not yet scored")
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


async def test_fetch_unscored_includes_a_story_whose_item_is_inside_the_window(db):
    """The window half of FRESH_WINDOW_PREDICATE, not just the manual-idea
    NOT EXISTS branch: a story whose only item was published inside the
    fresh-news window must be returned."""
    from app.score import fetch_unscored

    source_id = await _seed_source(db)
    story_id = await _seed_story(db, "Fresh item story")
    item_id = await _seed_item(
        db, source_id, published_at=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    await _link_story_item(db, story_id, item_id)

    found = {s["headline"] for s in await fetch_unscored(limit=25, fresh_hours=48)}
    assert "Fresh item story" in found


async def test_fetch_unscored_excludes_a_story_whose_item_is_outside_the_window(db):
    """A story whose only item is older than the fresh-news window, and has
    no other linked item, must not be returned: it fails both branches of
    the predicate."""
    from app.score import fetch_unscored

    source_id = await _seed_source(db)
    story_id = await _seed_story(db, "Stale item story")
    item_id = await _seed_item(
        db, source_id, published_at=datetime.now(timezone.utc) - timedelta(hours=72)
    )
    await _link_story_item(db, story_id, item_id)

    found = {s["headline"] for s in await fetch_unscored(limit=25, fresh_hours=48)}
    assert "Stale item story" not in found


async def test_fetch_unscored_excludes_a_story_whose_item_has_date_missing(db):
    """A story whose only item carries the date_missing warning must not be
    returned, even if its published_at otherwise looks fresh: the timestamp
    is untrusted."""
    from app.score import fetch_unscored

    source_id = await _seed_source(db)
    story_id = await _seed_story(db, "Date-missing item story")
    item_id = await _seed_item(
        db,
        source_id,
        published_at=datetime.now(timezone.utc) - timedelta(hours=1),
        warnings=["date_missing"],
    )
    await _link_story_item(db, story_id, item_id)

    found = {s["headline"] for s in await fetch_unscored(limit=25, fresh_hours=48)}
    assert "Date-missing item story" not in found


async def test_fetch_unscored_items_exclude_evidence_the_inbox_would_hide(db):
    """A story can qualify through one fresh item while also carrying a
    stale, unrelated item. The scorer must reason over the same evidence the
    Inbox shows the owner, not the full unfiltered link set."""
    from app.score import fetch_unscored

    source_id = await _seed_source(db)
    story_id = await _seed_story(db, "Mixed-evidence story")
    fresh_item = await _seed_item(
        db,
        source_id,
        title="Fresh item",
        published_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    stale_item = await _seed_item(
        db,
        source_id,
        title="Stale item",
        published_at=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    await _link_story_item(db, story_id, fresh_item)
    await _link_story_item(db, story_id, stale_item)

    stories = {s["headline"]: s for s in await fetch_unscored(limit=25, fresh_hours=48)}
    titles = {item["title"] for item in stories["Mixed-evidence story"]["items"]}
    assert titles == {"Fresh item"}
