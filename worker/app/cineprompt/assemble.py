"""Deterministic prompt assembly.

Pure by design: field dict in, string out. No I/O, no config, no model calls.
That purity is what lets the golden fixtures test this against the vendor's
JavaScript implementation byte-for-byte.

Ported from lib/prompt-builder.js in the `cineprompt` npm package,
MIT licensed, Copyright (c) 2026 Light Owl, LLC.
"""
from __future__ import annotations

from typing import Callable

SECTIONS: dict[str, list[str]] = {
    "STYLE": ["media_type", "commercial_type", "documentary_style", "animation_style",
              "music_video_style", "social_media_style", "genre", "tone", "format"],
    "SUBJECT": ["char_label", "age_range", "build", "hair_style", "hair_color",
                "subject_description", "wardrobe", "expression", "body_language", "framing",
                "creature_category", "creature_subtype", "creature_label", "creature_size",
                "creature_body", "creature_skin", "creature_description", "creature_expression",
                "obj_description", "obj_material", "obj_condition", "obj_scale",
                "prod_description", "prod_material", "prod_staging", "prod_condition",
                "food_description", "food_state", "food_presentation", "food_texture",
                "cloth_description", "cloth_fabric", "cloth_presentation", "cloth_fit",
                "art_description", "art_medium", "art_setting", "art_condition",
                "botan_description", "botan_type", "botan_stage", "botan_detail",
                "veh_type", "veh_subtype", "veh_description", "veh_era", "veh_condition",
                "land_scale", "abs_description", "abs_quality", "abs_movement"],
    "ACTIONS": ["movement_type", "pacing", "interaction_type", "action_primary",
                "beat_1", "beat_2", "beat_3"],
    "ENVIRONMENT": ["setting", "isolation", "location_type", "abstract_environment",
                    "custom_location", "location", "env_time", "weather", "props",
                    "env_fg", "env_mg", "env_bg"],
    "CINEMATOGRAPHY": ["shot_type", "movement", "camera_body", "focal_length", "lens_brand",
                       "lens_filter", "dof", "lighting_style", "lighting_type",
                       "key_light", "fill_light"],
    "PALETTE": ["color_science", "film_stock", "color_grade", "palette_colors", "skin_tones"],
    "DIALOGUE": ["delivery_style", "delivery_style_custom", "dialogue", "dialogue_language"],
    "SOUND": ["sound_mode", "voiceover_text", "sfx_environment", "sfx_interior",
              "sfx_mechanical", "sfx_dramatic", "ambient", "music_genre", "music_mood", "music"],
}

DEFAULT_ORDER = ["STYLE", "SUBJECT", "ACTIONS", "ENVIRONMENT",
                 "CINEMATOGRAPHY", "PALETTE", "DIALOGUE", "SOUND"]

MEDIA_SUBCAT_FIELDS = {
    "commercial": "commercial_type", "cinematic": "genre", "documentary": "documentary_style",
    "animation": "animation_style", "music video": "music_video_style",
    "social media": "social_media_style",
}
MEDIA_ABSORBED = {"media_type", "commercial_type", "documentary_style", "animation_style",
                  "music_video_style", "social_media_style", "genre"}

_BRANDS = ("ARRI", "Sony", "RED", "Canon", "Panasonic", "Blackmagic")


def nl_join(seq) -> str:
    """['a','b','c'] -> 'a, b and c'. Non-lists pass through unchanged."""
    if not isinstance(seq, list):
        return seq
    if len(seq) <= 1:
        return seq[0] if seq else ""
    return ", ".join(seq[:-1]) + " and " + seq[-1]


def _merge_camera(cam, cs):
    if cam and cs:
        profile = cs.split(" flat log")[0].split(" flat ")[0]
        for brand in _BRANDS:
            if brand in cam and profile.startswith(brand + " "):
                profile = profile[len(brand) + 1:]
                break
        return f"{cam} in {profile}, flat log footage, ungraded"
    return cam or cs


def _merge_shot(a, b):
    if a and b:
        return f"{a}, locked-off static camera" if b == "static" else f"{a} with {b} camera movement"
    if b:
        return "locked-off static camera" if b == "static" else f"{b} camera movement"
    return a


def _merge_sound(mode, text):
    if mode and text:
        vo = text.strip()
        if not vo.startswith('"') and not vo.startswith("“"):
            vo = f'"{vo}"'
        return f"{mode}: {vo}"
    return mode or text


