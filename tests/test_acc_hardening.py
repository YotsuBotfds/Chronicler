"""Regression tests for Lane A: Hybrid Accumulator Hardening.

Verifies that era bonuses, injected events, and restoration stat changes
route through the StatAccumulator as keep mutations when acc is provided.
"""
import pytest
from chronicler.accumulator import StatAccumulator
from chronicler.models import (
    Civilization,
    ExileModifier,
    GreatPerson,
    Leader,
    Region,
    TechEra,
    WorldState,
)
from chronicler.tech import apply_era_bonus, remove_era_bonus, ERA_BONUSES
from chronicler.utils import civ_index

# simulation.py transitively imports culture.py which needs ffi_constants (Rust-built).
# Guard tests that need simulation imports so they skip gracefully in worktrees
# without compiled FFI modules.
try:
    from chronicler.simulation import apply_injected_event, run_turn
    _HAS_SIMULATION = True
except ImportError:
    _HAS_SIMULATION = False

_skip_no_sim = pytest.mark.skipif(not _HAS_SIMULATION, reason="ffi_constants not available")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_civ(name="TestCiv", **overrides):
    defaults = dict(
        name=name,
        population=50, military=30, economy=40, culture=30, stability=50,
        tech_era=TechEra.IRON, treasury=100,
        leader=Leader(name=f"Leader of {name}", trait="cautious", reign_start=0),
        regions=[f"{name}_region"],
        asabiya=0.5,
    )
    defaults.update(overrides)
    return Civilization(**defaults)


def _make_world(*civs):
    regions = []
    for c in civs:
        for rname in c.regions:
            regions.append(Region(
                name=rname, terrain="plains",
                carrying_capacity=60, resources="fertile",
                controller=c.name,
            ))
    rels = {}
    names = [c.name for c in civs]
    for a in names:
        rels[a] = {}
        for b in names:
            if a != b:
                from chronicler.models import Relationship
                rels[a][b] = Relationship()
    return WorldState(
        name="TestWorld", seed=42, turn=5,
        regions=regions, civilizations=list(civs),
        relationships=rels,
    )


# ---------------------------------------------------------------------------
# A1: Era bonus routing through accumulator
# ---------------------------------------------------------------------------

class TestEraBonusAccRouting:
    """apply_era_bonus and remove_era_bonus route through acc when provided."""

    def test_apply_era_bonus_routes_through_acc(self):
        civ = _make_civ(military=30, economy=40)
        world = _make_world(civ)
        acc = StatAccumulator()
        idx = civ_index(world, civ.name)

        old_military = civ.military
        old_economy = civ.economy
        apply_era_bonus(civ, TechEra.INDUSTRIAL, acc=acc, civ_idx=idx)

        # Stats should NOT change yet (deferred in acc)
        assert civ.military == old_military
        assert civ.economy == old_economy

        # Apply keep mutations
        acc.apply_keep(world)

        # Now stats should reflect INDUSTRIAL bonuses: economy +20, military +20
        assert civ.military == old_military + 20
        assert civ.economy == old_economy + 20

    def test_remove_era_bonus_routes_through_acc(self):
        civ = _make_civ(military=50, economy=60)
        world = _make_world(civ)
        acc = StatAccumulator()
        idx = civ_index(world, civ.name)

        old_military = civ.military
        old_economy = civ.economy
        remove_era_bonus(civ, TechEra.INDUSTRIAL, acc=acc, civ_idx=idx)

        # Stats should NOT change yet
        assert civ.military == old_military
        assert civ.economy == old_economy

        acc.apply_keep(world)

        # INDUSTRIAL bonuses reversed: economy -20, military -20
        assert civ.military == old_military - 20
        assert civ.economy == old_economy - 20

    def test_apply_era_bonus_all_changes_are_keep_category(self):
        civ = _make_civ(military=30, economy=40, culture=30)
        world = _make_world(civ)
        acc = StatAccumulator()
        idx = civ_index(world, civ.name)

        apply_era_bonus(civ, TechEra.RENAISSANCE, acc=acc, civ_idx=idx)

        # All changes should be "keep"
        for change in acc._changes:
            assert change.category == "keep", f"Expected 'keep', got '{change.category}' for {change.stat}"

    def test_apply_era_bonus_fallback_without_acc(self):
        """When acc is None, direct mutation still works (backward compat)."""
        civ = _make_civ(military=30)
        old_military = civ.military
        apply_era_bonus(civ, TechEra.BRONZE)
        # BRONZE gives military +10
        assert civ.military == old_military + 10

    def test_remove_era_bonus_fallback_without_acc(self):
        """When acc is None, direct mutation still works (backward compat)."""
        civ = _make_civ(economy=60)
        old_economy = civ.economy
        remove_era_bonus(civ, TechEra.IRON)
        # IRON gives economy +10, so removing = -10
        assert civ.economy == old_economy - 10

    def test_tech_advancement_routes_era_bonus_through_acc(self):
        """check_tech_advancement passes acc to apply_era_bonus."""
        from chronicler.tech import check_tech_advancement
        from chronicler.models import Resource, ResourceType, EMPTY_SLOT

        civ = _make_civ(
            military=30, economy=40, culture=40, treasury=150,
            tech_era=TechEra.TRIBAL, regions=["RegA"],
        )
        world = WorldState(
            name="Test", seed=42, turn=5,
            regions=[Region(
                name="RegA", terrain="plains",
                carrying_capacity=80, resources="fertile",
                controller="TestCiv",
                specialized_resources=[Resource.IRON, Resource.TIMBER],
                resource_types=[ResourceType.ORE, ResourceType.TIMBER, EMPTY_SLOT],
            )],
            civilizations=[civ],
        )
        acc = StatAccumulator()

        old_military = civ.military
        event = check_tech_advancement(civ, world, acc=acc)
        assert event is not None
        assert civ.tech_era == TechEra.BRONZE

        # Before apply_keep, the era bonus hasn't been applied to civ directly
        # (treasury cost is also deferred)
        # After apply_keep, both treasury cost and era bonus take effect
        acc.apply_keep(world)

        # BRONZE: military +10
        assert civ.military == old_military + 10


