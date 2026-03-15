"""Post-processing analytics pipeline — reads bundles, computes metrics."""
from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path

ERA_ORDER = [
    "tribal", "bronze", "iron", "classical", "medieval",
    "renaissance", "industrial", "information",
]


def load_bundles(batch_dir: Path) -> list[dict]:
    """Glob batch_dir/*/chronicle_bundle.json, deserialize, return list.

    Raises ValueError if fewer than 2 bundles found (distributions require
    multiple runs). If bundles have different total_turns, checkpoint clamping
    uses the minimum total_turns across all bundles.
    """
    bundle_paths = sorted(batch_dir.glob("*/chronicle_bundle.json"))
    if len(bundle_paths) < 2:
        raise ValueError(
            f"Analytics requires at least 2 bundles; fewer than 2 found "
            f"({len(bundle_paths)}) in {batch_dir}"
        )
    bundles = []
    for p in bundle_paths:
        with open(p) as f:
            bundles.append(json.load(f))
    return bundles


# --- Distribution helpers ---

DEFAULT_CHECKPOINTS = [25, 50, 100, 200, 500]


def _compute_percentiles(values: list[float | int]) -> dict[str, float]:
    """Compute p10, p25, median, p75, p90, min, max for a list of values."""
    if not values:
        return {"min": 0, "p10": 0, "p25": 0, "median": 0, "p75": 0, "p90": 0, "max": 0}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    return {
        "min": sorted_vals[0],
        "p10": sorted_vals[max(0, int(n * 0.1))],
        "p25": sorted_vals[max(0, int(n * 0.25))],
        "median": statistics.median(sorted_vals),
        "p75": sorted_vals[min(n - 1, int(n * 0.75))],
        "p90": sorted_vals[min(n - 1, int(n * 0.9))],
        "max": sorted_vals[-1],
    }


def _clamp_checkpoints(checkpoints: list[int] | None, max_turn: int) -> list[int]:
    """Clamp checkpoint list to <= max_turn."""
    cps = checkpoints if checkpoints is not None else DEFAULT_CHECKPOINTS
    return [c for c in cps if c <= max_turn]


def _min_total_turns(bundles: list[dict]) -> int:
    """Get the minimum total_turns across all bundles."""
    return min(len(b["history"]) for b in bundles)


def _snapshot_at_turn(bundle: dict, turn: int) -> dict | None:
    """Look up a snapshot by its turn field, not list position."""
    for snap in bundle["history"]:
        if snap["turn"] == turn:
            return snap
    return None


# --- Extractors ---

def extract_stability(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Stability percentiles at checkpoint turns and per-checkpoint zero-rates."""
    max_turn = _min_total_turns(bundles) - 1  # 0-indexed
    cps = _clamp_checkpoints(checkpoints, max_turn)

    percentiles_by_turn: dict[str, dict] = {}
    zero_rate_by_turn: dict[str, float] = {}

    for cp in cps:
        values = []
        zero_count = 0
        total_count = 0
        for bundle in bundles:
            snap = _snapshot_at_turn(bundle, cp)
            if snap is None:
                continue
            for civ_name, civ_data in snap["civ_stats"].items():
                stab = civ_data["stability"]
                values.append(stab)
                total_count += 1
                if stab == 0:
                    zero_count += 1
        if values:
            percentiles_by_turn[str(cp)] = _compute_percentiles(values)
            zero_rate_by_turn[str(cp)] = zero_count / max(1, total_count)

    return {
        "percentiles_by_turn": percentiles_by_turn,
        "zero_rate_by_turn": zero_rate_by_turn,
    }


# --- Firing rate helper ---

def _firing_rate(bundles: list[dict], event_type: str) -> float:
    """Fraction of runs where event_type appears at least once."""
    count = sum(
        1 for b in bundles
        if any(e["event_type"] == event_type for e in b.get("events_timeline", []))
    )
    return count / len(bundles)


# --- Additional Extractors ---

def extract_resources(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Famine turn distribution, trade route and treasury percentiles by turn."""
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)

    # famine_turn_distribution: first famine turn per run
    famine_turns = []
    for b in bundles:
        for e in b.get("events_timeline", []):
            if e["event_type"] == "famine":
                famine_turns.append(e["turn"])
                break

    trade_route_percentiles_by_turn: dict[str, dict] = {}
    treasury_percentiles_by_turn: dict[str, dict] = {}

    for cp in cps:
        trade_values = []
        treasury_values = []
        for bundle in bundles:
            snap = _snapshot_at_turn(bundle, cp)
            if snap is None:
                continue
            trade_values.append(len(snap.get("trade_routes", [])))
            for civ_data in snap["civ_stats"].values():
                treasury_values.append(civ_data.get("treasury", 0))
        if trade_values:
            trade_route_percentiles_by_turn[str(cp)] = _compute_percentiles(trade_values)
        if treasury_values:
            treasury_percentiles_by_turn[str(cp)] = _compute_percentiles(treasury_values)

    return {
        "famine_turn_distribution": _compute_percentiles(famine_turns),
        "trade_route_percentiles_by_turn": trade_route_percentiles_by_turn,
        "treasury_percentiles_by_turn": treasury_percentiles_by_turn,
    }


