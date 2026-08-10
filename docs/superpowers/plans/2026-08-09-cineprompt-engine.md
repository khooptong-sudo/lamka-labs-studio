# CinePrompt Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `worker/app/cineprompt/`, a pure-Python engine that turns a structured field-state into a cinematography prompt string, with vocabulary, compatibility pruning, per-model formatting, mode resolution, and an enum-constrained LLM fill.

**Architecture:** Seven modules with one-way dependencies. `assemble.py` is pure (dict in, string out) and is verified byte-for-byte against a JavaScript oracle via frozen fixtures. `vocab.py` is the only module touching disk, `fill.py` the only one touching a model. Mode handling collapses to a list of flat field-dicts in `resolve.py`, so all four modes share one builder.

**Tech Stack:** Python 3.11+, stdlib only (`json`, `difflib`, `re`, `pathlib`). Tests: pytest. Fixture generation: Node 18+, run once, offline, not part of the test suite.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-09-cineprompt-engine-design.md`
- Tests must not touch the network. No Ollama, no DeepSeek, no node at test time.
- Never fabricate field values. A failed fill raises; it does not invent.
- Run tests with: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`
- Do not run the full suite while an end-to-end render is in flight (DB tests truncate tables).
- No `Co-Authored-By` trailer and no "Generated with Claude Code" line on any commit.
- `data/base.json` is MIT, Copyright (c) 2026 Light Owl, LLC. Keep `data/LICENSE-cineprompt` beside it and never edit `base.json` by hand.
- Vocabulary lookups are by exact field name. Field names are snake_case and match the vendor's exactly (`camera_body`, not `cameraBody`).

## Oracle scope (read before Task 3)

The vendor's npm CLI and their live site are not identical. The CLI's `SECTION_ORDER` has **7 sections** and never emits `dialogue`, `delivery_style`, `delivery_style_custom`, or `dialogue_language` — those four appear in no section list, so the CLI's loop silently skips them. The live site has **8 sections**, with a separate `DIALOGUE` section holding exactly those four fields.

We implement the site's 8-section model, because that is the real product. The oracle therefore only applies to states with no dialogue fields set. **Fixture states must not contain any of those four field names.** DIALOGUE placement gets its own hand-written tests in Task 4.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/cineprompt/__init__.py` | Public surface: `build_prompt`, `resolve_state`, `fill_from_scene`, `FillError` |
| `app/cineprompt/vocab.py` | Load `base.json` + `lamka.json`, expose field enums |
| `app/cineprompt/compat.py` | Format-driven pruning matrix |
| `app/cineprompt/assemble.py` | Sections, merge rules, sentence assembly (pure, oracle-tested) |
| `app/cineprompt/profiles.py` | Per-model section order + character caps |
| `app/cineprompt/resolve.py` | Mode dispatch and `ms_*` inheritance |
| `app/cineprompt/fill.py` | Scene → fields, snap-to-enum, acceptance gate, escalation |
| `app/cineprompt/data/base.json` | Vendor vocabulary, untouched |
| `app/cineprompt/data/lamka.json` | Our overlay |
| `app/cineprompt/data/LICENSE-cineprompt` | MIT notice |
| `scripts/gen_cineprompt_fixtures.mjs` | One-time fixture generation from the JS oracle |
| `tests/fixtures/cineprompt_golden.json` | 240 frozen `{state, expected}` pairs |
| `tests/test_cineprompt_*.py` | One test module per engine module |

---

### Task 1: Vocabulary loading

**Files:**
- Create: `worker/app/cineprompt/__init__.py`
- Create: `worker/app/cineprompt/vocab.py`
- Create: `worker/app/cineprompt/data/base.json`, `data/lamka.json`, `data/LICENSE-cineprompt`
- Test: `worker/tests/test_cineprompt_vocab.py`

**Interfaces:**
- Consumes: nothing
- Produces: `values_for(field: str) -> list[str]`, `all_fields() -> set[str]`, `is_free_text(field: str) -> bool`

- [ ] **Step 1: Vendor the data files**

```powershell
cd "F:\Content Creation Project\worker"
New-Item -ItemType Directory -Force app\cineprompt\data
npm pack cineprompt@1.2.0
tar -xzf cineprompt-1.2.0.tgz
Copy-Item package\data\field-values.json app\cineprompt\data\base.json
Copy-Item package\LICENSE app\cineprompt\data\LICENSE-cineprompt
Remove-Item -Recurse -Force package, cineprompt-1.2.0.tgz
'{}' | Set-Content app\cineprompt\data\lamka.json
```

