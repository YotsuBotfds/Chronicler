#!/usr/bin/env python3
"""Trim a real all-systems bundle into the viewer's systems fixture.

    python scripts/build_viewer_systems_fixture.py BUNDLE OUT [--every N]

The source is a bundle written with every default-off system on, for example

    python -m chronicler.main --seed 42 --turns 120 --agents hybrid --simulate-only \\
        --epidemiology --finance --diplomacy --techniques --maritime \\
        --worldgen procedural --regions 48 --civs 10 --output DIR/chronicle.md

The fixture keeps every N-th history snapshot (default 8) (and the last one) with its
``epidemics``, ``finance``, ``diplomacy``, ``techniques`` and ``maritime``
fields exactly as exported, the snapshot keys the shell reads, the system
events (and the events they cite, so provenance resolves), the region and
civilization lists and the maritime zone ports. Everything else is dropped
to keep the fixture small; nothing is invented or rewritten.
See docs/integration/viewer-systems.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SYSTEMS = ("epidemics", "finance", "diplomacy", "techniques", "maritime")
SNAPSHOT_KEYS = ("turn", "civ_stats", "region_control", "relationships", "trade_routes", "active_wars",
                 "pandemic_regions", *SYSTEMS)
CIV_STAT_KEYS = ("population", "military", "economy", "culture", "stability", "treasury", "asabiya",
                 "tech_era", "trait", "regions", "leader_name", "alive")
REGION_KEYS = ("name", "terrain", "carrying_capacity", "population", "resources", "controller", "x", "y")
CIV_KEYS = ("name", "population", "military", "economy", "culture", "stability", "tech_era", "treasury",
            "domains", "values", "leader", "goal", "regions", "asabiya", "cultural_milestones",
            "action_counts", "leader_name_pool")
METADATA_KEYS = ("seed", "total_turns", "generated_at", "sim_model", "narrative_model", "scenario_name",
                 "interestingness_score", "bundle_version", "narrator_mode")
#: Event types the systems panels list (viewer/src/lib/systems.ts SYSTEM_EVENT_TYPES).
SYSTEM_EVENT_TYPES = {
    "epidemic_arrival", "epidemic", "epidemic_ended", "pathogen_mutation", "quarantine", "quarantine_ended",
    "loan_taken", "state_default", "debasement", "debt_written_off",
    "treaty_signed", "treaty_renewed", "treaty_expired", "treaty_broken", "call_to_arms", "aid_convoy",
    "vassalization", "vassal_promoted", "vassal_loosened", "union_annexation",
    "technique_invented", "technique_adopted", "technique_lost", "tech_advancement", "tech_regression",
    "fleet_commissioned", "fleet_storm", "fleet_lost", "naval_battle", "sea_control", "sea_contested",
    "sea_control_lost", "blockade", "blockade_lifted", "piracy", "piracy_ended", "amphibious_landing",
}


def trim(bundle: dict, every: int) -> dict:
    history = bundle["history"]
    keep = [snap for i, snap in enumerate(history) if i % every == 0 or i == len(history) - 1]
    snapshots = []
    for snap in keep:
        out = {key: snap[key] for key in SNAPSHOT_KEYS if key in snap}
        out["civ_stats"] = {name: {k: stats[k] for k in CIV_STAT_KEYS if k in stats}
                            for name, stats in snap["civ_stats"].items()}
        snapshots.append(out)

    events = bundle["events_timeline"]
    chosen = [e for e in events if e["event_type"] in SYSTEM_EVENT_TYPES]
    wanted = {cause for e in chosen for cause in e.get("causes", [])}
    chosen_ids = {id(e) for e in chosen}
    timeline = [e for e in events if id(e) in chosen_ids or e.get("event_id") in wanted]

    ws = bundle["world_state"]
    maritime = ws.get("maritime") or {}
    world = {
        "name": ws["name"],
        "seed": ws["seed"],
        "turn": ws["turn"],
        "regions": [{k: r[k] for k in REGION_KEYS if k in r} for r in ws["regions"]],
        "civilizations": [{k: c[k] for k in CIV_KEYS if k in c} for c in ws["civilizations"]],
        "relationships": {},
        "events_timeline": [],
        "named_events": [],
        "scenario_name": ws.get("scenario_name"),
        "maritime": {"zones": [{"name": z["name"], "kind": z.get("kind"), "ports": z.get("ports", [])}
                               for z in maritime.get("zones", [])]},
    }
    return {
        "world_state": world,
        "history": snapshots,
        "events_timeline": timeline,
        "named_events": [],
        "chronicle_entries": [],
        "era_reflections": {},
        "metadata": {k: v for k, v in bundle["metadata"].items() if k in METADATA_KEYS},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--every", type=int, default=8, help="keep every N-th snapshot (default 8)")
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    missing = [s for s in SYSTEMS if not any(s in snap for snap in bundle["history"])]
    if missing:
        raise SystemExit(f"source bundle lacks {', '.join(missing)}: run it with every system on")
    fixture = trim(bundle, args.every)
    args.out.write_text(json.dumps(fixture, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(fixture['history'])} snapshots, {len(fixture['events_timeline'])} events, "
          f"{args.out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
