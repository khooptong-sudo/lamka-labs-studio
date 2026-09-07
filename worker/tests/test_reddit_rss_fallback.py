"""Reddit RSS fallback: credential-free collection via the public top/week Atom feed.

PROGRESS.md #90. The network layer (httpx) is always faked; no live Reddit
calls in tests.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.sources import reddit as reddit_mod
from app.sources.base import SourceError

OLD = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
RECENT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
LONG_TEXT = "word " * 60  # 300 chars, above RSS_MIN_TEXT_CHARS

ATOM = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>top scoring links : UnresolvedMysteries</title>
  <entry>
    <title>The cold case of Doe</title>
    <link href="https://www.reddit.com/r/UnresolvedMysteries/comments/abc123/the_cold_case_of_doe/" />
    <updated>{OLD}</updated>
    <author><name>sleuth</name></author>
    <content type="html">&lt;p&gt;{LONG_TEXT}&lt;/p&gt;</content>
  </entry>
  <entry>
    <title>Too fresh to have settled</title>
    <link href="https://www.reddit.com/r/UnresolvedMysteries/comments/def456/too_fresh/" />
    <updated>{RECENT}</updated>
    <author><name>newposter</name></author>
    <content type="html">&lt;p&gt;{LONG_TEXT}&lt;/p&gt;</content>
  </entry>
  <entry>
    <title>Thin media-only post</title>
    <link href="https://www.reddit.com/r/UnresolvedMysteries/comments/ghi789/thin/" />
    <updated>{OLD}</updated>
    <author><name>picposter</name></author>
    <content type="html">&lt;p&gt;just a link&lt;/p&gt;</content>
  </entry>
</feed>
"""


def _source_row():
    from types import SimpleNamespace

    return SimpleNamespace(id="src-1", kind="reddit",
                           url="https://www.reddit.com/r/UnresolvedMysteries/",
                           name="UnresolvedMysteries")


class _Resp:
    def __init__(self, status, text="", headers=None):
        self.status_code = status
        self.content = text.encode()
        self.headers = headers or {}


def _fake_client(monkeypatch, responses):
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, **kwargs):
            assert "Mozilla/5.0" in kwargs["headers"]["user-agent"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            assert "/r/UnresolvedMysteries/top/.rss" in url
            assert "t=week" in url
            resp = responses[min(calls["n"], len(responses) - 1)]
            calls["n"] += 1
            return resp

    monkeypatch.setattr(reddit_mod.httpx, "AsyncClient", FakeClient)
    return calls


async def test_rss_fallback_collects_qualifying_post_only(monkeypatch):
    _fake_client(monkeypatch, [_Resp(200, ATOM)])
    raws = await reddit_mod.RedditSource()._fetch_via_rss(_source_row(), "UnresolvedMysteries")

    assert [r.raw_title for r in raws] == ["The cold case of Doe"]
    raw = raws[0]
    assert raw.fetch_meta["post_id"] == "abc123"
    assert raw.fetch_meta["author"] == "sleuth"
    assert raw.fetch_meta["subreddit"] == "UnresolvedMysteries"
    assert raw.fetch_meta["score"] is None
    assert raw.fetch_meta["collection_mode"] == "rss"
    assert raw.raw_url.endswith("/comments/abc123/the_cold_case_of_doe/")


async def test_rss_fallback_retries_429_then_succeeds(monkeypatch):
    calls = _fake_client(
        monkeypatch,
        [_Resp(429, headers={"retry-after": "0"}), _Resp(200, ATOM)],
    )
    raws = await reddit_mod.RedditSource()._fetch_via_rss(_source_row(), "UnresolvedMysteries")
    assert calls["n"] == 2
    assert len(raws) == 1


async def test_rss_fallback_gives_up_after_third_429(monkeypatch):
    calls = _fake_client(monkeypatch, [_Resp(429, headers={"retry-after": "0"})])
    with pytest.raises(SourceError, match="429"):
        await reddit_mod.RedditSource()._fetch_via_rss(_source_row(), "UnresolvedMysteries")
    assert calls["n"] == 3


async def test_rss_fallback_raises_on_other_errors(monkeypatch):
    _fake_client(monkeypatch, [_Resp(403)])
    with pytest.raises(SourceError, match="403"):
        await reddit_mod.RedditSource()._fetch_via_rss(_source_row(), "UnresolvedMysteries")


async def test_rss_fallback_rejects_empty_200_body(monkeypatch):
    """Reddit answers some throttled clients with an empty 200 — that must be
    a loud not_a_feed error (health bookkeeping), not a silent empty poll."""
    _fake_client(monkeypatch, [_Resp(200, "")])
    with pytest.raises(SourceError, match="not_a_feed"):
        await reddit_mod.RedditSource()._fetch_via_rss(_source_row(), "UnresolvedMysteries")


async def test_rss_normalize_flags_score_unavailable(monkeypatch):
    _fake_client(monkeypatch, [_Resp(200, ATOM)])
    source = reddit_mod.RedditSource()
    raws = await source._fetch_via_rss(_source_row(), "UnresolvedMysteries")
    item = await source.normalize(raws[0])
    assert "score_unavailable" in item.warnings
    assert "date_missing" not in item.warnings
