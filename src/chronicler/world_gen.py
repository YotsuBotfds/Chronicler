"""Initial world generation — creates a starting WorldState.

Uses deterministic generation from a seed. Region names, civilization names,
leader names, and cultural details are drawn from curated pools to ensure
thematic coherence without requiring LLM calls during generation.
"""
from __future__ import annotations

import json
import random
from typing import Any

from chronicler.models import (
    Civilization,
    Disposition,
    Leader,
    Region,
    Relationship,
    TechEra,
    WorldState,
)
from chronicler.ecology import effective_capacity, TERRAIN_ECOLOGY_DEFAULTS
from chronicler.leaders import _pick_regnal_name, _compose_regnal_name

# --- Name and trait pools ---

REGION_TEMPLATES: list[dict] = [
    {"name": "Verdant Plains", "terrain": "plains", "capacity": 80, "resources": "fertile"},
    {"name": "Iron Peaks", "terrain": "mountains", "capacity": 40, "resources": "mineral"},
    {"name": "Sapphire Coast", "terrain": "coast", "capacity": 60, "resources": "maritime"},
    {"name": "Thornwood", "terrain": "forest", "capacity": 50, "resources": "timber"},
    {"name": "Ashara Desert", "terrain": "desert", "capacity": 30, "resources": "barren"},
    {"name": "Crystalfen Marsh", "terrain": "plains", "capacity": 40, "resources": "fertile"},
    {"name": "Stormbreak Cliffs", "terrain": "mountains", "capacity": 30, "resources": "mineral"},
    {"name": "Sunfire Steppe", "terrain": "plains", "capacity": 60, "resources": "fertile"},
    {"name": "Mistwood", "terrain": "forest", "capacity": 50, "resources": "timber"},
    {"name": "Obsidian Shore", "terrain": "coast", "capacity": 50, "resources": "maritime"},
    {"name": "Frostholm Tundra", "terrain": "tundra", "capacity": 20, "resources": "barren"},
    {"name": "Amber Valley", "terrain": "plains", "capacity": 70, "resources": "fertile"},
]

CIV_TEMPLATES: list[dict] = [
    {"name": "Kethani Empire", "domains": ["maritime", "commerce"], "values": ["Trade", "Order"], "trait": "calculating"},
    {"name": "Dorrathi Clans", "domains": ["mountain", "warfare"], "values": ["Honor", "Strength"], "trait": "aggressive"},
    {"name": "Selurian Republic", "domains": ["scholarship", "diplomacy"], "values": ["Knowledge", "Liberty"], "trait": "cautious"},
    {"name": "Vrashni Dominion", "domains": ["faith", "expansion"], "values": ["Piety", "Destiny"], "trait": "zealous"},
    {"name": "Thornwall Confederacy", "domains": ["forest", "resilience"], "values": ["Tradition", "Self-reliance"], "trait": "stubborn"},
    {"name": "Ashkari Nomads", "domains": ["desert", "adaptability"], "values": ["Freedom", "Cunning"], "trait": "opportunistic"},
]

LEADER_NAMES: list[str] = [
    "Vaelith", "Gorath", "Seren", "Thaldric", "Mirael",
    "Kassander", "Ulveth", "Zhara", "Fenrik", "Aelindra",
]

LEADER_TITLES: list[str] = [
    "Emperor", "Empress", "Warchief", "Archon", "High Priestess",
    "Chancellor", "Sovereign", "Elder", "Khan", "Consul",
]

DEFAULT_EVENT_PROBABILITIES: dict[str, float] = {
    "drought": 0.05,
    "plague": 0.03,
    "earthquake": 0.02,
    "religious_movement": 0.04,
    "discovery": 0.06,
    "leader_death": 0.03,
    "rebellion": 0.05,
    "migration": 0.04,
    "cultural_renaissance": 0.03,
    "border_incident": 0.08,
}


