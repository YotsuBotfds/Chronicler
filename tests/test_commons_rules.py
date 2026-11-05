"""L8 commons rules on the L3 timber stock (``--commons-rules``), offline.

docs/integration/commons-rules.md. A recorded economy stands in for the native
kernel: it produces ``min(potential, cap)`` per timber slot, as the economy's
``timber_harvest_cap_{slot}`` columns specify (null: no cap). Acceptance
cases: open access, cost-only administration, ineffective enforcement,
effective rule, neighbouring displacement, policy repeal and ownership change,
plus feature-off identity and an exact pickle round trip.
"""
from __future__ import annotations

import json
import math
import pickle

import numpy as np
import pyarrow as pa
import pytest

from chronicler import commons_rules as cr
from chronicler import timber_stock as ts
from chronicler.climate import get_climate_phase
from chronicler.commons_rules_state import COUNTER_KEYS, CommonsRulesState
from chronicler.ecology import refresh_resource_yields
from chronicler.economy import EconomyResult
from chronicler.livelihoods import (
    configure_livelihoods, finish_phase2, livelihoods_snapshot_fields, prepare_phase2, rollback_phase2,
)
from chronicler.main import _build_parser
from chronicler.world_gen import generate_world

THORN, MIST = (0, 0), (2, 0)        # template seed 3: Thornwood (civ 3), Mistwood (civ 1)
THORN_OWNER, MIST_OWNER = 3, 1


def _world(*flags, seed=3):
    world = generate_world(seed=seed)
    refresh_resource_yields(world, get_climate_phase(world.turn, world.climate_config))
    if flags:
        configure_livelihoods(world, _build_parser().parse_args(list(flags)), agent_mode="hybrid")
    return world


def _batch(world):
    data = {"region_id": pa.array(range(len(world.regions)), type=pa.uint16())}
    for slot in range(3):
        data[f"resource_type_{slot}"] = pa.array([r.resource_types[slot] for r in world.regions], type=pa.uint8())
    return pa.record_batch(data)


def _snapshot(world, farmers=5, without=()):
    """A Phase 2 agent snapshot: ``farmers`` farmers in every region (none in ``without``)."""
    regions, occupations = [], []
    for rid in range(len(world.regions)):
        n = 0 if rid in without else farmers
        regions += [rid] * (n + 1)
        occupations += [0] * n + [1]
    return pa.record_batch({"region": pa.array(regions, type=pa.uint16()),
                            "occupation": pa.array(occupations, type=pa.uint8())})


def _kernel(world, batch, potential):
    result = EconomyResult()
    for rid, region in enumerate(world.regions):
        outputs = []
        for slot in range(3):
            amount = np.float32(potential.get((rid, slot), 0.0))
            name = f"timber_harvest_cap_{slot}"
            cap = batch.column(name)[rid].as_py() if name in batch.schema.names else None
            if cap is not None:
                amount = min(amount, np.float32(cap))
            outputs.append(float(amount))
        result.slot_output[region.name] = tuple(outputs)
    return result


def _tick(world, potential=None, *, without=()):
    """One Phase 2 (prepare, the recorded kernel, finish); then the turn ends."""
    batch = prepare_phase2(world, _batch(world), None, _snapshot(world, without=without))
    result = _kernel(world, batch, potential or {})
    finish_phase2(world, result, None)
    world.turn += 1
    return batch, result


def _cap(batch, key):
    return batch.column(f"timber_harvest_cap_{key[1]}")[key[0]].as_py()


def _set_stock(world, key, share):
    for row in world.livelihoods.timber_stock.stocks:
        if (row.region_id, row.slot) == key:
            row.stock = share * ts.effective_capacity(world.regions[key[0]], key[1])


def _receipt(world, key):
    record = cr.snapshot_summary(world)
    rows = [r for r in record["receipts"] or [] if (r["region_id"], r["slot"]) == key]
    return rows[0] if rows else None


