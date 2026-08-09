from app.cineprompt import profiles


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
    fields = {"shot_type": "wide shot", "setting": "a cramped office",
              "camera_body": "shot on ARRI Alexa 65", "music_genre": "orchestral"}
    out = profiles.render(fields, "pixverse")
    assert len(out) <= 2048
    assert out.endswith((".", "!", '"'))


def test_cap_never_returns_partial_sentence():
    fields = {f"beat_{i}": "x" * 900 for i in (1, 2, 3)}
    out = profiles.render(fields, "pixverse")
    assert len(out) <= 2048
    assert out.endswith(".")
