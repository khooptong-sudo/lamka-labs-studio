"""Reddit source kind: weekly-top collection from allowlisted subs, read-only.

Write path (PMs) lives in app/reddit_outreach.py, NOT here — collection must
never be able to send.

Two collection modes, chosen per poll:
- praw: all five REDDIT_* credentials in .env → real scores; the MIN_SCORE
  gate applies.
- rss:  credentials absent (or REDDIT_COLLECTION_FORCE_RSS=true) → the
  public /top/.rss Atom feed: no account, login, cookies, or API key.
  Feeds carry no score and no NSFW flag, so the score gate is replaced by
  top-of-week rank order plus a substance floor, and this mode is only
  seeded against the SFW allowlist subs. See PROGRESS.md #90.

Either way every collected post becomes a candidate rights row and only
owner-approved (granted) posts reach story building — the human gate is
constant across modes.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone

import feedparser
import httpx
import praw

from app.sources.base import NormalizedItem, RawItem, Source, SourceError

MIN_SCORE = 100
MIN_AGE_DAYS = 7
FETCH_LIMIT = 50
RSS_FETCH_LIMIT = 25
RSS_MIN_TEXT_CHARS = 200
FEED_TIMEOUT = 30.0

# Reddit 403s non-browser user-agents on the public feeds.
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

CREDENTIAL_VARS = ("REDDIT_CLIENT_ID", "REDDIT_SECRET", "REDDIT_USERNAME",
                   "REDDIT_PASSWORD", "REDDIT_USER_AGENT")


def _collection_mode() -> str:
    """praw when fully credentialed, rss otherwise. Force-flag wins."""
    if os.environ.get("REDDIT_COLLECTION_FORCE_RSS", "").strip().lower() == "true":
        return "rss"
    missing = [v for v in CREDENTIAL_VARS if not os.environ.get(v, "").strip()]
    return "praw" if not missing else "rss"


def _credentials() -> dict[str, str]:
    missing = [v for v in CREDENTIAL_VARS if not os.environ.get(v, "").strip()]
    if missing:
        raise SourceError(f"reddit credentials missing: {', '.join(missing)} (set them in .env)")
    return {v: os.environ[v].strip() for v in CREDENTIAL_VARS}


def _subreddit_from_url(url: str) -> str:
    """https://www.reddit.com/r/Name/... -> Name. Raises SourceError if unparsable."""
    match = re.search(r"reddit\.com/r/([A-Za-z0-9_]+)", url or "")
    if not match:
        raise SourceError(f"reddit source url is not a subreddit: {url!r}")
    return match.group(1)


def _post_id_from_permalink(url: str) -> str:
    match = re.search(r"/comments/([A-Za-z0-9]+)", url or "")
    return match.group(1) if match else ""


def _entry_text(entry) -> str:
    """Selftext/summary of a feedparser entry, tags stripped."""
    import html as html_mod

    value = ""
    if entry.get("content"):
        value = entry["content"][0].get("value", "")
    if not value:
        value = entry.get("summary", "")
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html_mod.unescape(text)).strip()


def _entry_published_ts(entry) -> float | None:
    import time as time_mod

    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            return time_mod.mktime(st)
    return None


