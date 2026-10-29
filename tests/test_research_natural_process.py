"""Tiny real Linux ownership probes. No simulation imports, pools or worlds.

These belong to the POSIX process lane, not the guarded offline selection.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux subreaper/proc qualification")

CONTROLLER = r'''
import json, os, pathlib, signal, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
import run_research_natural_continuation as R
root, mode = pathlib.Path(sys.argv[2]), sys.argv[3]
worker = r"""
import os, pathlib, subprocess, sys, time
root, mode = pathlib.Path(sys.argv[1]), sys.argv[2]
(root / 'leader.pid').write_text(str(os.getpid()))
if mode == 'burst':
    child = subprocess.Popen([sys.executable, '-c', 'import time; s=time.process_time();\nwhile time.process_time()-s < .25: pass'])
    (root / 'descendant.pid').write_text(str(child.pid))
    child.wait()
elif mode in ('orphan', 'early_exit', 'early_old_session'):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=mode != 'early_old_session')
    (root / 'descendant.pid').write_text(str(child.pid))
elif mode == 'cpu':
    child = subprocess.Popen([sys.executable, '-c', 'while True: pass'])
    (root / 'descendant.pid').write_text(str(child.pid))
    time.sleep(60)
else:
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
    (root / 'descendant.pid').write_text(str(child.pid))
    time.sleep(60)
"""
result = {'complete': False, 'native_modules_loaded': False}
if mode == 'run_interrupt':
    from types import SimpleNamespace
    R.C.SEEDS = (2000,)
    frozen = {'control': {'git_sha': 'explicit-controller-test-fixture'}}
    R.verify_freeze = lambda *args: frozen
    R.resources = lambda *args, **kwargs: {'test_resources_only': True}
    freeze = root / 'prospective-fixture.json'
    R.C.write(freeze, frozen)
    original_popen = subprocess.Popen
    def stub_worker(command, **kwargs):
        return original_popen([sys.executable, '-c', worker, str(root), mode], **kwargs)
    R.subprocess.Popen = stub_worker
    code = R.run(SimpleNamespace(source_root=str(root / 'unused-producer'),
        output_root=str(root / 'execution'), freeze=str(freeze)))
    execution = R.C.read(root / 'execution/execution.json')
    result.update(returncode=code, execution=execution, cleanup_complete=not R.direct_children(),
        known_pids=[int((root / name).read_text()) for name in ('leader.pid', 'descendant.pid')])
    (root / 'result.json').write_text(json.dumps(result))
    raise SystemExit(0)
with R.exclusive_subreaper(), R.interruption_guard():
    child = subprocess.Popen([sys.executable, '-c', worker, str(root), mode], start_new_session=True)
    if mode in ('early_exit', 'early_old_session'):
        time.sleep(.3)
        # Exercise a missing initial birth handshake after the real leader has
        # exited and been reaped; its setsid orphan is already adopted by us.
        child.wait(timeout=2)
        known = {}
    else:
        lease = R.process_record(child.pid)
        known = {child.pid: lease['start_ticks']}
    started = time.monotonic()
    first = True
    def guard():
        global first
        if first and mode in ('orphan', 'burst'):
            time.sleep(.6)  # Intentionally miss the entire initial leader lifetime.
        first = False
    (root / 'ready').touch()
    try:
        result['accounting'] = R.supervise(child, known, lambda: 0.0, guard, started, started,
            worker_cpu=.12 if mode in ('cpu', 'burst') else 5,
            worker_wall=.25 if mode == 'wall' else 5, aggregate_wall=8)
        result['complete'] = True
    except BaseException as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        R.cleanup(child, known)
        result['cleanup_complete'] = not R.owned_tree(child.pid, known) and not R.direct_children()
        result['known_pids'] = sorted(known)
result['native_modules_loaded'] = any(n.startswith('chronicler') for n in sys.modules)
(root / 'result.json').write_text(json.dumps(result))
'''


def invoke(tmp_path, mode, interruption=None):
    controller = subprocess.Popen([sys.executable, "-c", CONTROLLER, str(ROOT / "scripts"), str(tmp_path), mode],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        if interruption is not None:
            deadline = time.monotonic() + 5
            while not (tmp_path / "descendant.pid").exists() and time.monotonic() < deadline:
                time.sleep(.01)
            assert (tmp_path / "descendant.pid").exists()
            os.kill(controller.pid, interruption)
        stdout, stderr = controller.communicate(timeout=12)
        assert controller.returncode == 0, (stdout, stderr)
        result = json.loads((tmp_path / "result.json").read_text())
        assert result["cleanup_complete"] is True
        assert result["native_modules_loaded"] is False
        assert result["complete"] is False
        for filename in ("leader.pid", "descendant.pid"):
            pid = int((tmp_path / filename).read_text())
            # A child already waited by the leader may never be sampled;
            # wait4 charges its CPU through the leader's exit usage instead.
            if mode not in ("early_exit", "early_old_session") and (filename == "leader.pid" or mode != "burst"):
                assert pid in result["known_pids"]
            assert not Path(f"/proc/{pid}").exists(), f"unreaped owned process {pid}"
        return result
    finally:
        if controller.poll() is None:
            controller.kill()
            controller.wait()


def test_idle_leader_cannot_hide_descendant_cpu(tmp_path):
    result = invoke(tmp_path, "cpu")
    assert "worker process-tree CPU budget" in result["error"]["message"]


def test_wait4_accounts_a_whole_cpu_burst_between_samples(tmp_path):
    result = invoke(tmp_path, "burst")
    assert "worker process-tree CPU budget" in result["error"]["message"]


def test_transient_leader_cannot_leave_an_unobserved_setsid_orphan(tmp_path):
    result = invoke(tmp_path, "orphan")
    assert "owned descendants" in result["error"]["message"]


def test_missing_initial_birth_handshake_still_cleans_adopted_orphan(tmp_path):
    result = invoke(tmp_path, "early_exit")
    assert "owned descendants" in result["error"]["message"]


def test_missing_birth_handshake_cleans_orphan_in_the_original_group(tmp_path):
    result = invoke(tmp_path, "early_old_session")
    assert "owned descendants" in result["error"]["message"]


def test_wall_timeout_cleans_the_complete_owned_tree(tmp_path):
    result = invoke(tmp_path, "wall")
    assert "wall budget" in result["error"]["message"]


@pytest.mark.parametrize("interruption", [signal.SIGTERM, signal.SIGINT])
def test_controller_interruption_unwinds_and_reaps_both_sessions(tmp_path, interruption):
    result = invoke(tmp_path, "interrupt", interruption)
    assert result["error"]["type"] == "InterruptedError"


def test_actual_controller_retains_negative_receipt_and_stops_remaining_roles(tmp_path):
    result = invoke(tmp_path, "run_interrupt", signal.SIGTERM)
    assert result["returncode"] == 1
    execution = result["execution"]
    assert execution["execution_complete"] is False
    assert [row["status"] for row in execution["runs"]] == [
        "failed", "not_attempted_after_failure", "not_attempted_after_failure"]
    assert execution["runs"][0]["error"]["type"] == "InterruptedError"
