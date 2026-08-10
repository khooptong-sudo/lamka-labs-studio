# Studio Cinema Page: Design

Date: 2026-08-10
Status: approved, ready for implementation planning

## Goal

Ship the "Cinema" product the CinePrompt engine design doc (`2026-08-09-cineprompt-engine-design.md`)
named as its first-class deliverable but never built: a Studio page where a user
types a scene description, the CinePrompt engine turns it into a structured
cinematography prompt, and the user generates video against fal.run with their
own API key. The engine itself (`worker/app/cineprompt/`) is finished and tested;
nothing has called it outside its own test suite until now.

This corrects a sequencing gap from the prior session: `FRAME_BACKEND=cineprompt`
pipeline integration was picked first, but the original design doc explicitly
scoped that as "seam left open, not built" — a hypothetical, not a spec'd feature.
The actual designed target was always Cinema. This spec builds that instead.

## Why BYOK stays client-side

The original cineprompt.io site ran video generation entirely in the browser
against `queue.fal.run`, `api.venice.ai`, `api.evolink.ai` with the user's own
keys — their server never touched a key. We keep that model: the worker gains
zero new secret-handling surface. The only thing the worker does after
generation is download the *result* video by URL, which requires no key at all
(fal.run result URLs are directly fetchable object-storage links).

## Architecture

```
Studio (Next.js, browser)                Worker (FastAPI)              fal.run
─────────────────────────                ───────────────               ───────
1. type scene description
2. POST /cineprompt/fill ────────────►  fill_from_scene()
                                          (Ollama → DeepSeek)
   ◄──────────────────────────────────  field-state JSON
3. edit fields, pick mode/model
4. POST /cineprompt/build ───────────►  build_prompt()
   ◄──────────────────────────────────  assembled prompt text
5. call fal.run directly ─────────────────────────────────────────►  (user's own key,
   with user's fal.run key                                            never sent to worker)
   ◄─────────────────────────────────────────────────────────────  video URL
6. POST /cineprompt/save ────────────►  downloads video from URL,
   {description, fields, mode,          writes to local storage,
    model, prompt, video_url}           inserts DB row
```

Steps 2, 4, and 6 carry no secret. Step 5 is a plain client-side `fetch` to
`queue.fal.run` with the key in a header, entirely in the browser.

## Worker API surface

New routes in `app/routes.py`:

| Route | In | Out |
|---|---|---|
| `POST /cineprompt/fill` | `{description, mode, level, locked?}` | field-state dict (from `fill_from_scene`), or 422 with the `FillError` message |
| `POST /cineprompt/build` | `{mode, model, fields}` | `{prompt: str}` (from `build_prompt`) |
| `POST /cineprompt/save` | `{description, mode, model, fields, prompt, video_url}` | `{id, local_path}` — downloads `video_url`, writes to `videos/cineprompt/<id>.mp4`, inserts a DB row |
| `GET /cineprompt/history` | — | up to 50 most recent saved generations, newest first; no pagination in v1 |

## Data model

New migration `supabase/migrations/011_cineprompt_generations.sql`:

```sql
CREATE TABLE cineprompt_generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL,
    mode TEXT NOT NULL,
    model TEXT NOT NULL,
    fields JSONB NOT NULL,
    prompt TEXT NOT NULL,
    video_url TEXT NOT NULL,      -- original fal.run URL, kept for provenance
    local_path TEXT NOT NULL,     -- downloaded copy; this is what the GUI plays
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`local_path` is authoritative for playback. `video_url` is retained only as a
provenance record — fal.run retention windows are not guaranteed, so it may
404 on a later fetch; that's expected and not an error condition once the
local copy already exists.

## Frontend: `/cinema` page

New nav item in `Sidebar.tsx` ("Cinema", between Production and Drafts — a
production tool, not a draft or a settings screen). New
`gui/src/app/cinema/page.tsx`.

Interaction flow (structure only; visual design is a separate pass via the
`frontend-design` skill once the session restart activates it):

1. Textarea for the scene description, plus mode/level pickers. "Fill" button
   calls `/cineprompt/fill`.
2. Editable field list showing the returned field-state — the user can
   override any snapped value before building.
3. Model picker (veo/sora/kling/...). "Build prompt" calls `/cineprompt/build`
   and displays the assembled prompt text.
4. fal.run API key input (never sent to the worker — stored in
   `localStorage` only, set once) and a "Generate" button that calls fal.run
   directly from the browser.
5. On completion: video preview plus a "Save" button that calls
   `/cineprompt/save`.
6. A history section below, backed by `GET /cineprompt/history`, showing past
   generations with thumbnails.

Key storage: `localStorage.getItem('falrun_api_key')`. No request to the
worker ever carries this value.

## Error handling

- `/cineprompt/fill`: a `FillError` (both providers failed, or the acceptance
  gate rejected the response) returns HTTP 422 with the message verbatim. The
  frontend shows it inline. No fabricated field-state — consistent with the
  engine's existing "never fabricate" guarantee.
- `/cineprompt/save` video download: if the fal.run URL has already expired or
  times out, return 502 with a clear message and do **not** insert a DB row
  with a broken `local_path`. The file write happens before the DB insert;
  insert only on a successful write, and clean up the partial file on any
  failure — no half-saved generation.
- The fal.run call itself is entirely client-side. Its errors surface directly
  from fal.run's response in the browser; the worker has no role in handling
  them.

## Testing

- `test_routes_cineprompt.py`: route tests patching `fill_from_scene` and
  `build_prompt` directly — never reaching Ollama or DeepSeek — plus a `save`
  test with a stubbed `httpx` download (success and failure-cleanup cases).
- No test touches fal.run; it's client-side and outside the worker's test
  boundary entirely.
- The existing 297 cineprompt engine tests are untouched — routes call the
  engine, they don't modify it.

## Out of scope (still)

- Share links, saved projects, subject library (separate future items)
- Additional BYOK providers beyond fal.run (venice.ai, evolink.ai)
- Visual/aesthetic design of the Cinema page (blocked on the `frontend-design`
  skill activating after session restart; this spec covers structure only)
