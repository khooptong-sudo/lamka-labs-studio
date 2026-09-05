import pytest

from app.channels import BASE_BLOCKLIST
from scripts.seed_channels import build_channels_payload

VOICE_PROFILES = {
    "activeProfileId": "adult_male",
    "profiles": [
        {
            "id": "adult_male",
            "name": "Adult Casual Male",
            "prompt": "You are a casual, humorous, and informative adult male.",
            "blocklist": ["buy", "sell", "guaranteed returns"],
        },
        {
            "id": "baby",
            "name": "Baby",
            "prompt": "You are a humorous, highly intelligent baby.",
            "blocklist": ["buy", "sell"],
        },
    ],
}


def test_finance_channel_takes_the_active_profile():
    payload = build_channels_payload(VOICE_PROFILES)
    assert payload["finance"]["voice_key"] == "adult_male"
    assert payload["finance"]["script_prompt"] == VOICE_PROFILES["profiles"][0]["prompt"]


def test_base_terms_are_not_duplicated_into_extras():
    payload = build_channels_payload(VOICE_PROFILES)
    extras = payload["finance"]["extra_blocklist"]
    for term in BASE_BLOCKLIST:
        assert term not in extras


def test_non_base_terms_are_preserved_as_extras():
    payload = build_channels_payload(VOICE_PROFILES)
    assert "guaranteed returns" in payload["finance"]["extra_blocklist"]


def test_kids_channel_is_created():
    payload = build_channels_payload(VOICE_PROFILES)
    assert payload["kids"]["voice_key"] == "baby"
    assert payload["kids"]["display_name"]


def test_missing_voice_profiles_raises():
    with pytest.raises(ValueError):
        build_channels_payload(None)


def test_unrecognized_voice_id_raises():
    bad_profiles = {
        "activeProfileId": "custom_voice",
        "profiles": [
            {
                "id": "custom_voice",
                "name": "Custom",
                "prompt": "You are a custom voice.",
                "blocklist": [],
            }
        ],
    }
    with pytest.raises(ValueError, match="custom_voice"):
        build_channels_payload(bad_profiles)


def test_builtin_channels_use_known_voices():
    from app.youtube import VOICE_MAP
    from scripts.seed_channels import BUILT_IN_CHANNELS

    assert set(BUILT_IN_CHANNELS) == {"history", "science", "mystery"}
    for entry in BUILT_IN_CHANNELS.values():
        assert entry["voice_key"] in VOICE_MAP
        assert entry["display_name"].strip()
        assert entry["script_prompt"].strip()


def test_builtin_extras_exclude_base_terms():
    from app.channels import BASE_BLOCKLIST
    from scripts.seed_channels import BUILT_IN_CHANNELS

    for entry in BUILT_IN_CHANNELS.values():
        for term in BASE_BLOCKLIST:
            assert term not in entry["extra_blocklist"]


def test_ensure_adds_missing_and_never_touches_present():
    from scripts.seed_channels import ensure_builtin_channels

    existing = {"finance": {"display_name": "Finance", "voice_key": "adult_male",
                            "script_prompt": "tuned", "extra_blocklist": ["x"]}}
    merged = ensure_builtin_channels(existing)
    assert merged["finance"] == existing["finance"]
    assert set(merged) == {"finance", "history", "science", "mystery"}
    assert list(merged) == ["finance", "history", "science", "mystery"]


def test_ensure_on_empty_returns_builtins_only():
    from scripts.seed_channels import BUILT_IN_CHANNELS, ensure_builtin_channels

    assert ensure_builtin_channels(None) == BUILT_IN_CHANNELS
    assert ensure_builtin_channels({}) == BUILT_IN_CHANNELS


def test_ensure_rejects_a_bad_builtin_voice(monkeypatch):
    import scripts.seed_channels as seed

    monkeypatch.setitem(seed.BUILT_IN_CHANNELS, "broken",
                        {"display_name": "B", "voice_key": "nope",
                         "script_prompt": "p", "extra_blocklist": []})
    try:
        with pytest.raises(ValueError, match="nope"):
            seed.ensure_builtin_channels({})
    finally:
        del seed.BUILT_IN_CHANNELS["broken"]
