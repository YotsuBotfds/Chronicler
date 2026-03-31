"""Tests verifying that get_severity_multiplier is applied at negative stat drain sites."""
import pytest

from chronicler.models import (
    Civilization, Disposition, Event, Leader, Region,
    Relationship, TechEra, WorldState,
)
from chronicler.emergence import get_severity_multiplier
from chronicler.utils import clamp, STAT_FLOOR


@pytest.fixture
def stressed_world(make_world):
    """Create a world where Civ0 is highly stressed (high severity multiplier)."""
    world = make_world(num_civs=2)

    # Make Civ0 highly stressed: active wars, low stability, 3+ regions
    civ0 = world.civilizations[0]
    civ0.stability = 15
    # Add extra regions so civ qualifies for secession stress (3+ regions, stability < 20)
    for i in range(3):
        rname = f"extra_region_{i}"
        world.regions.append(Region(
            name=rname, terrain="plains",
            carrying_capacity=60, resources="fertile",
            controller=civ0.name,
        ))
        civ0.regions.append(rname)

    # Add active war to boost stress
    world.active_wars.append((civ0.name, world.civilizations[1].name))

    # Force decline turns for twilight stress
    civ0.decline_turns = 5

    # Compute and store stress for all civs (required by get_severity_multiplier)
    from chronicler.emergence import compute_all_stress
    compute_all_stress(world)
    assert civ0.civ_stress > 0, f"Civ0 should have nonzero stress, got {civ0.civ_stress}"
    mult = get_severity_multiplier(civ0, world)
    assert mult > 1.0, f"Expected mult > 1.0, got {mult}"

    return world


class TestSeverityAtEmbargoSite:
    """Verify severity multiplier is applied in the EMBARGO action handler."""

    def test_embargo_stability_drain_uses_severity(self, stressed_world):
        """Embargo stability drain on target should scale with severity."""
        world = stressed_world
        target = world.civilizations[0]  # The stressed civ
        target.stability = 50  # Reset to known value

        mult = get_severity_multiplier(target, world)
        expected_drain = int(5 * mult)  # embargo_damage = 5 (non-banking)

        # Call the embargo handler
        from chronicler.action_engine import _resolve_embargo
        sponsor = world.civilizations[1]
        # Ensure sponsor has hostile relationship to target
        world.relationships[sponsor.name][target.name].disposition = Disposition.HOSTILE

        _resolve_embargo(sponsor, world)

        # Target stability should have dropped by severity-scaled amount
        assert target.stability == clamp(50 - expected_drain, STAT_FLOOR["stability"], 100)


class TestSeverityAtWarSite:
    """Verify severity multiplier is applied in war resolution stability drains."""

    def test_war_defender_stability_drain_uses_severity(self, stressed_world):
        """When attacker wins, defender stability drain should scale with severity."""
        world = stressed_world
        attacker = world.civilizations[1]
        defender = world.civilizations[0]  # Stressed civ

        # Make attacker overwhelmingly strong for a decisive attacker_wins
        attacker.military = 100
        defender.military = 10
        defender.stability = 50

        mult = get_severity_multiplier(defender, world)
        expected_max_drain = int(10 * mult)

        from chronicler.action_engine import resolve_war
        result = resolve_war(attacker, defender, world, seed=42)

        if result.outcome == "attacker_wins":
            # Defender stability should have dropped by severity-scaled 10
            assert defender.stability == clamp(50 - expected_max_drain, STAT_FLOOR["stability"], 100)


class TestSeverityAtLeaderSuccession:
    """Verify severity multiplier is applied in leader succession drains."""

    def test_usurper_succession_uses_severity(self, stressed_world):
        """Usurper succession stability drain should scale with severity."""
        world = stressed_world
        civ = world.civilizations[0]
        civ.stability = 80  # High enough to see the drain clearly

        mult = get_severity_multiplier(civ, world)
        expected_drain = int(30 * mult)

        from chronicler.leaders import generate_successor
        generate_successor(civ, world, seed=42, force_type="usurper")

        assert civ.stability == clamp(80 - expected_drain, STAT_FLOOR["stability"], 100)

    def test_general_succession_uses_severity(self, stressed_world):
        """General succession stability drain should scale with severity."""
        world = stressed_world
        civ = world.civilizations[0]
        civ.stability = 80

        mult = get_severity_multiplier(civ, world)
        expected_drain = int(10 * mult)

        from chronicler.leaders import generate_successor
        generate_successor(civ, world, seed=42, force_type="general")

        assert civ.stability == clamp(80 - expected_drain, STAT_FLOOR["stability"], 100)


