"""Tests for M18 Emergence and Chaos systems."""
import pytest
from chronicler.models import PandemicRegion, TerrainTransitionRule


class TestPandemicRegion:
    def test_create(self):
        pr = PandemicRegion(region_name="Verdant Plains", severity=2, turns_remaining=5)
        assert pr.region_name == "Verdant Plains"
        assert pr.severity == 2
        assert pr.turns_remaining == 5

    def test_serialization_roundtrip(self):
        pr = PandemicRegion(region_name="Iron Peaks", severity=1, turns_remaining=4)
        data = pr.model_dump()
        pr2 = PandemicRegion(**data)
        assert pr2 == pr


class TestTerrainTransitionRule:
    def test_create(self):
        rule = TerrainTransitionRule(
            from_terrain="forest", to_terrain="plains",
            condition="low_fertility", threshold_turns=50,
        )
        assert rule.from_terrain == "forest"
        assert rule.threshold_turns == 50

    def test_serialization_roundtrip(self):
        rule = TerrainTransitionRule(
            from_terrain="plains", to_terrain="forest",
            condition="depopulated", threshold_turns=100,
        )
        data = rule.model_dump()
        rule2 = TerrainTransitionRule(**data)
        assert rule2 == rule
