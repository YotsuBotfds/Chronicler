"""A1 observation-only wealth ledger (``--wealth-accounting``): offline cases.

Constructed worlds: a generated template world with synthetic Phase 2 and
Phase 10 agent snapshots (Arrow batches of ``id``, ``region``, ``wealth``) and
stand-in package records holding exactly the fields the ledger reads. Real
packages on the compiled extension: ``tests/test_wealth_accounting_native.py``.
"""
from __future__ import annotations

import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import livelihoods as LV
from chronicler import wealth_accounting as WA
from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
from chronicler.feature_catalog import REQUIREMENTS
from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES
from chronicler.main import _build_parser
from chronicler.wealth_accounting_state import (
    CHANNEL_NAMES, COUNTERS, LIFETIME, MAX_LOG, WEALTH_WRITER_METHODS, WEALTH_WRITERS, WITHHELD_OTHER,
    WITHHELD_PACKAGES, WealthAccountingState,
)
from chronicler.world_gen import generate_world

N_REGIONS = 6


def parse(*argv):
    return _build_parser().parse_args(list(argv))


def _world():
    world = generate_world(seed=42, num_regions=N_REGIONS, num_civs=2)
    world.agent_mode = "hybrid"
    for civ in world.civilizations:
        civ.last_income = 0                      # the tithe base without an economy result
    LV.configure_livelihoods(world, parse("--wealth-accounting"), agent_mode="hybrid")
    return world


def _batch(people):
    """people: {id: (region, wealth)} -> a native-shaped snapshot (slot order shuffled)."""
    ids = sorted(people, key=lambda a: (a * 7919) % 101)
    return pa.record_batch([
        pa.array(ids, type=pa.uint32()),
        pa.array([people[a][0] for a in ids], type=pa.uint16()),
        pa.array([people[a][1] for a in ids], type=pa.float32()),
    ], names=["id", "region", "wealth"])


class _Bridge:
    def __init__(self, people):
        self._sim = SimpleNamespace(get_snapshot=lambda: _batch(people))


class _Packages:
    """Stand-in package records and counters behind ``_active``/``_counter``."""

    def __init__(self, monkeypatch):
        self.subs: dict[str, object] = {}
        self.counters: dict[tuple[str, str], float] = {}
        self.credit = None
        monkeypatch.setattr(WA, "_active", lambda world, name: self.subs.get(name))
        monkeypatch.setattr(WA, "_counter", lambda world, package, key: self.counters.get((package, key), 0))
        monkeypatch.setattr(WA, "_credit_state", lambda world: self.credit)


def _turn(world, opening, closing, *, between=None, economy=None, acc=None):
    """One observed turn: the Phase 2 opening, ``between`` (package activity),
    then the Phase 10 closing. Returns the committed frame."""
    WA.prepare_phase2(world, None, None, _batch(opening), acc)
    if between is not None:
        between()
    WA.phase10(world, acc, economy, _Bridge(closing))
    state = world.livelihoods.wealth_accounting
    world.turn += 1
    return state.frame


def _state(world) -> WealthAccountingState:
    return world.livelihoods.wealth_accounting


# --- registry, CLI, catalog, manifest ------------------------------------------

def test_switch_is_appended_last_with_cli_catalog_and_manifest_keys():
    assert LIVELIHOODS_SWITCHES[-1] == "wealth_accounting"
    assert LV.LIVELIHOODS_ARG_KEYS[-1] == "wealth_accounting"
    assert "wealth_accounting" not in LV.LIVELIHOODS_CHOICES            # no modes in slice 1
    assert REQUIREMENTS["wealth_accounting"] == ({"agents": ["hybrid"]},)
    assert "wealth_accounting" in SIMULATION_ARG_KEYS
    default = parse()
    assert default.wealth_accounting is None
    assert "wealth_accounting" not in simulation_config(default)       # feature-off manifests keep their bytes
    assert simulation_config(parse("--wealth-accounting"))["wealth_accounting"] is True
    assert simulation_config(parse("--no-wealth-accounting"))["wealth_accounting"] is False
    assert LV.livelihoods_arguments(parse("--wealth-accounting")) == ["--wealth-accounting"]
    assert LV.livelihoods_arguments(parse("--no-wealth-accounting")) == ["--no-wealth-accounting"]
    assert "observation-only" in LV._HELP["wealth_accounting"] and "hybrid" in LV._HELP["wealth_accounting"]
    for fn in ("set_wealth_accounting_enabled", "wealth_accounting_active", "snapshot_summary"):
        assert callable(getattr(WA, fn))
    # No agent-tick hook: the post-tick snapshot hand-over is unchanged.
    assert not hasattr(WA, "before_agent_tick") and not hasattr(WA, "after_agent_tick")


@pytest.mark.parametrize("mode", ["off", "shadow", "demographics-only"])
def test_refused_outside_hybrid_at_startup(mode):
    world = generate_world(seed=42, num_regions=N_REGIONS, num_civs=2)
    with pytest.raises(ValueError, match="--wealth-accounting requires --agents hybrid") as refused:
        LV.configure_livelihoods(world, parse("--wealth-accounting"), agent_mode=mode)
    assert "pass --no-wealth-accounting" not in str(refused.value)
    assert world.livelihoods is None


def test_never_enabled_world_has_no_container():
    world = generate_world(seed=42, num_regions=N_REGIONS, num_civs=2)
    before = world.model_dump_json()
    LV.configure_livelihoods(world, parse("--no-wealth-accounting"), agent_mode="hybrid")
    assert world.livelihoods is None and world.model_dump_json() == before


