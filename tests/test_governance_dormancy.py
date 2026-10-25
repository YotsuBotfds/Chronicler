"""Dormant standalone governance preserves the corrected Python off-mode oracle."""
import hashlib
import json
import random
from pathlib import Path

import pytest

from chronicler import governance_kernel_harness as harness
from scripts.benchmark_headless import rng_trace, run
from scripts.third_wave_controls import legacy_artifact_bytes, legacy_event_dump


FIXTURES = Path(__file__).parent / "fixtures" / "performance"
# Rolled forward from the frozen corrected_423a67c oracles by the 2026-10
# deferred-backlog corrections, the 2026-10 extinction fix, the 2026-10
# food-balance corrections, the 2026-10 food-logistics changes, the 2026-10
# hunger corrections and then the 2026-10 farmland and regional-climate
# corrections; see the fixture provenance and
# tests/test_performance_equivalence.py for the scoped-difference proofs.
BASELINE = json.loads((FIXTURES / "corrected_farmland_2026_10.json").read_text())
HUNGER_BASELINE = json.loads((FIXTURES / "corrected_hunger_2026_10.json").read_text())
FOOD_LOGISTICS_BASELINE = json.loads((FIXTURES / "corrected_food_logistics_2026_10.json").read_text())
# Bundle version 5 (dead civs pruned from history snapshots) rolled the
# artifact oracle forward as a format change; the food-balance artifacts stay
# frozen as its pre-pruning reference. The food-logistics artifact oracle
# records both projections of the same run and stays frozen, as does the
# hunger one; the farmland artifact oracle is live.
ARTIFACTS = json.loads((FIXTURES / "corrected_artifacts_dead_civ_pruning_2026_10.json").read_text())
PRE_PRUNING_ARTIFACTS = json.loads((FIXTURES / "corrected_artifacts_food_balance_2026_10.json").read_text())
FOOD_LOGISTICS_ARTIFACTS = json.loads((FIXTURES / "corrected_artifacts_food_logistics_2026_10.json").read_text())
HUNGER_ARTIFACTS = json.loads((FIXTURES / "corrected_artifacts_hunger_2026_10.json").read_text())
LIVE_ARTIFACTS = json.loads((FIXTURES / "corrected_artifacts_farmland_2026_10.json").read_text())


@pytest.mark.parametrize("name", BASELINE["workloads"])
@pytest.mark.parametrize("call_disabled", [False, True])
def test_complete_corrected_outputs_with_dormant_governance(
    name, call_disabled, tmp_path, monkeypatch,
):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    # Causal provenance is recorded but the timeline stays provenance-free, so
    # the frozen oracle still pins every event (see legacy_event_dump).
    monkeypatch.setattr("chronicler.provenance.LEGACY_TIMELINE", True)
    # This callback is a test seam, never a production simulation hook. The
    # empty synthetic carry has no connection to simulation state or extractors.
    opening = harness.HarnessCarry(0, -1, (), ())
    opening_json = harness.carry_to_json(opening)
    turns = []

    def forbidden(*args, **kwargs):
        raise AssertionError("dormant governance invoked a kernel")

    for module, entry in ((harness.g01, "fund_institutions"),
                          (harness.g02, "compute_elite_metrics"),
                          (harness.g03, "resolve_spending"),
                          (harness.g04, "start_reign")):
        monkeypatch.setattr(module, entry, forbidden)

    def capture(snapshot, text, events, named):
        if call_disabled:
            before = random.getstate()
            result = harness.run_kernel_frame(
                opening=opening, observations=object(), policy=object(),
            )
            assert result.carry is opening
            assert result.receipts == () and result.elite_metrics is None
            assert random.getstate() == before
            assert harness.carry_to_json(opening) == opening_json
        data = [snapshot.model_dump(mode="json"), text,
                [legacy_event_dump(event) for event in events],
                [event.model_dump(mode="json") for event in named]]
        turns.append(hashlib.sha256(json.dumps(
            data, ensure_ascii=False, separators=(",", ":"),
        ).encode()).hexdigest())

    expected = BASELINE["workloads"][name]
    with rng_trace(tmp_path / "rng.jsonl") as trace:
        run(expected["spec"], tmp_path / "artifacts", on_turn=capture)
    assert turns == expected["turn_sha256"]
    assert trace == expected["rng"]
    # Third-wave schema fields intentionally change raw state/bundle bytes.
    # Assert their exact dormant defaults; all original content still matches
    # the unchanged independently captured corrected-baseline oracle. The
    # fixture was captured on Unix; production text writers use platform
    # newlines. Compare their LF representation on Windows without changing
    # production writes or the frozen fixture. State/bundle JSON is already
    # canonicalized by the dormant-schema helper.
    for pre_pruning, oracle in ((False, LIVE_ARTIFACTS["workloads"]),
                                (True, LIVE_ARTIFACTS["pre_pruning_workloads"])):
        emitted = {}
        for path in sorted((tmp_path / "artifacts").iterdir()):
            if not path.is_file():
                continue
            data = legacy_artifact_bytes(path, pre_pruning=pre_pruning)
            if path.name not in ("state.json", "chronicle_bundle.json"):
                data = data.replace(b"\r\n", b"\n")
            emitted[path.name] = {"sha256": hashlib.sha256(data).hexdigest(),
                                  "bytes": len(data)}
        assert emitted == oracle[name], pre_pruning


