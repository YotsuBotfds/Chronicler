"""Production ledger report: realized against proxy depletion, exhausted
slots, collapses and recovery times, per world and per batch.

Reads each seed directory of one or more batches (``batch_<seed>/seed_*``):
the final world state and events of ``chronicle_bundle.json`` (every batch)
and, where present, ``validation_resource_ledger.arrow`` (the production
ledger, written with the validation sidecar since 2026-10). A batch from a
source without the ledger is summarized from its bundles alone. Read-only.

    python scripts/production_ledger_report.py --batch main=<batch dir> \
        --batch branch=<batch dir> --json out.json --markdown out.md

See docs/integration/production-ledger.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from chronicler.production_ledger import (  # noqa: E402
    EXHAUSTED_RESERVE, LEDGER_FILENAME, read_ledger, summarize_ledger,
)

ORE, PRECIOUS, FISH = 5, 6, 3
EVENT_TYPES = ("mine_collapse", "fishery_collapse", "fishery_recovery", "resource_depletion",
               "soil_exhaustion", "ecological_recovery")
_COLLAPSE = re.compile(r"^The fishing grounds of (.+) collapse")
_RECOVERY = re.compile(r"^Fish return to the waters of (.+?);")

LEDGER_TOTALS = (
    "mineral_depletion_realized", "mineral_depletion_proxy", "mineral_output",
    "fish_landed", "fish_lost", "fish_charged_proxy", "fish_regrowth", "fish_collapses",
    "fish_recoveries", "fish_unrecovered", "mine_soil_charged", "mine_soil_proxy",
    "overextraction_slot_turns_over", "yield_penalties",
)


def _bundle_summary(bundle: dict) -> dict:
    ws = bundle["world_state"]
    reserves = [r for region in ws["regions"]
                for r, t in zip(region["resource_reserves"], region["resource_types"]) if t in (ORE, PRECIOUS)]
    fish = [s for region in ws["regions"]
            for s, t in zip(region.get("fishery_stocks", [1.0] * 3), region["resource_types"]) if t == FISH]
    counts = {name: 0 for name in EVENT_TYPES}
    open_collapse: dict[str, int] = {}
    recoveries: list[int] = []
    for event in bundle.get("events_timeline", []):
        kind = event.get("event_type")
        if kind not in counts:
            continue
        counts[kind] += 1
        text = event.get("description") or ""
        if kind == "fishery_collapse":
            match = _COLLAPSE.match(text)
            if match:
                open_collapse.setdefault(match.group(1), event["turn"])
        elif kind == "fishery_recovery":
            match = _RECOVERY.match(text)
            if match and match.group(1) in open_collapse:
                recoveries.append(event["turn"] - open_collapse.pop(match.group(1)))
    return {
        "turns": ws.get("turn"),
        "mineral_slots": len(reserves),
        "mineral_exhausted": sum(1 for r in reserves if r < EXHAUSTED_RESERVE),
        "mineral_reserve_sum": sum(reserves),
        "fish_slots": len(fish),
        "fish_stock_sum": sum(fish),
        "fish_below_collapse": sum(1 for s in fish if s < 0.25),
        "events": counts,
        "fishery_recovery_turns": recoveries,
        "fishery_collapses_open": len(open_collapse),
        "population_final": sum(region["population"] for region in ws["regions"]),
    }


def summarize_batch(batch_dir: Path) -> dict:
    seeds = sorted(p for p in batch_dir.glob("seed_*") if p.is_dir())
    per_seed = {}
    for seed_dir in seeds:
        bundle_path = seed_dir / "chronicle_bundle.json"
        if not bundle_path.is_file():
            continue
        entry = {"bundle": _bundle_summary(json.loads(bundle_path.read_text()))}
        ledger_path = seed_dir / LEDGER_FILENAME
        if ledger_path.is_file():
            entry["ledger"] = summarize_ledger(read_ledger(ledger_path))
        per_seed[seed_dir.name] = entry
    return {"batch": str(batch_dir), "totals": totals_of(per_seed), "per_seed": per_seed}


def totals_of(per_seed: dict) -> dict:
    """A batch's totals from its per-seed summaries."""
    totals: dict = {"worlds": len(per_seed), "with_ledger": sum(1 for e in per_seed.values() if "ledger" in e)}
    b_keys = ("mineral_slots", "mineral_exhausted", "mineral_reserve_sum", "fish_slots", "fish_stock_sum",
              "fish_below_collapse", "fishery_collapses_open", "population_final")
    for key in b_keys:
        totals[key] = sum(e["bundle"][key] for e in per_seed.values())
    totals["events"] = {name: sum(e["bundle"]["events"][name] for e in per_seed.values()) for name in EVENT_TYPES}
    recov = [t for e in per_seed.values() for t in e["bundle"]["fishery_recovery_turns"]]
    totals["fishery_recoveries"] = len(recov)
    totals["fishery_recovery_turns_mean"] = sum(recov) / len(recov) if recov else None
    totals["mineral_reserve_mean"] = (totals["mineral_reserve_sum"] / totals["mineral_slots"]
                                      if totals["mineral_slots"] else None)
    totals["fish_stock_mean"] = totals["fish_stock_sum"] / totals["fish_slots"] if totals["fish_slots"] else None
    ledgers = [e["ledger"] for e in per_seed.values() if "ledger" in e]
    if ledgers:
        totals["ledger"] = {key: sum(l.get(key) or 0 for l in ledgers) for key in LEDGER_TOTALS}
        totals["ledger"]["overextraction_pressure_max"] = max(l.get("overextraction_pressure_max", 0.0)
                                                              for l in ledgers)
        recov_l = [l["fish_recovery_turns_mean"] * l["fish_recoveries"] for l in ledgers
                   if l.get("fish_recoveries")]
        n_recov = sum(l.get("fish_recoveries") or 0 for l in ledgers)
        totals["ledger"]["fish_recovery_turns_mean"] = sum(recov_l) / n_recov if n_recov else None
    return totals


