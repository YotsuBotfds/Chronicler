"""D1a poor relief as a real service (``--reform-services``): offline contract.

No native extension: a stand-in simulator gives keyed native wealth transfers
(``tests/test_money.py``'s rules) and the household-retail turn is constructed
directly (a settled provisioning row per pilot region). The real-native path is
``test_reform_services_native.py``. Worlds are the template seed 42.
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from fractions import Fraction

import pytest

from chronicler import household_retail as HR
from chronicler import money as M
from chronicler import reform_services as RS
from chronicler.agent_movements_state import (
    COMMONS, HOME_RULE, IN_FORCE, LAPSED, RELIEF, TOLERATION, MovementState, Reform,
)
from chronicler.household_retail_state import RETAIL_GOODS, HouseholdRetailState, RetailRegion
from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES, LivelihoodsState
from chronicler.reform_services_state import COUNTERS, ReformServicesState
from chronicler.world_gen import generate_world
from tests.test_money import FakeSim

VERDANT, AMBER = 2, 5          # template 42: Thornwall's and Kethani's capitals


def _world(mode="service", *, owners=None, region=VERDANT, treasury=50):
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    world.turn = 10
    world.agent_movements = MovementState()
    world.livelihoods = LivelihoodsState()
    world.livelihoods.household_retail = HouseholdRetailState(enabled=True)
    owners = {101: 3000, 102: 1000} if owners is None else owners
    reg = RetailRegion(region=region, opened_turn=1, reason="capital", claims=dict(owners),
                       goods=[sum(owners.values())] + [0] * (len(RETAIL_GOODS) - 1))
    world.livelihoods.household_retail.regions = [reg]
    RS.set_reform_services_enabled(world, True, args=argparse.Namespace(reform_services_mode=mode))
    civ = _civ_of(world, region)
    world.civilizations[civ].treasury = treasury
    return world, civ


def _civ_of(world, region):
    name = world.regions[region].controller
    return next(i for i, c in enumerate(world.civilizations) if c.name == name)


def _relief(world, civ, *, institution=""):
    world.agent_movements.reforms.append(Reform(kind=RELIEF, civ=civ, enacted_turn=1, institution=institution))
    return len(world.agent_movements.reforms) - 1


def _provision(world, region, *, persons=10.0, rations=8.0, price=1000, free=(2.0, 2.0, 0.0),
               commons_sufficiency=0.7, overflow=0.0):
    """This turn's settled provisioning of a pilot region (what retail's
    after-tick settlement leaves in its turn book)."""
    state = world.livelihoods.household_retail
    book = HR._book(state, world, state.region(region))
    pool, given, left = free
    book.price_milli = price
    book.provisioning = {"price_milli": float(price), "persons": persons, "rations": rations,
                         "priced_out_persons": float(math.ceil(persons - rations)), "offer_short_persons": 0.0,
                         "free_rations": pool, "free_given": given, "free_unallocated": left}
    book.phase2 = {"commons_sufficiency": commons_sufficiency,
                   **{f"retail_owned_overflow_{g}": (overflow if g == "grain" else 0.0) for g in RETAIL_GOODS}}
    return book


def _sim(world, owners=(101, 102)):
    return FakeSim({aid: 1.0 for aid in owners})


def _phase10(world, sim):
    return RS.phase10(world, None, None, argparse.Namespace(_sim=sim))


def _deposit(world, civ, k, due=2):
    return RS.relief_upkeep(world, None, civ, k, due)


# --- registry and switch ------------------------------------------------------------

def test_switch_registry_cli_catalog_and_manifest():
    from chronicler import livelihoods as LV
    from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
    from chronicler.feature_catalog import REQUIREMENTS
    from chronicler.main import _build_parser
    assert LIVELIHOODS_SWITCHES.index("reform_services") == LIVELIHOODS_SWITCHES.index("household_retail") - 1
    assert LV.LIVELIHOODS_CHOICES["reform_services_mode"] == ("service", "cost_only")
    keys = LV.LIVELIHOODS_ARG_KEYS
    assert keys[keys.index("reform_services") + 1] == "reform_services_mode"
    assert {"reform_services", "reform_services_mode"} <= set(SIMULATION_ARG_KEYS)
    assert REQUIREMENTS["reform_services"] == (
        {"agents": ["hybrid"]}, {"feature": "household_retail"},
        {"choice": "household_retail_mode", "values": ["retail", "no_relief"]}, {"setting": "agent_movements"})
    default = _build_parser().parse_args([])
    assert default.reform_services is None and default.reform_services_mode is None
    assert "reform_services" not in simulation_config(default)         # feature-off manifests keep their bytes
    assert ReformServicesState().mode == "service"
    assert M.MONEY_BOOKS[-1] == "reform_services" and M.NATIVE_ALIASES["relief_purchase"] == "food_procurement"


def test_never_enabled_world_has_no_state_and_withholds_nothing():
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    assert RS._state(world) is None and not RS.withholds_relief_credit(world)
    assert RS.relief_upkeep(world, None, 0, 0, 3) == 0
    assert RS.institution_upkeep(world, None, 0, None, 3, 2.0) == 0


def _parse(*flags):
    from chronicler.main import _build_parser
    return _build_parser().parse_args(["--seed", "42", "--turns", "2", *flags])


@pytest.mark.parametrize("flags, message", [
    (("--agents", "demographics-only", "--reform-services"), "requires --agents hybrid"),
    (("--agents", "hybrid", "--reform-services"), "requires --agents hybrid, --household-retail"),
    (("--agents", "hybrid", "--food-allocation", "--household-retail", "--household-retail-mode", "free_exchange",
      "--reform-services"), "in mode retail or no_relief"),
    (("--agents", "hybrid", "--food-allocation", "--household-retail", "--no-agent-movements", "--reform-services"),
     "agent movements"),
])
def test_refused_without_its_prerequisites_at_startup(flags, message):
    from chronicler.livelihoods import configure_livelihoods
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    args = _parse(*flags)
    world.agent_movements = None if args.agent_movements is False else MovementState()
    with pytest.raises(ValueError, match=message):
        configure_livelihoods(world, args, agent_mode=args.agents)


def test_a_saved_switch_refuses_a_resume_without_retail_until_ended():
    from chronicler.livelihoods import configure_livelihoods
    world, _civ = _world()
    world.livelihoods.household_retail.enabled = False
    args = _parse("--agents", "hybrid")
    with pytest.raises(ValueError, match="pass --no-reform-services to end it"):
        configure_livelihoods(world, args, agent_mode="hybrid")


def test_pickle_drops_the_transient_turn_and_json_round_trips():
    world, civ = _world()
    k = _relief(world, civ)
    assert _deposit(world, civ, k) == 2
    state = RS._state(world)
    assert state._turn is not None
    back = pickle.loads(pickle.dumps(state))
    assert back._turn is None and back.funds == {civ: 2000}
    again = ReformServicesState.model_validate_json(state.model_dump_json())
    assert again.funds == {civ: 2000} and again.book.settled == state.book.settled


# --- the label: the native reform table -----------------------------------------------

def _table(world):
    from chronicler.agent_movements import reform_table
    return reform_table(world).to_pydict()


@pytest.mark.parametrize("mode", ["service", "cost_only"])
def test_the_reform_table_omits_relief_rows_and_keeps_the_other_reforms(mode):
    world, civ = _world(mode)
    _relief(world, civ)
    world.agent_movements.reforms.append(Reform(kind=HOME_RULE, civ=civ, enacted_turn=2, regions=[VERDANT]))
    world.agent_movements.reforms.append(Reform(kind=TOLERATION, civ=civ, enacted_turn=3, faith=255))
    table = _table(world)
    assert RELIEF not in table["creed"] and HOME_RULE in table["creed"] and TOLERATION in table["creed"]
    assert RS._state(world).counters["credit_rows_withheld"] == 1
    RS.set_reform_services_enabled(world, False)
    assert _table(world)["creed"].count(RELIEF) == 1          # off: the label is back


# --- payments into the fund -----------------------------------------------------------

def test_upkeep_goes_into_the_fund_up_to_its_cap_and_the_rest_is_left_to_sink():
    world, civ = _world(treasury=100)
    k = _relief(world, civ)
    regions = len(world.civilizations[civ].regions)
    due = math.ceil(0.75 * regions)
    cap = RS.FUND_CAP_TURNS * due
    held = [_deposit_turn(world, civ, k, due, t) for t in range(10, 10 + RS.FUND_CAP_TURNS + 1)]
    assert held == [due] * RS.FUND_CAP_TURNS + [0]           # the fifth turn is sunk by the caller
    state = RS._state(world)
    assert state.funds[civ] == cap * 1000
    assert world.civilizations[civ].treasury == 100 - cap      # the seam debited exactly what it held
    assert state.counters["upkeep_to_fund_units"] == cap and state.counters["sunk_units"] == due


def _deposit_turn(world, civ, k, due, turn):
    world.turn = turn
    RS._state(world)._turn = None
    return RS.relief_upkeep(world, None, civ, k, due)


def test_cost_only_sinks_the_upkeep_and_records_it():
    world, civ = _world("cost_only")
    k = _relief(world, civ)
    assert _deposit(world, civ, k, due=3) == 0
    state = RS._state(world)
    assert state.funds == {} and state.counters["sunk_units"] == 3
    assert state._turn.civs[civ].path == "upkeep" and state._turn.civs[civ].sunk_units == 3


def test_a_fund_payment_settles_once_per_turn_and_reform():
    world, civ = _world()
    k = _relief(world, civ)
    assert _deposit(world, civ, k) == 2
    # The same key again (a second call in one turn) is refused by the seam and held nowhere.
    assert _deposit(world, civ, k) == 0
    state = RS._state(world)
    assert state.funds[civ] == 2000 and state.log[-1].kind == "purchase_refused"


def test_the_institution_share_is_pro_rata_to_enforcement_cost():
    from types import SimpleNamespace
    world, civ = _world()
    k = _relief(world, civ, institution="commons_management")
    snap = SimpleNamespace(institutions=(
        SimpleNamespace(institution_type=SimpleNamespace(value="written_law"), enforcement_cost=2.0),
        SimpleNamespace(institution_type=SimpleNamespace(value="commons_management"), enforcement_cost=1.5)))
    # paid 7 of a demand of 3.5: commons management's share is floor(7 x 1.5 / 3.5) = 3.
    assert RS.institution_upkeep(world, None, civ, snap, 7, 3.5) == 3
    state = RS._state(world)
    assert state.funds[civ] == 3000 and state._turn.civs[civ].path == "institution"
    assert state.book.settled[-1] == (10, "relief_budget", 2 * k + 1)
    # A relief without the institution, or a payment without it, gives nothing.
    world.agent_movements.reforms[k].institution = ""
    world.turn, state._turn = 11, None
    assert RS.institution_upkeep(world, None, civ, snap, 7, 3.5) == 0
    world.agent_movements.reforms[k].institution = "commons_management"
    bare = SimpleNamespace(institutions=snap.institutions[:1])
    assert RS.institution_upkeep(world, None, civ, bare, 7, 2.0) == 0
    assert state.log[-1].kind == "institution_share_unknown"


def test_governance_funding_pays_the_same_treasury_with_the_switch():
    """The Phase 2 enforcement payment debits the treasury by the same total;
    service mode routes the relief institution's share into the fund."""
    from chronicler import governance_runtime as G
    from chronicler.governance_state import GovernanceInstitution

    def run(enabled):
        from chronicler.governance_state import CivGovernance
        world, civ = _world(treasury=40)
        world.turn = 20
        G.set_governance_enabled(world, True)
        civ_obj = world.civilizations[civ]
        civ_obj.governance = CivGovernance(institutions=[GovernanceInstitution(
            institution_type="commons_management", enacted_turn=5, legitimacy=1.0, enforcement_cost=1.5,
            opposing_faction="cultural")])
        _relief(world, civ, institution="commons_management")
        if not enabled:
            RS.set_reform_services_enabled(world, False)
        before = civ_obj.treasury
        G.fund_institutions_phase2(world, acc=None)
        return before - civ_obj.treasury, RS._state(world).funds.get(civ, 0)

    off_spent, off_fund = run(False)
    on_spent, on_fund = run(True)
    assert off_fund == 0 and on_fund > 0
    assert on_spent == off_spent             # the treasury pays the same; part of it is now the fund


