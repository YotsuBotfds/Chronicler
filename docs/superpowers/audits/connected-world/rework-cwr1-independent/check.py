#!/usr/bin/env python3
"""Independent CWR1 metric arithmetic audit. Standard library; no simulation imports.

This reads receipts, not authoritative per-turn frames. A passing result does
not replace source review, the strict extractor, raw-bundle readback or native
identity verification. It never executes a simulation or writes a registry.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import re
import statistics

NATIVE = "b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd"
HORIZON = 120
ARMS = {
    "RD": ("record_only", "all", "density_only", "active", "retail"),
    "AD": ("adapt", "all", "density_only", "active", "retail"),
    "RL": ("record_only", "all", "legacy_displacement", "active", "retail"),
    "AL": ("adapt", "all", "legacy_displacement", "active", "retail"),
    "MX": ("adapt", "no_migration_experience", "density_only", "active", "retail"),
    "IX": ("adapt", "no_information", "density_only", "active", "retail"),
    "WX": ("adapt", "no_work", "density_only", "active", "retail"),
    "TX": ("adapt", "no_trade", "density_only", "active", "retail"),
    "RPC": ("record_only", "all", "density_only", "cost_only", "retail"),
    "APC": ("adapt", "all", "density_only", "cost_only", "retail"),
    "RNR": ("record_only", "all", "density_only", "active", "no_relief"),
    "ANR": ("adapt", "all", "density_only", "active", "no_relief"),
}
SEEDS = {
    "pilot": {"t": (5,), "p": (19,)},
    "held": {"t": tuple(range(4101, 4107)), "p": tuple(range(4201, 4207))},
}
PAIRS = (("AD", "RD"), ("AL", "RL"), ("RL", "RD"), ("AL", "AD"),
         ("MX", "AD"), ("IX", "AD"), ("WX", "AD"), ("TX", "AD"),
         ("APC", "RPC"), ("RPC", "RD"), ("APC", "AD"),
         ("ANR", "RNR"), ("RNR", "RD"), ("ANR", "AD"))
INTERACTIONS = {
    "crowding": (("AL", 1), ("RL", -1), ("AD", -1), ("RD", 1)),
    "health": (("AD", 1), ("RD", -1), ("APC", -1), ("RPC", 1)),
    "retail": (("AD", 1), ("RD", -1), ("ANR", -1), ("RNR", 1)),
}
PRIMARY = {
    "cwr_food": ("food_shortfall", (("AD", 1), ("RD", -1))),
    "cwr_epidemic": ("epidemic_deaths", (("AD", 1), ("RD", -1))),
    "cwr_crowding_interaction": ("epidemic_deaths", INTERACTIONS["crowding"]),
}
SUPPORTING = (
    "food_shortfall_per_1000_pt", "epidemic_deaths_per_1000_pt", "person_turns",
    "all_migrations", "unknown_migration_share", "x1_displaced_person_turns",
    "recent_arrival_person_turns", "added_crowding_factor_sum", "a6_personal_rows",
    "d3_input_rows", "combined_native_choice_changes", "a6_offer_declines",
    "retail_access_deficit", "retail_access_unknown_region_turns",
    "retail_free_rations_observed", "retail_free_pool_observed",
    "retail_priority_household_turns", "retail_free_to_priority_observed",
    "public_relief_food", "native_food_produced", "native_food_consumed",
    "health_cash_milli", "care_farm_time", "guard_farm_time", "food_consumed_milli",
)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def count(value):
    return number(value) and value >= 0 and value == math.floor(value)


def near(a, b):
    return number(a) and number(b) and math.isclose(a, b, rel_tol=1e-11, abs_tol=1e-10)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def obj(value):
    return value if isinstance(value, dict) else {}


def describe(values, draws=10000):
    """Whole-world descriptive summaries; never an eligibility decision."""
    if not values:
        return None
    mean = statistics.mean(values)
    flipped = [math.fsum(s * v for s, v in zip(signs, values)) / len(values)
               for signs in itertools.product((-1, 1), repeat=len(values))]
    tolerance = 1e-12 * max(1, abs(mean))
    rng = random.Random(20261107)
    bootstrap = sorted(math.fsum(values[rng.randrange(len(values))] for _ in values) / len(values)
                       for _ in range(draws))
    return {"n": len(values), "mean": mean, "min": min(values), "max": max(values),
            "positive": sum(v > 0 for v in values), "negative": sum(v < 0 for v in values),
            "zero": sum(v == 0 for v in values), "sign_flip_assignments": len(flipped),
            "sign_flip_extreme": sum(abs(v) >= abs(mean) - tolerance for v in flipped),
            "sign_flip_min": min(flipped), "sign_flip_max": max(flipped),
            "bootstrap_draws": draws, "bootstrap_seed": 20261107,
            "bootstrap_95": [bootstrap[int(.025 * (draws - 1))], bootstrap[int(.975 * (draws - 1))]]}


def identity_receipt(text):
    lines = []
    for line in text.splitlines():
        if line.startswith(("run: ", "resumed: ")):
            break
        lines.append(line)
    fields = {}
    duplicates = []
    for line in lines:
        key, _, value = line.partition(" ")
        if key in fields:
            duplicates.append(key)
        fields[key] = value
    return lines, fields, duplicates


def registry_content(registry):
    """Reconstruct cohort content independently; run records do not spend a new cohort."""
    entries = []
    for entry in registry["entries"]:
        ignored = {"status", "held_run", "unused"}
        if entry.get("cohort") == "reserve":
            ignored.add("screen")
        entries.append({key: value for key, value in entry.items() if key not in ignored})
    content = {"restricted_ranges": registry.get("restricted_ranges"), "entries": entries}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def expand(items):
    seeds = set()
    for item in items:
        if type(item) is int:
            seeds.add(item)
        elif isinstance(item, list) and len(item) == 2 and all(type(x) is int for x in item) and item[0] <= item[1]:
            seeds.update(range(item[0], item[1] + 1))
        else:
            raise ValueError("malformed registry seed/range")
    return seeds


def reservation_errors(registry):
    errors = []
    for stratum, tag in (("template", "t"), ("procedural", "p")):
        entries = [e for e in registry["entries"] if e.get("stratum") == stratum]
        own = [e for e in entries if e.get("screen") == "CWR1" and e.get("cohort") == "held"]
        registered = set().union(*(expand(e["seeds"]) for e in own))
        expected = set(SEEDS["held"][tag])
        if registered != expected:
            errors.append(f"{stratum}: CWR1 reservation differs from fixed held cohort")
        restricted = expand(registry["restricted_ranges"].get(stratum, [])) | expand(registry["restricted_ranges"].get("both", []))
        if restricted & expected:
            errors.append(f"{stratum}: held cohort collides with restricted ranges")
        for entry in entries:
            if entry not in own and expand(entry["seeds"]) & expected:
                errors.append(f"{stratum}: held seed collision with {entry.get('id')}")
        pilot = SEEDS["pilot"][tag][0]
        if not any(e.get("cohort") == "pilot" and e.get("screen") in (None, "CWR1")
                   and e.get("status") == "reserved" and pilot in expand(e["seeds"]) for e in entries):
            errors.append(f"{stratum}: timing pilot is not registered as shared")
    return errors


def validate_rows(rows, cohort, identity):
    errors, invalid, statuses = [], set(), []
    expected = {(arm, tag, seed) for arm in ARMS for tag, seeds in SEEDS[cohort].items() for seed in seeds}
    usable = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or any(type(row.get(k)) is not t for k, t in
                                            (("arm", str), ("stratum", str), ("seed", int))):
            errors.append(f"row {index}: malformed arm/stratum/seed object")
            continue
        usable.append(row)
    keys = [(r["arm"], r["stratum"], r["seed"]) for r in usable]
    counts = Counter(keys)
    by = {key: row for key, row in zip(keys, usable)}
    for key in sorted(expected | set(keys), key=str):
        status = "not_run" if not counts[key] else "duplicate" if counts[key] > 1 else "present"
        if key not in expected:
            status = "outside_cohort"
        if status != "present":
            errors.append(f"{key}: {status}")
            invalid.add(key)
        statuses.append({"arm": key[0], "stratum": key[1], "seed": key[2], "status": status})
    for key, row in by.items():
        before = len(errors)
        def check(condition, reason):
            if not condition:
                errors.append(f"{key}: {reason}")
        check(row.get("screen") == "CWR1" and row.get("cohort") == cohort, "screen/cohort differs")
        check(row.get("identity") == identity, "source identity digest differs")
        check(type(row.get("rc")) is int and row["rc"] == 0, f"failed rc={row.get('rc')}: {row.get('error')}")
        if row.get("rc") != 0 or key not in expected:
            invalid.add(key)
            continue
        m, harm = row.get("m"), row.get("harm")
        check(isinstance(m, dict) and isinstance(harm, dict), "metrics/harm missing")
        if not isinstance(m, dict) or not isinstance(harm, dict):
            invalid.add(key)
            continue
        arm, tag, seed = key
        check(m.get("turns") == HORIZON and m.get("regions") == {"t": 8, "p": 32}[tag]
              and m.get("seed") == seed, "requested horizon/region/seed differs")
        check(row.get("pk") == {}, "unexpected package receipt schema")
        for metric in ("wall_s", "extract_s"):
            check(number(row.get(metric)) and row[metric] >= 0, f"{metric} missing/nonfinite")
        activation = obj(row.get("activation"))
        check(activation == {"activated": None, "evidence": "root arm"} if arm == "RD" else
              activation.get("activated") is True and activation.get("evidence") ==
              "Every enrolled world enters; actual mechanism activation is reported separately",
              "unconditional enrollment label differs")
        schemas = obj(row.get("schemas"))
        check(schemas.get("bundle") == 6 and schemas.get("livelihoods") == [1], "bundle/container schemas differ")
        packages = obj(schemas.get("packages"))
        for package in ("adaptive_livelihoods", "public_health", "residence_ledger", "household_retail",
                        "war_consequences", "war_requisition", "wealth_accounting", "timber_orders"):
            check(packages.get(package) == [1], f"{package} schema differs")
        records = obj(schemas.get("records"))
        check(records.get("food_accounting") == records.get("regional_population") == [1], "physical observation schemas differ")
        for metric in ("food_shortfall", "epidemic_deaths", "world_epidemic_deaths", "person_turns",
                       "world_person_turns", "world_infectious_pt", "deaths", "all_migrations",
                       "unknown_migration_drivers", "native_food_produced", "native_food_consumed",
                       "public_relief_food", "retail_access_unknown_region_turns", "retail_deficit_observed"):
            check(number(m.get(metric)) and m[metric] >= 0, f"required {metric} missing/nonfinite/negative")
        check(number(m.get("person_turns")) and m["person_turns"] > 0, "person-turn denominator not positive")
        for metric in ("person_turns", "world_person_turns", "deaths", "all_migrations", "unknown_migration_drivers",
                       "retail_access_unknown_region_turns"):
            check(count(m.get(metric)), f"cardinality {metric} is not a nonnegative whole count")
        check(near(m.get("world_person_turns"), m.get("person_turns")), "native/health population denominators differ")
        check(near(m.get("epidemic_deaths"), m.get("world_epidemic_deaths")), "epidemic authority alias differs")
        for numerator, denominator, rate, scale in (
                ("food_shortfall", "person_turns", "food_shortfall_per_1000_pt", 1000),
                ("epidemic_deaths", "person_turns", "epidemic_deaths_per_1000_pt", 1000),
                ("epidemic_deaths", "world_infectious_pt", "world_deaths_per_ipt", 1),
                ("deaths", "person_turns", "deaths_per_1000_pt", 1000)):
            n, d = m.get(numerator), m.get(denominator)
            if number(n) and number(d):
                check(near(m.get(rate), scale * n / d) if d > 0 else m.get(rate) is None,
                      f"{rate} denominator/undefined semantics differ")
        for cause in ("deaths_famine", "deaths_war"):
            h = obj(harm.get(cause))
            check(h.get("value") is None and h.get("state") == "requires_slice_extractor", f"{cause} unrecorded null lost")
        for label, metric in (("food_shortfall", "food_shortfall"), ("deaths_epidemic", "epidemic_deaths"),
                              ("out_migration", "all_migrations")):
            h = obj(harm.get(label))
            check(h.get("state") == "recorded" and near(h.get("value"), m.get(metric)), f"harm {label} authority differs")
        for hkey in ("population", "treasury", "priced_out_persons", "priced_out_children", "wealth_gini"):
            h = obj(harm.get(hkey))
            check(h.get("state") == "recorded" and number(h.get("value")), f"harm {hkey} absent")
        forest = obj(harm.get("forest_stand"))
        check((forest.get("state") == "recorded" and number(forest.get("value"))) or
              (forest.get("state") == "not_recorded" and forest.get("value") is None), "forest missing-vs-zero differs")
        side = obj(m.get("event_sidecar"))
        check(side.get("present") is True and near(side.get("migration"), m.get("all_migrations"))
              and near(side.get("unknown"), m.get("unknown_migration_drivers")) and near(side.get("deaths"), m.get("deaths")),
              "untruncated event authority differs")
        check(type(side.get("bytes")) is int and side["bytes"] > 0 and
              re.fullmatch(r"[0-9a-f]{64}", str(side.get("sha256"))) is not None, "event sidecar identity malformed")
        moves, unknown = m.get("all_migrations"), m.get("unknown_migration_drivers")
        if number(moves) and number(unknown):
            check(0 <= unknown <= moves and near(m.get("unknown_migration_share"), unknown / moves if moves else 0),
                  "unknown migration attribution ratio differs")
        mode, channel, crowding, _health, retail = ARMS[arm]
        for metric in ("a6_personal_rows", "d3_input_rows", "a6_offer_declines", "a6_information_turns",
                       "trade_unknown_destination", "trade_personal_return_refusal", "added_crowding_factor_sum",
                       "combined_migration_input_rows", "combined_native_choice_changes", "retail_free_rations_observed",
                       "retail_free_pool_observed", "retail_priority_household_turns", "retail_free_to_priority_observed"):
            check(number(m.get(metric)) and m[metric] >= 0, f"activation diagnostic {metric} missing")
        for metric in ("a6_personal_rows", "d3_input_rows", "a6_offer_declines", "a6_information_turns",
                       "trade_unknown_destination", "trade_personal_return_refusal", "combined_migration_input_rows",
                       "combined_native_choice_changes", "retail_priority_household_turns"):
            check(count(m.get(metric)), f"cardinality {metric} is not a nonnegative whole count")
        if mode == "record_only" or channel == "no_migration_experience":
            check(m.get("a6_personal_rows") == 0, "disabled personal migration input active")
        if mode == "record_only" or channel == "no_work":
            check(m.get("a6_offer_declines") == 0, "disabled personal work choice active")
        if mode == "record_only" or channel == "no_trade":
            check(m.get("trade_unknown_destination") == m.get("trade_personal_return_refusal") == 0,
                  "disabled personal trade choice active")
        check(m.get("a6_information_turns") == (0 if mode == "record_only" or channel == "no_information" else HORIZON),
              "migration information gate count differs")
        if crowding == "density_only":
            check(m.get("added_crowding_factor_sum") == 0, "density-only adds classified crowding")
        if retail == "no_relief":
            check(m.get("retail_priority_household_turns") == m.get("retail_free_to_priority_observed") == 0,
                  "no_relief retail means-test branch active")
            # Deliberately no free_given == 0 assertion: mode1 retains L2's free pool.
        missing_access = m.get("retail_access_unknown_region_turns")
        if number(missing_access):
            check(m.get("retail_access_deficit") is None if missing_access else
                  near(m.get("retail_access_deficit"), m.get("retail_deficit_observed")), "household access missing-vs-zero differs")
        nregions = m.get("regions")
        arrival = [m.get(k) for k in ("arrival_complete_region_turns", "arrival_incomplete_region_turns", "arrival_unknown_region_turns")]
        check(number(nregions) and all(count(x) for x in arrival) and sum(arrival) == nregions * HORIZON,
              "arrival coverage accounting differs")
        merge = [m.get(k) for k in ("merge_validated_turns", "merge_truncated_turns")]
        check(all(count(x) for x in merge) and sum(merge) == HORIZON, "bounded component validation accounting differs")
        if len(errors) != before:
            invalid.add(key)
    for row in statuses:
        key = row["arm"], row["stratum"], row["seed"]
        if row["status"] == "present":
            row["status"] = "failed" if by[key].get("rc") != 0 else "invalid" if key in invalid else "valid"
    return errors, invalid, statuses, by


def contrast(by, invalid, cohort, tag, metric, terms, draws):
    worlds, values = [], []
    for seed in SEEDS[cohort][tag]:
        levels, problems = {}, []
        for arm, _sign in terms:
            key = arm, tag, seed
            row = by.get(key)
            if row is None:
                problems.append(f"{arm}: not_run")
            elif key in invalid:
                problems.append(f"{arm}: failed_or_invalid")
            else:
                value = row["m"].get(metric)
                levels[arm] = value
                if value is None:
                    problems.append(f"{arm}: unknown_metric")
                elif not number(value):
                    problems.append(f"{arm}: malformed_metric")
        value = None if problems else sum(sign * levels[arm] for arm, sign in terms)
        worlds.append({"seed": seed, "levels": levels, "value": value, "problems": problems})
        if value is not None:
            values.append(value)
    complete = len(values) == len(SEEDS[cohort][tag])
    return {"metric": metric, "terms": list(terms), "stratum": tag, "worlds": worlds,
            "complete": complete, "summary": describe(values, draws) if complete else None,
            "summary_policy": "all enrolled paired worlds; aggregate withheld if any value unavailable"}


def audit(rows, source_text, cohort, expected_source, expected_native, checkout=None, protocol=None, draws=10000):
    lines, fields, duplicates = identity_receipt(source_text)
    identity = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    errors = [f"duplicate identity field: {key}" for key in duplicates]
    if fields.get("source") != expected_source:
        errors.append("recorded source differs from independently supplied expected source")
    if fields.get("dirty") != "0 tracked files" or fields.get("dirty-code") != "0 tracked code files":
        errors.append("recorded source was not clean")
    if fields.get("native", "").rsplit(" ", 1)[-1] != expected_native:
        errors.append("recorded native differs from independently supplied expected artifact")
    for key in ("chronicler", "interpreter", "runner", "screens", "registry", "registry-content"):
        if key not in fields:
            errors.append(f"missing source identity field: {key}")
    verification, ceiling = {}, None
    if checkout:
        for key, relative in (("runner", "scripts/screen_runner.py"), ("screens", "scripts/cw_rework_screen.py"),
                              ("registry", "scripts/seed_registry.json")):
            actual = sha(checkout / relative)
            verification[key] = {"sha256": actual, "path": relative}
            # Status/run records can change the full registry hash after mark-run.
            if key != "registry" and fields.get(key, "").split(" ")[0] != actual:
                errors.append(f"{key} source bytes differ from recorded source")
        reg = json.loads((checkout / "scripts/seed_registry.json").read_text())
        errors.extend(reservation_errors(reg))
        actual_content = registry_content(reg)
        verification["registry_content_sha256"] = actual_content
        if fields.get("registry-content", "").split(" ")[0] != actual_content:
            errors.append("registry cohort content differs from recorded source")
    if protocol:
        text = protocol.read_text()
        verification["protocol_sha256"] = sha(protocol)
        primary_line = re.search(r"^Primary outcomes:\s*(.+)$", text, re.M)
        if primary_line is None or {v.strip() for v in primary_line[1].split(",")} != set(PRIMARY):
            errors.append("protocol primary outcome declaration differs")
        cap_line = re.search(r"^Compute ceiling:\s*([0-9]+(?:\.[0-9]+)?)\s+core-hours\b", text, re.M)
        ceiling = float(cap_line[1]) if cap_line else None
        if ceiling is None or not math.isfinite(ceiling) or ceiling <= 0:
            errors.append("protocol has no valid positive compute ceiling")
        if cohort == "held":
            if not re.search(r"^Status:\s*FROZEN\b", text, re.M):
                errors.append("held protocol was not FROZEN")
            if fields.get("preregistration", "").split(" ")[0] != verification["protocol_sha256"]:
                errors.append("held preregistration source hash differs")
        elif "preregistration" in fields and fields["preregistration"].split(" ")[0] != verification["protocol_sha256"]:
            errors.append("optional pilot preregistration hash differs")
    elif cohort == "held":
        errors.append("held audit requires the frozen protocol file")
    row_errors, invalid, statuses, by = validate_rows(rows, cohort, identity)
    if errors:
        invalid.update(by)  # No effect summary from an unverified source identity.
        for entry in statuses:
            if entry["status"] == "valid":
                entry["status"] = "unverified_source"
    errors.extend(row_errors)
    primary, secondary, supporting = {}, {}, {}
    for tag in SEEDS[cohort]:
        for key, (metric, terms) in PRIMARY.items():
            primary[f"{key}:{tag}"] = contrast(by, invalid, cohort, tag, metric, terms, draws)
        for a, b in PAIRS:
            for metric in ("food_shortfall", "epidemic_deaths"):
                secondary[f"{a}-{b}:{metric}:{tag}"] = contrast(by, invalid, cohort, tag, metric, ((a, 1), (b, -1)), draws)
        for key, terms in INTERACTIONS.items():
            for metric in ("food_shortfall", "epidemic_deaths"):
                secondary[f"{key}_interaction:{metric}:{tag}"] = contrast(by, invalid, cohort, tag, metric, terms, draws)
        for metric in SUPPORTING:
            supporting[f"AD-RD:{metric}:{tag}"] = contrast(by, invalid, cohort, tag, metric, (("AD", 1), ("RD", -1)), draws)
    seconds = math.fsum(r.get("wall_s", 0) + r.get("extract_s", 0) for r in rows
                        if isinstance(r, dict) and number(r.get("wall_s")) and number(r.get("extract_s")))
    timing_valid = not errors
    budget = {"declared_cap_core_hours": ceiling, "projection_multiplier": 6 if cohort == "pilot" else 1,
              "fixed_margin": 1.5 if cohort == "pilot" else 1,
              "counted_seconds": seconds, "budget_pass": None}
    if timing_valid and ceiling is not None:
        budget["budget_pass"] = seconds / 3600 * budget["projection_multiplier"] * budget["fixed_margin"] <= ceiling
        if not budget["budget_pass"]:
            errors.append("measured/prospective run cost exceeds declared compute ceiling")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "cohort": cohort,
            "expected_rows": len(ARMS) * sum(map(len, SEEDS[cohort].values())), "observed_rows": len(rows),
            "identity": identity, "source": expected_source, "native_expected": expected_native,
            "source_verification": verification, "matrix": statuses,
            "declared_control_matrix": {arm: {"A6_rules": "3", "A6_mode": values[0], "A6_channels": values[1],
                "PH_crowding": values[2], "PH_mode": values[3], "retail_mode": values[4], "D3_mode": "active"}
                for arm, values in ARMS.items()},
            "simulation_and_extraction_seconds": seconds, "core_hours": seconds / 3600,
            "budget": budget,
            "pilot_held_projection_core_hours": seconds * 6 / 3600 if cohort == "pilot" and timing_valid else None,
            "pilot_held_projection_with_1_5_margin": seconds * 9 / 3600 if cohort == "pilot" and timing_valid else None,
            "primaries": primary, "secondary": secondary, "supporting": supporting,
            "scope": "Metric arithmetic and recorded identities/control implications only; no unseen per-turn frame or compiled-source verification; no simulation, no seed spending, no qualification, no activation conditioning."}


def check_primary_report(text, result):
    errors, checked = [], 0
    for key, record in result["primaries"].items():
        if not record["complete"]:
            continue
        outcome, tag = key.split(":")
        matches = [line.split("|")[1:-1] for line in text.splitlines()
                   if line.startswith(f"| {outcome}:") and len(line.split("|")) >= 7
                   and line.split("|")[2].strip() == tag]
        if len(matches) != 1:
            errors.append(f"report {key}: missing or duplicate primary table row")
            continue
        cells = [c.strip() for c in matches[0]][2:]
        d = record["summary"]
        expected = ["; ".join(f"{r['seed']}: {r['value']:+.4g}" for r in record["worlds"]),
                    f"{d['mean']:+.4g} [{d['min']:+.4g}, {d['max']:+.4g}]",
                    f"{d['positive']} / {d['negative']} / {d['zero']}",
                    f"{d['sign_flip_extreme']}/{d['sign_flip_assignments']} as extreme; means "
                    f"[{d['sign_flip_min']:+.4g}, {d['sign_flip_max']:+.4g}]"]
        if cells != expected:
            errors.append(f"report {key}: rendered primary arithmetic differs")
        checked += 1
    return errors, checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--cohort", choices=tuple(SEEDS), required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-native-sha", default=NATIVE)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("receipt path already exists; choose a new path to preserve prior evidence")
    path = args.directory / "metrics.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    result = audit(rows, (args.directory / "source.txt").read_text(), args.cohort, args.expected_source,
                   args.expected_native_sha, args.checkout, args.protocol)
    result["metrics_sha256"] = sha(path)
    report = args.directory / "report.md"
    result["report_sha256"] = sha(report) if report.exists() else None
    if report.exists():
        report_errors, checked = check_primary_report(report.read_text(), result)
        result["errors"].extend(report_errors)
        result["rendered_primary_rows_checked"] = checked
        if report_errors:
            result["status"] = "FAIL"
    else:
        result["errors"].append("report.md missing; rendered arithmetic was not checked")
        result["rendered_primary_rows_checked"] = 0
        result["status"] = "FAIL"
    result["checker_sha256"] = sha(Path(__file__))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "cohort", "expected_rows", "observed_rows", "identity", "errors")}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
