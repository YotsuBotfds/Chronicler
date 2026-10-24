#!/usr/bin/env python3
"""Per-run maritime numbers for a set of run directories (or gate batches).

``maritime_report.py DIR [DIR ...] [--json OUT]``

Each DIR is a run directory (holding ``state.json``) or a batch directory
(holding ``seed_*/state.json``). For every run it prints:

* fleets commissioned, ships built, naval battles, blockades, piracy losses
  (cargo units), overseas campaigns (armies landed on foreign shores),
  colonies, and the maritime layer's own measured sea-lane trade (cargo
  units over the run): all 0 when the switch was off;
* ``ledger_sea_trade``: the contact ledger's final decayed trade stock on
  sea-lane edges, measured the same way with the switch on or off (the sea
  model is derived from the saved world when the run has no maritime state);
* polities alive at the end.

See docs/integration/maritime.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

COLUMNS = (
    "fleets", "ships_built", "naval_battles", "blockades", "piracy_losses",
    "overseas_campaigns", "colonies", "sea_trade", "ledger_sea_trade", "polities_alive",
)


def _states(paths: list[Path]) -> list[Path]:
    out = []
    for path in paths:
        if (path / "state.json").exists():
            out.append(path / "state.json")
        else:
            out.extend(sorted(path.glob("seed_*/state.json")))
    return out


def run_metrics(state_path: Path) -> dict:
    from chronicler.maritime import build_sea_model
    from chronicler.models import WorldState
    world = WorldState.load(state_path)
    state = world.maritime
    counters = state.counters if state is not None else {}
    model = state if state is not None else build_sea_model(world)
    lanes = {(a, b) for a, b, _ in model.lanes} | {(b, a) for a, b, _ in model.lanes}
    ledger = world.contact_ledger
    ledger_sea = 0.0
    if ledger is not None:
        ledger_sea = sum(row[2] for row in ledger.edges if (row[0], row[1]) in lanes)
    return {
        "run": str(state_path.parent),
        "seed": world.seed,
        "maritime": state is not None,
        "zones": len(model.zones),
        "lanes": len(model.lanes),
        "fleets": int(counters.get("fleets_commissioned", 0)),
        "ships_built": int(counters.get("ships_built", 0)),
        "naval_battles": int(counters.get("naval_battles", 0)),
        "blockades": int(counters.get("blockades", 0)),
        "piracy_losses": round(float(counters.get("piracy_losses", 0.0)), 2),
        "overseas_campaigns": int(counters.get("overseas_campaigns", 0)),
        "colonies": int(counters.get("colonies", 0)),
        "sea_trade": round(float(counters.get("sea_trade", 0.0)), 1),
        "ledger_sea_trade": round(ledger_sea, 2),
        "polities_alive": sum(1 for c in world.civilizations if c.regions),
    }


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {}
    return {col: round(sum(r[col] for r in rows) / len(rows), 3) for col in COLUMNS}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dirs", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    rows = [run_metrics(p) for p in _states(args.dirs)]
    header = ["run", *COLUMNS]
    print("\t".join(header))
    for r in rows:
        print("\t".join(str(r[c]) for c in header))
    mean = summarize(rows)
    if mean:
        print("\t".join(["mean", *(str(mean[c]) for c in COLUMNS)]))
    if args.json is not None:
        args.json.write_text(json.dumps({"runs": rows, "mean": mean}, indent=2), encoding="utf-8")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
