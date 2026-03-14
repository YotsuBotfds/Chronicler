"""Tests for M16a cultural foundations."""
import pytest
from chronicler.models import Civilization, Region, Relationship, Leader, TechEra, Disposition, WorldState
from chronicler.models import ActiveCondition
from chronicler.culture import (
    VALUE_OPPOSITIONS, apply_value_drift,
    tick_cultural_assimilation, ASSIMILATION_THRESHOLD, RECONQUEST_COOLDOWN,
    tick_prestige,
)


class TestModelFields:
    def test_civilization_has_prestige_field(self):
        civ = Civilization(
            name="Test", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade"], regions=["R1"],
        )
        assert civ.prestige == 0

    def test_region_has_cultural_identity_field(self):
        region = Region(name="R1", terrain="plains", carrying_capacity=5, resources="fertile")
        assert region.cultural_identity is None
        assert region.foreign_control_turns == 0

    def test_relationship_has_disposition_drift_field(self):
        rel = Relationship()
        assert rel.disposition_drift == 0


@pytest.fixture
def drift_world():
    """Two civs with known value relationships."""
    regions = [
        Region(name="R1", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivA"),
        Region(name="R2", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivB"),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LA", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade", "Order"], regions=["R1"],
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LB", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade", "Freedom"], regions=["R2"],
        ),
    ]
    relationships = {
        "CivA": {"CivB": Relationship(disposition=Disposition.NEUTRAL)},
        "CivB": {"CivA": Relationship(disposition=Disposition.NEUTRAL)},
    }
    return WorldState(
        name="test", seed=42, regions=regions,
        civilizations=civs, relationships=relationships,
    )


class TestValueOppositions:
    def test_freedom_opposes_order(self):
        assert VALUE_OPPOSITIONS["Freedom"] == "Order"

    def test_neutral_values_not_in_table(self):
        assert "Strength" not in VALUE_OPPOSITIONS
        assert "Destiny" not in VALUE_OPPOSITIONS


class TestValueDrift:
    def test_shared_value_positive_drift(self, drift_world):
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 0  # shared=1, opposing=1 -> net=0

    def test_pure_shared_values_drift(self, drift_world):
        drift_world.civilizations[1].values = ["Trade", "Order"]
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 4  # shared=2, opposing=0

    def test_drift_upgrades_disposition_at_threshold(self, drift_world):
        drift_world.civilizations[1].values = ["Trade", "Order"]
        drift_world.relationships["CivA"]["CivB"].disposition_drift = 8
        drift_world.relationships["CivB"]["CivA"].disposition_drift = 8
        apply_value_drift(drift_world)
        rel_ab = drift_world.relationships["CivA"]["CivB"]
        assert rel_ab.disposition == Disposition.FRIENDLY
        assert rel_ab.disposition_drift == 0

    def test_drift_downgrades_disposition_at_negative_threshold(self, drift_world):
        drift_world.civilizations[0].values = ["Freedom"]
        drift_world.civilizations[1].values = ["Order"]
        drift_world.relationships["CivA"]["CivB"].disposition_drift = -9
        drift_world.relationships["CivB"]["CivA"].disposition_drift = -9
        apply_value_drift(drift_world)
        rel_ab = drift_world.relationships["CivA"]["CivB"]
        assert rel_ab.disposition == Disposition.SUSPICIOUS
        assert rel_ab.disposition_drift == 0

    def test_empty_values_no_drift(self, drift_world):
        drift_world.civilizations[0].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 0


@pytest.fixture
def assimilation_world():
    regions = [
        Region(
            name="Contested", terrain="plains", carrying_capacity=5,
            resources="fertile", controller="CivB",
            cultural_identity="CivA", foreign_control_turns=0,
        ),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LA", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade"], regions=[],
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LB", trait="cautious", reign_start=0),
            domains=["trade"], values=["Order"], regions=["Contested"],
        ),
    ]
    return WorldState(
        name="test", seed=42, regions=regions, civilizations=civs,
        relationships={"CivA": {"CivB": Relationship()}, "CivB": {"CivA": Relationship()}},
    )


