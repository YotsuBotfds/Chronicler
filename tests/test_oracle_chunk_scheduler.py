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


def test_an_interrupt_publishes_finished_and_running_items_then_propagates(scheduler, monkeypatch):
    """Ctrl-C at the second wait: the first result and the items still running are kept."""
    real_wait, calls = scheduler.wait, []
    release = threading.Event()
    def interrupting_wait(futures, return_when):
        calls.append(1)
        if len(calls) == 2:
            release.set()  # let the running items finish while the executor unwinds
            raise KeyboardInterrupt
        return real_wait(futures, return_when=return_when)
    monkeypatch.setattr(scheduler, "wait", interrupting_wait)
    run, started = recorder(gates={1: release, 2: release})
    published = {}
    with pytest.raises(KeyboardInterrupt):
        scheduler.run_in_order(range(8), run, lambda r: r["passed"], jobs=2, results=published)
    assert 0 in published and sorted(published) == sorted(started)  # every started item is kept
    assert sorted(published) == list(range(len(published)))  # still a prefix
    assert all(r["passed"] for r in published.values())


# The real runner, executed in process: child processes are replaced and the
# offline guard is never entered, so these stay inside the bounded lane's rules.
import ast
import json
import runpy
import subprocess
import sys
import types

RUNNER = ROOT / "scripts/run_python_oracle_checks.py"


def chunk_names():
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) == "CHUNKS" for t in n.targets))
    return list(ast.literal_eval(node.value))


def fake_lane(monkeypatch, out, argv, bad_guard=()):
    def fake_run(command, cwd=None, env=None, stdout=None, stderr=None, timeout=None):
        name = Path(command[command.index("--basetemp") + 1]).name
        guard = Path(env["CHRONICLER_OFFLINE_GUARD_REPORT"])
        guard.write_text("{not json" if name in bad_guard else
                         json.dumps({"state": "PASS", "test_reports": {"passed": 1}}), encoding="utf-8")
        return types.SimpleNamespace(returncode=0, stdout=f"fake {name}\n".encode())
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: b"0" * 40 + b"\n")
    monkeypatch.setattr(sys, "argv", [str(RUNNER), "--output-dir", str(out), *argv])
    monkeypatch.setattr(sys, "path", list(sys.path))


def run_runner():
    runpy.run_path(str(RUNNER), run_name="__main__")


def receipt(out):
    return json.loads((out / "receipt.json").read_text(encoding="utf-8"))


def test_runner_receipts_serial_and_parallel(monkeypatch, tmp_path, capsys):
    names = chunk_names()
    fake_lane(monkeypatch, tmp_path / "serial", [])
    with pytest.raises(SystemExit) as stop:
        run_runner()
    serial = receipt(tmp_path / "serial")
    assert stop.value.code == 0 and serial["passed"] and "jobs" not in serial
    assert [c["name"] for c in serial["chunks"]] == names
    fake_lane(monkeypatch, tmp_path / "parallel", ["--jobs", "3"])
    with pytest.raises(SystemExit) as stop:
        run_runner()
    parallel = receipt(tmp_path / "parallel")
    assert stop.value.code == 0 and parallel["passed"] and parallel["jobs"] == 3
    assert [c["name"] for c in parallel["chunks"]] == names
    assert set(parallel) - {"jobs"} == set(serial)


def test_runner_records_a_chunk_error_and_starts_nothing_after_it(monkeypatch, tmp_path, capsys):
    names = chunk_names()
    fake_lane(monkeypatch, tmp_path / "out", ["--jobs", "3"], bad_guard={names[1]})
    with pytest.raises(SystemExit) as stop:
        run_runner()
    rows = receipt(tmp_path / "out")["chunks"]
    assert stop.value.code == 1 and [c["name"] for c in rows] == names[:len(rows)]
    assert rows[1]["passed"] is False and rows[1]["error"].startswith("runner error: JSONDecodeError")
    # The exact count depends on thread timing (chunks that finished before the failure
    # was seen could start others); the deterministic stop rule is proven above.
    assert len(rows) < len(names)
    assert not receipt(tmp_path / "out")["passed"]


def test_runner_interrupt_keeps_finished_chunks_and_fails(monkeypatch, tmp_path, capsys):
    names = chunk_names()
    fake_lane(monkeypatch, tmp_path / "out", ["--jobs", "2"])
    spec = importlib.util.spec_from_file_location("chunk_scheduler", ROOT / "scripts/testing/chunk_scheduler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    real_wait, calls = module.wait, []
    def interrupting_wait(futures, return_when):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real_wait(futures, return_when=return_when)
    monkeypatch.setattr(module, "wait", interrupting_wait)
    monkeypatch.setitem(sys.modules, "chunk_scheduler", module)
    with pytest.raises(KeyboardInterrupt):
        run_runner()
    result = receipt(tmp_path / "out")
    rows = [c["name"] for c in result["chunks"]]
    assert result["passed"] is False and result["error"] == "interrupted" and result["jobs"] == 2
    assert rows and rows == names[:len(rows)] and all(c["passed"] for c in result["chunks"])
