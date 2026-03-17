"""Tests for civ_index() and get_civ() helpers in utils.py."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Stub out the Rust extension so tests run without a compiled wheel
if "chronicler_agents" not in sys.modules:
    sys.modules["chronicler_agents"] = MagicMock()

import pytest
from chronicler.models import WorldState, Civilization, Leader, TechEra, Region


def _make_world(civ_names: list[str]) -> WorldState:
    """Create a minimal WorldState with named civs."""
    civs = []
    regions = []
    for name in civ_names:
        region = Region(name=f"{name}_region", terrain="plains", carrying_capacity=10, resources="fertile", controller=name)
        civ = Civilization(
            name=name, population=10, military=5, economy=5, culture=5, stability=50,
            tech_era=TechEra.IRON, treasury=10,
            leader=Leader(name=f"Leader of {name}", trait="cautious", reign_start=0),
            regions=[region.name], values=["Honor"], asabiya=0.5,
        )
        civs.append(civ)
        regions.append(region)
    return WorldState(name="Test", seed=42, turn=0, regions=regions, civilizations=civs, relationships={})


class TestCivIndex:
    def test_finds_existing_civ(self):
        from chronicler.utils import civ_index
        world = _make_world(["Alpha", "Beta", "Gamma"])
        assert civ_index(world, "Alpha") == 0
        assert civ_index(world, "Beta") == 1
        assert civ_index(world, "Gamma") == 2

    def test_raises_on_missing_civ(self):
        from chronicler.utils import civ_index
        world = _make_world(["Alpha"])
        with pytest.raises(StopIteration):
            civ_index(world, "NonExistent")


class TestGetCiv:
    def test_returns_civ_object(self):
        from chronicler.utils import get_civ
        world = _make_world(["Alpha", "Beta"])
        civ = get_civ(world, "Beta")
        assert civ is not None
        assert civ.name == "Beta"

    def test_returns_none_on_miss(self):
        from chronicler.utils import get_civ
        world = _make_world(["Alpha"])
        assert get_civ(world, "NonExistent") is None
