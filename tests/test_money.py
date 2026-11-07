"""The shared payment seam (``chronicler.money``) without the native extension.

A stand-in simulator gives keyed native wealth transfers with the limits of
``wealth_transfer.rs`` (credits stop at the ceiling, debits at zero, a key
settles once) and a snapshot of ``id`` and ``wealth``.
"""
from __future__ import annotations

import math
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import money as M

MAX_WEALTH = 100.0


class FakeSim:
    def __init__(self, wealth, purposes=M.NATIVE_PURPOSES):
        self.wealth = dict(wealth)
        self.keys: list[tuple[int, int, int]] = []
        self.purposes = list(purposes)
        self.calls = 0

    def wealth_transfer_purposes(self):
        return list(self.purposes)

    def get_snapshot(self):
        ids = sorted(self.wealth)
        return pa.record_batch({"id": pa.array(ids, pa.uint32()),
                                "wealth": pa.array([self.wealth[a] for a in ids], pa.float32())})

    def transfer_wealth(self, turn, purpose, batch, rows):
        self.calls += 1
        if purpose >= len(self.purposes):
            raise ValueError("unknown wealth transfer purpose")
        if any(p == purpose and b == batch and t >= turn for t, p, b in self.keys):
            raise ValueError("wealth transfer already applied for this turn, purpose and batch")
        self.keys = [k for k in self.keys if k[0] >= turn] + [(turn, purpose, batch)]
        out = []
        for aid, amount in rows:
            if aid not in self.wealth:
                out.append((aid, amount, 0, amount, 2))
                continue
            w = self.wealth[aid]
            applied = min(amount, math.floor((MAX_WEALTH - w) * 1000)) if amount >= 0 \
                else -min(-amount, math.floor(w * 1000))
            self.wealth[aid] = w + applied / 1000
            out.append((aid, amount, applied, amount - applied, 0 if applied == amount else 1))
        return out


class PairSim(FakeSim):
    """The stand-in plus native ``settle_pairs`` (A4) with its limits."""

    def settle_pairs(self, turn, purpose, batch, rows):
        self.calls += 1
        if purpose not in (8, 9):
            raise ValueError("not a pairwise wealth transfer purpose")
        if any(p == purpose and b == batch and t >= turn for t, p, b in self.keys):
            raise ValueError("wealth transfer already applied for this turn, purpose and batch")
        self.keys = [k for k in self.keys if k[0] >= turn] + [(turn, purpose, batch)]
        left, room, out = {}, {}, []
        for payer, payee, amount in rows:
            if payer not in self.wealth or payee not in self.wealth:
                out.append((payer, payee, amount, 0, 0, 0, 2))
                continue
            left.setdefault(payer, math.floor(self.wealth[payer] * 1000))
            room.setdefault(payee, math.floor((MAX_WEALTH - self.wealth[payee]) * 1000))
            sent = min(amount, left[payer])
            credited = min(sent, room[payee])
            left[payer] -= credited
            room[payee] -= credited
            self.wealth[payer] -= credited / 1000
            self.wealth[payee] += credited / 1000
            out.append((payer, payee, amount, sent, credited, sent - credited,
                        0 if sent == amount and credited == sent else 1))
        return out


def _world(treasury=(10, 3)):
    return SimpleNamespace(civilizations=[SimpleNamespace(name=f"C{i}", treasury=t) for i, t in enumerate(treasury)])


def _firm(cash):
    return SimpleNamespace(cash=cash)


