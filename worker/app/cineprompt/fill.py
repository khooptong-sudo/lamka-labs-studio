"""Scene description to field-state.

The model picks slots from a fixed vocabulary; it never writes prose. Whatever
it returns is snapped to that vocabulary, so an imprecise-but-correct answer
("ARRI Alexa 65" when the vocabulary says "shot on ARRI Alexa 65") is rescued
rather than discarded. Values that match nothing are dropped and logged.

A fill that fails raises. It never invents fields: a prompt the user believes
describes their scene but does not is worse than no prompt at all.
"""
from __future__ import annotations

import difflib
import json
import logging
import re

from . import compat, vocab

log = logging.getLogger(__name__)

# Never accepted from a model; the UI owns these.
BLOCKED_FIELDS = frozenset({"delivery_style", "delivery_style_custom",
                            "sound_mode", "dialogue_language"})

SNAP_THRESHOLD = 0.82
MIN_FILLED_FIELDS = 6     # absolute floor
MIN_SNAP_SURVIVAL = 0.5   # proportion of returned values that are real vocabulary

_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


class FillError(RuntimeError):
    """The model did not produce a usable field-state."""


def extract_json(text: str) -> dict | None:
    """Pull a JSON object out of a model response, fenced or bare."""
    match = _FENCE.search(text)
    candidate = match.group(1) if match else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(candidate[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def snap(field: str, value: str) -> str | None:
    """Match a returned value to the field's vocabulary, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    allowed = vocab.values_for(field)
    if not allowed:
        return value if vocab.is_free_text(field) else None

    if value in allowed:
        return value
    folded = value.casefold().strip()
    for candidate in allowed:
        if candidate.casefold() == folded:
            return candidate
    for candidate in allowed:
        if folded in candidate.casefold():
            return candidate
    best = difflib.get_close_matches(value, allowed, n=1, cutoff=SNAP_THRESHOLD)
    return best[0] if best else None


def snap_fields(raw: dict) -> tuple[dict, list[dict]]:
    """Snap every value; return (kept, near_misses)."""
    kept: dict[str, str] = {}
    misses: list[dict] = []
    known = vocab.all_fields()
    for field, value in raw.items():
        if field in BLOCKED_FIELDS or field not in known:
            continue
        snapped = snap(field, value)
        if snapped is None:
            allowed = vocab.values_for(field)
            closest = difflib.get_close_matches(str(value), allowed, n=1, cutoff=0.0)
            misses.append({"field": field, "returned": value,
                           "closest": closest[0] if closest else None})
            continue
        kept[field] = snapped
    return kept, misses


async def _generate(description: str, mode: str, level: str, provider: str) -> dict | None:
    """Call the configured model and return parsed JSON.

    Patched wholesale in tests; the engine test suite never reaches a network.
    """
    from . import prompts

    system = prompts.system_prompt(mode, level)
    if provider == "local":
        from ..localllm import ask_local
        text = await ask_local(system, description)
    else:
        from ..scene3d.author import _call_model as call_cloud
        text = await call_cloud(system, description)
    return extract_json(text) if text else None


async def fill_from_scene(description: str, mode: str = "single", level: str = "complex",
                          locked: dict | None = None, escalate: bool = True) -> dict:
    """Turn a free-text scene description into a validated field-state."""
    attempts = ["local", "local"] + (["cloud"] if escalate else [])
    last_error = "no attempt made"

    for provider in attempts:
        raw = await _generate(description, mode, level, provider)
        if not raw:
            last_error = "model returned no JSON"
            continue

        kept, misses = snap_fields(raw)
        for miss in misses:
            log.info("cineprompt snap miss field=%s returned=%r closest=%r",
                     miss["field"], miss["returned"], miss["closest"])

        considered = len(kept) + len(misses)
        survival = len(kept) / considered if considered else 0.0

        if survival < MIN_SNAP_SURVIVAL:
            last_error = f"snap survival {survival:.2f} < {MIN_SNAP_SURVIVAL}"
            continue
        if len(kept) < MIN_FILLED_FIELDS:
            last_error = f"too few fields: {len(kept)} < {MIN_FILLED_FIELDS}"
            continue

        result = compat.prune(kept)
        if locked:
            result.update(locked)
        return result

    raise FillError(f"scene-to-prompt failed: {last_error}")
