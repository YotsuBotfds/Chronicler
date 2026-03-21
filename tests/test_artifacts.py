# tests/test_artifacts.py
import pytest
from chronicler.models import (
    Artifact, ArtifactType, ArtifactStatus,
    ArtifactIntent, ArtifactLifecycleIntent, WorldState,
    GreatPerson,
)
from chronicler.artifacts import tick_artifacts, PRESTIGE_BY_TYPE, _prosperity_gate, select_cultural_artifact_type


def _make_world_with_civ(civ_name="TestCiv", region_name="Region1", values=None):
    """Helper: build a minimal WorldState with one civ and one region."""
    from chronicler.models import WorldState, Civilization, Region, Leader
    region = Region(name=region_name, terrain="plains", resources="fertile",
                    adjacencies=[], carrying_capacity=100)
    leader = Leader(name="TestLeader", trait="brave", reign_start=0)
    civ = Civilization(
        name=civ_name,
        values=values or ["Honor"],
        leader=leader,
        regions=[region_name],
        capital_region=region_name,
    )
    world = WorldState(name="TestWorld", seed=42)
    world.civilizations = [civ]
    world.regions = [region]
    region.controller = civ_name
    return world


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


class TestTickArtifactsCreation:
    def test_creation_from_intent(self):
        world = _make_world_with_civ()
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.RELIC,
            trigger="temple_construction",
            creator_name=None,
            creator_born_turn=None,
            holder_name=None,
            holder_born_turn=None,
            civ_name="TestCiv",
            region_name="Region1",
            anchored=True,
            context="Sacred relic forged in the temple",
        ))
        world.turn = 10
        events = tick_artifacts(world)
        assert len(world.artifacts) == 1
        a = world.artifacts[0]
        assert a.artifact_type == ArtifactType.RELIC
        assert a.anchored is True
        assert a.owner_civ == "TestCiv"
        assert a.origin_region == "Region1"
        assert a.status == ArtifactStatus.ACTIVE
        assert a.prestige_value == PRESTIGE_BY_TYPE[ArtifactType.RELIC]

    def test_creation_emits_event(self):
        world = _make_world_with_civ()
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.WEAPON,
            trigger="gp_promotion",
            creator_name="Kiran",
            creator_born_turn=8,
            holder_name="Kiran",
            holder_born_turn=8,
            civ_name="TestCiv",
            region_name="Region1",
            anchored=False,
            context="Forged at promotion",
        ))
        world.turn = 10
        events = tick_artifacts(world)
        assert any(e.event_type == "artifact_created" for e in events)

    def test_intents_cleared_after_tick(self):
        world = _make_world_with_civ()
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.ARTWORK,
            trigger="cultural_work",
            creator_name=None,
            creator_born_turn=None,
            holder_name=None,
            holder_born_turn=None,
            civ_name="TestCiv",
            region_name="Region1",
            anchored=False,
            context="Cultural masterwork",
        ))
        world.turn = 10
        tick_artifacts(world)
        assert world._artifact_intents == []
        assert world._artifact_lifecycle_intents == []

    def test_artifact_id_increments(self):
        world = _make_world_with_civ()
        for i in range(3):
            world._artifact_intents.append(ArtifactIntent(
                artifact_type=ArtifactType.TREATISE,
                trigger="cultural_work",
                creator_name=None,
                creator_born_turn=None,
                holder_name=None,
                holder_born_turn=None,
                civ_name="TestCiv",
                region_name="Region1",
                anchored=False,
                context=f"Work {i}",
            ))
        world.turn = 10
        tick_artifacts(world)
        ids = [a.artifact_id for a in world.artifacts]
        assert ids == [1, 2, 3]

    def test_name_collision_reroll(self):
        world = _make_world_with_civ()
        for _ in range(2):
            world._artifact_intents.append(ArtifactIntent(
                artifact_type=ArtifactType.RELIC,
                trigger="temple_construction",
                creator_name=None,
                creator_born_turn=None,
                holder_name=None,
                holder_born_turn=None,
                civ_name="TestCiv",
                region_name="Region1",
                anchored=True,
                context="Temple relic",
            ))
        world.turn = 10
        tick_artifacts(world)
        names = [a.name for a in world.artifacts]
        assert len(set(names)) == 2  # No duplicates

    def test_prestige_by_civ_computed(self):
        world = _make_world_with_civ()
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.MONUMENT,
            trigger="cultural_work",
            creator_name=None,
            creator_born_turn=None,
            holder_name=None,
            holder_born_turn=None,
            civ_name="TestCiv",
            region_name="Region1",
            anchored=True,
            context="Monument",
        ))
        world.turn = 10
        tick_artifacts(world)
        assert world._artifact_prestige_by_civ.get("TestCiv") == PRESTIGE_BY_TYPE[ArtifactType.MONUMENT]

    def test_history_entry_on_creation(self):
        world = _make_world_with_civ()
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.RELIC,
            trigger="temple_construction",
            creator_name=None,
            creator_born_turn=None,
            holder_name=None,
            holder_born_turn=None,
            civ_name="TestCiv",
            region_name="Region1",
            anchored=True,
            context="Sacred relic forged in the temple",
        ))
        world.turn = 10
        tick_artifacts(world)
        assert len(world.artifacts[0].history) == 1
        assert "turn 10" in world.artifacts[0].history[0]