# ---------------------------------------------------------------------------
# A2: Injected event routing through accumulator
# ---------------------------------------------------------------------------

class TestInjectedEventAccRouting:
    """apply_injected_event routes mutations through acc when provided."""

    @_skip_no_sim
    def test_drought_injection_routes_through_acc(self):
        civ = _make_civ(stability=50, economy=60)
        world = _make_world(civ)
        acc = StatAccumulator()

        old_stability = civ.stability
        old_economy = civ.economy

        events = apply_injected_event("drought", "TestCiv", world, acc=acc)
        assert len(events) > 0

        # Stats should NOT change yet (routed through acc)
        assert civ.stability == old_stability
        assert civ.economy == old_economy

        # Verify changes are in the accumulator as signal category
        signal_changes = [c for c in acc._changes if c.category == "signal"]
        assert len(signal_changes) >= 2  # stability + economy

    @_skip_no_sim
    def test_plague_injection_routes_stability_through_acc(self):
        civ = _make_civ(stability=50, population=100, regions=["TestCiv_region"])
        world = _make_world(civ)
        # Set region population for plague pop_loss
        for r in world.regions:
            if r.controller == civ.name:
                r.population = 100
        acc = StatAccumulator()

        old_stability = civ.stability
        events = apply_injected_event("plague", "TestCiv", world, acc=acc)
        assert len(events) > 0

        # Stability should NOT change yet
        assert civ.stability == old_stability

        signal_changes = [c for c in acc._changes
                          if c.category == "signal" and c.stat == "stability"]
        assert len(signal_changes) >= 1

    @_skip_no_sim
    def test_injected_event_fallback_without_acc(self):
        """When acc is None, direct mutation still works."""
        civ = _make_civ(stability=50, economy=60)
        world = _make_world(civ)

        events = apply_injected_event("drought", "TestCiv", world, acc=None)
        assert len(events) > 0
        # Direct mutation should have happened
        assert civ.stability < 50 or civ.economy < 60


# ---------------------------------------------------------------------------
# A3: Restoration routing through accumulator
# ---------------------------------------------------------------------------

