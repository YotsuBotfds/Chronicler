"""D1c dated local organization; real money seam with a bounded fake native pool."""
import copy
import pickle
from types import SimpleNamespace as NS

import pyarrow as pa
import pytest

from chronicler import money, movement_branches as MB
from chronicler.agent_movements_state import Movement, MovementState
from chronicler.movement_branches_state import MovementBranchesState


class Sim:
    def __init__(self, people):
        # id -> (region, age, membership, wealth)
        self.people = dict(people)
        self.trips = set()
        self.transfers = []
        self.installed = []
        self.cancelled = []

    def get_snapshot(self):
        ids = sorted(self.people)
        return pa.record_batch({"id": ids, "region": [self.people[a][0] for a in ids],
                                "age": [self.people[a][1] for a in ids],
                                "movement_id": [self.people[a][2] for a in ids],
                                "wealth": [self.people[a][3] for a in ids]})

    def trip_agent_ids(self):
        return sorted(self.trips)

    def wealth_transfer_purposes(self):
        return money.NATIVE_PURPOSES

    def transfer_wealth(self, turn, purpose, batch, rows):
        self.transfers.append((turn, purpose, batch, list(rows)))
        out = []
        for aid, milli in rows:
            region, age, mid, wealth = self.people[aid]
            assert milli <= 0 and wealth * 1000 + milli >= 0
            self.people[aid] = region, age, mid, wealth + milli / 1000
            out.append((aid, milli, milli, 0, 0))
        return out

    def set_movement_branches(self, source, target, ids, hosts):
        self.installed.append((source, target, ids, hosts))

    def cancel_movement_branches(self, turn):
        self.cancelled.append(turn)


@pytest.fixture
def world(monkeypatch):
    # The lead owns append-only shared registrations. These fixture-only
    # declarations isolate this module's contract until integration lands.
    from chronicler.wealth_accounting_state import MONEY_PURPOSE_CHANNELS
    monkeypatch.setitem(money.NATIVE_ALIASES, "branch_dues", "remittance")
    monkeypatch.setitem(money.PURPOSES, "branch_dues", money.NATIVE_PURPOSES.index("remittance"))
    monkeypatch.setitem(MONEY_PURPOSE_CHANNELS, "branch_dues", "branch_dues")
    movement = Movement(name="Commons", creed=0, founded_turn=0, home_region=0, target=0)
    return NS(turn=4, agent_mode="hybrid", active_wars=[], epidemics=None,
              civilizations=[NS(name="Home", regions=["Home field"], treasury=10),
                             NS(name="Host", regions=["Host field"], treasury=10)],
              regions=[NS(name="Home field", controller="Home"), NS(name="Host field", controller="Host")],
              agent_movements=MovementState(movements=[movement]),
              livelihoods=NS(movement_branches=MovementBranchesState()))


def _sim(n=4):
    return Sim({a: (1, 30, 1, 1.0) for a in range(1, n + 1)})


def _tick(world, sim):
    MB.phase10(world, agent_bridge=NS(_sim=sim))
    return world.livelihoods.movement_branches.frame.rows


def test_actual_named_dues_reach_host_treasury_carry_and_activate_next_tick(world):
    sim = _sim()
    (row,) = _tick(world, sim)
    assert row.status == "funded" and row.active_from == 5
    assert row.payers == [1, 2, 3, 4] and row.dues_milli == 40
    assert sum(p[3] for p in sim.people.values()) == pytest.approx(3.96)
    state = world.livelihoods.movement_branches
    assert state.book.carry["1:branch_dues"] == 40
    assert world.civilizations[1].treasury == 10
    money.check_book(state.book)
    with pytest.raises(RuntimeError, match="same-turn"):
        MB.read_frame(world, consumer_turn=4)
    world.turn = 5
    MB.before_agent_tick(world, NS(_sim=sim), None)
    assert sim.installed == [(4, 5, [1], [1])]
    # A copy cannot arm the native pass by changing the persisted receipt.
    frame = MB.read_frame(world, consumer_turn=5)
    frame.rows[0].status = "empty"
    assert state.frame.rows[0].status == "funded"
    MB.rollback_agent_tick(world, NS(_sim=sim))
    assert sim.cancelled == [5]


def test_no_children_trips_or_same_polity_and_no_anonymous_member_fill(world):
    sim = _sim()
    sim.people.update({5: (1, 15, 1, 2.0), 6: (0, 30, 1, 2.0), 7: (1, 30, 0, 2.0)})
    sim.trips.add(1)
    (row,) = _tick(world, sim)
    assert row.members == 3 and row.payers == [2, 3, 4]
    assert {a for *_, rows in sim.transfers for a, _ in rows} == {2, 3, 4}


@pytest.mark.parametrize("mode", ["record_only", "cost_only"])
def test_controls_separate_observation_and_real_cost_from_native_permission(world, mode):
    world.livelihoods.movement_branches.mode = mode
    sim = _sim()
    (row,) = _tick(world, sim)
    assert row.status == mode and row.active_from is None
    assert bool(sim.transfers) == (mode == "cost_only")
    world.turn += 1
    MB.before_agent_tick(world, NS(_sim=sim), None)
    assert sim.installed == []


def test_poor_or_too_small_group_pays_nothing(world):
    sim = _sim(3)
    sim.people[1] = (1, 30, 1, 0.001)
    (row,) = _tick(world, sim)
    assert row.status == "poor" and not sim.transfers
    world.turn += 1
    sim.people.pop(1)
    (row,) = _tick(world, sim)
    assert row.status == "too_few" and not sim.transfers


