"""Public granaries (``chronicler.grain_reserves``, ``--grain-reserves``).

Mechanics run on the template world (seed 42) with the ticks called directly
on an economy result built here (``acc=None``, an agent mode without native
commitments unless a test gives them). Native tests run the real extension.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

import pyarrow as pa
import pytest

import chronicler.grain_reserves as G
from chronicler.economy import FIXED_GOODS, EconomyResult
from chronicler.grain_reserves_state import (
    ABANDONED, BOUGHT, CAPTURED, COUNTER_KEYS, FLOW_KINDS, RELEASED, SEIZED, SPOILED, Granary,
)
from chronicler.models import WorldState
from chronicler.world_gen import generate_world

ROOT = Path(__file__).resolve().parents[1]
# Template seed 42: Kethani Empire (civ 1) holds Frostholm Tundra (0) and
# Amber Valley (5); Thornwall Confederacy (2) Verdant Plains (2) and Thornwood
# (4), adjacent; Selurian Republic (3) Ashara Desert (3), next to Verdant
# Plains and Amber Valley; Ashkari Nomads (0) Obsidian Shore (7).
FROST, IRON, VERDANT, ASHARA, THORNWOOD, AMBER, OBSIDIAN = 0, 1, 2, 3, 4, 5, 7
ASHKARI, KETHANI, THORNWALL, SELURIAN = 0, 1, 2, 3


def _world(mode: str = "demographics-only") -> WorldState:
    world = generate_world(seed=42)
    world.agent_mode = mode
    G.set_grain_reserves_enabled(world, True)
    world.turn = 30
    for civ in world.civilizations:
        civ.treasury = 200
    for region in world.regions:
        region.stockpile.goods = {}
    from chronicler.models import Disposition
    for row in world.relationships.values():     # every pair may trade (the route graph's rule)
        for rel in row.values():
            rel.disposition = Disposition.NEUTRAL
    return world


def _economy(world, suff: dict[int, float] | None = None, pop: dict[int, int] | None = None,
             harvest: dict[int, float] | None = None) -> EconomyResult:
    """An economy result: demand 0.5 per head, the given sufficiency (default
    1.0), post-trade food supply = sufficiency x demand, food harvest in the
    region's first food slot (or foraged)."""
    suff = suff or {}
    pop = pop or {}
    harvest = harvest or {}
    res = EconomyResult()
    for i, region in enumerate(world.regions):
        if i in pop:
            region.population = pop[i]
        demand = 0.5 * region.population
        s = suff.get(i, 1.0)
        supply = max(s * demand, sum(region.stockpile.goods.values()))
        res.food_sufficiency[region.name] = s
        res.market_demand[region.name] = (demand, 0.0, 0.0, 0.0)
        res.market_supply[region.name] = (supply, 0.0, 0.0, 0.0)
        res.slot_output[region.name] = [0.0, 0.0, 0.0]
        h = harvest.get(i, demand)
        food_slot = next((k for k, rt in enumerate(region.resource_types)
                          if rt != 255 and FIXED_GOODS and rt in (0, 2, 3, 4, 7)), None)
        if food_slot is None:
            res.forage_output[region.name] = h
        else:
            res.slot_output[region.name][food_slot] = h
    return res


def _granary(world, rid) -> Granary:
    G._ensure(world)
    granary = world.grain_reserves.granaries[rid]
    ctl = world.regions[rid].controller
    granary.owner = next(i for i, c in enumerate(world.civilizations) if c.name == ctl)
    return granary


def _flows(world, kind):
    return [f for f in world.grain_reserves.flows if f.kind == kind]


# --- the switch ----------------------------------------------------------------------

