"""L9 local collective budgets without the native extension.

The template world (seed 42) runs the real services offline: grain storage
work (``prepare_storage_work``/``finish_storage_work`` with the native
delivery taken as requested), L1 workshops (a stand-in crew planner) and
granary purchases (``tick_grain_reserves`` on an economy result built here).
Thornwall Confederacy (civ 2) holds Verdant Plains (2, its capital, with a
worn granary) and Thornwood (4, a workshop city whose granary is empty and
whose poorer households went short).
"""
from __future__ import annotations

import math
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

import chronicler.grain_reserves as G
from chronicler import local_budgets as LB
from chronicler import workshops as W
from chronicler.cities_state import City, CityState
from chronicler.economy import EconomyResult
from chronicler.food_allocation_state import FoodAllocationState
from chronicler.grain_reserves_state import BOUGHT
from chronicler.grain_storage import enable_storage, finish_storage_work, prepare_storage_work
from chronicler.grain_storage_state import StorageAsset, StorageReceipt
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.local_budgets_state import MAX_PROPOSALS, LocalBudgetState
from chronicler.models import Disposition, FactionType
from chronicler.workshops_state import WorkshopReceipt, WorkshopSite, WorkshopState
from chronicler.world_gen import generate_world

VERDANT, THORNWOOD = 2, 4
THORNWALL = 2
CITY = 12
#: Budget = floor(0.25 x (treasury - 20)).
TREASURY_FOR = {2: 28, 3: 32, 10: 60}


def _world(*, budget=10, commons=0.6, patricians=0.1, mode="bargained", food=True, workshop=True):
    world = generate_world(seed=42)
    world.agent_mode = "hybrid"
    G.set_grain_reserves_enabled(world, True)
    G._ensure(world)
    world.turn = 30
    for civ in world.civilizations:
        civ.treasury = 500
    world.civilizations[THORNWALL].treasury = TREASURY_FOR[budget]
    for region in world.regions:
        region.stockpile.goods = {}
    for row in world.relationships.values():
        for rel in row.values():
            rel.disposition = Disposition.NEUTRAL
    index = {c.name: i for i, c in enumerate(world.civilizations)}
    for rid, region in enumerate(world.regions):
        world.grain_reserves.granaries[rid].owner = index.get(region.controller, -1)
    inf = world.civilizations[THORNWALL].factions.influence
    inf[FactionType.CULTURAL], inf[FactionType.MERCHANT] = commons, patricians
    # Verdant: grain for sale (80 held, 4 x 12.5 kept) and timber for repairs;
    # its granary holds 18 in a store worn to half its capacity of 40.
    world.regions[VERDANT].stockpile.goods = {"grain": 80.0, "timber": 10.0}
    verdant, thornwood = world.grain_reserves.granaries[VERDANT], world.grain_reserves.granaries[THORNWOOD]
    verdant.grain, verdant.target, verdant.observed = 18.0, 18.0, 50
    thornwood.grain, thornwood.target, thornwood.observed = 0.0, 20.0, 50
    for g in (verdant, thornwood):                 # harvests that usually cover the need
        g.harvest_mean = g.harvest_sq = 1.0
    storage = enable_storage(world)
    storage.assets[VERDANT] = StorageAsset(capacity=40.0, condition=0.5, owner=THORNWALL)
    storage.assets[THORNWOOD] = StorageAsset(capacity=100.0, condition=1.0, owner=THORNWALL)
    for rid, asset in enumerate(storage.assets):
        if asset is None:
            storage.assets[rid] = StorageAsset(capacity=100.0, owner=world.grain_reserves.granaries[rid].owner)
    storage.receipts = [_receipt(VERDANT, 0.5, 40.0, requested=30.0), _receipt(THORNWOOD, 1.0, 100.0, requested=20.0)]
    storage.receipt_turn = world.turn
    world.cities = CityState(cities=[City(settlement_id=CITY, region=THORNWOOD, name="Thornhold", founded_turn=1,
                                          founder=THORNWALL, lord=THORNWALL, rank=1, size=15.0, grievance=0.2)])
    world.livelihoods = LivelihoodsState()
    if workshop:
        world.livelihoods.workshops = state = WorkshopState(mode="operate")
        state.sites = [WorkshopSite(site=0, region=THORNWOOD, settlement_id=CITY, city_name="Thornhold",
                                    selected_turn=1, asset="open", construction_paid=W.CONSTRUCTION_COST)]
        state.next_site = 1
        state.frame_turn = world.turn
        state.frame = [_workshop_receipt(world.turn, funded=False)]
    if food:
        world.livelihoods.food_allocation = FoodAllocationState(
            regime="targeted_relief", frame_turn=world.turn,
            regions=[{"region": THORNWOOD, "shortfall_poorer_half": 6.0, "people_poorer_half": 6}])
    LB.set_local_budgets_enabled(world, True, args=SimpleNamespace(local_budget_mode=mode))
    return world


