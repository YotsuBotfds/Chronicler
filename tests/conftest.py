"""Shared test fixtures for the chronicler test suite."""
import pytest
from chronicler.models import (
    TechEra,
    Disposition,
    Region,
    Leader,
    Civilization,
    Relationship,
    WorldState,
)


@pytest.fixture
def make_civ():
    """Factory fixture: create a minimal Civilization with defaults."""
    def _make(name, **overrides):
        defaults = dict(
            name=name,
            population=50, military=30, economy=40, culture=30, stability=50,
            tech_era=TechEra.IRON,
            treasury=50,
            leader=Leader(name=f"Leader of {name}", trait="cautious", reign_start=0),
            regions=[f"{name}_region"],
            asabiya=0.5,
        )
        defaults.update(overrides)
        return Civilization(**defaults)
    return _make


@pytest.fixture
def make_world(make_civ):
    """Factory fixture: create a WorldState with N civs and relationships."""
    def _make(num_civs=2, seed=42):
        names = [f"Civ{i}" for i in range(num_civs)]
        regions = []
        for n in names:
            regions.append(Region(
                name=f"{n}_region", terrain="plains",
                carrying_capacity=60, resources="fertile", controller=n,
            ))
        civs = [make_civ(n) for n in names]
        rels = {}
        for a in names:
            rels[a] = {}
            for b in names:
                if a != b:
                    rels[a][b] = Relationship()
        return WorldState(
            name="TestWorld", seed=seed, turn=0,
            regions=regions, civilizations=civs, relationships=rels,
        )
    return _make


@pytest.fixture
def sample_regions():
    return [
        Region(name="Verdant Plains", terrain="plains", carrying_capacity=80, resources="fertile", controller="Kethani Empire"),
        Region(name="Iron Peaks", terrain="mountains", carrying_capacity=40, resources="mineral", controller="Dorrathi Clans"),
        Region(name="Sapphire Coast", terrain="coast", carrying_capacity=60, resources="maritime", controller="Kethani Empire"),
        Region(name="Thornwood", terrain="forest", carrying_capacity=50, resources="timber"),
        Region(name="Ashara Desert", terrain="desert", carrying_capacity=30, resources="barren"),
    ]


@pytest.fixture
def sample_civilizations():
    return [
        Civilization(
            name="Kethani Empire",
            population=70, military=50, economy=80, culture=60, stability=60,
            tech_era=TechEra.IRON,
            treasury=120,
            leader=Leader(name="Empress Vaelith", trait="calculating", reign_start=0),
            domains=["maritime", "commerce"],
            values=["Trade", "Order"],
            goal="Expand trade networks to all coastal regions",
            regions=["Verdant Plains", "Sapphire Coast"],
            asabiya=0.6,
        ),
        Civilization(
            name="Dorrathi Clans",
            population=40, military=70, economy=30, culture=50, stability=40,
            tech_era=TechEra.IRON,
            treasury=50,
            leader=Leader(name="Warchief Gorath", trait="aggressive", reign_start=0),
            domains=["mountain", "warfare"],
            values=["Honor", "Strength"],
            goal="Conquer the Verdant Plains",
            regions=["Iron Peaks"],
            asabiya=0.8,
        ),
    ]


@pytest.fixture
def sample_relationships():
    return {
        "Kethani Empire": {
            "Dorrathi Clans": Relationship(
                disposition=Disposition.SUSPICIOUS,
                grievances=["Border raids in the northern foothills"],
                trade_volume=2,
            ),
        },
        "Dorrathi Clans": {
            "Kethani Empire": Relationship(
                disposition=Disposition.HOSTILE,
                grievances=["Kethani merchants exploit mountain resources"],
                trade_volume=2,
            ),
        },
    }


@pytest.fixture
def sample_world(sample_regions, sample_civilizations, sample_relationships):
    return WorldState(
        name="Testworld",
        seed=42,
        turn=0,
        regions=sample_regions,
        civilizations=sample_civilizations,
        relationships=sample_relationships,
        events_timeline=[],
        active_conditions=[],
        event_probabilities={
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
        },
    )