# --- purchases, deliveries and refunds ------------------------------------------------

def test_a_purchase_buys_owners_surplus_for_recorded_need_and_pays_them_by_id():
    world, civ = _world()
    k = _relief(world, civ)
    _deposit(world, civ, k, due=2)                            # the fund holds 2 units
    _provision(world, VERDANT, persons=10.0, rations=8.5, price=800)
    stock = dict(world.regions[VERDANT].stockpile.goods)
    sim = _sim(world)
    _phase10(world, sim)
    state = RS._state(world)
    (p,) = state.frame.purchases
    rm = Fraction(HR._ration(world)) * 1000
    wanted = math.ceil(Fraction(1.5) * rm)
    assert p.food_milli == min(wanted, 4000, math.floor(Fraction(2000) * rm / 800))
    assert p.cost_milli == math.ceil(Fraction(p.food_milli) * 800 / rm)
    assert p.credited_milli == p.cost_milli and p.residual_milli == 0 and p.sellers == 2
    # Owners debited pro rata (3:1), paid by id pro rata to what they gave.
    reg = world.livelihoods.household_retail.region(VERDANT)
    assert sum(reg.claims.values()) == 4000 - p.food_milli
    paid = {aid: round((w - 1.0) * 1000) for aid, w in sim.wealth.items()}
    assert sum(paid.values()) == p.cost_milli and paid[101] >= 3 * paid[102] - 1
    # The food is in the commons now, and the fund paid exactly the bill.
    assert world.regions[VERDANT].stockpile.goods["grain"] == pytest.approx(
        stock.get("grain", 0.0) + p.food_milli / 1000)
    assert state.funds[civ] == 2000 - p.cost_milli
    assert sim.keys == [(10, M.NATIVE_PURPOSES.index("food_procurement"), RS.RELIEF_BATCH_BASE + VERDANT)]
    # Retail's turn book records the flow, so its frame closes.
    book = world.livelihoods.household_retail._turn.books[VERDANT]
    assert sum(book.goods["relief_bought"]) == p.food_milli
    HR.check_region(reg, book)
    HR.check_owner(reg, book)