def test_a_collection_is_validated_whole_before_anything_moves():
    world, book = _world(), M.MoneyBook()
    sim = FakeSim({1: 2.0, 2: 0.3, 3: 5.0})
    firms = {7: _firm(0)}
    # Payer 2 holds 300 milli: the whole bill is refused, nobody is debited.
    bill = M.Bill(purpose="wares_purchase", batch=7, phase="phase10", payee=M.firm_cash(7),
                  lines=((M.agent(1), 500), (M.agent(2), 400), (M.agent(3), 100)))
    got = M.pay(world, bill, turn=4, book=book, sim=sim, firms=firms)
    assert not got.ok and got.reason == "payer_short"
    assert sim.calls == 0 and firms[7].cash == 0 and book.settled == [] and book.flows == []
    assert sim.wealth == {1: 2.0, 2: 0.3, 3: 5.0}
    # An absent payer refuses the bill too.
    absent = M.Bill(purpose="wares_purchase", batch=7, phase="phase10", payee=M.firm_cash(7),
                    lines=((M.agent(1), 100), (M.agent(9), 100)))
    assert M.pay(world, absent, turn=4, book=book, sim=sim, firms=firms).reason == "payer_absent"
    # Within every payer's holding: applied in full, the firm credited exactly.
    ok = M.Bill(purpose="wares_purchase", batch=7, phase="phase10", payee=M.firm_cash(7),
                lines=((M.agent(1), 500), (M.agent(2), 300)), regions=(2, 2))
    got = M.pay(world, ok, turn=4, book=book, sim=sim, firms=firms)
    assert got.ok and got.applied == 800 and firms[7].cash == 800
    assert sim.wealth[1] == pytest.approx(1.5) and sim.wealth[2] == pytest.approx(0.0, abs=1e-9)
    assert [(f.payer, f.payee, f.applied, f.region) for f in book.flows] == [
        (("agent_wealth", 1), ("firm_cash", 7), 500, 2), (("agent_wealth", 2), ("firm_cash", 7), 300, 2)]
    # Native keys: debit rows of purpose 7, batch = the firm.
    assert sim.keys == [(4, M.PURPOSES["wares_purchase"], 7)] and M.PURPOSES["wares_purchase"] == 7


def test_payers_must_cover_the_whole_bill():
    world, book = _world(treasury=(10, 3)), M.MoneyBook()
    firms = {1: _firm(999)}
    short = M.Bill(purpose="firm_input_purchase", batch=1, phase="phase2", payer=M.firm_cash(1),
                   lines=((M.treasury(0), 1000),))
    assert M.pay(world, short, turn=1, book=book, firms=firms).reason == "payer_short"
    assert firms[1].cash == 999 and world.civilizations[0].treasury == 10
    capital = M.Bill(purpose="firm_capital", batch=1, phase="phase10", payer=M.treasury(1),
                     lines=((M.firm_cash(1), 4000),))
    assert M.pay(world, capital, turn=1, book=book, firms=firms).reason == "payer_short"
    assert world.civilizations[1].treasury == 3 and firms[1].cash == 999
    capital = M.Bill(purpose="firm_capital", batch=1, phase="phase10", payer=M.treasury(1),
                     lines=((M.firm_cash(1), 3000),))
    got = M.pay(world, capital, turn=1, book=book, firms=firms)
    assert got.ok and got.treasury_units == -3 and world.civilizations[1].treasury == 0 and firms[1].cash == 3999


