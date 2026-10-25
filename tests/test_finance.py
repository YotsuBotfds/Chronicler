"""Money, credit and public finance: accounting, interest, default, prices, persistence, dormancy."""
from __future__ import annotations

import argparse
import json
import math

import pytest

from chronicler.bundle_codec import load_bundle
import chronicler.finance as F
from chronicler.accumulator import StatAccumulator
from chronicler.action_engine import ActionEngine
from chronicler.models import ActionType, Disposition, Event, TurnSnapshot, WorldState
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world


def _world(seed: int = 42, *, finance: bool = True, campaigns: bool = True) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = campaigns
    F.set_finance_enabled(world, finance)
    return world


def _advance(world: WorldState, turns: int, *, bridge=None) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn, agent_bridge=bridge)
    return world


def _living(world) -> list[int]:
    return [i for i, c in enumerate(world.civilizations) if c.regions]


def _tick(world, income: dict[int, int] | None = None, economy_result=None) -> tuple[list, StatAccumulator]:
    """One stand-alone fiscal turn: book ``income`` as this turn's revenue, tick,
    apply the accumulator and move to the next turn."""
    acc = StatAccumulator()
    for idx, amount in (income or {}).items():
        acc.add(idx, world.civilizations[idx], "treasury", amount, "keep")
    events = F.tick_finance(world, acc=acc, economy_result=economy_result)
    acc.apply(world)
    world.turn += 1
    return events, acc


def _outstanding(world) -> int:
    return sum(loan.principal for loan in world.finance.loans)


def _ledger_balance(world) -> int:
    t = world.finance.totals
    return (t["issued_domestic"] + t["issued_foreign"] + t["capitalized"]
            - t["repaid_principal"] - t["written_off"])


# --- debt accounting ------------------------------------------------------------------

def test_debt_ledger_balances_over_a_full_run():
    world = _advance(_world(42), 40)
    st = world.finance
    assert st.totals["issued_domestic"] > 0 and st.totals["issued_foreign"] > 0
    # Outstanding principal is exactly what was lent, capitalized, repaid and written off.
    assert _outstanding(world) == _ledger_balance(world)
    assert all(loan.principal > 0 for loan in st.loans)
    assert all(loan.lender == F.DOMESTIC or 0 <= loan.lender < len(world.civilizations) for loan in st.loans)
    # Per-civ accounts agree with the world ledger.
    assert sum(f.borrowed_total for f in st.civs) == st.totals["issued_domestic"] + st.totals["issued_foreign"]
    assert sum(f.repaid_total for f in st.civs) == st.totals["repaid_principal"]


def test_foreign_flows_conserve_treasury_between_civs():
    world = _world(42)
    a, b = _living(world)[:2]
    ca, cb = world.civilizations[a], world.civilizations[b]
    ca.treasury, cb.treasury = 5000, 0
    _tick(world, {a: 40, b: 40})  # initialize revenue and money
    before = ca.treasury + cb.treasury
    loan = F.extend_loan(world, a, b, 300)
    assert loan is not None and loan.principal == 300 and loan.lender == a
    assert ca.treasury + cb.treasury == before
    assert F.outstanding_debt(world, b) == 300 == F.creditor_claims(world, a)[b]
    # Service: everything the debtor pays a foreign lender, the lender receives,
    # so across all civs the treasuries change by income less upkeep and court
    # only (prices are at par and no one borrows: every treasury is ample).
    for civ in world.civilizations:
        civ.treasury = max(civ.treasury, 3000)
    cb.treasury = 300
    living = _living(world)
    for _ in range(5):
        total_before = sum(c.treasury for c in world.civilizations)
        income = {i: 60 for i in living}
        _tick(world, income)
        st = world.finance
        assert st.civs[b].last_borrowed == 0
        spent = sum(st.civs[i].last_upkeep + st.civs[i].last_court for i in living)
        assert sum(c.treasury for c in world.civilizations) == total_before + sum(income.values()) - spent
    assert world.finance.totals["interest_foreign"] > 0
    assert world.finance.totals["issued_domestic"] == 0
    assert _outstanding(world) == _ledger_balance(world)


