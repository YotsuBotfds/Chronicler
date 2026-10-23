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
# fields/signals. Geography 2.0 appends steppe/jungle/marsh (append only, never
# reorder: the discriminants index Rust terrain tables).
TERRAIN_MAP: dict[str, int] = {
    "plains": 0,
    "mountains": 1,
    "coast": 2,
    "forest": 3,
    "desert": 4,
    "tundra": 5,
    "river": 0,
    "hills": 0,
    "steppe": 6,
    "jungle": 7,
    "marsh": 8,
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

# Region ids cross the bridge as uint16.
MAX_NATIVE_REGIONS = 0xFFFF
# Civ ids cross the bridge as uint8 with 255 reserved for "none", and civ
# records are never removed (secessions and restorations append). Worlds are
# capped at 254 records, ids 0..253, leaving the top of the range unused.
MAX_CIV_RECORDS = 254


def check_civ_capacity(world) -> None:
    """Fail clearly when a world has more civ records than uint8 ids allow."""
    count = len(world.civilizations)
    if count > MAX_CIV_RECORDS:
        raise ValueError(
            f"World has {count} civilization records but the native runtimes "
            f"support at most {MAX_CIV_RECORDS} (civ ids are uint8, 255 = none, "
            "and civ records are never removed)"
        )


def river_ids_from_mask(mask: int) -> list[int]:
    """Ascending river ids encoded in a Python ``Region.river_mask`` int."""
    ids: list[int] = []
    bit = 0
    while mask:
        if mask & 1:
            ids.append(bit)
        mask >>= 1
        bit += 1
    return ids


__all__ = (
    "TERRAIN_MAP", "VALUE_TO_ID", "VALUE_EMPTY", "MAX_CIV_RECORDS",
    "MAX_NATIVE_REGIONS", "check_civ_capacity", "river_ids_from_mask",
)
