"""Pure/mocked adapter tests; do not qualify native M4 execution."""
from dataclasses import FrozenInstanceError
import math
from types import SimpleNamespace

import pytest

from chronicler.household_mobility_state import capture_mobility_frame, liquid_requirement, snapshot_fields


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
