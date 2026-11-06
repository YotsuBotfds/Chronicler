"""PL3 maintenance obligation without the native extension: the real L9
decision (``local_budgets._decide``) on the L9 test world with an open RS2
granary project, and RS2's execution against a reservation on the recovery
crews test world."""
from __future__ import annotations

import pickle
from types import SimpleNamespace

import pytest

from chronicler import livelihoods as LV
from chronicler import local_budgets as LB
from chronicler import maintenance_obligation as MO
from chronicler import repair_projects as RP
from chronicler.local_budgets_state import Commitment, Decision, LocalBudgetState
from chronicler.maintenance_obligation_state import MaintenanceObligationState, ReservationUse
from tests import test_local_budgets as l9
from tests import test_recovery_crews as rc

VERDANT, THORNWALL = l9.VERDANT, l9.THORNWALL


@pytest.fixture(autouse=True)
def _no_commitments(monkeypatch):
    monkeypatch.setattr(RP, "_commitments", lambda world, sim: {})


def _decide(world):
    """L9's Phase 10 decision, then this package's Phase 10 (it runs after
    L9's in the switch order) committing the staged reservations."""
    l9._decide(world)
    if world.livelihoods.maintenance_obligation is not None and MO.maintenance_obligation_active(world):
        MO.phase10(world, None, None, None)


def _l9_world(*, mode=None, treasury=None, budget_mode="bargained"):
    world = l9._world(mode=budget_mode)
    if treasury is not None:
        world.civilizations[THORNWALL].treasury = treasury
    RP.set_repair_projects_enabled(world, True, args=None)
    RP.phase10_before_reserves(world, None, None, None)
    assert [(p.kind, p.region) for p in world.livelihoods.repair_projects.projects] == [("granary", VERDANT)]
    if mode is not None:
        MO.set_maintenance_obligation_enabled(world, True, args=SimpleNamespace(maintenance_obligation_mode=mode))
    return world


def _decision(world):
    return next(d for d in world.livelihoods.local_budgets.decisions if d.civ == THORNWALL)


def _repairs(decision):
    return [p for p in decision.proposals if p.service == "repairs"]


# ---------------------------------------------------------------------------
# The decision: reserved before the budget, capped, the proposal beyond it
# ---------------------------------------------------------------------------

def test_l9_alone_proposes_the_full_repairs_cost_and_reserves_nothing():
    world = _l9_world()
    _decide(world)
    d = _decision(world)
    assert "maintenance" not in d.reserved and d.budget == 10
    (p,) = _repairs(d)
    assert p.cost == 8 and p.expected == pytest.approx(4.0)     # 4 work at 2 coins
    assert "maintenance_obligation" not in LV.livelihoods_snapshot_fields(world)["livelihoods"]


def test_the_reservation_is_capped_at_a_share_of_the_budget_and_the_proposal_asks_the_rest():
    world = _l9_world(mode="reserve")
    _decide(world)
    d = _decision(world)
    # Budget without it: floor(0.25 x (60 - 20)) = 10; the cap is half of it.
    assert d.reserved == {"maintenance": 5} and d.obligations == 5
    assert d.budget == int(0.25 * (60 - 20 - 5))
    (p,) = _repairs(d)
    assert p.cost == 3 and p.expected == pytest.approx(4.0 * 3 / 8) and p.detail["reserved"] == 5
    state = world.livelihoods.maintenance_obligation
    (row,) = [r for r in state.decisions if r.civ == THORNWALL]
    assert (row.planned, row.budget_before, row.cap, row.reserved) == (8, 10, 5, 5)
    assert state.counters["cap_binding"] >= 1 and state.decision_turn == world.turn
    world.turn += 1                               # the next turn's snapshot shows this decision
    snap = LV.livelihoods_snapshot_fields(world)["livelihoods"]["maintenance_obligation"]
    assert [d["reserved"] for d in snap["decisions"] if d["civ"] == THORNWALL] == [5]
    assert snap["uses"] is None


def test_an_uncapped_reservation_covers_the_planned_charges_and_no_proposal_remains():
    world = _l9_world(mode="reserve", treasury=200)
    _decide(world)
    d = _decision(world)
    assert d.reserved == {"maintenance": 8}
    assert _repairs(d) == []
    assert d.budget == int(0.25 * (200 - 20 - 8))


def test_reserve_only_reserves_the_same_and_keeps_the_full_proposal():
    a, b = _l9_world(mode="reserve"), _l9_world(mode="reserve_only")
    for w in (a, b):
        _decide(w)
    da, db = _decision(a), _decision(b)
    assert da.reserved == db.reserved == {"maintenance": 5} and da.budget == db.budget
    (p,) = _repairs(db)
    assert p.cost == 8 and "reserved" not in p.detail


