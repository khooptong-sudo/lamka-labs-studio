import uuid

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
    second = await _seed(db, "Newer, no score")
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