Verify: `base.json` has 130 top-level keys and 1,412 total list entries.

- [ ] **Step 2: Write the failing test**

```python
# worker/tests/test_cineprompt_vocab.py
from app.cineprompt import vocab


def test_loads_vendor_vocabulary():
    assert "shot on ARRI Alexa 65" in vocab.values_for("camera_body")
    assert len(vocab.all_fields()) == 130


def test_free_text_fields_have_no_enum():
    assert vocab.is_free_text("dialogue")
    assert not vocab.is_free_text("camera_body")


def test_unknown_field_returns_empty():
    assert vocab.values_for("not_a_real_field") == []


def test_overlay_extends_and_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(vocab, "_OVERLAY", {"camera_body": ["shot on a Lamka rig"],
                                            "brand_beat": ["logo settles into frame"]})
    vocab._CACHE.clear()
    assert "shot on a Lamka rig" in vocab.values_for("camera_body")
    assert "shot on ARRI Alexa 65" in vocab.values_for("camera_body")
    assert vocab.values_for("brand_beat") == ["logo settles into frame"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_vocab.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.cineprompt'`

- [ ] **Step 4: Implement**

```python
# worker/app/cineprompt/__init__.py
"""CinePrompt engine: structured field-state to cinematography prompt."""
```

```python
# worker/app/cineprompt/vocab.py
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_vocab.py -q`
Expected: PASS, 5 tests

- [ ] **Step 6: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/cineprompt worker/tests/test_cineprompt_vocab.py
git commit -m "feat(cineprompt): vocabulary loading with overlay support"
```

---

### Task 2: Compatibility matrix

**Files:**
- Create: `worker/app/cineprompt/compat.py`
- Test: `worker/tests/test_cineprompt_compat.py`

**Interfaces:**
- Consumes: nothing
- Produces: `prune(fields: dict) -> dict` (returns a new dict, never mutates), `category_of(format_value: str) -> str | None`

Why this exists: `format` gates three other fields. Without pruning the engine emits "shot on ARRI Alexa 65 in LogC4, Kodak Portra 400 film colors", which is three mutually exclusive things at once. The vendor enforces this in the DOM, so any non-UI caller bypasses it. Here it runs before assembly, so every caller gets it.

- [ ] **Step 1: Write the failing test**

```python
# worker/tests/test_cineprompt_compat.py
import pytest

from app.cineprompt import compat


def test_film_format_drops_color_science():
    out = compat.prune({"format": "35mm film", "color_science": "ARRI LogC4 flat log footage, ungraded",
                        "film_stock": "Kodak Portra 400 film colors, warm pastels"})
    assert "color_science" not in out
    assert out["film_stock"] == "Kodak Portra 400 film colors, warm pastels"


def test_digital_format_drops_film_stock():
    out = compat.prune({"format": "digital", "film_stock": "Kodak Portra 400 film colors, warm pastels",
                        "color_science": "ARRI LogC4 flat log footage, ungraded"})
    assert "film_stock" not in out
    assert out["color_science"] == "ARRI LogC4 flat log footage, ungraded"


def test_dslr_format_drops_film_stock_only():
    out = compat.prune({"format": "DSLR / mirrorless", "film_stock": "Kodak Portra 400 film colors, warm pastels",
                        "color_science": "Sony S-Log3 flat log footage, ungraded"})
    assert "film_stock" not in out
    assert "color_science" in out


@pytest.mark.parametrize("gated", ["camera_body", "color_science", "film_stock"])
def test_consumer_format_drops_all_three(gated):
    out = compat.prune({"format": "VHS", gated: "anything"})
    assert gated not in out


def test_no_format_prunes_nothing():
    state = {"camera_body": "shot on RED V-Raptor", "film_stock": "Kodak Portra 400 film colors, warm pastels"}
    assert compat.prune(state) == state


def test_prune_does_not_mutate_input():
    state = {"format": "VHS", "camera_body": "shot on RED V-Raptor"}
    compat.prune(state)
    assert "camera_body" in state