def test_a_saved_ledger_refuses_a_non_hybrid_resume_until_it_is_ended_with_a_dated_record():
    world = _world()
    people = {1: (0, 1.0), 2: (1, 2.0)}
    _turn(world, people, people)
    state = _state(world)
    assert state.closing is not None and state.frame is not None
    before = world.model_dump_json()
    for mode in ("off", "shadow"):
        with pytest.raises(ValueError, match="pass --no-wealth-accounting to end it"):
            LV.configure_livelihoods(world, parse(), agent_mode=mode)
        assert world.model_dump_json() == before                     # refused before any change
    world.turn = 7
    LV.configure_livelihoods(world, parse("--no-wealth-accounting"), agent_mode="off")
    world.agent_mode = "off"
    state = _state(world)
    assert not state.enabled and state.closing is None and state.frame is None and state.frame_turn is None
    assert not WA.wealth_accounting_active(world)
    off = state.log[-1]
    assert (off.turn, off.kind, off.detail) == (7, "switched_off", {"closing_turn": 0, "frame_turn": 0})
    assert state.counters["switched_off"] == 1 and state.lifetime            # history kept
    assert LV.livelihoods_snapshot_fields(world) == {}
    assert LV.livelihoods_feature_flags(world) == {"wealth_accounting": False}
    # Re-enabled in hybrid: dated, and the next opening is unchecked.
    world.agent_mode = "hybrid"
    LV.configure_livelihoods(world, parse("--wealth-accounting"), agent_mode="hybrid")
    assert _state(world).log[-1].kind == "switched_on" and WA.wealth_accounting_active(world)
    frame = _turn(world, people, people)
    assert frame["continuity"] == {"status": "unchecked", "reason": "first_turn", "previous_close_turn": None}


def test_changing_the_switch_inside_a_pending_turn_is_refused():
    world = _world()
    WA.prepare_phase2(world, None, None, _batch({1: (0, 1.0)}), None)
    with pytest.raises(RuntimeError, match="pending"):
        WA.set_wealth_accounting_enabled(world, False)
    WA.rollback_phase2(world)
    WA.set_wealth_accounting_enabled(world, False)


def test_pickle_drops_the_transient_turn_and_json_round_trips():
    world = _world()
    _turn(world, {1: (0, 1.0)}, {1: (0, 1.25)})
    WA.prepare_phase2(world, None, None, _batch({1: (0, 1.25)}), None)
    state = _state(world)
    assert state._turn is not None
    back = pickle.loads(pickle.dumps(state))
    assert back._turn is None and back.model_dump_json() == state.model_dump_json()
    again = WealthAccountingState.model_validate_json(state.model_dump_json())
    assert again.model_dump() == state.model_dump()


# --- identities ------------------------------------------------------------------

def test_region_and_world_identities_with_migration_births_deaths_and_typed_flows(monkeypatch):
    """Exactly representable balances: each region's residual is the model
    change assigned to it, migrants carry their closing balance, the typed
    flows are located where the package recorded them, and the world closes."""
    pk = _Packages(monkeypatch)
    world = _world()
    opening = {1: (0, 4.0), 2: (0, 2.0), 3: (1, 3.0), 4: (1, 1.0), 5: (2, 8.0)}
    # 1: an RS2 wage of 1.0 (region 0) and model income 0.25; 2: moves 0 -> 1
    # with model income 0.5 (carries 2.5); 3: dies, 4: inherits 3.0 (both
    # region 1); 5: pays a 0.75 L7 fare (region 2) and earns 0.25; 6: born in 2.
    closing = {1: (0, 5.25), 2: (1, 2.5), 4: (1, 4.0), 5: (2, 7.5), 6: (2, 0.5)}

    def payers():
        turn = world.turn
        pk.subs["repair_projects"] = SimpleNamespace(
            frame_turn=turn, receipts=[SimpleNamespace(region=0, wages_milli=1000, kind="workshop", crew=[1])],
            ledger=[SimpleNamespace(civ=0, charged=1, prepaid_before_milli=0, coin_cost_milli=0,
                                    wages_applied_milli=1000, prepaid_after_milli=0)])
        pk.subs["relocation_costs"] = SimpleNamespace(
            frame_turn=turn, last_assistance_turn=None, assistance=[],
            households=[SimpleNamespace(from_region=2, applied=True, reason="passed", paid=750)])
        for key, value in (("fare_debited_milli", 750), ("fare_due_milli", 750), ("travel_sink_milli", 750)):
            pk.counters[("relocation_costs", key)] = value

    frame = _turn(world, opening, closing, between=payers)
    w = frame["world"]
    assert (w["open"], w["close"], w["delta"]) == (18.0, 19.75, 1.75)
    assert (w["typed_in_milli"], w["typed_out_milli"], w["typed_net_milli"]) == (1000, 750, 250)
    assert w["native_model"] == pytest.approx(1.5, abs=1e-12)        # 0.25 + 0.5 + 0.25 + 0.5 born
    assert (w["births"], w["births_close"], w["deaths"], w["deaths_open"]) == (1, 0.5, 1, 3.0)
    assert (w["moved"], w["moved_close"], w["unlocated_in_milli"], w["unlocated_out_milli"]) == (1, 2.5, 0, 0)
    rows = {r["region"]: r for r in frame["regions"]}
    assert set(rows) == {0, 1, 2}
    r0, r1, r2 = rows[0], rows[1], rows[2]
    assert (r0["open"], r0["close"], r0["migration_out"], r0["typed_in_milli"]) == (6.0, 5.25, 2.5, 1000)
    assert r0["native_model"] == pytest.approx(0.75)                  # 1's 0.25 and the mover's 0.5
    assert (r1["migration_in"], r1["deaths"], r1["deaths_open"]) == (2.5, 1, 3.0)
    assert r1["native_model"] == pytest.approx(0.0)                   # the estate went to an heir
    assert (r2["births"], r2["births_close"], r2["typed_out_milli"]) == (1, 0.5, 750)
    assert r2["native_model"] == pytest.approx(0.75)                  # 0.25 earned + 0.5 endowment
    for r in frame["regions"]:
        change = r["close"] - r["open"]
        assert change == pytest.approx(r["migration_in"] - r["migration_out"]
                                       + (r["typed_in_milli"] - r["typed_out_milli"]) / 1000 + r["native_model"])
    assert sum(r["native_model"] for r in frame["regions"]) == pytest.approx(w["native_model"])
    assert sum(r["migration_in"] - r["migration_out"] for r in frame["regions"]) == 0.0
    assert all(c["closes"] for c in frame["closures"]) and frame["typed_complete"]
    state = _state(world)
    assert state.lifetime["repair_wage_in_milli"] == 1000 and state.lifetime["relocation_fare_out_milli"] == 750
    assert state.lifetime["native_model"] == pytest.approx(1.5)


