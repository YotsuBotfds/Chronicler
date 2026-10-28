"""Benchmark-only family cohort and fixed native food-input shock.

The unwrapped production-default identity matrix is separate. This fixture
preloads actual adult marriages and overrides condition inputs, not physical
food stocks. It is a performance stress test, not a balanced food intervention.
Run both interpreters with their own source on PYTHONPATH, using this exact
script. The frozen first pilot is seed42/20k/12regions/4civs,20warmup+8turns.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pyarrow as pa

import turn_phase_profile as profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case", choices=("cohort_control", "food_shock"), default="food_shock")
    parser.add_argument("--target", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--regions", type=int, default=12)
    parser.add_argument("--civs", type=int, default=4)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--turns", type=int, default=8)
    parser.add_argument("--keep-run", action="store_true")
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    import chronicler.agent_bridge as bridge_module
    import chronicler.main as cm

    source_root = Path(cm.__file__).resolve().parents[2]
    native = importlib.import_module("chronicler_agents.chronicler_agents")
    native_path = Path(native.__file__)
    chosen_pairs = []
    selection = {}
    exposure = []
    bridges = []
    worlds = []
    run_dirs = []
    previous_events = 0
    original_batch = bridge_module.build_region_batch

    def condition_batch(world, *a, **kw):
        batch = original_batch(world, *a, **kw)
        if not selection:
            if max(r.population for r in world.regions) > 50_000:
                raise ValueError("fixture region exceeds its registered 50k population cap")
            origin = min(range(len(world.regions)), key=lambda r: (-world.regions[r].population, r))
            indexes = {r.name: i for i, r in enumerate(world.regions)}
            neighbors = sorted(indexes[n] for n in world.regions[origin].adjacencies)
            selection.update(origin=origin, origin_name=world.regions[origin].name,
                             neighbors=neighbors, initial_population=[r.population for r in world.regions],
                             origin_food=0.05, neighbor_food=1.5, shock_start_turn=args.warmup)
        if args.case == "food_shock" and world.turn >= args.warmup:
            values = batch.column("food_sufficiency").to_pylist()
            for i in selection["neighbors"]:
                values[i] = 1.5
            values[selection["origin"]] = 0.05
            column = batch.schema.get_field_index("food_sufficiency")
            batch = batch.set_column(column, batch.schema.field(column), pa.array(values, type=pa.float32()))
        return batch

    bridge_module.build_region_batch = condition_batch
    original_init = bridge_module.AgentBridge.__init__

    def family_init(self, world, *a, **kw):
        original_init(self, world, *a, **kw)
        by_region = defaultdict(list)
        snapshot = self._sim.get_snapshot()
        for aid, region, age in zip(snapshot.column("id").to_pylist(),
                                    snapshot.column("region").to_pylist(),
                                    snapshot.column("age").to_pylist()):
            if age >= 20:
                by_region[int(region)].append(int(aid))
        for region in sorted(by_region):
            ids = sorted(by_region[region])
            chosen_pairs.extend((region, ids[i], ids[i + 1]) for i in range(0, len(ids) - 1, 2))
        if chosen_pairs:
            self.apply_relationship_ops([{"op_type": 1, "agent_a": a, "agent_b": b,
                                         "bond_type": 2, "sentiment": 50, "formed_turn": 0}
                                        for _, a, b in chosen_pairs])
        worlds.append(world)
        bridges.append(self)

    bridge_module.AgentBridge.__init__ = family_init
    original_execute = cm.execute_run

    def execute(run_args, *a, **kw):
        callback = kw.get("on_turn")

        def completed(*cb_args, **cb_kw):
            nonlocal previous_events
            world, bridge = worlds[0], bridges[0]
            events = world.agent_events_raw[previous_events:]
            previous_events = len(world.agent_events_raw)
            migration = Counter(e.region for e in events if e.event_type == "migration")
            exposure.append({"source_turn": world.turn - 1,
                             "migrations": sum(migration.values()),
                             "migrations_by_source_region": dict(sorted(migration.items())),
                             "population_after_turn": [r.population for r in world.regions],
                             "household": dict(bridge.household_stats[-1])})
            if callback:
                callback(*cb_args, **cb_kw)

        kw["on_turn"] = completed
        run_dirs.append(str(Path(run_args.output).parent))
        return original_execute(run_args, *a, **kw)

    cm.execute_run = execute
    opts = profile._parse(["--target", str(args.target), "--seed", str(args.seed),
                           "--regions", str(args.regions), "--civs", str(args.civs),
                           "--worldgen", "template", "--agents", "hybrid",
                           "--warmup", str(args.warmup), "--turns", str(args.turns),
                           "--no-instrument", "--run-root", str(args.out.parent),
                           *(["--keep-run"] if args.keep_run else [])])
    result = profile._child(opts)
    result.update(fixture_case=args.case, fixture=selection, exposure=exposure,
                  chosen_pairs_file=str(args.out.with_suffix(".pairs.json")),
                  chosen_pairs_count=len(chosen_pairs), run_dirs=run_dirs,
                  source_root=str(source_root),
                  source_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source_root, text=True).strip(),
                  native_path=str(native_path), native_sha256=hashlib.sha256(native_path.read_bytes()).hexdigest(),
                  harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.out.with_suffix(".pairs.json").write_text(json.dumps(chosen_pairs) + "\n")
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(profile.report(result))
    print(json.dumps({"source_turns": [r["source_turn"] for r in exposure[args.warmup:]],
                      "migrations": [r["migrations"] for r in exposure[args.warmup:]],
                      "household": [r["household"] for r in exposure[args.warmup:]]}))


if __name__ == "__main__":
    main()
