# Reddit Collection + Permission Outreach — Design

**Date:** 2026-09-05
**Status:** Approved, awaiting implementation plan
**Scope:** Mystery-lane Reddit sourcing with owner-approved auto-PMs and
mandatory credit. Read path first, send path second, both gated. No
commenting, no voting, no mass outreach, no strict-rule subs.

## Problem

The mystery lane has no newswire. Reddit holds the best raw material
(firsthand accounts, case discussions) but taking it without asking burns
authors and risks the owner's account. Manual copy-paste scales to nothing,
while unsupervised auto-DMs scale to a banned account.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | New `reddit` source kind beside rss/edgar/nse | The scheduler already dispatches per kind; a fourth kind reuses poll/cluster/evidence machinery instead of a sidecar. |
| 2 | Nothing usable without `granted` | Enforced where stories build from items, not by convention. A PM ignored for 30 days expires; a deny opts the author out forever. |
| 3 | One PM per author per post, only after per-PM owner approval | Auto-send with human fingers on every trigger. Matches the studio's manual-gate philosophy at the riskiest boundary. |
| 4 | Hard caps + kill switch + dry-run default | 5 sends/day max, spaced; `REDDIT_OUTREACH_LIVE=false` default ships dry-run (log only). One config flip stops everything. |
| 5 | Subreddit allowlist, starting narrow | `r/UnresolvedMysteries` + `r/TrueCrime`, both verified live during implementation (exists, public, rules allow good-faith contact). Strict-rule subs excluded until reviewed line by line. |
| 6 | Credit in narration + upload packet, always | `u/author on r/sub` spoken where natural; URL + author in `upload.txt` sources and description, same as news sources. |

## Collection

Poll job (same cadence family as RSS): weekly top per allowlisted subreddit,
score floor (default 100) and age floor (7 days, so vote rank has settled),
self-posts and link-posts with substantive text only (drop media-only,
megathreads, moderator posts). Stored per post: subreddit, post id, author,
URL, title, excerpt (first 2000 chars), score, published date, flair.
PRAW added to `pyproject` AND installed into both venvs in the same change
(the python-multipart lesson). Credentials are owner-set in `.env`
(`REDDIT_CLIENT_ID`, `REDDIT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`,
`REDDIT_USER_AGENT`); code reads env only, and the poll refuses to start
with any missing (loud, at job time — never a silent empty pull).

## Rights model

New table `reddit_rights` (migration): `post_id` (unique), `author`,
`subreddit`, `url`, `state` (`candidate|pm_approved|sent|granted|denied|expired`),
`pm_text`, state timestamps, `send_count`. Transitions only forward except
`denied` (terminal, opts out the author across all their posts) and `expired`
(30 days after `sent` without reply; re-contact allowed once, then terminal).
Story building joins items to rights and admits only `granted` Reddit items —
a candidate that sneaks into a cluster never reaches a script.

## Send path

GUI queue (extends the Inbox pattern): candidate posts with author, excerpt,
and a pre-filled PM draft (template + post title + credit promise + opt-out
line, editable). Owner approves per PM (exact-text preview) → state
`pm_approved`. Sender job (same cadence family, separate lock): takes oldest
approved, checks daily cap + kill switch + dry-run flag, sends via PRAW,
records `sent`. Reply detection: any PM reply from the author flips to human
review (granted/denied decided by the owner reading the actual reply — no
sentiment judge; a third automated layer buys risk, not value).

## PM template (verbatim default, editable per send)

> Hi u/{author} — I run an educational YouTube channel and your post
> "{title}" (r/{sub}) would make a strong segment. May I adapt it into a
> narrated video with full on-screen credit to you and a link to your post?
> Reply YES and I'll send you the link when it's live, or NO and I'll never
> ask again. — Min

## Testing

- No-send-without-approval: direct `send_pm` call on a `candidate` raises;
  only `pm_approved` sends (the load-bearing test of this spec).
- Caps: 6th send in a day refuses; kill switch and dry-run short-circuit
  before any API call (PRAW patched at the boundary, never live).
- Expiry: 30-day-old `sent` becomes `expired`; denied author blocks all
  their posts; granted items pass the story-build filter, others don't.
- Credit: upload packet and description contain author + URL; narration
  prompt carries the credit line.
- Migration round-trip on a scratch DB; seed allowlist test.

## Non-goals

- Commenting, voting, following, mass or cold outreach beyond approved PMs.
- r/AskHistorians, r/science, and any strict-rule sub until rules review.
- Sentiment judging of replies; commercial API tiers (revisit on volume).

## Files touched

- `worker/pyproject.toml` (+ both venv installs, same change)
- `worker/app/sources/reddit.py` (new kind module), `worker/app/ingest.py` (dispatch), scheduler registration
- Migration: `reddit_rights` table + allowlist seed
- GUI: permission queue page (or Inbox extension), credit rendering
- Tests: `test_reddit_sources.py`, `test_reddit_rights.py`
