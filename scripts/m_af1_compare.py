#!/usr/bin/env python3
"""M-AF1 regression comparison: pre-fix vs post-fix 200-seed batch."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np


METRICS = ["population", "military", "economy", "culture", "stability", "treasury"]
CHECKPOINTS = [100, 250, 500]


def load_bundle(path: Path) -> dict | None:
    for name in ["chronicle_bundle.json", "bundle.json"]:
        f = path / name
        if f.exists():
            return json.loads(f.read_text())
    return None


def extract_metrics(bundle: dict, checkpoints: list[int]) -> dict[int, dict[str, list[float]]]:
    """Extract per-checkpoint, per-metric values across all civs."""
    history = bundle.get("history", [])
    snap_by_turn = {s["turn"]: s for s in history}
    result: dict[int, dict[str, list[float]]] = {}
    for cp in checkpoints:
        snap = snap_by_turn.get(cp)
        if snap is None:
            continue
        result[cp] = defaultdict(list)
        civ_stats = snap.get("civ_stats", {})
        for civ_name, civ in civ_stats.items():
            for m in METRICS:
                val = civ.get(m)
                if val is not None:
                    result[cp][m].append(float(val))
    return result


def main():
    baseline_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/m-af1-baseline")
    postfix_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output/m-af1-post/batch_1")

    # Find common seeds
    baseline_seeds = {d.name for d in baseline_dir.iterdir() if d.is_dir() and d.name.startswith("seed_")}
    postfix_seeds = {d.name for d in postfix_dir.iterdir() if d.is_dir() and d.name.startswith("seed_")}
    common = sorted(baseline_seeds & postfix_seeds, key=lambda s: int(s.split("_")[1]))

    print(f"Baseline: {baseline_dir} ({len(baseline_seeds)} seeds)")
    print(f"Post-fix: {postfix_dir} ({len(postfix_seeds)} seeds)")
    print(f"Common seeds: {len(common)}")

    if not common:
        print("ERROR: No common seeds found!")
        sys.exit(1)

    # Check for crashes
    baseline_crashes = []
    postfix_crashes = []
    for seed_name in common:
        b = load_bundle(baseline_dir / seed_name)
        p = load_bundle(postfix_dir / seed_name)
        if b is None:
            baseline_crashes.append(seed_name)
        if p is None:
            postfix_crashes.append(seed_name)

    print(f"\n=== CRASH CHECK ===")
    print(f"Baseline crashes: {len(baseline_crashes)}")
    print(f"Post-fix crashes: {len(postfix_crashes)}")
    if postfix_crashes:
        print(f"  Crashed seeds: {postfix_crashes[:10]}")

    # Aggregate metrics at checkpoints
    baseline_agg: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    postfix_agg: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for seed_name in common:
        b = load_bundle(baseline_dir / seed_name)
        p = load_bundle(postfix_dir / seed_name)
        if b is None or p is None:
            continue
        b_metrics = extract_metrics(b, CHECKPOINTS)
        p_metrics = extract_metrics(p, CHECKPOINTS)
        for cp in CHECKPOINTS:
            if cp in b_metrics:
                for m in METRICS:
                    baseline_agg[cp][m].extend(b_metrics[cp].get(m, []))
            if cp in p_metrics:
                for m in METRICS:
                    postfix_agg[cp][m].extend(p_metrics[cp].get(m, []))

    # Print comparison
    print(f"\n=== METRIC COMPARISON (mean ± std) ===")
    for cp in CHECKPOINTS:
        print(f"\n--- Turn {cp} ---")
        print(f"{'Metric':<12} {'Baseline':>20} {'Post-fix':>20} {'Delta%':>10} {'Direction':>12}")
        print("-" * 76)
        for m in METRICS:
            b_vals = baseline_agg[cp].get(m, [])
            p_vals = postfix_agg[cp].get(m, [])
            if not b_vals or not p_vals:
                continue
            b_mean = np.mean(b_vals)
            p_mean = np.mean(p_vals)
            b_std = np.std(b_vals)
            p_std = np.std(p_vals)
            if b_mean != 0:
                delta_pct = ((p_mean - b_mean) / abs(b_mean)) * 100
            else:
                delta_pct = 0.0
            direction = "UP" if delta_pct > 2 else "DOWN" if delta_pct < -2 else "~"
            print(f"{m:<12} {b_mean:>8.1f} ± {b_std:>6.1f}   {p_mean:>8.1f} ± {p_std:>6.1f}   {delta_pct:>+8.1f}%   {direction:>8}")

    # Check for pathological outcomes
    print(f"\n=== PATHOLOGICAL CHECK ===")
    dead_civs_baseline = 0
    dead_civs_postfix = 0
    for seed_name in common:
        b = load_bundle(baseline_dir / seed_name)
        p = load_bundle(postfix_dir / seed_name)
        if b is None or p is None:
            continue
        b_last = b["history"][-1] if b.get("history") else None
        p_last = p["history"][-1] if p.get("history") else None
        if b_last:
            for civ in b_last.get("civ_stats", {}).values():
                if len(civ.get("regions", [])) == 0:
                    dead_civs_baseline += 1
        if p_last:
            for civ in p_last.get("civ_stats", {}).values():
                if len(civ.get("regions", [])) == 0:
                    dead_civs_postfix += 1

    print(f"Dead civs at end (baseline): {dead_civs_baseline}")
    print(f"Dead civs at end (post-fix): {dead_civs_postfix}")

    # Summary
    print(f"\n=== GATE RESULT ===")
    hard_pass = len(postfix_crashes) == 0
    print(f"Hard gate (no crashes): {'PASS' if hard_pass else 'FAIL'}")
    print(f"Adjudication: Review directional shifts above against spec expectations")


if __name__ == "__main__":
    main()
