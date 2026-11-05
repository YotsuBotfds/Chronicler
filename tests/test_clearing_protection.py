"""RS5 funded clearing protection (``--clearing-protection``), offline.

docs/integration/clearing-protection.md. The pure-Python ecology fallback is
the authoritative tick here (no extension): it applies the pending
protection at the clearing decision exactly as the native tick does
(tests/test_clearing_protection_parity.py compares the two). Acceptance cases:
feature-off identity, bounded deterministic adoption, enforced freezing and
charging only for active clearing, the authoritative receipt, underfunding,
the cost-only control, conquest, a failed tick, exact pickle and checkpoint
resume, dated copied observations, untouched wildfire and cooling, and the
L9 envelope.
"""
from __future__ import annotations

import argparse
import copy
import json
import pickle
from pathlib import Path

import pytest

from chronicler import clearing_protection as cp
from chronicler.accumulator import StatAccumulator
from chronicler.agent_bridge import build_region_batch
from chronicler.clearing_protection_state import COUNTER_KEYS, ClearingProtectionState
from chronicler.climate import ClimatePhase
from chronicler.ecology import tick_ecology
from chronicler.livelihoods import (
    after_ecology, before_ecology, configure_livelihoods, livelihoods_snapshot_fields,
)
from chronicler.main import _build_parser
from chronicler.world_gen import generate_world

CLEARING = 0.02
T = ClimatePhase.TEMPERATE


def _world(*flags, seed=1):
    world = generate_world(seed=seed)
    if flags:
        configure_livelihoods(world, _build_parser().parse_args(list(flags)), agent_mode="off")
    for region in world.regions:          # no clearing pressure anywhere ...
        region.population = 1
    for civ in world.civilizations:
        civ.treasury = 100
    return world


def _press(world, rid, owner, cover=0.6):
    """... except where a test puts it: population at capacity, forested."""
    region = world.regions[rid]
    region.terrain = "forest"                          # forest cover cap 0.95
    region.controller = world.civilizations[owner].name
    region.population = region.carrying_capacity
    region.ecology.forest_cover = cover
    region.ecology.water = 0.7
    return region


def _phase9(world, acc=None, phase=T):
    before_ecology(world, acc=acc)
    tick_ecology(world, phase, acc=acc)
    events = after_ecology(world, acc=acc)
    world.turn += 1
    return events


def _state(world) -> ClearingProtectionState:
    return world.livelihoods.clearing_protection


def _receipt(world, rid):
    return next(r for r in _state(world).frame if r.region_id == rid)


# --- Switch and feature-off ---------------------------------------------------------

def test_feature_off_sends_no_column_and_keeps_no_state():
    world = _world()
    assert world.livelihoods is None
    assert "clearing_protection" not in build_region_batch(world).schema.names
    assert cp.pending_protection(world) is None
    assert livelihoods_snapshot_fields(world) == {}

    on = _world("--clearing-protection")
    state = _state(on)
    assert state.enabled and state.mode == "enforced"
    assert set(state.counters) == set(COUNTER_KEYS)
    assert "clearing_protection" not in build_region_batch(on).schema.names   # no plan pending
    _press(on, 0, 0)
    before_ecology(on, acc=None)
    batch = build_region_batch(on)
    column = batch.column("clearing_protection").to_pylist()
    assert len(column) == len(on.regions) and column[0] == 1.0 and set(column[1:]) <= {0.0, 1.0}
    assert _world("--clearing-protection", "--clearing-protection-mode", "cost_only").livelihoods \
        .clearing_protection.mode == "cost_only"
    with pytest.raises(ValueError):
        cp.set_clearing_protection_enabled(on, True, args=argparse.Namespace(clearing_protection_mode="x"))


