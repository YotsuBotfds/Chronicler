"""Pure/mocked adapter tests; do not qualify native M4 execution."""
from dataclasses import FrozenInstanceError
import math
from types import SimpleNamespace

import pytest

from chronicler.household_mobility_state import capture_mobility_frame, liquid_requirement, snapshot_fields
from test_expansion_feature_wiring import configure_without_native


def world(value=None, turn=7):
    return SimpleNamespace(turn=turn, household_mobility_liquid_requirement=value, maritime=None)


def frame(turn=7):
    return ((turn, 2, 4, 1, 1, 1, 3, 0), [
        (12, 0, 1, 3, 0.5, 2.0, 3.0, 1),
        (20, 0, 2, 1, None, 5.0, 1.0, 3),
    ])


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True, "1", 10**500, 1e-300])
def test_requirement_rejects_invalid_before_native(value):
    with pytest.raises(ValueError):
        liquid_requirement(world(value))


def test_frame_is_detached_immutable_and_dated():
    raw = frame()
    obs = capture_mobility_frame(raw, source_turn=7, mode="hybrid", requirement=1.0)
    raw[1].clear()
    assert len(obs.samples) == 2
    with pytest.raises(FrozenInstanceError):
        obs.samples[0].group_id = 99
    value = snapshot_fields(obs, 8)["household_mobility"]
    assert value["schema_version"] == 1
    assert value["source_turn"] == 7 and value["completed_turn"] == 8
    assert value["person_units"] == "native_agents"
    assert value["passed_means"] == "gate_passed_not_observed_move"
    assert value["samples"][0]["reason"] == "insufficient"
    assert value["samples"][1]["reason"] == "unknown_destination"
    with pytest.raises(ValueError, match="completed turn"):
        snapshot_fields(obs, 9)
    assert snapshot_fields(None, 8) == {}


@pytest.mark.parametrize("bad", [
    None, ((6, 2, 4, 1, 1, 1, 3, 0), frame()[1]),
    ((7, 2, 4, 1, 1, 0, 3, 0), frame()[1]),
    ((7, 2, 4, 1, 1, 1, 3, 1), frame()[1]),
    ((7, 1, 1, 1, 1, 0, 0, 0), [(1, 0, 1, 1, math.nan, 1., 1., 0)]),
    ((7, 1, 1, 1, 1, 0, 0, 0), [(1, 0, 1, 1, 1., 1., 1., 5)]),
])
def test_bad_or_stale_native_frame_is_not_silently_fabricated(bad):
    with pytest.raises(ValueError):
        capture_mobility_frame(bad, source_turn=7, mode="hybrid", requirement=1.0)


class Sim:
    def __init__(self):
        self.calls = []
    def tick(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "events"
    def get_mobility_gate_frame(self):
        return frame()
    def set_merchant_route_graph(self, batch):
        pass


def bridge(monkeypatch, sim=None):
    from chronicler.agent_bridge import AgentBridge
    from chronicler import agent_bridge, economy, transaction_receipts
    obj = AgentBridge.__new__(AgentBridge)
    obj._sim = sim or Sim()
    obj._mode = "hybrid"
    obj._gini_by_civ = {}
    obj._economy_result = None
    obj._begin_decision_delivery = lambda world: None
    obj._capture_decision_delivery = lambda delivery, events: None
    obj._process_tick_results = lambda events, world, **kwargs: [events]
    obj.sync_regions = lambda world: None
    monkeypatch.setattr(economy, "build_merchant_route_graph", lambda world: "route")
    monkeypatch.setattr(agent_bridge, "build_signals", lambda *a, **kw: "signals")
    monkeypatch.setattr(agent_bridge, "_city_route_graph", lambda w, r: r)
    monkeypatch.setattr(agent_bridge, "_send_movement_table", lambda *a: None)
    monkeypatch.setattr(transaction_receipts, "prepare_transaction_receipts", lambda *a: None)
    monkeypatch.setattr(transaction_receipts, "capture_transaction_receipts", lambda *a: None)
    return obj


@pytest.mark.parametrize("method", ["tick", "tick_agents"])
def test_adapter_off_keeps_two_argument_call_and_active_frame_is_one_shot(monkeypatch, method):
    obj = bridge(monkeypatch)
    assert getattr(obj, method)(world()) == ["events"]
    assert obj._sim.calls[-1] == ((7, "signals"), {})
    assert obj.take_household_mobility_observation(7) is None
    assert getattr(obj, method)(world(1.0)) == ["events"]
    assert obj._sim.calls[-1] == ((7, "signals"), {"liquid_requirement": 1.0})
    assert "_household_mobility_observation" not in obj.__getstate__()
    assert obj.take_household_mobility_observation(7).blocked_native_persons == 3
    assert obj.take_household_mobility_observation(7) is None
    getattr(obj, method)(world(1.0))
    assert obj.take_household_mobility_observation(8) is None
    assert obj.take_household_mobility_observation(7) is None


def test_failed_or_disabled_tick_cannot_reuse_old_observation(monkeypatch):
    obj = bridge(monkeypatch)
    obj.tick_agents(world(1.0))
    obj.tick_agents(world())
    assert obj.take_household_mobility_observation(7) is None
    obj.tick_agents(world(1.0))
    before = len(obj._sim.calls)
    with pytest.raises(ValueError):
        obj.tick_agents(world(-1))
    assert len(obj._sim.calls) == before
    assert obj.take_household_mobility_observation(7) is None
    obj.tick_agents(world(1.0))
    obj._process_tick_results = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("failed"))
    with pytest.raises(RuntimeError):
        obj.tick_agents(world(1.0))
    assert obj.take_household_mobility_observation(7) is None