def test_switch_dormancy_and_old_saves(tmp_path):
    assert G.DEFAULT_ENABLED_FOR_NEW_WORLDS is False
    world = generate_world(seed=42)
    assert world.grain_reserves is None and not G.grain_reserves_enabled(world)
    assert "grain_reserves" not in json.loads(world.model_dump_json())
    assert G.open_granaries(world, EconomyResult()) == []
    assert G.tick_grain_reserves(world, None, EconomyResult()) == []
    path = tmp_path / "state.json"
    world.save(path)
    assert "grain_reserves" not in json.loads(path.read_text())
    assert WorldState.load(path).grain_reserves is None
    G.set_grain_reserves_enabled(world, True)
    assert G.grain_reserves_enabled(world) and not G.grain_reserves_active(world)
    # Dormant under --agents off: a strict no-op.
    before = world.grain_reserves.model_dump()
    assert G.open_granaries(world, _economy(world, {VERDANT: 0.5})) == []
    assert G.tick_grain_reserves(world, None, _economy(world)) == []
    assert world.grain_reserves.model_dump() == before
    world.agent_mode = "hybrid"
    _granary(world, VERDANT).grain = 7.5
    world.save(path)
    loaded = WorldState.load(path)
    assert loaded.grain_reserves == world.grain_reserves
    G.set_grain_reserves_enabled(world, False)
    assert world.grain_reserves is None


def test_append_only_orders():
    assert FLOW_KINDS[:6] == ("bought", "released", "spoiled", "seized", "abandoned", "captured")
    assert COUNTER_KEYS[:4] == ("bought_own", "bought_realm", "bought_foreign", "sent")
    assert G.EVENT_TYPES == ("granary_opened", "granary_exhausted", "grain_bought")


def test_cli_flag_gate_forwarding_live_default_and_benchmark_pin(tmp_path):
    from chronicler.batch_manifest import SIMULATION_ARG_KEYS
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    assert parser.parse_args([]).grain_reserves is None
    assert parser.parse_args(["--grain-reserves"]).grain_reserves is True
    assert parser.parse_args(["--no-grain-reserves"]).grain_reserves is False
    assert "grain_reserves" in SIMULATION_ARG_KEYS
    spec = importlib.util.spec_from_file_location("m53b", ROOT / "scripts" / "m53b_run_validation.py")
    m53b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m53b)
    assert m53b._grain_reserves_args(argparse.Namespace(grain_reserves=True)) == ["--grain-reserves"]
    assert m53b._grain_reserves_args(argparse.Namespace(grain_reserves=False)) == ["--no-grain-reserves"]
    assert m53b._grain_reserves_args(argparse.Namespace(grain_reserves=None)) == []
    assert "set_grain_reserves_enabled" in (ROOT / "src" / "chronicler" / "live.py").read_text()
    assert "grain_reserves=False" in (ROOT / "scripts" / "benchmark_headless.py").read_text()
    # An explicit switch needs the goods economy of an agent mode.
    args = parser.parse_args(["--seed", "42", "--turns", "2", "--regions", "8", "--civs", "4",
                              "--agents", "off", "--simulate-only",
                              "--grain-reserves", "--output", str(tmp_path / "c.md"),
                              "--state", str(tmp_path / "s.json")])
    with pytest.raises(ValueError, match="agent-backed goods economy"):
        execute_run(args)


def test_new_worlds_follow_the_default_and_resume_keeps_the_saved_setting(tmp_path):
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()

    def args(out, *extra, turns=3):
        return parser.parse_args(["--seed", "42", "--turns", str(turns), "--regions", "8", "--civs", "4",
                                  "--agents", "off",
                                  "--simulate-only", *extra, "--output", str(out / "chronicle.md"),
                                  "--state", str(out / "state.json")])
    fresh = tmp_path / "fresh"
    execute_run(args(fresh))
    state = json.loads((fresh / "state.json").read_text())
    assert "grain_reserves" not in state
    # A saved world with the switch on resumes with it, dormant under --agents off.
    world = WorldState.model_validate(state)
    G.set_grain_reserves_enabled(world, True)
    world.save(fresh / "on.json")
    resumed = args(fresh, turns=5)
    resumed.resume = str(fresh / "on.json")
    resumed.state = str(fresh / "resumed.json")
    execute_run(resumed)
    kept = json.loads((fresh / "resumed.json").read_text())["grain_reserves"]
    assert kept["granaries"] == [] and all(v == 0 for v in kept["counters"].values())


