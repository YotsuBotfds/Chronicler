#!/usr/bin/env python3
"""M28 Oracle Gate — 200-seed validation of hybrid vs aggregate mode."""
from __future__ import annotations

import json
from pathlib import Path

METRICS = ["population", "military", "economy", "culture", "stability"]


def load_comparison_data(
    agg_dir: Path,
    hyb_dir: Path,
    checkpoints: list[int] | None = None,
) -> dict[str, list]:
    """Load aggregate and hybrid bundles, extract civ stats at checkpoints.

    Returns columnar dict matching shadow_oracle's expected format:
    keys: turn, agent_{metric}, agg_{metric} for each metric.
    """
    if checkpoints is None:
        checkpoints = [100, 250, 500]

    columns: dict[str, list] = {"turn": []}
    for m in METRICS:
        columns[f"agent_{m}"] = []
        columns[f"agg_{m}"] = []

    agg_seeds = _find_seed_dirs(agg_dir)
    hyb_seeds = _find_seed_dirs(hyb_dir)
    common_seeds = sorted(set(agg_seeds) & set(hyb_seeds))

    for seed_name in common_seeds:
        agg_bundle = _load_bundle(agg_dir / seed_name)
        hyb_bundle = _load_bundle(hyb_dir / seed_name)
        if agg_bundle is None or hyb_bundle is None:
            continue

        agg_snaps = {s["turn"]: s for s in agg_bundle["history"]}
        hyb_snaps = {s["turn"]: s for s in hyb_bundle["history"]}

        for turn in checkpoints:
            agg_snap = agg_snaps.get(turn)
            hyb_snap = hyb_snaps.get(turn)
            if agg_snap is None or hyb_snap is None:
                continue

            common_civs = set(agg_snap["civ_stats"]) & set(hyb_snap["civ_stats"])
            for civ_name in sorted(common_civs):
                agg_stats = agg_snap["civ_stats"][civ_name]
                hyb_stats = hyb_snap["civ_stats"][civ_name]
                columns["turn"].append(turn)
                for m in METRICS:
                    columns[f"agent_{m}"].append(hyb_stats[m])
                    columns[f"agg_{m}"].append(agg_stats[m])

    return columns


def _find_seed_dirs(batch_dir: Path) -> list[str]:
    """Find seed_N directories in a batch directory."""
    if not batch_dir.exists():
        return []
    return [d.name for d in sorted(batch_dir.iterdir())
            if d.is_dir() and d.name.startswith("seed_")]


def _load_bundle(seed_dir: Path) -> dict | None:
    """Load chronicle_bundle.json from a seed directory."""
    bundle_path = seed_dir / "chronicle_bundle.json"
    if not bundle_path.exists():
        return None
    with open(bundle_path) as f:
        return json.load(f)
