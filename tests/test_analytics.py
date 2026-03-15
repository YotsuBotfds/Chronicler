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
