# Lamka Labs Studio — Memory Note

> Obsidian-style durable note. Drop into your vault under `Projects/Lamka Labs Studio/`.
> Capture what was built, what's settled, what's open — so the next session (or
> you in 3 months) doesn't re-litigate decisions or re-discover bugs.

**Project:** AI pipeline for compliant US/India finance content (X + IG).
**Owner:** UMinkoo (sole publish authority).
**Started:** 2026-07-25. **Last update:** 2026-09-07.
**GitHub repo:** `khooptong-sudo/lamka-labs-studio` (transferred/renamed from `khooptong-creator/fin-content-engine`).
**Local folder:** `F:\Lamka Labs Studio` (renamed from `F:\lamka-labs-studio` on 2026-09-07; that name came from `F:\Content Creation Project`, 2026-08-14).

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

### Session-close update — 2026-08-20 (evening): P2a merged and proven live

- **P2a is merged to `main` (`1cd78ae`) and pushed.** 16 commits, 682 tests green. Nine
  tasks, each implemented and reviewed independently, plus a whole-branch review and a
  final fix wave. Not yet deployed to the VPS.
- **First live scoring run succeeded.** 36 items ingested from ET Markets → 36 stories →
  25 scored by Gemini. Score spread 25-82 (mean 59.7, 14 distinct values), **zero
  out-of-set enum values, zero audit failures**. The low scores were correctly reasoned:
  a daily price-move wrap scored 25 with the angle "offers no compliant, educational
  hook"; a Bitcoin price-forecast piece scored 30 as "mostly a price-forecast comment
  with an implied action". The scorer is rejecting exactly the stories that could only be
  written as recommendations.
- **Known quality gap: 65% of archetypes came back `explainer`.** The closed set is being
  honoured but not used variedly. §5 exists for editorial variety as much as compliance,
  so this wants a prompt iteration — cheap to test now the path is live.
- **Clustering is still unproven.** There is no local embedder and
  `settings.embedding_edge_function_url` still defaults to the Supabase edge function
  that decision #33 dropped, so the live run used `FCE_EMBED_MOCK=true`. Hash embeddings
  meant `merged=0` and one story per item. On the VPS the real embedder is configured
  (P1 deploy step 6, `127.0.0.1:8001`), so this is a LOCAL gap, not a production defect.
- **Trap worth fixing: `worker/tests/test_cold_start.py:80` runs
  `UPDATE sources SET active = false` and nothing restores it.** Any full test-suite run
  silently disables ingest on the local database. It bit twice in one session. The repo's
  own workflow points development and testing at the same `fce` database, so this will
  keep biting. Either restore sources in the fixture teardown, or point the suite at a
  separate database.
- **Two defects this branch caught originated in the plan, not the implementation:** a
  config loader that silently discarded DB-provided routing (`hasattr` fails for a
  `field(default_factory=...)` field), and a post-query Python `stories.sort()` that had
  always overridden the SQL `ORDER BY` — which would have made `order=score` ship doing
  nothing. Both were found by review, not by the author.
- **Blocking the VPS deploy, needs an SSH session:** does the VPS `.env` carry an LLM API
  key? P1 was ingest-only and made no LLM calls. Without one, `score_new` resolves to an
  empty provider chain and every story fails safely with an audit event — scoring nothing,
  silently, forever. Also still outstanding: `fce.lamkalabs.com` returns HTTP 525.

### Session-close update — 2026-08-20 (late): the three-week silent outage

- **Found by inspecting the VPS, not by any test: every advisory-locked job had been
  silently doing nothing since ~2026-07-29.** `register_jobs` asserted the async
  invariant on `spec.fn`, then wrapped it in a plain lambda. A lambda is not a coroutine
  function, so `AsyncIOExecutor` never awaited it. The only trace was one RuntimeWarning
  in the journal. `/health` reported healthy throughout because `db_health` is the single
  lock-exempt job. **This is deploy bug D5 recurring inside the wrapper D5's own fix
  introduced.** Fixed in `59c533e`: named `async def` wrapper plus an assertion on the
  callable APScheduler actually holds. 686 tests had passed against this bug because they
  all asserted on `spec.fn`, which is not what gets registered.
