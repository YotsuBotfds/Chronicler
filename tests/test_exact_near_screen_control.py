"""Tiny stdlib control contracts; no compiler, native import, network or World.

Run directly with Python -I -B. The guard refuses all child launches and source
simulation imports. C60's already-qualified ownership algorithm is source-reused;
these tests exercise this owner's failure classification and evidence boundary.
"""
from __future__ import annotations
import contextlib
import copy
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class SourceGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"chronicler", "chronicler_agents", "numpy", "pyarrow"}:
            raise AssertionError("control contract attempted simulation/native import")
        return None


def refused(*args, **kwargs):
    raise AssertionError("control contract attempted child process or network")


_guard = SourceGuard()
sys.meta_path.insert(0, _guard)
try:
    with patch.object(subprocess, "Popen", refused), patch.object(socket, "socket", refused):
        spec = importlib.util.spec_from_file_location("exact_near_test_owner", SCRIPTS / "run_exact_near_screen.py")
        O = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(O)
finally:
    sys.meta_path.remove(_guard)


def context():
    result = dict(O.CAPS, GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted", GITHUB_EVENT_NAME="push",
        GITHUB_REPOSITORY="YotsuBotfds/Chronicler", GITHUB_REF="refs/heads/" + O.BRANCH,
        GITHUB_JOB="synthetic-screen", GITHUB_RUN_ATTEMPT="1", GITHUB_RUN_ID="12345", GITHUB_SHA="a" * 40,
        GITHUB_WORKFLOW_REF="YotsuBotfds/Chronicler/" + O.WORKFLOW + "@refs/heads/" + O.BRANCH)
    return result


def records(rejected=False):
    rows = [{"kind": "header", "version": 1, "synthetic_only": True, "cases": 15, "pairs": 5,
        "crossover": 256, "wall_seconds_cap": 60, "cpu_seconds_cap": 60, "rss_kib_cap": 524288}]
    for case in O.CASES:
        rows.append({"kind": "parity", "case": case, "route": "Grid", "ordered_near_d2_fnv": "a" * 16,
            "old_distances": 10, "new_distances": 5, "new_words": 2, "near_results": 1,
            "later_far": 1, "incest": 0, "hostile": 0, "valid": 0})
        new = 110001 if rejected and case == "dense4096" else 80000
        for pair in range(5):
            for arm in (("old", "candidate") if pair % 2 == 0 else ("candidate", "old")):
                rows.append({"kind": "sample", "case": case, "pair": pair, "arm": arm, "route": "Grid",
                    "setup_ns": 100, "query_ns": 100, "total_ns_with_drop": 100000 if arm == "old" else new,
                    "cpu_ticks": 0, "peak_process_rss_kib": 100, "index_live_bytes": 0,
                    "index_peak_bytes": 0, "scratch_capacity_bytes": 0, "words": 0, "distances": 0, "gathered": 0})
        limit = 90000 if case in ("spread1024", "spread4096") else 105000
        if case in ("empty0", "singleton1", "small16", "spread255", "spread256", "nan1024", "infinity1024"):
            limit += 5000
        rows.append({"kind": "decision", "case": case, "old_median_ns": 100000,
            "candidate_median_ns": new, "limit_ns": limit, "pass": new <= limit})
    rows.append({"kind": "final", "complete_cases": 15, "samples": 150,
        "accepted_for_later_planner_work": not rejected, "production_promoted": False, "worlds": 0})
    return rows


def encoded(rows, rejected=False):
    summary = "test result: FAILED. 0 passed; 1 failed;" if rejected else "test result: ok. 1 passed; 0 failed;"
    return ("\n".join("EXACT_NEAR " + json.dumps(row, allow_nan=False) for row in rows) + "\n" + summary + "\n").encode()


