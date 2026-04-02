"""Tests for initial world generation."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from unittest.mock import MagicMock
from chronicler.world_gen import (
    DEFAULT_EVENT_PROBABILITIES,
    assign_civilizations,
    generate_regions,
    generate_world,
)
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


class TestGenerateRegionsValidation:
    def test_exceeding_template_pool_raises(self):
        with pytest.raises(ValueError, match="region templates are available"):
            generate_regions(count=13, seed=42)

    def test_exact_pool_size_works(self):
        regions = generate_regions(count=12, seed=42)
        assert len(regions) == 12


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
        assert world.event_probabilities == DEFAULT_EVENT_PROBABILITIES
        world.event_probabilities["drought"] = 0.9
        assert DEFAULT_EVENT_PROBABILITIES["drought"] == 0.05

    def test_used_leader_names_seeded(self):
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        assert len(world.used_leader_names) == len(world.civilizations)
        for civ in world.civilizations:
            assert civ.leader.name in world.used_leader_names
        assert len(world.used_leader_names) == len(set(world.used_leader_names))

    def test_cross_process_deterministic_with_randomized_python_hash_seed(self):
        repo_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "src")
        env.pop("PYTHONHASHSEED", None)

        script = """
import json
from chronicler.world_gen import generate_world

world = generate_world(seed=42, num_regions=8, num_civs=4)
payload = {
    "regions": [
        {
            "name": region.name,
            "resource_types": [int(rt) for rt in region.resource_types],
            "resource_base_yields": [round(val, 6) for val in region.resource_base_yields],
        }
        for region in world.regions
    ],
    "civilizations": [
        {
            "name": civ.name,
            "leader": civ.leader.name,
            "regions": list(civ.regions),
        }
        for civ in world.civilizations
    ],
}
print(json.dumps(payload, sort_keys=True))
""".strip()

        out_a = subprocess.check_output(
            [sys.executable, "-c", script],
            cwd=repo_root,
            env=env,
            text=True,
        )
        out_b = subprocess.check_output(
            [sys.executable, "-c", script],
            cwd=repo_root,
            env=env,
            text=True,
        )

        assert json.loads(out_a) == json.loads(out_b)

    def test_previous_majority_faith_seeded_from_founding_faith(self):
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        seeded = [c.previous_majority_faith for c in world.civilizations]
        current = [c.civ_majority_faith for c in world.civilizations]

        assert seeded == current
        assert len(set(current)) == len(world.civilizations)


class TestLLMWorldGeneration:
    def test_llm_generates_goals(self):
        mock_client = MagicMock()
        expected_goals = [
            "Dominate the eastern trade routes",
            "Unite the mountain clans",
            "Spread the faith to all shores",
            "Preserve the ancient knowledge",
        ]
        mock_client.complete.return_value = (
            '{"goals": ["Dominate the eastern trade routes", '
            '"Unite the mountain clans", '
            '"Spread the faith to all shores", '
            '"Preserve the ancient knowledge"]}'
        )
        mock_client.model = "test-model"
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        # Without LLM, goals are empty
        assert all(c.goal == "" for c in world.civilizations)

        from chronicler.world_gen import enrich_with_llm
        enrich_with_llm(world, client=mock_client)
        assert [c.goal for c in world.civilizations] == expected_goals
        mock_client.complete.assert_called_once()


def test_civilizations_start_at_tribal():
    regions = generate_regions(count=8, seed=42)
    civs = assign_civilizations(regions, civ_count=4, seed=42)
    for civ in civs:
        assert civ.tech_era == TechEra.TRIBAL, f"{civ.name} started at {civ.tech_era}"
