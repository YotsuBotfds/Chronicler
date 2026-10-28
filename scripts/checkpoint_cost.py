#!/usr/bin/env python3
"""Size and save/load time of an exact checkpoint (``chronicler.run_checkpoint``).

Runs the real CLI pipeline in this process (``execute_run``,
``--simulate-only``) on the 12-region template world scaled to about
``--target`` starting agents (as ``scripts/turn_speed_identity.py``), and at
the end of turn ``--warmup`` writes the checkpoint ``--repeat`` times and
reads each back, timing every stage: the native state blob(s), the Python
pickle, compression, the header and the atomic write; on load, the read
and verification, the native restore and the Python restore. Also reports
the alive agents and each section's raw and compressed size, and how other zlib levels would compress the same bytes.

Example::

    RAYON_NUM_THREADS=1 python scripts/checkpoint_cost.py --target 43700 --warmup 20 --out cost52k.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
import zlib
from pathlib import Path


def _stats(values: list[float]) -> dict:
    return {"median": statistics.median(values), "min": min(values), "max": max(values)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--target", type=int, default=43700)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--regions", type=int, default=12)
    p.add_argument("--civs", type=int, default=4)
    p.add_argument("--agents", default="hybrid")
    p.add_argument("--warmup", type=int, default=20)
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--cli-arg", action="append", default=[])
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args(argv)

    import chronicler.main as cm
    from chronicler import run_checkpoint as rc
    from chronicler.utils import sync_civ_population

    original = cm.generate_world

    def scaled(*args, **kwargs):
        world = original(*args, **kwargs)
        if a.target:
            mult = a.target / max(1, sum(r.population for r in world.regions))
            for region in world.regions:
                region.carrying_capacity = max(1, round(region.carrying_capacity * mult))
                region.population = round(region.population * mult)
            for civ in world.civilizations:
                sync_civ_population(civ, world)
        return world

    cm.generate_world = scaled
    result: dict = {"target": a.target, "seed": a.seed, "agents": a.agents, "warmup": a.warmup}
    original_write = cm._write_exact_checkpoint

    def measure(template, world, memories, history, chronicle_entries, era_reflections, pending,
                run_start, seed, num_turns, agent_bridge, ecology_runtime, politics_runtime,
                economy_tracker, scenario_config, run_config, live=None):
        state = rc.RunState(
            world=world, memories=memories, history=history, chronicle_entries=chronicle_entries,
            era_reflections=era_reflections, pending_injections=pending, start_turn=run_start,
            seed=seed, num_turns=num_turns, agent_bridge=agent_bridge,
            ecology_runtime=ecology_runtime, politics_runtime=politics_runtime,
            economy_tracker=economy_tracker, scenario_config=scenario_config, run_config=run_config,
            live=live,
        )
        sim = getattr(agent_bridge, "_sim", None)
        if sim is not None:
            result["alive_agents"] = int(sim.last_tick_alive)
        writes, reads = [], []
        directory = Path(template).parent
        for i in range(a.repeat):
            path = directory / f"measure_{i}.ckpt"
            report = rc.write_checkpoint(path, state)
            writes.append(report)
            loaded = rc.read_checkpoint(path)
            reads.append(loaded)
            # The restored state continues the same run: same pool, same turn.
            assert loaded.state.world.turn == world.turn
            del loaded
            if i:
                path.unlink()
        first = writes[0]
        result["turn"] = world.turn
        result["bytes"] = first.bytes
        result["raw_bytes"] = first.raw_bytes
        result["sections"] = first.sections
        header, body = rc.read_header(directory / "measure_0.ckpt")
        result["sections_raw"] = {s["name"]: s["raw_length"] for s in header["sections"]}
        result["write_seconds"] = _stats([w.seconds for w in writes])
        result["write_stages"] = {k: _stats([w.timings[k] for w in writes]) for k in first.timings}
        result["read_seconds"] = _stats([r.seconds for r in reads])
        result["read_stages"] = {k: _stats([r.timings[k] for r in reads]) for k in reads[0].timings}
        levels = {}
        raws = [rc._section(directory / "measure_0.ckpt", header, body, s["name"])
                for s in header["sections"]]
        for level in (1, 3, 6):
            t0 = time.perf_counter()
            size = sum(len(zlib.compress(data, level)) for data in raws)
            levels[str(level)] = {"bytes": size, "seconds": time.perf_counter() - t0}
        result["zlib_levels"] = levels
        (directory / "measure_0.ckpt").unlink()
        return original_write(template, world, memories, history, chronicle_entries, era_reflections,
                              pending, run_start, seed, num_turns, agent_bridge, ecology_runtime,
                              politics_runtime, economy_tracker, scenario_config, run_config,
                              live=live)

    cm._write_exact_checkpoint = measure
    with tempfile.TemporaryDirectory(prefix="ckpt-cost-") as tmp:
        tmp = Path(tmp)
        args = cm._build_parser().parse_args([
            "--seed", str(a.seed), "--turns", str(a.warmup + 1), "--regions", str(a.regions),
            "--civs", str(a.civs), "--agents", a.agents, "--simulate-only",
            "--output", str(tmp / "chronicle.md"), "--state", str(tmp / "state.json"),
            "--checkpoint-every", str(a.warmup), "--checkpoint", str(tmp / "checkpoint.ckpt"),
            *a.cli_arg,
        ])
        args.reflection_interval = 10
        args.tuning_overrides = {}
        t0 = time.perf_counter()
        cm.execute_run(args)
        result["run_seconds"] = time.perf_counter() - t0
    text = json.dumps(result, indent=2)
    print(text)
    if a.out:
        a.out.write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
