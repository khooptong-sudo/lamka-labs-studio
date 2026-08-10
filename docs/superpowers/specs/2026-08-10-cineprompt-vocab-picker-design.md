# CinePrompt Vocabulary Picker: Design

Date: 2026-08-10
Status: approved, ready for implementation planning

## Goal

The Studio Cinema page shipped earlier today only exposes cinematography
fields through an LLM ("Fill" fills whatever fields it decides to from a
free-text scene description). Comparing it against the original
cineprompt.io site made a real gap visible: that site's actual product is a
manual, category-grouped field picker — you browse and click through every
field grouped by section, with no AI involvement required. Fill is meant to
be a shortcut layered on top of that picker, not the only way in.

This spec adds the picker. It does not touch visual design (colors,
spacing, animation) — that's a separate pass deferred until the
`frontend-design` skill is available after a session restart. This is
interaction-model and data-flow work only.

## What already exists (unchanged by this work)

- `worker/app/cineprompt/vocab.py`: the full ~130-field vocabulary, loaded
  from `data/base.json` (vendor) + `data/lamka.json` (overlay).
  `values_for(field)` returns a field's allowed values (empty = free text);
  `is_free_text(field)` and `all_fields()` round out the surface.
- `worker/app/cineprompt/assemble.py`: `SECTIONS` maps each of the 8
  sections (STYLE, SUBJECT, ACTIONS, ENVIRONMENT, CINEMATOGRAPHY, PALETTE,
  DIALOGUE, SOUND) to its field list. `nl_join` already joins a *list* of
  selected values into natural English ("a, b and c") — the engine has
  always supported multiple values per field; nothing in this repo's GUI
  has exercised that path yet.
- `worker/app/cineprompt/prompts.py`: `fields_in_scope(mode, level)` already
  filters the full field set down to what's relevant for a given mode
  (`single`/`frame_motion`) and level (`simple`/`complex`), for the Fill
  system prompt's catalogue. This is the exact filtering the picker reuses.
- `build_prompt` (via `resolve_state` → `assemble`) already accepts a field
  value as either a plain string or a list — no change needed there.

## Architecture

```
GET /cineprompt/vocab?mode=single&level=complex
  → reuses prompts.fields_in_scope(mode, level) + assemble.SECTIONS
    + vocab.values_for/is_free_text
  → { "STYLE": {"genre": {"values": [...], "free_text": false}, ...},
      "SUBJECT": {...}, ... }   (only the 8 sections that have in-scope
                                 fields for this mode/level appear)

Cinema page `fields` state: Record<string, string | string[]>
  - Fill (AI) sets some entries as single strings — unchanged behavior.
  - The picker toggles enum chips on/off, building/editing the same
    entries as string | string[].
  - Free-text fields get a textarea, always a single string.
  - Build Prompt sends `fields` as-is; the engine already handles a
    string-or-list value uniformly.
```

Fill and the picker read and write the exact same `fields` state — there is
no sync step, no second source of truth. A field Fill already populated
shows pre-toggled/pre-filled in the picker; a field the user picks manually
shows up in Build Prompt exactly like a Fill-produced one.

## Worker: `GET /cineprompt/vocab`

New route in `worker/app/routes.py`, alongside the other `/cineprompt/*`
routes:

| Route | In | Out |
|---|---|---|
| `GET /cineprompt/vocab?mode=single&level=complex` | query params, both optional (defaults `single`/`complex`) | `{section_name: {field_name: {values: string[], free_text: bool}}}` |

Implementation: for each section in `assemble.SECTIONS`, filter its fields
through `prompts.fields_in_scope(mode, level)`, and for each surviving
field emit `{"values": vocab.values_for(field), "free_text":
vocab.is_free_text(field)}`. A section with zero in-scope fields for this
mode/level is omitted from the response entirely (nothing to render).

No new error path: this is pure, in-process, network-free — the same risk
profile as `POST /cineprompt/build`. No `HTTPException` cases beyond
FastAPI's own validation.

## Frontend: the vocabulary browser

Inserted into `gui/src/app/cinema/page.tsx` between the description/Fill
section and the model/Build Prompt section (functional structure only, no
visual design):

1. On mount, and whenever `mode` or `level` changes, `fetch` `/api/cineprompt/vocab?mode=...&level=...` and store the result.
2. Render each returned section as a collapsible block, open by default (a `<details open>`/toggle-state pair is enough — no animation or styling investment here). Within a section, each field renders as:
   - **Enum field:** one button per allowed value. Clicking toggles that value's membership in `fields[field]` (treated as an array regardless of how many are selected). Clicking a chip that's the field's last remaining selection removes the key from `fields` entirely — an unset field must not appear in the built prompt, matching `assemble.py`'s existing prune-of-empty-fields behavior.
   - **Free-text field:** a single `<textarea>` bound to `fields[field]` as a plain string (no multi-select — free text has no meaningful "toggle").
3. A field Fill already populated (a single string) shows correctly whether the user picked one chip or the value came from Fill — the picker reads the same `fields[field]` value it writes to, with no type coercion needed on read (a lone string displays as one active chip; an array displays as N active chips).

If the vocab fetch fails (worker unreachable), the picker section is simply empty — Fill, Build Prompt, Generate, Save, and History all remain usable independently, since the picker is additive rather than a dependency of the rest of the flow.

## Testing

- `worker/tests/test_routes_cineprompt.py`: one new, unmocked test (same "real engine through the route" pattern used for the two `/cineprompt/build` tests added in today's final-review fix wave) asserting `/cineprompt/vocab` returns all expected section keys, that a known enum field (e.g. `genre`) lists real values from `vocab.values_for`, and that a known free-text field (e.g. `dialogue`) is marked `free_text: true`.
- No GUI test framework exists in this repo (confirmed during today's earlier work — GUI verification is `npm run build` plus a manual walkthrough). The picker's chip-toggle logic gets the same manual-smoke verification the rest of the Cinema page got.

## Out of scope (still)

- Visual/aesthetic design of the picker (colors, spacing, chip styling, collapse animation) — Task 10 from the original Cinema plan, blocked on the `frontend-design` skill activating after a session restart.
- A subject-type selector to hide/show SUBJECT's per-category field families (creature_*, obj_*, food_*, veh_*, etc.) — deliberately not built here; unset fields already don't appear in the final prompt, so showing all of them and letting the user ignore what doesn't apply is the simplest correct behavior for this pass. Revisit only if it proves confusing in practice.
- Any change to `fill.py`, `assemble.py`, `resolve.py`, `build_prompt`'s contract, or the vocabulary data itself — this spec is purely additive.
