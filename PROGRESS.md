# Lamka Labs Studio — Progress Tracker

**Project:** AI pipeline for compliant US/India finance content (X + IG).
**Source of truth:** `fin-content-engine-FINAL-blueprint.md`.
**Canonical phase map:** blueprint Part I §6.
**GitHub repo:** `khooptong-sudo/lamka-labs-studio` (transferred/renamed from `khooptong-creator/fin-content-engine` on 2026-08-14).

---

## Phase status

| Phase | Status | Notes |
|---|---|---|
| **P0 — Accounts & keys** | 🟡 Partial | GitHub ✅, Supabase ❌ (dropped in P1), Anthropic ⬜ (P2), Railway ❌ (dropped — VPS), X/Meta ⬜ (P4) |
| **P1 — Spine + Reader** | ✅ Deployed, ⚠️ **silently dead 2026-07-29 → 2026-08-20** | Worker live on VPS. **Ingest stopped for three weeks**: `register_jobs` wrapped every advisory-locked job in a plain lambda, which `AsyncIOExecutor` never awaits, so `poll_rss`/`poll_edgar`/`poll_nse`/`cluster_new`/`embed_retry`/`autopilot_ideation` all evaporated on each tick. Only `db_health` ran (lock-exempt), so `/health` kept reporting healthy. Fixed in `59c533e`; ingest verified again 2026-08-20 (50 fetched/embedded, real embedder). Public HTTPS still **525**. |
| **P2a — Score & Inbox** | ✅ **Merged to `main`** (`1cd78ae`) | LLM router (`worker/app/llm/`: task-keyed routing, retry, fallback, repair-once), closed `ARCHETYPES`/`VERTICALS` taxonomy, `score_new` every 15 min under advisory lock, scoring columns on the Inbox with opt-in `order=score`. 682 tests green. **Live run 2026-08-20:** 36 items ingested → 36 stories → 25 scored by Gemini, score spread 25-82 (mean 59.7, 14 distinct), zero out-of-set enums, zero audit failures; ranked Inbox verified through the GUI proxy. Spec/plan in `docs/superpowers/`. **Not yet deployed to the VPS.** **Debt:** `youtube.py` still calls providers directly instead of via `llm/router.py`; retire at the end of P2b. |
| **P2b — Draft & Gate** | ⬜ Not started | Voice Pack, archetype-aware drafting, L1 regex gate, L2 cross-model judge. Needs a `voice_profile` migration: that table has `version`/`system_prompt`/`banned_phrases`/`example_posts` but **no name or key column**, so it models one voice. Two X profiles are wanted (Min Khooptong first-person, and a Lamka Labs masthead), selected per archetype. |
| **P2.5 — Newsletter + Funnel** | ⬜ Not started | |
| **P3 — Cockpit (GUI)** | 🟡 In progress | Next.js in `gui/`. Existing pages: dashboard, `drafts`, `films`, `settings`, `docs`. New `/x` page (sidebar "X Post") is a three-column manual-X cockpit: story Inbox, rewrite/poster panel with tone presets, reply helper. Calls worker via `NEXT_PUBLIC_WORKER_URL`. PosterCard renders 1080×1350 HTML/CSS and exports PNG via `html-to-image`. GUI `next build` clean. |
| **P4 — Publishers** | 🟡 Manual path active, auto blocked | X direct publish returns `402 Payment Required` (credits depleted). Manual copy-paste from `/x` is the active publisher until revenue justifies the $100/mo X write tier. |
| **P5 — Reply engine** | ⬜ Not started | |
| **P6 — Analytics & hardening** | ⬜ Not started | |
| **YT P1/P2 — Scripting & Audio** | ✅ Completed | LLM Markdown scripts (Gemini) + ElevenLabs TTS integrated in Worker. |
| **YT P4 — YouTube API Upload** | ❌ Dropped | Uploads are manual. Publish path deleted 2026-08-06; see YT P5. |
| **YT P5 — Per-channel config** | ✅ **DEPLOYED** | Two channels (finance, kids) off one engine. Compliance floor as code constants. Every render ships `upload.txt` with title + SEO description. Migration 008 + channels config applied to local and VPS Postgres. Deployed to VPS 2026-08-06 (was stuck behind safe.directory). |
| **YT P6 — Research-first 3D Shorts** | 🟡 Live smoke complete; review/hardening open | `/films` makes the normal Short flow a 1080×1920 image-led 3D route. One Kids short rendered locally with its manual-upload packet on 2026-08-09. A second ComfyUI run was interrupted by a GPU thermal shutdown after narration, before image generation/render; it is not a draft. Migrations 009–010 add official feeds and enforce a 48-hour, dated-only fresh-news Inbox. |
| **CinePrompt — Studio Cinema page** | 🟡 Shipped, visual pass pending | `/cinema`: describe a scene → CinePrompt engine (`worker/app/cineprompt/`, 318 tests incl. golden fixtures) fills fields via LLM or manual category-grouped picker (8 sections, ~130 fields, multi-select) → build prompt → BYOK fal.run (Kling 2.0) generation → save + history. 4 worker routes (`/cineprompt/fill`, `/build`, `/save`, `/history`, `/vocab`), migration 011. Key never reaches the worker. Deferred: aesthetic/visual design pass, blocked on `frontend-design` skill needing a session restart to activate. |