def _receipt(rid, condition, capacity, *, requested):
    return StorageReceipt(turn=30, region=rid, owner=THORNWALL, policy="neglect", requested=0.0, delivered=0.0,
                          timber_reserved=0.0, timber_used=0.0, timber_returned=0.0, treasury_paid=0,
                          condition_before=condition, condition_after=condition, capacity_before=capacity,
                          capacity_after=capacity, repair_progress=0.0, expansion_progress=0.0,
                          target_requested=requested, target_feasible=min(requested, capacity * condition))


def _workshop_receipt(turn, *, funded):
    return WorkshopReceipt(turn=turn, site=0, region=THORNWOOD, settlement_id=CITY, rank=1, diverted_fraction=0.2,
                           resident_adult_farmers=3, excluded_trip=0, excluded_army=0, excluded_assigned=0,
                           eligible=3, crew=[10, 20, 30], crew_ages=[30, 30, 30], work_available=0.6,
                           allocated=0.6 if funded else 0.0, asset="open" if funded else "idle", payer=THORNWALL,
                           funded=funded)


def _economy(world, *, verdant_supply=125.0, hungry=0.5):
    """Demand 0.5 per head; Verdant's food price 12.5 / supply; Thornwood short."""
    res = EconomyResult()
    for region in world.regions:
        demand = 0.5 * region.population
        s = hungry if region.name == "Thornwood" else 1.0
        res.food_sufficiency[region.name] = s
        res.market_demand[region.name] = (demand, 0.0, 0.0, 0.0)
        res.market_supply[region.name] = (max(s * demand, 1.0), 0.0, 0.0, 0.0)
        res.slot_output[region.name] = [0.0, 0.0, 0.0]
        res.forage_output[region.name] = demand
    res.market_supply["Verdant Plains"] = (verdant_supply, 0.0, 0.0, 0.0)
    return res


class _Sim:
    """Stand-in crew planner: three farmers at the site, no craft output."""

    def __init__(self):
        self.inputs = None

    def plan_workshop_crews(self, requests, enlisted, turn=None):
        return [(site, region, settlement, 3, 0, 0, 0, 3, [10, 20, 30], [30, 30, 30], 3 * diverted)
                for site, region, settlement, diverted, _ in requests]

    def take_craft_inputs(self):
        out, self.inputs = self.inputs, None
        return out


def _decide(world, res=None):
    return LB.phase10(world, acc=None, economy_result=res or _economy(world), agent_bridge=None)


def _execute(world, res=None, *, before_phase2=None):
    """Turn T+1: Phase 2 storage and workshops, Phase 10 purchases, then L9."""
    world.turn += 1
    res = res or _economy(world)
    if before_phase2 is not None:
        before_phase2(world)
    plan = prepare_storage_work(world, [0.5 * r.population for r in world.regions], acc=None, commitments={})
    bridge = SimpleNamespace(_sim=_Sim())
    batch = pa.record_batch({"region_id": pa.array(range(len(world.regions)), pa.uint16()),
                             "craft_raw_demand": pa.array([1.0] * len(world.regions), pa.float32())})
    if W.workshops_active(world):
        batch = W.prepare_phase2(world, batch, bridge, None, None)
    LB.prepare_phase2(world, batch, bridge, None, None)
    finish_storage_work(world, plan, list(plan.requests))
    if W.workshops_active(world):
        bridge._sim.inputs = [[0.0] * 9 for _ in world.regions]
        W.finish_phase2(world, SimpleNamespace(craft_output={r.name: 0.0 for r in world.regions}), bridge, None)
    targets = [g.target for g in world.grain_reserves.granaries]
    original = G._observe
    try:
        G._observe = lambda *a: None
        G.tick_grain_reserves(world, None, res)
    finally:
        G._observe = original
    for g, t in zip(world.grain_reserves.granaries, targets):
        g.target = t
    return LB.phase10(world, acc=None, economy_result=res, agent_bridge=None)


