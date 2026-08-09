"""Vocabulary loading.

base.json is the vendor's field-values.json, MIT licensed, Copyright (c) 2026
Light Owl, LLC. Never edit it by hand; put additions in lamka.json, which both
extends fields with new values and introduces fields of its own.
"""
from __future__ import annotations

import json
from pathlib import Path

_DATA = Path(__file__).parent / "data"


def _load(name: str) -> dict[str, list[str]]:
    with (_DATA / name).open(encoding="utf-8") as fh:
        return json.load(fh)


_BASE: dict[str, list[str]] = _load("base.json")
_OVERLAY: dict[str, list[str]] = _load("lamka.json")
_CACHE: dict[str, list[str]] = {}


def values_for(field: str) -> list[str]:
    """Allowed values for a field. Empty list means free text or unknown."""
    if field in _CACHE:
        return _CACHE[field]
    merged = list(_BASE.get(field, []))
    for value in _OVERLAY.get(field, []):
        if value not in merged:
            merged.append(value)
    _CACHE[field] = merged
    return merged


def all_fields() -> set[str]:
    return set(_BASE) | set(_OVERLAY)


def is_free_text(field: str) -> bool:
    """True when the field takes arbitrary text rather than a fixed vocabulary."""
    return field in all_fields() and not values_for(field)
