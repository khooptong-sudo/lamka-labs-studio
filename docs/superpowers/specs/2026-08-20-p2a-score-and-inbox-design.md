# P2a — Score & Inbox: Design

Date: 2026-08-20
Status: approved, ready for implementation planning

## Goal

Turn the deployed P1 reader into a ranked editorial queue. Every story that
clusters gets scored, angled, and stamped with a vertical and a content
archetype, so the Inbox stops being a reverse-chronological list and becomes a
ranked one. Nothing is drafted and nothing is published in P2a.

This is the first half of the blueprint's P2 (Part I §6). It is split from P2b
(Draft & Gate) so each half is independently verifiable, per decision #1. The
blueprint's own P2 acceptance criterion is already two sentences; this spec owns
the first, "10 stories yield archetype-stamped drafts", reduced to its scoring
half.

## Scope

**In:** the shared LLM router, the closed taxonomy, the `score_new` job, the
Inbox surfacing of rank, and the tests for all of it.

**Out, deferred to P2b:** the Voice Pack, archetype-aware drafting, the L1 regex
gate, the L2 cross-model judge, anything writing to `drafts`. Out permanently
for this phase: publishing (P4), replies (P5).

One gap belongs to P2b and is recorded here so it is not rediscovered: the
`voice_profile` table has `version`, `system_prompt`, `banned_phrases`, and
`example_posts` but **no name or key column**, so it models a single versioned
voice. The owner wants two X profiles, first-person as Min Khooptong and a
Lamka Labs masthead, selected per archetype. P2b therefore needs a migration
that P2a does not.

## What already exists

An audit of the repo before designing, so P2a builds on what is there instead of
beside it.

| P2a needs | Already in the repo | Gap |
|---|---|---|
| Columns for the output | `stories.score`, `.angle`, `.vertical`, `.content_archetype`, all created in `001_init.sql` and commented "P2-populated" | None. P2a needs **no migration** |
| A picking surface | `stories.status='inbox'`, fetcher `db.get_pending_stories` (`db.py:553`), route `routes.py:302`, films GUI consumes it | Return the new columns; add an ordering option |
| Strict JSON out of a model | `localllm._extract_json` / `_validate` | Generalize into `llm/contract.py` |
| A model router | Nothing. `youtube.py` hand-rolls `_generate_script_gemini` and `_generate_script_deepseek` with separate retry loops, selected by env var | Build it |
| Audit events | `audit.py` | None |

Available providers, confirmed from `worker/.env`: **Gemini, DeepSeek, OpenAI**.
There is no Anthropic key and no Moonshot key, so the blueprint's routing table
(§8: Haiku primary, Kimi for variant B) names models this deployment cannot
call. The seeded routing below uses what exists.

## Architecture

Approach C from the brainstorm: the router and the taxonomy are built as shared
modules that P2b and, later, a retrofitted `youtube.py` all consume. The
existing YouTube provider calls are left running untouched, and their migration
is written down as explicit debt rather than left implicit (see Follow-up debt).

### Module layout

```
worker/app/llm/
  __init__.py
  router.py      task -> provider resolution, retry, no-fabrication discipline
  providers.py   gemini / deepseek / openai adapters behind one call signature
  contract.py    strict-JSON request, parse, validate
worker/app/taxonomy.py   closed enums: ARCHETYPES, VERTICALS
worker/app/score.py      the scoring job
```

### The router

One entry point:

```python
async def complete_json(task: str, *, system: str, user: str, spec: FieldSpec) -> dict
```

`FieldSpec` is a small local declaration living in `contract.py`: a mapping of
field name to a validator callable, plus the required-field set. It is
deliberately not `jsonschema`. The validation surface here is four fields with
two closed enums and a numeric range, which does not justify a new dependency,
and a callable-per-field keeps the enum checks in the same Python that owns the
tuples.

`task` is a routing key, never a model name. Callers name what they want done
and stay ignorant of which provider does it, which is what makes decision #4
("model router config-driven") real rather than aspirational.

The router raises on exhaustion. There is no path that returns a default, a
stub, or a partially-populated dict. This is decision #41 generalized from
script generation to every LLM call in the repo.

### Routing config, two-tier

Per decision #21: provider credentials in env, task-to-provider mapping in the
`config` table under key `llm`, in a `routing` field. Re-routing a task to a
different provider is a database edit, not a deploy.

Seeded value:

```json
{ "story_score": { "primary": "gemini", "fallback": "deepseek" } }
```

A provider whose API key is absent from the environment is skipped at
resolution time with a startup log line, not discovered at call time.

### The taxonomy

