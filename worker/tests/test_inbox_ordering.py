import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.integration


async def _seed(db, headline: str) -> uuid.UUID:
    from app.db import _fetchval

    async with db.connection() as conn:
        return await _fetchval(
            conn,
            "INSERT INTO stories (headline, status) VALUES (%s, 'inbox') RETURNING id",
            headline,
        )


async def _seed_source(db) -> uuid.UUID:
    from app.db import _fetchval

    async with db.connection() as conn:
        return await _fetchval(
            conn,
            "INSERT INTO sources (kind, url, name, market, active, poll_minutes) "
            "VALUES ('rss', 'https://test.example/feed', 'TEST_source', 'IN', true, 30) "
            "RETURNING id",
        )


async def _seed_item(db, source_id: uuid.UUID, *, published_at: datetime) -> uuid.UUID:
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


async def _link_story_item(db, story_id: uuid.UUID, item_id: uuid.UUID) -> None:
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO story_items (story_id, item_id) VALUES (%s, %s)",
            (story_id, item_id),
        )


async def test_rows_carry_the_scoring_columns(db):
    from app.db import get_pending_stories
    from app.score import write_score

    story_id = await _seed(db, "Has a score")
    await write_score(story_id, {
        "score": 61.0, "angle": "An angle",
        "vertical": "macro", "content_archetype": "explainer",
    })

    row = next(s for s in await get_pending_stories(fresh_hours=48) if s["id"] == story_id)
    assert row["score"] == 61.0
    assert row["angle"] == "An angle"
    assert row["vertical"] == "macro"
    assert row["content_archetype"] == "explainer"


async def test_default_ordering_is_unchanged(db):
    """The films page depends on this. Changing the shared default would
    silently reorder the working video queue."""
    from app.db import get_pending_stories
    from app.score import write_score

    first = await _seed(db, "Older, high score")
    await _seed(db, "Newer, no score")
    await write_score(first, {
        "score": 99.0, "angle": "An angle",
        "vertical": "macro", "content_archetype": "explainer",
    })

    headlines = [s["headline"] for s in await get_pending_stories(fresh_hours=48)]
    # Newest first, regardless of score.
    assert headlines.index("Newer, no score") < headlines.index("Older, high score")


async def test_score_ordering_puts_the_highest_score_first(db):
    from app.db import get_pending_stories
    from app.score import write_score

    low = await _seed(db, "Low score")
    high = await _seed(db, "High score")
    await write_score(low, {
        "score": 10.0, "angle": "a", "vertical": "macro", "content_archetype": "explainer",
    })
    await write_score(high, {
        "score": 90.0, "angle": "b", "vertical": "macro", "content_archetype": "explainer",
    })

    headlines = [
        s["headline"] for s in await get_pending_stories(fresh_hours=48, order="score")
    ]
    assert headlines.index("High score") < headlines.index("Low score")


async def test_score_ordering_puts_unscored_stories_last(db):
    from app.db import get_pending_stories
    from app.score import write_score

    scored = await _seed(db, "Scored")
    await _seed(db, "Unscored")
    await write_score(scored, {
        "score": 5.0, "angle": "a", "vertical": "macro", "content_archetype": "explainer",
    })

    headlines = [
        s["headline"] for s in await get_pending_stories(fresh_hours=48, order="score")
    ]
    assert headlines.index("Scored") < headlines.index("Unscored")


async def test_an_unknown_order_is_rejected(db):
    from app.db import get_pending_stories

    with pytest.raises(ValueError, match="unknown order"):
        await get_pending_stories(fresh_hours=48, order="'; DROP TABLE stories--")


async def test_recent_sorts_by_source_date_while_score_ordering_bypasses_it(db):
    """Closes two gaps at once, both invisible to the other tests here:

    1. Every other test seeds stories with no linked items, so the
       created_at-vs-published_at post-query sort always falls into its
       `else story["created_at"]` branch. The `published_at` branch — the
       entire reason that sort exists — is otherwise never exercised.
    2. Nothing asserts that the 'score' ordering path skips that sort. A
       story created first but source-dated recently (A), and a story
       created second but source-dated older (B), only disagree on order
       between 'recent' (source-date order: A before B) and 'score' (SQL
       order: whichever has the higher score) if the post-query sort truly
       only runs for 'recent'.

    published_at values are hours apart (not seconds) and set explicitly,
    so this does not depend on two `created_at` calls landing on distinct
    Postgres `now()` values.
    """
    from app.db import get_pending_stories
    from app.score import write_score

    headline_a = "A - created first, source-dated recent"
    headline_b = "B - created second, source-dated old"

    source_id = await _seed_source(db)
    now = datetime.now(timezone.utc)

    # A: created first, but its source item is recent (2 hours old).
    story_a = await _seed(db, headline_a)
    item_a = await _seed_item(db, source_id, published_at=now - timedelta(hours=2))
    await _link_story_item(db, story_a, item_a)

    # B: created second, but its source item is much older (40 hours),
    # still inside the 48h fresh window.
    story_b = await _seed(db, headline_b)
    item_b = await _seed_item(db, source_id, published_at=now - timedelta(hours=40))
    await _link_story_item(db, story_b, item_b)

    # 'recent': sort must key on published_at, not created_at or insertion
    # order. If it used created_at, B (created later) would come first.
    recent_headlines = [
        s["headline"] for s in await get_pending_stories(fresh_hours=48)
    ]
    assert recent_headlines.index(headline_a) < recent_headlines.index(headline_b)

    # Score B higher than A, so SQL ordering wants B first.
    await write_score(story_a, {
        "score": 10.0, "angle": "a", "vertical": "macro", "content_archetype": "explainer",
    })
    await write_score(story_b, {
        "score": 90.0, "angle": "b", "vertical": "macro", "content_archetype": "explainer",
    })

    # 'score': if the recent-sort still ran, A's newer published_at would
    # float it back above B, silently discarding the SQL ORDER BY.
    score_headlines = [
        s["headline"] for s in await get_pending_stories(fresh_hours=48, order="score")
    ]
    assert score_headlines.index(headline_b) < score_headlines.index(headline_a)
