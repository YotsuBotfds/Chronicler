"""M53 Social-Need Probe — measure effect of SOCIAL_BLEND_ALPHA ramp.

Runs simulations and snapshots social-need distribution, bond counts,
satisfaction, and migration at T50/T100/T200.

Usage:
  PYTHONPATH=src python scripts/m53_social_probe.py --seeds 10 --turns 200
  PYTHONPATH=src python scripts/m53_social_probe.py --seeds 20 --turns 200 --verbose
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pyarrow as pa
from chronicler.world_gen import generate_world
from chronicler.simulation import run_turn
from chronicler.action_engine import ActionEngine


CHECKPOINTS = [50, 100, 150, 200]
# Needs thresholds — behavioral (from agent.rs) and diagnostic (higher, for sensitivity)
SOCIAL_THRESHOLD_BEHAVIORAL = 0.25
SOCIAL_THRESHOLD_DIAGNOSTIC = 0.35
AUTONOMY_THRESHOLD = 0.30
SAFETY_THRESHOLD = 0.25


def null_narrator(world, events):
    return ""


def snapshot_needs(sim) -> dict:
    """Get bulk need data from Rust via Arrow."""
    batch_raw = sim.get_all_needs()
    batch = pa.record_batch(batch_raw)
    social = batch.column("social").to_pylist()
    autonomy = batch.column("autonomy").to_pylist()
    safety = batch.column("safety").to_pylist()
    satisfaction = batch.column("satisfaction").to_pylist()
    n = len(social)
    if n == 0:
        return {"n": 0}
    social_below_beh = sum(1 for v in social if v < SOCIAL_THRESHOLD_BEHAVIORAL) / n
    social_below_diag = sum(1 for v in social if v < SOCIAL_THRESHOLD_DIAGNOSTIC) / n
    autonomy_below = sum(1 for v in autonomy if v < AUTONOMY_THRESHOLD) / n
    safety_below = sum(1 for v in safety if v < SAFETY_THRESHOLD) / n
    sat_mean = sum(satisfaction) / n
    sat_above_fert = sum(1 for v in satisfaction if v > 0.2) / n
    social_mean = sum(social) / n
    autonomy_mean = sum(autonomy) / n
    # Memory occupancy check
    mem_slots_mean = 0.0
    mem_intensity_mean = 0.0
    try:
        mem_raw = sim.get_all_memories()
        mem_batch = pa.record_batch(mem_raw)
        mem_count = mem_batch.num_rows
        if mem_count > 0 and n > 0:
            mem_slots_mean = round(mem_count / n, 2)
            intensities = mem_batch.column("intensity").to_pylist()
            mem_intensity_mean = round(sum(abs(v) for v in intensities) / len(intensities), 1)
    except Exception:
        pass

    return {
        "n": n,
        "social_mean": round(social_mean, 4),
        "social_below_025": round(social_below_beh * 100, 1),
        "social_below_035": round(social_below_diag * 100, 1),
        "autonomy_mean": round(autonomy_mean, 4),
        "autonomy_below_pct": round(autonomy_below * 100, 1),
        "safety_below_pct": round(safety_below * 100, 1),
        "satisfaction_mean": round(sat_mean, 4),
        "satisfaction_above_fert_pct": round(sat_above_fert * 100, 1),
        "mem_slots_per_agent": mem_slots_mean,
        "mem_intensity_mean": mem_intensity_mean,
    }


def run_seed(seed: int, turns: int, verbose: bool) -> dict:
    """Run one seed and collect checkpoints."""
    world = generate_world(seed=seed, num_regions=8, num_civs=4)

    from chronicler.agent_bridge import AgentBridge
    bridge = AgentBridge(world, mode="hybrid")
    sim = bridge._sim

    engine = ActionEngine(world)
    action_selector = lambda civ, w: engine.select_action(civ, seed=w.seed + w.turn)

    bridge.tick(world)  # init

    checkpoints = {}
    extinctions_turn = None

    for turn_num in range(turns):
        world.turn = turn_num
        run_turn(world, action_selector, null_narrator, seed=seed, agent_bridge=bridge)

        alive = sim.last_tick_alive
        if alive == 0 and extinctions_turn is None:
            extinctions_turn = turn_num
            break

        if (turn_num + 1) in CHECKPOINTS:
            needs = snapshot_needs(sim)
            rel_stats = sim.get_relationship_stats()
            bonds_per_agent = rel_stats.get("mean_rel_count", 0.0)
            needs["bonds_per_agent"] = round(bonds_per_agent, 2)
            needs["alive"] = alive
            checkpoints[turn_num + 1] = needs

            if verbose:
                print(f"  seed={seed} T{turn_num+1}: alive={alive} "
                      f"soc<.25={needs['social_below_025']:.0f}% "
                      f"soc<.35={needs['social_below_035']:.0f}% "
                      f"soc_mean={needs['social_mean']:.3f} "
                      f"aut<.30={needs['autonomy_below_pct']:.0f}% "
                      f"aut_mean={needs['autonomy_mean']:.3f} "
                      f"bonds={bonds_per_agent:.2f} "
                      f"sat={needs['satisfaction_mean']:.3f}")

    bridge.close()
    return {
        "seed": seed,
        "extinct": extinctions_turn is not None,
        "extinction_turn": extinctions_turn,
        "checkpoints": checkpoints,
    }


def main():
    parser = argparse.ArgumentParser(description="M53 Social-Need Probe")
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--seed-start", type=int, default=10)
    parser.add_argument("--turns", type=int, default=200)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    seed_range = range(args.seed_start, args.seed_start + args.seeds)
    results = []

    print(f"Running {args.seeds} seeds × {args.turns} turns")
    print(f"Thresholds: social_beh={SOCIAL_THRESHOLD_BEHAVIORAL} social_diag={SOCIAL_THRESHOLD_DIAGNOSTIC}, autonomy={AUTONOMY_THRESHOLD}, safety={SAFETY_THRESHOLD}")
    print()

    for seed in seed_range:
        if args.verbose:
            print(f"Seed {seed}:")
        r = run_seed(seed, args.turns, args.verbose)
        results.append(r)
        if not args.verbose:
            status = f"extinct@T{r['extinction_turn']}" if r['extinct'] else "alive"
            cp = r['checkpoints'].get(args.turns, r['checkpoints'].get(max(r['checkpoints']) if r['checkpoints'] else 0, {}))
            if cp:
                print(f"  seed={seed}: {status} soc<.25={cp.get('social_below_025', '?')}% "
                      f"aut<.30={cp.get('autonomy_below_pct', '?')}% "
                      f"bonds={cp.get('bonds_per_agent', '?')} sat={cp.get('satisfaction_mean', '?')}")
            else:
                print(f"  seed={seed}: {status}")

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY — {args.seeds} seeds × {args.turns} turns")
    print(f"{'='*80}")

    extinct = sum(1 for r in results if r['extinct'])
    print(f"Extinctions: {extinct}/{len(results)}")

    for cp_turn in CHECKPOINTS:
        if cp_turn > args.turns:
            continue
        cp_data = [r['checkpoints'].get(cp_turn) for r in results if cp_turn in r['checkpoints']]
        if not cp_data:
            continue
        n = len(cp_data)
        print(f"\n  T{cp_turn} ({n} seeds alive):")
        for key in ["alive", "social_mean", "social_below_025", "social_below_035",
                     "autonomy_mean", "autonomy_below_pct",
                     "safety_below_pct", "satisfaction_mean", "satisfaction_above_fert_pct",
                     "bonds_per_agent", "mem_slots_per_agent", "mem_intensity_mean"]:
            vals = [d[key] for d in cp_data if key in d]
            if vals:
                mean_val = sum(vals) / len(vals)
                min_val = min(vals)
                max_val = max(vals)
                print(f"    {key}: mean={mean_val:.2f} min={min_val:.2f} max={max_val:.2f}")


if __name__ == "__main__":
    main()