def test_unlocated_flows_stay_in_the_world_identity_and_out_of_the_regions(monkeypatch):
    pk = _Packages(monkeypatch)
    world = _world()
    opening = {1: (0, 1.0), 2: (1, 1.0)}
    closing = {1: (0, 3.0), 2: (1, 1.0)}

    def procure():
        pk.subs["household_retail"] = SimpleNamespace(
            frame_turn=world.turn, frame=[], income={"replaced": 0.5},
            money={"procurement_owed_milli": 2000, "procurement_credited_milli": 2000,
                   "procurement_residual_milli": 0, "procurement_unpaid_milli": 0})

    frame = _turn(world, opening, closing, between=procure)
    w = frame["world"]
    assert (w["typed_in_milli"], w["unlocated_in_milli"], w["native_model"]) == (2000, 2000, 0.0)
    rows = {r["region"]: r for r in frame["regions"]}
    assert rows[0]["typed_in_milli"] == 0 and rows[0]["native_model"] == 2.0
    assert sum(r["native_model"] for r in frame["regions"]) == w["native_model"] + w["unlocated_in_milli"] / 1000
    procurement = next(r for r in frame["typed"] if r["channel"] == "food_procurement")
    assert (procurement["in_milli"], procurement["unlocated_in_milli"]) == (2000, 2000)
    assert frame["treasury"]["to_households_milli"]["food_procurement"] == 2000


# --- continuity (the no-hidden-writer check) -------------------------------------

def test_an_unchanged_pool_between_turns_is_exact_and_an_injected_transfer_is_detected():
    world = _world()
    a = {1: (0, 1.5), 2: (1, 2.25), 3: (3, 0.5)}
    b = {1: (0, 1.75), 2: (1, 2.0), 3: (3, 0.5), 4: (3, 0.5)}
    first = _turn(world, a, b)
    assert first["continuity"]["status"] == "unchecked" and first["continuity"]["reason"] == "first_turn"
    second = _turn(world, b, b)
    assert second["continuity"] == {"status": "exact", "reason": None, "previous_close_turn": 0}
    # A hidden writer between this Phase 10 and the next Phase 2: 5.0 to id 2.
    injected = {**b, 2: (1, 7.0)}
    third = _turn(world, injected, injected)
    c = third["continuity"]
    assert c["status"] == "broken" and c["wealth_changed"] and not c["region_changed"]
    assert (c["difference"], c["agents_difference"], c["regions"]) == (5.0, 0, [[1, 5.0, 0]])
    state = _state(world)
    assert state.counters["continuity_broken"] == 1 and state.lifetime["discontinuity"] == 5.0
    assert state.log[-1].kind == "continuity_broken" and state.log[-1].turn == 2
    # A region rewritten outside the tick is a break too, with the same total.
    moved = {**injected, 3: (2, 0.5)}
    fourth = _turn(world, moved, moved)
    c = fourth["continuity"]
    assert c["status"] == "broken" and c["region_changed"] and not c["wealth_changed"] and c["difference"] == 0.0
    assert c["regions"] == [[2, 0.5, 1], [3, -0.5, -1]]
    # A spawn outside the tick changes the agent count.
    extra = {**moved, 9: (0, 0.0)}
    assert _turn(world, extra, extra)["continuity"]["agents_difference"] == 1


def test_a_pool_reset_drops_the_closing_with_a_dated_record_and_a_gap_is_unchecked():
    world = _world()
    people = {1: (0, 1.0)}
    WA.on_pool_reset(world)                                           # fresh run: nothing to drop
    assert _state(world).log[-1].kind == "switched_on" and "pool_resets" not in _state(world).counters
    _turn(world, people, people)
    WA.on_pool_reset(world)
    state = _state(world)
    assert state.closing is None and state.counters["pool_resets"] == 1
    reset = state.log[-1]
    assert (reset.turn, reset.kind, reset.detail["closing_turn"], reset.detail["closing_agents"]) == (
        1, "pool_reset", 0, 1)
    frame = _turn(world, people, people)
    assert frame["continuity"]["status"] == "unchecked" and frame["continuity"]["reason"] == "pool_reset"
    world.turn += 3                                                   # turns the ledger did not observe
    gap = _turn(world, people, people)["continuity"]
    assert (gap["status"], gap["reason"], gap["previous_close_turn"]) == ("unchecked", "gap", 1)


def test_a_turn_without_an_opening_is_unobserved_not_zero():
    world = _world()
    WA.phase10(world, None, None, _Bridge({1: (0, 1.0)}))            # no Phase 2 this turn
    state = _state(world)
    assert state.frame is None and state.frame_turn == 0 and state.closing is not None
    assert state.counters["turns_unobserved"] == 1 and state.log[-1].kind == "unobserved"
    world.turn += 1
    record = WA.snapshot_summary(world)
    assert record["source_turn"] == 0 and record["frame"] is None
    assert WA.record_status({"livelihoods": {"wealth_accounting": record}}) == ("unobserved", None)


# --- typed flows and closures per purpose ----------------------------------------

