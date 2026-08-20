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