@pytest.mark.parametrize("bill, message", [
    (M.Bill(purpose="nothing", batch=0, phase="p", payer=M.firm_cash(1), lines=((M.treasury(0), 5),)),
     "unregistered"),
    (M.Bill(purpose="firm_capital", batch=-1, phase="p", payer=M.treasury(0), lines=((M.firm_cash(1), 1000),)),
     "batch"),
    (M.Bill(purpose="firm_capital", batch=0, phase="p", payer=M.treasury(0), lines=((M.firm_cash(1), 0),)),
     "positive"),
    (M.Bill(purpose="firm_capital", batch=0, phase="p", payer=M.treasury(0), lines=((M.firm_cash(1), 2.5),)),
     "positive"),
    (M.Bill(purpose="firm_capital", batch=0, phase="p", payer=M.treasury(0), lines=((M.firm_cash(1), 1500),)),
     "whole units"),
    (M.Bill(purpose="wares_purchase", batch=0, phase="p", payee=M.firm_cash(1),
            lines=((M.agent(1), 5), (M.agent(1), 6))), "duplicate"),
    (M.Bill(purpose="firm_input_purchase", batch=0, phase="p", payer=M.firm_cash(1),
            lines=((M.sink("void"), 5),)), "undeclared sink"),
    (M.Bill(purpose="wares_purchase", batch=0, phase="p", payer=M.firm_cash(1), lines=((M.agent(1), 5),),
            residual="sink:void"), "undeclared residual"),
    (M.Bill(purpose="firm_input_purchase", batch=0, phase="p", payer=M.firm_cash(1), payee=M.treasury(0),
            lines=((M.treasury(1), 5),)), "exactly one"),
    (M.Bill(purpose="firm_capital", batch=0, phase="p", payer=M.firm_cash(1), lines=((M.agent(1), 5),)),
     "no native code"),
    (M.Bill(purpose="wares_purchase", batch=0, phase="p", payer=M.treasury(0), lines=((M.agent(1), 1000),)),
     "treasury payment to agents"),
])
def test_malformed_bills_raise_before_anything_moves(bill, message):
    world, book = _world(), M.MoneyBook()
    with pytest.raises(M.MoneyError, match=message):
        M.pay(world, bill, turn=1, book=book, sim=FakeSim({1: 1.0}), firms={1: _firm(10_000)})
    assert world.civilizations[0].treasury == 10 and book.settled == []


def test_each_turn_purpose_and_batch_settles_exactly_once_across_round_trips():
    world, book = _world(), M.MoneyBook()
    firms = {3: _firm(5000), 4: _firm(5000)}

    def bill(batch):
        return M.Bill(purpose="firm_input_purchase", batch=batch, phase="phase2", payer=M.firm_cash(batch),
                      lines=((M.treasury(0), 700),))

    assert M.pay(world, bill(3), turn=5, book=book, firms=firms).ok
    again = M.pay(world, bill(3), turn=5, book=book, firms=firms)
    assert not again.ok and again.reason == "already_settled" and firms[3].cash == 4300
    assert M.pay(world, bill(4), turn=5, book=book, firms=firms).ok            # another batch, same turn
    # An exact checkpoint (JSON or pickle) keeps the settled keys: a repeat is refused.
    for restored in (M.MoneyBook.model_validate_json(book.model_dump_json()), pickle.loads(pickle.dumps(book))):
        assert M.pay(world, bill(3), turn=5, book=restored, firms=firms).reason == "already_settled"
        assert M.pay(world, bill(3), turn=4, book=restored, firms=firms).reason == "already_settled"
    assert M.pay(world, bill(3), turn=6, book=book, firms=firms).ok
    assert book.settled == [(6, "firm_input_purchase", 3)]                     # only the latest turn kept
    assert firms[3].cash == 3600


def test_treasury_credits_carry_sub_unit_amounts_and_create_nothing():
    world, book = _world(treasury=(0, 0)), M.MoneyBook()
    firms = {1: _firm(10_000)}
    paid = 0
    for turn, amount in enumerate((1234, 800, 966, 1)):
        bill = M.Bill(purpose="firm_input_purchase", batch=1, phase="phase2", payer=M.firm_cash(1),
                      lines=((M.treasury(0), amount),))
        got = M.pay(world, bill, turn=turn, book=book, firms=firms)
        paid += amount
        flow = book.flows[0]
        assert flow.carry_after == book.carry.get("0:firm_input_purchase", 0)
        assert world.civilizations[0].treasury * 1000 + book.carry.get("0:firm_input_purchase", 0) == paid
        assert firms[1].cash == 10_000 - paid and got.treasury_units == flow.treasury_units
    assert world.civilizations[0].treasury == 3 and book.carry == {"0:firm_input_purchase": 1}
    M.check_book(book)


