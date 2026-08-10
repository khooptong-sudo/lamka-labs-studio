from app.cineprompt import profiles, assemble


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
    # Build fields with content that genuinely exceeds pixverse limit (2048)
    fields = {f"beat_{i}": ("word " * 180).strip() for i in (1, 2, 3)}

    # Verify the fixture actually exceeds the limit before applying _cap
    raw = assemble.build_text(fields, profiles.order_for("pixverse"))
    assert len(raw) > 2048, f"Fixture should exceed limit: raw {len(raw)} chars vs 2048 limit"

    # Now apply render which will cap it
    out = profiles.render(fields, "pixverse")

    # Verify the capping actually happened: result must be shorter than raw
    assert len(out) < len(raw), "Capping should shorten the output"

    # And verify it's within limits and properly terminated
    assert len(out) <= 2048
    assert out.endswith((".", "!", '"'))


def test_cap_never_returns_partial_sentence():
    fields = {f"beat_{i}": "x" * 900 for i in (1, 2, 3)}
    out = profiles.render(fields, "pixverse")
    assert len(out) <= 2048
    assert out.endswith(".")


def test_cap_handles_single_sentence_exceeding_limit():
    # One very long segment with no sentence boundary: _cap must truncate at word boundary
    # while retaining a meaningful portion of the budget (not collapsing to a few chars)
    fields = {"dialogue": "x" * 5000}
    out = profiles.render(fields, "pixverse")
    assert out  # Non-empty
    assert len(out) <= 2048
    assert out.endswith(".")
    # The result should retain at least half the limit's budget when input is far longer
    assert len(out) >= 1024, f"Expected at least 1024 chars retained, got {len(out)}"


def test_render_applies_model_order():
    # VEO puts CINEMATOGRAPHY first, universal puts STYLE/SUBJECT first
    # Use a state with both cinematography and subject content
    fields = {
        "shot_type": "cinematic wide shot",
        "char_label": "a mysterious figure",
    }
    veo_out = profiles.render(fields, "veo")
    universal_out = profiles.render(fields, "universal")

    # Both should contain the key phrases (case-insensitive check)
    assert "cinematic wide shot" in veo_out.lower()
    assert "mysterious figure" in universal_out.lower()

    # In veo output, cinematography content should appear before subject content
    veo_shot_pos = veo_out.lower().find("cinematic wide shot")
    veo_char_pos = veo_out.lower().find("mysterious figure")
    assert veo_shot_pos < veo_char_pos, "VEO should lead with CINEMATOGRAPHY"

    # In universal output, subject (character) typically appears earlier
    # (STYLE/SUBJECT come before CINEMATOGRAPHY in universal)
    universal_char_pos = universal_out.lower().find("mysterious figure")
    universal_shot_pos = universal_out.lower().find("cinematic wide shot")
    assert universal_char_pos < universal_shot_pos, "Universal should lead with SUBJECT before CINEMATOGRAPHY"
