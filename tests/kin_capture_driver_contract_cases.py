"""Pure acquisition-driver contracts: namespaces and wire rows, no World/native."""
from copy import deepcopy
import argparse
import json
from types import SimpleNamespace

import pytest

from scripts import capture_kin_root_exposure as driver
from chronicler.kin_root_exposure import summarize_kin_root_exposure
from chronicler.validation_communities import oracle1_snapshot
from tests.kin_root_exposure_contract_cases import bits, candidate, decision, frames


class Batch:
    def __init__(self, rows):
        self.rows = rows

    def to_pylist(self):
        return deepcopy(self.rows)


def fixture(tmp_path, *, empty_members=False, partial=False):
    calls = []
    sidecar = SimpleNamespace(
        _base_dir=tmp_path / "parent",
        _relationship_rows=[dict(turn=100, agent_id=i, target_id=i+1,
            bond_type=0 if empty_members else 6, sentiment=50) for i in range(1, 5)],
        _memory_rows=[dict(turn=100, agent_id=i, event_type=1, memory_turn=99, valence_sign=1)
            for i in range(1, 6)],
        _needs_rows=[dict(turn=100, agent_id=i, region=0 if i <= 5 else 1) for i in range(1, 7)])
    sidecar._needs_rows.insert(0, dict(turn=90, agent_id=99, region=7))
    bridge = SimpleNamespace(_sidecar=sidecar)
    bridge.close = lambda: calls.append(("bridge_close", sidecar._base_dir))
    header = dict(turn=101, seed=42, num_turns=500, exact=True,
        world=dict(regions=8, civilizations=4, geography=False), sections=[dict(raw_length=1)],
        identity={"source": "fake", "native": "fake"},
        run_config=dict(agent_mode="hybrid", validation_sidecar=True,
            output_args=dict(simulate_only=True, narrator="local")))
    world = SimpleNamespace(turn=101, seed=42, regions=list(range(8)), civilizations=list(range(4)))
    state = SimpleNamespace(seed=42, num_turns=500, world=world, agent_bridge=bridge,
        run_config=deepcopy(header["run_config"]))
    loaded = SimpleNamespace(exact=True, mismatches=[], header=header, state=state)
    ids = [] if empty_members else [1, 2, 3, 4, 5]
    rows = [decision(i) for i in ids]
    targets = [candidate(i) for i in ids]
    if rows:
        # Membership is independent of whether this turn has relationship roots.
        rows[2] = decision(3, roots_bits=0, home_bonds_bits=0, voluntary_pull_bits=bits(.5),
            migration_post_pull_bits=bits(.6), migration_post_wealth_bits=bits(.6))
        targets[2] = candidate(3, roots_bits=0, net_frontier_bits=bits(.5),
            post_roots_pull_bits=bits(.5), applied_pull_bits=bits(.5))
    wire = frames(rows, targets)
    wire["decision_header"].update(alive_seen_all=6, evaluated_all=6,
        mobility_eligible_all=6, admissible_candidates_all=6,
        selection_is_explicit=True, selected_ids_requested=len(ids))
    wire["move_header"].update(selection_is_explicit=True, selected_ids_requested=len(ids))
    if partial:
        wire["decision_header"].update(decision_capture_complete=False, dropped_candidate_rows=1)
    readout = SimpleNamespace(status="captured", reason=None, source_turn=101,
        native_event_count=0, applied_event_links_checked=0,
        decision_header=Batch([wire["decision_header"]]), decisions=Batch(wire["decision_rows"]),
        candidates=Batch(wire["candidate_rows"]), move_header=Batch([wire["move_header"]]),
        moves=Batch(wire["move_rows"]))

    class Observer:
        def read_latest(self, *, expected_source_turn):
            calls.append(("read", expected_source_turn))
            return readout

        def close(self):
            calls.append(("observer_close",))
            return SimpleNamespace(reason="closed")

    observer = Observer()

    def parser():
        result = argparse.ArgumentParser()
        result.add_argument("--resume")
        result.add_argument("--turns", type=int)
        result.add_argument("--simulate-only", action="store_true")
        result.add_argument("--state-every", type=int)
        result.add_argument("--output")
        result.add_argument("--state")
        return result

    def load(path, *, allow_mismatch):
        calls.append(("load", allow_mismatch))
        return loaded

    def retarget(saved, directory, shadow):
        calls.append(("retarget", directory, shadow))
        directory.mkdir()
        saved.agent_bridge._sidecar._base_dir = directory

    def attach(saved, **kwargs):
        calls.append(("attach", kwargs))
        assert saved is bridge
        return observer

    def execute(args, *, checkpoint_resume, on_turn, quit_check):
        calls.append(("execute", args.turns, args.state_every))
        assert checkpoint_resume is loaded and quit_check() is True
        world.turn += 1
        on_turn(None, None, None, None)
        bridge.close()

    runtime = SimpleNamespace(read_header=lambda path: (header, b"fake"), load=load,
        parser=parser, adopt=lambda *args: [], retarget=retarget, execute=execute,
        attach=attach, snapshot=oracle1_snapshot, summarize=summarize_kin_root_exposure)
    checkpoint = tmp_path / "checkpoint_turn_101.ckpt"
    checkpoint.write_bytes(b"fake checkpoint; not executable evidence")
    return SimpleNamespace(checkpoint=checkpoint, output=tmp_path / "capture", runtime=runtime,
        calls=calls, loaded=loaded, header=header, state=state, bridge=bridge, observer=observer,
        readout=readout, wire=wire)