class RedditSource(Source):
    kind = "reddit"

    async def fetch(self, source_row) -> list[RawItem]:
        sub_name = _subreddit_from_url(getattr(source_row, "url", ""))
        if _collection_mode() == "praw":
            return await self._fetch_via_praw(source_row, sub_name)
        return await self._fetch_via_rss(source_row, sub_name)

    async def _fetch_via_praw(self, source_row, sub_name: str) -> list[RawItem]:
        creds = _credentials()
        now = datetime.now(timezone.utc).timestamp()

        def call():
            reddit = praw.Reddit(
                client_id=creds["REDDIT_CLIENT_ID"],
                client_secret=creds["REDDIT_SECRET"],
                username=creds["REDDIT_USERNAME"],
                password=creds["REDDIT_PASSWORD"],
                user_agent=creds["REDDIT_USER_AGENT"],
            )
            return list(reddit.subreddit(sub_name).top(time_filter="week", limit=FETCH_LIMIT))

        submissions = await asyncio.to_thread(call)
        raws: list[RawItem] = []
        for post in submissions:
            author = getattr(getattr(post, "author", None), "name", None) or "[deleted]"
            created = getattr(post, "created_utc", None)
            if created is not None and now - float(created) < MIN_AGE_DAYS * 86400:
                continue
            if int(getattr(post, "score", 0) or 0) < MIN_SCORE:
                continue
            if not getattr(post, "is_self", False) and not (getattr(post, "selftext", "") or "").strip():
                continue  # media-only, no usable text
            if getattr(post, "over_18", False):
                continue  # keep the lane brand-safe; revisit deliberately
            raws.append(RawItem(
                source_id=str(getattr(source_row, "id", "")),
                raw_title=str(getattr(post, "title", "") or ""),
                raw_url=f"https://www.reddit.com{getattr(post, 'permalink', '') or ''}",
                raw_published_at=datetime.fromtimestamp(float(created), tz=timezone.utc) if created else None,
                raw_html_or_xml=str(getattr(post, "selftext", "") or "")[:4000],
                fetch_meta={"author": author, "post_id": str(getattr(post, "id", "")),
                            "subreddit": sub_name, "score": int(getattr(post, "score", 0) or 0),
                            "collection_mode": "praw"},
            ))
        return raws

    async def _fetch_via_rss(self, source_row, sub_name: str) -> list[RawItem]:
        """Credential-free collection via the public top/week Atom feed.

        The feed has no scores: top-of-week rank order (plus
        RSS_FETCH_LIMIT) is the quality proxy, and RSS_MIN_TEXT_CHARS is
        the substance floor. The candidate→granted rights gate downstream
        is unchanged and remains the real filter.
        """
        feed_url = (f"https://www.reddit.com/r/{sub_name}/top/.rss"
                    f"?t=week&limit={RSS_FETCH_LIMIT}")
        body = await self._get(feed_url)
        head = body.lstrip()[:512].lower()
        if not (head.startswith(b"<?xml") or head.startswith(b"<feed") or head.startswith(b"<rss")):
            raise SourceError("not_a_feed")
        parsed = feedparser.parse(body)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise SourceError(f"reddit rss parse failed: {parsed.bozo_exception}")

        now = datetime.now(timezone.utc).timestamp()
        raws: list[RawItem] = []
        for entry in parsed.entries:
            link = str(entry.get("link", "") or "")
            post_id = _post_id_from_permalink(link)
            if not post_id:
                continue
            published = _entry_published_ts(entry)
            if published is not None and now - published < MIN_AGE_DAYS * 86400:
                continue  # settling floor, same as praw mode
            text = _entry_text(entry)
            if len(text) < RSS_MIN_TEXT_CHARS:
                continue
            author_detail = entry.get("author_detail") or {}
            author = str(getattr(entry, "author", None) or author_detail.get("name") or "[deleted]")
            raws.append(RawItem(
                source_id=str(getattr(source_row, "id", "")),
                raw_title=str(entry.get("title", "") or ""),
                raw_url=link,
                raw_published_at=(datetime.fromtimestamp(published, tz=timezone.utc)
                                  if published else None),
                raw_html_or_xml=text[:4000],
                fetch_meta={"author": author, "post_id": post_id,
                            "subreddit": sub_name, "score": None,
                            "collection_mode": "rss"},
            ))
        return raws

    async def _get(self, url: str) -> bytes:
        """One feed GET; retries a 429 twice honouring Retry-After (cap 60s)."""
        async with httpx.AsyncClient(
            timeout=FEED_TIMEOUT, follow_redirects=True,
            headers={"user-agent": BROWSER_UA},
        ) as client:
            for attempt in range(3):
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.content
                if resp.status_code == 429 and attempt < 2:
                    retry_after = resp.headers.get("retry-after", "")
                    wait = float(retry_after) if retry_after.isdigit() else 30.0
                    await asyncio.sleep(min(wait, 60.0))
                    continue
                raise SourceError(f"reddit rss http {resp.status_code}")
        raise SourceError("reddit rss unreachable")

    async def normalize(self, raw: RawItem) -> NormalizedItem:
        meta = raw.fetch_meta or {}
        warnings = []
        if raw.raw_published_at is None:
            warnings.append("date_missing")
        if meta.get("collection_mode") == "rss":
            warnings.append("score_unavailable")
        return NormalizedItem.build(
            source_id=raw.source_id,
            title=raw.raw_title,
            url=raw.raw_url,
            published_at=raw.raw_published_at,
            full_text=raw.raw_html_or_xml or None,
            warnings=warnings,
        )
