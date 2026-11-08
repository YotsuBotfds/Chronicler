"""Chunk scheduling for ``run_python_oracle_checks.py --jobs``: order, prefix and stop rules.

Threads only, coordinated by events rather than sleeps. No child process is started.
"""
import importlib.util
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WAIT = 10  # seconds; a hang means the scheduler broke its contract


@pytest.fixture(scope="module")
def scheduler():
    spec = importlib.util.spec_from_file_location("chunk_scheduler_under_test",
                                                  ROOT / "scripts/testing/chunk_scheduler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def recorder(fail=(), gates=None):
    """A ``run`` that records starts, waits on its gate (if any) and fails listed items."""
    started, lock = [], threading.Lock()
    def run(item):
        with lock:
            started.append(item)
        gate = (gates or {}).get(item)
        if gate is not None:
            assert gate.wait(WAIT), f"item {item} was never released"
        return {"item": item, "passed": item not in fail}
    return run, started


def test_one_job_is_serial_and_stops_at_the_first_failure(scheduler):
    run, started = recorder(fail={2})
    results = scheduler.run_in_order(range(6), run, lambda r: r["passed"], jobs=1)
    assert [r["item"] for r in results] == [0, 1, 2] and started == [0, 1, 2]


def test_results_keep_item_order_when_items_finish_out_of_order(scheduler):
    last_done = threading.Event()
    def run(item):
        if item == 0:
            assert last_done.wait(WAIT)
        if item == 2:
            last_done.set()
        return {"item": item, "passed": True}
    results = scheduler.run_in_order(range(3), run, lambda r: r["passed"], jobs=3)
    assert [r["item"] for r in results] == [0, 1, 2]


def test_nothing_new_starts_after_a_failure_and_running_items_finish(scheduler):
    release = threading.Event()
    run, started = recorder(fail={1}, gates={0: release, 2: release})
    def passed(result):
        if not result["passed"]:
            release.set()  # the slow items may finish only once the failure is recorded
        return result["passed"]
    results = scheduler.run_in_order(range(10), run, passed, jobs=3)
    assert sorted(started) == [0, 1, 2]
    assert [r["item"] for r in results] == [0, 1, 2]  # a prefix, in order


def test_every_item_runs_when_all_pass(scheduler):
    run, started = recorder()
    results = scheduler.run_in_order(list("abcdefg"), run, lambda r: r["passed"], jobs=4)
    assert [r["item"] for r in results] == list("abcdefg") and sorted(started) == list("abcdefg")
    assert scheduler.run_in_order([], run, lambda r: True, jobs=2) == []


@pytest.mark.parametrize("jobs", [0, -1, True, 1.5])
def test_jobs_must_be_a_positive_integer(scheduler, jobs):
    with pytest.raises(ValueError):
        scheduler.run_in_order([1], lambda item: item, lambda result: True, jobs=jobs)


def test_runner_uses_the_scheduler_only_for_more_than_one_job():
    source = (ROOT / "scripts/run_python_oracle_checks.py").read_text(encoding="utf-8")
    assert 'parser.add_argument("--jobs", type=int, default=1' in source
    serial = source.index("if args.jobs == 1:")
    assert serial < source.index("from chunk_scheduler import run_in_order")
    assert "report[\"jobs\"] = args.jobs" in source  # serial receipts keep their keys
