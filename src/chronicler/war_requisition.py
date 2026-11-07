"""D4: requisition reaches carried rations; every source and residual is dated.

The legacy destructive war seams remain the physical debit authorities. We
observe before/after there, move removed food into armies that actually stand
in the region, and book the uncarried remainder as destruction. Transfer mode
replaces generated refill/forage and initial kits with real commons supply;
cost_only removes the same physical supply while retaining legacy kit credit.
Residence and attachment are distinct: soldiers still migrate natively. This
module never moves native agents or writes the residence ledger.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from chronicler import money
from chronicler.war_requisition_state import (
    COUNTERS, MAX_CLAIMS, MAX_ROWS, MODES, RestitutionClaim, WarRequisitionState,
)

MILLI = 1000
FOOD_PER_RATION_MILLI = 500
RESTITUTION_BATCH = 0xD4000


def _state(world):
    return getattr(getattr(world, "livelihoods", None), "war_requisition", None)


def war_requisition_active(world):
    state = _state(world)
    return bool(state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid")


def set_war_requisition_enabled(world, value, *, args=None, agent_mode=None):
    state = _state(world)
    mode = getattr(args, "war_requisition_mode", None) if args is not None else None
    if state is None:
        world.livelihoods.war_requisition = state = WarRequisitionState(mode=mode or MODES[0])
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)


def _bump(state, key, value=1):
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + int(value)


def _event(world, state, **row):
    turn = int(world.turn)
    if state.events_turn != turn:
        state.events_turn, state.events, state.events_dropped = turn, [], 0
    if len(state.events) < MAX_ROWS:
        state.events.append({"source_turn": turn, **row})
    else:
        state.events_dropped += 1


def _rid(world, region):
    return next(i for i, r in enumerate(world.regions) if r is region)


def _civ(world, actor):
    name = getattr(actor, "name", actor)
    return next((i for i in reversed(range(len(world.civilizations)))
                 if world.civilizations[i].name == name), None)


def _commons(region):
    from chronicler.economy import FOOD_GOODS
    return math.fsum(max(0.0, region.stockpile.goods.get(g, 0.0)) for g in FOOD_GOODS)


def _granary(world, rid):
    from chronicler.grain_reserves import grain_reserves_active
    if not grain_reserves_active(world):
        return 0.0
    state = world.grain_reserves
    return max(0.0, state.granaries[rid].grain) if rid < len(state.granaries) else 0.0


def _retail(world, rid):
    state = getattr(getattr(world, "livelihoods", None), "household_retail", None)
    reg = state.region(rid) if state is not None and state.enabled else None
    if reg is None:
        return {}, 1000
    # Price already determined at the retail opening, in milli-wealth/ration.
    t = getattr(state, "_turn", None)
    book = getattr(t, "books", {}).get(rid) if t is not None else None
    return dict(reg.claims), int(getattr(book, "price_milli", None) or 1000)


@dataclass(frozen=True)
class LossOpening:
    region: int
    commons: float
    granary: float
    claims: dict[int, int]
    price_milli: int


def capture_loss(world, region):
    if world is None or not war_requisition_active(world):
        return None
    rid = _rid(world, region)
    claims, price = _retail(world, rid)
    return LossOpening(rid, _commons(region), _granary(world, rid), claims, price)


def _claim(world, state, payer, owner, region, due, source):
    if payer is None or due <= 0:
        return
    # Merge liabilities for the same payer/person/place; stable id survives.
    existing = next((c for c in state.claims if c.status == "open" and
                     (c.payer, c.owner, c.region, c.source) == (payer, owner, region, source)), None)
    if existing is not None:
        existing.due_milli += due
    elif len(state.claims) < MAX_CLAIMS:
        state.claims.append(RestitutionClaim(id=state.next_claim, turn=world.turn, payer=payer,
                            owner=owner, region=region, due_milli=due, source=source))
        state.next_claim += 1
    else:
        _bump(state, "claims_unrecorded_milli", due)
        return
    _bump(state, "claims_due_milli", due)


def _credit_removed(world, state, region, actor, milli):
    from chronicler.war.params import POLICY
    credited = 0
    allocations = []
    if state.mode == "transfer":
        armies = sorted((a for a in world.war_state.armies if a.region == region.name
                         and a.civ == getattr(actor, "name", actor) and a.soldiers > 0), key=lambda a: a.army_id)
        remaining = milli // FOOD_PER_RATION_MILLI
        for army in armies:
            given = min(remaining, max(0, army.soldiers * POLICY.carried_limit - army.rations))
            if given:
                army.rations += given
                allocations.append({"army": army.army_id, "rations": given})
                credited += given
                remaining -= given
    _bump(state, "rations_credited", credited)
    destroyed = milli - credited * FOOD_PER_RATION_MILLI
    _bump(state, "destroyed_milli", destroyed)
    return allocations, destroyed


def finish_loss(world, region, actor, cause, opening):
    if opening is None:
        return
    state = _state(world)
    claims, _ = _retail(world, opening.region)
    owned = {aid: max(0, amount - claims.get(aid, 0)) for aid, amount in opening.claims.items()}
    commons = max(0, int(round((opening.commons - _commons(region)) * MILLI)))
    granary = max(0, int(round((opening.granary - _granary(world, opening.region)) * MILLI)))
    total = commons + granary + sum(owned.values())
    allocations, destroyed = _credit_removed(world, state, region, actor, total)
    payer = _civ(world, actor)
    for aid, amount in sorted(owned.items()):
        _claim(world, state, payer, aid, opening.region,
               amount * 2 * opening.price_milli // MILLI, "owned_food")
    _bump(state, "events")
    _bump(state, "removed_milli", total)
    _event(world, state, kind="requisition", region=opening.region, payer=payer, cause=cause,
           commons_milli=commons, granary_milli=granary, owned_milli=sum(owned.values()),
           allocations=allocations, removed_milli=total, destroyed_milli=destroyed)


def _withdraw(world, state, rid, requested, kind, army):
    """Whole kits only; debit exactly 0.5 food per credited ration."""
    from chronicler.economy import FOOD_GOODS
    region = world.regions[rid]
    # Reserved merchant loads still belong to the commons but are already
    # committed. Reuse the native read-only commitment interface, as L4/aid do.
    from chronicler.mutual_aid import read_stockpile_commitments, _free_goods
    sim = getattr(getattr(world, "_agent_bridge", None), "_sim", None)
    commitments = read_stockpile_commitments(world, sim) if sim is not None else {}
    free = _free_goods(region, commitments)
    available = int(math.floor((math.fsum(free.values()) + 1e-10) * 2))
    taken = min(max(0, requested), available)
    left = taken / 2
    for good in FOOD_GOODS:
        amount = min(free.get(good, 0.0), left)
        if amount:
            region.stockpile.goods[good] -= amount
            left -= amount
    if left > 1e-8:
        raise RuntimeError("army supply debit did not close")
    _bump(state, "forage_food_milli" if kind == "forage" else "refill_food_milli", taken * 500)
    _event(world, state, kind=kind, region=rid, army=army.army_id,
           removed_milli=taken * 500, credited_rations=taken if state.mode == "transfer" else 0)
    return taken


def supply(world, army, refill, forage, sources, graph, here, *, initial=False):
    """Return (refill, forage) after replacing model-created supply.

    Reachable friendly sources are sorted by distance then region id. This
    never withdraws more than free carried capacity, even when refill and
    foraging compete or a requisition filled the kits before this step.
    """
    if not war_requisition_active(world):
        return refill, forage
    from collections import deque
    from chronicler.war.params import POLICY
    state = _state(world)
    if state.supply_turn != world.turn:
        state.supply_turn, state.supplied = world.turn, []
    key = army.army_id + (":initial" if initial else ":tick")
    if key in state.supplied:
        raise RuntimeError("army supply already executed for this turn")
    state.supplied.append(key)
    room = max(0, army.soldiers * POLICY.carried_limit - army.rations)
    refill_wanted = min(room, max(0, refill))
    forage_wanted = min(room - refill_wanted, max(0, forage))
    distances, queue = {here: 0}, deque([here])
    while queue:
        node = queue.popleft()
        for nb in sorted(graph.get(node, ())):
            if nb not in distances:
                distances[nb] = distances[node] + 1
                queue.append(nb)
    filled = 0
    for rid in sorted((r for r in sources if r in distances), key=lambda r: (distances[r], r)):
        if distances[rid] > 3:
            continue
        filled += _withdraw(world, state, rid, refill_wanted - filled, "initial" if initial else "refill", army)
        if filled == refill_wanted:
            break
    # Unmet refill leaves room for real local foraging, bounded by its quote.
    foraged = _withdraw(world, state, here, min(max(0, forage), room - filled), "forage", army) if forage else 0
    _bump(state, "initial_requested" if initial else "refill_requested", refill_wanted + forage_wanted)
    _bump(state, "initial_credited" if initial else "refill_credited", filled + foraged if state.mode == "transfer" else min(room, refill + forage))
    return (filled, foraged) if state.mode == "transfer" else (refill, forage)


def seize_cargo(world, ship, trade_state, turn_state):
    """Close hostile food cargo once where a hostile field army stands.

    A distant change of destination controller is still a return: seizure
    needs actual custody at the cargo's current region, before or after a hop.
    """
    if not war_requisition_active(world) or ship.status != "moving":
        return False
    from chronicler.war.common import at_war
    from chronicler import titled_trade as TT
    state = _state(world)
    region = world.regions[ship.region()]
    origin_polity = ship.controllers[0]
    actors = sorted((a for a in world.war_state.armies if a.region == region.name and a.soldiers > 0
                     and origin_polity and at_war(world, a.civ, origin_polity)), key=lambda a: a.army_id)
    if not actors:
        return False
    actor = actors[0].civ
    total = ship.total()
    allocations, destroyed = _credit_removed(world, state, region, actor, total)
    payer = _civ(world, actor)
    _claim(world, state, payer, ship.holder, ship.region(),
           ship.cost_milli * total // max(1, sum(ship.cargo_open)), "cargo")
    ship.losses["war_seizure"] = ship.losses.get("war_seizure", 0) + total
    ship.cargo = [0] * len(ship.cargo)
    TT._close(world, trade_state, ship, world.turn, "seized", None, turn_state)
    TT._bump(trade_state, "war_seizure_milli", total)
    _bump(state, "cargo_seized_milli", total)
    _bump(state, "removed_milli", total)
    _event(world, state, kind="cargo_seizure", shipment=ship.id, owner=ship.holder,
           region=ship.region(), payer=payer, removed_milli=total, allocations=allocations,
           destroyed_milli=destroyed)
    return True


def _settle(world, state, sim, acc):
    """Pay living claimants from the liable state's existing treasury only.

    Death or pool rebuild lapses an unfulfilled personal promise explicitly;
    it does not transfer money, grain, or native wealth. Arrears and ceiling
    refusals remain open, so an insolvent state never mints restitution.
    """
    from chronicler.columnar import pylist
    alive = set(int(aid) for aid in pylist(sim.get_snapshot().column("id")))
    for claim in state.claims:
        if claim.status != "open":
            continue
        if claim.owner not in alive:
            claim.status = "owner_dead"
            _bump(state, "claims_lapsed_milli", claim.due_milli - claim.paid_milli)
    for payer in sorted({c.payer for c in state.claims if c.status == "open"}):
        if not 0 <= payer < len(world.civilizations):
            continue
        available = money._civ_budget(world, payer, acc) * MILLI
        available += state.book.carry.get(f"{payer}:restitution", 0)
        by_owner = {}
        allocations = []
        for claim in sorted(state.claims, key=lambda c: c.id):
            if claim.payer != payer or claim.status != "open":
                continue
            amount = min(available, claim.due_milli - claim.paid_milli)
            if amount:
                by_owner[claim.owner] = by_owner.get(claim.owner, 0) + amount
                allocations.append((claim, amount))
                available -= amount
        if not by_owner:
            continue
        bill = money.Bill(purpose="restitution", batch=RESTITUTION_BATCH + payer, phase="phase10",
                          payer=money.treasury(payer),
                          lines=tuple((money.agent(owner), amount) for owner, amount in sorted(by_owner.items())))
        receipt = money.pay(world, bill, turn=world.turn, book=state.book, sim=sim, acc=acc)
        if not receipt.ok:
            continue
        paid = {int(f.payee[1]): f.applied for f in receipt.flows or []}
        for claim, amount in allocations:
            applied = min(amount, paid.get(claim.owner, 0))
            claim.paid_milli += applied
            paid[claim.owner] -= applied
            if claim.paid_milli == claim.due_milli:
                claim.status = "paid"
        _bump(state, "restitution_paid_milli", receipt.applied)


def phase10(world, acc, economy_result, agent_bridge):
    state = _state(world)
    if state.last_settled_turn is not None and state.last_settled_turn >= world.turn:
        raise RuntimeError("war requisition phase10 ran twice")
    if any(c.status == "open" for c in state.claims):
        sim = getattr(agent_bridge, "_sim", None)
        if sim is None:
            raise RuntimeError("war restitution requires the native simulator")
        _settle(world, state, sim, acc)
    state.last_settled_turn, state.frame_turn = int(world.turn), int(world.turn)
    state.frame = {"turn": int(world.turn), "events": list(state.events) if state.events_turn == world.turn else [],
                   "events_dropped": state.events_dropped if state.events_turn == world.turn else 0,
                   "claims": [c.model_dump() for c in state.claims[-MAX_ROWS:]],
                   "claims_dropped": max(0, len(state.claims) - MAX_ROWS),
                   "claims_open": sum(c.status == "open" for c in state.claims),
                   "claims_due_milli": sum(c.due_milli - c.paid_milli for c in state.claims if c.status == "open")}
    _bump(state, "frames")
    money.check_book(state.book)
    return []


def on_pool_reset(world):
    state = _state(world)
    if state is None:
        return
    for claim in state.claims:
        if claim.status == "open":
            claim.status = "pool_reset"
            _bump(state, "claims_lapsed_milli", claim.due_milli - claim.paid_milli)
    _bump(state, "pool_resets")


def snapshot_summary(world):
    state = _state(world)
    return {"schema_version": 1, "stage": "D4", "mode": state.mode, "enabled": state.enabled,
            "source_turn": state.frame_turn, "frame": state.frame,
            "counters": {k: state.counters.get(k, 0) for k in COUNTERS}}


def enlisted_ids(world):
    """Stable ids whose civilian food and farm work the native seam suppresses.

    Army attachment applies even when residence equals the army region: the
    army logistics already provisions these people. Migration stays native.
    """
    if not war_requisition_active(world):
        return []
    return sorted({int(aid) for army in world.war_state.armies for aid, _ in army.roster})


def note_consumption(world, army, consumed, demand):
    """Date actual kit consumption; released people retain this turn's meal.

    This is food information only, never a second death authority. The native
    food term sees the same shortfall the existing army stress/attrition sees.
    """
    if not war_requisition_active(world):
        return
    state = _state(world)
    if state.feeding_turn != world.turn:
        state.feeding_turn, state.feeding, state.fed_ids = world.turn, {}, {}
    if army.army_id in state.feeding:
        raise RuntimeError("army ration consumption observed twice")
    fraction = min(1.0, max(0.0, consumed / demand)) if demand > 0 else 0.0
    state.feeding[army.army_id] = fraction
    for aid, _ in army.roster:
        state.fed_ids[int(aid)] = fraction
    _event(world, state, kind="consumption", army=army.army_id,
           consumed_rations=int(consumed), demanded_rations=int(demand), adequacy=fraction)


def enlisted_service_rows(world, *, after_logistics=False):
    """Native service input, refreshed before economy and before agent tick.

    The Phase 2 read supplies the last meal and excludes this turn's live
    enlisted labour. The before-tick read uses this turn's actual consumption;
    a newly raised army that skipped logistics consumes existing kits once.
    Roster releases after a meal keep their service row through this tick, so
    demobilization/desertion cannot create a second civilian meal.
    """
    if not war_requisition_active(world):
        return []
    from chronicler.war.params import POLICY
    state = _state(world)
    if after_logistics:
        for army in sorted(world.war_state.armies, key=lambda a: a.army_id):
            if state.feeding_turn == world.turn and army.army_id in state.feeding:
                continue
            demand = army.soldiers * POLICY.ration_demand
            consumed = min(max(0, army.rations), demand)
            army.rations -= consumed
            note_consumption(world, army, consumed, demand)
        rows = dict(state.fed_ids) if state.feeding_turn == world.turn else {}
    else:
        rows = {}
    for army in world.war_state.armies:
        fraction = state.feeding.get(army.army_id, 0.0) if state.feeding_turn in (world.turn, world.turn - 1) else 0.0
        for aid, _ in army.roster:
            rows.setdefault(int(aid), fraction)
    return sorted(rows.items())


def note_cargo_seizure(world, *, owner, region, actor, value_milli, shipment, goods="timber", quantity_milli=0):
    """Non-food custody seam for A4-3: caller transfers its actual cargo.

    This records an existing physical seizure and its acquisition-value
    liability only; it creates neither timber nor ration kits. The caller
    retains sole authority over its cargo's single terminal outcome.
    """
    if not war_requisition_active(world):
        return
    if not isinstance(value_milli, int) or value_milli < 0 or not 0 <= region < len(world.regions):
        raise ValueError("cargo restitution needs a nonnegative acquisition value and real region")
    state = _state(world)
    payer = _civ(world, actor)
    _claim(world, state, payer, int(owner), int(region), value_milli, str(goods))
    _event(world, state, kind="cargo_seizure", goods=str(goods), shipment=shipment,
           package="timber_orders", owner=int(owner), region=int(region), payer=payer,
           quantity_milli=int(quantity_milli), acquisition_value_milli=value_milli)
