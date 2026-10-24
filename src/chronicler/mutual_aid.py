"""Default-off, treasury-funded adjacent mutual aid using existing food stocks.

Observe Phase 2 sufficiency at N; dispatch before the economy at N+1. This is
a small coordination rule, not the Phase 8 institution lifecycle. No production,
ecology, fertility, migration or merchant planning is changed here.
"""
from __future__ import annotations

from chronicler.columnar import pylist
from collections import Counter
import math

from chronicler.economy import FIXED_GOODS, FOOD_GOODS, PER_CAPITA_FOOD, TRANSIT_DECAY
from chronicler.models import Event, MutualAidState, MutualAidTransfer, WorldState
from chronicler.tuning import get_override

# Experimental hypotheses [CALIBRATE], not empirically fitted parameters.
STRESS_THRESHOLD = 0.8
ACTIVATION_TURNS = 3
DONOR_RESERVE_TURNS = 2.0
DONOR_CAPACITY_FRACTION = 0.25
RECIPIENT_CAPACITY_FRACTION = 0.5
TREASURY_COST_PER_UNIT = 0.1


def _populations(world, snapshot) -> dict[str, int]:
    counts = Counter(pylist(snapshot.column("region")))
    return {r.name: counts[i] for i, r in enumerate(world.regions)}


def _owned(world, region) -> bool:
    civ = world.civ_map.get(region.controller)
    return civ is not None and region.name in civ.regions


def _food(region) -> float | None:
    values = [region.stockpile.goods.get(g, 0.0) for g in sorted(FOOD_GOODS)]
    if any(not math.isfinite(v) or v < 0 for v in values):
        return None
    total = math.fsum(values)
    return total if math.isfinite(total) else None


def _fresh_state(world, region):
    state = world.mutual_aid_state.get(region.name)
    if (state is None or state.controller != region.controller
            or state.last_observed_turn != world.turn - 1):
        return None
    return state


def read_stockpile_commitments(world: WorldState, simulator) -> dict[str, dict[str, float]]:
    """Read the native ledger without draining it or counting pending arrivals.

    In-transit cargo already debited from stocks is not subtracted twice.
    Returns/arrivals are not yet available for dispatch. Non-hybrid economy
    uses abstract trade, so shadow reservations do not encumber physical stocks.
    """
    if world.agent_mode != "hybrid":
        return {}
    if not hasattr(simulator, "get_stockpile_commitments"):
        raise RuntimeError("Hybrid mutual aid requires get_stockpile_commitments; rebuild chronicler-agents")
    batch = simulator.get_stockpile_commitments()
    rows = zip(*(pylist(batch.column(c)) for c in
                 ("region_id", "good_slot", "reserved", "pending_departure")), strict=True)
    commitments = {r.name: {} for r in world.regions}
    for rid, slot, reserved, departure in rows:
        if not 0 <= rid < len(world.regions) or not 0 <= slot < len(FIXED_GOODS):
            raise ValueError("Mutual aid commitment batch has invalid region/good index")
        goods = commitments[world.regions[rid].name]
        good = FIXED_GOODS[slot]
        if good in goods or any(not math.isfinite(v) or v < 0 for v in (reserved, departure)):
            raise ValueError("Mutual aid commitment batch has duplicate/invalid values")
        goods[good] = reserved + departure
    if any(set(goods) != set(FIXED_GOODS) for goods in commitments.values()):
        raise ValueError("Mutual aid commitment batch is incomplete")
    return commitments


def _free_goods(region, commitments):
    return {g: max(0.0, region.stockpile.goods.get(g, 0.0)
                   - commitments.get(region.name, {}).get(g, 0.0)) for g in sorted(FOOD_GOODS)}


def observe_mutual_aid(world: WorldState, economy_result, snapshot) -> None:
    """Record one observation per turn; missing data breaks the stress streak."""
    if not world.mutual_aid_enabled:
        return
    if economy_result is None or snapshot is None:
        world.mutual_aid_state = {}
        return
    populations = _populations(world, snapshot)
    states = {}
    for region in world.regions:
        suff = economy_result.food_sufficiency.get(region.name)
        if (not _owned(world, region) or populations[region.name] <= 0
                or suff is None or not math.isfinite(suff) or not 0 <= suff <= 2):
            continue
        previous = world.mutual_aid_state.get(region.name)
        if (previous is not None and previous.controller == region.controller
                and previous.last_observed_turn == world.turn):
            states[region.name] = previous
            continue
        previous = _fresh_state(world, region)
        streak = (previous.stress_streak if previous else 0) + 1
        states[region.name] = MutualAidState(
            controller=region.controller, last_observed_turn=world.turn,
            food_sufficiency=suff,
            stress_streak=min(streak, ACTIVATION_TURNS) if suff < STRESS_THRESHOLD else 0,
        )
    world.mutual_aid_state = states


