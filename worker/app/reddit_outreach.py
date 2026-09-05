"""Owner-approved Reddit PMs. The only module allowed to message anyone.

Collection (app/sources/reddit.py) is read-only by construction; this module
owns every write to Reddit: at most one PM per owner-approved post, sent via
PRAW under a daily cap, behind a kill switch, dry-run by default.

No send without a `pm_approved` row. No exceptions, no backdoors, no bulk
endpoint — send_pm raises unless state == 'pm_approved'.

Denied opts the author out forever: approve_right refuses their posts, the
sender queue skips them, and ensure_candidate_row (the collect insert) pins
their future posts at `candidate`.
"""

from __future__ import annotations

import asyncio
import os

import structlog

from app.reddit_rights import RightsError, transition

log = structlog.get_logger()

DAILY_CAP = 5
PM_SUBJECT = "Quick question about your post"

PM_TEMPLATE = (
    "Hi u/{author} — I run an educational YouTube channel and your post "
    "\"{title}\" (r/{sub}) would make a strong segment. May I adapt it into "
    "a narrated video with full on-screen credit to you and a link to your "
    "post? Reply YES and I'll send you the link when it's live, or NO and "
    "I'll never ask again. — Min"
)

CREDENTIAL_VARS = ("REDDIT_CLIENT_ID", "REDDIT_SECRET", "REDDIT_USERNAME",
                   "REDDIT_PASSWORD", "REDDIT_USER_AGENT")

STATES = ("candidate", "pm_approved", "sent", "granted", "denied", "expired", "review")


class OutreachError(ValueError):
    """Outreach refused (state, caps, switch) or failed."""


class NotFoundError(OutreachError):
    """No rights row for that post_url."""


def render_pm(*, author: str, title: str, sub: str) -> str:
    """Fill the owner-approved template. The per-send text stays editable by
    the owner; this is the default draft."""
    return PM_TEMPLATE.format(author=author, title=title, sub=sub)


def _is_live() -> bool:
    """Kill switch: only the literal string "true" sends. Default is dry-run."""
    return os.environ.get("REDDIT_OUTREACH_LIVE", "false").strip().lower() == "true"


def validate_approve(row: dict | None, pm_text: str, opted_out: bool) -> str:
    """Pure approval gate. Returns the exact text to store, or raises."""
    if row is None:
        raise NotFoundError("no reddit right for that post_url")
    text = (pm_text or "").strip()
    if not text:
        raise OutreachError("pm_text must be non-empty (owner approves the exact text)")
    if opted_out:
        raise OutreachError(
            f"author {row.get('author')!r} opted out; post stays candidate forever"
        )
    try:
        transition(row.get("state", ""), "pm_approved")
    except RightsError as exc:
        raise OutreachError(str(exc)) from exc
    return text


def validate_decide(row: dict | None, verdict: str) -> str:
    """Pure decide gate (owner reads the reply, then grants or denies)."""
    if row is None:
        raise NotFoundError("no reddit right for that post_url")
    if verdict not in ("granted", "denied"):
        raise OutreachError(f"verdict must be granted|denied, got {verdict!r}")
    try:
        transition(row.get("state", ""), verdict)
    except RightsError as exc:
        raise OutreachError(str(exc)) from exc
    return verdict


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

    def call():
        return sender.redditor(author).message(PM_SUBJECT, pm_text)

    message = await asyncio.to_thread(call)
    return str(getattr(message, "id", "") or "")


def _build_sender():
    """PRAW Reddit instance from owner-managed env. No network at construct
    time; raises OutreachError if any credential is missing."""
    import praw

    missing = [v for v in CREDENTIAL_VARS if not os.environ.get(v, "").strip()]
    if missing:
        raise OutreachError(f"reddit credentials missing: {', '.join(missing)} (set them in .env)")
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"].strip(),
        client_secret=os.environ["REDDIT_SECRET"].strip(),
        username=os.environ["REDDIT_USERNAME"].strip(),
        password=os.environ["REDDIT_PASSWORD"].strip(),
        user_agent=os.environ["REDDIT_USER_AGENT"].strip(),
    )


# ---------------------------------------------------------------------------
# DB accessors (the only seams the sender job and routes touch — tests patch
# these, never inline SQL).
# ---------------------------------------------------------------------------

