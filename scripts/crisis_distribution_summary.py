#!/usr/bin/env python3
"""Summarize already-recorded regional native food observations; never simulates.

Demand-weighted regional sufficiency is not household access or meal distribution.
Changing demand weights may move a mean independently of regional improvement.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

DECLARATION = {
    "measure": "native Phase-2 food sufficiency weighted by positive native food demand",
    "coverage": "known positive-demand regions / all region rows; zero or missing demand is not weighted",
    "deficit": "max(0, 1 - known regional sufficiency)",
    "recovery": "first of two consecutive known positive-demand turns >= 1 after an earlier observed turn < 1",
    "improving_mean": "strict increase from preceding consecutive turn with the same known positive-demand region IDs",
    "disparity": "all improving-mean transitions with a comparable region below 1 or a comparable region worsening",
    "limits": "regional model aggregates, not household meals, access, causal effects or population estimates; demand weights can change",
}


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def summarize(food_turns):
    rows = []
    for food in food_turns:
        if food is None or food.get("mode") != "hybrid" or food.get("timing") != "phase2":
            raise ValueError("expected native Phase-2 hybrid food accounting")
        source = food["source_turn"]
        regions = food["regions"]
        regional = []
        for r in regions:
            native = r.get("native") or {}
            demand, suff = native.get("demand"), native.get("sufficiency")
            demand = float(demand) if _number(demand) and demand >= 0 else None
            suff = float(suff) if _number(suff) and suff >= 0 else None
            regional.append({"region_id": r["region_id"], "native_count": r.get("native_count"),
                "demand": demand, "sufficiency": suff,
                "deficit": max(0.0, 1.0 - suff) if suff is not None else None,
                "weighted": demand is not None and demand > 0 and suff is not None})
        ids = [r["region_id"] for r in regional]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate region ID")
        known = [r for r in regional if r["weighted"]]
        known_demand = math.fsum(r["demand"] for r in known)
        rows.append({"source_turn": source, "regions": regional, "total_regions": len(regional),
            "known_positive_demand_regions": len(known), "known_positive_demand": known_demand,
            "region_coverage": len(known) / len(regional) if regional else None,
            "weighted_mean": (math.fsum(r["demand"] * r["sufficiency"] for r in known) / known_demand
                              if known_demand else None)})
    if any(b["source_turn"] <= a["source_turn"] for a, b in zip(rows, rows[1:])):
        raise ValueError("source turns must be strictly increasing")
    recovery = {}
    sustained = {}
    ids = sorted({r["region_id"] for row in rows for r in row["regions"]})
    for rid in ids:
        recovery[str(rid)] = None
        sustained[str(rid)] = None
        prior_deficit = False
        for a, b in zip(rows, rows[1:]):
            ar = next((r for r in a["regions"] if r["region_id"] == rid), None)
            br = next((r for r in b["regions"] if r["region_id"] == rid), None)
            if ar and ar["weighted"] and ar["sufficiency"] < 1:
                prior_deficit = True
            if (b["source_turn"] == a["source_turn"] + 1 and ar and br and
                    ar["weighted"] and br["weighted"] and ar["sufficiency"] >= 1 and br["sufficiency"] >= 1):
                if sustained[str(rid)] is None:
                    sustained[str(rid)] = a["source_turn"]
                if prior_deficit:
                    recovery[str(rid)] = a["source_turn"]
                    break
    transitions = []
    for a, b in zip(rows, rows[1:]):
        left = {r["region_id"]: r for r in a["regions"] if r["weighted"]}
        right = {r["region_id"]: r for r in b["regions"] if r["weighted"]}
        if (b["source_turn"] != a["source_turn"] + 1 or not left or left.keys() != right.keys() or
                b["weighted_mean"] <= a["weighted_mean"]):
            continue
        below = sorted(k for k in left if right[k]["sufficiency"] < 1)
        worsened = sorted(k for k in left if right[k]["sufficiency"] < left[k]["sufficiency"])
        if below or worsened:
            transitions.append({"from_source_turn": a["source_turn"], "to_source_turn": b["source_turn"],
                "mean_before": a["weighted_mean"], "mean_after": b["weighted_mean"],
                "below_one_regions": below, "worsening_regions": worsened})
    return {"timeline": rows, "first_sustained_sufficiency_by_region": sustained,
            "first_sustained_recovery_by_region": recovery,
            "mean_improved_with_regional_shortfall_or_decline": transitions}


def run(root: Path):
    from chronicler.bundle_codec import load_bundle
    a = root / "a-transport" / "first"
    receipt_path = a / "crisis-case.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("state") != "validated":
        raise ValueError("transport pair was not validated")
    pair_dir = Path(receipt["exact_pair_directory"])
    inputs = [receipt_path]
    cases = {}
    for arm in ("baseline", "intervention"):
        observations = a / f"{arm}-observations.json"
        bundle_path = pair_dir / arm / "chronicle_bundle.json"
        inputs.extend((observations, bundle_path))
        observed = json.loads(observations.read_text())
        history = load_bundle(bundle_path)["history"]
        if (len(observed) != len(history) or any(
            x["snapshot_turn"] != y["turn"] or x["food_accounting"] != y.get("food_accounting")
            for x, y in zip(observed, history))):
            raise ValueError(f"transport {arm} observations differ from exact pair bundle")
        cases[f"A_{arm}"] = summarize([x["food_accounting"] for x in observed])
    labor = root / "b-labor" / "actual" / "result.json"
    migration = root / "c-displacement" / "actual" / "result.json"
    inputs.extend((labor, migration))
    labor_data, migration_data = json.loads(labor.read_text()), json.loads(migration.read_text())
    for arm in ("care_off", "care_on"):
        cases[f"B_{arm}"] = summarize([r["food_accounting"] for r in labor_data["arms"][arm]["timeline"]])
    cases["C_distress_migration"] = summarize([r["food"] for r in migration_data["timeline"]])
    return {"declaration": DECLARATION, "input_sha256": {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
            "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "declaration.json").write_text(json.dumps(DECLARATION, indent=2) + "\n")
    result = run(args.cases_root)
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"cases": list(result["cases"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
