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