def generate_regions(count: int = 8, seed: int = 42) -> list[Region]:
    """Generate a set of named regions from the template pool.

    If *count* exceeds the template pool size (currently 12), a ValueError
    is raised rather than silently capping the result.
    """
    if count > len(REGION_TEMPLATES):
        raise ValueError(
            f"Requested {count} regions but only {len(REGION_TEMPLATES)} "
            f"region templates are available"
        )
    rng = random.Random(seed)
    templates = rng.sample(REGION_TEMPLATES, k=count)
    regions = []
    for t in templates:
        region = Region(
            name=t["name"],
            terrain=t["terrain"],
            carrying_capacity=t["capacity"],
            resources=t["resources"],
        )
        defaults = TERRAIN_ECOLOGY_DEFAULTS.get(region.terrain)
        if defaults:
            region.ecology = defaults.model_copy()
        regions.append(region)
    return regions


def assign_civilizations(
    regions: list[Region],
    civ_count: int = 4,
    seed: int = 42,
) -> list[Civilization]:
    """Create civilizations and assign them starting regions."""
    rng = random.Random(seed)
    templates = rng.sample(CIV_TEMPLATES, k=min(civ_count, len(CIV_TEMPLATES)))
    names_pool = list(LEADER_NAMES)
    rng.shuffle(names_pool)
    titles_pool = list(LEADER_TITLES)
    rng.shuffle(titles_pool)

    # Distribute regions: each civ gets at least 1, remainder uncontrolled
    available = list(regions)
    rng.shuffle(available)

    civs: list[Civilization] = []
    for i, t in enumerate(templates):
        # Assign 1–2 starting regions
        assigned = [available.pop(0).name] if available else []
        if available and rng.random() < 0.5:
            assigned.append(available.pop(0).name)

        # Mark regions as controlled
        for region in regions:
            if region.name in assigned:
                region.controller = t["name"]

        # Use pools for placeholder leader name (consumed from main RNG to preserve sequence)
        _placeholder_title = titles_pool[i % len(titles_pool)]
        _placeholder_name = names_pool[i % len(names_pool)]
        leader_name = f"{_placeholder_title} {_placeholder_name}"
        total_pop = rng.randint(30, 70)
        civs.append(
            Civilization(
                name=t["name"],
                population=total_pop,
                military=rng.randint(20, 70),
                economy=rng.randint(30, 70),
                culture=rng.randint(20, 70),
                stability=rng.randint(40, 70),
                tech_era=TechEra.TRIBAL,
                treasury=rng.randint(30, 150),
                leader=Leader(name=leader_name, trait=t["trait"], reign_start=0),
                domains=t["domains"],
                values=t["values"],
                goal="",
                regions=assigned,
                asabiya=round(rng.uniform(0.4, 0.8), 2),
            ),
        )

        # M51: Apply regnal naming to founding leader
        # Use the pre-selected pool name as throne_name and title directly.
        # Seed regnal_name_counts for the founding leader.
        civ = civs[-1]
        throne_name = _placeholder_name
        civ.regnal_name_counts[throne_name] = 1
        ordinal = 0  # First holder
        regnal_display = _compose_regnal_name(_placeholder_title, throne_name, ordinal)
        civ.leader.name = regnal_display
        civ.leader.throne_name = throne_name
        civ.leader.regnal_ordinal = ordinal

        # P4: distribute initial population across starting regions
        assigned_regions = [r for r in regions if r.name in assigned]
        if assigned_regions:
            total_cap = sum(effective_capacity(r) for r in assigned_regions)
            remainder = total_pop
            for j, ar in enumerate(assigned_regions):
                if j == len(assigned_regions) - 1:
                    ar.population = remainder
                else:
                    share = (
                        round(total_pop * effective_capacity(ar) / total_cap)
                        if total_cap > 0
                        else total_pop // len(assigned_regions)
                    )
                    ar.population = share
                    remainder -= share

    return civs


def _build_relationships(civ_names: list[str], seed: int) -> dict[str, dict[str, Relationship]]:
    """Initialize relationship matrix between all civilizations."""
    rng = random.Random(seed)
    dispositions = [Disposition.NEUTRAL, Disposition.SUSPICIOUS, Disposition.FRIENDLY]
    rels: dict[str, dict[str, Relationship]] = {}
    for name in civ_names:
        rels[name] = {}
        for other in civ_names:
            if other != name:
                rels[name][other] = Relationship(
                    disposition=rng.choice(dispositions),
                )
    return rels


