#!/usr/bin/env python3
"""A constructed seed-42 distress-associated migration development example.

An agent's dominant migration term is a diagnostic contribution, not proof of
forced flight or a sole cause. Native agents and model food goods are distinct.
The case reduces initial receiving-region yields; no shock event is injected.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

CONDITIONS = {
    "seed": 42, "regions": 5, "civilizations": 2, "turns": 4,
    "initial_grain_region_0": 100.0, "initial_grain_other_regions": 0.0,
    "region_2_initial_yield_multiplier": 0.25,
    "native_liquid_requirement_per_person": 1.0,
    "qualification": "development variant after an unconstrained-receiver result; not held-out or forced eviction",
}


def _agents(bridge):
    import pyarrow as pa
    return {row["id"]: row for row in pa.record_batch(bridge._sim.get_snapshot()).to_pylist()}


def _advance(world, bridge):
    from chronicler.action_engine import ActionEngine
    from chronicler.models import migration_driver_name
    from chronicler.simulation import run_turn_result
    pre = _agents(bridge)
    event_start = len(world.agent_events_raw)
    engine = ActionEngine(world)
    result = run_turn_result(world, lambda civ, w: engine.select_action(civ, seed=w.seed),
        lambda w, events: "", seed=world.seed + world.turn, agent_bridge=bridge)
    post = _agents(bridge)
    moves = []
    for event in world.agent_events_raw[event_start:]:
        if event.event_type == "migration":
            row = asdict(event)
            row["driver_name"] = migration_driver_name(event.migration_driver)
            row["pre_region"] = pre.get(event.agent_id, {}).get("region")
            row["post_region"] = post.get(event.agent_id, {}).get("region")
            moves.append(row)
    observation = result.observation
    if observation.food_accounting is None or observation.household_mobility is None:
        raise RuntimeError("required native food and mobility observations are missing")
    return {
        "source_turn": observation.source_turn,
        "before_native_counts": dict(Counter(row["region"] for row in pre.values())),
        "after_native_counts": dict(Counter(row["region"] for row in post.values())),
        "migration_events": moves,
        "mobility": observation.household_mobility.as_dict(observation.completed_turn),
        "food": observation.food_accounting.as_dict(observation.completed_turn),
    }


def run(output: Path) -> dict:
    from chronicler.agent_bridge import AgentBridge
    from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
    from chronicler.world_gen import generate_world

    output.mkdir(parents=True, exist_ok=False)
    random.seed(42)
    world = generate_world(seed=42, num_regions=5, num_civs=2)
    world.agent_mode = "hybrid"
    for rid, region in enumerate(world.regions):
        region.stockpile.goods = {"grain": 100.0 if rid == 0 else 0.0}
    original_yields = list(world.regions[2].resource_base_yields)
    world.regions[2].resource_base_yields = [0.25 * v for v in original_yields]
    world.household_mobility_liquid_requirement = 1.0
    bridge = AgentBridge(world, mode="hybrid")
    try:
        history = [_advance(world, bridge) for _ in range(3)]
        checkpoint = output / "arrival.ckpt"
        write_checkpoint(checkpoint, RunState(world=world, agent_bridge=bridge, memories={}, history=history,
            chronicle_entries=[], era_reflections={}, pending_injections=[], start_turn=0, seed=42, num_turns=4))
        restored = read_checkpoint(checkpoint)
        if not restored.exact or restored.state.history != history:
            raise RuntimeError("arrival checkpoint did not preserve exact history")
        resumed, resumed_bridge = restored.state.world, restored.state.agent_bridge
        try:
            rng = random.getstate()
            expected = _advance(world, bridge)
            after_rng = random.getstate()
            random.setstate(rng)
            continued = _advance(resumed, resumed_bridge)
            if (continued != expected or random.getstate() != after_rng or
                    world.model_dump_json() != resumed.model_dump_json() or
                    bridge._sim.checkpoint_state() != resumed_bridge._sim.checkpoint_state()):
                raise RuntimeError("exact continuation mismatch after arrival")
            history.append(expected)
            result = {"conditions": CONDITIONS, "original_region_2_yields": original_yields,
                "effective_region_2_yields": [0.25 * v for v in original_yields],
                "timeline": history, "exact_resume": True,
                "final_native_sha256": hashlib.sha256(bytes(bridge._sim.checkpoint_state())).hexdigest()}
        finally:
            resumed_bridge.close()
    finally:
        bridge.close()
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh external output directory")
    args = parser.parse_args()
    run(args.output)
    print(json.dumps({"output": str(args.output), "exact_resume": True}))


if __name__ == "__main__":
    main()
