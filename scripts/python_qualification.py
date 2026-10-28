#!/usr/bin/env python3
"""Run one immutable full Python test lane and retain its execution evidence.

Only fixed pytest execution is supported. Run ``--help`` for the explicit
source/interpreter/native identity requirements and cooperative controls.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.machinery
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
import xml.etree.ElementTree as ET

KIND = "chronicler-python-qualification"
VERSION = 1
THREAD_ENV = {
    "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUNBUFFERED": "1", "RAYON_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1", "OPENBLAS_THREAD_TIMEOUT": "16",
    "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "BLIS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1", "GOTO_NUM_THREADS": "1",
}
PYTEST_OVERRIDE_ENV = ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTEST_CURRENT_TEST")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1 << 20), b""):
            digest.update(data)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def git(source: Path, *args: str) -> bytes:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.check_output(["git", "-C", str(source), *args], stderr=subprocess.PIPE, env=env)


def source_identity(source: Path, expected: str) -> dict:
    top = Path(os.fsdecode(git(source, "rev-parse", "--show-toplevel")).strip()).resolve()
    if top != source:
        raise ValueError("--source must be the checkout root")
    head = git(source, "rev-parse", "HEAD").decode("ascii").strip()
    if head != expected:
        raise ValueError(f"source HEAD differs: expected {expected}, found {head}")
    if git(source, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("source checkout is not clean")
    hashes = {}
    for raw in git(source, "ls-files", "--stage", "-z").split(b"\0"):
        if not raw:
            continue
        metadata, raw_name = raw.split(b"\t", 1)
        mode = metadata.split()[0]
        name = os.fsdecode(raw_name)
        path = source / name
        # Git mode catches links checked out as plain text on Windows too.
        if mode not in (b"100644", b"100755") or path.is_symlink():
            raise ValueError(f"tracked symlinks/submodules are unsupported: {name}")
        if path.is_file():
            hashes[name] = {"sha256": file_hash(path)}
        else:
            raise ValueError(f"tracked path is missing or unsupported: {name}")
    return {"checkout": str(source), "git_sha": head, "tracked_files": hashes}


def native_identity(expected: str | None) -> dict:
    found = importlib.util.find_spec("chronicler_agents")
    if expected is None:
        if found is not None:
            raise ValueError("no-native lane can import chronicler_agents")
        return {"status": "absent"}
    if found is None:
        raise ValueError("native lane cannot import chronicler_agents")
    package = importlib.import_module("chronicler_agents")
    native = importlib.import_module("chronicler_agents.chronicler_agents")
    spec = native.__spec__
    origin = Path(native.__file__).resolve()
    if (spec is None or not isinstance(spec.loader, importlib.machinery.ExtensionFileLoader)
            or not str(origin).endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES))):
        raise ValueError("native submodule is not loaded by a compiled-extension loader")
    actual = file_hash(origin)
    if actual != expected:
        raise ValueError(f"native SHA-256 differs: expected {expected}, found {actual}")
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(package, name, None)
        if not isinstance(cls, type) or cls is not getattr(native, name, None):
            raise ValueError(f"native exported class is not the compiled class: {name}")
    return {"status": "compiled", "path": str(origin), "sha256": actual, "bytes": origin.stat().st_size}


def runtime_identity(request: dict) -> dict:
    if Path(sys.executable).absolute() != Path(request["python"]):
        raise ValueError("worker interpreter differs from the explicit --python path")
    if any(os.environ.get(key) != value for key, value in THREAD_ENV.items()):
        raise ValueError("worker thread/hash environment differs from the fixed lane")
    versions = {}
    for package in importlib.metadata.distributions():
        name = package.metadata.get("Name")
        if name:
            versions[name] = package.version
    return {
        "python": str(Path(sys.executable).absolute()), "python_realpath": str(Path(sys.executable).resolve()),
        "python_sha256": file_hash(Path(sys.executable)), "version": sys.version,
        "implementation": platform.python_implementation(), "platform": platform.platform(),
        "machine": platform.machine(), "prefix": sys.prefix,
        "packages": dict(sorted(versions.items())),
        "thread_env": {key: os.environ.get(key) for key in THREAD_ENV},
        "pythonpath": os.environ.get("PYTHONPATH"), "native": native_identity(request["native_sha256"]),
    }


def child_environment(source: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in PYTEST_OVERRIDE_ENV:
        env.pop(key, None)
    env.update(THREAD_ENV)
    env["PYTHONPATH"] = str(source / "src")
    return env


def pytest_arguments(request: dict) -> list[str]:
    output = Path(request["output"])
    return ["-q", "-o", "addopts=", "-o", f"pythonpath={Path(request['source']) / 'src'}", "-p", "no:cacheprovider",
            "--basetemp", str(output / "pytest-tmp"), "--junitxml", str(output / "pytest-junit.xml")]


def process_identity(pid: int) -> dict | None:
    """Verified Linux PID creation identity; unknown on other platforms."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text()
    except FileNotFoundError:
        return {"pid": pid, "missing": True}
    except OSError:
        return None
    try:
        fields = raw[raw.rfind(")") + 2:].split()
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        return {"pid": pid, "start_ticks": int(fields[19]), "boot_id": boot_id, "state": fields[0]}
    except (OSError, ValueError, IndexError):
        return None


