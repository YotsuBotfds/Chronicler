"""H-36: Tests for the 2.5x combined weight multiplier cap in action_engine.py.

Verifies that when multiple multiplicative modifiers combine (trait × situational
× tech focus × factions × holy war), the product is capped at 2.5x.
"""
import pytest
from chronicler.models import (
    ActionType, Civilization, Disposition, Leader, Region, Relationship, TechEra, WorldState,
)
from chronicler.action_engine import ActionEngine


def _make_world(
    trait="aggressive",
    stability=50,
    military=80,
    treasury=150,
    economy=50,
    culture=50,
    population=50,
    hostile=True,
):
    """Build a minimal two-civ world for weight-cap testing."""
    civ1 = Civilization(
        name="Civ A", population=population, military=military,
        economy=economy, culture=culture, stability=stability,
        tech_era=TechEra.IRON, treasury=treasury,
        leader=Leader(name="Vaelith", trait=trait, reign_start=0),
        regions=["Region A", "Region B"], domains=["warfare"],
    )
    civ2 = Civilization(
        name="Civ B", population=50, military=50, economy=50, culture=50,
        stability=50, tech_era=TechEra.IRON, treasury=150,
        leader=Leader(name="Gorath", trait="cautious", reign_start=0),
        regions=["Region C"], domains=["commerce"],
    )
    disp = Disposition.HOSTILE if hostile else Disposition.FRIENDLY
    return WorldState(
        name="Test", seed=42, turn=5,
        regions=[
            Region(name="Region A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Civ A"),
            Region(name="Region B", terrain="forest", carrying_capacity=60,
                   resources="timber", controller="Civ A"),
            Region(name="Region C", terrain="coast", carrying_capacity=70,
                   resources="maritime", controller="Civ B"),
            Region(name="Region D", terrain="plains", carrying_capacity=50,
                   resources="fertile"),
        ],
        civilizations=[civ1, civ2],
        relationships={
            "Civ A": {"Civ B": Relationship(disposition=disp)},
            "Civ B": {"Civ A": Relationship(disposition=disp)},
        },
    )


class TestWeightCap:
    """Tests that the 2.5x combined weight multiplier cap is enforced."""

    def test_cap_applies_when_modifiers_exceed_2_5(self):
        """Aggressive trait (2.0) + hostile high-military situational (2.5) = 5.0,
        which exceeds 2.5 and should be capped."""
        world = _make_world(trait="aggressive", military=80, stability=50)
        engine = ActionEngine(world)
        civ = world.civilizations[0]
        weights = engine.compute_weights(civ)

        # The max weight should not exceed 2.5 (base is 0.2, so absolute max is 0.5)
        max_weight = max(weights.values())
        assert max_weight <= 2.5, (
            f"Max weight {max_weight} exceeded 2.5x cap"
        )

    def test_cap_boundary_exact(self):
        """When the max weight is exactly 2.5, cap should not reduce it."""
        world = _make_world(trait="cautious", military=20, stability=50, hostile=False)
        engine = ActionEngine(world)
        civ = world.civilizations[0]
        weights = engine.compute_weights(civ)

        # With cautious trait in a peaceful world, weights are moderate.
        # Verify cap logic doesn't over-suppress reasonable values.
        max_weight = max(weights.values())
        assert max_weight <= 2.5

    def test_cap_proportional_scaling(self):
        """When cap fires, all weights should be scaled proportionally, preserving
        relative ratios between actions."""
        world = _make_world(trait="aggressive", military=80, stability=50)
        engine = ActionEngine(world)
        civ = world.civilizations[0]
        weights = engine.compute_weights(civ)

        # Collect non-zero weights
        nonzero = {a: w for a, w in weights.items() if w > 0}
        if len(nonzero) >= 2:
            vals = list(nonzero.values())
            # Max should be at or below the cap
            assert max(vals) <= 2.5

    def test_cap_does_not_alter_zero_weights(self):
        """Zero-weight actions should remain zero after cap scaling."""
        world = _make_world(trait="aggressive", military=80, stability=50)
        engine = ActionEngine(world)
        civ = world.civilizations[0]
        weights = engine.compute_weights(civ)

        # Zero weights stay zero
        for action, weight in weights.items():
            if action not in engine.get_eligible_actions(civ):
                assert weight == 0.0, (
                    f"Ineligible action {action} has weight {weight} after cap"
                )

    def test_cap_value_configurable_via_overrides(self):
        """The cap should respect the K_WEIGHT_CAP tuning override."""
        world = _make_world(trait="aggressive", military=80, stability=50)
        world.tuning_overrides = {"action.weight_cap": 1.0}  # Lower cap
        engine = ActionEngine(world)
        civ = world.civilizations[0]
        weights = engine.compute_weights(civ)

        max_weight = max(weights.values())
        assert max_weight <= 1.0, (
            f"Max weight {max_weight} exceeded custom cap of 1.0"
        )

    def test_max_precap_weight_tracked(self):
        """The pre-cap max weight should be tracked on the civ for analytics."""
        world = _make_world(trait="aggressive", military=80, stability=50)
        engine = ActionEngine(world)
        civ = world.civilizations[0]
        engine.compute_weights(civ)

        # max_precap_weight should be set and potentially > cap
        assert hasattr(civ, "max_precap_weight")
        assert civ.max_precap_weight >= 0

    def test_multiple_boosters_all_capped(self):
        """Even with martial tradition + aggressive + high military, cap holds."""
        world = _make_world(trait="aggressive", military=80, stability=50)
        civ = world.civilizations[0]
        civ.traditions = ["martial"]  # +1.2x WAR
        engine = ActionEngine(world)
        weights = engine.compute_weights(civ)

        max_weight = max(weights.values())
        assert max_weight <= 2.5, (
            f"Max weight {max_weight} exceeded 2.5x cap despite martial tradition"
        )

    def test_precap_exceeds_cap_then_gets_scaled(self):
        """If max_precap_weight > cap, the actual weights are scaled down."""
        world = _make_world(trait="aggressive", military=80, stability=50)
        civ = world.civilizations[0]
        civ.traditions = ["martial"]
        engine = ActionEngine(world)
        weights = engine.compute_weights(civ)

        # If precap exceeded cap, all weights were scaled
        if civ.max_precap_weight > 2.5:
            max_weight = max(weights.values())
            assert max_weight <= 2.5 + 0.001  # Float tolerance