def test_fixed_shares_also_reserves_first():
    world = _l9_world(mode="reserve", budget_mode="fixed_shares")
    _decide(world)
    assert _decision(world).reserved == {"maintenance": 5}


def test_a_suspended_granary_reserves_nothing():
    """The RS2 correction: a granary project in a region without farm labour
    is not proposed and has no planned charge to reserve."""
    world = _l9_world(mode="reserve")
    world.livelihoods.repair_projects._labour = (world.turn, [0 if r == VERDANT else 5
                                                               for r in range(len(world.regions))])
    _decide(world)
    d = _decision(world)
    assert "maintenance" not in d.reserved and _repairs(d) == []


# ---------------------------------------------------------------------------
# Execution: RS2 within envelope plus reservation (reserve) or the envelope
# alone (reserve_only); the books close
# ---------------------------------------------------------------------------

def _budgets(world, *, reserved, envelope):
    state = world.livelihoods.local_budgets = LocalBudgetState()
    state.decision_turn = world.turn - 1
    state.decisions = [Decision(turn=world.turn - 1, civ=0, mode="bargained", projected=0, floor=20,
                                obligations=reserved, reserved={"maintenance": reserved} if reserved else {},
                                committed=0, budget=0)]
    if envelope is not None:
        state.open = [Commitment(cid=0, civ=0, service="repairs", pid=0, decided_turn=world.turn - 1,
                                 for_turn=world.turn, claims=["repairs:0"], amount=envelope, unit="work",
                                 expected=4.0 * envelope / 8, detail={"cost": envelope})]
    return state


@pytest.fixture
def settle_only(monkeypatch):
    """L9's Phase 10 settles the envelopes; its next decision needs a full
    economy observation and is tested above."""
    settled = []

    def phase10(world, acc=None, economy_result=None, agent_bridge=None):
        state = world.livelihoods.local_budgets
        obs = SimpleNamespace(economy=economy_result, turn=world.turn, trace={})
        events = LB._settle(world, state, obs, LB._providers())
        settled.extend(state.settled)
        return events

    monkeypatch.setattr(LB, "phase10", phase10)
    return settled


def _exec_world(mode):
    world = rc._world(crews=None)
    MO.set_maintenance_obligation_enabled(world, True, args=SimpleNamespace(maintenance_obligation_mode=mode))
    return world


@pytest.mark.usefixtures("settle_only")
def test_reserve_spends_the_reservation_first_and_the_envelope_settles_its_part(settle_only):
    world = _exec_world("reserve")
    sim = rc._Sim(rc._people())
    rc._open(world, sim)
    _budgets(world, reserved=5, envelope=3)
    rc._turn(world, sim)
    (rr,) = world.livelihoods.repair_projects.receipts
    assert rr.delivered == pytest.approx(4.0) and rr.envelope == 8          # the limit: 3 + 5
    (ledger,) = world.livelihoods.repair_projects.ledger
    assert ledger.charged == 8
    state = world.livelihoods.maintenance_obligation
    (use,) = state.uses
    assert use == ReservationUse(turn=5, civ=0, reserved=5, envelope=3, charged=8, used=5, returned=0,
                                 envelope_spent=3)
    (c,) = settle_only
    assert (c.outcome, c.spent, c.detail["reservation_used"]) == ("kept", 3, 5)
    assert c.delivered == pytest.approx(4.0 * 3 / 8)
    assert state.counters["used_coins"] == 5 and state.counters["returned_coins"] == 0


@pytest.mark.usefixtures("settle_only")
def test_reserve_only_is_held_to_its_envelope_and_returns_the_reservation(settle_only):
    world = _exec_world("reserve_only")
    sim = rc._Sim(rc._people())
    rc._open(world, sim)
    _budgets(world, reserved=5, envelope=3)
    treasury = world.civilizations[0].treasury
    rc._turn(world, sim)
    (rr,) = world.livelihoods.repair_projects.receipts
    assert rr.envelope == 3 and "no_envelope" in rr.reasons and rr.delivered == pytest.approx(1.5)
    (use,) = world.livelihoods.maintenance_obligation.uses
    assert (use.reserved, use.used, use.returned, use.charged, use.envelope_spent) == (5, 0, 5, 3, 3)
    (c,) = settle_only
    assert c.spent == 3 and "reservation_used" not in c.detail
    # The returned reservation never left the treasury (only storage of the
    # other granaries and the 3 repair coins did).
    assert treasury - world.civilizations[0].treasury >= 3