def _rule(world, key):
    rules = [r for r in world.livelihoods.commons_rules.rules if (r.region_id, r.slot) == key]
    return rules[0] if rules else None


def _adopted(*flags, share=0.1, potential=5.0):
    """A world whose Thornwood stand is depleted and harvested; the rule is
    adopted in the second Phase 2 (the first settles the dated observation)."""
    world = _world("--timber-stock", "--commons-rules", *flags)
    _set_stock(world, THORN, share)
    _tick(world, {THORN: potential})
    assert _rule(world, THORN) is None, "no dated observation yet: nothing to decide"
    return world


# --- Wiring, prerequisites, feature-off identity --------------------------------

def test_prerequisites_and_parser():
    parse = _build_parser().parse_args
    assert parse([]).commons_rules is None and parse([]).commons_rule_mode is None
    world = _world()
    with pytest.raises(ValueError, match="requires --timber-stock"):
        configure_livelihoods(world, parse(["--commons-rules"]), agent_mode="hybrid")
    with pytest.raises(ValueError, match="requires --timber-stock"):
        configure_livelihoods(world, parse(["--no-timber-stock", "--commons-rules"]), agent_mode="hybrid")
    assert world.livelihoods is None
    with pytest.raises(SystemExit):
        parse(["--commons-rule-mode", "strict"])
    world = _world("--timber-stock")
    configure_livelihoods(world, parse(["--commons-rules", "--commons-rule-mode", "cost_only"]), agent_mode="hybrid")
    assert world.livelihoods.commons_rules.mode == "cost_only" and cr.commons_rules_active(world)


def test_never_enabled_world_is_unchanged_and_has_no_record():
    world = _world("--timber-stock")
    before = world.model_dump_json()
    configure_livelihoods(world, _build_parser().parse_args(["--no-commons-rules"]), agent_mode="hybrid")
    assert world.model_dump_json() == before and world.livelihoods.commons_rules is None
    assert "commons_rules" not in json.loads(before)["livelihoods"]
    assert "commons_rules" not in livelihoods_snapshot_fields(world)["livelihoods"]


def _strip_commons(world):
    data = json.loads(world.model_dump_json())
    data["livelihoods"].pop("commons_rules", None)
    return data


def test_switch_on_without_a_depleted_stand_matches_timber_only():
    """Open access: healthy stands draw no rule, no bill and no cap change."""
    plain = _world("--timber-stock")
    ruled = _world("--timber-stock", "--commons-rules")
    potential = {THORN: 6.0, MIST: 9.0}
    for _ in range(6):
        a, _ = _tick(plain, potential)
        b, _ = _tick(ruled, potential)
        assert a.equals(b)
    assert _strip_commons(plain) == _strip_commons(ruled)
    record = cr.snapshot_summary(ruled)
    assert record["observed"] and record["receipts"] == [] and record["rules"] == []
    counters = record["counters"]
    assert counters["eligible_slot_turns"] == 10      # two slots, five dated observations
    assert counters["adoption_candidates"] == counters["adopted"] == counters["paid"] == 0


def test_unobserved_turn_is_unknown_not_zero():
    world = _world("--timber-stock", "--commons-rules")
    record = cr.snapshot_summary(world)
    assert record["observed"] is False and record["receipts"] is None and record["decisions"] is None
    assert set(record["counters"]) == set(COUNTER_KEYS)


# --- Effective rule, quota and dated knowledge ------------------------------------