def test_hostility_and_quarantine_block_funding_and_delivery(world, monkeypatch):
    sim = _sim()
    world.active_wars = [("Home", "Host")]
    (row,) = _tick(world, sim)
    assert row.status == "hostile" and not sim.transfers
    world.turn += 1
    world.active_wars = []
    monkeypatch.setattr("chronicler.quarantine_rules.closed_pairs", lambda _: {("Home", "Host")})
    (row,) = _tick(world, sim)
    assert row.status == "quarantined" and not sim.transfers
    world.turn += 1
    monkeypatch.setattr("chronicler.quarantine_rules.closed_pairs", lambda _: set())
    (row,) = _tick(world, sim)
    assert row.status == "funded"
    world.turn += 1
    world.active_wars = [("Home", "Host")]
    MB.before_agent_tick(world, NS(_sim=sim), None)
    assert sim.installed[-1] == (6, 7, [], [])


def test_identity_is_never_reused_and_paying_or_observing_twice_refuses(world):
    sim = _sim()
    _tick(world, sim)
    with pytest.raises(RuntimeError, match="already settled"):
        _tick(world, sim)
    world.turn += 1
    for a, (r, age, mid, w) in list(sim.people.items()):
        sim.people[a] = (0, age, mid, w)
    assert _tick(world, sim)[0].status == "empty"
    world.turn += 1
    for a, (r, age, mid, w) in list(sim.people.items()):
        sim.people[a] = (1, age, mid, w)
    assert _tick(world, sim)[0].branch == 1
    assert world.livelihoods.movement_branches.next_branch == 2


def test_exact_python_restore_preserves_funded_frame_and_book(world):
    sim = _sim()
    _tick(world, sim)
    restored = pickle.loads(pickle.dumps(world))
    sim2 = copy.deepcopy(sim)
    for w, s in ((world, sim), (restored, sim2)):
        w.turn += 1
        MB.before_agent_tick(w, NS(_sim=s), None)
        _tick(w, s)
    assert world.livelihoods.movement_branches.model_dump() == restored.livelihoods.movement_branches.model_dump()
    assert sim.installed == sim2.installed and sim.people == sim2.people


def test_reader_rejects_dates_malformed_paid_ids_and_unobserved_is_not_zero(world):
    sim = _sim()
    _tick(world, sim)
    world.turn += 1
    snapshot = {"turn": world.turn, "livelihoods": {"movement_branches": MB.snapshot_summary(world)}}
    assert MB.record_status(snapshot)[0] == "recorded"
    malformed = copy.deepcopy(snapshot)
    malformed["livelihoods"]["movement_branches"]["frame"]["rows"][0]["payers"][1] = 1
    assert MB.record_status(malformed) == ("malformed", None)
    malformed = copy.deepcopy(snapshot)
    malformed["livelihoods"]["movement_branches"]["source_turn"] += 1
    assert MB.record_status(malformed) == ("malformed", None)
    assert MB.record_status({"livelihoods": []}) == ("malformed", None)
    world.turn += 1
    assert MB.snapshot_summary(world)["frame"] is None
    with pytest.raises(RuntimeError, match="own turn"):
        MB.read_frame(world, consumer_turn=world.turn - 1)
    assert MB.read_frame(world, consumer_turn=world.turn) is None


def test_legacy_pool_reset_clears_old_payer_ids_but_preserves_branch_identity(world):
    _tick(world, _sim())
    MB.on_pool_reset(world)
    state = world.livelihoods.movement_branches
    assert state.frame is None and state.frame_turn is None
    assert state.next_branch == 2 and state.branches[0].branch == 1


def test_total_named_fee_limit_keeps_all_flows_and_money_closes_across_whole_coin_credit(world):
    world.agent_movements.movements = [world.agent_movements.movements[0].model_copy(deep=True) for _ in range(20)]
    sim = Sim({a: (1, 30, (a - 1) // 32 + 1, 1.0) for a in range(1, 641)})
    rows = _tick(world, sim)
    assert sum(len(row.payers) for row in rows) == 512
    assert sum(row.status == "funded" for row in rows) == 16
    assert sum(row.status == "capacity" for row in rows) == 4
    book = world.livelihoods.movement_branches.book
    assert len(book.flows) == 512 and book.flows_dropped == 0
    assert world.civilizations[1].treasury == 15 and book.carry["1:branch_dues"] == 120
    assert 640 - sum(p[3] for p in sim.people.values()) == pytest.approx(5.12)
    money.check_book(book)


def test_lifetime_identity_capacity_refuses_new_branch_without_reusing_an_id(world):
    from chronicler.movement_branches_state import Branch, MAX_BRANCHES
    state = world.livelihoods.movement_branches
    state.branches = [Branch(branch=i, movement=i, host=1, first_turn=0) for i in range(1, MAX_BRANCHES + 1)]
    state.next_branch = MAX_BRANCHES + 1
    world.agent_movements.movements = [world.agent_movements.movements[0].model_copy(deep=True)
                                       for _ in range(MAX_BRANCHES + 1)]
    sim = Sim({1: (1, 30, MAX_BRANCHES + 1, 1.0)})
    _tick(world, sim)
    assert state.frame.new_identities_refused == 1 and state.next_branch == MAX_BRANCHES + 1
    assert len(state.branches) == MAX_BRANCHES and not sim.transfers