def worker_liveness(status: dict) -> str:
    saved = status.get("worker_identity")
    if not isinstance(saved, dict) or "start_ticks" not in saved:
        return "unknown"
    current = process_identity(saved["pid"])
    if current is None:
        return "unknown"
    if current.get("missing") or current.get("state") == "Z":
        return "exited"
    if current.get("start_ticks") != saved["start_ticks"] or current.get("boot_id") != saved.get("boot_id"):
        return "reused_pid"
    return "verified_alive"


@contextmanager
def control_lock(output: Path):
    path = output / "control.lock"
    until = time.monotonic() + 5
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            break
        except FileExistsError:
            if time.monotonic() >= until:
                raise ValueError("control operation already in progress; lock preserved")
            time.sleep(0.05)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def update_status(output: Path, status: dict, **changes) -> None:
    status.update(changes, observed_at=utc_now())
    atomic_json(output / "status.json", status)


def boundary(output: Path, status: dict, label: str) -> None:
    marker = output / "pause-request.json"
    if not marker.exists():
        return
    # This is called only before child launch or after wait() returned.
    if status.get("active_child_pid") is not None:
        raise ValueError("cannot acknowledge a pause while a pytest child is active")
    with control_lock(output):
        if not marker.exists():
            return
        requested = read_json(marker)
        interval = {"request_id": requested["request_id"], "requested_at": requested["requested_at"], "acknowledged_at": utc_now(), "boundary": label}
        update_status(output, status, state="paused", pause=interval)
    while marker.exists():
        # A resume followed immediately by another pause need not launch
        # pytest between them, but its acknowledgement must name the new request.
        try:
            current = read_json(marker)
        except FileNotFoundError:
            break
        if current["request_id"] != interval["request_id"]:
            interval["resumed_at"] = utc_now()
            status["pause_intervals"].append(interval)
            interval = {"request_id": current["request_id"], "requested_at": current["requested_at"], "acknowledged_at": utc_now(), "boundary": label}
            update_status(output, status, state="paused", pause=interval)
        time.sleep(0.2)
    interval["resumed_at"] = utc_now()
    status.setdefault("pause_intervals", []).append(interval)
    status.pop("pause", None)
    update_status(output, status, state=label)


