#!/usr/bin/env python3
"""Per-run nomad numbers for a set of run directories (or gate batches).

``nomads_report.py DIR [DIR ...] [--json OUT]``

Each DIR is a run directory holding ``state.json`` (and, when present,
``chronicle_bundle.json``), or a directory of such runs (``seed_*``
subdirectories, searched recursively). For every run it prints:

* nomadic and pastoral civs (the peak alive at once over the run, from the
  bundle's ``history[n].nomads``; the final state's modes otherwise);
* raids that got through and raids driven off, plunder, tribute pacts;
* hordes formed, fragmented on the khan's death and dissolved otherwise,
  the wars hordes rode to;
* regions pastoral civs took from other polities, sedentarizations, dzuds;
* herd stock (mean over the run and final);
* polities alive at the end, civ records, final population, wars declared,
  secessions and federations formed (the same counts for flag-off runs, so
  on/off rows compare directly; nomad columns are zero there).

See docs/integration/nomads.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _runs(paths: list[Path]) -> list[Path]:
    out = []
    for path in paths:
        if (path / "state.json").exists():
            out.append(path / "state.json")
        else:
            out.extend(sorted(path.rglob("state.json")))
    return out


def run_metrics(state_path: Path) -> dict:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    nomads = state.get("nomads")
    civs = state.get("civilizations", [])
    events = state.get("events_timeline", [])
    counts: dict[str, int] = {}
    for ev in events:
        counts[ev["event_type"]] = counts.get(ev["event_type"], 0) + 1
    bundle_path = state_path.parent / "chronicle_bundle.json"
    history = []
    if bundle_path.exists():
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        history = [h["nomads"] for h in bundle.get("history", []) if h.get("nomads")]
    row = {
        "run": str(state_path.parent),
        "nomads": nomads is not None,
        "turns": state.get("turn", 0),
        "polities_alive": sum(1 for c in civs if c.get("regions")),
        "civ_records": len(civs),
        "population": sum(r.get("population", 0) for r in state.get("regions", [])),
        "wars_declared": counts.get("war_declared", 0),
        "secessions": counts.get("secession", 0),
        "federations_formed": counts.get("federation_formed", 0),
        "famines": counts.get("famine", 0),
    }
    keys = ("raids", "raids_repulsed", "plunder", "tributes", "tributes_repudiated", "hordes_formed",
            "hordes_fragmented", "hordes_dissolved", "horde_wars", "horde_rides", "nomad_conquests",
            "sedentarizations", "dzuds", "pastures_abandoned")
    if nomads is None:
        row.update({k: 0 for k in keys})
        row.update({"nomadic_civs": 0, "pastoral_civs": 0, "herd_mean": 0.0, "herd_final": 0.0})
        return row
    counters = nomads.get("counters", {})
    row.update({k: int(counters.get(k, 0)) for k in keys})
    if history:
        row["nomadic_civs"] = max(sum(1 for m in h["modes"].values() if m == "nomadic") for h in history)
        row["pastoral_civs"] = max(sum(1 for m in h["modes"].values() if m != "sedentary") for h in history)
        row["herd_mean"] = round(sum(h["herd_total"] for h in history) / len(history), 1)
    else:
        alive = [i for i, c in enumerate(civs) if c.get("regions")]
        modes = nomads.get("modes", [])
        row["nomadic_civs"] = sum(1 for i in alive if i < len(modes) and modes[i] == 2)
        row["pastoral_civs"] = sum(1 for i in alive if i < len(modes) and modes[i] > 0)
        row["herd_mean"] = round(sum(nomads.get("herds", [])), 1)
    row["herd_final"] = round(sum(nomads.get("herds", [])), 1)
    return row


COLUMNS = ("nomadic_civs", "pastoral_civs", "raids", "raids_repulsed", "tributes", "hordes_formed",
           "hordes_fragmented", "hordes_dissolved", "horde_wars", "horde_rides", "nomad_conquests",
           "sedentarizations",
           "dzuds", "herd_mean", "herd_final", "polities_alive", "civ_records", "population",
           "wars_declared", "secessions", "federations_formed", "famines")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dirs", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    rows = [run_metrics(p) for p in _runs(args.dirs)]
    print("run\t" + "\t".join(COLUMNS))
    for row in rows:
        print(row["run"] + "\t" + "\t".join(str(row[c]) for c in COLUMNS))
    if args.json is not None:
        args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
