"""Tests for initial world generation."""
import pytest
from unittest.mock import AsyncMock
from chronicler.world_gen import generate_world, generate_regions, assign_civilizations
from chronicler.models import WorldState, TechEra


class TestGenerateRegions:
    def test_generates_correct_count(self):
        regions = generate_regions(count=8, seed=42)
        assert len(regions) == 8

    def test_all_regions_have_names(self):
        regions = generate_regions(count=6, seed=42)
        assert all(r.name for r in regions)

    def test_deterministic_with_same_seed(self):
        r1 = generate_regions(count=6, seed=42)
        r2 = generate_regions(count=6, seed=42)
        assert [r.name for r in r1] == [r.name for r in r2]

    def test_terrain_variety(self):
        regions = generate_regions(count=8, seed=42)
        terrains = {r.terrain for r in regions}
        assert len(terrains) >= 3  # At least 3 different terrain types


class TestAssignCivilizations:
    def test_correct_civ_count(self):
        regions = generate_regions(count=8, seed=42)
        civs = assign_civilizations(regions, civ_count=4, seed=42)
        assert len(civs) == 4

    def test_each_civ_controls_at_least_one_region(self):
        regions = generate_regions(count=8, seed=42)
        civs = assign_civilizations(regions, civ_count=4, seed=42)
        for civ in civs:
            assert len(civ.regions) >= 1

    def test_civs_have_domains(self):
        regions = generate_regions(count=8, seed=42)
        civs = assign_civilizations(regions, civ_count=4, seed=42)
        for civ in civs:
            assert len(civ.domains) >= 2

    def test_civs_have_leaders(self):
        regions = generate_regions(count=8, seed=42)
        civs = assign_civilizations(regions, civ_count=4, seed=42)
        for civ in civs:
            assert civ.leader.name
            assert civ.leader.trait


class TestGenerateWorld:
    def test_produces_valid_world_state(self):
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        assert isinstance(world, WorldState)
        assert world.seed == 42
        assert world.turn == 0
        assert len(world.regions) == 8
        assert len(world.civilizations) == 4

    def test_relationships_initialized(self):
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        civ_names = [c.name for c in world.civilizations]
        for name in civ_names:
            assert name in world.relationships
            for other in civ_names:
                if other != name:
                    assert other in world.relationships[name]

    def test_event_probabilities_initialized(self):
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        assert len(world.event_probabilities) > 0
        assert all(0 < p < 1 for p in world.event_probabilities.values())