def test_effective_rule_rests_a_depleted_stand_and_binds():
    world = _adopted()
    treasury = world.civilizations[THORN_OWNER].treasury
    observed, observed_turn = world.livelihoods.timber_stock.ledger[0], world.livelihoods.timber_stock.ledger_turn
    mist_cap = ts.harvest_caps(world)[MIST]
    batch, _ = _tick(world, {THORN: 5.0, MIST: 3.0})
    receipt = _receipt(world, THORN)
    assert receipt["new"] and receipt["status"] == "rest" and receipt["quota"] == 0.0
    assert receipt["observation"]["turn"] == observed_turn == world.turn - 2   # dated: last settled turn
    assert receipt["observation"]["stock"] == observed.stock
    assert receipt["paid"] == 2 and receipt["coverage"] == 1.0 and receipt["limit"] == 0.0
    assert receipt["applied"] and _cap(batch, THORN) == 0.0 and receipt["extraction"] == 0.0
    assert receipt["binding"] is True and receipt["excess"] == 0.0
    assert world.civilizations[THORN_OWNER].treasury == treasury - 2
    assert _cap(batch, MIST) == mist_cap                                # Mistwood untouched
    decisions = cr.snapshot_summary(world)["decisions"]
    assert decisions == [{"turn": 1, "region_id": 0, "slot": 0, "civ": THORN_OWNER,
                          "kind": "adopted", "reason": "depleted"}]


def test_quota_holds_harvest_to_the_observed_growth():
    world = _adopted(share=0.35)
    ledger = {(r.region_id, r.slot): r for r in world.livelihoods.timber_stock.ledger}[THORN]
    expected = cr.allowable_harvest(ledger.stock, ledger.capacity, ledger.water_gate_open)
    assert expected > 1.0
    batch, _ = _tick(world, {THORN: 500.0})
    receipt = _receipt(world, THORN)
    assert receipt["status"] == "quota" and receipt["quota"] == pytest.approx(expected)
    assert receipt["limit"] == ts._f32_floor(expected) == _cap(batch, THORN)
    assert receipt["extraction"] == receipt["limit"] and receipt["binding"]
    # Below the quota the rule does not bind.
    _tick(world, {THORN: 0.5})
    assert _receipt(world, THORN)["binding"] is False


def test_the_current_stock_is_not_known_to_the_owner():
    world = _adopted(share=0.35)
    ledger = {(r.region_id, r.slot): r for r in world.livelihoods.timber_stock.ledger}[THORN]
    _set_stock(world, THORN, 0.95)                     # e.g. an unobserved recovery this turn
    _tick(world, {THORN: 5.0})
    receipt = _receipt(world, THORN)
    assert receipt["observation"]["stock"] == ledger.stock and receipt["status"] == "quota"


def test_rest_hysteresis():
    obs = cr.StockObservation(turn=0, stock=30.0, capacity=100.0, extraction=1.0, water_gate_open=True)
    assert cr.next_status(None, obs) == "quota" and cr.next_status("rest", obs) == "rest"
    assert cr.next_status("quota", obs.model_copy(update={"stock": 20.0})) == "rest"
    assert cr.next_status("rest", obs.model_copy(update={"stock": 40.0})) == "quota"
    assert cr.next_status("quota", obs.model_copy(update={"capacity": 0.0, "stock": 0.0})) == "rest"
    assert cr.allowable_harvest(80.0, 100.0, False) == 0.0
    # Above the most productive stock the quota is that stock's growth.
    best = 100.0 * (1 - ts.SEED_FRACTION) / 2
    assert cr.allowable_harvest(90.0, 100.0, True) == pytest.approx(ts.regrowth(best, 100.0, True))


