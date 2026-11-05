"""L7 costly voluntary relocation: offline settlement contract (no native extension).

A small fake stands in for the native policy, gate receipt and wealth
transfer with the rules of ``chronicler-agents/src/relocation.rs`` and
``wealth_transfer.rs``; the real-native path is in
``test_relocation_costs_native.py``.
"""
from __future__ import annotations

import json
import pickle

import pytest

from chronicler import relocation_costs as R
from chronicler.livelihoods import configure_livelihoods, livelihoods_snapshot_fields
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.main import _build_parser
from chronicler.relocation_costs_state import COUNTERS, GATE_REASONS, MODES, RelocationCostsState
from chronicler.world_gen import generate_world


class FakeSim:
    """Policy, gate receipts and the wealth transfer over a dict of people."""

    def __init__(self, wealth: dict[int, int]):
        self.wealth = dict(wealth)          # id -> milli
        self.alive = set(wealth)
        self.policy = None
        self.receipt = None
        self.keys = set()

    def set_relocation_policy(self, turn, fare, assist, payers, budgets, track):
        assert self.policy is None
        self.policy = {"turn": turn, "fare": fare, "assist": assist, "payers": list(payers),
                       "budgets": list(budgets), "track": list(track)}

    def cancel_relocation_policy(self):
        had, self.policy = self.policy is not None, None
        return had

    def tick(self, households, n_regions=4, applied=None, rations=None, die_after=()):
        """``households``: (members, adults, frm, to); the gate prices them in order."""
        p, self.policy = self.policy, None
        before = [0] * n_regions
        groups = []
        for members, adults, frm, to in households:
            before[frm] += len(members)
            liquid = [(a, self.wealth[a]) for a in adults]
            have = sum(w for _, w in liquid)
            fare = p["fare"] * len(members)
            grant, payer = 0, -1
            if have >= fare:
                code = 0
            else:
                payer = p["payers"][to]
                budget = p["budgets"][payer] if payer >= 0 else 0
                offer = min(min(p["assist"], p["fare"]) * len(members), budget)
                if offer > 0 and have + offer >= fare:
                    code, grant = 5, offer
                    p["budgets"][payer] -= offer
                else:
                    code = 1
            moved = code != 1 and (applied is None or applied.get(min(members), True))
            if code == 5 and not moved:
                p["budgets"][payer] += grant
            groups.append(((min(members), frm, to, code, moved),
                           (sorted(members), sorted(liquid), len(members) - len(adults)),
                           (have, fare, grant, payer if grant else -1)))
        after = list(before)
        for (lead, frm, to, code, moved), (members, _, _), _ in groups:
            if moved:
                after[frm] -= len(members)
                after[to] += len(members)
        for aid in die_after:
            self.alive.discard(aid)
        self.receipt = (p["turn"], groups, before, after, p["budgets"], rations)

    def take_relocation_receipt(self, turn):
        if self.receipt is None or self.receipt[0] != turn:
            return None
        r, self.receipt = self.receipt, None
        return r[1:]

    def transfer_wealth(self, turn, purpose, batch, rows):
        assert purpose == R.PURPOSE_RELOCATION_FARE and (turn, purpose, batch) not in self.keys
        assert len({a for a, _ in rows}) == len(rows)
        self.keys.add((turn, purpose, batch))
        out = []
        for aid, amount in rows:
            if aid not in self.alive:
                out.append((aid, amount, 0, amount, 2))
                continue
            applied = -min(-amount, self.wealth[aid])
            self.wealth[aid] += applied
            out.append((aid, amount, applied, amount - applied, 0 if applied == amount else 1))
        return out


class FakeBridge:
    def __init__(self, sim):
        self._sim = sim


class Economy:
    def __init__(self, world, value=0.8):
        self.food_sufficiency = {r.name: value for r in world.regions}


def _world(mode="paid", treasury=200):
    world = generate_world(seed=42, num_regions=4, num_civs=2)
    world.agent_mode = "hybrid"
    for i, r in enumerate(world.regions):
        r.controller = world.civilizations[0 if i < 2 else 1].name
    for civ in world.civilizations:
        civ.treasury = treasury
    args = _build_parser().parse_args(["--relocation-costs", "--relocation-mode", mode])
    configure_livelihoods(world, args, agent_mode="hybrid")
    return world


def turn(world, sim, households, *, acc=None, between=None, **tick):
    bridge = FakeBridge(sim)
    R.before_agent_tick(world, bridge, Economy(world))
    sim.tick(households, **tick)
    R.after_agent_tick(world, bridge)
    if between is not None:
        between(world)
    R.phase10_before_reserves(world, acc, None, bridge)
    world.turn += 1
    return world.livelihoods.relocation_costs


FAMILY = ([10, 11, 12], [10, 11], 0, 1)          # two adults and a child, 0 -> 1