def test_feature_off_never_runs_granary_code(monkeypatch):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn

    def boom(*a, **k):
        raise AssertionError("granary code ran with the switch off")

    for name in ("open_granaries", "tick_grain_reserves", "seize_granary", "_route_graph"):
        monkeypatch.setattr(G, name, boom)
    world = generate_world(seed=42)
    world.campaigns_enabled = True
    for _ in range(15):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)
    assert world.grain_reserves is None


# --- targets -------------------------------------------------------------------------

def test_target_follows_the_harvest_swing_counted_up_to_the_need():
    world = _world()
    granary = _granary(world, VERDANT)
    for _ in range(40):                           # a steady harvest: nothing to buffer
        G._observe(world, world.grain_reserves, _economy(world, pop={VERDANT: 40},
                                                       harvest={VERDANT: 20.0}))
    assert G.harvest_cv(granary) == pytest.approx(0.0, abs=1e-9) and granary.target == pytest.approx(0.0)
    # A harvest far above the need counts as the need: no swing either.
    for k in range(40):
        G._observe(world, world.grain_reserves, _economy(world, harvest={VERDANT: 60.0 if k % 2 else 25.0}))
    assert granary.target == pytest.approx(0.0, abs=1e-9)
    # A harvest swinging between half and all of the need.
    for k in range(240):
        G._observe(world, world.grain_reserves, _economy(world, harvest={VERDANT: 10.0 if k % 2 else 20.0}))
    cv = G.harvest_cv(granary)
    assert 0.25 < cv < 0.4
    assert granary.target == pytest.approx(min(G.MAX_TURNS, G.TURNS_PER_CV * cv) * 20.0)
    # A failing harvest raises it to the cap.
    for k in range(240):
        G._observe(world, world.grain_reserves, _economy(world, harvest={VERDANT: 0.0 if k % 2 else 20.0}))
    assert granary.target == pytest.approx(G.MAX_TURNS * 20.0)
    # Nothing grown, nothing to swing.
    other = _granary(world, ASHARA)
    other.observed = 0
    for _ in range(30):
        G._observe(world, world.grain_reserves, _economy(world, harvest={ASHARA: 0.0}))
    assert other.target == 0.0


# --- release -------------------------------------------------------------------------

def test_release_covers_the_shortfall_before_anything_reads_it():
    world = _world()
    granary = _granary(world, VERDANT)
    granary.grain, granary.target = 20.0, 20.0
    res = _economy(world, {VERDANT: 0.5}, pop={VERDANT: 20})    # need 10, 5 on hand
    events = G.open_granaries(world, res)
    assert res.food_sufficiency["Verdant Plains"] == 1.0
    assert res.market_supply["Verdant Plains"][0] == pytest.approx(5.0 + 5.0)
    (rel,) = _flows(world, RELEASED)
    assert rel.amount == pytest.approx(5.0) and rel.before == 0.5 and rel.after == 1.0
    (sp,) = _flows(world, SPOILED)
    assert sp.amount == pytest.approx(15.0 * 0.03) and granary.grain == pytest.approx(15.0 * 0.97)
    assert [e.event_type for e in events] == ["granary_opened"]
    assert "Thornwall Confederacy opens its granary in Verdant Plains" in events[0].description
    # A fed region releases nothing.
    fed = _economy(world, {VERDANT: 1.2})
    world.turn += 1
    assert G.open_granaries(world, fed) == [] and not _flows(world, RELEASED)
    assert fed.food_sufficiency["Verdant Plains"] == 1.2


