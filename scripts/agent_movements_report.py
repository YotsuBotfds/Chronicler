#!/usr/bin/env python3
"""Print every agent movement's record from a run's ``state.json``.

``agent_movements_report.py RUN_DIR [--counters]``

For each movement: the header (creed, founding, target, leader, idea, peak,
demands, martyrs, end) and its history with the event text the simulation
wrote (``chronicler.agent_movements.movement_history``). ``--counters`` adds
the world's counters. See docs/integration/agent-movements.md.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    run = Path(argv[0])
    state = run / "state.json" if run.is_dir() else run
    from chronicler.agent_movements import movement_history
    from chronicler.models import WorldState
    world = WorldState.load(state)
    if world.agent_movements is None:
        print("agent movements are off in this run")
        return 1
    for i in range(len(world.agent_movements.movements)):
        print("\n".join(movement_history(world, i)))
    if "--counters" in argv:
        print({k: v for k, v in world.agent_movements.counters.items() if v})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
