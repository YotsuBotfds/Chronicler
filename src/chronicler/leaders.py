"""Leader system — succession, name pools, legacy, rivalry, trait evolution."""

from __future__ import annotations

import random
import re

from chronicler.models import (
    ActiveCondition, Civilization, Event, Leader, NamedEvent, TechEra, WorldState,
)
from chronicler.utils import civ_index, clamp, STAT_FLOOR
from chronicler.emergence import get_severity_multiplier


_DOMAIN_TO_ARCHETYPE: dict[str, str] = {
    "maritime": "maritime", "commerce": "maritime", "coastal": "maritime",
    "nomadic": "steppe", "pastoral": "steppe", "plains": "steppe",
    "highland": "mountain", "mining": "mountain", "fortress": "mountain",
    "woodland": "forest", "sylvan": "forest", "nature": "forest",
    "arid": "desert", "oasis": "desert",
    "knowledge": "scholarly", "arcane": "scholarly", "culture": "scholarly",
    "warfare": "military", "conquest": "military", "martial": "military",
    "trade": "maritime",
}

CULTURAL_NAME_POOLS: dict[str, list[str]] = {
    "maritime": [
        "Thalor", "Nerissa", "Caelwen", "Maren", "Pelago", "Coralind", "Wavecrest",
        "Tidara", "Nautica", "Syrenis", "Riptide", "Kelphorn", "Deepwell", "Saltara",
        "Brinehart", "Seafoam", "Anchora", "Pearlwind", "Driftmere", "Gillian",
        "Hullbreaker", "Sternwell", "Bowsprit", "Jetsam", "Flotsam", "Reefborn",
        "Cordelia", "Tempesta", "Marinus", "Oceania", "Trillia", "Cascadis",
        "Abyssia", "Lagunara", "Shoalwick", "Harbright", "Windlass", "Compass",
        "Starboard", "Portwyn", "Leeward", "Helmford",
    ],
    "steppe": [
        "Toghrul", "Arslan", "Khulan", "Borte", "Temuge", "Jochi", "Sartaq",
        "Khutulun", "Batu", "Chagatai", "Ogedei", "Mongke", "Qasar", "Belgutei",
        "Subotai", "Jelme", "Muqali", "Jebe", "Subutai", "Tolui", "Alaqhai",
        "Manduhai", "Dayir", "Esen", "Turakina", "Guyuk", "Berke", "Hulagu",
        "Ariqboke", "Kaidu", "Toregene", "Sorqoqtani", "Chabi", "Doquz",
        "Bayar", "Tengri", "Altani", "Sorghaghtani", "Qutula", "Yesugei",
        "Hoelun", "Kublai",
    ],
    "mountain": [
        "Grimald", "Valdris", "Kareth", "Stonvar", "Brynhild", "Ironpeak",
        "Granith", "Basaltus", "Slatewood", "Quartzara", "Feldspar", "Obsidara",
        "Deepforge", "Anvilor", "Cragmore", "Peakwind", "Ridgeborn", "Cliffward",
        "Bouldergate", "Stonehelm", "Crystalis", "Gneissara", "Marblind",
        "Jasperine", "Shalewick", "Chalkstone", "Flintara", "Pumicor",
        "Rockstead", "Gorgemeld", "Summitara", "Plateauris", "Escarpment",
        "Morainia", "Talonpeak", "Spirehold", "Buttressara", "Pinnaclis",
        "Corniceus", "Ledgewick", "Cairnhold", "Dolmenara",
    ],
    "forest": [
        "Elara", "Sylvain", "Thornwick", "Fernhollow", "Alder", "Willowmere",
        "Birchwind", "Oakshade", "Pinecrest", "Mossgrove", "Ivywood", "Hazelborn",
        "Ashenvale", "Cedarhelm", "Hollywick", "Elmsworth", "Maplelind",
        "Rowan", "Laurelei", "Junipera", "Yewguard", "Larchmont", "Spruceford",
        "Lindenara", "Hickorind", "Beechwell", "Chestnutar", "Walnutgrove",
        "Sequoiara", "Cypresswind", "Banyaris", "Balsamon", "Magnolind",
        "Wisteris", "Acacia", "Tamarind", "Sassafras", "Dogwoodis",
        "Redwoodara", "Timberlind", "Briarvale", "Canopyara",
    ],
    "desert": [
        "Rashidi", "Zephyra", "Khalun", "Amaris", "Deshaan", "Saharen",
        "Dunewalker", "Miraga", "Oasian", "Scorchwind", "Sandara", "Sirocco",
        "Haboobis", "Aridius", "Xerxara", "Palmyra", "Bedounis", "Camelorn",
        "Twilara", "Solstara", "Heatsear", "Dustbloom", "Cactara", "Mesquiton",
        "Saltflat", "Playana", "Wadian", "Hammadis", "Ergunis", "Taklamaris",
        "Gobindis", "Negeva", "Atacaris", "Kalahari", "Sonoris", "Chihuan",
        "Mojavan", "Tharada", "Registan", "Karakorin", "Dasht", "Nubian",
    ],
    "scholarly": [
        "Vaelis", "Isendra", "Codrin", "Lexara", "Sapienth", "Erudis",
        "Scholara", "Logicus", "Theoris", "Hypothis", "Axiomara", "Proofwind",
        "Quillborn", "Inkwell", "Parchment", "Scribanis", "Tomelord", "Volumen",
        "Catalogis", "Indexara", "Referens", "Citadel", "Archivon", "Libris",
        "Canonis", "Dogmara", "Doctrinis", "Thesaura", "Lexicon", "Glossara",
        "Syntaxis", "Grammaris", "Rhetoris", "Dialectis", "Pedagogis",
        "Curricula", "Seminarion", "Symposia", "Colloquis", "Disquisara",
        "Monographis", "Treatisa",
    ],
    "military": [
        "Gorath", "Ironvar", "Bladwyn", "Shieldra", "Warmund", "Spearhart",
        "Helmgar", "Swordane", "Arroweld", "Pikemond", "Maceborn", "Halberd",
        "Catapultis", "Rampart", "Bulwark", "Siegemund", "Vanguardis", "Flanker",
        "Skirmara", "Sentinell", "Guardwald", "Garrison", "Battalius",
        "Legionara", "Cohortis", "Centurian", "Praetoris", "Imperator",
        "Tribunes", "Optimus", "Decurian", "Signifera", "Aquilara",
        "Ballistara", "Onagris", "Trebuchet", "Mantlegar", "Palisade",
        "Stockadis", "Bastionis", "Curtainis", "Parapetar",
    ],
    "default": [],
}

