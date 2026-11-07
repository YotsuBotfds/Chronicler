#!/usr/bin/env python3
"""Recompute historical CW6 adverse contrasts without simulation or source imports.

This intentionally requires the original frozen metrics bytes. It never spends
seeds, modifies the historical evidence or estimates a pure component effect.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics

METRICS_SHA256 = "b8365bf868b7cfdfa88740304a669429be2bff52d1000c9f0cd7b039eb0fba45"
IDENTITY = "45b176288eaf43018283a542f1531f855e58b8c6e55e0bb55bd0bef5b9624ab9"
ARMS = ("FULL", "A6R", "D3R", "D4C", "SUP")
SEEDS = {"t": tuple(range(781, 787)), "p": tuple(range(881, 887))}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("Historical audit refused: " + message)


def finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def near(a, b) -> bool:
    return finite(a) and finite(b) and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def describe(values: dict[str, float]) -> dict:
    observations = list(values.values())
    average = statistics.mean(observations)
    flipped_means = [math.fsum(sign * value for sign, value in zip(signs, observations)) / len(observations)
                     for signs in itertools.product((-1, 1), repeat=len(observations))]
    tolerance = 1e-12 * max(1.0, abs(average))
    return {"FULL_minus_A6R": values, "mean": average,
            "min": min(observations), "max": max(observations),
            "positive": sum(x > 0 for x in observations),
            "negative": sum(x < 0 for x in observations),
            "zero": sum(x == 0 for x in observations),
            "extreme_abs_sign_flips": sum(abs(x) >= abs(average) - tolerance for x in flipped_means),
            "sign_flips": len(flipped_means)}


def audit(metrics: Path) -> dict:
    contents = metrics.read_bytes()
    digest = hashlib.sha256(contents).hexdigest()
    require(digest == METRICS_SHA256, "metrics do not match the frozen historical bytes")
    rows = [json.loads(line) for line in contents.splitlines() if line.strip()]
    expected = {(arm, tag, seed) for arm in ARMS for tag, seeds in SEEDS.items() for seed in seeds}
    keys = [(row["arm"], row["stratum"], row["seed"]) for row in rows]
    require(len(rows) == len(set(keys)) == 60 and set(keys) == expected, "not exactly 60 enrolled arm/world rows")
    by = dict(zip(keys, rows))
    for key, row in by.items():
        label = str(key)
        require(row["screen"] == "CW6" and row["cohort"] == "held", label + " cohort")
        require(type(row["rc"]) is int and row["rc"] == 0 and row["pk"] == {}, label + " execution/extraction failure")
        require(row["identity"] == IDENTITY, label + " source identity")
        metric = row["m"]
        require(metric["turns"] == 120 and metric["regions"] == {"t": 8, "p": 32}[key[1]], label + " horizon/regions")
        require(finite(metric["person_turns"]) and metric["person_turns"] > 0, label + " population denominator")
        for result, total in (("balance_change_per_1000_pt", "balance_change"), ("deaths_per_1000_pt", "deaths")):
            require(near(metric[result], 1000 * metric[total] / metric["person_turns"]), label + " " + result)
        require(near(metric["service_per_region_turn"], metric["service_asset_turns"] / (120 * metric["regions"])), label + " service denominator")
        for cause in ("deaths_famine", "deaths_war"):
            harm = row["harm"][cause]
            require(harm["value"] is None and harm["state"] == "requires_slice_extractor", label + " fabricated cause-specific deaths")
        sidecar = metric["event_sidecar"]
        require(sidecar["present"] is True and sidecar["migration"] == metric["all_migrations"] == metric["x1_moves"] == row["harm"]["out_migration"]["value"], label + " migration authority")
        require(sidecar["unknown"] == metric["unknown_migration_drivers"] and sidecar["deaths"] == metric["deaths"], label + " sidecar counts")
        require(near(metric["unknown_migration_share"], sidecar["unknown"] / sidecar["migration"] if sidecar["migration"] else 0), label + " unknown share")
        require(sidecar["turn_min"] == 0 and sidecar["turn_max"] == 119, label + " sidecar dates")
        require(row["activation"]["activated"] is (None if key[0] == "FULL" else True), label + " filtered enrollment")

    strata = {}
    for tag, seeds in SEEDS.items():
        observations = {}
        for field in ("food_shortfall", "deaths_epidemic", "priced_out_persons", "priced_out_children", "population"):
            pairs = {}
            for seed in seeds:
                full = by[("FULL", tag, seed)]["harm"][field]["value"]
                control = by[("A6R", tag, seed)]["harm"][field]["value"]
                require(finite(full) and finite(control), f"{tag}{seed} {field} unobserved")
                pairs[str(seed)] = full - control
            observations[field] = describe(pairs)
        full_rows = [by[("FULL", tag, seed)] for seed in seeds]
        control_rows = [by[("A6R", tag, seed)] for seed in seeds]
        unknown = sum(row["m"]["unknown_migration_drivers"] for row in full_rows)
        migrations = sum(row["m"]["all_migrations"] for row in full_rows)
        observations["FULL_unknown_pooled"] = {"unknown": unknown, "migration": migrations, "share": unknown / migrations}
        observations["FULL_unknown_world_mean"] = statistics.mean(row["m"]["unknown_migration_share"] for row in full_rows)
        observations["FULL_A6R_totals"] = {
            arm: {field: math.fsum(row["m"][field] for row in selected)
                  for field in ("all_migrations", "x1_displaced_person_turns", "d3_evacuated", "d3_returned", "a6_offer_declines", "timber_orders")}
            for arm, selected in (("FULL", full_rows), ("A6R", control_rows))}
        strata[tag] = observations
    simulation = math.fsum(row["wall_s"] for row in rows)
    extraction = math.fsum(row["extract_s"] for row in rows)
    return {"status": "PASS", "source_metrics_sha256": digest, "source_identity": IDENTITY,
            "row_count": len(rows), "horizon": 120, "strata": strata,
            "simulation_s": simulation, "extraction_s": extraction,
            "simulation_and_extraction_s": simulation + extraction,
            "cause_specific_null_counts": {field: sum(row["harm"][field]["value"] is None for row in rows)
                                          for field in ("deaths_famine", "deaths_war")},
            "interpretation": "Historical total-package outcomes, not a pure A6/D3/crowding effect; sign-flip enumeration is descriptive, not qualification."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require(args.metrics.resolve() != args.out.resolve(), "refusing to overwrite historical metrics")
    receipt = audit(args.metrics)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": receipt["status"], "rows": receipt["row_count"],
                      "out": str(args.out), "simulation_and_extraction_s": receipt["simulation_and_extraction_s"]}))


if __name__ == "__main__":
    main()
