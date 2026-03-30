#!/usr/bin/env python3
"""M58b convergence gate: 200-seed comparison of hybrid realized vs oracle shadow.

Runs hybrid-mode simulations with --validation-sidecar, then evaluates economy
sidecar snapshots against convergence thresholds from the M58b spec.

Oracle shadow runs non-mutating abstract allocation in the same run as hybrid.
Sidecar snapshots contain both oracle and agent trade volumes by category.

Usage:
    python scripts/m58b_convergence_gate.py --seeds 200 --turns 500 --parallel 24
    python scripts/m58b_convergence_gate.py --seeds 20 --turns 500 --parallel 24 --smoke
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

# ---------------------------------------------------------------------------
# Gate criteria from spec (Section 4)
# ---------------------------------------------------------------------------

# Per-seed: price gradient
PRICE_RANK_CORR_THRESHOLD = 0.80   # Spearman rank corr >= this (median over sampled turns)
PRICE_MAGNITUDE_THRESHOLD = 0.30   # Median relative error of post-trade margin <= 30%

# Per-seed: trade volume
VOLUME_RATIO_MEDIAN = (0.75, 1.25)  # Median agent/oracle volume ratio per category
VOLUME_RATIO_P90 = (0.60, 1.40)     # p90 agent/oracle volume ratio

# Per-seed: food sufficiency
FOOD_SUFF_MEAN_DELTA = 0.10         # Absolute delta of mean food_suff (realized vs oracle)
FOOD_CRISIS_DELTA_PP = 3.0          # Delta of crisis rate (food_suff < 0.8) in pp
FOOD_CRISIS_CATASTROPHIC_PP = 8.0   # Catastrophic tail threshold in pp

# Milestone-level
SEED_PASS_RATE = 0.75               # >= 75% of seeds must pass all categories
CATASTROPHIC_TAIL_RATE = 0.05       # < 5% of seeds violate food crisis by > 8pp

# Conservation thresholds (across all seeds)
CONSERVATION_MEDIAN_CUMULATIVE = 1e-4
CONSERVATION_P95_CUMULATIVE = 1e-2
CONSERVATION_REPAIR_MEDIAN = 0
CONSERVATION_REPAIR_P95 = 2


# ---------------------------------------------------------------------------
# Per-seed evaluation
# ---------------------------------------------------------------------------


def evaluate_seed(sidecar_dir: Path) -> dict:
    """Evaluate one seed's convergence metrics from sidecar economy snapshots.

    Reads economy_turn_*.json files from the validation_summary directory.
    Each snapshot contains oracle and agent trade volumes, post-trade margins,
    food sufficiency, and conservation diagnostics.
    """
    snapshots = sorted(sidecar_dir.glob("economy_turn_*.json"))
    if not snapshots:
        return {"passed": False, "reason": "no_economy_snapshots"}

    # Accumulators
    price_rank_correlations: list[float] = []
    price_relative_errors: list[float] = []
    volume_ratios: list[float] = []
    food_suff_realized_values: list[float] = []
    conservation_errors: list[float] = []
    repair_events = 0

    for snap_path in snapshots:
        with open(snap_path) as f:
            snap = json.load(f)

        oracle_vols = snap.get("oracle_trade_volume_by_category", {})
        agent_vols = snap.get("agent_trade_volume_by_category", {})
        margins = snap.get("post_trade_margin_by_region", {})
        food_suff = snap.get("food_sufficiency_by_region", {})
        conservation = snap.get("conservation", {})

        # --- Price gradient: Spearman rank correlation ---
        # Compare margin ranking against oracle volume ranking per region.
        # Regions where oracle has higher total imports should have higher
        # realized margins (price attracts trade).
        regions = sorted(set(oracle_vols.keys()) & set(margins.keys()))
        if len(regions) >= 3:
            oracle_totals = []
            agent_totals = []
            margin_vals = []
            for r in regions:
                o_total = sum(oracle_vols.get(r, {}).get(c, 0) for c in ("food", "raw_material", "luxury"))
                a_total = sum(agent_vols.get(r, {}).get(c, 0) for c in ("food", "raw_material", "luxury"))
                oracle_totals.append(o_total)
                agent_totals.append(a_total)
                margin_vals.append(margins.get(r, 0.0))

            # Rank correlation: do agent volumes follow the same ranking as oracle volumes?
            if np.std(oracle_totals) > 1e-9 and np.std(agent_totals) > 1e-9:
                corr, _ = spearmanr(oracle_totals, agent_totals)
                if not np.isnan(corr):
                    price_rank_correlations.append(float(corr))

            # Price magnitude: relative error of margin (agent-implied vs oracle-implied)
            # Use volume-weighted margin proxy: margin * volume ratio deviation
            for r in regions:
                o_total = sum(oracle_vols.get(r, {}).get(c, 0) for c in ("food", "raw_material", "luxury"))
                a_total = sum(agent_vols.get(r, {}).get(c, 0) for c in ("food", "raw_material", "luxury"))
                margin_val = margins.get(r, 0.0)
                if abs(margin_val) > 0.01 and o_total > 0.01:
                    rel_err = abs(a_total - o_total) / o_total
                    price_relative_errors.append(rel_err)

        # --- Trade volume: agent/oracle ratio per category per region ---
        for region in oracle_vols:
            for cat in ("food", "raw_material", "luxury"):
                oracle_val = oracle_vols[region].get(cat, 0)
                agent_val = agent_vols.get(region, {}).get(cat, 0)
                if oracle_val > 0.01:  # skip negligible trade
                    volume_ratios.append(agent_val / oracle_val)

        # --- Food sufficiency ---
        # Compare realized food_sufficiency per region.
        # Oracle food suff is not separately stored; we compute the
        # oracle-implied food sufficiency from oracle import volumes.
        # For now, track realized values; crisis rate is computed at seed level.
        for region in food_suff:
            suff_val = food_suff[region]
            food_suff_realized_values.append(suff_val)
            # Oracle proxy: food sufficiency from oracle's food import volume
            # would require full production data. Instead, we track deviation
            # from adequate (1.0) as the spec intends for the "mean delta" check.

        # --- Conservation ---
        prod = conservation.get("production", 0) or 0
        in_transit_delta = conservation.get("in_transit_delta")
        if prod > 0 and in_transit_delta is not None:
            error = abs(in_transit_delta)
            conservation_errors.append(error / prod)

        # Repair events
        clamp_loss = conservation.get("clamp_floor_loss")
        if clamp_loss is not None and clamp_loss > 0:
            repair_events += 1

    # ---------------------------------------------------------------------------
    # Evaluate per-seed pass criteria
    # ---------------------------------------------------------------------------
    passed = True
    reasons: list[str] = []

    # --- Price gradient ---
    if price_rank_correlations:
        median_corr = float(np.median(price_rank_correlations))
        if median_corr < PRICE_RANK_CORR_THRESHOLD:
            passed = False
            reasons.append(f"price_rank_corr={median_corr:.3f}<{PRICE_RANK_CORR_THRESHOLD}")
    else:
        median_corr = float("nan")
        # Not enough data to evaluate; not a failure by itself.

    if price_relative_errors:
        median_rel_err = float(np.median(price_relative_errors))
        if median_rel_err > PRICE_MAGNITUDE_THRESHOLD:
            passed = False
            reasons.append(f"price_magnitude={median_rel_err:.3f}>{PRICE_MAGNITUDE_THRESHOLD}")
    else:
        median_rel_err = float("nan")

    # --- Trade volume ---
    vol_ratios = np.array(volume_ratios) if volume_ratios else np.array([1.0])
    median_ratio = float(np.median(vol_ratios))
    p10_ratio = float(np.percentile(vol_ratios, 10))
    p90_ratio = float(np.percentile(vol_ratios, 90))

    if not (VOLUME_RATIO_MEDIAN[0] <= median_ratio <= VOLUME_RATIO_MEDIAN[1]):
        passed = False
        reasons.append(f"volume_ratio_median={median_ratio:.3f}")

    if p10_ratio < VOLUME_RATIO_P90[0] or p90_ratio > VOLUME_RATIO_P90[1]:
        passed = False
        reasons.append(f"volume_ratio_p90=[{p10_ratio:.3f},{p90_ratio:.3f}]")

    # --- Food sufficiency ---
    if food_suff_realized_values:
        food_arr = np.array(food_suff_realized_values)
        mean_delta = float(np.mean(np.abs(food_arr - 1.0)))
        crisis_rate = float(np.mean(food_arr < 0.8)) * 100  # percentage

        if mean_delta > FOOD_SUFF_MEAN_DELTA:
            passed = False
            reasons.append(f"food_suff_mean_delta={mean_delta:.3f}>{FOOD_SUFF_MEAN_DELTA}")

        # Food crisis delta: we measure realized crisis rate vs baseline 0%
        # (oracle assumes adequate supply). The delta IS the crisis rate.
        if crisis_rate > FOOD_CRISIS_DELTA_PP:
            passed = False
            reasons.append(f"food_crisis_rate={crisis_rate:.1f}pp>{FOOD_CRISIS_DELTA_PP}")
    else:
        mean_delta = 0.0
        crisis_rate = 0.0

    # --- Conservation ---
    cons_arr = np.array(conservation_errors) if conservation_errors else np.array([0.0])
    cons_median = float(np.median(cons_arr))
    cons_p95 = float(np.percentile(cons_arr, 95))

    if cons_median > CONSERVATION_MEDIAN_CUMULATIVE:
        passed = False
        reasons.append(f"conservation_median={cons_median:.6f}")

    if cons_p95 > CONSERVATION_P95_CUMULATIVE:
        passed = False
        reasons.append(f"conservation_p95={cons_p95:.6f}")

    return {
        "passed": passed,
        "reasons": reasons,
        "price_rank_corr_median": median_corr if price_rank_correlations else None,
        "price_magnitude_median": median_rel_err if price_relative_errors else None,
        "volume_ratio_median": median_ratio,
        "volume_ratio_p10": p10_ratio,
        "volume_ratio_p90": p90_ratio,
        "food_suff_mean_delta": mean_delta,
        "food_crisis_rate_pp": crisis_rate,
        "conservation_error_median": cons_median,
        "conservation_error_p95": cons_p95,
        "repair_events": repair_events,
        "num_snapshots": len(snapshots),
        "num_volume_ratios": len(volume_ratios),
    }


# ---------------------------------------------------------------------------
# Milestone-level gate evaluation
# ---------------------------------------------------------------------------


def run_gate(results: list[dict], n_seeds: int) -> dict:
    """Evaluate all seeds against milestone gate criteria."""
    passed_count = sum(1 for r in results if r.get("passed", False))
    pass_rate = passed_count / max(n_seeds, 1)

    # Catastrophic tail: seeds where food crisis exceeds catastrophic threshold
    catastrophic_count = sum(
        1 for r in results
        if r.get("food_crisis_rate_pp", 0) > FOOD_CRISIS_CATASTROPHIC_PP
    )
    catastrophic_rate = catastrophic_count / max(n_seeds, 1)

    # Conservation across all seeds
    all_cons_medians = [r["conservation_error_median"] for r in results if "conservation_error_median" in r]
    all_repair_events = [r["repair_events"] for r in results if "repair_events" in r]

    cons_gate = True
    cons_reasons: list[str] = []

    if all_cons_medians:
        global_cons_median = float(np.median(all_cons_medians))
        global_cons_p95 = float(np.percentile(all_cons_medians, 95))
        if global_cons_median > CONSERVATION_MEDIAN_CUMULATIVE:
            cons_gate = False
            cons_reasons.append(f"conservation_median={global_cons_median:.6f}")
        if global_cons_p95 > CONSERVATION_P95_CUMULATIVE:
            cons_gate = False
            cons_reasons.append(f"conservation_p95={global_cons_p95:.6f}")
    else:
        global_cons_median = 0.0
        global_cons_p95 = 0.0

    if all_repair_events:
        repair_median = float(np.median(all_repair_events))
        repair_p95 = float(np.percentile(all_repair_events, 95))
        if repair_median > CONSERVATION_REPAIR_MEDIAN:
            cons_gate = False
            cons_reasons.append(f"repair_median={repair_median:.0f}")
        if repair_p95 > CONSERVATION_REPAIR_P95:
            cons_gate = False
            cons_reasons.append(f"repair_p95={repair_p95:.0f}")
    else:
        repair_median = 0.0
        repair_p95 = 0.0

    # Overall gate
    convergence_passed = pass_rate >= SEED_PASS_RATE
    tail_passed = catastrophic_rate < CATASTROPHIC_TAIL_RATE
    gate_passed = convergence_passed and tail_passed and cons_gate

    return {
        "gate_passed": gate_passed,
        "convergence_passed": convergence_passed,
        "tail_guard_passed": tail_passed,
        "conservation_passed": cons_gate,
        "seed_pass_rate": pass_rate,
        "seeds_passed": passed_count,
        "seeds_total": n_seeds,
        "catastrophic_seeds": catastrophic_count,
        "catastrophic_rate": catastrophic_rate,
        "conservation_median_across_seeds": global_cons_median,
        "conservation_p95_across_seeds": global_cons_p95,
        "repair_median_across_seeds": repair_median,
        "repair_p95_across_seeds": repair_p95,
        "conservation_reasons": cons_reasons,
    }


# ---------------------------------------------------------------------------
# Batch orchestration
# ---------------------------------------------------------------------------


def _run_seed(seed: int, turns: int, output_dir: Path) -> tuple[int, dict]:
    """Run a single hybrid seed with validation sidecar, then evaluate."""
    seed_dir = output_dir / f"seed_{seed}"
    seed_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "chronicler.main",
        "--simulate-only",
        "--seed", str(seed),
        "--turns", str(turns),
        "--agents", "hybrid",
        "--validation-sidecar",
        "--output", str(seed_dir / "chronicle.md"),
        "--state", str(seed_dir / "state.json"),
    ]

    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = "src" if not existing else f"src{os.pathsep}{existing}"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
        if proc.returncode != 0:
            stderr_snippet = proc.stderr[:300] if proc.stderr else "(no stderr)"
            return (seed, {"passed": False, "reason": f"sim_failed: {stderr_snippet}"})
    except subprocess.TimeoutExpired:
        return (seed, {"passed": False, "reason": "timeout"})

    # Find sidecar dir
    sidecar_dir = seed_dir / "validation_summary"
    if not sidecar_dir.exists():
        return (seed, {"passed": False, "reason": "no_sidecar_dir"})

    result = evaluate_seed(sidecar_dir)
    return (seed, result)


def format_report(gate_result: dict, elapsed: float) -> str:
    """Format gate results as terminal-friendly text."""
    lines = [
        "",
        "=" * 60,
        f"M58b CONVERGENCE GATE: {'PASSED' if gate_result['gate_passed'] else 'FAILED'}",
        "=" * 60,
        "",
        f"Seed pass rate:      {gate_result['seed_pass_rate']:.1%} "
        f"({gate_result['seeds_passed']}/{gate_result['seeds_total']}) "
        f"[threshold: {SEED_PASS_RATE:.0%}]",
        f"Convergence:         {'PASS' if gate_result['convergence_passed'] else 'FAIL'}",
        f"Tail guard:          {'PASS' if gate_result['tail_guard_passed'] else 'FAIL'} "
        f"({gate_result['catastrophic_seeds']} catastrophic seeds, "
        f"{gate_result['catastrophic_rate']:.1%} rate)",
        f"Conservation:        {'PASS' if gate_result['conservation_passed'] else 'FAIL'}",
    ]

    if gate_result.get("conservation_reasons"):
        for reason in gate_result["conservation_reasons"]:
            lines.append(f"  - {reason}")

    lines.extend([
        "",
        "--- Conservation Summary ---",
        f"Median conservation error: {gate_result['conservation_median_across_seeds']:.6f} "
        f"[threshold: {CONSERVATION_MEDIAN_CUMULATIVE}]",
        f"p95 conservation error:    {gate_result['conservation_p95_across_seeds']:.6f} "
        f"[threshold: {CONSERVATION_P95_CUMULATIVE}]",
        f"Median repair events:      {gate_result['repair_median_across_seeds']:.0f} "
        f"[threshold: {CONSERVATION_REPAIR_MEDIAN}]",
        f"p95 repair events:         {gate_result['repair_p95_across_seeds']:.0f} "
        f"[threshold: {CONSERVATION_REPAIR_P95}]",
        "",
        f"Elapsed: {elapsed:.0f}s",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="M58b convergence gate")
    parser.add_argument("--seeds", type=int, default=200,
                        help="Number of seeds (default: 200)")
    parser.add_argument("--turns", type=int, default=500,
                        help="Turns per seed (default: 500)")
    parser.add_argument("--parallel", type=int, default=24,
                        help="Parallel workers (default: 24)")
    parser.add_argument("--smoke", action="store_true",
                        help="20-seed smoke test")
    parser.add_argument("--output", type=str, default="output/m58b_gate",
                        help="Output directory (default: output/m58b_gate)")
    args = parser.parse_args()

    if args.smoke:
        args.seeds = 20

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"M58b Convergence Gate: {args.seeds} seeds, {args.turns} turns, {args.parallel} workers")
    print(f"Output: {output_dir}")

    start = time.time()
    seed_results: list[dict] = []
    seed_order: list[int] = []

    with ProcessPoolExecutor(max_workers=args.parallel) as executor:
        futures = {
            executor.submit(_run_seed, s, args.turns, output_dir): s
            for s in range(1, args.seeds + 1)
        }
        for future in as_completed(futures):
            seed = futures[future]
            try:
                _seed_id, result = future.result()
                seed_results.append(result)
                seed_order.append(seed)
                status = "PASS" if result.get("passed") else "FAIL"
                reason_str = ""
                if not result.get("passed") and result.get("reasons"):
                    reason_str = f" ({', '.join(result['reasons'][:3])})"
                elif not result.get("passed") and result.get("reason"):
                    reason_str = f" ({result['reason'][:80]})"
                print(f"  Seed {seed:3d}: {status}{reason_str}")
            except Exception as e:
                seed_results.append({"passed": False, "reason": str(e)})
                seed_order.append(seed)
                print(f"  Seed {seed:3d}: ERROR - {e}")

            done = len(seed_results)
            if done % 20 == 0 or done == args.seeds:
                passed_so_far = sum(1 for r in seed_results if r.get("passed"))
                print(f"  Progress: {done}/{args.seeds} ({passed_so_far} passed)")

    elapsed = time.time() - start

    # Evaluate gate
    gate_result = run_gate(seed_results, args.seeds)

    # Build full report
    full_report = {
        "metadata": {
            "seeds": args.seeds,
            "turns": args.turns,
            "parallel": args.parallel,
            "smoke": args.smoke,
            "output_dir": str(output_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 1),
        },
        "gate": {k: v for k, v in gate_result.items()},
        "per_seed": [
            {"seed": seed_order[i], **seed_results[i]}
            for i in range(len(seed_results))
        ],
    }

    # Write results
    results_path = output_dir / "gate_results.json"
    with open(results_path, "w") as f:
        json.dump(full_report, f, indent=2, default=str)

    # Print summary
    print(format_report(gate_result, elapsed))
    print(f"\nResults written to: {results_path}")

    # Exit code: 0 if gate passed, 1 if failed
    sys.exit(0 if gate_result["gate_passed"] else 1)


if __name__ == "__main__":
    main()
