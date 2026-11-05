"""Sprint lane module for ``--workshops`` (default off; see chronicler.livelihoods).

Interface stub from the L0 wiring landing: enabling records a dormant state
and produces no behavior until the lane lands its mechanism.
"""
from __future__ import annotations

from chronicler.workshops_state import WorkshopState


def _state(world):
    container = getattr(world, "livelihoods", None)
    return getattr(container, "workshops", None) if container is not None else None


def set_workshops_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    state = _state(world)
    if state is None:
        world.livelihoods.workshops = state = WorkshopState()
    state.enabled = bool(value)


def workshops_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled


def snapshot_summary(world) -> dict:
    return {"schema_version": 1, "source_turn": world.turn - 1, "status": "interface_stub"}
