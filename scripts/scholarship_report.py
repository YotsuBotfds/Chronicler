#!/usr/bin/env python3
"""Seats of learning in a run (``--scholarship``).

``scholarship_report.py RUN_DIR [--seat INDEX]``
    Each seat's record (or one seat's) with the event text the simulation
    wrote, from ``RUN_DIR/state.json``; then the techniques its region's
    civ adopted from fleeing scholars, the accounts its own scholars wrote
    (from the historiography sidecar) and the run's counters.

See docs/integration/scholarship.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

from chronicler import historiography as H
from chronicler.models import WorldState
from chronicler.scholarship import seat_history


def report(run_dir: Path, seat: int | None = None) -> list[str]:
    path = run_dir / "state.json"
    world = WorldState.load(path)
    H.load_sidecar(world, path)
    state = world.scholarship
    if state is None:
        return ["no seats of learning in this run (--scholarship was off)"]
    indices = range(len(state.seats)) if seat is None else [seat]
    hist = H.state_of(world)
    lines: list[str] = []
    for i in indices:
        lines.extend(seat_history(world, i))
        carried = [e for e in world.events_timeline if e.event_type == "technique_adopted"
                   and "from scholars fleeing" in e.description
                   and e.description.endswith(world.regions[state.seats[i].region].name)]
        for ev in carried:
            lines.append(f"  {ev.turn:>4}: carried: {ev.description}")
        if hist is not None:
            for acc in hist.accounts:
                if acc.chronicler == f"seat:{i}":
                    lost = f" [lost turn {acc.lost_turn}: {acc.lost_cause}]" if acc.lost_turn else ""
                    lines.append(f"  {acc.turn:>4}: its scholars wrote: {acc.text}{lost}")
    counters = {k: v for k, v in state.counters.items() if v}
    lines.append(f"counters: {counters}")
    return lines


def main(argv: list[str]) -> int:
    seat = None
    if "--seat" in argv:
        k = argv.index("--seat")
        seat = int(argv[k + 1])
        argv = argv[:k] + argv[k + 2:]
    if len(argv) != 1:
        print(__doc__)
        return 2
    print("\n".join(report(Path(argv[0]), seat)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
