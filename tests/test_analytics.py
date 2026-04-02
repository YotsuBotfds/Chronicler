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
            "ecology": {f"{n}_region": {"soil": 0.8 - t * 0.05, "water": 0.6, "forest_cover": 0.3} for n in civ_names},
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
        "metadata": {
            "seed": seed,
            "total_turns": turns,
            "generated_at": "2026-01-01T00:00:00",
            "interestingness_score": float(seed * 10),
        },
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


class TestPrecapWeightExtractor:
    def test_cap_fire_uses_base_scaled_default_threshold(self):
        from chronicler.analytics import extract_precap_weights

        bundle = {
            "history": [{
                "turn": 0,
                "civ_stats": {
                    "A": {"alive": True, "max_precap_weight": 0.6},
                    "B": {"alive": True, "max_precap_weight": 0.4},
                },
            }],
            "world_state": {"tuning_overrides": {}},
            "metadata": {"total_turns": 1},
        }

        result = extract_precap_weights([bundle], checkpoints=[0])
        assert result["cap_fire_rate"] == pytest.approx(0.5)

    def test_cap_fire_respects_bundle_weight_cap_override(self):
        from chronicler.analytics import extract_precap_weights

        bundle = {
            "history": [{
                "turn": 0,
                "civ_stats": {
                    "A": {"alive": True, "max_precap_weight": 0.25},
                    "B": {"alive": True, "max_precap_weight": 0.15},
                },
            }],
            "world_state": {"tuning_overrides": {"action.weight_cap": 1.0}},
            "metadata": {"total_turns": 1},
        }

        result = extract_precap_weights([bundle], checkpoints=[0])
        assert result["cap_fire_rate"] == pytest.approx(0.5)


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


class TestRunSummaries:
    def test_run_summaries_treat_empty_regions_as_dead_without_alive_field(self):
        from chronicler.analytics import compute_run_summaries

        bundle = _make_bundle(seed=7)
        dead_civ = bundle["history"][-1]["civ_stats"]["Civ1"]
        dead_civ.pop("alive")
        dead_civ["regions"] = []

        summaries = compute_run_summaries([(Path("batch/seed_7/chronicle_bundle.json"), bundle)])

        assert "fractured" in summaries[0]["signal_flags"]


class TestEventFiringRates:
    def test_firing_rate_empty_input_returns_zero(self):
        from chronicler.analytics import _firing_rate

        assert _firing_rate([], "war") == 0.0

    def test_discovers_event_types_from_data(self, tmp_path):
        from chronicler.analytics import load_bundles, compute_event_firing_rates
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        rates = compute_event_firing_rates(bundles)
        assert "famine" in rates
        assert "war" in rates
        assert rates["famine"] == 1.0
        assert rates["war"] == 1.0


class TestAnomalyDetection:
    def test_detects_degenerate_patterns(self):
        from chronicler.analytics import detect_anomalies
        report = {
            "stability": {"zero_rate_by_turn": {"100": 0.5}},
            "event_firing_rates": {"famine": 0.99},
            "general": {"median_era_at_final": "tribal"},
        }
        anomalies = detect_anomalies(report)
        assert any(a["name"] == "stability_collapse" for a in anomalies)

    def test_detects_never_fire(self):
        from chronicler.analytics import detect_anomalies
        report = {
            "stability": {"zero_rate_by_turn": {}},
            "event_firing_rates": {"famine": 1.0, "hostage_taken": 0.0},
            "general": {"median_era_at_final": "medieval"},
        }
        anomalies = detect_anomalies(report)
        never_fire = [a for a in anomalies if a["name"] == "never_fire"]
        assert len(never_fire) >= 1