def _decision(world, civ=THORNWALL):
    return next(d for d in world.livelihoods.local_budgets.decisions if d.civ == civ)


def _awarded(decision):
    return {decision.proposals[a.pid].service: a.amount for a in decision.awards}


def _settled(world, service):
    return next(c for c in world.livelihoods.local_budgets.settled if c.service == service and c.civ == THORNWALL)


# --- proposals, budget and arbitration -----------------------------------------------

def test_proposals_have_costs_recipients_and_dated_benefits():
    world = _world()
    _decide(world)
    d = _decision(world)
    assert d.budget == 10 and d.projected == 60 and d.floor == 20 and d.obligations == 0
    by = {p.service: p for p in d.proposals}
    assert set(by) == {"relief", "granary_maintain", "granary_expand", "workshop"}
    relief = by["relief"]
    # Verdant sells 30 beyond four turns of its need at 0.1: 2 coins buy toward
    # Thornwood's empty granary (target 20), less transit loss.
    assert relief.recipients == [THORNWOOD] and relief.cost == 2 and relief.divisible
    assert relief.expected == pytest.approx(20.0 * (1 - G._transit_loss()), rel=0.05)
    assert relief.relief["commons"] == pytest.approx(3.0)              # 6 rations short x 0.5 food
    maintain, expand = by["granary_maintain"], by["granary_expand"]
    assert maintain.claims == expand.claims == [f"storage:{VERDANT}"]
    assert maintain.cost == 8 and maintain.expected == 4.0
    assert maintain.relief["commons"] == pytest.approx(10 * 0.07 * 0.1 * 18 + 4.0)
    assert by["workshop"].cost == W.UPKEEP and by["workshop"].relief == {"patricians": pytest.approx(0.6)}
    assert all(p.source_turn == 30 for p in d.proposals)
    assert d.burdens["commons"] == pytest.approx(3.0 + 10 * 0.07 * 0.5 * 18 + 10.0)
    assert d.burdens["patricians"] == pytest.approx(0.6)


def test_relief_counts_the_reserve_gap_the_harvest_record_expects():
    world = _world()
    world.grain_reserves.granaries[THORNWOOD].harvest_mean = 0.8     # a fifth of the need short on average
    _decide(world)
    d = _decision(world)
    relief = next(p for p in d.proposals if p.service == "relief")
    demand = 0.5 * world.regions[THORNWOOD].population
    expected = LB.HORIZON * 0.2 * demand
    assert relief.detail["expected_short"] == pytest.approx(expected)
    assert relief.relief["commons"] == pytest.approx(min(relief.expected, 3.0 + expected))
    assert d.burdens["commons"] == pytest.approx(3.0 + 10 * 0.07 * 0.5 * 18 + 10.0 + min(20.0, expected))


def test_a_foreign_market_sells_only_beyond_its_own_rulers_granary_deficits():
    ASHARA, SELURIAN = 3, 3
    world = _world()
    world.regions[VERDANT].stockpile.goods = {"timber": 10.0}           # no surplus at home
    world.regions[ASHARA].stockpile.goods = {"grain": 300.0}             # abroad, next to Verdant
    selurian = world.grain_reserves.granaries[ASHARA]
    selurian.target, selurian.grain, selurian.observed = 200.0, 0.0, 50
    selurian.harvest_mean = selurian.harvest_sq = 1.0
    res = _economy(world)
    res.market_supply["Ashara Desert"] = (300.0, 0.0, 0.0, 0.0)
    _decide(world, res)
    # Selurian's own granary takes what Ashara sells before any foreign buyer.
    assert not [p for p in _decision(world).proposals if p.service == "relief"]
    world = _world()
    world.regions[VERDANT].stockpile.goods = {"timber": 10.0}
    world.regions[ASHARA].stockpile.goods = {"grain": 300.0}
    world.grain_reserves.granaries[ASHARA].target = 0.0
    res = _economy(world)
    res.market_supply["Ashara Desert"] = (300.0, 0.0, 0.0, 0.0)
    _decide(world, res)
    relief = next(p for p in _decision(world).proposals if p.service == "relief")
    assert relief.recipients == [THORNWOOD] and relief.expected > 0


