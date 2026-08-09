"""Per-model prompt shaping.

Model-specific optimisation is two things and no more: the order the sections
appear in, and how many characters the target accepts. Extracted from the
cineprompt.io application bundle.
"""
from __future__ import annotations

from . import assemble

MODEL_ORDERS: dict[str, list[str]] = {
    "universal": ["STYLE", "SUBJECT", "ACTIONS", "ENVIRONMENT", "CINEMATOGRAPHY", "PALETTE", "DIALOGUE", "SOUND"],
    "sora": ["STYLE", "SUBJECT", "ENVIRONMENT", "CINEMATOGRAPHY", "ACTIONS", "PALETTE", "DIALOGUE", "SOUND"],
    "veo": ["CINEMATOGRAPHY", "SUBJECT", "ACTIONS", "ENVIRONMENT", "STYLE", "PALETTE", "DIALOGUE", "SOUND"],
    "kling": ["ENVIRONMENT", "SUBJECT", "ACTIONS", "CINEMATOGRAPHY", "STYLE", "PALETTE", "DIALOGUE", "SOUND"],
    "seedance": ["SUBJECT", "ACTIONS", "CINEMATOGRAPHY", "STYLE", "PALETTE", "ENVIRONMENT", "DIALOGUE", "SOUND"],
    "grok": ["SUBJECT", "ACTIONS", "ENVIRONMENT", "CINEMATOGRAPHY", "STYLE", "PALETTE", "SOUND", "DIALOGUE"],
    "pixverse": ["SUBJECT", "ACTIONS", "ENVIRONMENT", "CINEMATOGRAPHY", "STYLE", "PALETTE", "DIALOGUE", "SOUND"],
    "happyhorse": ["SUBJECT", "ACTIONS", "CINEMATOGRAPHY", "ENVIRONMENT", "STYLE", "PALETTE", "DIALOGUE", "SOUND"],
    "luma": ["STYLE", "SUBJECT", "ACTIONS", "CINEMATOGRAPHY", "PALETTE", "ENVIRONMENT", "DIALOGUE", "SOUND"],
}

FM_IMAGE_SECTIONS = ["STYLE", "SUBJECT", "ACTIONS", "ENVIRONMENT", "CINEMATOGRAPHY", "PALETTE"]

CHAR_LIMITS: dict[str, int] = {
    "universal": 3000, "sora": 2500, "veo": 3000, "kling": 2500, "seedance": 10000,
    "luma": 3000, "wan": 3000, "grok": 4096, "ltx": 3000, "pixverse": 2048,
    "happyhorse": 2500,
}

DEFAULT_LIMIT = 3000


def order_for(model: str, kind: str = "video") -> list[str]:
    if kind == "fm_image":
        base = MODEL_ORDERS.get(model, MODEL_ORDERS["universal"])
        return [s for s in base if s in FM_IMAGE_SECTIONS]
    return MODEL_ORDERS.get(model, MODEL_ORDERS["universal"])


def limit_for(model: str) -> int:
    return CHAR_LIMITS.get(model, DEFAULT_LIMIT)


def _cap(text: str, limit: int) -> str:
    """Trim to `limit` by dropping whole trailing sentences.

    Sections are already ordered by the target model's priority, so the trailing
    sentence is the least important one for that model. Truncating mid-string
    would hand the model a severed clause, which is worse than saying less.
    """
    if len(text) <= limit:
        return text

    def _rendered(parts: list[str]) -> str:
        out = ". ".join(parts)
        if out and not out.endswith((".", "!", '"')):
            out += "."
        return out

    parts = text.split(". ")
    while len(parts) > 1 and len(_rendered(parts)) > limit:
        parts.pop()

    out = _rendered(parts)
    if len(out) <= limit:
        return out

    # One sentence longer than the whole budget: there is no sentence boundary
    # left to cut at. Truncate at the last word boundary that leaves room for the
    # period — an empty prompt is a worse failure than a shortened one.
    head = parts[0][: limit - 1]
    cut = head.rfind(" ")
    if cut > 0:
        head = head[:cut]
    return head.rstrip(" ,;:") + "."


def render(fields: dict, model: str = "universal", kind: str = "video") -> str:
    text = assemble.build_text(fields, order_for(model, kind))
    return _cap(text, limit_for(model))
