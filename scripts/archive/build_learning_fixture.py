#!/usr/bin/env python3
"""Build the viewer's Learning fixture from a run's bundle.

``build_learning_fixture.py BUNDLE OUT [--every K]`` writes ``OUT``
(normally ``viewer/src/__fixtures__/learning_bundle.json``): every K-th
snapshot's ``turn`` and ``scholarship`` (and the last; ``civ_stats``
emptied), the seat events plus the events they cite (not the food reports),
and a world state with the regions' and civilizations' names and the final
``scholarship`` seats. Read with ``bundle_codec.load_bundle`` (bundle version
6 writes the history as changes between snapshots). As
``scripts/build_movements_fixture.py``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SEAT_EVENTS = {
    "seat_founded", "seat_rose", "seat_declined", "seat_patron", "seat_master", "seat_fell", "scholars_fled",
}
SEAT_FIELDS = ("region", "kind", "name", "founded_turn", "founder", "level", "peak_level", "peak_scholars",
               "teachers", "fallen_turn", "fall_cause", "refuge", "history")
FOOD = ("famine", "dearth", "famine_ended", "dearth_ended")


def _load(path: Path) -> dict:
    try:
        from chronicler.bundle_codec import load_bundle
    except ImportError:
        return json.loads(path.read_text())
    return load_bundle(path)


def build(bundle: dict, every: int = 1) -> dict:
    events = bundle["events_timeline"]
    by_id = {e.get("event_id"): e for e in events if e.get("event_id")}
    seats = bundle["world_state"]["scholarship"]["seats"]
    wanted = {eid for s in seats for _t, _k, eid in s["history"] if eid}
    wanted |= {e["event_id"] for e in events if e["event_type"] in SEAT_EVENTS and e.get("event_id")}
    # Cited events other than the food reports (with them the viewer would
    # read the fixture as a food record too).
    cited = {c for eid in wanted if eid in by_id for c in by_id[eid].get("causes", [])
             if c in by_id and by_id[c]["event_type"] not in FOOD}
    keep = wanted | cited
    world = bundle["world_state"]
    return {
        "metadata": {**{k: v for k, v in bundle["metadata"].items() if not k.endswith("_stats")},
                     "generated_at": "fixture"},
        "world_state": {
            "name": world["name"], "seed": world["seed"], "turn": world["turn"],
            "regions": [{"name": r["name"], "controller": r.get("controller"), "x": r.get("x"),
                         "y": r.get("y")} for r in world["regions"]],
            "civilizations": [{"name": c["name"], "regions": c.get("regions", [])}
                              for c in world["civilizations"]],
            "relationships": {}, "events_timeline": [], "named_events": [],
            "scenario_name": world.get("scenario_name"),
            "scholarship": {"seats": [{k: s.get(k) for k in SEAT_FIELDS} for s in seats]},
        },
        "history": [{"turn": h["turn"], "civ_stats": {}, "scholarship": h["scholarship"]}
                    for n, h in enumerate(bundle["history"])
                    if h.get("scholarship") is not None
                    and (n % every == 0 or n == len(bundle["history"]) - 1)],
        "events_timeline": [e for e in events if e.get("event_id") in keep],
        "named_events": [], "chronicle_entries": [], "era_reflections": [],
    }


def main(argv: list[str]) -> int:
    every = 1
    if "--every" in argv:
        k = argv.index("--every")
        every = int(argv[k + 1])
        argv = argv[:k] + argv[k + 2:]
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = build(_load(Path(argv[0])), every)
    Path(argv[1]).write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"{argv[1]}: {len(out['history'])} snapshots, {len(out['events_timeline'])} events, "
          f"{len(out['world_state']['scholarship']['seats'])} seats")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
