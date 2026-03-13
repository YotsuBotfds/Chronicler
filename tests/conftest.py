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
def sample_regions():
    return [
        Region(name="Verdant Plains", terrain="plains", carrying_capacity=8, resources="fertile", controller="Kethani Empire"),
        Region(name="Iron Peaks", terrain="mountains", carrying_capacity=4, resources="mineral", controller="Dorrathi Clans"),
        Region(name="Sapphire Coast", terrain="coast", carrying_capacity=6, resources="maritime", controller="Kethani Empire"),
        Region(name="Thornwood", terrain="forest", carrying_capacity=5, resources="timber"),
        Region(name="Ashara Desert", terrain="desert", carrying_capacity=3, resources="barren"),
    ]


@pytest.fixture
def sample_civilizations():
    return [
        Civilization(
            name="Kethani Empire",
            population=7, military=5, economy=8, culture=6, stability=6,
            tech_era=TechEra.IRON,
            treasury=12,
            leader=Leader(name="Empress Vaelith", trait="calculating", reign_start=0),
            domains=["maritime", "commerce"],
            values=["Trade", "Order"],
            goal="Expand trade networks to all coastal regions",
            regions=["Verdant Plains", "Sapphire Coast"],
            asabiya=0.6,
        ),
        Civilization(
            name="Dorrathi Clans",
            population=4, military=7, economy=3, culture=5, stability=4,
            tech_era=TechEra.IRON,
            treasury=5,
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
        historical_figures=[],
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
