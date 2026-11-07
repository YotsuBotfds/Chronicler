#!/usr/bin/env python3
"""Independent CW6 final held arithmetic audit; stdlib only, no source imports.

Run only after the held cohort and report are complete. The receipt retains the
registered FULL-minus-control primary sign and control-minus-FULL harm sign.
"""
import argparse
from collections import Counter
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import statistics

ARMS = ("FULL", "A6R", "D3R", "D4C", "SUP")
CONTROLS = ARMS[1:]
SEEDS = {"t": tuple(range(781, 787)), "p": tuple(range(881, 887))}
PRIMARY = {
    "cw6_balance": ("A6R", "balance_change_per_1000_pt"),
    "cw6_deaths": ("D3R", "deaths_per_1000_pt"),
    "cw6_service": ("SUP", "service_per_region_turn"),
}
SECONDARY = (
    "income_gross", "income_applied", "wages_milli", "withheld_native", "wealth_close", "a6_refusals",
    "a6_repeated_refusals", "d3_wounded", "d3_released", "d3_evacuated", "d3_returned", "battle_deaths",
    "separation_person_pairs", "injury_episode_turns", "army_hunger_ration_turns", "army_supply_food_milli",
    "requisition_milli", "destroyed_food_milli", "restitution_paid_milli", "claims_unpaid_final_milli",
    "infra_work", "infra_timber_used", "infra_paid_milli", "timber_delivered_milli", "cover_loss",
    "all_migrations", "unknown_migration_share", "x1_opened_spells", "x1_displaced_person_turns",
    "branch_funded_turns", "branch_payer_turns", "branch_dues_milli",
)
HARMS = {
    "population": "Population at the end (sum over civilizations)",
    "treasury": "Treasury at the end (sum over civilizations)",
    "food_shortfall": "Food shortfall after relief over the run (food)",
    "priced_out_persons": "Priced-out person-turns",
    "priced_out_children": "Priced-out child-turns",
    "deaths_famine": "Deaths by famine (the famine authority)",
    "deaths_epidemic": "Deaths by epidemic (the epidemic authority)",
    "deaths_war": "Deaths by war (the casualty authority)",
    "out_migration": "Agents migrating between regions over the run",
    "wealth_gini": "Mean wealth Gini of living civilizations at the end",
    "forest_stand": "Timber stand share of capacity at the end",
}
EXPECTED_IDENTITY = "45b176288eaf43018283a542f1531f855e58b8c6e55e0bb55bd0bef5b9624ab9"


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def near(a, b):
    return number(a) and number(b) and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def describe(values):
    average = statistics.mean(values)
    means = [math.fsum(sign * value for sign, value in zip(signs, values)) / len(values)
             for signs in itertools.product((-1, 1), repeat=len(values))]
    tolerance = 1e-12 * max(1, abs(average))
    return {
        "n": len(values), "mean": average, "min": min(values), "max": max(values),
        "positive": sum(x > 0 for x in values), "negative": sum(x < 0 for x in values),
        "zero": sum(x == 0 for x in values), "assignments": len(means),
        "extreme": sum(abs(x) >= abs(average) - tolerance for x in means),
        "flip_min": min(means), "flip_max": max(means),
    }