def test_disabling_freezes_protections_and_drops_a_pending_plan():
    world = _world("--clearing-protection")
    _press(world, 0, 0)
    _phase9(world)
    before_ecology(world, acc=None)
    cp.set_clearing_protection_enabled(world, False)
    assert cp.pending_protection(world) is None and _state(world)._plan is None
    assert not cp.clearing_protection_active(world)
    assert [p.region_id for p in _state(world).protections] == [0]
    assert livelihoods_snapshot_fields(world) == {}


# --- Adoption -----------------------------------------------------------------------

def test_adoption_is_bounded_by_max_regions_and_deterministic():
    world = _world("--clearing-protection")
    for rid, cover in ((1, 0.5), (2, 0.7), (3, 0.6), (4, 0.7)):
        _press(world, rid, 0, cover)
    _press(world, 5, 0, 0.1)                          # below MIN_COVER: not forested
    _phase9(world)
    state = _state(world)
    # Descending cover, then region index; at most MAX_REGIONS per civ.
    assert [p.region_id for p in state.protections] == [2, 4]
    assert all(p.payer == 0 for p in state.protections)
    c = state.counters
    assert (c["eligible_region_turns"], c["adoption_candidates"], c["adoption_over_limit"], c["adopted"]) \
        == (4, 4, 2, 2)
    assert [(d.region_id, d.kind) for d in state.decisions] == [(2, "adopted"), (4, "adopted")]
    again = _world("--clearing-protection")
    for rid, cover in ((1, 0.5), (2, 0.7), (3, 0.6), (4, 0.7)):
        _press(again, rid, 0, cover)
    _press(again, 5, 0, 0.1)
    _phase9(again)
    assert _state(again).model_dump_json() == state.model_dump_json()


def test_adoption_needs_the_first_bill_in_full():
    world = _world("--clearing-protection")
    _press(world, 0, 0)
    world.civilizations[0].treasury = cp.WARDEN_COST - 1
    _phase9(world)
    state = _state(world)
    assert state.protections == [] and state.counters["adoption_unaffordable"] == 1
    assert world.civilizations[0].treasury == cp.WARDEN_COST - 1


# --- Enforcement and payment ----------------------------------------------------------

def test_enforced_protection_freezes_cover_and_is_charged_only_while_clearing():
    world = _world("--clearing-protection")
    _press(world, 0, 0, 0.6)
    _press(world, 1, 0, 0.6)
    _press(world, 2, 0, 0.55)                          # third region: over the limit, unprotected
    _phase9(world)
    regions = world.regions
    assert regions[0].ecology.forest_cover == pytest.approx(0.6, abs=1e-12)
    assert regions[2].ecology.forest_cover == pytest.approx(0.55 - CLEARING, abs=1e-9)
    assert world.civilizations[0].treasury == 100 - 2 * cp.WARDEN_COST
    r = _receipt(world, 0)
    assert (r.pressure_planned, r.required, r.paid_planned, r.p_planned, r.p_applied, r.clearing_active,
            r.charged, r.source) == (True, 2, 2, 1.0, 1.0, True, 2, "python")
    assert r.cover_not_cleared == pytest.approx(CLEARING) and r.cover_would_keep == pytest.approx(CLEARING)
    assert r.cover_before == pytest.approx(0.6) and r.cover_after == pytest.approx(0.6)
    # The pressure lifts in region 1: nothing is due, nothing charged; the
    # protection idles (and regrowth resumes there).
    regions[1].population = 1
    _phase9(world)
    r1 = _receipt(world, 1)
    assert (r1.pressure_planned, r1.required, r1.charged, r1.clearing_active, r1.p_applied) == (False, 0, 0, False, 0.0)
    assert world.civilizations[0].treasury == 100 - 3 * cp.WARDEN_COST
    assert regions[1].ecology.forest_cover > 0.6
    held = {p.region_id: p for p in _state(world).protections}
    assert (held[0].active_turns, held[0].idle_turns, held[0].charged) == (2, 0, 4)
    assert (held[1].active_turns, held[1].idle_turns, held[1].charged) == (1, 1, 2)


