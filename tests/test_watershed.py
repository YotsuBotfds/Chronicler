"""Watershed account (``--watershed``): B1 (S1-A) ``record_only`` and B2 ``flow``, offline.

docs/integration/watershed.md. The pure-Python ecology fallback runs the
tick here (no extension). Acceptance cases from the program-B audit's S1-A
test plan: the drainage graph (every persisted river step reproduced on the
procedural development worlds, one destination per region, a topological
order, confluence inflow equal to the tributaries' outflow), river and
template refusals, the conserved account (closure every turn, bounds,
non-negative flows, external inflows recorded as such, irrigation's
upstream/downstream trade-off), floods and droughts with their recorded
conditions, record_only changing nothing outside its state and drawing no
randomness, a turn settling once, the transient plan's reset, the dated
record, registry and catalog entries, refusals of a switch change on resume
and an exact checkpoint resume equal to the straight run. B2 (``flow``): the
replaced native terms switched off once through the seam, refusals (no native
ecology, the Python fallback, a stale baseline, a mode change on resume), the
derived index written and floods acting through existing fields, the river
flood superseded with its draws kept, and the untouched state of the
replaced terms.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import pickle
import random
from pathlib import Path

import pytest

from chronicler import watershed as ws
from chronicler.climate import get_climate_phase
from chronicler.ecology import tick_ecology
from chronicler.livelihoods import (
    after_ecology, before_ecology, configure_livelihoods, livelihoods_resume_conflicts,
    livelihoods_snapshot_fields,
)
from chronicler.main import _build_parser
from chronicler.models import Infrastructure, InfrastructureType, River
from chronicler.watershed_state import COUNTER_KEYS, FLOW_KEYS, FRAME_COLUMNS, SEA, SINK, WatershedState
from chronicler.world_gen import generate_world

DEVELOPMENT_PROCEDURAL = (7, 11, 13, 17, 21, 31, 302, 303)


def _procedural(seed=11, regions=32, civs=10):
    return generate_world(seed=seed, num_regions=regions, num_civs=civs, worldgen="procedural")


def _world(seed=11, *flags, regions=32, civs=10):
    world = _procedural(seed, regions, civs)
    configure_livelihoods(world, _build_parser().parse_args(["--watershed", *flags]), agent_mode="off")
    return world


def _state(world) -> WatershedState:
    return world.livelihoods.watershed


def _phase9(world):
    before_ecology(world, acc=None)
    tick_ecology(world, get_climate_phase(world.turn, world.climate_config), acc=None)
    events = after_ecology(world, acc=None)
    world.turn += 1
    return events


def _headwater_chain(state):
    """A region with an inland tributary (the first confluence-like edge)."""
    down = state.graph.down
    for r, d in enumerate(down):
        if d >= 0:
            return r, d
    raise AssertionError("no inland drainage edge")


def _set_storage(state, r: int, value: float) -> None:
    """A constructed test condition: the opening storage moves with it, so the
    cumulative account still closes (the account itself never creates water)."""
    state.opening_storage += value - state.storage[r]
    state.storage[r] = value


def _strip(dump: dict) -> dict:
    dump = copy.deepcopy(dump)
    container = dump.get("livelihoods") or {}
    container.pop("watershed", None)
    return dump


# --- The drainage graph ---------------------------------------------------------------

@pytest.mark.parametrize("seed, regions, civs", [(s, 32, 10) for s in DEVELOPMENT_PROCEDURAL]
                         + [(7, 64, 16), (11, 64, 16)])
def test_the_drainage_graph_reproduces_every_persisted_river_step(seed, regions, civs):
    world = _procedural(seed, regions, civs)
    graph = ws.build_graph(world)
    n = len(world.regions)
    assert len(graph.down) == n and sorted(graph.order) == list(range(n))
    assert graph.river_steps == sum(len(r.path) - 1 for r in world.rivers)
    index = {r.name: i for i, r in enumerate(world.regions)}
    for river in world.rivers:
        for a, b in zip(river.path, river.path[1:]):
            assert graph.down[index[a]] == index[b]
    position = {r: k for k, r in enumerate(graph.order)}
    lanes = {frozenset(p) for p in world.geography.sea_lanes}
    for i, region in enumerate(world.regions):
        d = graph.down[i]
        if region.geo.coastal:
            assert d == SEA
            continue
        land = [index[a] for a in region.adjacencies if frozenset((region.name, a)) not in lanes]
        lower = [j for j in land if world.regions[j].geo.elevation < region.geo.elevation]
        if not lower:
            assert d == SINK
            continue
        assert d in land and world.regions[d].geo.elevation == min(world.regions[j].geo.elevation for j in lower)
        assert position[d] > position[i]              # every region after all regions draining into it
    for i in range(n):                                   # acyclic: each path ends at the sea or a sink
        node, hops = i, 0
        while node >= 0:
            node, hops = graph.down[node], hops + 1
            assert hops <= n
        assert node in (SEA, SINK)


def test_river_validation_refuses_reversed_duplicates_cycles_and_multiple_targets():
    names = ["A", "B", "C", "D"]
    ws.validate_river_paths([River(name="ok", path=["A", "B", "C"]), River(name="trib", path=["D", "C"])], names)
    with pytest.raises(ValueError, match="reversed duplicate"):
        ws.validate_river_paths([River(name="up", path=["A", "B"]), River(name="down", path=["B", "A"])], names)
    with pytest.raises(ValueError, match="multiple downstream targets"):
        ws.validate_river_paths([River(name="one", path=["A", "B"]), River(name="two", path=["A", "C"])], names)
    with pytest.raises(ValueError, match="cycle"):
        ws.validate_river_paths([River(name="loop", path=["A", "B", "C", "A"])], names)
    with pytest.raises(ValueError, match="unknown region"):
        ws.validate_river_paths([River(name="lost", path=["A", "Z"])], names)
    with pytest.raises(ValueError, match="does not move"):
        ws.validate_river_paths([River(name="still", path=["A", "A"])], names)


def test_scenario_rivers_that_fail_validation_or_contradict_elevation_are_refused():
    world = _procedural(11)
    graph = ws.build_graph(world)
    a, b = next((i, d) for i, d in enumerate(graph.down) if d >= 0)
    na, nb = world.regions[a].name, world.regions[b].name
    reversed_world = world.model_copy(deep=True)
    reversed_world.rivers = [River(name="the Up", path=[na, nb]), River(name="the Down", path=[nb, na])]
    with pytest.raises(ValueError, match="reversed duplicate"):
        ws.build_graph(reversed_world)
    uphill = world.model_copy(deep=True)
    uphill.rivers = [River(name="the Uphill", path=[nb, na])]
    with pytest.raises(ValueError, match="drains"):
        ws.build_graph(uphill)
    with pytest.raises(ValueError, match="drains"):
        configure_livelihoods(uphill, _build_parser().parse_args(["--watershed"]), agent_mode="off")


def test_template_worlds_are_refused_at_startup_and_on_resume():
    template = generate_world(seed=7)
    assert template.geography is None
    with pytest.raises(ValueError, match="requires a procedural world"):
        configure_livelihoods(template, _build_parser().parse_args(["--watershed"]), agent_mode="hybrid")
    assert template.livelihoods is None            # refused before anything changed
    resumed = generate_world(seed=3)
    resumed.turn = 12                               # a state-file resume of a template world
    with pytest.raises(ValueError, match="requires a procedural world"):
        configure_livelihoods(resumed, _build_parser().parse_args(["--watershed"]), agent_mode="off")
    # Without the switch a template world is untouched.
    configure_livelihoods(template, _build_parser().parse_args([]), agent_mode="off")
    assert template.livelihoods is None


def test_a_switch_change_on_a_state_file_resume_is_refused():
    late = _procedural(13)
    late.turn = 20
    with pytest.raises(ValueError, match="opens its account with a new world"):
        configure_livelihoods(late, _build_parser().parse_args(["--watershed"]), agent_mode="off")
    world = _world(13)
    with pytest.raises(ValueError, match="cannot be ended"):
        configure_livelihoods(world, _build_parser().parse_args(["--no-watershed"]), agent_mode="off")
    world.turn = 20                                 # an omitted or repeated switch keeps the account
    before = _state(world).model_dump()
    configure_livelihoods(world, _build_parser().parse_args([]), agent_mode="off")
    configure_livelihoods(world, _build_parser().parse_args(["--watershed"]), agent_mode="off")
    assert _state(world).model_dump() == before
    with pytest.raises(ValueError, match="watershed_mode"):
        ws.check_request(world, True, argparse.Namespace(watershed_mode="bogus"))


def test_a_mode_change_on_a_state_file_resume_is_refused():
    world = _world(13)
    with pytest.raises(ValueError, match="conflicts with this world's watershed account"):
        ws.check_request(world, None, argparse.Namespace(watershed_mode="flow"))
    ws.check_request(world, None, argparse.Namespace(watershed_mode="record_only"))


def test_exact_resume_refuses_a_switch_change():
    world = _world(11)
    assert livelihoods_resume_conflicts(world, argparse.Namespace(watershed=None), {}) == []
    assert livelihoods_resume_conflicts(world, argparse.Namespace(watershed=True), {}) == []
    assert livelihoods_resume_conflicts(world, argparse.Namespace(watershed=False), {}) == [
        "--watershed False conflicts with the checkpoint (saved: True)"]
    off = _procedural(11)
    assert livelihoods_resume_conflicts(off, argparse.Namespace(watershed=True), {}) == [
        "--watershed True conflicts with the checkpoint (saved: False)"]
    assert livelihoods_resume_conflicts(off, argparse.Namespace(watershed_mode="record_only"), {}) == [
        "--watershed-mode 'record_only' conflicts with the checkpoint (saved: None)"]


# --- The account ----------------------------------------------------------------------

def _check_frame(state, world):
    """Independent re-check of a settled frame from its columns."""
    frame = state.frame
    c = frame.columns
    n = len(world.regions)
    down = state.graph.down
    for r in range(n):
        flows = [c[k][r] for k in ("precipitation", "external_in", "external_out", "inflow", "evaporation",
                                   "withdrawal", "outflow", "storage_open", "storage", "capacity")]
        assert all(v >= 0.0 and math.isfinite(v) for v in flows)
        assert c["storage"][r] <= c["capacity"][r]
        lhs = c["storage"][r] - c["storage_open"][r]
        rhs = (c["precipitation"][r] + c["external_in"][r] - c["external_out"][r] + c["inflow"][r]
               - c["evaporation"][r] - c["withdrawal"][r] - c["outflow"][r])
        assert abs(lhs - rhs) <= 1e-9 * max(1.0, sum(abs(v) for v in flows))
        tributaries = [c["outflow"][u] for u in range(n) if down[u] == r]
        assert math.isclose(math.fsum(tributaries), c["inflow"][r], rel_tol=1e-12, abs_tol=1e-15)
        lo, hi = ws.INDEX_FLOOR, ws.index_cap(world.regions[r])
        assert lo - 1e-12 <= c["index_derived"][r] <= hi + 1e-12
    sea = math.fsum(c["outflow"][r] for r in range(n) if down[r] == SEA)
    sink = math.fsum(c["outflow"][r] for r in range(n) if down[r] == SINK)
    assert math.isclose(frame.totals["to_sea"], sea, rel_tol=1e-12, abs_tol=1e-15)
    assert math.isclose(frame.totals["to_sink"], sink, rel_tol=1e-12, abs_tol=1e-15)
    t = frame.totals
    lake = math.fsum(c["outflow"][r] for r in range(n) if down[r] == ws.LAKE)
    assert math.isclose(frame.totals["to_lake"], lake, rel_tol=1e-12, abs_tol=1e-15)
    net = t["precipitation"] + t["external_in"] - t["external_out"] - t["evaporation"] - t["withdrawal"] \
        - t["to_sea"] - t["to_sink"] - t["to_lake"]
    gross = sum(abs(t[k]) for k in FLOW_KEYS) + frame.storage_open + frame.storage_close
    assert abs((frame.storage_close - frame.storage_open) - net) <= 1e-9 * gross
    assert abs(frame.closure_residual) <= 1e-9 * gross
    cum = state.cumulative
    cum_net = cum["precipitation"] + cum["external_in"] - cum["external_out"] - cum["evaporation"] \
        - cum["withdrawal"] - cum["to_sea"] - cum["to_sink"] - cum["to_lake"]
    cum_gross = sum(abs(cum[k]) for k in FLOW_KEYS) + state.opening_storage
    assert abs((math.fsum(state.storage) - state.opening_storage) - cum_net) <= 1e-9 * cum_gross


def test_the_account_closes_every_turn_of_a_climate_cycle():
    world = _world(31)
    state = _state(world)
    assert state.counters == {key: 0 for key in COUNTER_KEYS}
    phases = set()
    for _ in range(80):
        _phase9(world)
        _check_frame(state, world)
        phases.add(state.frame.phase)
        assert state._plan is None                   # the transient plan is consumed every turn
    assert phases == {"temperate", "warming", "drought", "cooling"}
    assert state.counters["settled_turns"] == state.counters["planned_turns"] == 80
    assert state.cumulative["precipitation"] > 0 and state.cumulative["to_sea"] > 0
    assert state.cumulative["to_sink"] > 0           # procedural 31 has a closed basin


def test_opening_storage_is_continuous_with_the_index():
    world = _world(11)
    state = _state(world)
    for r, region in enumerate(world.regions):
        cap = ws.capacity(min(1.0, max(0.0, region.ecology.forest_cover)))
        assert 0.0 <= state.storage[r] <= cap
        assert math.isclose(ws.derived_index(region, state.storage[r], 0.0, cap),
                            max(ws.INDEX_FLOOR, min(ws.index_cap(region), region.ecology.water)), abs_tol=1e-12)
    assert state.last_index == [r.ecology.water for r in world.regions]
    assert math.isclose(state.opening_storage, math.fsum(state.storage))


def test_an_index_change_between_turns_is_an_external_inflow_or_outflow():
    world = _world(11)
    _phase9(world)
    state = _state(world)
    coast = next(i for i, r in enumerate(world.regions)
                 if state.graph.down[i] == SEA and state.last_index[i] + 0.1 <= ws.index_cap(r))
    region = world.regions[coast]
    region.ecology.water = min(ws.index_cap(region), state.last_index[coast] + 0.1)   # a coastal flood
    delta = region.ecology.water - state.last_index[coast]
    cap = ws.capacity(min(1.0, max(0.0, region.ecology.forest_cover)))
    _phase9(world)
    c = state.frame.columns
    assert math.isclose(c["external_in"][coast], delta / (ws.index_cap(region) - ws.INDEX_FLOOR) * cap)
    assert sum(1 for v in c["external_in"] if v > 0) == 1 and sum(c["external_out"]) == 0
    _check_frame(state, world)
    # A drop larger than the storage is limited to the storage; the rest is unmet, not taken elsewhere.
    _set_storage(state, coast, 0.01)
    region.ecology.water = ws.INDEX_FLOOR
    state.last_index[coast] = ws.index_cap(region)
    _phase9(world)
    assert state.frame.columns["external_out"][coast] == pytest.approx(0.01)
    assert state.frame.totals["external_out_unmet"] > 0 and state.counters["external_out_unmet_turns"] == 1
    _check_frame(state, world)


def test_irrigation_withdraws_upstream_water_and_lowers_downstream_inflow():
    plain = _world(11)
    up, down = _headwater_chain(_state(plain))
    irrigated = copy.deepcopy(plain)
    irrigated.regions[up].infrastructure.append(
        Infrastructure(type=InfrastructureType.IRRIGATION, builder_civ="x", built_turn=0))
    _phase9(plain)
    _phase9(irrigated)
    a, b = _state(plain).frame.columns, _state(irrigated).frame.columns
    assert a["withdrawal"][up] == 0.0 and b["withdrawal"][up] == pytest.approx(ws.IRRIGATION_DEMAND)
    assert b["outflow"][up] < a["outflow"][up] and b["inflow"][down] < a["inflow"][down]
    assert b["index_derived"][up] > ws.INDEX_FLOOR
    _check_frame(_state(irrigated), irrigated)


def test_forest_cover_raises_capacity_and_transpiration():
    world = _world(11)
    r = 0
    low, high = copy.deepcopy(world), copy.deepcopy(world)
    low.regions[r].ecology.forest_cover = 0.0
    high.regions[r].ecology.forest_cover = 0.9
    _phase9(low)
    _phase9(high)
    lc, hc = _state(low).frame.columns, _state(high).frame.columns
    assert hc["capacity"][r] > lc["capacity"][r] == ws.STORAGE_BASE
    assert hc["evaporation"][r] >= lc["evaporation"][r]


def test_a_flood_is_recorded_with_the_arrivals_and_tributaries_that_caused_it():
    world = _world(11)
    state = _state(world)
    up, down = _headwater_chain(state)
    _set_storage(state, up, 10.0)                   # far above capacity: it overflows downstream
    _phase9(world)
    flood = next(f for f in state.frame.floods if f.region == down)
    c = state.frame.columns
    assert flood.turn == state.frame.turn and flood.excess == pytest.approx(c["flood_excess"][down])
    assert flood.arrivals == pytest.approx(flood.precipitation + flood.inflow + flood.external_in)
    assert flood.excess == pytest.approx(flood.arrivals - flood.channel)
    assert dict(flood.tributaries)[up] == pytest.approx(c["outflow"][up])
    assert math.fsum(q for _, q in flood.tributaries) == pytest.approx(flood.inflow)
    assert flood.upstream_cover is not None and state.counters["flood_region_turns"] >= 1
    _check_frame(state, world)


def test_a_drought_is_declared_with_its_conditions_and_ended_when_storage_recovers():
    world = _world(11)
    world.turn = 45                                 # the drought phase of the 75-turn cycle
    state = _state(world)
    head = next(r for r in range(len(world.regions))
                if not ws.upstream_regions(state)[r])
    for _ in range(ws.DROUGHT_TURNS):
        _set_storage(state, head, 0.0)
        state.last_index[head] = world.regions[head].ecology.water
        _phase9(world)
    spell = next(s for s in state.spells if s.region == head)
    assert spell.turns == ws.DROUGHT_TURNS and spell.declared_turn == world.turn - 1
    assert spell.start_turn == 45 and spell.normal_precipitation > spell.precipitation   # forcing deficit
    assert state.counters["droughts_declared"] >= 1
    record = livelihoods_snapshot_fields(world)["livelihoods"]["watershed"]
    assert any(s["region"] == head for s in record["droughts"]["open"])
    assert record["regions"]["drought_turns"][head] == ws.DROUGHT_TURNS
    _set_storage(state, head, ws.capacity(1.0))     # refilled: the next settled turn ends it
    _phase9(world)
    ended = next(s for s in state.frame.droughts_ended if s.region == head)
    assert ended.end_turn == state.frame.turn and ended.turns == ws.DROUGHT_TURNS
    assert all(s.region != head for s in state.spells)


# --- record_only changes nothing and draws no randomness -------------------------------

def test_record_only_mutates_nothing_outside_its_state():
    world = _world(11)
    world.regions[0].infrastructure.append(
        Infrastructure(type=InfrastructureType.IRRIGATION, builder_civ="x", built_turn=0))
    for _ in range(6):
        before = _strip(world.model_dump(mode="json"))
        before_dicts = [sorted(vars(r)) for r in world.regions]
        before_ecology(world, acc=None)
        assert _strip(world.model_dump(mode="json")) == before
        tick_ecology(world, get_climate_phase(world.turn, world.climate_config), acc=None)
        middle = _strip(world.model_dump(mode="json"))
        after_ecology(world, acc=None)
        assert _strip(world.model_dump(mode="json")) == middle
        assert [sorted(vars(r)) for r in world.regions] == before_dicts
        world.turn += 1


def test_the_hooks_draw_no_randomness(monkeypatch):
    world = _world(13)
    _phase9(world)

    def refuse(*args, **kwargs):
        raise AssertionError("the watershed drew randomness")

    for name in ("random", "randint", "randrange", "uniform", "choice", "choices", "shuffle", "sample",
                 "gauss", "getrandbits", "seed"):
        monkeypatch.setattr(random.Random, name, refuse)
        monkeypatch.setattr(random, name, refuse)
    before_ecology(world, acc=None)
    monkeypatch.undo()
    tick_ecology(world, get_climate_phase(world.turn, world.climate_config), acc=None)
    for name in ("random", "randint", "randrange", "uniform", "choice", "shuffle", "sample", "gauss"):
        monkeypatch.setattr(random.Random, name, refuse)
        monkeypatch.setattr(random, name, refuse)
    after_ecology(world, acc=None)
    livelihoods_snapshot_fields(world)


def test_the_account_is_deterministic():
    def run():
        world = _world(17)
        for _ in range(30):
            _phase9(world)
        return json.dumps(_state(world).model_dump(mode="json"), sort_keys=True)

    assert run() == run()


# --- A turn settles once ------------------------------------------------------------------

def test_a_failed_tick_settles_nothing_and_the_next_turn_settles_cleanly():
    world = _world(11)
    _phase9(world)
    state = _state(world)
    storage, frame = list(state.storage), state.frame.model_copy(deep=True)
    before_ecology(world, acc=None)                  # the tick then fails: no settlement
    assert state._plan is not None and state.storage == storage and state.frame == frame
    clean = copy.deepcopy(world)
    clean.livelihoods.watershed._plan = None
    before_ecology(world, acc=None)                  # the next planning drops the stale plan
    assert state.counters["abandoned_plans"] == 1
    tick_ecology(world, get_climate_phase(world.turn, world.climate_config), acc=None)
    after_ecology(world, acc=None)
    _check_frame(state, world)
    _phase9(clean)
    assert state.storage == _state(clean).storage   # the dropped plan left no trace
    with pytest.raises(RuntimeError, match="plan missing"):
        after_ecology(world, acc=None)              # no plan: nothing settles twice
    before_ecology(world, acc=None)
    world.turn += 1
    with pytest.raises(RuntimeError, match="plan missing"):
        after_ecology(world, acc=None)              # a plan of another turn


def test_a_pending_plan_is_never_serialized():
    world = _world(11)
    before_ecology(world, acc=None)
    assert _state(world)._plan is not None
    restored = pickle.loads(pickle.dumps(world))
    assert restored.livelihoods.watershed._plan is None
    assert restored.livelihoods.watershed.model_dump() == _state(world).model_dump()
    via_json = WatershedState.model_validate_json(_state(world).model_dump_json())
    assert via_json.model_dump() == _state(world).model_dump()


# --- The record -----------------------------------------------------------------------

def test_the_snapshot_record_is_dated_copied_and_distinguishes_unobserved():
    world = _world(11)
    world.turn = 1                                   # no Phase 9 settled yet
    opening = livelihoods_snapshot_fields(world)["livelihoods"]["watershed"]
    assert opening["observed"] is False and opening["source_turn"] == 0
    assert opening["regions"] is None and opening["floods"] is None and opening["totals"] is None
    assert opening["external"] is None and opening["stale_baseline"] is None
    assert len(opening["storage"]) == len(world.regions)
    world.turn = 0
    _phase9(world)
    record = livelihoods_snapshot_fields(world)["livelihoods"]["watershed"]
    assert (record["schema_version"], record["stage"], record["mode"]) == (1, "B1", "record_only")
    assert record["source_turn"] == world.turn - 1 == record["completed_turn"] - 1 and record["observed"]
    # Outflow is each region's residual by construction: readers derive it.
    assert set(record["regions"]) == set(FRAME_COLUMNS) - {"outflow"} | {"drought_turns"}
    assert record["storage"] is None                 # the settled turn's regions.storage is the same list
    assert record["graph"]["down"] == _state(world).graph.down and record["graph"]["lake"] == -3
    assert record["parameters"] == ws.parameters() and record["stale_baseline"] is False
    json.dumps(record)
    record["regions"]["storage"][0] = -1.0           # a copy, never live state
    assert _state(world).frame.columns["storage"][0] >= 0.0
    _phase9(world)                                   # every record carries the static part (review N2)
    later = livelihoods_snapshot_fields(world)["livelihoods"]["watershed"]
    assert later["observed"] and later["graph"] == record["graph"] and later["parameters"] == record["parameters"]
    world.turn += 1                                  # a later snapshot without a settled turn
    assert livelihoods_snapshot_fields(world)["livelihoods"]["watershed"]["observed"] is False


def test_lake_shores_drain_to_closed_water_not_to_the_sea():
    world = _procedural(11)
    zones = {z.name: z for z in world.geography.sea_zones}
    shore = next(i for i, r in enumerate(world.regions) if r.geo.coastal and len(r.geo.sea_zones) == 1)
    lake = world.model_copy(deep=True)
    zone = next(z for z in lake.geography.sea_zones if z.name == world.regions[shore].geo.sea_zones[0])
    zone.kind = "lake"                               # a constructed lake (no development world has one)
    assert zones[zone.name].kind != "lake"
    graph = ws.build_graph(lake)
    assert graph.down[shore] == ws.LAKE
    for i, r in enumerate(lake.regions):            # a shore that also touches open sea still drains to the sea
        if r.geo.coastal and zone.name in r.geo.sea_zones and len(r.geo.sea_zones) > 1:
            assert graph.down[i] == SEA
    configure_livelihoods(lake, _build_parser().parse_args(["--watershed"]), agent_mode="off")
    _phase9(lake)
    frame = _state(lake).frame
    assert frame.totals["to_lake"] > 0 and frame.totals["to_lake"] == pytest.approx(math.fsum(
        frame.columns["outflow"][i] for i, d in enumerate(graph.down) if d == ws.LAKE))
    assert frame.totals["to_sea"] == pytest.approx(math.fsum(
        frame.columns["outflow"][i] for i, d in enumerate(graph.down) if d == SEA))
    _check_frame(_state(lake), lake)


def test_external_inflow_is_attributed_to_a_coastal_flood_and_the_rest_left_unattributed():
    from chronicler.climate import _deterministic_roll, _disaster_probability, check_disasters
    from chronicler.geography import disaster_factor
    world = _world(11)
    _phase9(world)
    state = _state(world)
    coast = next(i for i, r in enumerate(world.regions) if r.terrain == "coast")
    region = world.regions[coast]
    region.ecology.water = state.last_index[coast] = 0.5   # constructed: room for the flood's +0.1

    def strikes(turn):
        phase = get_climate_phase(turn, world.climate_config)
        prob = _disaster_probability("flood", "coast", phase, world.climate_config.severity)
        prob *= disaster_factor(region.latitude_band, "flood") if region.latitude_band is not None else 1.0
        return _deterministic_roll(world.seed, region.name, turn, "flood") < prob

    turn = next(t for t in range(world.turn, world.turn + 5000) if strikes(t))
    world.turn = turn
    state.frame = state.frame.model_copy(update={"turn": turn - 1})   # constructed: the previous turn settled
    for r in world.regions:
        r.disaster_cooldowns.clear()
    others = [float(r.ecology.water) for r in world.regions]
    check_disasters(world, get_climate_phase(turn, world.climate_config))   # the real Phase 1 authority
    assert region.ecology.water == pytest.approx(0.6) and ws.coastal_flood_gain(world, region) == pytest.approx(0.1)
    struck = [i for i, r in enumerate(world.regions) if r.ecology.water != others[i]]
    region.ecology.water += 0.05                     # another writer on top of the flood
    _phase9(world)
    frame = state.frame
    assert not frame.stale_baseline
    flows = {(f.region, f.source): f.amount for f in frame.external}
    span = ws.index_cap(region) - ws.INDEX_FLOOR
    cap = frame.columns["capacity"][coast]
    assert flows[(coast, "coastal_flood")] == pytest.approx(0.1 / span * cap)
    assert flows[(coast, "unattributed")] == pytest.approx(0.05 / span * cap)
    assert {i for i, _ in flows} == set(struck) | {coast}
    assert frame.totals["external_in"] == pytest.approx(
        frame.totals["external_in_coastal_flood"] + frame.totals["external_in_unattributed"])
    record = livelihoods_snapshot_fields(world)["livelihoods"]["watershed"]
    assert {(f["region"], f["source"]) for f in record["external"]} == set(flows)
    _check_frame(state, world)


def test_a_stale_baseline_is_recorded_and_left_unattributed():
    world = _world(11)
    _phase9(world)
    state = _state(world)
    before_ecology(world, acc=None)                  # a tick that never settles ...
    tick_ecology(world, get_climate_phase(world.turn, world.climate_config), acc=None)
    world.turn += 1                                  # ... and the run goes on
    _phase9(world)
    assert state.frame.stale_baseline and state.counters["stale_baseline_turns"] == 1
    assert all(f.source == "unattributed" for f in state.frame.external)
    _phase9(world)                                   # the next settled turn is clean again
    assert not state.frame.stale_baseline and state.counters["stale_baseline_turns"] == 1
    gap = _world(13)
    _phase9(gap)
    gap.turn += 3                                    # a missing turn (e.g. an out-of-band load)
    _phase9(gap)
    assert _state(gap).frame.stale_baseline


def test_feature_off_keeps_no_state_and_no_manifest_keys():
    from chronicler.batch_manifest import simulation_config
    world = _procedural(11)
    configure_livelihoods(world, _build_parser().parse_args([]), agent_mode="off")
    assert world.livelihoods is None and livelihoods_snapshot_fields(world) == {}
    config = simulation_config(_build_parser().parse_args([]))
    assert "watershed" not in config and "watershed_mode" not in config
    on = simulation_config(_build_parser().parse_args(["--watershed"]))
    assert on["watershed"] is True and "watershed_mode" not in on
    assert simulation_config(_build_parser().parse_args(["--watershed", "--watershed-mode", "record_only"])
                             )["watershed_mode"] == "record_only"


def test_the_feature_catalog_requires_a_procedural_world():
    from chronicler import feature_catalog as fc
    entry = next(e for e in fc.feature_entries() if e["key"] == "watershed")
    assert entry["requires"] == [{"setting": "procedural_world",
                                  "reason": "requires " + fc.SETTINGS["procedural_world"]}]
    mode = next(e for e in fc.feature_entries() if e["key"] == "watershed_mode")
    assert mode["parent"] == "watershed" and mode["choices"] == ["record_only", "flow"]
    live = fc.live_surface(argparse.Namespace(agents="hybrid"))
    assert fc.validate_features({"watershed": True}, live).startswith("'watershed' (--watershed) requires a procedural")
    assert fc.validate_batch_features({"regions": 32, "features": {"watershed": True}}, {"agents": "off"}) is None
    assert fc.validate_batch_features({"regions": 8, "features": {"watershed": True}}, {"agents": "off"}) \
        .startswith("'watershed' (--watershed) requires a procedural")


def test_the_batch_surface_follows_the_requested_regions():
    from chronicler import feature_catalog as fc
    assert fc.batch_surface({"agents": "off"})["settings"]["procedural_world"] is False      # the default 8 regions
    assert fc.batch_surface({"agents": "off"}, {"regions": 13})["settings"]["procedural_world"] is True
    assert fc.batch_surface({"agents": "off"}, {"regions": 12})["settings"]["procedural_world"] is False
    assert fc.batch_surface({"agents": "off", "regions": 32})["settings"]["procedural_world"] is True
    # The viewer's TEMPLATE_REGION_POOL (viewer/src/lib/featureWorld.ts) mirrors this threshold.
    from chronicler.world_gen import REGION_TEMPLATES, resolve_worldgen
    assert len(REGION_TEMPLATES) == 12
    assert (resolve_worldgen(None, 12), resolve_worldgen(None, 13)) == ("template", "procedural")


@pytest.fixture
def sentinel_runtimes(monkeypatch):
    from chronicler import agent_bridge, main

    class Accepted(Exception):
        pass

    def accepted(*args, **kwargs):
        raise Accepted

    monkeypatch.setattr(agent_bridge, "AgentBridge", accepted)
    monkeypatch.setattr(main, "_create_ecology_runtime", accepted)
    return Accepted


@pytest.mark.parametrize("agents", ["off", "demographics-only", "shadow", "hybrid"])
def test_the_run_accepts_every_agent_mode_on_a_procedural_world(tmp_path, sentinel_runtimes, agents):
    from chronicler import main
    args = _build_parser().parse_args(["--seed", "11", "--turns", "3", "--regions", "16", "--civs", "4",
                                       "--worldgen", "procedural", "--agents", agents, "--watershed",
                                       "--simulate-only", "--output", str(tmp_path / "c.md")])
    world = generate_world(seed=11, num_regions=16, num_civs=4, worldgen="procedural")
    with pytest.raises(sentinel_runtimes):
        main._configure_run(args, world, True, tmp_path / "c.md")
    assert world.livelihoods.watershed is not None
    template = generate_world(seed=11, num_regions=8, num_civs=4)
    with pytest.raises(ValueError, match="requires a procedural world"):
        main._configure_run(args, template, True, tmp_path / "c.md")


class _Stop(Exception):
    pass


def _lobby(starts):
    """A LiveServer without sockets whose viewer sends ``starts`` in turn (the
    next one when the lobby reopens); replies and reopenings are recorded."""
    from chronicler.live import LiveServer

    class Server(LiveServer):
        def __init__(self):
            super().__init__(port=0)
            self.starts, self.replies, self.reopened = list(starts), [], []

        def _send_next(self):
            # A refused start leaves the lobby open: the viewer then sends the next one.
            while self.starts:
                reply = self._handle_start({"type": "start", **self.starts.pop(0)})
                self.replies.append(reply)
                if reply is None:
                    return

        def start(self):
            self._actual_port = 0
            self._send_next()

        def stop(self):
            pass

        def reopen_lobby(self, message):
            super().reopen_lobby(message)
            self.reopened.append(message)
            self._send_next()

    return Server()


def test_a_live_lobby_refuses_a_template_start_and_keeps_running(tmp_path, monkeypatch):
    """Review N1: a start that asks for the watershed on a template world is refused with the
    reason and the lobby reopens (the process keeps running); a saved state is refused at
    validation; a procedural start then runs with the account."""
    from chronicler import feature_catalog as fc
    from chronicler import live, main
    assert fc.live_surface(_build_parser().parse_args(["--agents", "hybrid"]))["settings"]["procedural_world"] is False
    seen = {}

    def execute_run(args, **kwargs):
        seen["world"] = kwargs["world"]
        raise _Stop

    monkeypatch.setattr(main, "execute_run", execute_run)
    monkeypatch.setattr(live, "_get_available_models", lambda args: [""])
    template = {"turns": 3, "civs": 4, "regions": 8, "seed": 11, "features": {"watershed": True}}
    resumed = {"turns": 3, "civs": 4, "regions": 8, "features": {"watershed": True}, "resume_state": {"turn": 4}}
    procedural = {"turns": 3, "civs": 4, "regions": 16, "seed": 11, "features": {"watershed": True}}
    server = _lobby([template, resumed, procedural])
    args = _build_parser().parse_args(["--live", "--agents", "off", "--simulate-only",
                                       "--output", str(tmp_path / "chronicle.md")])
    assert fc.live_surface(args)["settings"]["procedural_world"] is True     # the run checks a live start's world
    with pytest.raises(_Stop):
        live.run_live(args, server=server)
    assert len(server.reopened) == 1 and server.reopened[0].startswith(
        "Start field 'features': --watershed requires a procedural world")
    assert server.replies[0] is None                 # accepted by the catalog, refused by the run
    assert server.replies[1] == {"type": "error",   # a saved state cannot take it: refused, lobby kept
                                 "message": "Start field 'features': applies to new worlds only, not with resume_state"}
    assert server.replies[2] is None and seen["world"].livelihoods.watershed is not None


def test_a_live_lobby_server_holding_the_watershed_is_refused_before_it_opens(tmp_path, monkeypatch):
    """The residual of review N1: a live start chooses its own world (the server's --worldgen
    does not apply to it), so a lobby whose command line holds --watershed could meet a
    template start that names nothing and end the session. It is refused at startup, before
    the lobby opens, even with --worldgen procedural; a start without features on a lobby
    without it runs (here on a procedural world, without an account)."""
    from chronicler import feature_catalog as fc
    from chronicler import live, main
    monkeypatch.setattr(live, "_get_available_models", lambda args: [""])
    assert live._live_world(_build_parser().parse_args(["--live", "--worldgen", "procedural"]),
                            {"seed": 11, "regions": 8, "civs": 4})[0].geography is None   # the client's world, not the server's
    for extra in ([], ["--worldgen", "procedural"]):
        server = _lobby([{"turns": 3, "civs": 4, "regions": 16, "seed": 11}])
        args = _build_parser().parse_args(["--live", "--agents", "off", "--watershed", *extra, "--simulate-only",
                                           "--output", str(tmp_path / "chronicle.md")])
        with pytest.raises(ValueError, match="cannot be set on a live lobby's command line"):
            live.run_live(args, server=server)
        assert server.replies == [] and server._server_state == "lobby"   # the lobby never opened
    assert fc.lobby_feature_catalog(_build_parser().parse_args(["--live", "--no-watershed"]))["schema_version"] == 1
    seen = {}

    def execute_run(args, **kwargs):
        seen["world"] = kwargs["world"]
        raise _Stop

    monkeypatch.setattr(main, "execute_run", execute_run)
    server = _lobby([{"turns": 3, "civs": 4, "regions": 16, "seed": 11}])
    with pytest.raises(_Stop):
        live.run_live(_build_parser().parse_args(["--live", "--agents", "off", "--simulate-only",
                                                  "--output", str(tmp_path / "chronicle.md")]), server=server)
    assert server.replies == [None] and seen["world"].geography is not None and seen["world"].livelihoods is None


# --- End to end (CLI, Python fallback): exact resume ---------------------------------------

def _args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=11, turns=turns, civs=4, regions=16, worldgen="procedural",
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents="off", tuning_overrides={}, watershed=True,
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def test_a_run_records_the_account_and_resumes_exactly(tmp_path):
    from chronicler import run_checkpoint as rc
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _adopt_checkpoint_args, execute_run

    def content(path: Path) -> bytes:
        if path.name == "chronicle_bundle.json":
            data = load_bundle(path)
            data["metadata"].pop("generated_at", None)
            return json.dumps(data, sort_keys=True).encode()
        return path.read_bytes()

    def outputs(folder: Path) -> dict[str, bytes]:
        return {p.relative_to(folder).as_posix(): content(p) for p in sorted(folder.rglob("*"))
                if p.is_file() and p.suffix != ".ckpt"}

    straight = tmp_path / "straight"
    execute_run(_args(straight, 24, checkpoint_every=11, checkpoint=str(straight / "c{turn}.ckpt")))
    assert rc.describe(straight / "c11.ckpt")["flags"]["watershed"] is True
    state = json.loads((straight / "state.json").read_text())["livelihoods"]["watershed"]
    assert state["counters"]["settled_turns"] == 24 and state["frame"]["turn"] == 23
    history = load_bundle(straight / "chronicle_bundle.json")["history"]
    records = [s["livelihoods"]["watershed"] for s in history]
    assert [r["source_turn"] for r in records] == [s["turn"] - 1 for s in history]
    assert all(r["observed"] for r in records)
    resumed = tmp_path / "resumed"
    args = _args(resumed, 24)
    args.watershed = None
    execute_run(args, checkpoint_resume=rc.read_checkpoint(straight / "c11.ckpt"))
    expected, got = outputs(straight), outputs(resumed)
    assert got.keys() == expected.keys()
    assert [name for name in got if got[name] != expected[name]] == []
    # A switch change on an exact resume is refused.
    parser = _build_parser()
    loaded = rc.read_checkpoint(straight / "c11.ckpt")
    refused = parser.parse_args(["--resume", str(straight / "c11.ckpt"), "--no-watershed"])
    assert any("--watershed" in line for line in _adopt_checkpoint_args(parser, refused, loaded))


# --- flow mode (B2): offline parts (the native tick itself: tests/test_watershed_native.py) ---------

def _flow_world(monkeypatch, seed=11, regions=32, civs=10):
    monkeypatch.setattr(ws, "native_available", lambda: True)   # the offline lane has no extension
    return _world(seed, "--watershed-mode", "flow", regions=regions, civs=civs)


class _FakeSimulator:
    def __init__(self):
        self.ecology, self.climate, self.topology = [], [], []

    def set_river_topology(self, paths):
        self.topology.append(paths)

    def set_ecology_config(self, **config):
        self.ecology.append(config)

    def set_climate_config(self, trend, shock_water):
        self.climate.append((trend, shock_water))

    def set_extraction_config(self, *rules):
        pass


def test_flow_switches_the_replaced_native_terms_off_exactly_once(monkeypatch):
    from chronicler.agent_bridge import configure_ecology_runtime
    off, record, flow = _procedural(11), _world(11), _flow_world(monkeypatch)
    assert ws.native_overrides(off) == ({}, None) and ws.native_overrides(record) == ({}, None)
    assert ws.native_overrides(flow) == (ws.FLOW_REPLACED_TERMS, 0.0)
    sims = {}
    for name, world in (("off", off), ("record", record), ("flow", flow)):
        sims[name] = _FakeSimulator()
        configure_ecology_runtime(sims[name], world)
    assert [len(s.ecology) for s in sims.values()] == [1, 1, 1]          # one configuration each
    assert sims["record"].ecology == sims["off"].ecology and sims["record"].climate == sims["off"].climate
    base, replaced = sims["off"].ecology[0], sims["flow"].ecology[0]
    assert set(base) == set(replaced)
    assert {k for k in base if base[k] != replaced[k]} == {k for k, v in ws.FLOW_REPLACED_TERMS.items() if base[k] != v}
    assert all(replaced[k] == v for k, v in ws.FLOW_REPLACED_TERMS.items())
    assert base["irrigation_water_bonus"] > 0 and base["deforestation_water_loss"] > 0 and base["water_recovery"] > 0
    (trend, shock), = sims["flow"].climate
    assert shock == 0.0 and trend == sims["off"].climate[0][0] < 1.0    # the crops keep the trend share
    assert sims["off"].climate[0][1] > 0.0


def test_flow_is_refused_without_the_native_ecology():
    from chronicler.livelihoods import configure_livelihoods as configure
    world = _procedural(11)
    assert ws.native_available() is False                             # the offline lane
    with pytest.raises(ValueError, match="requires the native ecology"):
        configure(world, _build_parser().parse_args(["--watershed", "--watershed-mode", "flow"]), agent_mode="off")
    assert world.livelihoods is None


def test_flow_refuses_the_python_fallback_and_a_stale_baseline_at_planning(monkeypatch):
    world = _flow_world(monkeypatch)
    with pytest.raises(RuntimeError, match="requires the native ecology"):
        before_ecology(world, acc=None, native=False)
    before_ecology(world, acc=None, native=True)        # a tick that never settles ...
    world.turn += 1
    with pytest.raises(RuntimeError, match="stale"):
        before_ecology(world, acc=None, native=True)    # ... flow will not apply the next account


def test_flow_writes_the_derived_index_and_floods_act_through_existing_fields(monkeypatch):
    world = _flow_world(monkeypatch)
    state = _state(world)
    up, down = _headwater_chain(state)
    _set_storage(state, up, 10.0)                       # overflow: the downstream region floods
    region = world.regions[down]
    region.capacity_modifier, soil = 1.0, region.ecology.soil
    others = {r: (world.regions[r].capacity_modifier, dict(world.regions[r].disaster_cooldowns))
              for r in range(len(world.regions)) if r != down}
    before_ecology(world, acc=None, native=True)
    plan = state._plan
    assert [r.ecology.water for r in world.regions] == plan.columns["index_derived"]
    assert region.capacity_modifier == ws.PARAMETERS.flood_capacity_modifier
    assert region.disaster_cooldowns["flood"] == 3      # excess >= the long-flood excess: 2 turns, from Phase 9
    assert region.ecology.soil == pytest.approx(min(soil + ws.PARAMETERS.flood_silt, 0.95), abs=0.06)
    flooded = {r for r, v in enumerate(plan.columns["flood_excess"]) if v > 0}
    for r, (modifier, cooldowns) in others.items():
        if r not in flooded:
            assert (world.regions[r].capacity_modifier, world.regions[r].disaster_cooldowns) == (modifier, cooldowns)
    after_ecology(world, acc=None)                      # the native tick (water terms switched off) stands in here
    world.turn += 1
    flood = next(f for f in state.frame.floods if f.region == down)
    assert flood.consequence.capacity_modifier == 0.85 and flood.consequence.cooldown == 3
    assert flood.consequence.soil_after > flood.consequence.soil_before
    assert state.counters["flood_consequences"] == len(state.frame.floods)
    record = livelihoods_snapshot_fields(world)["livelihoods"]["watershed"]
    assert (record["mode"], record["stage"], record["superseded"]) == ("flow", "B2", [])
    assert next(f for f in record["floods"] if f["region"] == down)["consequence"]["cooldown"] == 3
    _check_frame(state, world)


def test_record_only_floods_have_no_consequence_and_records_keep_the_b1_shape():
    world = _world(11)
    state = _state(world)
    up, down = _headwater_chain(state)
    _set_storage(state, up, 10.0)
    _phase9(world)
    record = livelihoods_snapshot_fields(world)["livelihoods"]["watershed"]
    assert (record["mode"], record["stage"]) == ("record_only", "B1") and "superseded" not in record
    assert all("consequence" not in f for f in record["floods"]) and record["floods"]
    assert set(record["counters"]) == set(COUNTER_KEYS)


def _river_flood_world(world):
    """A river region in spring with water above 0.8, so _check_flood's draw decides."""
    from chronicler.resources import get_season_id
    region = next(r for r in world.regions if r.river_mask)
    region.ecology.water = 0.85
    region.disaster_cooldowns.clear()
    turn = next(t for t in range(world.turn, world.turn + 48) if get_season_id(t) == 0)
    world.turn = turn
    return region


