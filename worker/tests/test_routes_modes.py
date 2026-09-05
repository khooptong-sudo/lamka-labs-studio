"""Format toggle -> frame backend. No DB, no network."""

import pytest

from app.routes import MODE_BACKENDS, backend_for_mode


def test_film_selects_the_three_backend():
    assert backend_for_mode("film") == "three"


def test_cinematic_selects_the_image_led_backend():
    """Cinematic shorts must not silently fall through to a 2D card renderer."""
    assert backend_for_mode("cinematic") == "cinematic"


def test_short_selects_the_image_led_cinematic_backend():
    """A Short is the premium portrait format, never a 2D fallback."""
    assert backend_for_mode("short") == "cinematic"


def test_absent_mode_falls_through_too():
    assert backend_for_mode(None) is None


@pytest.mark.parametrize("bad", ["cinema", "3d", "Film", ""])
def test_unknown_mode_raises_rather_than_defaulting(bad):
    """Defaulting a typo would ship a portrait 2D video under a film's headline."""
    with pytest.raises(ValueError, match="unknown mode"):
        backend_for_mode(bad)


def test_every_declared_mode_is_resolvable():
    assert all(backend_for_mode(mode) == MODE_BACKENDS[mode] for mode in MODE_BACKENDS)


def test_documentary_selects_the_image_led_cinematic_backend():
    assert backend_for_mode("documentary") == "cinematic"
