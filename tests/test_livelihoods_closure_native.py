"""Money closure across every livelihoods claimant on the real compiled extension.

Review R2 (2026-11-05). Three short hybrid worlds run with every money
claimant on: grain reserves with storage works, shipments and convoys; L1
workshops with L6a payroll and academy services; L3 timber with L8 wardens;
L2 food allocation; L5 cohorts; L7 assisted relocation; and L9 budgets (off
in the first world, where firms sell and distribute early). A fourth world
adds every recovery-skills switch: RS2 repair coins and RS5 warden charges
are itemised claimants, RS1 stipends close in firm cash, and RS4
remittances move native wealth by exactly minus the courier fees. Each turn,
per civilization, the checks below compare what the accumulator was actually
told against what each service itemised in its own receipts:

* every treasury change a claimant made is a ``keep`` change, never clamped by
  the accumulator's floor, and sums to the service's itemised receipts for
  that turn (workshop bills, storage work, warden bills, firm sales and
  distributions, relocation assistance, granary purchases and sales,
  shipment and convoy payments, escort fees): nothing is charged twice and
  nothing unrecorded;
* each firm's cash changes by exactly sales - wages - distributions -
  write-offs, and the native agent wealth moved by the wage and fare
  transfers equals what the books say was applied;
* L9 (docs/integration/local-budgets.md, Limits): assisted relocation never
  charges a ruler more than the obligation L9 reserved for it at the decision.

The worlds are chosen so that every claimant is exercised at least once
(checked), so no closure assertion is vacuous.
"""
from __future__ import annotations

import sys
from collections import defaultdict

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

FLAGS = ("--grain-reserves", "--grain-storage", "--public-grain-shipments", "--grain-convoys",
         "--scholarship", "--techniques", "--academy-services", "--workshops", "--workshop-payroll",
         "--timber-stock", "--commons-rules", "--food-allocation", "--learning-cohorts",
         "--relocation-costs", "--relocation-mode", "assisted", "--local-budgets")
#: The recovery-skills switches (each package's default mode).
RS_FLAGS = ("--apprenticeship", "--repair-projects", "--veteran-reintegration", "--remittances",
            "--clearing-protection")
#: (seed, turns, extra): a template world without L9 (firm sales from turn 43,
#: distributions from 59, wardens), the same world in L9's fixed-shares
#: control (storage works, the reservation check) and a procedural world
#: (shipments, and convoys from turn 6).
_TEMPLATE = ("--civs", "4", "--regions", "8")
WORLDS = ((4, 80, (*_TEMPLATE, "--no-local-budgets")),
          (4, 80, (*_TEMPLATE, "--local-budget-mode", "fixed_shares")),
          (9, 80, ("--worldgen", "procedural", "--civs", "10", "--regions", "32")),
          # Every recovery-skills switch as well (review B 2026-11-05): RS2 repair
          # coins, RS5 warden charges, RS4 remittances, RS1 and RS3 alongside.
          (31, 80, ("--worldgen", "procedural", "--civs", "10", "--regions", "32", *RS_FLAGS)))
#: Modules whose treasury changes are itemised in their own receipts.
CLAIMANTS = ("chronicler.workshops", "chronicler.grain_storage", "chronicler.commons_rules",
             "chronicler.workshop_payroll", "chronicler.relocation_costs", "chronicler.grain_reserves",
             "chronicler.public_grain_shipments", "chronicler.grain_convoys",
             "chronicler.clearing_protection", "chronicler.repair_projects")
#: Helpers that write a caller's treasury change (attributed to the caller).
_WRITERS = ("chronicler.finance", "chronicler.war.common")


