#!/usr/bin/env python3
"""Prove that causal provenance changes no simulation outcome.

Two subcommands:

``run-legacy -- <chronicler.main args>``
    Run ``chronicler.main`` with ``provenance.LEGACY_TIMELINE`` set: ids and
    causes are recorded, but chronic repeats stay on the timeline (as
    ``episode="repeat"``), importance is not capped and no ``*_ended``
    events are added, so the timeline lines up event for event with a
    provenance-free run.

``compare BASE_DIR NEW_DIR {keep,prod}``
    Compare a run of the base commit (BASE_DIR: ``state.json``,
    ``chronicle_bundle.json``, ``agent_events.arrow``) with a run of this
    branch, after setting aside the provenance fields (event ids/causes/
    region/civs/episode/duration, condition ids, ``WorldState.provenance``)
    and, in prod mode, the added ``*_ended`` events and supply-shock
    ``importance`` (episode onsets are capped at 6).

    legacy NEW ran via ``run-legacy``: state, every history snapshot, the
           world state in the bundle, named events, agent events and the
           whole timeline must be identical.
    prod   NEW ran the production path: everything except the timeline must be
           identical, and the timeline must be the base timeline with only
           chronic repeats removed (an ordered subsequence check).

Exit status 0 when identical. See docs/integration/causal-provenance.md.
"""
from __future__ import annotations

import json
import os
import sys

EVENT_FIELDS = ("event_id", "causes", "region", "civs", "episode", "duration")
COND_FIELDS = ("condition_id", "cause_id", "onset_turn")


def _chronic_types() -> set[str]:
    from chronicler.provenance import CHRONIC
    return set(CHRONIC)


def strip_event(e: dict, importance: bool = True) -> dict:
    e = {k: v for k, v in e.items() if k not in EVENT_FIELDS}
    if not importance and e["event_type"] == "supply_shock":
        e.pop("importance", None)
    return e


def strip_world(w: dict) -> dict:
    w = dict(w)
    w.pop("provenance", None)
    w["active_conditions"] = [{k: v for k, v in c.items() if k not in COND_FIELDS}
                              for c in w.get("active_conditions", [])]
    w.pop("events_timeline", None)
    return w


def first_diff(a, b, path: str = "$") -> str | None:
    if type(a) is not type(b):
        return f"{path}: type {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}: missing on one side"
            d = first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: len {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else f"{path}: {a!r} != {b!r}"


def check_prod_timeline(base_evs: list, new_evs: list) -> int | str:
    chronic = _chronic_types()
    new_kept = [strip_event(e, False) for e in new_evs if e.get("episode") != "end"]
    i = dropped = 0
    for b in base_evs:
        sb = strip_event(b, False)
        if i < len(new_kept) and new_kept[i] == sb:
            i += 1
            continue
        if b["event_type"] not in chronic:
            return f"non-chronic base event missing in new: {b}"
        dropped += 1
    if i != len(new_kept):
        return f"new has extra events from index {i}: {new_kept[i]}"
    return dropped


def _read(path: str) -> bytes:
    return open(path, "rb").read() if os.path.exists(path) else b""


def compare(base: str, new: str, mode: str) -> bool:
    ok = True
    sb = json.load(open(os.path.join(base, "state.json")))
    sn = json.load(open(os.path.join(new, "state.json")))
    d = first_diff(strip_world(sb), strip_world(sn))
    print("  state.json (excl. timeline):", d or "IDENTICAL")
    ok &= d is None
    bb = json.load(open(os.path.join(base, "chronicle_bundle.json")))
    bn = json.load(open(os.path.join(new, "chronicle_bundle.json")))
    d = first_diff(bb["history"], bn["history"], "history")
    print(f"  bundle history ({len(bb['history'])} snapshots):", d or "IDENTICAL")
    ok &= d is None
    d = first_diff(strip_world(bb["world_state"]), strip_world(bn["world_state"]), "world_state")
    print("  bundle world_state (excl. timeline):", d or "IDENTICAL")
    ok &= d is None
    d = first_diff(bb["named_events"], bn["named_events"], "named_events")
    print("  named events:", d or "IDENTICAL")
    ok &= d is None
    ab = _read(os.path.join(base, "agent_events.arrow"))
    an = _read(os.path.join(new, "agent_events.arrow"))
    print(f"  agent_events.arrow ({len(ab)} bytes):", "IDENTICAL" if ab == an else "DIFFERENT")
    ok &= ab == an
    tb, tn = sb["events_timeline"], sn["events_timeline"]
    ends = sum(1 for e in tn if e.get("episode") == "end")
    if mode == "legacy":
        d = first_diff([strip_event(e) for e in tb], [strip_event(e) for e in tn], "timeline")
        if ends:
            d = d or f"{ends} end events in a legacy-timeline run"
        linked = sum(1 for e in tn if e.get("causes"))
        print(f"  timeline ({len(tb)} events, {linked} with recorded causes):", d or "IDENTICAL")
        ok &= d is None
    else:
        res = check_prod_timeline(tb, tn)
        if isinstance(res, int):
            print(f"  timeline: base {len(tb)} -> new {len(tn)} events ({res} chronic repeats "
                  f"folded, {ends} end events added): ordered subsequence OK")
        else:
            print("  timeline:", res)
            ok = False
    print("  RESULT:", "PASS" if ok else "FAIL")
    return ok


def main(argv: list[str]) -> int:
    if argv[:1] == ["run-legacy"]:
        import chronicler.provenance as provenance
        provenance.LEGACY_TIMELINE = True
        from chronicler.main import main as chronicler_main
        rest = argv[1:]
        if rest[:1] == ["--"]:
            rest = rest[1:]
        sys.argv = ["chronicler"] + rest
        chronicler_main()
        return 0
    if argv[:1] == ["compare"] and len(argv) == 4 and argv[3] in ("legacy", "prod"):
        return 0 if compare(argv[1], argv[2], argv[3]) else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
