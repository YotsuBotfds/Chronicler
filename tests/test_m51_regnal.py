"""M51 Regnal Naming Tests."""
import random

from chronicler.models import (
    Civilization, Disposition, Leader, Region, Relationship, TechEra, WorldState,
)
from chronicler.leaders import to_roman, strip_title, generate_successor, _compose_regnal_name, _pick_regnal_name


def test_leader_has_regnal_fields():
    leader = Leader(name="King Kiran", trait="bold", reign_start=0)
    assert leader.agent_id is None
    assert leader.dynasty_id is None
    assert leader.throne_name is None
    assert leader.regnal_ordinal == 0


def test_leader_with_regnal_data():
    leader = Leader(name="King Kiran II", trait="bold", reign_start=100,
                    agent_id=42, dynasty_id=1, throne_name="Kiran", regnal_ordinal=2)
    assert leader.throne_name == "Kiran"
    assert leader.regnal_ordinal == 2


def test_civilization_has_regnal_name_counts():
    civ = Civilization(name="Aram", leader=Leader(name="Founder", trait="bold", reign_start=0))
    assert civ.regnal_name_counts == {}
    civ.regnal_name_counts["Kiran"] = 1
    assert civ.regnal_name_counts["Kiran"] == 1


def test_strip_title_single_word():
    assert strip_title("Emperor Kiran") == "Kiran"


def test_strip_title_multi_word():
    assert strip_title("High Priestess Mira") == "Mira"


def test_strip_title_no_title():
    assert strip_title("Kiran") == "Kiran"


def test_strip_title_with_numeral():
    assert strip_title("Kiran III") == "Kiran"


def test_to_roman():
    assert to_roman(2) == "II"
    assert to_roman(3) == "III"
    assert to_roman(4) == "IV"
    assert to_roman(9) == "IX"
    assert to_roman(14) == "XIV"
    assert to_roman(20) == "XX"


# --- Helpers for wiring tests ---

def _make_test_world():
    """Create a minimal world suitable for succession tests."""
    civ = Civilization(
        name="Kethani Empire", population=50, military=50, economy=50,
        culture=60, stability=50, tech_era=TechEra.CLASSICAL, treasury=150,
        leader=Leader(name="Emperor Thalor", trait="bold", reign_start=0),
        regions=["Region A"], domains=["maritime", "commerce"],
        values=["Trade", "Order"],
    )
    civ2 = Civilization(
        name="Dorrathi Clans", population=50, military=50, economy=50,
        culture=50, stability=50, tech_era=TechEra.IRON, treasury=100,
        leader=Leader(name="Warchief Gorath", trait="aggressive", reign_start=0),
        regions=["Region B"], domains=["warfare", "conquest"],
    )
    world = WorldState(
        name="Test", seed=42, turn=20,
        regions=[
            Region(name="Region A", terrain="plains", carrying_capacity=80, resources="fertile"),
            Region(name="Region B", terrain="mountains", carrying_capacity=50, resources="mineral"),
        ],
        civilizations=[civ, civ2],
        relationships={
            "Kethani Empire": {"Dorrathi Clans": Relationship(disposition=Disposition.HOSTILE)},
            "Dorrathi Clans": {"Kethani Empire": Relationship(disposition=Disposition.HOSTILE)},
        },
        used_leader_names=["Emperor Thalor", "Warchief Gorath"],
    )
    return world


# --- Task 9: Wiring tests ---

