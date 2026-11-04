#!/usr/bin/env python3
"""Guild, movement and movement-news statistics over a batch of runs.

``guilds_probe.py BATCH_DIR [BATCH_DIR ...] [--json OUT]``

Each BATCH_DIR holds ``seed_*`` run directories (``state.json`` and
``chronicle_bundle.json``), as a gate or ``--seed-range`` run writes them.
Per batch, means per world of: guilds founded and dissolved, privileges,
levies, threats, guild movements and charters, realms with burghers at the
end and burgher-dominated realms; movements founded by creed, significant
movements (a demand and 10+ members at the peak), regions reached per
movement, members at the peak, demands, reforms, risings; foundings boosted
by news; news packets created and passed on. Compare a batch with news
(``--guilds``) against one without (tuning ``guilds.movement_news: 0``) to
read how news changes movement spread. See docs/integration/guilds.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

CREEDS = ("commons", "liberty", "sect", "guild")


def _runs(batch: Path) -> list[Path]:
    return sorted(p for p in batch.glob("seed_*") if (p / "state.json").exists())


def run_stats(run: Path) -> dict:
    from chronicler.bundle_codec import load_bundle
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    out: dict[str, float] = {}
    guilds = state.get("guilds") or {}
    for key, value in (guilds.get("counters") or {}).items():
        out[f"guilds.{key}"] = float(value)
    civs = [c for c in state.get("civilizations", []) if c.get("regions")]
    burgher = [c for c in civs if "burgher" in (c.get("factions") or {}).get("influence", {})]
    out["realms_with_burghers"] = float(len(burgher))
    out["burgher_dominant"] = float(sum(
        1 for c in burgher
        if max(c["factions"]["influence"], key=c["factions"]["influence"].get) == "burgher"))
    out["burgher_influence_mean"] = (mean(c["factions"]["influence"]["burgher"] for c in burgher)
                                     if burgher else 0.0)
    movements = (state.get("agent_movements") or {}).get("movements", [])
    for k, creed in enumerate(CREEDS):
        out[f"founded.{creed}"] = float(sum(1 for m in movements if m.get("creed") == k))
    need = [m for m in movements if m.get("creed", 0) < 3]
    out["founded"] = float(len(need))
    out["significant"] = float(sum(1 for m in need if m.get("demands", 0) >= 1
                                   and m.get("peak_members", 0) >= 10))
    out["regions_reached_mean"] = mean(len(m.get("regions_reached", [])) for m in need) if need else 0.0
    out["peak_members_mean"] = mean(m.get("peak_members", 0) for m in need) if need else 0.0
    counters = (state.get("agent_movements") or {}).get("counters", {})
    for key in ("demands", "reforms", "concessions", "refusals", "crackdowns", "risings", "secessions"):
        out[f"movements.{key}"] = float(counters.get(key, 0))
    bundle = load_bundle(run / "chronicle_bundle.json")
    ks = bundle.get("metadata", {}).get("knowledge_stats") or []
    out["news_created"] = float(sum(s.get("created_news", 0) for s in ks))
    out["news_transmitted"] = float(sum(s.get("transmitted_news", 0) for s in ks))
    out["spread_events"] = float(sum(1 for e in bundle.get("events_timeline", [])
                                     if e.get("event_type") == "movement_spread"))
    return out


def batch_stats(batch: Path) -> dict:
    rows = [run_stats(run) for run in _runs(batch)]
    keys = sorted({k for row in rows for k in row})
    return {"batch": str(batch), "worlds": len(rows),
            "mean": {k: round(mean(row.get(k, 0.0) for row in rows), 3) for k in keys}}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    out = None
    if "--json" in argv:
        i = argv.index("--json")
        out = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    results = [batch_stats(Path(b)) for b in argv]
    keys = sorted({k for r in results for k in r["mean"]})
    print("| per world | " + " | ".join(Path(r["batch"]).parent.parent.name or r["batch"]
                                        for r in results) + " |")
    print("| --- |" + " ---: |" * len(results))
    print("| worlds | " + " | ".join(str(r["worlds"]) for r in results) + " |")
    for k in keys:
        print(f"| {k} | " + " | ".join(f"{r['mean'].get(k, 0.0):g}" for r in results) + " |")
    if out is not None:
        out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
