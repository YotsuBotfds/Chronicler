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
