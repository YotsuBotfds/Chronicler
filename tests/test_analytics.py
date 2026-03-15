"""Tests for the analytics pipeline."""
import json
from pathlib import Path

import pytest


def _make_bundle(seed: int, turns: int = 10, num_civs: int = 2) -> dict:
    """Create a minimal synthetic bundle for testing.

    Generates diverse event types so all extractors have data to work with.
    """
    civ_names = [f"Civ{i}" for i in range(num_civs)]
    history = []
    events = []
    for t in range(turns):
        era = "iron" if t < 5 else "classical"
        civ_stats = {}
        for name in civ_names:
            civ_stats[name] = {
                "population": 50, "military": 30, "economy": 40,
                "culture": 30, "stability": max(0, 50 - t * 3),
                "treasury": 50 + t, "asabiya": 0.5,
                "tech_era": era, "trait": "cautious",
                "regions": [f"{name}_region"], "leader_name": f"Leader_{name}",
                "alive": True, "last_income": 5,
                "active_trade_routes": 1 if t > 2 else 0,
                "is_vassal": False, "is_fallen_empire": False,
                "in_twilight": False, "federation_name": None,
                "prestige": 0, "capital_region": f"{name}_region",
                "great_persons": [{"name": "GP1", "role": "general", "trait": "bold"}] if t > 6 else [],
                "traditions": ["warrior"] if t > 7 else [],
                "folk_heroes": [], "active_crisis": t == 8,
                "civ_stress": t,
            }
        history.append({
            "turn": t, "civ_stats": civ_stats,
            "region_control": {f"{n}_region": n for n in civ_names},
            "relationships": {},
            "trade_routes": [["Civ0", "Civ1"]] if t > 2 else [],
            "active_wars": [["Civ0", "Civ1"]] if t == 5 else [],
            "embargoes": [],
            "fertility": {f"{n}_region": 0.8 - t * 0.05 for n in civ_names},
            "mercenary_companies": [],
            "vassal_relations": [], "federations": [],
            "proxy_wars": [], "exile_modifiers": [],
            "capitals": {n: f"{n}_region" for n in civ_names},
            "peace_turns": 0,
            "region_cultural_identity": {},
            "movements_summary": [{"id": "mov1", "value_affinity": "order", "adherent_count": 2, "origin_civ": "Civ0"}] if t > 4 else [],
            "stress_index": t,
            "pandemic_regions": [],
            "climate_phase": "temperate" if t < 5 else "drought",
            "active_conditions": [{"type": "drought", "severity": 50, "duration": 3}] if t == 6 else [],
        })
        if t == 2:
            events.append({"turn": t, "event_type": "drought", "actors": ["Civ0"], "description": "drought"})
        if t == 3:
            events.append({"turn": t, "event_type": "famine", "actors": ["Civ0"], "description": "famine"})
        if t == 4:
            events.append({"turn": t, "event_type": "movement_emerged", "actors": ["Civ0"], "description": "movement"})
        if t == 5:
            events.append({"turn": t, "event_type": "war", "actors": ["Civ0", "Civ1"], "description": "war"})
        if t == 6:
            events.append({"turn": t, "event_type": "great_person_born", "actors": ["Civ0"], "description": "gp born"})
            events.append({"turn": t, "event_type": "succession_crisis", "actors": ["Civ0"], "description": "crisis"})
        if t == 7:
            events.append({"turn": t, "event_type": "tech_advancement", "actors": ["Civ0"], "description": "tech"})
        if t == 8 and seed % 3 == 0:
            events.append({"turn": t, "event_type": "pandemic", "actors": [], "description": "black swan"})
        if t == 9 and seed % 5 == 0:
            events.append({"turn": t, "event_type": "secession", "actors": ["Civ0"], "description": "secession"})
    return {
        "metadata": {"seed": seed, "total_turns": turns, "generated_at": "2026-01-01T00:00:00"},
        "history": history,
        "events_timeline": events,
        "named_events": [],
        "world_state": {
            "civilizations": [
                {"name": n, "action_counts": {"develop": 3, "trade": 2, "war": 1}}
                for n in civ_names
            ],
        },
    }


def _write_batch(tmp_path: Path, num_runs: int = 5, turns: int = 10) -> Path:
    """Write synthetic bundles to a batch directory."""
    batch_dir = tmp_path / "batch_1"
    for i in range(num_runs):
        run_dir = batch_dir / f"seed_{i + 1}"
        run_dir.mkdir(parents=True)
        bundle = _make_bundle(seed=i + 1, turns=turns)
        (run_dir / "chronicle_bundle.json").write_text(json.dumps(bundle))
    return batch_dir