CULTURAL_NAME_POOLS["default"] = [
    name for pool in CULTURAL_NAME_POOLS.values() for name in pool
]

TITLES = [
    "Emperor", "Empress", "King", "Queen", "Warchief", "High Priestess",
    "Chancellor", "Archon", "Consul", "Regent", "Sovereign", "Tribune",
    "Patriarch", "Matriarch", "Chieftain", "Elder",
]

SUCCESSION_WEIGHTS: dict[str, float] = {
    "heir": 0.40, "general": 0.25, "usurper": 0.20, "elected": 0.15,
}

_FALLBACK_WEIGHTS: dict[str, float] = {
    "heir": 0.47, "general": 0.29, "usurper": 0.24,
}

SUCCESSION_TRAIT_BIAS: dict[str, list[str]] = {
    "heir": [],
    "general": ["aggressive", "bold", "ambitious"],
    "usurper": ["ambitious", "calculating", "shrewd"],
    "elected": ["cautious", "visionary", "shrewd"],
    "clergy": ["zealous", "visionary", "cautious"],  # M38a: clergy succession type
}

ALL_TRAITS = [
    "ambitious", "cautious", "aggressive", "calculating", "zealous",
    "opportunistic", "stubborn", "bold", "shrewd", "visionary",
]

LEGACY_TRAIT_MAP: dict[str, str] = {
    "aggressive": "military_legacy", "bold": "military_legacy",
    "cautious": "stability_legacy", "calculating": "stability_legacy",
    "visionary": "economy_legacy", "shrewd": "economy_legacy",
    "zealous": "culture_legacy", "ambitious": "culture_legacy",
    "opportunistic": "economy_legacy", "stubborn": "stability_legacy",
}

LEGACY_EPITHETS: dict[str, str] = {
    "military_legacy": "the Conqueror", "stability_legacy": "the Wise",
    "economy_legacy": "the Prosperous", "culture_legacy": "the Enlightened",
}

ACTION_TO_SECONDARY: dict[str, str] = {
    "war": "warlike", "develop": "builder", "trade": "merchant",
    "expand": "conqueror", "diplomacy": "diplomat",
}


def get_archetype_for_domains(domains: list[str]) -> str:
    for domain in domains:
        archetype = _DOMAIN_TO_ARCHETYPE.get(domain.lower())
        if archetype:
            return archetype
    return "default"


def strip_title(display_name: str) -> str:
    """Extract base name from a display name by stripping known title prefixes
    and trailing crude Roman numeral sequences."""
    for title in sorted(TITLES, key=len, reverse=True):  # longest first
        prefix = title + " "
        if display_name.startswith(prefix):
            display_name = display_name[len(prefix):]
            break
    # Strip trailing crude 'I' sequences (old numbering fallback)
    display_name = re.sub(r'\s+I{2,}$', '', display_name)
    # Strip trailing proper Roman numerals
    display_name = re.sub(r'\s+(?:XX|XIX|XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|X|IX|VIII|VII|VI|V|IV|III|II)$', '', display_name)
    return display_name.strip()


