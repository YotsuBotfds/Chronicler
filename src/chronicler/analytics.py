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