def test_constituencies_prefer_different_feasible_allocations_and_influence_decides():
    commons = _world(budget=10, commons=0.6, patricians=0.1)
    _decide(commons)
    d = _decision(commons)
    services = {p.pid: p.service for p in d.proposals}
    own = {name: sorted(services[pid] for pid, _ in d.candidates[name]) for name in ("commons", "patricians")}
    assert own == {"commons": ["granary_maintain", "relief"], "patricians": ["workshop"]}
    assert d.outcome == "commons_first" and _awarded(d) == {"relief": 2, "granary_maintain": 8}
    patricians = _world(budget=10, commons=0.1, patricians=0.6)
    _decide(patricians)
    d = _decision(patricians)
    assert d.chosen in ("compromise", "patricians")
    assert "workshop" in _awarded(d) and sum(a.amount for a in d.awards) <= d.budget


def test_incompatible_promises_are_refused():
    world = _world(budget=10)
    _decide(world)
    d = _decision(world)
    expand = next(p.pid for p in d.proposals if p.service == "granary_expand")
    assert dict(d.refused)[expand] == "incompatible"
    claims = [c for a in d.awards for c in d.proposals[a.pid].claims]
    assert len(claims) == len(set(claims))
    # Commons can never hold both promises over one storage slot, whatever the budget.
    world = _world(budget=10)
    world.civilizations[THORNWALL].treasury = 10_000
    _decide(world)
    d = _decision(world)
    slot = [d.proposals[a.pid].service for a in d.awards if d.proposals[a.pid].claims == [f"storage:{VERDANT}"]]
    assert len(slot) == 1


def test_the_budget_is_one_projected_envelope_less_obligations(monkeypatch):
    world = _world(budget=10)
    monkeypatch.setattr(LB.TEACHING, "obligations", lambda w, civ, obs: 12 if civ == THORNWALL else 0)
    _decide(world)
    d = _decision(world)
    assert d.obligations == 12 and d.budget == math.floor(0.25 * (60 - 20 - 12))
    state = world.livelihoods.local_budgets
    assert sum(c.amount for c in state.open if c.civ == THORNWALL) <= d.budget


def test_teaching_supplies_are_reserved_from_dated_receipts(monkeypatch):
    import chronicler.learning_services as L
    receipt = SimpleNamespace(source_turn=30, lord=THORNWALL, craft_price=0.5, learner_upper_bound=12,
                              scholar_upper_bound=1, paid=3)
    world = SimpleNamespace(scholarship=SimpleNamespace(learning_services=SimpleNamespace(procurement_receipts=[receipt])))
    monkeypatch.setattr(L, "learning_services_active", lambda w: True)
    obs = SimpleNamespace(turn=30)
    assert LB.TEACHING.obligations(world, THORNWALL, obs) == math.ceil(8 * 0.5)
    assert LB.TEACHING.obligations(world, 0, obs) == 0
    assert LB.TEACHING.obligations(world, THORNWALL, SimpleNamespace(turn=31)) == 0


def test_proposals_are_bounded_per_civ_and_turn():
    items = [LB.Proposal(pid=0, service="granary_maintain", civ=0, source_turn=1, recipients=[i],
                         claims=[f"storage:{i}"], cost=2, unit="work", expected=1.0, relief={"commons": float(i)})
             for i in range(10)]
    items += [LB.Proposal(pid=0, service="workshop", civ=0, source_turn=1, recipients=[i], site=i,
                          claims=[f"workshop:{i}"], cost=3, unit="work", expected=1.0, relief={"patricians": 1.0 + i})
              for i in range(3)]
    kept = LB._bounded(items)
    assert len(kept) == MAX_PROPOSALS
    # Each constituency's best items come in turn: all three workshops stay.
    assert sum(p.service == "workshop" for p in kept) == 3
    assert {p.recipients[0] for p in kept if p.service == "granary_maintain"} == {9, 8, 7, 6, 5}


# --- execution: unfunded promises, changed allocations, deferrals ---------------------

