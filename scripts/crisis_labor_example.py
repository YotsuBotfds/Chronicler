#!/usr/bin/env python3
"""One constructed seed-42 poor-production and occupational-care development pair.

Both arms restore the same real hybrid pool at turn zero. The control disables
existing spouse care; the intervention enables it. This scenario is not an
infectious illness model, a drought-event effect, or a held-out evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

CONDITIONS = {
    "seed": 42, "turns": 8, "regions": 8, "civilizations": 4,
    "region_food_slots": [0, 255, 255], "region_base_yields": [0.05, 0.0, 0.0],
    "initial_grain": 0.0, "soil": 0.2, "water": 0.2,
    "occupational_injury_rate": 0.25, "recovery_work": 10.0,
    "comparison": "existing spouse-first care disabled versus enabled",
    "qualification": "constructed development example; not held-out or a disease model",
}


def run(output: Path) -> dict:
    from chronicler.action_engine import ActionEngine
    from chronicler.agent_bridge import AgentBridge
    from chronicler.health_care import set_health_care_enabled, snapshot_summary
    from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
    from chronicler.simulation import run_turn_result
    from chronicler.world_gen import generate_world

    output.mkdir(parents=True, exist_ok=False)
    random.seed(CONDITIONS["seed"])
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    for region in world.regions:
        region.resource_types = [0, 255, 255]
        region.resource_base_yields = [0.05, 0.0, 0.0]
        region.stockpile.goods = {"grain": 0.0}
        region.ecology.soil = 0.2
        region.ecology.water = 0.2
    set_health_care_enabled(world, True)
    world.health_care.injury_rate = 0.25
    world.health_care.recovery_work = 10.0
    bridge = AgentBridge(world, mode="hybrid")
    path = output / "common.ckpt"
    try:
        write_checkpoint(path, RunState(world=world, agent_bridge=bridge, memories={}, history=[],
            chronicle_entries=[], era_reflections={}, pending_injections=[], start_turn=0,
            seed=42, num_turns=8))
        original_native = hashlib.sha256(bytes(bridge._sim.checkpoint_state())).hexdigest()
        rng = random.getstate()
        arms = {}
        for name, enabled in (("care_off", False), ("care_on", True)):
            loaded = read_checkpoint(path)
            if not loaded.exact:
                raise RuntimeError("development pair requires an exact common checkpoint")
            w, b = loaded.state.world, loaded.state.agent_bridge
            try:
                if hashlib.sha256(bytes(b._sim.checkpoint_state())).hexdigest() != original_native:
                    raise RuntimeError("restored native pool differs from common checkpoint")
                w.health_care.care_enabled = enabled
                random.setstate(rng)
                timeline = []
                for _ in range(8):
                    engine = ActionEngine(w)
                    result = run_turn_result(w, lambda c, state: engine.select_action(c, seed=state.seed),
                        lambda state, events: "", seed=w.seed + w.turn, agent_bridge=b)
                    food = result.observation.food_accounting
                    if food is None:
                        raise RuntimeError("authoritative native food accounting is unavailable")
                    timeline.append({"source_turn": w.turn - 1,
                        "health_care": snapshot_summary(w),
                        "food_accounting": food.as_dict(result.observation.completed_turn),
                        "episodes": [episode.model_dump(mode="json") for episode in w.health_care.episodes]})
                arms[name] = {"timeline": timeline, "final_world": w.model_dump(mode="json"),
                    "final_native_sha256": hashlib.sha256(bytes(b._sim.checkpoint_state())).hexdigest()}
            finally:
                b.close()
    finally:
        bridge.close()
    result = {"conditions": CONDITIONS, "common_native_sha256": original_native, "arms": arms}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh external output directory")
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({"output": str(args.output), "common_native_sha256": result["common_native_sha256"]}))


if __name__ == "__main__":
    main()
