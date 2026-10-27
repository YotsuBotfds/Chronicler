"""Community anchoring with the real native extension: the switch and its
checkpoint state, the validator's mirror of the native community ties, a
run with the switch on, and its ablation arm (chronicler-agents/src/community.rs,
chronicler.community_anchoring)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from chronicler.main import execute_run

pytestmark = pytest.mark.native


def _native():
    ca = pytest.importorskip("chronicler_agents")
    sim = getattr(ca, "AgentSimulator", None)
    if not isinstance(sim, type) or not hasattr(sim, "set_community_anchoring"):
        pytest.skip("requires a chronicler_agents build with community anchoring")
    return ca


def _args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=42, turns=turns, civs=4, regions=8,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents="hybrid", tuning_overrides={},
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _events(folder: Path) -> list[tuple]:
    import pyarrow.ipc as ipc
    table = ipc.open_file(folder / "agent_events.arrow").read_all().to_pydict()
    return [tuple(table[c][i] for c in table) for i in range(len(table["turn"]))]


def test_switch_survives_a_checkpoint_and_is_off_by_default():
    ca = _native()
    sim = ca.AgentSimulator(num_regions=4, seed=7)
    enabled, full_anchor = sim.community_anchoring
    assert enabled is False and full_anchor == pytest.approx(0.120143, abs=1e-6)
    with pytest.raises(ValueError, match="finite and not negative"):
        sim.set_community_anchoring(True, -0.1)
    sim.set_community_anchoring(True)
    assert sim.community_anchoring[0] is True
    sim.set_community_anchoring(True, 0.3)
    restored = ca.AgentSimulator.from_checkpoint_state(bytes(sim.checkpoint_state()))
    assert restored.community_anchoring == pytest.approx((True, 0.3))
    _version, _fingerprint, schema = ca.AgentSimulator.checkpoint_schema()
    assert "community_anchoring:CommunityAnchoring{enabled:bool,full_anchor:f32,}" in schema
    sim.set_decision_ablation(["community_anchor"], 12)
    assert sim.decision_ablation == (["community_anchor"], 12)


def test_native_ties_match_the_sidecar_mirror(tmp_path):
    """After a hybrid run with sidecars, the native ties of the final pool
    equal the validator's ties computed from the final sidecar snapshot."""
    _native()
    from chronicler.columnar import pylist
    from chronicler.validation_ablation import community_ties
    from chronicler.validation_io import _graph_snapshot_from_columns, _needs_snapshot_from_columns, _read_arrow_columns

    folder = tmp_path / "run"
    captured = {}
    import chronicler.agent_bridge as bridge_module

    original = bridge_module.AgentBridge.write_final_sidecar_snapshot

    def capture(self, world):
        original(self, world)
        batch = self._sim.get_community_ties()
        captured["turn"] = world.turn
        captured["ties"] = {name: pylist(batch.column(name)) for name in ("agent_id", "ties", "non_kin", "counted")}

    bridge_module.AgentBridge.write_final_sidecar_snapshot = capture
    try:
        execute_run(_args(folder, 60, validation_sidecar=True, community_anchoring=True))
    finally:
        bridge_module.AgentBridge.write_final_sidecar_snapshot = original
    assert captured, "the final sidecar snapshot was written"
    rel = _read_arrow_columns(folder / "validation_relationships.arrow")
    mem = _read_arrow_columns(folder / "validation_memory_signatures.arrow")
    needs = _read_arrow_columns(folder / "validation_needs.arrow")
    turn = captured["turn"]
    graph = _graph_snapshot_from_columns(rel, mem, turn)
    snapshot = _needs_snapshot_from_columns(needs, turn)
    regions = {int(a): int(r) for a, r in zip(snapshot["columns"]["agent_id"], snapshot["columns"]["region"])}
    mirror = community_ties(graph["edges"], regions, graph["memory_signatures"])
    native = {int(a): (int(t), int(nk), int(c)) for a, t, nk, c in zip(
        captured["ties"]["agent_id"], captured["ties"]["ties"], captured["ties"]["non_kin"],
        captured["ties"]["counted"]) if int(t) > 0}
    assert native == mirror
    assert any(c >= 1 for _t, _nk, c in native.values()), "the run forms community ties"


def test_anchoring_changes_the_run_and_its_ablation_restores_the_decisions(tmp_path):
    _native()
    execute_run(_args(tmp_path / "plain", 40))
    execute_run(_args(tmp_path / "anchored", 40, community_anchoring=True))
    execute_run(_args(tmp_path / "ablated", 40, community_anchoring=True,
                      decision_ablation="community_anchor", ablation_start_turn=0))
    plain, anchored, ablated = (_events(tmp_path / n) for n in ("plain", "anchored", "ablated"))
    assert anchored != plain
    # The arm switches the anchor off from turn 0: the decisions are the
    # plain run's (the anchor draws nothing).
    assert ablated == plain
    state = json.loads((tmp_path / "anchored" / "state.json").read_text(encoding="utf-8"))
    assert state["community_anchoring"] is True
    plain_state = json.loads((tmp_path / "plain" / "state.json").read_text(encoding="utf-8"))
    assert "community_anchoring" not in plain_state
    with pytest.raises(ValueError, match="requires community anchoring"):
        execute_run(_args(tmp_path / "bad", 5, decision_ablation="community_anchor", ablation_start_turn=0))


def test_an_anchored_run_resumes_exactly_and_keeps_its_switch(tmp_path):
    _native()
    from chronicler.run_checkpoint import read_checkpoint

    execute_run(_args(tmp_path / "straight", 24, community_anchoring=True, checkpoint_turns=(12,)))
    checkpoint = tmp_path / "straight" / "checkpoint_turn_12.ckpt"
    args = _args(tmp_path / "resumed", 24, resume=str(checkpoint))
    execute_run(args, checkpoint_resume=read_checkpoint(checkpoint))
    assert _events(tmp_path / "resumed") == _events(tmp_path / "straight")
