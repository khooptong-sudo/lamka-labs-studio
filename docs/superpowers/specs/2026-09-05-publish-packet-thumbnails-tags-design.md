# Publish Packet (Thumbnails + Tags) — Design

**Date:** 2026-09-05
**Status:** Approved, awaiting implementation plan
**Scope:** Piece 2 of the Kutly upgrade. A/B Gemini-art thumbnails + validated
tags in the manual-upload packet. No migration, no GUI work, no autoplay.

## Problem

`youtube.py:1230` `_generate_thumbnail` paints one gradient title-card with a
hardcoded "Trending" badge — the exact generic-AI look Kutly's motion-design
pitch beats. And the packet has no tags: `_require_metadata` enforces
title + description, `_write_upload_txt` writes CHANNEL/TITLE/DESCRIPTION
(+kids COPPA reminder), the draft body carries title/description — tags exist
nowhere, so every manual upload ships untagged.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Model paints backgrounds only; title text stays in the Playwright overlay | Gemini-rendered text is unreliable; the existing template path already renders type correctly. Two deterministic layouts, bundled traits per decision #70. |
| 2 | Variants build post-render, best-effort, per-variant fallback | Thumbnail is a convenience (existing rule at `youtube.py:355-368`): a failed variant falls back to the legacy card; both failing still records the draft. Never raises, never blocks. |
| 3 | Tags ride frontmatter → draft body jsonb → `upload.txt`; no migration | The body column is schemaless jsonb and `upload.txt` already travels with the folder. A tags column + migration buys nothing. |
| 4 | Tags validated pre-render with title/description, blocklist-scanned | A tag is search surface: `find_blocked_terms` over each tag, plus count/length caps. Same fail-loud family as `_require_metadata`. |
| 5 | No A/B titles, no picker UI, no DB tags column | Out of scope; the owner picks a thumbnail file by eye at upload. |

## Contract

Frontmatter gains `tags: "t1, t2, ..."` (comma-separated, max 12, each
1–60 chars after strip, no empties, no duplicates case-insensitively).
`parse_tags(frontmatter) -> list[str]` splits and cleans;
`validate_tags(tags, blocklist) -> list[str]` returns violations.
`_require_metadata` grows to return `(title, description, tags)` with tags
validated the same way title/description are (raise on violation, pre-render).
Generation prompt FORMAT gains a `tags:` example line. Override boards may
carry tags the same way; absent tags on an override board default to `[]`
(an editor's board is not failed for missing marketing metadata — title and
description stay mandatory).

## Variants

`build_thumbnail_variants(*, title, hook, bible, video_dir) -> dict[str, Path]`:

- Art prompt per variant, built from title + hook + continuity bible, ending
  with: no words, letters, numbers, logos, or people outside the video's
  world; 16:9 landscape YouTube thumbnail composition with clear negative
  space for the title band. Variant B adds a distinct stated mood/palette
  shift so A/B is a real choice, not a re-roll.
- `_generate_gemini_thumbnail_art(prompt, destination)` reuses the
  `GEMINI_IMAGE_MODEL` env (same model as keyframes; thumbnails are cheap
  enough not to need their own knob) and the inline-bytes parsing pattern
  from `_generate_gemini_cinematic_image` — factor the byte-extraction into
  one shared helper rather than duplicating it.
- Overlay via the existing Playwright template path: layout A title top-band,
  layout B title bottom-band + badge. Output `thumbnail-a.jpg`,
  `thumbnail-b.jpg`. The GUI references no thumbnail filename today, so the
  legacy single `thumbnail.jpg` is retired, not aliased.
- Each variant independently try/excepts to the legacy gradient card.
  Both failing logs `thumbnail_generation_failed` and continues — the draft
  records regardless.

## Wiring

In `generate_youtube_video`, replace the single-thumbnail block
(`youtube.py:355-368`) with the variants call fed by the parsed board
(title, Scene-1 hook, direction bible). `_record_youtube_draft` gains tags
in the body dict. `_write_upload_txt` gains a `TAGS` section (comma-joined;
omitted when empty so old goldens keep passing only after update — update
the golden test).

## Testing

- Pure: tag parse/validate cases (too many, too long, dupes, empties,
  blocked term via the real `find_blocked_terms`, happy path).
- Seams patched, never the network: Gemini art helper (byte extraction +
  no-data raise), overlay path, per-variant fallback (art raises → legacy
  card file exists), both-fail → draft still records.
- Pipeline: PASS/FLAG/BLOCK matrix unaffected — gates run pre-render,
  thumbnails post-render; existing gate tests untouched.
- Golden: `upload.txt` with and without tags.

## Non-goals (later pieces)

- A/B titles, drafts-page thumbnail picker, DB tags column.
- Voiceover-to-video (piece 3), queue concurrency (piece 4),
  Documentary/Education/custom channels (piece 5), long-form track.

## Files touched

- `worker/app/youtube.py` (tags plumbing, variants wiring, draft body, upload.txt)
- `worker/app/scene3d/backend.py` (shared Gemini byte-extraction helper only)
- `worker/tests/test_youtube.py`, `worker/tests/test_upload_metadata.py`
- New: `worker/tests/test_publish_packet.py` (tag validator + variant fallback cases)
