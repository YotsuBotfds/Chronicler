#!/usr/bin/env python3
"""Read closed first-world CWR1 artifacts independently; never run a simulation.

Only the frozen bundle codec is imported from Chronicler, solely to decode
history_delta. All contract arithmetic below is implemented here. Arrow is
read in full. Bounded frame samples are never presented as complete inputs.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

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
FIRST = {"p": 4201, "t": 4101}
FOOD_TERMS = ("opening", "produced", "transport_net", "craft_input", "clamp_correction",
              "pre_consumption", "consumed", "storage_loss", "cap_overflow", "closing")
OBSERVATIONS = ("person_turns", "deaths", "all_migrations", "a6_offer_declines", "a6_would_decline_offers",
                "a6_work_observed", "a6_work_unknown", "a6_personal_rows", "d3_input_rows", "a6_would_rows",
                "combined_migration_input_rows", "combined_native_choice_changes", "a6_information_turns",
                "native_migration_refusals", "dropped_a6_rows", "dropped_work_rows", "merge_validated_turns",
                "merge_truncated_turns", "recent_arrival_person_turns", "recent_arrival_unknown_reason_person_turns",
                "x1_displaced_person_turns", "arrival_complete_region_turns", "arrival_incomplete_region_turns",
                "arrival_unknown_region_turns", "added_crowding_factor_sum", "added_crowding_region_turns",
                "food_shortfall", "native_food_produced", "native_food_consumed", "native_food_demand",
                "public_relief_food", "retail_deficit_observed", "retail_priced_out_deficit_observed",
                "retail_offer_short_deficit_observed", "retail_free_rations_observed", "retail_free_pool_observed",
                "retail_priority_household_turns", "retail_free_to_priority_observed", "retail_rations_observed",
                "retail_person_turns_observed", "retail_observed_region_turns", "retail_access_unknown_region_turns",
                "epidemic_deaths", "world_infectious_pt")


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value):
    return type(value) is int and value >= 0


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def close(a, b, reason, tolerance=1e-7):
    require(number(a) and number(b) and math.isclose(a, b, rel_tol=1e-11, abs_tol=tolerance), reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def literal(checkout, relative, name):
    """Read enum/flow declarations as data; never import their modules."""
    for node in ast.parse((checkout / relative).read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    raise ValueError(f"declaration missing: {relative}:{name}")


def score_sample(frame, name, total_name, regions, *, merged=False, penalty=False):
    sample, total = frame.get(name), frame.get(total_name)
    require(integer(total) and isinstance(sample, list) and len(sample) == min(total, 256), f"{name}: capped sample/count")
    for row in sample:
        require(isinstance(row, list) and len(row) == 3 and integer(row[0]) and row[0] < 2**32
                and integer(row[1]) and row[1] < regions and number(row[2]) and abs(row[2]) <= .30000002,
                f"{name}: ID/destination/signed score")
        require(not penalty or row[2] <= 0, f"{name}: refusal penalty became positive")
    if merged:
        require(len({tuple(r[:2]) for r in sample}) == len(sample), "duplicate actual input ID/destination")
        require(sample == sorted(sample), "actual input order differs from ID/destination order")
    return sample, total


def verify_history(bundle, arm, flow_signs, *, horizon=120):
    mode, channel, crowding, health_mode, retail_mode = ARMS[arm]
    history = bundle["history"]
    regions = len(bundle["world_state"]["regions"])
    require([s["turn"] for s in history] == list(range(1, horizon + 1)), "completed history dates/horizon")
    out = Counter(dict.fromkeys(OBSERVATIONS, 0))
    prior = None
    coverage = []
    migrations = Counter()
    native_deaths = Counter()
    final_counters = {}
    for turn, snap in enumerate(history):
        lv = snap["livelihoods"]
        pop = snap["regional_population"]
        require(pop["source_turn"] == turn and len(pop["counts"]) == regions
                and all(integer(n) for n in pop["counts"]), "dated native population")
        out["person_turns"] += sum(pop["counts"])
        wealth = lv["wealth_accounting"]
        require(wealth["source_turn"] == wealth["frame"]["turn"] == turn, "native death observation date")
        count = wealth["frame"]["world"]["deaths"]
        require(integer(count), "native death count")
        native_deaths[turn] = count
        out["deaths"] += count
        for row in snap["migration"]:
            require(isinstance(row, list) and len(row) == 3 and all(integer(x) for x in row)
                    and row[0] < regions and row[1] < regions and row[0] != row[1] and row[2] > 0,
                    "dated migration flow")
            migrations[(turn, row[0], row[1])] += row[2]
            out["all_migrations"] += row[2]
        war = lv["war_consequences"]
        require(war["source_turn"] == turn and war["mode"] == "active", "D3 control/date")
        state = lv["adaptive_livelihoods"]
        frame = state["frame"]
        require(state["schema_version"] == 1 and state["source_turn"] == frame["turn"] == turn
                and state["rules"] == "3" and state["mode"] == mode
                and state["decision_channels"] == frame["decision_channels"] == channel,
                "rules-3 control/frame date")
        actual, na = score_sample(frame, "rows", "rows_total", regions, merged=True)
        personal, np = score_sample(frame, "a6_rows", "a6_rows_total", regions, penalty=True)
        d3, nd = score_sample(frame, "d3_rows", "d3_rows_total", regions)
        _would, nw = score_sample(frame, "migration_rows_would", "migration_rows_would_total", regions, penalty=True)
        require(frame["rows_installed"] == na and frame["rows_dropped"] == max(0, na - 256), "actual input count closure")
        require(not (mode == "record_only" or channel == "no_migration_experience") or np == 0,
                "disabled personal migration inputs")
        if np <= 256 and nd <= 256:
            merged = defaultdict(float)
            for aid, destination, value in personal + d3:
                merged[(aid, destination)] += value
            expected = [[aid, destination, max(-.3, min(.3, value))]
                        for (aid, destination), value in sorted(merged.items()) if value != 0]
            require(len(expected) == na and len(actual) == min(na, 256), "complete components/actual count differ")
            for observed, calculated in zip(actual, expected[:256]):
                require(observed[:2] == calculated[:2], "signed merge ID/destination differs")
                close(observed[2], calculated[2], "signed merge/clamp differs")
            out["merge_validated_turns"] += 1
        else:
            out["merge_truncated_turns"] += 1
        info_on = mode != "record_only" and channel != "no_information"
        require(frame["information_gate_installed"] is info_on, "actual information gate differs")
        masks, nm = frame["known_destinations"], frame["known_destinations_total"]
        require(integer(nm) and isinstance(masks, list) and len(masks) == min(nm, 256)
                and frame["known_destinations_dropped"] == max(0, nm - 256), "would-information cap/count")
        for aid, destination, mask in masks:
            require(integer(aid) and aid < 2**32 and integer(destination) and destination < regions
                    and type(mask) is int and 0 < mask <= 7, "would-information source-mask row")
        receipt = frame["receipt"]
        require(isinstance(receipt, list) and len(receipt) == 4 and receipt[0] == turn
                and integer(receipt[2]) and integer(receipt[3]), "native combined receipt/date")
        require(len(receipt[1]) == min(frame["refusals_total"], 256)
                and frame["refusals_dropped"] == max(0, frame["refusals_total"] - 256), "native refusal cap/count")
        for aid, origin, destination, gate in receipt[1]:
            require(integer(aid) and aid < 2**32 and integer(origin) and origin < regions
                    and integer(destination) and destination < regions and gate in (0, 1), "native refusal row")
        offers, work = frame["offers"], frame["work"]
        require(isinstance(offers, list) and isinstance(work, list), "work/offer observations absent")
        require(all(integer(frame[key]) for key in ("offers_dropped", "trade_dropped", "work_dropped")),
                "bounded observation drop counts absent")
        for offer in offers:
            require(offer["turn"] == turn and integer(offer["id"]) and type(offer["accepted"]) is bool
                    and type(offer["would_decline"]) is bool, "work offer date/identity/observation")
            require(not (mode == "record_only" or channel == "no_work") or offer["accepted"] is True,
                    "disabled personal work offer decline")
            out["a6_offer_declines"] += not offer["accepted"]
            out["a6_would_decline_offers"] += offer["would_decline"]
        for row in work:
            require(row["turn"] == turn and integer(row["id"]), "personal work date/ID")
            parts = [row.get(k) for k in ("paid_milli", "withheld_milli", "title_forgone_milli")]
            require(all(x is None or integer(x) for x in parts), "work cost observations malformed")
            if all(x is not None for x in parts):
                require(row.get("net_milli") == parts[0] - parts[1] - parts[2], "personal work net arithmetic")
                out["a6_work_observed"] += 1
            else:
                require(row.get("net_milli") is None, "missing personal work cost became zero/known")
                out["a6_work_unknown"] += 1
        out["a6_personal_rows"] += np
        out["d3_input_rows"] += nd
        out["a6_would_rows"] += nw
        out["combined_migration_input_rows"] += na
        out["combined_native_choice_changes"] += receipt[3]
        out["a6_information_turns"] += info_on
        out["native_migration_refusals"] += frame["refusals_total"]
        out["dropped_a6_rows"] += max(0, na - 256)
        out["dropped_work_rows"] += frame["work_dropped"]
        out["offers_capped_observations_unseen"] += frame["offers_dropped"]
        out["trade_capped_observations_unseen"] += frame["trade_dropped"]
        final_counters = state["counters"]

        ledger = lv["residence_ledger"]
        x1 = ledger["frame"]
        require(ledger["source_turn"] == x1["turn"] == turn, "X1 source/frame date")
        diagnostics = x1["arrival_diagnostics"]
        require(diagnostics["window_turns"] == 20 and all(type(diagnostics[k]) is bool for k in
                ("coverage_complete", "window_complete", "complete")), "X1 arrival diagnostic contract")
        coverage.append(diagnostics["coverage_complete"])
        window = len(coverage) >= 20 and all(coverage[-20:])
        require(diagnostics["window_complete"] is window and diagnostics["complete"] is
                (window and diagnostics["coverage_complete"]), "rolling20 fully covered writes")
        rows = x1["regions"]
        require(isinstance(rows, list) and len({r["region"] for r in rows}) == len(rows), "X1 duplicate region")
        totals = x1["totals"]
        for row in rows:
            require(integer(row["region"]) and row["region"] < regions
                    and all(integer(row[k]) for k in ("residents", "displaced", "recent_residence_arrivals",
                                                       "recent_residence_arrivals_unknown_reason")), "X1 region/count schema")
            require(0 <= row["displaced"] <= row["residents"] and
                    0 <= row["recent_residence_arrivals_unknown_reason"] <= row["recent_residence_arrivals"] <= row["residents"],
                    "X1 observed-count bounds/double-count guard")
        require(sum(r["residents"] for r in rows) == totals["observed"] and
                sum(r["displaced"] for r in rows) == totals["displaced"], "X1 residence/displacement count closure")
        require(integer(totals["alive"]) and integer(totals["observed"]) and integer(totals["deferred"])
                and totals["observed"] + totals["deferred"] <= totals["alive"], "X1 observed/deferred bounds")
        if diagnostics["coverage_complete"]:
            require(totals["observed"] == totals["alive"] and totals["deferred"] == 0, "X1 complete coverage contradicts counts")
        for key, metric in (("recent_residence_arrivals", "recent_arrival_person_turns"),
                            ("recent_residence_arrivals_unknown_reason", "recent_arrival_unknown_reason_person_turns")):
            require(integer(totals[key]) and sum(r[key] for r in rows) == totals[key], "X1 region/world count closure")
            out[metric] += totals[key]
        out["x1_displaced_person_turns"] += totals["displaced"]
        ph = lv["public_health"]
        require(ph["source_turn"] == ph["environment_turn"] == turn and ph["crowding"] == crowding
                and ph["mode"] == health_mode, "PH control/environment date")
        environment = ph["environment"]
        require(len(environment) == regions and {r["region"] for r in environment} == set(range(regions)), "PH region coverage")
        prior_rows = {r["region"]: r for r in prior["regions"]} if prior is not None else {}
        complete = prior["arrival_diagnostics"]["complete"] if prior is not None else None
        for row in environment:
            older = prior_rows.get(row["region"], {})
            require(row["source_turn"] == turn - 1 and row["residence_observed"] is (prior is not None), "PH factual T-1 provenance")
            require(row["crowding_basis"] == crowding and row["crowding_source_turn"] ==
                    (turn if crowding == "density_only" else turn - 1), "PH configuration/frame provenance")
            displaced = min(1, max(0, older.get("displaced", 0) / max(1, older.get("residents", 0))))
            close(row["displaced_share"], displaced, "classified T-1 share")
            factor = 1 if crowding == "density_only" else 1 + .25 * displaced
            close(row["crowding_factor"], factor, "density/legacy susceptibility input")
            require(row["arrival_diagnostics_complete"] is complete, "PH prior arrival completeness")
            if complete is True:
                share = older.get("recent_residence_arrivals", 0) / max(1, older.get("residents", 0))
                close(row["recent_arrival_share"], share, "PH prior complete arrival share")
            else:
                require(row["recent_arrival_share"] is None, "incomplete arrival ratio became zero/known")
            require(number(row["water_service"]) and 0 <= row["water_service"] <= 1, "sanitation observation range")
            close(row["flux_factor"], 1 if health_mode == "cost_only" else 1 - .2 * row["water_service"], "sanitation effect/control")
            out["arrival_complete_region_turns" if complete is True else "arrival_incomplete_region_turns" if complete is False else
                "arrival_unknown_region_turns"] += 1
            out["added_crowding_factor_sum"] += factor - 1
            out["added_crowding_region_turns"] += factor > 1
        prior = x1

        food = snap["food_accounting"]
        require(food["source_turn"] == turn and len(food["regions"]) == regions, "food date/complete regions")
        food_rows = {}
        for rid, row in enumerate(food["regions"]):
            require(row["region_id"] == rid and integer(row.get("native_count")), "food region/native count")
            native = row["native"]
            require(all(number(native.get(k)) for k in FOOD_TERMS + ("demand", "sufficiency")), "native food ledger schema")
            require(all(native[k] >= 0 for k in FOOD_TERMS + ("demand", "sufficiency") if k not in
                        ("transport_net", "clamp_correction")), "negative native stock/withdrawal")
            terms = [native["opening"], native["produced"], native["transport_net"], -native["craft_input"],
                     native["clamp_correction"], -native["consumed"], -native["storage_loss"], -native["cap_overflow"]]
            residual = native["closing"] - math.fsum(terms)
            tolerance = 1e-5 * max(1, math.fsum(abs(x) for x in terms))
            require(abs(residual) <= tolerance, "native food stock flow closure")
            close(native["balance_residual"], residual, "native declared residual", 1e-10)
            close(native["balance_tolerance"], tolerance, "native declared tolerance", 1e-10)
            public = row["public"]
            require(isinstance(public, dict) and number(public["released"]) and public["released"] >= 0, "public release unknown/invalid")
            if public["opening"] is None:
                require(public["balance_residual"] is None, "unknown public opening treated as closure")
                out["public_opening_unknown_region_turns"] += 1
            else:
                delta = public["after_open"] - math.fsum([public["opening"], -public["released"], -public["spoiled"], -public["abandoned"]])
                close(public["balance_residual"], delta, "public declared residual")
                close(delta, 0, "public pre-procurement local stock closure", 1e-5 * max(1, public["opening"]))
            sufficiency = row["sufficiency_after_relief"]
            require(number(sufficiency) and sufficiency >= 0, "availability observation absent")
            out["food_shortfall"] += native["demand"] * max(0, 1 - min(1, sufficiency))
            out["native_food_produced"] += native["produced"]
            out["native_food_consumed"] += native["consumed"]
            out["native_food_demand"] += native["demand"]
            out["public_relief_food"] += public["released"]
            food_rows[rid] = row
        retail = lv["household_retail"]
        require(retail["source_turn"] == turn and retail["mode"] == retail_mode and retail["boundary"] == "all"
                and retail["rules_version"] == 2 and retail["parameters"]["theta"] == (1 if retail_mode == "no_relief" else .9),
                "retail food ownership/allocation control")
        seen, enrolled = set(), set()
        for row in retail["regions"]:
            rid = row["region"]
            require(integer(rid) and rid < regions and rid not in enrolled, "retail region identity")
            enrolled.add(rid)
            seen.add(rid)
            flows = row["flows"]
            require(all(key in flow_signs and integer(value) for key, value in flows.items()), "retail flow schema")
            require(integer(row["open_milli"]) and integer(row["close_milli"]) and row["open_milli"] +
                    sum(flow_signs[k] * value for k, value in flows.items()) == row["close_milli"], "owned food local stock closure")
            provision = row.get("provisioning")
            if provision is None:
                seen.remove(rid)  # Region exists, its household access was not observed.
                continue
            require(provision["region"] == rid and number(provision["mode"]) and
                    provision["mode"] == (1 if retail_mode == "no_relief" else 0), "native retail mode/identity")
            for name, metric in (("deficit", "retail_deficit_observed"), ("priced_out_deficit", "retail_priced_out_deficit_observed"),
                                 ("offer_short_deficit", "retail_offer_short_deficit_observed"), ("free_given", "retail_free_rations_observed"),
                                 ("free_rations", "retail_free_pool_observed"), ("priority_households", "retail_priority_household_turns"),
                                 ("free_to_priority", "retail_free_to_priority_observed"), ("rations", "retail_rations_observed"),
                                 ("persons", "retail_person_turns_observed")):
                require(number(provision[name]) and provision[name] >= 0, f"retail {name} observation")
                out[metric] += provision[name]
            ration = provision["milli_food_per_ration"]
            require(number(ration) and ration > 0, "retail ration unit")
            close(provision["free_given"] + provision["free_unallocated"], provision["free_rations"], "free pool closure", 1e-4)
            close(provision["own_eaten_milli"] + provision["sold_milli"] + provision["unsold_milli"], provision["offered_milli"], "owned food disposition")
            close(provision["rations"], provision["free_given"] + (provision["own_eaten_milli"] + provision["sold_milli"]) / ration,
                  "household ration composition", 1e-4 * max(1, provision["persons"]))
            close(provision["paid_milli"], provision["credited_milli"] + provision["refunded_milli"], "local retail transaction closure")
            if retail_mode == "no_relief":
                require(provision["priority_households"] == provision["free_to_priority"] == 0, "no_relief retail means test active")
            out["retail_observed_region_turns"] += 1
        out["retail_access_unknown_region_turns"] += sum(rid not in seen and row["native_count"] > 0 for rid, row in food_rows.items())
        epi = snap["epidemics"]
        require(number(epi["deaths"]) and epi["deaths"] >= 0, "epidemic authority absent")
        out["epidemic_deaths"] += epi["deaths"]
        close(epi["deaths_total"], out["epidemic_deaths"], "cumulative epidemic authority")
        care = lv["epidemic_care"]
        tick = care["tick"]
        require(care["source_turn"] == tick["turn"] == turn and care["mode"] ==
                ("cost_only" if health_mode == "cost_only" else "care"), "care date/control")
        close(sum(row["deaths"] for row in tick["regions"]), epi["deaths"], "care tick/epidemic authority")
        out["world_infectious_pt"] += sum(row["infectious_pt"] for row in tick["regions"])
        for row in tick["regions"]:
            close(sum(x[1] for x in row["pathogens"]), row["deaths"], "per-pathogen diagnostic death closure")
            close(sum(x[2] for x in row["pathogens"]), row["infectious_pt"], "per-pathogen diagnostic infectious-time closure",
                  1e-6 * max(1, row["infectious_pt"]))
        for row in tick["applied"]:
            require(row["source_turn"] == turn - 1 and 0 <= row["coverage"] <= 1, "care prior capacity provenance")
            require(health_mode != "cost_only" or row["care_factor"] == 1, "cost-only care benefit applied")
    for name in ("trade_unknown_destination", "trade_personal_return_refusal"):
        value = final_counters.get(name, 0)
        require(integer(value) and not ((mode == "record_only" or channel == "no_trade") and value), "disabled trade gate counter")
        out[name] = value
    out["retail_access_deficit"] = out["retail_deficit_observed"] if out["retail_access_unknown_region_turns"] == 0 else None
    return dict(out), migrations, native_deaths


def verify_arrow(columns, types, drivers, regions, migrations, native_deaths):
    count = len(columns["turn"])
    require(all(len(values) == count for values in columns.values()), "Arrow equal column lengths")
    deaths, births, first_event = {}, {}, {}
    flows = Counter()
    by_turn_deaths = Counter()
    kinds = Counter()
    unknown = 0
    for turn, aid, kind, origin, target, driver in zip(*(columns[k] for k in
            ("turn", "agent_id", "event_type", "region", "target_region", "migration_driver"))):
        require(integer(turn) and 0 <= turn < 120 and integer(aid) and aid < 2**32, "Arrow stable ID/source date")
        require(kind in types and integer(origin) and origin < regions, "Arrow declared event enum/origin")
        require(type(driver) is int and (0 <= driver < len(drivers) or driver == 255), "Arrow declared driver enum")
        require(kind == "migration" or driver == 255, "non-migration event fabricated a move reason")
        first_event[aid] = min(first_event.get(aid, turn), turn)
        kinds[kind] += 1
        if kind == "migration":
            require(integer(target) and target < regions and origin != target, "Arrow applied migration route")
            flows[(turn, origin, target)] += 1
            unknown += driver == 255
        elif kind == "death":
            require(aid not in deaths, "stable ID died twice/reused")
            deaths[aid] = turn
            by_turn_deaths[turn] += 1
        elif kind == "birth":
            require(aid not in births, "stable birth ID reused")
            births[aid] = turn
    require(flows == migrations, "Arrow migration per-turn origin/destination flows differ")
    require(by_turn_deaths == +native_deaths, "Arrow/native death per-turn authority differs")
    require(all(first_event[aid] >= turn for aid, turn in births.items()), "event actor precedes its recorded birth ID")
    require(all(aid not in deaths or deaths[aid] >= turn for aid, turn in births.items()), "death precedes recorded birth ID")
    require(all(turn <= deaths.get(aid, turn) for turn, aid in zip(columns["turn"], columns["agent_id"])),
            "event actor continues after its stable ID died")
    return {"events": count, "kinds": dict(kinds), "migration": kinds["migration"], "unknown": unknown,
            "deaths": kinds["death"], "distinct_birth_ids": len(births), "distinct_death_ids": len(deaths),
            "identity_scope": "Event-level stable-ID chronology only; target references and all living IDs are not a complete household registry."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--stratum", choices=tuple(FIRST), required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--previous-receipt", type=Path, action="append", default=[])
    args = parser.parse_args()
    require(not args.receipt.exists(), "receipt exists; preserve it")
    previous_cpu = 0
    for path in args.previous_receipt:
        previous = json.loads(path.read_text())
        previous_cpu += previous.get("cpu_user_seconds", 0) + previous.get("cpu_system_seconds", 0)
    remaining = math.floor(120 - previous_cpu)
    require(remaining > 1, "120CPU-second cumulative raw-review budget exhausted")
    resource.setrlimit(resource.RLIMIT_CPU, (remaining, remaining + 1))
    signal.signal(signal.SIGXCPU, lambda _sig, _frame: (_ for _ in ()).throw(RuntimeError("CPU review budget exhausted")))
    start = time.perf_counter()
    before = resource.getrusage(resource.RUSAGE_SELF)
    require(subprocess.check_output(["git", "-C", str(args.checkout), "rev-parse", "HEAD"], text=True).strip() == args.expected_source,
            "frozen checkout source differs")
    sys.path.insert(0, str(args.checkout / "src"))
    from chronicler.bundle_codec import load_bundle
    import chronicler.bundle_codec as codec
    import pyarrow as pa
    import pyarrow.ipc as ipc
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    require(Path(codec.__file__).resolve() == (args.checkout / "src/chronicler/bundle_codec.py").resolve(), "decoder from wrong checkout")
    require(not any(k.startswith("chronicler_agents") for k in sys.modules), "native import before raw read")
    types = set(literal(args.checkout, "src/chronicler/agent_bridge.py", "EVENT_TYPE_MAP").values())
    drivers = literal(args.checkout, "src/chronicler/models.py", "MIGRATION_DRIVER_NAMES")
    flow_signs = literal(args.checkout, "src/chronicler/household_retail_state.py", "FLOW_SIGNS")
    rows = [json.loads(s) for s in (args.directory / "metrics.jsonl").read_text().splitlines() if s]
    lookup = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    seed = FIRST[args.stratum]
    require(all((arm, args.stratum, seed) in lookup and lookup[(arm, args.stratum, seed)]["rc"] == 0 for arm in ARMS),
            "all12 first-world cases must be closed and strict-pass before batch")
    results = []
    def receipt():
        after = resource.getrusage(resource.RUSAGE_SELF)
        modules = sorted(k for k in sys.modules if k == "chronicler" or k.startswith("chronicler."))
        return {"status": "PASS" if len(results) == 12 and all(r["status"] == "PASS" for r in results) else "FAIL",
                "source": args.expected_source, "stratum": args.stratum, "seed": seed,
                "raw_readbacks": results, "available_closed_rows": len(rows), "cpu_budget_total_seconds": 120,
                "previous_cpu_seconds": previous_cpu, "wall_seconds": time.perf_counter() - start,
                "cpu_user_seconds": after.ru_utime - before.ru_utime, "cpu_system_seconds": after.ru_stime - before.ru_stime,
                "max_single_process_rss_kib": after.ru_maxrss,
                "imported_chronicler_modules": modules, "native_module_imported": any(k.startswith("chronicler_agents") for k in sys.modules),
                "checker_sha256": sha(Path(__file__)), "codec_sha256": sha(args.checkout / "src/chronicler/bundle_codec.py"),
                "no_simulation": True, "no_partial_cohort_effect_claim": True,
                "scope": "Raw artifact/closed-metric readback only. Capped native inputs remain unseen. X1 exports counts, not complete per-ID residence rows; unique-arrival provenance relies on the reviewed writer. No inferred births, motives, housing, global cash conservation, or cause-specific famine/war mortality."}
    for arm in ARMS:
        row = lookup[(arm, args.stratum, seed)]
        path = args.directory / "runs" / f"{arm}-{args.stratum}{seed}" / "chronicle_bundle.json"
        result = {"arm": arm, "stratum": args.stratum, "seed": seed}
        try:
            bundle = load_bundle(path)
            require(bundle["metadata"]["seed"] == bundle["world_state"]["seed"] == seed and
                    bundle["metadata"]["total_turns"] == 120, "bundle/world identity/horizon")
            require(len(bundle["world_state"]["regions"]) == (32 if args.stratum == "p" else 8), "declared region scale")
            raw, migrations, native_deaths = verify_history(bundle, arm, flow_signs)
            metric = row["m"]
            require(all(key in metric for key in (*OBSERVATIONS, "retail_access_deficit",
                    "trade_unknown_destination", "trade_personal_return_refusal")), "required retained metric absent")
            comparisons = [key for key in raw if key in metric]
            for key in comparisons:
                if raw[key] is None:
                    require(metric[key] is None, f"{key}: unknown raw observation became known")
                else:
                    close(raw[key], metric[key], f"raw metric differs: {key}")
            for name in ("deaths_famine", "deaths_war"):
                require(row["harm"][name]["value"] is None and row["harm"][name]["state"] == "requires_slice_extractor", "unrecorded cause became zero")
            arrow_path = path.with_name("agent_events.arrow")
            table = ipc.open_file(arrow_path).read_all()
            columns = {k: table[k].to_pylist() for k in ("turn", "agent_id", "event_type", "region", "target_region", "migration_driver")}
            arrow = verify_arrow(columns, types, drivers, len(bundle["world_state"]["regions"]), migrations, native_deaths)
            digest = sha(arrow_path)
            require(digest == metric["event_sidecar"]["sha256"] and arrow_path.stat().st_size == metric["event_sidecar"]["bytes"], "Arrow byte identity")
            require(arrow["migration"] == metric["all_migrations"] and arrow["unknown"] == metric["unknown_migration_drivers"]
                    and arrow["deaths"] == metric["deaths"], "Arrow whole counts/metrics")
            require(not any(k.startswith("chronicler_agents") for k in sys.modules), "native module imported")
            result.update(status="PASS", metric_identity=row["identity"], snapshots=120,
                          bundle_sha256=sha(path), bundle_bytes=path.stat().st_size,
                          raw_observations=raw, metrics_compared=comparisons, arrow=arrow, arrow_sha256=digest)
            del bundle, table, columns
        except Exception as error:
            result.update(status="FAIL", error=f"{type(error).__name__}: {error}")
        results.append(result)
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt(), indent=2, allow_nan=False) + "\n")
        print(arm, args.stratum, seed, result["status"], result.get("error", ""), flush=True)
    final = receipt()
    require(final["imported_chronicler_modules"] == ["chronicler", "chronicler.bundle_codec"] and
            final["native_module_imported"] is False, "unexpected Chronicler/native imports")
    args.receipt.write_text(json.dumps(final, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: final[k] for k in ("status", "stratum", "cpu_user_seconds", "cpu_system_seconds", "wall_seconds")}))
    return 0 if final["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
