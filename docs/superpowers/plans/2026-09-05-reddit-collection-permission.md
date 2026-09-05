# Reddit Collection + Permission Outreach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mystery-lane Reddit posts flow into evidence only after the author grants permission, asked by an owner-approved PM sent within hard caps.

**Architecture:** A fourth source kind (`reddit`) reuses poll→normalize→upsert→cluster→score; a `reddit_rights` table gates story-building on `granted`; a sender job moves only owner-approved PMs under a daily cap with dry-run default. Credit rides the existing upload-packet citation path. No auto-comments, no voting, no sentiment judging.

**Tech Stack:** Python worker, PRAW (new dep — declared AND installed in the same change, both venvs), FastAPI, Postgres migration, Next.js queue page, pytest with PRAW patched at the boundary (never live Reddit).

**Spec:** `docs/superpowers/specs/2026-09-05-reddit-collection-permission-design.md`

## Global Constraints

- Tests must not touch live Reddit, the network, or a real DB for unit paths; PRAW is always faked, DB paths use the repo's existing DB-test pattern only where unavoidable (prefer pure + seam tests).
- No send without a `pm_approved` row. No exceptions, no backdoors, no bulk endpoint.
- Credentials live in owner-managed `.env` only (`REDDIT_CLIENT_ID`, `REDDIT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `REDDIT_USER_AGENT`). Code reads env, never stores, never logs, never echoes. Tests use dummy values.
- `REDDIT_OUTREACH_LIVE` defaults to false (dry-run: log the exact PM instead of sending).
- PowerShell 5.1 for shells (no `&&`); pytest as `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`; GUI `npx tsc --noEmit` in `gui/`.
- The working tree may hold unrelated uncommitted work: stage ONLY your files/hunks. Depend ONLY on committed code. Do NOT push (Task 5 pushes once).

---

### Task 1: PRAW dependency + Reddit source kind

**Files:**
- Modify: `worker/pyproject.toml`, `worker/app/sources/__init__.py`, `worker/app/ingest.py` (only if dispatch needs it — `get_source(kind)` + `run_all_sources(kind=...)` already generalize; verify, don't touch), `worker/app/scheduler.py` (poll job)
- Create: `worker/app/sources/reddit.py`
- Test: `worker/tests/test_reddit_sources.py` (new)

**Interfaces:**
- Consumes: `Source`/`RawItem`/`NormalizedItem` (`base.py`), `get_source` registry, `REDDIT_*` env.
- Produces: `RedditSource(Source)` with `kind = "reddit"`; `fetch(source_row) -> list[RawItem]`; `normalize(raw) -> NormalizedItem`; `poll_reddit` JobSpec (60 min).

- [ ] **Step 1: Write the failing tests**

```python
"""Reddit source: allowlist, floors, credential gates. PRAW always faked."""

import pytest


def _source_row(url="https://www.reddit.com/r/UnresolvedMysteries/"):
    from types import SimpleNamespace

    return SimpleNamespace(id="src-1", kind="reddit", url=url, name="UnresolvedMysteries")


async def test_fetch_requires_credentials(monkeypatch):
    from app.sources import reddit as reddit_mod

    for var in ("REDDIT_CLIENT_ID", "REDDIT_SECRET", "REDDIT_USERNAME",
                "REDDIT_PASSWORD", "REDDIT_USER_AGENT"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(Exception, match="REDDIT_CLIENT_ID"):
        await reddit_mod.RedditSource().fetch(_source_row())


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
```

(`date_missing` warning mirrors the existing convention — check `rss.py`
`_entry_published`/warnings for the exact token and match it; if the token
differs, use the real one. Reddit `created_utc` is always present in practice,
so this path is defensive.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_reddit_sources.py -q`
Expected: FAIL with `ImportError` (no `reddit` module / registry entry)

- [ ] **Step 3: Implement `worker/app/sources/reddit.py`**

```python
"""Reddit source kind: weekly-top collection from allowlisted subs, read-only.

Write path (PMs) lives in app/reddit_outreach.py, NOT here — collection must
never be able to send.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

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
        import asyncio

        import praw

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
```

PRAW is sync — `asyncio.to_thread` like the existing OpenAI/Gemini image paths.
`asyncio` top-level import in the module.

Register in `app/sources/__init__.py`: import + `"reddit": RedditSource` +
`__all__`. Scheduler: `poll_reddit` mirroring `poll_rss` (check the exact
wrapper shape in `scheduler.py` lines 73–97 first — same `active_sources` +
`run_all_sources(kind="reddit")` call), `JobSpec(id="poll_reddit", minutes=60,
fn=poll_reddit)` in the specs list. (60 min: weekly-top barely moves; the
existing 10-min jobs stay untouched.)

`pyproject.toml`: add `"praw>=7.8"` to dependencies AND install into the
local venv (`..\\.venv\\Scripts\\python.exe -m pip install "praw>=7.8"`) in
the same task — declaring without installing crash-loops deploys (decision
#84). VPS venv install happens at deploy time, noted in Task 5.

- [ ] **Step 4: Run green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_reddit_sources.py tests/test_ingest.py -q`
Expected: PASS (`test_ingest.py` guards the shared dispatch)

- [ ] **Step 5: Commit**

```bash
git add worker/app/sources/reddit.py worker/app/sources/__init__.py worker/app/scheduler.py worker/pyproject.toml worker/tests/test_reddit_sources.py
git commit -m "Add read-only Reddit source kind with floors and gates"
```

---

### Task 2: Rights table + story-build gate + credit

**Files:**
- Modify: `supabase/migrations/013_reddit_rights.sql` (new), story-build filter (wherever items join into stories — check `ideation.py`/cluster write path first), `worker/app/youtube.py` (`_append_research_sources` reddit author line)
- Test: `worker/tests/test_reddit_rights.py` (new; pure state machine + filter tests with fakes)

**Interfaces:**
- Consumes: Task 1 (`fetch_meta` author/post_id/subreddit on items).
- Produces: `reddit_rights` table; `reddit_usable(urls) -> set[str]` (granted only); credit suffix in upload packet.

- [ ] **Step 1: Write the failing tests**

```python
"""Rights gate: only granted posts reach scripts. No DB, no network."""

STATES = ["candidate", "pm_approved", "sent", "granted", "denied", "expired", "review"]


def test_usable Admits_only_granted():
    pass
```

No — write real tests, no placeholders. Concrete:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_reddit_rights.py -q`
Expected: FAIL with `ImportError` (no `app.reddit_rights`)

- [ ] **Step 3: Implement `worker/app/reddit_rights.py`** (pure, no DB, no network)

```python
"""Reddit permission state machine (pure logic; persistence lives in the table).

States: candidate → pm_approved → sent → granted | denied | expired | review;
review → granted | denied. granted/denied/expired are terminal. Only granted
items may enter evidence — enforced by split_usable at story-build time.
"""

from __future__ import annotations

EXPIRY_DAYS = 30

_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "candidate": ("pm_approved",),
    "pm_approved": ("sent",),
    "sent": ("granted", "denied", "expired", "review"),
    "review": ("granted", "denied"),
    "granted": (),
    "denied": (),
    "expired": (),
}


class RightsError(ValueError):
    """An illegal rights transition was attempted."""


def transition(state: str, to: str) -> str:
    """Move a post right forward. Raises RightsError on any illegal move."""
    if to not in _TRANSITIONS.get(state, ()):
        raise RightsError(f"cannot move reddit right from {state!r} to {to!r}")
    return to


def is_expired(*, sent_days_ago: int) -> bool:
    return sent_days_ago > EXPIRY_DAYS


def split_usable(
    items: list[dict], rights_by_url: dict[str, str]
) -> tuple[list[dict], list[dict]]:
    """Partition story items into (usable, held). Non-reddit items always pass;
    reddit items pass only when granted. Pure — callers supply the rows."""
    usable, held = [], []
    for item in items:
        if item.get("kind") != "reddit":
            usable.append(item)
            continue
        (usable if rights_by_url.get(item.get("url")) == "granted" else held).append(item)
    return usable, held


def credit_suffix(author: str, subreddit: str) -> str:
    """Attribution fragment for packets and narration prompts."""
    if not (author or "").strip() or not (subreddit or "").strip():
        return ""
    return f" (u/{author.strip()} on r/{subreddit.strip()})"
```

- [ ] **Step 4: Migration `supabase/migrations/013_reddit_rights.sql`**

```sql
-- Reddit permission rights (one row per collected post).
CREATE TABLE IF NOT EXISTS reddit_rights (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id     text NOT NULL,
    author      text NOT NULL DEFAULT '',
    subreddit   text NOT NULL DEFAULT '',
    post_url    text NOT NULL UNIQUE,
    state       text NOT NULL DEFAULT 'candidate'
                CHECK (state IN ('candidate','pm_approved','sent','granted','denied','expired','review')),
    pm_text     text NOT NULL DEFAULT '',
    send_count  integer NOT NULL DEFAULT 0,
    sent_at     timestamptz,
    decided_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rights_state ON reddit_rights (state);
CREATE INDEX IF NOT EXISTS idx_rights_author ON reddit_rights (author);
```

(Check `001_init.sql` for the uuid-default idiom — `gen_random_uuid()` needs
pgcrypto; if 001 uses a different default, mirror it exactly.)

- [ ] **Step 5: Wire the gate + credit (no behavior change for non-reddit)**

a) Story-build: wherever clustered items become story evidence, call
`split_usable` with rights loaded for reddit-kind urls in one query
(`SELECT post_url, state FROM reddit_rights WHERE post_url = ANY(%s)`),
drop `held` with a log line (`reddit_items_held`), proceed with `usable`.
Find the exact insertion point by reading the story-write path first
(`ideation.py` cluster commit); do NOT guess the function name.

b) `_append_research_sources` in `youtube.py`: after building each citation
line, look up the granted right for that url (passed in or queried — reuse
whatever `_research_items` already returns; if author/subreddit are not on
the item dicts, extend `_research_items` to carry them from a joined rights
lookup) and append `credit_suffix(author, subreddit)`. Non-reddit lines
byte-identical (suffix is `""`).

c) Narration prompt: the channel prompt for mystery already demands credit;
add the concrete `u/author on r/sub` string to the per-scene evidence context
wherever source attribution already flows (same lookup as (b), no new query).

