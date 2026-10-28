"""Pure full-gate controller contracts: no native imports or world execution."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/cloud_full_gate_qualification.py"
spec = importlib.util.spec_from_file_location("cloud_full_gate_qualification", SCRIPT)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
HASH = "0" * 64


def records(worldgen="template", stage="full", gate_pass=True):
    config = worker.expected(worldgen, stage)
    seeds = list(range(42, 42 + config["seed_count"]))
    source, native = {"git_sha": worker.BASE}, {"sha256": HASH}
    run = dict(profile=config["profile"], worldgen=worldgen, seeds=len(seeds), turns=config["turns"],
        seed_start=42, parallel=2, ablation_forks=config["fork_count"],
        ablation_fork_turns=config["fork_turns"], ablation_arms=config["arms"],
        require_strict_regression=config["require_strict_regression"], causal_oracles_required=False,
        ablation_oracles=True, exploratory_comparison=False, baseline_report_path=None, comparison_status=None,
        gate_exit_code=0 if gate_pass else 2, gate_status="PASS" if gate_pass else "FAIL")
    batch = dict(status="complete", seeds=seeds, turns=config["turns"], source=source, native=native,
        simulation=dict(agents="hybrid", regions=config["regions"], civs=config["civs"],
                        worldgen=None if worldgen == "template" else "procedural"),
        runs=[dict(seed=seed, dir=f"seed_{seed}", total_turns=config["turns"],
                   files={f"seed_{seed}/" + name: HASH for name in worker.PARENT_REQUIRED}) for seed in seeds])
    forks = []
    for arm in config["arms"]:
        for seed in seeds:
            for turn in config["fork_turns"]:
                forks.append(dict(arm=arm, seed=seed, fork_turn=turn, total_turns=turn + 22,
                    decision_ablation=dict(name=arm, start_turn=turn + 1, forked_at=turn + 1),
                    files={"agent_events.arrow": HASH, "fork.json": HASH},
                    dir=f"{arm}/seed_{seed}/fork_{turn}"))
    ablation = dict(status="complete", schema_version=2, design=2, seeds=seeds,
        arms=config["arms"], fork_turns=config["fork_turns"], window_turns=20,
        fork_count=config["fork_count"], forks=forks, source=source, native=native)
    report = dict(profile=config["profile"], causal_oracles_required=False,
                  batch_manifest={"status": "verified"}, ablation_arms={"status": "verified"})
    decision = dict(profile=config["profile"], require_strict_regression=config["require_strict_regression"],
                    causal_oracles_required=False, ok=gate_pass, exit_code=0 if gate_pass else 2)
    return run, batch, ablation, report, decision, config


class FullGateContracts(unittest.TestCase):
    def validate(self, values):
        return worker.validate_records(*values, worker.BASE, HASH)

    def test_fixed_full_and_smoke_exposure(self):
        template, procedural = worker.expected("template"), worker.expected("procedural")
        self.assertEqual((template["seed_count"], template["turns"], template["fork_count"]), (200, 500, 1600))
        self.assertEqual((procedural["seed_count"], procedural["turns"], procedural["fork_count"]), (100, 300, 1800))
        self.assertEqual(procedural["fork_turns"], list(range(100, 280, 20)))
        self.assertEqual(procedural["checkpoint_turns"], list(range(101, 281, 20)))
        exposures = []
        for worldgen in ("template", "procedural"):
            smoke = worker.expected(worldgen, "smoke")
            self.assertEqual((smoke["profile"], smoke["seed_count"], smoke["turns"],
                              smoke["fork_count"], smoke["checkpoint_turns"]),
                             ("subset", 2, 125, 4, [101]))
            self.assertFalse(smoke["require_strict_regression"])
            exposures.append(2 * (smoke["seed_count"] * smoke["turns"] + smoke["fork_count"] * 21))
        self.assertEqual(sum(exposures), 1336)
        self.assertEqual(worker.COHORT_SECONDS, 330 * 60)
        self.assertEqual(worker.SMOKE_SECONDS, 80 * 60)

    def test_fixed_commands_have_no_intervention_or_mismatch_passthrough(self):
        source = Path("/frozen/source")
        command = worker.cohort_command("/venv/python", source, "procedural", Path("/fresh/full"))
        self.assertEqual(command, ["/venv/python", "/frozen/source/scripts/m53b_run_validation.py",
            "--profile", "full", "--worldgen", "procedural", "--parallel", "2",
            "--output-root", "/fresh/full", "--require-strict-regression"])
        smoke = worker.cohort_command("/venv/python", source, "template", Path("/fresh/smoke"), "smoke")
        self.assertEqual(smoke, ["/venv/python", "/frozen/source/scripts/m53b_run_validation.py",
            "--profile", "subset", "--worldgen", "template", "--parallel", "2",
            "--output-root", "/fresh/smoke", "--seed-start", "42", "--seeds", "2", "--turns", "125",
            "--ablation-oracles"])
        self.assertFalse(any("allow-mismatch" in arg or "no-ablation" in arg for arg in command + smoke))

    def test_all_four_schemas_accept_complete_original_pass_and_fail(self):
        for worldgen in ("template", "procedural"):
            for stage in ("full", "smoke"):
                for passed in (True, False):
                    with self.subTest(worldgen=worldgen, stage=stage, passed=passed):
                        values = records(worldgen, stage, passed)
                        before = deepcopy(values)
                        result = self.validate(values)
                        self.assertEqual(values, before)
                        self.assertIs(result["gate_pass"], passed)
                        self.assertEqual(result["gate_exit_code"], 0 if passed else 2)

    def test_duplicate_missing_and_truncated_fork_evidence_refuses(self):
        for mutate in (
            lambda v: v[2]["forks"].pop(),
            lambda v: v[2]["forks"].__setitem__(1, deepcopy(v[2]["forks"][0])),
            lambda v: v[2]["forks"][0].update(total_turns=121),
            lambda v: v[2]["forks"][0].update(fork_turn=100.0),
            lambda v: v[2].update(schema_version=2.0),
            lambda v: v[1]["runs"][0].update(total_turns=499),
            lambda v: v[1]["runs"][0].update(seed=42.0),
        ):
            values = deepcopy(records())
            mutate(values)
            with self.assertRaises(worker.Refusal):
                self.validate(values)

    def test_original_strict_and_causal_policies_are_not_interchangeable(self):
        for mutate in (
            lambda v: v[0].update(require_strict_regression=False),
            lambda v: v[3].update(causal_oracles_required=True),
            lambda v: v[4].update(causal_oracles_required=True),
            lambda v: v[0].update(baseline_report_path="/prior/report.json"),
            lambda v: v[0].update(comparison_status="NO_REGRESSION"),
            lambda v: v[1]["native"].update(sha256="1" * 64),
        ):
            values = deepcopy(records())
            mutate(values)
            with self.assertRaises(worker.Refusal):
                self.validate(values)

    def test_smoke_success_never_claims_full_qualification(self):
        self.assertEqual(worker.outcome_flags("smoke", True, True, False),
                         {"qualified": False, "smoke_pass": True})
        self.assertEqual(worker.outcome_flags("full", True, True, False),
                         {"qualified": False, "smoke_pass": False})
        self.assertEqual(worker.outcome_flags("full", True, True, True),
                         {"qualified": True, "smoke_pass": False})
        self.assertEqual(worker.outcome_flags("smoke", True, False, True),
                         {"qualified": False, "smoke_pass": False})

    def test_330_minute_budget_does_not_reuse_80_minute_label(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = worker.Supervisor(Path(directory), time.monotonic() - 1, 330)
            with self.assertRaisesRegex(worker.Refusal, "330-minute"):
                supervisor.command("forbidden", ["not-launched"], {}, directory)
            self.assertTrue(supervisor.cleanup_complete)

    def test_light_index_excludes_final_receipt_and_preserves_original_bytes(self):
        for stage in ("full", "smoke"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name, original in worker.light_sources(stage).items():
                    path = root / original
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'{"original":true}\n')
                index = worker.copy_light(root, stage)
                self.assertTrue(index["complete"])
                self.assertEqual(set(index["files"]), set(worker.light_sources(stage)))
                self.assertNotIn("result.json", index["files"])
                self.assertEqual(index["file_count"], 9)
                for name, original in worker.light_sources(stage).items():
                    self.assertEqual((root / original).read_bytes(), (root / "light" / name).read_bytes())

    def test_missing_and_oversize_light_records_never_form_complete_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = worker.copy_light(root)
            self.assertFalse(index["complete"])
            self.assertEqual(set(index["missing"]), set(worker.light_sources("full")))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / next(iter(worker.LIGHT_SOURCES.values()))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * 17)
            with mock.patch.object(worker, "MAX_FILE_BYTES", 16):
                with self.assertRaises(worker.Refusal):
                    worker.copy_light(root)

    def test_native_schema_numeric_aliases_refuse(self):
        schemas = {name: dict(version=1, fingerprint="actual", schema_sha256=HASH) for name in worker.CLASS_NAMES}
        native = dict(sha256=HASH, schemas=schemas)
        worker.native_shape(native)
        native["schemas"][worker.CLASS_NAMES[0]]["version"] = True
        with self.assertRaises(worker.Refusal):
            worker.native_shape(native)

    def test_parent_and_fork_hash_crosslinks_match_actual_raw_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch_path = root / "raw/full_gate/batch_42/batch_manifest.json"
            batch_path.parent.mkdir(parents=True)
            batch_path.write_bytes(b"parent-manifest")
            batch = {"runs": [{"files": {"seed_42/bundle.json": HASH}}]}
            ablation = {"plain_manifest_sha256": worker.sha(batch_path), "forks": [
                dict(arm="needs", seed=42, fork_turn=100, dir="needs/seed_42/fork_100",
                     files={"agent_events.arrow": HASH, "fork.json": HASH})]}
            files = {"raw/full_gate/batch_42/seed_42/bundle.json": {"sha256": HASH}}
            for name in ("agent_events.arrow", "fork.json"):
                files["raw/full_gate/ablation_42/needs/seed_42/fork_100/" + name] = {"sha256": HASH}
            inventory = {"files": files}
            worker.check_manifest_hashes(root, batch, ablation, inventory)
            files["raw/full_gate/ablation_42/needs/seed_42/fork_100/fork.json"]["sha256"] = "1" * 64
            with self.assertRaises(worker.Refusal):
                worker.check_manifest_hashes(root, batch, ablation, inventory)


    def test_supervisor_allows_complete_gate_exit_two_only_when_declared(self):
        if not all(hasattr(worker.controls.os, name) for name in ("waitid", "P_PID", "WEXITED", "WNOHANG", "WNOWAIT")):
            self.skipTest("Linux waitid controls required")
        for allowed in ((0, 2), (0,)):
            with self.subTest(allowed=allowed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "logs").mkdir()
                supervisor = worker.controls.Supervisor(root, time.monotonic() + 30, budget_label="330-minute")
                supervisor.admission = lambda *args: None
                supervisor.event = mock.Mock()
                child = mock.Mock(pid=100, returncode=2)
                owner = dict(pid=100, state="Z", pgrp=100, session=100, birth=10)
                with mock.patch.object(worker.controls.subprocess, "Popen", return_value=child), \
                     mock.patch.object(worker.controls, "boot_id", return_value="fixed-boot"), \
                     mock.patch.object(worker.controls, "process_stat", return_value=owner), \
                     mock.patch.object(worker.controls, "session_live", return_value=[]), \
                     mock.patch.object(worker.controls.os, "waitid", return_value=object()):
                    if 2 in allowed:
                        self.assertEqual(supervisor.command("fixture", ["not-executed"], {}, root,
                                                           allowed_exit_codes=allowed), 2)
                    else:
                        with self.assertRaisesRegex(worker.Refusal, "exited 2"):
                            supervisor.command("fixture", ["not-executed"], {}, root)
                self.assertTrue(supervisor.cleanup_complete)
                child.wait.assert_called_once()

    def test_late_positive_copy_failure_invalidates_both_receipts(self):
        for primary, smoke in (("build-manifest.json", False), ("result.json", False), ("result.json", True)):
            with self.subTest(primary=primary, smoke=smoke), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "light").mkdir()
                (root / "light/artifact-index.json").write_text("{}")
                report = dict(qualified=not smoke, smoke_pass=smoke, gate_pass=False if smoke else True)
                real_write = worker.write

                def fail_positive_copy(path, value):
                    positive = value.get("qualified") or value.get("smoke_pass")
                    if Path(path) == root / "light" / primary and positive:
                        raise OSError("injected late positive-copy failure")
                    real_write(path, value)

                with mock.patch.object(worker, "write", side_effect=fail_positive_copy):
                    self.assertFalse(worker.finish_receipts(root, report, primary, time.monotonic() + 60, time.monotonic()))
                self.assertIn("injected late", report["finalization_error"])
                for path in (root / primary, root / "light" / primary):
                    saved = worker.bounded_json(path)
                    self.assertFalse(saved["qualified"])
                    self.assertFalse(saved["smoke_pass"])

    def test_complete_lightweight_total_includes_receipt_and_index_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "light").mkdir()
            (root / "light/artifact-index.json").write_bytes(b"{}")
            (root / "light/data.json").write_bytes(b"raw-proof")
            report = dict(qualified=True)
            positive = dict(report, elapsed_wall_seconds=100.0)
            size = len((json.dumps(positive, indent=2, sort_keys=True) + "\n").encode())
            limit = 2 + len(b"raw-proof") + size - 1
            with mock.patch.object(worker, "MAX_LIGHT_BYTES", limit), \
                 mock.patch.object(worker.time, "monotonic", return_value=100.0):
                self.assertFalse(worker.finish_receipts(root, report, "result.json", 1000.0, 0.0))
            self.assertIn("including receipts", report["finalization_error"])
            self.assertFalse(worker.bounded_json(root / "light/result.json")["qualified"])

    def test_missing_core_parent_sidecar_refuses_even_a_verified_smoke_report(self):
        values = deepcopy(records(stage="smoke"))
        values[1]["runs"][0]["files"].pop("seed_42/validation_needs.arrow")
        with self.assertRaisesRegex(worker.Refusal, "core parent"):
            self.validate(values)


if __name__ == "__main__":
    unittest.main()