class ControlContracts(unittest.TestCase):
    def setUp(self):
        self.guard_stack = contextlib.ExitStack()
        self.guard_stack.enter_context(patch.object(subprocess, "Popen", refused))
        self.guard_stack.enter_context(patch.object(socket, "socket", refused))
        self.guard = SourceGuard(); sys.meta_path.insert(0, self.guard)
        self.addCleanup(sys.meta_path.remove, self.guard)
        self.addCleanup(self.guard_stack.close)

    def test_exact_context_and_every_authority_boundary(self):
        env = context(); self.assertEqual(O.require_context(env)["GITHUB_RUN_ATTEMPT"], "1")
        for key in env:
            with self.subTest(key=key), self.assertRaises(ValueError):
                O.require_context({**env, key: "different"})
        for value in ("2", "01", "", "0"):
            with self.subTest(attempt=value), self.assertRaises(ValueError):
                O.require_context({**env, "GITHUB_RUN_ATTEMPT": value})

    def test_complete_positive_and_negative_are_distinct(self):
        good = O.screen_result(encoded(records()), 0)
        bad = O.screen_result(encoded(records(True), True), 101)
        self.assertTrue(good["screen_accepted"])
        self.assertTrue(bad["execution_complete"])
        self.assertFalse(bad["screen_accepted"])
        for status in (124, 137, 1, -15, True):
            with self.subTest(status=status), self.assertRaises(ValueError):
                O.screen_result(encoded(records(True), True), status)

    def test_partial_missing_duplicate_and_reordered_rows_refuse(self):
        base = records()
        variants = [base[:-1], base[1:], base + [base[-1]], base[:3] + base[4:], base[:3] + [base[2]] + base[3:]]
        changed = copy.deepcopy(base); changed[2], changed[3] = changed[3], changed[2]; variants.append(changed)
        changed = copy.deepcopy(base); changed[1]["case"] = "unregistered"; variants.append(changed)
        for index, rows in enumerate(variants):
            with self.subTest(index=index), self.assertRaises((ValueError, KeyError)):
                O.screen_result(encoded(rows), 0)

    def test_medians_fixed_thresholds_types_and_exit_cannot_contradict(self):
        base = records()
        for selector, key, value in (("decision", "pass", False), ("decision", "limit_ns", 999999),
                ("sample", "pair", True), ("sample", "total_ns_with_drop", -1),
                ("sample", "peak_process_rss_kib", 524289), ("header", "synthetic_only", 1),
                ("final", "accepted_for_later_planner_work", False)):
            rows = copy.deepcopy(base)
            next(row for row in rows if row["kind"] == selector)[key] = value
            with self.subTest(selector=selector, key=key), self.assertRaises(ValueError):
                O.screen_result(encoded(rows), 0)
        with self.assertRaises(ValueError): O.screen_result(encoded(records()), 101)
        with self.assertRaises(ValueError): O.screen_result(encoded(records(True), True), 0)

    def test_json_duplicate_nonfinite_and_oversized_intake_refuse(self):
        for raw in (b'{"kind":"sample","kind":"final"}', b'{"value":NaN}', b'{"value":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): O.strict_json(raw)
        with self.assertRaises(ValueError): O.screen_result(b"x" * (O.P.MAX_LOG_BYTES + 1), 0)

    def test_compiler_executable_must_be_unique_regular_and_under_fresh_target(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); target = root / "target"; target.mkdir(); binary = target / "test"; binary.write_bytes(b"not executable")
            row = {"reason": "compiler-artifact", "profile": {"test": True}, "executable": str(binary), "target": {"name": "chronicler_agents"}}
            data = json.dumps(row).encode() + b"\n"
            self.assertEqual(O.binary_from_build(b"compiler progress\n" + data, target), binary)
            for bad in (b"", data + data):
                with self.assertRaises(ValueError): O.binary_from_build(bad, target)
            outside = root / "outside"; outside.write_bytes(b"outside")
            row["executable"] = str(outside)
            with self.assertRaises(ValueError): O.binary_from_build(json.dumps(row).encode(), target)
            link = target / "link"; link.symlink_to(binary); row["executable"] = str(link)
            with self.assertRaises(ValueError): O.binary_from_build(json.dumps(row).encode(), target)

    def test_empty_proc_scan_requires_actual_kernel_echild(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw); children = path / "self/task/7/children"; children.parent.mkdir(parents=True); children.write_bytes(b"")
            def echild(*args): raise ChildProcessError()
            self.assertEqual(O.P.direct_children(proc_root=path, process_id=7, waitid_fn=echild), [])
            with self.assertRaises(ValueError): O.P.direct_children(proc_root=path, process_id=7, waitid_fn=lambda *args: None)
            children.write_bytes(b"20 20")
            with self.assertRaises(ValueError): O.P.direct_children(proc_root=path, process_id=7, waitid_fn=echild)

    def test_light_pack_retains_bounded_excerpts_and_explicit_omissions(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "light").mkdir(); (root / "logs").mkdir()
            (root / "logs/build.log").write_bytes(b"a" * (O.MAX_LOG_COPY + 100))
            report = {"status": "incomplete", "execution_complete": False, "screen_accepted": False}
            O.stage_light(root, report)
            saved = json.loads((root / "light/terminal.json").read_text())
            self.assertTrue(saved["log_publication"][0]["middle_omitted"])
            self.assertFalse(saved["execution_complete"])
            self.assertLess((root / "light/build.log").stat().st_size, O.MAX_LOG_COPY + 100)
            (root / "logs/unsafe.log").symlink_to(root / "logs/build.log")
            with self.assertRaises(ValueError): O.stage_light(root, report)

    def test_early_build_refusal_always_closes_negative_after_lease(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "exact-marriage-screen"; (root / "light").mkdir(parents=True)
            (root / "light/terminal.json").write_text('{"status":"incomplete"}')
            state = {"lease_exited": False}
            @contextlib.contextmanager
            def lease():
                try: yield object()
                finally: state["lease_exited"] = True
            class Cancellation:
                def __enter__(self): return self
                def check(self): pass
                def __exit__(self, *args): pass
            class Supervisor:
                cleanup_complete = True
                def command(self, label, *args, **kwargs):
                    self.assert_trace = kwargs["trace"] is False
                    raise O.P.B.BridgeRefused("synthetic build refusal")
            supervisor = Supervisor()
            env = {**context(), "RUNNER_TEMP": raw, "GITHUB_WORKSPACE": str(SCRIPTS.parent)}
            original_identity = O.file_identity
            def identity(path, *args):
                if Path(path).name == "wealth_floor_build_resources.py": return {"sha256": O.RESOURCE_SHA}
                if Path(path).name == "wealth_floor_hosted_deployment.py": return {"sha256": O.DEPLOYMENT_SHA}
                return original_identity(path, *args)
            with patch.dict(os.environ, env, clear=True), patch.object(O, "hosted_vm_precondition", return_value={}), \
                    patch.object(O.platform, "python_version", return_value="3.13.5"), patch.object(O.os, "sched_getaffinity", return_value={2}), \
                    patch.object(O.os, "sched_setaffinity"), patch.object(O, "source_snapshot", return_value={"files": {}}), \
                    patch.object(O, "runtime_snapshot", return_value={}), patch.object(O, "file_identity", side_effect=identity), \
                    patch.object(O, "final_files", return_value={"errors": {}, "source": {}}), \
                    patch.object(O, "admission", return_value={"admitted": True}), patch.object(O.P, "direct_children", return_value=[]), \
                    patch.object(O.P, "SubreaperLease", side_effect=lease), patch.object(O.P, "Cancellation", Cancellation), \
                    patch.object(O.P, "make_supervisor", return_value=supervisor):
                self.assertEqual(O.run(), 1)
            terminal = json.loads((root / "light/terminal.json").read_text())
            self.assertTrue(state["lease_exited"])
            self.assertTrue(supervisor.assert_trace)
            self.assertEqual(terminal["status"], "incomplete")
            self.assertFalse(terminal["execution_complete"])
            self.assertFalse(terminal["screen_accepted"])
            self.assertTrue(terminal["supervisor_cleanup_complete"])
            self.assertIn("build", terminal["phases_reached"])


    def test_complete_outcome_loses_qualification_on_cleanup_identity_or_late_floor_failure(self):
        for mode in ("accepted", "rejected", "lease_failure", "identity_drift", "post_pack_floor"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as raw:
                task = Path(raw); root = task / "exact-marriage-screen"; (root / "light").mkdir(parents=True)
                (root / "light/terminal.json").write_text('{"status":"incomplete"}')
                target = task / "exact-marriage-target"; binary = target / "test-binary"
                @contextlib.contextmanager
                def lease():
                    yield object()
                    if mode == "lease_failure": raise O.P.B.BridgeRefused("synthetic lease cleanup failure")
                class Cancellation:
                    def __enter__(self): return self
                    def check(self): pass
                    def __exit__(self, *args): pass
                class Supervisor:
                    cleanup_complete = True
                    def command(self, label, *args, **kwargs):
                        if label == "contracts": return b"test result: ok. 6 passed; 0 failed; 1 ignored;"
                        if label == "original-radius": return b"test result: ok. 1 passed; 0 failed; 0 ignored;"
                        if label == "screen":
                            (root / "progress.jsonl").write_text(json.dumps({"event": "child_exit", "label": "screen",
                                "returncode": 101 if mode == "rejected" else 0}) + "\n")
                            return encoded(records(mode == "rejected"), mode == "rejected")
                        return b"synthetic compiler intake"
                    def check(self, **kwargs): pass
                original_identity = O.file_identity
                runtime_path = str(Path(sys.executable).resolve())
                runtime_identity = original_identity(Path(runtime_path))
                runtime = {"tools": {}, "python_executable": runtime_path, "python_library": runtime_path,
                    "python_executable_identity": runtime_identity, "python_library_identity": runtime_identity}
                def compile_result(*args):
                    target.mkdir(); binary.write_bytes(b"synthetic bytes; never executable")
                    return binary
                def final_files(*args):
                    result = {"source": {}, "binary": {"path": str(binary), **original_identity(binary)},
                        "runtime_files": {runtime_path: runtime_identity}, "errors": {}}
                    if mode == "identity_drift": result["binary"]["sha256"] = "f" * 64
                    return result
                def identity(path, *args):
                    if Path(path).name == "wealth_floor_build_resources.py": return {"sha256": O.RESOURCE_SHA}
                    if Path(path).name == "wealth_floor_hosted_deployment.py": return {"sha256": O.DEPLOYMENT_SHA}
                    return original_identity(path, *args)
                count = [0]
                def admission(*args):
                    count[0] += 1
                    return {"admitted": mode != "post_pack_floor" or count[0] != 4}
                env = {**context(), "RUNNER_TEMP": raw, "GITHUB_WORKSPACE": str(SCRIPTS.parent)}
                with patch.dict(os.environ, env, clear=True), patch.object(O, "hosted_vm_precondition", return_value={}), \
                        patch.object(O.platform, "python_version", return_value="3.13.5"), patch.object(O.os, "sched_getaffinity", return_value={2}), \
                        patch.object(O.os, "sched_setaffinity"), patch.object(O, "source_snapshot", return_value={"files": {}}), \
                        patch.object(O, "runtime_snapshot", return_value=runtime), patch.object(O, "file_identity", side_effect=identity), \
                        patch.object(O, "final_files", side_effect=final_files), patch.object(O, "admission", side_effect=admission), \
                        patch.object(O, "binary_from_build", side_effect=compile_result), patch.object(O, "linkage_snapshot", return_value={}), \
                        patch.object(O.P, "direct_children", return_value=[]), patch.object(O.P, "SubreaperLease", side_effect=lease), \
                        patch.object(O.P, "Cancellation", Cancellation), patch.object(O.P, "make_supervisor", return_value=Supervisor()):
                    exit_code = O.run()
                terminal = json.loads((root / "light/terminal.json").read_text())
                expected = "complete-accepted" if mode == "accepted" else "complete-rejected" if mode == "rejected" else "incomplete"
                self.assertEqual(terminal["status"], expected)
                self.assertEqual(terminal["execution_complete"], mode in ("accepted", "rejected"))
                self.assertEqual(terminal["screen_accepted"], mode == "accepted")
                self.assertEqual(exit_code, 0 if mode == "accepted" else 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
