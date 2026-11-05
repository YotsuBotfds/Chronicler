"""RS4 migration, knowledge and household support (``--remittances``, default off).

Recovery-skills groundwork (RS0): the switch, its mode and inert stubs of the
livelihoods package protocol (:mod:`chronicler.livelihoods`). Enabling it
records the switch and nothing else: no ledger is kept and nothing is sent.
The RS4 lane fills in the mechanism of the phase plan
(``docs/superpowers/roadmaps/recovery-skills-phase.md``, RS4), with its own
native pairwise operation under the transfer purpose ``remittance``
(``wealth_transfer::PURPOSE_REMITTANCE``, code 4).

Requires ``--agents hybrid``. Modes (``--remittance-mode``): ``send``
(default) and the control ``record_only``.
"""
from __future__ import annotations

from chronicler.remittances_state import MODES, RemittancesState


def _state(world) -> RemittancesState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "remittances", None) if container is not None else None


def set_remittances_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--remittance-mode``, default ``send``) or disable; an
    omitted mode keeps the saved one."""
    mode = getattr(args, "remittance_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.remittances = state = RemittancesState(mode=mode or MODES[0])
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)


def remittances_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def snapshot_summary(world) -> dict:
    """The completed-turn observation (RS0: the switch only; never final state)."""
    state = _state(world)
    return {"schema_version": 1, "stage": "RS0", "enabled": state.enabled, "mode": state.mode,
            "counters": dict(state.counters)}
