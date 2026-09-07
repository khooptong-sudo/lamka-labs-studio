# Views-Based Retention Loop — Design

**Date:** 2026-09-05
**Status:** Approved, awaiting implementation plan
**Scope:** Manual publishing means the Studio never learns YouTube video IDs
on its own — so the loop has a human link step, then runs itself: pull stats,
tilt future scores, show what works.

## Problem

Scoring judges promise; nothing judges performance. The analytics fetcher
exists but feeds no decision, and manual uploads leave no video ID behind,
so there is nothing to look up even if it ran nightly.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Owner links the uploaded video per draft (paste URL or ID) | Manual publishing has no API callback; a 10-second paste is the only honest link. |
| 2 | Reuse the `metrics` table (`platform='youtube'`) | It already has draft_id/impressions/likes/replies/captured_at. No migration. |
| 3 | Multipliers computed at score time, not stored | No weights table to go stale; one aggregate query per batch. No data → 1.0. |
| 4 | Clamp 0.7–1.3, minimum 3 videos per archetype | History tilts judgment, never overrides it; small samples stay neutral. |
| 5 | 90-day trailing window | Old winners shouldn't tax new formats forever. |

## Flow

1. Drafts YouTube tab gains "Link uploaded video" (accepts full watch URL or
   bare 11-char ID, validates shape, stores `body.youtube_video_id`).
2. Nightly `video_stats_job`: drafts with `youtube_video_id` and no fresh
   row (or older than 7 days) → `get_youtube_analytics` batch → upsert
   `metrics` rows (`platform='youtube'`, impressions=views, likes,
   replies=comments). Missing OAuth creds fail loud in logs, skip quietly in
   UI (band shows "connect YouTube in settings"... no — there is no such
   settings surface; show "analytics unavailable").
3. `score_new_job`: one aggregate query (trailing 90d metrics joined
   drafts→stories for archetype/vertical/channel) → per-archetype multiplier
   → `score = round(model_score * mult)`; audit records both numbers.
4. `GET /analytics/summary`: per-archetype totals + top 5 videos; Research
   dashboard gains a compact "what's working" band reusing stat-card styling.

## Testing

- ID extraction (URLs, shorts links, bare IDs, rejects garbage).
- Multiplier math (clamps, minimums, empty → 1.0, rounding).
- Stats upsert (insert + refresh paths, creds-missing loud log).
- Score integration (multiplied value written + audited; no-stats path unchanged).
- Endpoint shape; band renders with and without data.

## Non-goals

- Retention curves, CTR, auto-picking, prompt changes, watch-time API,
  backfill UI beyond the link field.