async def _approved_queue(limit: int = 1) -> list[dict]:
    """Oldest pm_approved rows first. Authors who opted out (a denied row)
    are excluded here too, so a deny between approve and send can never leak
    a PM — defense in depth behind validate_approve."""
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT r.post_url, r.author, r.subreddit, r.state, r.pm_text,
                       r.created_at, COALESCE(i.title, '') AS title
                FROM reddit_rights r
                LEFT JOIN items i ON i.url = r.post_url
                WHERE r.state = 'pm_approved'
                  AND NOT EXISTS (
                      SELECT 1 FROM reddit_rights d
                      WHERE d.author = r.author AND d.state = 'denied'
                  )
                ORDER BY r.created_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            return await cur.fetchall()


async def _sent_today_count() -> int:
    """PMs sent since local midnight (the DAILY_CAP window)."""
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) AS n FROM reddit_rights WHERE sent_at >= CURRENT_DATE"
            )
            row = await cur.fetchone()
    return int((row or {}).get("n", 0) or 0)


async def _mark_sent(post_url: str, message_id: str) -> None:
    """pm_approved → sent. The WHERE clause re-checks approval at write time;
    zero rows means the row left pm_approved under us — never silently pass."""
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE reddit_rights
                SET state = 'sent', sent_at = now(), send_count = send_count + 1
                WHERE post_url = %s AND state = 'pm_approved'
                """,
                (post_url,),
            )
            if cur.rowcount == 0:
                raise OutreachError(
                    f"cannot mark sent: {post_url!r} is no longer pm_approved"
                )
    log.info("reddit_pm_sent", post_url=post_url, message_id=message_id)


async def _sent_urls_for_author(author: str) -> list[str]:
    """Post urls still awaiting a reply from this author."""
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT post_url FROM reddit_rights WHERE author = %s AND state = 'sent'",
                (author,),
            )
            return [r["post_url"] for r in await cur.fetchall()]


async def _mark_review(post_url: str) -> None:
    """sent → review. The owner reads the actual reply and decides."""
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE reddit_rights SET state = 'review' "
                "WHERE post_url = %s AND state = 'sent'",
                (post_url,),
            )


async def _sweep_inbox(sender) -> int:
    """Inbox sweep: any message from an author with a sent row flips that row
    to review. No auto-classification of the reply — the owner reads it.
    Each message is marked read only after its flip is recorded. Returns the
    number of rows flipped."""
    messages = await asyncio.to_thread(lambda: list(sender.inbox.unread()))
    flipped = 0
    seen: set[str] = set()
    for msg in messages:
        author = getattr(getattr(msg, "author", None), "name", None)
        if author and author not in seen:
            seen.add(author)
            for url in await _sent_urls_for_author(author):
                await _mark_review(url)
                flipped += 1
        # Read only after recording (or deliberately skipping an author with
        # no sent rows), so a crash replays the message instead of losing it.
        await asyncio.to_thread(msg.mark_read)
    if flipped:
        log.info("reddit_replies_to_review", flipped=flipped)
    return flipped


async def is_opted_out(author: str) -> bool:
    """True once any post by this author is denied — forever, across posts."""
    if not (author or "").strip():
        return False
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM reddit_rights WHERE author = %s AND state = 'denied' LIMIT 1",
                (author,),
            )
            return await cur.fetchone() is not None


async def ensure_candidate_row(*, post_id: str, author: str,
                               subreddit: str, post_url: str) -> dict:
    """Collect insert: one candidate row per collected post (idempotent).

    The opt-out enforcement lives here, not just the UI: posts by denied
    authors are still recorded, but pinned at candidate, and validate_approve
    refuses them — they stay candidate forever."""
    from app.db import get_pool

    opted = await is_opted_out(author)
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO reddit_rights (post_id, author, subreddit, post_url, state)
                VALUES (%s, %s, %s, %s, 'candidate')
                ON CONFLICT (post_url) DO NOTHING
                RETURNING post_url, author, subreddit, state
                """,
                (post_id, author, subreddit, post_url),
            )
            row = await cur.fetchone()
            if row is None:
                await cur.execute(
                    "SELECT post_url, author, subreddit, state FROM reddit_rights "
                    "WHERE post_url = %s",
                    (post_url,),
                )
                row = await cur.fetchone()
    if opted:
        log.info("reddit_author_opted_out", author=author, post_url=post_url)
    return row or {"post_url": post_url, "author": author,
                   "subreddit": subreddit, "state": "candidate"}


async def get_right(post_url: str) -> dict | None:
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT post_url, author, subreddit, state, pm_text, send_count, "
                "sent_at, decided_at, created_at FROM reddit_rights WHERE post_url = %s",
                (post_url,),
            )
            return await cur.fetchone()