class _Closure:
    def __init__(self):
        self.turn = None
        self.changes = []                     # (turn, civ, delta, category, module, function)
        self.clamped = []
        self.reserved = {}                    # (decision turn, civ) -> L7 obligation
        self.wealth = []                      # (kind, turn, native wealth moved (milli), booked)
        self.problems = defaultdict(list)
        self.activity = defaultdict(int)

    def check_turn(self, world, t):
        from chronicler.grain_reserves_state import BOUGHT, DISPATCHED
        got = defaultdict(float)
        for turn, civ, delta, category, module, function in self.changes:
            if turn == t and module in CLAIMANTS:
                got[(civ, module)] += delta
                if category != "keep":
                    self.problems["category"].append((t, civ, module, function, category))
        want = defaultdict(int)
        liv = world.livelihoods
        if liv.workshops.frame_turn == t:
            for r in liv.workshops.frame:
                if r.paid:
                    want[(r.payer, "chronicler.workshops")] -= sum(r.paid.values())
                    self.activity["workshop bill"] += 1
        storage = world.grain_reserves.storage
        if storage is not None and storage.receipt_turn == t:
            for r in storage.receipts:
                if r.owner >= 0 and r.treasury_paid:
                    want[(r.owner, "chronicler.grain_storage")] -= r.treasury_paid
                    self.activity["storage work"] += 1
        rules = liv.commons_rules
        if rules.frame_turn == t:
            for r in rules.frame:
                if r.paid:
                    want[(r.owner, "chronicler.commons_rules")] -= r.paid
                    self.activity["warden bill"] += 1
        payroll = liv.workshop_payroll
        if payroll.frame_turn == t:
            for m in payroll.money:
                if m.turn == t and m.kind == "sale":
                    want[(m.payer[1], "chronicler.workshop_payroll")] -= m.applied // 1000
                    self.activity["firm sale"] += 1
                elif m.turn == t and m.kind == "distribution":
                    want[(m.payee[1], "chronicler.workshop_payroll")] += m.applied // 1000
                    self.activity["firm distribution"] += 1
            for r in payroll.frame:
                if r.cash_close - r.cash_open != (r.sales - r.wages_paid - r.distributed - r.written_off
                                                  - (r.stipends or 0)):
                    self.problems["firm cash"].append((t, r.site))
        reloc = liv.relocation_costs
        if reloc.frame_turn == t:
            for a in reloc.assistance:
                if a.turn == t and a.charged_coins:
                    want[(a.civ, "chronicler.relocation_costs")] -= a.charged_coins
                    self.activity["relocation assistance"] += 1
                    reserved = self.reserved.get((t - 1, a.civ))
                    if reserved is not None and a.charged_coins > reserved:
                        self.problems["assistance beyond the L9 reservation"].append(
                            (t, a.civ, a.charged_coins, reserved))
        reserves = world.grain_reserves
        if reserves.flows_turn == t:
            for f in reserves.flows:
                if f.kind == BOUGHT and f.cost:
                    want[(f.buyer, "chronicler.grain_reserves")] -= f.cost
                    if f.seller != f.buyer:
                        want[(f.seller, "chronicler.grain_reserves")] += f.cost
                    self.activity["granary purchase"] += 1
                elif f.kind == DISPATCHED and f.cost:
                    want[(f.buyer, "chronicler.public_grain_shipments")] -= f.cost
                    want[(f.seller, "chronicler.public_grain_shipments")] += f.cost
                    self.activity["shipment"] += 1
        convoys = liv.grain_convoys
        if convoys.frame_turn == t:
            seller = {c.convoy: c.seller for c in convoys.convoys}
            for row in convoys.frame:
                if row.operation == "dispatched" and row.turn == t:
                    want[(row.buyer, "chronicler.grain_convoys")] -= (row.paid or 0) + (row.escort_fee or 0)
                    want[(seller[row.convoy], "chronicler.grain_convoys")] += row.paid or 0
                    self.activity["convoy"] += 1
        protection = getattr(liv, "clearing_protection", None)
        if protection is not None and protection.frame_turn == t:
            for r in protection.frame:
                if r.charged:
                    want[(r.payer, "chronicler.clearing_protection")] -= r.charged
                    self.activity["clearing warden"] += 1
        repairs = getattr(liv, "repair_projects", None)
        if repairs is not None and repairs.frame_turn == t:
            for row in repairs.ledger or []:
                if row.turn == t and row.charged:
                    want[(row.civ, "chronicler.repair_projects")] -= row.charged
                    self.activity["repair coins"] += 1
        for key in sorted({k for k, v in got.items() if v} | {k for k, v in want.items() if v}):
            if abs(got.get(key, 0) - want.get(key, 0)) > 1e-9:
                self.problems["treasury"].append((t, key, got.get(key, 0), want.get(key, 0)))
        for turn, civ, delta, category, module, function in self.changes:
            if turn == t and module == "chronicler.learning_services" and delta < 0:
                self.activity["academy procurement"] += 1


def _wealth(sim):
    batch = sim.get_snapshot()
    return dict(zip(batch.column("id").to_pylist(), batch.column("wealth").to_pylist()))


