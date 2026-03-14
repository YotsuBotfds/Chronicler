import pytest
from chronicler.models import (
    Region, Civilization, Leader, WorldState, ActionType, Relationship,
    Infrastructure, InfrastructureType,
)


class TestExplorationModels:
    def test_civ_known_regions_default_none(self):
        leader = Leader(name="L", trait="bold", reign_start=0)
        civ = Civilization(
            name="Rome", population=50, military=30, economy=40,
            culture=30, stability=50, leader=leader,
        )
        assert civ.known_regions is None

    def test_civ_known_regions_list(self):
        leader = Leader(name="L", trait="bold", reign_start=0)
        civ = Civilization(
            name="Rome", population=50, military=30, economy=40,
            culture=30, stability=50, leader=leader,
            known_regions=["Alpha", "Beta"],
        )
        assert civ.known_regions == ["Alpha", "Beta"]

    def test_region_depopulated_since(self):
        r = Region(name="T", terrain="plains", carrying_capacity=80,
                   resources="fertile")
        assert r.depopulated_since is None
        assert r.ruin_quality == 0

    def test_world_fog_of_war_default(self):
        w = WorldState(name="T", seed=42)
        assert w.fog_of_war is False

    def test_explore_action_type(self):
        assert ActionType.EXPLORE == "explore"

    def test_relationship_trade_contact_turns(self):
        r = Relationship()
        assert r.trade_contact_turns == 0


def _make_civ(name, regions=None, known_regions=None, treasury=100, trait="bold"):
    leader = Leader(name=f"L-{name}", trait=trait, reign_start=0)
    return Civilization(
        name=name, population=50, military=30, economy=40,
        culture=30, stability=50, treasury=treasury,
        leader=leader, regions=regions or [],
        known_regions=known_regions,
    )


class TestFogInitialization:
    def test_fog_seeds_home_and_adjacencies(self):
        from chronicler.exploration import initialize_fog
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome", adjacencies=["B", "C"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A", "D"]),
            Region(name="C", terrain="coast", carrying_capacity=70,
                   resources="maritime", adjacencies=["A"]),
            Region(name="D", terrain="mountains", carrying_capacity=50,
                   resources="mineral", adjacencies=["B", "E"]),
            Region(name="E", terrain="desert", carrying_capacity=30,
                   resources="mineral", adjacencies=["D"]),
        ]
        civ = _make_civ("Rome", regions=["A"])
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        initialize_fog(w)
        assert set(civ.known_regions) == {"A", "B", "C"}

    def test_fog_disabled_keeps_none(self):
        from chronicler.exploration import initialize_fog
        civ = _make_civ("Rome", regions=["A"])
        w = WorldState(name="T", seed=42, civilizations=[civ], fog_of_war=False)
        initialize_fog(w)
        assert civ.known_regions is None


class TestExploreAction:
    def test_explore_reveals_region(self):
        from chronicler.exploration import handle_explore
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A", "C"]),
            Region(name="C", terrain="coast", carrying_capacity=70,
                   resources="maritime", adjacencies=["B"]),
        ]
        civ = _make_civ("Rome", regions=["A"], known_regions=["A"],
                        treasury=20)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        event = handle_explore(w, civ)
        assert "B" in civ.known_regions
        assert "C" in civ.known_regions
        assert civ.treasury == 15

    def test_explore_costs_treasury(self):
        from chronicler.exploration import handle_explore
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A"]),
        ]
        civ = _make_civ("Rome", regions=["A"], known_regions=["A"],
                        treasury=10)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        handle_explore(w, civ)
        assert civ.treasury == 5