def to_roman(n: int) -> str:
    if n <= 0:
        return ""
    vals = [
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    result = ""
    for value, numeral in vals:
        while n >= value:
            result += numeral
            n -= value
    return result


def _compose_regnal_name(title: str, throne_name: str, ordinal: int) -> str:
    if ordinal <= 0:
        return f"{title} {throne_name}"
    return f"{title} {throne_name} {to_roman(ordinal)}"


def _pick_base_name(civ: Civilization, world: WorldState, rng: random.Random) -> str:
    archetype = get_archetype_for_domains(civ.domains)
    pool = CULTURAL_NAME_POOLS[archetype]
    used_bases = set()
    for used in world.used_leader_names:
        parts = used.split(" ", 1)
        used_bases.add(parts[-1] if len(parts) > 1 else parts[0])
        used_bases.add(used)
    # Custom name pool (scenario-provided) takes priority
    if civ.leader_name_pool:
        custom_available = [n for n in civ.leader_name_pool if n not in used_bases]
        if custom_available:
            return rng.choice(custom_available)
    # Existing cultural pool logic
    available = [n for n in pool if n not in used_bases]
    if not available:
        available = [n for n in CULTURAL_NAME_POOLS["default"] if n not in used_bases]
    if not available:
        base = rng.choice(pool)
        count = sum(1 for n in world.used_leader_names if base in n)
        return f"{base} {'I' * (count + 2)}"
    return rng.choice(available)


def _pick_name(civ: Civilization, world: WorldState, rng: random.Random) -> str:
    base_name = _pick_base_name(civ, world, rng)
    title = rng.choice(TITLES)
    full_name = f"{title} {base_name}"
    world.used_leader_names.append(full_name)
    return full_name


def _pick_regnal_name(civ: Civilization, world: WorldState, rng: random.Random) -> tuple[str, str, int]:
    """Pick a regnal name for a new leader.

    Uses per-civ regnal_name_counts for ordinal tracking.
    Does NOT append to world.used_leader_names (separation from GP naming).

    Returns:
        (title, throne_name, ordinal) where ordinal=0 means first holder.
    """
    throne_name = _pick_base_name(civ, world, rng)
    title = rng.choice(TITLES)
    count = civ.regnal_name_counts.get(throne_name, 0)
    ordinal = count  # 0 = first holder, 1 = second holder (gets "II"), etc.
    civ.regnal_name_counts[throne_name] = count + 1
    return (title, throne_name, ordinal)


def generate_successor(civ: Civilization, world: WorldState, seed: int, force_type: str | None = None, acc=None) -> Leader:
    rng = random.Random(seed + world.turn + hash(civ.name))
    old_leader = civ.leader
    if force_type:
        stype = force_type
    else:
        types = list(SUCCESSION_WEIGHTS.keys())
        weights = list(SUCCESSION_WEIGHTS.values())
        stype = rng.choices(types, weights=weights, k=1)[0]
    if stype == "elected" and civ.culture < 50 and civ.tech_era.value not in [
        "classical", "medieval", "renaissance", "industrial"
    ]:
        types = list(_FALLBACK_WEIGHTS.keys())
        weights = list(_FALLBACK_WEIGHTS.values())
        stype = rng.choices(types, weights=weights, k=1)[0]
    bias = SUCCESSION_TRAIT_BIAS[stype]
    if stype == "heir" and rng.random() < 0.5:
        trait = old_leader.trait
    elif bias:
        trait = rng.choice(bias)
    else:
        trait = rng.choice(ALL_TRAITS)
    name = _pick_name(civ, world, rng)
    new_leader = Leader(name=name, trait=trait, reign_start=world.turn, succession_type=stype, predecessor_name=old_leader.name)
    if stype == "heir" and old_leader.rival_leader:
        new_leader.rival_leader = old_leader.rival_leader
        new_leader.rival_civ = old_leader.rival_civ
    # Inherit grudges from predecessor
    from chronicler.succession import inherit_grudges
    inherit_grudges(old_leader, new_leader)
    if stype == "general":
        mult = get_severity_multiplier(civ, world)
        if acc is not None:
            civ_idx = civ_index(world, civ.name)
            acc.add(civ_idx, civ, "stability", -int(10 * mult), "guard-shock")
            acc.add(civ_idx, civ, "military", 10, "guard-shock")
        else:
            civ.stability = clamp(civ.stability - int(10 * mult), STAT_FLOOR["stability"], 100)
            civ.military = clamp(civ.military + 10, STAT_FLOOR["military"], 100)
    elif stype == "usurper":
        mult = get_severity_multiplier(civ, world)
        if acc is not None:
            civ_idx = civ_index(world, civ.name)
            acc.add(civ_idx, civ, "stability", -int(30 * mult), "guard-shock")
            acc.add(civ_idx, civ, "asabiya", 0.1, "keep")
        else:
            civ.stability = clamp(civ.stability - int(30 * mult), STAT_FLOOR["stability"], 100)
            civ.asabiya = min(civ.asabiya + 0.1, 1.0)
        world.named_events.append(NamedEvent(
            name=f"The {civ.name} Coup", event_type="coup", turn=world.turn,
            actors=[civ.name], description=f"{name} seizes power from {old_leader.name}", importance=8,
        ))
    elif stype == "elected":
        if acc is not None:
            civ_idx = civ_index(world, civ.name)
            acc.add(civ_idx, civ, "stability", 10, "guard-shock")
        else:
            civ.stability = clamp(civ.stability + 10, STAT_FLOOR["stability"], 100)
    civ.action_counts = {}
    return new_leader


def apply_leader_legacy(civ: Civilization, leader: Leader, world: WorldState) -> Event | None:
    reign_length = world.turn - leader.reign_start
    if reign_length < 15:
        return None
    legacy_type = LEGACY_TRAIT_MAP.get(leader.trait)
    if not legacy_type:
        return None
    for condition in world.active_conditions:
        if condition.condition_type.endswith("_legacy") and civ.name in condition.affected_civs:
            return None
    world.active_conditions.append(ActiveCondition(
        condition_type=legacy_type, affected_civs=[civ.name], duration=10, severity=10,
    ))
    epithet = LEGACY_EPITHETS.get(legacy_type, "the Great")
    world.named_events.append(NamedEvent(
        name=f"The Legacy of {leader.name} {epithet}", event_type="legacy", turn=world.turn,
        actors=[civ.name], description=f"{leader.name}'s {reign_length}-turn reign leaves a lasting mark",
    ))

    # --- Legacy memory tracking ---
    # Golden age: long reign with high economy
    if reign_length >= 20 and civ.economy >= 70:
        civ.legacy_counts["golden_age"] = civ.legacy_counts.get("golden_age", 0) + 1

    # Shame: capital lost during reign
    if civ.event_counts.get("capital_lost", 0) > 0:
        civ.legacy_counts["shame"] = civ.legacy_counts.get("shame", 0) + 1

    # Fracture: secession occurred during reign
    if civ.event_counts.get("secession_occurred", 0) > 0:
        civ.legacy_counts["fracture"] = civ.legacy_counts.get("fracture", 0) + 1

    return Event(turn=world.turn, event_type="legacy", actors=[civ.name],
        description=f"The legacy of {leader.name} {epithet} endures", importance=6)


def update_rivalries(attacker: Civilization, defender: Civilization, world: WorldState) -> None:
    attacker.leader.rival_leader = defender.leader.name
    attacker.leader.rival_civ = defender.name
    defender.leader.rival_leader = attacker.leader.name
    defender.leader.rival_civ = attacker.name


def check_rival_fall(civ: Civilization, dead_leader_name: str, world: WorldState, acc=None) -> Event | None:
    for other_civ in world.civilizations:
        if other_civ.name == civ.name:
            continue
        if other_civ.leader.rival_leader == dead_leader_name:
            if acc is not None:
                other_idx = civ_index(world, other_civ.name)
                acc.add(other_idx, other_civ, "culture", 10, "guard-shock")
            else:
                other_civ.culture = clamp(other_civ.culture + 10, STAT_FLOOR["culture"], 100)
            other_civ.leader.rival_leader = None
            other_civ.leader.rival_civ = None
            world.named_events.append(NamedEvent(
                name=f"The Fall of {dead_leader_name}", event_type="rival_fall", turn=world.turn,
                actors=[other_civ.name, civ.name],
                description=f"{other_civ.leader.name} celebrates the fall of rival {dead_leader_name}",
            ))
            return Event(turn=world.turn, event_type="rival_fall", actors=[other_civ.name, civ.name],
                description=f"The rivalry ends with the fall of {dead_leader_name}", importance=6)
    return None


def check_trait_evolution(civ: Civilization, world: WorldState) -> str | None:
    leader = civ.leader
    reign_length = world.turn - leader.reign_start
    if reign_length < 10:
        return None
    if leader.secondary_trait is not None:
        return None
    if not civ.action_counts:
        return None
    majority_action = max(civ.action_counts, key=lambda k: civ.action_counts[k])
    secondary = ACTION_TO_SECONDARY.get(majority_action)
    if secondary:
        leader.secondary_trait = secondary
    return secondary
