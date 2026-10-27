#!/usr/bin/env python3
"""Build the viewer's Movements fixture from a run's bundle.

``build_movements_fixture.py BUNDLE OUT [--every K] [--faiths]`` writes ``OUT``
(normally ``viewer/src/__fixtures__/movements_bundle.json``): every K-th
snapshot's ``turn`` and ``agent_movements`` (and the last; ``civ_stats``
emptied), the movement and reform events plus the events they cite (not the food
reports), and a world state with the regions' and civilizations' names, the
faith registry, the permanent faith table (``faiths``, when the run has one:
docs/integration/permanent-faiths.md) and the final ``agent_movements``. With
``--faiths`` (``viewer/src/__fixtures__/faiths_bundle.json``) it also keeps the
movements' faith fields and the faiths' own events (schisms, reformations,
temples destroyed). Read with ``bundle_codec.load_bundle`` when available
(bundle version 6 writes the history as changes between snapshots).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MOVEMENT_EVENTS = {
    "movement_founded", "movement_spread", "movement_demand", "movement_reform", "movement_refused",
    "movement_crackdown", "movement_martyr", "movement_rising", "movement_concession", "movement_crushed",
    "movement_dispersed", "movement_end", "movement_leader", "reform_repealed", "reform_lapsed",
}
FAITH_EVENTS = {"Schism", "Reformation", "temple_destroyed"}
#: Movement record fields kept (the faith fields when the record has them).
MOVEMENT_FIELDS = ("name", "creed", "founded_turn", "home_region", "target", "leader", "peak_members",
                   "demands", "martyrs", "ended_turn", "end", "reform", "history")
FAITH_FIELDS = ("faith", "schism_turn", "schism_from", "schism_to")


def _load(path: Path) -> dict:
    try:
        from chronicler.bundle_codec import load_bundle
    except ImportError:
        return json.loads(path.read_text())
    return load_bundle(path)


def build(bundle: dict, every: int = 1, keep_faiths: bool = False) -> dict:
    """``keep_faiths``: also the movements' faith fields and the faiths' own
    events (the faiths fixture)."""
    events = bundle["events_timeline"]
    by_id = {e.get("event_id"): e for e in events if e.get("event_id")}
    state = bundle["world_state"]["agent_movements"]
    wanted = {eid for m in state["movements"] for _t, _k, eid in m["history"] if eid}
    wanted |= {e["event_id"] for e in events if e["event_type"] in MOVEMENT_EVENTS and e.get("event_id")}
    for r in state.get("reforms", []):
        wanted |= {r.get("event_id"), r.get("repeal_event_id")}
    faith_events = [e for e in events if e["event_type"] in FAITH_EVENTS]
    # Cited events other than the food reports (with them the viewer would
    # read the fixture as a food record too).
    cited = {c for eid in wanted if eid in by_id for c in by_id[eid].get("causes", [])
             if c in by_id and by_id[c]["event_type"] not in ("famine", "dearth", "famine_ended",
                                                              "dearth_ended")}
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
            "belief_registry": [{"faith_id": b["faith_id"], "name": b["name"],
                                 **({"civ_origin": b["civ_origin"]} if "faiths" in world else {})}
                                for b in world.get("belief_registry", [])],
            **({"faiths": world["faiths"]} if "faiths" in world else {}),
            "agent_movements": {
                "movements": [{k: m[k] for k in MOVEMENT_FIELDS + (FAITH_FIELDS if keep_faiths else ())
                               if k in m}
                              for m in state["movements"]],
                "reforms": state.get("reforms", []),
            },
        },
        "history": [{"turn": h["turn"], "civ_stats": {}, "agent_movements": h["agent_movements"]}
                    for n, h in enumerate(bundle["history"])
                    if h.get("agent_movements") is not None
                    and (n % every == 0 or n == len(bundle["history"]) - 1)],
        "events_timeline": [e for e in events if e.get("event_id") in keep
                            or (keep_faiths and e in faith_events)],
        "named_events": [], "chronicle_entries": [], "era_reflections": [],
    }


def main(argv: list[str]) -> int:
    every = 1
    keep_faiths = "--faiths" in argv
    argv = [a for a in argv if a != "--faiths"]
    if "--every" in argv:
        k = argv.index("--every")
        every = int(argv[k + 1])
        argv = argv[:k] + argv[k + 2:]
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = build(_load(Path(argv[0])), every, keep_faiths)
    Path(argv[1]).write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"{argv[1]}: {len(out['history'])} snapshots, {len(out['events_timeline'])} events, "
          f"{len(out['world_state']['agent_movements']['movements'])} movements, "
          f"{len(out['world_state']['agent_movements']['reforms'])} reforms")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
