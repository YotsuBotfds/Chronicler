"""Post-processing analytics pipeline — reads bundles, computes metrics."""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime
from pathlib import Path

ERA_ORDER = [
    "tribal", "bronze", "iron", "classical", "medieval",
    "renaissance", "industrial", "information",
]

# All focus names across all eras (for capability event types)
ALL_FOCUS_NAMES = [
    "navigation", "metallurgy", "agriculture",
    "fortification", "commerce", "scholarship",
    "exploration", "banking", "printing",
    "mechanization", "railways", "naval_power",
    "networks", "surveillance", "media",
]

# ERA_FOCUSES mapping for valid focus names per era
ERA_FOCUSES_MAP: dict[str, list[str]] = {
    "classical": ["navigation", "metallurgy", "agriculture"],
    "medieval": ["fortification", "commerce", "scholarship"],
    "renaissance": ["exploration", "banking", "printing"],
    "industrial": ["mechanization", "railways", "naval_power"],
    "information": ["networks", "surveillance", "media"],
}


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
    """Fraction of runs where event_type appears at least once (events + named_events)."""
    count = sum(
        1 for b in bundles
        if any(e["event_type"] == event_type for e in b.get("events_timeline", []))
        or any(e["event_type"] == event_type for e in b.get("named_events", []))
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


def extract_stockpiles(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Per-region per-good stockpile levels at checkpoints.

    Returns: {region_name: {good_name: {turn: level}}}
    """
    if not bundles:
        return {}
    bundle = bundles[0]
    if checkpoints is None:
        checkpoints = [50, 100, 200, 300, 400, 500]

    result: dict[str, dict[str, dict[int, float]]] = {}
    for turn in checkpoints:
        snapshot = _snapshot_at_turn(bundle, turn)
        if snapshot is None:
            continue
        for region_data in snapshot.get("world_state", {}).get("regions", []):
            rname = region_data.get("name", "")
            stockpile = region_data.get("stockpile", {}).get("goods", {})
            if rname not in result:
                result[rname] = {}
            for good, amount in stockpile.items():
                if good not in result[rname]:
                    result[rname][good] = {}
                result[rname][good][turn] = amount
    return result


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


# --- M22 Extractors ---

def _shannon_entropy(counts: dict[str, int]) -> float:
    """Compute Shannon entropy (log base 2) from a dict of counts.

    Handles edge cases: empty dict -> 0, single action -> 0,
    and the convention 0 * log(0) = 0.
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        if count <= 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def extract_focus_distribution(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Criterion 6: Focus distribution per era.

    At each checkpoint, for each alive civ, record (tech_era, active_focus).
    Group by era, count focuses within each era.
    Only include eras with >= 3 civs having a focus.
    """
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)

    # era -> {focus -> count}
    era_focus_counts: dict[str, dict[str, int]] = {}
    # era -> total civs with a focus
    era_total: dict[str, int] = {}

    for cp in cps:
        for bundle in bundles:
            snap = _snapshot_at_turn(bundle, cp)
            if snap is None:
                continue
            for civ_data in snap["civ_stats"].values():
                if not civ_data.get("alive", True):
                    continue
                era = civ_data.get("tech_era")
                focus = civ_data.get("active_focus")
                if era is None or focus is None:
                    continue
                if era not in era_focus_counts:
                    era_focus_counts[era] = {}
                    era_total[era] = 0
                era_focus_counts[era][focus] = era_focus_counts[era].get(focus, 0) + 1
                era_total[era] += 1

    # Build result: only include eras with >= 3 civs having a focus
    result: dict[str, dict[str, float]] = {}
    for era, focus_counts in era_focus_counts.items():
        total = era_total[era]
        if total < 3:
            continue
        result[era] = {focus: count / total for focus, count in focus_counts.items()}

    return result


def extract_focus_geography(bundles: list[dict]) -> dict:
    """Criterion 7: Focus-geography correlation.

    From world_state.regions, classify each alive civ as coastal/landlocked
    and mountain/non-mountain. Compute navigation/metallurgy rates by geography.
    """
    coastal_nav = 0
    coastal_no_nav = 0
    non_coastal_nav = 0
    non_coastal_no_nav = 0
    mountain_met = 0
    mountain_no_met = 0
    non_mountain_met = 0
    non_mountain_no_met = 0

    for bundle in bundles:
        regions = bundle.get("world_state", {}).get("regions", [])
        # Build controller -> set of terrains
        civ_terrains: dict[str, set[str]] = {}
        for region in regions:
            ctrl = region.get("controller")
            if ctrl is None:
                continue
            if ctrl not in civ_terrains:
                civ_terrains[ctrl] = set()
            terrain = region.get("terrain", "")
            civ_terrains[ctrl].add(terrain)

        # Get the final snapshot for alive check and active_focus
        last_snap = bundle["history"][-1]
        for civ_name, civ_data in last_snap["civ_stats"].items():
            if not civ_data.get("alive", True):
                continue
            terrains = civ_terrains.get(civ_name, set())
            focus = civ_data.get("active_focus")
            is_coastal = "coast" in terrains
            is_mountain = "mountains" in terrains

            # Navigation correlation
            if is_coastal:
                if focus == "navigation":
                    coastal_nav += 1
                else:
                    coastal_no_nav += 1
            else:
                if focus == "navigation":
                    non_coastal_nav += 1
                else:
                    non_coastal_no_nav += 1

            # Metallurgy correlation
            if is_mountain:
                if focus == "metallurgy":
                    mountain_met += 1
                else:
                    mountain_no_met += 1
            else:
                if focus == "metallurgy":
                    non_mountain_met += 1
                else:
                    non_mountain_no_met += 1

    coastal_total = coastal_nav + coastal_no_nav
    non_coastal_total = non_coastal_nav + non_coastal_no_nav
    mountain_total = mountain_met + mountain_no_met
    non_mountain_total = non_mountain_met + non_mountain_no_met

    return {
        "coastal_navigation_rate": coastal_nav / max(1, coastal_total),
        "non_coastal_navigation_rate": non_coastal_nav / max(1, non_coastal_total),
        "mountain_metallurgy_rate": mountain_met / max(1, mountain_total),
        "non_mountain_metallurgy_rate": non_mountain_met / max(1, non_mountain_total),
    }


def extract_action_entropy(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Criterion 8: Action selection entropy per civ per era.

    For each civ, find turns where tech_era changes (era transitions).
    Compute per-era action counts by diffing cumulative counts between transitions.
    Shannon entropy per era block, then aggregate via percentiles.
    """
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)

    # era -> list of entropy values
    entropy_by_era: dict[str, list[float]] = {}
    all_entropies: list[float] = []

    for bundle in bundles:
        history = bundle["history"]
        if not history:
            continue

        # Get all civ names from first snapshot
        first_snap = history[0]
        civ_names = list(first_snap.get("civ_stats", {}).keys())

        for civ_name in civ_names:
            # Collect (turn, era, action_counts) for this civ across all snapshots
            civ_timeline: list[tuple[int, str, dict[str, int]]] = []
            for snap in history:
                civ_data = snap.get("civ_stats", {}).get(civ_name)
                if civ_data is None or not civ_data.get("alive", True):
                    continue
                turn = snap["turn"]
                era = civ_data.get("tech_era", "tribal")
                ac = civ_data.get("action_counts", {})
                civ_timeline.append((turn, era, ac))

            if not civ_timeline:
                continue

            # Identify era blocks: find where era changes
            era_blocks: list[tuple[str, dict[str, int], dict[str, int]]] = []
            block_start_era = civ_timeline[0][1]
            block_start_ac = civ_timeline[0][2]

            for i in range(1, len(civ_timeline)):
                _, era, ac = civ_timeline[i]
                if era != block_start_era:
                    # Close the previous block
                    era_blocks.append((block_start_era, block_start_ac, civ_timeline[i - 1][2]))
                    block_start_era = era
                    block_start_ac = ac
            # Close the final block
            era_blocks.append((block_start_era, block_start_ac, civ_timeline[-1][2]))

            for era, start_ac, end_ac in era_blocks:
                # Diff cumulative counts to get per-era counts
                all_keys = set(start_ac.keys()) | set(end_ac.keys())
                era_counts: dict[str, int] = {}
                for key in all_keys:
                    diff = end_ac.get(key, 0) - start_ac.get(key, 0)
                    if diff > 0:
                        era_counts[key] = diff

                if not era_counts:
                    continue

                h = _shannon_entropy(era_counts)
                if era not in entropy_by_era:
                    entropy_by_era[era] = []
                entropy_by_era[era].append(h)
                all_entropies.append(h)

    return {
        "entropy_by_era": {era: _compute_percentiles(vals) for era, vals in entropy_by_era.items()},
        "overall_median": statistics.median(all_entropies) if all_entropies else 0.0,
    }


def extract_capability_firing(bundles: list[dict]) -> dict:
    """Criterion 9: Focus capability firing rates.

    For each capability name, compute:
    - How many runs had a civ with that focus for 20+ consecutive turns (denominator)
    - How many of those runs had at least one capability_{name} event (numerator)
    """
    result: dict[str, dict[str, int | float]] = {}

    for focus_name in ALL_FOCUS_NAMES:
        eligible_runs = 0
        fired_runs = 0

        for bundle in bundles:
            history = bundle["history"]
            if not history:
                continue

            # Check if any civ had this focus for 20+ consecutive turns
            civ_names: set[str] = set()
            for snap in history:
                civ_names.update(snap.get("civ_stats", {}).keys())

            run_has_eligible_civ = False
            for civ_name in civ_names:
                consecutive = 0
                max_consecutive = 0
                for snap in history:
                    civ_data = snap.get("civ_stats", {}).get(civ_name)
                    if civ_data is None or not civ_data.get("alive", True):
                        consecutive = 0
                        continue
                    if civ_data.get("active_focus") == focus_name:
                        consecutive += 1
                        if consecutive > max_consecutive:
                            max_consecutive = consecutive
                    else:
                        consecutive = 0
                if max_consecutive >= 20:
                    run_has_eligible_civ = True
                    break

            if not run_has_eligible_civ:
                continue

            eligible_runs += 1

            # Check if this run has a capability_{focus_name} event
            event_type = f"capability_{focus_name}"
            has_event = (
                any(e["event_type"] == event_type for e in bundle.get("events_timeline", []))
                or any(e["event_type"] == event_type for e in bundle.get("named_events", []))
            )
            if has_event:
                fired_runs += 1

        result[focus_name] = {
            "eligible_runs": eligible_runs,
            "fired_runs": fired_runs,
            "rate": fired_runs / max(1, eligible_runs),
        }

    return result


def extract_faction_dominance(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Criteria 10, 11, 18: Faction dominance distribution.

    At each checkpoint, for each alive civ, determine dominant faction
    (highest influence). Count distribution across all civs.
    """
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)

    by_checkpoint: dict[str, dict[str, float | int]] = {}

    for cp in cps:
        faction_counts: dict[str, int] = {}
        sample_size = 0

        for bundle in bundles:
            snap = _snapshot_at_turn(bundle, cp)
            if snap is None:
                continue
            for civ_data in snap["civ_stats"].values():
                if not civ_data.get("alive", True):
                    continue
                factions = civ_data.get("factions")
                if factions is None:
                    continue
                influence = factions.get("influence")
                if not influence:
                    continue
                # Find dominant faction (highest influence value)
                dominant = max(influence, key=influence.get)
                # Normalize to uppercase for consistency
                dominant_upper = dominant.upper()
                faction_counts[dominant_upper] = faction_counts.get(dominant_upper, 0) + 1
                sample_size += 1

        if sample_size > 0:
            entry: dict[str, float | int] = {}
            for faction_name in ["MILITARY", "MERCHANT", "CULTURAL"]:
                entry[faction_name] = faction_counts.get(faction_name, 0) / sample_size
            entry["sample_size"] = sample_size
            by_checkpoint[str(cp)] = entry

    return {"by_checkpoint": by_checkpoint}


def extract_power_struggles(bundles: list[dict]) -> dict:
    """Criteria 12, 13: Power struggle frequency and resolution balance.

    Per-civ frequency: fraction of civs alive 100+ turns that had >= 1 struggle.
    Resolution balance: which faction won resolved power struggles.
    """
    # Per-civ rate: civs alive 100+ turns that had >= 1 power_struggle_started
    civs_alive_100_plus = 0
    civs_with_struggle = 0

    # Resolution balance
    resolution_faction_counts: dict[str, int] = {}
    total_resolutions = 0

    for bundle in bundles:
        history = bundle["history"]
        events = bundle.get("events_timeline", [])

        # Build per-civ alive turn counts
        civ_alive_turns: dict[str, int] = {}
        for snap in history:
            for civ_name, civ_data in snap.get("civ_stats", {}).items():
                if civ_data.get("alive", True):
                    civ_alive_turns[civ_name] = civ_alive_turns.get(civ_name, 0) + 1

        # Find civs alive 100+ turns
        long_lived_civs = {name for name, turns in civ_alive_turns.items() if turns >= 100}
        civs_alive_100_plus += len(long_lived_civs)

        # Check power_struggle_started events for each long-lived civ
        struggle_civs: set[str] = set()
        for e in events:
            if e["event_type"] == "power_struggle_started":
                for actor in e.get("actors", []):
                    if actor in long_lived_civs:
                        struggle_civs.add(actor)
        civs_with_struggle += len(struggle_civs)

        # Resolution balance: power_struggle_resolved events
        for e in events:
            if e["event_type"] != "power_struggle_resolved":
                continue
            total_resolutions += 1
            # Try to determine winning faction from description or actors
            desc = e.get("description", "").lower()
            actors = e.get("actors", [])
            winning_faction = None
            for faction_name in ["military", "merchant", "cultural"]:
                if faction_name in desc:
                    winning_faction = faction_name.upper()
                    break
            if winning_faction is None:
                # Check actors list for faction names
                for actor in actors:
                    actor_lower = actor.lower()
                    for faction_name in ["military", "merchant", "cultural"]:
                        if faction_name in actor_lower:
                            winning_faction = faction_name.upper()
                            break
                    if winning_faction is not None:
                        break
            if winning_faction is not None:
                resolution_faction_counts[winning_faction] = (
                    resolution_faction_counts.get(winning_faction, 0) + 1
                )

    per_civ_rate = civs_with_struggle / max(1, civs_alive_100_plus)

    # Build resolution balance as fractions
    resolution_balance: dict[str, float] = {}
    resolved_with_faction = sum(resolution_faction_counts.values())
    for faction_name in ["MILITARY", "MERCHANT", "CULTURAL"]:
        resolution_balance[faction_name] = (
            resolution_faction_counts.get(faction_name, 0) / max(1, resolved_with_faction)
        )

    return {
        "per_civ_rate": per_civ_rate,
        "per_civ_sample_size": civs_alive_100_plus,
        "resolution_balance": resolution_balance,
        "total_resolutions": total_resolutions,
    }


def extract_faction_succession(bundles: list[dict]) -> dict:
    """Criterion 14: Faction-succession correlation.

    Find cases where succession_crisis_resolved occurs during or shortly after
    (within 5 turns) a power_struggle_resolved event for the same civ.
    Check if winning faction's influence increased by >= 0.10.
    """
    qualifying = 0
    influence_increased = 0

    for bundle in bundles:
        events = bundle.get("events_timeline", [])
        history = bundle["history"]

        # Index power_struggle_resolved events by (civ, turn)
        power_resolved: list[tuple[str, int]] = []
        for e in events:
            if e["event_type"] == "power_struggle_resolved":
                for actor in e.get("actors", []):
                    power_resolved.append((actor, e["turn"]))

        # Find succession_crisis_resolved events
        for e in events:
            if e["event_type"] != "succession_crisis_resolved":
                continue
            succ_turn = e["turn"]
            succ_actors = set(e.get("actors", []))

            for civ_name, pr_turn in power_resolved:
                if civ_name not in succ_actors:
                    continue
                if not (pr_turn <= succ_turn <= pr_turn + 5):
                    continue

                # Found a qualifying case
                qualifying += 1

                # Compare factions before and after the succession turn.
                # Off-by-one: run_turn increments world.turn after processing,
                # so events at turn T produce snapshot labeled turn T+1.
                # snap(T) = state BEFORE turn T's phases; snap(T+1) = state AFTER.
                snap_before = _snapshot_at_turn(bundle, succ_turn)
                snap_after = _snapshot_at_turn(bundle, succ_turn + 1)
                if snap_before is None or snap_after is None:
                    continue

                civ_before = snap_before.get("civ_stats", {}).get(civ_name)
                civ_after = snap_after.get("civ_stats", {}).get(civ_name)
                if civ_before is None or civ_after is None:
                    continue

                factions_before = civ_before.get("factions")
                factions_after = civ_after.get("factions")
                if factions_before is None or factions_after is None:
                    continue

                inf_before = factions_before.get("influence", {})
                inf_after = factions_after.get("influence", {})

                # Find the dominant faction after resolution
                if not inf_after:
                    continue
                dominant = max(inf_after, key=inf_after.get)
                before_val = inf_before.get(dominant, 0.0)
                after_val = inf_after.get(dominant, 0.0)
                if after_val - before_val >= 0.10:
                    influence_increased += 1

                break  # Only count first matching power_struggle for this succession

    return {
        "correlation_rate": influence_increased / max(1, qualifying),
        "sample_size": qualifying,
    }


def extract_population(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Criterion 15: Population and secession viability.

    At each checkpoint, for alive civs: collect population values.
    Compute fraction with population < 10 (low capacity).
    """
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)

    population_by_checkpoint: dict[str, dict] = {}
    low_capacity_rate: dict[str, float] = {}

    for cp in cps:
        pop_values: list[int] = []
        low_count = 0
        total_count = 0

        for bundle in bundles:
            snap = _snapshot_at_turn(bundle, cp)
            if snap is None:
                continue
            for civ_data in snap["civ_stats"].values():
                if not civ_data.get("alive", True):
                    continue
                pop = civ_data.get("population", 0)
                pop_values.append(pop)
                total_count += 1
                if pop < 10:
                    low_count += 1

        if pop_values:
            population_by_checkpoint[str(cp)] = _compute_percentiles(pop_values)
            low_capacity_rate[str(cp)] = low_count / max(1, total_count)

    return {
        "population_by_checkpoint": population_by_checkpoint,
        "low_capacity_rate": low_capacity_rate,
    }


def extract_precap_weights(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Criterion 17: Pre-cap weight distribution and cap firing rate.

    At each checkpoint, collect max_precap_weight values from all alive civs.
    Compute median, fraction where max_precap_weight > 2.5 (cap fires).
    """
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)

    all_precap_values: list[float] = []
    cap_fire_count = 0
    total_entries = 0

    for cp in cps:
        for bundle in bundles:
            snap = _snapshot_at_turn(bundle, cp)
            if snap is None:
                continue
            for civ_data in snap["civ_stats"].values():
                if not civ_data.get("alive", True):
                    continue
                weight = civ_data.get("max_precap_weight", 0.0)
                all_precap_values.append(weight)
                total_entries += 1
                if weight > 2.5:
                    cap_fire_count += 1

    return {
        "median_precap_weight": statistics.median(all_precap_values) if all_precap_values else 0.0,
        "cap_fire_rate": cap_fire_count / max(1, total_entries),
        "percentiles": _compute_percentiles(all_precap_values),
    }


def extract_action_persistence(bundles: list[dict]) -> dict:
    """Criterion 19: Top-action persistence over 100-turn windows.

    For each civ, look at 100-turn windows (0-99, 100-199, etc.).
    In each window, find most frequent action via action_counts diffs.
    Compute fraction of turns the top action was chosen.
    """
    max_persistence_values: list[float] = []
    civs_above_80pct = 0
    total_civ_windows = 0

    for bundle in bundles:
        history = bundle["history"]
        if not history:
            continue

        max_turn = history[-1]["turn"]
        civ_names: set[str] = set()
        for snap in history:
            civ_names.update(snap.get("civ_stats", {}).keys())

        for civ_name in civ_names:
            # Build turn -> action_counts mapping for this civ
            civ_snapshots: dict[int, dict[str, int]] = {}
            for snap in history:
                civ_data = snap.get("civ_stats", {}).get(civ_name)
                if civ_data is None or not civ_data.get("alive", True):
                    continue
                civ_snapshots[snap["turn"]] = civ_data.get("action_counts", {})

            # Process 100-turn windows
            window_start = 0
            while window_start <= max_turn:
                window_end = window_start + 99

                # Find closest available snapshots to window boundaries
                start_ac = None
                end_ac = None
                for t in range(window_start, min(window_end + 1, max_turn + 1)):
                    if t in civ_snapshots:
                        start_ac = civ_snapshots[t]
                        break
                for t in range(min(window_end, max_turn), window_start - 1, -1):
                    if t in civ_snapshots:
                        end_ac = civ_snapshots[t]
                        break

                if start_ac is not None and end_ac is not None:
                    # Diff cumulative counts
                    all_keys = set(start_ac.keys()) | set(end_ac.keys())
                    window_counts: dict[str, int] = {}
                    for key in all_keys:
                        diff = end_ac.get(key, 0) - start_ac.get(key, 0)
                        if diff > 0:
                            window_counts[key] = diff

                    total_actions = sum(window_counts.values())
                    if total_actions > 0:
                        top_action_count = max(window_counts.values())
                        persistence = top_action_count / total_actions
                        max_persistence_values.append(persistence)
                        total_civ_windows += 1
                        if persistence > 0.80:
                            civs_above_80pct += 1

                window_start += 100

    return {
        "max_persistence_by_window": _compute_percentiles(max_persistence_values),
        "civs_above_80pct": civs_above_80pct / max(1, total_civ_windows),
    }


def extract_new_event_types(bundles: list[dict]) -> dict:
    """Criterion 16: Firing rates for M22-specific event types."""
    return {
        "power_struggle_started_rate": _firing_rate(bundles, "power_struggle_started"),
        "power_struggle_resolved_rate": _firing_rate(bundles, "power_struggle_resolved"),
        "faction_dominance_shift_rate": _firing_rate(bundles, "faction_dominance_shift"),
    }


# --- Task 9: Anomaly Detection and Event Firing Rates ---

EXPECTED_EVENT_TYPES = {
    "famine", "embargo", "war", "secession", "collapse", "mercenary_spawned",
    "federation_formed", "twilight_absorption",
    "drought", "plague", "earthquake", "flood", "migration",
    "movement_emergence", "paradigm_shift", "cultural_assimilation",
    "great_person_born", "tradition_acquired", "succession_crisis",
    "hostage_taken", "rivalry_formed", "folk_hero_created",
    "pandemic", "supervolcano", "tech_accident",
    "tech_regression", "terrain_transition",
    "tech_advancement", "rebellion",
    # M22 event types
    "power_struggle_started", "power_struggle_resolved", "faction_dominance_shift",
    # Capability event types
    "capability_navigation", "capability_metallurgy", "capability_agriculture",
    "capability_fortification", "capability_commerce", "capability_scholarship",
    "capability_exploration", "capability_banking", "capability_printing",
    "capability_mechanization", "capability_railways", "capability_naval_power",
    "capability_networks", "capability_surveillance", "capability_media",
}


def compute_event_firing_rates(bundles: list[dict]) -> dict[str, float]:
    """Discover event types from data and compute firing rates.

    Scans both events_timeline and named_events to capture all event types.
    """
    n_runs = len(bundles)
    type_run_sets: dict[str, set[int]] = {}
    for i, bundle in enumerate(bundles):
        for event in bundle.get("events_timeline", []):
            et = event["event_type"]
            if et not in type_run_sets:
                type_run_sets[et] = set()
            type_run_sets[et].add(i)
        for event in bundle.get("named_events", []):
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

    # Universal famine: warn at 98%+ (famine over 500 turns is historically normal)
    famine_rate = report.get("event_firing_rates", {}).get("famine", 0)
    if famine_rate > 0.98:
        anomalies.append({
            "name": "near_universal_famine", "severity": "WARNING",
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

    # M22: Faction dominance where one faction > 50% at turn 100
    faction_dom = report.get("faction_dominance", {}).get("by_checkpoint", {})
    cp100 = faction_dom.get("100", {})
    for faction_name in ["MILITARY", "MERCHANT", "CULTURAL"]:
        frac = cp100.get(faction_name, 0)
        if frac > 0.50:
            anomalies.append({
                "name": "faction_dominance_skew", "severity": "WARNING",
                "detail": f"{faction_name} dominant in {frac:.0%} of civs at turn 100",
            })

    # M22: Power struggle rate anomalies
    ps = report.get("power_struggles", {})
    ps_rate = ps.get("per_civ_rate", 0)
    if ps_rate < 0.05:
        anomalies.append({
            "name": "power_struggle_too_rare", "severity": "WARNING",
            "detail": f"Power struggle per-civ rate is {ps_rate:.0%} (< 5%)",
        })
    elif ps_rate > 0.40:
        anomalies.append({
            "name": "power_struggle_too_frequent", "severity": "WARNING",
            "detail": f"Power struggle per-civ rate is {ps_rate:.0%} (> 40%)",
        })

    # M22: Cap fire rate anomalies
    precap = report.get("precap_weights", {})
    cap_rate = precap.get("cap_fire_rate", 0)
    if cap_rate < 0.05:
        anomalies.append({
            "name": "cap_fire_too_rare", "severity": "WARNING",
            "detail": f"Pre-cap weight cap fires in {cap_rate:.0%} of entries (< 5%)",
        })
    elif cap_rate > 0.50:
        anomalies.append({
            "name": "cap_fire_too_frequent", "severity": "WARNING",
            "detail": f"Pre-cap weight cap fires in {cap_rate:.0%} of entries (> 50%)",
        })

    return anomalies


# --- Task 10: Report Assembly and Text Formatter ---

def generate_report(
    batch_dir: Path,
    checkpoints: list[int] | None = None,
) -> dict:
    """Load bundles, run all extractors, run anomaly checks, return composite report."""
    bundles = load_bundles(batch_dir)
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)

    seeds = [b["metadata"]["seed"] for b in bundles]
    metadata = {
        "runs": len(bundles),
        "turns_per_run": max_turn + 1,
        "seed_range": [min(seeds), max(seeds)],
        "checkpoints": cps,
        "timestamp": datetime.now().isoformat(),
        "version": "post-M18",
        "report_schema_version": 1,
        "tuning_file": None,
    }

    stability = extract_stability(bundles, checkpoints=cps)
    resources = extract_resources(bundles, checkpoints=cps)
    politics = extract_politics(bundles)
    climate = extract_climate(bundles)
    memetic = extract_memetic(bundles, checkpoints=cps)
    great_persons = extract_great_persons(bundles)
    emergence = extract_emergence(bundles, checkpoints=cps)
    general = extract_general(bundles)
    firing_rates = compute_event_firing_rates(bundles)

    # M22 extractors
    focus_distribution = extract_focus_distribution(bundles, checkpoints=cps)
    focus_geography = extract_focus_geography(bundles)
    action_entropy = extract_action_entropy(bundles, checkpoints=cps)
    capability_firing = extract_capability_firing(bundles)
    faction_dominance = extract_faction_dominance(bundles, checkpoints=cps)
    power_struggles = extract_power_struggles(bundles)
    faction_succession = extract_faction_succession(bundles)
    population = extract_population(bundles, checkpoints=cps)
    precap_weights = extract_precap_weights(bundles, checkpoints=cps)
    action_persistence = extract_action_persistence(bundles)
    new_event_types = extract_new_event_types(bundles)
    artifacts = extract_artifacts(bundles)

    report = {
        "metadata": metadata,
        "stability": stability,
        "resources": resources,
        "politics": politics,
        "climate": climate,
        "memetic": memetic,
        "great_persons": great_persons,
        "emergence": emergence,
        "general": general,
        "event_firing_rates": firing_rates,
        # M22 sections
        "focus_distribution": focus_distribution,
        "focus_geography": focus_geography,
        "action_entropy": action_entropy,
        "capability_firing": capability_firing,
        "faction_dominance": faction_dominance,
        "power_struggles": power_struggles,
        "faction_succession": faction_succession,
        "population": population,
        "precap_weights": precap_weights,
        "action_persistence": action_persistence,
        "new_event_types": new_event_types,
        "artifacts": artifacts,
    }

    report["anomalies"] = detect_anomalies(report)
    return report


def format_text_report(report: dict) -> str:
    """Format full analytics report as grep-friendly plain text."""
    lines = []
    meta = report["metadata"]
    n_runs = meta["runs"]
    lines.append(f"ANALYTICS REPORT — {n_runs} runs, {meta['turns_per_run']} turns each")
    lines.append(f"Seeds: {meta['seed_range'][0]}-{meta['seed_range'][1]}")
    lines.append(f"Checkpoints: {meta['checkpoints']}")
    lines.append("")

    # Stability
    stab = report.get("stability", {})
    lines.append("STABILITY:")
    for cp, pcts in stab.get("percentiles_by_turn", {}).items():
        lines.append(f"  turn {cp}:  median={pcts['median']}, p10={pcts['p10']}, p90={pcts['p90']}")
    for cp, zr in stab.get("zero_rate_by_turn", {}).items():
        if zr > 0:
            flag = "  ← CRITICAL" if zr > 0.4 else ""
            lines.append(f"  Zero-stability rate at turn {cp}: {zr:.0%}{flag}")
    lines.append("")

    # Resources
    res = report.get("resources", {})
    famine_dist = res.get("famine_turn_distribution", {})
    if famine_dist:
        lines.append(f"Famine:     first occurrence median turn {famine_dist.get('median', '?')}")
    for cp, pcts in res.get("trade_route_percentiles_by_turn", {}).items():
        lines.append(f"Trade routes at turn {cp}: median={pcts.get('median', 0)}")
    lines.append("")

    # Politics
    pol = report.get("politics", {})
    for key in ["war_rate", "secession_rate", "federation_rate", "vassal_rate", "mercenary_rate", "twilight_rate"]:
        rate = pol.get(key, 0)
        if rate > 0:
            count = int(rate * n_runs)
            label = key.replace("_rate", "").title()
            flag = "  ← EVERY RUN" if rate >= 1.0 else ""
            lines.append(f"{label}: {count}/{n_runs} ({rate:.0%}){flag}")
    lines.append("")

    # Climate
    clim = report.get("climate", {})
    for dtype, freq in clim.get("disaster_frequency_by_type", {}).items():
        lines.append(f"Disaster {dtype}: {freq:.0%} of runs")
    lines.append("")

    # Great Persons
    gp = report.get("great_persons", {})
    for key in ["great_person_born_rate", "succession_crisis_rate", "tradition_acquired_rate", "hostage_taken_rate"]:
        rate = gp.get(key, 0)
        label = key.replace("_rate", "").replace("_", " ").title()
        lines.append(f"{label}: {rate:.0%} of runs")
    lines.append("")

    # Emergence
    emrg = report.get("emergence", {})
    bs = emrg.get("black_swan_frequency_by_type", {})
    if bs:
        parts = ", ".join(f"{k} {v:.0%}" for k, v in bs.items())
        lines.append(f"Black Swan: {parts}")
    lines.append(f"Regression: {emrg.get('regression_rate', 0):.0%} of runs")
    lines.append("")

    # General
    gen = report.get("general", {})
    if "median_era_at_final" in gen:
        lines.append(f"Median era at final turn: {gen['median_era_at_final']}")
    lines.append("")

    # Focus Distribution (M22)
    fd = report.get("focus_distribution", {})
    if fd:
        lines.append("FOCUS DISTRIBUTION:")
        for era, focuses in sorted(fd.items()):
            parts = ", ".join(f"{f}={frac:.0%}" for f, frac in sorted(focuses.items()))
            lines.append(f"  {era}: {parts}")
        lines.append("")

    # Focus Geography (M22)
    fg = report.get("focus_geography", {})
    if fg:
        lines.append("FOCUS-GEOGRAPHY CORRELATION:")
        lines.append(f"  Coastal navigation rate: {fg.get('coastal_navigation_rate', 0):.0%}")
        lines.append(f"  Non-coastal navigation rate: {fg.get('non_coastal_navigation_rate', 0):.0%}")
        lines.append(f"  Mountain metallurgy rate: {fg.get('mountain_metallurgy_rate', 0):.0%}")
        lines.append(f"  Non-mountain metallurgy rate: {fg.get('non_mountain_metallurgy_rate', 0):.0%}")
        lines.append("")

    # Action Entropy (M22)
    ae = report.get("action_entropy", {})
    if ae:
        lines.append("ACTION ENTROPY:")
        lines.append(f"  Overall median: {ae.get('overall_median', 0):.2f} bits")
        for era, pcts in sorted(ae.get("entropy_by_era", {}).items()):
            lines.append(f"  {era}: median={pcts.get('median', 0):.2f}, p10={pcts.get('p10', 0):.2f}, p90={pcts.get('p90', 0):.2f}")
        lines.append("")

    # Capability Firing (M22)
    cf = report.get("capability_firing", {})
    if cf:
        lines.append("CAPABILITY FIRING RATES:")
        for cap_name, data in sorted(cf.items()):
            eligible = data.get("eligible_runs", 0)
            fired = data.get("fired_runs", 0)
            rate = data.get("rate", 0)
            if eligible > 0:
                lines.append(f"  {cap_name}: {fired}/{eligible} ({rate:.0%})")
            else:
                lines.append(f"  {cap_name}: no eligible runs")
        lines.append("")

    # Faction Dominance (M22)
    fdom = report.get("faction_dominance", {})
    if fdom:
        lines.append("FACTION DOMINANCE:")
        for cp, data in sorted(fdom.get("by_checkpoint", {}).items()):
            sample = data.get("sample_size", 0)
            parts = []
            for faction_name in ["MILITARY", "MERCHANT", "CULTURAL"]:
                frac = data.get(faction_name, 0)
                parts.append(f"{faction_name}={frac:.0%}")
            lines.append(f"  turn {cp}: {', '.join(parts)} (n={sample})")
        lines.append("")

    # Power Struggles (M22)
    ps = report.get("power_struggles", {})
    if ps:
        lines.append("POWER STRUGGLES:")
        lines.append(f"  Per-civ rate: {ps.get('per_civ_rate', 0):.0%} (n={ps.get('per_civ_sample_size', 0)})")
        rb = ps.get("resolution_balance", {})
        parts = ", ".join(f"{f}={rb.get(f, 0):.0%}" for f in ["MILITARY", "MERCHANT", "CULTURAL"])
        lines.append(f"  Resolution balance: {parts} (total={ps.get('total_resolutions', 0)})")
        lines.append("")

    # Faction Succession (M22)
    fs = report.get("faction_succession", {})
    if fs:
        lines.append("FACTION-SUCCESSION CORRELATION:")
        lines.append(f"  Correlation rate: {fs.get('correlation_rate', 0):.0%} (n={fs.get('sample_size', 0)})")
        lines.append("")

    # Population (M22)
    pop = report.get("population", {})
    if pop:
        lines.append("POPULATION:")
        for cp, pcts in sorted(pop.get("population_by_checkpoint", {}).items()):
            lines.append(f"  turn {cp}: median={pcts.get('median', 0)}, p10={pcts.get('p10', 0)}, p90={pcts.get('p90', 0)}")
        for cp, rate in sorted(pop.get("low_capacity_rate", {}).items()):
            if rate > 0:
                lines.append(f"  Low capacity (<10) at turn {cp}: {rate:.0%}")
        lines.append("")

    # Pre-cap Weights (M22)
    pcw = report.get("precap_weights", {})
    if pcw:
        lines.append("PRE-CAP WEIGHTS:")
        lines.append(f"  Median pre-cap weight: {pcw.get('median_precap_weight', 0):.2f}")
        lines.append(f"  Cap fire rate: {pcw.get('cap_fire_rate', 0):.0%}")
        pcts = pcw.get("percentiles", {})
        if pcts:
            lines.append(f"  p10={pcts.get('p10', 0):.2f}, p90={pcts.get('p90', 0):.2f}")
        lines.append("")

    # Action Persistence (M22)
    ap = report.get("action_persistence", {})
    if ap:
        lines.append("ACTION PERSISTENCE:")
        pcts = ap.get("max_persistence_by_window", {})
        if pcts:
            lines.append(f"  Window persistence: median={pcts.get('median', 0):.0%}, p90={pcts.get('p90', 0):.0%}")
        lines.append(f"  Civ-windows above 80%: {ap.get('civs_above_80pct', 0):.0%}")
        lines.append("")

    # New Event Types (M22)
    net = report.get("new_event_types", {})
    if net:
        lines.append("M22 EVENT TYPES:")
        for key in ["power_struggle_started_rate", "power_struggle_resolved_rate", "faction_dominance_shift_rate"]:
            rate = net.get(key, 0)
            label = key.replace("_rate", "").replace("_", " ").title()
            lines.append(f"  {label}: {rate:.0%} of runs")
        lines.append("")

    # Event firing rates
    lines.append("EVENT FIRING RATES:")
    for et, rate in sorted(report.get("event_firing_rates", {}).items(), key=lambda x: -x[1]):
        count = int(rate * n_runs)
        flag = ""
        if rate >= 1.0:
            flag = "  ← EVERY RUN"
        elif rate < 0.05:
            flag = "  ← RARE"
        lines.append(f"  {et}: {count}/{n_runs} ({rate:.0%}){flag}")
    lines.append("")

    # Anomalies
    anomalies = report.get("anomalies", [])
    if anomalies:
        critical = [a for a in anomalies if a["severity"] == "CRITICAL"]
        warnings_ = [a for a in anomalies if a["severity"] == "WARNING"]
        if critical:
            lines.append("DEGENERATE PATTERNS:")
            for a in critical:
                lines.append(f"  ⚠ {a['name']}: {a['detail']}")
            lines.append("")
        if warnings_:
            lines.append("NEVER-FIRE / WARNINGS:")
            for a in warnings_:
                lines.append(f"  ⚠ {a['name']}: {a['detail']}")
            lines.append("")
    else:
        lines.append("No anomalies detected.")
        lines.append("")

    return "\n".join(lines)


# --- Task 11: Delta Comparison Report ---

def format_delta_report(
    baseline: dict,
    current: dict,
    threshold: float = 0.05,
) -> str:
    """Format delta-only comparison between two reports."""
    lines = ["DELTA REPORT (baseline → current)", "=" * 40, ""]

    deltas = []
    omitted = 0

    def _walk(base: dict, curr: dict, prefix: str = ""):
        nonlocal omitted
        for key in sorted(set(list(base.keys()) + list(curr.keys()))):
            if key in ("anomalies", "metadata"):
                continue
            full_key = f"{prefix}.{key}" if prefix else key
            b_val = base.get(key)
            c_val = curr.get(key)
            if isinstance(b_val, dict) and isinstance(c_val, dict):
                _walk(b_val, c_val, full_key)
            elif isinstance(b_val, (int, float)) and isinstance(c_val, (int, float)):
                rel_change = abs(c_val - b_val) / max(abs(b_val), 1e-9)
                if rel_change >= threshold:
                    pct = ((c_val - b_val) / max(abs(b_val), 1e-9)) * 100
                    sign = "+" if pct > 0 else ""
                    deltas.append(f"  {full_key}: {b_val} → {c_val}  ({sign}{pct:.0f}%)")
                else:
                    omitted += 1

    _walk(baseline, current)

    if deltas:
        lines.extend(deltas)
    else:
        lines.append("  No significant changes.")
    lines.append("")

    base_anomaly_names = {a["name"] for a in baseline.get("anomalies", [])}
    curr_anomaly_names = {a["name"] for a in current.get("anomalies", [])}
    resolved = base_anomaly_names - curr_anomaly_names
    new_anomalies = curr_anomaly_names - base_anomaly_names

    if resolved:
        lines.append("ANOMALIES RESOLVED:")
        for name in sorted(resolved):
            lines.append(f"  ✓ {name}")
        lines.append("")
    if new_anomalies:
        lines.append("ANOMALIES NEW:")
        for name in sorted(new_anomalies):
            lines.append(f"  ⚠ {name}")
        lines.append("")

    lines.append(f"{omitted} metrics omitted (< {threshold:.0%} change)")
    return "\n".join(lines)


# --- M47b Extractors ---

def extract_gini_trajectory(bundles: list[dict], checkpoints: list[int] | None = None) -> dict:
    """Gini coefficient per civ at checkpoints."""
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)
    result = {}
    for turn in cps:
        values = []
        for b in bundles:
            snap = _snapshot_at_turn(b, turn)
            if snap:
                for name, cs in snap["civ_stats"].items():
                    if len(cs.get("regions", [])) > 0:
                        values.append(cs.get("gini", 0.0))
        result[str(turn)] = _compute_percentiles(values) if values else {}
    return {"gini_by_turn": result}


def extract_schism_count(bundles: list[dict]) -> dict:
    """Count of schism events per run."""
    counts = []
    for b in bundles:
        n = sum(1 for e in b.get("events_timeline", []) if e.get("event_type") == "Schism")
        counts.append(n)
    return {
        "schism_count": _compute_percentiles(counts),
        "firing_rate": sum(1 for c in counts if c > 0) / max(len(counts), 1),
    }


def extract_dynasty_count(bundles: list[dict]) -> dict:
    """Count of unique dynasties per run."""
    counts = []
    for b in bundles:
        dynasty_ids = set()
        for civ_data in b.get("world_state", {}).get("civilizations", []):
            for gp in civ_data.get("great_persons", []):
                did = gp.get("dynasty_id")
                if did and did != 0:
                    dynasty_ids.add(did)
        counts.append(len(dynasty_ids))
    return {
        "dynasty_count": _compute_percentiles(counts),
        "firing_rate": sum(1 for c in counts if c > 0) / max(len(counts), 1),
    }


def extract_arc_distribution(bundles: list[dict]) -> dict:
    """Arc type distribution across all great persons."""
    type_counts: dict[str, int] = {}
    total = 0
    for b in bundles:
        for civ_data in b.get("world_state", {}).get("civilizations", []):
            for gp in civ_data.get("great_persons", []):
                at = gp.get("arc_type")
                if at:
                    type_counts[at] = type_counts.get(at, 0) + 1
                    total += 1
    return {"arc_types": type_counts, "total": total, "distinct_count": len(type_counts)}


def extract_food_sufficiency(bundles: list[dict], checkpoints: list[int] | None = None) -> dict:
    """Food sufficiency distribution at checkpoints. Reads economy_result from bundle metadata."""
    # EconomyResult is transient and not bundled into turn snapshots yet.
    # For now, read the final world_state stockpile levels as a proxy.
    counts = []
    for b in bundles:
        regions = b.get("world_state", {}).get("regions", [])
        total_food = 0.0
        for r in regions:
            stockpile = r.get("stockpile", {}).get("goods", {})
            for good, amount in stockpile.items():
                if good in ("grain", "fish", "salt"):
                    total_food += amount
        counts.append(total_food)
    return {"final_food_stock": _compute_percentiles(counts) if counts else {}}


def extract_trade_volume(bundles: list[dict]) -> dict:
    """Trade volume proxy from stockpile import/export data."""
    # Full per-turn trade volume requires EconomyResult persistence.
    # Use stockpile levels as a proxy for trade activity.
    return {"note": "Requires EconomyResult bundling (deferred to M62 viewer)"}


def extract_stockpile_levels(bundles: list[dict]) -> dict:
    """Stockpile levels at final turn per region."""
    all_totals = []
    for b in bundles:
        regions = b.get("world_state", {}).get("regions", [])
        for r in regions:
            stockpile = r.get("stockpile", {}).get("goods", {})
            total = sum(stockpile.values())
            all_totals.append(total)
    return {"stockpile_total": _compute_percentiles(all_totals) if all_totals else {}}


def extract_conversion_rates(bundles: list[dict]) -> dict:
    """Religious conversion event counts."""
    types = ("Persecution", "Schism", "Reformation")
    counts_by_type: dict[str, list[int]] = {t: [] for t in types}
    for b in bundles:
        per_run: dict[str, int] = {t: 0 for t in types}
        for e in b.get("events_timeline", []):
            et = e.get("event_type")
            if et in per_run:
                per_run[et] += 1
        for t in types:
            counts_by_type[t].append(per_run[t])
    return {t: _compute_percentiles(v) for t, v in counts_by_type.items()}


def extract_trade_flow_by_distance(bundles: list[dict]) -> dict:
    """Trade flow by distance — requires per-route data in bundle (deferred)."""
    return {"note": "Requires per-route EconomyResult bundling (deferred to M62 viewer)"}


def extract_artifacts(bundles: list[dict]) -> dict:
    """Extract artifact metrics from bundle dicts."""
    total = 0
    active = 0
    lost = 0
    destroyed = 0
    by_civ: dict[str, int] = {}
    by_type: dict[str, int] = {}
    prestige = 0
    mule = 0

    for bundle in bundles:
        artifacts = bundle.get("world_state", {}).get("artifacts", [])
        total += len(artifacts)
        for a in artifacts:
            status = a.get("status", "active")
            if status == "active":
                active += 1
                owner = a.get("owner_civ")
                if owner:
                    by_civ[owner] = by_civ.get(owner, 0) + 1
                    prestige += a.get("prestige_value", 0)
            elif status == "lost":
                lost += 1
            elif status == "destroyed":
                destroyed += 1
            atype = a.get("artifact_type", "unknown")
            by_type[atype] = by_type.get(atype, 0) + 1
            if a.get("mule_origin"):
                mule += 1

    return {
        "total_artifacts": total,
        "active_artifacts": active,
        "lost_artifacts": lost,
        "destroyed_artifacts": destroyed,
        "artifacts_by_civ": dict(by_civ),
        "artifacts_by_type": dict(by_type),
        "total_prestige_contribution": prestige,
        "mule_artifacts": mule,
    }


def extract_relationship_metrics(bundles: list[dict], checkpoints=None) -> dict:
    """Extract per-turn relationship formation/dissolution metrics."""
    metrics: dict[str, list] = {
        "bonds_formed_per_turn": [],
        "bonds_dissolved_per_turn": [],
        "mean_rel_count_per_turn": [],
    }
    for bundle in bundles:
        metadata = bundle.get("metadata", {})
        rel_stats = metadata.get("relationship_stats", [])
        for turn_stats in rel_stats:
            metrics["bonds_formed_per_turn"].append(
                turn_stats.get("bonds_formed", 0)
            )
            metrics["bonds_dissolved_per_turn"].append(
                turn_stats.get("bonds_dissolved_death", 0)
                + turn_stats.get("bonds_dissolved_structural", 0)
            )
            metrics["mean_rel_count_per_turn"].append(
                turn_stats.get("mean_rel_count", 0)
            )
    return metrics