class TestRestorationAccRouting:
    """check_restoration and check_exile_restoration route through acc."""

    def test_exile_restoration_stability_routes_through_acc(self):
        """check_exile_restoration routes +15 stability through acc as keep."""
        from chronicler.succession import check_exile_restoration

        origin = _make_civ(name="Origin", stability=15, regions=["Origin_region"])
        host = _make_civ(name="Host", stability=50, regions=["Host_region"])

        world = _make_world(origin, host)
        world.turn = 10

        # Run with many seeds to find one that triggers
        triggered = False
        for seed_offset in range(200):
            world.seed = seed_offset
            origin.stability = 15  # keep below threshold
            origin.leader = Leader(name="OldKing", trait="cautious", reign_start=0, alive=True)
            host.great_persons = [GreatPerson(
                name="ExiledLeader",
                role="exile",
                trait="bold",
                born_turn=1,
                civilization="Host",
                origin_civilization="Origin",
                agent_id=None,
                active=True,
                recognized_by=["Host"],
            )]
            acc = StatAccumulator()
            events = check_exile_restoration(world, acc=acc)
            if events:
                triggered = True
                # Verify the +15 stability was routed through acc as keep
                keep_changes = [c for c in acc._changes
                                if c.category == "keep" and c.stat == "stability"]
                assert len(keep_changes) >= 1
                assert any(c.delta == 15 for c in keep_changes)
                break

        assert triggered, "Expected exile restoration to trigger in 200 seed attempts"

    def test_restoration_dead_civ_revival_routes_through_acc(self):
        """check_restoration routes stat resets through acc without doubling population."""
        from chronicler.politics import check_restoration

        absorber = _make_civ(
            name="Absorber", stability=10,
            regions=["ConqueredLand", "AbsorberHome"],
            military=30, economy=40,
        )
        # Dead civ (no regions)
        dead_civ = _make_civ(
            name="DeadCiv", stability=0, military=0, economy=0, culture=0,
            population=0, treasury=0, regions=[],
        )

        world = _make_world(absorber, dead_civ)
        # Add the conquered land region
        conquered_region = Region(
            name="ConqueredLand", terrain="plains",
            carrying_capacity=60, resources="fertile",
            controller="Absorber",
            population=30,
        )
        # Replace regions to include the conquered land properly
        world.regions = [
            conquered_region,
            Region(name="AbsorberHome", terrain="plains",
                   carrying_capacity=60, resources="fertile",
                   controller="Absorber"),
        ]

        world.exile_modifiers = [ExileModifier(
            original_civ_name="DeadCiv",
            absorber_civ="Absorber",
            conquered_regions=["ConqueredLand"],
            turns_remaining=5,
            recognized_by=["SomeCiv"],
        )]
        world.turn = 10

        # Try many seeds to find one that triggers restoration
        triggered = False
        for seed_offset in range(500):
            world.seed = seed_offset
            absorber.stability = 10  # low enough
            absorber.regions = ["ConqueredLand", "AbsorberHome"]
            dead_civ.regions = []
            dead_civ.population = 0
            dead_civ.military = 0
            dead_civ.economy = 0
            dead_civ.culture = 0
            dead_civ.stability = 0
            dead_civ.treasury = 0
            world.exile_modifiers = [ExileModifier(
                original_civ_name="DeadCiv",
                absorber_civ="Absorber",
                conquered_regions=["ConqueredLand"],
                turns_remaining=5,
                recognized_by=["SomeCiv"],
            )]
            conquered_region.controller = "Absorber"

            acc = StatAccumulator()
            events = check_restoration(world, acc=acc)
            if events:
                triggered = True
                # Verify stat resets were routed through acc as keep
                keep_changes = [c for c in acc._changes if c.category == "keep"]
                stat_names = {c.stat for c in keep_changes}
                # Should have deltas for the stats being reset
                assert "stability" in stat_names or "military" in stat_names or "economy" in stat_names, \
                    f"Expected keep mutations for stat resets, got stats: {stat_names}"
                # Population is recomputed via sync_civ_population(), not keep.
                assert "population" not in stat_names

                # Applying keep should not double the restored population.
                acc.apply_keep(world)
                assert dead_civ.population == 30
                break

        assert triggered, "Expected restoration to trigger in 500 seed attempts"


class TestRunTurnPendingInjections:
    """Verify that pending_injections parameter is accepted by run_turn."""

    @_skip_no_sim
    def test_run_turn_accepts_pending_injections_param(self):
        """Verify run_turn signature includes pending_injections."""
        import inspect
        sig = inspect.signature(run_turn)
        assert "pending_injections" in sig.parameters
        # Default should be None
        assert sig.parameters["pending_injections"].default is None
