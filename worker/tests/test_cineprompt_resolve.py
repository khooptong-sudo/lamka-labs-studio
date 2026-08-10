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