def test_an_agent_wealth_purpose_without_a_ledger_channel_is_refused():
    """Fail closed: the seam moves agent wealth only for purposes the ledger
    reads (``MONEY_PURPOSE_CHANNELS``), so a new payer cannot vanish into the
    native-model residual."""
    world, book = _world(), M.MoneyBook()
    sim = FakeSim({1: 1.0})
    bill = M.Bill(purpose="workshop_wage", batch=1, phase="phase10", payer=M.firm_cash(1), lines=((M.agent(1), 10),))
    with pytest.raises(M.MoneyError, match="no ledger channel"):
        M.pay(world, bill, turn=2, book=book, sim=sim, firms={1: _firm(100)})
    assert sim.calls == 0 and book.settled == []


def test_refused_credits_return_to_the_payer_unless_a_sink_is_declared(monkeypatch):
    from chronicler import wealth_accounting_state as WAS
    # A constructed credit purpose for the seam's own contract (no package pays wages through it).
    monkeypatch.setitem(WAS.MONEY_PURPOSE_CHANNELS, "workshop_wage", "workshop_wage")
    world = _world()
    sim = FakeSim({1: MAX_WEALTH - 0.25, 2: 1.0})
    firms = {1: _firm(5000), 2: _firm(5000)}
    book = M.MoneyBook()
    back = M.Bill(purpose="workshop_wage", batch=1, phase="phase10", payer=M.firm_cash(1),
                  lines=((M.agent(1), 1000), (M.agent(2), 1000), (M.agent(9), 300)))
    got = M.pay(world, back, turn=2, book=book, sim=sim, firms=firms)
    # The ceiling took 250 of 1000; the absent id took nothing: both stay with the payer.
    assert got.ok and got.applied == 1250 and got.residual == 1050 and got.sunk == 0
    assert firms[1].cash == 5000 - 1250
    status = {f.payee[1]: (f.applied, f.residual, f.residual_to, f.status) for f in book.flows}
    assert status == {1: (250, 750, "payer", "limited"), 2: (1000, 0, None, "applied"),
                      9: (0, 300, "payer", "absent")}
    sim.wealth[1] = MAX_WEALTH - 0.25
    sunk = M.Bill(purpose="workshop_wage", batch=2, phase="phase10", payer=M.firm_cash(2),
                  lines=((M.agent(1), 1000),), residual="sink:credit_refused")
    got = M.pay(world, sunk, turn=2, book=book, sim=sim, firms=firms)
    assert got.ok and got.applied == 250 and got.sunk == 750
    assert firms[2].cash == 4000 and book.sinks == {"credit_refused": 750}
    assert book.flows[-1].residual_to == "sink:credit_refused"
    M.check_book(book)


def test_an_extension_without_the_purpose_is_refused():
    world, book = _world(), M.MoneyBook()
    old = FakeSim({1: 5.0}, purposes=M.NATIVE_PURPOSES[:7])
    bill = M.Bill(purpose="wares_purchase", batch=1, phase="phase10", payee=M.firm_cash(1),
                  lines=((M.agent(1), 100),))
    with pytest.raises(M.MoneyError, match="rebuild chronicler-agents"):
        M.pay(world, bill, turn=1, book=book, sim=old, firms={1: _firm(0)})
    assert old.wealth == {1: 5.0} and old.calls == 0


def test_the_register_is_read_per_turn_from_active_books():
    from chronicler.livelihoods_state import LivelihoodsState
    from chronicler.workshop_economics_state import WorkshopEconomicsState
    world = _world()
    world.livelihoods = LivelihoodsState()
    assert M.flows_for_turn(world, 3) is None
    world.livelihoods.workshop_economics = state = WorkshopEconomicsState()
    assert M.flows_for_turn(world, 3) == []
    bill = M.Bill(purpose="firm_input_purchase", batch=1, phase="phase2", payer=M.firm_cash(1),
                  lines=((M.treasury(0), 400),))
    M.pay(world, bill, turn=3, book=state.book, firms={1: _firm(400)})
    assert [f.applied for f in M.flows_for_turn(world, 3)] == [400] and M.flows_for_turn(world, 4) == []
    state.enabled = False
    assert M.flows_for_turn(world, 3) is None