def test_a_low_granary_keeps_the_people_above_the_famine_line_only():
    world = _world()
    granary = _granary(world, VERDANT)
    granary.target = 40.0
    granary.grain = 10.0                       # a quarter of its target
    res = _economy(world, {VERDANT: 0.8}, pop={VERDANT: 20})
    assert G.open_granaries(world, res) == []  # dearth above the famine line: kept
    assert res.food_sufficiency["Verdant Plains"] == 0.8 and granary.grain == pytest.approx(9.7)
    world.turn += 1
    res = _economy(world, {VERDANT: 0.3})
    G.open_granaries(world, res)
    assert res.food_sufficiency["Verdant Plains"] == pytest.approx(0.6)
    assert _flows(world, RELEASED)[0].amount == pytest.approx(3.0)


def test_an_opening_and_its_exhaustion_are_told_once():
    world = _world()
    granary = _granary(world, VERDANT)
    granary.grain, granary.target = 12.0, 12.0
    seen = []
    for turn, s in ((30, 0.4), (31, 0.2), (32, 0.2), (33, 1.1), (34, 0.5)):
        world.turn = turn
        seen.append([e.event_type for e in G.open_granaries(world, _economy(world, {VERDANT: s},
                                                                              pop={VERDANT: 20}))])
    # 30: 6 released (full); 31: below half its target, 4 to the famine line;
    # 32: its last 1.77 and it is empty; fed at 33; nothing left at 34.
    assert seen == [["granary_opened"], [], ["granary_exhausted"], [], []]
    assert world.grain_reserves.counters["openings"] == 1
    assert world.grain_reserves.counters["exhausted"] == 1
    # A small release opens the granary without an event.
    granary.grain = granary.target = 100.0
    world.turn = 40
    assert G.open_granaries(world, _economy(world, {VERDANT: 0.97})) == []
    assert world.grain_reserves.counters["openings"] == 2


# --- procurement ---------------------------------------------------------------------

def _target(world, rid, value):
    granary = _granary(world, rid)
    granary.target = value
    granary.observed = 50
    return granary


def _tick(world, res, acc=None, bridge=None):
    """The Phase 10 tick with the targets kept as the test set them."""
    targets = [g.target for g in world.grain_reserves.granaries]
    original = G._observe
    try:
        G._observe = lambda *a: None
        events = G.tick_grain_reserves(world, acc, res, bridge)
    finally:
        G._observe = original
    for g, t in zip(world.grain_reserves.granaries, targets):
        assert g.target == t
    return events


def test_buys_real_surplus_in_its_own_market_first_at_market_price():
    world = _world()
    thornwall = world.civilizations[THORNWALL]
    world.regions[VERDANT].stockpile.goods = {"grain": 70.0, "botanicals": 5.0}
    res = _economy(world, pop={VERDANT: 20, THORNWOOD: 10})   # Verdant needs 10 a turn
    res.market_supply["Verdant Plains"] = (75.0, 0.0, 0.0, 0.0)  # price 10 / 75
    granary = _target(world, VERDANT, 30.0)
    _tick(world, res)
    (buy,) = _flows(world, BOUGHT)
    price = 10.0 / 75.0
    assert buy.source == VERDANT and buy.seller == THORNWALL and buy.buyer == THORNWALL
    assert buy.cost == math.floor(30.0 * price) == 4
    assert buy.sent == pytest.approx(4 / price) and buy.amount == pytest.approx(buy.sent)
    assert granary.grain == pytest.approx(buy.sent)
    assert world.regions[VERDANT].stockpile.goods["grain"] == pytest.approx(70.0 - buy.sent)
    assert thornwall.treasury == 200 - 4                      # paid to its own producers
    # Real surplus only: the market keeps four turns of its own need.
    world.turn += 1
    world.regions[VERDANT].stockpile.goods = {"grain": 41.0}
    granary.grain = 0.0
    _tick(world, res)
    assert sum(f.sent for f in _flows(world, BOUGHT)) <= 1.0 + 1e-9


