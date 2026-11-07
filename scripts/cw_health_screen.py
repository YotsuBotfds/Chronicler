"""Bounded CW-health screen; no qualification gate or narration calls.

This module owns its strict extractor. Outcomes include every enrolled world,
including worlds with no supplied care, water service or staffed border guard.
Those mechanism activations are reported separately and never select outcomes.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen_runner as SR

MODULE = Path(__file__).resolve()
PREREGISTRATION = SR.REPO / "docs/superpowers/progress/connected-world-screen-health.md"
PATHOGENS = ("plague", "pox", "fever", "flux", "pestilence")


def _option(flags, key, default):
    return flags[flags.index(key) + 1] if key in flags else default


def extract(bundle: dict, flags) -> tuple[dict, list[str]]:
    """Validate completed-turn schemas and material/accounting dates before use.

    A failed field is a visible extraction failure, never a zero-valued success.
    Aggregate disease deaths remain the authority; care tick rows provide the
    infectious-person-turn denominator and must sum to the same death count.
    """
    problems: list[str] = []
    mode = _option(flags, "--public-health-mode", "active")
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
                    m["care_income_unknown_person_turns"] += row.get("paid") is not False
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
            if abs(amount(row, "crowding_factor", where) - (1 + .25 * displaced)) > 1e-8:
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
            for member in members:
                paid += amount(member, "wage_paid_milli", where)
                no_paid_work = str(row.get("payment", "")).startswith("refused:")
                if "income_withheld" in member and member["income_withheld"] is None:
                    m["guard_income_unknown_person_turns"] += not no_paid_work
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


def activation(bundle, flags):
    """ITT enrollment is unconditional; mechanism activation is diagnostic only."""
    m, problems = extract(bundle, flags)
    if problems:
        return None, f"strict schema failed: {problems[0]}"
    return True, (f"ITT enrolled regardless of activation; supplied care {m['care_covered_region_turns']} region-turns; "
                  f"water {m['water_service_region_turns']} region-turns; "
                  f"staffed guards {m['guard_staffed_pair_turns']} pair-turns; "
                  f"displacement {m['displaced_region_turns']} region-turns")


def _metric(name):
    return lambda row: (row.get("m") or {}).get(name)


BASE = ("--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves", "--grain-storage",
        "--local-budgets", "--repair-projects", "--infrastructure-condition", "--residence-ledger",
        "--food-allocation", "--household-retail", "--household-retail-rules", "2",
        "--epidemic-care", "--public-health", "--quarantine-mode", "closure", "--quarantine-channels", "trade,migration")
SCREEN = SR.Screen(
    name="CW-health", title="Connected public health: material care, water management and dated advice",
    preregistration=PREREGISTRATION, base=BASE,
    arms={"PC": (("--public-health-mode", "cost_only", "--public-health-policy", "evidence"), None),
          "PS": (("--public-health-mode", "active", "--public-health-policy", "shuffled"), "PC"),
          "PA": (("--public-health-mode", "active", "--public-health-policy", "evidence"), "PS")},
    root="PC", pilot={"template": (5,), "procedural": (19,)},
    held={"template": tuple(range(3901, 3907)), "procedural": tuple(range(4001, 4007))},
    packages=(SR.Package("--public-health", ("livelihoods", "public_health"),
                         mode_flag="--public-health-mode", default_mode="active"),
              SR.Package("--epidemic-care", ("livelihoods", "epidemic_care")),
              SR.Package("--infrastructure-condition", ("livelihoods", "infrastructure_condition"))),
    outcomes=(SR.Outcome("health_world_death_rate", "World epidemic deaths per 1,000 end-turn person-turns (PA - PC)",
                         "PA", "PC", _metric("world_deaths_per_1000_pt"), primary=True),
              SR.Outcome("health_world_dpi", "World epidemic deaths per infectious person-turn (PA - PC)",
                         "PA", "PC", _metric("world_deaths_per_ipt"), primary=True),
              SR.Outcome("health_world_arrivals", "World cross-polity epidemic arrivals (PA - PS)",
                         "PA", "PS", _metric("arrivals_world"), primary=True),
              *(SR.Outcome(f"health_h_{key}", f"{label} (PA - PC)", "PA", "PC", _metric(key)) for key, label in (
                  ("food_consumed_milli", "Actual patient grain consumed (milli-loads)"),
                  ("supplies_cash_milli", "Patient supply cash paid (milli-units)"),
                  ("supplies_internal_milli", "Local patient grain allocated at dated prices (milli-units)"),
                  ("care_paid_milli", "Care wages paid (milli-units)"),
                  ("care_income_withheld", "Observed ordinary carer income withheld subtotal"),
                  ("care_income_unknown_person_turns", "Paid carer person-turns without an income deduction observation"),
                  ("guard_paid_milli", "Guard wages paid (milli-units)"),
                  ("guard_income_withheld", "Observed ordinary guard income withheld subtotal"),
                  ("guard_income_unknown_person_turns", "Paid guard person-turns without an income deduction observation"),
                  ("care_farm_time", "Carer farm time removed"), ("guard_farm_time", "Guard farm time removed"),
                  ("l9_envelope_milli", "Gross single care/public-health envelopes (milli-units)"),
                  ("health_cash_milli", "Actual whole-coin health cash funding (milli-units)"),
                  ("care_carry_change_milli", "Change in prepaid care wage carry (milli-units)"),
                  ("guard_carry_change_milli", "Change in prepaid guard wage carry (milli-units)"),
                  ("famine_region_turns", "Region-turns below 0.6 food sufficiency"),
                  ("migrants_blocked", "Refused civilian migration person-turns"),
                  ("flight_blocked", "Refused flight person-turns"), ("hunger_blocked", "Refused hunger moves"),
                  ("route_turns_removed", "Removed partner route-turns"),
                  ("forgone_income", "Forgone partner route income")))),
    activation=activation, extract=extract, ready=True, module=MODULE)
SCREENS = {SCREEN.name: SCREEN}


def main(argv=None):
    return SR.main(resource_args(list(sys.argv[1:] if argv is None else argv)),
                   SCREENS, prog="cw_health_screen.py")


def resource_args(argv):
    """Keep omitted concurrency within the lead's one/two-process schedule."""
    if argv and argv[0] == "run":
        jobs = [token.split("=", 1)[1] for token in argv if token.startswith("--jobs=")]
        jobs += [argv[i + 1] for i, token in enumerate(argv[:-1]) if token == "--jobs"]
        if jobs and jobs not in (["1"], ["2"]):
            raise ValueError("CW-health requires one or two simulation jobs scheduled by the lead")
        if not jobs:
            argv = [*argv, "--jobs", "1"]
    return argv


if __name__ == "__main__":
    raise SystemExit(main())
