"""audit_log keeps its contract: it appends best-effort and never raises —
not on pool-acquisition failure, not on write failure."""

from unittest.mock import AsyncMock, MagicMock, patch

from app import audit


def _pool_with(conn):
    """psycopg's pool.connection() is sync and returns an async CM."""
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    pool.connection.return_value = cm
    return pool


async def test_audit_log_never_raises_when_the_pool_fails_to_open():
    """Regression: get_pool() used to sit outside the try, so a DB outage
    propagated PoolTimeout to the caller instead of logging it."""
    with patch("app.audit.get_pool", AsyncMock(side_effect=TimeoutError("db is down"))):
        assert await audit.audit_log(
            actor="worker",
            action="probe",
            entity="x",
            entity_type="story",
        ) is None


async def test_audit_log_never_raises_when_the_insert_fails():
    conn = AsyncMock()
    conn.execute.side_effect = RuntimeError("connection lost")
    with patch("app.audit.get_pool", AsyncMock(return_value=_pool_with(conn))):
        assert await audit.audit_log(
            actor="worker",
            action="probe",
            entity="x",
            entity_type="story",
        ) is None


async def test_audit_log_writes_the_event_on_the_happy_path():
    conn = AsyncMock()
    with patch("app.audit.get_pool", AsyncMock(return_value=_pool_with(conn))) as _:
        await audit.audit_log(
            actor="worker",
            action="script_fact_check_blocked",
            entity="story-id",
            entity_type="story",
            after={"violations": []},
        )
    conn.execute.assert_awaited_once()
    sql, params = conn.execute.await_args.args
    assert "INSERT INTO audit_log" in sql
    assert params[1] == "script_fact_check_blocked"
