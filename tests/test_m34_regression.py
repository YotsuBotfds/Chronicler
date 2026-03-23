"""M34 Tier 2: Behavioral regression — multi-seed validation."""
import pytest
from chronicler.models import ResourceType, EMPTY_SLOT


def _make_world(seed: int, turns: int = 50):
    """Create and run a world for the given seed."""
    from chronicler.world_gen import generate_world
    from chronicler.simulation import run_turn
    from chronicler.models import ActionType

    world = generate_world(seed=seed, num_civs=3)

    def _stub_selector(civ, w):
        return ActionType.DEVELOP

    def _stub_narrator(w, events):
        return ""

    for i in range(turns):
        run_turn(world, action_selector=_stub_selector, narrator=_stub_narrator, seed=seed + i)

    return world


class TestResourceDistribution:
    """Validate resource assignment across seeds."""

    def test_all_resource_types_appear(self):
        """All 8 resource types should appear across 20 seeds."""
        seen = set()
        for seed in range(20):
            world = _make_world(seed, turns=1)
            for r in world.regions:
                for rtype in r.resource_types:
                    if rtype != EMPTY_SLOT:
                        seen.add(rtype)
        assert len(seen) == 8, f"Only {len(seen)} of 8 resource types appeared: {seen}"

    def test_slot1_never_empty(self):
        """Every region in every seed has slot 1 filled."""
        for seed in range(20):
            world = _make_world(seed, turns=1)
            for r in world.regions:
                assert r.resource_types[0] != EMPTY_SLOT, \
                    f"Seed {seed}: {r.name} has empty slot 1"

    def test_terrain_primary_correct(self):
        """Spot-check that terrain→primary mapping is honored."""
        from chronicler.resources import TERRAIN_PRIMARY
        for seed in range(10):
            world = _make_world(seed, turns=1)
            for r in world.regions:
                expected = TERRAIN_PRIMARY.get(r.terrain)
                if expected is not None:
                    assert r.resource_types[0] == expected, \
                        f"Seed {seed}: {r.name} ({r.terrain}) has {r.resource_types[0]}, expected {expected}"


class TestSeasonalBehavior:
    """Validate seasonal yield variation."""

    def test_grain_yield_varies_across_seasons(self):
        """Grain yield should vary across a 12-turn cycle."""
        # Use legacy oracle for formula-level assertion (survives production helper deletion)
        from tests.legacy_ecology_oracle import compute_resource_yields as oracle_yields
        from tests.legacy_ecology_oracle import EMPTY_SLOT as ORACLE_EMPTY
        yields_by_season = []
        for turn in range(12):
            season_id = (turn % 12) // 3
            y, _ = oracle_yields(
                resource_types=[0, ORACLE_EMPTY, ORACLE_EMPTY],  # GRAIN=0
                resource_base_yields=[1.0, 0.0, 0.0],
                resource_reserves=[1.0, 1.0, 1.0],
                resource_suspensions={},
                soil=0.8, water=0.7, forest_cover=0.2,
                carrying_capacity=50, capacity_modifier=1.0, population=0,
                season_id=season_id, climate_phase="temperate", worker_count=0,
            )
            yields_by_season.append(y[0])
        # Should have at least 3 distinct yield levels (Spring, Summer, Autumn, Winter have different mods)
        unique_yields = set(round(y, 4) for y in yields_by_season)
        assert len(unique_yields) >= 3, f"Expected seasonal variation, got {unique_yields}"


class TestMineralDepletion:
    """Validate mineral depletion mechanics."""

    def test_mineral_depletes_over_time(self):
        """Mineral reserves should decrease when workers are present."""
        # Use legacy oracle for formula-level assertion (survives production helper deletion)
        from tests.legacy_ecology_oracle import compute_resource_yields as oracle_yields
        from tests.legacy_ecology_oracle import EMPTY_SLOT as ORACLE_EMPTY
        reserves = [1.0, 1.0, 1.0]
        for _ in range(150):
            _, reserves = oracle_yields(
                resource_types=[5, ORACLE_EMPTY, ORACLE_EMPTY],  # ORE=5
                resource_base_yields=[1.0, 0.0, 0.0],
                resource_reserves=reserves,
                resource_suspensions={},
                soil=0.4, water=0.8, forest_cover=0.3,
                carrying_capacity=60, capacity_modifier=1.0, population=100,
                season_id=0, climate_phase="temperate", worker_count=20,
            )
        # After 150 turns at 20 workers, reserves should be significantly depleted
        assert reserves[0] < 0.5, \
            f"Expected depletion, got reserves={reserves[0]}"
