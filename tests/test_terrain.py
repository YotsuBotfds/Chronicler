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


class TestTerrainFertilityCap:
    def test_plains_cap(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="F", terrain="plains", carrying_capacity=80, resources="fertile")
        assert terrain_fertility_cap(r) == 0.9

    def test_desert_cap(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="D", terrain="desert", carrying_capacity=30, resources="mineral")
        assert terrain_fertility_cap(r) == 0.3

    def test_tundra_cap(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="T", terrain="tundra", carrying_capacity=20, resources="mineral")
        assert terrain_fertility_cap(r) == 0.2

    def test_unknown_terrain_defaults_to_plains(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="H", terrain="river", carrying_capacity=60, resources="fertile")
        assert terrain_fertility_cap(r) == 0.9


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
    def test_basic_capacity(self):
        from chronicler.terrain import effective_capacity
        r = Region(name="F", terrain="plains", carrying_capacity=80, resources="fertile",
                   fertility=0.5)
        assert effective_capacity(r) == 40

    def test_capped_by_terrain(self):
        from chronicler.terrain import effective_capacity
        r = Region(name="D", terrain="desert", carrying_capacity=100, resources="mineral",
                   fertility=0.5)
        assert effective_capacity(r) == 30

    def test_floor_of_one(self):
        from chronicler.terrain import effective_capacity
        r = Region(name="X", terrain="tundra", carrying_capacity=10, resources="mineral",
                   fertility=0.0)
        assert effective_capacity(r) == 1

    def test_full_capacity(self):
        from chronicler.terrain import effective_capacity
        r = Region(name="F", terrain="plains", carrying_capacity=90, resources="fertile",
                   fertility=0.9)
        assert effective_capacity(r) == 81

    def test_fertility_above_cap_uses_cap(self):
        from chronicler.terrain import effective_capacity
        r = Region(name="M", terrain="mountains", carrying_capacity=50, resources="mineral",
                   fertility=1.0)
        assert effective_capacity(r) == 30


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


class TestTerrainFertilityCapIntegration:
    def test_desert_recovery_capped(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="D", terrain="desert", carrying_capacity=30,
                   resources="mineral", fertility=0.29)
        cap = terrain_fertility_cap(r)
        new_fertility = min(r.fertility + 0.01, cap)
        assert new_fertility == 0.3

    def test_desert_recovery_at_cap_stays(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="D", terrain="desert", carrying_capacity=30,
                   resources="mineral", fertility=0.3)
        cap = terrain_fertility_cap(r)
        new_fertility = min(r.fertility + 0.01, cap)
        assert new_fertility == 0.3


class TestFertilityRecoveryMultiTurn:
    def test_desert_recovers_to_cap_over_turns(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="D", terrain="desert", carrying_capacity=30,
                   resources="mineral", fertility=0.28)
        cap = terrain_fertility_cap(r)
        history = []
        for _ in range(5):
            r.fertility = min(r.fertility + 0.01, cap)
            history.append(round(r.fertility, 2))
        assert history == [0.29, 0.30, 0.30, 0.30, 0.30]