def _bill_call_sites():
    """``(module, enclosing function) -> purposes`` of every ``Bill(...)`` built
    under ``src/chronicler`` outside ``money`` itself, and non-literal purposes."""
    import ast
    from pathlib import Path
    root = Path(M.__file__).resolve().parent
    found, problems = {}, []
    for path in sorted(root.rglob("*.py")):
        module = ".".join(path.relative_to(root).with_suffix("").parts)
        if module == "money":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def visit(node, scope):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = node.name if scope == "<module>" else f"{scope}.{node.name}"
                for child in ast.iter_child_nodes(node):
                    visit(child, inner)
                return
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
                if name == "Bill":
                    purpose = next((k.value for k in node.keywords if k.arg == "purpose"), None)
                    if not (isinstance(purpose, ast.Constant) and isinstance(purpose.value, str)):
                        problems.append(f"{module}:{node.lineno}: a Bill without a literal purpose")
                    else:
                        found.setdefault((module, scope), set()).add(purpose.value)
            for child in ast.iter_child_nodes(node):
                visit(child, scope)

        visit(tree, "<module>")
    return {k: tuple(sorted(v)) for k, v in found.items()}, problems


def test_every_caller_of_the_seam_is_registered_with_its_purposes_and_channels():
    """The static guard for callers of ``money.pay`` (the ledger's per-path
    guard sees only the seam's own router): every bill's purpose is literal,
    every (module, function) is in ``MONEY_BILLS``, no row is stale, every
    purpose is registered, and every purpose that can move agent wealth has a
    ledger channel the router declares."""
    from chronicler.wealth_accounting_state import (
        CHANNEL_NAMES, MONEY_BILLS, MONEY_PURPOSE_CHANNELS, WEALTH_ROUTERS,
    )
    found, problems = _bill_call_sites()
    assert not problems, problems
    assert found == {k: tuple(sorted(v)) for k, v in MONEY_BILLS.items()}
    used = {p for purposes in MONEY_BILLS.values() for p in purposes}
    assert used <= set(M.PURPOSES)
    for purpose in used:
        if M.PURPOSES[purpose] is not None:          # a native purpose: it moves agent wealth
            assert purpose in MONEY_PURPOSE_CHANNELS, purpose
    # A3's keyed transfers and A4's pairwise payments each have their router.
    assert set(MONEY_PURPOSE_CHANNELS.values()) == (set(WEALTH_ROUTERS["_native_transfer"])
                                                     | set(WEALTH_ROUTERS["_native_pairs"]))
    assert {MONEY_PURPOSE_CHANNELS[p] for p in MONEY_PURPOSE_CHANNELS if p in M.PAIRWISE_PURPOSES} \
        == set(WEALTH_ROUTERS["_native_pairs"])
    assert set(MONEY_PURPOSE_CHANNELS.values()) <= set(CHANNEL_NAMES)
    assert all(M.PURPOSES.get(p) is not None for p in MONEY_PURPOSE_CHANNELS)


def test_payees_are_validated_before_anything_moves():
    world, book = _world(), M.MoneyBook()
    firms = {1: _firm(5000)}
    # The treasury line sorts first: an unknown firm payee must refuse before it is credited.
    bill = M.Bill(purpose="firm_input_purchase", batch=1, phase="phase2", payer=M.firm_cash(1),
                  lines=((M.treasury(0), 1000), (M.firm_cash(9), 1000)))
    with pytest.raises(M.MoneyError, match="unknown firm 9"):
        M.pay(world, bill, turn=1, book=book, firms=firms)
    bad_civ = M.Bill(purpose="firm_input_purchase", batch=2, phase="phase2", payer=M.firm_cash(1),
                     lines=((M.treasury(7), 1000),))
    with pytest.raises(M.MoneyError, match="unknown civilization 7"):
        M.pay(world, bad_civ, turn=1, book=book, firms=firms)
    sim = FakeSim({1: 2.0})
    collect = M.Bill(purpose="wares_purchase", batch=3, phase="phase10", payee=M.firm_cash(9),
                     lines=((M.agent(1), 100),))
    with pytest.raises(M.MoneyError, match="unknown firm 9"):
        M.pay(world, collect, turn=1, book=book, sim=sim, firms=firms)
    assert world.civilizations[0].treasury == 10 and firms[1].cash == 5000 and sim.calls == 0
    assert sim.wealth == {1: 2.0} and book.flows == [] and book.settled == []


