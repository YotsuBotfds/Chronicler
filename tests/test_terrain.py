import pytest
from chronicler.models import Region


class TestTerrainDefenseBonus:
    def test_mountains_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Peaks", terrain="mountains", carrying_capacity=50, resources="mineral")
        assert terrain_defense_bonus(r) == 20

    def test_plains_no_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Fields", terrain="plains", carrying_capacity=80, resources="fertile")
        assert terrain_defense_bonus(r) == 0

    def test_forest_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Woods", terrain="forest", carrying_capacity=60, resources="timber")
        assert terrain_defense_bonus(r) == 10

    def test_coast_no_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Shore", terrain="coast", carrying_capacity=70, resources="maritime")
        assert terrain_defense_bonus(r) == 0

    def test_desert_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Sands", terrain="desert", carrying_capacity=30, resources="mineral")
        assert terrain_defense_bonus(r) == 5

    def test_tundra_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Frost", terrain="tundra", carrying_capacity=20, resources="mineral")
        assert terrain_defense_bonus(r) == 10

    def test_unknown_terrain_defaults_to_plains(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Hills", terrain="hills", carrying_capacity=60, resources="fertile")
        assert terrain_defense_bonus(r) == 0


class TestTerrainEcologyCaps:
    """Terrain ecology caps are now in ecology.TERRAIN_ECOLOGY_CAPS."""

    def test_plains_soil_cap(self):
        from chronicler.ecology import TERRAIN_ECOLOGY_CAPS
        assert TERRAIN_ECOLOGY_CAPS["plains"]["soil"] == 0.95

    def test_desert_soil_cap(self):
        from chronicler.ecology import TERRAIN_ECOLOGY_CAPS
        assert TERRAIN_ECOLOGY_CAPS["desert"]["soil"] == 0.30

    def test_tundra_soil_cap(self):
        from chronicler.ecology import TERRAIN_ECOLOGY_CAPS
        assert TERRAIN_ECOLOGY_CAPS["tundra"]["soil"] == 0.20

    def test_all_terrains_present(self):
        from chronicler.ecology import TERRAIN_ECOLOGY_CAPS
        assert set(TERRAIN_ECOLOGY_CAPS.keys()) == {"plains", "forest", "mountains", "coast", "desert", "tundra"}


class TestTerrainTradeModifier:
    def test_coast_trade_bonus(self):
        from chronicler.terrain import terrain_trade_modifier
        r = Region(name="S", terrain="coast", carrying_capacity=70, resources="maritime")
        assert terrain_trade_modifier(r) == 2

    def test_plains_no_trade_bonus(self):
        from chronicler.terrain import terrain_trade_modifier
        r = Region(name="F", terrain="plains", carrying_capacity=80, resources="fertile")
        assert terrain_trade_modifier(r) == 0


class TestEffectiveCapacity:
    """effective_capacity now lives in ecology module."""

    def test_basic_capacity(self):
        from chronicler.ecology import effective_capacity
        from chronicler.models import RegionEcology
        r = Region(name="F", terrain="plains", carrying_capacity=80, resources="fertile",
                   ecology=RegionEcology(soil=0.5, water=0.6))
        assert effective_capacity(r) == 40

    def test_low_water_reduces_capacity(self):
        from chronicler.ecology import effective_capacity
        from chronicler.models import RegionEcology
        r = Region(name="D", terrain="desert", carrying_capacity=100, resources="mineral",
                   ecology=RegionEcology(soil=0.5, water=0.25))
        assert effective_capacity(r) == 25

    def test_floor_of_one(self):
        from chronicler.ecology import effective_capacity
        from chronicler.models import RegionEcology
        r = Region(name="X", terrain="tundra", carrying_capacity=10, resources="mineral",
                   ecology=RegionEcology(soil=0.05, water=0.10))
        assert effective_capacity(r) >= 1

    def test_full_capacity(self):
        from chronicler.ecology import effective_capacity
        from chronicler.models import RegionEcology
        r = Region(name="F", terrain="plains", carrying_capacity=90, resources="fertile",
                   ecology=RegionEcology(soil=1.0, water=1.0))
        assert effective_capacity(r) == 90

    def test_soil_and_water_combined(self):
        from chronicler.ecology import effective_capacity
        from chronicler.models import RegionEcology
        r = Region(name="M", terrain="mountains", carrying_capacity=50, resources="mineral",
                   ecology=RegionEcology(soil=0.5, water=0.25))
        assert effective_capacity(r) == 12


class TestClassifyRegions:
    def test_frontier_single_adjacency(self):
        from chronicler.adjacency import classify_regions
        adj = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}
        roles = classify_regions(adj)
        assert roles["A"] == "frontier"
        assert roles["C"] == "frontier"

    def test_crossroads_three_plus(self):
        from chronicler.adjacency import classify_regions
        # Hub has 3+ neighbors and is NOT an articulation point (A-B-C form a cycle)
        adj = {"Hub": ["A", "B", "C"], "A": ["Hub", "B"], "B": ["Hub", "A", "C"], "C": ["Hub", "B"]}
        roles = classify_regions(adj)
        assert roles["Hub"] == "crossroads"

    def test_chokepoint_articulation(self):
        from chronicler.adjacency import classify_regions
        adj = {"A": ["B"], "B": ["A", "C", "D"], "C": ["B", "D"], "D": ["B", "C"]}
        roles = classify_regions(adj)
        assert roles["B"] == "chokepoint"

    def test_standard_default(self):
        from chronicler.adjacency import classify_regions
        adj = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
        roles = classify_regions(adj)
        assert all(r == "standard" for r in roles.values())


