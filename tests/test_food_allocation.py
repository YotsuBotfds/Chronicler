"""L2 food allocation orchestration without the native extension."""
import math
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import food_allocation as F
from chronicler.food_allocation_state import FoodAllocationState
from chronicler.livelihoods_state import LivelihoodsState


def _world(regime="floor_means", turn=5):
    world = SimpleNamespace(turn=turn, agent_mode="hybrid", tuning_overrides={},
                            regions=[SimpleNamespace(name=f"R{i}") for i in range(3)],
                            livelihoods=LivelihoodsState())
    world.livelihoods.food_allocation = FoodAllocationState(regime=regime)
    return world


class _Sim:
    def __init__(self, frame=None):
        self.installed, self.frame, self.cancelled = None, frame, 0

    def set_food_allocation(self, *args):
        self.installed = args

    def take_food_allocation_frame(self):
        out, self.frame = self.frame, None
        return out

    def cancel_food_allocation(self):
        self.cancelled += 1
        return True


class _Bridge:
    def __init__(self, regions, sim):
        self._snap = pa.record_batch({"region": pa.array(regions, pa.uint16())})
        self._sim = sim

    def get_snapshot(self):
        raise AssertionError("food allocation must not request another native snapshot")


COLUMNS = ["region", "scarce", "phase2_alive", "alive", "households", "sufficiency", "rations_available",
           "relief_available", "allocated", "unallocated", "relief_to_targeted", "shortfall", "below_floor",
           "fully_fed", "min_ration", "max_ration", "people_poorer_half", "shortfall_poorer_half",
           "people_richer_half", "shortfall_richer_half", "children", "shortfall_children"]


def _row(region, scarce, alive, avail, alloc, short):
    values = dict.fromkeys(COLUMNS, 0.0)
    values.update(region=region, scarce=scarce, phase2_alive=alive, alive=alive, rations_available=avail,
                  allocated=alloc, shortfall=short, shortfall_poorer_half=short, people_poorer_half=alive)
    return [values[c] for c in COLUMNS]


def test_enable_records_regime_and_requires_hybrid():
    world = _world()
    world.livelihoods.food_allocation = None
    F.set_food_allocation_enabled(world, True, args=SimpleNamespace(food_allocation_regime="targeted_relief"))
    assert world.livelihoods.food_allocation.regime == "targeted_relief" and F.food_allocation_active(world)
    world.agent_mode = "shadow"
    assert not F.food_allocation_active(world)


def test_install_uses_pre_release_sufficiency_and_phase2_counts_then_takes_receipts():
    world = _world("targeted_relief")
    sim = _Sim()
    bridge = _Bridge([0, 0, 2, 2, 2], sim)
    result = SimpleNamespace(food_sufficiency={"R0": 0.5, "R2": 1.2})
    F.prepare_phase2(world, None, bridge, bridge._snap, None)
    F.finish_phase2(world, result, bridge, None)
    F.before_agent_tick(world, bridge, result)
    turn, regime, floor, share, pre, counts = sim.installed
    assert (turn, regime, floor, share) == (5, 2, 0.5, 0.5)
    assert pre[0] == 0.5 and math.isnan(pre[1]) and pre[2] == 1.2 and counts == [2, 0, 3]
    sim.frame = (5, 2, COLUMNS, [_row(0, 1, 2, 1.0, 1.0, 1.0), _row(2, 0, 3, 3.0, 3.0, 0.0)],
                 [(7, 0, 7, 0.5, True), (9, 2, 9, 1.0, False)], 0)
    F.after_agent_tick(world, bridge)
    state = world.livelihoods.food_allocation
    assert [r["region"] for r in state.regions] == [0] and state.sample == [[7, 0, 7, 0.5, True]]
    assert state.totals["shortfall"] == 1.0 and state.counters["allocated_turns"] == 1
    world.turn += 1
    summary = F.snapshot_summary(world)
    assert summary["source_turn"] == 5 and summary["totals"]["scarce_regions"] == 1
    world.turn += 1
    assert F.snapshot_summary(world)["totals"] is None


def test_receipts_that_do_not_close_or_do_not_match_are_refused():
    world = _world("equal")
    sim = _Sim()
    bridge = _Bridge([0], sim)
    F.prepare_phase2(world, None, bridge, bridge._snap, None)
    F.finish_phase2(world, SimpleNamespace(food_sufficiency={"R0": 0.5}), bridge, None)
    F.before_agent_tick(world, bridge, None)
    sim.frame = (5, 0, COLUMNS, [_row(0, 1, 2, 1.0, 0.7, 1.3)], [], 0)
    with pytest.raises(RuntimeError, match="close"):
        F.after_agent_tick(world, bridge)
    F.prepare_phase2(world, None, bridge, bridge._snap, None)
    F.finish_phase2(world, SimpleNamespace(food_sufficiency={"R0": 0.5}), bridge, None)
    F.before_agent_tick(world, bridge, None)
    sim.frame = (5, 1, COLUMNS, [], [], 0)
    with pytest.raises(RuntimeError, match="match"):
        F.after_agent_tick(world, bridge)


def test_no_phase2_observation_installs_nothing_and_an_untaken_request_is_cancelled():
    world = _world()
    sim = _Sim()
    bridge = _Bridge([0], sim)
    F.before_agent_tick(world, bridge, None)
    assert sim.installed is None and world.livelihoods.food_allocation.counters["turns_unobserved"] == 1
    F.prepare_phase2(world, None, bridge, bridge._snap, None)
    F.finish_phase2(world, SimpleNamespace(food_sufficiency={"R0": 0.5}), bridge, None)
    F.before_agent_tick(world, bridge, None)
    F.after_agent_tick(world, bridge)      # the tick produced no receipts
    assert sim.cancelled == 1 and world.livelihoods.food_allocation.counters["turns_not_taken"] == 1


def test_bad_parameters_are_refused():
    world = _world()
    world.tuning_overrides = {"livelihoods.food.floor": 0.0}
    sim = _Sim()
    bridge = _Bridge([0], sim)
    F.prepare_phase2(world, None, bridge, bridge._snap, None)
    F.finish_phase2(world, SimpleNamespace(food_sufficiency={"R0": 0.5}), bridge, None)
    with pytest.raises(ValueError):
        F.before_agent_tick(world, bridge, None)
