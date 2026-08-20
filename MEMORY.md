# Lamka Labs Studio — Memory Note

> Obsidian-style durable note. Drop into your vault under `Projects/Lamka Labs Studio/`.
> Capture what was built, what's settled, what's open — so the next session (or
> you in 3 months) doesn't re-litigate decisions or re-discover bugs.

**Project:** AI pipeline for compliant US/India finance content (X + IG).
**Owner:** UMinkoo (sole publish authority).
**Started:** 2026-07-25. **Last update:** 2026-08-14.
**GitHub repo:** `khooptong-sudo/lamka-labs-studio` (transferred/renamed from `khooptong-creator/fin-content-engine`).
**Local folder:** `F:\lamka-labs-studio` (renamed from `F:\Content Creation Project` on 2026-08-14).

---

## What this is

A human-in-the-loop content operation. Automated pipelines read financial news
(US + India), draft posts/threads/carousels/replies in your voice, run every
word through a compliance gate, and queue it in an approval dashboard. Nothing
publishes without your click. You are the editor-in-chief of a newsroom staffed
by three cheap, tireless LLMs.

**Codename:** The Cyborg Desk.
**Source of truth:** `fin-content-engine-FINAL-blueprint.md`.
**Phase map:** blueprint Part I §6 (P0 through P6).

### Session-close update — 2026-08-09

- The current YouTube work is **YT P6 — research-first 3D Shorts**. The finance path is now human-selected from a dated, linked-source Inbox; automatic scripting receives the bounded source packet and does not run for manual ideas.
- The 3D Short path is image-led and vertical; Story Film remains the separate low-poly Three.js landscape backend. Local ComfyUI and OpenAI image providers are selectable per run.
- Disk recovery after a GPU thermal shutdown found one complete Kids render (`videos/story-c88b4e8b-52bc-425b-860e-3c8d2feb9f05/renders/video.mp4`, 41 MB, with `upload.txt`) and one non-publishable interrupted Kids run (`videos/story-b9e889ee-c6e8-4b33-9e3e-9d636d021f04`): storyboard, index, and six voice clips exist, but no cinematic images, frame compositions, render, thumbnail, or upload packet.
- Do not resume the interrupted run blindly. Confirm cooling and ComfyUI readiness first, then rerun it as a new job; only a completed render plus review is a draft.

### Session-close update — 2026-08-10

- Shipped the CinePrompt Studio **Cinema page** (`/cinema`): the finished-but-previously-unwired `worker/app/cineprompt/` prompt-assembly engine (318 tests incl. golden fixtures against the JS oracle) now has a real consumer. Scene description → LLM Fill or manual category-grouped picker (8 sections, ~130 fields, multi-select chips) → assembled prompt → BYOK fal.run (Kling 2.0) generation → save + history. Four new worker routes, one migration (`cineprompt_generations`). Full detail: `docs/superpowers/specs/2026-08-10-cineprompt-studio-cinema-design.md` and the sibling vocab-picker spec/plan in the same directory.
- Also recovered a large stash of pre-session work-in-progress that had gotten swept into task commits and then auto-stashed by a `git pull --rebase`: the Lamka Labs Studio GUI redesign, the 48-hour fresh-news-inbox filter, and cinematic-image-provider/voice-key wiring. All landed on `main`, correctly attributed under their own commit messages, not folded into the Cinema work.
- **Deferred, not forgotten:** the Cinema page's visual/aesthetic design (colors, spacing, motion) is unstyled beyond reusing existing Tailwind tokens. Blocked on the `frontend-design` skill, re-enabled in `.claude/settings.local.json` this session but requiring a Claude Code session restart to actually activate.
- Live-browser confirmation of the picker's rendered behavior was never fully completed — a Claude-in-Chrome tool outage blocked it mid-session. What WAS verified: two independent code-trace reviews, an API-level `curl` check, and the full 318-test engine suite. Worth 30 seconds in a browser before trusting this further, per the `START_LAMKA_LABS_STUDIO.bat` instructions in `docs/youtube/YT-HANDOFF.md`.

### Session-close update — 2026-08-20

- **Direction set for the X/Twitter product.** The owner's loop (scrape news → skim for
  interest → agents expand → publish → agent-drafted replies he approves) maps onto the
  blueprint stage for stage: P1 ingest (deployed) → P2 score+draft+gate → P4 publisher →
  P5 replies. Only stage one exists. `drafts`, `mentions`, `replies` are schema with
  nothing writing to them.
