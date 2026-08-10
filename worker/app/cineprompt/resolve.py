"""Mode dispatch and multi-shot inheritance.

Every mode collapses to a list of flat field-dicts, which is what lets four
modes share one builder. Multi-shot inheritance is a dict merge: globals are
un-prefixed, then the shot's own keys overwrite them.
"""
from __future__ import annotations

from . import compat, profiles

MODES = ("single", "multi", "grid", "frame_motion")


def strip_ms(fields: dict) -> dict:
    """Rename ms_-prefixed globals to their plain field names."""
    out = {}
    for key, value in fields.items():
        out[key[3:] if key.startswith("ms_") else key] = value
    return out


def resolve_state(state: dict) -> list[dict]:
    """Flatten any mode into a list of field-dicts, compatibility-pruned."""
    mode = state.get("mode", "single")
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode!r}")

    fields = compat.prune(state.get("fields") or {})

    if mode in ("single", "frame_motion"):
        return [strip_ms(fields)]

    globals_ = strip_ms(fields)
    shots = state.get("shots") or []
    if mode == "grid":
        size = int(state.get("grid_size", 2))
        shots = shots[: size * size]

    return [globals_ | compat.prune(shot.get("fields") or {}) for shot in shots]


def build_prompt(state: dict) -> list[str]:
    """Render a state to prompt strings.

    Returns one string for `single`, N for `multi` and `grid`, and exactly two
    for `frame_motion` (still frame first, then motion).
    """
    model = state.get("model", "universal")
    resolved = resolve_state(state)

    if state.get("mode") == "frame_motion":
        fields = resolved[0]
        return [profiles.render(fields, model, kind="fm_image"),
                profiles.render(fields, model, kind="video")]

    return [profiles.render(fields, model) for fields in resolved]
