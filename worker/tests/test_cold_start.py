"""Cold-start smoke test — Layer 1 (Part II §5.5).

Mocks feed responses via respx, runs ingest.run_all_sources() against the
local Docker DB, asserts the full chain works end-to-end:
  - items inserted
  - all embedded (inline, §3.6)
  - stories created
  - zero orphans
  - idempotent on re-run (the §1.1 exact-dupe bar)
  - /stats reflects reality

The mock embedder (FCE_EMBED_MOCK=true) returns a deterministic vector per
input string so reruns are stable (§5.5 determinism requirement).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import respx

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "feeds"


def _fresh_rfc822(hours_ago: float) -> str:
    """RFC 822 date N hours before now — see _freshen_fixture_dates."""
    return format_datetime(datetime.now(timezone.utc) - timedelta(hours=hours_ago))


def _fresh_iso(hours_ago: float) -> str:
    """ISO 8601 UTC date N hours before now — see _freshen_fixture_dates."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _freshen_fixture_dates(rss_xml: str, edgar_atom: str) -> tuple[str, str]:
    """Rewrite the cassette fixtures' recorded dates to be recent.

    The fixtures are a "recorded cassette" with fixed 2025 dates for
    determinism of everything except time. `_is_fresh_news_item`
    (app/ingest.py) rejects anything older than `fresh_news_hours` (48h
    default) relative to wall-clock now, so a fixed date inevitably goes
    stale as real time passes — this happened, and is why this test started
    failing. Substituting in dates relative to "now" at test time keeps the
    cassette's content, shape, and ordering fixed while keeping it forever
    fresh enough to pass the filter it's meant to exercise.
    """
    rss_xml = (
        rss_xml
        .replace("Tue, 22 Jul 2025 09:30:00 +0530", _fresh_rfc822(1))
        .replace("Wed, 08 Oct 2025 10:00:00 +0530", _fresh_rfc822(2))
        .replace("Mon, 14 Jul 2025 06:00:00 +0530", _fresh_rfc822(3))
    )
    edgar_atom = (
        edgar_atom
        .replace("2025-07-22T14:00:00Z", _fresh_iso(1))
        .replace("2025-07-22T13:45:00Z", _fresh_iso(1))
        .replace("2025-07-22T12:10:00Z", _fresh_iso(2))
    )
    return rss_xml, edgar_atom


@pytest_asyncio.fixture
async def test_sources(db):
    """Seed two test sources (RSS + EDGAR) with URLs that respx will intercept.
    Deactivate all other (seeded production) sources so run_all_sources() only
    hits the test sources — otherwise respx blocks the real feed URLs."""
    rss_id = uuid.uuid4()
    edgar_id = uuid.uuid4()
    async with db.connection() as conn:
        # Deactivate seeded sources so the test is hermetic.
        await conn.execute("UPDATE sources SET active = false")
        await conn.execute(
            "INSERT INTO sources (id, kind, url, name, market, active, poll_minutes) "
            "VALUES (%s, 'rss', 'https://test.example/rss', 'TEST_cold_start_rss', 'IN', true, 30)",
            (rss_id,),
        )
        await conn.execute(
            "INSERT INTO sources (id, kind, url, name, market, active, poll_minutes) "
            "VALUES (%s, 'edgar', 'https://www.sec.gov/cgi-bin/browse-edgar', 'TEST_cold_start_edgar', 'US', true, 60)",
            (edgar_id,),
        )
    return {"rss": rss_id, "edgar": edgar_id}


@respx.mock
async def test_cold_start_idempotent(test_sources, db, monkeypatch):
    """The §5.5 Layer 1 acceptance test."""
    # Mock the RSS feed response.
    rss_xml = (FIXTURES / "etmarkets.xml").read_text(encoding="utf-8")
    edgar_atom = (FIXTURES / "edgar.atom").read_text(encoding="utf-8")
    rss_xml, edgar_atom = _freshen_fixture_dates(rss_xml, edgar_atom)
    respx.get("https://test.example/rss").mock(
        return_value=httpx.Response(200, content=rss_xml.encode("utf-8"))
    )
    # Mock the EDGAR Atom feed response.
    respx.get(url__regex=r"https://www\.sec\.gov/cgi-bin/browse-edgar.*").mock(
        return_value=httpx.Response(200, content=edgar_atom.encode("utf-8"))
    )

    # Ensure mock embedder is on (deterministic).
    monkeypatch.setenv("FCE_EMBED_MOCK", "true")
    from app.settings import get_settings
    get_settings.cache_clear()
    from app.embed import clear_mock_cache
    clear_mock_cache()

    from app.ingest import run_all_sources

    # ---- First ingest cycle ----
    summaries = await run_all_sources()
    assert len(summaries) == 2  # rss + edgar

    # Items inserted + embedded (inline at poll tail, §3.6).
    from app.db import _fetchval

    async with db.connection() as conn:
        item_count = await _fetchval(conn, "SELECT count(*) FROM items")
        unembedded = await _fetchval(
            conn, "SELECT count(*) FROM items WHERE embedding IS NULL"
        )

    assert item_count > 0, "no items inserted on first cycle"
    # All items must be embedded (inline at poll tail, §3.6).
    assert unembedded == 0, f"{unembedded} items have no embedding — inline embed failed"

    # Run clustering (separate job in production, §3.7) → creates stories.
    from app.cluster import cluster_new_items

    await cluster_new_items()

    async with db.connection() as conn:
        story_count = await _fetchval(conn, "SELECT count(*) FROM stories")
    assert story_count > 0, "no stories created after clustering"

    items_v1 = item_count
    stories_v1 = story_count

    # ---- Idempotency: second ingest cycle must insert ZERO new items ----
    clear_mock_cache()
    summaries_2 = await run_all_sources()
    async with db.connection() as conn:
        item_count_2 = await _fetchval(conn, "SELECT count(*) FROM items")
        story_count_2 = await _fetchval(conn, "SELECT count(*) FROM stories")

    assert item_count_2 == items_v1, (
        f"idempotency violated: {item_count_2 - items_v1} new items on second cycle "
        "(ON CONFLICT (hash) DO NOTHING should have suppressed them)"
    )
    # Stories should not churn either.
    assert story_count_2 == stories_v1

    # ---- /stats reflects reality ----
    from app.db import stats
    s = await stats()
    assert s["items"]["total"] == items_v1
    assert s["embedding_health"] == "ok"
    # Orphans must be zero (§3.9 non-negotiable in steady state).
    assert s["items"]["orphaned"] == 0, "orphans present — story creation dropped an item"