def test_old_native_build_rejected_before_tick_mutation(monkeypatch):
    old = SimpleNamespace(tick=lambda *a: None)
    obj = bridge(monkeypatch, old)
    with pytest.raises(RuntimeError, match="fresh native build"):
        obj.tick_agents(world(1.0))


def test_configuration_persists_control_and_saved_off_mode_is_dormant(configure_without_native):
    from chronicler.world_gen import generate_world
    from chronicler.main import _build_parser
    from chronicler.batch_manifest import simulation_config
    w = generate_world(seed=42)
    assert "household_mobility_liquid_requirement" not in w.model_dump(mode="json")
    assert "household_mobility_liquid_requirement" not in simulation_config(_build_parser().parse_args([]))
    _, config = configure_without_native(w, "--household-mobility-liquid-requirement", "1")
    assert w.household_mobility_liquid_requirement == 1
    assert config["simulation_args"]["household_mobility_liquid_requirement"] == 1
    _, dormant = configure_without_native(w, mode="off")
    assert w.household_mobility_liquid_requirement == 1
    assert dormant["simulation_args"]["household_mobility_liquid_requirement"] == 1
    configure_without_native(w, "--household-mobility-liquid-requirement", "0", mode="off")
    assert w.household_mobility_liquid_requirement is None


@pytest.mark.parametrize("value,mode", [("-1", "hybrid"), ("nan", "hybrid"),
    ("inf", "hybrid"), ("1001", "hybrid"), ("1", "off"), ("1", "shadow"),
    ("1", "demographics-only")])
def test_invalid_control_refused_before_native_construction(configure_without_native, value, mode):
    from chronicler.world_gen import generate_world
    with pytest.raises(ValueError):
        configure_without_native(generate_world(seed=42),
            "--household-mobility-liquid-requirement", value, mode=mode)
    assert not configure_without_native.constructions


def test_exact_resume_retains_control_and_rejects_changed_or_inconsistent_intent():
    from chronicler.main import _adopt_checkpoint_args, _build_parser
    from chronicler.world_gen import generate_world
    w = generate_world(seed=42)
    w.household_mobility_liquid_requirement = 1
    state = SimpleNamespace(world=w, seed=42, num_turns=8,
        run_config={"simulation_args": {"household_mobility_liquid_requirement": 1}})
    parser = _build_parser()
    args = parser.parse_args([])
    assert _adopt_checkpoint_args(parser, args, SimpleNamespace(state=state)) == []
    assert args.household_mobility_liquid_requirement == 1
    for value in ("0", "2", "nan"):
        changed = parser.parse_args(["--household-mobility-liquid-requirement", value])
        conflicts = _adopt_checkpoint_args(parser, changed, SimpleNamespace(state=state))
        assert any("household-mobility" in c for c in conflicts)
        assert w.household_mobility_liquid_requirement == 1
    state.run_config["simulation_args"]["household_mobility_liquid_requirement"] = 2
    assert any("retained state" in c for c in _adopt_checkpoint_args(
        parser, parser.parse_args([]), SimpleNamespace(state=state)))


def test_turn_observation_rejects_other_turn_and_old_snapshot_stays_unknown():
    from chronicler.models import TurnSnapshot
    from chronicler.turn_artifacts import TurnObservation
    observation = capture_mobility_frame(frame(), source_turn=7, mode="hybrid", requirement=1)
    with pytest.raises(ValueError, match="household_mobility source_turn"):
        TurnObservation(8, 9, None, household_mobility=observation)
    old = TurnSnapshot(turn=8, civ_stats={}, region_control={}, relationships={})
    assert old.household_mobility is None
    assert "household_mobility" not in old.model_dump(mode="json")