class _CountingRandom:
    def __init__(self, values):
        self.values, self.calls = list(values), []

    def random(self):
        self.calls.append("random")
        return self.values.pop(0) if self.values else 0.99

    def randint(self, a, b):
        self.calls.append("randint")
        return a


def test_flow_supersedes_the_river_flood_keeping_its_draws(monkeypatch):
    from chronicler import emergence
    for mode in ("record_only", "flow"):
        world = _flow_world(monkeypatch) if mode == "flow" else _world(11)
        region = _river_flood_world(world)
        soil, modifier = region.ecology.soil, region.capacity_modifier
        rng = _CountingRandom([0.0])                    # the flood's 20% draw fires
        result = emergence._check_flood(region, world, rng)
        assert rng.calls == ["random", "randint"]       # the same draws either way
        if mode == "record_only":
            assert result is not None and result is not emergence.SUPERSEDED
            assert region.disaster_cooldowns["flood"] == 1 and region.capacity_modifier == 0.85
        else:
            assert result is emergence.SUPERSEDED
            assert (region.ecology.soil, region.capacity_modifier, region.disaster_cooldowns) == (soil, modifier, {})
            pending = _state(world).pending_superseded
            assert [(f.region, f.turn, f.duration) for f in pending] == [
                (world.regions.index(region), world.turn, 1)]