- **VPS now runs `main`.** Ingest verified live again: 50 fetched, 50 embedded, 0 failures,
  with the REAL embedder. Clustering confirmed working on real vectors (`checked=50
  merged=4 new_stories=46`) — the first genuine clustering evidence P2a has.
- **`score_new` on the VPS is blocked on Gemini free-tier quota (`429
  RESOURCE_EXHAUSTED`), not on anything broken.** The key is valid. Quota was exhausted by
  local testing the same day; it resets on Google's daily cycle. The retry path behaved
  correctly (429 → retryable → backoff → safe failure, zero fabricated scores).
- **Add `DEEPSEEK_API_KEY` to `/opt/fce/.env`.** The routing log now says exactly what is
  wrong — `llm_routing_decision chain=['gemini'] skipped=['deepseek']` — and with a second
  provider present the 429 would have fallen through and scored.
- Note: a Gemini key of the form `AQ.A…` (53 chars) is valid. It is NOT the older `AIza…`
  39-char format, and assuming otherwise wasted a diagnostic step.

### Session-close update — 2026-08-20 (night): manual X cockpit shipped

- **X/Twitter is now a manual-assist workflow.** The GUI has an `/x` page (sidebar "X Post") with a three-column layout: Inbox → rewrite/poster → reply helper. The owner picks a story, chooses a tone (concise, analyst-educator, humorous, sarcastic, bullish, bearish) or types a custom one, clicks **Rewrite**, then copy-pastes the draft into X. Comments can be pasted into the reply helper for a suggested reply. Nothing auto-publishes.
- **Why manual:** direct X API publish returns `402 Payment Required` (credits depleted). The X write tier is $100/month, so the loop is human-gated until the account generates revenue.
- **Provider switch:** rewrite and poster generation now use **DeepSeek** by default, controlled by `X_REWRITE_PROVIDER` (default `deepseek`). Moonshot/Kimi key continues to be rejected by Moonshot's API, so DeepSeek is the working path. `DEEPSEEK_API_KEY` is set in `/opt/fce/.env` on the VPS.
- **Poster generator:** generates 1080×1350 educational infographic posters from a story or from a manual topic + bullet points. Render is HTML/CSS via `PosterCard`, exported to PNG with `html-to-image`. Every image is watermarked `equities.lamkalabs.com · Lamka Labs`. The footer also carries an educational disclaimer.
- **Faster freshness:** default RSS/NSE poll intervals dropped from 30 min to 10 min; cluster/score job dropped from 15 min to 10 min. Edgar stays hourly.
- **Backend routes added:** `GET /x/stories`, `POST /x/rewrite`, `POST /x/reply`, `POST /x/poster/story`, `POST /x/poster/text`.
- **Tests:** worker suite at **724 passed / 6 warnings**; GUI `next build` clean.
- **Deployed to VPS:** `git pull` in `/opt/fce/current`, `systemctl restart fce-worker`, `/health` green. End-to-end checks for `/x/rewrite` and `/x/poster/text` returned valid DeepSeek output.
- **VPS launcher:** `START_Lamka_Labs_Studio_VPS.bat` starts the GUI pointed at `http://160.250.204.73:8002` and opens `http://localhost:3000/x`.
- **Vault/RAG updated:** three new atomic pages ingested; graph rebuilt with `--no-llm` because Anthropic credits are depleted.

### Session-close update — 2026-09-06 (night): VPS render pipeline unblocked end-to-end

- **The YouTube film jobs run on the VPS worker, not the local one.** The GUI launcher
  sets `NEXT_PUBLIC_WORKER_URL=http://160.250.204.73:8002`; the local worker and local
  `videos/` are only a dev convenience. Two rounds of "fix it locally, watch it fail
  again" burned a session before `journalctl -u fce-worker` on the VPS was read. Rule:
  when testing the film workflow, fix → commit → push → `git -C /opt/fce/current pull`
  → `systemctl restart fce-worker`, then read the VPS journal.
- **Root cause of "Stopped at render / youtube rendering failed": the VPS had Node 20;
  hyperframes ≥ 0.8.27 requires Node ≥ 22.** `npx hyperframes` exited 1 instantly with
  the version complaint on stderr, and the old worker code swallowed stderr. Fixed in
  `worker/app/youtube.py` (commit `ebf50a8`): pinned `hyperframes@0.8.30` via
  `HYPERFRAMES_VERSION`, `npx --yes` so a cold cache can't stall on the install prompt,
  and the render failure now logs + raises with the last 20 stderr lines.