def test_realm_shipments_lose_transit_and_follow_the_route_graph():
    world = _world()
    world.regions[VERDANT].stockpile.goods = {"grain": 80.0}
    res = _economy(world, pop={VERDANT: 20, THORNWOOD: 10})
    granary = _target(world, THORNWOOD, 10.0)
    _tick(world, res)
    (buy,) = _flows(world, BOUGHT)
    assert buy.source == VERDANT and buy.region == THORNWOOD
    assert buy.amount == pytest.approx(buy.sent * (1 - 0.05)) and granary.grain == pytest.approx(buy.amount)
    # A suspended route carries nothing.
    world.turn += 1
    granary.grain = 0.0
    world.regions[THORNWOOD].route_suspensions = {"trade_route": 3}
    _tick(world, res)
    assert not _flows(world, BOUGHT)


def test_foreign_purchases_pay_the_seller_and_stop_at_war_and_embargo():
    world = _world()
    selurian, thornwall, kethani = (world.civilizations[i] for i in (SELURIAN, THORNWALL, KETHANI))
    thornwall.treasury = kethani.treasury = 0                  # they buy nothing at home
    world.regions[VERDANT].stockpile.goods = {"grain": 80.0}
    res = _economy(world, pop={VERDANT: 20, AMBER: 20, ASHARA: 20})
    res.market_supply["Amber Valley"] = (40.0, 0.0, 0.0, 0.0)
    granary = _target(world, ASHARA, 12.0)
    events = _tick(world, res)
    buys = _flows(world, BOUGHT)
    assert {b.source for b in buys} == {VERDANT} and all(b.seller == THORNWALL for b in buys)
    paid = sum(b.cost for b in buys)
    assert selurian.treasury == 200 - paid and thornwall.treasury == paid
    assert granary.grain == pytest.approx(sum(b.sent for b in buys) * 0.95)
    assert [e.event_type for e in events] == ["grain_bought"]
    assert events[0].civs == ["Thornwall Confederacy"] and events[0].region == "Ashara Desert"
    # At war with Thornwall: Amber Valley's market instead; with an embargo on
    # Kethani as well, no market.
    world.regions[AMBER].stockpile.goods = {"grain": 80.0}
    for blocked, sources in (([(selurian.name, thornwall.name)], {AMBER}), (None, set())):
        world.turn += 1
        granary.grain = 0.0
        if blocked:
            world.active_wars = blocked
        else:
            world.embargoes = [(selurian.name, kethani.name)]
        _tick(world, res)
        assert {b.source for b in _flows(world, BOUGHT)} == sources


def test_merchant_commitments_are_not_for_sale():
    world = _world("hybrid")
    world.regions[VERDANT].stockpile.goods = {"grain": 80.0}
    res = _economy(world, pop={VERDANT: 20})
    _target(world, VERDANT, 100.0)

    class _Sim:
        def get_stockpile_commitments(self):
            n, k = len(world.regions), len(FIXED_GOODS)
            reserved = [25.0 if (r == VERDANT and g == 0) else 0.0 for r in range(n) for g in range(k)]
            return pa.record_batch({
                "region_id": pa.array([r for r in range(n) for _ in range(k)], type=pa.uint16()),
                "good_slot": pa.array([g for _ in range(n) for g in range(k)], type=pa.uint8()),
                "reserved": pa.array(reserved, type=pa.float32()),
                "pending_departure": pa.array([0.0] * (n * k), type=pa.float32()),
            })

    class _Bridge:
        _sim = _Sim()
        _sidecar = None

    _tick(world, res, bridge=_Bridge())
    sold = sum(f.sent for f in _flows(world, BOUGHT))
    price = 10.0 / 80.0
    # 15 free beyond four turns of need; whole coins buy 8 of them.
    assert sold <= 80.0 - 25.0 - 4 * 10.0 + 1e-9 and sold == pytest.approx(math.floor(15 * price) / price)