class TestCulturalAssimilation:
    def test_foreign_control_increments(self, assimilation_world):
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].foreign_control_turns == 1

    def test_assimilation_flips_identity_at_threshold(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = ASSIMILATION_THRESHOLD - 1
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].cultural_identity == "CivB"
        assert assimilation_world.regions[0].foreign_control_turns == 0

    def test_assimilation_generates_named_event(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = ASSIMILATION_THRESHOLD - 1
        tick_cultural_assimilation(assimilation_world)
        assert any(
            ne.event_type == "cultural_assimilation"
            for ne in assimilation_world.named_events
        )

    def test_stability_drain_per_mismatched_region(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = RECONQUEST_COOLDOWN
        initial_stability = assimilation_world.civilizations[1].stability
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.civilizations[1].stability == initial_stability - 3

    def test_reconquest_cooldown_exempts_drain(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = 5
        initial_stability = assimilation_world.civilizations[1].stability
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.civilizations[1].stability == initial_stability

    def test_first_control_sets_identity_immediately(self, assimilation_world):
        assimilation_world.regions[0].cultural_identity = None
        assimilation_world.regions[0].controller = "CivB"
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].cultural_identity == "CivB"
        assert assimilation_world.regions[0].foreign_control_turns == 0

    def test_matching_identity_resets_counter(self, assimilation_world):
        assimilation_world.regions[0].controller = "CivA"
        assimilation_world.regions[0].cultural_identity = "CivA"
        assimilation_world.regions[0].foreign_control_turns = 10
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].foreign_control_turns == 0

    def test_reconquest_applies_restless_population(self, assimilation_world):
        assimilation_world.regions[0].cultural_identity = "CivA"
        assimilation_world.regions[0].controller = "CivA"
        assimilation_world.regions[0].foreign_control_turns = 5
        tick_cultural_assimilation(assimilation_world)
        restless = [
            c for c in assimilation_world.active_conditions
            if c.condition_type == "restless_population"
        ]
        assert len(restless) == 1
        assert restless[0].duration == RECONQUEST_COOLDOWN


class TestPrestige:
    def test_prestige_decays(self, drift_world):
        drift_world.civilizations[0].prestige = 10
        tick_prestige(drift_world)
        assert drift_world.civilizations[0].prestige == 9

    def test_prestige_minimum_zero(self, drift_world):
        drift_world.civilizations[0].prestige = 0
        tick_prestige(drift_world)
        assert drift_world.civilizations[0].prestige == 0

    def test_prestige_trade_income_bonus(self, drift_world):
        drift_world.civilizations[0].prestige = 11  # after decay: 10 -> bonus = 2
        initial_treasury = drift_world.civilizations[0].treasury
        tick_prestige(drift_world)
        assert drift_world.civilizations[0].treasury == initial_treasury + 2


class TestCulturalWorksEnhancement:
    def test_cultural_work_boosts_prestige(self, drift_world):
        drift_world.civilizations[0].culture = 80
        initial_prestige = drift_world.civilizations[0].prestige
        from chronicler.simulation import phase_cultural_milestones
        phase_cultural_milestones(drift_world)
        assert drift_world.civilizations[0].prestige == initial_prestige + 2

    def test_cultural_work_boosts_asabiya(self, drift_world):
        drift_world.civilizations[0].culture = 80
        initial_asabiya = drift_world.civilizations[0].asabiya
        from chronicler.simulation import phase_cultural_milestones
        phase_cultural_milestones(drift_world)
        assert drift_world.civilizations[0].asabiya == pytest.approx(initial_asabiya + 0.05)


class TestWorldGenCulture:
    def test_controlled_regions_get_cultural_identity(self):
        from chronicler.world_gen import generate_world
        world = generate_world(seed=42, num_civs=4)
        for region in world.regions:
            if region.controller is not None:
                assert region.cultural_identity == region.controller

    def test_uncontrolled_regions_have_no_identity(self):
        from chronicler.world_gen import generate_world
        world = generate_world(seed=42, num_civs=4)
        for region in world.regions:
            if region.controller is None:
                assert region.cultural_identity is None


class TestM16aPhaseIntegration:
    def test_prestige_runs_in_phase_production(self, drift_world):
        drift_world.civilizations[0].prestige = 10
        from chronicler.simulation import phase_production
        phase_production(drift_world)
        assert drift_world.civilizations[0].prestige == 9

    def test_value_drift_runs_in_consequences(self, drift_world):
        drift_world.civilizations[0].values = ["Trade", "Order"]
        drift_world.civilizations[1].values = ["Trade", "Order"]
        from chronicler.simulation import phase_consequences
        phase_consequences(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 4


from chronicler.models import Movement
from chronicler.movements import SCHISM_DIVERGENCE_THRESHOLD


class TestMovementDispositionEffects:
    def test_co_adopters_get_positive_drift(self, drift_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": 1},
        )
        drift_world.movements.append(m)
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 5

    def test_schism_co_adopters_get_negative_drift(self, drift_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": SCHISM_DIVERGENCE_THRESHOLD},
        )
        drift_world.movements.append(m)
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == -5

    def test_non_adopter_no_effect(self, drift_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0},
        )
        drift_world.movements.append(m)
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 0

    def test_multiple_movements_stack(self, drift_world):
        m1 = Movement(id="movement_0", origin_civ="CivA", origin_turn=0,
                       value_affinity="Trade", adherents={"CivA": 0, "CivB": 0})
        m2 = Movement(id="movement_1", origin_civ="CivA", origin_turn=0,
                       value_affinity="Order", adherents={"CivA": 0, "CivB": 0})
        drift_world.movements.extend([m1, m2])
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 10
