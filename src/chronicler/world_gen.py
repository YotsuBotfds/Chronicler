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
    return [
        Region(
            name=t["name"],
            terrain=t["terrain"],
            carrying_capacity=t["capacity"],
            resources=t["resources"],
        )
        for t in templates
    ]


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

        leader_name = f"{titles_pool[i % len(titles_pool)]} {names_pool[i % len(names_pool)]}"
        civs.append(
            Civilization(
                name=t["name"],
                population=rng.randint(30, 70),
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
    civs = assign_civilizations(regions, civ_count=num_civs, seed=seed)
    civ_names = [c.name for c in civs]
    relationships = _build_relationships(civ_names, seed=seed + 1)

    # Seed used_leader_names so succession can't duplicate initial leaders
    used_leader_names = [c.leader.name for c in civs]

    return WorldState(
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