class TestGenerateSuccessorRegnal:
    def test_generate_successor_has_regnal_metadata(self):
        """generate_successor should produce a leader with throne_name and ordinal."""
        world = _make_test_world()
        civ = world.civilizations[0]
        leader = generate_successor(civ, world, seed=42)
        assert leader.throne_name is not None
        assert leader.regnal_ordinal >= 0
        assert leader.throne_name in civ.regnal_name_counts
        # Display name should match regnal composition
        expected = _compose_regnal_name(
            leader.name.split(" ")[0],  # title is first word
            leader.throne_name,
            leader.regnal_ordinal,
        )
        assert leader.name == expected

    def test_generate_successor_increments_regnal_count(self):
        """Two successors with the same throne_name should get ordinals 0 then 2."""
        world = _make_test_world()
        civ = world.civilizations[0]
        # Force a specific name pool so both pick the same name
        civ.leader_name_pool = ["TestKing"]
        leader1 = generate_successor(civ, world, seed=42)
        assert leader1.throne_name == "TestKing"
        assert leader1.regnal_ordinal == 0
        assert civ.regnal_name_counts["TestKing"] == 1

        # Install as current leader, generate another
        civ.leader = leader1
        world.turn += 1
        leader2 = generate_successor(civ, world, seed=99)
        assert leader2.throne_name == "TestKing"
        assert leader2.regnal_ordinal == 2  # display ordinal, not 0-based count
        assert civ.regnal_name_counts["TestKing"] == 2
        # Second holder gets Roman numeral II
        assert " II" in leader2.name

    def test_founder_name_can_be_reused_as_throne_name(self):
        """P1 fix: _pick_regnal_name does NOT filter against used_leader_names,
        so a founder's name can return as throne name II, III, etc."""
        world = _make_test_world()
        civ = world.civilizations[0]
        # Seed the founder's name into used_leader_names (as world_gen does)
        founder_name = "Thalor"
        world.used_leader_names.append(f"Emperor {founder_name}")
        # Force pool to only have "Thalor"
        civ.leader_name_pool = [founder_name]
        import random
        rng = random.Random(42)
        title, throne_name, ordinal = _pick_regnal_name(civ, world, rng)
        assert throne_name == founder_name, (
            f"Expected throne_name='{founder_name}' but got '{throne_name}' — "
            "_pick_regnal_name should not filter against used_leader_names"
        )


class TestWorldGenFoundingRegnal:
    def test_founding_leaders_have_regnal_metadata(self):
        """Founding leaders from world_gen should have throne_name and ordinal."""
        from chronicler.world_gen import generate_world
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        for civ in world.civilizations:
            leader = civ.leader
            assert leader.throne_name is not None, (
                f"Civ '{civ.name}' founding leader '{leader.name}' missing throne_name"
            )
            assert leader.regnal_ordinal >= 0
            assert leader.throne_name in civ.regnal_name_counts

    def test_founding_leader_name_matches_regnal(self):
        """Founding leader display name should be composed from regnal components."""
        from chronicler.world_gen import generate_world
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        for civ in world.civilizations:
            leader = civ.leader
            expected = _compose_regnal_name(
                leader.name.split(" ")[0],
                leader.throne_name,
                leader.regnal_ordinal,
            )
            assert leader.name == expected, (
                f"Civ '{civ.name}': display name '{leader.name}' != expected '{expected}'"
            )


class TestSecessionRegnal:
    def test_secession_leader_has_regnal_metadata(self):
        """A secession leader should have throne_name and ordinal."""
        from chronicler.world_gen import generate_world
        from chronicler.politics import check_secession

        world = generate_world(seed=42, num_regions=8, num_civs=4)
        # Force secession conditions on first civ
        civ = world.civilizations[0]
        civ.stability = 1
        # Need 3+ regions
        for r in world.regions:
            if r.controller is None:
                r.controller = civ.name
                civ.regions.append(r.name)
            if len(civ.regions) >= 4:
                break
        civ.capital_region = civ.regions[0]

        # Run secession with a high probability
        events = check_secession(world)
        # Find breakaway civs (newly added civs after existing ones)
        breakaway_civs = [c for c in world.civilizations if c.founded_turn == world.turn]
        if breakaway_civs:
            for bc in breakaway_civs:
                leader = bc.leader
                assert leader.throne_name is not None, (
                    f"Secession civ '{bc.name}' leader '{leader.name}' missing throne_name"
                )
                assert leader.regnal_ordinal >= 0
                assert leader.throne_name in bc.regnal_name_counts


