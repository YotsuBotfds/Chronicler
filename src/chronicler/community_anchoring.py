"""Community anchoring (``--community-anchoring``, default off).

M53 oracle 4 expects community members to migrate 15-30% less than
matched non-members (social anchoring). With the switch on, the native
agent decision (``chronicler-agents/src/community.rs``) holds an agent with
a reason to move back by its community ties: positive bonds other than
marriage, of sentiment at least 20, to living agents of its own region with
whom it shares a memory (oracle 1's key), at least one of them non-kin.
The anchor grows with the ties up to four (with the agent, a community of
five) and lowers the odds of moving; it never removes the reason to move
and never touches rebellion, occupation switches or staying. See
``docs/integration/community-anchoring.md``.

The switch is stored on the world (``WorldState.community_anchoring``:
``True`` when on, ``None`` when off and then omitted from every output),
so a resumed run keeps it. With it off nothing here runs, the bridge sends
no native call it did not send before, and every output is identical to
the simulation without it. ``agents.community_full_anchor`` in the tuning
overrides sets the anchor of an agent with four ties (utility units; the
native default ``COMMUNITY_ANCHOR``, 0.120143, otherwise).
"""
from __future__ import annotations

from typing import Any

#: Default for worlds created by the CLI/batch/live entry points
#: (``--community-anchoring`` opts in; loaded worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = False

#: Tuning override: the full anchor (utility units).
FULL_ANCHOR_TUNING_KEY = "agents.community_full_anchor"


def community_anchoring_enabled(world: Any) -> bool:
    """True only when the world stores the switch on (mocks and None read as off)."""
    return getattr(world, "community_anchoring", None) is True


def set_community_anchoring_enabled(world: Any, enabled: bool) -> None:
    """Switch community anchoring on (``True``) or off (``None``: dormant, omitted)."""
    world.community_anchoring = True if enabled else None


def full_anchor_override(world: Any) -> float | None:
    """The tuning override of the full anchor, or None for the native default."""
    overrides = getattr(world, "tuning_overrides", None) or {}
    if FULL_ANCHOR_TUNING_KEY not in overrides:
        return None
    value = float(overrides[FULL_ANCHOR_TUNING_KEY])
    if not value >= 0.0 or value == float("inf"):
        raise ValueError(f"{FULL_ANCHOR_TUNING_KEY} must be finite and not negative, got {value!r}")
    return value


def apply_community_anchoring(simulator: Any, world: Any) -> None:
    """Send the switch to a native ``AgentSimulator`` when the world has it on;
    nothing otherwise (a run without it makes no new native call)."""
    if not community_anchoring_enabled(world):
        return
    if not hasattr(simulator, "set_community_anchoring"):
        raise RuntimeError(
            "the installed chronicler_agents extension predates community anchoring; "
            "rebuild it to use --community-anchoring"
        )
    full_anchor = full_anchor_override(world)
    if full_anchor is None:
        simulator.set_community_anchoring(True)
    else:
        simulator.set_community_anchoring(True, full_anchor)