def test_effective_rule_conserves_stock_at_a_production_cost():
    """Enforced against cost-only on identical worlds: the stand keeps more
    stock and the region loses the harvest the rule withheld."""
    runs = {}
    for mode in ("enforced", "cost_only"):
        world = _adopted("--commons-rule-mode", mode, share=0.1, potential=4.0)
        extracted = 0.0
        for _ in range(40):
            _, result = _tick(world, {THORN: 4.0})
            extracted += result.slot_output[world.regions[0].name][0]
        stock = {(s.region_id, s.slot): s.stock for s in world.livelihoods.timber_stock.stocks}[THORN]
        runs[mode] = (stock, extracted, world.civilizations[THORN_OWNER].treasury,
                      cr.snapshot_summary(world)["counters"])
    (s_on, x_on, t_on, c_on), (s_off, x_off, t_off, c_off) = runs["enforced"], runs["cost_only"]
    assert s_on > s_off and x_on < x_off
    assert t_on == t_off and c_on["paid"] == c_off["paid"] > 0       # identical costs
    assert c_on["binding_turns"] > 0 and c_off["binding_turns"] == 0
    assert 0.0 < c_off["excess"] <= c_off["extraction_under_rule"]
    assert c_off["would_bind_turns"] > 0 and c_on["tightened_turns"] > 0 and c_off["tightened_turns"] == 0


# --- Cost-only administration --------------------------------------------------------

def test_cost_only_pays_and_records_without_a_cap():
    world = _adopted("--commons-rule-mode", "cost_only")
    treasury = world.civilizations[THORN_OWNER].treasury
    stock_cap = ts.harvest_caps(world)[THORN]
    batch, _ = _tick(world, {THORN: 5.0})
    receipt = _receipt(world, THORN)
    assert receipt["paid"] == 2 and world.civilizations[THORN_OWNER].treasury == treasury - 2
    assert receipt["limit"] == 0.0 and receipt["applied"] and receipt["binding"] is None
    assert _cap(batch, THORN) == stock_cap == receipt["stock_cap"] > 5.0
    assert receipt["extraction"] == pytest.approx(5.0) and receipt["excess"] == pytest.approx(5.0)
    assert receipt["grievance_added"] == 0.0


def test_cost_only_batches_equal_timber_only():
    plain = _world("--timber-stock")
    _set_stock(plain, THORN, 0.1)
    world = _adopted("--commons-rule-mode", "cost_only")
    _tick(plain, {THORN: 5.0})
    for _ in range(4):
        a, _ = _tick(plain, {THORN: 5.0})
        b, _ = _tick(world, {THORN: 5.0})
        assert a.equals(b)


# --- Ineffective enforcement ---------------------------------------------------------

def test_partial_payment_leaves_part_of_the_stand_open_access():
    world = _adopted()
    _tick(world, {THORN: 5.0})                         # adopted, fully paid
    world.civilizations[THORN_OWNER].treasury = 1
    stock_cap = ts.harvest_caps(world)[THORN]
    batch, _ = _tick(world, {THORN: 500.0})
    receipt = _receipt(world, THORN)
    assert receipt["paid"] == 1 and receipt["coverage"] == 0.5
    assert receipt["limit"] == ts._f32_floor(0.5 * receipt["quota"] + 0.5 * stock_cap) == _cap(batch, THORN)
    assert 0.0 < receipt["limit"] < stock_cap and receipt["extraction"] == receipt["limit"]


def test_unpaid_rule_is_open_access_and_is_repealed():
    world = _adopted()
    _tick(world, {THORN: 5.0})
    world.civilizations[THORN_OWNER].treasury = 0
    for turn in range(3):
        batch, _ = _tick(world, {THORN: 5.0})
        receipt = _receipt(world, THORN)
        assert receipt["paid"] == 0 and receipt["coverage"] == 0.0 and not receipt["applied"]
        assert _cap(batch, THORN) == receipt["stock_cap"] and receipt["binding"] is False
        assert _rule(world, THORN).unfunded_turns == turn + 1
    world.civilizations[THORN_OWNER].treasury = 100
    _tick(world, {THORN: 5.0})
    record = cr.snapshot_summary(world)
    assert _rule(world, THORN) is None and record["receipts"] == []
    assert [d["reason"] for d in record["decisions"]] == ["unfunded"]
    assert record["counters"]["repealed_unfunded"] == 1 and record["counters"]["zero_coverage_turns"] == 3
    # The cooldown blocks an immediate readoption.
    for _ in range(3):
        _tick(world, {THORN: 5.0})
        assert _rule(world, THORN) is None


