#!/usr/bin/env python3
"""Narration coverage table: every event type the simulation can emit, and
how the curated narrator receives it, before and after a narration change.

``table SRC_DIR BEFORE_RUNS AFTER_RUNS``
    ``SRC_DIR`` is ``src/chronicler`` (scanned for ``Event(...)`` and helper
    emitters; types emitted under a computed name are listed explicitly
    below). ``BEFORE_RUNS`` and ``AFTER_RUNS`` hold run directories
    (``r1``, ``r2`` ...), each with ``chronicle_bundle.json`` and the
    ``prompts.jsonl`` written by ``scripts/narration_prompts.py capture``.
    The runs' simulations must be identical (only the narrator differs).
    Prints a Markdown table and the coverage counts.

Columns: where the type is emitted; occurrences in the runs; the prompt line
before and after (ok, empty, misleading, label, reworded); the curator class
after (bookkeeping, routine, turning point at importance 8+, scored); events
listed in a prompt before and after; whether in-world names can resolve it
(a region, a civ actor or a civ field); and how the historiography layer
treats it (its category; ``routine`` and ``bookkeeping`` are never
chronicled; ``unclassified`` is chronicled at importance 7+).
"""
from __future__ import annotations

import ast
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

#: Types emitted under a computed name (conditional or formatted emitters).
COMPUTED = {
    "reform_lapsed": "agent_movements.py", "reform_repealed": "agent_movements.py",
    "movement_crushed": "agent_movements.py", "movement_crackdown": "agent_movements.py",
    "movement_concession": "agent_movements.py", "movement_reform": "agent_movements.py",
    "liberation": "war/occupation.py", "occupation_revolt": "war/occupation.py",
    "drought": "simulation.py (hazard)", "plague": "simulation.py (hazard)",
    "earthquake": "simulation.py (hazard)", "religious_movement": "simulation.py (hazard)",
    "discovery": "simulation.py (hazard)", "rebellion": "simulation.py (hazard)",
    "cultural_renaissance": "simulation.py (hazard)", "border_incident": "simulation.py (hazard)",
    "proxy_detected": "politics.rs (native)", "federation_formed": "politics.rs (native)",
    "federation_collapsed": "politics.rs (native)", "capital_loss": "politics.rs (native)",
    "secession": "politics.rs (native)", "vassal_rebellion": "politics.rs (native)",
    "restoration": "politics.rs (native)", "twilight_absorption": "politics.rs (native)",
    "collapse": "politics.rs (native)",
}
#: Descriptions the narrator rewords (``narration_context.event_text``).
REWORDED = {"move_capital", "mass_migration", "brain_drain", "Mass Migration"}


def static_inventory(root: Path) -> dict[str, str]:
    """type -> first emitting file (``Event`` calls and one level of helpers)."""
    files = [p for p in sorted(root.rglob("*.py")) if "experimental" not in p.parts]
    trees = {p: ast.parse(p.read_text(encoding="utf-8")) for p in files}
    emitters = {"Event": ("event_type", 1)}
    found: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for p, tree in trees.items():
            parents = {ch: node for node in ast.walk(tree) for ch in ast.iter_child_nodes(node)}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if name not in emitters:
                    continue
                pname, pidx = emitters[name]
                et = next((kw.value for kw in node.keywords if kw.arg == pname), None)
                if et is None and len(node.args) > pidx:
                    et = node.args[pidx]
                if isinstance(et, ast.Constant) and isinstance(et.value, str):
                    found.setdefault(et.value, str(p.relative_to(root)))
                elif isinstance(et, ast.Name):
                    cur = node
                    while cur in parents and not isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        cur = parents[cur]
                    if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)) and cur.name not in emitters:
                        args = [a.arg for a in cur.args.posonlyargs + cur.args.args]
                        if et.id in args:
                            idx = args.index(et.id) - (1 if args and args[0] in ("self", "cls") else 0)
                            emitters[cur.name] = (et.id, idx)
                            changed = True
    for t, where in COMPUTED.items():
        found.setdefault(t, where)
    found.pop("none", None)
    return found


def _runs(path: Path) -> list[Path]:
    return sorted(p for p in path.iterdir() if p.is_dir() and (p / "prompts.jsonl").exists())