class TestExploreEligibility:
    def test_eligible_with_unknown_adjacent(self):
        from chronicler.exploration import is_explore_eligible
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A"]),
        ]
        civ = _make_civ("Rome", regions=["A"], known_regions=["A"], treasury=10)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        assert is_explore_eligible(w, civ) is True

    def test_ineligible_all_known(self):
        from chronicler.exploration import is_explore_eligible
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A"]),
        ]
        civ = _make_civ("Rome", regions=["A"], known_regions=["A", "B"],
                        treasury=10)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        assert is_explore_eligible(w, civ) is False

    def test_ineligible_no_fog(self):
        from chronicler.exploration import is_explore_eligible
        civ = _make_civ("Rome", regions=["A"], treasury=10)
        w = WorldState(name="T", seed=42, civilizations=[civ], fog_of_war=False)
        assert is_explore_eligible(w, civ) is False

    def test_ineligible_low_treasury(self):
        from chronicler.exploration import is_explore_eligible
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A"]),
        ]
        civ = _make_civ("Rome", regions=["A"], known_regions=["A"], treasury=3)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        assert is_explore_eligible(w, civ) is False


class TestFirstContact:
    def test_first_contact_creates_relationship(self):
        from chronicler.exploration import handle_explore
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", controller="Greece", adjacencies=["A", "C"]),
            Region(name="C", terrain="coast", carrying_capacity=70,
                   resources="maritime", adjacencies=["B"]),
        ]
        rome = _make_civ("Rome", regions=["A"], known_regions=["A"], treasury=20)
        greece = _make_civ("Greece", regions=["B"], known_regions=["B", "C"], treasury=20)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[rome, greece], fog_of_war=True)
        handle_explore(w, rome)
        assert "Greece" in w.relationships.get("Rome", {})
        assert "Rome" in w.relationships.get("Greece", {})
        fc_events = [e for e in w.events_timeline if e.event_type == "first_contact"]
        assert len(fc_events) == 1


class TestRuins:
    def test_ruin_discovery_gives_culture(self):
        from chronicler.exploration import _discover_ruins, mark_depopulated
        r = Region(name="Ruins", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller=None,
                   infrastructure=[
                       Infrastructure(type=InfrastructureType.ROADS,
                                     builder_civ="Old", built_turn=1),
                       Infrastructure(type=InfrastructureType.IRRIGATION,
                                     builder_civ="Old", built_turn=5),
                       Infrastructure(type=InfrastructureType.FORTIFICATIONS,
                                     builder_civ="Old", built_turn=10),
                   ])
        mark_depopulated(r, turn=0)
        assert r.ruin_quality == 3
        assert all(not i.active for i in r.infrastructure)

        civ = _make_civ("Rome", regions=["A"])
        civ.culture = 20
        w = WorldState(name="T", seed=42, turn=25, regions=[r],
                       civilizations=[civ])
        event = _discover_ruins(w, civ, r)
        assert civ.culture == 32
        assert r.depopulated_since is None
        assert r.ruin_quality == 0
        assert event is not None

    def test_ruin_diminishing_returns_high_culture(self):
        from chronicler.exploration import _discover_ruins
        r = Region(name="Ruins", terrain="plains", carrying_capacity=80,
                   resources="fertile", depopulated_since=0, ruin_quality=5)
        civ = _make_civ("Rome")
        civ.culture = 80
        w = WorldState(name="T", seed=42, turn=25)
        event = _discover_ruins(w, civ, r)
        assert civ.culture == 84

    def test_ruin_quality_zero_no_event(self):
        from chronicler.exploration import _discover_ruins
        r = Region(name="Ruins", terrain="plains", carrying_capacity=80,
                   resources="fertile", depopulated_since=0, ruin_quality=0)
        civ = _make_civ("Rome")
        w = WorldState(name="T", seed=42, turn=25)
        event = _discover_ruins(w, civ, r)
        assert event is None


class TestMigrationDiscovery:
    def test_migration_reveals_source_region(self):
        from chronicler.exploration import reveal_migration_source
        civ = _make_civ("Rome", known_regions=["A"])
        reveal_migration_source(civ, "B")
        assert "B" in civ.known_regions

    def test_migration_no_reveal_if_omniscient(self):
        from chronicler.exploration import reveal_migration_source
        civ = _make_civ("Rome")
        reveal_migration_source(civ, "B")
        assert civ.known_regions is None