---

## P1 deploy sub-status (complete)

| # | Step | Status |
|---|---|---|
| 0.1 | SSH as `root@160.250.204.73` | ✅ |
| 0.2 | GitHub repo (`khooptong-sudo/lamka-labs-studio`) | ✅ |
| 0.3 | ~~Supabase edge fn~~ → local embedder (Option C) | ✅ |
| 1 | apt install (postgres, python, git, curl) | ✅ |
| 2 | `fce` user + `/opt/fce` + repo cloned | ✅ |
| 3 | Postgres `fce` DB + pgvector on **port 5433** | ✅ |
| 4 | venvs (worker + embedder) + gte-small model | ✅ |
| 5 | migrations (15 tables, 12 sources, 4 config) | ✅ |
| 6 | `.env` (port 5433, embedder 8001) | ✅ |
| 7 | systemd units (embedder 8001 + worker 8002) | ✅ |
| 7.3 | live ingest verified (50 items fetched+embedded) | ✅ |
| 8 | Caddy vhost on `desk-caddy-1` | ✅ |
| 9 | public HTTPS `/health` | ⏳ final curl pending |

**Live-ingest proof:** `{"fetched":50,"new":50,"embedded":50,"embed_failures":0}` from ET Markets. `/stats`: items=50, embedding_health=ok, orphaned=0.

**Script-quality gates ops (piece 1, merged):** deployments whose `llm` config row
already exists must add the route once, or every fact-check fails loud with
`no available provider for task 'fact_check'` and nothing generates:
`UPDATE config SET value = jsonb_set(value, '{routing,fact_check}', '{"primary": "deepseek", "fallback": "openai"}') WHERE key = 'llm';`

---

## Deploy bugs (the full list — 9 found, all fixed)

| # | Bug | Fix landed in |
|---|---|---|
| D1 | Supabase edge fn OOM-killed (`EarlyDrop`, 10MB ceiling) | New local embedder (`embedder/`, Option C) |
| D2 | Host Postgres on 5433 not 5432 (Timescale owns 5432) | All `psql`/`.env` use 5433 |
| D3 | DB password had `@` → URL parser broke (`failed to resolve host 'ssw0rd'`) | URL-safe password; runbook guidance updated |
| D4 | Migrations owned by `postgres` → `permission denied for table config` | GRANT block in `001_init.sql` |
| D5 | Lambda wrappers broke async-def invariant (`job 'poll_rss' fn is not async def`) | Explicit `async def` wrappers in `scheduler.py` + regression test |
| D6 | sentence-transformers treated model id as relative path (`PermissionError`) | `HF_HOME` pinned in `fce-embedder.service` |
| D7 | Deprecated `get_sentence_embedding_dimension` | `getattr` fallback to new `get_embedding_dimension` in `app.py` |
| D8 | Git credential mismatch (`khooptong-sudo` vs `khooptong-creator`) | User switched `gh` auth; not a code bug |
| D9 | `FCESupa DB PW.txt` accidentally committed | Scrubbed via `git commit --amend` pre-push; `.gitignore` hardened |

---

## Decisions log (cumulative — full list)