def _listed(run: Path) -> set[str]:
    ids: set[str] = set()
    for line in (run / "prompts.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        ids.update(i for i in rec.get("shown_event_ids", rec["event_ids"]) if i)
    return ids


def table(src: Path, before: Path, after: Path) -> int:
    from chronicler import historiography as hg
    from chronicler import narration_context as nc
    from chronicler.bundle_codec import load_bundle
    from chronicler.models import Event

    inventory = static_inventory(src)
    count: Counter = Counter()
    empty: Counter = Counter()
    misleading: Counter = Counter()
    turning: set[str] = set()
    named_ok: Counter = Counter()
    listed_before: Counter = Counter()
    listed_after: Counter = Counter()
    for b_run, a_run in zip(_runs(before), _runs(after)):
        bundle = load_bundle(b_run / "chronicle_bundle.json")
        civs = {c["name"] for c in bundle["world_state"]["civilizations"]}
        lb, la = _listed(b_run), _listed(a_run)
        for raw in bundle["events_timeline"]:
            ev = Event.model_validate(raw)
            t = ev.event_type
            count[t] += 1
            if not ev.description:
                empty[t] += 1
            elif t in REWORDED and nc.event_text(ev) != ev.description.strip().rstrip("."):
                misleading[t] += 1
            if ev.importance >= nc.TURNING_POINT_IMPORTANCE and not nc.is_bookkeeping(ev):
                turning.add(t)
            if ev.region or ev.civs or any(a in civs for a in ev.actors):
                named_ok[t] += 1
            if ev.event_id in lb:
                listed_before[t] += 1
            if ev.event_id in la:
                listed_after[t] += 1

    types = sorted(set(inventory) | {t for t in count if not t.endswith("_ended")})
    ended = sorted(t for t in count if t.endswith("_ended") and t not in inventory)

    def accounts(t: str) -> str:
        if t in hg.ROUTINE:
            return "routine"
        if t.endswith("_ended") or t.startswith("capability_"):
            return "bookkeeping"
        for name in ("TWO_SIDED", "BATTLES", "ONE_SIDED_LOSS", "WAR_START", "HOSTILITY", "DISASTER",
                     "DISGRACE", "GLORY", "RULER", "FAITH", "PEACE"):
            if t in getattr(hg, name):
                return name.lower().replace("_", " ")
        return "unclassified (7+)"

    def curator_class(t: str) -> str:
        fake = Event(turn=0, event_type=t, actors=[], description="x")
        if nc.is_bookkeeping(fake):
            return "bookkeeping"
        if t in nc.ROUTINE_TYPES:
            return "routine"
        return "turning point" if t in turning else "scored"

    def text_before(t: str) -> str:
        if empty[t] or (t in COMPUTED and "hazard" in COMPUTED[t]):
            return "empty"
        if misleading[t]:
            return "misleading"
        return "ok"

    def text_after(t: str) -> str:
        if empty[t] or (t in COMPUTED and "hazard" in COMPUTED[t]):
            return "label" if t in nc.EVENT_LABELS else "generic label"
        if misleading[t]:
            return "reworded"
        return "ok"

    rows = []
    for t in types:
        names = "yes" if count[t] and named_ok[t] * 2 >= count[t] else ("actors" if count[t] else "-")
        rows.append((t, inventory.get(t, "runs only"), count[t], text_before(t), text_after(t), curator_class(t),
                     listed_before[t], listed_after[t], names, accounts(t)))
    print("| type | emitted in | n | line before | line after | curator after | listed before | listed after "
          "| names | accounts |")
    print("| --- | --- | ---: | --- | --- | --- | ---: | ---: | --- | --- |")
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")
    if ended:
        print(f"\nEpisode closings seen in the runs (bookkeeping, counted not listed): {', '.join(ended)}")

    total = len(rows)
    bad_before = [r[0] for r in rows if r[3] != "ok"]
    bad_after = [r[0] for r in rows if r[4] not in ("ok", "label", "reworded")]
    seen = [r for r in rows if r[2]]
    print(f"\nTypes: {total} (seen in the runs: {len(seen)}).")
    print(f"Readable, not misleading prompt line: before {total - len(bad_before)} of {total} "
          f"({', '.join(bad_before)}); after {total - len(bad_after)} of {total}.")
    print(f"Seen types listed in a prompt at least once: before {sum(1 for r in seen if r[6])} of {len(seen)}, "
          f"after {sum(1 for r in seen if r[7])} of {len(seen)}.")
    tp = [r for r in seen if r[5] == "turning point"]
    print(f"Turning-point types listed: before {sum(1 for r in tp if r[6])} of {len(tp)}, "
          f"after {sum(1 for r in tp if r[7])} of {len(tp)}.")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[0] == "table":
        return table(Path(argv[1]), Path(argv[2]), Path(argv[3]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
