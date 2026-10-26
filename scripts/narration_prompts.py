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
    event types that reach a prompt, and which of the run's highest-impact
    events (importance plus recorded consequences) reach one. Impact is
    measured independently of the curator's own score.

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


def _record(idx: int, moment, prep: dict) -> dict:
    return {
        "index": idx,
        "anchor_turn": moment.anchor_turn,
        "turn_range": list(moment.turn_range),
        "role": moment.narrative_role.value,
        "score": round(float(moment.score), 3),
        "event_ids": [e.event_id for e in moment.events],
        "event_types": [e.event_type for e in moment.events],
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


def impact_ranking(events: list[dict]) -> list[tuple[float, dict]]:
    """Events by impact: importance plus 1.5 x log2(1 + recorded consequences).

    Consequences are the events whose recorded ``causes`` lead back to the
    event (transitively, capped at 64). Episode repeats and endings are left out.
    """
    index = {e.get("event_id"): i for i, e in enumerate(events) if e.get("event_id")}
    children: list[list[int]] = [[] for _ in events]
    for j, e in enumerate(events):
        for cid in e.get("causes") or []:
            i = index.get(cid)
            if i is not None and i != j:
                children[i].append(j)
    ranked = []
    for i, e in enumerate(events):
        if e.get("episode") in ("repeat", "end"):
            continue
        seen, frontier, count = {i}, [i], 0
        while frontier and count < 64:
            nxt = []
            for node in frontier:
                for ch in children[node]:
                    if ch not in seen:
                        seen.add(ch)
                        nxt.append(ch)
                        count += 1
            frontier = nxt
        ranked.append((float(e.get("importance", 5)) + 1.5 * math.log2(1 + min(count, 64)), e))
    ranked.sort(key=lambda r: (-r[0], r[1].get("turn", 0), r[1].get("event_id") or ""))
    return ranked


def summarize(records: list[dict], bundle: dict, top: int = 25) -> dict:
    events = list(bundle.get("events_timeline") or bundle.get("events") or [])
    sizes = [len(r["prompt"]) + len(r["system"]) for r in records]
    in_prompt: set[str] = set()
    prompt_types: Counter = Counter()
    for r in records:
        in_prompt.update(eid for eid in r["event_ids"] if eid)
        prompt_types.update(r["event_types"])
    timeline_types = Counter(e.get("event_type") for e in events)
    ranked = impact_ranking(events)[:top]
    top_rows = []
    for score, e in ranked:
        eid = e.get("event_id") or ""
        top_rows.append({
            "impact": round(score, 2), "turn": e.get("turn"), "type": e.get("event_type"),
            "description": (e.get("description") or "")[:120], "in_prompt": eid in in_prompt,
            "quoted": any(eid and eid in r["prompt"] for r in records) or
                      any((e.get("description") or "\x00") in r["prompt"] for r in records),
        })
    named = bundle.get("named_events") or []
    named_turns = {(n.get("turn"), n.get("name")) for n in named}
    named_hit = sum(1 for n in named if any(n.get("name", "\x00") in r["prompt"] for r in records))
    return {
        "prompts": len(records),
        "chars_total": sum(sizes),
        "chars_mean": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        "chars_max": max(sizes) if sizes else 0,
        "tokens_total_est": sum(sizes) // TOKEN_CHARS,
        "tokens_max_est": (max(sizes) if sizes else 0) // TOKEN_CHARS,
        "events_in_timeline": len(events),
        "event_lines_in_prompts": sum(len(r["event_ids"]) for r in records),
        "types_in_timeline": len(timeline_types),
        "types_in_prompts": len(prompt_types),
        "types_never_in_prompts": sorted(t for t in timeline_types if t not in prompt_types),
        "top_impact_in_prompt": sum(1 for row in top_rows if row["in_prompt"]),
        "top_impact": top_rows,
        "named_events": len(named_turns),
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
