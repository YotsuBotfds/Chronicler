"""L1 workshop contract without the native extension: sites, funding, settlement."""
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler.cities_state import City, CityState
from chronicler.livelihoods_state import LivelihoodsState
from chronicler import workshops as W
from chronicler.workshops_state import MAX_SITES, WorkshopState


def _world(cities, turn=20, regions=6, mode="observe", treasury=(1000,)):
    civs = [SimpleNamespace(name=f"Civ{i}", treasury=t) for i, t in enumerate(treasury)]
    world = SimpleNamespace(turn=turn, civilizations=civs,
                            regions=[SimpleNamespace(name=f"R{i}", controller="Civ0") for i in range(regions)],
                            cities=CityState(cities=cities), livelihoods=LivelihoodsState(),
                            war_state=SimpleNamespace(armies=[]))
    world.livelihoods.workshops = WorkshopState(mode=mode)
    return world


def _city(sid, region, rank=1, size=10.0):
    return City(settlement_id=sid, region=region, name=f"C{sid}", founded_turn=1, founder=0, rank=rank, size=size)


class _Sim:
    def __init__(self, inputs=None, crew=2):
        self.inputs, self.calls, self.crew = inputs, [], crew

    def plan_workshop_crews(self, requests, enlisted):
        self.calls.append((list(requests), list(enlisted)))
        return [(site, region, settlement, 3, 0, 0, 0, 3, [10 + site, 20 + site][:self.crew],
                 [30, 40][:self.crew], self.crew * diverted)
                for site, region, settlement, diverted, _ in requests]

    def take_craft_inputs(self):
        out, self.inputs = self.inputs, None
        return out


def _batch(n=6, ceiling=1.5):
    return pa.record_batch({"region_id": pa.array(range(n), pa.uint16()),
                            "craft_raw_demand": pa.array([ceiling] * n, pa.float32())})


def _turn(world, sim, output=0.0, batch=None):
    """One Phase 2: prepare, a successful native tick, finish. Returns the packed batch."""
    batch = W.prepare_phase2(world, batch or _batch(len(world.regions)), SimpleNamespace(_sim=sim), None, None)
    goods = [[0.0] * 9 for _ in world.regions]
    for s in world.livelihoods.workshops.sites:
        goods[s.region][3] = output
    sim.inputs = goods
    result = SimpleNamespace(craft_output={r.name: output for r in world.regions})
    W.finish_phase2(world, result, SimpleNamespace(_sim=sim), None)
    world.turn += 1
    return batch


def test_modes_and_switching():
    world = _world([])
    world.livelihoods.workshops = None
    W.set_workshops_enabled(world, True, args=SimpleNamespace(workshop_mode=None))
    assert world.livelihoods.workshops.mode == "operate" and W.workshops_active(world)
    W.set_workshops_enabled(world, False, args=SimpleNamespace(workshop_mode=None))
    assert not W.workshops_active(world)
    world = _world([_city(1, 0)], mode="operate")
    W.refresh_sites(world, world.livelihoods.workshops)
    with pytest.raises(ValueError, match="observe"):
        W.set_workshops_enabled(world, True, args=SimpleNamespace(workshop_mode="observe"))
    W.set_workshops_enabled(world, True, args=SimpleNamespace(workshop_mode="cost_only"))
    assert world.livelihoods.workshops.mode == "cost_only"


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


def test_observe_mode_charges_nothing_and_keeps_the_legacy_ceiling():
    world = _world([_city(1, 2, 2)])
    sim = _Sim()
    batch = _turn(world, sim, output=1.0)
    assert batch.column("craft_raw_demand").to_pylist()[2] == pytest.approx(1.5)
    receipt = world.livelihoods.workshops.frame[0]
    assert receipt.crew == [10, 20] and receipt.allocated == 0.0 and receipt.realized == 0.0
    assert receipt.paid is None and world.civilizations[0].treasury == 1000
    assert receipt.region_craft_input == {"timber": 1.0, "ore": 0.0}