- **VPS Node 22 is a side-install at `/opt/node22`, not a system upgrade** — the trading
  desk's Prisma node service keeps Node 20. A systemd drop-in
  (`fce-worker.service.d/node22.conf`) puts it on the worker's PATH and also sets
  `PRODUCER_ENABLE_CHUNKED_ENCODE=true`, `PRODUCER_CHUNK_SIZE_FRAMES=300`,
  `HYPERFRAMES_TIMEOUT_SECONDS=3600`. Without chunked encode the Chrome tab dies
  mid-capture (`Target closed`, ~frame 465/1482) on the 8 GB box; with it, memory holds
  ~2.9 GB used and a 49 s film renders in ~21 min. Swapfile raised 256 MB → 4 GB.
  Full detail: `docs/P1-VPS-DEPLOY-RUNBOOK.md` cheat-sheet section.
- **"Stopped at shots / no image data" was a transient Gemini blank.** The image
  endpoint occasionally returns a response with no image part; the old code raised on
  the first blank and killed the film. Fixed in `worker/app/scene3d/backend.py`: up to
  4 attempts (`GEMINI_IMAGE_MAX_ATTEMPTS`) with backoff, and the error now carries
  `finish_reasons`/`block_reason` so a real safety block is distinguishable from a
  transient blank. 23 scene3d tests green incl. a new recover-from-blank test.
- **Verified live on the VPS:** the failed story's film rendered manually as `fce`
  with the worker's exact environment (26.4 MB, 49.4 s, 21m 27s); worker restarted with
  the new env confirmed via `/proc/<pid>/environ`; `/health` green. A fresh GUI job
  still needs to be re-run to produce the complete draft (thumbnails + registration)
  — the render alone is not a draft.

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
11. **The VPS checkout is a symlink: `/opt/fce/current` → `/opt/fce/releases/initial`.** `find /opt/fce/current` does NOT traverse it — root-owned scp leftovers (e.g. `scripts/`, `worker/app/script_quality.py`) stayed invisible and broke `git reset --hard` with `unable to unlink ... Permission denied`. Use `find -L`, chown the REAL path (`chown -R fce:fce /opt/fce/releases/initial`), and always run git as the `fce` user (root-run git poisons `.git/index` and refs ownership). After any scp-to-VPS deploy, expect ownership drift — chown before pulling.

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

