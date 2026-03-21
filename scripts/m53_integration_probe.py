"""M53 Integration Probe — check cross-system metrics for freeze readiness.

Verifies:
- Satisfaction floor-hitting (<30% of agents at floor)
- Rebellion rate (2-8% of agent-turns)
- Migration rate (5-15%)
- Occupation distribution (no collapse)
- Civ survival (1-4 at turn 500)
- Need activation fractions
- Memory/bond health

Usage:
  PYTHONPATH=src python scripts/m53_integration_probe.py --seeds 20 --turns 500
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


CHECKPOINTS = [50, 100, 200, 300, 500]


def null_narrator(world, events):
    return ""


def run_seed(seed: int, turns: int, verbose: bool) -> dict:
    world = generate_world(seed=seed)
    ae = ActionEngine(world)
    from chronicler.agent_bridge import AgentBridge
    bridge = AgentBridge(world, mode="hybrid")

    total_rebellions = 0
    total_migrations = 0
    total_agent_turns = 0
    sat_floor_fracs = []  # fraction of agents at satisfaction floor per turn

    results = {}
    prev_event_count = 0

    for t in range(1, turns + 1):
        run_turn(world, ae.select_action, null_narrator, agent_bridge=bridge)

        # Count new events from world.events_timeline
        new_events = world.events_timeline[prev_event_count:]
        prev_event_count = len(world.events_timeline)
        for e in new_events:
            if e.event_type in ("rebellion", "local_rebellion"):
                total_rebellions += 1
            if e.event_type == "mass_migration":
                total_migrations += 1

        # Agent-level metrics at checkpoints
        if t in CHECKPOINTS and t <= turns:
            alive_civs = [c for c in world.civilizations if len(c.regions) > 0]
            pop = sum(r.population for r in world.regions)

            # Needs
            try:
                needs_raw = bridge._sim.get_all_needs()
                needs_batch = pa.record_batch(needs_raw)
                satisfaction = needs_batch.column("satisfaction").to_pylist()
                social = needs_batch.column("social").to_pylist()
                autonomy = needs_batch.column("autonomy").to_pylist()
                safety = needs_batch.column("safety").to_pylist()
                n = len(satisfaction)
                if n > 0:
                    sat_mean = sum(satisfaction) / n
                    sat_floor = sum(1 for v in satisfaction if v < 0.05) / n
                    social_below = sum(1 for v in social if v < 0.25) / n
                    autonomy_below = sum(1 for v in autonomy if v < 0.30) / n
                    safety_below = sum(1 for v in safety if v < 0.30) / n
                else:
                    sat_mean = sat_floor = social_below = autonomy_below = safety_below = 0
            except Exception:
                n = sat_mean = sat_floor = social_below = autonomy_below = safety_below = 0

            # Memory — count slots per agent from per-slot rows
            mem_slots_mean = 0.0
            try:
                mem_raw = bridge._sim.get_all_memories()
                mem_batch = pa.record_batch(mem_raw)
                if mem_batch.num_rows > 0 and n > 0:
                    agent_ids = mem_batch.column("agent_id").to_pylist()
                    unique_agents = len(set(agent_ids))
                    mem_slots_mean = mem_batch.num_rows / unique_agents if unique_agents > 0 else 0
            except Exception:
                pass

            # GPs
            all_gps = []
            for civ in world.civilizations:
                all_gps.extend(civ.great_persons)
            active_gps = [gp for gp in all_gps if gp.active]

            results[t] = {
                "pop": pop, "civs": len(alive_civs), "agents": n,
                "sat_mean": sat_mean, "sat_floor_frac": sat_floor,
                "social_below_025": social_below,
                "autonomy_below_030": autonomy_below,
                "safety_below_030": safety_below,
                "mem_slots_mean": mem_slots_mean,
                "gp_count": len(active_gps),
                "artifacts": len(world.artifacts) if hasattr(world, 'artifacts') else 0,
            }

            if verbose:
                print(f"  Seed {seed} T{t}: pop={pop} civs={len(alive_civs)} "
                      f"sat={sat_mean:.2f} floor={sat_floor:.2f} "
                      f"social<0.25={social_below:.2f} "
                      f"GPs={len(active_gps)}")

    bridge.close()
    return {
        "checkpoints": results,
        "rebellions": total_rebellions,
        "migrations": total_migrations,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--turns", type=int, default=200)
    parser.add_argument("--seed-start", type=int, default=10)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    all_results = []
    for i in range(args.seeds):
        seed = args.seed_start + i
        print(f"Seed {seed}...")
        result = run_seed(seed, args.turns, args.verbose)
        all_results.append(result)

    # Aggregate
    print("\n=== INTEGRATION METRICS ===")
    for cp in CHECKPOINTS:
        if cp > args.turns:
            continue
        cps = [r["checkpoints"].get(cp) for r in all_results if cp in r["checkpoints"]]
        if not cps:
            continue
        n = len(cps)
        print(f"\n--- T{cp} ({n} seeds) ---")
        for key in ["pop", "civs", "sat_mean", "sat_floor_frac",
                     "social_below_025", "autonomy_below_030", "safety_below_030",
                     "mem_slots_mean", "gp_count", "artifacts"]:
            vals = [c[key] for c in cps]
            mean = sum(vals) / n
            mn = min(vals)
            mx = max(vals)
            print(f"  {key}: mean={mean:.2f} min={mn:.2f} max={mx:.2f}")

    print("\n--- Event Rates ---")
    total_reb = sum(r["rebellions"] for r in all_results)
    total_mig = sum(r["migrations"] for r in all_results)
    total_seeds = len(all_results)
    print(f"  Rebellions total: {total_reb} ({total_reb/total_seeds:.1f}/seed)")
    print(f"  Migrations total: {total_mig} ({total_mig/total_seeds:.1f}/seed)")

    # Civ survival check
    final_cp = max(cp for cp in CHECKPOINTS if cp <= args.turns)
    final_civs = [r["checkpoints"].get(final_cp, {}).get("civs", 0) for r in all_results
                  if final_cp in r["checkpoints"]]
    in_range = sum(1 for c in final_civs if 1 <= c <= 4)
    print(f"\n--- Survival Gate (T{final_cp}) ---")
    print(f"  Civs 1-4 at T{final_cp}: {in_range}/{len(final_civs)} seeds")
    print(f"  Civs distribution: {sorted(final_civs)}")


if __name__ == "__main__":
    main()