def _every_payer(pk, turn, *, crew_mode="paid"):
    """Stand-in committed records of every paying package for one turn."""
    paid = crew_mode == "paid"
    pk.subs["workshop_payroll"] = SimpleNamespace(frame_turn=turn, frame=[
        SimpleNamespace(region=3, wages_paid=600, stipends=150, cash_open=2000, sales=1000, distributed=1000,
                        written_off=0, cash_close=1250, controller=1, operating=True, crew=[30, 31])])
    pk.subs["apprenticeship"] = SimpleNamespace(frame_turn=turn, frame=[SimpleNamespace(seats=[
        SimpleNamespace(agent_id=32, mentor=30, aboard=None), SimpleNamespace(agent_id=33, mentor=None, aboard=None),
        SimpleNamespace(agent_id=31, mentor=30, aboard="crew")])])
    pk.subs["repair_projects"] = SimpleNamespace(frame_turn=turn, receipts=[
        SimpleNamespace(region=0, wages_milli=400, kind="workshop", crew=[40, 41]),
        SimpleNamespace(region=1, wages_milli=0, kind="granary", crew=[])], ledger=[
        SimpleNamespace(civ=0, charged=3, prepaid_before_milli=200, coin_cost_milli=2000, wages_applied_milli=400,
                        prepaid_after_milli=800)])
    pk.subs["recovery_crews"] = SimpleNamespace(frame_turn=turn, mode=crew_mode, receipts=[
        SimpleNamespace(kind="granary", region=1, wages_milli=2000 if paid else 0,
                        members=[SimpleNamespace(agent_id=50, worked=0.5), SimpleNamespace(agent_id=51, worked=0.0)]),
        SimpleNamespace(kind="workshop", region=0, wages_milli=0,
                        members=[SimpleNamespace(agent_id=40, worked=0.2), SimpleNamespace(agent_id=41, worked=0.2)])],
        ledger=[SimpleNamespace(civ=0, wages_milli=2000 if paid else 0, wage_residual_milli=0,
                                sunk_milli=0 if paid else 2000, coin_cost_milli=2000,
                                wages_due_milli=2000 if paid else 0)])
    pk.subs["timber_supply"] = SimpleNamespace(frame_turn=turn, receipts=[
        SimpleNamespace(home=4, wages_milli=1000, crew=[60, 61])], ledger=[
        SimpleNamespace(civ=1, charged=1, prepaid_before_milli=0, wages_applied_milli=1000, prepaid_after_milli=0)])
    pk.subs["household_retail"] = SimpleNamespace(
        frame_turn=turn, income={"replaced": 1.25},
        money={"paid_milli": 1300, "credited_milli": 1200, "refunded_milli": 100,
               "procurement_owed_milli": 700, "procurement_credited_milli": 600,
               "procurement_residual_milli": 100, "procurement_unpaid_milli": 0},
        frame=[SimpleNamespace(region=2, provisioning={"paid_milli": 1300.0, "credited_milli": 1200.0,
                                                       "refunded_milli": 100.0})])
    pk.subs["remittances"] = SimpleNamespace(frame_turn=turn, totals={
        "credited_milli": 85, "debited_milli": 100, "fee_milli": 15, "sent_milli": 110, "refunded_milli": 10},
        regions=[SimpleNamespace(region=5, inflow_milli=0, outflow_milli=100),
                 SimpleNamespace(region=2, inflow_milli=85, outflow_milli=0)])
    pk.subs["relocation_costs"] = SimpleNamespace(
        frame_turn=turn, last_assistance_turn=turn,
        assistance=[SimpleNamespace(status="charged", charged_coins=1, civ=1)],
        households=[SimpleNamespace(from_region=5, applied=True, reason="assisted", paid=300),
                    SimpleNamespace(from_region=4, applied=False, reason="short", paid=0)])
    for key, value in (("fare_debited_milli", 500), ("fare_residual_milli", 100), ("fare_due_milli", 1400),
                       ("assistance_granted_milli", 800), ("fare_not_charged_milli", 0),
                       ("travel_sink_milli", 1500)):
        pk.counters[("relocation_costs", key)] = pk.counters.get(("relocation_costs", key), 0) + value
    pk.credit = SimpleNamespace(merchant_sent=pk.credit.merchant_sent + 3.0 if pk.credit else 3.0,
                                merchant_applied=pk.credit.merchant_applied + 2.5 if pk.credit else 2.5)


def test_typed_flows_and_their_closures_per_purpose(monkeypatch):
    pk = _Packages(monkeypatch)
    world = _world()
    pk.credit = SimpleNamespace(merchant_sent=0.0, merchant_applied=0.0)
    people = {i: (i % N_REGIONS, 1.0) for i in range(30, 62)}
    frame = _turn(world, people, people, between=lambda: _every_payer(pk, world.turn))
    typed = {r["channel"]: r for r in frame["typed"]}
    assert list(typed) == [c for c in CHANNEL_NAMES if c in typed]   # declaration order
    expected = {"workshop_wage": (600, 0), "apprentice_stipend": (150, 0), "repair_wage": (400, 0),
                "granary_crew_wage": (2000, 0), "woodcut_wage": (1000, 0), "food_procurement": (600, 0),
                "food_purchase": (1200, 1200), "remittance": (85, 100), "relocation_fare": (0, 500),
                "domestic_credit": (2500.0, 0.0)}
    assert {k: (r["in_milli"], r["out_milli"]) for k, r in typed.items()} == expected
    unlocated = {k: (r["unlocated_in_milli"], r["unlocated_out_milli"]) for k, r in typed.items()
                 if r["unlocated_in_milli"] or r["unlocated_out_milli"]}
    assert unlocated == {"food_procurement": (600, 0), "relocation_fare": (0, 200),
                         "domestic_credit": (2500.0, 0.0)}
    checks = {(c["channel"], c["check"]): c for c in frame["closures"]}
    assert all(c["closes"] for c in checks.values()), [c for c in checks.values() if not c["closes"]]
    assert {c for c, _ in checks} == {"workshop_wage", "repair_wage", "granary_crew_wage", "woodcut_wage",
                                      "food_purchase", "food_procurement", "remittance", "relocation_fare"}
    tr = frame["treasury"]
    assert tr["to_households_milli"] == {"repair_wage": 400, "granary_crew_wage": 2000, "woodcut_wage": 1000,
                                         "food_procurement": 600}
    assert tr["firm_cash"] == {"sales_from_treasury_milli": 1000, "wages_milli": 600, "stipends_milli": 150,
                               "distributions_to_treasury_milli": 1000, "written_off_milli": 0}
    assert tr["charged"] == {"repair_projects": 3, "timber_supply": 1, "relocation_assistance": 1}
    assert tr["sinks_milli"] == {"repair_coins": 0, "granary_wage_residual": 0, "remittance_fee": 15,
                                 "relocation_fare": 500, "relocation_assistance": 1000, "procurement_residual": 100}
    assert tr["created"] == {"treasury_tax": 0}
    assert tr["tithe"] == {"potential": 0, "at_threshold_after_tick": 0, "approximate": True, "collected": None}
    civ = {row["civ"]: row for row in tr["by_civ"]}
    assert civ[0] == {"civ": 0, "charged": 3, "to_households_milli": 2400}
    assert civ[1] == {"civ": 1, "charged": 2, "firm_distributions_milli": 1000, "firm_sales_milli": 1000,
                      "to_households_milli": 1000}
    w = frame["world"]
    assert w["typed_in_milli"] == pytest.approx(600 + 150 + 400 + 2000 + 1000 + 600 + 1200 + 85 + 2500)
    assert w["typed_out_milli"] == pytest.approx(1200 + 100 + 500)
    assert w["native_model"] == pytest.approx(-w["typed_net_milli"] / 1000)   # balances unchanged