def generate_world(
    seed: int = 42,
    num_regions: int = 8,
    num_civs: int = 4,
    world_name: str = "Aetheris",
) -> WorldState:
    """Generate a complete initial WorldState ready for simulation."""
    regions = generate_regions(count=num_regions, seed=seed)
    from chronicler.adjacency import compute_adjacencies, classify_regions
    compute_adjacencies(regions)
    # Classify region roles by graph topology
    adj_map = {r.name: r.adjacencies for r in regions}
    roles = classify_regions(adj_map)
    for region in regions:
        region.role = roles.get(region.name, "standard")
    from chronicler.resources import assign_resources
    assign_resources(regions, seed=seed)
    from chronicler.resources import assign_resource_types, populate_legacy_resources
    assign_resource_types(regions, seed=seed)
    populate_legacy_resources(regions)
    civs = assign_civilizations(regions, civ_count=num_civs, seed=seed)
    for civ in civs:
        if civ.regions and civ.capital_region is None:
            civ.capital_region = civ.regions[0]
    civ_names = [c.name for c in civs]
    relationships = _build_relationships(civ_names, seed=seed + 1)

    # Seed used_leader_names so succession can't duplicate initial leaders
    used_leader_names = [c.leader.name for c in civs]

    world = WorldState(
        name=world_name,
        seed=seed,
        turn=0,
        regions=regions,
        civilizations=civs,
        relationships=relationships,
        historical_figures=[],
        events_timeline=[],
        active_conditions=[],
        event_probabilities=dict(DEFAULT_EVENT_PROBABILITIES),
        used_leader_names=used_leader_names,
    )

    # Auto-enable fog of war for larger worlds
    if len(regions) >= 15:
        world.fog_of_war = True

    from chronicler.exploration import initialize_fog
    initialize_fog(world)

    # M16a: Initialize cultural identity for controlled regions
    for region in world.regions:
        if region.controller is not None:
            region.cultural_identity = region.controller

    # M35b: Initialize disease baseline and effective yields
    for region in world.regions:
        eco = region.ecology
        if eco.water > 0.6 and eco.soil > 0.5:
            region.disease_baseline = 0.02  # Fever
        elif region.terrain == "desert":
            region.disease_baseline = 0.015  # Cholera
        else:
            region.disease_baseline = 0.01  # Plague
        region.endemic_severity = region.disease_baseline
        region.resource_effective_yields = list(region.resource_base_yields)

    # M43a: Initialize stockpile for controlled regions with valid resources
    from chronicler.economy import bootstrap_region_stockpile
    for region in world.regions:
        if region.controller is not None:
            bootstrap_region_stockpile(region)

    # M37: Generate one faith per civ
    if world.civilizations:
        from chronicler.religion import generate_faiths
        civ_values = [c.values for c in world.civilizations]
        civ_names = [c.name for c in world.civilizations]
        world.belief_registry = generate_faiths(civ_values, civ_names, seed=world.seed)
        # M38b: Seed previous_majority_faith from founding faith
        for civ in world.civilizations:
            civ.previous_majority_faith = civ.civ_majority_faith

    return world


def enrich_with_llm(world: WorldState, client: Any) -> None:
    """Use the LLM to generate creative goals and backstory details.

    Accepts any LLMClient (LocalClient or AnthropicClient). Uses the
    client.complete() protocol, not raw SDK calls.
    """
    civ_summaries = "\n".join(
        f"- {c.name}: domains={c.domains}, values={c.values}, "
        f"leader={c.leader.name} ({c.leader.trait}), regions={c.regions}"
        for c in world.civilizations
    )

    prompt = f"""Given these civilizations in the world of {world.name}:

{civ_summaries}

Generate a strategic goal for each civilization. Goals should be specific,
achievable within 50 turns, and reflect the civilization's domains and values.

Respond as JSON: {{"goals": ["goal for civ 1", "goal for civ 2", ...]}}"""

    response_text = client.complete(prompt, max_tokens=500)
    try:
        data = json.loads(response_text)
        goals = data.get("goals", [])
        for i, civ in enumerate(world.civilizations):
            if i < len(goals):
                civ.goal = goals[i]
    except (json.JSONDecodeError, KeyError):
        pass  # Keep empty goals on parse failure
