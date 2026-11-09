"""Opt-in, explicit paid restoration of a fallen academy at a paused boundary.

This deliberate choice bypasses the spontaneous founding lottery. The existing
fee pays for founding; it does not model construction labor or materials.
The coordinator must attest a completed-turn boundary with no live accumulator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from chronicler.models import Event, WorldState


@dataclass(frozen=True)
class AcademyRestorationRequest:
    region_id: int
    fallen_seat_id: int
    fallen_founder: int
    fallen_founded_turn: int
    fallen_turn: int
    current_lord: int


@dataclass(frozen=True)
class AcademyRestorationReceipt:
    source_turn: int
    request: AcademyRestorationRequest
    fee: int
    treasury_before: int
    treasury_after: int
    new_seat_id: int | None
    changed: bool
    event: Event | None = None


def _boundary(world, at_turn_boundary, accumulator):
    from chronicler.cities import cities_enabled
    from chronicler.lab_transport import _require_physical_hybrid
    from chronicler.learning_services import learning_services_active
    if at_turn_boundary is not True or accumulator is not None:
        raise ValueError("restoration requires an attested completed-turn boundary without an accumulator")
    _require_physical_hybrid(world)
    if not cities_enabled(world) or not learning_services_active(world):
        raise ValueError("restoration requires enabled cities, scholarship and academy services")
    services = world.scholarship.learning_services
    storage = getattr(getattr(world, "grain_reserves", None), "storage", None)
    if (getattr(services, "_active_plan", None) is not None
            or (storage is not None and getattr(storage, "_active_plan", None) is not None)
            or world._agent_bridge._sim.has_pending_teaching_work()):
        raise ValueError("restoration cannot run with pending work")
    if world.turn <= 0 or world.scholarship.last_tick_turn != world.turn - 1:
        raise ValueError("restoration requires a completed scholarship turn")


def preview_academy_restorations(world: WorldState, requests: Iterable[AcademyRestorationRequest],
                                 *, at_turn_boundary: bool, accumulator=None) -> tuple[AcademyRestorationReceipt, ...]:
    from chronicler import scholarship as s
    from chronicler.scholarship_state import ACADEMY
    from chronicler.war.common import projected_treasury
    _boundary(world, at_turn_boundary, accumulator)
    context = s._Tick(world, None, None, (), None)
    result = []
    regions, lords = set(), set()
    for req in tuple(requests):
        if not isinstance(req, AcademyRestorationRequest) or any(type(x) is not int for x in (
                req.region_id, req.fallen_seat_id, req.fallen_founder, req.fallen_founded_turn,
                req.fallen_turn, req.current_lord)):
            raise ValueError("invalid restoration request")
        if not 0 <= req.region_id < len(world.regions) or not 0 <= req.fallen_seat_id < len(world.scholarship.seats) or not 0 <= req.current_lord < len(world.civilizations):
            raise ValueError("invalid region, seat or lord index")
        if req.region_id in regions or req.current_lord in lords:
            raise ValueError("duplicate region or patron in restoration batch")
        regions.add(req.region_id)
        lords.add(req.current_lord)
        old = world.scholarship.seats[req.fallen_seat_id]
        if (old.region, old.kind, old.founder, old.founded_turn, old.fallen_turn) != (
                req.region_id, ACADEMY, req.fallen_founder, req.fallen_founded_turn, req.fallen_turn):
            raise ValueError("stale fallen academy identity")
        if context.falls.get(req.region_id) is not old:
            raise ValueError("fallen academy is not the latest fallen seat")
        region, lord = world.regions[req.region_id], world.civilizations[req.current_lord]
        if region.controller != lord.name or region.name not in lord.regions or lord.capital_region != region.name:
            raise ValueError("patron must control the capital region")
        # Marker is in the new seat's saved name, source turn and unique region;
        # it identifies a repeated request on this same paused boundary.
        name = f"the Lab-restored Academy of {region.name}"
        matches = [(i, seat) for i, seat in s.living_seats(world)
                   if seat.region == req.region_id and seat.kind == ACADEMY and seat.name == name
                   and seat.founded_turn == world.turn and seat.founder == req.current_lord]
        if matches:
            result.append(AcademyRestorationReceipt(world.turn, req, 0, lord.treasury,
                                                     lord.treasury, matches[0][0], False))
            continue
        if (req.region_id in s._seat_regions(world)
                or any(seat.kind == ACADEMY and seat.lord == req.current_lord for _, seat in s.living_seats(world))):
            raise ValueError("patron or region already has a live academy or seat")
        if not s._founding_ready(context, req.region_id):
            raise ValueError("academy site is not ready for founding")
        if (lord.culture < s.ACADEMY_CULTURE or lord.stability < s.ACADEMY_STABILITY
                or projected_treasury(context, lord) < s.ACADEMY_TREASURY
                or any(lord.name in pair for pair in world.active_wars)):
            raise ValueError("academy patron is not eligible or funded")
        result.append(AcademyRestorationReceipt(world.turn, req, s.ACADEMY_FEE,
                                                 lord.treasury, lord.treasury - s.ACADEMY_FEE,
                                                 None, True))
    return tuple(result)


def apply_academy_restorations(world: WorldState, requests: Iterable[AcademyRestorationRequest],
                               *, at_turn_boundary: bool, accumulator=None) -> tuple[AcademyRestorationReceipt, ...]:
    from dataclasses import replace
    from chronicler import faiths, scholarship as s
    from chronicler.scholarship_state import ACADEMY
    from chronicler.war.common import add_stat
    planned = preview_academy_restorations(world, requests, at_turn_boundary=at_turn_boundary, accumulator=accumulator)
    context = s._Tick(world, None, None, (), None)
    result = []
    for receipt in planned:
        if not receipt.changed:
            result.append(receipt)
            continue
        req = receipt.request
        region, lord = world.regions[req.region_id], world.civilizations[req.current_lord]
        add_stat(context, lord, "treasury", -receipt.fee, "keep")
        s._bump(context.state, "fees", receipt.fee)
        seat = s._new_seat(context, req.region_id, ACADEMY,
                           f"the Lab-restored Academy of {region.name}", req.current_lord,
                           faiths.uid_or_slot(world, lord.civ_majority_faith))
        seat_id = len(context.state.seats) - 1
        s._record_founding(context, seat, [lord.name],
                           f"[Lab] {lord.name} restores {seat.name} at {region.name}", 5)
        event = context.events[-1]
        world.events_timeline.append(event)
        result.append(replace(receipt, new_seat_id=seat_id, event=event))
    return tuple(result)
