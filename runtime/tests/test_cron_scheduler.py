"""Tests for cron_scheduler.py — CronScheduler."""

from __future__ import annotations

import time

import pytest

from agency.cron_scheduler import CronScheduler


@pytest.fixture
def scheduler():
    s = CronScheduler()
    yield s
    s.stop()


def test_add_job(scheduler):
    scheduler.add_job("test_job", 60, lambda: None)
    jobs = scheduler.list_jobs()
    assert any(j["name"] == "test_job" for j in jobs)


def test_add_job_interval(scheduler):
    scheduler.add_job("interval_job", 30, lambda: None)
    jobs = {j["name"]: j for j in scheduler.list_jobs()}
    assert jobs["interval_job"]["interval_s"] == 30


def test_add_job_enabled_by_default(scheduler):
    scheduler.add_job("enabled_job", 10, lambda: None)
    jobs = {j["name"]: j for j in scheduler.list_jobs()}
    assert jobs["enabled_job"]["enabled"] is True


def test_add_job_last_run_none(scheduler):
    scheduler.add_job("new_job", 10, lambda: None)
    jobs = {j["name"]: j for j in scheduler.list_jobs()}
    assert jobs["new_job"]["last_run"] is None


def test_remove_job_returns_true(scheduler):
    scheduler.add_job("removable", 10, lambda: None)
    result = scheduler.remove_job("removable")
    assert result is True


def test_remove_job_removes_it(scheduler):
    scheduler.add_job("to_remove", 10, lambda: None)
    scheduler.remove_job("to_remove")
    jobs = scheduler.list_jobs()
    assert not any(j["name"] == "to_remove" for j in jobs)


def test_remove_nonexistent_returns_false(scheduler):
    result = scheduler.remove_job("does_not_exist")
    assert result is False


def test_list_jobs_empty(scheduler):
    assert scheduler.list_jobs() == []


def test_list_jobs_multiple(scheduler):
    scheduler.add_job("job_a", 10, lambda: None)
    scheduler.add_job("job_b", 20, lambda: None)
    scheduler.add_job("job_c", 30, lambda: None)
    jobs = scheduler.list_jobs()
    assert len(jobs) == 3


def test_run_now_executes_job(scheduler):
    results = []
    scheduler.add_job("immediate", 3600, lambda: results.append(1))
    ran = scheduler.run_now("immediate")
    assert ran is True
    assert results == [1]


def test_run_now_nonexistent_returns_false(scheduler):
    result = scheduler.run_now("ghost_job")
    assert result is False


def test_run_now_updates_last_run(scheduler):
    scheduler.add_job("timed_job", 3600, lambda: None)
    scheduler.run_now("timed_job")
    jobs = {j["name"]: j for j in scheduler.list_jobs()}
    assert jobs["timed_job"]["last_run"] is not None


def test_start_stop(scheduler):
    scheduler.add_job("bg_job", 3600, lambda: None)
    scheduler.start()
    assert scheduler._running is True
    scheduler.stop()
    assert scheduler._running is False


def test_start_idempotent(scheduler):
    scheduler.start()
    scheduler.start()  # should not raise
    assert scheduler._running is True


def test_scheduler_runs_job_automatically():
    """Verify that a short-interval job fires automatically."""
    s = CronScheduler()
    fired = []
    s.add_job("fast", 0, lambda: fired.append(1))
    s.start()
    time.sleep(0.3)
    s.stop()
    assert len(fired) >= 1


def test_overwrite_job(scheduler):
    calls = []
    scheduler.add_job("overwrite_me", 10, lambda: calls.append("old"))
    scheduler.add_job("overwrite_me", 10, lambda: calls.append("new"))
    scheduler.run_now("overwrite_me")
    assert calls == ["new"]