def extract_politics(bundles: list[dict]) -> dict:
    """Firing rates for political events and elimination turn distribution."""
    political_event_types = [
        "war", "secession", "federation_formed", "vassal_imposed",
        "mercenary_spawned", "twilight_absorption",
    ]
    result: dict = {}
    for et in political_event_types:
        result[f"{et}_rate"] = _firing_rate(bundles, et)

    # elimination_turn_distribution: first turn where any civ's alive is False
    elimination_turns = []
    for b in bundles:
        for snap in b["history"]:
            for civ_data in snap["civ_stats"].values():
                if not civ_data.get("alive", True):
                    elimination_turns.append(snap["turn"])
                    break
            else:
                continue
            break

    result["elimination_turn_distribution"] = _compute_percentiles(elimination_turns)
    return result


def extract_climate(bundles: list[dict]) -> dict:
    """Disaster frequency by type."""
    disaster_types = {"drought", "plague", "earthquake", "flood", "wildfire", "sandstorm"}
    disaster_frequency_by_type: dict[str, float] = {}
    n = len(bundles)
    for dtype in disaster_types:
        count = sum(
            1 for b in bundles
            if any(e["event_type"] == dtype for e in b.get("events_timeline", []))
        )
        disaster_frequency_by_type[dtype] = count / n
    return {"disaster_frequency_by_type": disaster_frequency_by_type}


def extract_memetic(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Movement count percentiles by turn and memetic firing rates."""
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)

    movement_count_percentiles_by_turn: dict[str, dict] = {}
    for cp in cps:
        values = []
        for bundle in bundles:
            snap = _snapshot_at_turn(bundle, cp)
            if snap is None:
                continue
            values.append(len(snap.get("movements_summary", [])))
        if values:
            movement_count_percentiles_by_turn[str(cp)] = _compute_percentiles(values)

    return {
        "movement_count_percentiles_by_turn": movement_count_percentiles_by_turn,
        "paradigm_shift_rate": _firing_rate(bundles, "paradigm_shift"),
        "assimilation_rate": _firing_rate(bundles, "cultural_assimilation"),
    }


def extract_great_persons(bundles: list[dict]) -> dict:
    """Firing rates for great person and succession events."""
    event_types = ["great_person_born", "tradition_acquired", "succession_crisis", "hostage_taken"]
    return {f"{et}_rate": _firing_rate(bundles, et) for et in event_types}


def extract_emergence(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Black swan frequencies, regression/terrain rates, stress percentiles by turn."""
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)
    n = len(bundles)

    black_swan_types = ["pandemic", "supervolcano", "resource_discovery", "tech_accident"]
    black_swan_frequency_by_type: dict[str, float] = {}
    for bst in black_swan_types:
        count = sum(
            1 for b in bundles
            if any(e["event_type"] == bst for e in b.get("events_timeline", []))
        )
        black_swan_frequency_by_type[bst] = count / n

    stress_percentiles_by_turn: dict[str, dict] = {}
    for cp in cps:
        values = []
        for bundle in bundles:
            snap = _snapshot_at_turn(bundle, cp)
            if snap is None:
                continue
            si = snap.get("stress_index")
            if si is not None:
                values.append(si)
        if values:
            stress_percentiles_by_turn[str(cp)] = _compute_percentiles(values)

    return {
        "black_swan_frequency_by_type": black_swan_frequency_by_type,
        "regression_rate": _firing_rate(bundles, "tech_regression"),
        "terrain_transition_rate": _firing_rate(bundles, "terrain_transition"),
        "stress_percentiles_by_turn": stress_percentiles_by_turn,
    }