def test_no_purchase_without_need_owned_food_or_money():
    world, civ = _world()
    k = _relief(world, civ)
    _provision(world, VERDANT, persons=10.0, rations=10.0)            # everyone fed: no need
    _phase10(world, _sim(world))
    state = RS._state(world)
    assert state.frame.purchases == [] and state.counters.get("need_without_fund", 0) == 0
    # Need, but an empty fund.
    world.turn, state._turn = 11, None
    world.livelihoods.household_retail._turn = None
    _provision(world, VERDANT, persons=10.0, rations=7.0)
    _phase10(world, _sim(world))
    assert state.frame.purchases == [] and state.counters["need_without_fund"] == 1
    # Need and money, but the owners hold nothing.
    world.turn, state._turn = 12, None
    world.livelihoods.household_retail._turn = None
    reg = world.livelihoods.household_retail.region(VERDANT)
    reg.claims, reg.goods = {}, [0] * len(RETAIL_GOODS)
    _deposit(world, civ, k)
    _provision(world, VERDANT, persons=10.0, rations=7.0)
    _phase10(world, _sim(world))
    assert state.frame.purchases == [] and state.counters["need_without_owned_food"] == 1


def test_a_realm_buys_only_in_its_own_regions_neediest_first():
    world, civ = _world(owners={101: 500, 102: 500})
    other = world.livelihoods.household_retail
    other.regions.append(RetailRegion(region=AMBER, opened_turn=1, reason="capital", claims={103: 2000},
                                      goods=[2000, 0, 0, 0, 0]))
    k = _relief(world, civ)
    _deposit(world, civ, k, due=3)
    _provision(world, VERDANT, persons=10.0, rations=9.0, price=500)
    _provision(world, AMBER, persons=10.0, rations=2.0, price=500)    # another realm's need
    _phase10(world, _sim(world, owners=(101, 102, 103)))
    assert [p.region for p in RS._state(world).frame.purchases] == [VERDANT]


