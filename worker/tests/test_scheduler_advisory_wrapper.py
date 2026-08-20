"""The advisory-lock wrapper must be awaitable.

Regression test for a production outage found on 2026-08-20: `register_jobs`
asserted the async invariant on `spec.fn`, then wrapped it in a plain lambda.
A lambda is not a coroutine function, so APScheduler's AsyncIOExecutor never
awaited what it returned — every advisory-locked job silently did nothing for
roughly three weeks while `/health` still reported `scheduler_running: true`.

The pre-existing tests could not catch this: they asserted on `spec.fn`, which
is not the callable the scheduler ends up holding. These tests assert on the
registered callable instead.

This is deploy bug D5 recurring one layer up, so it is worth a dedicated file.
"""

from __future__ import annotations

import inspect

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.scheduler import JobSpec, register_jobs


async def _noop() -> None:
    return None


def _register(*specs: JobSpec) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    register_jobs(scheduler, list(specs))
    return scheduler


def test_locked_job_registers_a_coroutine_function():
    """The bug: this registered a lambda and the job never ran."""
    scheduler = _register(JobSpec(id="locked", minutes=15, fn=_noop))
    registered = scheduler.get_job("locked").func
    assert inspect.iscoroutinefunction(registered), (
        f"locked job registered {registered!r}, which AsyncIOExecutor will "
        f"never await"
    )


def test_lock_exempt_job_registers_a_coroutine_function():
    scheduler = _register(JobSpec(id="exempt", minutes=5, fn=_noop, lock=False))
    assert inspect.iscoroutinefunction(scheduler.get_job("exempt").func)


def test_every_registered_job_is_awaitable_regardless_of_lock():
    scheduler = _register(
        JobSpec(id="a", minutes=15, fn=_noop),
        JobSpec(id="b", minutes=30, fn=_noop),
        JobSpec(id="c", minutes=5, fn=_noop, lock=False),
    )
    for job in scheduler.get_jobs():
        assert inspect.iscoroutinefunction(job.func), f"{job.id} is not awaitable"


def test_each_locked_job_binds_its_own_spec():
    """Closure-in-a-loop check: late binding would make every wrapper run the
    last spec's job, so all locked jobs would take the same advisory lock and
    all but one would be skipped."""
    scheduler = _register(
        JobSpec(id="first", minutes=15, fn=_noop),
        JobSpec(id="second", minutes=30, fn=_noop),
    )
    bound = {
        job.id: inspect.signature(job.func).parameters["s"].default.id
        for job in scheduler.get_jobs()
    }
    assert bound == {"first": "first", "second": "second"}