def extract_general(bundles: list[dict]) -> dict:
    """Era distribution, median era, civs alive, first war turn, action diversity."""
    n = len(bundles)

    # era_distribution_at_final and median_era_at_final
    era_counts: dict[str, int] = {}
    era_ordinals: list[int] = []
    for b in bundles:
        last_snap = b["history"][-1]
        for civ_data in last_snap["civ_stats"].values():
            era = civ_data.get("tech_era", "tribal")
            era_counts[era] = era_counts.get(era, 0) + 1
            if era in ERA_ORDER:
                era_ordinals.append(ERA_ORDER.index(era))
    total_era_entries = sum(era_counts.values())
    era_distribution_at_final = {
        era: count / total_era_entries for era, count in era_counts.items()
    } if total_era_entries else {}

    if era_ordinals:
        med_ordinal = statistics.median(era_ordinals)
        # Round to nearest int to map back to era name
        median_era_at_final = ERA_ORDER[round(med_ordinal)]
    else:
        median_era_at_final = "tribal"

    # civs_alive_at_end
    civs_alive_counts = []
    for b in bundles:
        last_snap = b["history"][-1]
        alive_count = sum(
            1 for civ_data in last_snap["civ_stats"].values()
            if civ_data.get("alive", False)
        )
        civs_alive_counts.append(alive_count)

    # first_war_turn_distribution
    first_war_turns = []
    for b in bundles:
        for e in b.get("events_timeline", []):
            if e["event_type"] == "war":
                first_war_turns.append(e["turn"])
                break

    # action_diversity_median: distinct action types per civ, then median
    action_diversities = []
    for b in bundles:
        for civ_entry in b.get("world_state", {}).get("civilizations", []):
            ac = civ_entry.get("action_counts", {})
            action_diversities.append(len(ac))
    action_diversity_median = statistics.median(action_diversities) if action_diversities else 0

    return {
        "era_distribution_at_final": era_distribution_at_final,
        "median_era_at_final": median_era_at_final,
        "civs_alive_at_end": _compute_percentiles(civs_alive_counts),
        "first_war_turn_distribution": _compute_percentiles(first_war_turns),
        "action_diversity_median": action_diversity_median,
    }


# --- Task 9: Anomaly Detection and Event Firing Rates ---

EXPECTED_EVENT_TYPES = {
    "famine", "embargo", "war", "secession", "collapse", "mercenary_spawned",
    "vassal_imposed", "federation_formed", "proxy_war_started", "twilight_absorption",
    "drought", "plague", "earthquake", "flood", "migration",
    "movement_emerged", "paradigm_shift", "cultural_assimilation",
    "great_person_born", "tradition_acquired", "succession_crisis",
    "hostage_taken", "rivalry_formed", "folk_hero_created",
    "pandemic", "supervolcano", "resource_discovery", "tech_accident",
    "tech_regression", "terrain_transition",
    "tech_advancement", "rebellion",
}


def compute_event_firing_rates(bundles: list[dict]) -> dict[str, float]:
    """Discover event types from data and compute firing rates."""
    n_runs = len(bundles)
    type_run_sets: dict[str, set[int]] = {}
    for i, bundle in enumerate(bundles):
        for event in bundle.get("events_timeline", []):
            et = event["event_type"]
            if et not in type_run_sets:
                type_run_sets[et] = set()
            type_run_sets[et].add(i)
    return {et: len(runs) / n_runs for et, runs in sorted(type_run_sets.items())}


def detect_anomalies(report: dict) -> list[dict]:
    """Run anomaly checks against a completed report."""
    anomalies = []

    # Degenerate pattern: stability collapse (worst checkpoint zero rate)
    zero_rates = report.get("stability", {}).get("zero_rate_by_turn", {})
    if zero_rates:
        worst_cp = max(zero_rates, key=zero_rates.get)
        worst_rate = zero_rates[worst_cp]
        if worst_rate > 0.4:
            anomalies.append({
                "name": "stability_collapse", "severity": "CRITICAL",
                "detail": f"{worst_rate:.0%} of civs at stability 0 at turn {worst_cp}",
            })

    # Degenerate pattern: universal famine
    famine_rate = report.get("event_firing_rates", {}).get("famine", 0)
    if famine_rate > 0.95:
        anomalies.append({
            "name": "universal_famine", "severity": "CRITICAL",
            "detail": f"Famine fires in {famine_rate:.0%} of runs",
        })

    # Degenerate pattern: no late game
    median_era = report.get("general", {}).get("median_era_at_final", "medieval")
    if ERA_ORDER.index(median_era.lower()) < ERA_ORDER.index("medieval"):
        anomalies.append({
            "name": "no_late_game", "severity": "WARNING",
            "detail": f"Median era at final turn is {median_era}",
        })

    # Never-fire: event types with < 5% rate (discovered from data)
    firing_rates = report.get("event_firing_rates", {})
    for et, rate in firing_rates.items():
        if rate < 0.05:
            anomalies.append({
                "name": "never_fire", "severity": "WARNING",
                "detail": f"{et} fired in {rate:.0%} of runs",
            })

    # Safety net: expected types completely absent from all bundles
    present_types = set(firing_rates.keys())
    for et in sorted(EXPECTED_EVENT_TYPES - present_types):
        anomalies.append({
            "name": "never_fire", "severity": "CRITICAL",
            "detail": f"{et} absent from all runs (0 events across all bundles)",
        })

    return anomalies
