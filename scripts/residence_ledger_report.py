#!/usr/bin/env python3
"""Summarize the residence ledger (``--residence-ledger``) records of finished runs.

    PYTHONPATH=src python scripts/residence_ledger_report.py BUNDLE [BUNDLE ...] [--json OUT.json]

Reads only each bundle's history snapshots (``snapshot.livelihoods.residence_ledger``,
classified by ``chronicler.residence_ledger.record_status``) and reports, per run:

* the mean share of the living under each candidate definition of "displaced"
  in audit A6 section 10, over the last three quarters of the observed turns
  (as the audit's probe measured them): the native displacement counter
  (``recent_movers_native``), away from the birth region, an open spell (both
  causes), flight only, anchored to a famine or war event at home, anchored to
  a war event;
* the spells opened (by cause and anchor) and closed (by closure), with the
  median length of the closed spells per closure, from the bounded per-turn
  spell events (turns with dropped events are counted and named);
* the readings of every snapshot (recorded, recorded_zero, unobserved,
  malformed, absent).

Development worlds only; nothing here is a screen.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from chronicler.residence_ledger import record_status  # noqa: E402
from chronicler.residence_ledger_state import ANCHORS, CAUSES, CLOSURES  # noqa: E402

#: Audit section 10 definitions -> the frame total counted over the living.
DEFINITIONS: dict[str, str] = {
    "native_cooldown": "recent_movers_native",
    "away_from_birth_region": "away_from_birth_region",
    "open_spell": "displaced",
    "open_spell_flight": "displaced_flight",
    "open_spell_famine_or_war_anchor": "anchor_war_or_famine",
    "open_spell_war_anchor": "anchor_any_war",
}


def summarize(history: list[dict]) -> dict:
    readings: dict[str, int] = {}
    frames = []
    events = []
    dropped_turns = []
    for snap in history:
        status, frame = record_status(snap)
        readings[status] = readings.get(status, 0) + 1
        if frame is None:
            continue
        frames.append(frame)
        record = snap["livelihoods"]["residence_ledger"]
        events.extend(record.get("events") or [])
        if record.get("events_dropped"):
            dropped_turns.append(frame["turn"])
    later = frames[len(frames) // 4:]
    shares = {}
    for name, key in DEFINITIONS.items():
        values = [f["totals"][key] / f["totals"]["alive"] for f in later if f["totals"]["alive"]]
        shares[name] = round(statistics.mean(values), 4) if values else None
    opened = [e for e in events if e["kind"] == "opened"]
    closed = {reason: [e for e in events if e["kind"] == reason] for reason in CLOSURES}
    medians = {reason: (statistics.median_low([e["length"] for e in rows]) if rows else None)
               for reason, rows in closed.items()}
    return {
        "turns": len(frames), "readings": readings, "shares_last_three_quarters": shares,
        "opened": len(opened),
        "opened_by_cause": {c: sum(1 for e in opened if e["cause"] == c) for c in CAUSES},
        "opened_by_anchor": {a: sum(1 for e in opened if e["anchor"] == a) for a in ANCHORS},
        "closed": {reason: len(rows) for reason, rows in closed.items()},
        "median_length": medians,
        "war_anchored_open_mean": shares["open_spell_war_anchor"],
        "turns_with_dropped_events": dropped_turns,
        "alive_range": [min(f["totals"]["alive"] for f in frames), max(f["totals"]["alive"] for f in frames)]
        if frames else None,
        "last_counters": history[-1].get("livelihoods", {}).get("residence_ledger", {}).get("counters")
        if history else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundles", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    from chronicler.bundle_codec import load_bundle
    out = {}
    for path in args.bundles:
        bundle = load_bundle(path)
        out[str(path)] = summarize(bundle["history"])
        print(path, json.dumps(out[str(path)]["shares_last_three_quarters"]), json.dumps(out[str(path)]["closed"]))
    if args.json is not None:
        args.json.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
