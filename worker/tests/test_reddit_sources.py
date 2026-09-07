"""Reddit source: allowlist, floors, mode gates. PRAW always faked."""

import pytest

CREDENTIAL_VARS = ("REDDIT_CLIENT_ID", "REDDIT_SECRET", "REDDIT_USERNAME",
                   "REDDIT_PASSWORD", "REDDIT_USER_AGENT")


def _source_row(url="https://www.reddit.com/r/UnresolvedMysteries/"):
    from types import SimpleNamespace

    return SimpleNamespace(id="src-1", kind="reddit", url=url, name="UnresolvedMysteries")


def _clear_creds(monkeypatch):
    for var in CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)


async def test_missing_credentials_selects_rss_mode(monkeypatch):
    """PROGRESS.md #90: no creds no longer fails the poll — it falls back
    to the public RSS feed (network layer tested in test_reddit_rss_fallback)."""
    from app.sources import reddit as reddit_mod

    _clear_creds(monkeypatch)
    assert reddit_mod._collection_mode() == "rss"


def test_credentials_present_selects_praw_mode(monkeypatch):
    from app.sources import reddit as reddit_mod

    for var in CREDENTIAL_VARS:
        monkeypatch.setenv(var, "x")
    monkeypatch.delenv("REDDIT_COLLECTION_FORCE_RSS", raising=False)
    assert reddit_mod._collection_mode() == "praw"


def test_force_rss_overrides_credentials(monkeypatch):
    from app.sources import reddit as reddit_mod

    for var in CREDENTIAL_VARS:
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("REDDIT_COLLECTION_FORCE_RSS", "true")
    assert reddit_mod._collection_mode() == "rss"


def test_kind_registered():
    from app.sources import get_source

    assert get_source("reddit").kind == "reddit"


async def test_fetch_collects_qualifying_posts(monkeypatch):
    from types import SimpleNamespace

    from app.sources import reddit as reddit_mod

    for var, val in (("REDDIT_CLIENT_ID", "id"), ("REDDIT_SECRET", "s"),
                     ("REDDIT_USERNAME", "u"), ("REDDIT_PASSWORD", "p"),
                     ("REDDIT_USER_AGENT", "ua")):
        monkeypatch.setenv(var, val)
    monkeypatch.delenv("REDDIT_COLLECTION_FORCE_RSS", raising=False)

    good = SimpleNamespace(id="p1", title="The case", author=SimpleNamespace(name="sleuth"),
                           permalink="/r/x/comments/p1", selftext="long text here",
                           created_utc=1_750_000_000.0, score=500, over_18=False,
                           is_self=True, link_flair_text=None, url="https://x/p1")
    low_score = SimpleNamespace(id="p2", title="Weak", author=SimpleNamespace(name="a"),
                                permalink="/r/x/comments/p2", selftext="t",
                                created_utc=1_750_000_000.0, score=12, over_18=False,
                                is_self=True, link_flair_text=None, url="https://x/p2")
    media = SimpleNamespace(id="p3", title="Pic", author=SimpleNamespace(name="b"),
                            permalink="/r/x/comments/p3", selftext="",
                            created_utc=1_750_000_000.0, score=900, over_18=False,
                            is_self=False, link_flair_text=None, url="https://img/pic.jpg")

    class FakeSub:
        def top(self, time_filter="week", limit=50):
            assert time_filter == "week"
            return [good, low_score, media]

    class FakeReddit:
        def __init__(self, **kwargs):
            assert kwargs["username"] == "u"
        def subreddit(self, name):
            assert name == "UnresolvedMysteries"
            return FakeSub()

    monkeypatch.setattr(reddit_mod.praw, "Reddit", FakeReddit)
    raws = await reddit_mod.RedditSource().fetch(_source_row())
    assert [r.raw_title for r in raws] == ["The case"]
    assert raws[0].fetch_meta["author"] == "sleuth"
    assert raws[0].fetch_meta["post_id"] == "p1"


async def test_normalize_builds_canonical_item():
    from app.sources import reddit as reddit_mod

    raw = reddit_mod.RawItem(
        source_id="src-1", raw_title="  The case ",
        raw_url="https://www.reddit.com/r/x/comments/p1/",
        raw_published_at=None, raw_html_or_xml="body text",
        fetch_meta={"author": "sleuth", "post_id": "p1",
                    "subreddit": "UnresolvedMysteries"},
    )
    item = await reddit_mod.RedditSource().normalize(raw)
    assert item.title == "The case"
    assert item.full_text == "body text"
    assert "date_missing" in item.warnings  # Part II §3.3 pattern: warn, don't block