def test_flow_totals_stay_exact_beyond_the_flow_list_bound():
    world, book = _world(), M.MoneyBook()
    n = M.MAX_FLOWS + 40
    sim = FakeSim({aid: 1.0 for aid in range(1, n + 1)})
    firms = {1: _firm(0)}
    bill = M.Bill(purpose="wares_purchase", batch=1, phase="phase10", payee=M.firm_cash(1),
                  lines=tuple((M.agent(a), 3) for a in range(1, n + 1)), regions=tuple(2 for _ in range(n)))
    assert M.pay(world, bill, turn=5, book=book, sim=sim, firms=firms).ok
    assert len(book.flows) == M.MAX_FLOWS and book.flows_dropped == 40
    (total,) = book.totals
    assert (total.purpose, total.payer_kind, total.payee_kind, total.region) == ("wares_purchase", "agent_wealth",
                                                                                 "firm_cash", 2)
    assert total.applied == 3 * n == firms[1].cash and total.count == n
    M.check_book(book)


# --- A4: pairwise payments (an agent paying agents) -----------------------------------

def _pair_bill(batch=1, lines=((2, 1500), (3, 2500)), payer=1, purpose="cargo_purchase"):
    return M.Bill(purpose=purpose, batch=batch, phase="phase10", payer=M.agent(payer),
                  lines=tuple((M.agent(a), v) for a, v in lines), regions=tuple(4 for _ in lines), payer_region=6)


def test_a_pairwise_bill_moves_wealth_from_the_payer_to_each_payee_once():
    world, book = _world(), M.MoneyBook()
    sim = PairSim({1: 10.0, 2: 1.0, 3: 2.0})
    got = M.pay(world, _pair_bill(), turn=5, book=book, sim=sim)
    assert got.ok and (got.total, got.applied, got.residual) == (4000, 4000, 0)
    assert sim.wealth == pytest.approx({1: 6.0, 2: 2.5, 3: 4.5})
    assert sim.keys == [(5, M.PURPOSES["cargo_purchase"], 1)] and M.PURPOSES["cargo_purchase"] == 8
    assert [(f.payer, f.payee, f.applied, f.region, f.payer_region) for f in got.flows] == [
        (("agent_wealth", 1), ("agent_wealth", 2), 1500, 4, 6), (("agent_wealth", 1), ("agent_wealth", 3), 2500, 4, 6)]
    total = book.totals[0]
    assert (total.purpose, total.payer_kind, total.payee_kind, total.region, total.payer_region, total.applied) == (
        "cargo_purchase", "agent_wealth", "agent_wealth", 4, 6, 4000)
    M.check_book(book)
    # Exactly once: the same key is refused before anything moves.
    again = M.pay(world, _pair_bill(), turn=5, book=book, sim=sim)
    assert not again.ok and again.reason == "already_settled" and sim.calls == 1
    # The flows' payer region is omitted from dumps of books without pairwise flows.
    assert "payer_region" not in M.MoneyFlow(turn=1, phase="p", purpose="wares_purchase", batch=0,
                                             payer=("agent_wealth", 1), payee=("firm_cash", 2), requested=1,
                                             applied=1).model_dump()


