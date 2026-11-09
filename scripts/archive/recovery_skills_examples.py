#!/usr/bin/env python3
"""Find natural success and failure examples of the recovery-skills packages.

    python scripts/archive/recovery_skills_examples.py BUNDLE [BUNDLE ...]

Scans each run's dated livelihoods records (``history[i]["livelihoods"]``; never
the final world state) and prints, per package, the first natural instance of
each preregistered example kind (docs/superpowers/roadmaps/recovery-skills-phase.md,
section 6) with its snapshot turn and the stable ids involved, or "none found".
A bundle carries no CLI flags, so the reproducing command is the one that wrote
it (docs/superpowers/progress/recovery-skills-examples.md lists them).
Constructed examples are the unit tests named in that document, not this script.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _records(hist, name):
    for snap in hist:
        rec = (snap.get("livelihoods") or {}).get(name)
        if isinstance(rec, dict):
            yield snap.get("turn"), rec


def _first(hist, name, key, pred):
    for turn, rec in _records(hist, name):
        for row in rec.get(key) or []:
            if pred(row, rec):
                return turn, row
    return None


def _apprenticeship(hist):
    held = {}   # ids qualified through apprenticeship, from the dated records
    graduate_crew = None
    for turn, rec in _records(hist, "apprenticeship"):
        for q in rec.get("qualifications") or []:
            if q.get("via") == "apprenticeship":
                held.setdefault(q["agent_id"], q.get("earned_turn"))
        for r in rec.get("receipts") or []:
            on = [a for a in r.get("qualified_on_crew") or [] if a in held]
            if graduate_crew is None and on and r.get("operating"):
                graduate_crew = (turn, {"site": r["site"], "region": r["region"], "graduates_on_crew": on,
                                        "condition_after": r.get("condition_after"),
                                        "upkeep_offset": r.get("upkeep_offset")})
    return {
        "success: an apprentice completes and is granted a qualification":
            _first(hist, "apprenticeship", "archive", lambda a, _r: a.get("ended_reason") == "completed"
                   and a.get("granted")),
        "success: a site operates with a graduate on its crew": graduate_crew,
        "failure: a site loses its last qualified teacher":
            _first(hist, "apprenticeship", "events", lambda e, _r: e.get("kind") == "teaching_lost"),
        "failure: an apprenticeship ends without completion":
            _first(hist, "apprenticeship", "archive", lambda a, _r: a.get("ended_reason")
                   not in (None, "completed", "service_qualified")),
    }


def _repair(hist):
    return {
        "success: a project completes":
            _first(hist, "repair_projects", "closed", lambda p, _r: p.get("status") == "completed"),
        "success: a war-damaged asset is rebuilt":
            _first(hist, "repair_projects", "closed", lambda p, _r: p.get("status") == "completed"
                   and p.get("cause") == "war"),
        "success: a turn of paid repair work is credited":
            _first(hist, "repair_projects", "receipts", lambda r, _r: (r.get("credited") or 0) > 0),
        "failure: a project stalls for want of timber":
            _first(hist, "repair_projects", "receipts", lambda r, _r: r.get("status") == "stalled"
                   and "no_timber" in (r.get("reasons") or [])),
        "failure: war damage recorded at a real event":
            _first(hist, "repair_projects", "damages", lambda d, _r: True),
    }


def _veterans(hist):
    def placed(v, _r):
        return (v.get("placements") or 0) > 0
    found = _first(hist, "veteran_reintegration", "veterans", placed) or \
        _first(hist, "veteran_reintegration", "closed", placed)
    return {
        "success: a released soldier is placed in work or training": found,
        "failure: a veteran's eligibility expires while waiting without an opening":
            _first(hist, "veteran_reintegration", "closed", lambda v, _r: v.get("closed_reason") == "expired"
                   and not v.get("placements")),
        "failure: a veteran is remobilised":
            _first(hist, "veteran_reintegration", "closed", lambda v, _r: v.get("closed_reason") == "remobilised"),
    }


def _remittances(hist):
    senders = {}
    ended = None
    for turn, rec in _records(hist, "remittances"):
        for r in rec.get("receipts") or []:
            if (r.get("credited") or 0) > 0:
                senders.setdefault(r["sender"], turn)
        for u in rec.get("unmet") or []:
            if ended is None and u.get("reason") == "no_bond" and u["id"] in senders:
                ended = (turn, {**u, "last_sent_from_snapshot": senders[u["id"]]})
    return {
        "success: a recipient at home is credited a remittance":
            _first(hist, "remittances", "receipts", lambda r, _r: (r.get("credited") or 0) > 0),
        "failure: a sender's link home lapses (no Marriage or Kin bond strong enough)": ended,
        "failure: a diaspora entry closes by death":
            _first(hist, "remittances", "closures", lambda c, _r: c.get("reason") == "death"),
        "failure: a remittance is limited by the recipient's ceiling or the sender's wealth":
            _first(hist, "remittances", "receipts", lambda r, _r: r.get("status") == "limited"),
    }


def _clearing(hist):
    return {
        "success: a funded protection keeps cover from clearing":
            _first(hist, "clearing_protection", "receipts", lambda r, _r: (r.get("cover_not_cleared") or 0) > 0),
        "failure: clearing proceeds where protection is unaffordable":
            _first(hist, "clearing_protection", "unprotected", lambda u, _r: u.get("reason") == "unaffordable"
                   and u.get("clearing_active")),
        "failure: a protection ends":
            _first(hist, "clearing_protection", "decisions", lambda d, _r: d.get("kind") != "adopted"),
    }


FINDERS = {"apprenticeship": _apprenticeship, "repair_projects": _repair,
           "veteran_reintegration": _veterans, "remittances": _remittances,
           "clearing_protection": _clearing}


def find(bundle: dict) -> dict:
    hist = bundle.get("history") or []
    out = {}
    for name, finder in FINDERS.items():
        if any(True for _ in _records(hist, name)):
            out[name] = finder(hist)
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    sys.path.insert(0, str(REPO / "src"))
    from chronicler.bundle_codec import load_bundle
    for path in argv:
        b = load_bundle(Path(path))
        seed = (b.get("metadata") or {}).get("seed")
        print(f"== {path} (seed {seed}, {len(b.get('history') or [])} snapshots; natural)")
        for name, kinds in find(b).items():
            print(f"  {name}")
            for kind, hit in kinds.items():
                if hit is None:
                    print(f"    {kind}: none found")
                else:
                    turn, row = hit
                    print(f"    {kind}: snapshot {turn}: {json.dumps(row, sort_keys=True)[:400]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
