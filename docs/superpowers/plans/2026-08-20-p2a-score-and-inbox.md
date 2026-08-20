# P2a — Score & Inbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score every clustered story with a 0-100 rank, an editorial angle, a vertical, and a content archetype, then surface that rank in the Inbox, so the owner can pick what to draft.

**Architecture:** A shared `app/llm/` package (contract, providers, router) that P2b and a later `youtube.py` retrofit will also consume. A closed `app/taxonomy.py` supplies the two enums. `app/score.py` holds the scheduled job: fetch unscored stories inside the fresh-news window, one router call each, validate against the closed enums, write all four columns in a single UPDATE. Nothing mutates `stories.status`.

**Tech Stack:** Python 3.12, FastAPI, APScheduler, psycopg3 (async), httpx, google-genai, structlog, pytest + pytest-asyncio. Next.js 16 / React 19 for the one GUI change.

**Spec:** `docs/superpowers/specs/2026-08-20-p2a-score-and-inbox-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **No migration.** `stories.score/.angle/.vertical/.content_archetype` already exist from `001_init.sql`.
- **Scoring never mutates `stories.status`.** It stays `'inbox'`. Scored-ness is derived from `score IS NOT NULL`. Flipping it to `'scored'` would silently empty the Inbox (`db.py:569` hard-codes `WHERE s.status = 'inbox'`) and break YouTube ideation.
- **`ARCHETYPES` and `VERTICALS` are code constants in `app/taxonomy.py`, never config.** Closed sets. An out-of-set value is a validation failure, never a new taxonomy entry.
- **No fabricated defaults anywhere.** The router raises on exhaustion. A story that cannot be scored stays unscored.
- **All four columns are written in one `UPDATE` or none are.**
- **Tests never touch the network. Patch `app.llm.router.complete_json`, never a provider.** Recorded bug #13: mocking one layer down let a backend route around the mock and fire live HTTP.
- **Every scheduler job is `async def`**, asserted at registration (decision #22), and advisory-locked (decision #18).
- `SCORE_MAX_ATTEMPTS` defaults to `4`, env-overridable, mirroring `youtube.py:50`.
- **Inbox default ordering is unchanged** (`created_at DESC`). Score ordering is opt-in.
- psycopg3: `%s` placeholders, never `$1`. Helpers are `_fetchone` / `_fetchall` / `_fetchval`.
- Commits: conventional style, scope `p2a`. **Never add a `Co-Authored-By` trailer or a "Generated with Claude Code" line.**
- Run tests from the worker dir: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`. DB tests need local Postgres; they error without it and that is expected.

---

## File Structure

| File | Responsibility |
|---|---|
| `worker/app/taxonomy.py` | The two closed tuples and their membership predicates. Pure, no I/O. |
| `worker/app/llm/__init__.py` | Package marker; re-exports `complete_json`. |
| `worker/app/llm/contract.py` | Extract a JSON object from a model reply; validate it against a `FieldSpec`. Pure. |
| `worker/app/llm/providers.py` | Three adapters behind one signature, key-availability, retryable classification. |
| `worker/app/llm/router.py` | Task→provider resolution, retry, fallback, repair-once. The single seam tests patch. |
| `worker/app/config.py` | *(modify)* Add `LLMConfig` + `get_llm_config()`. |
| `worker/app/score.py` | The scoring job: prompt, fetch, call, write. |
| `worker/app/scheduler.py` | *(modify)* Register `score_new`. |
| `worker/app/db.py` | *(modify)* `get_pending_stories` returns the four columns; ordering becomes a parameter. |
| `worker/app/routes.py` | *(modify)* `GET /stories` accepts `?order=`. |
| `gui/src/app/films/page.tsx` | *(modify)* Show score and archetype on Inbox rows. |

---

## Task 1: Taxonomy

**Files:**
- Create: `worker/app/taxonomy.py`
- Test: `worker/tests/test_taxonomy.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ARCHETYPES: tuple[str, ...]`, `VERTICALS: tuple[str, ...]`, `is_archetype(value: object) -> bool`, `is_vertical(value: object) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `worker/tests/test_taxonomy.py`:

```python
"""The closed vocabularies are the structural defence against the listicle
trap (blueprint §2.2). These tests exist to make widening them loud."""

from app.taxonomy import ARCHETYPES, VERTICALS, is_archetype, is_vertical


def test_archetypes_match_blueprint_section_5():
    assert ARCHETYPES == (
        "explainer",
        "metric_teardown",
        "filing_walkthrough",
        "macro_calendar",
        "concept_comparison",
        "regulatory_update",
        "historical_parallel",
        "mistake_anatomy",
        "glossary_card",
        "data_curiosity",
    )


def test_verticals_are_the_eight_agreed_lanes():
    assert VERTICALS == (
        "macro",
        "equities",
        "regulation",
        "earnings",
        "market_structure",
        "investing_concept",
        "personal_finance_concept",
        "practical_skills",
    )


def test_no_duplicates_in_either_set():
    assert len(set(ARCHETYPES)) == len(ARCHETYPES)
    assert len(set(VERTICALS)) == len(VERTICALS)


def test_tips_is_not_a_vertical():
    # Renamed to practical_skills on purpose: the vertical label reaches the
    # P2b drafting prompt, so a lane named "tips" would prime advisory register.
    assert "tips" not in VERTICALS
    assert "practical_skills" in VERTICALS


def test_membership_accepts_known_values():
    assert is_archetype("explainer")
    assert is_vertical("macro")


def test_membership_rejects_unknown_values():
    assert not is_archetype("top_5_funds")
    assert not is_vertical("stock_tips")


