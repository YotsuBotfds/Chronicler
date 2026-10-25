#!/usr/bin/env python3
"""Per-run fiscal census of chronicle bundles (finance on or off).

``python scripts/finance_census.py BATCH_DIR [BATCH_DIR ...] [--json OUT]``

Reads every ``seed_*/chronicle_bundle.json`` (or bundle paths given
directly) and reports, per run and pooled: the treasury distribution over
living civ-turns, the share of civ-turns with economy >= 95, debt/revenue,
loans, defaults, debasements, the price-index range, PSI, PSI crises,
revolts, civil wars, living polities at the end and extinct worlds. Finance
fields are empty for runs without ``--finance``.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from chronicler.bundle_codec import load_bundle


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def census(bundle: dict) -> dict:
    history = bundle.get("history") or []
    treasury, psi, debt_ratio, prices, stress = [], [], [], [], []
    econ_high = civ_turns = 0
    for snap in history:
        fin = (snap.get("finance") or {}).get("civs", {})
        for name, c in snap["civ_stats"].items():
            if not c.get("alive"):
                continue
            civ_turns += 1
            treasury.append(c["treasury"])
            econ_high += c["economy"] >= 95
            gov = c.get("governance") or {}
            if "psi" in gov:
                psi.append(gov["psi"])
            row = fin.get(name)
            if row:
                debt_ratio.append(row["debt"] / max(row["revenue_ema"], 1.0))
                prices.append(row["price_index"])
                stress.append(row["fiscal_stress"])
    types = Counter(e["event_type"] for e in bundle.get("events_timeline", []))
    focus = Counter(e["description"].rsplit(" develops ", 1)[-1].split(" ")[0]
                    for e in bundle.get("events_timeline", []) if e["event_type"] == "tech_focus_selected")
    loans = [e for e in bundle.get("events_timeline", []) if e["event_type"] == "loan_taken"]
    last = history[-1] if history else {"civ_stats": {}}
    alive = [c for c in last["civ_stats"].values() if c.get("alive")]
    population = sum(c["population"] for c in alive)
    final_fin = (last.get("finance") or {}).get("civs", {})
    return {
        "turns": len(history),
        "civ_turns": civ_turns,
        "treasury": {"p10": _pct(treasury, 0.1), "p50": _pct(treasury, 0.5), "p90": _pct(treasury, 0.9),
                     "max": max(treasury, default=0),
                     "final_mean": statistics.fmean([c["treasury"] for c in alive]) if alive else 0.0},
        "economy_ge_95_share": econ_high / max(civ_turns, 1),
        "psi": {"mean": statistics.fmean(psi) if psi else 0.0, "max": max(psi, default=0.0)},
        "psi_crises": types.get("psi_crisis", 0),
        "revolts": types.get("revolt", 0),
        "civil_wars": types.get("civil_war", 0),
        "secessions": types.get("secession", 0),
        "collapses": types.get("collapse", 0),
        "wars_declared": types.get("war_declared", 0),
        "tech_advances": types.get("tech_advancement", 0),
        "fiscal_crisis_institutions": types.get("fiscal_crisis", 0),
        "mutual_aid": types.get("mutual_aid", 0),
        "mercenaries": types.get("mercenary_spawned", 0),
        "focus_commerce_banking": focus.get("commerce", 0) + focus.get("banking", 0),
        "focus_total": sum(focus.values()),
        "builds": types.get("build", 0),
        "develops": types.get("develop", 0),
        "expands": types.get("expand", 0),
        "trades": types.get("trade", 0),
        "embargoes": types.get("embargo", 0),
        "loans": len(loans),
        "foreign_loans": sum(1 for e in loans if len(e.get("civs", [])) > 1),
        "defaults": types.get("state_default", 0),
        "debasements": types.get("debasement", 0),
        "fiscal_strain_episodes": types.get("fiscal_strain", 0),
        "inflation_episodes": types.get("price_inflation", 0),
        "debt_to_revenue": {"p50": _pct(debt_ratio, 0.5), "p90": _pct(debt_ratio, 0.9),
                            "max": max(debt_ratio, default=0.0),
                            "share_indebted": (sum(1 for d in debt_ratio if d > 0) / len(debt_ratio))
                            if debt_ratio else 0.0},
        "price_index": {"min": min(prices, default=1.0), "p50": _pct(prices, 0.5),
                        "max": max(prices, default=1.0)},
        "fiscal_stress": {"p50": _pct(stress, 0.5), "p90": _pct(stress, 0.9), "max": max(stress, default=0.0)},
        "final_debt": sum(r["debt"] for r in final_fin.values()),
        "alive_end": len(alive),
        "population_end": population,
        "extinct": not alive or population <= 0,
    }


def _bundles(paths: list[Path]):
    for path in paths:
        if path.is_file():
            yield path.parent.name, path
            continue
        found = sorted(path.glob("seed_*/chronicle_bundle.json"),
                       key=lambda p: int(p.parent.name.split("_")[1]))
        if not found and (path / "chronicle_bundle.json").exists():
            found = [path / "chronicle_bundle.json"]
        for bundle in found:
            yield bundle.parent.name, bundle


def pooled(rows: list[dict]) -> dict:
    def mean(key, sub=None):
        vals = [r[key][sub] if sub else r[key] for r in rows]
        return statistics.fmean(vals) if vals else 0.0

    return {
        "runs": len(rows),
        "treasury_p50_mean": mean("treasury", "p50"),
        "treasury_p90_mean": mean("treasury", "p90"),
        "treasury_max_max": max((r["treasury"]["max"] for r in rows), default=0),
        "treasury_final_mean": mean("treasury", "final_mean"),
        "economy_ge_95_share": mean("economy_ge_95_share"),
        "psi_mean": mean("psi", "mean"),
        "psi_max_max": max((r["psi"]["max"] for r in rows), default=0.0),
        "psi_crises": sum(r["psi_crises"] for r in rows),
        "revolts": sum(r["revolts"] for r in rows),
        "civil_wars": sum(r["civil_wars"] for r in rows),
        "secessions": sum(r["secessions"] for r in rows),
        "collapses": sum(r["collapses"] for r in rows),
        "wars_declared": sum(r["wars_declared"] for r in rows),
        "tech_advances": sum(r["tech_advances"] for r in rows),
        "fiscal_crisis_institutions": sum(r["fiscal_crisis_institutions"] for r in rows),
        "mutual_aid": sum(r["mutual_aid"] for r in rows),
        "mercenaries": sum(r["mercenaries"] for r in rows),
        "focus_commerce_banking": sum(r["focus_commerce_banking"] for r in rows),
        "focus_total": sum(r["focus_total"] for r in rows),
        "builds": sum(r["builds"] for r in rows),
        "develops": sum(r["develops"] for r in rows),
        "expands": sum(r["expands"] for r in rows),
        "trades": sum(r["trades"] for r in rows),
        "embargoes": sum(r["embargoes"] for r in rows),
        "loans": sum(r["loans"] for r in rows),
        "foreign_loans": sum(r["foreign_loans"] for r in rows),
        "runs_with_loans": sum(1 for r in rows if r["loans"]),
        "defaults": sum(r["defaults"] for r in rows),
        "runs_with_default": sum(1 for r in rows if r["defaults"]),
        "debasements": sum(r["debasements"] for r in rows),
        "runs_with_debasement": sum(1 for r in rows if r["debasements"]),
        "fiscal_strain_episodes": sum(r["fiscal_strain_episodes"] for r in rows),
        "inflation_episodes": sum(r["inflation_episodes"] for r in rows),
        "debt_to_revenue_p90_mean": mean("debt_to_revenue", "p90"),
        "debt_to_revenue_max": max((r["debt_to_revenue"]["max"] for r in rows), default=0.0),
        "share_indebted_mean": mean("debt_to_revenue", "share_indebted"),
        "price_index_min": min((r["price_index"]["min"] for r in rows), default=1.0),
        "price_index_max": max((r["price_index"]["max"] for r in rows), default=1.0),
        "fiscal_stress_p90_mean": mean("fiscal_stress", "p90"),
        "alive_end_mean": mean("alive_end"),
        "population_end_mean": mean("population_end"),
        "extinct_worlds": sum(1 for r in rows if r["extinct"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    rows = []
    for name, path in _bundles(args.paths):
        row = census(load_bundle(path))
        row["run"] = name
        rows.append(row)
    result = {"pooled": pooled(rows), "by_run": rows}
    text = json.dumps(result, indent=1, sort_keys=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text, encoding="utf-8")
    print(json.dumps(result["pooled"], indent=1, sort_keys=True))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