@pytest.mark.parametrize("wealth, reason", [
    ({1: 3.9, 2: 1.0, 3: 1.0}, "payer_short"),          # cannot pay the whole bill
    ({1: 10.0, 2: 1.0}, "payee_absent"),                # payee 3 is dead or unknown
    ({2: 1.0, 3: 1.0}, "payer_absent"),
])
def test_a_pairwise_bill_is_refused_whole_before_anything_moves(wealth, reason):
    world, book = _world(), M.MoneyBook()
    sim = PairSim(wealth)
    before = dict(sim.wealth)
    got = M.pay(world, _pair_bill(), turn=2, book=book, sim=sim)
    assert not got.ok and got.reason == reason and sim.calls == 0 and sim.wealth == before and not book.settled


def test_a_payees_ceiling_refusal_stays_with_the_payer_and_is_recorded():
    world, book = _world(), M.MoneyBook()
    sim = PairSim({1: 10.0, 2: 99.5, 3: 1.0})
    got = M.pay(world, _pair_bill(), turn=2, book=book, sim=sim)
    assert got.ok and (got.applied, got.residual) == (3000, 1000)
    rich = got.flows[0]
    assert (rich.requested, rich.applied, rich.residual, rich.residual_to, rich.status) == (
        1500, 500, 1000, "payer", "limited")
    assert sim.wealth[1] == pytest.approx(7.0)            # only what the payees took left the payer
    M.check_book(book)


@pytest.mark.parametrize("bill, match", [
    (M.Bill(purpose="wares_purchase", batch=0, phase="p", payer=M.agent(1), lines=((M.agent(2), 5),)),
     "not a pairwise purpose"),
    (M.Bill(purpose="cargo_purchase", batch=0, phase="p", payee=M.firm_cash(1), lines=((M.agent(2), 5),)),
     "paid only by an agent to agents"),
    (M.Bill(purpose="cargo_purchase", batch=0, phase="p", payer=M.agent(1), lines=((M.firm_cash(2), 5),)),
     "pays agents"),
    (M.Bill(purpose="cargo_purchase", batch=0, phase="p", payer=M.agent(1), lines=((M.agent(2), 5),),
            residual="sink:credit_refused"), "returns refused credits"),
    (M.Bill(purpose="cargo_sale", batch=0, phase="p", payer=M.agent(1), lines=((M.agent(2), 5),)),
     "no ledger channel"),
])
def test_pairwise_bills_of_the_wrong_shape_are_refused(bill, match):
    with pytest.raises(M.MoneyError, match=match):
        M.quote(_world(), bill, turn=1, book=M.MoneyBook(), sim=PairSim({1: 1.0, 2: 1.0}))


def test_a_limited_payer_row_is_a_stale_read():
    class Stale(PairSim):
        def settle_pairs(self, turn, purpose, batch, rows):
            out = super().settle_pairs(turn, purpose, batch, rows)
            return [(a, b, r, s - 1, c - 1, f, 1) for a, b, r, s, c, f, _st in out]
    with pytest.raises(M.MoneyError, match="stale"):
        M.pay(_world(), _pair_bill(), turn=1, book=M.MoneyBook(), sim=Stale({1: 10.0, 2: 1.0, 3: 1.0}))


def test_a_book_pickled_before_pairwise_flows_loads_and_checks():
    """Review m1: ``payer_region`` was added to flows and totals; a book
    pickled before it (main's A3 books) restores with the default."""
    world, book = _world(), M.MoneyBook()
    firms = {1: _firm(0)}
    sim = FakeSim({30: 5.0})
    bill = M.Bill(purpose="wares_purchase", batch=1, phase="phase10", payee=M.firm_cash(1),
                  lines=((M.agent(30), 1500),), regions=(2,))
    assert M.pay(world, bill, turn=3, book=book, sim=sim, firms=firms).ok
    for model in (*book.flows, *book.totals):
        del model.__dict__["payer_region"]                # as an object restored from an older pickle
    back = pickle.loads(pickle.dumps(book))
    assert all(f.payer_region is None for f in back.flows) and all(t.payer_region is None for t in back.totals)
    M.check_book(back)
    assert back.model_dump() == M.MoneyBook.model_validate(back.model_dump()).model_dump()