def test_transfer_moves_treasury_and_specie():
    world = _world(42)
    a, b = _living(world)[:2]
    world.civilizations[a].treasury = 100
    _tick(world, {a: 10, b: 10})
    F.update_money(world)
    index = {r.name: i for i, r in enumerate(world.regions)}
    cap_a = F._anchor_region(world, world.civilizations[a], index)
    cap_b = F._anchor_region(world, world.civilizations[b], index)
    sa, sb = world.finance.region_specie[cap_a], world.finance.region_specie[cap_b]
    treasury_a = world.civilizations[a].treasury
    paid = F.transfer(world, a, b, 10_000)
    assert paid == treasury_a  # never more than the payer holds
    assert world.civilizations[a].treasury == 0
    moved = sa - world.finance.region_specie[cap_a]
    assert moved == pytest.approx(world.finance.region_specie[cap_b] - sb)
    assert moved == pytest.approx(min(sa, paid * world.finance.civs[a].fineness))
    # With finance off the transfer still pays, without touching any finance state.
    off = _world(42, finance=False)
    off.civilizations[a].treasury = 50
    assert F.transfer(off, a, b, 20) == 20 and off.finance is None


# --- interest and amortization -----------------------------------------------------

def test_interest_and_amortization_schedule():
    world = _world(42)
    a, b = _living(world)[:2]
    world.civilizations[a].treasury = 10_000
    world.civilizations[b].treasury = 300
    _tick(world, {b: 200})
    world.finance.civs[b].revenue_ema = 200.0
    F.extend_loan(world, a, b, 200, rate=0.05, term=10)
    interest_paid = 0
    principal_trace = []
    carry = 0.0
    expected_interest = 0
    expected_trace = []
    principal = 200
    for _ in range(10):
        accrued = principal * 0.05 + carry
        expected_interest += int(accrued)
        carry = accrued - int(accrued)
        principal -= min(principal, math.ceil(200 / 10))
        expected_trace.append(principal)
        # Treasury enough to service on schedule but under half the reserve
        # target, so nothing is prepaid and nothing new is borrowed.
        world.civilizations[b].treasury = 300
        _tick(world, {b: 200})
        interest_paid += world.finance.civs[b].last_interest
        principal_trace.append(F.outstanding_debt(world, b, a))
    assert principal_trace == expected_trace
    assert interest_paid == expected_interest
    assert world.finance.totals["interest_foreign"] == interest_paid
    assert world.finance.civs[b].interest_total == interest_paid
    assert world.finance.civs[b].borrowed_total == 200  # serviced from revenue, never refinanced
    assert F.outstanding_debt(world, b) == 0
    assert _outstanding(world) == _ledger_balance(world)


def test_surplus_prepays_the_dearest_line_first():
    world = _world(42)
    a, b = _living(world)[:2]
    world.civilizations[a].treasury = 10_000
    _tick(world, {b: 50})
    world.finance.civs[b].revenue_ema = 50.0
    cheap = F.extend_loan(world, a, b, 100, rate=0.03)
    dear = F._new_loan(world, b, F.DOMESTIC, 100, 0.12, F.LOAN_TERM)
    world.finance.totals["issued_domestic"] += 100
    world.civilizations[b].treasury = 450  # above half the reserve target (200): a partial prepayment
    _tick(world, {b: 50})
    assert dear.principal == 0 and cheap.principal > 0
    assert _outstanding(world) == _ledger_balance(world)


def test_unpaid_interest_is_capitalized_not_lost():
    world = _world(42)
    a, b = _living(world)[:2]
    world.civilizations[a].treasury = 10_000
    world.civilizations[b].treasury = 0
    _tick(world, {b: 1})
    F.extend_loan(world, a, b, 500, rate=0.1, term=20)
    world.civilizations[b].treasury = 0
    world.finance.civs[b].excluded_until = world.turn + 100  # no refinancing
    world.finance.civs[b].grace_until = world.turn + 100     # and no default
    world.finance.civs[b].domestic_trust = 0.0
    _tick(world, {})
    line = next(loan for loan in F.loans_of(world, b) if loan.lender == a)
    assert line.capitalized > 0
    assert line.principal > 500 - math.ceil(500 / 20)
    assert _outstanding(world) == _ledger_balance(world)


# --- default ------------------------------------------------------------------------

