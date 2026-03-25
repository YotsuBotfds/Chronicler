import pytest
from chronicler.models import (
    Civilization, Leader, TechEra, WorldState, Region, ActiveCondition,
    Disposition, Relationship, NamedEvent,
)
from chronicler.leaders import (
    generate_successor, apply_leader_legacy, check_trait_evolution,
    update_rivalries, get_archetype_for_domains, CULTURAL_NAME_POOLS, SUCCESSION_WEIGHTS,
    strip_title, to_roman, _compose_regnal_name, _pick_regnal_name,
)


@pytest.fixture
def leader_civ():
    return Civilization(
        name="Kethani Empire", population=50, military=50, economy=50, culture=60, stability=50,
        tech_era=TechEra.CLASSICAL, treasury=150,
        leader=Leader(name="Vaelith", trait="bold", reign_start=0),
        regions=["Region A"], domains=["maritime", "commerce"], values=["Trade", "Order"],
    )

@pytest.fixture
def leader_world(leader_civ):
    civ2 = Civilization(
        name="Dorrathi Clans", population=50, military=50, economy=50, culture=50, stability=50,
        tech_era=TechEra.IRON, treasury=100,
        leader=Leader(name="Gorath", trait="aggressive", reign_start=0),
        regions=["Region B"], domains=["warfare", "conquest"],
    )
    return WorldState(
        name="Test", seed=42, turn=20,
        regions=[
            Region(name="Region A", terrain="plains", carrying_capacity=80, resources="fertile", controller="Kethani Empire"),
            Region(name="Region B", terrain="mountains", carrying_capacity=50, resources="mineral", controller="Dorrathi Clans"),
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
        # M51: regnal naming metadata
        assert new.throne_name is not None
        assert new.regnal_ordinal >= 0
        assert new.throne_name in leader_civ.regnal_name_counts

    def test_general_succession_effects(self, leader_civ, leader_world):
        old_s, old_m = leader_civ.stability, leader_civ.military
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="general")
        assert new.succession_type == "general"
        assert new.trait in ["aggressive", "bold", "ambitious"]
        assert leader_civ.stability == old_s - 10
        assert leader_civ.military == min(old_m + 10, 100)

    def test_usurper_succession_effects(self, leader_civ, leader_world):
        old_s = leader_civ.stability
        region_a = leader_world.regions[0]
        old_region_asabiya = region_a.asabiya_state.asabiya
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="usurper")
        assert new.succession_type == "usurper"
        assert leader_civ.stability == max(old_s - 30, 1)
        # M55b: asabiya delta applied to regions via D-policy
        assert region_a.asabiya_state.asabiya == pytest.approx(
            min(old_region_asabiya + 0.1, 1.0), abs=1e-4
        )

    def test_elected_succession_requires_culture(self, leader_civ, leader_world):
        leader_civ.culture = 40
        leader_civ.tech_era = TechEra.BRONZE
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="elected")
        assert new.succession_type != "elected"

    def test_elected_succession_with_culture(self, leader_civ, leader_world):
        leader_civ.culture = 60
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="elected")
        assert new.succession_type == "elected"
        assert leader_civ.stability >= 50

    def test_elected_succession_with_classical_era(self, leader_civ, leader_world):
        leader_civ.culture = 30
        leader_civ.tech_era = TechEra.CLASSICAL
        leader_civ.leader.alive = False
        new = generate_successor(leader_civ, leader_world, seed=100, force_type="elected")
        assert new.succession_type == "elected"

    def test_name_deduplication(self, leader_civ, leader_world):
        names = set()
        for i in range(40):
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
        assert conds[0].severity == 10

    def test_legacy_cautious_leader(self, leader_civ, leader_world):
        leader_civ.leader.trait = "cautious"
        leader_civ.leader.reign_start = 0
        apply_leader_legacy(leader_civ, leader_civ.leader, leader_world)
        assert len([c for c in leader_world.active_conditions if c.condition_type == "stability_legacy"]) == 1

    def test_no_duplicate_legacy(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 0
        leader_world.active_conditions.append(
            ActiveCondition(condition_type="military_legacy", affected_civs=["Kethani Empire"], duration=5, severity=10)
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
        assert other.culture == old_c + 10

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
        leader_civ.action_counts = {"war": 5}
        assert check_trait_evolution(leader_civ, leader_world) is None

    def test_evolution_after_10_turns(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 5
        leader_civ.action_counts = {"war": 10, "develop": 3, "trade": 2}
        result = check_trait_evolution(leader_civ, leader_world)
        assert result == "warlike"
        assert leader_civ.leader.secondary_trait == "warlike"

    def test_evolution_develop(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 5
        leader_civ.action_counts = {"develop": 10, "war": 3}
        assert check_trait_evolution(leader_civ, leader_world) == "builder"

    def test_no_double_evolution(self, leader_civ, leader_world):
        leader_civ.leader.reign_start = 5
        leader_civ.leader.secondary_trait = "warlike"
        leader_civ.action_counts = {"develop": 10}
        assert check_trait_evolution(leader_civ, leader_world) is None


class TestRegnalHelpers:
    def test_strip_title_handles_multi_word_title(self):
        assert strip_title("High Priestess Nerissa") == "Nerissa"

    def test_strip_title_leaves_plain_name(self):
        assert strip_title("Nerissa") == "Nerissa"

    def test_strip_title_single_word_title(self):
        assert strip_title("Emperor Thalor") == "Thalor"

    def test_to_roman_small_values(self):
        assert to_roman(1) == "I"
        assert to_roman(2) == "II"
        assert to_roman(3) == "III"
        assert to_roman(4) == "IV"
        assert to_roman(5) == "V"
        assert to_roman(9) == "IX"
        assert to_roman(10) == "X"
        assert to_roman(14) == "XIV"
        assert to_roman(20) == "XX"

    def test_to_roman_zero_returns_empty(self):
        assert to_roman(0) == ""
        assert to_roman(-1) == ""

    def test_compose_regnal_name_without_ordinal(self):
        assert _compose_regnal_name("Emperor", "Kiran", 0) == "Emperor Kiran"

    def test_compose_regnal_name_with_ordinal(self):
        # ordinal=2 means 2nd holder -> display "II", ordinal=4 means 4th holder -> display "IV"
        assert _compose_regnal_name("King", "Thalor", 2) == "King Thalor II"
        assert _compose_regnal_name("Queen", "Nerissa", 4) == "Queen Nerissa IV"


class TestRegnalNameSelection:
    def test_pick_regnal_name_first_ordinal_is_zero(self, leader_civ, leader_world):
        import random
        rng = random.Random(42)
        leader_civ.regnal_name_counts = {}
        title, throne_name, ordinal = _pick_regnal_name(leader_civ, leader_world, rng)
        assert ordinal == 0
        assert throne_name in leader_civ.regnal_name_counts
        assert leader_civ.regnal_name_counts[throne_name] == 1

    def test_pick_regnal_name_reuse_increments(self, leader_civ, leader_world):
        import random
        leader_civ.regnal_name_counts = {"Thalor": 1}
        rng = random.Random(42)
        # Force the pool to only have "Thalor" available
        leader_civ.leader_name_pool = ["Thalor"]
        title, throne_name, ordinal = _pick_regnal_name(leader_civ, leader_world, rng)
        assert throne_name == "Thalor"
        assert ordinal == 2  # second holder → display ordinal "II"
        assert leader_civ.regnal_name_counts["Thalor"] == 2

    def test_pick_regnal_name_does_not_append_to_used_leader_names(self, leader_civ, leader_world):
        import random
        rng = random.Random(42)
        count_before = len(leader_world.used_leader_names)
        _pick_regnal_name(leader_civ, leader_world, rng)
        assert len(leader_world.used_leader_names) == count_before


class TestCustomNamePool:
    def test_picks_from_custom_pool(self, leader_world):
        civ = leader_world.civilizations[0]
        civ.leader_name_pool = ["CustomAlpha", "CustomBeta", "CustomGamma", "CustomDelta", "CustomEpsilon"]
        civ.leader.alive = False
        import random
        rng = random.Random(42)
        from chronicler.leaders import _pick_name
        name = _pick_name(civ, leader_world, rng)
        # Name should be "Title CustomX" format
        base = name.split(" ", 1)[-1] if " " in name else name
        assert base in civ.leader_name_pool

    def test_custom_pool_uses_rng(self, leader_world):
        """Same seed produces same name — deterministic."""
        civ = leader_world.civilizations[0]
        civ.leader_name_pool = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        import random
        from chronicler.leaders import _pick_name
        name1 = _pick_name(civ, leader_world, random.Random(99))
        # Reset used names
        leader_world.used_leader_names = leader_world.used_leader_names[:-1]
        name2 = _pick_name(civ, leader_world, random.Random(99))
        assert name1 == name2

    def test_custom_pool_dedup_against_used_bases(self, leader_world):
        """A name already used (with title) should not be picked from custom pool."""
        civ = leader_world.civilizations[0]
        civ.leader_name_pool = ["UsedName", "FreshName", "AnotherFresh", "MoreFresh", "YetMore"]
        leader_world.used_leader_names.append("Emperor UsedName")
        import random
        from chronicler.leaders import _pick_name
        name = _pick_name(civ, leader_world, random.Random(42))
        base = name.split(" ", 1)[-1] if " " in name else name
        assert base != "UsedName"

    def test_custom_pool_exhausted_falls_back(self, leader_world):
        """When custom pool is exhausted, falls back to cultural pool."""
        civ = leader_world.civilizations[0]
        civ.leader_name_pool = ["OnlyName", "SecondName", "ThirdName", "FourthName", "FifthName"]
        # Mark all custom names as used
        for n in civ.leader_name_pool:
            leader_world.used_leader_names.append(f"Title {n}")
        import random
        from chronicler.leaders import _pick_name
        name = _pick_name(civ, leader_world, random.Random(42))
        base = name.split(" ", 1)[-1] if " " in name else name
        assert base not in civ.leader_name_pool

    def test_custom_pool_adds_to_used_leader_names(self, leader_world):
        civ = leader_world.civilizations[0]
        civ.leader_name_pool = ["TrackMe", "Other", "Another", "More", "Extra"]
        import random
        from chronicler.leaders import _pick_name
        count_before = len(leader_world.used_leader_names)
        _pick_name(civ, leader_world, random.Random(42))
        assert len(leader_world.used_leader_names) == count_before + 1

    def test_deterministic_succession_with_custom_pool(self):
        """Two runs with same seed produce identical successor names."""
        from chronicler.leaders import generate_successor
        from chronicler.world_gen import generate_world

        def make_world():
            world = generate_world(seed=77, num_regions=4, num_civs=2)
            civ = world.civilizations[0]
            civ.leader_name_pool = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon",
                                    "Zeta", "Eta", "Theta", "Iota", "Kappa"]
            world.event_probabilities["leader_death"] = 1.0
            return world

        # Run 1
        world1 = make_world()
        names1 = []
        for i in range(5):
            civ = world1.civilizations[0]
            new_leader = generate_successor(civ, world1, seed=77)
            names1.append(new_leader.name)
            civ.leader = new_leader
            world1.turn += 1

        # Run 2
        world2 = make_world()
        names2 = []
        for i in range(5):
            civ = world2.civilizations[0]
            new_leader = generate_successor(civ, world2, seed=77)
            names2.append(new_leader.name)
            civ.leader = new_leader
            world2.turn += 1

        assert names1 == names2
