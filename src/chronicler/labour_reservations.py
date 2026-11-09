"""One labour reservation: who already holds work this turn (read-only).

Connected-world shared contract (lead decision for C2, to be reused by D3):
nobody is booked twice in one turn across rural health care's prepared
patient and caregiver rows, the shared native work registry (L1 workshop
crews, L5 learners, RS1 apprentices, RS2/PL3 repair crews, PL1 woodcutters
and C2 carers, each reserved under a native category; carers carry their
own label ``registry_care``), people away on a
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

from chronicler.switch_state import lane_active

#: Native work registry categories, in declaration order (``workshop_work.rs``
#: ``RESERVATION_CATEGORIES``, append only; A4 appended ``trade`` for its
#: carriers). A category index beyond this tuple, from a later native build, is
#: named ``registry_other`` (still booked: :func:`booked` uses the person, not
#: the label).
REGISTRY_CATEGORIES: tuple[str, ...] = ("workshop", "learning", "apprentice", "repair", "trade")
#: Reasons, in the order :func:`booked` assigns them (a person's first reason wins).
#: ``registry_care``: C2's carers of this turn (a Python label: they hold the
#: native registry's ``repair`` category; the registry has no care category).
REASONS: tuple[str, ...] = (
    "health_patient", "health_caregiver", "registry_care",
    *(f"registry_{name}" for name in REGISTRY_CATEGORIES), "registry_other",
    "trip", "enlisted", "mentor",
)


_lane_active = lane_active


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


def carers(world, turn: int) -> set[int]:
    """C2's carers named for ``turn`` (its in-flight plan; empty otherwise). Reads only."""
    care = getattr(getattr(world, "livelihoods", None), "epidemic_care", None)
    t = getattr(care, "_turn", None) if care is not None else None
    if t is None or getattr(t, "turn", None) != turn:
        return set()
    return {int(x.agent_id) for r in t.receipts for x in r.carers}


def booked(world, sim, turn: int) -> dict[int, str]:
    """Stable id -> the first reason the person may not take new work in ``turn``."""
    out: dict[int, str] = {}

    def put(ids, reason: str) -> None:
        for aid in sorted(ids):
            out.setdefault(int(aid), reason)

    patients, givers = health_rows(world)
    put(patients, "health_patient")
    put(givers, "health_caregiver")
    put(carers(world, turn), "registry_care")
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
