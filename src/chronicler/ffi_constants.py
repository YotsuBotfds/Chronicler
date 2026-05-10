"""Shared constants for Python/Rust FFI batch contracts.

Keep these values synchronized with the Rust-side discriminants used by
``chronicler_agents``.  They live in a lightweight module so pure-Python
callers such as ``chronicler.culture`` do not need to import the native Rust
extension through ``chronicler.agent_bridge`` just to encode static IDs.
"""

from __future__ import annotations

# Terrain discriminants mirror chronicler-agents/src/region.rs::Terrain.
# "river" and "hills" are legacy Python terrain labels that intentionally map
# to plains for Rust terrain modifiers; river/hill effects are carried by other
# fields/signals.
TERRAIN_MAP: dict[str, int] = {
    "plains": 0,
    "mountains": 1,
    "coast": 2,
    "forest": 3,
    "desert": 4,
    "tundra": 5,
    "river": 0,
    "hills": 0,
}

# M36 cultural value string -> u8 slot mapping.  The numeric order matches the
# Rust agent cultural-value slots documented as Freedom=0..Cunning=5.
VALUE_TO_ID: dict[str, int] = {
    "Freedom": 0,
    "Order": 1,
    "Tradition": 2,
    "Knowledge": 3,
    "Honor": 4,
    "Cunning": 5,
}

# Sentinel for an absent/unknown cultural value.  Mirrors Rust
# CULTURAL_VALUE_EMPTY = 0xFF.
VALUE_EMPTY: int = 0xFF

__all__ = ("TERRAIN_MAP", "VALUE_TO_ID", "VALUE_EMPTY")