class TestSeverityAtExilePretender:
    """Verify severity multiplier is applied in exile pretender stability drain."""

    def test_exile_pretender_drain_uses_severity(self, stressed_world):
        """Exile pretender stability drain on origin civ should scale with severity."""
        from chronicler.models import GreatPerson
        from chronicler.succession import apply_exile_pretender_drain

        world = stressed_world
        origin = world.civilizations[0]  # Stressed civ
        host = world.civilizations[1]
        origin.stability = 50

        # Create an exile great person in the host civ pointing back to origin
        exile = GreatPerson(
            name="Exiled Leader",
            role="exile",
            trait="cautious",
            civilization=host.name,
            origin_civilization=origin.name,
            born_turn=0,
        )
        host.great_persons.append(exile)

        mult = get_severity_multiplier(origin, world)
        expected_drain = int(2 * mult)

        apply_exile_pretender_drain(world)

        assert origin.stability == max(50 - expected_drain, 0)


class TestSeverityAtPlagueSite:
    """M-AF1 #9: plague stability drain must scale with severity."""

    def test_plague_stability_uses_severity_multiplier(self, make_world):
        """Plague stability drain should be raw_drain * severity multiplier."""
        world = make_world(num_civs=2)
        civ = world.civilizations[0]
        civ.stability = 80
        civ.civ_stress = 15

        mult = get_severity_multiplier(civ, world)
        assert mult > 1.0, f"Test setup: severity multiplier should be > 1.0, got {mult}"

        raw_drain = 3  # default K_PLAGUE_STABILITY
        pre_stability = civ.stability

        # Force plague to fire with probability 1.0
        world.event_probabilities = {"plague": 1.0}

        from chronicler.simulation import phase_environment
        phase_environment(world, seed=42, acc=None)

        # Verify plague actually fired (stability should have decreased)
        assert civ.stability < pre_stability, "Plague event did not fire"

        actual_drain = pre_stability - civ.stability
        expected_min_drain = int(raw_drain * mult)
        assert actual_drain >= expected_min_drain, \
            f"Plague drain should be >= {expected_min_drain} (raw {raw_drain} * mult {mult:.2f}), got {actual_drain}"


class TestSeverityAtWarBankruptcy:
    """M-AF1 #9: war bankruptcy stability drain must scale with severity."""

    def test_war_bankruptcy_stability_uses_severity_multiplier(self, make_world):
        """War bankruptcy stability drain should be raw_drain * severity multiplier."""
        world = make_world(num_civs=2)
        civ = world.civilizations[0]
        other = world.civilizations[1]
        civ.stability = 80
        civ.treasury = 2  # Will go to -1 after -3 war cost -> triggers bankruptcy drain
        civ.civ_stress = 20  # High stress for strong multiplier
        world.active_wars = [(civ.name, other.name)]

        mult = get_severity_multiplier(civ, world)
        assert mult > 1.0, f"Test setup: severity multiplier should be > 1.0, got {mult}"

        raw_drain = 2  # default K_WAR_COST_STABILITY
        expected_drain = int(raw_drain * mult)
        assert expected_drain > raw_drain, \
            f"Test setup: int({raw_drain} * {mult}) must exceed {raw_drain}"

        pre_stability = civ.stability

        from chronicler.simulation import apply_automatic_effects
        apply_automatic_effects(world)

        actual_drain = pre_stability - civ.stability
        assert actual_drain >= expected_drain, \
            f"War bankruptcy drain should be >= {expected_drain} (raw {raw_drain} * mult {mult:.2f}), got {actual_drain}"

    def test_war_bankruptcy_stability_direct_mode(self, make_world):
        """War bankruptcy drain scales with severity in direct (non-acc) mode."""
        world = make_world(num_civs=2)
        civ = world.civilizations[0]
        other = world.civilizations[1]
        civ.stability = 80
        civ.treasury = 2
        civ.civ_stress = 20
        world.active_wars = [(civ.name, other.name)]

        mult = get_severity_multiplier(civ, world)
        raw_drain = 2
        expected_drain = int(raw_drain * mult)

        pre_stability = civ.stability

        from chronicler.simulation import apply_automatic_effects
        apply_automatic_effects(world, acc=None)

        actual_drain = pre_stability - civ.stability
        assert actual_drain >= expected_drain, \
            f"Direct-mode war bankruptcy drain should be >= {expected_drain}, got {actual_drain}"


class TestSeverityMultiplierBasics:
    """Basic sanity checks for the severity multiplier itself."""

    def test_zero_stress_returns_1(self, make_world):
        """A civ with zero stress should get multiplier 1.0."""
        world = make_world(num_civs=1)
        civ = world.civilizations[0]
        civ.civ_stress = 0
        assert get_severity_multiplier(civ, world) == pytest.approx(1.0)

    def test_max_stress_returns_capped(self, make_world):
        """A civ with max stress (20) should get multiplier capped at 2.0."""
        world = make_world(num_civs=1)
        civ = world.civilizations[0]
        civ.civ_stress = 20
        mult = get_severity_multiplier(civ, world)
        assert mult <= 2.0
        assert mult > 1.0
