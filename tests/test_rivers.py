import pytest
from chronicler.models import River, WorldState
from chronicler.tuning import (
    K_RIVER_WATER_BONUS, K_RIVER_CAPACITY_MULTIPLIER,
    K_DEFORESTATION_THRESHOLD, K_DEFORESTATION_WATER_LOSS,
    KNOWN_OVERRIDES,
)
from chronicler.scenario import ScenarioConfig


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
