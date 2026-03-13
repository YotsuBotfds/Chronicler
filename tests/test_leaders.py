import pytest
from chronicler.models import (
    Civilization, Leader, TechEra, WorldState, Region, ActiveCondition,
    Disposition, Relationship, NamedEvent,
)
from chronicler.leaders import (
    generate_successor, apply_leader_legacy, check_trait_evolution,
    update_rivalries, get_archetype_for_domains, CULTURAL_NAME_POOLS, SUCCESSION_WEIGHTS,
)


@pytest.fixture
def leader_civ():
    return Civilization(
        name="Kethani Empire", population=5, military=5, economy=5, culture=6, stability=5,
        tech_era=TechEra.CLASSICAL, treasury=15,
        leader=Leader(name="Vaelith", trait="bold", reign_start=0),
        regions=["Region A"], domains=["maritime", "commerce"], values=["Trade", "Order"],
    )

@pytest.fixture
def leader_world(leader_civ):
    civ2 = Civilization(
        name="Dorrathi Clans", population=5, military=5, economy=5, culture=5, stability=5,
        tech_era=TechEra.IRON, treasury=10,
        leader=Leader(name="Gorath", trait="aggressive", reign_start=0),
        regions=["Region B"], domains=["warfare", "conquest"],
    )
    return WorldState(
        name="Test", seed=42, turn=20,
        regions=[
            Region(name="Region A", terrain="plains", carrying_capacity=8, resources="fertile"),
            Region(name="Region B", terrain="mountains", carrying_capacity=5, resources="mineral"),
        ],
        civilizations=[leader_civ, civ2],
        relationships={
            "Kethani Empire": {"Dorrathi Clans": Relationship(disposition=Disposition.HOSTILE)},
            "Dorrathi Clans": {"Kethani Empire": Relationship(disposition=Disposition.HOSTILE)},
        },
    )


class TestArchetypeMapping:
    def test_maritime_domain(self):
        assert get_archetype_for_domains(["maritime", "commerce"]) == "maritime"
    def test_warfare_domain(self):
        assert get_archetype_for_domains(["warfare", "conquest"]) == "military"
    def test_unknown_domain_uses_default(self):
        assert get_archetype_for_domains(["unknown_domain"]) == "default"
    def test_empty_domains_uses_default(self):
        assert get_archetype_for_domains([]) == "default"


class TestNamePools:
    def test_each_pool_has_40_plus_names(self):
        for archetype, names in CULTURAL_NAME_POOLS.items():
            assert len(names) >= 40, f"Pool '{archetype}' has only {len(names)} names"


class TestSuccession:
    def test_heir_succession(self, leader_civ, leader_world):
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="heir")
        assert new.succession_type == "heir"
        assert new.predecessor_name == "Vaelith"
        assert new.name != "Vaelith"
        assert new.name in leader_world.used_leader_names

    def test_general_succession_effects(self, leader_civ, leader_world):
        old_s, old_m = leader_civ.stability, leader_civ.military
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="general")
        assert new.succession_type == "general"
        assert new.trait in ["aggressive", "bold", "ambitious"]
        assert leader_civ.stability == old_s - 1
        assert leader_civ.military == min(old_m + 1, 10)

    def test_usurper_succession_effects(self, leader_civ, leader_world):
        old_s, old_a = leader_civ.stability, leader_civ.asabiya
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="usurper")
        assert new.succession_type == "usurper"
        assert leader_civ.stability == max(old_s - 3, 1)
        assert leader_civ.asabiya == min(old_a + 0.1, 1.0)

    def test_elected_succession_requires_culture(self, leader_civ, leader_world):
        leader_civ.culture = 4
        leader_civ.tech_era = TechEra.BRONZE
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="elected")
        assert new.succession_type != "elected"

    def test_elected_succession_with_culture(self, leader_civ, leader_world):
        leader_civ.culture = 6
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="elected")
        assert new.succession_type == "elected"
        assert leader_civ.stability >= 5

    def test_elected_succession_with_classical_era(self, leader_civ, leader_world):
        leader_civ.culture = 3
        leader_civ.tech_era = TechEra.CLASSICAL
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="elected")
        assert new.succession_type == "elected"

    def test_name_deduplication(self, leader_civ, leader_world):
        names = set()
        for i in range(100):
            leader_civ.leader.alive = False
            new = generate_successor(leader_civ, leader_world, seed=i)
            assert new.name not in names, f"Duplicate name: {new.name}"
            names.add(new.name)
            leader_civ.leader = new

    def test_heir_inherits_rivalry(self, leader_civ, leader_world):
        leader_civ.leader.rival_leader = "Gorath"
        leader_civ.leader.rival_civ = "Dorrathi Clans"
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="heir")
        assert new.rival_leader == "Gorath"
        assert new.rival_civ == "Dorrathi Clans"

    def test_usurper_generates_coup_event(self, leader_civ, leader_world):
        leader_civ.leader.alive = False
        generate_successor(leader_civ, leader_world, seed=100, force_type="usurper")
        coups = [ne for ne in leader_world.named_events if ne.event_type == "coup"]
        assert len(coups) == 1
        assert "Coup" in coups[0].name

    def test_general_does_not_inherit_rivalry(self, leader_civ, leader_world):
        leader_civ.leader.rival_leader = "Gorath"
        leader_civ.leader.rival_civ = "Dorrathi Clans"
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="general")
        assert new.rival_leader is None
        assert new.rival_civ is None