| # | Decision | Phase | Rationale |
|---|---|---|---|
| 1 | Phase 1 = v1.0 "Spine + Reader" only | brainstorm | Each phase independently verifiable |
| 2 | GUI Next.js (provisional, P3) | brainstorm | match PMS-portal muscle memory |
| 3 | Dry-run publisher (P4) | brainstorm | develop against a log; flip env for real publish |
| 4 | Model router config-driven | brainstorm | Kimi India access non-blocker |
| 5 | LE `active=false` in P1 | brainstorm | plumbing cheap, brain in P2 |
| 6 | `entity_type` on audit_log | brainstorm | `entity` alone is ambiguous |
| 7 | gte-small 384-dim in-DB | brainstorm | $0, no new API surface |
| 8 | RLS placeholder-uid | brainstorm | avoids config-table chicken-and-egg |
| 9 | `min_items_for_story=1` | brainstorm | a single strong item can seed a story |
| 10 | NSE via RSS, disabled if unavailable | brainstorm | NSE hostility makes scraping/CSV not worth P1 scope |
| 11 | Title-weighted embeddings | brainstorm | biggest lever on clustering precision |
| 12 | Keyword fallback ≥2 tokens | brainstorm | single-token = over-merge failure mode |
| 13 | Clustering separate from ingest | brainstorm | I/O-bound vs DB-bound; failure isolation |
| 14 | Re-embed via sweep, max 3 | brainstorm | failed embeddings recoverable, not permanent |
| 15 | Cluster link frozen after assignment | brainstorm | stability over theoretical optimality |
| 16 | Atomic story creation | brainstorm | orphan prevention |
| 17 | `/stats` orphan counter | brainstorm | count drops, not just survivors |
| 18 | Single replica + advisory locks | brainstorm | removes double-fire race at deploy layer |
| 19 | `coalesce` + `misfire_grace_time=60` | brainstorm | skip missed fires, run one catch-up |
| 20 | `/health` = process+scheduler+DB only | brainstorm | source health is `/stats`, not liveness |
| 21 | Two-tier config (env + config table) | brainstorm | secrets/structure vs tuning |
| 22 | All jobs `async def`, asserted at registration | brainstorm | AsyncIOExecutor runs coroutines; mixing is silent failure |
| 23 | FP ceiling ≤2 load-bearing, N-coupled | brainstorm | under-merge bias bounded absolutely |
| 24 | Frozen fixture + provenance assertion | brainstorm | deterministic tests; mismatch fails loud |
| 25 | 24h soak with closed-market stretch + forced retry | brainstorm | soak must exercise failure paths |
| 26 | Embedding inline in ingest | review | not a queue; `embed_retry` is failure-path only |
| 27 | `db_health` exempt from advisory lock | review | a probe needing the DB to acquire a lock fails for the wrong reason |
| 28 | `embed_retry_success` audit event | review | recovery provable after the fact |
| 29 | Auto-disabled-source check in soak | review | a source can die by auto-disabling and pass the gate invisibly |
| 30 | HNSW≈exact caveat documented in TUNING.md | review | threshold tuned in one engine, enforced in another |
| 31 | Clustering threshold 0.78 → **0.92** | build | gte-small's in-domain baseline cosine is ~0.79 |
| 32 | Self-host Postgres on VPS (Option C) | deploy | Supabase free tier pause + egress caps |
| 33 | Self-host embeddings on VPS (Option C) | deploy | Supabase hosted gte-small OOM-killed |
| 34 | Bare process, not Docker | deploy | systemd > Docker for one Python process |
| 35 | Worker on port 8002, embedder on 8001 | deploy | 5432/8000/443 owned by trading desk |
| 36 | Add Caddy vhost to `desk-caddy-1`, not a new Caddy | deploy | can't run two Caddys on 443 |
| 37 | Worker binds `0.0.0.0:8002` + ufw 22/80/443 only | deploy | Caddy reaches via Docker bridge; external blocked |
| 38 | Frame design local (Ollama `qwen2.5:7b`), story text cloud | youtube | model picks an archetype + fills slots, never writes HTML — a 7B is enough and quota stops being a failure mode |
| 39 | Archetype templates, not LLM-authored HTML | youtube | a pre-validated template cannot emit an invalid composition |
| 40 | `MIN_SCRIPT_FRAMES` alongside the ratio guards | youtube | ratios score a one-frame stub at 100%; a failed script was becoming a publishable draft |
| 41 | Script generation raises instead of falling back to a stub | youtube | there is no safe fabricated script; the caller must abort |
| 42 | Channels are a fixed pair in the `config` table, not a new table | channels | two channels; a table plus CRUD buys generality nothing needs |
| 43 | Compliance rules + base blocklist are code constants, not config | channels | in config they were one GUI edit from removal, with no trace |
| 44 | Effective blocklist is a **union**, not an override | channels | removing a base term becomes inexpressible rather than merely validated against |
| 45 | Uploads are manual; publish path deleted, not gated | channels | a dormant button hardcoding `selfDeclaredMadeForKids: False` is a live COPPA hazard |
| 46 | Metadata extracted at generation time, not publish time | channels | `_parse_storyboard_frontmatter` was only called from publish; deleting publish would have discarded the SEO description |
| 47 | Metadata validated **before** the render | channels | an empty description used to burn a full ffmpeg render before failing |
| 48 | Autopilot uses each story's own channel, skips those without one | channels | one env-var channel applied to every story would publish kids topics in the finance voice, on a daily timer |
| 49 | Image-led cinematic shorts are a separate backend, not an extension of low-poly Three.js films | youtube | character-led animated storytelling needs high-fidelity keyframes; the existing code-generated landscape film remains intact and its verification path is not weakened |
| 50 | fal.run generation stays entirely client-side (BYOK key never sent to the worker) | cineprompt | matches the original cineprompt.io architecture; zero new secret-handling surface on the backend |
| 51 | Vocabulary picker reuses `fields_in_scope(mode, level)`, the exact function Fill's system prompt already uses | cineprompt | one scoping rule, not two copies that can drift apart |
| 52 | `base.json` (vendor data) deduped defensively inside `values_for`, never hand-edited | cineprompt | the file's own docstring forbids hand edits; an internal duplicate is a vendor data-quality issue, not something to patch at the source |
| 53 | Final whole-branch review must execute code, not just read it | cineprompt | task-scoped review traced `build_prompt`'s "accepts a list" claim as written in the plan and passed it; only running it against every pickable field surfaced that ~23 merge-rule fields actually crash or silently corrupt output on a list input |
| 54 | P2 split into P2a (Score & Inbox) and P2b (Draft & Gate) | p2a | Decision #1 one level down: each half independently verifiable, and the router is proven against real stories before the gate is built on it |
| 55 | Router keys on task name, not model name | p2a | Callers stay ignorant of providers; re-routing is a config edit |
| 56 | Task-to-provider map in `config`, credentials in env | p2a | Decision #21's two-tier split applied to model routing |
| 57 | `ARCHETYPES` and `VERTICALS` are code constants, not config | p2a | Same reasoning as #43: in config they are one GUI edit from removal, with no git trace |
| 58 | Scoring does not mutate `stories.status` | p2a | `status` keeps one meaning; flipping it would silently empty the Inbox and break YouTube ideation |
| 59 | The practical-know-how vertical is named `practical_skills`, not `tips` | p2a | The vertical label reaches the drafting prompt in P2b, so the taxonomy word is a compliance surface |
| 60 | `investing_concept` separate from `personal_finance_concept` | p2a | Distinct editorial lanes; merging them loses a slice the owner asked for |
| 61 | Inbox ordering is a parameter, default unchanged | p2a | Changing the shared default would silently reorder the working video queue |
| 62 | Router raises on exhaustion; no fabricated score | p2a | #41 generalized from script generation to all LLM calls |
| 63 | Frontend hosting shelved; the GUI stays local-only until the pipeline is operational | product | A cockpit for absent functionality is the shop window before the shop. Also blocked in practice: any hosted frontend needs the worker publicly reachable, and `fce.lamkalabs.com` currently returns HTTP 525 |
| 64 | X publishing stays manual until revenue justifies the API cost | p4 | Direct X API publish returns 402 (credits depleted); the $100/mo write tier is off the table pre-revenue. The GUI drafts; the owner copy-pastes. The human gate is preserved and spend stays near-zero |
| 65 | DeepSeek is the default provider for X rewrite and poster generation | p4 | Moonshot/Kimi key is rejected by the provider; DeepSeek works and is cheap. `X_REWRITE_PROVIDER` keeps it configurable so the default can change when Kimi is restored |
| 66 | Poster posters are black on white; variety comes from form, not colour | p4 | Six variants differ by card shape, tilt, bullet marker, texture, mascot, section layout and title squiggle. One ink keeps the set coherent as a feed; changing hue per poster read as six unrelated brands |
| 67 | The poster summary is a required prose paragraph, and a blank one fails generation | p4 | A poster shipped with an empty "At a Glance" box. An absent summary must be a loud failure, not a silent hole — the same reasoning as the render guards. A list-shaped provider response is joined into a paragraph rather than dropped |
| 68 | A fixed-canvas layout is verified by measurement, not estimate | p4 | `gui/src/app/poster-preview/page.tsx` renders every variant against a worst case and Playwright measures the footer against 1350px. `overflow-hidden` makes a clipped poster look fine and makes `scrollHeight` report no overflow, so eyeballing cannot catch it |
| 69 | Poster fonts are self-hosted through `next/font`, not linked from Google | p4 | `html-to-image` inlines same-origin fonts; a stylesheet linked from `fonts.googleapis.com` renders correctly on screen but exports the PNG in fallback type |
| 70 | Poster variety splits into bundled traits and independently rolled ones | p4 | Card shape, heading style, bullet marker, tilt and layout interact, so they stay bundled in a named theme a human has looked at. Mascot, scenery, underline and background pattern cannot clash with a card design, so they are rolled per poster. Ten themes therefore cover several thousand distinct posters without ever rendering an unreviewed combination |
| 71 | Band art is authored at the band's own aspect ratio | p4 | The scenery SVGs were drawn in a 1080x260 viewBox and painted into a 124px band with `preserveAspectRatio="slice"`, which silently cropped everything above the ground line. Nothing errors and nothing looks broken; the art is simply absent. Same failure class as #68 |
| 72 | Illustration is reviewed on a 1:1 contact sheet, never inside the finished poster | p4 | Four rounds of defects (pines drawn apex down, a ridge line that read as a graph, boats that read as flags on mounds) were invisible at poster scale and obvious at band scale. `poster-preview` now renders every scene alone at 1080x178 |
| 73 | The uncommitted compliance teardown is held out of git pending the owner's call | p4 | The working tree empties `BASE_COMPLIANCE_RULES` and `BASE_BLOCKLIST`, deletes `_check_compliance` from X publish and rewrite, drops the pasted-storyboard gate and the advice prohibitions from the YouTube script prompt, and deletes the bypass regression test. It reads as a half-finished fix for blocklist false positives: the smarter `find_blocked_terms` matcher exists but is fed an empty tuple. Committing a half-migrated compliance layer is worse than either end state |
| 74 | A green suite is not evidence about a guard that was removed with its test | p4 | 35 tests pass against the teardown in #73, because the tests were edited alongside it. #53 generalized: the suite proves the code does what the tests now say, never what the product still requires |
| 75 | Script contract + fact-check gate on the generated path; override boards skip both | quality-first | Hook/chapters/closing enforced by a pure validator next to MIN_SCRIPT_FRAMES; BLOCK aborts pre-TTS with audit, FLAG audits and continues to human review; drafter excluded via a new router `exclude` param so the checker is never the drafter. New `script_quality.py`, `fact_check` route default (deepseek→openai). Spec + plan in `docs/superpowers/specs/2026-09-05-*` and `docs/superpowers/plans/2026-09-05-*` |
| 76 | Cinematic image provider is Gemini, not OpenAI | visual-cost | Same `GEMINI_API_KEY` the script path uses; model env-overridable (`GEMINI_IMAGE_MODEL`, default `gemini-2.5-flash-image`). OpenAI branch, `CINEMATIC_IMAGE_*` consts and GUI copy removed; ComfyUI untouched |
| 77 | Publish packet carries A-B thumbnails + validated tags; thumbnails best-effort, tags fail-loud | piece-2 | Model paints backgrounds only, title stays in template overlay; per-variant fallback, never blocks the draft. Tags: frontmatter → draft body jsonb → upload.txt, no migration. Tag matching mirrors the committed storyboard rule and stays local — `channels.find_blocked_terms` exists only in uncommitted work. |
| 78 | Voice-to-video via ordered per-scene clips; motion from intent over 8 paths | piece-3 | Clips land on synthesis paths so probing/timing run untouched; mismatch/unprobed/oversize abort loud, no silence under owner audio. `POST /youtube/jobs/with-voice` stages files before the job starts (needs `python-multipart`, now declared). Intent line selects ease family, unknown falls back; first 4 camera paths byte-identical. API-first; no GUI upload yet. |
| 79 | GPU slot + cancel + render timeout + named stages | piece-4 | One in-process semaphore around Ollama/ComfyUI/render; cloud paths overlap. DELETE cancels live runs. Render bounded at 20 min default. fact_check/thumbnails join STAGES + GUI mirror. No scheduler rewrite. |
| 80 | History/science/mystery channels seeded merge-only; both routes proven per channel | piece-5 | Built-ins in code, merge adds missing ids only. Shared taxonomy untouched. Manual-first; feeds are a follow-up. GUI already dynamic. |
| 81 | Long-form as acts on the cinematic path; per-act gates, merged render | long-form | Outline→acts→merge; 3-4×7-9 scenes (21-36). Same validator scaled, same fact-check per act. New mode + pacing, brief labeled owner-supplied. API-first. |

---

## Cost reality (steady state, pre-revenue)

| Item | Monthly | Notes |
|---|---|---|
| VPS | $0 marginal | already paying for the trading desk |
| Postgres | $0 | host Postgres, no cloud DB |
| Embeddings | $0 | local gte-small, no cloud API |
| LLMs (P2+) | ~$5–15 | Haiku + Gemini Flash + (eventually) Kimi |
| **Total (P1)** | **~$0** | |
