"""RS3 veteran reintegration (``--veteran-reintegration``, default off).

Recovery-skills groundwork (RS0): the switch, its mode and inert stubs of the
livelihoods package protocol (:mod:`chronicler.livelihoods`) and of the
cross-lane API. Enabling it records the switch and nothing else: no capture
hook exists yet and nobody is prioritised. The RS3 lane fills in the
mechanism of the phase plan
(``docs/superpowers/roadmaps/recovery-skills-phase.md``, RS3).

Requires ``--agents hybrid`` and at least one of ``--workshops``,
``--apprenticeship`` and ``--repair-projects``. Modes (``--veteran-mode``):
``priority`` (default) and the control ``record_only``.

RS0 seams (stable signatures, inert bodies):

* :func:`priority_ids`: eligible veterans' stable ids in a region, in
  priority order; :mod:`chronicler.workshops` passes them to the native crew
  planner (``priority_ids``) while this switch is active, and RS1/RS2 put them
  first for apprenticeship seats and repair crews. RS0 stub: ``[]``.
* :func:`note_outcome`: other lanes report a veteran's dated outcome
  (``veteran_reintegration_state.OUTCOMES``). RS0 stub: validates the kind
  and records nothing.
"""
from __future__ import annotations

from chronicler.veteran_reintegration_state import MODES, OUTCOMES, VeteranReintegrationState


def _state(world) -> VeteranReintegrationState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "veteran_reintegration", None) if container is not None else None


def set_veteran_reintegration_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--veteran-mode``, default ``priority``) or disable; an
    omitted mode keeps the saved one."""
    mode = getattr(args, "veteran_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.veteran_reintegration = state = VeteranReintegrationState(mode=mode or MODES[0])
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)


def veteran_reintegration_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def snapshot_summary(world) -> dict:
    """The completed-turn observation (RS0: the switch only; never final state)."""
    state = _state(world)
    return {"schema_version": 1, "stage": "RS0", "enabled": state.enabled, "mode": state.mode,
            "counters": dict(state.counters)}


# ---------------------------------------------------------------------------
# RS0 cross-lane seams (inert until the RS3 lane)
# ---------------------------------------------------------------------------

def priority_ids(world, region: int) -> list[int]:
    """RS0 seam: stable ids of eligible veterans in ``region`` (an index in
    ``world.regions``), in priority order (``priority`` mode only). Callers
    put them first among candidates who are otherwise eligible; nothing is
    guaranteed. RS0 stub: ``[]``."""
    return []


def note_outcome(world, agent_id: int, kind: str, *, turn: int, detail: dict | None = None) -> None:
    """RS0 seam: record a veteran's dated outcome ``kind`` (one of
    ``OUTCOMES``, e.g. ``placed:apprentice``) at ``turn``; ``detail`` is a
    small JSON-safe dict (site, region). Ids that are not open veteran
    records are ignored. RS0 stub: validates ``kind`` and records nothing."""
    if kind not in OUTCOMES:
        raise ValueError(f"unknown veteran outcome {kind!r}")
    return None
