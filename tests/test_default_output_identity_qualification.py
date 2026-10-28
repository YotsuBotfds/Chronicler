"""Pure contracts for the fixed export-parity qualification helper."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/default_output_identity_qualification.py"
spec = importlib.util.spec_from_file_location("default_output_identity_qualification", SCRIPT)
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


def sample(name="off_s42"):
    cli, _ = qualification.CASES[name]
    value = lambda flag, fallback=None: cli[cli.index(flag) + 1] if flag in cli else fallback
    turns, seed = int(value("--turns")), int(value("--seed"))
    world = {"turn": turns, "seed": seed, "agent_mode": None if value("--agents") == "off" else value("--agents"),
             "regions": [{}] * int(value("--regions", 8)),
             "civilizations": [{}] * int(value("--civs", 4))}
    bundle = {"world_state": deepcopy(world), "metadata": {"seed": seed, "total_turns": turns},
              "history": [{"turn": turn} for turn in range(1, turns + 1)]}
    files = set(qualification.COMMON) | {"memories_A.json"}
    if value("--agents") == "hybrid":
        files.add("agent_events.arrow")
    if "--validation-sidecar" in cli:
        files.update(qualification.SIDECARS)
    return files, world, bundle


class QualificationContracts(unittest.TestCase):
    def test_matrix_is_exact_and_has_fixed_budget(self):
        self.assertEqual(len(qualification.CASES), 9)
        turns = sum(int(cli[cli.index("--turns") + 1]) for cli, _ in qualification.CASES.values())
        self.assertEqual(turns * 2, 3200)
        qualification.require_matrix(SCRIPT.parent / "turn_speed_identity.py")
        qualification.require_case_sets(qualification.CASES, qualification.CASES)
        for baseline, candidate in (
            (set(qualification.CASES) - {"off_s42"}, set(qualification.CASES)),
            (set(qualification.CASES), set(qualification.CASES) | {"extra"}),
        ):
            with self.assertRaises(qualification.Refusal):
                qualification.require_case_sets(baseline, candidate)

    def test_every_registered_case_requires_complete_exports_and_horizon(self):
        for name in qualification.CASES:
            with self.subTest(name=name):
                files, state, bundle = sample(name)
                before = deepcopy((files, state, bundle))
                summary = qualification.case_contract(name, files, state, bundle)
                self.assertEqual((files, state, bundle), before)
                self.assertGreater(summary["turns"], 0)
                for missing in qualification.COMMON:
                    with self.assertRaises(qualification.Refusal):
                        qualification.case_contract(name, files - {missing}, state, bundle)
                if "hybrid" in name or name.startswith("scaled"):
                    with self.assertRaises(qualification.Refusal):
                        qualification.case_contract(name, files - {"agent_events.arrow"}, state, bundle)
                with self.assertRaises(qualification.Refusal):
                    qualification.case_contract(name, files - {"memories_A.json"}, state, bundle)
                if "--validation-sidecar" in qualification.CASES[name][0]:
                    for missing in qualification.SIDECARS:
                        with self.assertRaises(qualification.Refusal):
                            qualification.case_contract(name, files - {missing}, state, bundle)

    def test_successful_exit_cannot_substitute_for_completed_worlds(self):
        files, state, bundle = sample()
        mutations = [
            lambda s, b: s.update(turn=299),
            lambda s, b: s.update(seed=7),
            lambda s, b: s.update(agent_mode="hybrid"),
            lambda s, b: s.update(regions=[]),
            lambda s, b: b["metadata"].update(total_turns=299),
            lambda s, b: b["history"].pop(),
            lambda s, b: b["history"].__setitem__(0, {"turn": 2}),
        ]
        for mutate in mutations:
            s, b = deepcopy(state), deepcopy(bundle)
            mutate(s, b)
            with self.assertRaises(qualification.Refusal):
                qualification.case_contract("off_s42", files, s, b)

    def test_only_one_root_metadata_timestamp_can_be_normalized(self):
        qualification.require_stamp(b'{"metadata":{"generated_at":"2026-10-28"}}')
        for raw in (
            b'{"metadata":{}}',
            b'{"generated_at":"x","metadata":{}}',
            b'{"metadata":{"generated_at":"x"},"history":[{"generated_at":"y"}]}',
            b'{"metadata":{"generated_at":"x","generated_at":"y"}}',
            b'{"metadata":{"generated_at":null}}',
            b'{"metadata":{"generated_at":"x"},"other":1e9999}',
        ):
            with self.subTest(raw=raw), self.assertRaises((qualification.Refusal, ValueError)):
                qualification.require_stamp(raw)

    def test_resource_floors_are_not_rounded_down_or_waived(self):
        gib = qualification.GIB
        for disk, ram in ((12, 2), (6, 2), (3, 1)):
            qualification.admit({"disk_free": disk * gib, "ram_available": ram * gib}, disk, ram)
            for observation in (
                {"disk_free": disk * gib - 1, "ram_available": ram * gib},
                {"disk_free": disk * gib, "ram_available": ram * gib - 1},
            ):
                with self.assertRaises(qualification.Refusal):
                    qualification.admit(observation, disk, ram)

    def test_inventory_keeps_ignored_comparator_files_and_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values = {"run_manifest.json": b'{"source":"baseline"}', "run.log": b"",
                      "state.json": b'{"value":1}\n'}
            for name, raw in values.items():
                (root / name).write_bytes(raw)
            inventory = qualification.payload_inventory(root)
            self.assertEqual(set(inventory), set(values))
            for name, raw in values.items():
                self.assertEqual(inventory[name], {"bytes": len(raw),
                                 "sha256": hashlib.sha256(raw).hexdigest()})

    def test_strict_reader_rejects_ambiguous_or_nonfinite_input(self):
        for raw in (b'{"a":1,"a":2}', b'NaN', b'Infinity', b'1e9999'):
            with self.assertRaises((qualification.Refusal, ValueError)):
                qualification.strict_json(raw)
        self.assertEqual(qualification.strict_json(b'{"finite":1e308}'), {"finite": 1e308})


    def test_off_serialized_none_is_valid_only_for_explicit_off_case(self):
        files, state, bundle = sample()
        self.assertIsNone(state["agent_mode"])
        qualification.case_contract("off_s42", files, state, bundle)
        state["agent_mode"] = bundle["world_state"]["agent_mode"] = "off"
        qualification.case_contract("off_s42", files, state, bundle)
        files, state, bundle = sample("hybrid_s42")
        state["agent_mode"] = None
        with self.assertRaises(qualification.Refusal):
            qualification.case_contract("hybrid_s42", files, state, bundle)

    def test_missing_cgroup_memory_visibility_is_not_unbounded_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            memory, membership, group = root / "meminfo", root / "cgroup", root / "group"
            memory.write_text("MemAvailable: 2097152 kB\n")
            membership.write_text("0::/\n")
            group.mkdir()
            kwargs = dict(meminfo=memory, process_cgroup=membership, cgroup_root=group)
            with self.assertRaises(qualification.Refusal):
                qualification.resources(root, **kwargs)
            (group / "memory.max").write_text("max\n")
            with self.assertRaises(qualification.Refusal):
                qualification.resources(root, **kwargs)
            (group / "memory.current").write_text("123\n")
            result = qualification.resources(root, **kwargs)
            self.assertEqual(result["ram_available"], 2 * qualification.GIB)
            self.assertEqual(result["cgroup_limits"][0]["max"], "max")
            (group / "memory.max").write_text(str(qualification.GIB))
            (group / "memory.current").write_text(str(qualification.GIB // 2))
            result = qualification.resources(root, **kwargs)
            self.assertEqual(result["ram_available"], qualification.GIB // 2)

    def test_initial_owner_capture_failure_still_cleans_started_child(self):
        self._cleanup_counterexample(initial_capture_fails=True)

    def test_owned_descendant_in_another_process_group_is_cleaned(self):
        self._cleanup_counterexample(initial_capture_fails=False)

    def _cleanup_counterexample(self, initial_capture_fails):
        if not (all(hasattr(qualification.os, name) for name in ("waitid", "pidfd_open"))
                and hasattr(qualification.signal, "pidfd_send_signal")):
            self.skipTest("Linux waitid/pidfd process APIs are required")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "logs").mkdir()
            supervisor = qualification.Supervisor(root, time.monotonic() + 30)
            supervisor.admission = lambda *args: None
            supervisor.event = mock.Mock()
            child = mock.Mock(pid=100, returncode=None)
            live = {"value": True}
            owner = {"pid": 100, "state": "R" if initial_capture_fails else "Z",
                     "pgrp": 100, "session": 100, "birth": 10}
            member = owner if initial_capture_fails else {
                "pid": 101, "state": "R", "pgrp": 101, "session": 100, "birth": 11}
            calls = {"value": 0}

            def process_stat(pid):
                calls["value"] += 1
                if initial_capture_fails and calls["value"] == 1:
                    return None
                return owner if pid == 100 else member

            def send_signal(descriptor, sig):
                live["value"] = False

            def wait(timeout):
                self.assertFalse(live["value"])
                child.returncode = 0
                return 0

            child.wait.side_effect = wait
            with mock.patch.object(qualification.subprocess, "Popen", return_value=child), \
                 mock.patch.object(qualification, "boot_id", return_value="fixed-boot"), \
                 mock.patch.object(qualification, "process_stat", side_effect=process_stat), \
                 mock.patch.object(qualification, "session_live", side_effect=lambda sid: [member] if live["value"] else []), \
                 mock.patch.object(qualification.os, "waitid", return_value=object()), \
                 mock.patch.object(qualification.os, "pidfd_open", return_value=123) as open_pidfd, \
                 mock.patch.object(qualification.os, "close"), \
                 mock.patch.object(qualification.signal, "pidfd_send_signal", side_effect=send_signal), \
                 mock.patch.object(qualification.time, "sleep"):
                with self.assertRaises(qualification.Refusal):
                    supervisor.command("fixture", ["fixture"], {}, root)
            self.assertFalse(live["value"])
            self.assertTrue(supervisor.cleanup_complete)
            child.wait.assert_called_once()
            open_pidfd.assert_called_with(member["pid"])

    def test_inventory_failure_cannot_leave_a_positive_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = {"qualified": True}
            with mock.patch.object(qualification, "payload_inventory", side_effect=OSError("injected read failure")):
                result = qualification.finish_evidence(root, report, True, time.monotonic() + 60)
            self.assertFalse(result)
            saved = qualification.strict_json((root / "result.json").read_bytes())
            self.assertFalse(saved["qualified"])
            self.assertIn("injected read failure", saved["inventory_error"])

    def test_inventory_write_failure_cannot_leave_a_positive_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_write = qualification.write

            def failing_write(path, value):
                if Path(path).name == "inventory.json":
                    raise OSError("injected inventory write failure")
                real_write(path, value)

            with mock.patch.object(qualification, "write", side_effect=failing_write):
                self.assertFalse(qualification.finish_evidence(root, {"qualified": True}, True, time.monotonic() + 60))
            saved = qualification.strict_json((root / "result.json").read_bytes())
            self.assertFalse(saved["qualified"])
            self.assertIn("injected inventory write failure", saved["inventory_error"])

    def test_uncertain_cleanup_withholds_inventory_and_positive_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(qualification, "payload_inventory") as inventory:
                self.assertFalse(qualification.finish_evidence(root, {"qualified": True}, False, time.monotonic() + 60))
            inventory.assert_not_called()
            self.assertFalse(qualification.strict_json((root / "result.json").read_bytes())["qualified"])

    def test_inventory_deadline_overrun_is_censored_and_not_capped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deadline = time.monotonic()
            with mock.patch.object(qualification.time, "monotonic", return_value=deadline + 2):
                self.assertFalse(qualification.finish_evidence(root, {"qualified": True}, True, deadline))
            saved = qualification.strict_json((root / "result.json").read_bytes())
            self.assertFalse(saved["qualified"])
            self.assertGreater(saved["elapsed_wall_seconds"], qualification.WALL_SECONDS)


    def test_valid_nested_cgroup_allows_kernel_root_current_without_max(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            memory, membership, group = root / "meminfo", root / "cgroup", root / "group"
            memory.write_text("MemAvailable: 2097152 kB\n")
            membership.write_text("0::/leaf\n")
            leaf = group / "leaf"
            leaf.mkdir(parents=True)
            (group / "memory.current").write_text("100\n")
            (leaf / "memory.max").write_text(str(qualification.GIB))
            (leaf / "memory.current").write_text(str(qualification.GIB // 2))
            result = qualification.resources(root, meminfo=memory,
                process_cgroup=membership, cgroup_root=group)
            self.assertEqual(result["ram_available"], qualification.GIB // 2)
            self.assertEqual(result["cgroup_limits"][-1]["max"], "root-unbounded")

    def test_missing_declared_cgroup_is_not_replaced_by_readable_ancestor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            memory, membership, group = root / "meminfo", root / "cgroup", root / "group"
            memory.write_text("MemAvailable: 2097152 kB\n")
            membership.write_text("0::/missing/leaf\n")
            group.mkdir()
            (group / "memory.max").write_text("max\n")
            (group / "memory.current").write_text("100\n")
            with self.assertRaises(qualification.Refusal):
                qualification.resources(root, meminfo=memory,
                    process_cgroup=membership, cgroup_root=group)

    def test_root_current_only_refuses_without_any_actual_max_current_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            memory, membership, group = root / "meminfo", root / "cgroup", root / "group"
            memory.write_text("MemAvailable: 2097152 kB\n")
            membership.write_text("0::/\n")
            group.mkdir()
            (group / "memory.current").write_text("100\n")
            with self.assertRaises(qualification.Refusal):
                qualification.resources(root, meminfo=memory,
                    process_cgroup=membership, cgroup_root=group)


if __name__ == "__main__":
    unittest.main()