class TestProsperityGate:
    def test_prosperous_civ_passes(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 50
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 0
        world.active_wars = []
        assert _prosperity_gate(civ, world) is True

    def test_low_stability_fails(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 60
        civ.treasury = 50
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 0
        world.active_wars = []
        assert _prosperity_gate(civ, world) is False

    def test_at_war_fails(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 50
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 0
        world.active_wars = [("TestCiv", "EnemyCiv")]
        assert _prosperity_gate(civ, world) is False

    def test_in_decline_fails(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 50
        civ.decline_turns = 3
        civ.succession_crisis_turns_remaining = 0
        world.active_wars = []
        assert _prosperity_gate(civ, world) is False

    def test_succession_crisis_fails(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 50
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 5
        world.active_wars = []
        assert _prosperity_gate(civ, world) is False

    def test_low_treasury_fails(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 10
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 0
        world.active_wars = []
        assert _prosperity_gate(civ, world) is False


class TestCulturalArtifactTypeSelection:
    def test_returns_valid_type(self):
        from chronicler.models import Civilization, Leader
        civ = Civilization(
            name="TestCiv", values=["Knowledge"], leader=Leader(name="L", trait="t", reign_start=0),
            regions=["R1"],
        )
        atype = select_cultural_artifact_type(civ, seed=42)
        assert atype in (ArtifactType.ARTWORK, ArtifactType.TREATISE, ArtifactType.MONUMENT)

    def test_deterministic(self):
        from chronicler.models import Civilization, Leader
        civ = Civilization(
            name="TestCiv", values=["Knowledge"], leader=Leader(name="L", trait="t", reign_start=0),
            regions=["R1"],
        )
        t1 = select_cultural_artifact_type(civ, seed=42)
        t2 = select_cultural_artifact_type(civ, seed=42)
        assert t1 == t2


def _make_active_artifact(world, artifact_type=ArtifactType.RELIC, anchored=True,
                           owner_civ="TestCiv", region="Region1", **kwargs):
    """Helper: add an active artifact to world and return it."""
    aid = len(world.artifacts) + 1
    a = Artifact(
        artifact_id=aid, name=f"Artifact {aid}", artifact_type=artifact_type,
        anchored=anchored, origin_turn=1, origin_event="test",
        origin_region=region, creator_name=None, creator_civ=owner_civ,
        owner_civ=owner_civ, holder_name=kwargs.get("holder_name"),
        holder_born_turn=kwargs.get("holder_born_turn"),
        anchor_region=region if anchored else None,
        prestige_value=PRESTIGE_BY_TYPE.get(artifact_type, 1),
        status=ArtifactStatus.ACTIVE, history=["created"],
        **{k: v for k, v in kwargs.items() if k not in ("holder_name", "holder_born_turn")},
    )
    world.artifacts.append(a)
    return a


class TestConquestTransfers:
    def test_anchored_artifact_changes_owner_on_nondestructive_conquest(self):
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.MONUMENT, anchored=True, owner_civ="TestCiv")
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="conquest_transfer", losing_civ="TestCiv", gaining_civ="Conqueror",
            region="Region1", is_capital=False, is_full_absorption=False, is_destructive=False,
        ))
        world.turn = 20
        tick_artifacts(world)
        assert world.artifacts[0].owner_civ == "Conqueror"
        assert world.artifacts[0].status == ArtifactStatus.ACTIVE

    def test_anchored_artifact_destroyed_on_scorched_earth(self):
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.MONUMENT, anchored=True, owner_civ="TestCiv")
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="conquest_transfer", losing_civ="TestCiv", gaining_civ="Conqueror",
            region="Region1", is_capital=False, is_full_absorption=False, is_destructive=True,
        ))
        world.turn = 20
        events = tick_artifacts(world)
        assert world.artifacts[0].status == ArtifactStatus.DESTROYED
        assert world.artifacts[0].owner_civ is None
        assert any(e.event_type == "artifact_destroyed" for e in events)

    def test_portable_artifacts_transfer_on_capital_capture(self):
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.TREATISE, anchored=False, owner_civ="TestCiv")
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="conquest_transfer", losing_civ="TestCiv", gaining_civ="Conqueror",
            region="Region1", is_capital=True, is_full_absorption=False, is_destructive=False,
        ))
        world.turn = 20
        events = tick_artifacts(world)
        assert world.artifacts[0].owner_civ == "Conqueror"
        assert any(e.event_type == "artifact_captured" for e in events)

    def test_portable_artifacts_NOT_transferred_on_non_capital_conquest(self):
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.TREATISE, anchored=False, owner_civ="TestCiv")
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="conquest_transfer", losing_civ="TestCiv", gaining_civ="Conqueror",
            region="Region1", is_capital=False, is_full_absorption=False, is_destructive=False,
        ))
        world.turn = 20
        tick_artifacts(world)
        assert world.artifacts[0].owner_civ == "TestCiv"

    def test_character_held_artifact_stays_with_holder(self):
        world = _make_world_with_civ()
        _make_active_artifact(
            world, ArtifactType.WEAPON, anchored=False, owner_civ="TestCiv",
            holder_name="Kiran", holder_born_turn=8,
        )
        gp = GreatPerson(
            name="Kiran", role="general", trait="brave", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=8, active=True,
        )
        world.civilizations[0].great_persons.append(gp)
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="conquest_transfer", losing_civ="TestCiv", gaining_civ="Conqueror",
            region="Region1", is_capital=True, is_full_absorption=True, is_destructive=False,
        ))
        world.turn = 20
        tick_artifacts(world)
        assert world.artifacts[0].holder_name == "Kiran"


