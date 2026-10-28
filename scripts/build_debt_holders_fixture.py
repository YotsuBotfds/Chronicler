#!/usr/bin/env python3
"""Trim a real ``--domestic-credit`` bundle into the viewer's debt-holders fixture.

    python scripts/build_debt_holders_fixture.py BUNDLE OUT [--every N]

The source is a bundle written with ``--domestic-credit`` (finance is on by
default; the switch needs an agent mode), for example

    python -m chronicler.main --seed 42 --turns 120 --agents hybrid --simulate-only \\
        --domestic-credit --worldgen procedural --regions 32 --civs 10 --output DIR/chronicle.md

The fixture keeps every N-th history snapshot (default 6), the last one, and
every snapshot in which a civ's default count or the debt written off on it
rose, with the one before it, so each default and write-off stays visible.
Each kept snapshot holds its ``finance`` field exactly as exported and the
civ rows' population, treasury, regions and liveness; the finance events (and the events they cite), the
region and civilization lists and the metadata are kept. Everything else is
dropped to keep the fixture small (``relationships`` is left empty); nothing
is invented or rewritten. See docs/integration/domestic-credit.md, section 14.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from chronicler.bundle_codec import load_bundle

CIV_STAT_KEYS = ("population", "treasury", "regions", "alive")
REGION_KEYS = ("name", "terrain", "carrying_capacity", "population", "resources", "controller", "x", "y")
CIV_KEYS = ("name", "population", "military", "economy", "culture", "stability", "tech_era", "treasury",
            "domains", "values", "leader", "goal", "regions", "asabiya")
METADATA_KEYS = ("seed", "total_turns", "generated_at", "sim_model", "narrative_model", "scenario_name",
                 "interestingness_score", "bundle_version", "narrator_mode")
FINANCE_EVENT_TYPES = {"loan_taken", "state_default", "debasement", "debt_written_off"}


def _losses(snapshot: dict) -> dict[str, tuple[int, int]]:
    """Per civ: (defaults, debt written off on it) in a snapshot."""
    finance = snapshot.get("finance") or {}
    holders = (finance.get("domestic_credit") or {}).get("holders") or {}
    return {civ: (row["defaults"], (holders.get(civ) or {}).get("written_off", 0))
            for civ, row in finance.get("civs", {}).items()}


def _kept_positions(history: list[dict], every: int) -> set[int]:
    keep = {i for i in range(len(history)) if i % every == 0}
    keep.add(len(history) - 1)
    for i in range(1, len(history)):
        before, now = _losses(history[i - 1]), _losses(history[i])
        if any(now[civ] != before.get(civ, now[civ]) for civ in now):
            keep.update((i - 1, i))
    return keep


def trim(bundle: dict, every: int) -> dict:
    history = bundle["history"]
    snapshots = []
    for i in sorted(_kept_positions(history, every)):
        snap = history[i]
        snapshots.append({
            "turn": snap["turn"],
            "civ_stats": {name: {k: stats[k] for k in CIV_STAT_KEYS if k in stats}
                          for name, stats in snap["civ_stats"].items()},
            "region_control": snap["region_control"],
            "relationships": {},
            **({"finance": snap["finance"]} if "finance" in snap else {}),
        })
    events = bundle["events_timeline"]
    chosen = [e for e in events if e["event_type"] in FINANCE_EVENT_TYPES]
    wanted = {cause for e in chosen for cause in e.get("causes", [])}
    chosen_ids = {id(e) for e in chosen}
    timeline = [e for e in events if id(e) in chosen_ids or e.get("event_id") in wanted]
    ws = bundle["world_state"]
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
    parser.add_argument("--every", type=int, default=6, help="keep every N-th snapshot (default 6)")
    args = parser.parse_args()
    bundle = load_bundle(args.bundle)
    if not any((snap.get("finance") or {}).get("domestic_credit", {}).get("holders")
               for snap in bundle["history"]):
        raise SystemExit("source bundle has no finance.domestic_credit.holders: run it with --domestic-credit")
    fixture = trim(bundle, args.every)
    args.out.write_text(json.dumps(fixture, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(fixture['history'])} snapshots, {len(fixture['events_timeline'])} events, "
          f"{args.out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