def test_ms_prefixed_format_gates_ms_fields():
    out = compat.prune({"ms_format": "digital", "ms_film_stock": "Kodak Portra 400 film colors, warm pastels"})
    assert "ms_film_stock" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_compat.py -q`
Expected: FAIL, `ImportError: cannot import name 'compat'`

- [ ] **Step 3: Implement**

```python
# worker/app/cineprompt/compat.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_compat.py -q`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/cineprompt/compat.py worker/tests/test_cineprompt_compat.py
git commit -m "feat(cineprompt): format compatibility pruning"
```

---

### Task 3: Assembly core, verified against the JS oracle

**Files:**
- Create: `worker/app/cineprompt/assemble.py`
- Create: `worker/scripts/gen_cineprompt_fixtures.mjs`
- Create: `worker/tests/fixtures/cineprompt_golden.json`
- Test: `worker/tests/test_cineprompt_assemble.py`

**Interfaces:**
- Consumes: nothing (pure)
- Produces: `build_text(fields: dict, section_order: list[str] | None = None) -> str`, `SECTIONS: dict[str, list[str]]`, `nl_join(seq) -> str`

This is the module the fixtures pin. It must stay free of I/O, config, and model calls.

- [ ] **Step 1: Write the fixture generator**

```javascript
// worker/scripts/gen_cineprompt_fixtures.mjs
// Run once, offline, to freeze oracle output:
//   npm pack cineprompt@1.2.0 && tar -xzf cineprompt-1.2.0.tgz
//   node scripts/gen_cineprompt_fixtures.mjs > tests/fixtures/cineprompt_golden.json
// Never run as part of the test suite.
import { readFileSync } from 'fs';
import { buildPromptText } from '../package/lib/prompt-builder.js';

const VALUES = JSON.parse(readFileSync('../package/data/field-values.json', 'utf8'));

// The CLI omits these four from every section, the live site has a DIALOGUE
// section for them. Fixtures must avoid them or the oracle disagrees with us.
const EXCLUDED = new Set(['dialogue', 'delivery_style', 'delivery_style_custom', 'dialogue_language']);

// 40 hand-picked states, one per merge rule plus empty-partner variants.
// Random sampling essentially never hits these branches: the brand-dedup path
// only fires when camera_body and color_science share a manufacturer.
const HANDPICKED = [
  { camera_body: 'shot on ARRI Alexa 65', color_science: 'ARRI LogC4 flat log footage, ungraded' },
  { camera_body: 'shot on RED V-Raptor', color_science: 'ARRI LogC4 flat log footage, ungraded' },
  { camera_body: 'shot on ARRI Alexa 65' },
  { color_science: 'ARRI LogC4 flat log footage, ungraded' },
  { shot_type: 'wide shot', movement: 'static' },
  { shot_type: 'wide shot', movement: 'pan' },
  { shot_type: 'wide shot' },
  { movement: 'static' },
  { movement: 'pan' },
  { focal_length: '50mm lens', lens_brand: 'ARRI Master Prime' },
  { focal_length: '50mm lens' },
  { lens_brand: 'ARRI Master Prime' },
  { lighting_style: 'soft light', lighting_type: 'daylight' },
  { lighting_style: 'soft light' },
  { lighting_type: 'daylight' },
  { hair_style: 'short hair', hair_color: 'black hair' },
  { hair_style: 'short hair' },
  { hair_color: 'black hair' },
  { env_time: 'dawn, first light', weather: 'light rain' },
  { env_time: 'dawn, first light' },
  { key_light: 'hard key from camera left', fill_light: 'soft fill from camera right' },
  { key_light: 'hard key from camera left' },
  { film_stock: 'Kodak Portra 400 film colors, warm pastels', color_grade: 'warm tones' },
  { film_stock: 'Kodak Portra 400 film colors, warm pastels' },
  { expression: 'a faint smile', body_language: 'shoulders relaxed' },
  { expression: 'a faint smile' },
  { char_label: 'a woman', age_range: 'in their 30s' },
  { char_label: 'a woman', age_range: 'a child' },
  { char_label: 'a woman' },
  { creature_category: 'wild animal', creature_label: 'the alpha' },
  { creature_category: 'wild animal' },
  { veh_type: 'car', veh_subtype: 'vintage roadster' },
  { veh_type: 'car' },
  { music_genre: 'orchestral', music_mood: 'tense, unsettling' },
  { music_genre: 'orchestral' },
  { sound_mode: 'voice-over narration', voiceover_text: 'It began quietly.' },
  { sound_mode: 'voice-over narration' },
  { setting: 'a cramped office', location_type: 'living room', custom_location: 'above a laundromat' },
  { setting: 'a cramped office', custom_location: 'above a laundromat' },
  { media_type: 'cinematic', genre: ['action', 'thriller'] },
];

// Deterministic PRNG so regeneration is reproducible.
let seed = 20260809;
function rand() {
  seed = (seed * 1103515245 + 12345) & 0x7fffffff;
  return seed / 0x7fffffff;
}

const FIELDS = Object.keys(VALUES).filter(f => !EXCLUDED.has(f) && VALUES[f].length > 0);

