"""Pure contracts for the fixed export-parity qualification helper."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/default_output_identity_qualification.py"
spec = importlib.util.spec_from_file_location("default_output_identity_qualification", SCRIPT)
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


def sample(name="off_s42"):
    cli, _ = qualification.CASES[name]
    value = lambda flag, fallback=None: cli[cli.index(flag) + 1] if flag in cli else fallback
    turns, seed = int(value("--turns")), int(value("--seed"))
    world = {"turn": turns, "seed": seed, "agent_mode": value("--agents"),
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


if __name__ == "__main__":
    unittest.main()