def test_deliveries_are_bounded_by_the_next_free_pool():
    world, civ = _world()
    k = _relief(world, civ)
    _deposit(world, civ, k, due=2)
    _provision(world, VERDANT, persons=10.0, rations=8.0, price=500)
    _phase10(world, _sim(world))
    state = RS._state(world)
    (p,) = state.pending
    # Next turn: the commons fell short (all of it eaten), the pool gave all but 0.1 rations.
    world.turn, world.livelihoods.household_retail._turn = 11, None
    _provision(world, VERDANT, persons=10.0, rations=9.6, free=(3.0, 2.9, 0.1), commons_sufficiency=0.8)
    _phase10(world, _sim(world))
    (d,) = state.frame.deliveries
    rm = Fraction(HR._ration(world)) * 1000
    kept = float(Fraction(p.goods_milli[0]) * (1 - Fraction("0.03")) / rm)
    assert d.observed and d.bought_turn == 10
    assert d.delivered_at_most == pytest.approx(min(p.rations, 2.9))
    assert d.delivered_at_least == pytest.approx(max(0.0, min(kept, 3.0, d.delivered_at_most) - 0.1), abs=1e-6)
    # A commons that covered demand (some of it may have stayed in stock) gives no lower bound.
    world.turn, world.livelihoods.household_retail._turn = 12, None
    state.pending, state.pending_turn = [p], 11
    _provision(world, VERDANT, persons=10.0, rations=10.0, free=(3.0, 2.0, 1.0), commons_sufficiency=1.0)
    _phase10(world, _sim(world))
    (d,) = state.frame.deliveries
    assert d.delivered_at_least is None and d.delivered_at_most == pytest.approx(min(p.rations, 2.0))
    # A region with no provisioning the next turn: unobserved, not zero.
    world.turn, world.livelihoods.household_retail._turn = 13, None
    state.pending, state.pending_turn = [p], 12
    _phase10(world, _sim(world))
    (d,) = state.frame.deliveries
    assert not d.observed and d.delivered_at_most is None and state.counters["deliveries_unobserved"] == 1


