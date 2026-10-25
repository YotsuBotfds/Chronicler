#!/usr/bin/env python3
"""Trim a real all-systems bundle into the viewer's systems fixture.

    python scripts/build_viewer_systems_fixture.py BUNDLE OUT [--every N]

The source is a bundle written with every system on, in an agent mode (the
``food`` and ``migration`` fields need one), for example

    python -m chronicler.main --seed 42 --turns 120 --agents hybrid --simulate-only \\
        --maritime --nomads --gp-agendas \\
        --worldgen procedural --regions 48 --civs 10 --output DIR/chronicle.md

The fixture keeps every N-th history snapshot (default 10), the last one and,
for a version-5 bundle, each snapshot holding a dead civ's final row, with
its system fields (``SYSTEMS`` and ``EXTRA_SYSTEMS``) exactly as exported,
the civ rows' governance stats the viewer reads (``GOVERNANCE_KEYS``), the
snapshot keys the shell reads, the system events (and the events they cite,
so provenance resolves), the region and civilization lists, the maritime
zone ports and the procedural sea zones' positions. Everything else is
dropped to keep the fixture small; nothing is invented or rewritten.
See docs/integration/viewer-systems.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SYSTEMS = ("epidemics", "finance", "diplomacy", "techniques", "maritime")
#: Fields of the systems added to the viewer later (campaign, contact ledger,
#: nomads, agendas) and the viewer-only food and migration fields.
EXTRA_SYSTEMS = ("campaign", "contact", "nomads", "gp_agendas", "food", "migration")
SNAPSHOT_KEYS = ("turn", "civ_stats", "region_control", "relationships", "trade_routes", "active_wars",
                 "pandemic_regions", *SYSTEMS, *EXTRA_SYSTEMS)
CIV_STAT_KEYS = ("population", "military", "economy", "culture", "stability", "treasury", "asabiya",
                 "tech_era", "trait", "regions", "leader_name", "alive")
#: The ``civ_stats[civ].governance`` keys the governance panel reads.
GOVERNANCE_KEYS = ("institutions", "ruler_legitimacy", "psi", "psi_crisis", "institutional_regime",
                   "cycle_phase", "government_form", "elite_qualifiers", "office_holders",
                   "frustrated_aspirants", "revolts_total", "civil_wars_total")
REGION_KEYS = ("name", "terrain", "carrying_capacity", "population", "resources", "controller", "x", "y")
CIV_KEYS = ("name", "population", "military", "economy", "culture", "stability", "tech_era", "treasury",
            "domains", "values", "leader", "goal", "regions", "asabiya", "cultural_milestones",
            "action_counts", "leader_name_pool")
METADATA_KEYS = ("seed", "total_turns", "generated_at", "sim_model", "narrative_model", "scenario_name",
                 "interestingness_score", "bundle_version", "narrator_mode")
#: Event types the first five systems' panels list.
FIRST_SYSTEM_EVENT_TYPES = {
    "epidemic_arrival", "epidemic", "epidemic_ended", "pathogen_mutation", "quarantine", "quarantine_ended",
    "loan_taken", "state_default", "debasement", "debt_written_off",
    "treaty_signed", "treaty_renewed", "treaty_expired", "treaty_broken", "call_to_arms", "aid_convoy",
    "vassalization", "vassal_promoted", "vassal_loosened", "union_annexation",
    "technique_invented", "technique_adopted", "technique_lost", "tech_advancement", "tech_regression",
    "fleet_commissioned", "fleet_storm", "fleet_lost", "naval_battle", "sea_control", "sea_contested",
    "sea_control_lost", "blockade", "blockade_lifted", "piracy", "piracy_ended", "amphibious_landing",
}
FAMINE_TYPES = {"famine", "famine_ended"}
FAMINE_REGIONS = 8
EVENTS_PER_TYPE = 12
#: Event types the systems panels list (viewer/src/lib/systems.ts SYSTEM_EVENT_TYPES).
SYSTEM_EVENT_TYPES = FIRST_SYSTEM_EVENT_TYPES | {
    "famine", "famine_ended", "mutual_aid", "locust_swarm", "fishery_collapse", "fishery_recovery",
    "war_declared", "peace_treaty", "war_ended", "army_raised", "army_destroyed", "siege_begun", "occupation",
    "occupation_revolt", "liberation", "civ_conquered", "annexation", "general_fallen", "scorched_earth",
    "congress_peace", "congress_ceasefire", "congress_collapse",
    "raid", "raid_repulsed", "tribute_agreed", "tribute_ended", "horde_formed", "horde_rides", "horde_fragmented",
    "horde_dissolved", "dzud", "pasture_drought", "pasture_abandoned", "sedentarization",
    "agenda_declared", "agenda_fulfilled", "agenda_failed", "war_agitation", "campaign_victory", "gp_coup",
    "gp_coup_failed", "trade_mission", "trading_house_founded", "crown_loan", "preaching", "shrine_commissioned",
    "shrine_consecrated", "gp_alliance_formed", "gp_rivalry_formed", "succession_backed",
    "government_transition", "psi_crisis", "psi_recovery", "institution_enacted", "institution_repealed",
    "institution_enforcement_lapse", "institutional_regime_shift", "elite_overproduction", "legitimacy_crisis",
    "revolt", "reform_pressure", "ambition_declared", "ambition_fulfilled", "ambition_failed", "secession_suppressed",
    "embargo", "first_contact",
}


def _final_row_positions(history: list[dict]) -> set[int]:
    """Snapshots that hold a civ's last row before it leaves the history.

    Version-5 bundles leave dead civs out of later snapshots; keeping the
    snapshot with each one's final row keeps its death in the fixture.
    """
    return {i for i in range(len(history) - 1)
            if set(history[i]["civ_stats"]) - set(history[i + 1]["civ_stats"])}


def trim(bundle: dict, every: int) -> dict:
    history = bundle["history"]
    final_rows = _final_row_positions(history)
    keep = [snap for i, snap in enumerate(history)
            if i % every == 0 or i == len(history) - 1 or i in final_rows]
    snapshots = []
    for snap in keep:
        out = {key: snap[key] for key in SNAPSHOT_KEYS if key in snap}
        out["civ_stats"] = {name: {k: stats[k] for k in CIV_STAT_KEYS if k in stats}
                            for name, stats in snap["civ_stats"].items()}
        for name, stats in snap["civ_stats"].items():
            if isinstance(stats.get("governance"), dict):
                out["civ_stats"][name]["governance"] = {
                    k: stats["governance"][k] for k in GOVERNANCE_KEYS if k in stats["governance"]}
        snapshots.append(out)

    events = bundle["events_timeline"]
    # System events are many, so the fixture keeps famines (onsets, reports
    # and ends) in the first FAMINE_REGIONS regions only, so their spans stay
    # whole, and the first EVENTS_PER_TYPE events of every other type.
    famine_regions = {r["name"] for r in bundle["world_state"]["regions"][:FAMINE_REGIONS]}
    per_type: dict[str, int] = {}
    chosen = []
    for e in events:
        kind = e["event_type"]
        if kind not in SYSTEM_EVENT_TYPES:
            continue
        if kind in FAMINE_TYPES:
            if e.get("region") in famine_regions:
                chosen.append(e)
        elif per_type.get(kind, 0) < EVENTS_PER_TYPE:
            per_type[kind] = per_type.get(kind, 0) + 1
            chosen.append(e)
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
    geography = ws.get("geography") or {}
    if geography.get("sea_zones"):
        world["geography"] = {
            "generator": geography.get("generator"),
            "sea_zones": [{k: z[k] for k in ("name", "kind", "x", "y") if k in z} for z in geography["sea_zones"]],
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
    parser.add_argument("--every", type=int, default=10, help="keep every N-th snapshot (default 10)")
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