class TestBundleLoader:
    def test_loads_all_bundles(self, tmp_path):
        from chronicler.analytics import load_bundles
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        assert len(bundles) == 5

    def test_raises_on_fewer_than_2_bundles(self, tmp_path):
        from chronicler.analytics import load_bundles
        batch_dir = _write_batch(tmp_path, num_runs=1)
        with pytest.raises(ValueError, match="fewer than 2"):
            load_bundles(batch_dir)

    def test_raises_on_empty_directory(self, tmp_path):
        from chronicler.analytics import load_bundles
        batch_dir = tmp_path / "empty_batch"
        batch_dir.mkdir()
        with pytest.raises(ValueError, match="fewer than 2"):
            load_bundles(batch_dir)


class TestDistributionHelpers:
    def test_percentiles_basic(self):
        from chronicler.analytics import _compute_percentiles
        values = list(range(100))
        p = _compute_percentiles(values)
        assert p["min"] == 0
        assert p["max"] == 99
        assert p["median"] == 49.5 or p["median"] == 50


class TestStabilityExtractor:
    def test_returns_percentiles_by_turn(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_stability
        batch_dir = _write_batch(tmp_path, num_runs=5, turns=10)
        bundles = load_bundles(batch_dir)
        result = extract_stability(bundles, checkpoints=[5])
        assert "percentiles_by_turn" in result
        assert "5" in result["percentiles_by_turn"]
        assert "median" in result["percentiles_by_turn"]["5"]

    def test_clamps_checkpoints_to_total_turns(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_stability
        batch_dir = _write_batch(tmp_path, num_runs=3, turns=10)
        bundles = load_bundles(batch_dir)
        result = extract_stability(bundles, checkpoints=[5, 50, 500])
        assert "5" in result["percentiles_by_turn"]
        assert "50" not in result["percentiles_by_turn"]
        assert "500" not in result["percentiles_by_turn"]

    def test_zero_rate_per_checkpoint(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_stability
        batch_dir = _write_batch(tmp_path, num_runs=5, turns=10)
        bundles = load_bundles(batch_dir)
        result = extract_stability(bundles, checkpoints=[9])
        assert "zero_rate_by_turn" in result
        # stability = max(0, 50 - t*3), at turn 9 = max(0, 50-27) = 23 > 0
        assert result["zero_rate_by_turn"]["9"] == 0.0


class TestResourceExtractor:
    def test_famine_turn_distribution(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_resources
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_resources(bundles)
        assert "famine_turn_distribution" in result
        assert result["famine_turn_distribution"]["median"] == 3

    def test_trade_route_percentiles(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_resources
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_resources(bundles, checkpoints=[5])
        assert "trade_route_percentiles_by_turn" in result
        assert result["trade_route_percentiles_by_turn"]["5"]["median"] >= 1


class TestPoliticsExtractor:
    def test_firing_rates(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_politics
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_politics(bundles)
        assert "war_rate" in result
        assert result["war_rate"] == 1.0
        assert "elimination_turn_distribution" in result

    def test_secession_rate(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_politics
        batch_dir = _write_batch(tmp_path, num_runs=15)
        bundles = load_bundles(batch_dir)
        result = extract_politics(bundles)
        assert 0 < result.get("secession_rate", 0) < 1.0


class TestClimateExtractor:
    def test_disaster_frequency(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_climate
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_climate(bundles)
        assert "disaster_frequency_by_type" in result
        assert result["disaster_frequency_by_type"].get("drought", 0) == 1.0


class TestMemeticExtractor:
    def test_movement_metrics(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_memetic
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_memetic(bundles, checkpoints=[5])
        assert "paradigm_shift_rate" in result
        assert "movement_count_percentiles_by_turn" in result


class TestGreatPersonExtractor:
    def test_generation_and_crisis_rate(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_great_persons
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_great_persons(bundles)
        assert result["great_person_born_rate"] == 1.0
        assert result["succession_crisis_rate"] == 1.0


class TestEmergenceExtractor:
    def test_black_swan_frequency(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_emergence
        batch_dir = _write_batch(tmp_path, num_runs=15)
        bundles = load_bundles(batch_dir)
        result = extract_emergence(bundles)
        assert "black_swan_frequency_by_type" in result
        assert 0 < result["black_swan_frequency_by_type"].get("pandemic", 0) < 1.0
        assert "regression_rate" in result


class TestGeneralExtractor:
    def test_era_distribution(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_general
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_general(bundles)
        assert "era_distribution_at_final" in result
        assert "classical" in result["era_distribution_at_final"]
        assert "median_era_at_final" in result

    def test_first_war_and_civs_alive(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_general
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_general(bundles)
        assert "first_war_turn_distribution" in result
        assert result["first_war_turn_distribution"]["median"] == 5
        assert "civs_alive_at_end" in result
