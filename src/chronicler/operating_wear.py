"""Workshop operating wear as a maintenance assumption (PL2, ``--operating-wear``, default off).

Requires ``--workshops`` in ``operate`` mode (``--agents hybrid``). Phase plan:
``docs/superpowers/roadmaps/productive-recovery-phase.md`` (PL2); integration page:
``docs/integration/operating-wear.md``.

Why a switch. The D2 diagnosis found that the extra repairs RS1 adds are its own
maintenance assumption, not training: with RS1 on, every funded *operating* L1
site loses ``OPERATING_WEAR`` of condition a turn, while the reference arm
``--workshops`` alone has none (L1 wears a site only while it is unfunded). This
switch lets the reference arm carry the same assumption, so training can be
compared with a reference that wears alike: ``--workshops --operating-wear`` is
the reference arm ``W_wear``.

Rule. At workshop settlement (``workshops._operating_wear``), a funded operating
site loses ``OPERATING_WEAR`` less the upkeep offset of its qualified crew. Only
RS1 (``--apprenticeship``) qualifies anyone, so without it the offset is 0 and the
site loses the whole wear; with it the offset is RS1's own
(``apprenticeship.upkeep_offset``, at most the wear). Condition stays in [0, 1];
below ``workshops.OPERATE_CONDITION`` a worn site stops until repaired (the L1
lump, or RS2 when that is on). Construction, unfunded and non-operating turns
are not worn by this switch (unfunded built sites keep L1's own wear).

``--apprenticeship`` implies the wear (it applies it itself, as before this
switch existed), so every RS1 command keeps its wear exactly; adding
``--operating-wear`` to an RS1 run changes nothing but adds this package's
records. Nothing here draws RNG, moves money or touches a person.

Records (``snapshot.livelihoods.operating_wear``, dated by ``source_turn``): per
funded operating site and turn its wear, offset, net wear, condition before and
after, the qualified crew members and whether the wear was fully offset; lifetime
counters including the operating site-turns covered by a qualified member and the
L1 lump repairs paid. ``receipts`` is None when no Phase 2 completed in the source
turn (unknown, not zero). The constant is a declared modeling choice, not
calibrated: ``OPERATING_WEAR`` is RS1's value moved here unchanged.
"""
from __future__ import annotations

from chronicler.operating_wear_state import COUNTERS, OperatingWearState, WearReceipt
from chronicler.switch_state import sub_state_getter

#: Condition a funded operating site loses per turn (declared, uncalibrated;
#: moved unchanged from ``apprenticeship.py``). With nobody qualified a site
#: falls from 1.0 to the 0.5 operating floor in 25 operating turns.
OPERATING_WEAR = 0.02


_state = sub_state_getter("operating_wear")


def _bump(state: OperatingWearState, key: str, amount: float = 1) -> None:
    state.bump(key, amount)


def set_operating_wear_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    state = _state(world)
    if state is None:
        world.livelihoods.operating_wear = state = OperatingWearState()
    if not value and state._pending is not None:
        raise RuntimeError("cannot disable operating wear while a turn is pending")
    state.enabled = bool(value)


def operating_wear_active(world) -> bool:
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    from chronicler.workshops import workshops_active
    return workshops_active(world) and world.livelihoods.workshops.mode == "operate"


def operating_wear(world, site) -> float:
    """Workshops seam: this turn's net wear of the funded operating ``site``,
    ``OPERATING_WEAR`` less the qualified crew's upkeep offset (RS1 when active,
    else 0), recorded for this turn's receipts."""
    from chronicler.workshops import _lane_active
    state = _state(world)
    gross = OPERATING_WEAR
    offset = 0.0
    qualified: list[int] = []
    if _lane_active(world, "apprenticeship"):
        from chronicler.apprenticeship import operating_wear as rs1_wear, upkeep_offset
        net = float(rs1_wear(world, site))
        offset, qualified = upkeep_offset(world, site)
        if net != max(0.0, gross - offset):
            raise RuntimeError("operating wear and the RS1 upkeep offset disagree")
    else:
        net = gross
    pending = state._pending
    if pending is None or pending[0] != world.turn:
        pending = state._pending = (world.turn, {})
    if site.site in pending[1]:
        raise RuntimeError("operating wear applied twice to one site in a turn")
    condition = float(site.condition)
    pending[1][site.site] = WearReceipt(
        turn=world.turn, site=site.site, region=site.region, wear=gross, upkeep_offset=offset, net_wear=net,
        condition_before=condition, condition_after=max(0.0, condition - net), qualified_on_crew=list(qualified),
        full_offset=net == 0.0)
    return net


def finish_phase2(world, economy_result, agent_bridge, acc):
    """After workshop settlement: commit this turn's wear receipts (sites in
    workshop order) and count the turn's L1 lump repairs."""
    state = _state(world)
    ws = world.livelihoods.workshops
    if ws.frame_turn != world.turn:
        raise RuntimeError("workshop receipts missing for this turn")
    pending = state._pending
    state._pending = None
    rows = pending[1] if pending is not None and pending[0] == world.turn else {}
    frame = []
    for receipt in ws.frame:
        row = rows.pop(receipt.site, None)
        if receipt.paid and "repair" in receipt.paid:
            _bump(state, "repairs")
        if row is None:
            continue
        frame.append(row)
        _bump(state, "operating_site_turns")
        _bump(state, "wear", row.wear)
        _bump(state, "upkeep_offset", row.upkeep_offset)
        _bump(state, "net_wear", row.net_wear)
        if row.full_offset:
            _bump(state, "full_offset_site_turns")
        if row.qualified_on_crew:
            _bump(state, "covered_site_turns")
    if rows:
        raise RuntimeError("operating wear recorded for a site without a workshop receipt")
    _bump(state, "turns")
    state.frame = frame
    state.frame_turn = world.turn
    return []


def rollback_phase2(world) -> None:
    state = _state(world)
    if state is not None:
        state._pending = None


def snapshot_summary(world) -> dict:
    """The completed-turn observation; dated by ``source_turn``, never final state."""
    from chronicler.workshops import _lane_active
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source
    return {
        "schema_version": 1, "stage": "PL2", "source_turn": source,
        # None: no completed Phase 2 in the source turn (unknown, not zero).
        "receipts": [r.model_dump() for r in state.frame] if fresh else None,
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "parameters": {"operating_wear": OPERATING_WEAR},
        # RS1 applies the same wear itself; this switch then only records it.
        "with_apprenticeship": _lane_active(world, "apprenticeship"),
    }