def test_budget_share_and_treasury_floor():
    world = _world()
    thornwall = world.civilizations[THORNWALL]
    world.regions[VERDANT].stockpile.goods = {"grain": 500.0}
    res = _economy(world, pop={VERDANT: 20})
    res.market_supply["Verdant Plains"] = (10.0, 0.0, 0.0, 0.0)   # price 1
    _target(world, VERDANT, 300.0)
    thornwall.treasury = 120
    _tick(world, res)
    assert sum(f.cost for f in _flows(world, BOUGHT)) == int(G.BUDGET_SHARE * (120 - G.TREASURY_FLOOR))
    world.turn += 1
    thornwall.treasury = G.TREASURY_FLOOR
    _tick(world, res)
    assert not _flows(world, BOUGHT)


# --- owners, conquest, occupation ----------------------------------------------------

def test_conquest_occupation_and_siege_take_their_share():
    from chronicler.action_engine import apply_region_conquest
    from chronicler.war.occupation import _requisition
    world = _world()
    granary = _granary(world, VERDANT)
    granary.grain = 40.0
    G._flows(world, world.grain_reserves)
    _requisition(world.regions[VERDANT], 0.8, world)
    assert granary.grain == pytest.approx(32.0)
    attacker, defender = world.civilizations[SELURIAN], world.civilizations[THORNWALL]
    apply_region_conquest(attacker, defender, world.regions[VERDANT], world, seed=1)
    assert granary.grain == pytest.approx(16.0)
    assert [f.amount for f in _flows(world, SEIZED)] == pytest.approx([8.0, 16.0])
    # Next turn the conqueror takes the rest over.
    world.turn += 1
    G.open_granaries(world, None)
    assert granary.owner == SELURIAN and _flows(world, CAPTURED)[0].amount == pytest.approx(16.0)


def test_a_granary_without_a_ruler_goes_to_its_market():
    world = _world()
    granary = _granary(world, THORNWOOD)
    granary.grain = 10.0
    world.regions[THORNWOOD].controller = None
    world.regions[THORNWOOD].stockpile.goods = {"grain": 1.0}
    G.open_granaries(world, None)
    assert granary.grain == 0.0 and granary.owner == -1
    assert world.regions[THORNWOOD].stockpile.goods["grain"] == pytest.approx(11.0)
    assert _flows(world, ABANDONED)[0].amount == pytest.approx(10.0)


# --- the resource ledger -------------------------------------------------------------

def _turn(world, suff=None, goods=None):
    for rid, stock in (goods or {}).items():
        world.regions[rid].stockpile.goods = dict(stock)
    res = _economy(world, suff, pop={VERDANT: 20, THORNWOOD: 10, ASHARA: 20, AMBER: 20})
    G.open_granaries(world, res)
    return res


def test_resource_check_balances_a_season_of_granaries(monkeypatch):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    world = _world()
    for rid, t in ((VERDANT, 30.0), (THORNWOOD, 15.0), (ASHARA, 30.0), (AMBER, 30.0)):
        _target(world, rid, t)
    world.civilizations[THORNWALL].treasury = 30   # budget 1: it buys little
    for turn in range(30, 42):
        world.turn = turn
        suff = {ASHARA: 0.4, THORNWOOD: 0.7} if turn % 3 == 0 else {}
        res = _turn(world, suff, goods={VERDANT: {"grain": 70.0}, AMBER: {"grain": 70.0}})
        _tick(world, res)
    counters = world.grain_reserves.counters
    assert counters["bought_own"] > 0 and counters["bought_foreign"] > 0 and counters["released"] > 0
    assert counters["spoiled"] > 0


def test_resource_check_catches_grain_and_money_from_nowhere(monkeypatch):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    world = _world()
    _target(world, ASHARA, 30.0)
    world.civilizations[THORNWALL].treasury = 0
    res = _turn(world, goods={VERDANT: {"grain": 70.0}})
    world.grain_reserves.granaries[ASHARA].grain += 5.0          # not a recorded flow
    with pytest.raises(AssertionError, match="does not balance"):
        _tick(world, res)
    world.turn += 1
    world.grain_reserves.granaries[ASHARA].grain = 0.0
    res = _turn(world, goods={VERDANT: {"grain": 70.0}})
    import chronicler.finance as F

    def free_transfer(world, payer, payee, amount, *, acc=None):
        world.civilizations[payee].treasury += amount           # the payer never pays
        return amount

    monkeypatch.setattr(F, "transfer", free_transfer)
    with pytest.raises(AssertionError, match="treasury"):
        _tick(world, res)


