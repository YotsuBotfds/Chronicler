"""Post-processing analytics pipeline — reads bundles, computes metrics."""
from __future__ import annotations

import json
import statistics
from pathlib import Path


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
