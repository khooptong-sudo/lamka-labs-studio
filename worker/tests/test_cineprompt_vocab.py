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


def test_values_for_has_no_duplicates_for_any_field():
    """base.json carries at least one internal duplicate ('pouring, liquid
    flowing' appears twice under movement_type) — a React key collision in
    the GUI picker surfaced this. values_for must dedupe regardless of
    which source (base, overlay, or both) repeats a value."""
    for field in vocab.all_fields():
        values = vocab.values_for(field)
        assert len(values) == len(set(values)), f"{field} has duplicate values"


def test_returned_list_cannot_corrupt_cache():
    got = vocab.values_for("camera_body")
    got.append("not a real value")
    got.sort()
    assert vocab.values_for("camera_body") != got
    assert "not a real value" not in vocab.values_for("camera_body")
