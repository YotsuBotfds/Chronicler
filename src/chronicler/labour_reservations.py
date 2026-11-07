"""One labour reservation: who already holds work this turn (read-only).

Connected-world shared contract (lead decision for C2, to be reused by D3):
nobody is booked twice in one turn across rural health care's prepared
patient and caregiver rows, the shared native work registry (L1 workshop
crews, L5 learners, RS1 apprentices, RS2/PL3 repair crews, PL1 woodcutters
and C2 carers, each reserved under a native category), people away on a
merchant trip, the enlisted, and the mentors RS1 seated for this turn.

:func:`booked` reads those holders and returns each person's first reason in
a fixed order; it changes nothing (no reservation, no native call that
writes). The native registry itself also refuses to reserve anyone who holds
registry work, rural health work or a teaching plan that turn
(``workshop_work::reserve``), so a package that reserves through it cannot
double-book even if it skipped this query.

It answers the same question as ``recovery_crews._excluded`` (which PL3 keeps
for its own crews, unchanged, so its outputs are untouched); a test checks
the two agree on the people they exclude.
"""
from __future__ import annotations

from importlib import import_module

#: Native work registry categories (``workshop_work.rs``; the registry refuses
#: any other), in declaration order.
REGISTRY_CATEGORIES: tuple[str, ...] = ("workshop", "learning", "apprentice", "repair")
#: Reasons, in the order :func:`booked` assigns them (a person's first reason wins).
REASONS: tuple[str, ...] = (
    "health_patient", "health_caregiver",
    *(f"registry_{name}" for name in REGISTRY_CATEGORIES), "registry_other",
    "trip", "enlisted", "mentor",
)


def _lane_active(world, name: str) -> bool:
    if getattr(getattr(world, "livelihoods", None), name, None) is None:
        return False
    return bool(getattr(import_module("chronicler." + name), f"{name}_active")(world))


def health_rows(world) -> tuple[set[int], set[int]]:
    """(patients, caregivers) of this turn's prepared rural health work (empty
    without health care or before it is prepared). Reads only."""
    health = getattr(world, "health_care", None)
    rows = getattr(health, "_prepared", None) if health is not None else None
    patients: set[int] = set()
    givers: set[int] = set()
    for aid, _region, giver, care in rows or ():
        patients.add(int(aid))
        if int(giver) and float(care) > 0:
            givers.add(int(giver))
    return patients, givers


def booked(world, sim, turn: int) -> dict[int, str]:
    """Stable id -> the first reason the person may not take new work in ``turn``."""
    out: dict[int, str] = {}

    def put(ids, reason: str) -> None:
        for aid in sorted(ids):
            out.setdefault(int(aid), reason)

    patients, givers = health_rows(world)
    put(patients, "health_patient")
    put(givers, "health_caregiver")
    reservations = getattr(sim, "work_reservations", None)
    if callable(reservations):
        for aid, category, _fraction in sorted(reservations(turn)):
            c = int(category)
            put((aid,), f"registry_{REGISTRY_CATEGORIES[c]}" if 0 <= c < len(REGISTRY_CATEGORIES)
                else "registry_other")
    trips = getattr(sim, "trip_agent_ids", None)
    if callable(trips):
        put(trips(), "trip")
    from chronicler.workshops import _enlisted
    put(_enlisted(world), "enlisted")
    if _lane_active(world, "apprenticeship"):
        from chronicler.apprenticeship import seated_mentors
        put(seated_mentors(world), "mentor")
    return out