def test_switch_prerequisites_and_modes():
    world = generate_world(seed=42, num_regions=4, num_civs=2)
    parse = _build_parser().parse_args
    with pytest.raises(ValueError, match="hybrid"):
        configure_livelihoods(world, parse(["--relocation-costs"]), agent_mode="off")
    world.household_mobility_liquid_requirement = 0.5
    with pytest.raises(ValueError, match="liquid requirement"):
        configure_livelihoods(world, parse(["--relocation-costs"]), agent_mode="hybrid")
    assert world.livelihoods is None
    assert MODES == ("paid", "assisted", "liquidity_only")
    assert _world().livelihoods.relocation_costs.mode == "paid"


def test_paid_move_debits_adults_pro_rata_and_never_the_child():
    world, sim = _world(), FakeSim({10: 2000, 11: 1000, 12: 0})
    state = turn(world, sim, [FAMILY])
    h = state.households[0]
    assert (h.reason, h.applied, h.fare, h.assistance, h.movers_share) == ("passed", True, 3000, 0, 3000)
    assert h.children == 1 and h.adults == [10, 11]
    assert [d[:3] for d in h.debits] == [(10, 2000, 2000), (11, 1000, 1000)]
    assert (h.paid, h.residual) == (3000, 0) and sim.wealth[12] == 0
    c = state.counters
    assert (c["fare_due_milli"], c["fare_debited_milli"], c["travel_sink_milli"], c["children_applied"]) == (3000, 3000, 3000, 1)
    regions = {r.region: r for r in state.regions}
    assert (regions[1].arrivals, regions[1].arrival_households, regions[0].departures) == (3, 1, 3)
    assert regions[1].alive_after == regions[1].alive_before + 3


def test_liquidity_only_requires_the_fare_and_charges_nothing():
    world, sim = _world("liquidity_only"), FakeSim({10: 2000, 11: 1000, 12: 0, 20: 500, 21: 0})
    state = turn(world, sim, [FAMILY, ([20, 21], [20], 2, 3)])
    by = {h.lead: h for h in state.households}
    assert by[10].applied and by[10].debits == [] and by[10].paid == 0
    assert by[20].reason == "short" and not by[20].applied
    assert sim.wealth == {10: 2000, 11: 1000, 12: 0, 20: 500, 21: 0}
    assert state.counters["fare_not_charged_milli"] == 3000 and "fare_debited_milli" not in state.counters


def test_identical_short_families_differ_only_under_funded_assistance():
    outcomes = {}
    for mode in ("liquidity_only", "assisted"):
        world, sim = _world(mode), FakeSim({10: 1000, 11: 1000, 12: 0})
        state = turn(world, sim, [FAMILY])
        outcomes[mode] = (state, sim, world)
    alone, helped = outcomes["liquidity_only"][0], outcomes["assisted"][0]
    assert alone.households[0].reason == "short" and not alone.households[0].applied
    h = helped.households[0]
    assert (h.reason, h.applied, h.assistance, h.movers_share, h.payer) == ("assisted", True, 1500, 1500, 0)
    assert [d[:3] for d in h.debits] == [(10, 750, 750), (11, 750, 750)]
    assert h.assistance_status == "charged"
    world = outcomes["assisted"][2]
    assert world.civilizations[0].treasury == 200 - 2          # ceil(1500 milli) = 2 coins
    charge = helped.assistance[0]
    assert (charge.civ, charge.granted, charge.charged_coins, charge.status) == (0, 1500, 2, "charged")
    assert helped.counters["assistance_rounding_milli"] == 500


def test_assistance_budget_is_bounded_by_the_rulers_treasury():
    world, sim = _world("assisted", treasury=20), FakeSim({10: 1000, 11: 1000, 12: 0, 20: 1000, 21: 1000, 22: 0})
    # 5% of 20 coins = one coin: the first short family in gate order gets the
    # whole budget (1000 of its 1500 offer) and can move; the second cannot.
    state = turn(world, sim, [FAMILY, ([20, 21, 22], [20, 21], 0, 1)])
    by = {h.lead: h for h in state.households}
    assert (by[10].reason, by[10].assistance, by[10].movers_share) == ("assisted", 1000, 2000)
    assert by[20].reason == "short" and not by[20].applied
    assert world.civilizations[0].treasury == 19


def test_canceled_moves_and_unapplied_assistance_are_never_charged():
    world, sim = _world("assisted"), FakeSim({10: 1000, 11: 1000, 12: 0})
    state = turn(world, sim, [FAMILY], applied={10: False})
    h = state.households[0]
    assert h.reason == "assisted" and not h.applied and h.debits == [] and h.paid == 0
    assert state.assistance == [] and world.civilizations[0].treasury == 200
    assert "fare_due_milli" not in state.counters