# --- snapshot, metrics, narration ----------------------------------------------------

def test_history_summary_is_read_only_and_keeps_completed_turn_values():
    from chronicler.grain_reserves_state import ReserveFlow
    from chronicler.main import _grain_reserves_snapshot_fields
    world = _world()
    granary = _granary(world, VERDANT)
    granary.grain, granary.target, granary.observed = 11.125, 20.25, 3
    state = world.grain_reserves
    state.flows_turn = world.turn
    state.flows = [ReserveFlow(kind=BOUGHT, region=VERDANT, amount=2.25, source=ASHARA,
                              buyer=THORNWALL, seller=SELURIAN, sent=2.5, cost=4),
                   ReserveFlow(kind=RELEASED, region=VERDANT, amount=1.5, buyer=THORNWALL,
                               before=0.5, after=0.65)]
    world.turn += 1  # run_chronicle captures the snapshot after turn completion
    before = world.model_dump_json()
    summary = _grain_reserves_snapshot_fields(world)["grain_reserves"]
    row = summary["granaries"][VERDANT]
    assert summary["source_turn"] == 30
    assert (row["grain"], row["target"], row["owner"], row["owner_name"]) == (
        11.125, 20.25, THORNWALL, world.civilizations[THORNWALL].name)
    assert summary["flows"][0]["kind"] == "bought"
    assert summary["flows"][0]["sent"] == 2.5
    assert summary["flows"][1]["after"] == 0.65
    assert world.model_dump_json() == before
    # No aliased dictionaries/lists leak future mutations into the saved record.
    state.counters["spoiled"] = 20
    granary.grain = 1
    state.flows[0].amount = 0
    assert row["grain"] == 11.125 and summary["flows"][0]["amount"] == 2.25
    assert summary["counters"]["spoiled"] == 0
    world.turn += 1
    assert G.snapshot_summary(world)["flows"] == []  # stale flows must not repeat


def test_history_summary_does_not_initialise_granaries_or_infer_new_owner():
    world = _world()
    before = world.model_dump_json()
    assert G.snapshot_summary(world)["granaries"] == []
    assert world.model_dump_json() == before
    granary = _granary(world, VERDANT)
    world.regions[VERDANT].controller = world.civilizations[SELURIAN].name
    row = G.snapshot_summary(world)["granaries"][VERDANT]
    assert row["owner"] == THORNWALL
    assert row["controller"] == world.civilizations[SELURIAN].name
    assert granary.owner == THORNWALL


def test_history_summary_absent_when_off_or_dormant():
    from chronicler.main import _grain_reserves_snapshot_fields
    from chronicler.models import TurnSnapshot
    world = generate_world(seed=42)
    base = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    before = base.model_dump_json()
    assert _grain_reserves_snapshot_fields(world) == {}
    G.set_grain_reserves_enabled(world, True)
    world.agent_mode = "off"
    assert _grain_reserves_snapshot_fields(world) == {} and G.snapshot_summary(world) == {}
    assert base.model_copy(update=_grain_reserves_snapshot_fields(world)).model_dump_json() == before
    assert "grain_reserves" not in json.loads(before)