class TestLegacy:
    def test_no_legacy_short_reign(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 10
        assert apply_leader_legacy(leader_civ, leader_civ.leader, leader_world) is None

    def test_legacy_long_reign_bold(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 0
        event = apply_leader_legacy(leader_civ, leader_civ.leader, leader_world)
        assert event is not None
        assert event.event_type == "legacy"
        conds = [c for c in leader_world.active_conditions if c.condition_type == "military_legacy"]
        assert len(conds) == 1
        assert conds[0].duration == 10
        assert conds[0].severity == 1

    def test_legacy_cautious_leader(self, leader_civ, leader_world):
        leader_civ.leader.trait = "cautious"
        leader_civ.leader.reign_start = 0
        apply_leader_legacy(leader_civ, leader_civ.leader, leader_world)
        assert len([c for c in leader_world.active_conditions if c.condition_type == "stability_legacy"]) == 1

    def test_no_duplicate_legacy(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 0
        leader_world.active_conditions.append(
            ActiveCondition(condition_type="military_legacy", affected_civs=["Kethani Empire"], duration=5, severity=1)
        )
        assert apply_leader_legacy(leader_civ, leader_civ.leader, leader_world) is None


class TestRivalry:
    def test_war_creates_rivalry(self, leader_civ, leader_world):
        update_rivalries(leader_civ, leader_world.civilizations[1], leader_world)
        assert leader_civ.leader.rival_leader == "Gorath"
        assert leader_civ.leader.rival_civ == "Dorrathi Clans"
        assert leader_world.civilizations[1].leader.rival_leader == "Vaelith"
        assert leader_world.civilizations[1].leader.rival_civ == "Kethani Empire"


class TestRivalFall:
    def test_rival_fall_gives_culture_bonus(self, leader_civ, leader_world):
        from chronicler.leaders import check_rival_fall
        other = leader_world.civilizations[1]
        other.leader.rival_leader = "Vaelith"
        other.leader.rival_civ = "Kethani Empire"
        old_c = other.culture
        event = check_rival_fall(leader_civ, "Vaelith", leader_world)
        assert event is not None
        assert other.culture == old_c + 1

    def test_rival_fall_generates_named_event(self, leader_civ, leader_world):
        from chronicler.leaders import check_rival_fall
        other = leader_world.civilizations[1]
        other.leader.rival_leader = "Vaelith"
        other.leader.rival_civ = "Kethani Empire"
        check_rival_fall(leader_civ, "Vaelith", leader_world)
        falls = [ne for ne in leader_world.named_events if ne.event_type == "rival_fall"]
        assert len(falls) == 1
        assert "Vaelith" in falls[0].name

    def test_rival_fall_clears_rivalry(self, leader_civ, leader_world):
        from chronicler.leaders import check_rival_fall
        other = leader_world.civilizations[1]
        other.leader.rival_leader = "Vaelith"
        other.leader.rival_civ = "Kethani Empire"
        check_rival_fall(leader_civ, "Vaelith", leader_world)
        assert other.leader.rival_leader is None
        assert other.leader.rival_civ is None

    def test_no_rival_fall_if_no_rival(self, leader_civ, leader_world):
        from chronicler.leaders import check_rival_fall
        assert check_rival_fall(leader_civ, "Vaelith", leader_world) is None


class TestTraitEvolution:
    def test_no_evolution_short_reign(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 15
        leader_civ.action_counts = {"WAR": 5}
        assert check_trait_evolution(leader_civ, leader_world) is None

    def test_evolution_after_10_turns(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 5
        leader_civ.action_counts = {"WAR": 10, "DEVELOP": 3, "TRADE": 2}
        result = check_trait_evolution(leader_civ, leader_world)
        assert result == "warlike"
        assert leader_civ.leader.secondary_trait == "warlike"

    def test_evolution_develop(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 5
        leader_civ.action_counts = {"DEVELOP": 10, "WAR": 3}
        assert check_trait_evolution(leader_civ, leader_world) == "builder"

    def test_no_double_evolution(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 5
        leader_civ.leader.secondary_trait = "warlike"
        leader_civ.action_counts = {"DEVELOP": 10}
        assert check_trait_evolution(leader_civ, leader_world) is None
