"""Domestic credit through real lenders (``chronicler.domestic_credit``,
``--domestic-credit``): who lends, the cash flows and their books, losses and
grievance, the native transfer protocol (on a stand-in simulator), the
region batch column, the switch and its wiring. Native behaviour is in
tests/test_domestic_credit_native.py and the Rust tests (``credit.rs``,
``satisfaction.rs``)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import chronicler.cities as C
import chronicler.domestic_credit as D
import chronicler.finance as F
import chronicler.guilds as G
from chronicler.accumulator import StatAccumulator
from chronicler.cities_state import City
from chronicler.domestic_credit_state import CITY, GUILD, LEGACY, MERCHANTS, Funder
from chronicler.guilds_state import Guild
from chronicler.models import FactionType, WorldState
from chronicler.world_gen import generate_world

ROOT = Path(__file__).resolve().parents[1]
# Template seed 42: Thornwall Confederacy (civ 2) holds Verdant Plains (2,
# capital) and Thornwood (4).
VERDANT, THORNWOOD = 2, 4
THORNWALL = 2


class FakeSim:
    """The two native calls of domestic credit on a toy pool of merchants
    ([home region, wealth]); same rule as ``credit.rs`` (pro rata to
    wealth, a credit up to the ceiling, never below zero)."""

    MAX = 100.0

    def __init__(self, n_regions: int, merchants):
        self.n = n_regions
        self.merchants = [[r, float(w)] for r, w in merchants]
        self.calls: list[tuple[list[int], list[float]]] = []

    def merchant_wealth_by_region(self):
        wealth, counts = [0.0] * self.n, [0] * self.n
        for r, w in self.merchants:
            wealth[r] += w
            counts[r] += 1
        return wealth, counts

    def total(self, region: int) -> float:
        return sum(w for r, w in self.merchants if r == region)

    def apply_merchant_transfers(self, ids, amounts):
        self.calls.append((list(ids), list(amounts)))
        out = []
        for r, amount in zip(ids, amounts):
            group = [m for m in self.merchants if m[0] == r]
            total = sum(m[1] for m in group)
            before = total
            if not group:
                out.append(0.0)
                continue
            if amount < 0:
                if total > 0:
                    keep = 1.0 - min(-amount, total) / total
                    for m in group:
                        m[1] *= keep
            else:
                weights = [m[1] for m in group] if total > 0 else [1.0] * len(group)
                ws = sum(weights)
                for m, w in zip(group, weights):
                    m[1] = min(self.MAX, m[1] + amount * w / ws)
            out.append(sum(m[1] for m in group) - before)
        return out


def _world(*, guild_purse: float = 20.0, city_purse: float = 40.0, merchants=((VERDANT, 60.0), (THORNWOOD, 40.0))):
    world = generate_world(seed=42)
    F.set_finance_enabled(world, True)
    D.set_domestic_credit_enabled(world, True)
    C.set_cities_enabled(world, True)
    G.set_guilds_enabled(world, True)
    world.turn = 30
    city = City(settlement_id=1, region=THORNWOOD, name="Thornwood Settlement 1", founded_turn=20,
                founder=THORNWALL, lord=THORNWALL, rank=2, residents=30, size=30.0, wealth=city_purse)
    world.cities.cities.append(city)
    guild = Guild(city=1, region=THORNWOOD, name="the Weavers' Guild of Thornwood Settlement 1",
                  founded_turn=25, wealth=guild_purse, lord=THORNWALL, history=[(25, "founded", "")])
    world.guilds.guilds.append(guild)
    sim = FakeSim(len(world.regions), merchants)
    bridge = SimpleNamespace(_sim=sim)
    return world, bridge, sim, city, guild


def _tick(world, bridge, income: dict[int, int] | None = None):
    acc = StatAccumulator()
    for idx, amount in (income or {}).items():
        acc.add(idx, world.civilizations[idx], "treasury", amount, "keep")
    events = F.tick_finance(world, acc=acc, agent_bridge=bridge)
    acc.apply(world)
    world.turn += 1
    return events, acc


def _domestic(world, borrower=THORNWALL):
    return next((loan for loan in F.loans_of(world, borrower) if loan.lender == F.DOMESTIC), None)


def _line(world, loan):
    return next(line for line in world.domestic_credit.lines if line.loan_id == loan.loan_id)


def _claims(world, kind: int, key: int) -> int:
    return sum(fu.principal for line in world.domestic_credit.lines for fu in line.funders
               if fu.kind == kind and fu.key == key)


def _borrowing_world(**kw):
    """Thornwall short of money with only domestic lenders to turn to."""
    world, bridge, sim, city, guild = _world(**kw)
    for civ in world.civilizations:
        civ.treasury = 0
    world.civilizations[THORNWALL].military = 100   # upkeep it cannot pay
    return world, bridge, sim, city, guild


@pytest.fixture
def checked(monkeypatch):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")


# ---------------------------------------------------------------------------
# Who lends
# ---------------------------------------------------------------------------

def test_split_is_exact_pro_rata_and_never_above_a_weight():
    assert D.split(10, [1, 1]) == [5, 5]
    assert D.split(7, [3, 0, 1]) == [5, 0, 2]
    assert D.split(1, [1, 1, 1]) == [1, 0, 0]       # ties to the earlier index
    assert D.split(0, [2, 2]) == [0, 0]
    assert D.split(5, [0, 0]) == [0, 0]
    for total in range(0, 40):
        weights = [7, 13, 1, 19]
        parts = D.split(total, weights)
        assert sum(parts) == total
        assert all(p <= w for p, w in zip(parts, weights))


def test_lenders_fund_a_loan_pro_rata_from_their_wealth(checked):
    world, bridge, sim, city, guild = _borrowing_world()
    events, _ = _tick(world, bridge, {THORNWALL: 5})
    loan = _domestic(world)
    assert loan is not None
    line = _line(world, loan)
    assert sum(fu.principal for fu in line.funders) == loan.principal
    # Offers: half of each lender's wealth (no claims yet): merchants of
    # Verdant Plains 30, of Thornwood 20, the city 20, the guild 10.
    lent = {(fu.kind, fu.key): fu.principal for fu in line.funders}
    assert set(lent) <= {(MERCHANTS, VERDANT), (MERCHANTS, THORNWOOD), (CITY, 1), (GUILD, 0)}
    assert loan.principal <= 80
    keys = [(MERCHANTS, VERDANT), (MERCHANTS, THORNWOOD), (GUILD, 0), (CITY, 1)]
    offers = [30, 20, 10, 20]
    assert [lent.get(k, 0) for k in keys] == D.split(loan.principal, offers)
    assert all(lent.get(k, 0) <= o for k, o in zip(keys, offers))
    # The principal left the lenders' wealth.
    assert sim.total(VERDANT) == pytest.approx(60.0 - lent[(MERCHANTS, VERDANT)])
    assert sim.total(THORNWOOD) == pytest.approx(40.0 - lent.get((MERCHANTS, THORNWOOD), 0))
    assert city.wealth == pytest.approx(40.0 - lent.get((CITY, 1), 0))
    assert guild.wealth == pytest.approx(20.0 - lent.get((GUILD, 0), 0))
    assert world.domestic_credit.merchant_due == pytest.approx([0.0] * len(world.regions))
    # The event names who funded it and the main lending region; the actors
    # stay the borrower alone (great merchants' crown loans read them).
    ev = next(e for e in events if e.event_type == "loan_taken" and e.actors == ["Thornwall Confederacy"])
    assert "the merchants of Verdant Plains" in ev.description
    assert ev.region == "Verdant Plains"
    # A city or guild that lent records the loan in its history.
    assert (world.turn - 1, "loan", ev.event_id) in city.history
    assert (world.turn - 1, "loan", ev.event_id) in guild.history


def test_a_lender_keeps_a_quarter_however_deep_credit_runs(monkeypatch):
    world, bridge, sim, city, guild = _borrowing_world(merchants=((VERDANT, 100.0),), city_purse=0.0,
                                                        guild_purse=0.0)
    monkeypatch.setattr(D, "_civ_factors", lambda w, i: 10.0)
    F._ensure(world)
    t = D.begin(world, bridge)
    civ = world.civilizations[THORNWALL]
    f = world.finance.civs[THORNWALL]
    _cap, lenders = t.capacity(THORNWALL, civ, f)
    assert lenders == [(MERCHANTS, VERDANT, 75)]
    # With claims already held, a lender offers its share of wealth plus
    # claims, less what it is owed.
    t.claims[(MERCHANTS, VERDANT)] = 50
    assert t.lenders(THORNWALL, civ, 1.0) == [(MERCHANTS, VERDANT, int(0.75 * 150 - 50))]
    monkeypatch.setattr(D, "_civ_factors", lambda w, i: 1.0)
    assert t.lenders(THORNWALL, civ, 1.0) == [(MERCHANTS, VERDANT, 25)]
    assert t.lenders(THORNWALL, civ, 0.2) == []   # 0.1 x 150 < 50: nothing more


def test_merchants_lend_only_where_there_are_merchants():
    world, bridge, sim, city, guild = _borrowing_world(city_purse=0.0, guild_purse=0.0)
    world.domestic_credit.merchant_due = [0.0] * len(world.regions)
    world.domestic_credit.merchant_due[THORNWOOD] = 30.0     # owed to departed merchants
    sim.merchants = [m for m in sim.merchants if m[0] != THORNWOOD]
    t = D.begin(world, bridge)
    lenders = t.lenders(THORNWALL, world.civilizations[THORNWALL], 1.0)
    assert [(k, key) for k, key, _ in lenders] == [(MERCHANTS, VERDANT)]


# ---------------------------------------------------------------------------
# Cash flows
# ---------------------------------------------------------------------------

def _with_a_loan(**kw):
    world, bridge, sim, city, guild = _borrowing_world(**kw)
    _tick(world, bridge, {THORNWALL: 5})
    loan = _domestic(world)
    assert loan is not None
    return world, bridge, sim, city, guild, loan


def test_interest_and_repayments_go_back_to_the_funders(checked):
    world, bridge, sim, city, guild, loan = _with_a_loan()
    line = _line(world, loan)
    before = {(fu.kind, fu.key): fu.principal for fu in line.funders}
    wealth = (sim.total(VERDANT), city.wealth, guild.wealth)
    totals = dict(world.finance.totals)
    world.civilizations[THORNWALL].treasury = 500     # pays its service in full
    _tick(world, bridge, {THORNWALL: 40})
    st = world.domestic_credit.totals
    interest = world.finance.totals["interest_domestic"] - totals["interest_domestic"]
    assert interest > 0
    assert sum(st[f"interest_{k}"] for k in D.KIND_NAMES) == interest
    paid = {k: before[k] - _claims(world, *k) for k in before}
    assert sum(paid.values()) > 0
    # Each funder got its share of the interest (on its claim before) and
    # the principal its claim fell by.
    got = sim.total(VERDANT) - wealth[0]
    expect = paid[(MERCHANTS, VERDANT)] + _interest_of(MERCHANTS, VERDANT, before, interest)
    assert got == pytest.approx(expect, abs=1e-9)
    assert city.wealth == pytest.approx(wealth[1] + paid[(CITY, 1)] + _interest_of(CITY, 1, before, interest))
    assert guild.wealth == pytest.approx(wealth[2] + paid[(GUILD, 0)] + _interest_of(GUILD, 0, before, interest))


def _interest_of(kind, key, before, interest):
    keys = list(before)
    return D.split(interest, [before[k] for k in keys])[keys.index((kind, key))]


def test_unpaid_interest_is_capitalized_into_the_claims(checked):
    world, bridge, sim, city, guild, loan = _with_a_loan()
    world.finance.civs[THORNWALL].domestic_trust = 0.0   # no refinancing at home
    for civ in world.civilizations:
        civ.treasury = 0
    held = sum(fu.principal for fu in _line(world, loan).funders)
    _tick(world, bridge, {})
    st = world.domestic_credit.totals
    cap = sum(st[f"capitalized_{k}"] for k in D.KIND_NAMES)
    assert cap > 0
    loan = _domestic(world)
    assert sum(fu.principal for fu in _line(world, loan).funders) == loan.principal == held + cap - sum(
        st[f"repaid_{k}"] for k in D.KIND_NAMES)


def test_prepayment_is_paid_to_the_funders(checked):
    world, bridge, sim, city, guild, loan = _with_a_loan()
    world.civilizations[THORNWALL].treasury = 100_000   # far above its reserve
    before = sum(fu.principal for fu in _line(world, loan).funders)
    _tick(world, bridge, {THORNWALL: 40})
    st = world.domestic_credit.totals
    assert sum(st[f"repaid_{k}"] for k in D.KIND_NAMES) == before   # repaid in full
    assert _domestic(world) is None
    assert world.domestic_credit.lines == []


def test_a_default_lands_on_the_lenders_with_grievance(checked):
    world, bridge, sim, city, guild, loan = _with_a_loan()
    civ = world.civilizations[THORNWALL]
    f = world.finance.civs[THORNWALL]
    f.domestic_trust = 0.0
    f.excluded_until = None
    influence = civ.factions.influence.get(FactionType.MERCHANT, 0.0)
    defaults, accs = [], []
    for _ in range(F.ARREARS_LIMIT + 2):
        for c in world.civilizations:
            c.treasury = 0
        events, acc = _tick(world, bridge, {})
        accs.append(acc)
        defaults += [e for e in events if e.event_type == "state_default"]
        if defaults:
            break
    assert len(defaults) == 1
    ev = defaults[0]
    st = world.domestic_credit
    lost = sum(st.totals[f"written_off_{k}"] for k in D.KIND_NAMES)
    assert lost > 0
    # The losses land on who lent: merchants' grievance in their regions,
    # the city's grievance, the repudiation in the histories.
    assert st.grievance[VERDANT] > 0
    assert city.grievance > 0
    assert any(kind == "repudiated" and eid == ev.event_id for _t, kind, eid in city.history)
    assert any(kind == "repudiated" and eid == ev.event_id for _t, kind, eid in guild.history)
    assert "the merchants of Verdant Plains" in ev.description
    assert st.defaults_on_lenders == 1
    # The existing domestic-default consequences are kept.
    assert any(ch.stat == "economy" and ch.delta == -F.DEFAULT_ECONOMY and ch.category == "signal"
               for ch in accs[-1]._changes if ch.civ_id == THORNWALL)
    assert civ.factions.influence.get(FactionType.MERCHANT, 0.0) < influence + 1e-9
    # For the guild the repudiation is a threat to its privileges.
    threats = world.guilds.counters["threats"]
    world.turn -= 1   # the guild tick of the same turn
    G.tick_guilds(world)
    assert world.guilds.counters["threats"] == threats + 1
    assert any(kind == "threat" and eid == ev.event_id for _t, kind, eid in guild.history)


def test_grievance_decays_and_reaches_the_region_batch():
    from chronicler.agent_bridge import build_region_batch
    world, bridge, sim, city, guild = _world()
    st = world.domestic_credit
    D._ensure(world)
    st.grievance[VERDANT] = 0.4
    batch = build_region_batch(world)
    column = batch.column("creditor_grievance").to_pylist()
    assert column[VERDANT] == pytest.approx(0.4) and column[THORNWOOD] == 0.0
    # Recomputed from persisted state for every batch (not consumed).
    assert build_region_batch(world).column("creditor_grievance").to_pylist() == column
    _tick(world, bridge, {THORNWALL: 30})
    assert st.grievance[VERDANT] == pytest.approx(0.4 * D.GRIEVANCE_DECAY)
    st.grievance[VERDANT] = D.GRIEVANCE_FLOOR
    _tick(world, bridge, {THORNWALL: 30})
    assert st.grievance[VERDANT] == 0.0
    # Off: no column at all.
    D.set_domestic_credit_enabled(world, False)
    assert "creditor_grievance" not in build_region_batch(world).schema.names


def test_a_fallen_borrower_loses_its_lenders_their_claims(checked):
    world, bridge, sim, city, guild, loan = _with_a_loan()
    held = {(fu.kind, fu.key): fu.principal for fu in _line(world, loan).funders}
    civ = world.civilizations[THORNWALL]
    for name in list(civ.regions):
        world.regions[[r.name for r in world.regions].index(name)].controller = None
    civ.regions = []
    events, _ = _tick(world, bridge, {})
    st = world.domestic_credit
    assert sum(st.totals[f"lost_{k}"] for k in D.KIND_NAMES) == sum(held.values())
    assert st.lines == []
    lost = next((e for e in events if e.event_type == "debt_written_off"), None)
    if sum(held.values()) >= F.MIN_LOAN:
        assert lost is not None and "the merchants of Verdant Plains" in lost.description


def test_a_fallen_citys_claim_lapses(checked):
    world, bridge, sim, city, guild, loan = _with_a_loan(city_purse=200.0)
    claim = _claims(world, CITY, 1)
    assert claim >= F.MIN_LOAN
    principal = loan.principal
    world.cities.cities.remove(city)
    city.fallen_turn = world.turn
    city.history.append((world.turn, "fell", "30:city_fell:1"))
    world.cities.fallen.append(city)
    world.civilizations[THORNWALL].treasury = 0
    world.finance.civs[THORNWALL].domestic_trust = 0.0
    events, _ = _tick(world, bridge, {})
    assert world.domestic_credit.totals["lapsed_city"] == claim
    lapse = next(e for e in events if e.event_type == "debt_written_off")
    assert "Thornwood Settlement 1" in lapse.description and "30:city_fell:1" in lapse.causes
    loan = _domestic(world)
    assert loan is None or loan.principal < principal


# ---------------------------------------------------------------------------
# The native transfer protocol and the books
# ---------------------------------------------------------------------------

def test_merchant_due_is_sent_once_and_carried_when_it_cannot_be_applied(checked):
    world, bridge, sim, city, guild, loan = _with_a_loan(city_purse=0.0, guild_purse=0.0,
                                                          merchants=((THORNWOOD, 80.0),))
    st = world.domestic_credit
    assert st.merchant_due[THORNWOOD] == pytest.approx(0.0)
    lent = st.totals["lent_merchants"]
    assert sim.calls and sim.calls[-1][0] == [THORNWOOD] and sim.calls[-1][1][0] == -lent
    # The merchants leave: what they are paid stays due, sent again each turn.
    departed = list(sim.merchants)
    sim.merchants = []
    world.civilizations[THORNWALL].treasury = 500
    _tick(world, bridge, {THORNWALL: 40})
    owed = st.merchant_due[THORNWOOD]
    assert owed > 0
    calls = len(sim.calls)
    _tick(world, bridge, {THORNWALL: 40})
    assert st.merchant_due[THORNWOOD] >= owed
    assert len(sim.calls) == calls + 1      # one transfer call a tick, not more
    # They come back: the due is applied once and cleared.
    sim.merchants = departed
    owed = st.merchant_due[THORNWOOD]
    wealth = sim.total(THORNWOOD)
    for c in world.civilizations:
        c.treasury = 0
    _tick(world, bridge, {})
    flows = st.totals["interest_merchants"] + st.totals["repaid_merchants"] - st.totals["lent_merchants"]
    assert st.merchant_applied + sum(st.merchant_due) == pytest.approx(flows)
    assert sim.total(THORNWOOD) > wealth
    # A tick with nothing due sends nothing.
    st.merchant_due = [0.0] * len(world.regions)
    D.set_domestic_credit_enabled(world, True)
    t = D.begin(world, bridge)
    calls = len(sim.calls)
    t.finish()
    assert len(sim.calls) == calls
    assert owed >= 0


def test_the_ledger_balances_over_a_run_and_catches_a_broken_book(checked):
    world, bridge, sim, city, guild, loan = _with_a_loan()
    for turn in range(12):
        world.civilizations[THORNWALL].treasury = [0, 40, 500][turn % 3]
        _tick(world, bridge, {THORNWALL: 20 + turn})
    loan = _domestic(world)
    if loan is None:
        world.civilizations[THORNWALL].treasury = 0
        _tick(world, bridge, {THORNWALL: 30})
        loan = _domestic(world)
    assert loan is not None
    _line(world, loan).funders[0].principal += 1
    with pytest.raises(AssertionError, match="credit ledger does not balance"):
        _tick(world, bridge, {THORNWALL: 30})


def test_a_carried_rounding_residual_is_not_an_overdraft(checked):
    world, bridge, sim, city, guild, loan = _with_a_loan()
    st = world.domestic_credit
    # The native pool applied a debit a hair short (f32 rounding) and the
    # merchants then left: the residual waits in the due.
    sim.merchants = [m for m in sim.merchants if m[0] != THORNWOOD]
    st.merchant_due[THORNWOOD] = -2e-6
    for _ in range(3):
        world.civilizations[THORNWALL].treasury = 40
        _tick(world, bridge, {THORNWALL: 30})
    assert st.merchant_due[THORNWOOD] > -1e-5   # what they are paid now waits for them too


def test_finance_books_balance_with_domestic_credit():
    world, bridge, sim, city, guild, loan = _with_a_loan()
    for _ in range(6):
        _tick(world, bridge, {THORNWALL: 25})
    t = world.finance.totals
    outstanding = sum(loan.principal for loan in world.finance.loans)
    assert outstanding == (t["issued_domestic"] + t["issued_foreign"] + t["capitalized"]
                           - t["repaid_principal"] - t["written_off"])
    for line in world.domestic_credit.lines:
        loan = next(ln for ln in world.finance.loans if ln.loan_id == line.loan_id)
        assert sum(fu.principal for fu in line.funders) == loan.principal


def test_lines_lent_before_the_switch_belong_to_the_creditor_class(checked):
    world, bridge, sim, city, guild = _borrowing_world()
    D.set_domestic_credit_enabled(world, False)
    _tick(world, None, {THORNWALL: 30})          # the abstract creditor class lends
    loan = _domestic(world)
    assert loan is not None
    D.set_domestic_credit_enabled(world, True)
    world.civilizations[THORNWALL].treasury = 60    # its service, no prepayment
    _tick(world, bridge, {THORNWALL: 40})
    line = next(ln for ln in world.domestic_credit.lines if ln.loan_id == loan.loan_id)
    assert [fu.kind for fu in line.funders] == [LEGACY]
    assert world.domestic_credit.totals["interest_legacy"] > 0
    assert sum(fu.principal for fu in line.funders) == _domestic(world).principal


def test_domestic_credit_never_runs_while_off(monkeypatch):
    world = generate_world(seed=42)
    F.set_finance_enabled(world, True)
    assert not D.domestic_credit_enabled(world)
    monkeypatch.setattr(D, "begin", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    for c in world.civilizations:
        c.treasury = 0
    for _ in range(5):
        _tick(world, None, {0: 10, 1: 10, 2: 10, 3: 10})
    assert D.region_grievances(world) is None


def test_save_load_resume_identity_with_outstanding_lines():
    def run(split_at: int | None):
        world, bridge, sim, city, guild, loan = _with_a_loan()
        for turn in range(10):
            if split_at is not None and turn == split_at:
                world = WorldState.model_validate_json(world.model_dump_json())
                city = world.cities.cities[0]
            world.civilizations[THORNWALL].treasury = [0, 30, 200][turn % 3]
            _tick(world, bridge, {THORNWALL: 20})
        return world.model_dump_json(), sim.merchants

    straight, w1 = run(None)
    resumed, w2 = run(4)
    assert straight == resumed
    assert w1 == w2


# ---------------------------------------------------------------------------
# Switch, wiring, snapshot
# ---------------------------------------------------------------------------

def test_switch_is_off_by_default_dormant_and_omitted():
    assert D.DEFAULT_ENABLED_FOR_NEW_WORLDS is False
    world = WorldState(name="w", seed=1)
    assert not D.domestic_credit_enabled(world)
    assert "domestic_credit" not in json.loads(world.model_dump_json())
    D.set_domestic_credit_enabled(world, True)
    dumped = json.loads(world.model_dump_json())
    assert "domestic_credit" in dumped
    assert WorldState.model_validate_json(world.model_dump_json()).domestic_credit is not None
    D.set_domestic_credit_enabled(world, False)
    assert "domestic_credit" not in json.loads(world.model_dump_json())
    assert not D.domestic_credit_enabled(SimpleNamespace(domestic_credit="yes"))


def test_cli_parses_the_switch_and_the_manifest_and_checkpoints_record_it():
    from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
    from chronicler.main import _build_parser
    from chronicler.run_checkpoint import feature_flags

    parser = _build_parser()
    assert parser.parse_args([]).domestic_credit is None
    assert parser.parse_args(["--domestic-credit"]).domestic_credit is True
    assert parser.parse_args(["--no-domestic-credit"]).domestic_credit is False
    assert "domestic_credit" in SIMULATION_ARG_KEYS
    assert simulation_config(parser.parse_args(["--domestic-credit"]))["domestic_credit"] is True
    world = WorldState(name="w", seed=1)
    assert feature_flags(world)["domestic_credit"] is False
    D.set_domestic_credit_enabled(world, True)
    assert feature_flags(world)["domestic_credit"] is True


def _cli(tmp_path, **kw):
    base = dict(seed=42, turns=3, civs=4, regions=8, output=str(tmp_path / "chronicle.md"),
                state=str(tmp_path / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
                scenario=None, pause_every=None, simulate_only=True, agents="off")
    base.update(kw)
    return argparse.Namespace(**base)


def test_an_explicit_switch_needs_finance_and_an_agent_pool(tmp_path):
    from chronicler.main import execute_run
    with pytest.raises(ValueError, match="requires an agent pool"):
        execute_run(_cli(tmp_path / "a", domestic_credit=True))
    with pytest.raises(ValueError, match="--finance"):
        execute_run(_cli(tmp_path / "b", domestic_credit=True, finance=False, agents="hybrid"))


def test_new_worlds_default_off_and_a_resume_keeps_the_saved_setting(tmp_path):
    from chronicler.main import execute_run
    fresh = tmp_path / "fresh"
    execute_run(_cli(fresh))
    assert "domestic_credit" not in json.loads((fresh / "state.json").read_text())
    # A saved setting stays on when resumed without the flag, even with
    # --agents off (its books are kept; merchants without a pool lend nothing).
    state = json.loads((fresh / "state.json").read_text())
    state["domestic_credit"] = {}
    (fresh / "saved.json").write_text(json.dumps(state))
    resumed = _cli(fresh, turns=5, resume=str(fresh / "saved.json"), state=str(fresh / "resumed.json"))
    execute_run(resumed)
    assert "domestic_credit" in json.loads((fresh / "resumed.json").read_text())


def test_live_new_worlds_follow_the_default():
    text = (ROOT / "src" / "chronicler" / "live.py").read_text()
    assert "set_domestic_credit_enabled" in text


def _load_runner():
    import importlib.util
    path = ROOT / "scripts" / "m53b_run_validation.py"
    spec = importlib.util.spec_from_file_location("m53b_run_validation_credit", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def test_gate_runner_forwards_the_switch_to_agent_runs_only():
    runner = _load_runner()
    ns = argparse.Namespace
    assert runner._domestic_credit_args(ns(domestic_credit=None)) == []
    assert runner._domestic_credit_args(ns(domestic_credit=True)) == ["--domestic-credit"]
    assert runner._domestic_credit_args(ns(domestic_credit=False)) == ["--no-domestic-credit"]
    assert runner._domestic_credit_args(ns()) == []
    args = ns(domestic_credit=True, community_anchoring=None, worldgen=None, regions=None, civs=None,
              parallel=3)
    assert runner._determinism_manifest_args(args, "off").domestic_credit is None
    assert runner._determinism_manifest_args(args, "hybrid").domestic_credit is True


def test_snapshot_summary_and_metrics():
    world, bridge, sim, city, guild, loan = _with_a_loan()
    D.region_grievances(world)
    world.domestic_credit.grievance[VERDANT] = 0.2
    row = D.snapshot_summary(world)
    assert row["claims"]["merchants"] == _claims(world, MERCHANTS, VERDANT) + _claims(world, MERCHANTS, THORNWOOD)
    assert row["civs"]["Thornwall Confederacy"]["merchants"] > 0
    assert row["grievance"] == {"Verdant Plains": 0.2}
    assert F.snapshot_summary(world)["domestic_credit"] == row
    bundle = {"history": [{"finance": {"domestic_credit": row}}],
              "world_state": {"domestic_credit": world.domestic_credit.model_dump()}}
    metrics = D.extract_domestic_credit_metrics([bundle])
    assert metrics["runs"] == 1 and metrics["peak_claims"] == loan.principal
    assert sum(metrics["claim_share"].values()) == pytest.approx(1.0)
    assert D.extract_domestic_credit_metrics([{"history": [{}]}]) == {}


def test_funder_model_round_trips():
    f = Funder(kind=CITY, key=7, principal=3)
    assert Funder.model_validate_json(f.model_dump_json()) == f