def _seed_number(name: str) -> int:
    return int(name.rsplit("_", 1)[-1])


def restrict(report: dict, seeds: tuple[int, int] | None) -> dict:
    """``report`` with only the seeds in the inclusive range (all when None)."""
    if seeds is None:
        return report
    per_seed = {k: v for k, v in report["per_seed"].items() if seeds[0] <= _seed_number(k) <= seeds[1]}
    return {**report, "totals": totals_of(per_seed), "per_seed": per_seed}


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.4f}" if abs(value) < 10 else f"{value:,.1f}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def markdown(reports: dict[str, dict]) -> str:
    labels = list(reports)
    rows = [
        ("worlds (with ledger)", lambda t: f"{t['worlds']} ({t['with_ledger']})"),
        ("mineral slots exhausted at the end (of)", lambda t: f"{t['mineral_exhausted']} ({t['mineral_slots']})"),
        ("mean final mineral reserve", lambda t: _fmt(t["mineral_reserve_mean"])),
        ("mine collapses", lambda t: _fmt(t["events"]["mine_collapse"])),
        ("fish slots; mean final stock", lambda t: f"{t['fish_slots']}; {_fmt(t['fish_stock_mean'])}"),
        ("fish slots below 0.25 at the end", lambda t: _fmt(t["fish_below_collapse"])),
        ("fishery collapses / recoveries (events)", lambda t: f"{t['events']['fishery_collapse']} / "
                                                              f"{t['events']['fishery_recovery']}"),
        ("fishery recovery time, mean turns (events)", lambda t: _fmt(t["fishery_recovery_turns_mean"])),
        ("resource_depletion (overextraction) events", lambda t: _fmt(t["events"]["resource_depletion"])),
        ("soil_exhaustion events", lambda t: _fmt(t["events"]["soil_exhaustion"])),
        ("ecological_recovery events", lambda t: _fmt(t["events"]["ecological_recovery"])),
        ("final population (all worlds)", lambda t: _fmt(t["population_final"])),
    ]
    ledger_rows = [
        ("ledger: mineral reserve drawn (realized rule)", "mineral_depletion_realized"),
        ("ledger: mineral reserve the population proxy draws", "mineral_depletion_proxy"),
        ("ledger: ore and precious output (goods)", "mineral_output"),
        ("ledger: fish landed (stock units)", "fish_landed"),
        ("ledger: fish charged but never landed", "fish_lost"),
        ("ledger: fish allowance (the full-charge rule)", "fish_charged_proxy"),
        ("ledger: fish regrowth", "fish_regrowth"),
        ("ledger: fishery collapses / recoveries (stock < 0.25 / >= 0.6)", None),
        ("ledger: fishery recovery time, mean turns", "fish_recovery_turns_mean"),
        ("ledger: soil the mines took", "mine_soil_charged"),
        ("ledger: soil the flat per-mine rule takes", "mine_soil_proxy"),
        ("ledger: overextraction pressure max (take / sustainable)", "overextraction_pressure_max"),
        ("ledger: slot-turns over sustainable; yield penalties", None),
    ]
    out = ["| | " + " | ".join(labels) + " |", "| --- |" + " --- |" * len(labels)]
    for name, fn in rows:
        out.append(f"| {name} | " + " | ".join(fn(reports[l]["totals"]) for l in labels) + " |")
    for name, key in ledger_rows:
        cells = []
        for label in labels:
            ledger = reports[label]["totals"].get("ledger")
            if ledger is None:
                cells.append("-")
            elif key is None and "collapses" in name:
                cells.append(f"{ledger['fish_collapses']} / {ledger['fish_recoveries']}")
            elif key is None:
                cells.append(f"{ledger['overextraction_slot_turns_over']}; {ledger['yield_penalties']}")
            else:
                cells.append(_fmt(ledger.get(key)))
        out.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--batch", action="append", default=[], metavar="LABEL=DIR",
                        help="a labelled batch directory (batch_<seed>); repeat to compare")
    parser.add_argument("--saved", action="append", default=[], metavar="LABEL=JSON[:NAME]",
                        help="a batch summarized earlier by --json (its entry NAME, else its only one)")
    parser.add_argument("--seeds", metavar="LO-HI", help="only these seeds (inclusive), for matched comparisons")
    parser.add_argument("--json", type=Path, help="write the full report here")
    parser.add_argument("--markdown", type=Path, help="write the comparison table here")
    args = parser.parse_args(argv)
    seeds = None
    if args.seeds:
        lo, _, hi = args.seeds.partition("-")
        seeds = (int(lo), int(hi or lo))
    reports = {}
    for spec in args.batch:
        label, _, path = spec.partition("=")
        if not path:
            parser.error(f"--batch {spec!r}: expected LABEL=DIR")
        reports[label] = restrict(summarize_batch(Path(path)), seeds)
    for spec in args.saved:
        label, _, rest = spec.partition("=")
        path, _, name = rest.partition(":")
        saved = json.loads(Path(path).read_text())
        if not name:
            if len(saved) != 1:
                parser.error(f"--saved {spec!r}: name one of {sorted(saved)}")
            name = next(iter(saved))
        reports[label] = restrict(saved[name], seeds)
    if not reports:
        parser.error("give at least one --batch or --saved")
    table = markdown(reports)
    print(table)
    if args.json:
        args.json.write_text(json.dumps(reports, indent=1, sort_keys=True))
    if args.markdown:
        args.markdown.write_text(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