def junit_counts(path: Path) -> dict:
    root = ET.parse(path).getroot()
    if root.tag not in ("testsuites", "testsuite"):
        raise ValueError("JUnit root must be testsuites or testsuite")
    suites = [suite for suite in root.iter("testsuite") if not suite.findall("testsuite")]
    if not suites:
        raise ValueError("JUnit report contains no test suites")
    counts = {key: sum(int(item.get(key, "0")) for item in suites) for key in ("tests", "failures", "errors", "skipped")}
    cases = list(root.iter("testcase"))
    actual = {"tests": len(cases), **{key: sum(case.find(tag) is not None for case in cases)
                                     for key, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped"))}}
    if counts != actual:
        raise ValueError("JUnit declared counts differ from its test cases")
    if counts["tests"] <= counts["skipped"] or any(value < 0 for value in counts.values()):
        raise ValueError("JUnit report has no tests or invalid counts")
    return counts


def verify_terminal(output: Path, request: dict, result: dict) -> None:
    """Do not turn incomplete or internally inconsistent JSON into a pass."""
    if result.get("kind") != KIND or result.get("version") != VERSION or result.get("run_id") != request["run_id"]:
        raise ValueError("terminal receipt belongs to another request or protocol")
    passed = result.get("passed")
    code = result.get("exit_code")
    if type(passed) is not bool or type(code) is not int or (code == 0) != passed:
        raise ValueError("terminal pass and exit fields are inconsistent")
    if result.get("outcome") not in ("pass", "test_failure", "qualification_error") or (result["outcome"] == "pass") != passed:
        raise ValueError("terminal outcome and pass fields are inconsistent")
    if result.get("request_sha256") != file_hash(output / "request.json"):
        raise ValueError("request bytes differ from the terminal receipt")
    if result.get("runner_sha256") != request.get("runner_sha256") or result.get("runner_sha256") != file_hash(output / "supervisor.py"):
        raise ValueError("runner bytes differ from the terminal receipt")
    files = result.get("files")
    if not isinstance(files, dict) or (passed and set(files) != {"pytest.log", "pytest-junit.xml"}):
        raise ValueError("passing terminal receipt must include both pytest artifacts")
    for name, digest in files.items():
        if name not in ("pytest.log", "pytest-junit.xml") or file_hash(output / name) != digest:
            raise ValueError("qualification artifact bytes differ from the terminal receipt")
    if passed:
        if type(result.get("pytest_exit_code")) is not int or result["pytest_exit_code"] != 0:
            raise ValueError("passing receipt has no successful pytest exit")
        counts = junit_counts(output / "pytest-junit.xml")
        reported = result.get("junit")
        if (not isinstance(reported, dict) or any(type(value) is not int for value in reported.values())
                or reported != counts or counts["failures"] or counts["errors"]):
            raise ValueError("passing receipt does not match successful JUnit test cases")
        before = result.get("source_before")
        runtime = result.get("runtime_before")
        if (not isinstance(before, dict) or before.get("git_sha") != request["git_sha"] or before != result.get("source_after")
                or not isinstance(runtime, dict) or runtime.get("python") != request["python"] or runtime != result.get("runtime_after")):
            raise ValueError("passing receipt has inconsistent source/runtime identities")
        native = runtime.get("native", {})
        if ((request["native_sha256"] is None and native.get("status") != "absent")
                or (request["native_sha256"] is not None and native.get("sha256") != request["native_sha256"])):
            raise ValueError("passing receipt has inconsistent native identity")


def driver(request: dict) -> int:
    native_identity(request["native_sha256"])
    package = importlib.import_module("chronicler")
    actual = Path(package.__file__).resolve()
    if actual != (Path(request["source"]) / "src/chronicler/__init__.py").resolve():
        raise ValueError("pytest child imported another chronicler checkout")
    import pytest
    return int(pytest.main(pytest_arguments(request)))


def worker(request: dict) -> int:
    output = Path(request["output"])
    status = {"kind": KIND, "version": VERSION, "run_id": request["run_id"], "state": "preflight",
              "started_at": utc_now(), "worker_identity": process_identity(os.getpid()),
              "active_child_pid": None, "pause_intervals": []}
    update_status(output, status)
    result = {"kind": KIND, "version": VERSION, "run_id": request["run_id"], "started_at": status["started_at"],
              "passed": False, "request_sha256": file_hash(output / "request.json"),
              "runner_sha256": request["runner_sha256"]}
    child = None
    try:
        if file_hash(Path(__file__)) != request["runner_sha256"]:
            raise ValueError("copied runner bytes changed")
        result["source_before"] = source_identity(Path(request["source"]), request["git_sha"])
        result["runtime_before"] = runtime_identity(request)
        boundary(output, status, "before_pytest")
        command = [request["python"], str(Path(__file__)), "_driver", str(output / "request.json")]
        result["command"] = command
        result["pytest_arguments"] = pytest_arguments(request)
        with (output / "pytest.log").open("x", encoding="utf-8") as log:
            child = subprocess.Popen(command, cwd=request["source"], env=child_environment(Path(request["source"])),
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            update_status(output, status, state="pytest_running", active_child_pid=child.pid)
            code = child.wait()
        result["pytest_exit_code"] = code
        update_status(output, status, state="postflight", active_child_pid=None, pytest_exit_code=code)
        boundary(output, status, "after_pytest")
        result["source_after"] = source_identity(Path(request["source"]), request["git_sha"])
        result["runtime_after"] = runtime_identity(request)
        if result["source_before"] != result["source_after"] or result["runtime_before"] != result["runtime_after"]:
            raise ValueError("source or runtime identity changed during qualification")
        if file_hash(Path(__file__)) != request["runner_sha256"]:
            raise ValueError("copied runner bytes changed during qualification")
        result["junit"] = junit_counts(output / "pytest-junit.xml")
        result["passed"] = code == 0 and result["junit"]["failures"] == 0 and result["junit"]["errors"] == 0
        result["outcome"] = "pass" if result["passed"] else "test_failure"
        result["exit_code"] = 0 if result["passed"] else 1
    except BaseException as exc:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        result.update(outcome="qualification_error", exit_code=1, error=f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    result["completed_at"] = utc_now()
    result["pause_intervals"] = status["pause_intervals"]
    result["files"] = {name: file_hash(output / name) for name in ("pytest.log", "pytest-junit.xml") if (output / name).is_file()}
    atomic_json(output / "result.json", result)
    update_status(output, status, state="complete", active_child_pid=None, outcome=result["outcome"], exit_code=result["exit_code"])
    return result["exit_code"]


def observation(output: Path) -> dict:
    request = read_json(output / "request.json")
    if request.get("kind") != KIND or request.get("version") != VERSION:
        raise ValueError("unsupported qualification request")
    if (output / "launch-error.json").exists():
        return {"state": "launch_error", "passed": False, "exit_code": 2, "output": str(output),
                "error": read_json(output / "launch-error.json")}
    if (output / "result.json").exists():
        result = read_json(output / "result.json")
        verify_terminal(output, request, result)
        return {"state": "complete", "outcome": result["outcome"], "passed": result["passed"], "exit_code": result["exit_code"], "output": str(output)}
    status_path = output / "status.json"
    if not status_path.exists():
        if (output / "launch.json").exists():
            launch = read_json(output / "launch.json")
            live = worker_liveness(launch)
            if live in ("exited", "reused_pid"):
                return {"state": "interrupted", "liveness": live, "passed": False, "output": str(output)}
        return {"state": "launch_pending", "passed": False, "output": str(output)}
    status = read_json(status_path)
    if status.get("run_id") != request["run_id"]:
        raise ValueError("status belongs to another request")
    live = worker_liveness(status)
    state = "interrupted" if live in ("exited", "reused_pid") else status["state"]
    pause = (output / "pause-request.json").exists()
    try:
        marker = read_json(output / "pause-request.json") if pause else {}
    except FileNotFoundError:
        marker, pause = {}, False
    acknowledged = (state == "paused" and live == "verified_alive" and status.get("active_child_pid") is None
                    and pause and status.get("pause", {}).get("request_id") == marker.get("request_id"))
    return {"state": state, "liveness": live, "passed": False, "pause_requested": pause,
            "pause_acknowledged": acknowledged, "pause_pending": pause and not acknowledged,
            "last_worker_status": status, "output": str(output)}


def control(output: Path, action: str) -> dict:
    with control_lock(output):
        status = observation(output)
        if status["state"] in ("complete", "interrupted", "launch_error"):
            raise ValueError("cannot control a completed or interrupted qualification")
        marker = output / "pause-request.json"
        if action == "pause":
            if not marker.exists():
                atomic_json(marker, {"requested_at": utc_now(), "request_id": uuid.uuid4().hex})
        else:
            marker.unlink(missing_ok=True)
    return observation(output)


def launch(args: argparse.Namespace) -> dict:
    source = args.source.resolve(strict=True)
    python = args.python.expanduser().absolute()
    output = args.output.resolve()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError("--python must name an executable interpreter")
    if not (source / "src/chronicler/__init__.py").is_file() or not (source / "tests").is_dir():
        raise ValueError("--source must contain the Chronicler package and tests")
    if output == source or source in output.parents:
        raise ValueError("qualification output must be outside the source checkout")
    if args.detach and not sys.platform.startswith("linux"):
        raise ValueError("detached launch requires verified Linux process identities; use foreground on this host")
    if args.detach and not (process_identity(os.getpid()) or {}).get("start_ticks"):
        raise ValueError("detached launch cannot verify a process creation identity on this host")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", args.git_sha):
        raise ValueError("--git-sha must be the full lowercase Git object ID")
    if args.native_sha and not re.fullmatch(r"[0-9a-f]{64}", args.native_sha):
        raise ValueError("--native-sha must be a lowercase SHA-256")
    output.mkdir(parents=True, exist_ok=False)
    runner = output / "supervisor.py"
    shutil.copyfile(Path(__file__), runner)
    request = {"kind": KIND, "version": VERSION, "run_id": uuid.uuid4().hex, "created_at": utc_now(),
               "source": str(source), "git_sha": args.git_sha, "python": str(python),
               "native_sha256": args.native_sha, "lane": "native" if args.native_sha else "no-native",
               "output": str(output), "runner_sha256": file_hash(runner),
               "thread_env": THREAD_ENV, "protocol": "full-pytest-one-atomic-process", "detached": args.detach}
    atomic_json(output / "request.json", request)
    if args.start_paused:
        atomic_json(output / "pause-request.json", {"requested_at": utc_now(), "request_id": uuid.uuid4().hex})
    command = [str(python), str(runner), "_worker", str(output / "request.json")]
    try:
        with (output / "supervisor.log").open("x", encoding="utf-8") as log:
            child = subprocess.Popen(command, cwd=source, env=child_environment(source), stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, close_fds=True, start_new_session=args.detach)
        atomic_json(output / "launch.json", {"command": command, "pid": child.pid, "worker_identity": process_identity(child.pid), "launched_at": utc_now(), "detached": args.detach})
        if args.detach:
            return {"state": "launched", "pid": child.pid, "passed": False, "output": str(output)}
        code = child.wait()
        result = observation(output)
        if not (output / "result.json").exists():
            result.update(state="interrupted", exit_code=code or 1, passed=False)
        return result
    except BaseException as exc:
        atomic_json(output / "launch-error.json", {"at": utc_now(), "error": f"{type(exc).__name__}: {exc}"})
        raise


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run", help="Run the fixed full native/no-native Python lane")
    run.add_argument("--source", type=Path, required=True)
    run.add_argument("--git-sha", required=True)
    run.add_argument("--python", type=Path, required=True)
    native = run.add_mutually_exclusive_group(required=True)
    native.add_argument("--native-sha")
    native.add_argument("--no-native", action="store_true")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--detach", action="store_true")
    run.add_argument("--start-paused", action="store_true")
    for name in ("status", "pause", "resume"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] in ("_worker", "_driver"):
        request = read_json(Path(argv[1]))
        return worker(request) if argv[0] == "_worker" else driver(request)
    args = parser().parse_args(argv)
    try:
        if args.action == "run":
            result = launch(args)
        elif args.action == "status":
            result = observation(args.output.resolve())
        else:
            result = control(args.output.resolve(), args.action)
        print(json.dumps(result, sort_keys=True, indent=2))
        return result.get("exit_code", 0)
    except (ValueError, OSError, subprocess.SubprocessError, ET.ParseError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "passed": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