def test_food_logistics_artifacts_change_only_the_declared_workloads():
    """The food-logistics roll-forward moves only the workloads its turn
    oracle declares; the others keep the frozen bundle-v5 and pre-pruning
    artifacts byte for byte."""
    declared = set()
    for correction in FOOD_LOGISTICS_BASELINE["provenance"]["corrections"]:
        declared |= set(correction["workloads"])
    assert set(FOOD_LOGISTICS_ARTIFACTS["workloads"]) == set(ARTIFACTS["workloads"])
    for name in ARTIFACTS["workloads"]:
        same_v5 = FOOD_LOGISTICS_ARTIFACTS["workloads"][name] == ARTIFACTS["workloads"][name]
        same_pre = (FOOD_LOGISTICS_ARTIFACTS["pre_pruning_workloads"][name]
                    == PRE_PRUNING_ARTIFACTS["workloads"][name])
        assert same_v5 == same_pre == (name not in declared), name


def test_hunger_artifacts_change_only_the_declared_workloads():
    """The hunger roll-forward moves only the workloads its turn oracle
    declares; the others keep the food-logistics artifacts byte for byte in
    both projections."""
    declared = set()
    for correction in HUNGER_BASELINE["provenance"]["corrections"]:
        declared |= set(correction["workloads"])
    assert set(HUNGER_ARTIFACTS["workloads"]) == set(FOOD_LOGISTICS_ARTIFACTS["workloads"])
    for name in FOOD_LOGISTICS_ARTIFACTS["workloads"]:
        same_v5 = HUNGER_ARTIFACTS["workloads"][name] == FOOD_LOGISTICS_ARTIFACTS["workloads"][name]
        same_pre = (HUNGER_ARTIFACTS["pre_pruning_workloads"][name]
                    == FOOD_LOGISTICS_ARTIFACTS["pre_pruning_workloads"][name])
        assert same_v5 == same_pre == (name not in declared), name


def test_farmland_artifacts_change_only_the_declared_workloads():
    """The farmland roll-forward moves only the workloads its turn oracle
    declares; the others keep the hunger artifacts byte for byte in both
    projections."""
    declared = set()
    for correction in BASELINE["provenance"]["corrections"]:
        declared |= set(correction["workloads"])
    assert set(LIVE_ARTIFACTS["workloads"]) == set(HUNGER_ARTIFACTS["workloads"])
    for name in HUNGER_ARTIFACTS["workloads"]:
        same_v5 = LIVE_ARTIFACTS["workloads"][name] == HUNGER_ARTIFACTS["workloads"][name]
        same_pre = (LIVE_ARTIFACTS["pre_pruning_workloads"][name]
                    == HUNGER_ARTIFACTS["pre_pruning_workloads"][name])
        assert same_v5 == same_pre == (name not in declared), name


def test_pruning_artifact_oracle_changes_only_declared_files():
    """The version-5 roll-forward changes only the bundle entries it lists."""
    (change,) = ARTIFACTS["provenance"]["format_changes"]
    declared = change["artifact_files"]
    assert set(ARTIFACTS["workloads"]) == set(PRE_PRUNING_ARTIFACTS["workloads"])
    for name, files in ARTIFACTS["workloads"].items():
        prior = PRE_PRUNING_ARTIFACTS["workloads"][name]
        assert set(files) == set(prior)
        changed = {fname for fname in files if files[fname] != prior[fname]}
        assert changed == set(declared.get(name, {})) == {"chronicle_bundle.json"}
        for fname in changed:
            assert declared[name][fname] == {"from": prior[fname], "to": files[fname]}