def table_cells(seeds, values):
    summary = describe(values)
    return [
        "; ".join(f"{seed}: {value:+.4g}" for seed, value in zip(seeds, values)),
        f"{summary['mean']:+.4g} [{summary['min']:+.4g}, {summary['max']:+.4g}]",
        f"{summary['positive']} / {summary['negative']} / {summary['zero']}",
        f"{summary['extreme']}/{summary['assignments']} as extreme; means "
        f"[{summary['flip_min']:+.4g}, {summary['flip_max']:+.4g}]",
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--directory", type=Path, default=Path("/workspace/evidence/cw6/held"))
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()
    directory = args.directory
    metrics = directory / "metrics.jsonl"
    report = directory / "report.md"
    receipt_path = args.receipt or directory / "independent-arithmetic.json"
    contents = metrics.read_bytes()
    rows = [json.loads(line) for line in contents.splitlines() if line.strip()]
    expected = {(arm, tag, seed) for arm in ARMS for tag, seeds in SEEDS.items() for seed in seeds}
    counts = Counter((r["arm"], r["stratum"], r["seed"]) for r in rows)
    if len(rows) != 60 or set(counts) != expected or any(n != 1 for n in counts.values()):
        raise SystemExit("Final audit refused: expected exactly 60 unique enrolled arm/world rows; no partial efficacy analysis.")
    report_text = report.read_text()
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    problems = []

    def check(condition, message):
        if not condition:
            problems.append(message)

    for row in rows:
        label = f"{row['arm']}-{row['stratum']}{row['seed']}"
        m = row.get("m", {})
        check(row.get("screen") == "CW6" and row.get("cohort") == "held", f"{label}: cohort identity")
        check(row.get("rc") == 0 and row.get("pk") == {}, f"{label}: rc/pk failure")
        check(row.get("identity") == EXPECTED_IDENTITY, f"{label}: source identity")
        check(m.get("turns") == 120 and m.get("regions") == {"t": 8, "p": 32}[row["stratum"]],
              f"{label}: horizon/regions")
        for key in ("wall_s", "extract_s"):
            check(number(row.get(key)) and row[key] >= 0, f"{label}: {key} malformed")
        act = row.get("activation", {})
        if row["arm"] == "FULL":
            check(act == {"activated": None, "evidence": "root arm"}, f"{label}: FULL activation")
        else:
            check(act.get("activated") is True and act.get("evidence") ==
                  "Every enrolled world, including zero mechanism activation; validation is separate",
                  f"{label}: unconditioned enrollment")
        for key in ("balance_change_per_1000_pt", "deaths_per_1000_pt", "service_per_region_turn"):
            check(number(m.get(key)), f"{label}: missing primary {key}")
        check(number(m.get("person_turns")) and m["person_turns"] > 0, f"{label}: person-turn denominator")
        check(near(m["balance_change_per_1000_pt"], 1000 * m["balance_change"] / m["person_turns"]),
              f"{label}: balance denominator")
        check(near(m["deaths_per_1000_pt"], 1000 * m["deaths"] / m["person_turns"]), f"{label}: death denominator")
        check(near(m["service_per_region_turn"], m["service_asset_turns"] / (m["regions"] * 120)),
              f"{label}: service denominator")
        for key in ("deaths_famine", "deaths_war"):
            h = row.get("harm", {}).get(key, {})
            check(h.get("value") is None and h.get("state") == "requires_slice_extractor",
                  f"{label}: {key} null lost")
        side = m.get("event_sidecar", {})
        migrations, unknown = m.get("all_migrations"), m.get("unknown_migration_drivers")
        check(side.get("present") is True and side.get("migration") == migrations ==
              row["harm"]["out_migration"]["value"] == m.get("x1_moves"), f"{label}: total migration authority")
        check(side.get("unknown") == unknown and type(unknown) is int and 0 <= unknown <= migrations,
              f"{label}: unknown migration count")
        check(near(m.get("unknown_migration_share"), unknown / migrations if migrations else 0),
              f"{label}: unknown migration share")
        check(side.get("deaths") == m.get("deaths"), f"{label}: death authority")
        check(number(side.get("bytes")) and side["bytes"] > 0 and
              re.fullmatch(r"[0-9a-f]{64}", str(side.get("sha256"))) is not None,
              f"{label}: sidecar identity")
        check(side.get("turn_min") == 0 and side.get("turn_max") == 119, f"{label}: sidecar turn range")
        for key in ("dropped_a6_rows", "dropped_work_rows", "dropped_war_events"):
            check(number(m.get(key)) and m[key] >= 0, f"{label}: dropped sample count {key}")
    simulation_s = math.fsum(row["wall_s"] for row in rows)
    extraction_s = math.fsum(row["extract_s"] for row in rows)
    actual_s = math.fsum(row["wall_s"] + row["extract_s"] for row in rows)
    check(actual_s <= 3600, "actual compute exceeds one core-hour")
    check(f"Runs: 60; failed: 0 (missing outcomes: 0); simulation and extraction seconds {actual_s:.0f} "
          f"({actual_s / 3600:.3f} core-hours)" in report_text, "report uses actual run/extraction total incorrectly")
    check("INCOMPLETE" not in report_text and "FAILED" not in report_text, "report incomplete/failed")
    report_tables = [[cell.strip() for cell in line.strip().strip("|").split("|")]
                     for line in report_text.splitlines() if line.startswith("| ")]
    primary_receipt = {}
    outcome_checks = 0
    for outcome, (control, metric) in PRIMARY.items():
        primary_receipt[outcome] = {"sign": f"FULL - {control}", "metric": metric, "strata": {}}
        for tag, seeds in SEEDS.items():
            values = [by[("FULL", tag, seed)]["m"][metric] - by[(control, tag, seed)]["m"][metric] for seed in seeds]
            matching = [line for line in report_tables if line[0].startswith(outcome + ":") and line[1] == tag]
            check(len(matching) == 1 and matching[0][2:6] == table_cells(seeds, values), f"report primary {outcome}/{tag}")
            primary_receipt[outcome]["strata"][tag] = {"values": dict(zip(map(str, seeds), values)), **describe(values)}
            outcome_checks += 1
    secondary_checks = 0
    for control in CONTROLS:
        for metric in SECONDARY:
            outcome = f"cw6_{control}_{metric}"
            for tag, seeds in SEEDS.items():
                values = [by[("FULL", tag, seed)]["m"][metric] - by[(control, tag, seed)]["m"][metric] for seed in seeds]
                matching = [line for line in report_tables if line[0].startswith(outcome + ":") and line[1] == tag]
                check(len(matching) == 1 and matching[0][2:6] == table_cells(seeds, values), f"report secondary {outcome}/{tag}")
                secondary_checks += 1
    harm_checks = 0
    harm_summary = {}
    for control in CONTROLS:
        harm_summary[control] = {}
        for metric, label in HARMS.items():
            harm_summary[control][metric] = {}
            for tag, seeds in SEEDS.items():
                matching = [line for line in report_tables if line[0] == f"{control} - FULL" and line[1] == label and line[2] == tag]
                check(len(matching) == 1, f"report missing/duplicate harm {control}/{metric}/{tag}")
                if metric in ("deaths_famine", "deaths_war"):
                    check(len(matching) == 1 and matching[0][3:7] == ["requires slice extractor", "n/a", "n/a", "n/a"],
                          f"report fabricated cause harm {control}/{metric}/{tag}")
                    harm_summary[control][metric][tag] = None
                else:
                    values, valid_seeds, world_cells, missing = [], [], [], {}
                    for seed in seeds:
                        harms = [by[(arm, tag, seed)]["harm"][metric] for arm in (control, "FULL")]
                        if any(h["value"] is None for h in harms):
                            absent = next(h for h in harms if h["value"] is None)
                            world_cells.append(f"{seed}: {absent['state'].replace('_', ' ')}")
                            missing[str(seed)] = harms
                        else:
                            value = harms[0]["value"] - harms[1]["value"]
                            values.append(value)
                            valid_seeds.append(seed)
                            world_cells.append(f"{seed}: {value:+.4g}")
                    expected_cells = table_cells(valid_seeds, values)
                    expected_cells[0] = "; ".join(world_cells)
                    check(len(matching) == 1 and matching[0][3:7] == expected_cells,
                          f"report harm sign/arithmetic {control}/{metric}/{tag}")
                    harm_summary[control][metric][tag] = {**describe(values), "missing": missing}
                harm_checks += 1
    for control in CONTROLS:
        for tag, seeds in SEEDS.items():
            matching = [line for line in report_tables if line[0] == control and len(line) == 4 and line[1] == tag]
            check(len(matching) == 1 and matching[0][2:] ==
                  ["; ".join(f"{seed}: activated" for seed in seeds), "6 of 6"], f"report activation {control}/{tag}")
    full_observations = {}
    for tag, seeds in SEEDS.items():
        chosen = [by[("FULL", tag, seed)] for seed in seeds]
        migrations = sum(r["m"]["all_migrations"] for r in chosen)
        unknown = sum(r["m"]["unknown_migration_drivers"] for r in chosen)
        full_observations[tag] = {
            "all_migrations": migrations, "unknown_migration_drivers": unknown,
            "pooled_unknown_share": unknown / migrations if migrations else 0,
            "unknown_share_range": [min(r["m"]["unknown_migration_share"] for r in chosen), max(r["m"]["unknown_migration_share"] for r in chosen)],
            **{key: sum(r["m"][key] for r in chosen) for key in
               ("x1_other_moves", "x1_opened_spells", "x1_displaced_person_turns", "dropped_a6_rows", "dropped_work_rows", "dropped_war_events", "a6_work_unknown")},
        }
    samples = {}
    for arm in ARMS:
        samples[arm] = {}
        for tag, seeds in SEEDS.items():
            samples[arm][tag] = {key: sum(by[(arm, tag, seed)]["m"][key] for seed in seeds)
                                 for key in ("dropped_a6_rows", "dropped_work_rows", "dropped_war_events",
                                             "a6_work_observed", "a6_work_unknown")}
    receipt = {
        "audit": "Independent final CW6 held arithmetic; no simulation/source imports or source edits",
        "status": "PASS" if not problems else "FAIL", "problems": problems,
        "metrics_sha256": hashlib.sha256(contents).hexdigest(),
        "report_sha256": hashlib.sha256(report_text.encode()).hexdigest(),
        "rows": len(rows), "matrix": "5 arms x 12 registered worlds, exactly once each",
        "turns": 120, "regions_by_stratum": {"t": 8, "p": 32},
        "all_rc_zero": all(r.get("rc") == 0 for r in rows),
        "control_activation_unconditioned": all(r.get("activation", {}).get("activated") is True
                                                for r in rows if r["arm"] != "FULL"),
        "actual_simulation_s": simulation_s, "actual_extraction_s": extraction_s,
        "actual_total_s": actual_s, "actual_core_hours": actual_s / 3600,
        "identity": EXPECTED_IDENTITY,
        "primary_report_rows_checked": outcome_checks, "secondary_report_rows_checked": secondary_checks,
        "harm_report_rows_checked": harm_checks,
        "primary": primary_receipt,
        "fixed_harms_control_minus_FULL": harm_summary,
        "null_cause_fields": ["deaths_famine", "deaths_war"],
        "null_harm_counts": {key: sum(r["harm"][key]["value"] is None for r in rows)
                             for key in HARMS if any(r["harm"][key]["value"] is None for r in rows)},
        "FULL_measurement_and_sample_observations": full_observations,
        "bounded_sample_state_by_arm_stratum": samples,
        "interpretation": [
            "Primary comparisons include all six worlds per stratum regardless of mechanism activation.",
            "Actual service denominators use 8 template regions or 32 procedural regions, each for 120 turns.",
            "Forest stand is unrecorded for all t786 arms because no timber capacity remains; its template harm uses five pairs/32 assignments.",
            "Unknown migration drivers are measurement harm; lower classified X1 displacement cannot show a physical displacement benefit.",
            "T-1 X1 displaced share also changes C2 exposure via 1 + 0.25 * displaced_share; FULL-A6R includes this exposure-proxy feedback.",
            "Unknown personal work costs remain unknown; bounded dropped samples cannot replace world totals.",
            "Sign-flip enumeration is descriptive; these 12 worlds do not establish qualification or a universal effect.",
        ],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": receipt["status"], "rows": len(rows), "actual_s": actual_s,
                      "receipt": str(receipt_path), "problems": problems}, sort_keys=True))
    raise SystemExit(bool(problems))


if __name__ == "__main__":
    main()
