"""Rights gate: only granted posts reach scripts. No DB, no network."""

import pytest


def _row(url, state, author="sleuth", sub="UnresolvedMysteries"):
    return {"post_url": url, "author": author, "subreddit": sub, "state": state}


def test_allowed_transitions():
    from app.reddit_rights import transition

    assert transition("candidate", "pm_approved") == "pm_approved"
    assert transition("pm_approved", "sent") == "sent"
    assert transition("sent", "granted") == "granted"
    assert transition("sent", "denied") == "denied"
    assert transition("sent", "expired") == "expired"
    assert transition("sent", "review") == "review"
    assert transition("review", "granted") == "granted"
    assert transition("review", "denied") == "denied"


def test_terminal_states_reject_everything():
    from app.reddit_rights import RightsError, transition

    for state in ("granted", "denied", "expired"):
        with pytest.raises(RightsError):
            transition(state, "sent")


def test_candidate_cannot_skip_approval():
    from app.reddit_rights import RightsError, transition

    with pytest.raises(RightsError):
        transition("candidate", "sent")
    with pytest.raises(RightsError):
        transition("candidate", "granted")


def test_expiry_rule():
    from app.reddit_rights import is_expired

    assert is_expired(sent_days_ago=31) is True
    assert is_expired(sent_days_ago=29) is False


def test_story_filter_admits_only_granted_reddit_items():
    from app.reddit_rights import split_usable

    items = [
        {"url": "https://r/x/a", "kind": "rss"},
        {"url": "https://r/x/b", "kind": "reddit"},
        {"url": "https://r/x/c", "kind": "reddit"},
    ]
    rights = {"https://r/x/b": "granted", "https://r/x/c": "candidate"}
    usable, held = split_usable(items, rights)
    assert [i["url"] for i in usable] == ["https://r/x/a", "https://r/x/b"]
    assert [i["url"] for i in held] == ["https://r/x/c"]


def test_credit_line_names_author_and_sub():
    from app.reddit_rights import credit_suffix

    assert credit_suffix("sleuth", "UnresolvedMysteries") == " (u/sleuth on r/UnresolvedMysteries)"
    assert credit_suffix("", "X") == ""


@pytest.mark.integration
async def test_inbox_admits_granted_but_hides_candidate_reddit_stories(db):
    """The FRESH_WINDOW_PREDICATE reddit branch: old posts surface only when granted."""
    from datetime import datetime, timedelta, timezone

    from app.db import _fetchval, get_pending_stories

    async with db.connection() as conn:
        source_id = await _fetchval(
            conn,
            "INSERT INTO sources (kind, url, name, market, active, poll_minutes) "
            "VALUES ('reddit', 'https://www.reddit.com/r/UnresolvedMysteries/', 'TEST_reddit', 'US', true, 60) "
            "RETURNING id",
        )
        old = datetime.now(timezone.utc) - timedelta(days=10)
        granted_story = await _fetchval(
            conn, "INSERT INTO stories (headline, status) VALUES (%s, 'inbox') RETURNING id",
            "Granted mystery",
        )
        candidate_story = await _fetchval(
            conn, "INSERT INTO stories (headline, status) VALUES (%s, 'inbox') RETURNING id",
            "Candidate mystery",
        )
        granted_item = await _fetchval(
            conn,
            "INSERT INTO items (source_id, title, url, published_at, hash, warnings) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb) RETURNING id",
            source_id, "Granted post", "https://www.reddit.com/r/x/comments/g/",
            old, "ghash", "[]",
        )
        candidate_item = await _fetchval(
            conn,
            "INSERT INTO items (source_id, title, url, published_at, hash, warnings) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb) RETURNING id",
            source_id, "Candidate post", "https://www.reddit.com/r/x/comments/c/",
            old, "chash", "[]",
        )
        await conn.execute(
            "INSERT INTO story_items (story_id, item_id) VALUES (%s, %s)",
            (granted_story, granted_item),
        )
        await conn.execute(
            "INSERT INTO story_items (story_id, item_id) VALUES (%s, %s)",
            (candidate_story, candidate_item),
        )
        await conn.execute(
            "INSERT INTO reddit_rights (post_id, author, subreddit, post_url, state) "
            "VALUES (%s, %s, %s, %s, %s)",
            ("g", "sleuth", "UnresolvedMysteries",
             "https://www.reddit.com/r/x/comments/g/", "granted"),
        )
        await conn.execute(
            "INSERT INTO reddit_rights (post_id, author, subreddit, post_url, state) "
            "VALUES (%s, %s, %s, %s, %s)",
            ("c", "sleuth", "UnresolvedMysteries",
             "https://www.reddit.com/r/x/comments/c/", "candidate"),
        )

    visible = {str(s["id"]) for s in await get_pending_stories(fresh_hours=48)}
    assert str(granted_story) in visible
    assert str(candidate_story) not in visible
