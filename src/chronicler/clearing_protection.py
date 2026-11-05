"""RS5 funded protection of forest cover from clearing (``--clearing-protection``, default off).

Recovery-skills groundwork (RS0): the switch, its mode and inert stubs of the
livelihoods package protocol (:mod:`chronicler.livelihoods`). Enabling it
records the switch and nothing else: no region is protected and nothing is
paid. The RS5 lane fills in the mechanism of the phase plan
(``docs/superpowers/roadmaps/recovery-skills-phase.md``, RS5).

No prerequisite (it works in every ecology path). Modes
(``--clearing-protection-mode``): ``enforced`` (default) and the
cost-retaining control ``cost_only``.
"""
from __future__ import annotations

from chronicler.clearing_protection_state import MODES, ClearingProtectionState


def _state(world) -> ClearingProtectionState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "clearing_protection", None) if container is not None else None


def set_clearing_protection_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--clearing-protection-mode``, default ``enforced``) or disable; an
    omitted mode keeps the saved one."""
    mode = getattr(args, "clearing_protection_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.clearing_protection = state = ClearingProtectionState(mode=mode or MODES[0])
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)


def clearing_protection_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled


def snapshot_summary(world) -> dict:
    """The completed-turn observation (RS0: the switch only; never final state)."""
    state = _state(world)
    return {"schema_version": 1, "stage": "RS0", "enabled": state.enabled, "mode": state.mode,
            "counters": dict(state.counters)}
