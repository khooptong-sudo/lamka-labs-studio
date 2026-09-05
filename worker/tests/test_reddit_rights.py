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
