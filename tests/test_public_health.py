"""Connected public-health costs, dated evidence and authority boundaries."""
from __future__ import annotations

import ast
import pickle
from pathlib import Path
from types import SimpleNamespace

import pytest

from chronicler import epidemic_care as EC
from chronicler import money
from chronicler import public_health as PH
from chronicler import residence_ledger as RL
from chronicler.epidemic_care_state import CareCapacity
from chronicler.public_health_state import PublicHealthState
from chronicler.quarantine_rules import QuarantineClosure, configure_quarantine
from test_epidemic_care import _Bridge, _Sim, _batch, _envelope, _outbreak, _people, _world


def _enabled(mode="active"):
    w = _world()
    st = PublicHealthState(mode=mode)
    # Root integration adds the serialized container slot. Attaching directly
    # also exercises the module against historical containers without it.
    object.__setattr__(w.livelihoods, "public_health", st)
    st.prices, st.price_turn = {i: 1000 for i in range(3)}, w.turn - 1
    for region in w.regions:
        region.stockpile.goods["grain"] = 10.0
        region.adjacencies = []
    return w, st


@pytest.fixture(autouse=True)
def _seams(monkeypatch):
    # Shared root contract; no native code is involved in this purpose.
    monkeypatch.setitem(money.PURPOSES, "care_supply", None)
    monkeypatch.setattr("chronicler.mutual_aid.read_stockpile_commitments", lambda w, s: {})


def _settle(w):
    sim = _Sim(_people())
    bridge = _Bridge(sim)
    EC.prepare_phase2(w, _batch(w, sim), bridge, sim.get_snapshot(), None)
    EC.finish_phase2(w, SimpleNamespace(market_prices={r.name: {"food": 1.0} for r in w.regions}), bridge, None)
    return sim


def test_supplies_consume_real_grain_and_gross_cost_and_wage_fit_single_envelope():
    w, st = _enabled()
    _outbreak(w, 0, burden=0.05)
    _envelope(w, 0, 8)
    treasury = w.civilizations[0].treasury
    grain = w.regions[0].stockpile.goods["grain"]
    _settle(w)
    cs = w.livelihoods.epidemic_care
    consumed = sum(r.food_milli for r in st.supplies)
    assert consumed > 0
    assert w.regions[0].stockpile.goods["grain"] == pytest.approx(grain - consumed / 1000)
    assert sum(r.charged_milli + r.internal_milli for r in st.supplies) + sum(r.wages_paid_milli for r in cs.frame) <= 8000
    # Its local controller owns the public pool: net cash cost is wages only.
    assert sum(r.internal_milli for r in st.supplies) > 0
    assert sum(r.charged_milli for r in st.supplies) == 0
    assert w.civilizations[0].treasury < treasury
    assert cs.capacity[0].patients <= consumed / (1000 * PH._ration(w))


@pytest.mark.parametrize("failure", ["stock", "price"])
def test_missing_real_supply_never_mints_capacity(failure):
    w, st = _enabled()
    _outbreak(w, 0, burden=0.05)
    _envelope(w, 0, 8)
    if failure == "stock":
        w.regions[0].stockpile.goods["grain"] = 0
    else:
        st.price_turn = w.turn - 2
    _settle(w)
    assert all(c.patients == 0 for c in w.livelihoods.epidemic_care.capacity)
    assert sum(r.food_milli for r in st.supplies) == 0
    assert st.totals["patients_unsupplied"] > 0


def test_owned_and_committed_grain_are_never_sold_as_public_supply(monkeypatch):
    w, st = _enabled()
    w.regions[0].stockpile.goods["grain"] = 10
    monkeypatch.setattr("chronicler.household_retail.pilot_entry", lambda w, rid: SimpleNamespace(goods=[4000]) if rid == 0 else None)
    assert PH._available(w, 0, {w.regions[0].name: {"grain": 3.0}}) == 3000
    assert PH._available(w, 0, {w.regions[0].name: {"grain": 7.0}}) == 0


def test_only_open_direct_neighbors_sell_and_foreign_owner_receives_real_cash():
    w, st = _enabled()
    w.regions[0].stockpile.goods["grain"] = 0
    w.regions[0].adjacencies = [w.regions[2].name]
    before = w.civilizations[1].treasury
    _outbreak(w, 0, burden=0.05)
    _envelope(w, 0, 8)
    _settle(w)
    sold = [r for r in st.supplies if r.seller == 1 and r.food_milli]
    assert sold
    assert w.civilizations[1].treasury - before == sum(r.charged_milli for r in sold) // 1000
    assert all(r.source in (0, 2) for r in st.supplies)


def test_closure_refuses_foreign_patient_supplies():
    w, st = _enabled()
    configure_quarantine(w, SimpleNamespace(quarantine_mode="closure", quarantine_channels=None))
    rules = w.epidemics.quarantine_rules
    rules.closures = [QuarantineClosure(id=0, civ=0, target=1, opened_turn=0, last_renewed_turn=4, cause="")]
    w.regions[0].adjacencies = [w.regions[2].name]
    assert list(PH._sources(w, 0, 0)) == [(0, 0)]


