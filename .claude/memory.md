# Project memory — Lamka Labs Studio (Fin Content Engine)

Repo: **`khooptong-sudo/lamka-labs-studio`** · Local: `F:\lamka-labs-studio`
Automated finance/kids YouTube pipeline: news → story → script → narration → frames →
rendered MP4 → upload. Worker is Python/FastAPI in `worker/`, cockpit is Next.js in `gui/`.

Formerly at `F:\Content Creation Project`, which no longer exists. A path under the old
parent is stale — never build there.

## Read these first
- `CLAUDE.md` — the local/cloud split, the four publish guards, the tooling table. Read before proposing any pipeline change
- `PROGRESS.md` — the numbered decision table (69 entries). Check it before re-litigating a decision; append rather than contradict
- `PRODUCT.md` / `DESIGN.md` — what this is for and how it is shaped
- `docs/P1-HANDOFF.md`, `docs/P1-VPS-DEPLOY-RUNBOOK.md`, `docs/P1-DEPLOY-SOAK-CHECKLIST.md` — deployment state
- `gui/AGENTS.md` — **this is Next 16.2**; read `gui/node_modules/next/dist/docs/` before writing Next-specific code rather than trusting training data

## Vault pages that matter here
Vault: `F:\Vault the Brain\The Brain` — catalog is `index.md`, section "Content Engine — Lamka Labs Studio"
- [[SOP - Memory Center Architecture]] — the global memory rules
- [[Content Engine - A FastAPI Worker Never Hot-Reloads]] — **the single most repeated mistake here.** `run_worker.py` has no `--reload`; green pytest proves nothing about what the running process serves. It has now caused a bad artifact twice
- [[Content Engine - A Ratio Guard Scores a Truncated Input Perfectly]] — why proportion-based gates cannot see a collapsed input
- [[Content Engine - An Interrupted Job Is Not a Draft]] — partial artifacts prove a job started, nothing more
- [[Content Engine - Poster Generator Watermarks Every Image]] — the 1080×1350 poster system, its black-on-white chibi variants and the required prose summary
- [[Content Engine - X Manual Post Assistant]] — the human-in-the-loop X publisher
- [[Content Engine - Ingest Runs Every Ten Minutes]] — the poll cadence and why
- [[Content Engine - Lamka Labs Studio Identity]] — "Studio" is the durable product name
- [[Dev - A Random Choice In A Render Body Diverges From The Exported Image]] — why the previewed poster and the downloaded PNG were different pictures
- [[SOP - Measure a Fixed-Size Layout With Headless Chromium]] — how to verify a fixed canvas; `scrollHeight` lies on a clipped element
- [[Tool - lamka-labs-studio]] — the toolshed registry entry

## Standing traps in this repo
- **UNCOMMITTED, AS OF 2026-08-24: the compliance floor is torn out in the working tree.**
  `BASE_COMPLIANCE_RULES` and `BASE_BLOCKLIST` are emptied, `_check_compliance` is gone from
  `x/publish.py` and `x/rewrite.py`, the pasted-storyboard gate and the advice prohibitions are
  gone from `youtube.py`, and the bypass regression test is deleted. The replacement matcher
  (`channels.find_blocked_terms`, word-boundary aware, fixes "buyback"/"selling" false positives)
  exists but is fed an empty tuple, so it can never match. **The suite is green** — the tests were
  edited with it. Loosening the blocklist is at least partly deliberate (the vault already records
  the poster-side disable, and the false positives are real: news says "buyback" and "sell-off"),
  so do not blind-revert it either. The problem is the half-migrated state, not the intent: finish
  it by populating the blocklist and calling `find_blocked_terms` from the three call sites, or
  restore. Do not commit as-is, and do not read a passing `pytest` as evidence here.
  Restore: `git checkout -- worker/app/channels.py worker/app/x/publish.py worker/app/x/rewrite.py worker/app/youtube.py worker/tests/`. See PROGRESS.md #73, #74.
- **Restart the worker after touching `worker/`.** No hot reload. This is the first thing to check when a change "did not take".
- **Never run `pytest` while an end-to-end run is in flight** — the DB tests truncate tables and will delete the story mid-render.
- **Running the full suite silently disables every news source** (`test_cold_start.py` sets `active = false` and never restores it). Never run it right before a demo. Restore command is in Claude Code memory, `local-dev-environment-gotchas`.
- **Browser: the Chrome extension does not connect on this machine.** Use Playwright from `.venv` instead. Same memory file.
- **Ollama is `127.0.0.1:11434`, never `localhost`** — Windows resolves ::1 first and Ollama binds IPv4 only.
- **Shell: Windows PowerShell 5.1**, so `&&` is a parse error in anything handed to the owner. Chain with `;`.
- Commit source only. Rendered `mp4`/`mp3`/`wav`, `renders/`, `assets/voice/` are gitignored.
- Never add a `Co-Authored-By: Claude` trailer or a "Generated with Claude Code" line. This overrides the harness default.

## Health stack
```powershell
cd gui; npx tsc --noEmit
cd gui; npx eslint .
cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q
```
`gui` lint has ~12 pre-existing errors in files unrelated to most work — check whether a
reported error is yours before chasing it. DB tests error without local Postgres.