async def list_rights(state: str | None = "candidate") -> list[dict]:
    """Queue listing with author/excerpt/url (+ title/pm_text for the editor)."""
    if state is not None and state not in STATES:
        raise OutreachError(f"unknown rights state {state!r}; expected one of {sorted(STATES)}")
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            if state is None:
                await cur.execute(
                    """
                    SELECT r.post_url, r.author, r.subreddit, r.state, r.pm_text,
                           r.send_count, r.created_at,
                           COALESCE(i.title, '') AS title,
                           LEFT(COALESCE(i.full_text, ''), 500) AS excerpt
                    FROM reddit_rights r
                    LEFT JOIN items i ON i.url = r.post_url
                    ORDER BY r.created_at ASC
                    """
                )
            else:
                await cur.execute(
                    """
                    SELECT r.post_url, r.author, r.subreddit, r.state, r.pm_text,
                           r.send_count, r.created_at,
                           COALESCE(i.title, '') AS title,
                           LEFT(COALESCE(i.full_text, ''), 500) AS excerpt
                    FROM reddit_rights r
                    LEFT JOIN items i ON i.url = r.post_url
                    WHERE r.state = %s
                    ORDER BY r.created_at ASC
                    """,
                    (state,),
                )
            return await cur.fetchall()


async def approve_right(*, post_url: str, pm_text: str) -> dict:
    """Owner approves one PM's exact text: candidate → pm_approved."""
    row = await get_right(post_url)
    opted = await is_opted_out(row["author"]) if row else False
    text = validate_approve(row, pm_text, opted)
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE reddit_rights SET state = 'pm_approved', pm_text = %s "
                "WHERE post_url = %s",
                (text, post_url),
            )
    log.info("reddit_pm_approved", post_url=post_url, author=(row or {}).get("author"))
    return {"post_url": post_url, "author": (row or {}).get("author"),
            "state": "pm_approved", "pm_text": text}


async def decide_right(*, post_url: str, verdict: str) -> dict:
    """Owner verdict after reading the reply: review → granted | denied.
    A deny opts the author out across all their posts (see is_opted_out)."""
    row = await get_right(post_url)
    decision = validate_decide(row, verdict)
    from app.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE reddit_rights SET state = %s, decided_at = now() "
                "WHERE post_url = %s",
                (decision, post_url),
            )
    log.info("reddit_right_decided", post_url=post_url, verdict=decision)
    return {"post_url": post_url, "author": (row or {}).get("author"), "state": decision}


# ---------------------------------------------------------------------------
# Sender job (every 30 min via scheduler): one approved PM per tick, then an
# inbox sweep. Dry-run default; kill switch; daily cap.
# ---------------------------------------------------------------------------

async def reddit_outreach_job() -> dict:
    """Send the oldest approved PM (if live and under cap), then sweep replies."""
    live = _is_live()
    sent_today = await _sent_today_count()
    if sent_today >= DAILY_CAP:
        log.info("reddit_outreach_cap_reached", sent_today=sent_today, cap=DAILY_CAP)
        return {"sent": 0, "swept": 0, "dry_run": False, "skipped": "daily_cap"}

    queue = await _approved_queue(limit=1)
    if not queue:
        swept = 0
        if live:
            swept = await _sweep_inbox(_build_sender())
        return {"sent": 0, "swept": swept, "dry_run": not live, "skipped": "empty_queue"}

    row = queue[0]
    if not live:
        log.info("reddit_pm_dry_run", author=row.get("author"),
                 post_url=row.get("post_url"), pm_text=row.get("pm_text"))
        return {"sent": 0, "swept": 0, "dry_run": True, "skipped": "dry_run"}

    sender = _build_sender()
    message_id = await send_pm(
        sender=sender,
        post_url=row.get("post_url", ""),
        author=row.get("author", ""),
        subreddit=row.get("subreddit", ""),
        title=row.get("title", ""),
        state=row.get("state", ""),
        pm_text=row.get("pm_text", ""),
        dry_run=False,
    )
    await _mark_sent(row.get("post_url", ""), message_id)
    swept = await _sweep_inbox(sender)
    return {"sent": 1, "swept": swept, "dry_run": False, "skipped": None}


__all__ = [
    "DAILY_CAP",
    "PM_SUBJECT",
    "PM_TEMPLATE",
    "STATES",
    "NotFoundError",
    "OutreachError",
    "approve_right",
    "decide_right",
    "ensure_candidate_row",
    "get_right",
    "is_opted_out",
    "list_rights",
    "reddit_outreach_job",
    "render_pm",
    "send_pm",
    "validate_approve",
    "validate_decide",
    "_approved_queue",
    "_build_sender",
    "_mark_review",
    "_mark_sent",
    "_sent_today_count",
    "_sent_urls_for_author",
    "_sweep_inbox",
]
