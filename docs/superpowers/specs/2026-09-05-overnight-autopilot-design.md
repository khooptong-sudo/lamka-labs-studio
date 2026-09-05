# Overnight Autopilot (Pre-Approved Picks) — Design

**Date:** 2026-09-05
**Status:** Approved, awaiting implementation plan
**Scope:** Render owner-queued stories overnight into Drafts. Publishing stays
manual, every morning, no exceptions.

## Problem

Ingest and scoring run daily, but every render starts by hand. The queue sits
idle all night while consistency — the only growth lever that matters — waits
on morning labor.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Pre-approved picks only (owner queues in the evening) | No model-chosen renders at 3am; the human gate moves earlier, never away. |
| 2 | Approval is a new nullable column, never a status flip | Flipping `status` would silently empty the Inbox (the recorded score.py invariant). |
| 3 | Short format only in v1 | Predictable GPU time and spend per night. |
| 4 | Failure keeps the flag (retry tomorrow), success clears it | Transient 3am flakes shouldn't burn the pick; the audit trail shows repeats. |
| 5 | Day-gated interval job, not cron plumbing | The scheduler registry is interval-based; a day-gate inside the job needs no registry change. |
| 6 | Skip stories that already have a pending draft | Never double-render the same story overnight. |

## Queue flag

Migration `013_autopilot_queue.sql`: `ALTER TABLE stories ADD COLUMN
autopilot_queued_at timestamptz` (nullable, default NULL; NULL = not queued).
(NULL: the Reddit plan's draft numbers assumed 013 for rights — it moves to
014/015 when built; this lands first.)

GUI Inbox rows gain a "Queue overnight" moon toggle → `PATCH
/stories/{id}/queue {queued: bool}` → sets/clears the timestamp (clear is
idempotent). Queued rows show the marker in both Inbox and films flows.

## Nightly run

`autopilot_overnight_job` (30-min interval + day-gate: runs only 02:00–05:00
server-local, once per calendar day tracked in the `config` table as
`autopilot_last_run_date`):
1. Pick flagged stories: `autopilot_queued_at IS NOT NULL`, fresh
   (`fresh_news_hours` window, same predicate as the Inbox), no pending draft
   (`NOT EXISTS` on drafts by story_id with status pending), oldest-queued
   first, limit `autopilot_max_per_night` (config table, default 3).
2. For each: `generate_youtube_video(story, channel of story.channel_id,
   backend cinematic)` — Short path with every existing guard. Voice clips:
   none (TTS default; owner-voice overnight is a later step).
3. Success → clear flag + `audit_log(autopilot_rendered)`. Failure (None or
   exception) → keep flag + `audit_log(autopilot_failed)` + continue to next.
4. Record the run date; outside the window or already-ran-today → no-op with
   a debug log (a no-op must never look like a failure).

## Testing

- Migration round-trip (column exists, default NULL).
- Picker: skips stale/over-cap/already-drafted; orders oldest-queued; honors
  the cap; empty queue is a clean no-op.
- Day-gate: outside window no-op; second run same day no-op (inject clock).
- Failure keeps flag and continues; success clears flag + audits.
- Queue endpoint: set/clear/idempotent; unknown story 404.
- Scheduler registration asserted like `score_new` (async-def invariant).

## Non-goals

- Auto-publish, long-form/documentary autopilot, film autopilot, wake-up
  pings, model-chosen picks, owner-voice overnight.