function randomState() {
  const fields = {};
  const count = 3 + Math.floor(rand() * 18);
  for (let i = 0; i < count; i++) {
    const f = FIELDS[Math.floor(rand() * FIELDS.length)];
    fields[f] = VALUES[f][Math.floor(rand() * VALUES[f].length)];
  }
  return fields;
}

const out = [];
for (const fields of HANDPICKED) {
  out.push({ fields, expected: buildPromptText({ fields }) });
}
for (let i = 0; i < 200; i++) {
  const fields = randomState();
  out.push({ fields, expected: buildPromptText({ fields }) });
}
process.stdout.write(JSON.stringify(out, null, 1));
```

- [ ] **Step 2: Generate the fixtures**

```powershell
cd "F:\Content Creation Project\worker"
npm pack cineprompt@1.2.0
tar -xzf cineprompt-1.2.0.tgz
New-Item -ItemType Directory -Force tests\fixtures
node scripts\gen_cineprompt_fixtures.mjs > tests\fixtures\cineprompt_golden.json
Remove-Item -Recurse -Force package, cineprompt-1.2.0.tgz
```

Verify the file has 240 entries and every `expected` is a non-empty string.

- [ ] **Step 3: Write the failing test**

```python
# worker/tests/test_cineprompt_assemble.py
import json
from pathlib import Path

import pytest

from app.cineprompt import assemble

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "cineprompt_golden.json").read_text(encoding="utf-8"))


def test_fixture_corpus_is_complete():
    assert len(GOLDEN) == 240


@pytest.mark.parametrize("case", GOLDEN, ids=range(len(GOLDEN)))
def test_matches_oracle(case):
    assert assemble.build_text(case["fields"]) == case["expected"]


def test_empty_state_yields_empty_string():
    assert assemble.build_text({}) == ""


def test_nl_join():
    assert assemble.nl_join(["a"]) == "a"
    assert assemble.nl_join(["a", "b"]) == "a and b"
    assert assemble.nl_join(["a", "b", "c"]) == "a, b and c"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_assemble.py -q`
Expected: FAIL, `ImportError: cannot import name 'assemble'`

- [ ] **Step 5: Implement**

Port `lib/prompt-builder.js` faithfully. The section list below is the site's 8-section model; `DIALOGUE` is absent from the oracle, which is why fixtures exclude its fields.

```python
# worker/app/cineprompt/assemble.py
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
        if not vo.startswith('"') and not vo.startswith("\u201c"):
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
                v1, v2 = fields.get(field), fields.get(partner)
                if v1 or v2:
                    values.append({"text": fn(v1, v2), "section": section, "field": field})
                continue
            val = fields.get(field)
            if not val:
                continue
            if field == "dialogue":
                lines = val if val.startswith(('"', "\u201c")) else f'"{val}"'
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
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_assemble.py -q`
Expected: PASS, 243 tests

If any fixture mismatches, the port is wrong, not the fixture. Diff the offending state's fields against `prompt-builder.js` before touching the corpus.

- [ ] **Step 7: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/cineprompt/assemble.py worker/scripts/gen_cineprompt_fixtures.mjs worker/tests/fixtures/cineprompt_golden.json worker/tests/test_cineprompt_assemble.py
git commit -m "feat(cineprompt): assembly core verified against the JS oracle"
```

---

### Task 4: Model profiles, character caps, DIALOGUE placement

**Files:**
- Create: `worker/app/cineprompt/profiles.py`
- Test: `worker/tests/test_cineprompt_profiles.py`

**Interfaces:**
- Consumes: `assemble.build_text`, `assemble.DEFAULT_ORDER`
- Produces: `order_for(model: str) -> list[str]`, `limit_for(model: str) -> int`, `render(fields: dict, model: str = "universal", kind: str = "video") -> str`

`kind` is `"video"` or `"fm_image"`. The still-image half of Frame→Motion uses six sections and drops DIALOGUE and SOUND entirely, since a still frame has no audio.

- [ ] **Step 1: Write the failing test**