def _insolvent_debtor(world, *, lender_rel=Disposition.FRIENDLY):
    a, b = _living(world)[:2]
    ca, cb = world.civilizations[a], world.civilizations[b]
    ca.treasury, cb.treasury = 10_000, 0
    _tick(world, {a: 50, b: 50})
    F.extend_loan(world, a, b, 400, rate=0.08)
    cb.treasury = 0
    world.relationships[ca.name][cb.name].disposition = lender_rel
    f = world.finance.civs[b]
    f.domestic_trust = 0.0
    f.excluded_until = None
    return a, b


def test_default_after_material_arrears_with_consequences():
    world = _world(42)
    from chronicler.governance_runtime import set_governance_enabled
    set_governance_enabled(world, True)
    from chronicler.governance_state import CivGovernance
    a, b = _insolvent_debtor(world)
    cb = world.civilizations[b]
    cb.governance = CivGovernance(ruler_legitimacy=0.6)
    ca = world.civilizations[a]
    ca.treasury = 0  # the creditor cannot refinance the debtor
    stability_hits = []
    defaults = []
    for _ in range(F.ARREARS_LIMIT + 1):
        events, acc = _tick(world, {})
        defaults += [e for e in events if e.event_type == "state_default"]
        stability_hits += [c.delta for c in acc._changes if c.civ_id == b and c.stat == "stability"]
    assert len(defaults) == 1
    ev = defaults[0]
    f = world.finance.civs[b]
    assert f.defaults == 1 and f.last_default_turn == world.turn - 2
    assert -F.DEFAULT_STABILITY in stability_hits
    assert cb.governance.ruler_legitimacy == pytest.approx(0.6 - F.DEFAULT_LEGITIMACY)
    assert f.credit_premium >= F.DEFAULT_PREMIUM * F.PREMIUM_DECAY
    assert f.excluded_until == f.last_default_turn + F.CREDIT_EXCLUSION_TURNS
    # Haircut: half of the line is written off and the rest rescheduled at the base rate.
    line = next(loan for loan in F.loans_of(world, b) if loan.lender == a)
    assert world.finance.totals["written_off"] > 0
    assert line.rate <= F.FOREIGN_RATE and line.original <= line.principal
    # The foreign creditor holds a grievance and sours on the defaulter.
    assert world.finance.civs[a].grievance[b] > 0.5
    assert world.relationships[ca.name][cb.name].disposition == Disposition.NEUTRAL
    assert ev.civs == [cb.name, ca.name] and ev.importance == 8
    # Grace: no second default straight away.
    for _ in range(F.DEFAULT_GRACE - 2):
        events, _ = _tick(world, {})
        assert not [e for e in events if e.event_type == "state_default"]
    # Burned and excluded: no foreign lender will refinance.
    assert all(loan.lender in (a, F.DOMESTIC) for loan in F.loans_of(world, b))
    assert _outstanding(world) == _ledger_balance(world)


def test_small_debts_are_rolled_over_not_repudiated():
    world = _world(42)
    a, b = _living(world)[:2]
    world.civilizations[a].treasury = 10_000
    _tick(world, {a: 50, b: 400})
    F.extend_loan(world, a, b, 15, rate=0.08)  # well under a turn of revenue
    world.civilizations[b].treasury = 0
    world.civilizations[a].treasury = 0
    world.finance.civs[b].domestic_trust = 0.0
    for _ in range(6):
        events, _ = _tick(world, {})
        assert not [e for e in events if e.event_type == "state_default"]


# --- prices ---------------------------------------------------------------------------

def _money_world():
    world = _world(42)
    _tick(world, {i: 5 for i in _living(world)})
    F.update_money(world)
    return world