- **Content posture decided:** educator/analyst, may name and analyse specific companies,
  **never** recommendations. "Investment tips" was raised and walked back to this. The
  practical-know-how vertical is deliberately named `practical_skills`, not `tips`,
  because in P2b the vertical label is injected into the drafting prompt and would prime
  advisory register.
- **Voice decided:** two X profiles — Min Khooptong in first person, plus a Lamka Labs
  masthead — selected per archetype. Note the owner's real name is **Min Khooptong**;
  "UMinkoo" recorded elsewhere in this file is a nickname.
- **Draft trigger decided:** score everything automatically, draft only what the owner
  picks from the Inbox. Matches what YT P6 settled on and keeps spend proportional to
  what actually publishes.
- **§4 Voice Pack is contaminated.** It lists five *ElevenLabs narrator* personas (Teen
  Boy, Baby's Voice, "3 to 5 minutes") fused with genuinely X-specific rules. The half
  that matters for X — what the handle sounds like — was never specified. P2b must not
  "seed from §4" without untangling this.
- **P2 was split** into P2a (Score & Inbox) and P2b (Draft & Gate) so each half is
  independently verifiable, per decision #1. P2a is in flight on branch
  `p2a-score-and-inbox`; see `PROGRESS.md` and the SDD ledger noted below.
- **The blueprint's §8 routing table names models this deployment cannot call.** There is
  no Anthropic key and no Moonshot key. Real providers are Gemini, DeepSeek, OpenAI —
  three, which is one more than L2's cross-model rule needs.
- **The "11 pre-existing DB test errors" were never a defect.** They were only ever an
  absent local database. `docker compose up -d db`, create the `fce` role that
  `001_init.sql`'s D4 GRANT block expects (it exists on the VPS, not locally), apply the
  11 migrations, and the suite goes to **655 passed / 0 errors**. Supabase is not needed
  and must not be reintroduced — decisions #32/#33 dropped it deliberately.
- **`fce.lamkalabs.com` returns HTTP 525** (Cloudflare reached the origin on 443 but the
  TLS handshake failed). P1's "final curl pending" is actually a broken public endpoint.
  Needs an SSH session; nothing in P2a depends on it.
- **Deferred, tracked:** occasional beginner-facing infographics for the X account. The
  mechanism is already designed (§8: HTML template → Playwright screenshot, specced for
  IG carousels at P4) and the repo has HTML-to-image machinery already. The trap to
  design around: L1/L2 gate draft *text*, so image copy bypasses the compliance wall
  unless it is extracted and gated before render.

---

## Non-negotiables (governs every phase)

1. **Never auto-publish.** Your approval click is the compliance backstop AND what keeps you the genuine author.
2. **Compliance wall.** Educator + analyst + commentator, NEVER advisor. Three-layer gate (L1 regex / L2 cross-model judge / L3 human).
3. **No trading-signal overlap.** Co-located on the same VPS but fully isolated (separate DB on port 5433, separate `fce` user, separate services).
4. **Resist a third automated LLM layer.** Two models + human is the right depth.

---

## Where we are (2026-07-29)

**Phase 1 (Spine + Reader) — DEPLOYED. Worker live on the VPS.**

- Codebase: 60/60 unit tests green; live ingest verified (50 items fetched + embedded in one trigger).
- Deploy: all 9 phases done except the final public-HTTPS curl.
- Topology: bare process worker + embedder, host Postgres, behind the desk's Caddy.
- See `docs/P1-HANDOFF.md` (full deploy saga + bug list), `PROGRESS.md` (canonical status).

**YouTube Pipeline (Phase B) — IN PROGRESS (Local / Worker)**
- AI Scripting (Phase 2): Integrated `google-genai` using Gemini 1.5 Flash. Scripts are generated in valid Markdown with YAML frontmatter, strict compliance rules applied via DB configs.
- Voice/Audio TTS (Phase 3): Integrated ElevenLabs API. Worker parses Markdown to extract `Voiceover:` lines, maps personas (Teen boy, Adult Female, etc.) to ElevenLabs voice IDs, and synthesizes `audio.mp3`.
- Next: YouTube API Auto-Upload (Phase 4).

---

## Architecture decisions that won't change

- **Self-host everything in P1.** No Railway, no Supabase, no cloud DB, no cloud embeddings. Zero external dependencies.
- **Bare process, not Docker** for worker + embedder. systemd supervises.
- **Host Postgres 16 + pgvector on port 5433.** Timescale owns 5432; Ubuntu auto-bumped.
- **Local embedder (Option C):** `embedder/app.py` + systemd unit, `127.0.0.1:8001`, gte-small via sentence-transformers.
- **Worker on `0.0.0.0:8002`.** Caddy reaches via Docker bridge gateway `172.18.0.1`. ufw (22/80/443 only) blocks external.
- **Co-located with trading desk**, isolated via dedicated `fce` user + separate DB + separate systemd services.
- **Behind the trading desk's existing Caddy** (`desk-caddy-1`) — additive vhost, not a second Caddy.
- **Two-tier config:** env vars for secrets/structure, `config` table for tuning.
- **All jobs `async def`**, asserted at registration (decision #22). Regression-tested against lambda wrappers.
- **FP ceiling ≤2** is the load-bearing clustering criterion (decision #23).
- **Clustering threshold 0.92** (not the spec's 0.78 guess) — empirically tuned.

---

## VPS access

- **Host:** `160.250.204.73` (SSH as `root`).
- **Public domain:** `fce.lamkalabs.com` (DNS A record via Porkbun/Cloudflare).
- **Trading desk hostname:** `desk.lamkalabs.com` (same box).
- **fce DB password:** URL-safe (letters+digits+hyphens+underscores only — never `@:/?#%`). Stored locally at `F:\Content Creation Project\FCESupa DB PW.txt`.
- **Ports:** worker 8002, embedder 8001, Postgres 5433. Trading desk owns 5432/8000/443.

## Day-to-day ops (on the VPS, as root)

```bash
# Check services
systemctl status fce-worker --no-pager
systemctl status fce-embedder --no-pager

# Health + stats
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8002/stats
curl https://fce.lamkalabs.com/health     # public

# Update code after a change
sudo -u fce git -C /opt/fce/current pull
systemctl restart fce-worker
systemctl restart fce-embedder            # only if embedder code changed

# Logs
journalctl -u fce-worker -f
journalctl -u fce-embedder -f

# Reload Caddy after Caddyfile change
docker exec desk-caddy-1 caddy validate --config /etc/caddy/Caddyfile
docker exec desk-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```

---

## GitHub

- **Repo:** `khooptong-creator/fin-content-engine` (private).
- **Auth gotcha:** `khooptong-sudo` and `khooptong-creator` are two separate accounts. Push must authenticate as `creator`.
- **Security:** `FCESupa DB PW.txt` was accidentally committed once; scrubbed via `git commit --amend` before push; `.gitignore` hardened.

---

## Known bugs that recurred (avoid re-discovering)

### Build phase (pre-deploy)
1. **psycopg3 ≠ asyncpg.** Use `%s` placeholders (not `$1`), cursor pattern, `row_factory` as a property. Helpers: `_fetchone`/`_fetchall`/`_fetchval`.
2. **Pool configure callback must not leave transactions open.** Only `register_vector_async` + `row_factory`.
3. **Windows + psycopg3 needs `WindowsSelectorEventLoopPolicy`** (deprecated in 3.16).
4. **APScheduler 3.11 drift:** `AsyncIOExecutor()` takes no `max_workers`; `_job_defaults` is a dict; use `inspect.iscoroutinefunction`.
5. **Clustering threshold 0.92, not 0.78.** gte-small's in-domain baseline cosine is ~0.79.

### Deploy phase
6. **DB password must be URL-safe** (no `@:/?#%`) — psycopg3 parses the connection string per RFC 3986.
7. **Migrations run as `postgres` → tables owned by `postgres` → worker as `fce` gets `permission denied`.** Fix: GRANT block in `001_init.sql` + `ALTER DEFAULT PRIVILEGES`.
8. **Lambda wrappers break the async-def invariant.** `inspect.iscoroutinefunction(lambda: ...)` is `False`. Use explicit `async def` wrappers in `build_job_specs()`.
9. **sentence-transformers loader needs `HF_HOME` pinned** in the systemd unit, or it treats the model id as a relative path and fails on permissions.
10. **Host Postgres on 5433, not 5432** — Timescale owns 5432; every `psql`/`.env` must use `-p 5433`.

### YouTube pipeline phase
11. **Ratio guards cannot catch a truncated input.** `MAX_SILENT_RATIO` and `MAX_PLACEHOLDER_RATIO` both score a one-frame stub at 100%. Length needs its own check (`MIN_SCRIPT_FRAMES`).
12. **Never fabricate a script when the LLM fails.** The old stub fallback turned a Gemini 503 into a 5-second video recorded as a publishable draft. Retry, then raise.
13. **Patch the dispatcher, not a backend.** Mocking `_generate_frame_compositions` let `FRAME_BACKEND=local` route around the mock and fire live HTTP at Ollama. Patch `_build_frames`.
14. **Never infer degradation by value equality.** `plan == heuristic_plan(...)` is a false positive whenever the model legitimately agrees. Return an explicit flag.
15. **ElevenLabs free tier:** `premade` voices only (library voices → 402), 2 concurrent requests (→ 429), SDK v2 dropped `client.generate()` for `text_to_speech.convert()`.
16. **The 7B plans each frame in isolation** — it repeats archetypes and drifts into Chinese unless already-used shapes are excluded from the menu and English is pinned in the prompt.
17. **Don't run `pytest` during an end-to-end run.** DB tests truncate tables; the seeded story vanishes mid-render and surfaces as a `ForeignKeyViolation` that looks like a pool/commit bug.
18. **Migration 006's columns were dead.** Everything read `body->>'channel_id'`; the real columns sat NULL/default, so any schema-trusting SQL read every draft as `'manual'`. Now written to both.

### CinePrompt / Cinema page phase
19. **The FastAPI worker never hot-reloads.** `run_worker.py` has no `--reload`. Editing Python and testing against an already-running process serves stale code with zero warning — silently 404s a brand-new route, or serves a pre-fix bug, with no error pointing at the real cause. Recurred three separate times in one session (a route silently missing, then a data-dedup fix silently not applied twice). Always restart the worker process after a backend code change before trusting a live check against it; a green `pytest` run proves nothing about what a *running* process is currently serving.
20. **A `git pull --rebase` run by a subagent mid-task can auto-stash unrelated pre-existing uncommitted work.** If the working tree has substantial dirty state when a rebase needs a clean tree, the stash silently absorbs everything, not just what the rebase needed out of the way. Always check `git stash list` after any task that ran a rebase; recovering it later means diffing against the stash's actual base commit, since local history may have moved on since it was created.
21. **A plan's stated technical premise about existing code needs to be tested, not just read.** The Cinema plan asserted `build_prompt` already accepted a list value for any field ("`nl_join` handles both"). True for simple fields, false for every field routed through a merge rule (`assemble.py`'s `_merge_rules`) — those functions do raw string `.split()`/`.endswith()`/concatenation and either crash or silently embed a Python list repr into a prompt shipped to fal.run. No task-scoped review caught it because no single task's diff contained both the picker's multi-select capability and the merge-rule code it would eventually feed. Only a final whole-branch review that actually *ran* every pickable field through the real pipeline surfaced it.
22. **Vendor data files can have internal duplicates; dedupe defensively, don't hand-edit the vendor file.** `cineprompt`'s `data/base.json` (MIT-licensed, "never edit by hand") lists one `movement_type` value twice — a vendor data-quality issue. `vocab.py`'s `values_for` now dedupes across base+overlay together (not just overlay-against-merged) so this class of bug can't resurface for any field, present or future.

---

## What's NOT in P1 (don't build these yet)

- Scoring, drafting, compliance gate, voice pack → P2.
- Any GUI → P3 (Next.js, provisional).
- Publishers → P4 (X API, IG Graph).
- Reply engine → P5.
- Analytics + feedback loop → P6.
- LE price-table content triggers → P2 (drafting concern).
- NSE scraping → out of scope; ships `active=false` if no RSS.

---

## How to resume

1. Read `PROGRESS.md` for canonical status.
2. Read `docs/P1-HANDOFF.md` for the full deploy saga + bug list.
3. Read `docs/P1-VPS-DEPLOY-RUNBOOK.md` for the step-by-step (Phases 0–9).
4. Read `docs/P1-DEPLOY-SOAK-CHECKLIST.md` for the 24h soak.
5. The blueprint (`fin-content-engine-FINAL-blueprint.md`) is the source of truth for everything after P1.
6. The YouTube expansion is detailed in `docs/youtube/YT-STRATEGY-OS-FINANCE.md`, `docs/youtube/YT-STRATEGY-OS-BABY.md`, and `docs/youtube/YT-HANDOFF.md`.
7. **Latest session handoff is at the bottom of `docs/youtube/YT-HANDOFF.md`** (2026-07-31) — first true end-to-end production run, the guards it forced, and the ranked open items.
