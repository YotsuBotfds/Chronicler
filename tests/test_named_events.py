import pytest
from chronicler.models import (
    Civilization, Leader, NamedEvent, TechEra, WorldState, Region,
    Relationship, Disposition,
)
from chronicler.named_events import (
    generate_battle_name, generate_treaty_name, generate_cultural_work,
    generate_tech_breakthrough_name, deduplicate_name,
)


@pytest.fixture
def named_world():
    leader = Leader(name="Vaelith", trait="bold", reign_start=0)
    civ1 = Civilization(
        name="Kethani Empire", population=5, military=5, economy=5, culture=5,
        stability=5, tech_era=TechEra.IRON, treasury=10,
        leader=leader, regions=["Thornwood"], domains=["maritime", "commerce"],
        values=["Trade", "Order"],
    )
    civ2 = Civilization(
        name="Dorrathi Clans", population=5, military=5, economy=5, culture=5,
        stability=5, tech_era=TechEra.IRON, treasury=10,
        leader=Leader(name="Gorath", trait="aggressive", reign_start=0),
        regions=["Iron Peaks"], domains=["warfare", "conquest"],
        values=["Honor", "Strength"],
    )
    return WorldState(
        name="Test", seed=42, turn=10,
        regions=[
            Region(name="Thornwood", terrain="forest", carrying_capacity=7, resources="timber"),
            Region(name="Iron Peaks", terrain="mountains", carrying_capacity=5, resources="mineral"),
        ],
        civilizations=[civ1, civ2],
    )


class TestBattleNames:
    def test_tribal_era_uses_raid_or_skirmish(self, named_world):
        name = generate_battle_name("Thornwood", TechEra.TRIBAL, named_world, seed=42)
        assert "Thornwood" in name
        assert any(prefix in name for prefix in ["Raid", "Skirmish"])

    def test_iron_era_uses_battle_or_siege(self, named_world):
        name = generate_battle_name("Iron Peaks", TechEra.IRON, named_world, seed=42)
        assert "Iron Peaks" in name
        assert any(prefix in name for prefix in ["Battle", "Siege"])

    def test_medieval_era_uses_siege_sack_rout(self, named_world):
        name = generate_battle_name("Thornwood", TechEra.MEDIEVAL, named_world, seed=42)
        assert "Thornwood" in name
        assert any(prefix in name for prefix in ["Siege", "Sack", "Rout"])

    def test_deterministic_with_same_seed(self, named_world):
        n1 = generate_battle_name("Thornwood", TechEra.IRON, named_world, seed=42)
        n2 = generate_battle_name("Thornwood", TechEra.IRON, named_world, seed=42)
        assert n1 == n2

    def test_different_seed_can_produce_different_name(self, named_world):
        n1 = generate_battle_name("Thornwood", TechEra.IRON, named_world, seed=42)
        n2 = generate_battle_name("Thornwood", TechEra.IRON, named_world, seed=999)
        assert "Thornwood" in n1
        assert "Thornwood" in n2


class TestTreatyNames:
    def test_treaty_name_format(self, named_world):
        name = generate_treaty_name("Kethani Empire", "Dorrathi Clans", named_world, seed=42)
        assert name.startswith("The ")
        assert len(name) > 10

    def test_deterministic(self, named_world):
        n1 = generate_treaty_name("Kethani Empire", "Dorrathi Clans", named_world, seed=42)
        n2 = generate_treaty_name("Kethani Empire", "Dorrathi Clans", named_world, seed=42)
        assert n1 == n2


class TestCulturalWorks:
    def test_cultural_work_format(self, named_world):
        name = generate_cultural_work(named_world.civilizations[0], named_world, seed=42)
        assert len(name) > 10
        assert name.startswith("The ")

    def test_deterministic(self, named_world):
        n1 = generate_cultural_work(named_world.civilizations[0], named_world, seed=42)
        n2 = generate_cultural_work(named_world.civilizations[0], named_world, seed=42)
        assert n1 == n2


class TestTechBreakthroughs:
    def test_breakthrough_name_for_bronze(self):
        assert generate_tech_breakthrough_name(TechEra.BRONZE) == "The Forging of Bronze"

    def test_breakthrough_name_for_industrial(self):
        assert generate_tech_breakthrough_name(TechEra.INDUSTRIAL) == "The First Engines"


class TestNamedEventCreation:
    def test_battle_name_creates_appendable_named_event(self, named_world):
        name = generate_battle_name("Thornwood", TechEra.IRON, named_world, seed=42)
        ne = NamedEvent(
            name=name, event_type="battle", turn=named_world.turn,
            actors=["Kethani Empire", "Dorrathi Clans"],
            region="Thornwood", description="A decisive victory", importance=7,
        )
        named_world.named_events.append(ne)
        assert len(named_world.named_events) == 1
        assert named_world.named_events[0].name == name


class TestDeduplication:
    def test_no_collision(self):
        assert deduplicate_name("The Siege of Iron Peaks", ["The Battle of Thornwood"]) == "The Siege of Iron Peaks"

    def test_collision_appends_second(self):
        assert deduplicate_name("The Battle of Thornwood", ["The Battle of Thornwood"]) == "The Second Battle of Thornwood"

    def test_double_collision_appends_third(self):
        existing = ["The Battle of Thornwood", "The Second Battle of Thornwood"]
        assert deduplicate_name("The Battle of Thornwood", existing) == "The Third Battle of Thornwood"