def test_adoption_needs_the_full_first_bill():
    world = _adopted()
    world.civilizations[THORN_OWNER].treasury = 1
    _tick(world, {THORN: 5.0})
    counters = cr.snapshot_summary(world)["counters"]
    assert _rule(world, THORN) is None
    assert counters["adoption_candidates"] == counters["adoption_unaffordable"] == 1


def test_pending_workshop_and_storage_bills_are_left_untouched(monkeypatch):
    from chronicler import workshops
    from chronicler.workshops_state import WorkshopState
    world = _adopted()
    world.civilizations[THORN_OWNER].treasury = 4
    state = WorkshopState(enabled=False)
    world.livelihoods.workshops = state
    state._plan = workshops._Plan(world.turn, [workshops._SitePlan(
        None, THORN_OWNER, "x", {"upkeep": 3}, True, True, 0.0, {})], {})
    assert cr.pending_phase2_bills(world)[THORN_OWNER] == 3
    monkeypatch.setattr(workshops, "_pending_storage_bills", lambda w: [0, 0, 0, 0])
    _tick(world, {THORN: 5.0})
    assert _rule(world, THORN) is None
    assert cr.snapshot_summary(world)["counters"]["adoption_unaffordable"] == 1
    assert world.civilizations[THORN_OWNER].treasury == 4


def test_commons_management_supplies_wardens():
    from chronicler.governance_runtime import set_governance_enabled
    from chronicler.governance_state import CivGovernance, GovernanceInstitution
    world = _adopted()
    set_governance_enabled(world, True)
    civ = world.civilizations[THORN_OWNER]
    civ.governance = CivGovernance(institutions=[GovernanceInstitution(
        institution_type="commons_management", enacted_turn=0, legitimacy=0.5, opposing_faction="cultural")])
    civ.governance.funding_turn = world.turn
    civ.governance.last_institution_funding_ratio = 1.0
    treasury = civ.treasury
    _tick(world, {THORN: 5.0})
    receipt = _receipt(world, THORN)
    assert receipt["institution_share"] == 0.5 and receipt["bill"] == receipt["paid"] == 1
    assert receipt["coverage"] == 1.0 and civ.treasury == treasury - 1
    # Unfunded institutions supply nothing.
    civ.governance.funding_turn = world.turn
    civ.governance.last_institution_funding_ratio = 0.0
    _tick(world, {THORN: 5.0})
    assert _receipt(world, THORN)["institution_share"] == 0.0 and _receipt(world, THORN)["paid"] == 2


def test_settlement_refuses_a_bill_the_treasury_no_longer_covers():
    world = _adopted()
    batch = prepare_phase2(world, _batch(world), None, _snapshot(world))
    world.civilizations[THORN_OWNER].treasury = 0      # a spender the plan did not see
    before = world.livelihoods.commons_rules.model_dump_json()
    with pytest.raises(RuntimeError, match="exceeds the projected treasury"):
        finish_phase2(world, _kernel(world, batch, {THORN: 5.0}), None)
    rollback_phase2(world)
    assert world.livelihoods.commons_rules.model_dump_json() == before


def test_settlement_refuses_a_payer_that_lost_the_region_mid_turn():
    world = _adopted()
    batch = prepare_phase2(world, _batch(world), None, _snapshot(world))
    world.regions[0].controller = world.civilizations[0].name
    with pytest.raises(RuntimeError, match="payer changed"):
        finish_phase2(world, _kernel(world, batch, {THORN: 5.0}), None)
    rollback_phase2(world)


# --- Repeal, lapse and ownership change ---------------------------------------------