def test_unfunded_promises_do_nothing():
    world = _world(budget=10)
    storage = world.grain_reserves.storage
    # Enabling L9 takes over the storage policy: nothing is funded yet.
    assert all(p.policy == "neglect" and p.work_budget == 0.0 for p in storage.policies)
    # No decision yet: every governed service stands still under L9.
    events = _execute(world)
    assert events == []
    assert world.livelihoods.workshops.frame[0].funded is False
    assert world.civilizations[THORNWALL].treasury == 60
    assert all(r.requested == 0.0 and r.treasury_paid == 0 for r in storage.receipts)
    assert not [f for f in world.grain_reserves.flows if f.kind == BOUGHT]


def test_a_changed_allocation_moves_actual_goods_work_and_payments():
    results = {}
    for name, (c, p) in {"commons": (0.6, 0.1), "patricians": (0.1, 0.6)}.items():
        world = _world(budget=3, commons=c, patricians=p)
        _decide(world)
        _execute(world)
        storage = {r.region: r for r in world.grain_reserves.storage.receipts}
        bought = sum(f.amount for f in world.grain_reserves.flows if f.kind == BOUGHT and f.buyer == THORNWALL)
        results[name] = dict(
            workshop_paid=world.livelihoods.workshops.frame[0].paid or {},
            storage_work=storage[VERDANT].delivered, storage_paid=storage[VERDANT].treasury_paid,
            grain_bought=bought, granary=world.grain_reserves.granaries[THORNWOOD].grain,
            treasury=world.civilizations[THORNWALL].treasury)
    commons, patricians = results["commons"], results["patricians"]
    # Commons: relief bought grain (2 coins) and a coin of repairs; the workshop idled.
    assert commons["grain_bought"] > 15 and commons["granary"] > 15 and commons["workshop_paid"] == {}
    assert commons["storage_work"] == pytest.approx(0.5) and commons["storage_paid"] == 1
    # Patricians: the workshop's upkeep was paid; no grain, no repairs.
    assert patricians["workshop_paid"] == {"upkeep": W.UPKEEP} and patricians["grain_bought"] == 0
    assert patricians["storage_work"] == 0.0 and patricians["granary"] == 0.0
    assert commons["treasury"] == patricians["treasury"] == TREASURY_FOR[3] - 3


def test_relief_first_leaves_maintenance_debt():
    world = _world(budget=3, commons=0.6, patricians=0.1)
    _decide(world)
    d = _decision(world)
    # Relief first; the one coin left buys half a unit of the four repair work
    # units the worn granary needs (8 coins).
    assert d.outcome == "commons_first" and _awarded(d) == {"relief": 2, "granary_maintain": 1}
    _execute(world)
    verdant = world.grain_reserves.storage.assets[VERDANT]
    # No repair batch completed: the granary wore further and the debt grows.
    assert verdant.condition == pytest.approx(0.49) and verdant.repair_progress == pytest.approx(0.5)
    assert world.grain_reserves.granaries[THORNWOOD].grain > 15
    assert _settled(world, "relief").outcome == "kept"
    # The next decision has no poorer-half receipt for turn 31: the commons'
    # burden is unknown (None), not zero, and relief gets no support.
    d = _decision(world)
    assert d.turn == 31 and d.burdens["commons"] is None
    assert all("commons" not in p.relief for p in d.proposals if p.service == "relief")


def test_production_first_leaves_some_households_worse_off():
    after = {}
    for name, (c, p) in {"relief_first": (0.6, 0.1), "production_first": (0.1, 0.6)}.items():
        world = _world(budget=3, commons=c, patricians=p)
        _decide(world)
        d = _decision(world)
        after[name] = d.outcome
        _execute(world)
        # The next shortfall in Thornwood: the granary covers what it holds.
        world.turn += 1
        res = _economy(world, hungry=0.5)
        G.open_granaries(world, res)
        after[name + "_food"] = res.food_sufficiency["Thornwood"]
    assert after["relief_first"] == "commons_first" and after["production_first"] == "patricians_first"
    # Thornwood's poorer households (targeted relief routes the release to
    # them) eat the release only where relief was bought.
    assert after["relief_first_food"] == pytest.approx(1.0)
    assert after["production_first_food"] == pytest.approx(0.5)


