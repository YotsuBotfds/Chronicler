"""Closed pause command for the existing explicit academy restoration."""
from chronicler.lab_academy import (
    AcademyRestorationRequest, preview_academy_restorations, apply_academy_restorations,
)

CONTROL = "academy_restoration"
TARGET = "@academy"
STAT = "lab.academy_restore"


def validate_command(target: str, stat: str, value: int) -> None:
    if target != TARGET or stat != STAT or type(value) is not int or value < 0:
        raise ValueError("Invalid academy restoration command")


def request_for_seat(world, target: str, stat: str, value: int):
    validate_command(target, stat, value)
    state = getattr(world, "scholarship", None)
    if state is None or value >= len(state.seats):
        raise ValueError("Unknown fallen academy seat")
    seat = state.seats[value]
    if type(seat.region) is not int or not 0 <= seat.region < len(world.regions):
        raise ValueError("Invalid fallen academy region")
    controller = world.regions[seat.region].controller
    patrons = [i for i, civ in enumerate(world.civilizations) if civ.name == controller]
    if len(patrons) != 1 or type(seat.fallen_turn) is not int:
        raise ValueError("Fallen academy must have a current patron and recorded fall")
    return AcademyRestorationRequest(seat.region, value, seat.founder, seat.founded_turn,
                                     seat.fallen_turn, patrons[0])


def preview(world, target: str, stat: str, value: int):
    request = request_for_seat(world, target, stat, value)
    return preview_academy_restorations(world, (request,), at_turn_boundary=True)[0]


def apply(world, target: str, stat: str, value: int):
    request = request_for_seat(world, target, stat, value)
    # The core records its founding event once, including its causal fall link.
    return apply_academy_restorations(world, (request,), at_turn_boundary=True)[0]


def paused_context(world, *, limit: int = 64) -> dict:
    """Read-only, bounded current-turn restoration choices for a live pause."""
    from chronicler.lab_academy import _boundary
    from chronicler.scholarship_state import ACADEMY
    result = {"schema_version": 1, "turn": world.turn, "supported": False,
              "unavailable_reason": None, "candidates": [], "total_candidates": 0, "omitted": 0}
    try:
        _boundary(world, True, None)
    except (ValueError, ImportError, AttributeError) as exc:
        result["unavailable_reason"] = str(exc)[:500]
        return result
    result["supported"] = True
    latest = {}
    for seat_id, seat in enumerate(world.scholarship.seats):
        if (seat.kind != ACADEMY or type(seat.region) is not int or
                not 0 <= seat.region < len(world.regions) or type(seat.fallen_turn) is not int or
                seat.fallen_turn >= world.turn):
            continue
        old = latest.get(seat.region)
        if old is None or seat.fallen_turn >= old[1].fallen_turn:
            latest[seat.region] = (seat_id, seat)
    result["total_candidates"] = len(latest)
    result["omitted"] = max(0, len(latest) - limit)
    for region_id in sorted(latest)[:limit]:
        seat_id, seat = latest[region_id]
        region = world.regions[region_id]
        patrons = [i for i, civ in enumerate(world.civilizations) if civ.name == region.controller]
        lord_id = patrons[0] if len(patrons) == 1 else None
        row = {"region_id": region_id, "region_name": region.name[:200],
               "fallen_seat_id": seat_id, "fallen_seat_name": seat.name[:200],
               "fallen_founder": seat.founder, "fallen_founded_turn": seat.founded_turn,
               "fallen_turn": seat.fallen_turn, "current_lord": lord_id,
               "current_lord_name": world.civilizations[lord_id].name[:200] if lord_id is not None else None,
               "eligible": False, "reason": None, "fee": None,
               "treasury_before": None, "treasury_after": None}
        try:
            receipt = preview(world, TARGET, STAT, seat_id)
            if not receipt.changed:
                raise ValueError("Academy is already restored at this boundary")
            row.update(eligible=True, fee=receipt.fee, treasury_before=receipt.treasury_before,
                       treasury_after=receipt.treasury_after)
        except ValueError as exc:
            row["reason"] = str(exc)[:500] or "Academy restoration unavailable"
        result["candidates"].append(row)
    return result
