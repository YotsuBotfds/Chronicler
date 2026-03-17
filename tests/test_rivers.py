import pytest
from chronicler.models import River, WorldState


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