def test_unpaid_granary_crews_sink_the_coins_and_a_broken_book_is_flagged(monkeypatch):
    pk = _Packages(monkeypatch)
    world = _world()
    people = {i: (0, 1.0) for i in range(30, 62)}
    frame = _turn(world, people, people, between=lambda: _every_payer(pk, world.turn, crew_mode="unpaid"))
    crew = next(r for r in frame["typed"] if r["channel"] == "granary_crew_wage")
    assert crew["in_milli"] == 0
    assert frame["treasury"]["sinks_milli"]["repair_coins"] == 2000       # RS2's coins leave the economy
    assert all(c["closes"] for c in frame["closures"])
    assert any(c["check"] == "granary coins = wages + sunk (unpaid)" for c in frame["closures"])

    def broken():
        _every_payer(pk, world.turn)
        pk.subs["repair_projects"].ledger[0].prepaid_after_milli = 799     # one milli missing
    frame = _turn(world, people, people, between=broken)
    failed = [c for c in frame["closures"] if not c["closes"]]
    assert [(c["channel"], c["lhs"], c["rhs"]) for c in failed] == [("repair_wage", 3200, 3199)]
    assert _state(world).counters["closures_failed"] == 1


def test_located_flows_beyond_a_packages_total_fail_a_closure_and_the_frame_is_still_observed(monkeypatch):
    """Re-check N3: a package whose per-region rows exceed its own total leaves
    a negative unlocated flow and a failed closure; readers must show the
    failure on an observed frame, not reject the record."""
    pk = _Packages(monkeypatch)
    world = _world()
    people = {1: (0, 1.0), 2: (2, 1.0)}

    def inconsistent():
        pk.subs["remittances"] = SimpleNamespace(frame_turn=world.turn, totals={
            "credited_milli": 85, "debited_milli": 100, "fee_milli": 15, "sent_milli": 100, "refunded_milli": 0},
            regions=[SimpleNamespace(region=2, inflow_milli=200, outflow_milli=0),
                     SimpleNamespace(region=0, inflow_milli=0, outflow_milli=100)])
    frame = _turn(world, people, people, between=inconsistent)
    row = next(r for r in frame["typed"] if r["channel"] == "remittance")
    assert (row["in_milli"], row["unlocated_in_milli"]) == (85, -115)
    failed = [c for c in frame["closures"] if not c["closes"]]
    assert [(c["channel"], c["check"]) for c in failed] == [
        ("remittance", "located flows do not exceed the package's total")]
    assert _state(world).counters["closures_failed"] == 1
    record = WA.snapshot_summary(world)
    status, observed = WA.record_status({"livelihoods": {"wealth_accounting": record}})
    assert status == "observed" and observed["world"]["unlocated_in_milli"] == -115


def test_a_package_without_this_turns_frame_is_unobserved_and_the_turn_incomplete(monkeypatch):
    pk = _Packages(monkeypatch)
    world = _world()
    people = {1: (0, 1.0)}

    def stale():
        pk.subs["repair_projects"] = SimpleNamespace(frame_turn=world.turn - 1, receipts=[], ledger=[])
    frame = _turn(world, people, people, between=stale)
    row = next(r for r in frame["typed"] if r["channel"] == "repair_wage")
    assert row["observed"] is False and (row["in_milli"], row["out_milli"]) == (0, 0)
    assert frame["typed_complete"] is False and _state(world).counters["typed_incomplete_turns"] == 1


# --- withheld paid work and RL7 ---------------------------------------------------

def test_every_paid_work_row_is_attributed_once_and_pl3_splits_granary_from_workshop(monkeypatch):
    pk = _Packages(monkeypatch)
    world = _world()
    people = {i: (0, 1.0) for i in range(30, 62)}
    rows = {30: (0.4, 0.5, 0.2), 31: (0.4, 0.5, 0.2), 32: (0.25, 0.4, 0.1), 40: (0.2, 0.5, 0.1),
            41: (0.2, 0.25, 0.05), 50: (0.5, 0.5, 0.25), 60: (1.0, 0.3, 0.3), 61: (1.0, 0.2, 0.2)}

    def install():
        _every_payer(pk, world.turn)
        world.livelihoods._paid_receipt = (world.turn, dict(rows))
        for key, value in ((("workshop_payroll", "income_replaced"), 0.4),
                           (("apprenticeship", "income_forgone"), 0.1),
                           (("repair_projects", "income_replaced"), 0.15),
                           (("recovery_crews", "income_replaced"), 0.4),
                           (("timber_supply", "income_withheld"), 0.5)):
            pk.counters[key] = pk.counters.get(key, 0) + value
    frame = _turn(world, people, people, between=install)
    wh = frame["withheld"]
    by = {r["package"]: r for r in wh["packages"]}
    assert [r["package"] for r in wh["packages"]] == list(WITHHELD_PACKAGES)
    assert {k: r["rows"] for k, r in by.items()} == {
        "workshop_payroll": 2, "apprenticeship": 1, "recovery_crews_granary": 1, "recovery_crews_workshop": 2,
        "repair_projects": 0, "timber_supply": 2}
    assert by["workshop_payroll"]["deducted"] == pytest.approx(0.4)
    assert by["recovery_crews_workshop"]["deducted"] == pytest.approx(0.15)
    assert all(r["matches"] in (True, None) for r in wh["packages"])
    assert by["repair_projects"]["matches"] is True                  # RS2's counter covers PL3's workshop crews
    assert (wh["rows"], wh["unattributed_rows"], wh["conflicts"]) == (8, 0, 0)
    assert wh["paid_work_active"] and wh["retail_active"] and wh["unattributed_pl3_dropped_rows"] == 0
    assert wh["deducted"] == pytest.approx(sum(v[2] for v in rows.values()))
    split = wh["recovery_crews"]
    assert split["granary"] == pytest.approx(0.25) and split["workshop"] == pytest.approx(0.15)
    assert split["total"] == pytest.approx(0.4) and split["closes"] and split["rows_dropped"] == 0
    assert wh["retail_income_replaced"] == 1.25
    state = _state(world)
    assert state.counters["withheld_rows"] == 8 and "unattributed_rows" not in state.counters
    assert state.lifetime["withheld_recovery_crews_granary"] == pytest.approx(0.25)


