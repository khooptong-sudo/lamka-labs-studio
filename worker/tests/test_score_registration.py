"""score_new must obey the registry invariant (decision #22): every job under
AsyncIOExecutor is `async def`, or it fails silently at fire time."""

import inspect

import pytest

pytestmark = pytest.mark.integration


async def test_score_new_is_registered(db):
    from app.scheduler import build_job_specs

    specs = {spec.id: spec for spec in await build_job_specs()}
    assert "score_new" in specs


async def test_score_new_runs_every_ten_minutes(db):
    from app.scheduler import build_job_specs

    specs = {spec.id: spec for spec in await build_job_specs()}
    assert specs["score_new"].minutes == 10


async def test_score_new_is_a_coroutine_function(db):
    from app.scheduler import build_job_specs

    specs = {spec.id: spec for spec in await build_job_specs()}
    assert inspect.iscoroutinefunction(specs["score_new"].fn)


async def test_score_new_takes_the_advisory_lock(db):
    """Only db_health is exempt (decision #27). A second replica must not
    double-score and double-bill."""
    from app.scheduler import build_job_specs

    specs = {spec.id: spec for spec in await build_job_specs()}
    assert specs["score_new"].lock is True