- [ ] **Step 6: Run green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_reddit_rights.py tests/test_reddit_sources.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add worker/app/reddit_rights.py worker/app/youtube.py supabase/migrations/013_reddit_rights.sql worker/tests/test_reddit_rights.py
git commit -m "Gate story evidence on granted Reddit rights with credit"
```

(Plus whatever story-build file Step 5a touches — add it explicitly, never whole-tree.)

---

### Task 3: Permission queue + sender (caps, kill switch, dry-run)

**Files:**
- Modify: `worker/app/routes.py` (queue + approve + send-now endpoints), scheduler (sender job), GUI (`reddit` queue page + sidebar entry + api client)
- Test: `worker/tests/test_reddit_outreach.py` (new); GUI via tsc

**Interfaces:**
- Consumes: Tasks 1–2 (rights table + transitions), PRAW send.
- Produces: `GET /reddit/rights?state=`, `POST /reddit/approve`, sender job; GUI queue page.

- [ ] **Step 1: Write the failing tests**

```python
"""Outreach: approval-gated sends under caps. PRAW always faked."""


PM_TEMPLATE = (
    "Hi u/{author} — I run an educational YouTube channel and your post "
    "\"{title}\" (r/{sub}) would make a strong segment. May I adapt it into "
    "a narrated video with full on-screen credit to you and a link to your "
    "post? Reply YES and I'll send you the link when it's live, or NO and "
    "I'll never ask again. — Min"
)