def _merge_rules(fields: dict) -> dict[str, tuple[str, Callable]]:
    def setting_loc(s, lt):
        custom = fields.get("custom_location") or ""
        loc = f"{lt}, {custom}" if lt and custom else (lt or custom or "")
        return f"{s}, {loc}" if s and loc else (s or loc)

    def focal(fl, brand):
        if fl and brand:
            return f"{fl[:-5] if fl.endswith(' lens') else fl} {brand}"
        return fl or brand

    def lighting(style, kind):
        if style and kind:
            base = style
            for suffix in (" light", " lighting"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
            return f"{base} {kind}"
        return style or kind

    def hair(style, color):
        if style and color:
            s = style[:-5] if style.endswith(" hair") else style
            c = color[:-5] if color.endswith(" hair") else color
            return f"{s} {c} hair"
        return style or color

    def char(label, age):
        if label and age:
            return f"{label} {age}" if age.startswith("in their") else f"{label}, {age}"
        return label or age

    def joined(a, b):
        return f"{a}, {b}" if a and b else (a or b)

    def music(genre, mood):
        if genre and mood:
            return f"{mood.split(',')[0].strip()} {genre}"
        return genre or mood

    return {
        "shot_type": ("movement", _merge_shot),
        "setting": ("location_type", setting_loc),
        "focal_length": ("lens_brand", focal),
        "lighting_style": ("lighting_type", lighting),
        "env_time": ("weather", joined),
        "key_light": ("fill_light", joined),
        "camera_body": ("color_science", _merge_camera),
        "film_stock": ("color_grade", joined),
        "hair_style": ("hair_color", hair),
        "expression": ("body_language", joined),
        "char_label": ("age_range", char),
        "creature_category": ("creature_label", joined),
        "veh_type": ("veh_subtype", lambda t, s: s or t or None),
        "music_genre": ("music_mood", music),
        "sound_mode": ("voiceover_text", _merge_sound),
    }


def _media_type_text(fields: dict) -> str | None:
    raw = fields.get("media_type")
    if not raw:
        return None
    types = raw if isinstance(raw, list) else [raw]
    parts = []
    for mt in types:
        subcat_field = MEDIA_SUBCAT_FIELDS.get(mt)
        subcat = fields.get(subcat_field) if subcat_field else None
        if subcat:
            if mt == "cinematic":
                arr = subcat if isinstance(subcat, list) else [subcat]
                parts.append(f"cinematic {nl_join(arr)}")
            elif isinstance(subcat, list):
                parts.append(nl_join(subcat))
            else:
                parts.append(subcat)
        else:
            parts.append(mt)
    return " ".join(parts)


_GEAR = {"camera_body", "focal_length", "lens_filter"}


def build_text(fields: dict, section_order: list[str] | None = None) -> str:
    """Assemble ordered field values into prompt prose."""
    rules = _merge_rules(fields)
    skip = {partner for partner, _fn in rules.values()}
    skip.add("custom_location")

    media_text = _media_type_text(fields)
    order = section_order or DEFAULT_ORDER

    values: list[dict] = []
    for section in order:
        for field in SECTIONS[section]:
            if field in MEDIA_ABSORBED:
                if field == "media_type" and media_text:
                    values.append({"text": media_text, "section": section, "field": field})
                continue
            if field in skip:
                continue
            if field in rules:
                partner, fn = rules[field]
                v1, v2 = nl_join(fields.get(field)), nl_join(fields.get(partner))
                if v1 or v2:
                    values.append({"text": fn(v1, v2), "section": section, "field": field})
                continue
            val = fields.get(field)
            if not val:
                continue
            if field == "dialogue":
                lines = val if val.startswith(('"', "“")) else f'"{val}"'
                values.append({"text": f"Dialogue: {lines}", "section": section, "field": field})
            else:
                values.append({"text": nl_join(val), "section": section, "field": field})

    if not values:
        return ""

    segments: list[str] = []
    subject_buf: list[dict] = []
    gear_buf: list[dict] = []

    def flush_subject():
        if subject_buf:
            out = subject_buf[0]["text"]
            for item in subject_buf[1:]:
                out += ("; " if item["field"] == "framing" else ", ") + item["text"]
            segments.append(out)
            subject_buf.clear()

    def flush_gear():
        if gear_buf:
            segments.append(", ".join(g["text"] for g in gear_buf))
            gear_buf.clear()

    for v in values:
        if v["section"] == "SUBJECT":
            flush_gear()
            subject_buf.append(v)
        elif v["section"] == "CINEMATOGRAPHY" and v["field"] in _GEAR:
            flush_subject()
            gear_buf.append(v)
        else:
            flush_subject()
            flush_gear()
            segments.append(v["text"])
    flush_subject()
    flush_gear()

    out = []
    for seg in segments:
        text = seg[0].upper() + seg[1:] if seg else seg
        if not text.endswith((".", "!", '"')):
            text += "."
        out.append(text)
    return " ".join(out)