def test_a_superseded_river_flood_ends_the_regions_checks_like_a_fired_one(monkeypatch):
    from chronicler import emergence
    counts = {}
    for mode in ("record_only", "flow"):
        world = _flow_world(monkeypatch) if mode == "flow" else _world(11)
        _river_flood_world(world)
        for r in world.regions:
            r.disaster_cooldowns.clear()
        rng = _CountingRandom([0.0] * 0)
        rng.values = [0.0] * 1000                       # every condition-gated draw fires
        events = emergence.check_environmental_events(world, rng)
        counts[mode] = (len(rng.calls), [e.event_type for e in events])
    assert counts["flow"][0] == counts["record_only"][0]   # the shared stream stays aligned
    assert counts["record_only"][1].count("flood") == counts["flow"][1].count("flood") + 1


def test_flow_settles_superseded_floods_into_the_record(monkeypatch):
    from chronicler import emergence
    world = _flow_world(monkeypatch)
    region = _river_flood_world(world)
    state = _state(world)
    state.frame = None
    state.opened_turn = world.turn                     # constructed: the account opens at this turn
    emergence._check_flood(region, world, _CountingRandom([0.0]))
    before_ecology(world, acc=None, native=True)
    after_ecology(world, acc=None)
    world.turn += 1
    assert [f.region for f in state.frame.superseded] == [world.regions.index(region)]
    assert state.pending_superseded == [] and state.counters["superseded_river_floods"] == 1
    record = livelihoods_snapshot_fields(world)["livelihoods"]["watershed"]
    assert record["superseded"] == [{"turn": world.turn - 1, "region": world.regions.index(region), "duration": 1}]