def test_the_charge_follows_the_authoritative_clearing_receipt():
    world = _world("--clearing-protection")
    _press(world, 0, 0)
    before_ecology(world, acc=None)
    # The tick (native, float32) says the clearing did not fire there.
    cp.record_clearing(world, [(False, 0.0)] * len(world.regions), "native")
    after_ecology(world, acc=None)
    r = _receipt(world, 0)
    assert (r.pressure_planned, r.paid_planned, r.clearing_active, r.charged) == (True, 2, False, 0)
    assert world.civilizations[0].treasury == 100
    with pytest.raises(RuntimeError):
        cp.record_clearing(world, [(False, 0.0)] * len(world.regions), "native")   # no plan pending


def test_charges_go_through_the_accumulator_as_keep():
    world = _world("--clearing-protection")
    _press(world, 0, 0)
    acc = StatAccumulator()
    acc.add(0, world.civilizations[0], "treasury", -97, "keep")      # queued: 3 coins left
    _phase9(world, acc=acc)
    assert world.civilizations[0].treasury == 100                    # not applied yet
    changes = [(c.civ_id, c.stat, c.delta, c.category) for c in acc._changes if c.stat == "treasury"]
    assert changes == [(0, "treasury", -97, "keep"), (0, "treasury", -2, "keep")]
    acc.apply_keep(world)
    assert world.civilizations[0].treasury == 1


def test_off_mode_projection_replays_every_category():
    world = _world("--clearing-protection")
    world.agent_mode = None
    acc = StatAccumulator()
    acc.add(0, world.civilizations[0], "treasury", -99, "guard")      # applied by acc.apply() in off mode
    assert cp.projected_treasury(world, 0, acc) == 1
    world.agent_mode = "hybrid"
    assert cp.projected_treasury(world, 0, acc) == 100


def test_underfunding_lowers_p_and_an_unfunded_protection_ends():
    world = _world("--clearing-protection")
    region = _press(world, 0, 0, 0.6)
    civ = world.civilizations[0]
    civ.treasury = cp.WARDEN_COST
    _phase9(world)                                     # adopted, paid in full
    assert region.ecology.forest_cover == pytest.approx(0.6)
    civ.treasury = 1
    _phase9(world)                                     # half paid: half the clearing
    r = _receipt(world, 0)
    assert (r.paid_planned, r.p_planned, r.charged) == (1, 0.5, 1)
    assert region.ecology.forest_cover == pytest.approx(0.6 - CLEARING / 2, abs=1e-9)
    assert civ.treasury == 0
    for k in range(cp.UNFUNDED_LIMIT):
        _phase9(world)
        r = _receipt(world, 0)
        assert (r.paid_planned, r.p_applied, r.charged) == (0, 0.0, 0)
    assert region.ecology.forest_cover == pytest.approx(0.6 - CLEARING / 2 - cp.UNFUNDED_LIMIT * CLEARING, abs=1e-9)
    assert _state(world).protections[0].unfunded_turns == cp.UNFUNDED_LIMIT
    civ.treasury = 100
    _phase9(world)                                     # ended before paying; re-adopted afresh
    state = _state(world)
    assert [(d.kind, d.reason) for d in state.decisions[-2:]] == [("ended", "unfunded"),
                                                                  ("adopted", "clearing_pressure")]
    assert state.counters["ended_unfunded"] == 1
    c = state.counters
    assert (c["full_funded_turns"], c["partial_funded_turns"], c["zero_funded_turns"]) == (2, 1, cp.UNFUNDED_LIMIT)