def _run(path, seed, turns, extra):
    import chronicler.main as M
    from chronicler import local_budgets as LB
    from chronicler import relocation_costs as R
    from chronicler import remittances as RM
    from chronicler import workshop_payroll as P
    from chronicler.accumulator import StatAccumulator
    from chronicler.main import _build_parser, execute_run

    c = _Closure()
    add, obligations = StatAccumulator.add, LB._RelocationAssistance.obligations
    after_tick, payroll_phase10, turn_result = R.after_agent_tick, P.phase10, M.run_turn_result
    remit_tick = RM.after_agent_tick

    def recording_add(self, civ_idx, civ, stat, delta, category):
        if stat == "treasury":
            frame = sys._getframe(1)
            while frame.f_globals.get("__name__") in _WRITERS:
                frame = frame.f_back
            module = frame.f_globals.get("__name__")
            projected = float(civ.treasury)
            for change in self._changes[self._keep_applied_up_to:]:
                if change.civ_id == civ_idx and change.stat == "treasury" and change.category == "keep":
                    projected = max(0.0, projected + change.delta)
            c.changes.append((c.turn, civ_idx, delta, category, module, frame.f_code.co_name))
            if module in CLAIMANTS and delta < 0 and projected + delta < -1e-9:
                c.clamped.append((c.turn, civ_idx, module, projected, delta))
        return add(self, civ_idx, civ, stat, delta, category)

    def recording_obligations(self, world, civ, obs):
        value = obligations(self, world, civ, obs)
        c.reserved[(world.turn, civ)] = value
        return value

    def fare_closure(world, agent_bridge):
        state = R._state(world)
        before, debited = _wealth(agent_bridge._sim), state.counters.get("fare_debited_milli", 0)
        events = after_tick(world, agent_bridge)
        moved = _wealth(agent_bridge._sim)
        c.wealth.append(("fare", world.turn, 1000.0 * sum(moved.get(a, 0.0) - w for a, w in before.items()),
                         -(state.counters.get("fare_debited_milli", 0) - debited)))
        return events

    def remittance_closure(world, agent_bridge):
        # The pool loses exactly the courier fees: credits move wealth between people.
        state = RM._state(world)
        before, fees = _wealth(agent_bridge._sim), state.counters.get("fee_milli", 0)
        events = remit_tick(world, agent_bridge)
        moved = _wealth(agent_bridge._sim)
        c.wealth.append(("remittance", world.turn,
                         1000.0 * sum(moved.get(a, 0.0) - w for a, w in before.items()),
                         -(state.counters.get("fee_milli", 0) - fees)))
        return events

    def wage_closure(world, acc, economy_result, agent_bridge):
        state = P._state(world)
        before, paid = _wealth(agent_bridge._sim), state.counters.get("wages_paid", 0)
        events = payroll_phase10(world, acc, economy_result, agent_bridge)
        moved = _wealth(agent_bridge._sim)
        c.wealth.append(("wage", world.turn, 1000.0 * sum(moved.get(a, 0.0) - w for a, w in before.items()),
                         state.counters.get("wages_paid", 0) - paid))
        return events

    def checked_turn(world, *args, **kwargs):
        c.turn = t = world.turn
        result = turn_result(world, *args, **kwargs)
        c.check_turn(world, t)
        return result

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(StatAccumulator, "add", recording_add)
        mp.setattr(LB._RelocationAssistance, "obligations", recording_obligations)
        mp.setattr(R, "after_agent_tick", fare_closure)
        mp.setattr(P, "phase10", wage_closure)
        mp.setattr(RM, "after_agent_tick", remittance_closure)
        mp.setattr(M, "run_turn_result", checked_turn)
        args = _build_parser().parse_args([
            "--seed", str(seed), "--turns", str(turns), "--agents", "hybrid", "--simulate-only",
            "--output", str(path / "chronicle.md"), "--state", str(path / "state.json"), *FLAGS, *extra])
        execute_run(args)
    return c


@pytest.fixture(scope="module")
def closures(tmp_path_factory):
    return [_run(tmp_path_factory.mktemp(f"closure{seed}_"), seed, turns, extra) for seed, turns, extra in WORLDS]


def test_every_money_claimant_is_exercised(closures):
    activity = defaultdict(int)
    for c in closures:
        for key, value in c.activity.items():
            activity[key] += value
    for kind in ("workshop bill", "storage work", "warden bill", "firm sale", "firm distribution",
                 "relocation assistance", "granary purchase", "shipment", "convoy", "academy procurement",
                 "clearing warden", "repair coins"):
        assert activity[kind] > 0, (kind, dict(activity))
    assert sum(1 for c in closures for kind, *_ in c.wealth if kind == "wage") > 0


def test_each_claimants_treasury_changes_match_its_receipts_once(closures):
    for c in closures:
        assert c.problems["treasury"] == []
        assert c.problems["category"] == []
        assert c.clamped == []


def test_firm_cash_and_native_agent_wealth_close_with_the_books(closures):
    for c in closures:
        assert c.problems["firm cash"] == []
        moved = [(kind, turn, native, booked) for kind, turn, native, booked in c.wealth
                 if abs(native - booked) > 0.5]          # f32 wealth: well under a milli-unit per turn
        assert moved == []
    assert any(booked for c in closures for kind, _t, _n, booked in c.wealth if kind == "wage")
    assert any(booked for c in closures for kind, _t, _n, booked in c.wealth if kind == "fare")
    assert any(booked for c in closures for kind, _t, _n, booked in c.wealth if kind == "remittance")


def test_assisted_relocation_never_charges_beyond_the_l9_reservation(closures):
    for c in closures:
        assert c.problems["assistance beyond the L9 reservation"] == []