def test_a_flow_world_cannot_switch_mode_on_resume(monkeypatch):
    world = _flow_world(monkeypatch)
    with pytest.raises(ValueError, match="conflicts with this world's watershed account"):
        ws.check_request(world, None, argparse.Namespace(watershed_mode="record_only"))
    assert livelihoods_resume_conflicts(world, argparse.Namespace(watershed_mode="record_only"), {}) == [
        "--watershed-mode 'record_only' conflicts with the checkpoint (saved: 'flow')"]
    monkeypatch.setattr(ws, "native_available", lambda: False)
    with pytest.raises(ValueError, match="requires the native ecology"):   # a resume without the extension
        ws.check_request(world, None, argparse.Namespace(watershed_mode=None))


def test_a_b1_record_only_checkpoint_still_loads():
    world = _world(11)
    _phase9(world)
    state = _state(world)
    blob = pickle.dumps(world)
    restored = pickle.loads(blob)
    rs = restored.livelihoods.watershed
    for obj, key in ((rs, "pending_superseded"), (rs.frame, "superseded")):
        del obj.__dict__[key]                           # the shape a B1 pickle has
    again = pickle.loads(pickle.dumps(restored))
    assert again.livelihoods.watershed.pending_superseded == [] and again.livelihoods.watershed.frame.superseded == []
    _phase9(again)
    assert again.livelihoods.watershed.counters["settled_turns"] == state.counters["settled_turns"] + 1


def test_flow_changes_only_the_water_index_and_what_its_floods_do(monkeypatch):
    """The replaced terms' own state is untouched: irrigation works, rivers and the
    river topology stay as they were; flow writes the index and, in flooded regions
    only, the capacity modifier, the flood cooldown and the soil."""
    world = _flow_world(monkeypatch)
    world.regions[0].infrastructure.append(
        Infrastructure(type=InfrastructureType.IRRIGATION, builder_civ="x", built_turn=0))
    _set_storage(_state(world), _headwater_chain(_state(world))[0], 10.0)
    before = _strip(world.model_dump(mode="json"))
    before_ecology(world, acc=None, native=True)
    after = _strip(world.model_dump(mode="json"))
    flooded = {r for r, v in enumerate(_state(world)._plan.columns["flood_excess"]) if v > 0}
    assert flooded
    for r, (a, b) in enumerate(zip(before.pop("regions"), after.pop("regions"))):
        for side in (a, b):
            side["ecology"].pop("water")
            if r in flooded:
                side.pop("capacity_modifier"), side.pop("disaster_cooldowns"), side["ecology"].pop("soil")
        assert a == b, r
    assert before == after
