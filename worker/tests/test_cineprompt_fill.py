import pytest

from app.cineprompt import fill


def test_snap_exact():
    assert fill.snap("camera_body", "shot on ARRI Alexa 65") == "shot on ARRI Alexa 65"


def test_snap_casefold():
    assert fill.snap("camera_body", "SHOT ON ARRI ALEXA 65") == "shot on ARRI Alexa 65"


def test_snap_containment():
    assert fill.snap("camera_body", "ARRI Alexa 65") == "shot on ARRI Alexa 65"


def test_snap_fuzzy():
    assert fill.snap("camera_body", "shot on ARI Alexa 65") == "shot on ARRI Alexa 65"


def test_snap_rejects_unrelated():
    assert fill.snap("camera_body", "a purple giraffe") is None


def test_snap_passes_free_text_through():
    assert fill.snap("dialogue", "We should go.") == "We should go."


def test_snap_fields_reports_near_misses():
    kept, misses = fill.snap_fields({"camera_body": "a purple giraffe", "genre": "action"})
    assert kept == {"genre": "action"}
    assert misses[0]["field"] == "camera_body"


def test_blocked_fields_dropped():
    kept, _ = fill.snap_fields({"sound_mode": "voice-over narration", "genre": "action"})
    assert "sound_mode" not in kept


def test_unknown_fields_dropped():
    kept, _ = fill.snap_fields({"not_a_field": "x", "genre": "action"})
    assert kept == {"genre": "action"}


GOOD_RAW = {"genre": "action", "mood": "nostalgic", "pacing": "slow motion",
            "camera_body": "ARRI Alexa 65", "dof": "deep focus",
            "env_time": "dawn, first light", "movement": "pan"}


def _stub(monkeypatch, payload):
    """Replace the model call with a coroutine returning `payload`."""
    async def fake(*args, **kwargs):
        return payload
    monkeypatch.setattr(fill, "_generate", fake)


@pytest.mark.asyncio
async def test_gate_rejects_sparse_fill_despite_perfect_survival(monkeypatch):
    """Two fields that both snap cleanly score 100% on the ratio and must still fail.

    This is the MIN_SCRIPT_FRAMES lesson: a proportion guard cannot see a
    truncated input, because the little that arrived was all valid.
    """
    _stub(monkeypatch, {"genre": "action", "mood": "nostalgic"})
    with pytest.raises(fill.FillError, match="too few fields"):
        await fill.fill_from_scene("a long detailed scene description", escalate=False)


@pytest.mark.asyncio
async def test_gate_rejects_low_survival(monkeypatch):
    _stub(monkeypatch, {"genre": "action", "mood": "nostalgic", "pacing": "slow motion",
                        "camera_body": "purple giraffe", "film_stock": "invented stock",
                        "lens_brand": "nonsense", "weather": "not a weather", "dof": "made up"})
    with pytest.raises(fill.FillError, match="survival"):
        await fill.fill_from_scene("a scene", escalate=False)


@pytest.mark.asyncio
async def test_accepts_good_fill(monkeypatch):
    _stub(monkeypatch, GOOD_RAW)
    out = await fill.fill_from_scene("a scene")
    assert out["camera_body"] == "shot on ARRI Alexa 65"
    assert len(out) >= fill.MIN_FILLED_FIELDS


@pytest.mark.asyncio
async def test_locked_fields_survive(monkeypatch):
    _stub(monkeypatch, GOOD_RAW)
    out = await fill.fill_from_scene("a scene", locked={"camera_body": "shot on RED V-Raptor"})
    assert out["camera_body"] == "shot on RED V-Raptor"


@pytest.mark.asyncio
async def test_never_fabricates_on_total_failure(monkeypatch):
    _stub(monkeypatch, None)
    with pytest.raises(fill.FillError):
        await fill.fill_from_scene("a scene", escalate=False)


@pytest.mark.asyncio
async def test_compat_pruned_after_snapping(monkeypatch):
    _stub(monkeypatch, dict(GOOD_RAW, format="VHS"))
    out = await fill.fill_from_scene("a scene")
    assert "camera_body" not in out
