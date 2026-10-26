#!/usr/bin/env python3
"""Print every guild's record from a run's ``state.json``.

``guilds_report.py RUN_DIR [--guild INDEX] [--counters]``

For each guild: the header (kind, region, founding, peak masters, standing),
its history with the event text the simulation wrote (privileges, levies,
threats, its movements and guild charter), then the record of each movement
it raised with the lasting reform it won (``chronicler.guilds.guild_history``).
``--counters`` adds the world's guild counters. See docs/integration/guilds.md.
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
    from chronicler.guilds import guild_history
    from chronicler.models import WorldState
    world = WorldState.load(state)
    if world.guilds is None:
        print("guilds are off in this run")
        return 1
    only = int(argv[argv.index("--guild") + 1]) if "--guild" in argv else None
    for i in range(len(world.guilds.guilds)):
        if only is None or i == only:
            print("\n".join(guild_history(world, i)))
    if "--counters" in argv:
        print({k: v for k, v in world.guilds.counters.items() if v})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
