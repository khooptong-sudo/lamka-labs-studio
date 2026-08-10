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
