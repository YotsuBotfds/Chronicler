"""RS2 maintenance, reconstruction and repair projects (``--repair-projects``, default off).

Recovery-skills groundwork (RS0): the switch, its mode and inert stubs of the
livelihoods package protocol (:mod:`chronicler.livelihoods`) and of the
cross-lane API. Enabling it records the switch and nothing else: no phase
hook exists yet, no person, money, timber or asset changes. The RS2 lane
fills in the mechanism of the phase plan
(``docs/superpowers/roadmaps/recovery-skills-phase.md``, RS2).

Requires ``--agents hybrid`` and ``--workshops`` in ``operate`` mode or
``--grain-storage``. Modes (``--repair-mode``): ``repair`` (default) and the
cost-retaining control ``cost_only``.

RS0 seam (stable signature, inert body):

* :func:`legacy_workshop_repair_allowed`: whether the L1 lump repair
  (``workshops.REPAIR_COST``) may still be billed; :mod:`chronicler.workshops`
  reads it in ``_bill``. RS0 stub: always True.
"""
from __future__ import annotations

from chronicler.repair_projects_state import MODES, RepairProjectsState


def _state(world) -> RepairProjectsState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "repair_projects", None) if container is not None else None


def set_repair_projects_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--repair-mode``, default ``repair``) or disable; an
    omitted mode keeps the saved one."""
    mode = getattr(args, "repair_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.repair_projects = state = RepairProjectsState(mode=mode or MODES[0])
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)


def _grain_storage_on(world) -> bool:
    from chronicler.grain_reserves_state import grain_reserves_on
    return grain_reserves_on(world) and getattr(world.grain_reserves, "storage", None) is not None


def repair_projects_active(world) -> bool:
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    from chronicler.workshops import workshops_active
    # Workshops in any mode (observe builds no asset, so its side is inert) or storage.
    return workshops_active(world) or _grain_storage_on(world)


def snapshot_summary(world) -> dict:
    """The completed-turn observation (RS0: the switch only; never final state)."""
    state = _state(world)
    return {"schema_version": 1, "stage": "RS0", "enabled": state.enabled, "mode": state.mode,
            "counters": dict(state.counters)}


# ---------------------------------------------------------------------------
# RS0 cross-lane seam (inert until the RS2 lane)
# ---------------------------------------------------------------------------

def legacy_workshop_repair_allowed(world) -> bool:
    """RS0 seam: True while the L1 lump repair may be billed. With RS2 on,
    repair projects own workshop repair and the lump must be disabled so a
    site is never repaired twice. RS0 stub: always True."""
    # TODO(RS2): return not repair_projects_active(world) once projects repair workshops.
    return True
