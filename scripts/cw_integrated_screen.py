"""CW6 bounded integrated screen. No qualification or default promotion.

The standalone loader also reads the untruncated agent-event Arrow sidecar;
unknown migration provenance is an explicit measurement harm, never a decline
in actual displacement. All enrolled worlds enter every defined comparison.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen_runner as SR

MODULE = Path(__file__).resolve()
PREREG = SR.REPO / "docs/superpowers/progress/connected-world-screens-cw6-integrated.md"
BASE = ("--turns", "200", "--agents", "hybrid", "--simulate-only", "--campaigns", "--health-care",
        "--grain-reserves", "--grain-storage", "--public-grain-shipments", "--grain-convoys",
        "--scholarship", "--academy-services", "--learning-cohorts", "--workshops", "--workshop-payroll",
        "--workshop-economics", "--workshop-economics-rules", "2", "--apprenticeship", "--operating-wear", "--veteran-reintegration",
        "--timber-stock", "--commons-rules", "--clearing-protection", "--timber-supply", "--repair-projects",
        "--recovery-crews", "--local-budgets", "--maintenance-obligation", "--remittances", "--relocation-costs",
        "--food-allocation", "--household-retail", "--household-retail-rules", "2",
        "--household-retail-boundary", "all", "--titled-trade", "--infrastructure-condition", "--infrastructure-condition-mode", "repair",
        "--reform-services", "--guild-leagues", "--movement-branches", "--movement-branches-mode", "funded", "--epidemic-care", "--public-health",
        "--quarantine-mode", "closure", "--quarantine-channels", "trade,migration", "--residence-ledger",
        "--war-requisition", "--war-consequences", "--adaptive-livelihoods", "--adaptive-livelihoods-rules", "2",
        "--attribution-records", "--wealth-accounting", "--wealth-accounting-mode", "strict")


def arm_flags(a6="adapt", d3="active", d4="transfer", supply=True):
    return ("--adaptive-livelihoods-mode", a6, "--war-consequences-mode", d3,
            "--war-requisition-mode", d4, "--harvest-cover", "--harvest-cover-mode",
            "loss" if supply else "record_only", *(("--timber-orders",) if supply else ()))


ARMS = {"FULL": (arm_flags(), None), "A6R": (arm_flags(a6="record_only"), "FULL"),
        "D3R": (arm_flags(d3="record_only"), "FULL"), "D4C": (arm_flags(d4="cost_only"), "FULL"),
        "SUP": (arm_flags(supply=False), "FULL")}


def option(flags, key, default):
    return flags[flags.index(key) + 1] if key in flags else default


def event_sidecar(path):
    """Read exact event counts without changing the saved bundle or sidecar."""
    import pyarrow.ipc as ipc
    from chronicler.models import MIGRATION_DRIVER_NAMES
    path = Path(path)
    if not path.exists():
        return {"present": False, "migration": 0, "unknown": 0, "deaths": 0, "bytes": 0, "sha256": None}
    batch = ipc.open_file(path).read_all()
    required = {"turn", "event_type", "migration_driver"}
    if not required <= set(batch.column_names):
        raise ValueError("CW6 requires event sidecar turn, event_type and migration_driver columns")
    migrations = unknown = deaths = 0
    turns = batch.column("turn").to_pylist()
    if any(type(turn) is not int or turn < 0 for turn in turns):
        raise ValueError("event sidecar has malformed source turns")
    for kind, driver in zip(batch.column("event_type").to_pylist(), batch.column("migration_driver").to_pylist()):
        if kind == "migration" and (type(driver) is not int or driver not in (*range(len(MIGRATION_DRIVER_NAMES)), 255)):
            raise ValueError("event sidecar has an unrecognized migration driver")
        migrations += kind == "migration"
        unknown += kind == "migration" and driver == 255
        deaths += kind == "death"
    return {"present": True, "migration": migrations, "unknown": unknown, "deaths": deaths,
            "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "turn_min": min(turns) if turns else None, "turn_max": max(turns) if turns else None}


_load_bundle_file = SR.load_bundle_file


def load_bundle_file(path):
    bundle = _load_bundle_file(path)
    bundle["_cw6_events"] = event_sidecar(Path(path).parent / "agent_events.arrow")
    return bundle


def extract(bundle, flags):
    from chronicler.wealth_accounting import record_status
    from chronicler.timber_orders import check_order
    from chronicler.timber_orders_state import TimberOrder
    from chronicler.reform_services import record_status as relief_status
    from chronicler.guild_leagues import record_status as league_status
    from chronicler.movement_branches import record_status as branch_status
    problems = []
    m = dict.fromkeys(("person_turns", "balance_change", "deaths", "income_gross", "income_applied", "wages_milli",
        "withheld_native", "wealth_close", "a6_refusals", "a6_repeated_refusals", "a6_input_rows", "a6_changed",
        "a6_work_observed", "a6_work_unknown", "a6_offer_declines", "d3_wounded", "d3_released", "d3_evacuated",
        "d3_returned", "separation_person_pairs", "injury_episode_turns", "new_occupational_injuries",
        "battle_deaths", "army_consumed", "army_demand", "army_hunger_ration_turns", "army_consumption_rows",
        "requisition_milli", "army_supply_food_milli", "destroyed_food_milli", "restitution_paid_milli",
        "claims_unrecorded_milli", "claims_unpaid_final_milli", "service_asset_turns", "asset_turns", "infra_work",
        "infra_timber_used", "infra_paid_milli", "timber_delivered_milli", "timber_carrier_paid_milli",
        "timber_orders", "cover_loss", "all_migrations", "x1_moves", "x1_other_moves", "x1_opened_spells",
        "x1_displaced_person_turns", "dropped_war_events", "dropped_a6_rows", "dropped_work_rows",
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
    a6_mode = option(flags, "--adaptive-livelihoods-mode", "adapt")
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
        a6 = dated(lv, "adaptive_livelihoods", turn, mode=a6_mode)
        af = a6.get("frame") or {}
        if af.get("information_gate_installed") is not (a6_mode != "record_only"):
            problems.append(f"A6 information control differs at {turn}")
        m["a6_input_rows"] += finite(af.get("rows_installed"), "A6 installed rows")
        m["dropped_a6_rows"] += finite(af.get("rows_dropped", 0), "A6 dropped rows")
        receipt = af.get("receipt")
        if not isinstance(receipt, (list, tuple)) or len(receipt) != 4 or receipt[0] != turn:
            problems.append(f"A6 native receipt absent or misdated at {turn}")
        else:
            m["a6_changed"] += finite(receipt[3], "A6 changed")
        m["a6_refusals"] += finite(af.get("refusals_total", 0), "A6 refusal total")
        for refusal in rows(af, "refusals", "A6"):
            key = (refusal.get("id"), refusal.get("region"))
            m["a6_repeated_refusals"] += key in past_refused
            past_refused.add(key)
        for work in rows(af, "work", "A6"):
            m["a6_work_observed"] += work.get("net_milli") is not None
            m["a6_work_unknown"] += work.get("net_milli") is None
        m["dropped_work_rows"] += finite(af.get("work_dropped"), "A6 dropped work")
        m["a6_offer_declines"] += sum(row.get("accepted") is False for row in rows(af, "offers", "A6"))
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


def activation(bundle, flags):
    return True, "Every enrolled world, including zero mechanism activation; validation is separate"


def metric(key):
    return lambda row: row["m"][key]


def full_minus_control(key):
    # The generic runner's tree is rooted at FULL, so its comparison arm is
    # the modified control. Negating both observations yields FULL-control;
    # the generic fixed harm table retains its ordinary control-FULL sign.
    return lambda row: -row["m"][key] if row["m"][key] is not None else None


OUTCOMES = [SR.Outcome("cw6_balance", "World household balance change per 1,000 person-turns (FULL - A6R)",
                       "A6R", "FULL", full_minus_control("balance_change_per_1000_pt"), primary=True),
            SR.Outcome("cw6_deaths", "Observed native deaths per 1,000 person-turns (FULL - D3R)",
                       "D3R", "FULL", full_minus_control("deaths_per_1000_pt"), primary=True),
            SR.Outcome("cw6_service", "Service asset-turns per world region-turn (FULL - joint SUP)",
                       "SUP", "FULL", full_minus_control("service_per_region_turn"), primary=True)]
for control in ("A6R", "D3R", "D4C", "SUP"):
    for key in ("income_gross", "income_applied", "wages_milli", "withheld_native", "wealth_close", "a6_refusals",
                "a6_repeated_refusals", "d3_wounded", "d3_released", "d3_evacuated", "d3_returned", "battle_deaths",
                "separation_person_pairs", "injury_episode_turns", "army_hunger_ration_turns", "army_supply_food_milli",
                "requisition_milli", "destroyed_food_milli", "restitution_paid_milli", "claims_unpaid_final_milli",
                "infra_work", "infra_timber_used", "infra_paid_milli", "timber_delivered_milli", "cover_loss",
                "all_migrations", "unknown_migration_share", "x1_opened_spells", "x1_displaced_person_turns",
                "branch_funded_turns", "branch_payer_turns", "branch_dues_milli"):
        OUTCOMES.append(SR.Outcome(f"cw6_{control}_{key}", f"{key} (FULL - {control})", control, "FULL", full_minus_control(key)))

SCREEN = SR.Screen(name="CW6", title="Connected World integrated A-E bounded screen", module=MODULE,
    preregistration=PREREG, base=BASE, arms=ARMS, root="FULL",
    pilot={"template": (5,), "procedural": (19,)}, held={"template": tuple(range(781, 787)), "procedural": tuple(range(881, 887))},
    packages=(SR.Package("--adaptive-livelihoods", ("livelihoods", "adaptive_livelihoods"), mode_flag="--adaptive-livelihoods-mode", default_mode="adapt"),
              SR.Package("--war-consequences", ("livelihoods", "war_consequences"), mode_flag="--war-consequences-mode", default_mode="active"),
              SR.Package("--war-requisition", ("livelihoods", "war_requisition"), mode_flag="--war-requisition-mode", default_mode="transfer"),
              SR.Package("--timber-orders", ("livelihoods", "timber_orders"))),
    outcomes=tuple(OUTCOMES), activation=activation, extract=extract, ready=True,
    procedural=(*SR.PROCEDURAL, "--watershed", "--watershed-mode", "flow"))


def main(argv=None):
    argv = serial_run_args(list(sys.argv[1:] if argv is None else argv))
    SR.load_bundle_file = load_bundle_file
    try:
        return SR.main(argv, {"CW6": SCREEN}, prog="cw_integrated_screen.py")
    finally:
        SR.load_bundle_file = _load_bundle_file


def serial_run_args(argv):
    if argv and argv[0] == "run":
        jobs = [token.split("=", 1)[1] for token in argv if token.startswith("--jobs=")]
        jobs += [argv[i + 1] for i, token in enumerate(argv[:-1]) if token == "--jobs"]
        if jobs and jobs != ["1"]:
            raise ValueError("CW6 preregistration requires exactly one simulation job")
        if not jobs:
            argv = [*argv, "--jobs", "1"]
    return argv


if __name__ == "__main__":
    raise SystemExit(main())