```python
# worker/tests/test_cineprompt_profiles.py
from app.cineprompt import assemble, profiles


def test_veo_leads_with_cinematography():
    assert profiles.order_for("veo")[0] == "CINEMATOGRAPHY"


def test_kling_leads_with_environment():
    assert profiles.order_for("kling")[0] == "ENVIRONMENT"


def test_grok_puts_sound_before_dialogue():
    order = profiles.order_for("grok")
    assert order.index("SOUND") < order.index("DIALOGUE")


def test_unknown_model_falls_back_to_universal():
    assert profiles.order_for("wan") == profiles.order_for("universal")


def test_limits():
    assert profiles.limit_for("pixverse") == 2048
    assert profiles.limit_for("seedance") == 10000
    assert profiles.limit_for("nonexistent") == 3000


def test_fm_image_drops_audio_sections():
    order = profiles.order_for("universal", kind="fm_image")
    assert "SOUND" not in order and "DIALOGUE" not in order
    assert len(order) == 6


def test_dialogue_section_renders():
    out = profiles.render({"dialogue": "We should go."}, "universal")
    assert 'Dialogue: "We should go."' in out


def test_cap_drops_trailing_segments_not_mid_string():
    fields = {f"beat_{i}": ("word " * 180).strip() for i in (1, 2, 3)}
    raw = assemble.build_text(fields, profiles.order_for("pixverse"))
    assert len(raw) > 2048, "fixture must actually overflow, or the drop loop never runs"

    out = profiles.render(fields, "pixverse")
    assert len(out) < len(raw)
    assert len(out) <= 2048
    assert out.endswith((".", "!", '"'))
    # Retained sentences must be whole. The drop loop keeps complete sentences;
    # the mid-string fallback would truncate this one. Without this assertion the
    # test passes even with the drop loop deleted, because the fallback also
    # shortens the text and also ends it with a period.
    assert out.split(". ")[0] == raw.split(". ")[0]


def test_cap_never_returns_partial_sentence():
    fields = {f"beat_{i}": "x" * 900 for i in (1, 2, 3)}
    out = profiles.render(fields, "pixverse")
    assert len(out) <= 2048
    assert out.endswith(".")


def test_cap_handles_single_sentence_exceeding_limit():
    # No sentence boundary anywhere, and the only space follows a short label.
    # Backing up to the last space would collapse this to "Dialogue.", so the
    # word-boundary rule needs a floor.
    out = profiles.render({"dialogue": "x" * 5000}, "pixverse")
    assert out
    assert len(out) <= 2048
    assert out.endswith(".")
    assert len(out) >= 1024, f"expected most of the budget retained, got {len(out)}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_profiles.py -q`
Expected: FAIL, `ImportError: cannot import name 'profiles'`

- [ ] **Step 3: Implement**

```python
# worker/app/cineprompt/profiles.py
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
    if cut > 0 and cut >= len(head) * 0.8:
        head = head[:cut]
    return head.rstrip(" ,;:") + "."


def render(fields: dict, model: str = "universal", kind: str = "video") -> str:
    text = assemble.build_text(fields, order_for(model, kind))
    return _cap(text, limit_for(model))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_profiles.py -q`
Expected: PASS, 11 tests

- [ ] **Step 5: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/cineprompt/profiles.py worker/tests/test_cineprompt_profiles.py
git commit -m "feat(cineprompt): per-model section order and character caps"
```

---

### Task 5: Mode resolution

**Files:**
- Create: `worker/app/cineprompt/resolve.py`
- Modify: `worker/app/cineprompt/__init__.py`
- Test: `worker/tests/test_cineprompt_resolve.py`

**Interfaces:**
- Consumes: `compat.prune`, `profiles.render`
- Produces: `resolve_state(state: dict) -> list[dict]`, `build_prompt(state: dict) -> list[str]`, `strip_ms(fields: dict) -> dict`

`build_prompt` always returns a list: one entry for `single`, N for `multi`/`grid`, exactly two for `frame_motion` (still prompt first, motion prompt second).

- [ ] **Step 1: Write the failing test**

```python
# worker/tests/test_cineprompt_resolve.py
import pytest

from app.cineprompt import resolve


def test_strip_ms_renames_globals():
    assert resolve.strip_ms({"ms_camera_body": "shot on RED V-Raptor", "genre": "action"}) == {
        "camera_body": "shot on RED V-Raptor", "genre": "action"}


def test_single_mode_passes_through():
    out = resolve.resolve_state({"mode": "single", "fields": {"genre": "action"}})
    assert out == [{"genre": "action"}]


def test_multi_shot_overrides_global():
    state = {"mode": "multi",
             "fields": {"ms_camera_body": "shot on RED V-Raptor", "ms_genre": "action"},
             "shots": [{"fields": {"camera_body": "shot on ARRI Alexa 65"}}, {"fields": {}}]}
    out = resolve.resolve_state(state)
    assert out[0]["camera_body"] == "shot on ARRI Alexa 65"
    assert out[0]["genre"] == "action"
    assert out[1]["camera_body"] == "shot on RED V-Raptor"


