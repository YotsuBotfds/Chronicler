"""Named event generation — battles, treaties, cultural works, tech breakthroughs."""

from __future__ import annotations

import random
from collections.abc import Collection

from chronicler.history_index import history_index
from chronicler.models import Civilization, TechEra, WorldState
from chronicler.utils import stable_hash_int

TECH_BREAKTHROUGH_NAMES: dict[TechEra, str] = {
    TechEra.BRONZE: "The Forging of Bronze",
    TechEra.IRON: "The Mastery of Iron",
    TechEra.CLASSICAL: "The Codification of Law",
    TechEra.MEDIEVAL: "The Age of Fortification",
    TechEra.RENAISSANCE: "The Great Enlightenment",
    TechEra.INDUSTRIAL: "The First Engines",
}

BATTLE_PREFIXES: dict[str, list[str]] = {
    "early": ["The Raid on", "The Skirmish at"],
    "mid": ["The Battle of", "The Siege of"],
    "late": ["The Siege of", "The Sack of", "The Rout at"],
}

TREATY_ADJECTIVES = [
    "Sapphire", "Iron", "Golden", "Silver", "Ivory", "Crimson", "Amber",
    "Jade", "Obsidian", "Pearl", "Cedar", "Marble", "Twilight", "Dawn",
    "Storm", "Frost", "Flame", "Shadow", "Sun", "Moon",
]

TREATY_NOUNS = [
    "Accord", "Pact", "Concord", "Treaty", "Alliance", "Covenant",
    "Compact", "Convention", "Understanding", "Truce", "Bond",
    "Charter", "Concordat", "Entente", "Protocol",
]

WORK_TYPES = [
    "Codex", "Chronicle", "Great Lighthouse", "Grand Temple", "Monument",
    "Library", "Academy", "Cathedral", "Colosseum", "Amphitheater",
    "Obelisk", "Archive", "Gallery", "Mosaic", "Tapestry",
]

WORK_THEMES = [
    "Songs", "Wisdom", "Valor", "Stars", "Ages", "Dreams",
    "Legends", "Winds", "Tides", "Flames", "Shadows", "Dawn",
    "Ancestors", "Prophecy", "Memory",
]

_ORDINALS = ["Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth"]


def _seed_rng(base_seed: int, turn: int, extra: str) -> random.Random:
    return random.Random(stable_hash_int("named_event", base_seed, turn, extra))


def generate_battle_name(region: str, era: TechEra, world: WorldState, seed: int) -> str:
    rng = _seed_rng(seed, world.turn, region)
    era_idx = list(TechEra).index(era)
    if era_idx <= 1:
        prefixes = BATTLE_PREFIXES["early"]
    elif era_idx <= 3:
        prefixes = BATTLE_PREFIXES["mid"]
    else:
        prefixes = BATTLE_PREFIXES["late"]
    prefix = rng.choice(prefixes)
    name = f"{prefix} {region}"
    existing = history_index(world).named_event_names(world)
    return deduplicate_name(name, existing)


def generate_treaty_name(civ1_name: str, civ2_name: str, world: WorldState, seed: int) -> str:
    rng = _seed_rng(seed, world.turn, civ1_name + civ2_name)
    adj = rng.choice(TREATY_ADJECTIVES)
    noun = rng.choice(TREATY_NOUNS)
    name = f"The {adj} {noun}"
    existing = history_index(world).named_event_names(world)
    return deduplicate_name(name, existing)


def generate_cultural_work(civ: Civilization, world: WorldState, seed: int) -> str:
    rng = _seed_rng(seed, world.turn, civ.name)
    work_type = rng.choice(WORK_TYPES)
    theme = rng.choice(WORK_THEMES)
    civ_adj = civ.name.split()[0]
    name = f"The {work_type} of {civ_adj} {theme}"
    existing = history_index(world).named_event_names(world)
    return deduplicate_name(name, existing)


def generate_tech_breakthrough_name(era: TechEra) -> str:
    return TECH_BREAKTHROUGH_NAMES.get(era, f"The Advance to {era.value}")


def deduplicate_name(name: str, existing: "Collection[str]") -> str:
    """Return name, or its first unused ordinal variant.

    ``existing`` needs only ``in`` and ``len`` (a list of names or the
    history index's equivalent view).
    """
    if name not in existing:
        return name
    for ordinal in _ORDINALS:
        if name.startswith("The "):
            candidate = f"The {ordinal} {name[4:]}"
        else:
            candidate = f"{ordinal} {name}"
        if candidate not in existing:
            return candidate
    return f"{name} ({len(existing) + 1})"