def test_an_unknown_row_and_a_doubly_named_person_are_counted_and_logged(monkeypatch):
    pk = _Packages(monkeypatch)
    world = _world()
    people = {i: (0, 1.0) for i in range(30, 100)}

    def install():
        _every_payer(pk, world.turn)
        pk.subs["timber_supply"].receipts[0].crew.append(30)           # also on the L6a crew
        world.livelihoods._paid_receipt = (world.turn, {30: (0.4, 0.5, 0.2), 99: (0.5, 0.2, 0.1)})
    frame = _turn(world, people, people, between=install)
    wh = frame["withheld"]
    assert (wh["unattributed_rows"], wh["unattributed_deducted"], wh["conflicts"]) == (1, 0.1, 1)
    assert next(r for r in wh["packages"] if r["package"] == "workshop_payroll")["rows"] == 1
    state = _state(world)
    assert state.counters["unattributed_rows"] == 1 and state.counters["attribution_conflicts"] == 1
    assert state.log[-1].kind == "attribution"
    assert state.log[-1].detail == {"unattributed": 1, "pl3_dropped": 0, "conflicts": 1}


def test_no_paid_work_package_is_not_a_recorded_zero():
    world = _world()
    frame = _turn(world, {1: (0, 1.0)}, {1: (0, 1.0)})
    assert frame["withheld"] is None and frame["typed"] == [] and frame["closures"] == []


def test_retail_replaced_income_is_shown_without_a_paid_work_package(monkeypatch):
    """Review m4: L6b's replaced farm income is withheld income too; with no
    paid-work package the paid-work fields are unknown (None), not zero."""
    pk = _Packages(monkeypatch)
    world = _world()

    def retail(replaced):
        def install():
            pk.subs["household_retail"] = SimpleNamespace(frame_turn=world.turn, frame=[], money={},
                                                          income={"replaced": replaced} if replaced else {})
        return install
    wh = _turn(world, {1: (0, 1.0)}, {1: (0, 1.0)}, between=retail(0.75))["withheld"]
    assert wh["paid_work_active"] is False and wh["retail_active"] is True
    assert wh["retail_income_replaced"] == 0.75
    assert all(wh[k] is None for k in ("rows", "deducted", "packages", "unattributed_rows", "conflicts",
                                       "recovery_crews", "unattributed_pl3_dropped_rows", "unattributed_deducted"))
    assert _state(world).lifetime["withheld_retail"] == 0.75 and "withheld_rows" not in _state(world).counters
    wh = _turn(world, {1: (0, 1.0)}, {1: (0, 1.0)}, between=retail(None))["withheld"]
    assert wh["retail_active"] is True and wh["retail_income_replaced"] is None     # not observed: unknown


def test_a_workshop_crew_of_a_dropped_pl3_receipt_is_unattributed_not_credited_to_rs2(monkeypatch):
    """Review m3: while PL3 is active every RS2 workshop crew is a PL3 workshop
    crew; a member only RS2 names was on a receipt PL3's 64-row cap dropped."""
    pk = _Packages(monkeypatch)
    world = _world()
    people = {i: (0, 1.0) for i in range(30, 62)}

    def install():
        _every_payer(pk, world.turn)
        pk.subs["recovery_crews"].receipts = [r for r in pk.subs["recovery_crews"].receipts if r.kind == "granary"]
        pk.counters[("recovery_crews", "rows_dropped")] = pk.counters.get(("recovery_crews", "rows_dropped"), 0) + 1
        pk.counters[("recovery_crews", "income_replaced")] = pk.counters.get(("recovery_crews", "income_replaced"), 0) + 0.4
        pk.counters[("repair_projects", "income_replaced")] = pk.counters.get(("repair_projects", "income_replaced"), 0) + 0.15
        world.livelihoods._paid_receipt = (world.turn, {40: (0.2, 0.5, 0.1), 41: (0.2, 0.25, 0.05),
                                                        50: (0.5, 0.5, 0.25)})
    wh = _turn(world, people, people, between=install)["withheld"]
    by = {r["package"]: r for r in wh["packages"]}
    assert by["repair_projects"]["rows"] == 0 and by["recovery_crews_workshop"]["rows"] == 0
    assert (wh["unattributed_rows"], wh["unattributed_pl3_dropped_rows"], wh["conflicts"]) == (2, 2, 0)
    assert wh["unattributed_deducted"] == pytest.approx(0.15)
    assert by["repair_projects"]["matches"] is False                  # RS2's own counter saw them
    split = wh["recovery_crews"]
    assert split["rows_dropped"] == 1 and not split["closes"] and split["granary"] == pytest.approx(0.25)
    state = _state(world)
    assert state.counters["unattributed_pl3_dropped_rows"] == 2
    assert state.log[-1].kind == "attribution" and state.log[-1].detail["pl3_dropped"] == 2


