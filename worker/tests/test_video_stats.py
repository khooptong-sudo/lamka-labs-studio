"""Retention loop: ID parsing, multiplier math. No network, no DB."""


def test_extract_video_id_accepts_urls_and_bare_ids():
    from app.video_stats import extract_video_id

    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("not a url at all!!") is None
    assert extract_video_id("") is None


def test_multipliers_clamp_and_require_minimums():
    from app.video_stats import compute_multipliers

    rows = [
        {"archetype": "explainer", "views": 1000},
        {"archetype": "explainer", "views": 2000},
        {"archetype": "explainer", "views": 3000},
        {"archetype": "glossary_card", "views": 100},
    ]
    mults = compute_multipliers(rows, min_videos=3)
    assert mults["explainer"] == 1.3  # 2000 avg vs 1525 global → clamped
    assert mults["glossary_card"] == 1.0  # too few videos stays neutral


def test_multipliers_empty_is_neutral():
    from app.video_stats import compute_multipliers

    assert compute_multipliers([]) == {}


async def test_stats_job_logs_and_skips_without_credentials(monkeypatch, caplog):
    from unittest.mock import AsyncMock

    from app import video_stats

    monkeypatch.setattr(
        video_stats, "get_youtube_analytics",
        AsyncMock(side_effect=RuntimeError("YouTube OAuth credentials are missing")),
    )
    written = []
    monkeypatch.setattr(video_stats, "upsert_video_stats", AsyncMock(side_effect=lambda *a: written.append(a)))
    with caplog.at_level("ERROR"):
        await video_stats.video_stats_job()
    assert written == []
    assert any("credentials" in r.message.lower() for r in caplog.records)