def test_recovered_stand_repeals_the_rule():
    world = _adopted()
    _tick(world, {THORN: 5.0})
    _set_stock(world, THORN, 0.9)
    _tick(world, {THORN: 5.0})                          # settles the recovered account
    assert _rule(world, THORN) is not None
    _tick(world, {THORN: 5.0})
    record = cr.snapshot_summary(world)
    assert _rule(world, THORN) is None and record["decisions"][0]["reason"] == "recovered"
    assert world.livelihoods.commons_rules.cooldowns[0].until == world.turn - 1 + cr.COOLDOWN_TURNS


def test_idle_stand_repeals_the_rule():
    world = _adopted()
    _tick(world, {THORN: 5.0})
    for _ in range(cr.IDLE_LIMIT):
        _tick(world, {THORN: 5.0}, without=(0,))
        assert _receipt(world, THORN)["possible"] is False
    _tick(world, {THORN: 5.0})
    assert _rule(world, THORN) is None
    assert cr.snapshot_summary(world)["counters"]["repealed_idle"] == 1


def test_ownership_change_lapses_and_the_new_controller_decides_afresh():
    world = _adopted()
    _tick(world, {THORN: 5.0})
    old = world.civilizations[THORN_OWNER]
    new_owner = 0
    world.regions[0].controller = world.civilizations[new_owner].name
    treasuries = (old.treasury, world.civilizations[new_owner].treasury)
    batch, _ = _tick(world, {THORN: 5.0})
    record = cr.snapshot_summary(world)
    assert record["decisions"] == [{"turn": world.turn - 1, "region_id": 0, "slot": 0, "civ": THORN_OWNER,
                                    "kind": "lapsed", "reason": "owner_changed"}]
    assert _rule(world, THORN) is None and _cap(batch, THORN) > 0.0   # open access this turn
    assert record["counters"]["lapsed_owner_changed"] == 1
    # The rest left no harvest in the dated account, so the new controller
    # waits for an observed harvest; then adopts and pays from its own treasury.
    _tick(world, {THORN: 5.0})
    rule = _rule(world, THORN)
    assert rule is not None and rule.owner == new_owner and rule.adopted_turn == world.turn - 1
    assert old.treasury == treasuries[0]
    assert world.civilizations[new_owner].treasury == treasuries[1] - 2


def test_slot_no_longer_timber_lapses():
    world = _adopted()
    _tick(world, {THORN: 5.0})
    world.regions[0].resource_types[0] = 0             # the stand became grain
    _tick(world, {})
    record = cr.snapshot_summary(world)
    assert _rule(world, THORN) is None and record["decisions"][0]["reason"] == "slot_removed"


def test_disabling_freezes_rules_without_caps_or_bills():
    world = _adopted()
    _tick(world, {THORN: 5.0})
    configure_livelihoods(world, _build_parser().parse_args(["--no-commons-rules"]), agent_mode="hybrid")
    treasury = world.civilizations[THORN_OWNER].treasury
    batch, _ = _tick(world, {THORN: 5.0})
    assert _cap(batch, THORN) > 0.0 and world.civilizations[THORN_OWNER].treasury == treasury
    assert _rule(world, THORN) is not None and "commons_rules" not in livelihoods_snapshot_fields(world)["livelihoods"]
    configure_livelihoods(world, _build_parser().parse_args(["--commons-rules"]), agent_mode="hybrid")
    batch, _ = _tick(world, {THORN: 5.0})
    assert _receipt(world, THORN) is not None


# --- Conflict routed to the city's grievance -----------------------------------------

def _city(world, rid=0, grievance=0.2, unrest=0.1):
    from chronicler.cities_state import City, CityState
    world.cities = CityState(cities=[City(settlement_id=7, region=rid, name="Thornwood Town", founded_turn=0,
                                          founder=THORN_OWNER, lord=THORN_OWNER, rank=1, size=15.0,
                                          grievance=grievance, unrest=unrest)])
    return world.cities.cities[0]


