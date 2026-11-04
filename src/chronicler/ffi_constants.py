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

# Relationship bond types: the discriminants of
# chronicler-agents/src/relationships.rs::BondType, as the relationship
# sidecar (``validation_relationships.arrow``, column ``bond_type``) and the
# relationship FFI carry them. tests/test_bond_types.py checks this mirror
# against the Rust source and, with the extension installed, the native
# behaviour of the kin, marriage and mentor codes.
BOND_TYPES: dict[str, int] = {
    "mentor": 0,
    "rival": 1,
    "marriage": 2,
    "exile_bond": 3,
    "co_religionist": 4,
    "kin": 5,
    "friend": 6,
    "grudge": 7,
}
BOND_MENTOR = BOND_TYPES["mentor"]
BOND_RIVAL = BOND_TYPES["rival"]
BOND_MARRIAGE = BOND_TYPES["marriage"]
BOND_EXILE = BOND_TYPES["exile_bond"]
BOND_CO_RELIGIONIST = BOND_TYPES["co_religionist"]
BOND_KIN = BOND_TYPES["kin"]
BOND_FRIEND = BOND_TYPES["friend"]
BOND_GRUDGE = BOND_TYPES["grudge"]
# relationships.rs::is_positive_valence (rival and grudge are negative).
POSITIVE_VALENCE_BONDS = frozenset({
    BOND_MENTOR, BOND_MARRIAGE, BOND_EXILE, BOND_CO_RELIGIONIST, BOND_KIN, BOND_FRIEND,
})

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


CIV_CAPACITY_REFUSAL = (
    "civilization lifetime capacity 254 reached; no new identity allocated"
)


def has_civ_capacity(world, pending: int = 0) -> bool:
    """Whether one further identity fits, counting dead records and queued births."""
    check_civ_capacity(world)
    if type(pending) is not int or pending < 0:
        raise ValueError("pending civilization reservations must be a nonnegative integer")
    return len(world.civilizations) + pending < MAX_CIV_RECORDS


def require_new_civ_capacity(world) -> None:
    """Reject a direct creator before callbacks or mutations, without recycling ids."""
    if not has_civ_capacity(world):
        raise ValueError(CIV_CAPACITY_REFUSAL)


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
    "BOND_TYPES", "BOND_MENTOR", "BOND_RIVAL", "BOND_MARRIAGE", "BOND_EXILE",
    "BOND_CO_RELIGIONIST", "BOND_KIN", "BOND_FRIEND", "BOND_GRUDGE", "POSITIVE_VALENCE_BONDS",
)
