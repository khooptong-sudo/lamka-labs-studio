# CinePrompt Engine Port: Design

Date: 2026-08-09
Status: approved, ready for implementation planning

## Goal

Port the CinePrompt prompt-assembly engine into `worker/app/cineprompt/` as a pure
Python subpackage, consumed by Lamka Labs Studio (Next 16). Studio ships it as a
visible "Cinema" product with BYOK browser-side video generation. The engine stays
neutral so the existing news→story→script→render pipeline can adopt it later as a
`FRAME_BACKEND` without a rewrite.

## Source analysis

cineprompt.io is a single 1.15 MB static `index.html` on nginx/Ubuntu. No framework,
no bundler modules, 17 inline `<script>` blocks. Supabase (auth + `saved_prompts`,
`shared_prompts`, `prompt_projects`), Stripe.js, GoatCounter at `/count`, IndexedDB
(`CinePromptSubjects`) for subjects and reference images.

Server-side surface is five routes: `/api/scene-to-prompt`, `/api/share`,
`/api/check-tier`, `/api/create-checkout`, `/api/create-portal`. Video generation
runs entirely in the browser against `queue.fal.run`, `api.venice.ai`,
`api.evolink.ai` with the user's own keys.

The assembly core is published by the vendor as the `cineprompt` npm package
(MIT, Copyright 2026 Light Owl, LLC), whose `lib/prompt-builder.js` header states it
mirrors the frontend logic. Verified against the minified site bundle: same
`nlJoin`, same section order. `data/field-values.json` carries 130 fields and 1,412
curated values, 39 of them free-text.

### Two components not in the npm package

1. **Per-model profiles**: each target model reorders the 7 sections and carries a
   character cap (universal 3000, sora 2500, veo 3000, kling 2500, seedance 10000,
   grok 4096, ltx 3000, pixverse 2048, happyhorse 2500, luma 3000, wan 3000).
   Extracted from the site bundle.
2. **Compatibility matrix**: `format` gates other fields. `film` deletes
   `color_science` and restricts `camera_body` by gauge; `digital` deletes
   `film_stock`; `consumer` deletes `camera_body`, `color_science`, `film_stock`.
   Enforced in their DOM, which means any non-UI caller bypasses it.

### Known gap in the reference

`stpFilterFields` filters by field *name* only (four blocked fields plus a
simple-mode whitelist). Returned *values* are never checked against the enum. We
close this with snap-to-enum server-side.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Engine-neutral module; Studio "Cinema" ships first, pipeline seam left open | Engine is pure functions over a field dict; neutrality is the default, not an investment |
| 2 | Vocabulary as data: `data/base.json` verbatim (MIT, attributed) + `data/lamka.json` overlay | Parity day one; divergence is a data edit, not a code change |
| 3 | Fill: local Ollama first → DeepSeek on failure → hard fail. Snap-to-enum on output | Snapping rescues imprecise-but-correct 7B output, making local viable |
| 4 | Testing: frozen golden fixtures generated once from the JS oracle | Oracle-grade guarantee, hermetic suite, no node at test time |
| 5 | All four state modes in slice one (five prompt kinds, since `frame_motion` emits two) | `multi` override layer is the feature that justifies the tool |
| 6 | Subpackage decomposition mirroring `app/scene3d/` | `youtube.py` at 1,526 lines is the counter-example already in the repo |

## Module layout

```
app/cineprompt/
  __init__.py    public surface: build_prompt, resolve_state, fill_from_scene
  vocab.py       load base.json + lamka.json overlay; field lookup, enum access
  compat.py      format→camera/color/stock pruning matrix
  assemble.py    section order, merge rules, nl_join → prompt text   [oracle-tested]
  profiles.py    per-model section reordering + char limits
  resolve.py     ms_* global/override resolution; mode dispatch
  fill.py        scene-to-prompt: local→cloud, JSON extract, snap-to-enum
  data/base.json           (MIT, Light Owl LLC, untouched)
  data/lamka.json          (our overlay)
  data/LICENSE-cineprompt
```

Dependency direction is one-way: `fill → vocab, compat`; `resolve → assemble,
profiles`; `assemble → vocab`. Nothing imports `fill`, so the engine is fully
testable with no model present.

`assemble.py` is pure: field dict in, string out, no I/O, no LLM, no config. That
purity is what makes the golden-fixture oracle possible. `vocab.py` is the only
module touching disk; `fill.py` the only one touching a model.

## Data model

```python
{
  "mode":  "single" | "multi" | "frame_motion" | "grid",
  "model": "universal" | "veo" | "sora" | "kling" | ...,
  "fields": {...},                    # single-shot fields; ms_* globals live here too
  "shots": [{"fields": {...}}, ...],  # multi and grid only
}
```

Plain dict, JSON-serialisable end to end, so it crosses the Studio↔worker boundary
and lands in a share link unchanged.

## Mode resolution

`resolve.py` turns any mode into a flat list of field-dicts. This is what lets five
prompt kinds share one builder.

