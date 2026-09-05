"""Reddit source kind: weekly-top collection from allowlisted subs, read-only.

Write path (PMs) lives in app/reddit_outreach.py, NOT here — collection must
never be able to send.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import praw

from app.sources.base import NormalizedItem, RawItem, Source, SourceError

MIN_SCORE = 100
MIN_AGE_DAYS = 7
FETCH_LIMIT = 50

CREDENTIAL_VARS = ("REDDIT_CLIENT_ID", "REDDIT_SECRET", "REDDIT_USERNAME",
                   "REDDIT_PASSWORD", "REDDIT_USER_AGENT")


def _credentials() -> dict[str, str]:
    missing = [v for v in CREDENTIAL_VARS if not os.environ.get(v, "").strip()]
    if missing:
        raise SourceError(f"reddit credentials missing: {', '.join(missing)} (set them in .env)")
    return {v: os.environ[v].strip() for v in CREDENTIAL_VARS}


def _subreddit_from_url(url: str) -> str:
    """https://www.reddit.com/r/Name/... -> Name. Raises SourceError if unparsable."""
    import re

    match = re.search(r"reddit\.com/r/([A-Za-z0-9_]+)", url or "")
    if not match:
        raise SourceError(f"reddit source url is not a subreddit: {url!r}")
    return match.group(1)


class RedditSource(Source):
    kind = "reddit"

    async def fetch(self, source_row) -> list[RawItem]:
        creds = _credentials()
        sub_name = _subreddit_from_url(getattr(source_row, "url", ""))
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
                            "subreddit": sub_name, "score": int(getattr(post, "score", 0) or 0)},
            ))
        return raws

    async def normalize(self, raw: RawItem) -> NormalizedItem:
        meta = raw.fetch_meta or {}
        warnings = []
        if raw.raw_published_at is None:
            warnings.append("date_missing")
        return NormalizedItem.build(
            source_id=raw.source_id,
            title=raw.raw_title,
            url=raw.raw_url,
            published_at=raw.raw_published_at,
            full_text=raw.raw_html_or_xml or None,
            warnings=warnings,
        )