class TestReportAssembly:
    def test_generate_report_returns_all_sections(self, tmp_path):
        from chronicler.analytics import generate_report
        batch_dir = _write_batch(tmp_path, num_runs=5)
        report = generate_report(batch_dir)
        assert "metadata" in report
        assert "stability" in report
        assert "resources" in report
        assert "politics" in report
        assert "event_firing_rates" in report
        assert "anomalies" in report
        assert "run_summaries" in report
        assert report["metadata"]["runs"] == 5
        assert report["metadata"]["report_schema_version"] == 2

    def test_generate_report_respects_checkpoints(self, tmp_path):
        from chronicler.analytics import generate_report
        batch_dir = _write_batch(tmp_path, num_runs=3, turns=10)
        report = generate_report(batch_dir, checkpoints=[5])
        assert "5" in report["stability"]["percentiles_by_turn"]

    def test_generate_report_ranks_run_summaries_by_interestingness(self, tmp_path):
        from chronicler.analytics import generate_report

        batch_dir = tmp_path / "batch_ranked"
        batch_dir.mkdir()

        low_bundle = _make_bundle(seed=11, turns=10)
        low_bundle["metadata"]["interestingness_score"] = 12.5

        high_bundle = _make_bundle(seed=22, turns=10)
        high_bundle["metadata"]["interestingness_score"] = 87.0
        high_bundle["history"][-1]["civ_stats"]["Civ0"]["tech_era"] = "industrial"
        high_bundle["history"][-1]["civ_stats"]["Civ1"]["stability"] = 1
        high_bundle["events_timeline"].extend([
            {"turn": 8, "event_type": "war", "actors": ["Civ0", "Civ1"], "description": "war 2", "importance": 8},
            {"turn": 9, "event_type": "war", "actors": ["Civ0", "Civ1"], "description": "war 3", "importance": 8},
            {"turn": 9, "event_type": "tech_advancement", "actors": ["Civ0"], "description": "advance", "importance": 7},
        ])
        high_bundle["named_events"] = [
            {
                "turn": 9,
                "name": "Empire Breaks",
                "event_type": "capital_collapse",
                "actors": ["Civ1"],
                "region": None,
                "description": "collapse",
                "importance": 9,
            },
        ]

        for run_name, bundle in (("seed_11", low_bundle), ("seed_22", high_bundle)):
            run_dir = batch_dir / run_name
            run_dir.mkdir()
            (run_dir / "chronicle_bundle.json").write_text(json.dumps(bundle))

        report = generate_report(batch_dir)
        summaries = report["run_summaries"]

        assert [summary["seed"] for summary in summaries] == [22, 11]
        assert [summary["rank"] for summary in summaries] == [1, 2]
        assert summaries[0]["war_count"] == 3
        assert summaries[0]["collapse_count"] == 1
        assert summaries[0]["tech_advancement_count"] == 2
        assert summaries[0]["named_event_count"] == 1
        assert "war-heavy" in summaries[0]["signal_flags"]
        assert "collapse-risk" in summaries[0]["signal_flags"]
        assert "instability" in summaries[0]["signal_flags"]
        assert "late-tech" in summaries[0]["signal_flags"]


class TestTextFormatter:
    def test_format_text_report_produces_output(self, tmp_path):
        from chronicler.analytics import generate_report, format_text_report
        batch_dir = _write_batch(tmp_path, num_runs=5)
        report = generate_report(batch_dir)
        text = format_text_report(report)
        assert "ANALYTICS REPORT" in text
        assert "STABILITY" in text
        assert "EVENT FIRING RATES" in text
        assert len(text) > 200


class TestDeltaReport:
    def test_delta_shows_changed_metrics(self):
        from chronicler.analytics import format_delta_report
        baseline = {
            "stability": {"zero_rate_by_turn": {"100": 0.43}},
            "event_firing_rates": {"famine": 0.99},
            "anomalies": [{"name": "stability_collapse", "severity": "CRITICAL", "detail": "bad"}],
        }
        current = {
            "stability": {"zero_rate_by_turn": {"100": 0.08}},
            "event_firing_rates": {"famine": 0.65},
            "anomalies": [],
        }
        text = format_delta_report(baseline, current)
        assert "100" in text
        assert "famine" in text
        assert "RESOLVED" in text

    def test_delta_omits_small_changes(self):
        from chronicler.analytics import format_delta_report
        baseline = {"stability": {"zero_rate_by_turn": {"100": 0.50}}}
        current = {"stability": {"zero_rate_by_turn": {"100": 0.49}}}
        text = format_delta_report(baseline, current, threshold=0.05)
        assert "omitted" in text.lower()


