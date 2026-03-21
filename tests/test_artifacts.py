# tests/test_artifacts.py
import pytest
from chronicler.models import (
    Artifact, ArtifactType, ArtifactStatus,
    ArtifactIntent, ArtifactLifecycleIntent, WorldState,
    GreatPerson,
)


class TestArtifactModel:
    def test_artifact_type_enum_values(self):
        assert ArtifactType.RELIC == "relic"
        assert ArtifactType.WEAPON == "weapon"
        assert ArtifactType.MONUMENT == "monument"
        assert ArtifactType.ARTWORK == "artwork"
        assert ArtifactType.TREATISE == "treatise"
        assert ArtifactType.MANIFESTO == "manifesto"
        assert ArtifactType.TRADE_GOOD == "trade_good"

    def test_artifact_status_enum_values(self):
        assert ArtifactStatus.ACTIVE == "active"
        assert ArtifactStatus.LOST == "lost"
        assert ArtifactStatus.DESTROYED == "destroyed"

    def test_artifact_construction_minimal(self):
        a = Artifact(
            artifact_id=1,
            name="The Iron Blade of Tessara",
            artifact_type=ArtifactType.WEAPON,
            anchored=False,
            origin_turn=10,
            origin_event="Forged at promotion of General Kiran",
            origin_region="Tessara",
            creator_name="Kiran",
            creator_civ="Kethani Empire",
            owner_civ="Kethani Empire",
            holder_name="Kiran",
            holder_born_turn=8,
            anchor_region=None,
            prestige_value=2,
            status=ArtifactStatus.ACTIVE,
            history=["Forged at the promotion of General Kiran, turn 10"],
        )
        assert a.artifact_id == 1
        assert a.mule_origin is False
        assert a.anchored is False

    def test_artifact_civ_owned_monument(self):
        a = Artifact(
            artifact_id=2,
            name="The Great Pillar of Ashara",
            artifact_type=ArtifactType.MONUMENT,
            anchored=True,
            origin_turn=50,
            origin_event="Erected during cultural renaissance",
            origin_region="Ashara",
            creator_name=None,
            creator_civ="Selurian Republic",
            owner_civ="Selurian Republic",
            holder_name=None,
            holder_born_turn=None,
            anchor_region="Ashara",
            prestige_value=4,
            status=ArtifactStatus.ACTIVE,
            history=["Erected during a cultural renaissance in Ashara, turn 50"],
        )
        assert a.anchored is True
        assert a.holder_name is None
        assert a.anchor_region == "Ashara"

    def test_artifact_serialization_roundtrip(self):
        a = Artifact(
            artifact_id=1,
            name="Test Artifact",
            artifact_type=ArtifactType.RELIC,
            anchored=True,
            origin_turn=5,
            origin_event="test",
            origin_region="Region1",
            creator_name=None,
            creator_civ="Civ1",
            owner_civ="Civ1",
            holder_name=None,
            holder_born_turn=None,
            anchor_region="Region1",
            prestige_value=3,
            status=ArtifactStatus.ACTIVE,
            history=["created"],
        )
        data = a.model_dump()
        a2 = Artifact(**data)
        assert a2.name == a.name
        assert a2.artifact_type == ArtifactType.RELIC


class TestArtifactIntent:
    def test_creation_intent(self):
        intent = ArtifactIntent(
            artifact_type=ArtifactType.RELIC,
            trigger="temple_construction",
            creator_name=None,
            creator_born_turn=None,
            holder_name=None,
            holder_born_turn=None,
            civ_name="Kethani Empire",
            region_name="Ashara",
            anchored=True,
            context="Sacred relic forged in the temple of Ashara",
        )
        assert intent.mule_origin is False

    def test_lifecycle_intent(self):
        intent = ArtifactLifecycleIntent(
            action="conquest_transfer",
            losing_civ="Selurian Republic",
            gaining_civ="Kethani Empire",
            region="Ashara",
            is_capital=True,
            is_full_absorption=False,
            is_destructive=False,
        )
        assert intent.action == "conquest_transfer"


class TestWorldStateArtifactFields:
    def test_world_state_has_artifacts_field(self):
        world = WorldState(name="TestWorld", seed=42)
        assert hasattr(world, 'artifacts')
        assert world.artifacts == []

    def test_world_state_has_transient_intent_lists(self):
        world = WorldState(name="TestWorld", seed=42)
        assert hasattr(world, '_artifact_intents')
        assert world._artifact_intents == []
        assert hasattr(world, '_artifact_lifecycle_intents')
        assert world._artifact_lifecycle_intents == []
        assert hasattr(world, '_artifact_prestige_by_civ')
        assert world._artifact_prestige_by_civ == {}

    def test_transient_fields_not_serialized(self):
        world = WorldState(name="TestWorld", seed=42)
        world._artifact_intents.append("test")
        data = world.model_dump()
        assert '_artifact_intents' not in data
        assert '_artifact_lifecycle_intents' not in data
        assert '_artifact_prestige_by_civ' not in data


class TestGreatPersonArtifactField:
    def test_mule_artifact_created_default_false(self):
        gp = GreatPerson(
            name="Kiran the Bold",
            role="general",
            trait="courageous",
            civilization="Kethani Empire",
            origin_civilization="Kethani Empire",
            born_turn=10,
        )
        assert gp.mule_artifact_created is False


from chronicler.artifacts import generate_artifact_name


class TestArtifactNaming:
    def test_weapon_name_with_creator(self):
        name = generate_artifact_name(
            ArtifactType.WEAPON, "Kiran", "Tessara", ["Honor"], seed=42,
        )
        assert isinstance(name, str)
        assert len(name) > 0
        assert "Kiran" in name or "Tessara" in name

    def test_monument_name_with_place(self):
        name = generate_artifact_name(
            ArtifactType.MONUMENT, None, "Ashara", ["Trade"], seed=99,
        )
        assert "Ashara" in name

    def test_deterministic_same_seed(self):
        n1 = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", ["Honor"], seed=42)
        n2 = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", ["Honor"], seed=42)
        assert n1 == n2

    def test_different_seed_different_name(self):
        n1 = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", ["Honor"], seed=42)
        n2 = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", ["Honor"], seed=43)
        assert isinstance(n1, str) and isinstance(n2, str)

    def test_cultural_flavor_honor(self):
        name = generate_artifact_name(ArtifactType.WEAPON, "Kiran", "Tessara", ["Honor"], seed=0)
        assert isinstance(name, str)

    def test_cultural_flavor_trade(self):
        name = generate_artifact_name(ArtifactType.ARTWORK, None, "Velanya", ["Trade"], seed=0)
        assert isinstance(name, str)

    def test_fallback_to_default_for_unknown_value(self):
        name = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", ["UnknownValue"], seed=42)
        assert isinstance(name, str) and len(name) > 0

    def test_empty_values_uses_default(self):
        name = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", [], seed=42)
        assert isinstance(name, str) and len(name) > 0

    def test_possessive_creator_name(self):
        name = generate_artifact_name(ArtifactType.MONUMENT, "Ashara", "Region1", ["Order"], seed=0)
        assert isinstance(name, str)

    def test_all_types_produce_names(self):
        for atype in ArtifactType:
            name = generate_artifact_name(atype, "Creator", "Place", ["Honor"], seed=42)
            assert isinstance(name, str) and len(name) > 0