@pytest.mark.usefixtures("settle_only")
def test_a_reservation_without_an_envelope_funds_repairs_alone(settle_only):
    world = _exec_world("reserve")
    sim = rc._Sim(rc._people())
    rc._open(world, sim)
    _budgets(world, reserved=4, envelope=None)
    rc._turn(world, sim)
    (rr,) = world.livelihoods.repair_projects.receipts
    assert rr.envelope == 4 and rr.delivered == pytest.approx(2.0) and "no_envelope" in rr.reasons
    (use,) = world.livelihoods.maintenance_obligation.uses
    assert (use.reserved, use.used, use.returned, use.envelope_spent) == (4, 4, 0, 0)
    assert settle_only == []


@pytest.mark.usefixtures("settle_only")
def test_unspent_reservation_is_returned_when_repairs_fall_short(settle_only):
    world = _exec_world("reserve")
    sim = rc._Sim(rc._people())
    rc._open(world, sim)
    _budgets(world, reserved=6, envelope=2)
    world.regions[0].stockpile.goods["timber"] = 1.0              # only one work unit of timber
    rc._turn(world, sim)
    (use,) = world.livelihoods.maintenance_obligation.uses
    assert (use.charged, use.used, use.returned, use.envelope_spent) == (2, 2, 4, 0)
    (c,) = settle_only
    assert c.outcome == "deferred" and c.spent == 0 and c.reason == "inputs_short"


def test_closure_check_refuses_unbalanced_rows():
    MO.check_use(ReservationUse(turn=1, civ=0, reserved=5, charged=8, used=5, returned=0, envelope_spent=3))
    for bad in (dict(returned=1), dict(envelope_spent=2), dict(envelope=2)):
        row = dict(turn=1, civ=0, reserved=5, envelope=3, charged=8, used=5, returned=0, envelope_spent=3)
        row.update(bad)
        with pytest.raises(RuntimeError):
            MO.check_use(ReservationUse(**row))


def test_a_failed_phase2_records_nothing(settle_only):
    world = _exec_world("reserve")
    sim = rc._Sim(rc._people())
    rc._open(world, sim)
    _budgets(world, reserved=5, envelope=3)
    before = world.livelihoods.maintenance_obligation.model_dump_json()
    with pytest.raises(RuntimeError, match="economy failed"):
        rc._turn(world, sim, fail_economy=True)
    state = world.livelihoods.maintenance_obligation
    assert state._turn is None and state.model_dump_json() == before
    assert MO.reservation_used(world, 0) == 0


# ---------------------------------------------------------------------------
# Switch, persistence, feature off
# ---------------------------------------------------------------------------

def test_prerequisites_and_modes():
    world = _l9_world()
    LV.configure_livelihoods(world, rc._parse("--maintenance-obligation", "--maintenance-obligation-mode",
                                              "reserve_only"), agent_mode="hybrid")
    assert world.livelihoods.maintenance_obligation.mode == "reserve_only"
    assert MO.maintenance_obligation_active(world)
    no_l9 = rc._world(crews=None)
    with pytest.raises(ValueError, match="--maintenance-obligation requires"):
        LV.configure_livelihoods(no_l9, rc._parse("--maintenance-obligation"), agent_mode="hybrid")
    world = _l9_world()
    RP.set_repair_projects_enabled(world, False)
    with pytest.raises(ValueError, match="--maintenance-obligation requires"):
        LV.configure_livelihoods(world, rc._parse("--maintenance-obligation"), agent_mode="hybrid")


def test_feature_off_decisions_are_identical_and_hold_no_state():
    a, b = _l9_world(), _l9_world()
    LV.configure_livelihoods(b, rc._parse("--no-maintenance-obligation"), agent_mode="hybrid")
    for w in (a, b):
        _decide(w)
    assert b.livelihoods.maintenance_obligation is None
    assert a.livelihoods.local_budgets.model_dump_json() == b.livelihoods.local_budgets.model_dump_json()
    # Switched off after it ran: the provider reserves nothing again.
    c = _l9_world(mode="reserve")
    MO.set_maintenance_obligation_enabled(c, False)
    _decide(c)
    assert "maintenance" not in _decision(c).reserved
    assert "maintenance_obligation" not in LV.livelihoods_snapshot_fields(c)["livelihoods"]


def test_state_pickles_exactly_and_drops_what_is_staged():
    world = _l9_world(mode="reserve")
    _decide(world)
    state = world.livelihoods.maintenance_obligation
    state._staged = (world.turn, {})
    state._turn = MO._Turn(world.turn)
    back = pickle.loads(pickle.dumps(state))
    assert back.model_dump() == state.model_dump() and back._staged is None and back._turn is None
    assert MaintenanceObligationState.model_validate_json(state.model_dump_json()).model_dump() == state.model_dump()
    whole = pickle.loads(pickle.dumps(world.livelihoods))
    assert whole.maintenance_obligation.model_dump() == state.model_dump()
