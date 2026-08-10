# Content Creation Project — Agent Operating Protocol

This file is auto-loaded by Kimi Code CLI at session start because it lives at the
project root. It inlines the workspace-wide rules from `F:\CLAUDE.md`,
`F:\.claude\memory.md`, and `F:\AGENTS.md` that are unsafe to discover late, plus
this project's own source-of-truth docs.

---

## 1. Read this first (every session)

1. This file.
2. This project's README and docs.

For cross-project memory and durable lessons:
- `F:\CLAUDE.md` — workspace map, off-limits paths, naming collisions.
- `F:\.claude\memory.md` — environment gotchas that have already cost time.
- `F:\Vault the Brain\The Brain\index.md` — vault catalog (source of truth).
- Query: `python F:/RAG/rag.py -q "..."`
- Graph: `mcp__vault-graph__graph_answer_question`, `graph_query_cypher`, `graph_get_page`.

If vault/RAG is unreachable (non-Windows / cloud session), state it in one line and
continue from this repo's docs.

---

## 2. Hard workspace rules (from `F:\CLAUDE.md` / `F:\AGENTS.md`)

### `F:\` is a workspace root, not a repo
- **Never run drive-wide commands from `F:\`.** No `git status`, no recursive `npm`/`pytest`,
  no drive-wide `Glob`/`Grep`. It holds ~10 unrelated projects, media, installers, etc.
- **Always `cd` into the specific project first**, then follow *that* project's docs.

### Off-limits paths (never read, list, or open)
- `F:\KEYS`
- `F:\Lamka Exchange\Google Service Key`
- `F:\Lamka Equities\Lamka Equities\Keys & Masters`
- Any `.env` file
- Loose `*Key*.txt` / `gh auth login.txt` notes at `F:\` root

If a task seems to need a key, ask the owner to set it in the environment instead.

### Shell rules
- This machine is Windows 11 + PowerShell 7 for the Kimi-driven shell.
- **The owner's Desktop terminal is Windows PowerShell 5.1**, not PS7. `&&` is not valid
  there — use `;`. No bash heredocs, no `/dev/null`, no `export`, no PS7-only syntax
  (`??`, `?.`, ternary).
- Long pasted lines wrap and the tail executes as a separate command. Hand over a short
  `.ps1` invoked by name, never a long one-liner.
- Paths contain spaces; quote them: `Set-Location "F:\Lamka Equities and Desk\ltt2"`.

### Memory rules
- The **vault** (`F:\Vault the Brain\The Brain`) is the source of truth.
- `F:\RAG` (Chroma + Neo4j) is a **rebuildable index**, not a knowledge store.
- Never write a durable fact into an index — a rebuild erases it.
- Current project state → this repo's `docs/` or project tracker files.
- Durable lessons that outlive the repo → one atomic vault page per the vault's own
  `CLAUDE.md` schema, then `python F:/RAG/graph_cli.py --rebuild`.

---

## 3. Standing gotchas (from `F:\.claude\memory.md`)

### `F:\` root is not writable
Creating a file directly at `F:\` fails with `EPERM`. Write into a subdirectory
(e.g., `F:\.claude\`) or another drive.

### JDK on this machine
- JDK 8 and JDK 25 are pre-installed, but **JDK 25 is incompatible with Android Gradle
  Plugin 8.5**. For Android projects, use the Temurin 17 install at
  `C:\Users\Min K\.jdks\jdk-17.0.17+10`.
- Set `JAVA_HOME` to that path before running Gradle.

### Sizing / deleting under `.claude\projects`
Transcript paths exceed `MAX_PATH`. Use `robocopy`, not `Get-ChildItem`:
```powershell
robocopy <src> NUL /L /E /BYTES /NFL /NDL /NJH /XJ
```
Deleting needs `cmd /c rmdir /s /q` on the literal path; one target per call.

### Deletions need literal paths
A protection hook rejects delete commands it cannot statically resolve. Write the path
out in full, one per call, then verify with `Test-Path -LiteralPath`.

### `F:\RAG\.env` is the real LLM config
Defaults in the code are decorative. The active provider/model is whatever `.env` sets.
Verify any provider change with `Set-Location F:\RAG; python smoke_llm.py` in a fresh
shell — a cached rebuild proves nothing.

### Agents without a SessionStart hook
Kimi Code auto-loads `AGENTS.md` and has no hook mechanism, which is why this file
exists. `F:\.claude\SESSION-CONTEXT.md` is generated for Claude Code; do not edit it
and do not store facts only there.

---

## 4. Naming collisions that cause real errors

- `LE` = Lamka Equities (the repo).
- `LES` = Lamka Exchange Society (the legal entity).
- `les-lounge` = a separate repo unpacked under `F:\Lamka Exchange\les-lounge-main`.
- `ltt` = LTT v1, superseded and dead.
- `ltt2` = live trading terminal.
- `MKTS` = MK Transcription Studio / Lamka Transcription Services (same project).
Always name the concrete path.

---

## 5. Project-specific rules

- Read this project's own README/docs first.
- If a project-level `CLAUDE.md` exists, read it after this file.
- Follow any project-specific `BUILD_PHASES.md`, `PROJECT_TRACKER.md`, `HANDOFF.md`, or
  `MEMORY.md` if present.