def test_grid_fans_out():
    state = {"mode": "grid", "grid_size": 3, "fields": {"ms_genre": "action"},
             "shots": [{"fields": {"beat_1": f"beat {i}"}} for i in range(9)]}
    assert len(resolve.resolve_state(state)) == 9


def test_grid_size_caps_shots():
    state = {"mode": "grid", "grid_size": 2, "fields": {},
             "shots": [{"fields": {}} for _ in range(9)]}
    assert len(resolve.resolve_state(state)) == 4


def test_frame_motion_yields_two_prompts():
    state = {"mode": "frame_motion", "model": "universal",
             "fields": {"subject_description": "a lone figure", "movement": "pan",
                        "music_genre": "orchestral"}}
    out = resolve.build_prompt(state)
    assert len(out) == 2
    still, motion = out
    assert "orchestral" not in still          # no audio in a still frame
    assert "pan camera movement" in motion


def test_compat_applies_before_assembly():
    state = {"mode": "single", "fields": {"format": "VHS", "camera_body": "shot on ARRI Alexa 65"}}
    assert "ARRI" not in resolve.build_prompt(state)[0]


def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown mode"):
        resolve.resolve_state({"mode": "nonsense", "fields": {}})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_resolve.py -q`
Expected: FAIL, `ImportError: cannot import name 'resolve'`

- [ ] **Step 3: Implement**

```python
# worker/app/cineprompt/resolve.py
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
```

```python
# worker/app/cineprompt/__init__.py
"""CinePrompt engine: structured field-state to cinematography prompt.

Public surface:
    build_prompt(state)      -> list[str]
    resolve_state(state)     -> list[dict]
    fill_from_scene(...)     -> dict   (added in Task 6)
"""
from .resolve import build_prompt, resolve_state, strip_ms