def test_domestic_credit_is_recorded_in_whole_milli_units(monkeypatch):
    pk = _Packages(monkeypatch)
    world = _world()
    people = {1: (0, 1.0)}
    pk.credit = SimpleNamespace(merchant_sent=0.0, merchant_applied=10.0)

    def lend(amount):
        def step():
            pk.credit = SimpleNamespace(merchant_sent=0.0, merchant_applied=pk.credit.merchant_applied + amount)
        return step
    for amount, expected in ((2.5004, (2500, 0)), (-0.0123456, (0, 12)), (0.0004, (0, 0))):
        frame = _turn(world, people, people, between=lend(amount))
        row = next(r for r in frame["typed"] if r["channel"] == "domestic_credit")
        assert (row["in_milli"], row["out_milli"]) == expected
        assert all(isinstance(row[k], int) for k in ("in_milli", "out_milli", "unlocated_in_milli"))
    life = _state(world).lifetime
    assert (life["domestic_credit_in_milli"], life["domestic_credit_out_milli"]) == (2500, 12)


# --- treasury side -------------------------------------------------------------

def test_the_treasury_tax_is_reproduced_and_the_tithe_is_a_potential_not_created_money():
    from chronicler.models import FactionType
    world = _world()
    world._treasury_tax_carry = {0: 0.75, 1: 0.5}
    world.civilizations[0].last_income = 30           # not in the economy's tithe base: the fallback
    world.civilizations[1].last_income = 50
    economy = SimpleNamespace(treasury_tax={0: 1.5, 1: 0.25, 9: 4.0}, tithe_base={})

    def taxed():
        world._treasury_tax_carry = {0: 0.25, 1: 0.75}  # what the economy's tax step leaves
        world.civilizations[0].factions.influence[FactionType.CLERGY] = 0.2    # at the threshold
        world.civilizations[1].factions.influence[FactionType.CLERGY] = 0.1    # below it
    frame = _turn(world, {1: (0, 1.0)}, {1: (0, 1.0)}, between=taxed, economy=economy, acc=object())
    tr = frame["treasury"]
    assert tr["created"] == {"treasury_tax": 2}                     # the tithe is not in "created"
    assert tr["tithe"] == {"potential": 8, "at_threshold_after_tick": 3, "approximate": True, "collected": None}
    civ = {r["civ"]: r for r in tr["by_civ"]}
    assert civ[0] == {"civ": 0, "tithe_at_threshold_after_tick": 3, "tithe_potential": 3, "treasury_tax": 2}
    assert civ[1] == {"civ": 1, "tithe_potential": 5}
    state = _state(world)
    assert state.lifetime["treasury_tax_created"] == 2 and state.lifetime["tithe_potential"] == 8
    assert state.lifetime["tithe_at_threshold_after_tick"] == 3 and "tithe_offered" not in LIFETIME
    assert "NOT created money" in WA.LABELS["tithe"]


# --- the record and its readers ---------------------------------------------------

def test_record_shape_and_reader_states_are_distinct():
    world = _world()
    _turn(world, {1: (0, 1.0)}, {1: (0, 1.0)})
    record = WA.snapshot_summary(world)
    assert record["schema_version"] == 1 and record["stage"] == "A1" and record["source_turn"] == 0
    assert set(record) == {"schema_version", "stage", "source_turn", "units", "frame", "lifetime", "counters", "log",
                           "log_dropped", "labels", "parameters"}
    assert set(record["frame"]) == set(WA.FRAME_KEYS)
    assert set(record["lifetime"]) <= set(LIFETIME) and set(record["counters"]) <= set(COUNTERS)
    assert "native model flows" in record["labels"]["native_model"]
    observed = {"livelihoods": {"wealth_accounting": record}}
    status, frame = WA.record_status(observed)
    assert status == "observed" and frame["world"]["typed_in_milli"] == 0       # a recorded zero
    assert WA.record_status({}) == ("absent", None)
    assert WA.record_status({"livelihoods": {"schema_version": 1}}) == ("absent", None)
    assert WA.record_status(None) == ("absent", None)
    unobserved = {"livelihoods": {"wealth_accounting": {**record, "frame": None}}}
    assert WA.record_status(unobserved) == ("unobserved", None)
    for broken in (None, [], {**record, "stage": "PL4"}, {**record, "schema_version": 2},
                   {**record, "source_turn": "0"}, {**record, "source_turn": True},
                   {k: v for k, v in record.items() if k != "frame"},
                   {**record, "frame": {**record["frame"], "turn": 5}},
                   {**record, "frame": {k: v for k, v in record["frame"].items() if k != "world"}},
                   {**record, "frame": []}):
        assert WA.record_status({"livelihoods": {"wealth_accounting": broken}}) == ("malformed", None)


def test_the_log_is_bounded_and_counts_what_it_dropped():
    world = _world()
    state = _state(world)
    for i in range(MAX_LOG + 5):
        WA._log(state, i, "unobserved")
    assert len(state.log) == MAX_LOG and state.log_dropped == 6 and state.log[0].turn == 5
    with pytest.raises(KeyError):
        WA._bump(state, "undeclared")
    with pytest.raises(KeyError):
        WA._total(state, "undeclared", 1)


# --- the payer registry (review m1, re-check N1/N2) --------------------------------

