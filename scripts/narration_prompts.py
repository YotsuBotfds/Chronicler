#!/usr/bin/env python3
"""Capture and measure the prompts the curated narrator would receive.

``capture OUT.jsonl -- <chronicler arguments>``
    Run ``chronicler.main`` with the given arguments and write every
    prepared narrator prompt (one JSON line per moment) to ``OUT.jsonl``.
    Use ``--narrator mechanical`` (no LLM, no API): the engine still builds
    each prompt before it renders the moment mechanically. Works for a full
    run (prompts from the live world at the end of the run) and for
    ``--narrate BUNDLE`` (prompts rebuilt from a saved bundle).

``report OUT.jsonl BUNDLE [--top N]``
    Prompt sizes (characters; tokens estimated at 4 characters each), the
    event types listed in a prompt, and how many of the run's turning points
    and highest-impact events a prompt lists. Impact is importance plus
    log2(1 + direct recorded consequences), measured independently of the
    curator's score; turning points are events of importance 8 or more.

Prompts depend only on the run's recorded data: the same run gives the same
file (compare two captures byte for byte). Run with ``PYTHONHASHSEED=0``;
put another source tree first on ``PYTHONPATH`` to capture its prompts.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

TOKEN_CHARS = 4  # rough estimate for English prose and lists
TURNING_POINT = 8
_BOOKKEEPING = ("repeat", "end")


def _record(idx: int, moment, prep: dict) -> dict:
    shown = prep.get("shown_event_ids")
    if shown is None:  # narrators before the bounded event list listed every event
        shown = [e.event_id for e in moment.events]
    return {
        "index": idx,
        "anchor_turn": moment.anchor_turn,
        "turn_range": list(moment.turn_range),
        "role": moment.narrative_role.value,
        "score": round(float(moment.score), 3),
        "event_ids": [e.event_id for e in moment.events],
        "event_types": [e.event_type for e in moment.events],
        "shown_event_ids": list(shown),
        "system": prep["system"],
        "prompt": prep["prompt"],
    }


def capture(out: Path, argv: list[str]) -> int:
    """Run the CLI with a hook that records every prepared prompt."""
    from chronicler import narrative
    from chronicler import main as cli

    records: list[dict] = []
    original = narrative.NarrativeEngine._prepare_narration_prompts

    def recording(self, moments, *args, **kwargs):
        prepared = original(self, moments, *args, **kwargs)
        for idx, (moment, prep) in enumerate(zip(moments, prepared)):
            records.append(_record(idx, moment, prep))
        return prepared

    narrative.NarrativeEngine._prepare_narration_prompts = recording
    saved_argv = sys.argv
    sys.argv = ["chronicler", *argv]
    try:
        cli.main()
    finally:
        sys.argv = saved_argv
        narrative.NarrativeEngine._prepare_narration_prompts = original
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"{len(records)} prompts -> {out} (sha256 {digest[:16]})")
    return 0


def load_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _substantive(e: dict) -> bool:
    t = e.get("event_type", "")
    return (e.get("episode") not in _BOOKKEEPING and not t.endswith("_ended")
            and not t.startswith("capability_"))


def impact_ranking(events: list[dict]) -> list[tuple[float, dict]]:
    """Substantive events by impact: importance + log2(1 + direct consequences),
    one per (type, first actor, region); ties by turn."""
    children: Counter = Counter()
    for e in events:
        for cid in e.get("causes") or []:
            children[cid] += 1
    ranked = []
    for e in events:
        if not _substantive(e):
            continue
        n = children.get(e.get("event_id") or "", 0)
        ranked.append((float(e.get("importance", 5)) + math.log2(1 + n), e))
    ranked.sort(key=lambda r: (-r[0], r[1].get("turn", 0), r[1].get("event_id") or ""))
    out, seen = [], set()
    for score, e in ranked:
        key = (e.get("event_type"), (e.get("actors") or [""])[0], e.get("region"))
        if key in seen:
            continue
        seen.add(key)
        out.append((score, e))
    return out


def summarize(records: list[dict], bundle: dict, top: int = 25) -> dict:
    events = list(bundle.get("events_timeline") or bundle.get("events") or [])
    sizes = [len(r["prompt"]) + len(r["system"]) for r in records]
    shown: set[str] = set()
    listed_types: Counter = Counter()
    by_id = {e.get("event_id"): e for e in events if e.get("event_id")}
    dominant: Counter = Counter()
    for r in records:
        ids = [eid for eid in r.get("shown_event_ids", r["event_ids"]) if eid]
        shown.update(ids)
        rows = [by_id[eid] for eid in ids if eid in by_id]
        listed_types.update(e["event_type"] for e in rows)
        best = max(rows, key=lambda e: e.get("importance", 0), default=None)
        if best is not None:
            dominant[best["event_type"]] += 1
    timeline_types = Counter(e.get("event_type") for e in events)
    turning = [e for e in events if _substantive(e) and e.get("importance", 0) >= TURNING_POINT]
    big_types = sorted({e["event_type"] for e in events if _substantive(e) and e.get("importance", 0) >= 7})
    ranked = impact_ranking(events)[:top]
    top_rows = [{
        "impact": round(score, 2), "turn": e.get("turn"), "type": e.get("event_type"),
        "description": (e.get("description") or "")[:120],
        "listed": (e.get("event_id") or "") in shown,
    } for score, e in ranked]
    named = bundle.get("named_events") or []
    named_hit = sum(1 for n in named if any(n.get("name", "\x00") in r["prompt"] for r in records))
    return {
        "prompts": len(records),
        "chars_total": sum(sizes),
        "chars_mean": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        "chars_max": max(sizes) if sizes else 0,
        "tokens_total_est": sum(sizes) // TOKEN_CHARS,
        "tokens_mean_est": (sum(sizes) // len(sizes) // TOKEN_CHARS) if sizes else 0,
        "tokens_max_est": (max(sizes) if sizes else 0) // TOKEN_CHARS,
        "events_in_timeline": len(events),
        "event_lines": sum(len(r.get("shown_event_ids", r["event_ids"])) for r in records),
        "types_in_timeline": len(timeline_types),
        "types_listed": len(listed_types),
        "turning_points": len(turning),
        "turning_points_listed": sum(1 for e in turning if e.get("event_id") in shown),
        "types_ge7": len(big_types),
        "types_ge7_listed": sum(1 for t in big_types if t in listed_types),
        "types_ge7_missing": [t for t in big_types if t not in listed_types],
        "top_impact_listed": sum(1 for row in top_rows if row["listed"]),
        "top_impact": top_rows,
        "dominant_types": dict(dominant.most_common(6)),
        "named_events": len(named),
        "named_events_in_prompts": named_hit,
    }


def report(path: Path, bundle_path: Path, top: int = 25) -> int:
    from chronicler.bundle_codec import load_bundle
    from chronicler.snapshot_pruning import restore_bundle

    bundle = restore_bundle(load_bundle(bundle_path))
    summary = summarize(load_records(path), bundle, top=top)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "capture" and argv[2] == "--":
        return capture(Path(argv[1]), argv[3:])
    if len(argv) >= 3 and argv[0] == "report":
        top = 25
        if "--top" in argv:
            top = int(argv[argv.index("--top") + 1])
        return report(Path(argv[1]), Path(argv[2]), top=top)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