def test_death_after_the_move_leaves_a_recorded_residual():
    world, sim = _world(), FakeSim({10: 2000, 11: 1000, 12: 0})
    state = turn(world, sim, [FAMILY], die_after=[11])
    h = state.households[0]
    assert h.debits[1] == (11, 1000, 0, 1000, "absent")
    assert (h.paid, h.residual) == (2000, 1000)
    assert state.counters["fare_residual_milli"] == 1000 and state.counters["groups_with_residual"] == 1


def test_conquest_between_plan_and_settlement_refuses_the_charge():
    world, sim = _world("assisted"), FakeSim({10: 1000, 11: 1000, 12: 0})

    def conquest(w):
        w.regions[1].controller = w.civilizations[1].name

    state = turn(world, sim, [FAMILY], between=conquest)
    h = state.households[0]
    assert h.applied and h.assistance == 1500 and h.assistance_status == "controller_changed"
    assert [c.status for c in state.assistance] == ["controller_changed"]
    assert all(c.treasury == 200 for c in world.civilizations)
    assert state.counters["assistance_refused_milli"] == 1500


def test_a_short_treasury_at_settlement_refuses_the_charge():
    world, sim = _world("assisted"), FakeSim({10: 1000, 11: 1000, 12: 0})

    def spend(w):
        w.civilizations[0].treasury = 1

    state = turn(world, sim, [FAMILY], between=spend)
    assert state.households[0].assistance_status == "treasury_short"
    assert world.civilizations[0].treasury == 1


def test_a_return_is_a_new_move_and_pays_again():
    world, sim = _world(), FakeSim({10: 5000, 11: 5000, 12: 0})
    turn(world, sim, [FAMILY])
    state = turn(world, sim, [([10, 11, 12], [10, 11], 1, 0)])
    h = state.households[0]
    assert h.is_return and h.paid == 3000
    assert state.counters["returns"] == 1 and state.counters["fare_debited_milli"] == 6000


def test_service_receipts_follow_last_turns_arrivals():
    world, sim = _world(), FakeSim({10: 2000, 11: 1000, 12: 0})
    turn(world, sim, [FAMILY])
    state = turn(world, sim, [], rations=[(1, 3, 1.5, 7, 6.3)])
    s = state.services[0]
    assert (s.region, s.arrival_turn, s.arrivals_rationed, s.residents_rationed) == (1, 0, 3, 7)
    assert s.arrivals_mean_ration == pytest.approx(0.5) and s.residents_mean_ration == pytest.approx(0.9)
    world, sim = _world(), FakeSim({10: 2000, 11: 1000, 12: 0})
    turn(world, sim, [FAMILY])
    state = turn(world, sim, [])                  # no allocation: the region's signal only
    assert state.services[0].arrivals_mean_ration is None and state.services[0].food_sufficiency == 0.8


def test_settlement_is_once_per_turn_and_state_round_trips():
    world, sim = _world(), FakeSim({10: 2000, 11: 1000, 12: 0})
    turn(world, sim, [FAMILY])
    state = world.livelihoods.relocation_costs
    assert state.last_settled_turn == 0
    world.turn -= 1                                # replaying a settled turn is refused
    with pytest.raises(RuntimeError, match="already settled"):
        R.before_agent_tick(world, FakeBridge(sim), Economy(world))
    world.turn += 1
    assert pickle.loads(pickle.dumps(state)).model_dump_json() == state.model_dump_json()
    assert RelocationCostsState.model_validate_json(state.model_dump_json()) == state
    assert LivelihoodsState.model_validate_json(world.livelihoods.model_dump_json()).relocation_costs == state
    fields = livelihoods_snapshot_fields(world)["livelihoods"]["relocation_costs"]
    json.dumps(fields)
    assert fields["source_turn"] == 0 and fields["households"][0]["lead"] == 10
    assert list(fields["counters"]) == [k for k in COUNTERS if k in fields["counters"]]
    world.turn += 1                                # no completed relocation turn: unknown
    later = livelihoods_snapshot_fields(world)["livelihoods"]["relocation_costs"]
    assert later["households"] is None and later["regions"] is None and later["gate"] is None


def test_split_share_is_pro_rata_with_largest_remainder():
    assert R.split_share(1000, [(1, 1), (2, 1), (3, 1)]) == [(1, 334), (2, 333), (3, 333)]
    assert R.split_share(3000, [(1, 2000), (2, 1000)]) == [(1, 2000), (2, 1000)]
    assert R.split_share(10, [(5, 0), (4, 0)]) == [(5, 5), (4, 5)]
    assert R.split_share(0, [(1, 5)]) == [] and R.split_share(5, []) == []
    assert sum(a for _, a in R.split_share(1001, [(1, 7), (2, 13), (3, 1)])) == 1001


def test_declared_codes_are_append_only_prefixes():
    assert GATE_REASONS[:6] == ("passed", "short", "no_local_distress", "route", "trip", "assisted")
