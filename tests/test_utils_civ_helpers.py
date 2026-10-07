"""Tests for civ_index() and get_civ() helpers in utils.py."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from chronicler.models import WorldState, Civilization, Leader, TechEra, Region
from chronicler.utils import sync_all_populations, sync_civ_population


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
        with pytest.raises(ValueError, match="NonExistent"):
            civ_index(world, "NonExistent")

    def test_cache_rebuilds_after_civilization_list_growth(self):
        from chronicler.utils import civ_index

        world = _make_world(["Alpha"])
        assert civ_index(world, "Alpha") == 0

        region = Region(name="Beta_region", terrain="plains", carrying_capacity=10, resources="fertile", controller="Beta")
        world.regions.append(region)
        world.civilizations.append(Civilization(
            name="Beta", population=10, military=5, economy=5, culture=5, stability=50,
            tech_era=TechEra.IRON, treasury=10,
            leader=Leader(name="Leader of Beta", trait="cautious", reign_start=0),
            regions=[region.name], values=["Honor"], asabiya=0.5,
        ))

        assert civ_index(world, "Beta") == 1


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

    def test_civ_map_refreshes_after_append(self):
        from chronicler.utils import civ_index, get_civ

        world = _make_world(["Alpha"])
        assert get_civ(world, "Alpha") is not None

        region = Region(name="Beta_region", terrain="plains", carrying_capacity=10, resources="fertile", controller="Beta")
        civ = Civilization(
            name="Beta", population=10, military=5, economy=5, culture=5, stability=50,
            tech_era=TechEra.IRON, treasury=10,
            leader=Leader(name="Leader of Beta", trait="cautious", reign_start=0),
            regions=[region.name], values=["Honor"], asabiya=0.5,
        )
        world.regions.append(region)
        world.civilizations.append(civ)

        assert get_civ(world, "Beta") is civ
        assert civ_index(world, "Beta") == 1


class TestSyncAllPopulations:
    def test_matches_per_civ_helper_on_world_state(self):
        world = _make_world(["Alpha", "Beta", "Gamma"])
        world.regions[0].population = 12.5
        world.regions[1].population = 3
        world.regions[2].controller = None
        expected_world = deepcopy(world)
        for civ in expected_world.civilizations:
            sync_civ_population(civ, expected_world)

        sync_all_populations(world)

        assert [civ.population for civ in world.civilizations] == [
            civ.population for civ in expected_world.civilizations
        ]

    def test_matches_per_civ_helper_with_duplicate_names_and_mixed_populations(self):
        civs = [
            SimpleNamespace(name="Alpha", regions=["stale"], population=-99),
            SimpleNamespace(name="Alpha", regions=[], population=-99),
            SimpleNamespace(name="Beta", regions=["B"], population=-99),
            SimpleNamespace(name="Zero", regions=[], population=-99),
            SimpleNamespace(name="Zero", regions=["missing"], population=-99),
            SimpleNamespace(name="Missing", regions=[], population=-99),
        ]
        regions = [
            SimpleNamespace(controller="Alpha", population=1e16),
            SimpleNamespace(controller="Beta", population=3.25),
            SimpleNamespace(controller="Unknown", population=500),
            SimpleNamespace(controller="Alpha", population=1.0),
            SimpleNamespace(controller=None, population=200),
            SimpleNamespace(controller="Alpha", population=-1e16),
            SimpleNamespace(controller="Beta", population=-7.25),
        ]
        world = SimpleNamespace(civilizations=civs, regions=regions)
        expected_world = deepcopy(world)
        for civ in expected_world.civilizations:
            sync_civ_population(civ, expected_world)

        sync_all_populations(world)

        assert [civ.population for civ in world.civilizations] == [
            civ.population for civ in expected_world.civilizations
        ]
        assert world.civilizations[2].population == 1  # negative total, owned regions
        assert world.civilizations[3].population == 0  # no regions, no floor
        assert world.civilizations[4].population == 1  # stale region list still floors
        assert world.civilizations[5].population == 0  # unknown owner stays absent

    def test_matches_per_civ_helper_with_empty_world_shapes(self):
        for world in (
            SimpleNamespace(civilizations=[], regions=[]),
            SimpleNamespace(civilizations=[], regions=[
                SimpleNamespace(),  # no civ means no region attributes are read
            ]),
            SimpleNamespace(civilizations=[
                SimpleNamespace(name="Alone", regions=["stale"], population=9),
                SimpleNamespace(name="Gone", regions=[], population=9),
            ], regions=[]),
        ):
            expected_world = deepcopy(world)
            for civ in expected_world.civilizations:
                sync_civ_population(civ, expected_world)
            sync_all_populations(world)
            assert [civ.population for civ in world.civilizations] == [
                civ.population for civ in expected_world.civilizations
            ]

    def test_matches_per_civ_failure_timing_and_partial_state(self):
        world = SimpleNamespace(
            civilizations=[
                SimpleNamespace(name="First", regions=["first"], population=-99),
                SimpleNamespace(name="Broken", regions=["broken"], population=-99),
                SimpleNamespace(name="Later", regions=["later"], population=-99),
            ],
            regions=[
                SimpleNamespace(controller="First", population=5),
                SimpleNamespace(controller="Broken", population=None),
                SimpleNamespace(controller="Later", population=7),
            ],
        )
        expected_world = deepcopy(world)
        with pytest.raises(TypeError) as baseline_error:
            for civ in expected_world.civilizations:
                sync_civ_population(civ, expected_world)
        with pytest.raises(TypeError) as current_error:
            sync_all_populations(world)

        assert str(current_error.value) == str(baseline_error.value)
        assert [civ.population for civ in world.civilizations] == [
            civ.population for civ in expected_world.civilizations
        ] == [5, -99, -99]

    def test_unknown_controller_does_not_read_its_population(self):
        world = SimpleNamespace(
            civilizations=[SimpleNamespace(name="Known", regions=["K"], population=-99)],
            regions=[
                SimpleNamespace(controller="Known", population=3),
                SimpleNamespace(controller="Unknown"),  # no population attribute
            ],
        )
        expected_world = deepcopy(world)
        sync_civ_population(expected_world.civilizations[0], expected_world)
        sync_all_populations(world)
        assert world.civilizations[0].population == expected_world.civilizations[0].population == 3