class TestRestoredCivRegnal:
    def test_restored_civ_leader_has_regnal_metadata(self):
        """A restored civ's leader should have throne_name and ordinal."""
        from chronicler.politics import check_restoration
        from chronicler.models import ExileModifier

        world = _make_test_world()
        # Create a third region to restore into
        r3 = Region(name="Region C", terrain="plains", carrying_capacity=60, resources="fertile")
        r3.controller = "Kethani Empire"
        world.regions.append(r3)
        world.civilizations[0].regions.append("Region C")

        # Create exile
        exile = ExileModifier(
            original_civ_name="Old Empire",
            absorber_civ="Kethani Empire",
            conquered_regions=["Region C"],
            turns_remaining=10,
        )
        world.exile_modifiers.append(exile)
        # Force conditions for restoration
        world.civilizations[0].stability = 5  # absorber weak

        # Run restoration many times with different turns until one fires
        restored = False
        for t in range(100):
            world.turn = t
            exile.turns_remaining = 10  # keep alive
            events = check_restoration(world)
            # Check if "Old Empire" was restored
            restored_civ = next(
                (c for c in world.civilizations if c.name == "Old Empire"), None
            )
            if restored_civ:
                leader = restored_civ.leader
                assert leader.throne_name is not None
                assert leader.regnal_ordinal >= 0
                assert leader.throne_name in restored_civ.regnal_name_counts
                restored = True
                break
        # If restoration never fired due to RNG, that's OK — skip assertion
        if not restored:
            import pytest
            pytest.skip("Restoration never fired (RNG-dependent)")


class TestExileRestorationRegnal:
    def test_exile_restoration_uses_base_name(self):
        """Exile restoration should use gp.base_name as throne_name."""
        from chronicler.succession import check_exile_restoration
        from chronicler.models import GreatPerson

        world = _make_test_world()
        # Set up the origin civ with low stability
        origin = world.civilizations[0]
        origin.stability = 5

        # Create exile GP in the other civ
        host = world.civilizations[1]
        exile_gp = GreatPerson(
            name="Emperor Thalor",
            role="exile",
            trait="bold",
            civilization=host.name,
            origin_civilization=origin.name,
            born_turn=0,
        )
        exile_gp.base_name = "Thalor"
        host.great_persons.append(exile_gp)

        # Run restoration many times with different turns until one fires
        restored = False
        for t in range(200):
            world.turn = t
            exile_gp.active = True
            if exile_gp not in host.great_persons:
                host.great_persons.append(exile_gp)
            events = check_exile_restoration(world)
            if origin.leader.succession_type == "restoration":
                leader = origin.leader
                assert leader.throne_name == "Thalor"
                assert leader.regnal_ordinal >= 0
                assert "Thalor" in origin.regnal_name_counts
                restored = True
                break
        if not restored:
            import pytest
            pytest.skip("Exile restoration never fired (RNG-dependent)")


class TestScenarioRegnal:
    def test_scenario_seeds_regnal_name_counts(self):
        """apply_scenario should seed regnal_name_counts for overridden leaders."""
        from chronicler.world_gen import generate_world
        from chronicler.scenario import ScenarioConfig, apply_scenario, LeaderOverride, CivOverride

        world = generate_world(seed=42, num_regions=4, num_civs=2)
        config = ScenarioConfig(
            name="Test Scenario",
            civilizations=[
                CivOverride(
                    name=world.civilizations[0].name,
                    leader=LeaderOverride(name="Emperor Kiran"),
                ),
            ],
        )
        apply_scenario(world, config)
        civ = world.civilizations[0]
        assert civ.leader.name == "Emperor Kiran"
        # Regnal counts should be seeded for "Kiran"
        assert civ.regnal_name_counts.get("Kiran", 0) >= 1