def test_cost_only_adopts_and_pays_identically_but_leaves_the_clearing():
    worlds = {}
    for mode in ("enforced", "cost_only", None):
        flags = () if mode is None else ("--clearing-protection", "--clearing-protection-mode", mode)
        world = _world(*flags)
        _press(world, 0, 0, 0.6)
        _press(world, 3, 1, 0.5)
        for _ in range(4):
            if mode is None:
                tick_ecology(world, T, acc=None)
                world.turn += 1
            else:
                _phase9(world)
        worlds[mode] = world
    enforced, cost_only, off = worlds["enforced"], worlds["cost_only"], worlds[None]
    assert [c.treasury for c in cost_only.civilizations] == [c.treasury for c in enforced.civilizations]
    assert [c.treasury for c in off.civilizations][:2] == [100, 100]
    assert _state(cost_only).counters["charged"] == _state(enforced).counters["charged"] == 16
    assert [p.model_dump() for p in _state(cost_only).protections] == \
        [{**p.model_dump(), "cover_not_cleared": 0.0} for p in _state(enforced).protections]
    # The control's ecology is the switch-off ecology, exactly.
    assert [r.ecology.model_dump() for r in cost_only.regions] == [r.ecology.model_dump() for r in off.regions]
    assert enforced.regions[0].ecology.forest_cover > off.regions[0].ecology.forest_cover
    r = _receipt(cost_only, 0)
    assert (r.p_planned, r.p_applied, r.cover_not_cleared, r.charged) == (1.0, 0.0, 0.0, 2)
    assert r.cover_would_keep == pytest.approx(CLEARING)


# --- Lifecycle ------------------------------------------------------------------------

def test_conquest_ends_protection_and_the_new_controller_decides_afresh():
    world = _world("--clearing-protection")
    _press(world, 0, 0)
    _phase9(world)
    assert _state(world).protections[0].payer == 0
    world.regions[0].controller = world.civilizations[1].name          # conquered
    _phase9(world)
    state = _state(world)
    assert [(d.civ, d.kind, d.reason) for d in state.decisions[-2:]] == [(0, "ended", "controller_changed"),
                                                                         (1, "adopted", "clearing_pressure")]
    assert [(p.region_id, p.payer, p.adopted_turn) for p in state.protections] == [(0, 1, 1)]
    assert world.civilizations[0].treasury == 100 - cp.WARDEN_COST     # the old payer is billed no more
    assert world.civilizations[1].treasury == 100 - cp.WARDEN_COST
    world.regions[0].controller = None                                # abandoned
    _phase9(world)
    assert _state(world).protections == [] and _state(world).counters["ended_uncontrolled"] == 1


def test_lost_cover_and_idle_protections_end():
    world = _world("--clearing-protection")
    _press(world, 0, 0, 0.6)
    _press(world, 1, 0, 0.6)
    _phase9(world)
    world.regions[0].ecology.forest_cover = 0.1                         # e.g. a wildfire
    world.regions[1].population = 1
    for _ in range(cp.IDLE_LIMIT + 1):
        _phase9(world)
    c = _state(world).counters
    assert (c["ended_cover_lost"], c["ended_idle"]) == (1, 1)
    assert _state(world).protections == []


def test_a_failed_tick_charges_nothing_and_its_plan_is_dropped(monkeypatch):
    world = _world("--clearing-protection")
    _press(world, 0, 0)
    _phase9(world)
    before = (copy.deepcopy(_state(world).model_dump()), [c.treasury for c in world.civilizations])
    import chronicler.ecology as eco

    def boom(*a, **k):
        raise RuntimeError("tick failed")

    monkeypatch.setattr(eco, "_tick_water", boom)
    before_ecology(world, acc=None)
    with pytest.raises(RuntimeError, match="tick failed"):
        tick_ecology(world, T, acc=None)
    monkeypatch.undo()
    assert (_state(world).model_dump(), [c.treasury for c in world.civilizations]) == before
    # A plan without the tick's receipts cannot be settled ...
    plan = _state(world)._plan
    with pytest.raises(RuntimeError, match="no clearing receipts"):
        after_ecology(world, acc=None)
    assert [c.treasury for c in world.civilizations] == before[1]
    # ... and a stale plan is dropped by the next planning, then settles normally.
    _state(world)._plan = plan
    _phase9(world)
    state = _state(world)
    assert state.counters["abandoned_plans"] == 1 and state.counters["settled_turns"] == 2
    assert world.civilizations[0].treasury == before[1][0] - cp.WARDEN_COST