def test_debasement_raises_prices_slowly_toward_the_new_standard():
    world = _money_world()
    c = _living(world)[0]
    civ = world.civilizations[c]
    f = world.finance.civs[c]
    index = {r.name: i for i, r in enumerate(world.regions)}
    silver_before = sum(world.finance.region_specie[index[n]] for n in civ.regions)
    book = F._Book(world, None)
    treasury = civ.treasury
    events: list = []
    gain = F._debase(world, c, civ, f, book, index, None, events, [])
    assert gain > 0 and civ.treasury == treasury + gain
    assert f.fineness == pytest.approx(1 - F.DEBASE_STEP)
    assert events[0].event_type == "debasement"
    assert sum(world.finance.region_specie[index[n]] for n in civ.regions) == pytest.approx(silver_before)
    # A second debasement inside the cooldown does nothing.
    assert F._debase(world, c, civ, f, book, index, None, [], []) == 0
    prices = [f.price_index]
    for _ in range(60):
        F.update_money(world)
        prices.append(f.price_index)
    assert all(b >= a - 1e-9 for a, b in zip(prices, prices[1:]))
    first_step = prices[1] - prices[0]
    assert 0 < first_step < 0.05                                # slow: sticky prices
    assert prices[-1] == pytest.approx(1 / f.fineness, rel=0.03)  # permanent nominal level
    assert f.inflation < first_step / prices[0]                   # inflation has decayed
    # The next fiscal tick reports a price-inflation episode while it lasts.
    world2 = _money_world()
    c2 = _living(world2)[0]
    f2 = world2.finance.civs[c2]
    F._debase(world2, c2, world2.civilizations[c2], f2, F._Book(world2, None), index, None, [], [])
    F.update_money(world2)
    f2.inflation = 0.03
    events, _ = _tick(world2, {c2: 5})
    assert any(e.event_type == "price_inflation" for e in events)


def test_sack_carries_specie_home_once_and_prices_follow():
    world = _money_world()
    index = {r.name: i for i, r in enumerate(world.regions)}
    a, b = _living(world)[:2]
    victim = index[world.civilizations[b].regions[0]]
    world.regions[victim].occupied_by = world.civilizations[a].name
    home = F._anchor_region(world, world.civilizations[a], index)
    before = world.finance.region_specie[victim]
    home_before = world.finance.region_specie[home]
    F.update_money(world)
    loot = F.SACK_SHARE * before
    assert world.finance.civs[a].loot_specie == pytest.approx(loot, rel=1e-6)
    assert world.finance.region_specie[home] > home_before + 0.5 * loot
    # The occupation persists: no second sack next turn (consumed exactly once).
    F.update_money(world)
    assert world.finance.civs[a].loot_specie == pytest.approx(loot, rel=1e-6)
    p_a = [world.finance.civs[a].price_index]
    for _ in range(30):
        F.update_money(world)
        p_a.append(world.finance.civs[a].price_index)
    assert max(p_a) > 1.0  # loot inflation at home ...
    assert p_a[-1] < max(p_a)  # ... that the specie flow wears down


def test_precious_mines_mint_bullion_paid_to_the_crown_next_turn():
    from chronicler.models import ResourceType
    world = _money_world()
    c = _living(world)[0]
    civ = world.civilizations[c]
    region = next(r for r in world.regions if r.controller == civ.name)
    region.resource_types = [int(ResourceType.PRECIOUS), 255, 255]
    region.resource_effective_yields = [1.0, 0.0, 0.0]
    region.resource_reserves = [1.0, 1.0, 1.0]
    region.population = max(region.population, 10)
    F.update_money(world)
    f = world.finance.civs[c]
    expected = F.ROYAL_SHARE * F.MINT_PER_YIELD
    assert f.royal_bullion == pytest.approx(expected, rel=1e-6)
    treasury = civ.treasury
    _tick(world, {})
    assert world.finance.totals["royal_bullion"] == int(expected)
    assert f.royal_bullion == pytest.approx(expected - int(expected), abs=1e-6)
    assert civ.treasury >= treasury - f.last_upkeep - f.last_court - f.last_service + int(expected) - 1


# --- persistence, determinism, dormancy ------------------------------------------------

def test_save_load_resume_identity_with_outstanding_loans(tmp_path):
    straight = _advance(_world(42), 30)
    first = _advance(_world(42), 15)
    assert first.finance.loans, "fixture carries outstanding loans at the save point"
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.finance == first.finance
    _advance(resumed, 15)
    assert resumed.finance.model_dump() == straight.finance.model_dump()
    assert resumed.model_dump_json() == straight.model_dump_json()


def test_finance_runs_are_deterministic():
    w1 = _advance(_world(11), 30)
    w2 = _advance(_world(11), 30)
    assert w1.model_dump_json() == w2.model_dump_json()
    assert w1.finance.last_tick_turn == 29 and w1.finance.last_money_turn == 29


