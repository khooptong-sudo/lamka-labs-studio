"""Format compatibility pruning.

Choosing a `format` makes some other fields meaningless. Log colour profiles are
a digital-sensor concept, so they cannot coexist with a film gauge; film stock is
a film concept, so it cannot coexist with a digital sensor; consumer formats
(VHS, CCTV) have no cinema camera, colour profile, or stock at all.

Runs before assembly so that LLM-built and pipeline-built states are pruned too,
not just states a human clicked together.
"""
from __future__ import annotations

FORMAT_CATEGORY: dict[str, str] = {
    "35mm film": "film",
    "16mm film": "film",
    "8mm film": "film",
    "Super 8mm film": "film",
    "65mm film": "film",
    "VistaVision": "film",
    "anamorphic 35mm film": "film",
    "infrared film": "film",
    "hand-cranked early cinema": "film",
    "digital": "digital",
    "digital large format": "digital",
    "DSLR / mirrorless": "dslr",
    "MiniDV": "consumer",
    "VHS": "consumer",
    "360-degree video": "consumer",
    "surveillance CCTV": "consumer",
}

# Fields dropped for each format category.
DROPPED: dict[str, tuple[str, ...]] = {
    "film": ("color_science",),
    "digital": ("film_stock",),
    "dslr": ("film_stock",),
    "consumer": ("camera_body", "color_science", "film_stock"),
}


def category_of(format_value: str | None) -> str | None:
    if not format_value:
        return None
    return FORMAT_CATEGORY.get(format_value)


def prune(fields: dict) -> dict:
    """Return a copy of `fields` with format-incompatible entries removed.

    Handles both plain and `ms_`-prefixed fields; a multi-shot global format
    gates the multi-shot global fields.
    """
    out = dict(fields)
    for prefix in ("", "ms_"):
        category = category_of(out.get(f"{prefix}format"))
        if category is None:
            continue
        for field in DROPPED.get(category, ()):
            out.pop(f"{prefix}{field}", None)
    return out