def test_construction_installments_then_upkeep_and_a_ceiling_bounded_by_crew_work():
    world = _world([_city(1, 2, 2)], mode="operate")       # rank 2: d = 0.3
    sim = _Sim()
    for i in range(W.CONSTRUCTION_COST // W.INSTALLMENT):
        batch = _turn(world, sim, output=0.0)
        # While building, the site replaces the region's ceiling with zero.
        assert batch.column("craft_raw_demand").to_pylist()[2] == 0.0
        assert batch.column("craft_raw_demand").to_pylist()[1] == pytest.approx(1.5)
    site = world.livelihoods.workshops.sites[0]
    assert site.asset == "open" and site.construction_paid == W.CONSTRUCTION_COST
    assert world.civilizations[0].treasury == 1000 - W.CONSTRUCTION_COST
    batch = _turn(world, sim, output=0.6)
    ceiling = batch.column("craft_raw_demand").to_pylist()[2]
    assert ceiling == pytest.approx(W.K_RAW_PER_WORK * 0.6)           # 2 crew x 0.3
    receipt = world.livelihoods.workshops.frame[0]
    assert receipt.paid == {"upkeep": W.UPKEEP} and receipt.funded and receipt.payer == 0
    assert receipt.allocated == pytest.approx(0.6) and receipt.realized == pytest.approx(0.3)
    assert receipt.realized <= receipt.allocated and receipt.affected_ordinary_income_share == 0.0
    # Half the crew bounds the ceiling at half.
    sim.crew = 1
    batch = _turn(world, sim, output=0.0)
    assert batch.column("craft_raw_demand").to_pylist()[2] == pytest.approx(ceiling / 2)
    # No crew: funded upkeep, zero ceiling, zero work.
    sim.crew = 0
    batch = _turn(world, sim, output=0.0)
    assert batch.column("craft_raw_demand").to_pylist()[2] == 0.0
    assert world.livelihoods.workshops.frame[0].allocated == 0.0


def test_unfunded_turns_accrue_arrears_wear_condition_and_a_conqueror_inherits_them():
    world = _world([_city(1, 0, 1)], mode="operate", treasury=(1000, 0))
    sim = _Sim()
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT):
        _turn(world, sim)
    world.civilizations[0].treasury = 0
    for _ in range(12):
        batch = _turn(world, sim)
        assert batch.column("craft_raw_demand").to_pylist()[0] == 0.0
    site = world.livelihoods.workshops.sites[0]
    assert site.asset == "idle" and site.arrears == W.ARREARS_CAP
    assert site.condition < W.OPERATE_CONDITION
    # A conqueror with money inherits arrears and the repair; nothing is free.
    world.regions[0].controller = "Civ1"
    world.civilizations[1].treasury = 100
    _turn(world, sim, output=0.0)
    receipt = world.livelihoods.workshops.frame[0]
    assert receipt.payer == 1 and receipt.paid == {"upkeep": W.UPKEEP, "arrears": W.ARREARS_CAP, "repair": W.REPAIR_COST}
    assert world.civilizations[1].treasury == 100 - W.UPKEEP - W.ARREARS_CAP - W.REPAIR_COST
    assert site.arrears == 0 and site.condition == 1.0 and site.asset == "open"
    events = [(h[1], h[2]) for h in site.history]
    assert ("idle_unfunded", 0) in events
    assert events[-4:] == [("payer", 1), ("repaired", 1), ("arrears_paid", 1), ("reopened", 1)]


def test_insufficient_funds_charge_nothing_and_one_budget_is_shared_across_sites():
    world = _world([_city(1, 0, 3), _city(2, 1, 2)], mode="operate", treasury=(15,))
    sim = _Sim()
    _turn(world, sim)
    paid = [r.paid for r in world.livelihoods.workshops.frame]
    # One projected budget: the first site's installment fits, the second does not.
    assert paid == [{"construction": W.INSTALLMENT}, {}]
    assert world.civilizations[0].treasury == 15 - W.INSTALLMENT


def test_failed_tick_charges_nothing_and_rollback_releases_the_plan():
    world = _world([_city(1, 0)], mode="operate")
    sim = _Sim()
    W.prepare_phase2(world, _batch(), SimpleNamespace(_sim=sim), None, None)
    with pytest.raises(RuntimeError, match="pending"):
        W.prepare_phase2(world, _batch(), SimpleNamespace(_sim=sim), None, None)
    W.rollback_phase2(world)
    assert world.civilizations[0].treasury == 1000
    assert world.livelihoods.workshops.sites[0].construction_paid == 0
    with pytest.raises(RuntimeError, match="missing"):
        W.finish_phase2(world, SimpleNamespace(craft_output={}), SimpleNamespace(_sim=sim), None)


def test_cost_only_pays_like_operate_but_keeps_the_legacy_ceiling():
    world = _world([_city(1, 0, 2)], mode="cost_only")
    sim = _Sim()
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT + 1):
        batch = _turn(world, sim, output=0.5)
        assert batch.column("craft_raw_demand").to_pylist()[0] == pytest.approx(1.5)
    receipt = world.livelihoods.workshops.frame[0]
    assert receipt.paid == {"upkeep": W.UPKEEP} and receipt.allocated == 0.0 and receipt.realized == 0.0
    assert world.civilizations[0].treasury == 1000 - W.CONSTRUCTION_COST - W.UPKEEP


def test_city_fall_closes_the_site_and_writes_off_arrears():
    world = _world([_city(1, 0)], mode="operate", treasury=(60,))
    sim = _Sim()
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT):
        _turn(world, sim)
    _turn(world, sim)                          # unfunded: arrears accrue
    fallen = world.cities.cities.pop()
    world.cities.fallen.append(fallen)
    batch = _turn(world, sim)
    state = world.livelihoods.workshops
    assert not state.sites and state.closed[0].asset == "closed"
    assert state.counters["arrears_written_off"] == W.UPKEEP
    # A closed site no longer replaces the ceiling.
    assert batch.column("craft_raw_demand").to_pylist()[0] == pytest.approx(1.5)


def test_missing_native_inputs_are_unknown_and_snapshot_is_dated():
    world = _world([_city(1, 0)])
    batch = pa.record_batch({"region_id": pa.array(range(6), pa.uint16())})
    sim = _Sim()
    W.prepare_phase2(world, batch, SimpleNamespace(_sim=sim), None, None)
    W.finish_phase2(world, SimpleNamespace(craft_output={}), SimpleNamespace(_sim=sim), None)
    receipt = world.livelihoods.workshops.frame[0]
    assert receipt.region_craft_input is None and receipt.region_craft_output is None
    assert receipt.legacy_craft_ceiling is None
    world.turn += 1
    summary = W.snapshot_summary(world)
    assert summary["source_turn"] == 20 and summary["receipts"][0]["crew"] == [10, 20]
    world.turn += 1
    assert W.snapshot_summary(world)["receipts"] is None


def test_prepare_requires_native():
    world = _world([_city(1, 0)])
    with pytest.raises(RuntimeError, match="native"):
        W.prepare_phase2(world, _batch(), SimpleNamespace(_sim=object()), None, None)
