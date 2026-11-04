"""Emit a tiny deterministic control for comparison with untouched public main.

Select source/native builds with PYTHONPATH. No narrative or external services.
Only newly added, default-valued aid metadata is excluded from the world dump.
"""
import argparse
import json

import pyarrow as pa

import chronicler
import chronicler_agents
from chronicler.models import ActionType
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["off", "hybrid"], required=True)
    args = parser.parse_args()
    world = generate_world(seed=42, num_regions=3, num_civs=1)
    world.agent_mode = args.mode
    bridge = None
    if args.mode == "hybrid":
        from chronicler.agent_bridge import AgentBridge
        bridge = AgentBridge(world, mode="hybrid")
    snapshots = []
    worlds = []
    try:
        for turn in range(4):
            run_turn(world, lambda civ, w: ActionType.DEVELOP, lambda w, events: "",
                     seed=42 + turn, agent_bridge=bridge)
            data = world.model_dump(mode="json")
            for key in ("mutual_aid_enabled", "mutual_aid_state", "mutual_aid_last_dispatch_turn",
                        "mutual_aid_last_transfers"):
                data.pop(key, None)
            worlds.append(data)
            if bridge:
                snapshots.append(pa.record_batch(bridge.get_snapshot()).to_pydict())
        print(json.dumps({"source": chronicler.__file__, "native": chronicler_agents.__file__,
                          "mode": args.mode, "worlds": worlds, "agent_snapshots": snapshots}, sort_keys=True))
    finally:
        if bridge:
            bridge.close()