def test_a_relief_that_ends_returns_its_fund_to_the_treasury():
    world, civ = _world(treasury=30)
    k = _relief(world, civ)
    _deposit(world, civ, k, due=2)
    assert world.civilizations[civ].treasury == 28      # the seam debited the deposit (direct, acc None)
    world.agent_movements.reforms[k].repeal = LAPSED
    world.livelihoods.household_retail._turn = None
    _phase10(world, _sim(world))
    state = RS._state(world)
    assert state.funds == {} and world.civilizations[civ].treasury == 30
    (row,) = state.frame.civs
    assert row.refunded_milli == 2000 and row.fund_close_milli == 0
    assert state.counters["refunded_to_treasury_milli"] == 2000


def test_switching_off_returns_the_funds_with_a_dated_record():
    world, civ = _world(treasury=30)
    k = _relief(world, civ)
    _deposit(world, civ, k, due=2)
    RS._state(world)._turn = None
    world.turn = 11
    RS.set_reform_services_enabled(world, False)
    state = RS._state(world)
    assert state.funds == {} and world.civilizations[civ].treasury == 30 and not state.enabled
    assert [r.kind for r in state.log][-2:] == ["fund_refunded", "switched_off"]


def test_committing_twice_in_one_turn_is_refused():
    world, civ = _world()
    _phase10(world, _sim(world))
    with pytest.raises(RuntimeError, match="twice"):
        _phase10(world, _sim(world))


# --- record ---------------------------------------------------------------------------

def test_snapshot_and_reader_states_are_distinct():
    world, civ = _world()
    k = _relief(world, civ)
    _deposit(world, civ, k, due=2)
    _provision(world, VERDANT, persons=10.0, rations=8.0)
    _phase10(world, _sim(world))
    world.turn += 1
    snap = {"livelihoods": {"schema_version": 1, "reform_services": RS.snapshot_summary(world)}}
    json.dumps(snap)
    status, frame = RS.record_status(snap)
    assert status == "recorded" and frame["purchases"] and frame["turn"] == 10
    assert RS.record_status({"livelihoods": {"schema_version": 1}})[0] == "absent"
    assert RS.record_status({"livelihoods": {"reform_services": {"schema_version": 2}}})[0] == "malformed"
    world.turn += 1                                           # a turn the package did not commit
    assert RS.record_status({"livelihoods": {"reform_services": RS.snapshot_summary(world)}})[0] == "unobserved"
    quiet, _ = _world()
    quiet.livelihoods.household_retail._turn = None
    _phase10(quiet, _sim(quiet))
    quiet.turn += 1
    assert RS.record_status({"livelihoods": {"reform_services": RS.snapshot_summary(quiet)}})[0] == "recorded_zero"


def test_counters_are_a_fixed_key_set():
    world, civ = _world()
    with pytest.raises(KeyError):
        RS._bump(RS._state(world), "not_a_counter")
    assert set(RS._state(world).counters) <= set(COUNTERS)


def test_rounding_residue_with_nobody_recorded_short_is_no_need():
    world, civ = _world()
    k = _relief(world, civ)
    _deposit(world, civ, k)
    book = _provision(world, VERDANT, persons=100.0, rations=99.996)
    book.provisioning["priced_out_persons"] = 0.0           # f32 sums, nobody short
    _phase10(world, _sim(world))
    assert RS._state(world).frame.purchases == []


def test_every_ledger_channel_a_reader_can_emit_has_its_lifetime_totals():
    """The A1 ledger commits each typed row into lifetime totals by channel name;
    a channel without them fails at commit (the all-enabled checkpoint case found
    it for ``relief_purchase``). Channels of packages excluded with the ledger
    are never emitted."""
    from chronicler.feature_catalog import REQUIREMENTS
    from chronicler.wealth_accounting_state import CHANNELS, LIFETIME
    excluded = {key for key, conditions in REQUIREMENTS.items()
                if {"not": {"feature": "wealth_accounting"}} in conditions}
    for name, package, _payer in CHANNELS:
        if package in excluded:
            continue
        assert {f"{name}_in_milli", f"{name}_out_milli"} <= set(LIFETIME), name
