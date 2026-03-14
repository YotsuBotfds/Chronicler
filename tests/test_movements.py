"""Tests for M16b movements and schisms."""
import pytest
from chronicler.models import (
    Movement, WorldState, Region, Civilization, Relationship,
    Leader, TechEra, Disposition,
)


class TestMovementModel:
    def test_movement_creation(self):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=30,
            value_affinity="Trade",
        )
        assert m.adherents == {}
        assert m.value_affinity == "Trade"

    def test_worldstate_has_movements(self):
        world = WorldState(name="test", seed=42)
        assert world.movements == []
        assert world.next_movement_id == 0


from chronicler.movements import tick_movements, MOVEMENT_EMERGENCE_INTERVAL


@pytest.fixture
def movement_world():
    regions = [
        Region(name="R1", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivA", cultural_identity="CivA"),
        Region(name="R2", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivB", cultural_identity="CivB"),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=70,
            stability=30, leader=Leader(name="LA", trait="visionary", reign_start=0),
            domains=["trade"], values=["Trade", "Order"], regions=["R1"],
            tech_era=TechEra.CLASSICAL,
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=40,
            stability=80, leader=Leader(name="LB", trait="aggressive", reign_start=0),
            domains=["warfare"], values=["Honor", "Strength"], regions=["R2"],
            tech_era=TechEra.IRON,
        ),
    ]
    relationships = {
        "CivA": {"CivB": Relationship(disposition=Disposition.NEUTRAL, trade_volume=5)},
        "CivB": {"CivA": Relationship(disposition=Disposition.NEUTRAL, trade_volume=5)},
    }
    return WorldState(
        name="test", seed=42, turn=0, regions=regions,
        civilizations=civs, relationships=relationships,
    )


class TestMovementEmergence:
    def test_no_emergence_before_interval(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL - 1
        tick_movements(movement_world)
        assert len(movement_world.movements) == 0

    def test_emergence_at_interval(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        assert len(movement_world.movements) == 1

    def test_movement_has_correct_fields(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        m = movement_world.movements[0]
        assert m.id == "movement_0"
        assert m.origin_turn == MOVEMENT_EMERGENCE_INTERVAL
        assert m.origin_civ in [c.name for c in movement_world.civilizations]
        assert m.value_affinity in movement_world.civilizations[0].values + movement_world.civilizations[1].values

    def test_origin_civ_auto_adopts(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        m = movement_world.movements[0]
        assert m.origin_civ in m.adherents

    def test_next_movement_id_increments(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        assert movement_world.next_movement_id == 1

    def test_emergence_generates_named_event(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        assert any(
            ne.event_type == "movement_emergence"
            for ne in movement_world.named_events
        )

    def test_empty_values_skips_emergence(self, movement_world):
        for civ in movement_world.civilizations:
            civ.values = []
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        assert len(movement_world.movements) == 0

    def test_deterministic_tiebreaker(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        movement_world.civilizations[0].culture = 50
        movement_world.civilizations[0].stability = 50
        movement_world.civilizations[1].culture = 50
        movement_world.civilizations[1].stability = 50
        movement_world.civilizations[0].tech_era = TechEra.IRON
        movement_world.civilizations[1].tech_era = TechEra.IRON
        tick_movements(movement_world)
        origin1 = movement_world.movements[0].origin_civ

        movement_world.movements.clear()
        movement_world.next_movement_id = 0
        movement_world.named_events.clear()
        tick_movements(movement_world)
        origin2 = movement_world.movements[0].origin_civ

        assert origin1 == origin2


class TestMovementSpread:
    def test_spread_via_trade_route(self, movement_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0},
        )
        movement_world.movements.append(m)
        movement_world.relationships["CivA"]["CivB"].trade_volume = 200
        movement_world.relationships["CivB"]["CivA"].trade_volume = 200
        tick_movements(movement_world)
        assert "CivB" in m.adherents

    def test_no_spread_to_opposing_value(self, movement_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Cunning",
            adherents={"CivA": 0},
        )
        movement_world.movements.append(m)
        movement_world.relationships["CivA"]["CivB"].trade_volume = 1000
        movement_world.relationships["CivB"]["CivA"].trade_volume = 1000
        tick_movements(movement_world)
        assert "CivB" not in m.adherents

    def test_no_cascade_in_single_turn(self, movement_world):
        civ_c = Civilization(
            name="CivC", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LC", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade"], regions=["R3"],
        )
        movement_world.civilizations.append(civ_c)
        r3 = Region(name="R3", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivC", cultural_identity="CivC")
        movement_world.regions.append(r3)
        movement_world.relationships["CivA"]["CivC"] = Relationship(trade_volume=0)
        movement_world.relationships["CivC"] = {
            "CivA": Relationship(trade_volume=0),
            "CivB": Relationship(trade_volume=200),
        }
        movement_world.relationships["CivB"]["CivC"] = Relationship(trade_volume=200)

        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0},
        )
        movement_world.movements.append(m)
        movement_world.relationships["CivA"]["CivB"].trade_volume = 200

        tick_movements(movement_world)
        if "CivB" in m.adherents:
            assert "CivC" not in m.adherents, "Single-turn cascade should be prevented"

    def test_spread_generates_named_event(self, movement_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0},
        )
        movement_world.movements.append(m)
        movement_world.relationships["CivA"]["CivB"].trade_volume = 200
        movement_world.relationships["CivB"]["CivA"].trade_volume = 200
        tick_movements(movement_world)
        if "CivB" in m.adherents:
            assert any(
                ne.event_type == "movement_adoption"
                for ne in movement_world.named_events
            )
