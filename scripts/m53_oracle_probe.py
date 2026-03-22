"""M53 Oracle Probe — run validation oracles against live simulation data.

Collects edge, memory, needs, event, and artifact data from live sims
and feeds it to validate.py oracle functions.

Usage:
  PYTHONPATH=src python scripts/m53_oracle_probe.py --seeds 20 --turns 200
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pyarrow as pa
from chronicler.world_gen import generate_world
from chronicler.simulation import run_turn
from chronicler.action_engine import ActionEngine
from chronicler.validate import (
    detect_communities, compute_needs_diversity,
    detect_inflection_points, compute_cohort_distinctiveness,
    check_artifact_lifecycle, classify_civ_arc,
)


def null_narrator(world, events):
    return ""



def run_seed(seed: int, turns: int) -> dict:
    world = generate_world(seed=seed)
    ae = ActionEngine(world)
    from chronicler.agent_bridge import AgentBridge
    bridge = AgentBridge(world, mode="hybrid")

    pop_series = []
    civ_pop_series = {}  # civ_name -> [pop per turn]
    snapshot_turn = max(turns // 2, 50)  # mid-game snapshot for oracle data

    edges = []
    needs_data = {}
    agent_data = {}
    mem_sigs = {}

    for t in range(1, turns + 1):
        run_turn(world, ae.select_action, null_narrator, agent_bridge=bridge)
        pop_series.append(sum(r.population for r in world.regions))
        for civ in world.civilizations:
            civ_pop_series.setdefault(civ.name, []).append(civ.population)

        # Snapshot at mid-game when population and bonds are richest
        if t == snapshot_turn:
            # Edges
            try:
                raw = bridge._sim.get_all_relationships()
                batch = pa.record_batch(raw)
                src = batch.column("agent_id").to_pylist()
                tgt = batch.column("target_id").to_pylist()
                bt = batch.column("bond_type").to_pylist()
                sent = batch.column("sentiment").to_pylist()
                for i in range(len(src)):
                    edges.append((src[i], tgt[i], bt[i], sent[i]))
            except Exception:
                pass

            # Needs snapshot
            try:
                raw = bridge._sim.get_all_needs()
                batch = pa.record_batch(raw)
                for name in batch.schema.names:
                    needs_data[name] = batch.column(name).to_pylist()
            except Exception:
                pass

            # Agent snapshot for demographics
            try:
                raw = bridge._sim.get_snapshot()
                batch = pa.record_batch(raw)
                # Column is 'id' not 'agent_id'
                for src, dst in [("id", "agent_id"), ("civ_affinity", "civ_affinity"),
                                 ("region", "region"), ("occupation", "occupation"),
                                 ("boldness", "boldness"), ("ambition", "ambition"),
                                 ("loyalty_trait", "loyalty_trait")]:
                    if src in batch.schema.names:
                        agent_data[dst] = batch.column(src).to_pylist()
            except Exception:
                pass

            # Memory signatures
            try:
                raw = bridge._sim.get_all_memories()
                batch = pa.record_batch(raw)
                aids = batch.column("agent_id").to_pylist()
                ets = batch.column("event_type").to_pylist()
                tns = batch.column("turn").to_pylist()
                ints = batch.column("intensity").to_pylist()
                for i in range(len(aids)):
                    mem_sigs.setdefault(aids[i], []).append((ets[i], tns[i], ints[i]))
            except Exception:
                pass

    # Convert AgentEventRecord objects to oracle-compatible dicts
    EVENT_TYPE_MAP = {"death": 0, "migration": 1, "rebellion": 2, "occupation_switch": 3,
                      "loyalty_flip": 4, "birth": 5, "dissolution": 6}
    all_events = []
    for e in world.agent_events_raw:
        et_int = EVENT_TYPE_MAP.get(e.event_type, -1)
        if et_int >= 0:
            all_events.append({"agent_id": e.agent_id, "event_type": et_int, "turn": e.turn})

    # Civ trajectories for arc classification (time series)
    civ_trajectories = {}
    for civ_name, pops in civ_pop_series.items():
        civ_trajectories[civ_name] = {"population": pops}

    # Bundle-like structure for artifact oracle
    artifacts_list = []
    for a in (world.artifacts if hasattr(world, 'artifacts') else []):
        artifacts_list.append({
            "artifact_type": a.artifact_type.value if hasattr(a.artifact_type, 'value') else str(a.artifact_type),
            "status": a.status.value if hasattr(a.status, 'value') else str(a.status),
            "mule_origin": getattr(a, 'mule_origin', False),
        })

    bridge.close()

    return {
        "pop_series": pop_series,
        "edges": edges,
        "mem_sigs": mem_sigs,
        "needs_data": needs_data,
        "agent_data": agent_data,
        "artifacts": artifacts_list,
        "civ_trajectories": civ_trajectories,
        "events": all_events,
        "turns": turns,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--turns", type=int, default=200)
    parser.add_argument("--seed-start", type=int, default=42)
    args = parser.parse_args()

    all_results = []
    for i in range(args.seeds):
        seed = args.seed_start + i
        print(f"Seed {seed}...", end=" ", flush=True)
        result = run_seed(seed, args.turns)
        all_results.append(result)
        print(f"pop={result['pop_series'][-1]} edges={len(result['edges'])} "
              f"arts={len(result['artifacts'])}")

    # --- Oracle 1: Community Detection ---
    print("\n=== ORACLE 1: Community Detection ===")
    seeds_with_communities = 0
    for i, r in enumerate(all_results):
        communities = detect_communities(r["edges"], r["mem_sigs"])
        qualifying = [c for c in communities if len(c) >= 3]
        if qualifying:
            seeds_with_communities += 1
    print(f"  Seeds with qualifying communities (>=3 agents): "
          f"{seeds_with_communities}/{args.seeds} — target >=15/{args.seeds}")
    o1_pass = seeds_with_communities >= int(args.seeds * 0.75)
    print(f"  {'PASS' if o1_pass else 'FAIL'}")

    # --- Oracle 2: Needs Diversity ---
    print("\n=== ORACLE 2: Needs Diversity ===")
    total_pairs = 0
    total_rate_diff = 0
    seeds_with_sign = 0
    for r in all_results:
        if not r["needs_data"] or "safety" not in r["needs_data"]:
            continue
        result = compute_needs_diversity(r["needs_data"], r["events"], "safety", 1)
        total_pairs += result.get("pairs_found", 0)
        total_rate_diff += result.get("rate_difference", 0)
        if result.get("rate_difference", 0) > 0:
            seeds_with_sign += 1
    mean_rate_diff = total_rate_diff / args.seeds if args.seeds > 0 else 0
    print(f"  Matched pairs (safety): {total_pairs} across {args.seeds} seeds")
    print(f"  Mean rate difference (low-high): {mean_rate_diff:.4f}")
    print(f"  Seeds with expected sign: {seeds_with_sign}/{args.seeds} — target >=60%")
    o2_pass = seeds_with_sign >= int(args.seeds * 0.60)
    print(f"  {'PASS' if o2_pass else 'FAIL'}")

    # --- Oracle 3: Era Inflection ---
    print("\n=== ORACLE 3: Era Inflection Points ===")
    seeds_with_inflections = 0
    total_inflections = 0
    for r in all_results:
        inflections = detect_inflection_points(r["pop_series"])
        if len(inflections) >= 2:
            seeds_with_inflections += 1
        total_inflections += len(inflections)
    pct = seeds_with_inflections / args.seeds * 100
    print(f"  Seeds with >=2 inflection points: "
          f"{seeds_with_inflections}/{args.seeds} ({pct:.0f}%) — target >=80%")
    print(f"  Total inflections: {total_inflections} ({total_inflections/args.seeds:.1f}/seed)")
    o3_pass = pct >= 80
    print(f"  {'PASS' if o3_pass else 'FAIL'}")

    # --- Oracle 4: Cohort Distinctiveness ---
    print("\n=== ORACLE 4: Cohort Distinctiveness ===")
    seeds_expected_direction = 0
    seeds_analyzed = 0
    for r in all_results:
        communities = detect_communities(r["edges"], r["mem_sigs"])
        if communities and r["agent_data"] and r["events"]:
            seeds_analyzed += 1
            result = compute_cohort_distinctiveness(
                communities, r["events"], r["agent_data"], event_type=1
            )
            if result["effect_direction"] == "community_lower":
                seeds_expected_direction += 1
    print(f"  Seeds analyzed: {seeds_analyzed}/{args.seeds}")
    print(f"  Seeds with community_lower migration: "
          f"{seeds_expected_direction}/{args.seeds} — target >=60%")
    o4_pass = seeds_expected_direction >= int(args.seeds * 0.60)
    print(f"  {'PASS' if o4_pass else 'FAIL'}")

    # --- Oracle 5: Artifact Lifecycle ---
    print("\n=== ORACLE 5: Artifact Lifecycle ===")
    bundles = []
    for r in all_results:
        bundles.append({
            "world_state": {"artifacts": r["artifacts"]},
            "metadata": {"total_turns": r["turns"]},
        })
    art_result = check_artifact_lifecycle(bundles)
    print(f"  Creation rate: {art_result['creation_rate_per_civ_per_100']:.2f}/civ/100t — target [1, 3]")
    print(f"  Type diversity OK: {art_result['type_diversity_ok']}")
    print(f"  Loss/destruction rate: {art_result['loss_destruction_rate']:.2f} — target [0.10, 0.30]")
    print(f"  Mule artifacts: {art_result['mule_artifact_count']}")
    print(f"  Total: {art_result['total_artifacts']}")

    # --- Oracle 6: Six Arcs ---
    print("\n=== ORACLE 6: Civilization Arcs ===")
    arc_families = set()
    arc_counts = {}
    for r in all_results:
        for civ_name, traj in r["civ_trajectories"].items():
            try:
                # Skip very short trajectories
                if len(traj.get("population", [])) < 10:
                    continue
                arc = classify_civ_arc(traj)
                arc_counts[arc] = arc_counts.get(arc, 0) + 1
                if arc != "stable":
                    arc_families.add(arc)
            except Exception:
                continue
    print(f"  Arc families found: {sorted(arc_families)} ({len(arc_families)}/6)")
    print(f"  Arc distribution: { {k: v for k, v in sorted(arc_counts.items())} }")
    # Dominance cap: no arc > 40% of all civs (including stable)
    total_civs = sum(arc_counts.values())
    dominance_ok = True
    if total_civs > 0:
        for arc, count in arc_counts.items():
            if count / total_civs > 0.40:
                print(f"  WARNING: {arc} dominates at {count/total_civs:.0%} (>40% cap)")
                dominance_ok = False
    o6_families_ok = len(arc_families) >= 5
    o6_pass = o6_families_ok and dominance_ok
    print(f"  Families: {'PASS' if o6_families_ok else 'FAIL'} ({len(arc_families)}/6, target >=5)")
    print(f"  Dominance cap: {'PASS' if dominance_ok else 'FAIL'} (no arc >40%)")
    print(f"  Overall: {'PASS' if o6_pass else 'FAIL'}")


if __name__ == "__main__":
    main()