def test_repeat_supply_settlement_is_refused_before_any_stock_changes():
    w, st = _enabled()
    st.supply_turn = w.turn
    before = [r.stockpile.goods.copy() for r in w.regions]
    with pytest.raises(RuntimeError, match="already settled"):
        PH.supply_care(w, SimpleNamespace(), [], SimpleNamespace(), None)
    assert [r.stockpile.goods for r in w.regions] == before


def test_supplies_and_delayed_reports_restore_exactly():
    w, st = _enabled()
    _outbreak(w, 0)
    _envelope(w, 0, 8)
    _settle(w)
    assert pickle.loads(pickle.dumps(st)).model_dump() == st.model_dump()
    assert st.supply_turn == w.turn


def test_environment_reads_only_guarded_previous_frame_and_stale_sanitation_is_neutral(monkeypatch):
    w, st = _enabled()
    observed = []
    def read(world, *, consumer_turn):
        observed.append(consumer_turn)
        return {"regions": [{"region": 0, "displaced": 5, "residents": 10}]}
    monkeypatch.setattr(RL, "read_frame", read)
    st.sanitation_turn, st.sanitation = w.turn - 1, [1.0, 0.0, 0.0]
    rows = PH.environment_factors(w)
    assert observed == [w.turn]
    assert rows[0]["crowding_factor"] == 1.125
    assert rows[0]["flux_factor"] == 0.8
    st.sanitation_turn = w.turn - 2
    assert PH.environment_factors(w)[0]["flux_factor"] == 1


def test_environment_propagates_same_turn_read_refusal(monkeypatch):
    w, st = _enabled()
    def read(world, *, consumer_turn):
        raise RL.LedgerReadRefused("same-turn read refused")
    monkeypatch.setattr(RL, "read_frame", read)
    with pytest.raises(RL.LedgerReadRefused):
        PH.environment_factors(w)


def test_cost_control_keeps_real_supply_costs_and_crowding_but_no_protective_effect(monkeypatch):
    w, st = _enabled("cost_only")
    monkeypatch.setattr(RL, "read_frame", lambda *a, **k: {"regions": [{"region": 0, "displaced": 5, "residents": 10}]})
    st.sanitation_turn, st.sanitation = w.turn - 1, [1.0, 0.0, 0.0]
    assert PH.environment_factors(w)[0]["flux_factor"] == 1.0
    assert PH.environment_factors(w)[0]["crowding_factor"] == 1.125
    assert not PH.care_allowed(w)
    _outbreak(w, 0)
    _envelope(w, 0, 8)
    _settle(w)
    assert st.totals["food_consumed_milli"] > 0
    w.turn += 1
    assert EC.care_factors(w, w.epidemics.rows) is None


def test_outbreak_reports_are_delayed_and_current_own_deaths_are_not_prior_knowledge():
    w, st = _enabled()
    w.contact_ledger.edges = [(0, 2, 100.0, 100.0, 0.0, 0.0)]
    w.contact_ledger.invalidate()
    _outbreak(w, 2, burden=0.5)
    _outbreak(w, 0, burden=0.5)
    w.epidemics.last_deaths = [(0, 1, 10)]
    assert PH.report_targets(w, {(2, 1): object(), (0, 1): object()}) == {}
    reports = [r for r in st.reports if r.recipient == 0 and r.target == 1]
    assert reports and min(r.delivery for r in reports) == w.turn + 2
    assert st.fatality["0:1"][0] == 10
    w.turn += 1
    assert PH.report_targets(w, {}) == {}
    assert st.decisions == []
    w.turn += 1
    PH.report_targets(w, {})
    assert st.decisions and st.decisions[0]["fatality_observed"]


def test_reports_expire_and_never_read_current_hidden_prevalence():
    w, st = _enabled()
    w.contact_ledger.edges = [(0, 2, 100.0, 0.0, 0.0, 0.0)]
    w.contact_ledger.invalidate()
    _outbreak(w, 2, burden=0.1)
    PH.report_targets(w, {(2, 1): object()})
    issued = [r.prevalence for r in st.reports]
    w.epidemics.rows[0].burden = 0.9
    w.turn += 2
    PH.report_targets(w, {})
    assert [r.prevalence for r in st.reports] == issued
    w.turn += 10
    PH.report_targets(w, {})
    assert st.reports == [] and st.decisions == []


def test_new_module_never_creates_individual_injury_or_applies_deaths():
    tree = ast.parse(Path(PH.__file__).read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not {"InjuryEpisode", "_apply_deaths", "endemic_severity", "health_care"} & (names | attrs)


def test_feature_off_helpers_leave_capacity_and_decisions_unchanged():
    w = _world()
    capacity = [CareCapacity(region=0, source_turn=w.turn, carers=1, care_time=1, patients=5)]
    assert PH.supply_care(w, None, capacity, None, None) is capacity
    assert PH.supply_estimate(w, 100, [0]) == 0
    assert PH.wage_budget(w, 0, 4000) == 4000
    assert PH.report_targets(w, {}) is None
    assert PH.environment_factors(w) is None
    assert PH.care_allowed(w)