async def test_send_refuses_without_approval():
    from app import reddit_outreach

    with pytest.raises(reddit_outreach.OutreachError, match="pm_approved"):
        await reddit_outreach.send_pm(
            sender=object(), post_url="https://r/x/a", author="s",
            subreddit="S", title="T", state="candidate", pm_text="hi",
            dry_run=False,
        )


async def test_send_caps_per_day():
    from app import reddit_outreach

    sent = []

    class FakeMessage:
        pass

    class FakeRedditor:
        def __init__(self, name):
            self.name = name

        def message(self, subject, body):
            sent.append((subject, body))
            return FakeMessage()

    class FakeSender:
        def redditor(self, name):
            return FakeRedditor(name)

    message_id = await reddit_outreach.send_pm(
        sender=FakeSender(), post_url="https://r/x/a", author="s",
        subreddit="S", title="T", state="pm_approved", pm_text="hi",
        dry_run=False,
    )
    assert message_id is not None
    assert sent[0][1] == "hi"  # exact approved text, never reworded
```

(`import pytest`, `async def test_` per repo convention. Daily-cap and
kill-switch/dry-run tests operate one level up, on the sender job with a
faked `send_pm` + faked DB rows — write them against the real sender
signature after reading it; do not guess table-access helpers.)

Daily-cap test shape (DB rows faked at the seam the sender actually uses —
check `reddit_outreach` accessors first, then write; the rule is
`sent_today >= 5 → skip with log, no API call`).

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_reddit_outreach.py -q`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `worker/app/reddit_outreach.py`**

```python
"""Owner-approved Reddit PMs. The only module allowed to message anyone."""

DAILY_CAP = 5
PM_SUBJECT = "Quick question about your post"

PM_TEMPLATE = ( ... exact string from the test above ... )


class OutreachError(ValueError):
    """Outreach refused (state, caps, switch) or failed."""


async def send_pm(*, sender, post_url, author, subreddit, title,
                  state, pm_text, dry_run) -> str | None:
    """Send one approved PM. Returns a message id, or None in dry-run.
    Raises OutreachError unless state == 'pm_approved'."""
    if state != "pm_approved":
        raise OutreachError(
            f"refusing to message {author!r}: post right is {state!r}, not 'pm_approved'"
        )
    if dry_run:
        log.info("reddit_pm_dry_run", author=author, post_url=post_url, pm_text=pm_text)
        return None
    import asyncio

    def call():
        return sender.redditor(author).message(PM_SUBJECT, pm_text)

    message = await asyncio.to_thread(call)
    return str(getattr(message, "id", "") or "")
```