class TestRoleEffects:
    def test_crossroads_trade_bonus(self):
        from chronicler.terrain import ROLE_EFFECTS
        assert ROLE_EFFECTS["crossroads"].trade_mod == 3
        assert ROLE_EFFECTS["crossroads"].defense == -5

    def test_frontier_defense_bonus(self):
        from chronicler.terrain import ROLE_EFFECTS
        assert ROLE_EFFECTS["frontier"].defense == 10
        assert ROLE_EFFECTS["frontier"].trade_mod == -2

    def test_chokepoint_trade_toll(self):
        from chronicler.terrain import ROLE_EFFECTS
        assert ROLE_EFFECTS["chokepoint"].trade_mod == 5

    def test_standard_no_effect(self):
        from chronicler.terrain import ROLE_EFFECTS
        assert ROLE_EFFECTS["standard"].defense == 0
        assert ROLE_EFFECTS["standard"].trade_mod == 0


class TestRoleStacking:
    def test_mountain_frontier_defense_stacks(self):
        from chronicler.terrain import total_defense_bonus
        r = Region(name="Pass", terrain="mountains", carrying_capacity=50,
                   resources="mineral", role="frontier")
        assert total_defense_bonus(r) == 30

    def test_coastal_crossroads_trade_stacks(self):
        from chronicler.terrain import total_trade_modifier
        r = Region(name="Hub", terrain="coast", carrying_capacity=70,
                   resources="maritime", role="crossroads")
        assert total_trade_modifier(r) == 5


class TestEcologyCapIntegration:
    """Ecology capping is now handled by _clamp_ecology in ecology.py."""

    def test_desert_soil_capped(self):
        from chronicler.ecology import TERRAIN_ECOLOGY_CAPS, _clamp_ecology
        from chronicler.models import RegionEcology
        r = Region(name="D", terrain="desert", carrying_capacity=30,
                   resources="mineral",
                   ecology=RegionEcology(soil=0.50, water=0.10, forest_cover=0.0))
        _clamp_ecology(r)
        assert r.ecology.soil == 0.30  # desert soil cap

    def test_desert_soil_at_cap_stays(self):
        from chronicler.ecology import _clamp_ecology
        from chronicler.models import RegionEcology
        r = Region(name="D", terrain="desert", carrying_capacity=30,
                   resources="mineral",
                   ecology=RegionEcology(soil=0.30, water=0.10, forest_cover=0.0))
        _clamp_ecology(r)
        assert r.ecology.soil == 0.30
