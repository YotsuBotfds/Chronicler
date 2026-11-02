"""Explicit, opt-in Phase 10 academy service settlement; no simulation hooks.

Counts are caller-observed native agents, not seat.scholars, masters or refugees.
One unit of delivered learner-equivalent consumes one unit of local crafts.
Receipts represent a modeled service allocation, not measured teaching work.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from chronicler.learning_services_state import AcademyServiceReceipt, LearningServicesState
from chronicler.scholarship_state import ACADEMY, scholarship_on
from chronicler.war.common import add_stat, projected_treasury

LEARNERS_PER_SCHOLAR = 8
CRAFTS_PER_LEARNER = 1.0


@dataclass(frozen=True)
class AcademyServiceInput:
    seat_id: int
    demand: int | None
    native_staff: int | None
    upkeep_paid: bool | None
    craft_price: float | None
    # Sum of native reserved loading and pending departures; None means unknown.
    crafts_committed: float | None


def _nonnegative_int(value):
    return type(value) is int and value >= 0


def _nonnegative_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def settle_academy_services(world, inputs: list[AcademyServiceInput], *, acc=None):
    """Settle one complete, unique input batch once per turn; return receipts.

    Caller supplies actual upkeep results, Phase 10 counts, prices and current
    private commitments. Missing observations stay unknown and cannot buy or
    deliver. Crafts are bought from the local stock once, for a domestic sink;
    treasury payments use the existing keep projection/accumulator. Inputs
    are validated before any mutation. No service is provided when disabled.
    """
    if not scholarship_on(world) or getattr(world.scholarship, "learning_services", None) is None:
        return []
    state = world.scholarship.learning_services
    if not isinstance(state, LearningServicesState):
        raise ValueError("invalid learning services state")
    if not _nonnegative_int(world.turn) or (state.last_source_turn is not None and world.turn <= state.last_source_turn):
        raise ValueError("academy service turn already settled or out of order")
    if not isinstance(inputs, list):
        raise ValueError("academy service inputs must be a list")
    seen = set()
    # Validate all entries and their host before making any financial changes.
    for item in inputs:
        if not isinstance(item, AcademyServiceInput) or not _nonnegative_int(item.seat_id) or item.seat_id in seen or item.seat_id >= len(world.scholarship.seats):
            raise ValueError("invalid or duplicate academy seat")
        seen.add(item.seat_id)
        seat = world.scholarship.seats[item.seat_id]
        if (seat.kind != ACADEMY or seat.fallen_turn is not None or seat.level <= 0
                or not 0 <= seat.region < len(world.regions) or not 0 <= seat.lord < len(world.civilizations)
                or world.regions[seat.region].controller != world.civilizations[seat.lord].name):
            raise ValueError("academy host is not live under its recorded patron")
        if any(v is not None and not _nonnegative_int(v) for v in (item.demand, item.native_staff)):
            raise ValueError("invalid native demand or staff")
        if item.upkeep_paid is not None and type(item.upkeep_paid) is not bool:
            raise ValueError("invalid upkeep observation")
        if item.craft_price is not None and (not _nonnegative_number(item.craft_price) or item.craft_price <= 0):
            raise ValueError("craft price must be finite and positive")
        if item.crafts_committed is not None and not _nonnegative_number(item.crafts_committed):
            raise ValueError("invalid crafts commitments")
        stock = world.regions[seat.region].stockpile.goods.get("crafts", 0.0)
        if not _nonnegative_number(stock):
            raise ValueError("invalid crafts stock")

    # projected_treasury uses only world and acc; prior debits in the same batch
    # are visible even before the accumulator is flushed.
    from types import SimpleNamespace
    ctx = SimpleNamespace(world=world, acc=acc)
    receipts = []
    for item in sorted(inputs, key=lambda row: row.seat_id):
        seat = world.scholarship.seats[item.seat_id]
        region = world.regions[seat.region]
        civ = world.civilizations[seat.lord]
        stock = float(region.stockpile.goods.get("crafts", 0.0))
        available = None if item.crafts_committed is None else max(0.0, stock - item.crafts_committed)
        budget = max(0, projected_treasury(ctx, civ))
        capacity = None if item.native_staff is None else item.native_staff * LEARNERS_PER_SCHOLAR
        attempted = float(min(item.demand, capacity)) if item.demand is not None and capacity is not None else 0.0
        funded = None if item.upkeep_paid is None else item.upkeep_paid and budget > 0
        ready = item.upkeep_paid is True and item.craft_price is not None and available is not None
        delivered = min(attempted, available / CRAFTS_PER_LEARNER, budget / (item.craft_price * CRAFTS_PER_LEARNER)) if ready else 0.0
        used = delivered * CRAFTS_PER_LEARNER
        paid = min(budget, math.ceil(used * item.craft_price)) if used > 0 else 0
        if paid:
            region.stockpile.goods["crafts"] = stock - used
            add_stat(ctx, civ, "treasury", -paid, "keep")
        shortfalls = []
        if item.demand is None: shortfalls.append("demand_unknown")
        if item.native_staff is None: shortfalls.append("staff_unknown")
        elif item.demand is not None and capacity < item.demand: shortfalls.append("staff_capacity")
        if item.upkeep_paid is None: shortfalls.append("upkeep_unknown")
        elif not item.upkeep_paid: shortfalls.append("upkeep_unpaid")
        if item.craft_price is None: shortfalls.append("price_unknown")
        if available is None: shortfalls.append("commitments_unknown")
        elif attempted > available / CRAFTS_PER_LEARNER: shortfalls.append("crafts")
        if item.craft_price is not None and attempted * CRAFTS_PER_LEARNER * item.craft_price > budget: shortfalls.append("budget")
        receipts.append(AcademyServiceReceipt(seat_id=item.seat_id, region=seat.region, founder=seat.founder,
            founded_turn=seat.founded_turn, seat_name=seat.name, lord=seat.lord, source_turn=world.turn,
            available_turn=world.turn + 1, promised=item.demand, demand=item.demand, upkeep_paid=item.upkeep_paid,
            funded=funded, native_staff=item.native_staff, staff_capacity=capacity, craft_price=item.craft_price,
            crafts_stock=stock, crafts_committed=item.crafts_committed, crafts_available=available,
            budget_initial=budget, attempted=attempted, delivered=delivered, crafts_purchased=used, crafts_used=used,
            purchase_paid=paid, budget_remaining=budget - paid, shortfalls=shortfalls))
    state.receipts = receipts
    state.last_source_turn = world.turn
    return receipts


def academy_service_fraction(world, seat_id: int, *, turn: int) -> float:
    """Return the immediately previous completed service fraction, or zero if unknown.

    Off and non-academy seats retain their old effect. Identity, patron, liveness
    and exact availability are checked rather than carrying a stale receipt.
    """
    if not scholarship_on(world) or getattr(world.scholarship, "learning_services", None) is None:
        return 1.0
    if not _nonnegative_int(seat_id) or seat_id >= len(world.scholarship.seats) or not _nonnegative_int(turn) or turn != world.turn:
        return 0.0
    seat = world.scholarship.seats[seat_id]
    if seat.kind != ACADEMY:
        return 1.0
    if seat.fallen_turn is not None or seat.level <= 0 or not 0 <= seat.region < len(world.regions) or not 0 <= seat.lord < len(world.civilizations):
        return 0.0
    if world.regions[seat.region].controller != world.civilizations[seat.lord].name:
        return 0.0
    state = world.scholarship.learning_services
    if not isinstance(state, LearningServicesState) or state.last_source_turn != turn - 1:
        return 0.0
    rows = [r for r in state.receipts if r.seat_id == seat_id]
    if len(rows) != 1:
        return 0.0
    r = rows[0]
    if ((r.region, r.founder, r.founded_turn, r.seat_name, r.lord) != (seat.region, seat.founder, seat.founded_turn, seat.name, seat.lord)
            or r.source_turn != turn - 1 or r.available_turn != turn or r.promised is None or r.promised <= 0
            or not _nonnegative_number(r.delivered) or r.delivered > r.promised):
        return 0.0
    return r.delivered / r.promised