def test_binding_rule_raises_city_grievance_up_to_a_ceiling():
    world = _adopted()
    city = _city(world)
    added = []
    for _ in range(4):
        _tick(world, {THORN: 5.0})
        receipt = _receipt(world, THORN)
        assert receipt["binding"] and receipt["city"] == 7
        added.append(receipt["grievance_added"])
    assert added == pytest.approx([0.02, 0.02, 0.01, 0.0])
    assert city.grievance == cr.GRIEVANCE_CEILING
    assert _rule(world, THORN).grievance == pytest.approx(0.05)
    # Nothing is added where the rule did not bind (harvest impossible).
    city.grievance = 0.0
    _tick(world, {THORN: 5.0}, without=(0,))
    assert _receipt(world, THORN)["grievance_added"] == 0.0 and city.grievance == 0.0


def test_two_binding_stands_in_one_region_add_grievance_once_each():
    from chronicler.models import ResourceType
    world = _world()
    world.regions[2].resource_types[1] = ResourceType.TIMBER        # Mistwood: two timber slots
    configure_livelihoods(world, _build_parser().parse_args(["--timber-stock", "--commons-rules"]),
                          agent_mode="hybrid")
    second = (2, 1)
    for key in (MIST, second):
        _set_stock(world, key, 0.1)
    _tick(world, {MIST: 5.0, second: 5.0})
    city = _city(world, rid=2, grievance=0.1)
    _tick(world, {MIST: 5.0, second: 5.0})
    added = [_receipt(world, key)["grievance_added"] for key in (MIST, second)]
    assert added == pytest.approx([0.02, 0.02]) and city.grievance == pytest.approx(0.14)


def test_cost_only_and_cityless_regions_add_no_grievance():
    world = _adopted("--commons-rule-mode", "cost_only")
    city = _city(world)
    _tick(world, {THORN: 5.0})
    assert _receipt(world, THORN)["grievance_added"] == 0.0 and city.grievance == 0.2
    world = _adopted()
    _city(world, rid=2)                                # a city elsewhere
    _tick(world, {THORN: 5.0})
    assert _receipt(world, THORN)["city"] is None and _receipt(world, THORN)["grievance_added"] == 0.0


def test_city_at_the_revolt_threshold_forces_repeal():
    from chronicler.cities import REVOLT_UNREST
    world = _adopted()
    city = _city(world)
    _tick(world, {THORN: 5.0})
    city.unrest = REVOLT_UNREST
    _tick(world, {THORN: 5.0})
    record = cr.snapshot_summary(world)
    assert _rule(world, THORN) is None and record["decisions"][0]["reason"] == "unrest"


# --- Neighbouring displacement ---------------------------------------------------------

def test_neighbouring_open_extraction_is_observed_not_shifted():
    """A constructed adjacency (Thornwood next to Mistwood): the neighbour's
    harvest is recorded as open extraction and stays its own labour's output;
    the economy has no channel that moves withheld harvest onto it."""
    potential = {THORN: 5.0, MIST: 3.0}
    runs = {}
    for flags in (("--commons-rules",), ()):
        world = _world("--timber-stock", *flags)
        world.regions[0].adjacencies.append("Mistwood")
        _set_stock(world, THORN, 0.1)
        outputs = []
        for _ in range(6):
            mist_cap = ts.harvest_caps(world)[MIST]
            batch, result = _tick(world, potential)
            outputs.append(result.slot_output["Mistwood"][0])
            assert _cap(batch, MIST) == mist_cap                       # never tightened
        runs[bool(flags)] = (outputs, world)
    assert runs[True][0] == runs[False][0] == [pytest.approx(3.0)] * 6
    receipt = _receipt(runs[True][1], THORN)
    assert receipt["binding"] and receipt["neighbour_slots"] == 1
    assert receipt["neighbour_open_extraction"] == pytest.approx(3.0)


# --- Phase protocol, rollback, persistence -----------------------------------------------

