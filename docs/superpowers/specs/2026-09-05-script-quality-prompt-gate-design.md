# Script Quality (Prompt+Gate) — Design

**Date:** 2026-09-05
**Status:** Approved, awaiting implementation plan
**Scope:** Piece 1 of 5 in the Kutly upgrade. Hook/chapter prompt contract +
cross-model fact-check gate on the existing Shorts/film script path.
No migration, no GUI work, no new channels in this piece.

## Context

Kutly wins mapped against Studio (2026-09-05): same pipeline shape
(prompt → script → voice → visuals → SEO packet), opposite philosophy
(evidence-first, local-first, never auto-publish). Agreed build order:
(1) script quality, (2) publish packet w/ A-B thumbnails + tags,
(3) voice-to-video + motion uplift, (4) queue speed within the single-GPU
limit, (5) new channel registry (Documentary + Education bundles, plus a
custom list whose names are still pending from the owner).

## Problem

`youtube.py:486` `_generate_script_for_story()` is prompt-only:

- Research rules (`youtube.py:514-519`) instruct evidence-bounded writing
  but nothing verifies the output against the evidence packet.
- FORMAT has no hook/chapter/retention contract: Scene 1 can open flat,
  scenes can repeat one beat, MIN_SCRIPT_FRAMES=3 is the only length bar.
- Description ships SEO but there are no tags; thumbnails are not A-B
  (covered in piece 2, not here).
- Failure mode is a publishable-looking draft with an invented date, price,
  or legal claim — the exact class the ratio guards cannot catch.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Hook + chapters live in the prompt contract, enforced by a pure validator | Same pattern as archetype templates: pre-validated structure beats post-hoc repair. Validator sits next to MIN_SCRIPT_FRAMES. |
| 2 | Fact-check reuses `llm/router.py` with a different provider than the drafter | Cross-model kills sycophancy (P2 L2 rule). No new provider surface; task key e.g. `fact_check`. |
| 3 | BLOCK aborts pre-TTS; FLAG warns and continues to human review | Nothing auto-publishes, so FLAG is review signal, not a ship-blocker. BLOCK (invented date/price/legal claim) must never burn TTS/render spend. |
| 4 | Provider exhaustion raises, never passes silent | Decision #62 generalized: an unchecked script must be a loud failure, not a draft. |
| 5 | No stub fallback, no structure repair by a second LLM call | Decision #41: a fabricated or repaired script becomes a publishable draft. Raise with the validator/fact-check report attached. |

## Contract

System instruction FORMAT gains (within existing frontmatter + `# Scene N`
`Voiceover:`/`Scene:` shape the storyboard parser already expects):

- Scene 1 `Voiceover:` first sentence is the hook: ≤25 words, names the
  stake, no question-bait (`What if I told you…` banned).
- 4–8 scenes, each a new visual beat with a titled chapter
  (`# Scene N — <chapter>`, accepted by the `_FRAME_HEADING` parser in
  `storyboard.py:164` with the chapter landing in `Frame.title`);
  titles non-empty and unique.
- Retention restate roughly every 3rd scene (why this matters to the viewer)
  as a prompt instruction (see Validator note below).
- Final scene carries an explicit closing beat, not a trailing fact.
- Frontmatter keeps `title`/`description`/`preset`/`music`; tags deferred
  to piece 2.

Validator `validate_script_structure(script) -> list[str]` is pure
(no I/O): hook present/length (words = whitespace-split tokens on the first
sentence of the Scene 1 voiceover), scene count in range, chapter titles
present/unique, final scene carries a closing beat. Returns violation
strings; empty means pass. Called before TTS and before fact-check
(cheap fail first). Retention cadence (a restated stake ~every 3rd scene)
is prompt-directed, not validator-enforced: no shallow textual proxy can
detect it without the false-positive class of decision #14, so it is
verified by the fact-check read-through and the human review gate.

## Gate

`fact_check_script(script, evidence_packet)` after structure passes:

- Prompt: enumerate factual claims in the script, map each to supporting
  evidence-packet lines or mark UNSUPPORTED; return strict JSON
  `{verdict: PASS|FLAG|BLOCK, violations:[{quote, reason}]}`.
- Router selects a provider different from the drafting provider
  (`SCENE_MODEL_PROVIDER` vs fact-check task route); retry on 429/503 via
  existing router retry; exhaustion raises.
- BLOCK → raise + `audit.py` event with violations; no TTS, no render.
- FLAG → `log.warning` + continue; violations travel with the run log so
  the owner sees them at review. No DB column in this piece (no migration).
- Deterministic tests patch the router/dispatcher, never the network.

## Error handling

- Structure violations → raise with the violation list; caller aborts the run.
- Fact-check BLOCK → raise with violations; audit event written.
- Fact-check transport/parse failure after retries → raise (never default PASS).
- Progress reporting (`_stage`) failures never abort a run (existing rule).

## Testing

- Pure validator cases: missing hook, long hook, <4 scenes, dup/empty
  chapters, missing retention beat, happy path (cinematic + standard).
- Verdict parsing: PASS/FLAG/BLOCK mapping, malformed JSON raises.
- Router cross-model test: drafter gemini → fact-checker non-gemini and vice versa.
- Pipeline test: BLOCK raised pre-TTS (assert TTS/render not called);
  FLAG continues. Patch router entrypoint, not providers. No network.

## Non-goals (later pieces)

- Tags + A-B thumbnails + title/description polish → piece 2.
- Voiceover-to-video mode + cut-density/motion uplift → piece 3.
- Queue concurrency/throughput → piece 4 (single-GPU sequential rule stands).
- Documentary/Education/custom channel registry, taxonomy additions, new
  sources → piece 5. Needs owner-supplied custom topic names first.

## Files touched

- `worker/app/youtube.py` (contract text, validator call, gate call, audit)
- `worker/app/llm/router.py` + config task map (fact-check task key only)
- New: validator + fact-check helpers alongside `youtube.py` (or small module)
- `worker/tests/` (validator, verdict, cross-model, pipeline-abort cases)
