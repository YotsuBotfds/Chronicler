"""Named B3 farm crews when PL3 --recovery-crews is active.

No new native purpose: infrastructure_wage rides repair_wage in a disjoint
batch. Wages and materials are separately quoted against one finite budget.
Refused wealth credits return to the treasury's wage carry, never a sink.
"""
from __future__ import annotations

import math

from chronicler.infrastructure_condition_state import WorksCrewMember

WAGE_MILLI = 500
WAGE_BATCH = 0xB3000
PURPOSE = "infrastructure_wage"


def active(world):
    from chronicler.recovery_crews import recovery_crews_active
    return recovery_crews_active(world)


def mode(world):
    return world.livelihoods.recovery_crews.mode


def plan(world, p, amount, *, sim, snapshot):
    from chronicler.recovery_crews import plan_granary_crew
    return plan_granary_crew(world, p, amount, sim=sim, snapshot=snapshot, priority=[], offer_kind="infrastructure")


def _quote_bills(world, state, civ, wage_bill, material_bill, *, sim, acc):
    from chronicler.money import quote
    from chronicler.mutual_aid import _treasury_budget
    # The wage carry and the material prepaid remainder are distinct accounts.
    # Material bills have already spent their prepaid part in their amount.
    carry = state.book.carry.get(f"{civ}:{PURPOSE}", 0)
    wage_need = sum(v for _, v in wage_bill.lines) if wage_bill else 0
    wage_units = max(0, -(-(wage_need - carry) // 1000))
    material_units = sum(v for _, v in material_bill.lines) // 1000 if material_bill else 0
    available = max(0, math.floor(_treasury_budget(world, world.civilizations[civ], acc)))
    if wage_units + material_units > available:
        raise RuntimeError("infrastructure crew bills exceed their shared treasury reservation")
    for bill in (wage_bill, material_bill):
        if bill:
            q = quote(world, bill, turn=world.turn, book=state.book, sim=sim, acc=acc)
            if not q.ok:
                raise RuntimeError(f"infrastructure crew bill refused before settlement ({q.reason})")


def settle(world, state, t, sim, acc):
    """Quote all civs before any payment; then pay each distinct bill once.

    Returns total treasury charge/material carry per civ and extra closure
    columns. A failed quote reaches neither native withholding nor payment.
    """
    from chronicler import infrastructure_condition as I
    from chronicler.money import Bill, agent, pay, treasury
    from chronicler.recovery_crews import granary_shares, split_wages
    paid = mode(world) == "paid"
    grouped = {}
    for p in t.plans:
        worked = granary_shares(p, p.delivered)
        # One person cannot be in two plans: the shared registry reserved all
        # names before the next plan's candidate query.
        p.crew_worked = worked
        p.crew_wages = split_wages(max(0, math.floor(p.delivered * WAGE_MILLI + 1e-6)), worked) if paid else {a: 0 for a, _ in worked}
        row = grouped.setdefault(p.payer, {"nominal": 0, "wages": {}, "regions": {}})
        row["nominal"] += I._coin_milli(p.delivered, p.kind)
        for aid, amount in p.crew_wages.items():
            if aid in row["wages"]:
                raise RuntimeError("one person is on two infrastructure crews")
            row["wages"][aid] = amount
            row["regions"][aid] = p.region
    bills = {}
    for civ, row in sorted(grouped.items()):
        if civ < 0:
            continue
        requested = sum(row["wages"].values())
        material = row["nominal"] - requested
        if material < 0:
            raise RuntimeError("infrastructure wages exceed the nominal work cost")
        before = int(state.prepaid.get(civ, 0))
        material_units = max(0, -(-(material - before) // 1000))
        material_after = material_units * 1000 + before - material
        ordered = sorted((aid, value) for aid, value in row["wages"].items() if value > 0)
        wages = Bill(purpose="infrastructure_wage", batch=WAGE_BATCH+civ, phase="phase2", payer=treasury(civ),
                     lines=tuple((agent(aid), value) for aid, value in ordered),
                     regions=tuple(row["regions"][aid] for aid, _ in ordered)) if ordered else None
        materials = I._bill(civ, material_units) if material_units else None
        _quote_bills(world, state, civ, wages, materials, sim=sim, acc=acc)
        env = next((p.envelope for p in t.plans if p.payer == civ), None)
        wage_before = state.book.carry.get(f"{civ}:{PURPOSE}", 0)
        max_wage_units = max(0, -(-(requested-wage_before)//1000))
        if env is not None and material_units + max_wage_units > env:
            raise RuntimeError("infrastructure crew bills exceed their shared envelope")
        bills[civ] = (row, wages, materials, before, material_units, material_after, wage_before)
    charges, extras, applied = {}, {}, {}
    for civ, (row, wages, materials, before, units, after, wage_before) in sorted(bills.items()):
        wage_receipt = pay(world, wages, turn=world.turn, book=state.book, sim=sim, acc=acc) if wages else None
        if wage_receipt is not None and not wage_receipt.ok:
            raise RuntimeError("a prequoted infrastructure wage bill was refused")
        material_receipt = pay(world, materials, turn=world.turn, book=state.book, acc=acc) if materials else None
        if material_receipt is not None and not material_receipt.ok:
            raise RuntimeError("a prequoted infrastructure material bill was refused")
        requested = sum(row["wages"].values())
        credited = wage_receipt.applied if wage_receipt else 0
        for flow in wage_receipt.flows if wage_receipt else []:
            applied[int(flow.payee[1])] = (flow.applied, flow.residual)
        wage_after = state.book.carry.get(f"{civ}:{PURPOSE}", 0)
        charges[civ] = (before, units-(wage_receipt.treasury_units if wage_receipt else 0), after)
        extras[civ] = dict(nominal_cost_milli=row["nominal"], wages_requested_milli=requested,
                           wages_milli=credited, wages_refused_milli=requested-credited,
                           wage_carry_before_milli=wage_before, wage_carry_after_milli=wage_after,
                           coin_cost_milli=row["nominal"]-requested+credited)
    install = []
    for p in t.plans:
        got = dict(p.crew_worked)
        p.members = [WorksCrewMember(agent_id=aid, origin=origin, share=share, worked=got.get(aid, 0),
                    wage_requested_milli=p.crew_wages.get(aid, 0), wages_milli=applied.get(aid, (0, 0))[0],
                    wage_refused_milli=applied.get(aid, (0, 0))[1]) for aid, origin, share, _v in p.named]
        install.extend((aid, share) for aid, share in p.crew_worked if share > 0)
    if install:
        sim.extend_paid_work(world.turn, sorted(install))
    return charges, extras