def test_budget_loss_forces_a_visible_dated_deferral():
    world = _world(budget=10, commons=0.1, patricians=0.6)
    _decide(world)
    assert "workshop" in _awarded(_decision(world))

    def war_costs(w):                       # the treasury is spent before Phase 2
        w.civilizations[THORNWALL].treasury = 1

    events = _execute(world, before_phase2=war_costs)
    c = _settled(world, "workshop")
    assert (c.outcome, c.reason, c.decided_turn, c.settled_turn, c.spent) == ("deferred", "treasury_shortfall", 30, 31, 0)
    assert world.livelihoods.workshops.frame[0].funded is False
    (event,) = [e for e in events if e.event_type == "budget_deferral"]
    assert "treasury short" in event.description and "turn 30" in event.description
    counters = world.livelihoods.local_budgets.counters
    assert counters["deferred_treasury_shortfall"] >= 1


def test_political_response_follows_observed_delivery_not_selection():
    kept, broken = _world(budget=10, commons=0.1, patricians=0.6), _world(budget=10, commons=0.1, patricians=0.6)
    for world in (kept, broken):
        _decide(world)
        # Selection alone moves nothing.
        assert world.cities.cities[0].grievance == 0.2
    _execute(kept)
    _execute(broken, before_phase2=lambda w: setattr(w.civilizations[THORNWALL], "treasury", 1))
    assert _settled(kept, "workshop").outcome == "kept" and _settled(broken, "workshop").outcome == "deferred"
    g_kept, g_broken = kept.cities.cities[0].grievance, broken.cities.cities[0].grievance
    assert g_kept < 0.2 < g_broken
    assert g_broken - 0.2 <= LB.RESPONSE_CAP + 1e-9 and 0.2 - g_kept <= LB.RESPONSE_CAP + 1e-9
    (response,) = broken.livelihoods.local_budgets.responses
    assert response.settlement_id == CITY and response.applied == pytest.approx(g_broken - 0.2)


def test_response_is_capped_per_city_and_turn():
    world = _world(budget=10, commons=0.6, patricians=0.1)
    world.cities.cities[0].grievance = 0.95
    _decide(world)
    _execute(world, before_phase2=lambda w: setattr(w.civilizations[THORNWALL], "treasury", 0))
    assert world.cities.cities[0].grievance <= 1.0
    for r in world.livelihoods.local_budgets.responses:
        assert abs(r.applied) <= LB.RESPONSE_CAP + 1e-9


def test_fixed_shares_control_splits_the_same_budget_without_response():
    world = _world(budget=10, commons=0.6, patricians=0.1, mode="fixed_shares")
    _decide(world)
    d = _decision(world)
    assert d.chosen == "fixed_shares" and d.budget == 10
    awards = _awarded(d)
    # relief 0.4 x 10 = 4 (needs 2), granary 3 (partial repair), workshop 3 (upkeep).
    assert awards == {"relief": 2, "granary_maintain": 3, "workshop": 3}
    assert all(a.sponsor is None for a in d.awards)
    _execute(world, before_phase2=lambda w: setattr(w.civilizations[THORNWALL], "treasury", 1))
    assert world.cities.cities[0].grievance == 0.2
    assert world.livelihoods.local_budgets.responses == []


# --- identity, persistence and the provider interface -------------------------------

def test_hooks_are_the_identity_without_local_budgets():
    world = _world()
    world.livelihoods.local_budgets = None
    site = world.livelihoods.workshops.sites[0]
    assert LB.workshop_funded(world, THORNWALL, site, 3, True) is True
    assert LB.workshop_funded(world, THORNWALL, site, 3, False) is False
    budget = [1, 2, 3, 4]
    assert LB.procurement_budget(world, budget, [100] * 4) is budget
    world = _world()
    LB.set_local_budgets_enabled(world, False)
    assert LB.workshop_funded(world, THORNWALL, site, 3, True) is True
    assert LB.procurement_budget(world, budget, [100] * 4) is budget