def test_failed_tick_charges_and_decides_nothing():
    world = _adopted()
    before = (world.livelihoods.commons_rules.model_dump_json(), world.civilizations[THORN_OWNER].treasury)
    prepare_phase2(world, _batch(world), None, _snapshot(world))
    with pytest.raises(RuntimeError, match="already pending"):
        cr.prepare_phase2(world, _batch(world), None, None, None)
    rollback_phase2(world)
    assert world.livelihoods.commons_rules._plan is None
    assert (world.livelihoods.commons_rules.model_dump_json(), world.civilizations[THORN_OWNER].treasury) == before
    _tick(world, {THORN: 5.0})
    assert _rule(world, THORN) is not None


def test_finish_refuses_an_extension_that_ignores_the_limit():
    world = _adopted()
    batch = prepare_phase2(world, _batch(world), None, _snapshot(world))
    result = _kernel(world, batch, {})
    result.slot_output["Thornwood"] = (0.5, 0.0, 0.0)  # above the zero limit, within the stock cap
    before = world.livelihoods.commons_rules.model_dump_json()
    with pytest.raises(RuntimeError, match="commons limit"):
        finish_phase2(world, result, None)
    rollback_phase2(world)
    assert world.livelihoods.commons_rules.model_dump_json() == before


def test_tighten_harvest_caps_never_raises_a_cap_and_validates():
    world = _world("--timber-stock")
    batch = ts.prepare_phase2(world, _batch(world), None, None, None)
    cap = _cap(batch, THORN)
    lowered = ts.tighten_harvest_caps(world, batch, {THORN: 1.5})
    assert _cap(lowered, THORN) == 1.5 and _cap(lowered, MIST) == _cap(batch, MIST)
    assert _cap(ts.tighten_harvest_caps(world, batch, {THORN: cap * 10}), THORN) == cap
    with pytest.raises(ValueError, match="not a timber slot"):
        ts.tighten_harvest_caps(world, batch, {(1, 0): 1.0})
    with pytest.raises(ValueError, match="invalid"):
        ts.tighten_harvest_caps(world, batch, {THORN: math.nan})
    ts.rollback_phase2(world)
    with pytest.raises(RuntimeError, match="prepared timber caps"):
        ts.tighten_harvest_caps(world, batch, {THORN: 1.0})


def test_timber_ablation_still_gets_the_rule_limit():
    world = _world("--timber-stock", "--commons-rules")
    world.tuning_overrides = {"livelihoods.timber.enforce_cap": 0}
    _set_stock(world, THORN, 0.1)
    _tick(world, {THORN: 5.0})
    batch, _ = _tick(world, {THORN: 5.0})
    assert _cap(batch, THORN) == 0.0 and _cap(batch, MIST) is None
    assert _receipt(world, THORN)["binding"] is True


def test_exact_pickle_and_json_round_trip():
    world = _adopted()
    _city(world)
    for _ in range(3):
        _tick(world, {THORN: 5.0})
    state = world.livelihoods.commons_rules
    back = pickle.loads(pickle.dumps(state))
    assert back.model_dump_json() == state.model_dump_json() and back._plan is None
    assert CommonsRulesState.model_validate_json(state.model_dump_json()).model_dump_json() == state.model_dump_json()
    container = pickle.loads(pickle.dumps(world.livelihoods))
    assert container.model_dump_json() == world.livelihoods.model_dump_json()
    # A pickle taken mid-turn never carries the plan.
    prepare_phase2(world, _batch(world), None, _snapshot(world))
    assert pickle.loads(pickle.dumps(state))._plan is None
    rollback_phase2(world)
    # A pickle without the private slot restores it.
    raw = state.__getstate__()
    raw.pop("__pydantic_private__", None)
    bare = CommonsRulesState.__new__(CommonsRulesState)
    bare.__setstate__(raw)
    assert bare._plan is None and bare.model_dump_json() == state.model_dump_json()