### Local dev on Windows
23. **Windows excludes host ports 5427-5526 and 8000 from binding** (`netsh interface ipv4 show excludedportrange`), so `docker compose up -d db` (host 5432) and the worker default (8000) both fail and the Studio page shows ERR_CONNECTION_REFUSED. Local workaround, env-only, no repo changes: run fce-db via `docker run` on host port **15432** reusing the `fce_pgdata` volume, start the worker with `WORKER_PORT=8002` + `FCE_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:15432/fce`, and start the GUI with `NEXT_PUBLIC_WORKER_URL=http://127.0.0.1:8002`. (8001 is the embedder's documented port; 5433 sits inside the excluded range, so neither is a substitute. `START_LAMKA_LABS_STUDIO.bat` is patched for this: DB via `docker run` on 15432 reusing `fce_pgdata`, worker on 8002, GUI pointed at it.)
24. **VPS has no GPU; local RTX 3070 is exposed via Cloudflare quick tunnel** (`cloudflared tunnel --url http://127.0.0.1:8188` → `https://<random>.trycloudflare.com`). VPS `COMFYUI_BASE_URL` points at the tunnel, so VPS renders hit the local GPU. Quick tunnels are ephemeral — after a reboot or `cloudflared` restart the URL changes; refresh with `powershell -ExecutionPolicy Bypass -File scripts/refresh-comfy-tunnel.ps1` (kills old tunnel, starts new one, patches `/opt/fce/.env` and restarts `fce-worker`). The tunnel process is detached via `wscript` so the `bash` tool's ChildProcess killer does not reap it.

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


---

### Session-close update — 2026-09-07

**Shipped: true motion video for 3D Shorts (image-to-video per scene) + the VPS database repair that was blocking all builds.**

**VPS database drift (root cause of "STOPPED AT THUMBNAILS — column channel_id does not exist").** The VPS Postgres had only migrations 001–005 applied; 006–015 existed on disk but had only ever been hand-applied in fragments (that's why `jobs`, `stories.channel_id`, and `cineprompt_generations` existed while `drafts.channel_id`/`upload_preference` and the widened platform/format CHECKs from 006 did not). Fix: `pg_dump -Fc` backup to `/tmp/fce-pre-migration-20260906.dump` (note: `/tmp` is ephemeral — re-dump before any risky work), then applied 006→015 in order with `ON_ERROR_STOP=1`; all are idempotent so the partially-present ones skipped cleanly. **Lesson: after any VPS deploy, diff `supabase/migrations/` against what's actually applied — fragments were applied ad hoc at least twice.** A migration-check step in the deploy path is the durable fix, still unbuilt.

**Motion pipeline (v1 then v2, both validated end-to-end on the VPS):**
- Every scene still gets its generated keyframe (style anchor, thumbnail source, I2V start frame). When a build selects a motion provider, the keyframe is animated by an image-to-video model, then ffmpeg-normalized to the scene's measured narration duration (model audio stripped — narration is always the fact-checked TTS; clip trimmed or `-stream_loop`-ed to fit). Per-scene timing model untouched, so narration sync is identical to Ken Burns builds.
- **v1**: `<video>`-based HyperFrames composition (`render_cinematic_motion_frame`, same determinism contract as the Ken Burns renderer). Validated: "The Ghost Clouds with No Stars" (65s) — frame extraction proved real camera moves + character action, not Ken Burns.
- **v2**: motion builds skip HyperFrames entirely — `scene3d/assemble.py` does single-pass ffmpeg assembly (concat → baked overlay PNG via Pillow → voice tracks with `adelay` at `frame.start + voice_offset` → bgm at 0.35 volume, `storyboard.BGM_VOLUME`). **Render stage: 37 min → 2 min. Same story head-to-head: v2 is native 1080p (v1 was 720p upscaled by the browser plus an MJPEG capture intermediate), single clean encode CRF 18.**
- Providers (Films page chip group, short mode only): `off` (Ken Burns, default) / `veo` (Google, `GEMINI_API_KEY`) / `kling` (fal.run queue REST, needs `FAL_KEY`, port of the Cinema page flow). `GET /youtube/motion-providers` mirrors `/youtube/image-providers`. New env: `GEMINI_VIDEO_MODEL`, `FAL_KEY`, `MOTION_MAX_PARALLEL` (default 3), `VEO_MAX_ATTEMPTS` (8), `VEO_RETRY_INITIAL_SECONDS` (20).
- **429 resilience**: Veo submit and poll retry with exponential backoff on quota errors only (other errors reraise immediately); a retried build reuses already-normalized clips per scene (`motion_clip_reused`) — only interrupted scenes regenerate.

**Gemini quota reality (cost the session its second half):** a consumer Gemini subscription (AI Pro/Ultra) does NOT include API quota — the API key draws from AI Studio free-tier pools. `veo-3.1-generate-preview` has a small daily pool; the validation builds exhausted it (~15 clips). `veo-3.1-fast-generate-preview` and `-lite-` are **separate pools** and stayed open — VPS `/opt/fce/.env` now sets `GEMINI_VIDEO_MODEL=veo-3.1-fast-generate-preview`. Full quality returns when the daily pool resets (Pacific) or when billing is enabled on the API project. **Kling via `FAL_KEY` is the vendor-independent backup — still unconfigured.**

**Deployment notes (unusual, by design this session):** code went to the VPS by direct `scp` to `/opt/fce/current/worker/` (originals in `/opt/fce/backup-motion-deploy/`), NOT git — the VPS checkout's remote is the OLD repo (`khooptong-creator/fin-content-engine`) and it sits 2 commits behind local (those 2 are docs-only). Replacing files under a running worker is safe for module-level imports only when the new import is lazy; motion/assemble imports are inside the call path, so mid-flight jobs were unaffected. This EoS commit brings git back in sync with what's deployed. **Also on the VPS venv:** installed Pillow 12.3.0 (assemble.py needs it), and removed a leftover `~ce_worker-0.1.0.dist-info` pip artifact that made every `pip install` as the `fce` user crash with PermissionError (run pip as root there; some editable-install hooks are root-owned).

**Open items, ranked:**
1. Owner's "The Novel Trial" build (job ea5ef691) died on the Veo quota 429 pre-fast-switch; rebuild picks it up — `f02`/`f03` clips are on disk and will be reused.
2. `MOTION_MAX_PARALLEL=3` × two concurrent jobs bursts the small free-tier pool; with retries it's survivable but slow. Drop to 2 via env if building two films at once becomes routine.
3. Progress blind spot: the shots-stage counter sits at 0/N through the entire clip-generation phase (compositions are written after all clips finish). Per-clip progress reporting is a small follow-up.
4. Local ComfyUI Wan/LTX image-to-video (phase 2) — free motion, needs the RTX 3070 + tunnel path.
5. Motion for `film`/Three.js backend and documentary mode — not built, by design.
6. VPS deploy path still git-less (see above); migration-check step unbuilt.
7. `worker/.env.example` had documented a removed `openai` image provider for weeks — fixed in passing; keep example files honest when providers change.

**Tests:** 53 motion/assemble tests (incl. 429 retry, non-quota reraise, clip reuse, ffmpeg command shape, adelay offsets, overlay bake); full suite 887 green minus the 5 known `test_x_publish.py` local-Postgres failures. GUI `tsc`/`eslint` clean.

### Session-close update — 2026-09-07 (day): Inbox starvation post-mortem + ComfyUI tunnel outage

**"Where have all the stories gone" — three stacked causes, none of them data loss.** All 1,785 stories stayed in the VPS Postgres the whole time; the Inbox only ever shows stories with source items ≤48h old (`get_pending_stories` freshness window), so when ingest stopped the window silently emptied. Ingest stopped because: (1) the worker crash-looped 15× on Sep 6–7 (deploy/test night) and `poll_rss` runs on a 30-min interval — uptime under the interval means the job never fires while 10-min jobs keep ticking; (2) the DB pool was `scheduler_max_workers + 2` = 6, and four 30-min jobs fire simultaneously at each half-hour mark, each holding a conn for its whole run — every boundary was a `PoolTimeout` lottery the loser dying silently (`/health` green throughout). **Fixes on the VPS:** `FCE_SCHEDULER_MAX_WORKERS=16` (pool 6→18), `rss_poll_minutes` 30→10 in the prod `config` row (the "10-minute ingest" tightening had only ever been applied to the local docker DB). Verified: 12 sources ingested, 54 new stories, Inbox back to 89.

**The env-var prefix trap (cost one full restart cycle):** worker settings use pydantic `env_prefix="FCE_"` — a bare `SCHEDULER_MAX_WORKERS=16` in `/opt/fce/.env` is silently ignored (`extra="ignore"`), so the first pool fix did nothing and starvation recurred exactly at the next 30-min pile-up. Correct form: `FCE_SCHEDULER_MAX_WORKERS=16`. **Rule: every worker env override starts with `FCE_`; verify by counting connections (`pg_stat_activity`), never by "I set it".**

**Finance channel + autopilot restored.** Stories arrive with `channel_id NULL`; scoring fills `vertical`/`content_archetype` but never the channel, so finance-vertical stories (macro/equities/market_structure/investing_concept/personal_finance/regulation/earnings) could never reach the video stage. Assigned `channel_id='finance'` to 256 stories; queued the top 3 fresh ones; autopilot (window 02:00–05:00 UTC = 07:30–10:30 IST, max 3/day, owner-queue-only) rendered the first one end-to-end minutes later. Standing flow: Inbox refills every 10 min → owner queues (or asks assistant to auto-queue top-scored) → window renders → manual publish from Drafts.

**ComfyUI tunnel outage (this morning's 530):** quick tunnel was dead AND ComfyUI itself was down. `scripts/refresh-comfy-tunnel.ps1` had three latent bugs (em-dash broke PS 5.1 ANSI parse of the no-BOM file; wscript redirect produced an empty log; `ssh` without `-n` hung on piped stdin) — fixed in commit `b75584f`. New tunnel live, VPS `.env` re-patched, end-to-end 200 verified from the VPS. Quick tunnels are ephemeral; if the PC/cloudflared restarts, rerun the script.

**Open items, ranked:**
1. VPS worker was crash-looping Sep 6–7 (Restart=on-failure, no OOM evidence) — root cause of the crashes uninvestigated; watch `journalctl -u fce-worker` for the next loop.
2. Auto-queue is manual/assistant-driven; no scheduled top-scored queueing exists.
3. Motion clip generation progress still blind at shots stage (carried over).
4. Pool starvation can recur under load: 18 conns vs 30-min pile-up is better but not provably sufficient — watch for `PoolTimeout` in the journal.

### Session note — 2026-09-07 (later): "No stories again" was a launcher race, not a recurrence

- Symptom identical to the starvation bug (empty Inbox), cause completely different: **both `.bat` launchers had been run, and both start the GUI on port 3000.** The local launcher won the race, so the browser talked to the *local* worker — whose `fce_pgdata` volume was recreated on 2026-09-06 and holds **0 items / 1 story**. Empty local DB + 48h freshness window = "no stories", while the VPS (1,880 stories, ingest ticking every 10 min) was perfectly healthy. **First diagnostic step for any "no stories" report: check which worker URL the GUI on port 3000 actually inlined** (`curl localhost:3000/_next/static/chunks/app/page.js | grep 160.250`), then read that worker's `/stats`.
- **Fix applied:** `START_Lamka_Labs_Studio_VPS.bat` now serves on **port 3100** (`npm run dev -- --port 3100`, browser opens `localhost:3100/x`); the local launcher keeps 3000. The two can no longer collide. Also killed a stuck duplicate `next dev` (waiting on the port prompt, listening on nothing) and a second orphan `run_worker.py` with no listener.
- Rule: the local DB is a scratch/dev database. If the Inbox matters, the GUI must point at the VPS worker.

**Deploy update (same day, done):** the Ken Burns renderer (`c73da8f`) is now DEPLOYED on the VPS. The checkout is fully in sync with `main` for the first time since the scp era: remote repointed from the old repo to `khooptong-sudo/lamka-labs-studio`, `git reset --hard origin/main` landed (`ebf50a8` → `c73da8f`), worker restarted clean (11 jobs registered, `/health` green, `app.scene3d.kenburns/motion/assemble` all import). The disk copies of `assemble.py`/`motion.py` were 180/301 lines BEHIND `main` — the repo, not the disk, was the newer side. Also seen: one transient Veo `code 13` internal error pre-restart (retries handle it).

### Session-close update — 2026-09-07 (evening): Reddit collection goes credential-free

- **The mystery-lane Reddit source no longer needs the five `REDDIT_*` credentials to collect.** `worker/app/sources/reddit.py` now picks per poll: creds present → PRAW (unchanged, real scores, MIN_SCORE=100); creds absent (or `REDDIT_COLLECTION_FORCE_RSS=true`) → the public `/r/{sub}/top/.rss?t=week` Atom feed — no account, login, cookies, or API key (verified live today). PROGRESS.md #90; spec addendum on `2026-09-05-reddit-collection-permission-design.md`.
- **Accepted trade-offs (deliberate, recorded):** feeds carry no scores → MIN_SCORE replaced by top-of-week rank + 25-item cap + 200-char substance floor; no NSFW flag → RSS mode only runs against the SFW allowlist subs. The candidate → owner-approved PM → granted rights gate is untouched — the human gate replaces the missing automated one. PM sending still requires creds; fallback is collection-only.
- **Reddit's throttle has silent shapes:** beyond an honest 429, it answers with HTTP 200 + empty body and with well-formed feeds containing zero entries. The source raises `not_a_feed` on non-feed 200s so throttling lands in source health instead of looking like a healthy empty week. My live smoke got rate-limited from testing traffic — the first real weekly production poll is the final confirmation; endpoints and parsing were proven live earlier in the day.
- **Local test-suite DB default mismatch:** `conftest.py` defaults `FCE_DATABASE_URL` to `localhost:5432`, but the local `fce-db` container publishes `127.0.0.1:15432` (Windows excluded-port range, see trap #23). DB tests error with PoolTimeout, not failures. Run them with `FCE_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:15432/fce`.
- **Restart the worker before trusting any of this live** — no hot reload (trap #19). 27 reddit-area tests green (incl. 6 new fallback tests); DB-backed rights/ingest tests pass against the 15432 container.
- **Also shipped (user-scope, all projects):** three agent skills — `reddit-research`, `feed-research` (zero-install RSS/Atom/JSON-Feed reader, `feedread.py`), and `research-sweep` (web + Reddit + RSS + X + video + code in one prompt). These are agent tooling, not product code.
- **Vault/RAG updated:** two atomic pages (`Content Engine - Reddit Collection Runs Credential-Free`, `Dev - Reddits Public Feeds Are the Credential-Free Read Path`), index/log entries, graph ingest + `graph_cli.py --rebuild --no-llm` (234 pages).

### Session-close update — 2026-09-07 (night): second GPU black-screen — local LTX path shelved

- **The RTX 3070 black-screened again (crash #2 of the day) during the 180 W-capped LTX validation run, and the telemetry exonerates software.** `.test-tmp/gpu_log2.csv` (1 Hz sampler, timestamped) shows the cap verifiably holding — sustained draw pegged at 175–177 W with clocks trimming at the limiter — at **65 °C** and **≤ 7.4 of 8 GB VRAM**, when the card dropped off the bus mid-sampler ("GPU is lost"; `comfyui_run2.log` faulthandler dump inside `sample_euler`). Run 1 (13:14) had read as a power-transient story (218 W spike at 75 C under the 190 W cap) → capped to 180 W; run 2 proves the cap is not the fix. Failure lives below software reach: VRM/power stage, PSU rail browning out on transients, or VRAM erroring under full allocation. **The power-cap/undervolt branch is closed; do not spend a third session on it — each failed attempt costs a hard hang and force restart.**
- **Product impact: none.** Motion video does not need the local card: the VPS pipeline renders via `veo-3.1-fast-generate-preview` (validated end-to-end earlier today) and Kling via fal.run needs only `FAL_KEY`. The local ComfyUI LTX provider (committed `fdfd75f`) was only the free-quota phase-2 option. **Shelved in abeyance until a 4090/5080 lands.** Resumption kit: `.test-tmp/run_ltx_test.py` + `ltx_i2v_test_payload.json` (validation harness), `scripts/run-comfyui-ltx.bat` (split-attention launcher), worker `scene3d/motion.py` LTX provider + `ltx_i2v_workflow.json`.
- **Recovered artifact:** `videos/story-88aa9c63-14aa-46b1-bbdd-e39364fccfaf/renders/video.mp4` (32.7 MB, Sep 6 21:31) — complete render with storyboard/assets/compositions, but no thumbnail or upload packet; a render alone is not a draft. Review it before any manual upload; never treat it as published.
- **Bypass answer for the record:** no bypass exists for the local card itself (CPU mode is technically present but LTX-on-CPU is hours per clip; further capping is disproven). The working bypass is provider-level: keep films on Veo fast / Kling, and consider setting `FAL_KEY` on the VPS as the vendor-independent backup (still unconfigured).
- **Also noted:** the ComfyUI quick tunnel will be stale after these reboots — if any VPS job selects a local provider, rerun `scripts/refresh-comfy-tunnel.ps1` (and expect the local GPU to still be a black-screen risk until the new card).
- **Vault/RAG updated:** new page `Dev - GPU Lost at Capped Power and Cool Temps Is Hardware`; index + log entries; graph rebuilt `--no-llm`.
- **Addendum (same night): the recurring film-job 530 explained and closed.** Every film that selected "ComfyUI Local" failed at the shots stage with `530` from the quick tunnel because the GPU crashes force-restarted the PC, killing cloudflared AND ComfyUI, while the VPS `.env` kept the evaporated tunnel URL (`tested-representative-wallet-myself`). The b75584f fix repaired the refresh *script*; nothing can make a free quick tunnel survive a reboot. The dashboard compounded it: `configured: true` only checks the env var is non-empty (`backend.py:109`), so a dead tunnel shows green until the job dies mid-flight. **Action taken:** `COMFYUI_BASE_URL` commented out on the VPS (line carries a re-enable note; `refresh-comfy-tunnel.ps1` appends a fresh line when run, so the re-enable path is intact), `fce-worker` restarted, `/youtube/image-providers` now shows `comfyui: configured:false`, `gemini: true`. Local provider is now hard-blocked in the UI instead of 530ing mid-job.
- **Addendum 2 (same night): quota split discovery + first Veo-motion film shipped.** When the Gemini project's **prepay balance hit zero (~20:03), all TEXT model calls** (`gemini-flash-latest` scripting) 429'd with "prepayment credits are depleted" — but the **Veo video pools kept answering**: job eadccfd0 (submitted 19:50, keyframes built 20:01) rendered all 5 motion clips and finished at 20:08 **after** the text pool was dead. So video (free per-model daily pools) and text (prepay balance) bill separately. Consequence: with zero prepay balance, NEW films cannot script (text=Gemini only; `SCENE_MODEL_PROVIDER=deepseek` exists but then fact_check — which must exclude the drafter — has only the dead Gemini left), while a film already past scripting still renders motion. **First motion draft shipped: `6f35d9e0` "NSE Pre-Open Rules Just Changed"** — 90 s, native 1080×1920, Veo fast clips, status pending owner review. Also: `SCENE_MODEL_PROVIDER=kimi` on the VPS silently falls through to Gemini (code only special-cases `"deepseek"`) — a misleading value worth cleaning up next session. Ken Burns insurance job 8d1db736 died at script on the same prepay wall (scripting is provider-independent of image/motion choices).
- **EoS note:** vault pages filed tonight — `Dev - GPU Lost at Capped Power and Cool Temps Is Hardware`, `Dev - Gemini Video Pools Outlive a Dead Prepay Balance`, `Content Engine - Readiness That Checks Configuration Shows Green on a Dead Bridge`, `Dev - ssh -n Silently Discards Piped Stdin`; index/log updated; RAG graph rebuilt `--no-llm`. YT-HANDOFF carries the full session close incl. retry guidance for zero-balance builds.

### Session-close update — 2026-09-08 (late night): X poster pipeline unblocked end-to-end

- **Root cause of the recurring "summary must be 500 characters or fewer" error:** the worker prompt asked for 70–120 words (~450–800 chars) while validation hard-rejected anything over 500 chars — most compliant LLM responses threw `PosterError`, so no poster ever rendered. Fixed in `worker/app/x/poster.py` (commits `09cf312`): prompt asks for one or two short paragraphs (60–120 words), overlong summaries are **trimmed at a sentence boundary** (cap 900 chars) instead of erroring, the only hard failures left are missing/empty summary or <40 words, and `\n\n` paragraph breaks survive normalization. `PosterCard.tsx` renders the summary as separate `<p>` blocks. 14/14 poster tests green.
- **The GUI talks to the VPS worker directly at `http://160.250.204.73:8002`** (inlined at build/dev time; verified via the network tab). Local code changes do nothing for the live app until: commit → push → `ssh root@160.250.204.73 "git -C /opt/fce/current pull && systemctl restart fce-worker"`. The VPS checkout was several commits behind `main` and caught up tonight (`c73da8f..09cf312`); worker restarted clean, live poster generation verified against a real story.
- **Push needs the right GitHub account:** the stored `gh` credential (`lamkaxchange`) gets 403 on `khooptong-sudo/lamka-labs-studio`. Working pattern: `gh auth switch --user khooptong-sudo && git push … && gh auth switch --user lamkaxchange`.
- **PosterCard now scale-to-fits** (`91ef3a3`): content is measured and the whole block shrinks to the fixed 1080×1350 frame, so the footer/scenery band are never clipped on dense posters (the RBI poster was 1651px → scale 0.76, footer visible). Dense-mode type went UP (bullets 13→14px, summary 15→16px, looser leading) since fit is guaranteed by scale, not by tiny fonts. Footer credit now reads "A Lamka Exchange Society Production" / "in collaboration with Lamka **Labs** Studio" with Labs in crimson in both lockups (`7586460`, `eca2a98`).
- **Pre-existing test debt (not from this session, unchanged):** `test_new_channels.py` cinematic render tests and `test_x_publish.py` fail/error on a clean tree too (psycopg fixtures need `FCE_DATABASE_URL` pointed at the 15432 container per trap #23). Worth a look next session.
- **GUI dev-server port reminder:** the VPS launcher owns **3100**; 3000 is the local-worker launcher (trap from the port-race note above). Browser QA tonight ran against `localhost:3100`.
- **Vault/RAG updated:** two pages (`Content Engine - Poster Validation Trimmed Instead of Rejecting`, `Dev - Pushing to lamka-labs-studio Needs the khooptong-sudo gh Account`), index/log entries, graph rebuilt `--no-llm`.