def test_off_switch_keeps_the_legacy_purchase_and_funding():
    def run(enabled):
        world = _world(budget=10)
        if not enabled:
            LB.set_local_budgets_enabled(world, False)
            world.livelihoods.local_budgets = None
        world.turn += 1
        original = G._observe
        try:
            G._observe = lambda *a: None                 # keep the targets set above
            G.tick_grain_reserves(world, None, _economy(world))
        finally:
            G._observe = original
        return [(f.kind, f.region, f.cost) for f in world.grain_reserves.flows], world.civilizations[THORNWALL].treasury
    legacy, unfunded = run(False), run(True)
    assert legacy[0] and not unfunded[0]          # without an envelope, L9 buys nothing


def test_pickle_round_trip_and_resume_are_exact():
    world = _world(budget=10)
    _decide(world)
    state = world.livelihoods.local_budgets
    assert state.open and state._trace == {}
    back = pickle.loads(pickle.dumps(world.livelihoods))
    assert back.model_dump_json() == world.livelihoods.model_dump_json()
    assert isinstance(back.local_budgets, LocalBudgetState) and back.local_budgets._trace == {}
    resumed = pickle.loads(pickle.dumps(world))
    _execute(world)
    _execute(resumed)
    assert resumed.livelihoods.model_dump_json() == world.livelihoods.model_dump_json()
    assert [c.treasury for c in resumed.civilizations] == [c.treasury for c in world.civilizations]
    assert resumed.cities.model_dump_json() == world.cities.model_dump_json()


def test_snapshot_unknown_is_not_zero():
    world = _world()
    world.turn += 1
    snap = LB.snapshot_summary(world)
    assert snap["decisions"] is None and snap["settled"] is None and snap["responses"] is None
    world.turn -= 1
    _decide(world)
    world.turn += 1
    snap = LB.snapshot_summary(world)
    assert snap["source_turn"] == 30 and len(snap["decisions"]) == len([c for c in world.civilizations if c.regions])
    assert snap["open"] and snap["parameters"]["envelope_share"] == LB.ENVELOPE_SHARE


def test_a_registered_provider_takes_part_in_one_budget(monkeypatch):
    calls = []

    class Payroll(LB.Provider):
        services, group = ("payroll",), "workshop"

        def proposals(self, world, civ, obs):
            if civ != THORNWALL:
                return []
            return [dict(service="payroll", recipients=[THORNWOOD], claims=["payroll:0"], cost=5,
                         unit="work", expected=1.0, relief={"patricians": 5.0})]

        def install(self, world, commitments):
            calls.append(("install", [c.amount for c in commitments]))

        def settle(self, world, c, obs):
            calls.append(("settle", c.amount, LB.envelope(world, c.civ, "payroll")))
            return {"outcome": "kept", "reason": None, "spent": c.amount, "delivered": 1.0, "ratio": 1.0}

    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "PAYROLL", Payroll(), raising=False)
    monkeypatch.setattr(LB, "PROVIDERS", LB.PROVIDERS + (f"{__name__}:PAYROLL",))
    world = _world(budget=10, commons=0.1, patricians=0.6)
    _decide(world)
    d = _decision(world)
    assert "payroll" in _awarded(d) and sum(a.amount for a in d.awards) <= d.budget
    assert ("install", [5]) in calls
    _execute(world)
    assert ("settle", 5, 5) in calls and _settled(world, "payroll").outcome == "kept"


def test_switching_off_lapses_open_promises():
    world = _world()
    _decide(world)
    state = world.livelihoods.local_budgets
    n = len(state.open)
    assert n
    LB.set_local_budgets_enabled(world, False)
    assert state.open == [] and state.counters["lapsed"] == n


def test_cli_and_prerequisites():
    from chronicler.livelihoods import configure_livelihoods
    from chronicler.main import _build_parser
    parse = _build_parser().parse_args
    args = parse(["--local-budgets", "--local-budget-mode", "fixed_shares"])
    assert (args.local_budgets, args.local_budget_mode) == (True, "fixed_shares")
    world = generate_world(seed=42, num_regions=6, num_civs=2)
    with pytest.raises(ValueError, match="grain-reserves"):
        configure_livelihoods(world, parse(["--local-budgets"]), agent_mode="hybrid")
    G.set_grain_reserves_enabled(world, True)
    with pytest.raises(ValueError, match="hybrid"):
        configure_livelihoods(world, parse(["--local-budgets"]), agent_mode="shadow")
    configure_livelihoods(world, args, agent_mode="hybrid")
    assert world.livelihoods.local_budgets.mode == "fixed_shares"
