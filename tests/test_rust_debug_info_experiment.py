"""Fail-closed checks for the optional Rust qualification evidence tool."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def experiment():
    path = Path(__file__).resolve().parents[1] / "scripts/experiment_rust_debug_info.py"
    spec = importlib.util.spec_from_file_location("rust_debug_info_experiment", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _messages(tool, **profile_changes):
    profile = {"opt_level": "0", "debuginfo": 0, "debug_assertions": True, "overflow_checks": True, "test": True}
    profile.update(profile_changes)
    return "\n".join(json.dumps({"reason": "compiler-artifact", "profile": profile, "features": ["default"],
        "target": {"name": "chronicler_agents" if i == 0 else f"test_{i}",
                   "src_path": str(tool.SOURCE / "chronicler-agents/tests/fixture.rs")},
        "filenames": [], "fresh": False}) for i in range(37))


def test_assertions_overflow_optimization_and_debug_info_are_independent_requirements(experiment):
    assert len(experiment.verify_profiles(_messages(experiment))) == 37
    for changed in ({"debug_assertions": False}, {"overflow_checks": False}, {"opt_level": "3"}, {"debuginfo": 2}):
        with pytest.raises(ValueError, match="effective native crate profile"):
            experiment.verify_profiles(_messages(experiment, **changed))
    with pytest.raises(ValueError, match="missing full"):
        experiment.verify_profiles(_messages(experiment).splitlines()[0])


def test_storage_measurement_counts_hardlink_allocation_once_and_ignores_symlinks(experiment, tmp_path):
    payload = tmp_path / "payload"
    payload.write_bytes(b"a" * 8192)
    os.link(payload, tmp_path / "hardlink")
    (tmp_path / "external").symlink_to(Path(__file__))
    observed = experiment.target_inventory(tmp_path)
    assert observed["files"] == 2 and observed["logical_bytes"] == 16384
    assert observed["allocated_unique_bytes"] == payload.stat().st_blocks * 512


def test_disk_guard_stops_before_floor_while_other_workers_can_still_grow(experiment):
    sample = {"free_bytes": experiment.FLOOR + experiment.STOP_RESERVE - 1,
              "target": {"allocated_unique_bytes": 0}}
    assert "stopping reserve" in experiment.guard_reason(sample)
    sample["free_bytes"] = 8 * experiment.GIB
    sample["target"]["allocated_unique_bytes"] = experiment.TARGET_CAP + 1
    assert "target exceeds" in experiment.guard_reason(sample)


def test_partial_or_filtered_test_log_cannot_claim_full_qualification(experiment):
    with pytest.raises(ValueError, match="full expected"):
        experiment.test_results("Running tests/one.rs (target/test)\ntest one ... ok\ntest result: ok. 1088 passed; 0 failed; 2 ignored; 0 measured; 1 filtered out\n")


def test_successful_child_cannot_hide_a_last_write_over_storage_limit(experiment):
    terminal = {"free_bytes": 8 * experiment.GIB,
                "target": {"allocated_unique_bytes": experiment.TARGET_CAP + 1}}
    with pytest.raises(RuntimeError, match="target exceeds"):
        experiment.verify_stage_completion(0, terminal)
    terminal["target"]["allocated_unique_bytes"] = 0
    terminal["free_bytes"] = experiment.FLOOR
    with pytest.raises(RuntimeError, match="stopping reserve"):
        experiment.verify_stage_completion(0, terminal)


def test_matching_source_does_not_allow_prepare_execute_environment_drift(experiment):
    recorded = {"PATH": "fixed", "LD_LIBRARY_PATH": None}
    experiment.verify_environment(dict(recorded), recorded)
    with pytest.raises(ValueError, match="LD_LIBRARY_PATH"):
        experiment.verify_environment({**recorded, "LD_LIBRARY_PATH": "/different"}, recorded)
