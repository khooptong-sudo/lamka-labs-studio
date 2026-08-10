"""System prompt and vocabulary catalogue for the fill call.

The model is shown only the fields in scope for (mode, level), each with its
full list of allowed values, so choosing correctly is easier than inventing.
"""
from __future__ import annotations

from . import assemble, vocab
from .fill import BLOCKED_FIELDS

# Fields offered at `simple` level: the ones a human reaches for first.
SIMPLE_FIELDS = frozenset({
    "media_type", "genre", "mood", "subject_description", "char_label", "age_range",
    "wardrobe", "expression", "movement_type", "pacing", "setting", "location_type",
    "env_time", "weather", "shot_type", "movement", "camera_body", "focal_length",
    "dof", "lighting_style", "lighting_type", "color_grade", "film_stock", "format",
    "framing", "props", "music_genre", "music_mood", "ambient", "sfx_environment",
})

FM_IMAGE_EXCLUDED = frozenset({"music_genre", "music_mood", "music", "ambient",
                               "sfx_environment", "sfx_interior", "sfx_mechanical",
                               "sfx_dramatic", "voiceover_text"})


def fields_in_scope(mode: str, level: str) -> list[str]:
    ordered = [f for section in assemble.SECTIONS.values() for f in section]
    scope = []
    for field in ordered:
        if field in BLOCKED_FIELDS or field not in vocab.all_fields():
            continue
        if level == "simple" and field not in SIMPLE_FIELDS:
            continue
        if mode == "fm_image" and field in FM_IMAGE_EXCLUDED:
            continue
        scope.append(field)
    return scope


def catalogue_for(mode: str, level: str) -> str:
    lines = []
    for field in fields_in_scope(mode, level):
        values = vocab.values_for(field)
        if values:
            lines.append(f"{field}: {' | '.join(values)}")
        else:
            lines.append(f"{field}: <free text>")
    return "\n".join(lines)


def system_prompt(mode: str, level: str) -> str:
    return (
        "You translate a scene description into cinematography fields.\n\n"
        "Return a single JSON object and nothing else. No prose, no explanation, "
        "no code fence commentary.\n\n"
        "Each key must be a field name below. Each value must be copied exactly "
        "from that field's allowed values, character for character. Fields marked "
        "<free text> take a short original phrase.\n\n"
        "Omit any field the description does not support. Do not guess to fill "
        "space; a short accurate answer beats a long invented one.\n\n"
        f"FIELDS\n{catalogue_for(mode, level)}"
    )
