"""M53 Mule/GP/Legacy/Artifact Probe — check promotion, Mule, legacy, and artifact metrics.

Runs simulations and checks GP promotion frequency, Mule assignment rate,
legacy memory persistence, legitimacy activation, and artifact creation.

Usage:
  PYTHONPATH=src python scripts/m53_mule_probe.py --seeds 10 --turns 200
  PYTHONPATH=src python scripts/m53_mule_probe.py --seeds 20 --turns 500 --verbose
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

    gp_counts = {}
    mule_counts = {}
    artifact_counts = {}
    legacy_counts = {}
    succession_counts = 0
    gp_succession_counts = 0  # successions where new leader has agent_id (legitimacy active)

    for t in range(1, turns + 1):
        # Track succession events
        pre_leaders = {civ.name: (civ.leader.name if civ.leader else None) for civ in world.civilizations}
        run_turn(world, ae.select_action, null_narrator, agent_bridge=bridge)
        for civ in world.civilizations:
            if len(civ.regions) == 0:
                continue
            if civ.leader and pre_leaders.get(civ.name) and civ.leader.name != pre_leaders[civ.name]:
                succession_counts += 1
                if civ.leader.agent_id is not None:
                    gp_succession_counts += 1

        if t in CHECKPOINTS and t <= turns:
            all_gps = []
            for civ in world.civilizations:
                all_gps.extend(civ.great_persons)
            gps = [gp for gp in all_gps if gp.active]
            mules = [gp for gp in gps if gp.mule]
            gp_counts[t] = len(gps)
            mule_counts[t] = len(mules)
            artifact_counts[t] = len(world.artifacts) if hasattr(world, 'artifacts') else 0

            # Legacy memory check via bulk FFI
            legacy_count = 0
            try:
                mem_raw = bridge._sim.get_all_memories()
                mem_batch = pa.record_batch(mem_raw)
                if "is_legacy" in mem_batch.schema.names:
                    is_legacy = mem_batch.column("is_legacy").to_pylist()
                    legacy_count = sum(1 for v in is_legacy if v)
            except Exception:
                pass
            legacy_counts[t] = legacy_count

            if verbose:
                alive_civs = [c for c in world.civilizations if len(c.regions) > 0]
                pop = sum(r.population for r in world.regions)
                print(f"  Seed {seed} T{t}: pop={pop}, civs={len(alive_civs)}, "
                      f"GPs={len(gps)}, mules={len(mules)}, "
                      f"artifacts={artifact_counts[t]}, legacy_mems={legacy_count}")
                for gp in gps:
                    role = gp.role or "?"
                    age = t - gp.born_turn
                    mule_tag = " [MULE]" if gp.mule else ""
                    print(f"    GP: {gp.name} ({role}), age={age}, "
                          f"civ={gp.civilization}{mule_tag}")

    bridge.close()
    return {
        "gp": gp_counts, "mule": mule_counts, "artifacts": artifact_counts,
        "legacy": legacy_counts, "successions": succession_counts,
        "gp_successions": gp_succession_counts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=10)
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
    print("\n=== GP / MULE / ARTIFACT SUMMARY ===")
    for cp in CHECKPOINTS:
        if cp > args.turns:
            continue
        gps = [r["gp"].get(cp, 0) for r in all_results]
        mules = [r["mule"].get(cp, 0) for r in all_results]
        arts = [r["artifacts"].get(cp, 0) for r in all_results]
        gp_mean = sum(gps) / len(gps)
        mule_mean = sum(mules) / len(mules)
        art_mean = sum(arts) / len(arts)
        gp_max = max(gps)
        seeds_with_gp = sum(1 for g in gps if g > 0)
        seeds_with_mule = sum(1 for m in mules if m > 0)
        print(f"T{cp}: GP mean={gp_mean:.1f} max={gp_max} "
              f"({seeds_with_gp}/{len(gps)} seeds), "
              f"Mule mean={mule_mean:.1f} ({seeds_with_mule}/{len(gps)} seeds), "
              f"Artifacts mean={art_mean:.1f}")

    print("\n=== LEGACY MEMORY SUMMARY ===")
    for cp in CHECKPOINTS:
        if cp > args.turns:
            continue
        legs = [r["legacy"].get(cp, 0) for r in all_results]
        leg_mean = sum(legs) / len(legs)
        leg_max = max(legs)
        seeds_with_legacy = sum(1 for l in legs if l > 0)
        print(f"T{cp}: legacy_mems mean={leg_mean:.1f} max={leg_max} "
              f"({seeds_with_legacy}/{len(legs)} seeds)")

    print("\n=== LEGITIMACY / SUCCESSION SUMMARY ===")
    total_succ = sum(r["successions"] for r in all_results)
    total_gp_succ = sum(r["gp_successions"] for r in all_results)
    rate = total_gp_succ / total_succ * 100 if total_succ > 0 else 0
    print(f"Total successions: {total_succ}, GP-sourced: {total_gp_succ} "
          f"({rate:.1f}%) — target >20%")
    succ_per_seed = total_succ / len(all_results) if all_results else 0
    print(f"Mean successions/seed: {succ_per_seed:.1f}")


if __name__ == "__main__":
    main()
