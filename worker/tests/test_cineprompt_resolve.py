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
    assert "Pan camera movement" in motion


def test_compat_applies_before_assembly():
    state = {"mode": "single", "fields": {"format": "VHS", "camera_body": "shot on ARRI Alexa 65"}}
    assert "ARRI" not in resolve.build_prompt(state)[0]


def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown mode"):
        resolve.resolve_state({"mode": "nonsense", "fields": {}})


def test_global_format_prunes_shot_fields():
    """Global format should prune incompatible fields from shot, even after merge."""
    state = {"mode": "multi",
             "fields": {"ms_format": "VHS"},
             "shots": [{"fields": {"camera_body": "shot on ARRI Alexa 65"}}]}
    out = resolve.resolve_state(state)
    assert "camera_body" not in out[0]
    assert out[0] == {"format": "VHS"}


def test_build_prompt_handles_two_value_selection_for_every_pickable_field():
    """Every field the vocabulary picker can multi-select must survive a
    two-value selection without raising and without leaking Python list
    syntax into the prompt. Regression test for the final-review finding:
    ~23 merge-rule fields raised TypeError, `movement` silently emitted
    "['static', 'pan'] camera movement." with no error at all.
    """
    from app.cineprompt import build_prompt, prompts, vocab

    in_scope = prompts.fields_in_scope("single", "complex")
    for field in in_scope:
        values = vocab.values_for(field)
        if len(values) < 2:
            continue  # free-text or single-valued fields aren't multi-select targets
        result = build_prompt({"mode": "single", "model": "universal", "fields": {field: values[:2]}})
        text = result[0]
        # Detect Python list-repr artifacts specifically (e.g. "['static', 'pan']"),
        # not any apostrophe — some vocab values are legitimate contractions
        # (e.g. art_setting's "an artist's studio").
        assert "[" not in text and "', '" not in text, f"{field} leaked list syntax: {text!r}"


def test_shot_format_prunes_global_fields():
    """Shot format should prune incompatible global fields, even after merge."""
    state = {"mode": "multi",
             "fields": {"ms_camera_body": "shot on RED V-Raptor"},
             "shots": [{"fields": {"format": "VHS"}}]}
    out = resolve.resolve_state(state)
    assert "camera_body" not in out[0]
    assert out[0] == {"format": "VHS"}