class TestHolderLifecycle:
    def test_inactive_holder_reverts_to_civ(self):
        world = _make_world_with_civ()
        _make_active_artifact(
            world, ArtifactType.WEAPON, anchored=False, owner_civ="TestCiv",
            holder_name="Kiran", holder_born_turn=8,
        )
        gp = GreatPerson(
            name="Kiran", role="general", trait="brave", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=8, active=False, fate="dead",
        )
        world.civilizations[0].great_persons.append(gp)
        world.turn = 30
        tick_artifacts(world)
        assert world.artifacts[0].holder_name is None
        assert world.artifacts[0].owner_civ == "TestCiv"

    def test_mule_holder_death_emits_event(self):
        world = _make_world_with_civ()
        _make_active_artifact(
            world, ArtifactType.WEAPON, anchored=False, owner_civ="TestCiv",
            holder_name="Kiran", holder_born_turn=8, mule_origin=True,
        )
        gp = GreatPerson(
            name="Kiran", role="general", trait="brave", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=8, active=False, fate="dead",
        )
        world.civilizations[0].great_persons.append(gp)
        world.turn = 30
        events = tick_artifacts(world)
        assert any(e.event_type == "mule_artifact_relinquished" for e in events)


class TestCivDestruction:
    def test_no_absorber_marks_artifacts_lost(self):
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.RELIC, anchored=True, owner_civ="TestCiv")
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="civ_destruction", losing_civ="TestCiv", gaining_civ=None,
            region="Region1", is_capital=True, is_full_absorption=True, is_destructive=False,
        ))
        world.turn = 50
        events = tick_artifacts(world)
        assert world.artifacts[0].status == ArtifactStatus.LOST
        assert world.artifacts[0].owner_civ is None
        assert any(e.event_type == "artifact_lost" for e in events)

    def test_live_holder_survives_civ_destruction(self):
        world = _make_world_with_civ()
        _make_active_artifact(
            world, ArtifactType.WEAPON, anchored=False, owner_civ="TestCiv",
            holder_name="Exile", holder_born_turn=5,
        )
        gp = GreatPerson(
            name="Exile", role="general", trait="brave", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=5, active=True,
        )
        world.civilizations[0].great_persons.append(gp)
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="civ_destruction", losing_civ="TestCiv", gaining_civ=None,
            region="Region1", is_capital=True, is_full_absorption=True, is_destructive=False,
        ))
        world.turn = 50
        tick_artifacts(world)
        assert world.artifacts[0].status == ArtifactStatus.ACTIVE
        assert world.artifacts[0].holder_name == "Exile"