def _treasury_budget(world, civ, acc) -> float:
    budget = float(civ.treasury)
    if acc is not None:
        # Match the existing projected-war-treasury pattern in simulation.py.
        # Replay unapplied keep changes with the accumulator's nonnegative clamp.
        civ_idx = world.civ_index_map[civ.name]
        for change in acc._changes[acc._keep_applied_up_to:]:
            if (change.civ_id == civ_idx and change.stat == "treasury"
                    and change.category == "keep"):
                budget = type(civ.treasury)(max(0.0, budget + change.delta))
    return budget


def dispatch_mutual_aid(world: WorldState, snapshot, acc=None, *, commitments=None) -> list[Event]:
    """Transfer real food before economy input packing; debit treasury as keep.

    Capacity is per donor per turn and per recipient per turn, shared across
    edges. Recipients are ordered by lagged sufficiency, then name; donors and
    goods by name. Received aid cannot be forwarded in the same dispatch.
    """
    if (not world.mutual_aid_enabled or snapshot is None
            or world.mutual_aid_last_dispatch_turn == world.turn):
        return []
    if world.agent_mode == "hybrid" and commitments is None:
        raise RuntimeError("Hybrid mutual aid requires native stockpile commitment accounting")
    commitments = commitments or {}
    if world.agent_mode == "hybrid":
        if any(set(commitments.get(r.name, {})) != set(FIXED_GOODS) for r in world.regions):
            raise ValueError("Hybrid mutual aid requires complete per-good commitment accounting")
        if any(not math.isfinite(v) or v < 0 for goods in commitments.values() for v in goods.values()):
            raise ValueError("Hybrid mutual aid commitments must be finite and nonnegative")
    per_capita_food = get_override(world, "economy.per_capita_food", PER_CAPITA_FOOD)
    if not math.isfinite(per_capita_food) or per_capita_food <= 0:
        raise ValueError("Mutual aid requires finite positive economy.per_capita_food")
    world.mutual_aid_last_dispatch_turn = world.turn
    world.mutual_aid_last_transfers = []
    populations = _populations(world, snapshot)
    eligible = {
        r.name: r for r in world.regions
        if _owned(world, r) and populations[r.name] > 0
        and _fresh_state(world, r) is not None and _food(r) is not None
    }
    donors = {}
    recipients = []
    for name, region in eligible.items():
        state = world.mutual_aid_state[name]
        demand = populations[name] * per_capita_food
        if state.food_sufficiency >= 1.0:
            donors[name] = min(
                max(0.0, math.fsum(_free_goods(region, commitments).values()) - DONOR_RESERVE_TURNS * demand),
                DONOR_CAPACITY_FRACTION * demand,
            )
        elif state.stress_streak >= ACTIVATION_TURNS:
            recipients.append(region)
    recipients.sort(key=lambda r: (world.mutual_aid_state[r.name].food_sufficiency, r.name))
    budgets = {c.name: _treasury_budget(world, c, acc) for c in world.civilizations}
    events = []
    for recipient in recipients:
        demand = populations[recipient.name] * per_capita_food
        need = min(
            demand * (1.0 - world.mutual_aid_state[recipient.name].food_sufficiency),
            max(0.0, demand - math.fsum(_free_goods(recipient, commitments).values())),
            RECIPIENT_CAPACITY_FRACTION * demand,
        )
        civ = world.civ_map[recipient.controller]
        for name in sorted(donors):
            donor = eligible[name]
            if (need <= 1e-9 or donors[name] <= 1e-9 or budgets[civ.name] < 1
                    or donor.controller != recipient.controller
                    or recipient.name not in donor.adjacencies
                    or donor.name not in recipient.adjacencies):
                continue
            free = _free_goods(donor, commitments)
            total = math.fsum(free.values())
            shares = {g: v / total for g, v in free.items()}
            survival = math.fsum(shares[g] * (1 - TRANSIT_DECAY[g]) for g in shares)
            amount = min(donors[name], need / survival,
                         math.floor(budgets[civ.name]) / TREASURY_COST_PER_UNIT)
            if amount <= 1e-9:
                continue
            cost = math.ceil(amount * TREASURY_COST_PER_UNIT)
            sent = {g: amount * share for g, share in shares.items() if share > 0}
            received = {g: v * (1 - TRANSIT_DECAY[g]) for g, v in sent.items()}
            delivered = math.fsum(received.values())
            for good, value in sent.items():
                donor.stockpile.goods[good] -= value
                recipient.stockpile.goods[good] = recipient.stockpile.goods.get(good, 0.0) + received[good]
            donors[name] -= amount
            need -= delivered
            budgets[civ.name] -= cost
            if acc is None:
                civ.treasury -= cost
            else:
                acc.add(world.civ_index_map[civ.name], civ, "treasury", -cost, "keep")
            transfer = MutualAidTransfer(
                turn=world.turn, controller=civ.name, donor=name, recipient=recipient.name,
                sent=sent, received=received, transit_loss=amount - delivered,
                treasury_cost=cost,
            )
            world.mutual_aid_last_transfers.append(transfer)
            events.append(Event(
                turn=world.turn, event_type="mutual_aid", actors=[civ.name], importance=3,
                description=(f"{name} sent {amount:.3f} food to {recipient.name}; "
                             f"{delivered:.3f} arrived, treasury cost {cost}."),
            ))
    return events
