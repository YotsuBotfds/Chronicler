#!/usr/bin/env python3
"""How curated moments spread over a run (``curator.spread_moments``).

``report BUNDLE...``
    The moments a run's narration chose (the bundle's ``chronicle_entries``).

``compare BUNDLE...``
    Moments curated again from each bundle as ``--narrate BUNDLE`` does,
    without the spread rule (``SPREAD_GAP`` 0) and with it.

For each: moments per tenth of the run (by anchor turn), the longest
stretch of turns no moment covers and the turns left untold, the largest
gap between anchors and the gaps' coefficient of variation, and what the
moments hold (turning points of importance 8+, their importance-10 events,
and the summed cluster scores). Narration only; reads bundles.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from chronicler.bundle_codec import load_bundle

TENTHS = 10


def _covered(ranges, lo: int, hi: int) -> tuple[int, int]:
    """(longest untold stretch, untold turns) within [lo, hi]."""
    told = [False] * (hi - lo + 1)
    for a, b in ranges:
        for t in range(max(lo, a), min(hi, b) + 1):
            told[t - lo] = True
    longest = run = 0
    for flag in told:
        run = 0 if flag else run + 1
        longest = max(longest, run)
    return longest, told.count(False)


def spread(anchors, ranges, lo: int, hi: int) -> dict:
    span = hi - lo + 1
    tenths = [0] * TENTHS
    for t in anchors:
        tenths[min(TENTHS - 1, (t - lo) * TENTHS // span)] += 1
    ordered = sorted(anchors)
    gaps = [b - a for a, b in zip(ordered, ordered[1:])]
    longest, untold = _covered(ranges, lo, hi)
    return {
        "moments": len(anchors),
        "tenths": tenths,
        "longest_untold": longest,
        "untold_turns": untold,
        "max_gap": max(gaps) if gaps else 0,
        "gap_cv": round(statistics.pstdev(gaps) / statistics.mean(gaps), 3) if len(gaps) > 1 else 0.0,
    }


def _held(events) -> dict:
    turning = [e for e in events if e.importance >= 8]
    return {"turning_points": len(turning),
            "importance_10": sum(1 for e in turning if e.importance >= 10)}


def _bounds(bundle) -> tuple[int, int]:
    turns = [s["turn"] for s in bundle.get("history", [])] or [e["turn"] for e in bundle["events_timeline"]]
    return min(turns), max(turns)


def report(path: Path) -> dict:
    bundle = load_bundle(path)
    lo, hi = _bounds(bundle)
    entries = bundle.get("chronicle_entries") or []
    anchors = [e["turn"] for e in entries]
    ranges = [tuple(e["covers_turns"]) for e in entries]
    out = spread(anchors, ranges, lo, hi)
    out["turns"] = [lo, hi]
    return out


def curate_bundle(path: Path, budget: int = 50):
    """Moments as ``main._run_narrate`` curates them from a bundle."""
    from chronicler.curator import curate
    from chronicler.historiography import AccountIndex
    from chronicler.languages import NameIndex
    from chronicler.models import Event, GreatPerson, NamedEvent, TurnSnapshot
    from chronicler.snapshot_pruning import restore_bundle

    bundle = restore_bundle(json.loads(path.read_text()))
    events = [Event.model_validate(e) for e in bundle.get("events_timeline", [])]
    named = [NamedEvent.model_validate(n) for n in bundle.get("named_events", [])]
    history = [TurnSnapshot.model_validate(s) for s in bundle.get("history", [])]
    seed = bundle.get("metadata", {}).get("seed", 42)
    ws = bundle.get("world_state", {})
    named_chars, gp_by_name = set(), {}
    for civ in ws.get("civilizations", []):
        for gp in civ.get("great_persons", []):
            if gp.get("active") and gp.get("agent_id") is not None:
                named_chars.add(gp.get("name", ""))
                gp_by_name[gp.get("name", "")] = GreatPerson(**gp)
    for gp in ws.get("retired_persons", []):
        if gp.get("death_turn") is not None:
            gp_by_name[gp.get("name", "")] = GreatPerson(**gp)
    accounts = AccountIndex.from_bundle(bundle)
    if accounts is not None:
        names = NameIndex.from_bundle(bundle)
        if names:
            accounts = AccountIndex(bundle["historiography"], names=names)
    moments, _gaps = curate(events, named, history, budget=budget, seed=seed,
                            named_characters=named_chars or None, gp_by_name=gp_by_name or None,
                            contested=accounts.contested_bonus() if accounts else None)
    return bundle, moments


def compare(path: Path, budget: int = 50) -> dict:
    import chronicler.curator as curator
    out = {}
    kept = curator.SPREAD_GAP
    for label, gap in (("without", 0.0), ("with", kept)):
        curator.SPREAD_GAP = gap
        try:
            bundle, moments = curate_bundle(path, budget)
        finally:
            curator.SPREAD_GAP = kept
        lo, hi = _bounds(bundle)
        row = spread([m.anchor_turn for m in moments], [m.turn_range for m in moments], lo, hi)
        row.update(_held([e for m in moments for e in m.events]))
        row["score"] = round(sum(m.score for m in moments), 1)
        out[label] = row
    out["turns"] = [lo, hi]
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("report", "compare"):
        print(__doc__)
        return 2
    fn = report if argv[0] == "report" else compare
    for name in argv[1:]:
        print(json.dumps({"bundle": name, **fn(Path(name))}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