__all__ = ["build_prompt", "resolve_state", "strip_ms"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_resolve.py -q`
Expected: PASS, 8 tests

- [ ] **Step 5: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/cineprompt/resolve.py worker/app/cineprompt/__init__.py worker/tests/test_cineprompt_resolve.py
git commit -m "feat(cineprompt): mode resolution and multi-shot inheritance"
```

---

### Task 6: Fill pipeline with snap-to-enum

**Files:**
- Create: `worker/app/cineprompt/fill.py`
- Modify: `worker/app/cineprompt/__init__.py`
- Test: `worker/tests/test_cineprompt_fill.py`

**Interfaces:**
- Consumes: `vocab.values_for`, `vocab.is_free_text`, `compat.prune`
- Produces: `snap(field: str, value: str) -> str | None`, `snap_fields(raw: dict) -> tuple[dict, list[dict]]`, `async fill_from_scene(description: str, mode: str = "single", level: str = "complex", locked: dict | None = None, escalate: bool = True) -> dict`, `FillError`

`fill_from_scene` is **async**, because both providers are: `localllm.py` uses `httpx.AsyncClient` and `scene3d/author.py:231` is `async def _call_model`. `pyproject.toml` sets `asyncio_mode = "auto"`, so async tests need no decorator, though the repo marks them `@pytest.mark.asyncio` by convention.

The model is never called in tests. Patch `fill._generate`, never a backend. It is named `_generate` rather than `_call_model` to avoid confusion with `scene3d.author._call_model`, which it delegates to.

- [ ] **Step 1: Write the failing test**

```python
# worker/tests/test_cineprompt_fill.py
import pytest

from app.cineprompt import fill


def test_snap_exact():
    assert fill.snap("camera_body", "shot on ARRI Alexa 65") == "shot on ARRI Alexa 65"


def test_snap_casefold():
    assert fill.snap("camera_body", "SHOT ON ARRI ALEXA 65") == "shot on ARRI Alexa 65"


def test_snap_containment():
    assert fill.snap("camera_body", "ARRI Alexa 65") == "shot on ARRI Alexa 65"


def test_snap_fuzzy():
    assert fill.snap("camera_body", "shot on ARI Alexa 65") == "shot on ARRI Alexa 65"


def test_snap_rejects_unrelated():
    assert fill.snap("camera_body", "a purple giraffe") is None


def test_snap_passes_free_text_through():
    assert fill.snap("dialogue", "We should go.") == "We should go."


def test_snap_fields_reports_near_misses():
    kept, misses = fill.snap_fields({"camera_body": "a purple giraffe", "genre": "action"})
    assert kept == {"genre": "action"}
    assert misses[0]["field"] == "camera_body"


def test_blocked_fields_dropped():
    kept, _ = fill.snap_fields({"sound_mode": "voice-over narration", "genre": "action"})
    assert "sound_mode" not in kept


def test_unknown_fields_dropped():
    kept, _ = fill.snap_fields({"not_a_field": "x", "genre": "action"})
    assert kept == {"genre": "action"}


GOOD_RAW = {"genre": "action", "mood": "nostalgic", "pacing": "slow motion",
            "camera_body": "ARRI Alexa 65", "dof": "deep focus",
            "env_time": "dawn, first light", "movement": "pan"}


def _stub(monkeypatch, payload):
    """Replace the model call with a coroutine returning `payload`."""
    async def fake(*args, **kwargs):
        return payload
    monkeypatch.setattr(fill, "_generate", fake)


@pytest.mark.asyncio
async def test_gate_rejects_sparse_fill_despite_perfect_survival(monkeypatch):
    """Two fields that both snap cleanly score 100% on the ratio and must still fail.

    This is the MIN_SCRIPT_FRAMES lesson: a proportion guard cannot see a
    truncated input, because the little that arrived was all valid.
    """
    _stub(monkeypatch, {"genre": "action", "mood": "nostalgic"})
    with pytest.raises(fill.FillError, match="too few fields"):
        await fill.fill_from_scene("a long detailed scene description", escalate=False)


@pytest.mark.asyncio
async def test_gate_rejects_low_survival(monkeypatch):
    _stub(monkeypatch, {"genre": "action", "mood": "nostalgic", "pacing": "slow motion",
                        "camera_body": "purple giraffe", "film_stock": "invented stock",
                        "lens_brand": "nonsense", "weather": "not a weather", "dof": "made up"})
    with pytest.raises(fill.FillError, match="survival"):
        await fill.fill_from_scene("a scene", escalate=False)


@pytest.mark.asyncio
async def test_accepts_good_fill(monkeypatch):
    _stub(monkeypatch, GOOD_RAW)
    out = await fill.fill_from_scene("a scene")
    assert out["camera_body"] == "shot on ARRI Alexa 65"
    assert len(out) >= fill.MIN_FILLED_FIELDS


@pytest.mark.asyncio
async def test_locked_fields_survive(monkeypatch):
    _stub(monkeypatch, GOOD_RAW)
    out = await fill.fill_from_scene("a scene", locked={"camera_body": "shot on RED V-Raptor"})
    assert out["camera_body"] == "shot on RED V-Raptor"


@pytest.mark.asyncio
async def test_never_fabricates_on_total_failure(monkeypatch):
    _stub(monkeypatch, None)
    with pytest.raises(fill.FillError):
        await fill.fill_from_scene("a scene", escalate=False)


@pytest.mark.asyncio
async def test_compat_pruned_after_snapping(monkeypatch):
    _stub(monkeypatch, dict(GOOD_RAW, format="VHS"))
    out = await fill.fill_from_scene("a scene")
    assert "camera_body" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_fill.py -q`
Expected: FAIL, `ImportError: cannot import name 'fill'`

- [ ] **Step 3: Implement**

```python
# worker/app/cineprompt/fill.py
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
    Wired for real in Task 7. Named `_generate` rather than `_call_model` so it
    is not confused with `scene3d.author._call_model`, which it delegates to.
    """
    raise NotImplementedError("wired in Task 7")


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

        if len(kept) < MIN_FILLED_FIELDS:
            last_error = f"too few fields: {len(kept)} < {MIN_FILLED_FIELDS}"
            continue
        if survival < MIN_SNAP_SURVIVAL:
            last_error = f"snap survival {survival:.2f} < {MIN_SNAP_SURVIVAL}"
            continue

        result = compat.prune(kept)
        if locked:
            result.update(locked)
        return result

    raise FillError(f"scene-to-prompt failed: {last_error}")
```

```python
# worker/app/cineprompt/__init__.py
"""CinePrompt engine: structured field-state to cinematography prompt.

Public surface:
    build_prompt(state)   -> list[str]
    resolve_state(state)  -> list[dict]
    fill_from_scene(...)  -> dict
"""
from .fill import FillError, fill_from_scene
from .resolve import build_prompt, resolve_state, strip_ms

__all__ = ["build_prompt", "resolve_state", "strip_ms", "fill_from_scene", "FillError"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_fill.py -q`
Expected: PASS, 15 tests

- [ ] **Step 5: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/cineprompt/fill.py worker/app/cineprompt/__init__.py worker/tests/test_cineprompt_fill.py
git commit -m "feat(cineprompt): fill pipeline with snap-to-enum and dual acceptance gate"
```

---

### Task 7: Wire `_generate` to the real providers

**Files:**
- Create: `worker/app/cineprompt/prompts.py`
- Modify: `worker/app/cineprompt/fill.py` (replace `_generate`)
- Modify: `worker/app/localllm.py` (append `ask_local`)
- Test: `worker/tests/test_cineprompt_prompts.py`

**Interfaces:**
- Consumes: `vocab.values_for`, `vocab.all_fields`
- Produces: `catalogue_for(mode: str, level: str) -> str`, `system_prompt(mode: str, level: str) -> str`

Mirrors `archetypes.py:475 catalogue_for_prompt()`. Only in-scope fields are sent, with their full enums, so the model sees the exact strings it must choose from.

- [ ] **Step 1: Write the failing test**

```python
# worker/tests/test_cineprompt_prompts.py
from app.cineprompt import prompts


def test_catalogue_lists_fields_with_values():
    text = prompts.catalogue_for("single", "simple")
    assert "camera_body:" in text
    assert "shot on ARRI Alexa 65" in text


def test_simple_level_is_smaller_than_complex():
    assert len(prompts.catalogue_for("single", "simple")) < len(prompts.catalogue_for("single", "complex"))


def test_blocked_fields_never_offered():
    text = prompts.catalogue_for("single", "complex")
    assert "sound_mode:" not in text
    assert "delivery_style:" not in text


def test_system_prompt_demands_json_only():
    text = prompts.system_prompt("single", "simple")
    assert "JSON" in text
    assert "exactly" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_prompts.py -q`
Expected: FAIL, `ImportError: cannot import name 'prompts'`

- [ ] **Step 3: Implement**

```python
# worker/app/cineprompt/prompts.py
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
```

`scene3d/author.py:231` already exposes `async def _call_model(system, user) -> str` with
provider dispatch, so the cloud path reuses it directly. `localllm.py` has no generic
helper (its `_ask` hardcodes the archetype system prompt), so add one there rather than
inlining an HTTP call in the engine.

Append to `worker/app/localllm.py`:

```python
async def ask_local(system: str, user: str, *, num_predict: int = 1200) -> str | None:
    """One generic Ollama round trip. Returns raw text, or None on any failure.

    OLLAMA_URL is 127.0.0.1, never `localhost`: Windows resolves ::1 first and
    Ollama binds IPv4 only, so the hostname form fails every connection attempt.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": user,
        "system": system,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.3, "num_predict": num_predict},
    }
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            response.raise_for_status()
            return response.json().get("response", "")
    except Exception as exc:
        log.warning("ollama_unavailable", error=str(exc)[:160])
        return None
```

Then replace `_generate` in `fill.py`:

```python
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
```

Note the import of `prompts` is deferred inside the function: `prompts` imports
`BLOCKED_FIELDS` from `fill`, so a module-level import would be circular.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_cineprompt_prompts.py tests/test_cineprompt_fill.py -q`
Expected: PASS, 19 tests. The fill tests still patch `_generate`, so nothing reaches a network.

- [ ] **Step 5: Run the whole engine suite**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q -k cineprompt`
Expected: PASS, 295 tests

- [ ] **Step 6: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/cineprompt/prompts.py worker/app/cineprompt/fill.py worker/tests/test_cineprompt_prompts.py
git commit -m "feat(cineprompt): vocabulary catalogue prompt and provider wiring"
git push
```

---

## Verification

After Task 7:

```powershell
cd "F:\Content Creation Project\worker"
..\.venv\Scripts\python.exe -m pytest tests -q -k cineprompt
```

295 passing, no network access, no node, no Ollama.

Manual smoke, engine only. Write `worker/scripts/smoke_cineprompt.py`:

```python
from app.cineprompt import build_prompt

print(build_prompt({"mode": "single", "model": "veo", "fields": {
    "media_type": "cinematic", "genre": ["thriller"],
    "char_label": "a woman", "age_range": "in their 30s",
    "shot_type": "wide shot", "movement": "pan",
    "camera_body": "shot on ARRI Alexa 65",
    "color_science": "ARRI LogC4 flat log footage, ungraded",
    "setting": "a cramped office", "env_time": "dawn, first light",
}})[0])
```

```powershell
cd "F:\Content Creation Project\worker"
..\.venv\Scripts\python.exe scripts\smoke_cineprompt.py
```

Expect one sentence-cased paragraph, cinematography first (Veo's order), with the manufacturer appearing once rather than twice.

## Not in this plan

Studio frontend, BYOK provider adapters, share links, subject library, Stripe tiers, and `FRAME_BACKEND=cineprompt` pipeline integration. The engine's public surface is the seam those will call.