| Mode | Resolution | Output |
|---|---|---|
| `single` | pass through | 1 field-dict |
| `multi` | per shot: `strip_ms(globals) \| shot.fields`, shot wins key-by-key | N field-dicts |
| `grid` | as `multi`, N from `grid_size` (2×2…5×5) | 4–25 field-dicts |
| `frame_motion` | one dict twice, through two section subsets | 2 prompts (still, motion) |

`strip_ms` renames `ms_camera_body` → `camera_body`, then the shot's own keys
overwrite. Inheritance is a dict merge.

## Assembly pipeline

```
prune (compat)  →  order sections (per model)  →  apply merge rules
                →  nl_join lists  →  group SUBJECT/gear runs  →  sentence-case  →  cap
```

Sections: STYLE, SUBJECT, ACTIONS, ENVIRONMENT, CINEMATOGRAPHY, PALETTE, SOUND.
Roughly 16 merge rules weld field pairs into English; the representative case is
`camera_body` + `color_science`, which strips a duplicated manufacturer so
`"ARRI Alexa 65"` + `"ARRI LogC4"` does not yield `"ARRI ... ARRI"`.

Two deliberate departures from the reference:

**Compatibility pruning runs before assembly, not in the UI.** Their DOM-level
enforcement works only while a human is clicking. Placing it in `compat.py` ahead of
assembly covers every caller, including `fill.py` and any future pipeline path.

**Character caps drop whole trailing segments, never truncate mid-string.** Sections
are already ordered by the target model's priority, so the trailing segment is by
construction the least important one for that model, and dropping it leaves
grammatical output. A mid-string cut hands the model a severed clause.

## Fill pipeline

`level` is `"simple"` or `"complex"`, carried on the request. It selects how much of
the vocabulary is in play: `simple` restricts to a per-mode whitelist of the
commonly-used fields, `complex` opens the full in-scope set.

Prompt construction sends only the in-scope fields for `(mode, level)` with their
full enums, in the style of `archetypes.py:475 catalogue_for_prompt()`. Simple mode
is roughly 30 fields, complex roughly 60.

Response handling, in order:

1. `_extract_json` (the `localllm.py:53` pattern, fenced or bare)
2. Drop unknown field names and the four blocked ones
   (`delivery_style`, `delivery_style_custom`, `sound_mode`, `dialogue_language`)
3. Snap each value to its enum: exact → casefold → containment →
   `difflib` ratio ≥ 0.82 → otherwise drop and log the near-miss
4. `compat.prune`
5. Restore locked fields; user pins always win

### Acceptance gate

Two independent conditions, both required:

```python
MIN_FILLED_FIELDS = 6     # absolute floor
MIN_SNAP_SURVIVAL = 0.5   # proportion of returned values that are real vocabulary
```

The ratio alone is the known trap: a model returning two fields that both snap
cleanly scores 100%. This is the same shape as `MIN_SCRIPT_FRAMES` and is recorded
in project memory as "a one-frame stub scores 100% on every proportion-based guard."
The ratio catches hallucinated vocabulary; the floor catches a model that gave up.
Neither catches both.

### Escalation

Local, one retry, then DeepSeek, then raise `FillError` to the caller. No fabricated
fields at any step. A failed fill returns nothing and says so. A prompt the user
believes describes their scene but does not is worse than no prompt.

### Snap logging

Every near-miss below threshold is logged with field, returned value, and best
candidate. This tunes the 0.82 threshold with evidence, and it is how `lamka.json`
gets written: the values a model reaches for and we lack are the values worth adding.

## Testing

| Layer | Test |
|---|---|
| `assemble.py` | 240 golden fixtures vs the JS oracle: 40 hand-picked (one per merge rule plus empty-partner variants), 200 random. Byte-identical. |
| `compat.py` | Table test: each format × each gated field → pruned or kept |
| `resolve.py` | ms_ override wins; grid fans out to N; frame_motion yields 2 prompts |
| `profiles.py` | Section order per model; cap drops trailing segments, output stays grammatical |
| `fill.py` | Snap units (exact/case/substring/fuzzy/drop). Gate tests: a 2-field response fails the floor at 100% survival. Model patched, never called. |

No network, no node, no Ollama at test time. Fixtures regenerate via
`scripts/gen_cineprompt_fixtures.mjs`, run manually after a vocabulary change.

Hand-picked fixtures are required because random sampling almost never hits the
interesting branches. The brand-deduplication path in the `camera_body`/
`color_science` merge fires only when both values share a manufacturer.

## Out of scope

- Studio frontend (design direction to be settled first via `stitch-design-taste`
  or `design-consultation`)
- BYOK provider adapters and the browser generation path
- Share links, projects, subject library, Stripe tiers
- `FRAME_BACKEND=cineprompt` pipeline integration (seam left open, not built)

## Attribution

`data/base.json` and the assembly logic derive from the `cineprompt` npm package,
MIT licensed, Copyright (c) 2026 Light Owl, LLC. `data/LICENSE-cineprompt` retains
the notice.
