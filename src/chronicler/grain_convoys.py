"""Sprint lane module for ``--grain-convoys`` (default off; see chronicler.livelihoods).

Interface stub from the L0 wiring landing: enabling records a dormant state
and produces no behavior until the lane lands its mechanism.
"""
from __future__ import annotations

from chronicler.grain_convoys_state import GrainConvoyState


def _state(world):
    container = getattr(world, "livelihoods", None)
    return getattr(container, "grain_convoys", None) if container is not None else None


def set_grain_convoys_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    state = _state(world)
    if state is None:
        world.livelihoods.grain_convoys = state = GrainConvoyState()
    state.enabled = bool(value)


def grain_convoys_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled


def snapshot_summary(world) -> dict:
    return {"schema_version": 1, "source_turn": world.turn - 1, "status": "interface_stub"}
