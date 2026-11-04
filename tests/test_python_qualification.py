"""Qualification evidence must fail closed and pause only outside pytest."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/python_qualification.py"


@pytest.fixture
def tool():
    spec = importlib.util.spec_from_file_location("qualification_tool_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def frozen_source(tmp_path):
    source = tmp_path / "source"
    (source / "src/chronicler").mkdir(parents=True)
    (source / "tests").mkdir()
    (source / "scripts").mkdir()
    (source / "src/chronicler/__init__.py").write_text("")
    (source / "scripts/__init__.py").write_text("")
    (source / "scripts/helper.py").write_text("VALUE = 4\n")
    (source / "tests/helper.py").write_text("VALUE = 2\n")
    (source / "tests/test_tiny.py").write_text("from scripts.helper import VALUE as four\nfrom tests.helper import VALUE as two\n\ndef test_tiny(subtests):\n    for value in (two, four):\n        with subtests.test(value=value):\n            assert value % two == 0\n")
    (source / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Qualification fixture", "-c", "user.email=qualification@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "tiny frozen source"], check=True)
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    return source, head


def request_fixture(tool, frozen_source, tmp_path):
    source, head = frozen_source
    output = tmp_path / "evidence"
    output.mkdir()
    shutil.copyfile(SCRIPT, output / "supervisor.py")
    request = {"kind": tool.KIND, "version": tool.VERSION, "run_id": "test-run",
               "source": str(source), "git_sha": head, "python": sys.executable,
               "native_sha256": None, "output": str(output), "runner_sha256": tool.file_hash(SCRIPT)}
    tool.atomic_json(output / "request.json", request)
    return request, output


def fake_pytest(tool, output, monkeypatch, *, code=0, junit=True, mutate=None, entered=None, release=None):
    original = subprocess.Popen

    class Child:
        pid = 123456789

        def wait(self, **kwargs):
            if entered:
                entered.set()
            if release:
                assert release.wait(10), "test did not release its mocked pytest child"
            if mutate:
                mutate()
            if junit:
                failure = '<failure message="failure" />' if code else ""
                (output / "pytest-junit.xml").write_text(f'<testsuites><testsuite tests="1" failures="{int(bool(code))}" errors="0" skipped="0"><testcase name="tiny">{failure}</testcase></testsuite></testsuites>')
            return code

        def poll(self):
            return code

    def popen(command, **kwargs):
        if command[0] == "git":
            return original(command, **kwargs)
        assert command[-2] == "_driver", command
        kwargs["stdout"].write("mocked pytest execution\n")
        return Child()

    monkeypatch.setattr(tool.subprocess, "Popen", popen)
    monkeypatch.setattr(tool, "runtime_identity", lambda request: {"runtime": "fixed", "python": request["python"], "native": {"status": "absent"}})


def test_no_optional_shell_or_pytest_selection_passthrough(tool):
    parser = tool.parser()
    required = ["run", "--source", "/source", "--git-sha", "a" * 40, "--python", sys.executable, "--output", "/evidence"]
    with pytest.raises(SystemExit):
        parser.parse_args(required)
    with pytest.raises(SystemExit):
        parser.parse_args([*required, "--no-native", "--pytest-args", "-k", "nothing"])


def test_environment_removes_inherited_test_filters_and_paths(tool, monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k select_nothing")
    monkeypatch.setenv("PYTEST_PLUGINS", "unexpected_plugin")
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTHONPATH", "/another/checkout")
    env = tool.child_environment(Path("/frozen"))
    assert all(key not in env for key in tool.PYTEST_OVERRIDE_ENV)
    assert env["PYTHONPATH"] == os.pathsep.join((str(Path("/frozen/src")), str(Path("/frozen"))))
    assert all(env[key] == value for key, value in tool.THREAD_ENV.items())


def test_native_absence_does_not_accept_a_replacement_module(tool, monkeypatch):
    monkeypatch.setattr(tool.importlib.util, "find_spec", lambda name: object())
    with pytest.raises(ValueError, match="can import"):
        tool.native_identity(None)


def test_compiled_native_bytes_must_match_the_requested_hash(tool, tmp_path, monkeypatch):
    path = tmp_path / ("native" + tool.importlib.machinery.EXTENSION_SUFFIXES[0])
    path.write_bytes(b"different build")
    native = SimpleNamespace(__file__=str(path), __spec__=SimpleNamespace(loader=tool.importlib.machinery.ExtensionFileLoader("native", str(path))))
    monkeypatch.setattr(tool.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(tool.importlib, "import_module", lambda name: native)
    with pytest.raises(ValueError, match="SHA-256 differs"):
        tool.native_identity("0" * 64)


@pytest.mark.parametrize("xml,error", [
    ("<testsuites>", ET.ParseError),
    ('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0" /></testsuites>', ValueError),
    ('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="1"><testcase name="skip"><skipped /></testcase></testsuite></testsuites>', ValueError),
])
def test_junit_must_describe_actual_executed_test_cases(tool, tmp_path, xml, error):
    path = tmp_path / "junit.xml"
    path.write_text(xml)
    with pytest.raises(error):
        tool.junit_counts(path)


def test_pytest9_successful_subtests_require_matching_terminal_evidence(tool, tmp_path):
    path, log = tmp_path / "junit.xml", tmp_path / "pytest.log"
    path.write_text('<testsuites><testsuite tests="4" failures="0" errors="0" skipped="1"><testcase name="parent" /><testcase name="skip"><skipped /></testcase></testsuite></testsuites>')
    log.write_text("progress\n1 passed, 1 skipped, 2 subtests passed in 0.01s\n")
    assert tool.junit_counts(path, log) == {"tests": 2, "failures": 0, "errors": 0, "skipped": 1,
                                            "subtests_passed": 2, "junit_declared_tests": 4}
    with pytest.raises(ValueError, match="JUnit declared counts"):
        tool.junit_counts(path)


@pytest.mark.parametrize("summary", [
    "", "mocked pytest execution", "1 passed, 1 subtests passed in 0.01s",
    "2 passed, 2 subtests passed in 0.01s", "1 passed, 1 subtests passed, 1 subtests failed in 0.01s",
    "1 passed, 2 subtests passed, 1 failed in 0.01s", "1 passed, 2 subtests passed, 1 passed in 0.01s",
    "1 passed, 2 subtests passed in 0.01s\ntrailing output",
])
def test_unreconciled_or_unsuccessful_subtests_cannot_earn_a_pass(tool, tmp_path, summary):
    path, log = tmp_path / "junit.xml", tmp_path / "pytest.log"
    path.write_text('<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0"><testcase name="parent" /></testsuite></testsuites>')
    log.write_text(summary + "\n")
    with pytest.raises(ValueError):
        tool.junit_counts(path, log)


@pytest.mark.parametrize("code,junit,outcome", [(0, True, "pass"), (1, True, "test_failure"), (0, False, "qualification_error")])
def test_terminal_receipt_requires_test_exit_and_junit(tool, frozen_source, tmp_path, monkeypatch, code, junit, outcome):
    request, output = request_fixture(tool, frozen_source, tmp_path)
    fake_pytest(tool, output, monkeypatch, code=code, junit=junit)
    result_code = tool.worker(request)
    receipt = tool.read_json(output / "result.json")
    assert receipt["outcome"] == outcome
    assert receipt["passed"] is (outcome == "pass")
    assert (result_code == 0) is (outcome == "pass")
    assert tool.observation(output)["passed"] is receipt["passed"]


def test_source_change_cannot_earn_a_pass(tool, frozen_source, tmp_path, monkeypatch):
    request, output = request_fixture(tool, frozen_source, tmp_path)
    source, _ = frozen_source
    fake_pytest(tool, output, monkeypatch, mutate=lambda: (source / "src/chronicler/__init__.py").write_text("CHANGED = True\n"))
    assert tool.worker(request) != 0
    receipt = tool.read_json(output / "result.json")
    assert receipt["pytest_exit_code"] == 0
    assert receipt["passed"] is False
    assert "not clean" in receipt["error"]


def test_runtime_change_cannot_earn_a_pass(tool, frozen_source, tmp_path, monkeypatch):
    request, output = request_fixture(tool, frozen_source, tmp_path)
    fake_pytest(tool, output, monkeypatch)
    calls = []
    def runtime(request):
        calls.append(1)
        return {"python": request["python"], "native": {"status": "absent"}, "dependency": len(calls)}
    monkeypatch.setattr(tool, "runtime_identity", runtime)
    assert tool.worker(request) != 0
    assert tool.read_json(output / "result.json")["pytest_exit_code"] == 0
    assert "identity changed" in tool.read_json(output / "result.json")["error"]


def test_changed_artifacts_are_not_a_verified_terminal_result(tool, frozen_source, tmp_path, monkeypatch):
    request, output = request_fixture(tool, frozen_source, tmp_path)
    fake_pytest(tool, output, monkeypatch)
    assert tool.worker(request) == 0
    (output / "pytest.log").write_text("replaced evidence")
    with pytest.raises(ValueError, match="artifact bytes differ"):
        tool.observation(output)


@pytest.mark.parametrize("change", [
    lambda r: r.update(outcome="qualification_error"),
    lambda r: r.update(exit_code=1),
    lambda r: r.update(pytest_exit_code=1),
    lambda r: r.update(files={}),
    lambda r: r["files"].pop("pytest-junit.xml"),
    lambda r: r["junit"].update(tests=100),
    lambda r: r.pop("runtime_after"),
])
def test_corrupt_valid_json_cannot_be_reported_as_a_pass(tool, frozen_source, tmp_path, monkeypatch, change):
    request, output = request_fixture(tool, frozen_source, tmp_path)
    fake_pytest(tool, output, monkeypatch)
    assert tool.worker(request) == 0
    result = tool.read_json(output / "result.json")
    change(result)
    tool.atomic_json(output / "result.json", result)
    with pytest.raises(ValueError):
        tool.observation(output)


def test_terminal_pass_rechecks_junit_even_with_an_updated_artifact_hash(tool, frozen_source, tmp_path, monkeypatch):
    request, output = request_fixture(tool, frozen_source, tmp_path)
    fake_pytest(tool, output, monkeypatch)
    assert tool.worker(request) == 0
    path = output / "pytest-junit.xml"
    path.write_text('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="tiny"><failure /></testcase></testsuite></testsuites>')
    receipt = tool.read_json(output / "result.json")
    receipt["files"]["pytest-junit.xml"] = tool.file_hash(path)
    tool.atomic_json(output / "result.json", receipt)
    with pytest.raises(ValueError, match="JUnit declared counts"):
        tool.observation(output)


def test_failed_launch_has_a_distinct_receipt(tool, frozen_source, tmp_path, monkeypatch):
    source, head = frozen_source
    output = tmp_path / "failed-launch"
    args = argparse.Namespace(source=source, git_sha=head, python=Path(sys.executable), native_sha=None,
                              no_native=True, output=output, detach=False, start_paused=False)
    def fail(*args, **kwargs):
        raise OSError("cannot start interpreter")
    monkeypatch.setattr(tool.subprocess, "Popen", fail)
    with pytest.raises(OSError):
        tool.launch(args)
    assert tool.observation(output)["state"] == "launch_error"
    assert tool.observation(output)["passed"] is False


def test_tracked_link_target_cannot_escape_frozen_source_identity(tool, frozen_source, tmp_path):
    source, _ = frozen_source
    target = tmp_path / "outside-source.py"
    target.write_text("VALUE = 1\n")
    link = source / "src/chronicler/linked.py"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("host cannot create file symlinks")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Qualification fixture", "-c", "user.email=qualification@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "tracked external link"], check=True)
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    for contents in ("VALUE = 1\n", "VALUE = 2\n"):
        target.write_text(contents)
        assert subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True) == ""
        with pytest.raises(ValueError, match="symlinks/submodules"):
            tool.source_identity(source, head)


def test_lost_or_reused_worker_without_result_is_interrupted(tool, frozen_source, tmp_path, monkeypatch):
    request, output = request_fixture(tool, frozen_source, tmp_path)
    tool.atomic_json(output / "status.json", {"run_id": request["run_id"], "state": "pytest_running", "worker_identity": {"pid": 1, "start_ticks": 10}})
    monkeypatch.setattr(tool, "process_identity", lambda pid: {"pid": pid, "start_ticks": 11, "state": "S"})
    result = tool.observation(output)
    assert result["state"] == "interrupted" and result["passed"] is False
    assert result["liveness"] == "reused_pid"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="verified Linux process-creation identity")
def test_pause_waits_for_atomic_pytest_exit(tool, frozen_source, tmp_path, monkeypatch):
    request, output = request_fixture(tool, frozen_source, tmp_path)
    entered, release = threading.Event(), threading.Event()
    fake_pytest(tool, output, monkeypatch, entered=entered, release=release)
    thread = threading.Thread(target=tool.worker, args=(request,))
    thread.start()
    try:
        assert entered.wait(5)
        pending = tool.control(output, "pause")
        assert pending["pause_pending"] and not pending["pause_acknowledged"]
        release.set()
        until = time.monotonic() + 5
        while not tool.observation(output)["pause_acknowledged"] and time.monotonic() < until:
            time.sleep(0.02)
        paused = tool.observation(output)
        assert paused["pause_acknowledged"]
        assert paused["last_worker_status"]["active_child_pid"] is None
        tool.control(output, "resume")
        thread.join(5)
        assert not thread.is_alive()
        assert tool.observation(output)["passed"]
        assert tool.read_json(output / "result.json")["pause_intervals"][0]["boundary"] == "after_pytest"
    finally:
        release.set()
        (output / "pause-request.json").unlink(missing_ok=True)
        thread.join(5)


@pytest.mark.parametrize("detached", [False, True])
def test_real_tiny_child(tool, frozen_source, tmp_path, monkeypatch, detached):
    if detached and not sys.platform.startswith("linux"):
        pytest.skip("detached process identity requires Linux")
    source, head = frozen_source
    output = tmp_path / "actual-evidence"
    native_sha = None
    if importlib.util.find_spec("chronicler_agents") is not None:
        spec = importlib.util.find_spec("chronicler_agents.chronicler_agents")
        native_sha = tool.file_hash(Path(spec.origin))
    # Prove inherited selection cannot turn the full lane into zero selected tests.
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k select_nothing")
    args = argparse.Namespace(source=source, git_sha=head, python=Path(sys.executable), native_sha=native_sha, no_native=native_sha is None,
                              output=output, detach=detached, start_paused=detached)
    result = tool.launch(args)
    if detached:
        until = time.monotonic() + 15
        while time.monotonic() < until:
            result = tool.observation(output)
            if result.get("pause_acknowledged") or result["state"] in ("complete", "interrupted"):
                break
            time.sleep(0.05)
        assert result.get("pause_acknowledged"), result
        tool.control(output, "resume")
        until = time.monotonic() + 15
        while time.monotonic() < until:
            result = tool.observation(output)
            if result["state"] in ("complete", "interrupted"):
                break
            time.sleep(0.05)
    assert result["state"] == "complete" and result["passed"], result
    receipt = tool.read_json(output / "result.json")
    assert receipt["junit"]["tests"] == 1 and receipt["junit"]["skipped"] == 0
    assert receipt["junit"]["subtests_passed"] == 2 and receipt["junit"]["junit_declared_tests"] == 3
    assert receipt["source_before"] == receipt["source_after"]
    with pytest.raises(FileExistsError):
        tool.launch(args)


@pytest.mark.parametrize("change", [
    lambda s, m: s.update(state="pytest_running"),
    lambda s, m: s.update(active_child_pid=123),
    lambda s, m: s["pause"].update(boundary="after_pytest"),
    lambda s, m: m.update(request_id="another-request"),
    lambda s, m: s.update(run_id="another-run"),
    lambda s, m: s.update(pause=None),
])
def test_cancel_requires_the_matching_before_test_boundary(tool, change):
    status = {"run_id": "run", "state": "paused", "active_child_pid": None,
              "pause": {"boundary": "before_pytest", "request_id": "pause"}}
    marker = {"request_id": "pause"}
    tool.before_tests_pause(status, marker, "run")
    change(status, marker)
    with pytest.raises(ValueError, match="before_pytest"):
        tool.before_tests_pause(status, marker, "run")


@pytest.mark.parametrize("liveness", ["unknown", "reused_pid", "exited"])
@pytest.mark.skipif(not sys.platform.startswith("linux") or not hasattr(os, "pidfd_open"), reason="Linux cancellation preflight")
def test_cancel_never_signals_unverified_workers(tool, frozen_source, tmp_path, monkeypatch, liveness):
    request, output = request_fixture(tool, frozen_source, tmp_path)
    status = {"run_id": request["run_id"], "state": "paused", "active_child_pid": None,
              "pause": {"boundary": "before_pytest", "request_id": "pause"}}
    tool.atomic_json(output / "status.json", status)
    tool.atomic_json(output / "pause-request.json", {"request_id": "pause"})
    monkeypatch.setattr(tool, "worker_liveness", lambda status: liveness)
    monkeypatch.setattr(tool.os, "pidfd_open", lambda pid: pytest.fail("must not acquire a process handle"), raising=False)
    with pytest.raises(ValueError, match="live verified"):
        tool.cancel_before_tests(output, "prototype rejected")
    assert not (output / tool.CANCEL_INTENT).exists()


@pytest.mark.parametrize("name", ["pytest.log", "pytest-junit.xml", "result.json"])
def test_cancel_refuses_any_evidence_that_tests_or_finalization_began(tool, tmp_path, name):
    (tmp_path / name).write_text("")
    with pytest.raises(ValueError, match="artifacts exist"):
        tool.no_pytest_artifacts(tmp_path)


def test_cancel_requires_a_reason_and_refuses_unsupported_signalling(tool, tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        tool.parser().parse_args(["cancel-before-tests", "--output", str(tmp_path)])
    with pytest.raises(ValueError, match="nonempty reason"):
        tool.cancel_before_tests(tmp_path, " ")
    monkeypatch.setattr(tool.sys, "platform", "unsupported")
    with pytest.raises(ValueError, match="Linux pidfd"):
        tool.cancel_before_tests(tmp_path, "reason")


def test_recovered_unknown_cancellation_refuses_any_new_signal(tool, tmp_path, monkeypatch):
    (tmp_path / tool.CANCEL_UNKNOWN).write_text("{}")
    monkeypatch.setattr(tool.sys, "platform", "linux")
    monkeypatch.setattr(tool, "owned_paused_worker", lambda *a: pytest.fail("unknown evidence must precede ownership probes"))
    monkeypatch.setattr(tool.os, "pidfd_open", lambda *a: pytest.fail("must not acquire a process handle"), raising=False)
    monkeypatch.setattr(tool.signal, "pidfd_send_signal", lambda *a: pytest.fail("must not send a signal"), raising=False)
    with pytest.raises(ValueError, match="already exists"):
        tool.cancel_before_tests(tmp_path, "do not override unknown evidence")


@pytest.mark.skipif(not sys.platform.startswith("linux") or not hasattr(os, "pidfd_open"), reason="Linux owned-command preflight")
def test_cancel_rejects_a_live_pid_running_another_command(tool, frozen_source, tmp_path, monkeypatch):
    request, output = request_fixture(tool, frozen_source, tmp_path)
    identity = tool.process_identity(os.getpid())
    status = {"run_id": request["run_id"], "state": "paused", "active_child_pid": None, "worker_identity": identity,
              "pause": {"boundary": "before_pytest", "request_id": "pause"}}
    command = [request["python"], str(output / "supervisor.py"), "_worker", str(output / "request.json")]
    tool.atomic_json(output / "status.json", status)
    tool.atomic_json(output / "pause-request.json", {"request_id": "pause"})
    tool.atomic_json(output / "launch.json", {"command": command, "pid": os.getpid(), "worker_identity": identity})
    monkeypatch.setattr(tool.os, "pidfd_open", lambda pid: pytest.fail("must reject command before a process handle"))
    with pytest.raises(ValueError, match="live worker command"):
        tool.cancel_before_tests(output, "this PID is not the launched worker")
    assert not (output / tool.CANCEL_INTENT).exists()


def _real_paused_lane(tool, frozen_source, output):
    source, head = frozen_source
    native_sha = None
    if importlib.util.find_spec("chronicler_agents") is not None:
        spec = importlib.util.find_spec("chronicler_agents.chronicler_agents")
        native_sha = tool.file_hash(Path(spec.origin))
    args = argparse.Namespace(source=source, git_sha=head, python=Path(sys.executable), native_sha=native_sha,
                              no_native=native_sha is None, output=output, detach=True, start_paused=True)
    launch = tool.launch(args)
    until = time.monotonic() + 15
    while time.monotonic() < until:
        state = tool.observation(output)
        if state.get("pause_acknowledged"):
            return launch
        if state["state"] in ("complete", "interrupted"):
            pytest.fail(str(state))
        time.sleep(.02)
    pytest.fail("real tiny worker did not acknowledge its initial pause")


def _stop_own_test_worker(tool, output):
    """Only cleanup a fixture-owned worker if a regression refuses cancellation."""
    launch = tool.read_json(output / "launch.json")
    saved = launch["worker_identity"]
    current = tool.process_identity(saved["pid"])
    if (current and not current.get("missing") and current.get("state") != "Z"
            and all(current.get(key) == saved.get(key) for key in ("start_ticks", "boot_id"))):
        try:
            raw = (Path("/proc") / str(saved["pid"]) / "cmdline").read_bytes()
        except FileNotFoundError:
            return
        if not raw:
            return  # SIGTERM may already have cleared the exiting worker's mm.
        actual = raw.rstrip(b"\0").split(b"\0")
        assert [os.fsdecode(value) for value in actual] == launch["command"]
        try:
            descriptor = os.pidfd_open(saved["pid"])
        except ProcessLookupError:
            return
        try:
            fresh = tool.process_identity(saved["pid"])
            if fresh and all(fresh.get(key) == saved.get(key) for key in ("start_ticks", "boot_id")):
                signal.pidfd_send_signal(descriptor, signal.SIGTERM)
        except ProcessLookupError:
            pass
        finally:
            os.close(descriptor)


@pytest.mark.skipif(not sys.platform.startswith("linux") or not hasattr(os, "pidfd_open")
                    or not hasattr(signal, "pidfd_send_signal"), reason="verified Linux pidfd cancellation")
def test_real_cancelled_before_tests_preserves_evidence_without_a_test_result(tool, frozen_source, tmp_path):
    output = tmp_path / "cancelled-evidence"
    _real_paused_lane(tool, frozen_source, output)
    original = {name: (output / name).read_bytes() for name in tool.CANCEL_INPUTS}
    try:
        result = tool.cancel_before_tests(output, "Rejected performance prototype; do not run pytest")
    finally:
        _stop_own_test_worker(tool, output)
    assert result["state"] == "cancelled_before_tests" and result["passed"] is False
    assert result["tests_started"] is False and "pytest_exit_code" not in result
    assert {name: (output / name).read_bytes() for name in tool.CANCEL_INPUTS} == original
    assert {name: (output / "cancellation-inputs" / name).read_bytes() for name in tool.CANCEL_INPUTS} == original
    assert not any((output / name).exists() for name in ("pytest.log", "pytest-junit.xml", "result.json"))
    for action in ("pause", "resume"):
        with pytest.raises(ValueError):
            tool.control(output, action)
    with pytest.raises(ValueError, match="already exists"):
        tool.cancel_before_tests(output, "second request")
    terminal = (output / tool.CANCEL_RESULT).read_bytes()
    for change in ({"passed": True}, {"tests_started": True}, {"worker_exit_observed": False}, {"pidfd_exit_events": []}):
        receipt = json.loads(terminal)
        receipt.update(change)
        tool.atomic_json(output / tool.CANCEL_RESULT, receipt)
        with pytest.raises(ValueError):
            tool.observation(output)
    (output / tool.CANCEL_RESULT).write_bytes(terminal)
    (output / "cancellation-inputs/status.json").write_text("{}")
    with pytest.raises(ValueError, match="snapshot bytes changed"):
        tool.observation(output)


@pytest.mark.skipif(not sys.platform.startswith("linux") or not hasattr(os, "pidfd_open")
                    or not hasattr(signal, "pidfd_send_signal"), reason="verified Linux pidfd cancellation")
def test_unverified_exit_stays_unknown_and_cannot_resume(tool, frozen_source, tmp_path, monkeypatch):
    output = tmp_path / "unknown-cancellation"
    _real_paused_lane(tool, frozen_source, output)
    monkeypatch.setattr(tool.select, "poll", lambda: SimpleNamespace(register=lambda *a: None, poll=lambda ms: []))
    try:
        with pytest.raises(ValueError, match="exit unverified"):
            tool.cancel_before_tests(output, "cancel before pytest")
    finally:
        _stop_own_test_worker(tool, output)
    state = tool.observation(output)
    assert state["state"] == "cancellation_unknown" and not state["passed"]
    assert not (output / tool.CANCEL_RESULT).exists() and not (output / "pytest.log").exists()
    with pytest.raises(ValueError):
        tool.control(output, "resume")


@pytest.mark.skipif(not sys.platform.startswith("linux") or not hasattr(os, "pidfd_open")
                    or not hasattr(signal, "pidfd_send_signal"), reason="verified Linux cancellation refusal")
def test_real_running_pytest_is_never_signalled(tool, frozen_source, tmp_path, monkeypatch):
    source, _ = frozen_source
    entered, release = tmp_path / "entered", tmp_path / "release"
    (source / "tests/test_tiny.py").write_text(
        "from pathlib import Path\nimport time\n\ndef test_wait():\n"
        f"    Path({str(entered)!r}).write_text('entered')\n"
        "    until = time.monotonic() + 10\n"
        f"    while not Path({str(release)!r}).exists() and time.monotonic() < until:\n"
        "        time.sleep(.01)\n"
        f"    assert Path({str(release)!r}).exists()\n")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Qualification fixture", "-c", "user.email=qualification@example.invalid",
                    "-c", "commit.gpgsign=false", "commit", "-qm", "explicit running-test barrier"], check=True)
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    output = tmp_path / "running-evidence"
    _real_paused_lane(tool, (source, head), output)
    try:
        tool.control(output, "resume")
        until = time.monotonic() + 10
        while not entered.exists() and time.monotonic() < until:
            time.sleep(.02)
        assert entered.exists(), tool.observation(output)
        with monkeypatch.context() as patch:
            patch.setattr(tool.signal, "pidfd_send_signal", lambda *a: pytest.fail("running pytest must never be signalled"))
            with pytest.raises(ValueError, match="before_pytest"):
                tool.cancel_before_tests(output, "too late")
        assert not (output / tool.CANCEL_INTENT).exists()
    finally:
        release.write_text("finish normally")
        until = time.monotonic() + 10
        while tool.observation(output)["state"] not in ("complete", "interrupted") and time.monotonic() < until:
            time.sleep(.02)
        _stop_own_test_worker(tool, output)
    assert tool.observation(output)["passed"]
