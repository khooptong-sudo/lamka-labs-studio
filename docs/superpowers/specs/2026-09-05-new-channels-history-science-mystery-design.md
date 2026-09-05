# New Channels (History, Science, Mystery) — Design

**Date:** 2026-09-05
**Status:** Approved, awaiting implementation plan
**Scope:** Piece 5 of the Kutly upgrade. Three new channels, manual-first,
both render routes. No feeds, no taxonomy additions, no GUI changes, no
migration (config-table data, not schema).

## Problem

One engine, two channels. Documentary and education demand the Kutly lanes
(history, science, mystery) with their own voices and compliance floors, and
the current seed path cannot add a channel without rewriting the whole
`channels` key from legacy voice profiles — re-running it would wipe
owner-tuned finance/kids entries.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Three channels: `history`, `science`, `mystery` | Documentary + education coverage with no overlap: business stays finance, how-to stays kids/practical-skills. |
| 2 | New channel defaults live in code, merged — never overwritten | Same reason as decision #57: git-traced, and `ensure` adds missing ids only. Existing entries are byte-identical after a run. |
| 3 | Manual-first: storyboard + manual-idea paths, no new RSS feeds | Feed curation (source quality, per-topic freshness, tuning) is its own project. Manual paths already work per channel. |
| 4 | Shared taxonomy, no additions | §5: new archetypes need owner approval, and the closed set still validates — finance-only values simply never fit non-finance drafts. |
| 5 | No GUI changes | `ChannelSelect` renders whatever `/api/config/channels` returns; modes are already per-run. Verified, not rebuilt. |

## Registry entries

All `voice_key` values are existing `VOICE_MAP` keys. `extra_blocklist`
unions over the base set; base terms are never duplicated.

- `history` — "History, Explained". Voice `news` (steady narrator).
  Prompt: measured documentary narrator; dates and claims only from evidence;
  uncertainty stated, never smoothed over; no present-day moralizing, no
  extremist glorification. Extras: none beyond base.
- `science` — "Science & Space". Voice `adult_female` (warm, clear).
  Prompt: curious explainer of space, physics, nature; mechanisms over
  marvels; never medical/financial advice, never miracle language.
  Extras: `miracle cure`, `guaranteed cure`, `doctors hate`.
- `mystery` — "Mysteries & True Crime". Voice `adult_male` (sober).
  Prompt: case-driven narrator; living persons are alleged until convicted;
  no method detail an imitator could use; no perpetrator glorification;
  victim dignity throughout. Extras: `how to kill`, `graphic autopsy`,
  `glorify the killer`.

Full prompt texts live in the seed module as `BUILT_IN_CHANNELS` and are
quoted verbatim in the implementation plan — no paraphrase drift.

## Seed merge

`ensure_builtin_channels(existing: dict | None) -> dict`: returns a new dict
with every `BUILT_IN_CHANNELS` id missing from `existing` added (validated
through the same `check_voice_key` + required-fields path as today);
present ids returned untouched, key order stable (existing first, additions
appended). A `main()` merge mode reads the live `channels` row, merges,
writes back only when something was added, and prints what changed.
`build_channels_payload` (legacy migration) is untouched — its tests stay green.

## Routes

Both backends already key off `channel_id` alone: Short (`cinematic`) and
Story Film (`three`) render per new channel with zero pipeline changes.
Piece 5 proves it (parametrized generation tests per channel × backend,
gates passing) rather than changing it.

## Testing

- Merge: adds missing, never touches present, stable order, validates voice
  keys and required fields, no-op run writes nothing.
- Resolve: each new id resolves with its voice, prompt, and union blocklist
  (patch `db.get_config`; mirror `test_db_channel.py`).
- Generation: Short + film per new channel with mocked seams and a
  contract-shaped board — draft records, provider/GUI untouched.
- Regression: legacy migration tests, finance/kids resolve, full affected suites.

## Non-goals (follow-ups)

- Per-topic RSS feeds + freshness tuning, taxonomy additions, GUI channel
  CRUD, kids COPPA changes, long-form track.

## Files touched

- `worker/scripts/seed_channels.py` (`BUILT_IN_CHANNELS`, `ensure_builtin_channels`, merge `main`)
- `worker/tests/test_seed_channels.py` (merge + new-channel cases; legacy tests untouched)
- `worker/tests/test_new_channels.py` (new: resolve + generation matrix)