def test_history_summary_survives_bundle_batch_live_and_reconnect_adapters():
    from chronicler.bundle_codec import decode_bundle, encode_bundle
    from chronicler.live import _build_init_data_from_bundle, _validate_legacy_live_bundle
    from chronicler.models import TurnSnapshot
    from chronicler.transport import snapshot_from_turn_message
    world = _world()
    _granary(world, VERDANT).grain = 17.125
    world.turn += 1
    summary = G.snapshot_summary(world)
    snapshot = TurnSnapshot(turn=world.turn, civ_stats={}, region_control={}, relationships={},
                            grain_reserves=summary).model_dump(mode="json")
    bundle = {"world_state": world.model_dump(mode="json"), "history": [snapshot],
              "events_timeline": [], "named_events": [], "chronicle_entries": [],
              "era_reflections": {}, "metadata": {"total_turns": world.turn}}
    static = decode_bundle(encode_bundle(bundle))
    loaded = _validate_legacy_live_bundle(static)
    reconnect = _build_init_data_from_bundle(loaded)
    for payload in (static, loaded, reconnect):
        assert payload["history"][0]["grain_reserves"] == summary
    assert snapshot_from_turn_message(dict(snapshot, type="turn"))["grain_reserves"] == summary

def test_metrics_and_event_classes():
    from chronicler.curator import event_label
    from chronicler.historiography import ROUTINE
    from chronicler.narration_context import ROUTINE_TYPES, is_routine
    world = _world()
    _target(world, VERDANT, 20.0).grain = 12.0
    res = _economy(world, {VERDANT: 0.5}, pop={VERDANT: 20})
    events = G.open_granaries(world, res)
    bundle = {"world_state": json.loads(world.model_dump_json())}
    metrics = G.extract_grain_reserve_metrics([bundle, {"world_state": {}}])
    assert metrics["runs"] == 1 and metrics["grain_final_mean"] == pytest.approx(7.0 * 0.97)
    assert metrics["target_final_mean"] == pytest.approx(20.0)
    assert metrics["counters_mean"]["released"] == pytest.approx(5.0)
    assert "grain_bought" in ROUTINE_TYPES and "grain_bought" in ROUTINE
    assert not is_routine(events[0]) and event_label(events[0]) == events[0].description


# --- native hybrid -------------------------------------------------------------------

def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


@pytest.mark.native
def test_native_hybrid_run_procures_releases_and_balances(tmp_path, monkeypatch):
    _require_native()
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    parser = _build_parser()
    out = tmp_path / "hyb"
    execute_run(parser.parse_args(["--seed", "42", "--turns", "60", "--regions", "8", "--civs", "4",
                                   "--agents", "hybrid", "--simulate-only",
                                   "--grain-reserves", "--validation-sidecar",
                                   "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")]))
    world = WorldState.load(out / "state.json")
    counters = world.grain_reserves.counters
    assert counters["sent"] > 0 and counters["released"] > 0
    ledger = G.read_reserve_ledger(out / G.RESERVE_LEDGER_FILENAME)
    assert len(ledger["turn"]) > 0 and math.fsum(ledger["released"]) == pytest.approx(counters["released"])
    bundle = load_bundle(out / "chronicle_bundle.json")
    assert bundle["world_state"]["grain_reserves"]["counters"]["released"] == pytest.approx(counters["released"])
    summary = bundle["history"][-1]["grain_reserves"]
    assert summary["source_turn"] == bundle["history"][-1]["turn"] - 1
    assert sum(row["grain"] for row in summary["granaries"]) == pytest.approx(
        sum(g.grain for g in world.grain_reserves.granaries))
    types = {e["event_type"] for e in bundle["events_timeline"]}
    assert "granary_opened" in types


@pytest.mark.native
def test_native_switch_off_is_the_run_without_it(tmp_path):
    _require_native()
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    parser = _build_parser()
    bundles = []
    for name, extra in (("absent", []), ("off", ["--no-grain-reserves"])):
        out = tmp_path / name
        execute_run(parser.parse_args(["--seed", "7", "--turns", "25", "--regions", "8", "--civs", "4",
                                       "--agents", "hybrid", "--simulate-only",
                                       *extra, "--output", str(out / "chronicle.md"),
                                       "--state", str(out / "state.json")]))
        bundle = load_bundle(out / "chronicle_bundle.json")
        bundle["metadata"].pop("generated_at", None)
        bundles.append(bundle)
        assert "grain_reserves" not in json.loads((out / "state.json").read_text())
    assert bundles[0] == bundles[1]