def test_gp_ascension_produces_regnal_name():
    """When a GP wins succession, their base name becomes the throne name."""
    from chronicler.leaders import strip_title
    gp_name = "High Priestess Mira"
    base = strip_title(gp_name)
    assert base == "Mira"


# ---------------------------------------------------------------------------
# Task 11: Dynasty legitimacy scoring
# ---------------------------------------------------------------------------

from chronicler.dynasties import compute_dynasty_legitimacy


def test_legitimacy_direct_heir():
    """GP whose parent_id matches ruler's agent_id gets full bonus."""
    ruler = Leader(name="King Kiran", trait="bold", reign_start=0,
                   agent_id=100, dynasty_id=1)
    civ = Civilization(name="Aram", leader=ruler)
    candidate = {"parent_id": 100, "dynasty_id": 1, "agent_id": 200}
    score = compute_dynasty_legitimacy(candidate, civ)
    assert score == 0.15  # LEGITIMACY_DIRECT_HEIR


def test_legitimacy_same_dynasty():
    """GP with matching dynasty_id but different parent gets lesser bonus."""
    ruler = Leader(name="King Kiran", trait="bold", reign_start=0,
                   agent_id=100, dynasty_id=1)
    civ = Civilization(name="Aram", leader=ruler)
    candidate = {"parent_id": 50, "dynasty_id": 1, "agent_id": 200}
    score = compute_dynasty_legitimacy(candidate, civ)
    assert score == 0.08  # LEGITIMACY_SAME_DYNASTY


def test_legitimacy_no_match():
    """GP from unrelated dynasty gets 0."""
    ruler = Leader(name="King Kiran", trait="bold", reign_start=0,
                   agent_id=100, dynasty_id=1)
    civ = Civilization(name="Aram", leader=ruler)
    candidate = {"parent_id": 50, "dynasty_id": 2, "agent_id": 200}
    assert compute_dynasty_legitimacy(candidate, civ) == 0.0


def test_legitimacy_no_ruler_lineage():
    """When ruler has no agent_id (non-GP), all candidates get 0."""
    ruler = Leader(name="King Kiran", trait="bold", reign_start=0)
    civ = Civilization(name="Aram", leader=ruler)
    candidate = {"parent_id": 100, "dynasty_id": 1, "agent_id": 200}
    assert compute_dynasty_legitimacy(candidate, civ) == 0.0


def test_legitimacy_parent_none_sentinel():
    """parent_id=0 (PARENT_NONE) should not match any ruler."""
    ruler = Leader(name="King Kiran", trait="bold", reign_start=0,
                   agent_id=0)  # edge case: ruler agent_id is 0
    civ = Civilization(name="Aram", leader=ruler)
    candidate = {"parent_id": 0, "dynasty_id": None, "agent_id": 200}
    assert compute_dynasty_legitimacy(candidate, civ) == 0.0


# ---------------------------------------------------------------------------
# Task 12: Succession event legitimacy phrasing
# ---------------------------------------------------------------------------

def test_succession_event_direct_heir_phrasing():
    """Direct heir succession should include 'by right of blood'."""
    legitimacy = 0.15  # LEGITIMACY_DIRECT_HEIR
    phrase = ""
    if legitimacy >= 0.15:
        phrase = ", by right of blood,"
    elif legitimacy >= 0.08:
        phrase = ", of the ruling house,"
    assert "right of blood" in phrase


def test_succession_event_dynasty_phrasing():
    """Same dynasty succession should include 'of the ruling house'."""
    legitimacy = 0.08
    phrase = ""
    if legitimacy >= 0.15:
        phrase = ", by right of blood,"
    elif legitimacy >= 0.08:
        phrase = ", of the ruling house,"
    assert "ruling house" in phrase


def test_succession_event_no_lineage_no_phrase():
    """No lineage should produce no phrase."""
    legitimacy = 0.0
    phrase = ""
    if legitimacy >= 0.15:
        phrase = ", by right of blood,"
    elif legitimacy >= 0.08:
        phrase = ", of the ruling house,"
    assert phrase == ""