Sender job (`reddit_outreach_job`, every 30 min): read one oldest
`pm_approved` row; count today's `sent`; if `sent_today >= DAILY_CAP` → log
and stop; if `REDDIT_OUTREACH_LIVE` is not `"true"` → dry-run path (log exact
text, leave state); else `send_pm`, set `sent` + `sent_at` + `send_count+1`.
Inbox sweep in the same job: PRAW `inbox.unread()`; any message from an
author with a `sent` row → mark `review` (NO auto-classification of the
reply; the owner reads it). Mark read only after recording. All DB access
behind small named functions the tests patch (`_approved_queue`,
`_sent_today_count`, `_mark_sent`, `_sweep_inbox`) — define them in this
module, not inline SQL in the job.

Routes: `GET /reddit/rights?state=candidate` (list with author/excerpt/url),
`POST /reddit/approve {post_url, pm_text}` (validates non-empty text,
`candidate`→`pm_approved`), `POST /reddit/decide {post_url, verdict}` where
verdict is `granted|denied` from `review` (denied also records the author
opt-out: future collects for that author stay `candidate` forever — enforce
in the collect insert, not just the UI). GUI: `/reddit` queue page (list,
exact-text preview + edit, approve button, state filter), sidebar entry
after Mystery-adjacent Inbox link, api client fns. tsc clean.

- [ ] **Step 4: Run green + typecheck**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_reddit_outreach.py tests/test_reddit_rights.py tests/test_reddit_sources.py -q`
Expected: PASS. Then `cd gui; npx tsc --noEmit`, clean.

- [ ] **Step 5: Commit**

```bash
git add worker/app/reddit_outreach.py worker/app/routes.py worker/app/scheduler.py gui/src/app/reddit/page.tsx gui/src/components/Sidebar.tsx gui/src/lib/api.ts worker/tests/test_reddit_outreach.py
git commit -m "Add owner-approved Reddit PM outreach under caps"
```

---

### Task 4: Seeds (subs + allowlist) — local + VPS

**Files:**
- Modify: `supabase/migrations/014_reddit_seeds.sql` (new)

- [ ] **Step 1: Write the migration**

```sql
-- Reddit allowlist seeds (verified live at spec time: public, active).
INSERT INTO sources (kind, url, name, market, active, poll_minutes) VALUES
    ('reddit', 'https://www.reddit.com/r/UnresolvedMysteries/', 'r/UnresolvedMysteries', 'US', true, 60),
    ('reddit', 'https://www.reddit.com/r/TrueCrime/',           'r/TrueCrime',           'US', true, 60)
ON CONFLICT DO NOTHING;
```

(Re-verify both subs resolve publicly at implementation time; drop any that
doesn't with a one-line plan deviation note in the commit message.)

- [ ] **Step 2: Apply locally, verify rows**

Run: `Get-Content supabase/migrations/014_reddit_seeds.sql | docker exec -i fce-db psql -U postgres -d fce -v ON_ERROR_STOP=1`
Expected: `INSERT 0 2`. Then row check.

- [ ] **Step 3: Commit, push, pull VPS, apply, install PRAW there**

```bash
git add supabase/migrations/014_reddit_seeds.sql
git commit -m "Seed Reddit allowlist subs"
git push
```

VPS (SSH, batch-safe commands only): pull, apply the file with
`sudo -u fce psql -p 5433 -d fce -v ON_ERROR_STOP=1 -f <path>`,
`sudo -u fce /opt/fce/.venv/bin/pip install "praw>=7.8"`,
restart worker, `/health` green. (Credentials stay owner-managed: the poll
refuses loudly until `.env` carries them — no key material in this task.)

- [ ] **Step 4: Commit nothing further** (deploy produces no repo diff)

---

### Task 5: Full verification + record + push

**Files:**
- Modify: `PROGRESS.md` (decision #87)

- [ ] **Step 1: Run the affected suites**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_reddit_sources.py tests/test_reddit_rights.py tests/test_reddit_outreach.py tests/test_ingest.py tests/test_youtube.py tests/test_routes_x.py -q`
Expected: PASS (DB-backed tests need local Postgres; without it they error — pre-existing, unrelated)

- [ ] **Step 2: Record the decision in PROGRESS.md**

```
| 87 | Reddit sourcing behind granted-only rights + approved PMs | reddit | New source kind with floors; rights table gates evidence; 5/day caps, dry-run default, kill switch; credit in narration + packet. PRAW declared and installed with the change. |
```

- [ ] **Step 3: Commit and push**

```bash
git add PROGRESS.md
git commit -m "Record Reddit sourcing decision"
git push
```
