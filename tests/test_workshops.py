"""L1A workshop contract without the native extension: sites, refusal, receipts."""
from types import SimpleNamespace

import pytest

from chronicler.cities_state import City, CityState
from chronicler.livelihoods_state import LivelihoodsState
from chronicler import workshops as W
from chronicler.workshops_state import MAX_SITES, WorkshopState


def _world(cities, turn=20, regions=6):
    world = SimpleNamespace(turn=turn, regions=[SimpleNamespace(name=f"R{i}") for i in range(regions)],
                            cities=CityState(cities=cities), livelihoods=LivelihoodsState(),
                            war_state=SimpleNamespace(armies=[]))
    world.livelihoods.workshops = WorkshopState(mode="observe")
    return world


def _city(sid, region, rank=1, size=10.0):
    return City(settlement_id=sid, region=region, name=f"C{sid}", founded_turn=1, founder=0, rank=rank, size=size)


class _Sim:
    def __init__(self, rows=None, inputs=None):
        self.rows, self.inputs, self.calls = rows, inputs, []

    def plan_workshop_crews(self, requests, enlisted):
        self.calls.append((list(requests), list(enlisted)))
        return [(site, region, settlement, 3, 0, 0, 0, 3, [10 + site, 20 + site], [30, 40],
                 2 * diverted) for site, region, settlement, diverted, _ in requests]

    def take_craft_inputs(self):
        out, self.inputs = self.inputs, None
        return out


def test_operate_is_refused_until_l1b_and_observe_enables():
    world = _world([])
    world.livelihoods.workshops = None
    with pytest.raises(ValueError, match="L1B"):
        W.set_workshops_enabled(world, True, args=SimpleNamespace(workshop_mode="operate"))
    with pytest.raises(ValueError, match="L1B"):
        W.set_workshops_enabled(world, True, args=SimpleNamespace(workshop_mode=None))
    W.set_workshops_enabled(world, True, args=SimpleNamespace(workshop_mode="observe"))
    assert world.livelihoods.workshops.mode == "observe" and W.workshops_active(world)
    W.set_workshops_enabled(world, False, args=SimpleNamespace(workshop_mode=None))
    assert not W.workshops_active(world)


def test_sites_one_per_region_ranked_and_capped_then_closed_with_reason():
    cities = [_city(1, 0, 1, 5), _city(2, 0, 2, 3), _city(3, 1, 3), _city(4, 2), _city(5, 3),
              _city(6, 4), _city(7, 5, 0)]
    world = _world(cities)
    state = world.livelihoods.workshops
    live = W.refresh_sites(world, state)
    assert len(state.sites) == MAX_SITES
    assert [s.settlement_id for s in state.sites] == [3, 2, 4, 5]   # rank, size, id; rank 0 never
    assert set(live) == {s.site for s in state.sites}
    fallen = world.cities.cities.pop(0 if world.cities.cities[0].settlement_id == 2 else 1)
    world.cities.fallen.append(fallen)
    world.turn = 30
    W.refresh_sites(world, state)
    closed = state.closed[-1]
    assert (closed.settlement_id, closed.status, closed.closed_turn, closed.closed_reason) == (2, "closed", 30, "city_fell")
    # The freed slot goes to the best remaining city (larger city 6 before
    # city 1); a closed city is never readmitted.
    assert {s.settlement_id for s in state.sites} == {3, 4, 5, 6}
    assert 2 not in {s.settlement_id for s in state.sites}


def test_prepare_requires_native_and_finish_records_region_inputs_once():
    import pyarrow as pa
    world = _world([_city(1, 2, 2)])
    world.regions[2].name = "R2"
    batch = pa.record_batch({"region_id": pa.array(range(6), pa.uint16()),
                             "craft_raw_demand": pa.array([0.0, 0, 1.5, 0, 0, 0], pa.float32())})
    with pytest.raises(RuntimeError, match="native"):
        W.prepare_phase2(world, batch, SimpleNamespace(_sim=object()), None, None)
    goods = [[0.0] * 9 for _ in range(6)]
    goods[2][3], goods[2][4] = 0.75, 0.25
    sim = _Sim(inputs=[[9.0] * 9] * 6)          # stale observation from an earlier tick
    bridge = SimpleNamespace(_sim=sim)
    assert W.prepare_phase2(world, batch, bridge, None, None) is batch
    assert sim.calls[0][0] == [(0, 2, 1, pytest.approx(0.3), 8)]
    sim.inputs = goods
    result = SimpleNamespace(craft_output={"R2": 1.0})
    W.finish_phase2(world, result, bridge, None)
    receipt = world.livelihoods.workshops.frame[0]
    assert receipt.crew == [10, 20] and receipt.allocated == 0.0 and receipt.realized == 0.0
    assert receipt.region_craft_input == {"timber": 0.75, "ore": 0.25}
    assert receipt.region_craft_output == 1.0 and receipt.legacy_craft_ceiling == 1.5
    with pytest.raises(RuntimeError, match="missing"):
        W.finish_phase2(world, result, bridge, None)


def test_missing_native_inputs_are_unknown_and_snapshot_is_dated():
    import pyarrow as pa
    world = _world([_city(1, 0)])
    batch = pa.record_batch({"region_id": pa.array(range(6), pa.uint16())})
    bridge = SimpleNamespace(_sim=_Sim(inputs=None))
    W.prepare_phase2(world, batch, bridge, None, None)
    W.finish_phase2(world, SimpleNamespace(craft_output={}), bridge, None)
    receipt = world.livelihoods.workshops.frame[0]
    assert receipt.region_craft_input is None and receipt.region_craft_output is None
    assert receipt.legacy_craft_ceiling is None
    world.turn += 1
    summary = W.snapshot_summary(world)
    assert summary["source_turn"] == 20 and summary["receipts"][0]["crew"] == [10, 20]
    world.turn += 1
    assert W.snapshot_summary(world)["receipts"] is None


def test_rollback_releases_a_pending_plan():
    import pyarrow as pa
    world = _world([_city(1, 0)])
    batch = pa.record_batch({"region_id": pa.array(range(6), pa.uint16())})
    bridge = SimpleNamespace(_sim=_Sim())
    W.prepare_phase2(world, batch, bridge, None, None)
    with pytest.raises(RuntimeError, match="pending"):
        W.prepare_phase2(world, batch, bridge, None, None)
    W.rollback_phase2(world)
    W.prepare_phase2(world, batch, bridge, None, None)