# --- M47b Extractor Tests ---

def test_extract_schism_count_basic():
    from chronicler.analytics import extract_schism_count
    bundles = [{"events_timeline": [{"event_type": "Schism"}, {"event_type": "war"}]}]
    result = extract_schism_count(bundles)
    assert result["schism_count"]["median"] == 1.0
    assert result["firing_rate"] == 1.0


def test_extract_schism_count_no_schisms():
    from chronicler.analytics import extract_schism_count
    bundles = [{"events_timeline": [{"event_type": "war"}]}]
    result = extract_schism_count(bundles)
    assert result["schism_count"]["median"] == 0
    assert result["firing_rate"] == 0.0


def test_extract_arc_distribution_counts_types():
    from chronicler.analytics import extract_arc_distribution
    bundles = [{"world_state": {"civilizations": [
        {"great_persons": [{"arc_type": "Rise-and-Fall"}, {"arc_type": "Exile-and-Return"}]}
    ]}}]
    result = extract_arc_distribution(bundles)
    assert result["distinct_count"] == 2
    assert result["total"] == 2


def test_extract_dynasty_count_basic():
    from chronicler.analytics import extract_dynasty_count
    bundles = [{"world_state": {"civilizations": [
        {"great_persons": [{"dynasty_id": 1}, {"dynasty_id": 2}, {"dynasty_id": 1}]}
    ]}}]
    result = extract_dynasty_count(bundles)
    assert result["dynasty_count"]["median"] == 2.0


def test_extract_stockpile_levels_basic():
    from chronicler.analytics import extract_stockpile_levels
    bundles = [{"world_state": {"regions": [
        {"stockpile": {"goods": {"grain": 10.0, "ore": 5.0}}},
        {"stockpile": {"goods": {"grain": 3.0}}},
    ]}}]
    result = extract_stockpile_levels(bundles)
    assert result["stockpile_total"]["max"] == 15.0


def test_extract_conversion_rates_basic():
    from chronicler.analytics import extract_conversion_rates
    bundles = [{"events_timeline": [
        {"event_type": "Persecution"},
        {"event_type": "Persecution"},
        {"event_type": "Schism"},
    ]}]
    result = extract_conversion_rates(bundles)
    assert result["Persecution"]["median"] == 2.0
    assert result["Schism"]["median"] == 1.0
    assert result["Reformation"]["median"] == 0


def test_settlement_diagnostics_includes_urbanization():
    """extract_settlement_diagnostics includes urban fraction time series."""
    from chronicler.analytics import extract_settlement_diagnostics
    from chronicler.models import TurnSnapshot, CivSnapshot

    # Build minimal history with urban fractions
    history = []
    for t in range(5):
        civ_stats = {
            "TestCiv": CivSnapshot(
                population=100, military=10, economy=20, culture=10,
                stability=50, treasury=50, asabiya=0.5, tech_era="iron",
                trait="cautious", regions=["r1"], leader_name="Leader",
                alive=True, urban_agents=t * 10, urban_fraction=t * 0.1,
            )
        }
        snap = TurnSnapshot(
            turn=t,
            civ_stats=civ_stats,
            region_control={"r1": "TestCiv"},
            relationships={},
            urban_agent_count=t * 10,
            urban_fraction=t * 0.1,
        )
        history.append(snap)

    result = extract_settlement_diagnostics(history)
    assert "urbanization" in result
    assert "global_trend" in result["urbanization"]
    assert len(result["urbanization"]["global_trend"]) == 5
    # Verify per-civ data
    assert "TestCiv" in result["urbanization"]["per_civ"]
    assert len(result["urbanization"]["per_civ"]["TestCiv"]) == 5
    # Verify values at turn 3
    global_t3 = result["urbanization"]["global_trend"][3]
    assert global_t3["turn"] == 3
    assert global_t3["urban_agent_count"] == 30
    assert abs(global_t3["urban_fraction"] - 0.3) < 1e-9
    per_civ_t3 = result["urbanization"]["per_civ"]["TestCiv"][3]
    assert per_civ_t3["urban_agents"] == 30
    assert abs(per_civ_t3["urban_fraction"] - 0.3) < 1e-9