def test_settlement_refuses_a_changed_payer():
    world = _world("--clearing-protection")
    _press(world, 0, 0)
    before_ecology(world, acc=None)
    tick_ecology(world, T, acc=None)
    world.regions[0].controller = world.civilizations[1].name
    with pytest.raises(RuntimeError, match="payer changed"):
        after_ecology(world, acc=None)
    assert world.civilizations[0].treasury == 100


def test_exact_pickle_round_trip_and_resume():
    world = _world("--clearing-protection")
    _press(world, 0, 0)
    _press(world, 2, 1, 0.5)
    for _ in range(3):
        _phase9(world)
    state = _state(world)
    assert pickle.loads(pickle.dumps(state)).model_dump_json() == state.model_dump_json()
    assert ClearingProtectionState.model_validate_json(state.model_dump_json()).model_dump() == state.model_dump()
    before_ecology(world, acc=None)
    assert pickle.loads(pickle.dumps(state))._plan is None            # a mid-turn pickle carries no plan
    state._plan = None
    resumed = pickle.loads(pickle.dumps(world))
    for w in (world, resumed):
        for _ in range(4):
            _phase9(w)
    assert resumed.livelihoods.model_dump_json() == world.livelihoods.model_dump_json()
    assert [c.treasury for c in resumed.civilizations] == [c.treasury for c in world.civilizations]
    assert [r.ecology.model_dump() for r in resumed.regions] == [r.ecology.model_dump() for r in world.regions]


# --- Observation ----------------------------------------------------------------------

def test_snapshot_summary_is_dated_and_copied():
    world = _world("--clearing-protection")
    _press(world, 0, 0)
    first = livelihoods_snapshot_fields(world)["livelihoods"]["clearing_protection"]
    assert first["observed"] is False and first["receipts"] is None and first["decisions"] is None
    _phase9(world)
    snap = livelihoods_snapshot_fields(world)["livelihoods"]["clearing_protection"]
    assert (snap["schema_version"], snap["source_turn"], snap["completed_turn"], snap["observed"]) == (1, 0, 1, True)
    assert snap["parameters"]["max_regions"] == cp.MAX_REGIONS
    assert [r["region_id"] for r in snap["receipts"]] == [0]
    assert [d["kind"] for d in snap["decisions"]] == ["adopted"]
    snap["receipts"][0]["charged"] = 999
    snap["counters"]["charged"] = 999
    assert _state(world).frame[0].charged == 2 and _state(world).counters["charged"] == 2
    json.dumps(snap)
    world.turn += 1                                     # a turn without a settled Phase 9
    assert livelihoods_snapshot_fields(world)["livelihoods"]["clearing_protection"]["observed"] is False


# --- Untouched cover changes ---------------------------------------------------------

def test_cooling_damage_is_untouched_by_protection():
    worlds = []
    for flags in (("--clearing-protection",), ()):
        world = _world(*flags)
        _press(world, 0, 0, 0.6)
        if flags:
            _phase9(world, phase=ClimatePhase.COOLING)
        else:
            tick_ecology(world, ClimatePhase.COOLING, acc=None)
        worlds.append(world)
    protected, off = worlds
    lost_protected = 0.6 - protected.regions[0].ecology.forest_cover
    lost_off = 0.6 - off.regions[0].ecology.forest_cover
    assert lost_off - lost_protected == pytest.approx(CLEARING, abs=1e-9)
    assert lost_protected == pytest.approx(0.01, abs=1e-9)             # cooling damage alone