def scan_wealth_writers(root):
    """Every payer path and every other reference to a writer or router name
    under ``root`` (a ``chronicler`` package tree). Returns ``(paths,
    references, problems)``: ``paths`` counts ``(module, function, name,
    identifying args)`` call sites; ``references`` counts non-call uses of a
    name (attributes, bare names, string constants other than docstrings);
    ``problems`` are calls missing an identifying argument and writer calls
    that take their purpose or batch from a parameter of a non-router."""
    import ast
    from collections import Counter
    from pathlib import Path
    from chronicler.wealth_accounting_state import WEALTH_PATH_ARGS, WEALTH_ROUTERS
    names = set(WEALTH_WRITER_METHODS) | set(WEALTH_ROUTERS)
    paths, references, problems = Counter(), Counter(), []
    for path in sorted(Path(root).rglob("*.py")):
        module = ".".join(path.relative_to(root).with_suffix("").parts)
        if module in ("wealth_accounting", "wealth_accounting_state"):     # the registry itself
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        called: set[int] = set()

        def visit(node, scope, params):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = node.name if scope == "<module>" else f"{scope}.{node.name}"
                if not isinstance(node, ast.ClassDef):
                    a = node.args
                    params = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
                for child in ast.iter_child_nodes(node):
                    visit(child, inner, params)
                return
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
                if name in names and (isinstance(f, ast.Attribute) or name in WEALTH_ROUTERS):
                    called.add(id(f))
                    parts = []
                    for pos, kw in WEALTH_PATH_ARGS.get(name, ()):
                        arg = node.args[pos] if pos is not None and len(node.args) > pos else next(
                            (k.value for k in node.keywords if k.arg == kw), None)
                        if arg is None:
                            problems.append(f"{module}:{node.lineno}: {name} without its {kw} argument")
                            continue
                        parts.append(f"{kw}={ast.unparse(arg)}")
                        if isinstance(arg, ast.Name) and arg.id in params and scope.split(".")[-1] not in WEALTH_ROUTERS:
                            problems.append(f"{module}:{node.lineno}: {name} takes its {kw} from a parameter of "
                                            f"{scope}, which is not a declared router (WEALTH_ROUTERS)")
                    paths[(module, scope, name, ",".join(parts))] += 1
            if isinstance(node, ast.Attribute) and node.attr in names and id(node) not in called:
                references[(module, scope, node.attr)] += 1
            if isinstance(node, ast.Name) and node.id in names and id(node) not in called:
                references[(module, scope, node.id)] += 1
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in names \
                    and id(node) not in docs:
                references[(module, scope, node.value)] += 1
            for child in ast.iter_child_nodes(node):
                visit(child, scope, params)

        visit(tree, "<module>", set())
    return paths, references, problems


def _source_root():
    from pathlib import Path
    return Path(WA.__file__).resolve().parent


def test_every_payer_path_is_registered_with_its_call_sites_and_a_ledger_channel():
    """A payer added without a ledger channel would vanish into the native-model
    residual while ``typed_complete`` stayed true. Every payer path - module,
    enclosing function, writer or router, purpose and batch - must be in
    ``WEALTH_WRITERS`` with its number of call sites, every other reference to a
    writer name in ``WEALTH_WRITER_REFERENCES``, and no row may be stale."""
    from chronicler.wealth_accounting_state import WEALTH_ROUTERS, WEALTH_WRITER_REFERENCES
    paths, references, problems = scan_wealth_writers(_source_root())
    assert not problems, problems
    registered = {key: n for key, (n, _channels) in WEALTH_WRITERS.items()}
    assert dict(paths) == registered, {
        "unregistered or recounted": {k: v for k, v in paths.items() if registered.get(k) != v},
        "stale": {k: v for k, v in registered.items() if k not in paths}}
    assert dict(references) == WEALTH_WRITER_REFERENCES, {
        "unrecognized references (fail closed)": {k: v for k, v in references.items()
                                                  if WEALTH_WRITER_REFERENCES.get(k) != v},
        "stale": {k: v for k, v in WEALTH_WRITER_REFERENCES.items() if k not in references}}
    known = set(CHANNEL_NAMES) | set(WITHHELD_PACKAGES) | set(WITHHELD_OTHER)
    for key, (n, channels) in WEALTH_WRITERS.items():
        assert n > 0 and channels and set(channels) <= known, key
        if key[2] in WEALTH_ROUTERS:            # a router's callers carry only its declared channels
            assert set(channels) <= set(WEALTH_ROUTERS[key[2]]), key
        if key[1].split(".")[-1] in WEALTH_ROUTERS:
            assert set(channels) == set(WEALTH_ROUTERS[key[1].split(".")[-1]]), key
    covered = {c for _n, channels in WEALTH_WRITERS.values() for c in channels}
    assert set(CHANNEL_NAMES) <= covered and set(WITHHELD_PACKAGES) <= covered and set(WITHHELD_OTHER) <= covered


GUARD_FIXTURE = {
    "registered.py": "def pay(sim, world):\n    sim.transfer_wealth(world.turn, PURPOSE_X, 0, [])\n",
    "second.py": ("def pay(sim, world):\n    sim.transfer_wealth(world.turn, PURPOSE_X, 0, [])\n"
                  "    sim.transfer_wealth(world.turn, 9, 0, [])\n"),
    "alias.py": "def pay(sim):\n    send = getattr(sim, 'transfer_wealth')\n    return send(1, 2, 3, [])\n",
    "bound.py": "def pay(sim):\n    send = sim.remit_wealth\n    return send(1, 2, [])\n",
    "helper.py": ("def route(sim, purpose, rows):\n    return sim.transfer_wealth(1, purpose, 0, rows)\n"
                  "def via(sim):\n    return pay_from_firm(None, sim, 0, {}, purpose=PURPOSE_NEW)\n"),
    "nested/kw.py": "class A:\n    def go(self, sim):\n        sim.transfer_wealth(1, batch=4, purpose=P, rows=[])\n",
}


def test_the_guard_counts_call_sites_and_fails_closed_on_dynamic_references(tmp_path):
    """The scanner itself, over a constructed package tree: a second payment
    in a registered function is a new path, ``getattr`` and bound-method
    aliases are references, a helper taking a purpose from its parameter is
    a problem unless declared a router, and routed calls carry their purpose."""
    for name, source in GUARD_FIXTURE.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(source, encoding="utf-8")
    paths, references, problems = scan_wealth_writers(tmp_path)
    assert paths[("registered", "pay", "transfer_wealth", "purpose=PURPOSE_X,batch=0")] == 1
    assert paths[("second", "pay", "transfer_wealth", "purpose=PURPOSE_X,batch=0")] == 1
    assert paths[("second", "pay", "transfer_wealth", "purpose=9,batch=0")] == 1          # a new purpose: a new path
    assert paths[("nested.kw", "A.go", "transfer_wealth", "purpose=P,batch=4")] == 1      # keywords, methods
    assert paths[("helper", "via", "pay_from_firm", "purpose=PURPOSE_NEW")] == 1          # a routed caller
    assert references[("alias", "pay", "transfer_wealth")] == 1                          # getattr by name
    assert references[("bound", "pay", "remit_wealth")] == 1                             # a bound-method alias
    assert problems == ["helper:2: transfer_wealth takes its purpose from a parameter of route, "
                        "which is not a declared router (WEALTH_ROUTERS)"]
    assert not any(key in WEALTH_WRITERS for key in paths)
