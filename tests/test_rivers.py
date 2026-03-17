import pytest
from chronicler.models import River, WorldState, EMPTY_SLOT, ResourceType
from chronicler.tuning import (
    K_RIVER_WATER_BONUS, K_RIVER_CAPACITY_MULTIPLIER,
    K_DEFORESTATION_THRESHOLD, K_DEFORESTATION_WATER_LOSS,
    KNOWN_OVERRIDES,
)
from chronicler.scenario import ScenarioConfig, apply_scenario
from chronicler.world_gen import generate_world


class TestRiverModel:
    def test_river_basic(self):
        r = River(name="Amber River", path=["Greenfields", "Marshfen", "Coasthaven"])
        assert r.name == "Amber River"
        assert r.path == ["Greenfields", "Marshfen", "Coasthaven"]

    def test_river_path_must_have_at_least_two(self):
        with pytest.raises(Exception):
            River(name="Creek", path=["Solo"])

    def test_world_state_has_rivers(self):
        ws = WorldState(name="Test", seed=42)
        assert ws.rivers == []


class TestRiverConstants:
    def test_river_constants_exist(self):
        assert K_RIVER_WATER_BONUS == "ecology.river_water_bonus"
        assert K_RIVER_CAPACITY_MULTIPLIER == "ecology.river_capacity_multiplier"
        assert K_DEFORESTATION_THRESHOLD == "ecology.deforestation_threshold"
        assert K_DEFORESTATION_WATER_LOSS == "ecology.deforestation_water_loss"

    def test_river_constants_in_known_overrides(self):
        assert K_RIVER_WATER_BONUS in KNOWN_OVERRIDES
        assert K_RIVER_CAPACITY_MULTIPLIER in KNOWN_OVERRIDES
        assert K_DEFORESTATION_THRESHOLD in KNOWN_OVERRIDES
        assert K_DEFORESTATION_WATER_LOSS in KNOWN_OVERRIDES


class TestScenarioRiverConfig:
    def test_config_accepts_rivers(self):
        config = ScenarioConfig(
            name="River Test",
            rivers=[{"name": "Amber River", "path": ["R1", "R2", "R3"]}],
        )
        assert len(config.rivers) == 1
        assert config.rivers[0].name == "Amber River"

    def test_config_default_no_rivers(self):
        config = ScenarioConfig(name="No Rivers")
        assert config.rivers == []


class TestRiverValidation:
    def _make_world_and_config(self, rivers):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        config = ScenarioConfig(name="Test", rivers=rivers)
        return world, config

    def test_valid_river_accepted(self):
        world, config = self._make_world_and_config([])
        r0 = world.regions[0]
        if r0.adjacencies:
            adj_name = r0.adjacencies[0]
            config.rivers = [River(name="Test River", path=[r0.name, adj_name])]
            apply_scenario(world, config)
            assert len(world.rivers) == 1
            assert world.rivers[0].name == "Test River"

    def test_river_with_unknown_region_raises(self):
        world, config = self._make_world_and_config([])
        config.rivers = [River(name="Bad River", path=["FAKE_REGION", world.regions[0].name])]
        with pytest.raises(ValueError, match="not found"):
            apply_scenario(world, config)

    def test_too_many_rivers_raises(self):
        world, config = self._make_world_and_config([])
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else "X"
        config.rivers = [
            River(name=f"River {i}", path=[r0.name, adj_name]) for i in range(33)
        ]
        with pytest.raises(ValueError, match="Maximum 32"):
            apply_scenario(world, config)

    def test_river_with_non_adjacent_regions_raises(self):
        world, config = self._make_world_and_config([])
        r0 = world.regions[0]
        non_adj = None
        for r in world.regions:
            if r.name != r0.name and r.name not in r0.adjacencies:
                non_adj = r
                break
        if non_adj:
            config.rivers = [River(name="Bad River", path=[r0.name, non_adj.name])]
            with pytest.raises(ValueError, match="not adjacent"):
                apply_scenario(world, config)


class TestRiverMaskAssignment:
    def test_river_mask_assigned(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies in test world")
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        assert region_map[r0.name].river_mask & 1 != 0
        assert region_map[adj_name].river_mask & 1 != 0

    def test_non_river_region_mask_zero(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies in test world")
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        river_region_names = {r0.name, adj_name}
        for r in world.regions:
            if r.name not in river_region_names:
                assert r.river_mask == 0, f"{r.name} should have river_mask=0"

    def test_confluence_has_multiple_bits(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        shared = None
        for r in world.regions:
            if len(r.adjacencies) >= 2:
                shared = r
                break
        if shared is None:
            pytest.skip("No region with 2+ adjacencies")
        a1, a2 = shared.adjacencies[0], shared.adjacencies[1]
        config = ScenarioConfig(
            name="Test",
            rivers=[
                River(name="River A", path=[a1, shared.name]),
                River(name="River B", path=[a2, shared.name]),
            ],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        mask = region_map[shared.name].river_mask
        assert mask & 1 != 0
        assert mask & 2 != 0


class TestRiverWorldGenBonuses:
    def _apply_rivers(self, seed=42):
        world = generate_world(seed=seed, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies")
        pre_water = r0.ecology.water
        pre_capacity = r0.carrying_capacity
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        return world, r0.name, adj_name, pre_water, pre_capacity

    def test_water_baseline_increased(self):
        world, rname, _, pre_water, _ = self._apply_rivers()
        region_map = {r.name: r for r in world.regions}
        assert region_map[rname].ecology.water >= pre_water

    def test_carrying_capacity_multiplied(self):
        world, rname, _, _, pre_cap = self._apply_rivers()
        region_map = {r.name: r for r in world.regions}
        assert region_map[rname].carrying_capacity >= int(pre_cap * 1.2)

    def test_fish_assigned_to_empty_slot(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies")
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        region = region_map[r0.name]
        has_fish = ResourceType.FISH in region.resource_types
        has_empty = EMPTY_SLOT in region.resource_types
        assert has_fish or not has_empty

    def test_fish_has_base_yield(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies")
        r0.resource_types[2] = EMPTY_SLOT
        r0.resource_base_yields[2] = 0.0
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        region = region_map[r0.name]
        if ResourceType.FISH in region.resource_types:
            fish_idx = region.resource_types.index(ResourceType.FISH)
            assert region.resource_base_yields[fish_idx] > 0.0, "Fish must have base yield set"

    def test_full_slot_region_keeps_resources(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies")
        r0.resource_types = [ResourceType.ORE, ResourceType.PRECIOUS, ResourceType.SALT]
        original_types = list(r0.resource_types)
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        assert region_map[r0.name].resource_types == original_types

    def test_confluence_bonuses_applied_once(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        shared = None
        for r in world.regions:
            if len(r.adjacencies) >= 2:
                shared = r
                break
        if shared is None:
            pytest.skip("No region with 2+ adjacencies")
        pre_water = shared.ecology.water
        a1, a2 = shared.adjacencies[0], shared.adjacencies[1]
        config = ScenarioConfig(
            name="Test",
            rivers=[
                River(name="River A", path=[a1, shared.name]),
                River(name="River B", path=[a2, shared.name]),
            ],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        water_increase = region_map[shared.name].ecology.water - pre_water
        assert water_increase < 0.25