def test_membership_rejects_non_strings():
    assert not is_archetype(None)
    assert not is_archetype(3)
    assert not is_vertical(["macro"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_taxonomy.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.taxonomy'`

- [ ] **Step 3: Write minimal implementation**

Create `worker/app/taxonomy.py`:

```python
"""Closed vocabularies for story classification (blueprint Part I §5).

These are code constants, not config, for the same reason the compliance
blocklist is (decisions #43, #44): in the config table they would be one GUI
edit away from removal, with no trace in git history. Adding a value is a
deliberate code change under owner approval, per §5.

The closure is the point. §2.2's listicle trap is defended structurally: the
model picks from a fixed set and an out-of-set answer is a validation failure,
so it cannot invent "top 5 funds" at 3 a.m.
"""

from __future__ import annotations

ARCHETYPES: tuple[str, ...] = (
    "explainer",
    "metric_teardown",
    "filing_walkthrough",
    "macro_calendar",
    "concept_comparison",
    "regulatory_update",
    "historical_parallel",
    "mistake_anatomy",
    "glossary_card",
    "data_curiosity",
)

# Topical lanes. Deliberately orthogonal to `market` (US/IN), which lives on
# `sources` and `items`. `practical_skills` covers how-to know-how (reading a
# cash-flow statement, driving a screener) and is NOT named `tips`: the label
# is injected into the P2b drafting prompt, so the word itself is a compliance
# surface.
VERTICALS: tuple[str, ...] = (
    "macro",
    "equities",
    "regulation",
    "earnings",
    "market_structure",
    "investing_concept",
    "personal_finance_concept",
    "practical_skills",
)


def is_archetype(value: object) -> bool:
    return isinstance(value, str) and value in ARCHETYPES


def is_vertical(value: object) -> bool:
    return isinstance(value, str) and value in VERTICALS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_taxonomy.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add worker/app/taxonomy.py worker/tests/test_taxonomy.py
git commit -m "feat(p2a): closed ARCHETYPES and VERTICALS taxonomy"
```

---

## Task 2: JSON contract

**Files:**
- Create: `worker/app/llm/__init__.py`, `worker/app/llm/contract.py`
- Test: `worker/tests/test_llm_contract.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `FieldSpec(validators: dict[str, Callable[[Any], bool]])`, `ContractError(ValueError)`, `extract_json(text: str) -> dict | None`, `validate(payload: dict, spec: FieldSpec) -> list[str]`, `parse(text: str, spec: FieldSpec) -> dict`.

- [ ] **Step 1: Write the failing test**

Create `worker/tests/test_llm_contract.py`:

```python
import pytest

from app.llm.contract import ContractError, FieldSpec, extract_json, parse, validate

SPEC = FieldSpec(validators={
    "name": lambda v: isinstance(v, str) and bool(v.strip()),
    "count": lambda v: isinstance(v, int) and 0 <= v <= 10,
})


def test_extract_json_from_a_fenced_block():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_from_a_bare_object():
    assert extract_json('here you go: {"a": 1} hope that helps') == {"a": 1}


def test_extract_json_returns_none_when_there_is_no_object():
    assert extract_json("sorry, I cannot help with that") is None


def test_extract_json_returns_none_for_a_json_array():
    # A list is valid JSON but not the contract shape; callers expect a dict.
    assert extract_json("[1, 2, 3]") is None


def test_validate_reports_a_missing_field():
    assert validate({"count": 1}, SPEC) == ["missing required field 'name'"]


def test_validate_reports_an_invalid_value():
    violations = validate({"name": "ok", "count": 99}, SPEC)
    assert violations == ["field 'count' has invalid value 99"]


def test_validate_returns_empty_for_a_good_payload():
    assert validate({"name": "ok", "count": 3}, SPEC) == []


def test_parse_returns_only_the_spec_fields():
    # Extra keys are dropped, so a model cannot smuggle values into a DB write.
    result = parse('{"name": "ok", "count": 3, "sneaky": "drop me"}', SPEC)
    assert result == {"name": "ok", "count": 3}


def test_parse_raises_when_there_is_no_json():
    with pytest.raises(ContractError, match="no JSON object"):
        parse("nope", SPEC)


def test_parse_raises_with_every_violation_listed():
    with pytest.raises(ContractError) as excinfo:
        parse('{"count": 99}', SPEC)
    message = str(excinfo.value)
    assert "missing required field 'name'" in message
    assert "field 'count' has invalid value 99" in message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_llm_contract.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm'`

- [ ] **Step 3: Write minimal implementation**

Create `worker/app/llm/__init__.py` with the docstring only. The
`complete_json` re-export is added in Task 4, once `router.py` exists; adding it
now would make this task's own test fail on an unresolvable import.

```python
"""Shared LLM surface for the whole worker.

P2a builds it for story scoring; P2b's drafter and both compliance-gate layers
consume it unchanged. `youtube.py`'s two hand-rolled provider paths are a
documented retrofit, scheduled for the end of P2b. See the Follow-up debt
section of the P2a design doc.
"""
```

Create `worker/app/llm/contract.py`:

```python
"""Strict JSON out of a model: extract, then validate against a FieldSpec.

The extraction half generalizes `localllm._extract_json`, which does the same
fenced-or-braces recovery for the local frame planner. The validation half is
new: P2a needs closed-enum and range checks the frame planner never had.

`parse` returns only the fields the spec names. Dropping extras is deliberate:
the result feeds a database write, and a model that invents a key should not be
able to get it near the UPDATE.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable


class ContractError(ValueError):
    """A model response that could not be parsed, or failed validation."""


@dataclass(frozen=True)
class FieldSpec:
    """Required field names mapped to a predicate each value must satisfy."""

    validators: dict[str, Callable[[Any], bool]]


_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model response."""
    fenced = _FENCED.search(text)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        candidate = text[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def validate(payload: dict, spec: FieldSpec) -> list[str]:
    """Return human-readable violations. An empty list means valid."""
    violations: list[str] = []
    for field, predicate in spec.validators.items():
        if field not in payload:
            violations.append(f"missing required field {field!r}")
            continue
        if not predicate(payload[field]):
            violations.append(f"field {field!r} has invalid value {payload[field]!r}")
    return violations


def parse(text: str, spec: FieldSpec) -> dict:
    """Extract and validate, or raise ContractError."""
    payload = extract_json(text)
    if payload is None:
        raise ContractError("response contained no JSON object")
    violations = validate(payload, spec)
    if violations:
        raise ContractError("; ".join(violations))
    return {field: payload[field] for field in spec.validators}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_llm_contract.py -q`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add worker/app/llm/ worker/tests/test_llm_contract.py
git commit -m "feat(p2a): strict-JSON contract for model responses"
```

---

## Task 3: Providers

**Files:**
- Create: `worker/app/llm/providers.py`
- Test: `worker/tests/test_llm_providers.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ProviderError(RuntimeError)` with `.retryable: bool`, `is_retryable(exc: Exception) -> bool`, `Provider(name: str, env_key: str, call: Callable[[str, str], Awaitable[str]])`, `PROVIDERS: dict[str, Provider]`, `available() -> tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

Create `worker/tests/test_llm_providers.py`:

```python
import pytest

from app.llm.providers import PROVIDERS, ProviderError, available, is_retryable


def test_the_three_real_providers_are_registered():
    # No Anthropic and no Moonshot: this deployment has no key for either, so
    # the blueprint's §8 table names models that cannot be called here.
    assert set(PROVIDERS) == {"gemini", "deepseek", "openai"}


def test_every_provider_declares_its_env_key():
    assert PROVIDERS["gemini"].env_key == "GEMINI_API_KEY"
    assert PROVIDERS["deepseek"].env_key == "DEEPSEEK_API_KEY"
    assert PROVIDERS["openai"].env_key == "OPENAI_API_KEY"


def test_available_lists_only_providers_with_a_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert available() == ("gemini",)


def test_available_treats_an_empty_key_as_absent(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert available() == ()


def test_provider_error_carries_its_own_retryable_flag():
    assert is_retryable(ProviderError("boom", retryable=True))
    assert not is_retryable(ProviderError("bad key", retryable=False))


@pytest.mark.parametrize("message", ["429 Too Many Requests", "503 overloaded", "Read timed out"])
def test_transport_errors_are_classified_retryable(message):
    assert is_retryable(RuntimeError(message))


@pytest.mark.parametrize("message", ["401 Unauthorized", "400 Bad Request"])
def test_auth_and_shape_errors_are_not_retryable(message):
    assert not is_retryable(RuntimeError(message))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_llm_providers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm.providers'`

- [ ] **Step 3: Write minimal implementation**

Create `worker/app/llm/providers.py`:

```python
"""One call signature over the text providers this deployment actually has.

Gemini, DeepSeek, OpenAI. There is no Anthropic key and no Moonshot key here,
so the blueprint's §8 routing table (Haiku primary, Kimi for variant B) names
models that cannot be called. Adding a provider is: write an adapter, add one
PROVIDERS entry, done — callers route by task name and never see this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Awaitable, Callable

import structlog

log = structlog.get_logger()

# Substring markers, matched case-insensitively against the exception text.
# Mirrors the classification `youtube.py` already applies to script generation.
RETRYABLE_MARKERS = (
    "429", "500", "502", "503", "504",
    "timeout", "timed out", "overloaded", "unavailable",
)

GEMINI_MODEL = "gemini-flash-latest"
DEEPSEEK_MODEL = "deepseek-chat"
OPENAI_MODEL = "gpt-4o-mini"

REQUEST_TIMEOUT_SECONDS = 90


class ProviderError(RuntimeError):
    """A provider call that failed, carrying its own retry classification."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def is_retryable(exc: Exception) -> bool:
    """Whether the same call is worth trying again against the same provider."""
    if isinstance(exc, ProviderError):
        return exc.retryable
    text = str(exc).lower()
    return any(marker in text for marker in RETRYABLE_MARKERS)


@dataclass(frozen=True)
class Provider:
    name: str
    env_key: str
    call: Callable[[str, str], Awaitable[str]]


async def _call_gemini(system: str, user: str) -> str:
    import asyncio

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def _sync() -> str:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return response.text or ""

    return await asyncio.to_thread(_sync)


async def _call_openai_compatible(
    *, base_url: str, api_key: str, model: str, system: str, user: str
) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
    if response.status_code >= 400:
        raise ProviderError(
            f"{response.status_code} {response.text[:200]}",
            retryable=response.status_code == 429 or response.status_code >= 500,
        )
    body = response.json()
    return body["choices"][0]["message"]["content"] or ""


async def _call_deepseek(system: str, user: str) -> str:
    return await _call_openai_compatible(
        base_url="https://api.deepseek.com/v1",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        model=DEEPSEEK_MODEL,
        system=system,
        user=user,
    )


async def _call_openai(system: str, user: str) -> str:
    return await _call_openai_compatible(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model=OPENAI_MODEL,
        system=system,
        user=user,
    )


PROVIDERS: dict[str, Provider] = {
    "gemini": Provider("gemini", "GEMINI_API_KEY", _call_gemini),
    "deepseek": Provider("deepseek", "DEEPSEEK_API_KEY", _call_deepseek),
    "openai": Provider("openai", "OPENAI_API_KEY", _call_openai),
}


def available() -> tuple[str, ...]:
    """Provider names whose API key is present and non-empty in the environment.

    Resolved here rather than discovered at call time, so a missing key is a
    routing fact rather than a runtime surprise mid-job.
    """
    return tuple(
        name for name, provider in PROVIDERS.items()
        if os.environ.get(provider.env_key, "").strip()
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_llm_providers.py -q`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add worker/app/llm/providers.py worker/tests/test_llm_providers.py
git commit -m "feat(p2a): provider adapters with key availability and retry classification"
```

---

## Task 4: Router and routing config

**Files:**
- Create: `worker/app/llm/router.py`
- Modify: `worker/app/config.py` (add `LLMConfig` after `EdgarConfig`, and `get_llm_config()` after `get_edgar_config()`)
- Modify: `worker/app/llm/__init__.py` (restore the `complete_json` re-export if it was emptied in Task 2)
- Test: `worker/tests/test_llm_router.py`

**Interfaces:**
- Consumes: `app.llm.contract.{FieldSpec, ContractError, parse}`, `app.llm.providers.{PROVIDERS, available, is_retryable}`.
- Produces: `RouterError(RuntimeError)`, `DEFAULT_MAX_ATTEMPTS: int`, `async complete_json(task: str, *, system: str, user: str, spec: FieldSpec, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> dict`. Config: `LLMConfig(routing: dict[str, dict[str, str]], score_batch_max: int)`, `async get_llm_config() -> LLMConfig`.

- [ ] **Step 1: Write the failing test**

Create `worker/tests/test_llm_router.py`:

```python
"""The router is the seam every test patches (recorded bug #13). These tests
are the only place a fake 'provider' exists; nothing here touches the network."""

import pytest

from app.llm import contract, providers, router

SPEC = contract.FieldSpec(validators={"verdict": lambda v: v in ("yes", "no")})

ROUTE = {"demo": {"primary": "gemini", "fallback": "deepseek"}}


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """Retry timing is not what these tests are about, and a real backoff would
    make the exhaustion test take 20 seconds."""
    monkeypatch.setattr(router, "_backoff", lambda _attempt: 0)


@pytest.fixture
def routed(monkeypatch):
    """Route 'demo' at gemini->deepseek, with both keys present."""
    async def _cfg():
        from app.config import LLMConfig

        return LLMConfig(routing=ROUTE)

    monkeypatch.setattr(router, "get_llm_config", _cfg)
    monkeypatch.setattr(providers, "available", lambda: ("gemini", "deepseek", "openai"))


def _provider_returning(*replies):
    """A fake provider whose successive calls return the given replies.

    A reply that is an Exception instance is raised instead of returned.
    """
    calls: list[str] = []

    async def _call(system: str, user: str) -> str:
        calls.append(user)
        reply = replies[min(len(calls) - 1, len(replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply

    _call.calls = calls  # type: ignore[attr-defined]
    return _call


async def test_returns_the_validated_payload(routed, monkeypatch):
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", _provider_returning('{"verdict": "yes"}')),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "yes"}


async def test_retries_a_retryable_error_on_the_same_provider(routed, monkeypatch):
    call = _provider_returning(RuntimeError("429 rate limited"), '{"verdict": "no"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", call),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "no"}
    assert len(call.calls) == 2


async def test_falls_straight_through_to_the_fallback_on_a_terminal_error(routed, monkeypatch):
    primary = _provider_returning(RuntimeError("401 Unauthorized"))
    fallback = _provider_returning('{"verdict": "yes"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", primary),
    )
    monkeypatch.setitem(
        providers.PROVIDERS, "deepseek",
        providers.Provider("deepseek", "DEEPSEEK_API_KEY", fallback),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "yes"}
    # Terminal means no retry against the primary at all.
    assert len(primary.calls) == 1


async def test_repairs_an_invalid_payload_exactly_once(routed, monkeypatch):
    call = _provider_returning('{"verdict": "maybe"}', '{"verdict": "yes"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", call),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "yes"}
    assert len(call.calls) == 2
    # The repair prompt tells the model what was wrong.
    assert "maybe" in call.calls[1]


async def test_gives_up_after_one_failed_repair(routed, monkeypatch):
    always_bad = _provider_returning('{"verdict": "maybe"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", always_bad),
    )
    monkeypatch.setitem(
        providers.PROVIDERS, "deepseek",
        providers.Provider("deepseek", "DEEPSEEK_API_KEY", _provider_returning('{"verdict": "no"}')),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "no"}
    # Original attempt plus one repair, then hand off. Never an endless loop.
    assert len(always_bad.calls) == 2


async def test_raises_when_every_provider_is_exhausted(routed, monkeypatch):
    for name, env in (("gemini", "GEMINI_API_KEY"), ("deepseek", "DEEPSEEK_API_KEY")):
        monkeypatch.setitem(
            providers.PROVIDERS, name,
            providers.Provider(name, env, _provider_returning(RuntimeError("503 down"))),
        )
    with pytest.raises(router.RouterError, match="exhausted"):
        await router.complete_json("demo", system="s", user="u", spec=SPEC)


async def test_raises_when_the_task_has_no_route(routed):
    with pytest.raises(router.RouterError, match="no available provider"):
        await router.complete_json("unrouted", system="s", user="u", spec=SPEC)


async def test_skips_a_routed_provider_whose_key_is_absent(monkeypatch):
    async def _cfg():
        from app.config import LLMConfig

        return LLMConfig(routing=ROUTE)

    monkeypatch.setattr(router, "get_llm_config", _cfg)
    # Primary is routed but has no key; only the fallback is usable.
    monkeypatch.setattr(providers, "available", lambda: ("deepseek",))
    fallback = _provider_returning('{"verdict": "yes"}')
    monkeypatch.setitem(
        providers.PROVIDERS, "deepseek",
        providers.Provider("deepseek", "DEEPSEEK_API_KEY", fallback),
    )
    result = await router.complete_json("demo", system="s", user="u", spec=SPEC)
    assert result == {"verdict": "yes"}
    assert len(fallback.calls) == 1


async def test_never_returns_a_default(routed, monkeypatch):
    """Decision #41 generalized: there is no fabricated-result path."""
    monkeypatch.setitem(
        providers.PROVIDERS, "gemini",
        providers.Provider("gemini", "GEMINI_API_KEY", _provider_returning("not json at all")),
    )
    monkeypatch.setitem(
        providers.PROVIDERS, "deepseek",
        providers.Provider("deepseek", "DEEPSEEK_API_KEY", _provider_returning("also not json")),
    )
    with pytest.raises(router.RouterError):
        await router.complete_json("demo", system="s", user="u", spec=SPEC)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_llm_router.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm.router'`

- [ ] **Step 3a: Add the config section**

In `worker/app/config.py`, add after the `EdgarConfig` dataclass:

```python
@dataclass(frozen=True)
class LLMConfig:
    """Task-to-provider routing (decisions #4, #21, #55, #56).

    Credentials live in env; this map lives in the `config` table under key
    'llm', so re-routing a task is a database edit rather than a deploy. The
    defaults below apply when no row exists, which is why P2a needs no
    migration: seeding the row is an ops action, not a schema change.
    """

    routing: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "story_score": {"primary": "gemini", "fallback": "deepseek"},
        }
    )
    score_batch_max: int = 25
```

Add `field` to the dataclasses import at the top of the file:

```python
from dataclasses import dataclass, field
```

Add after `get_edgar_config()`:

```python
async def get_llm_config() -> LLMConfig:
    raw = await _load("llm")
    return LLMConfig(**{k: v for k, v in raw.items() if hasattr(LLMConfig, k)})
```

- [ ] **Step 3b: Write the router**

Create `worker/app/llm/router.py`:

```python
"""Task-to-provider routing with retry, fallback, and a single repair attempt.

Callers name a *task*, never a model. That indirection is what makes decision
#4 ("model router config-driven") real: re-pointing `story_score` at another
provider is a config edit, and no caller changes.

This module is also the seam every test patches. Recorded bug #13: mocking one
layer further down let a backend route around the mock and fire live HTTP.
"""

from __future__ import annotations

import asyncio

import structlog

from app.config import get_llm_config
from app.llm import contract, providers

log = structlog.get_logger()

DEFAULT_MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2


class RouterError(RuntimeError):
    """No provider could satisfy the task. There is no fallback value."""


def _backoff(attempt: int) -> float:
    return BACKOFF_BASE_SECONDS * attempt


async def _resolve(task: str) -> list[str]:
    """Ordered, usable provider names for a task. Empty means unroutable."""
    cfg = await get_llm_config()
    route = cfg.routing.get(task)
    if route is None:
        return []
    have = providers.available()
    chain = [route.get("primary"), route.get("fallback")]
    return [name for name in chain if name and name in have]


async def complete_json(
    task: str,
    *,
    system: str,
    user: str,
    spec: contract.FieldSpec,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict:
    """Run `task` until a provider returns a payload satisfying `spec`.

    Raises RouterError when every routed provider is exhausted. It never
    returns a default, a stub, or a partially-populated dict (decision #41,
    generalized from script generation to every LLM call in the worker).
    """
    chain = await _resolve(task)
    if not chain:
        raise RouterError(f"no available provider for task {task!r}")

    last_error: Exception | None = None

    for provider_name in chain:
        provider = providers.PROVIDERS[provider_name]
        prompt = user
        repaired = False

        for attempt in range(1, max_attempts + 1):
            try:
                raw = await provider.call(system, prompt)
            except Exception as exc:  # noqa: BLE001 — classified immediately below
                last_error = exc
                if not providers.is_retryable(exc):
                    log.warning(
                        "llm_provider_terminal",
                        task=task, provider=provider_name, error=str(exc),
                    )
                    break
                log.warning(
                    "llm_provider_retry",
                    task=task, provider=provider_name, attempt=attempt, error=str(exc),
                )
                await asyncio.sleep(_backoff(attempt))
                continue

            try:
                return contract.parse(raw, spec)
            except contract.ContractError as exc:
                last_error = exc
                if repaired:
                    log.warning(
                        "llm_repair_failed",
                        task=task, provider=provider_name, error=str(exc),
                    )
                    break
                prompt = (
                    f"{user}\n\n"
                    f"Your previous reply was rejected: {exc}\n"
                    f"Return only corrected JSON. No prose, no markdown fence."
                )
                repaired = True

    raise RouterError(
        f"task {task!r} exhausted every provider in {chain}"
    ) from last_error
```

- [ ] **Step 3c: Restore the package re-export**

Ensure `worker/app/llm/__init__.py` contains the `complete_json` re-export shown in Task 2.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_llm_router.py -q`
Expected: 9 passed

Then confirm nothing else broke: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`
Expected: previously-passing count plus the new tests; the 11 DB errors remain if Postgres is down.

- [ ] **Step 5: Commit**

```bash
git add worker/app/llm/router.py worker/app/llm/__init__.py worker/app/config.py worker/tests/test_llm_router.py
git commit -m "feat(p2a): config-driven LLM router with retry, fallback, repair-once"
```

---

## Task 5: The scoring job

**Files:**
- Create: `worker/app/score.py`
- Create: `worker/tests/test_score.py` (unit), `worker/tests/test_score_db.py` (integration)
- Test fixture: `worker/tests/fixtures/score_prompt_user.txt`

**Interfaces:**
- Consumes: `app.llm.complete_json`, `app.taxonomy.{is_archetype, is_vertical}`, `app.config.{get_llm_config, get_ingest_config}`, `app.audit.audit_log`, `app.db.{get_pool, _fetchall}`.
- Produces: `SCORE_MAX_ATTEMPTS: int`, `SCORE_SPEC: FieldSpec`, `SYSTEM_PROMPT: str`, `build_user_prompt(headline: str, items: list[dict]) -> str`, `async fetch_unscored(limit: int, fresh_hours: int) -> list[dict]`, `async write_score(story_id, result: dict) -> bool`, `async score_new_job() -> None`.

- [ ] **Step 1: Write the failing unit test**

Create `worker/tests/test_score.py`:

```python
"""Unit tests for scoring. The router is patched, never a provider (bug #13)."""

import pytest

from app import score, taxonomy
from app.llm import contract

GOOD = {
    "score": 72.0,
    "angle": "Why the related-party note matters more than the headline number",
    "vertical": "earnings",
    "content_archetype": "filing_walkthrough",
}


def test_spec_rejects_an_invented_archetype():
    payload = {**GOOD, "content_archetype": "top_5_funds"}
    violations = contract.validate(payload, score.SCORE_SPEC)
    assert violations == ["field 'content_archetype' has invalid value 'top_5_funds'"]


def test_spec_rejects_an_invented_vertical():
    payload = {**GOOD, "vertical": "stock_tips"}
    violations = contract.validate(payload, score.SCORE_SPEC)
    assert violations == ["field 'vertical' has invalid value 'stock_tips'"]


@pytest.mark.parametrize("bad", [-1, 101, "high", None])
def test_spec_rejects_a_score_outside_the_range(bad):
    violations = contract.validate({**GOOD, "score": bad}, score.SCORE_SPEC)
    assert violations == [f"field 'score' has invalid value {bad!r}"]


def test_spec_rejects_an_empty_angle():
    violations = contract.validate({**GOOD, "angle": "   "}, score.SCORE_SPEC)
    assert violations == ["field 'angle' has invalid value '   '"]


def test_spec_accepts_a_good_payload():
    assert contract.validate(GOOD, score.SCORE_SPEC) == []


def test_spec_accepts_an_integer_score():
    assert contract.validate({**GOOD, "score": 72}, score.SCORE_SPEC) == []


def test_system_prompt_lists_every_taxonomy_value():
    """Provenance (decision #24). If someone widens a tuple without updating
    the prompt, the model is offered a menu that no longer matches the
    validator and every call fails validation for a reason nobody can see."""
    for value in taxonomy.ARCHETYPES:
        assert value in score.SYSTEM_PROMPT
    for value in taxonomy.VERTICALS:
        assert value in score.SYSTEM_PROMPT


def test_system_prompt_forbids_advisory_output():
    lowered = score.SYSTEM_PROMPT.lower()
    assert "never" in lowered
    assert "buy" in lowered and "sell" in lowered


def test_user_prompt_matches_the_frozen_fixture():
    from pathlib import Path

    items = [
        {"title": "Reliance Q1 profit rises 8%", "source_name": "ET Markets"},
        {"title": "RIL flags higher capex for retail", "source_name": "Mint"},
    ]
    rendered = score.build_user_prompt("Reliance posts Q1 results", items)
    expected = (
        Path(__file__).parent / "fixtures" / "score_prompt_user.txt"
    ).read_text(encoding="utf-8")
    assert rendered == expected


def test_user_prompt_handles_a_story_with_no_items():
    rendered = score.build_user_prompt("A manual idea with no sources", [])
    assert "A manual idea with no sources" in rendered
    assert "(no linked sources)" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_score.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.score'`

- [ ] **Step 3a: Write the scoring module**

Create `worker/app/score.py`:

```python
"""Story scoring (P2a).

Turns the P1 reader's output into a ranked editorial queue: every clustered
story gets a 0-100 score, an angle, a vertical, and a content archetype.

Two invariants this module exists to hold:

  1. It never mutates `stories.status`. `db.get_pending_stories` hard-codes
     `WHERE s.status = 'inbox'` and `ideation.py` reads the same Inbox for the
     video path, so flipping status to 'scored' would silently empty both.
     Scored-ness is derived from `score IS NOT NULL`.

  2. It never writes a fabricated score. A score the model did not produce
     silently reorders the owner's editorial queue, which is the scoring
     equivalent of recorded bug #12 (a stub script became a publishable video).
     A story that cannot be scored stays unscored and is retried next cycle.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import structlog

from app.audit import audit_log
from app.config import get_ingest_config, get_llm_config
from app.db import _fetchall, get_pool
from app.llm import complete_json
from app.llm.contract import FieldSpec
from app.llm.router import RouterError
from app.taxonomy import ARCHETYPES, VERTICALS, is_archetype, is_vertical

log = structlog.get_logger()

# Mirrors youtube.py:50 so the two LLM paths fail on the same shape and are
# tunable the same way under a flaky provider.
SCORE_MAX_ATTEMPTS = int(os.environ.get("SCORE_MAX_ATTEMPTS", "4"))


def _is_score(value: Any) -> bool:
    # bool is a subclass of int; True would otherwise pass as a score of 1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 0 <= value <= 100


def _is_angle(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


SCORE_SPEC = FieldSpec(validators={
    "score": _is_score,
    "angle": _is_angle,
    "vertical": is_vertical,
    "content_archetype": is_archetype,
})


SYSTEM_PROMPT = f"""You rank finance news stories for an educational X account.

The account's persona is educator, analyst, and commentator. It is NEVER an
adviser. It may name and analyse specific companies. It must never tell anyone
to buy, sell, hold, accumulate, or book profit, never give target prices or
entry and exit levels, and never promise or project returns.

Score a story on how well it can become a compliant, genuinely interesting post
under that persona. Reward stories that can be explained through fundamentals,
filings, mechanics, or history. Penalise stories whose only angle is a price
move plus an implied action, because that angle cannot be written compliantly.

Return ONE JSON object and nothing else. No markdown fence, no commentary.

{{
  "score": <number 0-100>,
  "angle": "<one sentence: the specific editorial angle worth taking>",
  "vertical": "<one of the verticals below>",
  "content_archetype": "<one of the archetypes below>"
}}

Verticals (choose exactly one):
{chr(10).join(f"- {v}" for v in VERTICALS)}

Archetypes (choose exactly one):
{chr(10).join(f"- {a}" for a in ARCHETYPES)}

Both lists are closed. Never invent a value; pick the closest fit."""


def build_user_prompt(headline: str, items: list[dict]) -> str:
    """Render the bounded source packet for one story."""
    if items:
        sources = "\n".join(
            f"- {item['title']} ({item['source_name']})" for item in items
        )
    else:
        sources = "(no linked sources)"
    return f"Headline: {headline}\n\nLinked sources:\n{sources}"


async def fetch_unscored(limit: int, fresh_hours: int) -> list[dict]:
    """Unscored Inbox stories inside the fresh-news window, with their items.

    The window predicate mirrors `db.get_pending_stories` exactly, including
    the manual-idea branch (a story with no linked items). Divergence between
    "what the Inbox shows" and "what gets scored" would leave manual ideas
    permanently unscored and sinking to the bottom of a score-ordered queue.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        stories = await _fetchall(
            conn,
            """
            SELECT s.id, s.headline
              FROM stories s
             WHERE s.score IS NULL
               AND s.status = 'inbox'
               AND (
                    NOT EXISTS (SELECT 1 FROM story_items si WHERE si.story_id = s.id)
                    OR EXISTS (
                        SELECT 1
                          FROM story_items si
                          JOIN items i ON i.id = si.item_id
                         WHERE si.story_id = s.id
                           AND i.published_at >= now() - make_interval(hours := %s)
                           AND NOT (i.warnings @> '["date_missing"]'::jsonb)
                    )
               )
             ORDER BY s.created_at DESC
             LIMIT %s
            """,
            fresh_hours,
            limit,
        )
        for story in stories:
            story["items"] = await _fetchall(
                conn,
                """
                SELECT i.title, src.name AS source_name
                  FROM items i
                  JOIN story_items si ON i.id = si.item_id
                  JOIN sources src ON i.source_id = src.id
                 WHERE si.story_id = %s
                 ORDER BY i.published_at DESC
                """,
                story["id"],
            )
    return stories


async def write_score(story_id: uuid.UUID, result: dict) -> bool:
    """Write all four columns in one UPDATE. Returns whether a row changed.

    `AND score IS NULL` makes this idempotent: a concurrent or repeated run
    cannot overwrite a score that already landed. `status` is deliberately
    absent from the SET clause.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            UPDATE stories
               SET score = %s, angle = %s, vertical = %s, content_archetype = %s
             WHERE id = %s AND score IS NULL
            """,
            (
                float(result["score"]),
                result["angle"],
                result["vertical"],
                result["content_archetype"],
                story_id,
            ),
        )
        return cursor.rowcount > 0


async def score_new_job() -> None:
    """Score a bounded batch of unscored Inbox stories."""
    llm_cfg = await get_llm_config()
    ingest_cfg = await get_ingest_config()

    stories = await fetch_unscored(llm_cfg.score_batch_max, ingest_cfg.fresh_news_hours)
    if not stories:
        return

    scored = 0
    failed = 0
    for story in stories:
        try:
            result = await complete_json(
                "story_score",
                system=SYSTEM_PROMPT,
                user=build_user_prompt(story["headline"], story["items"]),
                spec=SCORE_SPEC,
                max_attempts=SCORE_MAX_ATTEMPTS,
            )
        except RouterError as exc:
            failed += 1
            log.warning("story_score_failed", story_id=str(story["id"]), error=str(exc))
            await audit_log(
                actor="worker",
                action="story_score_failed",
                entity=str(story["id"]),
                entity_type="story",
                after={"error": str(exc)},
            )
            continue

        if await write_score(story["id"], result):
            scored += 1

    log.info("score_new_complete", scored=scored, failed=failed, considered=len(stories))
```

- [ ] **Step 3b: Generate the frozen prompt fixture**

Run this once to write the fixture from the implementation, then read it and confirm it looks right before committing:

```bash
cd worker; ..\.venv\Scripts\python.exe -c "from app.score import build_user_prompt; from pathlib import Path; items=[{'title':'Reliance Q1 profit rises 8%','source_name':'ET Markets'},{'title':'RIL flags higher capex for retail','source_name':'Mint'}]; Path('tests/fixtures/score_prompt_user.txt').write_text(build_user_prompt('Reliance posts Q1 results', items), encoding='utf-8')"
```

- [ ] **Step 4: Run the unit tests**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_score.py -q`
Expected: 13 passed

- [ ] **Step 5: Write the failing integration test**

Create `worker/tests/test_score_db.py`:

```python
"""DB-level behaviour of scoring. Requires local Postgres."""

import uuid

import pytest

pytestmark = pytest.mark.integration


async def _seed_story(db, headline: str = "Test story") -> uuid.UUID:
    from app.db import _fetchval

    async with db.connection() as conn:
        return await _fetchval(
            conn,
            "INSERT INTO stories (headline, status) VALUES (%s, 'inbox') RETURNING id",
            headline,
        )


async def _read_story(db, story_id: uuid.UUID) -> dict:
    from app.db import _fetchone

    async with db.connection() as conn:
        return await _fetchone(
            conn,
            "SELECT score, angle, vertical, content_archetype, status "
            "FROM stories WHERE id = %s",
            story_id,
        )


GOOD = {
    "score": 72.0,
    "angle": "The related-party note matters more than the headline number",
    "vertical": "earnings",
    "content_archetype": "filing_walkthrough",
}


async def test_write_score_sets_all_four_columns(db):
    from app.score import write_score

    story_id = await _seed_story(db)
    assert await write_score(story_id, GOOD) is True

    row = await _read_story(db, story_id)
    assert row["score"] == 72.0
    assert row["angle"] == GOOD["angle"]
    assert row["vertical"] == "earnings"
    assert row["content_archetype"] == "filing_walkthrough"


async def test_write_score_leaves_status_alone(db):
    """The load-bearing one. Flipping status would empty the Inbox."""
    from app.score import write_score

    story_id = await _seed_story(db)
    await write_score(story_id, GOOD)

    row = await _read_story(db, story_id)
    assert row["status"] == "inbox"


async def test_write_score_is_idempotent(db):
    from app.score import write_score

    story_id = await _seed_story(db)
    assert await write_score(story_id, GOOD) is True
    # A second pass must not overwrite an existing score.
    assert await write_score(story_id, {**GOOD, "score": 10.0}) is False

    row = await _read_story(db, story_id)
    assert row["score"] == 72.0


async def test_a_scored_story_is_still_returned_by_the_inbox(db):
    """Regression for the hazard this design was written around, and the shape
    of recorded bug #18: a scored story must not vanish from the Inbox."""
    from app.db import get_pending_stories
    from app.score import write_score

    story_id = await _seed_story(db, "Scored but still pending")
    await write_score(story_id, GOOD)

    headlines = [s["headline"] for s in await get_pending_stories(fresh_hours=48)]
    assert "Scored but still pending" in headlines


async def test_fetch_unscored_skips_already_scored_stories(db):
    from app.score import fetch_unscored, write_score

    unscored_id = await _seed_story(db, "Not yet scored")
    scored_id = await _seed_story(db, "Already scored")
    await write_score(scored_id, GOOD)

    found = {s["headline"] for s in await fetch_unscored(limit=25, fresh_hours=48)}
    assert "Not yet scored" in found
    assert "Already scored" not in found


async def test_fetch_unscored_respects_the_batch_limit(db):
    from app.score import fetch_unscored

    for index in range(5):
        await _seed_story(db, f"Story {index}")

    assert len(await fetch_unscored(limit=3, fresh_hours=48)) == 3


async def test_fetch_unscored_includes_manual_ideas_without_items(db):
    """Manual ideas have no linked items. They must still be scored, or they
    sink to the bottom of a score-ordered Inbox forever."""
    from app.score import fetch_unscored

    await _seed_story(db, "Manual idea, no sources")
    found = {s["headline"] for s in await fetch_unscored(limit=25, fresh_hours=48)}
    assert "Manual idea, no sources" in found
```

- [ ] **Step 6: Run the integration tests**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_score_db.py -q`
Expected: 7 passed with local Postgres up; errors (not failures) if it is down, same as the other DB tests.

- [ ] **Step 7: Commit**

```bash
git add worker/app/score.py worker/tests/test_score.py worker/tests/test_score_db.py worker/tests/fixtures/score_prompt_user.txt
git commit -m "feat(p2a): story scoring job with closed-enum validation"
```

---

## Task 6: Register the job

**Files:**
- Modify: `worker/app/scheduler.py` (inside `build_job_specs`, alongside the existing `cluster_job` / `embed_retry_job` wrappers)
- Test: `worker/tests/test_score_registration.py`

**Interfaces:**
- Consumes: `app.score.score_new_job`.
- Produces: a `JobSpec(id="score_new", minutes=15, ...)` entry in the list returned by `build_job_specs()`.

- [ ] **Step 1: Write the failing test**

Create `worker/tests/test_score_registration.py`:

```python
"""score_new must obey the registry invariant (decision #22): every job under
AsyncIOExecutor is `async def`, or it fails silently at fire time."""

import inspect

import pytest

pytestmark = pytest.mark.integration


async def test_score_new_is_registered(db):
    from app.scheduler import build_job_specs

    specs = {spec.id: spec for spec in await build_job_specs()}
    assert "score_new" in specs


async def test_score_new_runs_every_fifteen_minutes(db):
    from app.scheduler import build_job_specs

    specs = {spec.id: spec for spec in await build_job_specs()}
    assert specs["score_new"].minutes == 15


async def test_score_new_is_a_coroutine_function(db):
    from app.scheduler import build_job_specs

    specs = {spec.id: spec for spec in await build_job_specs()}
    assert inspect.iscoroutinefunction(specs["score_new"].fn)


async def test_score_new_takes_the_advisory_lock(db):
    """Only db_health is exempt (decision #27). A second replica must not
    double-score and double-bill."""
    from app.scheduler import build_job_specs

    specs = {spec.id: spec for spec in await build_job_specs()}
    assert specs["score_new"].lock is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_score_registration.py -q`
Expected: FAIL with `KeyError: 'score_new'` / assertion error on the first test

- [ ] **Step 3: Write minimal implementation**

In `worker/app/scheduler.py`, inside `build_job_specs()`, add a named wrapper next to the existing ones. It must be a real `async def`; a lambda or `functools.partial` is not a coroutine function and trips the registry assertion (recorded bug D5):

```python
    async def score_job() -> None:
        from app.score import score_new_job

        await score_new_job()
```

Then add to the returned list, after the `cluster_new` entry:

```python
        JobSpec(id="score_new", minutes=15, fn=score_job),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_score_registration.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add worker/app/scheduler.py worker/tests/test_score_registration.py
git commit -m "feat(p2a): register score_new on the 15-minute schedule"
```

---

## Task 7: Inbox surfacing

**Files:**
- Modify: `worker/app/db.py:553-600` (`get_pending_stories`)
- Modify: `worker/app/routes.py:300-308` (`GET /stories`)
- Test: `worker/tests/test_inbox_ordering.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `get_pending_stories(*, fresh_hours: int = 48, order: str = "recent") -> list[dict]`, where rows now also carry `score`, `angle`, `vertical`, `content_archetype`. `GET /stories?order=score` is the opt-in ranked view.

- [ ] **Step 1: Write the failing test**

Create `worker/tests/test_inbox_ordering.py`:

```python
import uuid

import pytest

pytestmark = pytest.mark.integration


async def _seed(db, headline: str) -> uuid.UUID:
    from app.db import _fetchval

    async with db.connection() as conn:
        return await _fetchval(
            conn,
            "INSERT INTO stories (headline, status) VALUES (%s, 'inbox') RETURNING id",
            headline,
        )


async def test_rows_carry_the_scoring_columns(db):
    from app.db import get_pending_stories
    from app.score import write_score

    story_id = await _seed(db, "Has a score")
    await write_score(story_id, {
        "score": 61.0, "angle": "An angle",
        "vertical": "macro", "content_archetype": "explainer",
    })

    row = next(s for s in await get_pending_stories(fresh_hours=48) if s["id"] == story_id)
    assert row["score"] == 61.0
    assert row["angle"] == "An angle"
    assert row["vertical"] == "macro"
    assert row["content_archetype"] == "explainer"


async def test_default_ordering_is_unchanged(db):
    """The films page depends on this. Changing the shared default would
    silently reorder the working video queue."""
    from app.db import get_pending_stories
    from app.score import write_score

    first = await _seed(db, "Older, high score")
    second = await _seed(db, "Newer, no score")
    await write_score(first, {
        "score": 99.0, "angle": "An angle",
        "vertical": "macro", "content_archetype": "explainer",
    })

    headlines = [s["headline"] for s in await get_pending_stories(fresh_hours=48)]
    # Newest first, regardless of score.
    assert headlines.index("Newer, no score") < headlines.index("Older, high score")


async def test_score_ordering_puts_the_highest_score_first(db):
    from app.db import get_pending_stories
    from app.score import write_score

    low = await _seed(db, "Low score")
    high = await _seed(db, "High score")
    await write_score(low, {
        "score": 10.0, "angle": "a", "vertical": "macro", "content_archetype": "explainer",
    })
    await write_score(high, {
        "score": 90.0, "angle": "b", "vertical": "macro", "content_archetype": "explainer",
    })

    headlines = [
        s["headline"] for s in await get_pending_stories(fresh_hours=48, order="score")
    ]
    assert headlines.index("High score") < headlines.index("Low score")


async def test_score_ordering_puts_unscored_stories_last(db):
    from app.db import get_pending_stories
    from app.score import write_score

    scored = await _seed(db, "Scored")
    await _seed(db, "Unscored")
    await write_score(scored, {
        "score": 5.0, "angle": "a", "vertical": "macro", "content_archetype": "explainer",
    })

    headlines = [
        s["headline"] for s in await get_pending_stories(fresh_hours=48, order="score")
    ]
    assert headlines.index("Scored") < headlines.index("Unscored")


async def test_an_unknown_order_is_rejected(db):
    from app.db import get_pending_stories

    with pytest.raises(ValueError, match="unknown order"):
        await get_pending_stories(fresh_hours=48, order="'; DROP TABLE stories--")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_inbox_ordering.py -q`
Expected: FAIL with `KeyError: 'score'` on the first test, `TypeError: unexpected keyword argument 'order'` on the rest

- [ ] **Step 3: Modify `get_pending_stories`**

In `worker/app/db.py`, change the signature and the story query. The ordering clause is chosen from a fixed dict, never interpolated from caller input, because it is the one part of the query that cannot be a bound parameter:

```python
_STORY_ORDERINGS = {
    # Default. The films page depends on this exact behaviour.
    "recent": "ORDER BY s.created_at DESC",
    # Opt-in ranked view for the X Inbox. NULLS LAST keeps not-yet-scored
    # stories from floating above scored ones.
    "score": "ORDER BY s.score DESC NULLS LAST, s.created_at DESC",
}


async def get_pending_stories(
    *, fresh_hours: int = 48, order: str = "recent"
) -> list[dict[str, Any]]:
    """Fetch only current, source-dated Inbox stories plus manual ideas.

    Historical data stays in the database for audit and deduplication, but a
    source story is reviewable only when at least one linked item was published
    inside the current-news window. This prevents a newly-imported old RSS
    entry from masquerading as breaking news.

    `order` selects the sort. It defaults to 'recent' so existing consumers
    are unaffected; P2a's ranked Inbox opts into 'score'.
    """
    if order not in _STORY_ORDERINGS:
        raise ValueError(f"unknown order {order!r}; expected one of {sorted(_STORY_ORDERINGS)}")
```

Then in the story `SELECT`, add the four columns and swap the hard-coded `ORDER BY`:

```python
            f"""
            SELECT s.id, s.headline, s.status, s.channel_id, s.created_at,
                   s.score, s.angle, s.vertical, s.content_archetype
              FROM stories s
             WHERE s.status = 'inbox'
               AND (
                    NOT EXISTS (SELECT 1 FROM story_items si WHERE si.story_id = s.id)
                    OR EXISTS (
                        SELECT 1
                          FROM story_items si
                          JOIN items i ON i.id = si.item_id
                         WHERE si.story_id = s.id
                           AND i.published_at >= now() - make_interval(hours := %s)
                           AND NOT (i.warnings @> '["date_missing"]'::jsonb)
                    )
               )
             {_STORY_ORDERINGS[order]}
            """,
```

Note the leading `f` on the string. The `%s` placeholder for `fresh_hours` stays a bound parameter; only the whitelisted ordering clause is interpolated.

- [ ] **Step 4: Modify the route**

In `worker/app/routes.py`, replace the `/stories` handler:

```python
@router.get("/stories")
async def get_stories(order: str = "recent") -> list[dict]:
    """Fetch current, source-dated stories for the Inbox.

    `order=score` returns the P2a ranked view; the default is unchanged so the
    films page keeps its existing queue order.
    """
    from app.config import get_ingest_config
    from app.db import get_pending_stories

    cfg = await get_ingest_config()
    try:
        return await get_pending_stories(fresh_hours=cfg.fresh_news_hours, order=order)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

Confirm `HTTPException` is already imported in `routes.py`; add it to the `fastapi` import if not.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_inbox_ordering.py -q`
Expected: 5 passed

Then the full suite: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`
Expected: all previously-passing tests still pass. Pay attention to `test_routes_*.py` and `test_autopilot.py`, which consume the Inbox.

- [ ] **Step 6: Commit**

```bash
git add worker/app/db.py worker/app/routes.py worker/tests/test_inbox_ordering.py
git commit -m "feat(p2a): expose scoring columns and opt-in score ordering on the Inbox"
```

---

## Task 8: Show the rank in the GUI

**Files:**
- Modify: `gui/src/app/films/page.tsx` (the `Story` type, and the story `<option>` at lines 254-256)

**Interfaces:**
- Consumes: the four new fields on `GET /stories` rows from Task 7.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Extend the Story type**

In `gui/src/app/films/page.tsx`, find the `Story` type and add the four optional fields. They are optional because a story is unscored until `score_new` reaches it:

```tsx
type Story = {
  id: string;
  headline: string;
  created_at: string;
  items: SourceItem[];
  score?: number | null;
  angle?: string | null;
  vertical?: string | null;
  content_archetype?: string | null;
};
```

- [ ] **Step 2: Show score and archetype on each option**

Replace the story `<option>` (currently `<option key={story.id} value={story.id}>{story.headline}</option>`):

```tsx
                {stories.map((story) => (
                  <option key={story.id} value={story.id}>
                    {story.score != null ? `[${Math.round(story.score)}] ` : ""}
                    {story.headline}
                    {story.content_archetype ? ` · ${story.content_archetype}` : ""}
                  </option>
                ))}
```

The page keeps requesting the default ordering. This task adds visibility, not reordering: changing the video queue's sort is explicitly out of scope.

- [ ] **Step 3: Verify the build and types**

Run: `cd gui; npm run build`
Expected: build succeeds, `/films` still listed as a route.

- [ ] **Step 4: Verify it renders**

Start the studio with `START_LAMKA_LABS_STUDIO.bat`, open `/films`, and open the Research story dropdown.
Expected: scored stories read `[72] Reliance posts Q1 results · filing_walkthrough`; unscored ones read as before.

Note recorded bug #19: the FastAPI worker never hot-reloads. Restart the worker process before trusting any live check against it.

- [ ] **Step 5: Commit**

```bash
git add gui/src/app/films/page.tsx
git commit -m "feat(p2a): show story score and archetype in the Inbox dropdown"
```

---

## Task 9: Close out

**Files:**
- Modify: `PROGRESS.md` (phase table row for P2, and the decisions log)

- [ ] **Step 1: Add the P2a row to the phase table**

In `PROGRESS.md`, replace the `**P2 — Brain + Gate**` row with two rows:

```markdown
| **P2a — Score & Inbox** | ✅ Shipped | LLM router (`worker/app/llm/`), closed taxonomy, `score_new` job every 15 min, ranked Inbox. Spec: `docs/superpowers/specs/2026-08-20-p2a-score-and-inbox-design.md`. No migration needed — the columns were laid down in P1. |
| **P2b — Draft & Gate** | ⬜ Not started | Voice Pack (needs a `voice_profile` profile-key migration), archetype-aware drafting, L1 regex gate, L2 cross-model judge. |
```

- [ ] **Step 2: Append decisions 54-62**

Add these rows to `PROGRESS.md`'s cumulative decisions log, continuing after #53:

```markdown
| 54 | P2 split into P2a (Score & Inbox) and P2b (Draft & Gate) | Decision #1 one level down: each half independently verifiable, and the router is proven against real stories before the gate is built on it |
| 55 | Router keys on task name, not model name | Callers stay ignorant of providers; re-routing is a config edit |
| 56 | Task-to-provider map in `config`, credentials in env | Decision #21's two-tier split applied to model routing |
| 57 | `ARCHETYPES` and `VERTICALS` are code constants, not config | Same reasoning as #43: in config they are one GUI edit from removal, with no git trace |
| 58 | Scoring does not mutate `stories.status` | `status` keeps one meaning; flipping it would silently empty the Inbox and break YouTube ideation |
| 59 | The practical-know-how vertical is named `practical_skills`, not `tips` | The vertical label reaches the drafting prompt in P2b, so the taxonomy word is a compliance surface |
| 60 | `investing_concept` separate from `personal_finance_concept` | Distinct editorial lanes; merging them loses a slice the owner asked for |
| 61 | Inbox ordering is a parameter, default unchanged | Changing the shared default would silently reorder the working video queue |
| 62 | Router raises on exhaustion; no fabricated score | #41 generalized from script generation to all LLM calls |
```

- [ ] **Step 3: Record the follow-up debt**

Add to `PROGRESS.md` under the P2a row's notes: `youtube.py`'s two hand-rolled provider paths still call providers directly rather than through `llm/router.py`. Retire at the end of P2b.

- [ ] **Step 4: Run the full suite one last time**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`
Expected: green, with DB tests passing if Postgres is up.

- [ ] **Step 5: Commit and push**

```bash
git add PROGRESS.md
git commit -m "docs(p2a): record shipped status, decisions 54-62, and the router retrofit debt"
git push origin main
```

---

## Acceptance

From the spec, verified at the end of Task 9:

- [ ] Ten stories come back scored, angled, and stamped with an in-set vertical and archetype.
- [ ] The Inbox returns them ranked when `order=score` is requested, and unchanged in the films path.
- [ ] Full worker suite green, no network in tests.
- [ ] A forced provider failure leaves the story unscored with a `story_score_failed` audit event, and the next cycle picks it up.