def run(case):
    return driver.acquire(case.checkpoint, case.output, case.runtime)


def test_default_cli_is_disabled_before_runtime_import_or_output(tmp_path, monkeypatch, capsys):
    def forbidden():
        raise AssertionError("default invocation imported the simulation")
    monkeypatch.setattr(driver, "_load_runtime", forbidden)
    output = tmp_path / "absent"
    assert driver.main(["--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "disabled"
    assert not output.exists()


def test_one_current_turn_preserves_horizon_native_selection_and_original_wire(tmp_path):
    case = fixture(tmp_path)
    before = deepcopy(case.bridge._sidecar.__dict__)
    result = run(case)
    assert result["status"] == "captured"
    assert ("load", False) in case.calls
    assert ("execute", 500, 500) in case.calls and ("read", 101) in case.calls
    attachment = next(row[1] for row in case.calls if row[0] == "attach")
    assert attachment == dict(selected_agent_ids=[1, 2, 3, 4, 5], max_agent_rows=4096,
        max_candidate_rows=16384, max_move_rows=16384, max_retained_bytes=8*1024*1024)
    assert json.loads((case.output / "wire.json").read_text()) == case.wire
    cohort = json.loads((case.output / "cohort.json").read_text())
    assert cohort["member_ids"] == [1, 2, 3, 4, 5]
    assert cohort["alive_at_fork"] == 6 and cohort["nonmembers_at_fork"] == 1
    report = json.loads((case.output / "exposure.json").read_text())
    assert report["decisions"]["captured"] == 5
    assert report["decisions"]["relationship_root_present"] == 4
    assert report["denominator"] == "captured selected rows"
    assert report["community_membership_observed"] is False
    assert result["twenty_turn_effect_estimate"] is result["execution_attestation"] is None
    assert result["ordinary_resume_exports_hard_budgeted"] is False
    for name in ("_relationship_rows", "_memory_rows", "_needs_rows"):
        assert getattr(case.bridge._sidecar, name) == before[name]


@pytest.mark.parametrize("empty,partial", [(True, False), (False, True)])
def test_empty_members_and_partial_capture_remain_visible(tmp_path, empty, partial):
    case = fixture(tmp_path, empty_members=empty, partial=partial)
    result = run(case)
    assert result["status"] == "captured"
    report = json.loads((case.output / "exposure.json").read_text())
    assert report["status"] == ("partial_capture" if partial else "complete_capture")
    assert report["decisions"]["captured"] == (0 if empty else 5)
    assert report["twenty_turn_effect_estimate"] is None


@pytest.mark.parametrize("field,value", [("turn", 100), ("seed", 43),
    ("num_turns", 101), ("exact", False)])
def test_wrong_fork_header_refuses_before_loading_or_flushing_parent(tmp_path, field, value):
    case = fixture(tmp_path)
    case.header[field] = value
    result = run(case)
    assert result["status"] == "failed" and result["error"]["message"] == "first_fork_checkpoint"
    assert not any(row[0] in ("load", "retarget", "bridge_close", "execute") for row in case.calls)


def test_strict_loader_error_is_retained_without_mismatch_override(tmp_path):
    case = fixture(tmp_path)
    def incompatible(path, *, allow_mismatch):
        assert allow_mismatch is False
        raise ValueError("source/native/environment mismatch")
    case.runtime.load = incompatible
    result = run(case)
    assert result["status"] == "failed" and "mismatch" in result["error"]["message"]
    assert not any(row[0] in ("attach", "retarget", "bridge_close") for row in case.calls)


@pytest.mark.parametrize("change", ["not_exact", "mismatches", "wrong_loaded_turn", "ablated", "no_bridge"])
def test_invalid_loaded_state_never_advances_or_flushes_parent(tmp_path, change):
    case = fixture(tmp_path)
    if change == "not_exact": case.loaded.exact = False
    elif change == "mismatches": case.loaded.mismatches = ["native"]
    elif change == "wrong_loaded_turn": case.state.world.turn = 100
    elif change == "ablated": case.state.run_config["decision_ablation"] = {"name": "kin_roots"}
    else: case.state.agent_bridge = None
    assert run(case)["status"] == "failed"
    assert not any(row[0] in ("attach", "retarget", "bridge_close", "execute") for row in case.calls)


@pytest.mark.parametrize("field,value", [("simulate_only", False), ("narrator", "api")])
def test_nonlocal_or_nonsimulation_checkpoint_refuses_before_attachment(tmp_path, field, value):
    case = fixture(tmp_path)
    for config in (case.state.run_config, case.header["run_config"]):
        config["output_args"][field] = value
    assert run(case)["error"]["message"] == "local_simulation_checkpoint"
    assert not any(row[0] in ("attach", "retarget", "bridge_close", "execute") for row in case.calls)


def test_conflicting_adopted_args_refuse_before_retarget(tmp_path):
    case = fixture(tmp_path)
    case.runtime.adopt = lambda *args: ["configuration mismatch"]
    assert run(case)["error"]["message"] == "checkpoint_args_conflict"
    assert not any(row[0] in ("retarget", "attach", "execute") for row in case.calls)


@pytest.mark.parametrize("kind", ["compressed", "raw", "sidecar", "fork"])
def test_input_limits_refuse_before_execution(tmp_path, monkeypatch, kind):
    case = fixture(tmp_path)
    names = dict(compressed="MAX_CHECKPOINT_BYTES", raw="MAX_CHECKPOINT_RAW_BYTES",
        sidecar="MAX_SIDECAR_ROWS", fork="MAX_FORK_ROWS")
    monkeypatch.setattr(driver, names[kind], 0)
    assert run(case)["status"] == "failed"
    assert not any(row[0] == "execute" for row in case.calls)


def test_missing_fork_graph_is_unavailable_not_an_empty_member_capture(tmp_path):
    case = fixture(tmp_path)
    case.bridge._sidecar._relationship_rows = []
    case.bridge._sidecar._memory_rows = []
    result = run(case)
    assert result["error"]["message"] == "fork_membership_unavailable"
    assert not any(row[0] == "attach" for row in case.calls)


def test_unavailable_observer_and_cleanup_failure_stay_failed(tmp_path):
    case = fixture(tmp_path)
    case.readout.status, case.readout.reason = "unavailable", "retention_limit"
    case.observer.close = lambda: SimpleNamespace(reason="disable_failed")
    result = run(case)
    assert result["status"] == "failed"
    assert result["readout"]["reason"] == "retention_limit"
    assert json.loads((case.output / "unavailable-headers.json").read_text()) == {
        "decision_header": [case.wire["decision_header"]], "move_header": [case.wire["move_header"]]}
    assert result["cleanup_errors"] == ["observer_disable_failed"]
    assert ("bridge_close", case.output / "run") in case.calls


def test_reader_refusal_preserves_original_wire_and_closes_after_private_retarget(tmp_path):
    case = fixture(tmp_path)
    def refusal(**wire):
        assert wire == case.wire
        raise ValueError("reader provenance refusal")
    case.runtime.summarize = refusal
    result = run(case)
    assert result["status"] == "failed" and result["error"]["message"] == "reader provenance refusal"
    assert json.loads((case.output / "wire.json").read_text()) == case.wire
    assert ("observer_close",) in case.calls and ("bridge_close", case.output / "run") in case.calls
    assert not (case.output / "exposure.json").exists()


def test_no_callback_cannot_claim_a_captured_turn(tmp_path):
    case = fixture(tmp_path)
    case.runtime.execute = lambda *args, **kwargs: None
    result = run(case)
    assert result["error"]["message"] == "one_turn_required"
    assert ("observer_close",) in case.calls


def test_existing_output_and_disk_floor_refuse_before_runtime(tmp_path, monkeypatch):
    case = fixture(tmp_path)
    case.output.mkdir()
    with pytest.raises(FileExistsError): run(case)
    monkeypatch.setattr(driver.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))
    with pytest.raises(ValueError, match="tmp_disk_floor"): run(case)
    assert case.calls == []


def test_driver_artifact_limit_stops_before_exposure_and_retains_failure(tmp_path, monkeypatch):
    case = fixture(tmp_path)
    monkeypatch.setattr(driver, "MAX_FRAME_BYTES", 1)
    result = run(case)
    assert result["status"] == "failed" and result["error"]["message"] == "driver_artifact_limit"
    assert not (case.output / "wire.json").exists()
    assert (case.output / "receipt.json").exists()


@pytest.mark.parametrize("phase", ["retarget", "attach"])
def test_pre_step_failures_never_flush_parent_outputs(tmp_path, phase):
    case = fixture(tmp_path)
    def failure(*args, **kwargs):
        raise RuntimeError(phase + " failed")
    setattr(case.runtime, phase, failure)
    result = run(case)
    assert result["status"] == "failed" and result["error"]["message"] == phase + " failed"
    assert not any(row[0] == "execute" for row in case.calls)
    closes = [row for row in case.calls if row[0] == "bridge_close"]
    assert closes == ([] if phase == "retarget" else [("bridge_close", case.output / "run")])


def test_wrong_source_turn_cannot_publish_a_wire_frame(tmp_path):
    case = fixture(tmp_path)
    case.readout.source_turn = 100
    result = run(case)
    assert result["status"] == "failed" and result["error"]["message"] == "capture_unavailable"
    assert not (case.output / "wire.json").exists()
    assert ("observer_close",) in case.calls
