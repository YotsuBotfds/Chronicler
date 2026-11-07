"""Fresh CWR1 bounded causal controls; old CW6 source and results stay frozen.

All enrolled worlds enter comparisons. The old physical/health validation logic
is retained here with explicitly new rules-3 and crowding contracts; no old
record-only control assumptions are applied to the new native score input.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from functools import partial
import math
from pathlib import Path
import random
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen_runner as SR
import cw_integrated_screen as CW6

MODULE = Path(__file__).resolve()
PREREG = SR.REPO / "docs/superpowers/progress/connected-world-rework-prereg-draft.md"
PATHOGENS = ("plague", "pox", "fever", "flux", "pestilence")
HORIZON = 120
BASE = list(CW6.BASE)
BASE[BASE.index("--adaptive-livelihoods-rules") + 1] = "3"
BASE = tuple(BASE)
CHANNELS = ("all", "no_migration_experience", "no_information", "no_work", "no_trade")


def option(flags, key, default):
    value = default
    for i, flag in enumerate(flags):
        if flag == key:
            if i + 1 == len(flags):
                raise ValueError(f"{key} has no value")
            value = flags[i + 1]
        elif flag.startswith(key + "="):
            value = flag.split("=", 1)[1]
    return value


_option = option


def arm_flags(mode="adapt", crowding="density_only", channels="all", health="active", retail="retail"):
    return (*CW6.arm_flags(a6=mode), "--adaptive-livelihoods-decision-channels", channels,
            "--public-health-crowding", crowding, "--public-health-mode", health,
            "--household-retail-mode", retail)


ARMS = {
    "RD": (arm_flags(mode="record_only"), None),
    "AD": (arm_flags(), "RD"),
    "RL": (arm_flags(mode="record_only", crowding="legacy_displacement"), "RD"),
    "AL": (arm_flags(crowding="legacy_displacement"), "RL"),
    "MX": (arm_flags(channels="no_migration_experience"), "AD"),
    "IX": (arm_flags(channels="no_information"), "AD"),
    "WX": (arm_flags(channels="no_work"), "AD"),
    "TX": (arm_flags(channels="no_trade"), "AD"),
    "RPC": (arm_flags(mode="record_only", health="cost_only"), "RD"),
    "APC": (arm_flags(health="cost_only"), "RPC"),
    "RNR": (arm_flags(mode="record_only", retail="no_relief"), "RD"),
    "ANR": (arm_flags(retail="no_relief"), "RNR"),
}

# Only the untruncated Arrow reader is reused. No old A6 control extractor runs.
_load_bundle_file = SR.load_bundle_file


def load_bundle_file(path):
    bundle = _load_bundle_file(path)
    bundle["_cw6_events"] = CW6.event_sidecar(Path(path).parent / "agent_events.arrow")
    match = re.fullmatch(r"([A-Z]+)-([pt])(\d+)", Path(path).parent.name)
    if match and match[1] in ARMS:
        bundle["_cwr_expected_world"] = {"arm": match[1], "stratum": match[2], "seed": int(match[3])}
    return bundle


# Adapted physical checks from the frozen CW6 extractor; its A6 block is absent.
def _physical(bundle, flags):
    from chronicler.wealth_accounting import record_status
    from chronicler.timber_orders import check_order
    from chronicler.timber_orders_state import TimberOrder
    from chronicler.reform_services import record_status as relief_status
    from chronicler.guild_leagues import record_status as league_status
    from chronicler.movement_branches import record_status as branch_status
    problems = []
    m = dict.fromkeys(("person_turns", "balance_change", "deaths", "income_gross", "income_applied", "wages_milli",
        "withheld_native", "wealth_close", "d3_wounded", "d3_released", "d3_evacuated",
        "d3_returned", "separation_person_pairs", "injury_episode_turns", "new_occupational_injuries",
        "battle_deaths", "army_consumed", "army_demand", "army_hunger_ration_turns", "army_consumption_rows",
        "requisition_milli", "army_supply_food_milli", "destroyed_food_milli", "restitution_paid_milli",
        "claims_unrecorded_milli", "claims_unpaid_final_milli", "service_asset_turns", "asset_turns", "infra_work",
        "infra_timber_used", "infra_paid_milli", "timber_delivered_milli", "timber_carrier_paid_milli",
        "timber_orders", "cover_loss", "all_migrations", "x1_moves", "x1_other_moves", "x1_opened_spells",
        "x1_displaced_person_turns", "dropped_war_events",
        "branch_funded_turns", "branch_payer_turns", "branch_dues_milli", "branch_new_identity_refusals"), 0)
    hist = bundle.get("history")
    regions = SR._get(bundle, ("world_state", "regions"))
    if not isinstance(hist, list) or not hist or not isinstance(regions, list) or not regions:
        return {}, ["CW6 requires nonempty history and world_state.regions"]
    nregions = len(regions)
    seen, past_refused, order_seen = set(), set(), set()
    previous_close = None
    d3_mode = option(flags, "--war-consequences-mode", "active")
    d4_mode = option(flags, "--war-requisition-mode", "transfer")
    orders_on = "--timber-orders" in flags

    def finite(value, where, *, signed=False):
        if not SR._num(value) or (not signed and value < 0):
            problems.append(f"{where}: invalid finite {'signed ' if signed else 'nonnegative '}number")
            return 0
        return value

    def rows(obj, key, where):
        value = obj.get(key) if isinstance(obj, dict) else None
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            problems.append(f"{where}.{key}: missing or malformed rows")
            return []
        return value

    def dated(lv, name, turn, *, mode=None, frame=True):
        record = lv.get(name)
        if not isinstance(record, dict) or record.get("schema_version") != 1 or record.get("source_turn") != turn:
            problems.append(f"{name}: missing, malformed or misdated at {turn}")
            return {}
        if mode is not None and record.get("mode") != mode:
            problems.append(f"{name}: control mode differs at {turn}")
        if frame and (not isinstance(record.get("frame"), dict) or record["frame"].get("turn") != turn):
            problems.append(f"{name}: missing or misdated frame at {turn}")
        return record

    for snap in hist:
        if not isinstance(snap, dict) or type(snap.get("turn")) is not int or snap["turn"] < 1:
            problems.append("malformed completed snapshot turn")
            continue
        turn = snap["turn"] - 1
        if turn in seen:
            problems.append(f"duplicate completed turn {turn}")
        seen.add(turn)
        lv = snap.get("livelihoods") or {}
        population = snap.get("regional_population") or {}
        counts = population.get("counts")
        if population.get("source_turn") != turn or not isinstance(counts, list) or len(counts) != nregions:
            problems.append(f"regional population missing or misdated at {turn}")
        else:
            m["person_turns"] += sum(finite(v, "population") for v in counts)
        status, wealth = record_status(snap)
        if status != "observed":
            problems.append(f"wealth ledger {status} at {turn}")
        else:
            if lv["wealth_accounting"].get("source_turn") != turn or wealth.get("turn") != turn:
                problems.append(f"wealth frame/source misdated at {turn}")
            if wealth.get("typed_complete") is not True:
                problems.append(f"wealth typed coverage incomplete at {turn}")
            if turn > 0 and wealth.get("continuity", {}).get("status") != "exact":
                problems.append(f"wealth continuity is not exact at {turn}")
            world = wealth["world"]
            opening = finite(world.get("open"), "wealth open")
            closing = finite(world.get("close"), "wealth close")
            change = finite(world.get("delta"), "wealth delta", signed=True)
            if abs(closing - opening - change) > 1e-8 or (previous_close is not None and abs(opening - previous_close) > 1e-8):
                problems.append(f"wealth opening/closing balances do not close continuously at {turn}")
            previous_close = closing
            m["balance_change"] += change
            m["deaths"] += finite(world.get("deaths"), "wealth observed deaths")
            m["wealth_close"] = finite(world.get("close"), "wealth close")
            native = wealth.get("native") or {}
            if native.get("source_turn") != turn or native.get("observed_complete") is not True \
                    or abs(finite(native.get("balance_closure"), "wealth closure", signed=True)) > 1e-8:
                problems.append(f"native wealth stages incomplete or misdated at {turn}")
            totals = native.get("totals") or {}
            for key in ("income_gross", "income_applied"):
                m[key] += finite(totals.get(key, 0), key, signed=True)
            m["withheld_native"] += sum(finite(value, key, signed=True) for key, value in totals.items() if key.startswith("withheld_"))
            for row in rows(wealth, "typed", "wealth"):
                if row.get("channel", "").endswith("_wage") or row.get("channel") == "apprentice_stipend":
                    m["wages_milli"] += finite(row.get("in_milli"), "typed wage")
        d3 = dated(lv, "war_consequences", turn, mode=d3_mode)
        df = d3.get("frame") or {}
        m["dropped_war_events"] += finite(df.get("events_dropped"), "D3 dropped events")
        for event in rows(df, "events", "D3"):
            if event.get("turn") != turn:
                problems.append(f"D3 event misdated at {turn}")
        separation = df.get("separation")
        if separation is not None:
            if separation.get("source_turn") != turn - 1:
                problems.append(f"D3 separation not T-1 at {turn}")
            m["separation_person_pairs"] += finite(separation.get("separated_total"), "separation pairs")
        for key in ("wounded", "released", "evacuated", "returned"):
            m["d3_" + key] = finite(d3.get("counters", {}).get(key, 0), "D3 counter")
        health = snap.get("health_care") or {}
        if health.get("source_turn") != turn:
            problems.append(f"health care summary absent or misdated at {turn}")
        m["injury_episode_turns"] += finite(health.get("episodes"), "injury episodes")
        m["new_occupational_injuries"] += finite(health.get("new_injuries"), "new injuries")
        for battle in rows(snap.get("campaign"), "battles", "campaign"):
            if battle.get("turn") != turn:
                problems.append(f"battle misdated at {turn}")
            m["battle_deaths"] += finite(battle.get("attacker_losses"), "battle losses") + finite(battle.get("defender_losses"), "battle losses")
        d4 = dated(lv, "war_requisition", turn, mode=d4_mode)
        rf = d4.get("frame") or {}
        if rf.get("events_dropped") != 0:
            problems.append(f"D4 complete physical closure unavailable: dropped events at {turn}")
        consumption = set()
        for event in rows(rf, "events", "D4"):
            if event.get("source_turn") != turn:
                problems.append(f"D4 source date differs at {turn}")
            kind = event.get("kind")
            if kind == "consumption":
                consumed = finite(event.get("consumed_rations"), "army consumed")
                demand = finite(event.get("demanded_rations"), "army demand")
                if consumed > demand or event.get("army") in consumption:
                    problems.append(f"army duplicate or excess meal at {turn}")
                consumption.add(event.get("army"))
                expected = consumed / demand if demand else 0
                if abs(finite(event.get("adequacy"), "army adequacy") - expected) > 1e-8:
                    problems.append(f"army adequacy does not match actual consumption at {turn}")
                m["army_consumed"] += consumed
                m["army_demand"] += demand
                m["army_hunger_ration_turns"] += demand - consumed
                m["army_consumption_rows"] += 1
            elif kind in ("initial", "refill", "forage"):
                removed = finite(event.get("removed_milli"), "army supply food")
                credited = finite(event.get("credited_rations"), "army supply credit")
                if (d4_mode == "transfer" and removed != 500 * credited) or (d4_mode == "cost_only" and credited != 0):
                    problems.append(f"army supply source does not close at {turn}")
                m["army_supply_food_milli"] += removed
            elif kind in ("requisition", "cargo_seizure") and event.get("goods") != "timber":
                removed = finite(event.get("removed_milli"), "requisition removed")
                destroyed = finite(event.get("destroyed_milli"), "requisition destroyed")
                credited = sum(finite(row.get("rations"), "allocated kits") for row in rows(event, "allocations", "D4"))
                if kind == "requisition" and removed != sum(finite(event.get(key), "requisition source")
                        for key in ("commons_milli", "granary_milli", "owned_milli")):
                    problems.append(f"requisition source removal split does not close at {turn}")
                if removed != destroyed + 500 * credited or (d4_mode == "cost_only" and credited):
                    problems.append(f"requisition physical food does not close at {turn}")
                m["requisition_milli"] += removed
                m["destroyed_food_milli"] += destroyed
        m["claims_unpaid_final_milli"] = finite(rf.get("claims_due_milli"), "unpaid claims")
        for key in ("restitution_paid_milli", "claims_unrecorded_milli"):
            m[key] = finite(d4.get("counters", {}).get(key, 0), key)
        infra = dated(lv, "infrastructure_condition", turn, mode="repair", frame=False)
        for asset in rows(infra, "assets", "infrastructure"):
            if asset.get("status") in ("serving", "failed"):
                service = finite(asset.get("service"), "asset service")
                if service > 1:
                    problems.append(f"asset service exceeds one at {turn}")
                m["service_asset_turns"] += service
                m["asset_turns"] += 1
        for receipt in rows(infra, "receipts", "infrastructure"):
            if receipt.get("turn") != turn:
                problems.append(f"infrastructure receipt misdated at {turn}")
            m["infra_work"] += finite(receipt.get("delivered"), "infrastructure delivered work")
            m["infra_timber_used"] += finite(receipt.get("timber_used"), "infrastructure timber")
            m["infra_paid_milli"] += finite(receipt.get("coin_cost_milli"), "infrastructure paid")
        canopy = dated(lv, "harvest_cover", turn, mode="loss" if orders_on else "record_only", frame=False)
        for row in rows(canopy, "rows", "canopy"):
            loss = finite(row.get("loss"), "canopy loss")
            if not orders_on and loss != 0:
                problems.append(f"joint supply control applies canopy loss at {turn}")
            m["cover_loss"] += loss
        if orders_on:
            orders = dated(lv, "timber_orders", turn)
            for order in rows(orders, "orders", "timber") + rows(orders, "closed", "timber"):
                try:
                    check_order(TimberOrder.model_validate(order))
                except (ValueError, RuntimeError) as error:
                    problems.append(f"timber order does not validate at {turn}: {error}")
                if order.get("price_turn", turn) >= order.get("dispatched_turn", -1):
                    problems.append(f"timber purchase did not use a prior price at {turn}")
                order_seen.add(order.get("id"))
            counters = orders.get("counters") or {}
            m["timber_delivered_milli"] = finite(counters.get("delivered_milli", 0), "timber delivered")
            m["timber_carrier_paid_milli"] = finite(counters.get("carrier_credited_milli", 0), "timber freight")
        elif "timber_orders" in lv:
            problems.append(f"timber orders unexpectedly recorded in joint supply control at {turn}")
        for name, mode, reader in (("reform_services", "service", relief_status), ("guild_leagues", "mutual", league_status),
                                   ("movement_branches", "funded", branch_status)):
            dated(lv, name, turn, mode=mode)
            status, frame = reader(snap)
            if status not in ("recorded", "recorded_zero"):
                problems.append(f"{name} record {status} at {turn}")
            elif name == "movement_branches":
                m["branch_new_identity_refusals"] += finite(frame.get("new_identities_refused"), "branch identity refusals")
                for row in frame["rows"]:
                    m["branch_funded_turns"] += row["status"] == "funded"
                    m["branch_payer_turns"] += len(row["payers"])
                    m["branch_dues_milli"] += finite(row["dues_milli"], "branch dues")
        x1 = dated(lv, "residence_ledger", turn)
        xt = (x1.get("frame") or {}).get("totals") or {}
        for field, key in (("x1_moves", "moves"), ("x1_other_moves", "moves_other"),
                           ("x1_opened_spells", "opened"), ("x1_displaced_person_turns", "displaced")):
            m[field] += finite(xt.get(key), "X1 " + key)
        migration = snap.get("migration")
        if not isinstance(migration, list) or not all(isinstance(row, list) and len(row) == 3
                and all(type(v) is int for v in row) and 0 <= row[0] < nregions and 0 <= row[1] < nregions
                and row[0] != row[1] and row[2] > 0 for row in migration):
            problems.append(f"all-migration observation absent at {turn}")
        else:
            m["all_migrations"] += sum(finite(row[2], "migration count") for row in migration)
    if seen != set(range(len(hist))):
        problems.append("completed history must cover every turn from zero without gaps")
    m["timber_orders"] = len(order_seen)
    sidecar = bundle.get("_cw6_events")
    if not isinstance(sidecar, dict):
        problems.append("untruncated event sidecar measurement missing")
        sidecar = {}
    if sidecar.get("present") is not True or not isinstance(sidecar.get("sha256"), str) \
            or len(sidecar["sha256"]) != 64 or not SR._num(sidecar.get("bytes")) or sidecar["bytes"] <= 0:
        problems.append("untruncated event sidecar absent or missing valid identity")
    if sidecar.get("turn_min") is not None and (sidecar["turn_min"] < 0 or sidecar.get("turn_max", len(hist)) >= len(hist)):
        problems.append("untruncated event sidecar source turns outside observed history")
    if sidecar.get("migration") != m["all_migrations"]:
        problems.append("untruncated migration sidecar count differs from aggregate migration authority")
    if sidecar.get("deaths") != m["deaths"]:
        problems.append("untruncated death sidecar count differs from A1 native death observation")
    m["unknown_migration_drivers"] = finite(sidecar.get("unknown"), "unknown migration drivers")
    m["unknown_migration_share"] = m["unknown_migration_drivers"] / m["all_migrations"] if m["all_migrations"] else 0
    m["event_sidecar"] = sidecar
    m["balance_change_per_1000_pt"] = 1000 * m["balance_change"] / m["person_turns"] if m["person_turns"] else None
    m["deaths_per_1000_pt"] = 1000 * m["deaths"] / m["person_turns"] if m["person_turns"] else None
    m["service_per_region_turn"] = m["service_asset_turns"] / (nregions * len(hist))
    m["army_consumed_fraction"] = m["army_consumed"] / m["army_demand"] if m["army_demand"] else None
    m["turns"], m["regions"] = len(hist), nregions
    return m, problems


def _adaptive(bundle, flags):
    """Rules-3 input provenance, without claiming separate realized effects."""
    problems = []
    expected_mode = option(flags, "--adaptive-livelihoods-mode", "adapt")
    channels = option(flags, "--adaptive-livelihoods-decision-channels", "all")
    nregions = len(bundle.get("world_state", {}).get("regions", []))
    out = dict.fromkeys(("combined_migration_input_rows", "a6_personal_rows", "d3_input_rows", "a6_would_rows",
        "combined_native_choice_changes", "native_migration_refusals", "a6_work_observed", "a6_work_unknown", "a6_offer_declines",
        "a6_would_decline_offers", "a6_information_turns", "dropped_a6_rows", "dropped_work_rows",
        "merge_validated_turns", "merge_truncated_turns"), 0)
    personal_on = expected_mode != "record_only" and channels != "no_migration_experience"
    info_on = expected_mode != "record_only" and channels != "no_information"
    work_on = expected_mode != "record_only" and channels != "no_work"

    def count(value, label):
        if type(value) is not int or value < 0:
            problems.append(f"{label}: invalid nonnegative integer")
            return 0
        return value

    def scores(frame, key, total_key, turn, *, merged=False):
        rows, total = frame.get(key), frame.get(total_key)
        total = count(total, f"{key} total at {turn}")
        valid = isinstance(rows, list) and len(rows) == min(total, 256) and all(
            isinstance(r, (list, tuple)) and len(r) == 3 and type(r[0]) is int and r[0] >= 0
            and type(r[1]) is int and 0 <= r[1] < nregions and SR._num(r[2])
            and abs(r[2]) <= .30000002 for r in rows)
        if not valid:
            problems.append(f"{key}: malformed signed input sample/count at {turn}")
            return [], total
        if merged and len({(r[0], r[1]) for r in rows}) != len(rows):
            problems.append(f"actual merged native inputs duplicate a person/destination at {turn}")
        return rows, total

    last = {}
    for snap in bundle.get("history", []):
        turn = snap.get("turn", 0) - 1
        state = (snap.get("livelihoods") or {}).get("adaptive_livelihoods")
        if not isinstance(state, dict) or state.get("schema_version") != 1 \
                or state.get("source_turn") != turn or state.get("mode") != expected_mode \
                or state.get("rules") != "3" or state.get("decision_channels") != channels:
            problems.append(f"A6 rules-3/channel control missing or differs at {turn}")
            continue
        frame = state.get("frame")
        if not isinstance(frame, dict) or frame.get("turn") != turn or frame.get("decision_channels") != channels:
            problems.append(f"A6 frame/source/channel missing or differs at {turn}")
            continue
        actual, ntotal = scores(frame, "rows", "rows_total", turn, merged=True)
        personal, nown = scores(frame, "a6_rows", "a6_rows_total", turn)
        d3, nd3 = scores(frame, "d3_rows", "d3_rows_total", turn)
        _would, nwould = scores(frame, "migration_rows_would", "migration_rows_would_total", turn)
        if frame.get("rows_installed") != ntotal or frame.get("rows_dropped") != max(0, ntotal - 256):
            problems.append(f"A6 actual installed/sample counts do not close at {turn}")
        if not personal_on and nown:
            problems.append(f"disabled personal migration channel installs rows at {turn}")
        if nown <= 256 and nd3 <= 256:
            combined = defaultdict(float)
            for aid, target, score in [*personal, *d3]:
                combined[(aid, target)] += score
            combined = {key: max(-.3, min(.3, value)) for key, value in combined.items() if value != 0}
            if ntotal != len(combined) or any((aid, target) not in combined or
                    abs(score - combined[(aid, target)]) > 1e-7 for aid, target, score in actual):
                problems.append(f"actual native inputs differ from clamped personal plus D3 contributions at {turn}")
            out["merge_validated_turns"] += 1
        else:
            out["merge_truncated_turns"] += 1
        if frame.get("information_gate_installed") is not info_on:
            problems.append(f"A6 native migration-information control differs at {turn}")
        known = frame.get("known_destinations")
        known_total = count(frame.get("known_destinations_total"), f"known destinations at {turn}")
        if not isinstance(known, list) or len(known) != min(known_total, 256) or not all(
            isinstance(r, (list, tuple)) and len(r) == 3 and type(r[0]) is int and r[0] >= 0
            and type(r[1]) is int and 0 <= r[1] < nregions and type(r[2]) is int and 0 < r[2] <= 7 for r in known):
            problems.append(f"A6 migration-information diagnostic sample malformed at {turn}")
        if frame.get("known_destinations_dropped") != max(0, known_total - 256):
            problems.append(f"A6 migration-information diagnostic count does not close at {turn}")
        receipt = frame.get("receipt")
        if not isinstance(receipt, (list, tuple)) or len(receipt) != 4 or receipt[0] != turn \
                or not all(type(receipt[i]) is int and receipt[i] >= 0 for i in (2, 3)):
            problems.append(f"combined native migration receipt absent or misdated at {turn}")
        else:
            # R3 record_only can legitimately apply D3 scores. This is a
            # combined comparison, never a measured per-input causal effect.
            out["combined_native_choice_changes"] += receipt[3]
        offers, work = frame.get("offers"), frame.get("work")
        if not isinstance(offers, list) or not all(isinstance(r, dict) and r.get("turn") == turn
                and type(r.get("id")) is int and r["id"] >= 0 and isinstance(r.get("kind"), str)
                and type(r.get("would_decline")) is bool and type(r.get("accepted")) is bool for r in offers):
            problems.append(f"A6 offer observations malformed at {turn}")
            offers = []
        if not work_on and any(not r["accepted"] for r in offers):
            problems.append(f"disabled work channel declines an offer at {turn}")
        if not isinstance(work, list) or not all(isinstance(r, dict) for r in work):
            problems.append(f"A6 personal work observations missing at {turn}")
            work = []
        for row in work:
            components = [row.get(k) for k in ("paid_milli", "withheld_milli", "title_forgone_milli")]
            if row.get("turn") != turn or type(row.get("id")) is not int or row["id"] < 0 \
                    or not isinstance(row.get("kind"), str) or not row["kind"] \
                    or (row.get("progress") is not None and type(row.get("progress")) is not bool) \
                    or (row.get("source") is not None and not isinstance(row.get("source"), str)) \
                    or not all(v is None or type(v) is int and v >= 0 for v in components) \
                    or (row.get("net_milli") is not None and type(row["net_milli"]) is not int):
                problems.append(f"A6 work receipt malformed or misdated at {turn}")
            elif all(v is not None for v in components):
                if row.get("net_milli") != components[0] - components[1] - components[2]:
                    problems.append(f"A6 work net does not close at {turn}")
            elif row.get("net_milli") is not None:
                problems.append(f"A6 unknown personal cost treated as known at {turn}")
            out["a6_work_observed"] += row.get("net_milli") is not None
            out["a6_work_unknown"] += row.get("net_milli") is None
        out["combined_migration_input_rows"] += ntotal
        out["a6_personal_rows"] += nown
        out["d3_input_rows"] += nd3
        out["a6_would_rows"] += nwould
        out["a6_information_turns"] += info_on
        out["native_migration_refusals"] += count(frame.get("refusals_total"), f"native migration refusals at {turn}")
        out["dropped_a6_rows"] += max(0, ntotal - 256)
        out["dropped_work_rows"] += count(frame.get("work_dropped"), f"A6 work drops at {turn}")
        out["a6_offer_declines"] += sum(not r["accepted"] for r in offers)
        out["a6_would_decline_offers"] += sum(r["would_decline"] for r in offers)
        last = state.get("counters") or {}
    for key in ("trade_unknown_destination", "trade_personal_return_refusal"):
        value = count(last.get(key, 0), key)
        if (expected_mode == "record_only" or channels == "no_trade") and value:
            problems.append(f"disabled trade channel has active {key}")
        out[key] = value
    return out, problems


def _factual_and_food(bundle, flags):
    """Dated physical diagnostics and actual availability/access observations."""
    from chronicler.household_retail import THETA
    from chronicler.household_retail_state import FLOW_SIGNS
    from chronicler.food_accounting import FOOD_LEDGER_FIELDS
    problems = []
    nregions = len(bundle.get("world_state", {}).get("regions", []))
    crowding = option(flags, "--public-health-crowding", "density_only")
    retail_mode = option(flags, "--household-retail-mode", "retail")
    out = dict.fromkeys(("recent_arrival_person_turns", "recent_arrival_unknown_reason_person_turns",
        "arrival_complete_region_turns", "arrival_incomplete_region_turns", "arrival_unknown_region_turns",
        "added_crowding_region_turns", "added_crowding_factor_sum", "native_food_produced",
        "native_food_consumed", "native_food_demand", "public_relief_food", "retail_observed_region_turns",
        "retail_access_unknown_region_turns", "retail_deficit_observed", "retail_priced_out_deficit_observed",
        "retail_offer_short_deficit_observed", "retail_free_rations_observed", "retail_rations_observed",
        "retail_free_pool_observed", "retail_priority_household_turns", "retail_free_to_priority_observed",
        "retail_person_turns_observed", "retail_paid_milli", "retail_income_replaced"), 0)

    def amount(value, label, *, signed=False):
        if not SR._num(value) or (not signed and value < 0):
            problems.append(f"{label}: invalid finite number")
            return 0
        return value

    prior = None
    coverage_history = []
    for snap in bundle.get("history", []):
        turn = snap.get("turn", 0) - 1
        lv = snap.get("livelihoods") or {}
        x1 = lv.get("residence_ledger") or {}
        frame = x1.get("frame") or {}
        diagnostics = frame.get("arrival_diagnostics")
        if not isinstance(diagnostics, dict) or diagnostics.get("window_turns") != 20 \
                or not all(type(diagnostics.get(k)) is bool for k in ("coverage_complete", "window_complete", "complete")):
            problems.append(f"X1 factual-arrival diagnostic contract missing at {turn}")
            coverage_history.append(False)
        elif diagnostics["complete"] is not (diagnostics["coverage_complete"] and diagnostics["window_complete"]):
            problems.append(f"X1 factual-arrival completeness flags disagree at {turn}")
            coverage_history.append(diagnostics["coverage_complete"])
        else:
            coverage_history.append(diagnostics["coverage_complete"])
            expected_window = len(coverage_history) >= 20 and all(coverage_history[-20:])
            if diagnostics["window_complete"] is not expected_window:
                problems.append(f"X1 rolling 20-write coverage history differs at {turn}")
        reg_rows = frame.get("regions")
        valid_regions = isinstance(reg_rows, list) and all(isinstance(r, dict) and type(r.get("region")) is int
                    and 0 <= r["region"] < nregions and type(r.get("residents")) is int and r["residents"] >= 0
                    and type(r.get("displaced")) is int and 0 <= r["displaced"] <= r["residents"] for r in reg_rows)
        if not valid_regions or len({r["region"] for r in reg_rows}) != len(reg_rows):
            problems.append(f"X1 factual regions missing, malformed or duplicate at {turn}")
            reg_rows = []
        for key, metric in (("recent_residence_arrivals", "recent_arrival_person_turns"),
                            ("recent_residence_arrivals_unknown_reason", "recent_arrival_unknown_reason_person_turns")):
            value = (frame.get("totals") or {}).get(key)
            if type(value) is not int or value < 0 or any(type(r.get(key)) is not int or r[key] < 0 for r in reg_rows):
                problems.append(f"X1 {key}: missing factual count at {turn}")
                continue
            if sum(r[key] for r in reg_rows) != value:
                problems.append(f"X1 {key}: region/total count does not close at {turn}")
            out[metric] += value
        for row in reg_rows:
            arrived = row.get("recent_residence_arrivals", 0)
            unknown = row.get("recent_residence_arrivals_unknown_reason", 0)
            if SR._num(arrived) and SR._num(unknown) and (unknown > arrived or arrived > row.get("residents", 0)):
                problems.append(f"X1 recent arrivals double-count residents at {turn}")
        ph = lv.get("public_health") or {}
        if ph.get("crowding") != crowding:
            problems.append(f"public-health saved crowding control differs at {turn}")
        environment = ph.get("environment")
        if not isinstance(environment, list) or len(environment) != nregions or not all(isinstance(r, dict)
                and type(r.get("region")) is int and 0 <= r["region"] < nregions for r in environment) \
                or len({r["region"] for r in environment}) != nregions:
            problems.append(f"public-health environment does not cover each region exactly once at {turn}")
            environment = []
        previous_regions = {r["region"]: r for r in (prior or {}).get("regions", [])}
        previous_diagnostics = (prior or {}).get("arrival_diagnostics")
        complete = previous_diagnostics.get("complete") if isinstance(previous_diagnostics, dict) else None
        for row in environment:
            rid = row["region"]
            previous = previous_regions.get(rid, {})
            residents = previous.get("residents", 0)
            displaced = min(1.0, max(0.0, previous.get("displaced", 0) / max(1, residents)))
            if row.get("source_turn") != turn - 1 or row.get("residence_observed") is not (prior is not None):
                problems.append(f"environment does not use the preceding X1 frame at {turn}")
            if row.get("crowding_basis") != crowding:
                problems.append(f"environment crowding basis differs from its saved control at {turn}")
            expected_crowding_turn = turn if crowding == "density_only" else turn - 1
            if row.get("crowding_source_turn") != expected_crowding_turn:
                problems.append(f"crowding configuration/frame source date differs at {turn}")
            if not SR._num(row.get("displaced_share")) or abs(row["displaced_share"] - displaced) > 1e-8:
                problems.append(f"legacy classified share differs from preceding X1 frame at {turn}")
            if "arrival_diagnostics_complete" not in row or row.get("arrival_diagnostics_complete") is not complete:
                problems.append(f"arrival completeness differs from preceding X1 frame at {turn}")
            if "recent_arrival_share" not in row:
                problems.append(f"recent-arrival diagnostic missing at {turn}")
            elif complete is True:
                expected = min(1.0, max(0.0, previous.get("recent_residence_arrivals", 0) / max(1, residents)))
                if not SR._num(row["recent_arrival_share"]) or abs(row["recent_arrival_share"] - expected) > 1e-8:
                    problems.append(f"recent-arrival share differs from complete preceding X1 frame at {turn}")
            elif row["recent_arrival_share"] is not None:
                problems.append(f"incomplete factual arrival observation became a ratio at {turn}")
            out["arrival_complete_region_turns" if complete is True else
                "arrival_incomplete_region_turns" if complete is False else "arrival_unknown_region_turns"] += 1
            factor = amount(row.get("crowding_factor"), "added crowding factor")
            out["added_crowding_region_turns"] += factor > 1
            out["added_crowding_factor_sum"] += factor - 1
        prior = frame
        food = snap.get("food_accounting") or {}
        food_rows = food.get("regions")
        if not isinstance(food_rows, list) or len(food_rows) != nregions:
            problems.append(f"complete regional food ledger missing at {turn}")
            food_rows = []
        food_by_region = {}
        for rid, row in enumerate(food_rows):
            if not isinstance(row, dict) or row.get("region_id") != rid:
                problems.append(f"food region identity differs at {turn}")
                continue
            if type(row.get("native_count")) is not int or row["native_count"] < 0:
                problems.append(f"required native population count missing or invalid at {turn}")
                continue
            native = row.get("native")
            if not isinstance(native, dict) or any(not SR._num(native.get(k)) for k in (*FOOD_LEDGER_FIELDS, "demand")):
                problems.append(f"native food ledger missing or nonfinite at {turn}")
                continue
            if any(native[k] < 0 for k in (*FOOD_LEDGER_FIELDS, "demand")
                   if k not in ("transport_net", "clamp_correction")):
                problems.append(f"native food stock or withdrawal is negative at {turn}")
            food_by_region[rid] = row
            terms = [native["opening"], native["produced"], native["transport_net"], -native["craft_input"],
                     native["clamp_correction"], -native["consumed"], -native["storage_loss"], -native["cap_overflow"]]
            residual = native["closing"] - math.fsum(terms)
            tolerance = 1e-5 * max(1, math.fsum(abs(v) for v in terms))
            if abs(residual) > tolerance or not SR._num(native.get("balance_residual")) \
                    or abs(native["balance_residual"] - residual) > 1e-10 \
                    or not SR._num(native.get("balance_tolerance")) \
                    or abs(native["balance_tolerance"] - tolerance) > 1e-10:
                problems.append(f"native food stock-flow balance does not close at {turn}")
            for key, target in (("produced", "native_food_produced"), ("consumed", "native_food_consumed"),
                                ("demand", "native_food_demand")):
                out[target] += amount(native[key], key)
            public = row.get("public")
            if isinstance(public, dict):
                out["public_relief_food"] += amount(public.get("released"), "public grain released")
            else:
                problems.append(f"required public grain observation missing or invalid at {turn}")
        retail = lv.get("household_retail") or {}
        expected_theta = 1.0 if retail_mode == "no_relief" else THETA
        if retail.get("schema_version") != 1 or retail.get("source_turn") != turn or retail.get("mode") != retail_mode \
                or retail.get("boundary") != "all" or retail.get("rules_version") != 2 \
                or (retail.get("parameters") or {}).get("theta") != expected_theta:
            problems.append(f"fixed retail enrollment/food-access regime differs at {turn}")
        retail_rows = retail.get("regions")
        if not isinstance(retail_rows, list) or not all(isinstance(r, dict) and type(r.get("region")) is int
                and 0 <= r["region"] < nregions for r in retail_rows) \
                or len({r["region"] for r in retail_rows}) != len(retail_rows):
            problems.append(f"retail region observations missing or malformed at {turn}")
            retail_rows = []
        observed = set()
        for row in retail_rows:
            flows = row.get("flows")
            if not isinstance(flows, dict) or any(k not in FLOW_SIGNS or type(v) is not int or v < 0
                                                   for k, v in flows.items()):
                problems.append(f"retail physical flows malformed at {turn}")
            else:
                opening, closing = row.get("open_milli"), row.get("close_milli")
                if type(opening) is not int or type(closing) is not int or min(opening, closing) < 0 \
                        or opening + sum(FLOW_SIGNS[k] * v for k, v in flows.items()) != closing:
                    problems.append(f"retail owned-food stock does not close at {turn}")
            provision = row.get("provisioning")
            if provision is None:
                continue  # unknown observation, counted below, never invented zero
            if not isinstance(provision, dict) or provision.get("region") != row["region"]:
                problems.append(f"retail provisioning identity malformed at {turn}")
                continue
            observed.add(row["region"])
            out["retail_observed_region_turns"] += 1
            for key, target in (("deficit", "retail_deficit_observed"),
                                ("priced_out_deficit", "retail_priced_out_deficit_observed"),
                                ("offer_short_deficit", "retail_offer_short_deficit_observed"),
                                ("free_given", "retail_free_rations_observed"),
                                ("free_rations", "retail_free_pool_observed"),
                                ("priority_households", "retail_priority_household_turns"),
                                ("free_to_priority", "retail_free_to_priority_observed"),
                                ("rations", "retail_rations_observed"),
                                ("persons", "retail_person_turns_observed")):
                out[target] += amount(provision.get(key), f"retail {key}")
            if not SR._num(provision.get("mode")) or provision["mode"] != (1 if retail_mode == "no_relief" else 0):
                problems.append(f"native retail provisioning mode differs at {turn}")
            priority = provision.get("priority_households")
            if not SR._num(priority) or priority < 0 or priority != math.floor(priority):
                problems.append(f"native retail priority-household count malformed at {turn}")
            if retail_mode == "no_relief" and (provision.get("priority_households") != 0
                                               or provision.get("free_to_priority") != 0):
                problems.append(f"no_relief applies the retail means test at {turn}")
        out["retail_access_unknown_region_turns"] += sum(rid not in observed and row["native_count"] > 0
                                                        for rid, row in food_by_region.items())
        out["retail_paid_milli"] += amount((retail.get("money") or {}).get("paid_milli"), "retail paid")
        out["retail_income_replaced"] += amount((retail.get("income") or {}).get("replaced"), "retail income replaced")
    return out, problems



# Health accounting checks retain costs; only the declared added crowding control differs.
def _health(bundle: dict, flags) -> tuple[dict, list[str]]:
    """Validate completed-turn schemas and material/accounting dates before use.

    A failed field is a visible extraction failure, never a zero-valued success.
    Aggregate disease deaths remain the authority; care tick rows provide the
    infectious-person-turn denominator and must sum to the same death count.
    """
    problems: list[str] = []
    mode = _option(flags, "--public-health-mode", "active")
    crowding = _option(flags, "--public-health-crowding", "density_only")
    policy = _option(flags, "--public-health-policy", "evidence")
    delay = int(_option(flags, "--public-health-report-delay", "0"))
    care_mode = "cost_only" if mode == "cost_only" else _option(flags, "--epidemic-care-mode", "care")
    regions = SR._get(bundle, ("world_state", "regions"))
    nregions = len(regions) if isinstance(regions, list) else 0
    if not nregions:
        problems.append("world_state.regions missing or empty")
    civilizations = SR._get(bundle, ("world_state", "civilizations"))
    names = [row.get("name") for row in civilizations if isinstance(row, dict)] \
        if isinstance(civilizations, list) else []
    if not names or not all(isinstance(name, str) and name for name in names) or len(names) != len(set(names)):
        problems.append("world_state.civilizations stable names missing or malformed")
        civ_names = set()
    else:
        civ_names = set(names)
    history = bundle.get("history")
    if not isinstance(history, list) or not history:
        return {}, [*problems, "history missing or empty"]
    m = dict.fromkeys(("world_epidemic_deaths", "world_person_turns", "world_infectious_pt", "arrivals_world",
                      "care_covered_region_turns", "water_service_region_turns", "displaced_region_turns",
                      "guard_staffed_pair_turns", "guard_paid_milli", "guard_farm_time", "guard_income_withheld",
                      "care_paid_milli", "care_farm_time", "care_income_withheld", "food_consumed_milli",
                      "supplies_cash_milli", "supplies_internal_milli", "l9_envelope_milli", "decisions",
                      "advised_closures", "unfunded_guard_teams", "migrants_blocked", "flight_blocked",
                      "hunger_blocked", "dearth_region_turns", "famine_region_turns"), 0)
    m.update(dict.fromkeys(("care_cash_milli", "supply_cash_milli", "guard_cash_milli", "health_cash_milli",
                           "care_carry_change_milli", "guard_carry_change_milli",
                           "care_income_unknown_person_turns", "guard_income_unknown_person_turns"), 0))
    seen_turns = set()
    sums = dict.fromkeys(("food_consumed_milli", "gross_supplies_milli", "internal_supplies_milli",
                          "guard_farm_time", "guard_wages_milli", "guard_income_withheld", "care_cash_milli",
                          "supply_cash_milli", "guard_cash_milli"), 0)
    last_epi = last_ph = last_rules = None

    def integer(x):
        return isinstance(x, int) and not isinstance(x, bool) and x >= 0

    def number(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0

    def amount(row, key, where):
        value = row.get(key)
        if not number(value):
            problems.append(f"{where}: invalid {key}")
            return 0
        return value

    def rows(obj, key, where):
        value = obj.get(key)
        if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
            problems.append(f"{where}: {key} missing or malformed")
            return []
        return value

    for snap in history:
        if not isinstance(snap, dict) or not integer(snap.get("turn")) or snap["turn"] < 1:
            problems.append("history contains a malformed snapshot turn")
            continue
        turn = snap["turn"] - 1
        where = f"snapshot {turn + 1}"
        if turn in seen_turns:
            problems.append(f"{where}: duplicate completed turn")
        seen_turns.add(turn)
        population = snap.get("regional_population")
        counts = population.get("counts") if isinstance(population, dict) else None
        if not isinstance(counts, list) or len(counts) != nregions or not all(number(x) for x in counts) \
                or population.get("source_turn") != turn:
            problems.append(f"{where}: regional_population missing or misdated")
        else:
            m["world_person_turns"] += sum(counts)
        epi = snap.get("epidemics")
        if not isinstance(epi, dict) or not isinstance(epi.get("active"), list):
            problems.append(f"{where}: epidemics missing")
            continue
        deaths = amount(epi, "deaths", where)
        m["world_epidemic_deaths"] += deaths
        last_epi = epi
        ph = SR._get(snap, ("livelihoods", "public_health"))
        care = SR._get(snap, ("livelihoods", "epidemic_care"))
        if not isinstance(ph, dict) or ph.get("schema_version") != 1 or ph.get("source_turn") != turn \
                or ph.get("enabled") is not True or ph.get("mode") != mode or ph.get("policy") != policy \
                or ph.get("report_delay") != delay:
            problems.append(f"{where}: public_health schema, mode, policy or source date differs")
            continue
        last_ph = ph
        if not isinstance(care, dict) or care.get("schema_version") != 1 or care.get("source_turn") != turn \
                or care.get("mode") != care_mode:
            problems.append(f"{where}: epidemic_care schema, mode or source date differs")
            continue
        tick = care.get("tick")
        if not isinstance(tick, dict) or tick.get("turn") != turn:
            problems.append(f"{where}: care tick missing or misdated")
            tick = {}
        if tick.get("refused") != []:
            problems.append(f"{where}: refused or unobserved care capacity")
        tick_deaths = 0
        for row in rows(tick, "regions", where):
            rid = row.get("region")
            if not integer(rid) or rid >= nregions:
                problems.append(f"{where}: invalid care tick region")
            d, ipt = amount(row, "deaths", where), amount(row, "infectious_pt", where)
            tick_deaths += d
            m["world_infectious_pt"] += ipt
            split = row.get("pathogens")
            valid = isinstance(split, list) and all(isinstance(x, list) and len(x) == 3 and integer(x[0])
                       and x[0] < len(PATHOGENS) and number(x[1]) and number(x[2]) for x in split)
            if not valid or sum(x[1] for x in split) != d \
                    or abs(sum(x[2] for x in split) - ipt) > 1e-6 * max(1, ipt):
                problems.append(f"{where}: pathogen split does not sum to care tick region")
        if tick_deaths != deaths:
            problems.append(f"{where}: care tick deaths {tick_deaths} differ from epidemic authority {deaths}")
        for row in rows(tick, "applied", where):
            coverage = amount(row, "coverage", where)
            if coverage > 1:
                problems.append(f"{where}: care coverage exceeds one")
            m["care_covered_region_turns"] += coverage > 0
            if row.get("source_turn") != turn - 1:
                problems.append(f"{where}: care used stale or future capacity")
            if mode == "cost_only" and row.get("care_factor") != 1:
                problems.append(f"{where}: cost_only applies a care benefit")
        budgets, spent, care_paid, guard_paid, supply_cash = {}, {}, {}, {}, {}
        for row in rows(care, "ledger", where):
            if row.get("turn") != turn or not integer(row.get("civ")):
                problems.append(f"{where}: care envelope missing payer or source date")
                continue
            civ = row.get("civ")
            budgets[civ] = budgets.get(civ, 0) + 1000 * amount(row, "envelope_coins", where)
        for row in rows(care, "frame", where):
            if row.get("turn") != turn or not integer(row.get("civ")):
                problems.append(f"{where}: care receipt missing payer or source date")
                continue
            if type(row.get("paid")) is not bool:
                problems.append(f"{where}: care receipt paid status is not an observed boolean")
            paid = amount(row, "wages_paid_milli", where)
            spent[row.get("civ")] = spent.get(row.get("civ"), 0) + paid
            care_paid[row.get("civ")] = care_paid.get(row.get("civ"), 0) + paid
            m["care_paid_milli"] += paid
            m["care_farm_time"] += amount(row, "farm_time_removed", where)
            for carer in rows(row, "carers", where):
                # A refused wage bill installs no paid-work share, so this
                # service withholds zero. A paid share may have no native
                # wealth-stage row (e.g. death before that stage): preserve
                # that explicit unknown instead of inventing a zero deduction.
                if "income_withheld" in carer and carer["income_withheld"] is None:
                    m["care_income_unknown_person_turns"] += row.get("paid") is True
                    continue
                m["care_income_withheld"] += amount(carer, "income_withheld", where)
        for field in ("report", "environment", "supply", "guard"):
            if ph.get(f"{field}_turn") != turn:
                problems.append(f"{where}: {field} observation missing or misdated")
        reports = {}
        for row in rows(ph, "reports", where):
            rid = row.get("id")
            if not integer(rid) or rid in reports or not all(integer(row.get(k)) for k in
                    ("recipient", "source", "target", "pathogen", "issued", "delivery", "expires")) \
                    or row["source"] >= nregions or row["pathogen"] >= len(PATHOGENS) \
                    or row["issued"] > turn or row["delivery"] <= row["issued"] \
                    or row["expires"] != row["delivery"] + 5 or not number(row.get("prevalence")) \
                    or row["prevalence"] > 1:
                problems.append(f"{where}: malformed, future or duplicate outbreak report")
                continue
            reports[rid] = row
        for row in rows(ph, "decisions", where):
            m["decisions"] += 1
            m["advised_closures"] += row.get("close") is True
            ids = row.get("report_ids")
            if not isinstance(ids, list) or not ids or not all(integer(i) for i in ids) \
                    or len(ids) != len(set(ids)) \
                    or not all(i in reports and reports[i]["delivery"] <= turn <= reports[i]["expires"]
                               and reports[i]["recipient"] == row.get("civ")
                               and reports[i]["target"] == row.get("target") for i in ids):
                problems.append(f"{where}: decision consumes absent, future or expired reports")
            for k in ("expected_loss_units", "cost_units", "goods_contact_cost_proxy"):
                amount(row, k, where)
            if row.get("close") is True and row.get("fatality_observed") is not True:
                problems.append(f"{where}: closure without prior fatality experience")
        for row in rows(ph, "environment", where):
            if row.get("source_turn") != turn - 1:
                problems.append(f"{where}: environment bypasses T-1 residence/service date")
            water = amount(row, "water_service", where)
            displaced = amount(row, "displaced_share", where)
            if water > 1 or displaced > 1 or row.get("residence_observed") not in (True, False) \
                    or row.get("sanitation_observed") not in (True, False):
                problems.append(f"{where}: invalid water/displacement observation")
            expected_crowding = 1 + .25 * displaced if crowding == "legacy_displacement" else 1
            if abs(amount(row, "crowding_factor", where) - expected_crowding) > 1e-8:
                problems.append(f"{where}: crowding factor differs from declared exposure")
            expected = 1 - .2 * water if mode == "active" else 1
            if abs(amount(row, "flux_factor", where) - expected) > 1e-8:
                problems.append(f"{where}: flux factor differs from declared control")
            m["water_service_region_turns"] += water > 0
            m["displaced_region_turns"] += displaced > 0
        for row in rows(ph, "supplies", where):
            if row.get("turn") != turn or not integer(row.get("civ")):
                problems.append(f"{where}: supply missing payer or source date")
                continue
            food = amount(row, "food_milli", where)
            cash = amount(row, "charged_milli", where)
            internal = amount(row, "internal_milli", where)
            if food > amount(row, "need_milli", where) or cash and internal:
                problems.append(f"{where}: supply exceeds patient need or duplicates internal/cash payment")
            if food and (row.get("reason") != "supplied" or not integer(row.get("source"))
                         or row["source"] >= nregions or not integer(row.get("seller"))
                         or not number(row.get("price_milli")) or row["price_milli"] <= 0
                         or cash + internal != math.ceil(food * row["price_milli"] / 1_000_000) * 1000
                         or (cash > 0) != (row["seller"] != row["civ"])):
                problems.append(f"{where}: supplied grain lacks priced actual-owner payment/allocation")
            spent[row.get("civ")] = spent.get(row.get("civ"), 0) + cash + internal
            m["food_consumed_milli"] += food
            m["supplies_cash_milli"] += cash
            supply_cash[row.get("civ")] = supply_cash.get(row.get("civ"), 0) + cash
            m["supplies_internal_milli"] += internal
            sums["food_consumed_milli"] += food
            sums["gross_supplies_milli"] += cash + internal
            sums["internal_supplies_milli"] += internal
        staffed = []
        for row in rows(ph, "guards", where):
            if row.get("turn") != turn or not integer(row.get("civ")) or not integer(row.get("target")):
                problems.append(f"{where}: guard receipt missing payer, target or source date")
                continue
            work = amount(row, "work", where)
            sums["guard_farm_time"] += work
            m["guard_farm_time"] += work
            paid = 0
            members = rows(row, "members", where)
            payment = row.get("payment")
            recognized_payment = isinstance(payment, str) and (payment == "paid" or
                (payment.startswith("refused:") and len(payment) > len("refused:")) or
                (payment == "no_workers" and not members))
            if not recognized_payment:
                problems.append(f"{where}: guard payment status is not a recognized settlement")
            for member in members:
                paid += amount(member, "wage_paid_milli", where)
                if "income_withheld" in member and member["income_withheld"] is None:
                    m["guard_income_unknown_person_turns"] += payment == "paid"
                    withheld = 0  # observed subtotal; unknown count remains separate
                else:
                    withheld = amount(member, "income_withheld", where)
                sums["guard_income_withheld"] += withheld
                m["guard_income_withheld"] += withheld
            spent[row.get("civ")] = spent.get(row.get("civ"), 0) + paid
            guard_paid[row.get("civ")] = guard_paid.get(row.get("civ"), 0) + paid
            m["guard_paid_milli"] += paid
            sums["guard_wages_milli"] += paid
            m["guard_staffed_pair_turns"] += row.get("staffed") is True
            m["unfunded_guard_teams"] += row.get("staffed") is not True
            if row.get("staffed") is True:
                staffed.append([row.get("civ"), row.get("target")])
                if row.get("payment") != "paid" or work < 1 - 1e-6 or not members \
                        or any(x.get("wage_paid_milli") != x.get("wage_due_milli") for x in members):
                    problems.append(f"{where}: enforcement capacity without full named paid work")
        capacity = ph.get("guard_capacity")
        valid_capacity = isinstance(capacity, list) and all(isinstance(x, (list, tuple)) and len(x) == 2
                         and all(integer(v) for v in x) for x in capacity)
        if ph.get("guard_capacity_turn") != turn or not valid_capacity \
                or sorted(map(list, capacity)) != sorted(staffed):
            problems.append(f"{where}: next-turn guard capacity differs from paid staffed teams")
        for civ, value in spent.items():
            if value > budgets.get(civ, 0):
                problems.append(f"{where}: care + supply + guard gross cost {value} exceeds civ {civ} envelope "
                                f"{budgets.get(civ, 0)}")
        if ph.get("funding_turn") != turn:
            problems.append(f"{where}: cash funding missing or misdated")
        funding_civs = set()
        for row in rows(ph, "funding", where):
            civ = row.get("civ")
            if row.get("turn") != turn or not integer(civ) or civ >= len(civ_names) or civ in funding_civs:
                problems.append(f"{where}: cash funding has invalid or duplicate payer/date")
                continue
            if integer(civ):
                funding_civs.add(civ)
            envelope = amount(row, "envelope_milli", where)
            if envelope != budgets.get(civ, 0):
                problems.append(f"{where}: cash funding envelope differs from single L9 care envelope")
            cash = 0
            for purpose in ("care", "guard"):
                paid = amount(row, f"{purpose}_paid_milli", where)
                charged = amount(row, f"{purpose}_cash_milli", where)
                before = amount(row, f"{purpose}_carry_before", where)
                after = amount(row, f"{purpose}_carry_after", where)
                if not all(integer(v) for v in (paid, charged, before, after)) or charged % 1000 \
                        or before >= 1000 or after >= 1000 or charged + before != paid + after:
                    problems.append(f"{where}: {purpose} cash + carry before != credited + carry after")
                expected = care_paid.get(civ, 0) if purpose == "care" else guard_paid.get(civ, 0)
                if paid != expected:
                    problems.append(f"{where}: {purpose} funding credits differ from named wage receipts")
                cash += charged
                m[f"{purpose}_cash_milli"] += charged
                m[f"{purpose}_carry_change_milli"] += after - before
                sums[f"{purpose}_cash_milli"] += charged
            charged = amount(row, "supply_cash_milli", where)
            if charged % 1000 or charged != supply_cash.get(civ, 0):
                problems.append(f"{where}: patient cash funding differs from actual foreign receipts")
            cash += charged
            m["supply_cash_milli"] += charged
            sums["supply_cash_milli"] += charged
            m["health_cash_milli"] += cash
            if cash > envelope:
                problems.append(f"{where}: fresh health cash funding exceeds its single L9 envelope")
        if funding_civs != set(budgets):
            problems.append(f"{where}: cash funding does not cover exactly the executed care envelopes")
        m["l9_envelope_milli"] += sum(budgets.values())
        rules = epi.get("quarantine_rules")
        if not isinstance(rules, dict) or rules.get("schema_version") != 1 or rules.get("mode") != "closure" \
                or rules.get("channels") != ["trade", "migration"]:
            problems.append(f"{where}: staffed closure/migration rules absent")
        else:
            last_rules = rules
            receipt = rules.get("receipt")
            if not isinstance(receipt, dict) or receipt.get("turn") != turn:
                problems.append(f"{where}: quarantine receipt missing or misdated")
            else:
                for key, dest in (("migrants_blocked", "migrants_blocked"),
                                  ("migrants_blocked_flight", "flight_blocked"),
                                  ("migrants_blocked_hunger", "hunger_blocked")):
                    m[dest] += amount(receipt, key, where)
        fa = snap.get("food_accounting")
        if not isinstance(fa, dict) or fa.get("source_turn") != turn:
            problems.append(f"{where}: food accounting missing or misdated")
        else:
            for row in rows(fa, "regions", where):
                suff = amount(row, "sufficiency_after_relief", where)
                m["dearth_region_turns"] += suff < 1
                m["famine_region_turns"] += suff < .6
    if seen_turns != set(range(len(history))):
        problems.append("history does not contain every completed turn from zero")
    if last_epi is not None and last_epi.get("deaths_total") != m["world_epidemic_deaths"]:
        problems.append("epidemic per-turn deaths differ from lifetime authority")
    if last_ph is not None:
        totals = last_ph.get("totals")
        if not isinstance(totals, dict):
            problems.append("public_health lifetime totals missing")
        else:
            for key, value in sums.items():
                got = totals.get(key, 0)
                if not number(got) or abs(got - value) > 1e-5 * max(1, value):
                    problems.append(f"public_health total {key} differs from receipt sum {value}")
    events = bundle.get("events_timeline")
    if not isinstance(events, list):
        problems.append("events_timeline missing")
    else:
        for event in events:
            if isinstance(event, dict) and event.get("event_type") == "epidemic_arrival":
                actors = event.get("actors")
                # Arrival emission deduplicates the controlled source/target
                # names. Zero/one actors are legitimate uncontrolled or same-
                # polity arrivals, not cross-polity events. Unknown names or
                # out-of-history turns are malformed, never a counted event.
                if not integer(event.get("turn")) or event["turn"] not in seen_turns:
                    problems.append("epidemic_arrival turn is outside observed completed history")
                elif not isinstance(actors, list) or len(actors) > 2 \
                        or not all(isinstance(name, str) and name in civ_names for name in actors) \
                        or len(actors) != len(set(actors)):
                    problems.append("epidemic_arrival actors are malformed or not stable controlled polities")
                elif len(actors) == 2:
                    m["arrivals_world"] += 1
    for key in ("route_turns_removed", "forgone_income", "closed_pair_turns"):
        m[key] = amount((last_rules or {}).get("totals") or {}, key, "quarantine totals")
    m["world_deaths_per_1000_pt"] = 1000 * m["world_epidemic_deaths"] / m["world_person_turns"] \
        if m["world_person_turns"] > 0 else None
    m["world_deaths_per_ipt"] = m["world_epidemic_deaths"] / m["world_infectious_pt"] \
        if m["world_infectious_pt"] > 0 else None
    return m, problems


def extract(bundle, flags, *, expected_turns=None):
    """Validate before reporting: a missing field never becomes a valid zero."""
    if not isinstance(bundle, dict) or not isinstance(bundle.get("history"), list) \
            or any(not isinstance(s, dict) for s in bundle["history"]):
        return {}, ["completed history missing or malformed"]
    physical, problems = _physical(bundle, flags)
    if not physical:
        return physical, problems
    health, hp = _health(bundle, flags)
    adaptive, ap = _adaptive(bundle, flags)
    factual, fp = _factual_and_food(bundle, flags)
    problems += hp + ap + fp
    if health.get("world_person_turns") != physical.get("person_turns"):
        problems.append("health and native population denominators differ")
    m = {**physical, **health, **adaptive, **factual}
    metadata = bundle.get("metadata") or {}
    world = bundle.get("world_state") or {}
    if type(metadata.get("seed")) is not int or metadata["seed"] < 0 or metadata["seed"] != world.get("seed"):
        problems.append("bundle/world seed missing or inconsistent")
    if type(metadata.get("total_turns")) is not int or metadata["total_turns"] != m["turns"]:
        problems.append("completed history differs from declared total_turns")
    if expected_turns is not None and m["turns"] != expected_turns:
        problems.append("completed history differs from the requested screen horizon")
    context = bundle.get("_cwr_expected_world")
    if context is not None and (metadata.get("seed") != context["seed"]
            or m["regions"] != {"t": 8, "p": 32}[context["stratum"]]):
        problems.append("saved world differs from the requested screen seed/stratum")
    m["seed"] = metadata.get("seed")
    m["epidemic_deaths"] = m.get("world_epidemic_deaths")
    m["epidemic_deaths_per_1000_pt"] = m.get("world_deaths_per_1000_pt")
    shortfall = SR.harm_food_shortfall(bundle)
    if shortfall.get("state") != SR.RECORDED or not SR._num(shortfall.get("value")):
        problems.append("regional availability shortfall is not completely recorded")
    m["food_shortfall"] = shortfall.get("value")
    m["food_shortfall_per_1000_pt"] = (1000 * m["food_shortfall"] / m["person_turns"]
        if SR._num(m["food_shortfall"]) and m["person_turns"] > 0 else None)
    # Observed subtotals are retained. A complete household-access claim is
    # unavailable if a populated region has no provisioning observation.
    m["retail_access_deficit"] = (m["retail_deficit_observed"]
        if m["retail_access_unknown_region_turns"] == 0 else None)
    return m, problems


def activation(bundle, flags):
    return True, "Every enrolled world enters; actual mechanism activation is reported separately"


def metric(name):
    return lambda row: (row.get("m") or {}).get(name)


OUTCOMES = [
    SR.Outcome("cwr_food", "Regional availability shortfall (AD - RD)", "AD", "RD",
               metric("food_shortfall"), primary=True),
    SR.Outcome("cwr_epidemic", "Recorded epidemic deaths (AD - RD)", "AD", "RD",
               metric("epidemic_deaths"), primary=True),
    SR.Outcome("cwr_crowding_interaction", "Epidemic deaths: (AL - RL) - (AD - RD)", "AL", "RL",
               metric("epidemic_deaths"), primary=True, minus=("AD", "RD")),
]
COMPARISONS = (("AD", "RD"), ("AL", "RL"), ("RL", "RD"),
    ("MX", "AD"), ("IX", "AD"), ("WX", "AD"), ("TX", "AD"),
    ("APC", "RPC"), ("RPC", "RD"), ("ANR", "RNR"), ("RNR", "RD"))
SECONDARY_METRICS = (
    "food_shortfall", "epidemic_deaths", "food_shortfall_per_1000_pt", "epidemic_deaths_per_1000_pt",
    "balance_change_per_1000_pt", "deaths_per_1000_pt", "all_migrations", "unknown_migration_share",
    "x1_displaced_person_turns", "recent_arrival_person_turns", "arrival_complete_region_turns",
    "arrival_incomplete_region_turns", "arrival_unknown_region_turns", "added_crowding_factor_sum",
    "a6_personal_rows", "d3_input_rows", "a6_offer_declines", "a6_work_unknown", "dropped_a6_rows",
    "combined_migration_input_rows", "combined_native_choice_changes", "native_migration_refusals",
    "trade_unknown_destination", "trade_personal_return_refusal", "care_covered_region_turns",
    "food_consumed_milli", "health_cash_milli", "care_farm_time", "guard_farm_time",
    "native_food_produced", "native_food_consumed", "public_relief_food", "retail_access_deficit",
    "retail_access_unknown_region_turns", "retail_priced_out_deficit_observed",
    "retail_offer_short_deficit_observed", "retail_free_rations_observed", "retail_paid_milli",
    "retail_free_pool_observed", "retail_priority_household_turns", "retail_free_to_priority_observed",
    "retail_income_replaced", "army_hunger_ration_turns", "timber_delivered_milli",
)
for arm, control in COMPARISONS:
    for key in SECONDARY_METRICS:
        OUTCOMES.append(SR.Outcome(f"cwr_{arm}_{control}_{key}", f"{key} ({arm} - {control})",
                                  arm, control, metric(key)))
for label, first, second in (
        ("crowding", ("AL", "RL"), ("AD", "RD")),
        ("health", ("AD", "RD"), ("APC", "RPC")),
        ("retail", ("AD", "RD"), ("ANR", "RNR"))):
    for key in ("food_shortfall", "epidemic_deaths"):
        if label == "crowding" and key == "epidemic_deaths":
            continue  # already a primary, never duplicate outcome ids
        OUTCOMES.append(SR.Outcome(f"cwr_{label}_{key}_interaction", f"{key}: {first} minus {second}",
                                  *first, metric(key), minus=second))


def paired_bootstrap(values, *, draws=10000):
    """Empirical paired-world interval, descriptive only; no simulation RNG."""
    if not values:
        return None
    rng = random.Random(20261107)
    n = len(values)
    means = sorted(math.fsum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(draws))
    return (means[int(.025 * (draws - 1))], means[int(.975 * (draws - 1))])


def extra_report(rows, strata):
    lines = ["", "## Enrollment and actual activation", "",
        "Every successful enrolled world enters every defined comparison, including zero-activation worlds. "
        "The generic eligibility label is not proof of mechanism activation. The observations below do not "
        "select worlds. Combined native score changes are not effects attributable to an individual input.", "",
        "| Arm | Stratum | World: personal rows / D3 rows / offer declines / supplied-care region-turns / added-crowding sum |",
        "| --- | --- | --- |"]
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    for arm in ARMS:
        for tag, seeds in strata.items():
            cells = []
            for seed in seeds:
                row = by.get((arm, tag, seed))
                if row is None or row.get("rc") != 0:
                    cells.append(f"{seed}: {'not run' if row is None else 'failed'}")
                else:
                    m = row.get("m") or {}
                    cells.append(f"{seed}: " + "/".join(str(m.get(k, "unknown")) for k in
                        ("a6_personal_rows", "d3_input_rows", "a6_offer_declines", "care_covered_region_turns",
                         "added_crowding_factor_sum")))
            lines.append(f"| {arm} | {tag} | {'; '.join(cells)} |")
    lines += ["", "## Paired-world uncertainty and supplemental direct contrasts", "",
        "Intervals resample whole paired worlds 10,000 times with fixed analysis seed 20261107. "
        "They describe the empirical enrolled-world sample (held n=6 per stratum; pilots smaller) "
        "and are unstable at this size; they are not "
        "qualification, model calibration, clinical evidence or a promotion threshold. No individual is "
        "treated as an independent replicate. All successful enrolled worlds remain included.", "",
        "| Contrast | Metric | Stratum | World differences | Mean [min, max] | Paired bootstrap 95% interval | Sign-flip |",
        "| --- | --- | --- | --- | --- | --- | --- |"]
    contrasts = [(a, c, None) for a, c in (*COMPARISONS, ("AL", "AD"), ("APC", "AD"), ("ANR", "AD"))]
    contrasts += [("AL", "RL", ("AD", "RD")), ("AD", "RD", ("APC", "RPC")),
                  ("AD", "RD", ("ANR", "RNR"))]
    for arm, control, minus in contrasts:
        label = f"{arm} - {control}" + (f" - ({minus[0]} - {minus[1]})" if minus else "")
        for key in ("food_shortfall", "epidemic_deaths"):
            for tag, seeds in strata.items():
                cells, values = SR.paired_values(rows, SCREEN, arm, control, metric(key), tag, seeds,
                                                 need_activation=False, minus=minus)
                summary, _signs, flip = SR._summary_cells(values)
                interval = paired_bootstrap(values)
                band = "undefined" if interval is None else f"[{interval[0]:+.6g}, {interval[1]:+.6g}]"
                lines.append(f"| {label} | {key} | {tag} | {'; '.join(cells)} | {summary} | {band} | {flip} |")
    lines += ["", "Regional food shortfall measures availability, not every household's access. Retail access "
        "subtotals and unknown coverage are separate; `no_relief` changes the title fraction from 0.9 to 1 "
        "and uses L2's existing free-pool allocation without the retail means test, a joint ownership/allocation regime. "
        "Existing commons and public releases can still supply free rations. It creates no new food, "
        "and is not a pure price control. PH cost_only retains wages/supplies/guards and the chosen "
        "crowding basis, but responsive realized spending need not be equal. Classified displacement "
        "is not inferred physical crowding. Incomplete arrival diagnostics remain unknown ratios."]
    return lines


SCREEN = SR.Screen(name="CWR1", title="Corrected Connected World causal mechanism screen", module=MODULE,
    preregistration=PREREG, base=BASE, arms=ARMS, root="RD",
    pilot={"template": (5,), "procedural": (19,)},
    held={"template": tuple(range(4101, 4107)), "procedural": tuple(range(4201, 4207))},
    packages=(SR.Package("--adaptive-livelihoods", ("livelihoods", "adaptive_livelihoods"),
                        mode_flag="--adaptive-livelihoods-mode", default_mode="adapt"),
              SR.Package("--public-health", ("livelihoods", "public_health"),
                        mode_flag="--public-health-mode", default_mode="active"),
              SR.Package("--household-retail", ("livelihoods", "household_retail"),
                        mode_flag="--household-retail-mode", default_mode="retail"),
              SR.Package("--war-consequences", ("livelihoods", "war_consequences"),
                        mode_flag="--war-consequences-mode", default_mode="active"),
              SR.Package("--war-requisition", ("livelihoods", "war_requisition"),
                        mode_flag="--war-requisition-mode", default_mode="transfer"),
              SR.Package("--timber-orders", ("livelihoods", "timber_orders"))),
    outcomes=tuple(OUTCOMES), activation=activation, extract=partial(extract, expected_turns=HORIZON),
    report=extra_report, ready=True,
    procedural=(*SR.PROCEDURAL, "--watershed", "--watershed-mode", "flow"))


def main(argv=None):
    argv = resource_args(list(sys.argv[1:] if argv is None else argv))
    screen = SCREEN
    if argv and argv[0] == "run" and option(argv, "--cohort", "pilot") == "dev":
        turns = option(argv, "--turns", None)
        if turns is not None:
            turns = int(turns)
            if turns <= 0:
                raise ValueError("development horizon must be positive")
            screen = replace(SCREEN, extract=partial(extract, expected_turns=turns))
    SR.load_bundle_file = load_bundle_file
    try:
        return SR.main(argv, {"CWR1": screen}, prog="cw_rework_screen.py")
    finally:
        SR.load_bundle_file = _load_bundle_file


def resource_args(argv):
    if argv and argv[0] == "run":
        jobs = [token.split("=", 1)[1] for token in argv if token.startswith("--jobs=")]
        jobs += [argv[i + 1] for i, token in enumerate(argv[:-1]) if token == "--jobs"]
        if jobs and jobs != ["1"]:
            raise ValueError("CWR1 requires exactly one simulation job")
        if not jobs:
            argv = [*argv, "--jobs", "1"]
        if option(argv, "--cohort", "pilot") in ("held", "reserve"):
            arms = option(argv, "--arms", None)
            if arms is not None and (set(arms.split(",")) != set(ARMS) or len(arms.split(",")) != len(ARMS)):
                raise ValueError("CWR1 evidence requires every preregistered arm")
    return argv


if __name__ == "__main__":
    raise SystemExit(main())


