#!/usr/bin/env python3
"""Fixed paired evaluation; protocol: docs/integration/shortfall-priority-evaluation.md.

Uses the production reserve kernels and existing native probe/checkpoint tools.
No policy constants are changed. Outputs must be fresh external directories.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import json
import os
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KEY = "grain_reserves.shortfall_priority"
CASES = {
    "scarce_budget": ((1.0, 0.6), (1.0, 0.0)),
    "multiple_hungry": ((0.5, 0.2), (0.0, 0.0)),
    "future_shortage": ((1.0, 0.6), (0.0, 1.0)),
    "disconnected": ((1.0, 0.6), (1.0, 0.0)),
    "ownership_change": ((1.0, 0.6), (1.0, 0.0)),
    "no_supply": ((1.0, 0.6), (1.0, 0.0)),
}
NUMERIC_ENV = {"PYTHONHASHSEED": "0", "RAYON_NUM_THREADS": "1",
               "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
               "CHRONICLER_CHECK_RESOURCES": "1"}


def _write(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _without_priority(data):
    """Normalize only the declared override, leaving all other content intact."""
    if isinstance(data, dict):
        return {k: _without_priority(v) for k, v in data.items() if k != KEY}
    if isinstance(data, list):
        return [_without_priority(v) for v in data]
    return data


def fixture(case, priority):
    from chronicler import grain_reserves as g
    from chronicler.models import Disposition
    from chronicler.world_gen import generate_world

    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.turn, world.agent_mode = 30, "demographics-only"
    g.set_grain_reserves_enabled(world, True)
    if priority is not None:
        world.tuning_overrides[KEY] = priority
    for ci, civ in enumerate(world.civilizations):
        civ.treasury = 30 if ci == 0 else 0
        civ.regions = [r.name for r in world.regions[:3]] if ci == 0 else []
    for rid, region in enumerate(world.regions):
        region.controller = world.civilizations[0].name if rid < 3 else None
        region.population = 20 if rid < 3 else 0
        region.terrain = "plains"
        region.stockpile.goods = {}
        neighbors = ([1, 2] if rid == 0 else [0]) if rid < 3 else []
        if case == "disconnected":
            neighbors = [1] if rid == 0 else ([0] if rid == 1 else [])
        region.adjacencies = [world.regions[i].name for i in neighbors]
    for row in world.relationships.values():
        for rel in row.values():
            rel.disposition = Disposition.NEUTRAL
    world.regions[0].stockpile.goods = {"grain": 40.0 if case == "no_supply" else 80.0}
    state = g._ensure(world)
    for rid in range(3):
        state.granaries[rid].owner = 0
    for rid, stock in ((1, 0.0), (2, 2.0)):
        granary = state.granaries[rid]
        granary.grain = stock
        granary.observed, granary.harvest_mean, granary.harvest_sq = 12, 0.5, 0.5
    return world


def _economy(world, food):
    from chronicler.economy import EconomyResult
    result = EconomyResult()
    for rid, region in enumerate(world.regions):
        demand = 0.5 * region.population
        suff = food[rid - 1] if rid in (1, 2) else 1.0
        result.food_sufficiency[region.name] = suff
        result.market_demand[region.name] = (demand, 0.0, 0.0, 0.0)
        result.market_supply[region.name] = (
            max(suff * demand, sum(region.stockpile.goods.values())), 0.0, 0.0, 0.0)
        result.forage_output[region.name] = demand
    return result


def _continue(world, case):
    from chronicler import grain_reserves as g
    if case == "ownership_change":
        name = world.regions[2].name
        world.civilizations[0].regions.remove(name)
        world.civilizations[1].regions.append(name)
        world.regions[2].controller = world.civilizations[1].name
    world.turn += 1
    result = _economy(world, CASES[case][1])
    g.open_granaries(world, result)
    g.tick_grain_reserves(world, economy_result=None)
    return [result.food_sufficiency[world.regions[rid].name] for rid in (1, 2)]


def constructed_arm(case, priority):
    from chronicler import grain_reserves as g
    from chronicler.grain_reserves_state import BOUGHT, RELEASED
    from chronicler.models import WorldState

    world = fixture(case, priority)
    input_state = _without_priority(world.model_dump(mode="json"))
    input_digest = hashlib.sha256(json.dumps(input_state, sort_keys=True).encode()).hexdigest()
    result = _economy(world, CASES[case][0])
    before_food, before_rng = dict(result.food_sufficiency), random.getstate()
    grain_before = sum(r.stockpile.goods.get("grain", 0) for r in world.regions) + 2.0
    g.ReserveLedger.begin(world, world.grain_reserves)
    g.tick_grain_reserves(world, economy_result=result)
    assert result.food_sufficiency == before_food
    purchases = [f.model_dump() for f in world.grain_reserves.flows if f.kind == BOUGHT]
    restored = WorldState.model_validate_json(world.model_dump_json())
    food = _continue(world, case)
    assert _continue(restored, case) == food
    assert restored.model_dump() == world.model_dump()
    assert random.getstate() == before_rng
    state = world.grain_reserves
    remaining = sum(r.stockpile.goods.get("grain", 0) for r in world.regions)
    remaining += sum(s.grain for s in state.granaries)
    sinks = sum(state.counters[k] for k in ("released", "spoiled", "transit_loss", "seized"))
    assert abs(grain_before - remaining - sinks) < 1e-9
    assert world.civilizations[0].treasury == 30 - sum(p["cost"] for p in purchases)
    assert world.regions[0].stockpile.goods["grain"] >= 40
    return {
        "input_sha256_without_priority": input_digest, "purchases": purchases,
        "next_food": food, "next_grain": [state.granaries[i].grain for i in (1, 2)],
        "next_release": [sum(f.amount for f in state.flows if f.kind == RELEASED and f.region == i)
                         for i in (1, 2)],
        "next_owner": [state.granaries[i].owner for i in (1, 2)],
        "treasury": [c.treasury for c in world.civilizations],
        "source_stock": world.regions[0].stockpile.goods["grain"],
        "counters": state.counters, "final_state": _without_priority(world.model_dump(mode="json")),
    }


def constructed(out):
    report = {}
    for case in CASES:
        absent, off, on = (constructed_arm(case, priority) for priority in (None, 0, 1))
        assert absent == off, f"default parity: {case}"
        assert on == constructed_arm(case, 1), f"determinism: {case}"
        assert off["input_sha256_without_priority"] == on["input_sha256_without_priority"]
        for arm in (off, on):
            arm.pop("final_state")
        report[case] = {"off": off, "on": on,
                        "food_delta": [b - a for a, b in zip(off["next_food"], on["next_food"])]}
    _write(out / "constructed.json", report)
    return report


def _native_identity():
    import chronicler
    import chronicler_agents as native
    import chronicler_agents.chronicler_agents as compiled
    expected_tree = "edb263686adb7ea5e23864146a5f7d0c5a163da4"
    tree = subprocess.check_output(["git", "rev-parse", "HEAD:chronicler-agents"], cwd=ROOT, text=True).strip()
    assert tree == expected_tree, f"prebuilt native source does not match: {tree}"
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "chronicler-agents"], cwd=ROOT, check=True)
    prebuilt_source = "32ac587908b28167e45ff105f62ace988fbb8e12"
    built_tree = subprocess.check_output(
        ["git", "rev-parse", f"{prebuilt_source}:chronicler-agents"], cwd=ROOT, text=True).strip()
    assert built_tree == tree
    assert Path(chronicler.__file__).resolve().parent == ROOT / "src/chronicler"
    binary = Path(compiled.__file__)
    assert any(str(binary).endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES)
    assert all(isinstance(getattr(native, name), type) for name in
               ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"))
    return {"rust_tree": tree, "binary": str(binary),
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "prebuilt_source": prebuilt_source,
            "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "python": sys.executable, "python_version": sys.version,
            "python_source": str(Path(chronicler.__file__).resolve()),
            "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}


def native(out):
    # Imported here so the constructed lane never probes native availability.
    from checkpoint_identity import _compare_resume
    from cities_identity import compare
    from grain_reserves_probe import summarize_run
    from chronicler.grain_reserves import RESERVE_LEDGER_FILENAME, read_reserve_ledger

    identity = _native_identity()
    _write(out / "identity.json", identity)
    env = {**os.environ, **NUMERIC_ENV, "PYTHONPATH": str(ROOT / "src")}

    def run(name, cli, probe):
        directory = out / name
        command = ([sys.executable, str(ROOT / "scripts/grain_reserves_probe.py"),
                    "run", str(directory), "--"] if probe else
                   [sys.executable, "-m", "chronicler.main"])
        command += [*cli, "--simulate-only", "--output", str(directory / "chronicle.md"),
                    "--state", str(directory / "state.json")]
        with (out / f"{name}.log").open("w") as log:
            subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        return directory

    base = ["--seed", "42", "--regions", "8", "--civs", "4", "--turns", "60",
            "--agents", "hybrid", "--grain-reserves", "--validation-sidecar"]
    directories = {}
    summary = {"identity": identity, "metrics": {}, "checks": {}}
    for name, priority in (("absent", None), ("off", 0), ("on", 1), ("repeat", 1)):
        cli = list(base)
        if priority is not None:
            tuning = out / f"{name}.yaml"
            tuning.write_text(f"grain_reserves:\n  shortfall_priority: {priority}\n")
            cli += ["--tuning", str(tuning)]
        if name in ("off", "on"):
            cli += ["--checkpoint-turns", "30"]
        directory = run(name, cli, True)
        directories[name] = directory
        summary["metrics"][name] = summarize_run(directory)
        if name in ("off", "on"):
            resumed = run(f"{name}_resume", ["--resume", str(directory / "checkpoint_turn_30.ckpt")], False)
            count, differences = _compare_resume(directory, resumed, 30)
            differences = [d for d in differences if d not in (
                "only in base: probe_turns.jsonl", "only in base: checkpoint_turn_30.ckpt")]
            summary["checks"][f"{name}_resume"] = {"files": count, "differences": differences}
        _write(out / "native.json", summary)

    def normalize(_name, data):
        cleaned = _without_priority(data)
        data.clear()
        data.update(cleaned)

    for name, a, b, normalizer in (("default_parity", "absent", "off", normalize),
                                   ("determinism", "on", "repeat", None)):
        count, differences = compare(directories[a], directories[b], normalize=normalizer)
        differences = [d for d in differences if "checkpoint_turn_30.ckpt" not in d]
        summary["checks"][name] = {"files": count, "differences": differences}
    off, on = summary["metrics"]["off"], summary["metrics"]["on"]
    summary["delta"] = {k: on[k] - off[k] for k in off
                        if isinstance(off[k], (int, float)) and k != "seed"}
    purchases = {}
    for name in ("off", "on"):
        ledger = read_reserve_ledger(directories[name] / RESERVE_LEDGER_FILENAME)
        purchases[name] = {(t, r): amount for t, r, amount in
                           zip(ledger["turn"], ledger["region"], ledger["bought"]) if amount > 0}
    off_buys, on_buys = purchases["off"], purchases["on"]
    summary["purchasing"] = {
        "off_purchase_region_turns": len(off_buys), "on_purchase_region_turns": len(on_buys),
        "changed_purchase_region_turns": sum(off_buys.get(key, 0) != on_buys.get(key, 0)
                                            for key in off_buys.keys() | on_buys.keys())}
    _write(out / "native.json", summary)
    assert all(c["files"] > 0 and not c["differences"] for c in summary["checks"].values())
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=("constructed", "native"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if os.environ.get("PYTHONHASHSEED") != "0":
        parser.error("launch with PYTHONHASHSEED=0 (it cannot be changed after startup)")
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ.update(NUMERIC_ENV)
    result = constructed(args.output) if args.lane == "constructed" else native(args.output)
    print(json.dumps({"lane": args.lane, "cases": len(result) if args.lane == "constructed" else 1,
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()
