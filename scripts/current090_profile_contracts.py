"""A single metadata-only 110-second hosted preflight, never full collection.

No project/Native/NumPy module or process/network operation is permitted. The
controller runs this leaf under its authenticated owner before input admission.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import importlib.abc
import io
import json
import os
from pathlib import Path
import runpy
import sys
import time
import xml.etree.ElementTree as ET

MODULES = ("tests/test_current090_passive_profile.py", "tests/test_current090_profile_owner.py")
EXPECTED_CASES = 164


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root, out = args.control.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "tests": None, "project_native_imports": [], "blocked_operations": [],
              "source_unchanged": False, "collection_or_setup_failure": True}
    (out / "receipt.json").write_text(json.dumps(report) + "\n")
    paths = [*MODULES, "scripts/current090_passive_profile.py", "scripts/current090_profile_owner.py",
             "scripts/current090_profile_inputs.py", "scripts/current090_profile_contracts.py",
             "scripts/current090_profile_publish.py", "docs/experiments/current090-passive-profile.yml.inactive",
             "scripts/run_python_oracle_checks.py", "docs/experiments/current090-passive-profile-inputs.json"]
    def pins():
        return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}
    before, blocked, log = pins(), [], io.StringIO()
    forbidden = {"chronicler", "chronicler_agents", "numpy", "pyarrow"}
    def loaded(): return sorted(name for name in sys.modules if name.split(".")[0] in forbidden)
    class Guard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in forbidden:
                blocked.append({"import": fullname}); raise RuntimeError("metadata preflight project/native import refused")
    def audit(event, _args):
        if event.startswith("socket.") or event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork"):
            blocked.append({"operation": event}); raise RuntimeError("metadata preflight process/network refused")
    if loaded(): raise RuntimeError("project/native module present before metadata guard")
    sys.meta_path.insert(0, Guard()); sys.addaudithook(audit)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    started = time.monotonic()
    try:
        # Exercise the real registry CLI without pytest collection or any child.
        old_argv = sys.argv; sys.argv = [str(root / "scripts/run_python_oracle_checks.py"), "--list"]
        listed = io.StringIO()
        try:
            with contextlib.redirect_stdout(listed):
                try: runpy.run_path(sys.argv[0], run_name="__main__")
                except SystemExit as exc:
                    if exc.code != 0: raise
        finally: sys.argv = old_argv
        nodes = listed.getvalue().splitlines()
        if any(nodes.count(name) != 1 for name in MODULES): raise RuntimeError("new modules missing/duplicated in --list")
        (out / "oracle-list.txt").write_text(listed.getvalue())
        import pytest
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            code = pytest.main(["-q", "--noconftest", "-p", "no:cacheprovider", "--rootdir=" + str(root),
                "--basetemp=" + str(out / "fixtures"), "--junitxml=" + str(out / "junit.xml"),
                *(str(root / name) for name in MODULES)])
        rows = ET.parse(out / "junit.xml").findall(".//testcase")
        errors = sum(row.find("error") is not None for row in rows)
        failures = sum(row.find("failure") is not None for row in rows)
        skips = sum(row.find("skipped") is not None for row in rows)
        report.update(tests=len(rows), errors=errors, failures=failures, skips=skips, pytest_exit=int(code),
                      collection_or_setup_failure=bool(errors), registry_module_counts={n: nodes.count(n) for n in MODULES})
        report["source_unchanged"] = pins() == before
        report["passed"] = code == 0 and len(rows) == EXPECTED_CASES and errors == failures == skips == 0
    except BaseException as exc:
        report["error_type"] = type(exc).__name__
    finally:
        raw = log.getvalue().encode()
        if len(raw) > 128 * 1024:
            report["log_omitted_bytes"] = len(raw); raw = b""; report["passed"] = False
        (out / "pytest.log").write_bytes(raw)
        report.update(project_native_imports=loaded(), blocked_operations=blocked,
                      before=before, after=pins(), wall_seconds=time.monotonic() - started,
                      runtime_flags={**{name: getattr(sys.flags, name) for name in
                          ("safe_path", "no_user_site", "ignore_environment", "isolated", "hash_randomization")},
                          "cpu_count": os.cpu_count()},
                      guard_scope="All project/Native/NumPy imports blocked; no project factories can be reached.")
        report["passed"] = (report["passed"] and not blocked and not loaded() and report["source_unchanged"]
                            and report["wall_seconds"] <= 110)
        (out / "receipt.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