`taxonomy.py` holds two closed tuples. They are **code constants, not config**,
for the same reason the compliance blocklist is (decisions #43, #44): in the
config table they would be one GUI edit away from removal, with no trace in
git history.

```python
ARCHETYPES = ("explainer", "metric_teardown", "filing_walkthrough",
              "macro_calendar", "concept_comparison", "regulatory_update",
              "historical_parallel", "mistake_anatomy", "glossary_card",
              "data_curiosity")

VERTICALS = ("macro", "equities", "regulation", "earnings", "market_structure",
             "investing_concept", "personal_finance_concept", "practical_skills")
```

`ARCHETYPES` is §5's starter set verbatim. `VERTICALS` is defined here for the
first time: the blueprint says P2 populates `vertical` but never says what it
holds. It is a topical lane and is deliberately orthogonal to `market`
(`US`/`IN`), which already lives on `sources` and `items`.

Two naming decisions inside `VERTICALS` are load-bearing:

- `investing_concept` and `personal_finance_concept` stay separate. What a P/E
  ratio measures and how an EMI amortises are different lanes editorially.
- The lane covering practical know-how is named `practical_skills`, not `tips`.
  In P2b the vertical label is injected into the drafting prompt, so the
  taxonomy word is itself a compliance surface. A lane named `tips` would prime
  advisory register in every draft it touched, and it is the precise term
  SEBI's finfluencer framing keys on. The content is unchanged: how to read a
  cash-flow statement, how to drive a screener, where the data lives.

The set is closed by construction. Adding a value is a deliberate code change
under owner approval, mirroring §5's rule for archetypes.

## The scoring job

### Trigger and scheduling

APScheduler job `score_new`, every 15 minutes, registered as `async def` and
asserted at registration (decision #22), wrapped in an advisory lock (decision
#18).

It selects stories where `score IS NULL` that fall inside the same fresh-news
window the Inbox uses (`config.ingest.fresh_news_hours`, currently 48). Scoring
a story too old to post wastes a call.

A per-cycle cap bounds the blast radius so a large backlog cannot fire hundreds
of calls in one tick: `config.llm.score_batch_max`, seeded at 25. At the
observed ingest rate (50 items per trigger, clustering well below that) one
cycle clears the queue, and a first run against a historical backlog is bounded
to 25 calls per 15 minutes rather than unbounded.

Attempt budget: `SCORE_MAX_ATTEMPTS`, per provider, defaulting to 4 and
overridable by environment variable. This mirrors `youtube.py:50`
(`SCRIPT_MAX_ATTEMPTS = int(os.environ.get("SCRIPT_MAX_ATTEMPTS", "4"))`)
exactly, so the two LLM paths fail on the same shape and are tunable the same
way under a flaky provider.

### Input packet

The story headline plus, for each linked item inside the fresh window, its
title and source name. Bounded by construction: the same packet discipline the
YouTube research path already uses.

### Output contract

```json
{ "score": 0-100, "angle": "string", "vertical": "<enum>", "content_archetype": "<enum>" }
```

### Validation is the compliance mechanism

`content_archetype` and `vertical` are checked against the closed tuples in
code. An out-of-set value is a validation failure, never a new taxonomy entry.

This is the structural enforcement of §2.2, the listicle trap. The model cannot
invent "top 5 funds" at 3 a.m. because the field is closed and checked after the
call returns, not merely discouraged in the prompt. Prompt instructions are a
request; a validated closed enum is a guarantee.

## The status decision

**`score_new` does not change `stories.status`.** It stays `'inbox'`.

`db.get_pending_stories` hard-codes `WHERE s.status = 'inbox'` (`db.py:569`),
and `ideation.py` reads that same Inbox for the video path. Flipping status to
`'scored'` on success would silently remove every scored story from the Inbox
and break YouTube ideation as a side effect, with no error pointing at the
cause.

So `status` keeps exactly one meaning, "awaiting the owner's editorial
decision", and "has been scored" is derived from `score IS NOT NULL`. The
`'scored'` value in the CHECK constraint stays unused and harmless.

The rejected alternative was widening the filter to `IN ('inbox','scored')`.
That makes one column carry two orthogonal meanings, which is the shape of
recorded bug #18, where migration 006's real columns sat unread while
everything keyed off `body->>'channel_id'`.

## Data flow

```
cluster_new ──► stories (status='inbox', score=NULL)
                      │
                score_new  (15 min, advisory-locked, capped)
                      │  router.complete_json("story_score", …)
                      ▼
        score · angle · vertical · content_archetype written in one UPDATE
        status unchanged
                      │
                GET /stories  (extended)
                      ▼
                Inbox, orderable by score
```

## Error handling

| Failure | Handling |
|---|---|
| Retryable provider error (429, 5xx, timeout) | Retry with backoff, mirroring `_is_retryable` in `youtube.py` |
| Terminal provider error (401, 400) | No retry; fall through to the fallback provider immediately |
| Primary chain exhausted | Fallback provider receives a fresh attempt budget |
| Both exhausted | Raise. Story stays unscored, `story_score_failed` audit event, next cycle retries it naturally |
| Validation failure | One repair attempt with the violation appended to the prompt, then give up. Not an unbounded correction loop |
| Provider key absent | Provider skipped at resolution time with a startup log |

Two invariants:

**Atomic writes.** All four columns land in a single `UPDATE` or none do. A
half-scored story cannot exist.

**No fabricated defaults.** There is no code path that invents a score. A
fabricated score silently reorders the editorial queue, which is the scoring
equivalent of recorded bug #12, where a stub script turned a Gemini 503 into a
publishable five-second video.

## Inbox surfacing

`get_pending_stories` gains the four columns in its `SELECT`. This is purely
additive and cannot affect existing consumers.

Ordering becomes a parameter, defaulting to the current `created_at DESC`.
The X Inbox requests score ordering (`score DESC NULLS LAST, created_at DESC`);
the films page keeps its existing behaviour untouched. Changing the shared
default would silently reorder the video queue, which approach C exists to
avoid.

The GUI change is deliberately minimal for P2a: the existing Inbox rows on
`gui/src/app/films/page.tsx` gain a score value and an archetype label. No new
page, no new route, no reordering of that page's queue. This crosses the blueprint's P2/P3 boundary knowingly.
A score nobody can see is not verifiable by the person whose editorial judgement
the whole "score everything, draft only what you pick" topology depends on.

## Testing

Built test-first. Enum validation is exactly the guard-logic class the project's
CLAUDE.md flags for TDD, where a silent failure ships something degraded.

**Patch `router.complete_json`, never a provider.** This is recorded bug #13
restated: mocking `_generate_frame_compositions` let `FRAME_BACKEND=local` route
around the mock and fire live HTTP at Ollama. The router is the dispatcher, so
the router is the seam. No test touches the network.

Unit:

- Out-of-set `content_archetype` rejected; out-of-set `vertical` rejected.
- `score` outside 0-100 rejected; missing or empty `angle` rejected.
- Repair-once-then-give-up terminates rather than looping.
- Partial writes impossible.
- Routing resolves from config; fallback ordering honoured; absent-key provider
  skipped at resolution.

DB integration:

- All four columns written atomically.
- `status` unchanged after a successful scoring pass.
- `score IS NULL` idempotency guard holds across re-runs.
- **Regression:** a scored story is still returned by `get_pending_stories`.
  This is the test that would have caught bug #18 one phase earlier.

Frozen fixture (decision #24): a golden fixture of the rendered scoring prompt,
with a provenance assertion, so a prompt edit appears in a diff instead of
silently changing every score the system has ever produced.

## Acceptance

- Ten stories come back scored, angled, and stamped with an in-set vertical and
  archetype.
- Inbox returns them ranked when score ordering is requested, and unchanged in
  the films path.
- Full worker suite green, no network in tests.
- A forced provider failure leaves the story unscored with an audit event, and
  the next cycle picks it up.

## New decisions

To be appended to `PROGRESS.md`'s cumulative log on merge, continuing from #53.

| # | Decision | Rationale |
|---|---|---|
| 54 | P2 split into P2a (Score & Inbox) and P2b (Draft & Gate) | Decision #1 applied one level down: each half independently verifiable, and the router is proven against real stories before the gate is built on it |
| 55 | Router keys on task name, not model name | Callers stay ignorant of providers; re-routing is a config edit |
| 56 | Task-to-provider map in `config`, credentials in env | Decision #21's two-tier split applied to model routing |
| 57 | `ARCHETYPES` and `VERTICALS` are code constants, not config | Same reasoning as #43: in config they are one GUI edit from removal, with no git trace |
| 58 | Scoring does not mutate `stories.status` | `status` keeps one meaning; flipping it would silently empty the Inbox and break YouTube ideation |
| 59 | The practical-know-how vertical is named `practical_skills`, not `tips` | The vertical label reaches the drafting prompt in P2b, so the taxonomy word is a compliance surface |
| 60 | `investing_concept` separate from `personal_finance_concept` | Distinct editorial lanes; merging them loses a slice the owner asked for |
| 61 | Inbox ordering is a parameter, default unchanged | Changing the shared default would silently reorder the working video queue |
| 62 | Router raises on exhaustion; no fabricated score | #41 generalized from script generation to all LLM calls |

## Follow-up debt

Approach C leaves `youtube.py`'s two hand-rolled provider paths
(`_generate_script_gemini`, `_generate_script_deepseek`) in place, calling
providers directly rather than through `llm/router.py`. This is a deliberate,
time-boxed stopgap so that P2a does not destabilise a deployed pipeline that
currently ships videos.

It is recorded here because the project's engineering defaults warn that
undocumented stopgaps are the ones that become permanent.

**Retire by:** the completion of P2b, when the drafter and both gate layers are
also on the router and the shared surface has proven itself against three
consumers. The retrofit swaps two call sites and deletes two retry loops; the
existing YouTube tests are the safety net.
