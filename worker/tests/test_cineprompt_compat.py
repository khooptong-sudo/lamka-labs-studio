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