def test_wildfire_is_untouched_by_a_protection_in_force(monkeypatch):
    from chronicler import climate
    monkeypatch.setattr(climate, "_deterministic_roll", lambda *a: 0.0)
    covers = []
    for flags in (("--clearing-protection",), ()):
        world = _world(*flags)
        rid = next(i for i, r in enumerate(world.regions) if r.terrain == "forest")
        _press(world, rid, 0, 0.8)
        if flags:
            _phase9(world)
            assert [p.region_id for p in _state(world).protections] == [rid]
        else:
            tick_ecology(world, T, acc=None)
            world.turn += 1
        before = world.regions[rid].ecology.forest_cover
        climate.check_disasters(world, ClimatePhase.DROUGHT)
        covers.append((before, world.regions[rid].ecology.forest_cover))
    (pb, pa), (ob, oa) = covers
    assert pb - pa == pytest.approx(0.3) and ob - oa == pytest.approx(0.3)


# --- L9 envelope -------------------------------------------------------------------------

def test_the_local_budget_envelope_caps_payment_and_adoption(monkeypatch):
    world = _world("--clearing-protection")
    _press(world, 0, 0)
    _press(world, 1, 0, 0.5)
    caps = {0: 5, 1: 1}
    monkeypatch.setattr(cp, "_envelope", lambda w, owner, rid: caps.get(rid, 0))
    _phase9(world)                                     # region 1's envelope cannot pay a first bill
    assert [p.region_id for p in _state(world).protections] == [0]
    assert _state(world).counters["adoption_unaffordable"] == 1
    caps[0] = 1                                        # a partial envelope lowers p
    _phase9(world)
    r = _receipt(world, 0)
    assert (r.envelope, r.paid_planned, r.p_applied, r.charged) == (1, 1, 0.5, 1)


def test_the_clearing_wardens_provider_proposes_and_settles():
    from chronicler import local_budgets as LB
    assert cp.BUDGET_PROVIDER in LB._providers()
    provider = cp.BUDGET_PROVIDER
    assert (provider.services, provider.group) == (("clearing_wardens",), "wardens")
    world = _world("--clearing-protection")
    _press(world, 0, 0, 0.6)
    _press(world, 1, 0, 0.7)
    _press(world, 2, 0, 0.5)
    world.regions[0].resource_types[0] = 1             # a timber slot: a patrician stake
    world.regions[0].resource_base_yields[0] = 1.0
    obs = argparse.Namespace(economy=object(), turn=world.turn)
    items = provider.proposals(world, 0, obs)
    assert [(i["recipients"], i["claims"], i["cost"], i["divisible"]) for i in items] == \
        [([1], ["clearing:1"], 2, False), ([0], ["clearing:0"], 2, False)]   # by cover, MAX_REGIONS
    stake = {i["recipients"][0]: i["relief"] for i in items}
    assert stake[0]["patricians"] > 0 and stake[1] == {}
    assert provider.proposals(world, 0, argparse.Namespace(economy=None, turn=world.turn)) == []
    _phase9(world)
    world.turn -= 1                                    # settle in the same turn, as L9's Phase 10 does
    c = argparse.Namespace(civ=0, recipients=[0], amount=2)
    assert provider.settle(world, c, obs)["outcome"] == "kept"
    assert provider.settle(world, c, obs)["spent"] == 2
    lost = provider.settle(world, argparse.Namespace(civ=1, recipients=[0], amount=2), obs)
    assert (lost["outcome"], lost["reason"]) == ("deferred", "recipient_lost")
    none = provider.settle(world, argparse.Namespace(civ=0, recipients=[5], amount=2), obs)
    assert (none["outcome"], none["reason"]) == ("deferred", "not_adopted")
    world.turn += 1
    # Continuing protections are divisible proposals.
    items = provider.proposals(world, 0, argparse.Namespace(economy=object(), turn=world.turn))
    assert all(i["divisible"] for i in items) and len(items) == 2