def test_no_transient_state_survives_a_turn():
    """Finance keeps no transient queue: every tick input is persisted state or
    this turn's accumulator, and carried amounts are consumed once."""
    world = _advance(_world(42), 5)
    assert not world.finance.__pydantic_private__  # no private (unsaved) attributes
    dumped = WorldState.model_validate_json(world.model_dump_json())
    assert dumped.finance == world.finance
    # Royal bullion minted at the end of a turn is paid by the next tick exactly once.
    before = world.finance.totals["royal_bullion"]
    pending = sum(int(f.royal_bullion) for f in world.finance.civs)
    _advance(world, 1)
    assert world.finance.totals["royal_bullion"] >= before + pending
    # Two ticks in one turn would double count revenue: the turn loop runs one.
    assert world.finance.last_tick_turn == world.turn - 1


def test_feature_off_never_runs_finance_code(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("finance invoked while disabled")

    for name in ("tick_finance", "update_money", "finance_weight_modifiers", "psi_fiscal_distress",
                 "snapshot_summary"):
        monkeypatch.setattr(F, name, forbidden)
    world = _world(42, finance=False)
    from chronicler.governance_runtime import set_governance_enabled
    set_governance_enabled(world, True)
    _advance(world, 30)
    assert world.finance is None
    assert "finance" not in world.model_dump(mode="json")


def test_dormant_fields_are_omitted_and_old_saves_load():
    world = _world(finance=False)
    assert "finance" not in json.loads(world.model_dump_json())
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert "finance" not in snap.model_dump()
    snap.finance = {"civs": {}}
    assert snap.model_dump()["finance"] == {"civs": {}}
    on = _advance(_world(finance=True), 3)
    raw = json.loads(on.model_dump_json())
    assert raw["finance"]["civs"]
    raw.pop("finance")
    assert WorldState.model_validate(raw).finance is None


# --- consumers: PSI, action weights, provenance --------------------------------------

def test_psi_state_debt_input_comes_from_fiscal_stress():
    from chronicler.governance_runtime import set_governance_enabled
    world = _world(42)
    set_governance_enabled(world, True)
    _advance(world, 25)
    stressed = 0
    for idx in _living(world):
        civ = world.civilizations[idx]
        gov = civ.governance
        legit = [i.legitimacy for i in gov.institutions]
        legitimacy = sum(legit) / len(legit) if legit else 1.0
        expected = F.psi_fiscal_distress(world, idx, legitimacy, gov.last_institution_enforcement_cost)
        assert gov.sfd_raw == pytest.approx(expected)
        stressed += world.finance.civs[idx].fiscal_stress > 0
    assert stressed, "some civ carries fiscal stress in the fixture"
    # A debt-free, balanced polity is neutral.
    f = world.finance.civs[_living(world)[0]]
    f.fiscal_stress = 0.0
    assert F.psi_fiscal_distress(world, _living(world)[0], 0.5, 10.0) == 0.0


def test_finance_weight_bucket_is_clamped_and_directional():
    world = _world(42)
    a, b = _living(world)[:2]
    world.civilizations[a].treasury = 10_000
    _tick(world, {a: 20, b: 20})
    F.extend_loan(world, a, b, 2_000)
    world.finance.civs[b].fiscal_stress = 1.5
    mods = F.finance_weight_modifiers(world, b)
    assert mods[ActionType.WAR] < 1.0 < mods[ActionType.TRADE]
    assert mods[ActionType.BUILD] < 1.0
    world.finance.civs[a].grievance = {b: 5.0}
    creditor = F.finance_weight_modifiers(world, a)
    assert creditor[ActionType.WAR] > 1.0 and creditor[ActionType.EMBARGO] > 1.0
    lo, hi = 1 / F.FINANCE_WEIGHT_CEILING, F.FINANCE_WEIGHT_CEILING
    for m in (*mods.values(), *creditor.values()):
        assert lo - 1e-12 <= m <= hi + 1e-12
    # The action engine applies the bucket only with finance on (pre-cap weights).
    engine = ActionEngine(world)
    with_fin = engine.compute_weights(world.civilizations[b])
    saved = world.finance
    world.finance = None
    without = ActionEngine(world).compute_weights(world.civilizations[b])
    world.finance = saved
    assert with_fin != without


def test_loans_and_defaults_cite_their_causes():
    from chronicler import provenance as prov
    world = _world(42)
    a, b = _living(world)[:2]
    ca, cb = world.civilizations[a], world.civilizations[b]
    war = Event(turn=0, event_type="war_declared", actors=[cb.name, ca.name],
                description="war", importance=7)
    prov.observe(world, [war])
    world.active_wars.append((cb.name, ca.name))
    cb.treasury = 0
    events, _ = _tick(world, {b: 40})
    loans = [e for e in events if e.event_type == "loan_taken" and e.civs[0] == cb.name]
    assert loans and war.event_id in loans[0].causes
    # A default cites the debtor's credit lines; it registers the fiscal key the PSI cites.
    world.active_wars.clear()
    for loan in F.loans_of(world, b):
        loan.principal = max(loan.principal, 200)
    world.finance.civs[b].domestic_trust = 0.0
    world.finance.civs[b].excluded_until = world.turn + 50
    ca.treasury = 0
    cb.treasury = 0
    default = None
    for _ in range(6):
        events, _ = _tick(world, {})
        prov.observe(world, events)
        default = next((e for e in events if e.event_type == "state_default"), None)
        if default is not None:
            break
    assert default is not None
    line_ids = {loan.event_id for loan in F.loans_of(world, b) if loan.event_id}
    assert line_ids & set(default.causes)
    assert prov.recall(world, prov.key("fiscal", cb.name)) == default.event_id
    assert prov.recall(world, prov.key("default", cb.name)) == default.event_id


# --- CLI, gate runner, defaults --------------------------------------------------------

def _cli_args(tmp_path, *, finance, turns=10, agents="off"):
    return argparse.Namespace(
        seed=42, turns=turns, civs=4, regions=8, output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, pause_every=None, simulate_only=True, agents=agents, finance=finance,
    )


def test_cli_flag_persists_and_bundle_carries_finance_history(tmp_path):
    from chronicler.main import _build_parser, execute_run
    assert _build_parser().parse_args(["--finance"]).finance is True
    assert _build_parser().parse_args(["--no-finance"]).finance is False
    assert _build_parser().parse_args([]).finance is None
    execute_run(_cli_args(tmp_path, finance=True))
    state = json.loads((tmp_path / "state.json").read_text())
    assert "finance" in state
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    assert all("finance" in snap for snap in bundle["history"])
    row = next(iter(bundle["history"][-1]["finance"]["civs"].values()))
    assert {"debt", "price_index", "fiscal_stress", "defaults", "debasements"} <= set(row)
    metrics = F.extract_finance_metrics([bundle])
    assert metrics["runs"] == 1 and metrics["price_index"]["min"] > 0


def test_default_on_for_new_worlds_and_resume_keeps_saved_setting(tmp_path):
    from chronicler.main import execute_run
    assert F.DEFAULT_ENABLED_FOR_NEW_WORLDS is True
    fresh = tmp_path / "fresh"
    execute_run(_cli_args(fresh, finance=None, turns=3))
    assert "finance" in json.loads((fresh / "state.json").read_text())
    off = tmp_path / "off"
    execute_run(_cli_args(off, finance=False, turns=3))
    assert "finance" not in json.loads((off / "state.json").read_text())
    resumed = _cli_args(off, finance=None, turns=5)
    resumed.resume = str(off / "state.json")
    resumed.state = str(off / "resumed.json")
    execute_run(resumed)
    assert "finance" not in json.loads((off / "resumed.json").read_text())


def test_gate_runner_forwards_the_switch_only_when_explicit():
    from scripts.m53b_run_validation import _finance_args
    assert _finance_args(argparse.Namespace(finance=None)) == []
    assert _finance_args(argparse.Namespace(finance=True)) == ["--finance"]
    assert _finance_args(argparse.Namespace(finance=False)) == ["--no-finance"]
    assert _finance_args(argparse.Namespace()) == []


# --- agent modes (native) ------------------------------------------------------------

@pytest.mark.native
def test_hybrid_finance_reads_merchant_wealth_and_is_deterministic():
    pytest.importorskip("chronicler_agents")
    from chronicler.agent_bridge import AgentBridge

    def run():
        world = _world(7)
        world.agent_mode = "hybrid"
        bridge = AgentBridge(world, mode="hybrid")
        _advance(world, 25, bridge=bridge)
        return world

    w1, w2 = run(), run()
    assert w1.finance.model_dump() == w2.finance.model_dump()
    assert any(f.merchant_wealth > 0 for f in w1.finance.civs), "creditor class wealth from the economy"
    assert _outstanding(w1) == _ledger_balance(w1)