def test_a_local_budget_round_trip_funds_and_settles_the_clearing_wardens(monkeypatch):
    """L9 decides (Phase 10 of T) an envelope for ``clearing:<region>``; the
    planning of T+1 pays within it; L9 settles it from this turn's receipt.
    The ``wardens`` group's fixed share counts once although two providers
    (L8 and RS5) share it."""
    from chronicler import local_budgets as LB
    from tests.test_local_budgets import THORNWALL, THORNWOOD, _economy
    from tests.test_local_budgets import _world as l9_world

    world = l9_world(mode="fixed_shares", workshop=False, food=False)
    world.civilizations[THORNWALL].treasury = 200     # budget 45: the wardens' share pays a bill
    world.livelihoods.clearing_protection = ClearingProtectionState()
    region = world.regions[THORNWOOD]
    region.population, region.ecology.forest_cover, region.ecology.water = region.carrying_capacity, 0.6, 0.7
    for rid, other in enumerate(world.regions):
        if rid != THORNWOOD:
            other.population = 1
    scales = []
    real = LB._fixed_shares
    monkeypatch.setattr(LB, "_fixed_shares", lambda d, items, groups, scale=1.0:
                        (scales.append(scale), real(d, items, groups, scale))[1])
    LB.phase10(world, acc=None, economy_result=_economy(world), agent_bridge=None)
    decision = next(d for d in world.livelihoods.local_budgets.decisions if d.civ == THORNWALL)
    awarded = {decision.proposals[a.pid].claims[0]: a.amount for a in decision.awards}
    assert awarded.get(f"clearing:{THORNWOOD}") == cp.WARDEN_COST
    # L8 active as well: the shared group still adds its share once.
    with_rs5 = scales[-1]
    monkeypatch.setattr(LB.WARDENS, "active", lambda w: True)
    LB._decide(world, LB.LocalBudgetState(), LB._Obs(world, None, None), LB._providers(), None)
    assert scales[-1] == with_rs5 == pytest.approx(scales[0])
    monkeypatch.undo()
    monkeypatch.setattr(LB, "_fixed_shares", real)

    world.turn += 1                                    # T+1: Phase 9 pays within the envelope
    treasury = world.civilizations[THORNWALL].treasury
    before_ecology(world, acc=None)
    tick_ecology(world, T, acc=None)
    after_ecology(world, acc=None)
    r = _receipt(world, THORNWOOD)
    assert (r.payer, r.envelope, r.paid_planned, r.charged) == (THORNWALL, cp.WARDEN_COST, 2, 2)
    assert world.civilizations[THORNWALL].treasury == treasury - 2
    LB.phase10(world, acc=None, economy_result=_economy(world), agent_bridge=None)
    settled = next(c for c in world.livelihoods.local_budgets.settled if c.service == "clearing_wardens")
    assert (settled.outcome, settled.spent) == ("kept", 2)


# --- End to end (CLI, Python fallback) ------------------------------------------------------

def _args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=1, turns=turns, civs=4, regions=8,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents="off", tuning_overrides={}, clearing_protection=True,
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def test_a_run_protects_charges_and_resumes_exactly(tmp_path):
    from chronicler import run_checkpoint as rc
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import execute_run

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
    execute_run(_args(straight, 30, checkpoint_every=12, checkpoint=str(straight / "c{turn}.ckpt")))
    assert rc.describe(straight / "c12.ckpt")["flags"]["clearing_protection"] is True
    state = json.loads((straight / "state.json").read_text())["livelihoods"]["clearing_protection"]
    assert state["counters"]["settled_turns"] == 30 and state["counters"]["charged"] > 0
    assert state["counters"]["cover_not_cleared"] > 0
    resumed = tmp_path / "resumed"
    args = _args(resumed, 30)
    args.clearing_protection = None
    execute_run(args, checkpoint_resume=rc.read_checkpoint(straight / "c12.ckpt"))
    expected, got = outputs(straight), outputs(resumed)
    assert got.keys() == expected.keys()
    assert [name for name in got if got[name] != expected[name]] == []
