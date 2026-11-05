"""Livelihoods sprint screens: run the preregistered arms and summarize them.

    python scripts/livelihoods_screens.py run OUT_DIR [--sprint 1|2|3] [--seeds template|procedural|all] [--jobs 3] [--arms a,b] [--cohort held|pilot]
    python scripts/livelihoods_screens.py report OUT_DIR/metrics.jsonl [--sprint 1|2|3]

Run with the native interpreter whose extension matches the source under test
(the arms are hybrid). Arms, cohorts and outcomes are preregistered in
docs/superpowers/progress/livelihoods-sprint1-screens.md (sprint 1) and
docs/superpowers/progress/livelihoods-sprint2-screens.md (sprint 2) and
docs/superpowers/progress/recovery-skills-screens.md (sprint 3, recovery skills,
with a validated extractor: a missing or malformed outcome fails the run
visibly instead of reading as zero); worlds are
the units. Every arm is compared with its declared control arm on the same
world. Each run's raw output is deleted after extraction, except the first
seed of each stratum (kept as an example world). Metrics go to
OUT_DIR/metrics.jsonl.
"""
import argparse, json, os, shutil, subprocess, sys, time
from statistics import mean
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PY = sys.executable
REPO = str(Path(__file__).resolve().parents[1])
BASE = ["--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves", "--public-grain-shipments"]
# Arm -> (flags, control arm, tuning overrides). Sprint 1 is frozen as run.
NO_CAP = {"livelihoods": {"timber": {"enforce_cap": 0}}}
ARMS = {
    "off": ([], None, None),
    "L1_operate": (["--workshops"], "off", None),
    "L1_cost_only": (["--workshops", "--workshop-mode", "cost_only"], "off", None),
    "L2_floor_means": (["--food-allocation"], "off", None),
    "L2_targeted": (["--food-allocation", "--food-allocation-regime", "targeted_relief"], "off", None),
    "L3_timber": (["--timber-stock"], "off", None),
    "L3_ablation": (["--timber-stock"], "off", NO_CAP),
    "L4_convoys": (["--grain-convoys"], "off", None),
    "I1_work_food": (["--workshops", "--food-allocation"], "off", None),
    "I2_timber_work": (["--workshops", "--timber-stock"], "off", None),
    "I3_convoy_relief": (["--grain-convoys", "--food-allocation", "--food-allocation-regime", "targeted_relief"], "off", None),
    "ALL": (["--workshops", "--food-allocation", "--timber-stock", "--grain-convoys"], "off", None),
}
PROCEDURAL = ["--worldgen", "procedural", "--regions", "32", "--civs", "10"]
STRATA = {"template": [("t", s, []) for s in range(101, 107)],
          "procedural": [("p", s, PROCEDURAL) for s in range(201, 207)]}
# Sprint 2 (preregistered in docs/superpowers/progress/livelihoods-sprint2-screens.md).
# Every arm shares the base below, so one off arm serves as the root control;
# each package is also compared with its own reference arm.
BASE2 = ["--scholarship", "--techniques", "--academy-services", "--grain-storage"]
_W = ["--workshops"]
_PAY = _W + ["--workshop-payroll"]
_TS = ["--timber-stock"]
_SERVICES = _W + ["--food-allocation", "--food-allocation-regime", "targeted_relief"]
_FOOD = ["--food-allocation"]
_RELOC = _FOOD + ["--relocation-costs"]
ARMS2 = {
    "off": ([], None, None),
    "D1_workshops": (_W, "off", None),                                   # L1 downstream supplies
    "L5_learn": (["--learning-cohorts"], "off", None),
    "L5_no_learning": (["--learning-cohorts", "--learning-cohort-mode", "no_learning"], "off", None),
    "L6_paid": (_PAY, "D1_workshops", None),
    "L6_unpaid_labor": (_PAY + ["--workshop-payroll-mode", "unpaid_labor"], "D1_workshops", None),
    "L6_no_customer": (_PAY + ["--workshop-payroll-mode", "no_customer"], "D1_workshops", None),
    "T_timber": (_TS, "off", None),
    "L8_enforced": (_TS + ["--commons-rules"], "T_timber", None),
    "L8_cost_only": (_TS + ["--commons-rules", "--commons-rule-mode", "cost_only"], "T_timber", None),
    "I_timber_work": (_TS + _W, "D1_workshops", None),
    "I_commons_work": (_TS + _W + ["--commons-rules"], "I_timber_work", None),
    "W_services": (_SERVICES, "off", None),
    "L9_bargained": (_SERVICES + ["--local-budgets"], "W_services", None),
    "L9_fixed_shares": (_SERVICES + ["--local-budgets", "--local-budget-mode", "fixed_shares"], "W_services", None),
    "F_food": (_FOOD, "off", None),
    "L7_liquidity_only": (_RELOC + ["--relocation-mode", "liquidity_only"], "F_food", None),
    "L7_paid": (_RELOC + ["--relocation-mode", "paid"], "L7_liquidity_only", None),
    "L7_assisted": (_RELOC + ["--relocation-mode", "assisted"], "L7_liquidity_only", None),
    "I_learn_pay": (_PAY + ["--learning-cohorts"], "L6_paid", None),
    "ALL": (_PAY + ["--learning-cohorts", "--food-allocation", "--timber-stock", "--commons-rules",
                    "--grain-convoys", "--local-budgets", "--relocation-costs"], "off", None),
}
STRATA2 = {"template": [("t", s, BASE2) for s in range(301, 307)],
           "procedural": [("p", s, BASE2 + PROCEDURAL) for s in range(401, 407)]}
SPRINTS = {1: {"arms": ARMS, "strata": STRATA,
               "labels": {"t": "template 8x4 (seeds 101-106)", "p": "procedural 32x10 (seeds 201-206)"}},
           2: {"arms": ARMS2, "strata": STRATA2,
               "labels": {"t": "template 8x4 (seeds 301-306)", "p": "procedural 32x10 (seeds 401-406)"}}}
# Sprint 3: recovery skills (preregistered in docs/superpowers/progress/recovery-skills-screens.md).
# The same base as sprint 2; workshops run in operate mode (their default).
_WO = ["--workshops"]
_APP = _WO + ["--apprenticeship"]
_REP = _WO + ["--repair-projects"]
_VET = _WO + ["--veteran-reintegration"]
_TC = ["--timber-stock", "--commons-rules"]
NO_WAR_DAMAGE = {"repair_projects": {"war_damage": 0}}
ARMS3 = {
    "off": ([], None, None),
    "W_operate": (_WO, "off", None),                                    # reference for RS1-RS3
    "RS1_train": (_APP, "RS1_no_qualification", None),
    "RS1_no_qualification": (_APP + ["--apprenticeship-mode", "no_qualification"], "W_operate", None),
    "RS2_repair": (_REP, "RS2_cost_only", None),
    "RS2_cost_only": (_REP + ["--repair-mode", "cost_only"], "W_operate", None),
    "RS2_no_war_damage": (_REP, "RS2_repair", NO_WAR_DAMAGE),           # ablation: no damage records
    "RS3_priority": (_VET, "RS3_record_only", None),
    "RS3_record_only": (_VET + ["--veteran-mode", "record_only"], "W_operate", None),
    "RS4_send": (["--remittances"], "RS4_record_only", None),
    "RS4_record_only": (["--remittances", "--remittance-mode", "record_only"], "off", None),
    "RS5_enforced": (["--clearing-protection"], "RS5_cost_only", None),
    "RS5_cost_only": (["--clearing-protection", "--clearing-protection-mode", "cost_only"], "off", None),
    "T_commons": (_TC, "off", None),                                    # reference for clearing x commons
    "I_clearing_commons": (_TC + ["--clearing-protection"], "T_commons", None),
    "I_appr_repair": (_APP + ["--repair-projects"], "RS2_repair", None),
    "I_vet_appr": (_APP + ["--veteran-reintegration"], "RS1_train", None),
    "I_repair_budgets": (_REP + ["--local-budgets"], "RS2_repair", None),
    "ALL3": (_APP + ["--repair-projects", "--veteran-reintegration", "--remittances", "--clearing-protection"],
             "off", None),
}
STRATA3 = {"template": [("t", s, BASE2) for s in range(501, 507)],
           "procedural": [("p", s, BASE2 + PROCEDURAL) for s in range(601, 607)]}
#: Timing pilot on development worlds only (never held): template seed 2, procedural seed 7.
PILOT3 = {"template": [("t", 2, BASE2)], "procedural": [("p", 7, BASE2 + PROCEDURAL)]}
SPRINTS[3] = {"arms": ARMS3, "strata": STRATA3, "pilot": PILOT3,
              "labels": {"t": "template 8x4 (seeds 501-506)", "p": "procedural 32x10 (seeds 601-606)"}}
#: Sprint-3 switches, the snapshot key each writes, its mode option and default mode.
RS_PACKAGES = {
    "--apprenticeship": ("apprenticeship", "--apprenticeship-mode", "train"),
    "--repair-projects": ("repair_projects", "--repair-mode", "repair"),
    "--veteran-reintegration": ("veteran_reintegration", "--veteran-mode", "priority"),
    "--remittances": ("remittances", "--remittance-mode", "send"),
    "--clearing-protection": ("clearing_protection", "--clearing-protection-mode", "enforced"),
}
#: Lifetime counters the sprint-3 report reads per package (validated against the
#: package's declared counters by ``check_extractor3``; absent from a record = never
#: incremented = 0, since every record starts empty when its switch is enabled).
OUTCOMES3 = {
    "apprenticeship": ("operating_site_turns", "crew_turns_served", "qualified_service", "mentor_turns",
                       "seats_offered", "enrolled", "veterans_enrolled", "apprentice_turns_attended",
                       "completions", "completions_granted", "qualified_apprenticeship", "upkeep_work",
                       "upkeep_offset", "wear", "income_forgone", "stipends_paid", "teaching_lost",
                       "end_migrated", "end_died", "end_dropout", "end_site_closed"),
    "repair_projects": ("opened_wear", "opened_war", "opened_granary", "opened_workshop", "progress_turns",
                        "stalled_turns", "stalled_no_timber", "stalled_no_coins", "stalled_no_labor",
                        "stalled_no_envelope", "work_delivered", "work_credited", "timber_used", "charged",
                        "wages_milli", "crew_person_turns", "qualified_crew_turns", "unqualified_crew_turns",
                        "damages", "damages_conquest", "damages_sack", "damages_seizure", "completed",
                        "veterans_placed", "inherited"),
    "veteran_reintegration": ("captured", "captured_demobilised", "captured_desertion", "captured_scattered",
                              "offered", "placements", "placements_crew", "placements_apprentice",
                              "placements_repair", "people_placed", "placed_prioritised", "waiting_turns",
                              "unmet_no_site", "unmet_site_idle", "unmet_not_crew_eligible", "unmet_crew_full",
                              "closed_died", "closed_expired", "closed_remobilised"),
    "remittances": ("moves_seen", "departures", "returns", "deaths", "eligible_sender_turns",
                    "linked_sender_turns", "unlinked_sender_turns", "rows", "rows_applied", "rows_limited",
                    "rows_absent", "rows_not_sent", "requested_milli", "sent_milli", "fee_milli",
                    "credited_milli", "refunded_milli", "not_sent_milli"),
    "clearing_protection": ("eligible_region_turns", "adoption_candidates", "adoption_unaffordable", "adopted",
                            "protected_region_turns", "clearing_active_turns", "required", "charged",
                            "full_funded_turns", "partial_funded_turns", "zero_funded_turns",
                            "cover_not_cleared", "cover_cleared_unprotected", "ended_unfunded"),
}
#: Sprint-2 packages whose lifetime counters are copied from the last snapshot.
COUNTED = ("learning_cohorts", "workshop_payroll", "commons_rules", "local_budgets", "relocation_costs")
#: Funnel counters reported per package (None: every counter the records hold).
FUNNEL_KEYS = {
    "learning_cohorts": ("academy_turns", "cohorts_formed", "learners_enrolled", "sessions", "learner_turns_attended",
                         "learner_turns_no_seat", "no_session_too_little_teaching", "no_session_no_supplies",
                         "completions", "capability_changes", "attendance_income_charged"),
    "workshop_payroll": ("firms_opened", "operating_site_turns", "customer_firm_turns", "sales", "wages_due",
                         "wages_paid", "income_replaced", "paid_person_turns", "insolvent_firm_turns",
                         "hours_cuts", "layoffs", "closed_insolvent", "owed_written_off", "distributed"),
    "commons_rules": ("eligible_slot_turns", "adoption_candidates", "adopted", "rule_slot_turns", "paid",
                      "tightened_turns", "binding_turns", "excess", "extraction_under_rule", "grievance_added",
                      "repealed_recovered", "repealed_unfunded"),
    "local_budgets": None,
    "relocation_costs": None,
}


def check_counted() -> None:
    """Every counted package is a real livelihoods switch (its snapshot key)."""
    sys.path.insert(0, f"{REPO}/src")
    from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES
    missing = [name for name in COUNTED if name not in LIVELIHOODS_SWITCHES]
    if missing or set(FUNNEL_KEYS) != set(COUNTED):
        raise SystemExit(f"screen packages are not livelihoods switches: {missing or sorted(FUNNEL_KEYS)}")


def _yaml(tree: dict, indent: int = 0) -> str:
    out = []
    for key, value in tree.items():
        if isinstance(value, dict):
            out.append(" " * indent + f"{key}:\n" + _yaml(value, indent + 2))
        else:
            out.append(" " * indent + f"{key}: {value}\n")
    return "".join(out)


def _get(r, *path, default=None):
    x = r
    for p in path:
        if not isinstance(x, dict) or p not in x:
            return default
        x = x[p]
    return x


def paired_table(rows, outcomes) -> list[str]:
    """Per-world paired differences (arm minus control, or the arm alone)."""
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows if r["rc"] == 0}
    out = ["| Outcome | Stratum | Worlds | Mean diff [min, max] | Worlds >0 / <0 |", "| --- | --- | --- | --- | --- |"]
    for label, arm, ctl, f in outcomes:
        for s in ("t", "p"):
            d = []
            for seed in sorted({k[2] for k in by if k[1] == s}):
                a, c = by.get((arm, s, seed)), (by.get((ctl, s, seed)) if ctl else None)
                if a is None or (ctl and c is None):
                    continue
                va, vc = f(a), (f(c) if ctl else 0.0)
                if va is None or vc is None:
                    continue
                d.append(va - vc)
            if d:
                out.append(f"| {label} | {s} | {len(d)} | {mean(d):+.4g} [{min(d):+.4g}, {max(d):+.4g}] "
                           f"| {sum(x > 0 for x in d)} / {sum(x < 0 for x in d)} |")
    return out


#: Sprint-2 preregistered primary outcomes as per-world paired differences.
PAIRED2 = [
 ("D1 academy supplies purchased", "D1_workshops", "off", lambda r: _get(r, "academy", "purchased")),
 ("D1 teaching work delivered", "D1_workshops", "off", lambda r: _get(r, "academy", "work_delivered")),
 ("L5 completions (learn - no_learning)", "L5_learn", "L5_no_learning", lambda r: _get(r, "counters", "learning_cohorts", "completions", default=0)),
 ("L5 capability changes (learn - no_learning)", "L5_learn", "L5_no_learning", lambda r: _get(r, "counters", "learning_cohorts", "capability_changes", default=0)),
 ("L5 learner-turns attended (learn)", "L5_learn", None, lambda r: _get(r, "counters", "learning_cohorts", "learner_turns_attended", default=0)),
 ("L6 crew net income (paid - unpaid_labor)", "L6_paid", "L6_unpaid_labor", lambda r: (_get(r, "counters", "workshop_payroll", "wages_paid", default=0) / 1000 - _get(r, "counters", "workshop_payroll", "income_replaced", default=0))),
 ("L6 site-region craft output (paid - D1)", "L6_paid", "D1_workshops", lambda r: _get(r, "workshops", "out")),
 ("L6 insolvent closures (no_customer)", "L6_no_customer", None, lambda r: _get(r, "counters", "workshop_payroll", "closed_insolvent", default=0)),
 ("L8 extraction (enforced - cost_only)", "L8_enforced", "L8_cost_only", lambda r: _get(r, "timber", "extraction")),
 ("L8 closing stock (enforced - cost_only)", "L8_enforced", "L8_cost_only", lambda r: _get(r, "timber", "stock_end")),
 ("L8 regrowth (enforced - cost_only)", "L8_enforced", "L8_cost_only", lambda r: _get(r, "timber", "regrowth")),
 ("I commons x work: site craft output", "I_commons_work", "I_timber_work", lambda r: _get(r, "workshops", "out")),
 ("I commons x work: extraction", "I_commons_work", "I_timber_work", lambda r: _get(r, "timber", "extraction")),
 ("L9 poorer-half shortfall per person (bargained - W)", "L9_bargained", "W_services", lambda r: (_get(r, "food", "sp") / _get(r, "food", "pp")) if _get(r, "food", "pp") else None),
 ("L9 relief to targeted (bargained - W)", "L9_bargained", "W_services", lambda r: _get(r, "food", "relief_t")),
 ("L9 site craft output (bargained - W)", "L9_bargained", "W_services", lambda r: _get(r, "workshops", "out")),
 ("L9 site craft output (fixed - W)", "L9_fixed_shares", "W_services", lambda r: _get(r, "workshops", "out")),
 ("L9 poorer-half shortfall (fixed - W)", "L9_fixed_shares", "W_services", lambda r: (_get(r, "food", "sp") / _get(r, "food", "pp")) if _get(r, "food", "pp") else None),
 ("L7 persons moved (paid - liquidity_only)", "L7_paid", "L7_liquidity_only", lambda r: _get(r, "counters", "relocation_costs", "persons_applied", default=0)),
 ("L7 persons moved (assisted - liquidity_only)", "L7_assisted", "L7_liquidity_only", lambda r: _get(r, "counters", "relocation_costs", "persons_applied", default=0)),
 ("L7 groups short (assisted - paid)", "L7_assisted", "L7_paid", lambda r: _get(r, "counters", "relocation_costs", "groups_short", default=0)),
 ("L5xL6 completions (I_learn_pay - L5_learn)", "I_learn_pay", "L5_learn", lambda r: _get(r, "counters", "learning_cohorts", "completions", default=0)),
]


def declared_counters3() -> dict:
    """Each sprint-3 package's declared lifetime counter names, from its source."""
    sys.path.insert(0, f"{REPO}/src")
    from chronicler import apprenticeship_state as A, clearing_protection_state as C, remittances_state as R
    from chronicler import repair_projects_state as P, veteran_reintegration_state as V
    return {"apprenticeship": frozenset(A.COUNTERS), "repair_projects": frozenset(P.COUNTERS),
            "veteran_reintegration": frozenset(V.COUNTERS), "remittances": frozenset(R.COUNTERS),
            "clearing_protection": frozenset(C.COUNTER_KEYS)}


def check_extractor3() -> None:
    """Every outcome the sprint-3 report reads is a counter its package declares,
    and every arm's control and RS switch is known, so a renamed counter fails
    here instead of reading as zero."""
    sys.path.insert(0, f"{REPO}/src")
    from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES
    declared = declared_counters3()
    problems = [f"{name} is not a livelihoods switch" for name in OUTCOMES3 if name not in LIVELIHOODS_SWITCHES]
    problems += [f"{name}.{key} is not a declared counter" for name, keys in OUTCOMES3.items()
                 for key in keys if key not in declared[name]]
    problems += [f"arm {arm}: unknown control {control}" for arm, (_f, control, _t) in ARMS3.items()
                 if control is not None and control not in ARMS3]
    for label, arm, control, _f in PAIRED3:
        problems += [f"outcome {label!r}: unknown arm {a}" for a in (arm, control) if a and a not in ARMS3]
    if set(OUTCOMES3) != {v[0] for v in RS_PACKAGES.values()}:
        problems.append("OUTCOMES3 and RS_PACKAGES name different packages")
    if problems:
        raise SystemExit("sprint-3 extractor does not match the source: " + "; ".join(problems))


def expected_packages3(flags) -> dict:
    """{snapshot key: mode} of the sprint-3 packages an arm's flags enable."""
    flags = list(flags)
    out = {}
    for flag, (name, mode_flag, default) in RS_PACKAGES.items():
        if flag in flags:
            out[name] = flags[flags.index(mode_flag) + 1] if mode_flag in flags else default
    return out


def extract3(bundle: dict, flags, declared: dict) -> tuple[dict, list[str]]:
    """Sprint-3 outcomes of one run and the reasons any is missing or malformed.

    Every enabled package must have a record in the last snapshot, observed for
    the completed turn, in the arm's mode, with counters the package declares; a
    package the arm did not enable must have none. World-level outcomes must be
    present for every region. Any failure is returned, never read as zero."""
    hist = bundle.get("history") or []
    problems: list[str] = []
    if not hist:
        return {}, ["no snapshots"]
    last = hist[-1]
    liv = last.get("livelihoods") or {}
    expected = expected_packages3(flags)
    out: dict = {"rs": {}}
    for name in OUTCOMES3:
        rec = liv.get(name)
        if name not in expected:
            if rec is not None:
                problems.append(f"{name}: record present although the arm leaves it off")
            continue
        if not isinstance(rec, dict):
            problems.append(f"{name}: no record in the last snapshot")
            continue
        if rec.get("mode") != expected[name]:
            problems.append(f"{name}: mode {rec.get('mode')!r}, expected {expected[name]!r}")
        if rec.get("source_turn") != last.get("turn", 0) - 1:
            problems.append(f"{name}: source_turn {rec.get('source_turn')!r} is not the completed turn")
        counters = rec.get("counters")
        if not isinstance(counters, dict):
            problems.append(f"{name}: counters missing")
            continue
        unknown = sorted(set(counters) - declared[name])
        if unknown:
            problems.append(f"{name}: undeclared counters {unknown[:5]}")
        bad = [k for k, v in counters.items() if not isinstance(v, (int, float)) or v != v]
        if bad:
            problems.append(f"{name}: non-numeric counters {bad[:5]}")
        out["rs"][name] = {k: counters.get(k, 0) for k in OUTCOMES3[name]}
    regions = (bundle.get("world_state") or {}).get("regions") or []
    cover = [((r.get("ecology") or {}).get("forest_cover")) for r in regions]
    if not regions or any(not isinstance(c, (int, float)) for c in cover):
        problems.append("forest cover missing for some region")
    else:
        out["forest_end"] = mean(cover)
    sites = (((bundle.get("world_state") or {}).get("livelihoods") or {}).get("workshops") or {}).get("sites")
    if "--workshops" in flags:
        if sites is None:
            problems.append("workshop sites missing from the final world state")
        else:
            built = [x["condition"] for x in sites if x.get("status") == "open" and x.get("asset") != "building"
                     and isinstance(x.get("condition"), (int, float))]
            out["workshop_condition_end"] = mean(built) if built else None   # unknown, not zero
        lump = 0
        for snap in hist:
            for r in (((snap.get("livelihoods") or {}).get("workshops") or {}).get("receipts") or []):
                lump += bool((r.get("paid") or {}).get("repair"))
        out["lump_repairs"] = lump
    return out, problems


def metrics3(bundle_path: Path, flags) -> dict:
    """Sprint-3 row: the shared metrics plus the validated recovery-skills outcomes.
    A missing or malformed outcome makes the row a visible failure (rc 3)."""
    from chronicler.bundle_codec import load_bundle
    m = metrics(bundle_path)
    extra, problems = extract3(load_bundle(bundle_path), flags, declared_counters3())
    m.update(extra)
    if problems:
        m["rc"], m["error"] = 3, "missing or malformed outcomes: " + "; ".join(problems)
    return m


def _rs(r, name, key):
    return _get(r, "rs", name, key)


def _ratio(a, b):
    return (a / b) if (a is not None and b) else None


#: Sprint-3 preregistered primary outcomes: (label, arm, control or None, value).
PAIRED3 = [
 ("RS1 qualified through apprenticeship (train - no_qualification)", "RS1_train", "RS1_no_qualification", lambda r: _rs(r, "apprenticeship", "qualified_apprenticeship")),
 ("RS1 upkeep offset (train - no_qualification)", "RS1_train", "RS1_no_qualification", lambda r: _rs(r, "apprenticeship", "upkeep_offset")),
 ("RS1 workshop condition at end (train - no_qualification)", "RS1_train", "RS1_no_qualification", lambda r: r.get("workshop_condition_end")),
 ("RS1 operating site-turns (train - no_qualification)", "RS1_train", "RS1_no_qualification", lambda r: _get(r, "workshops", "operating")),
 ("RS1 enrolled apprentices (train)", "RS1_train", None, lambda r: _rs(r, "apprenticeship", "enrolled")),
 ("RS1 completions (train)", "RS1_train", None, lambda r: _rs(r, "apprenticeship", "completions")),
 ("RS1 income forgone by apprentices (train)", "RS1_train", None, lambda r: _rs(r, "apprenticeship", "income_forgone")),
 ("RS1 adverse: lump repairs (train - W_operate)", "RS1_train", "W_operate", lambda r: r.get("lump_repairs")),
 ("RS1 adverse: workshop condition at end (train - W_operate)", "RS1_train", "W_operate", lambda r: r.get("workshop_condition_end")),
 ("RS2 granary condition at end (repair - cost_only)", "RS2_repair", "RS2_cost_only", lambda r: _get(r, "storage_end", "mean_condition")),
 ("RS2 granary capacity at end (repair - cost_only)", "RS2_repair", "RS2_cost_only", lambda r: _get(r, "storage_end", "capacity")),
 ("RS2 workshop condition at end (repair - cost_only)", "RS2_repair", "RS2_cost_only", lambda r: r.get("workshop_condition_end")),
 ("RS2 operating site-turns (repair - cost_only)", "RS2_repair", "RS2_cost_only", lambda r: _get(r, "workshops", "operating")),
 ("RS2 granary condition at end (repair - W_operate)", "RS2_repair", "W_operate", lambda r: _get(r, "storage_end", "mean_condition")),
 ("RS2 coins charged (repair)", "RS2_repair", None, lambda r: _rs(r, "repair_projects", "charged")),
 ("RS2 timber used (repair)", "RS2_repair", None, lambda r: _rs(r, "repair_projects", "timber_used")),
 ("RS2 stalled project-turns (repair)", "RS2_repair", None, lambda r: _rs(r, "repair_projects", "stalled_turns")),
 ("RS2 war damages recorded (repair - no_war_damage)", "RS2_repair", "RS2_no_war_damage", lambda r: _rs(r, "repair_projects", "damages")),
 ("RS2 granary condition at end (repair - no_war_damage)", "RS2_repair", "RS2_no_war_damage", lambda r: _get(r, "storage_end", "mean_condition")),
 ("RS3 people placed (priority - record_only)", "RS3_priority", "RS3_record_only", lambda r: _rs(r, "veteran_reintegration", "people_placed")),
 ("RS3 placements (priority - record_only)", "RS3_priority", "RS3_record_only", lambda r: _rs(r, "veteran_reintegration", "placements")),
 ("RS3 veterans captured (priority)", "RS3_priority", None, lambda r: _rs(r, "veteran_reintegration", "captured")),
 ("RS3 waiting veteran-turns (priority)", "RS3_priority", None, lambda r: _rs(r, "veteran_reintegration", "waiting_turns")),
 ("RS4 credited to recipients, wealth units (send - record_only)", "RS4_send", "RS4_record_only", lambda r: _rs(r, "remittances", "credited_milli") / 1000 if _rs(r, "remittances", "credited_milli") is not None else None),
 ("RS4 courier fees leaving the economy, wealth units (send - record_only)", "RS4_send", "RS4_record_only", lambda r: _rs(r, "remittances", "fee_milli") / 1000 if _rs(r, "remittances", "fee_milli") is not None else None),
 ("RS4 linked share of eligible sender-turns (send)", "RS4_send", None, lambda r: _ratio(_rs(r, "remittances", "linked_sender_turns"), _rs(r, "remittances", "eligible_sender_turns"))),
 ("RS5 mean forest cover at end (enforced - cost_only)", "RS5_enforced", "RS5_cost_only", lambda r: r.get("forest_end")),
 ("RS5 mean forest cover at end (enforced - off)", "RS5_enforced", "off", lambda r: r.get("forest_end")),
 ("RS5 coins charged (enforced - cost_only)", "RS5_enforced", "RS5_cost_only", lambda r: _rs(r, "clearing_protection", "charged")),
 ("RS5 cover not cleared (enforced)", "RS5_enforced", None, lambda r: _rs(r, "clearing_protection", "cover_not_cleared")),
 ("RS5 protections adopted (enforced)", "RS5_enforced", None, lambda r: _rs(r, "clearing_protection", "adopted")),
 ("I apprenticeship x repair: qualified repair-crew turns", "I_appr_repair", "RS2_repair", lambda r: _rs(r, "repair_projects", "qualified_crew_turns")),
 ("I apprenticeship x repair: workshop condition at end", "I_appr_repair", "RS2_repair", lambda r: r.get("workshop_condition_end")),
 ("I veterans x apprenticeship: veterans enrolled", "I_vet_appr", "RS1_train", lambda r: _rs(r, "apprenticeship", "veterans_enrolled")),
 ("I veterans x apprenticeship: apprentice placements", "I_vet_appr", None, lambda r: _rs(r, "veteran_reintegration", "placements_apprentice")),
 ("I repair x budgets: granary condition at end", "I_repair_budgets", "RS2_repair", lambda r: _get(r, "storage_end", "mean_condition")),
 ("I repair x budgets: stalled for want of an envelope", "I_repair_budgets", None, lambda r: _rs(r, "repair_projects", "stalled_no_envelope")),
 ("I clearing x commons: mean forest cover at end", "I_clearing_commons", "T_commons", lambda r: r.get("forest_end")),
 ("I clearing x commons: timber extraction", "I_clearing_commons", "T_commons", lambda r: _get(r, "timber", "extraction")),
]


def per_world_table(rows, outcomes, strata) -> list[str]:
    """Each world's paired difference (or value), the stratum mean and the signs;
    a world whose arm or control failed, or whose outcome is unknown, is listed as such."""
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    out = ["| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 |",
           "| --- | --- | --- | --- | --- |"]
    for label, arm, ctl, f in outcomes:
        for s in strata:
            cells, d = [], []
            for seed in sorted({k[2] for k in by if k[1] == s}):
                a, c = by.get((arm, s, seed)), (by.get((ctl, s, seed)) if ctl else None)
                if a is None or (ctl and c is None):
                    cells.append(f"{seed}: not run"); continue
                if a["rc"] != 0 or (ctl and c["rc"] != 0):
                    cells.append(f"{seed}: failed"); continue
                va, vc = f(a), (f(c) if ctl else 0.0)
                if va is None or vc is None:
                    cells.append(f"{seed}: unknown"); continue
                d.append(va - vc); cells.append(f"{seed}: {va - vc:+.4g}")
            summary = (f"{mean(d):+.4g} [{min(d):+.4g}, {max(d):+.4g}]" if d else "n/a")
            signs = f"{sum(x > 0 for x in d)} / {sum(x < 0 for x in d)} / {sum(x == 0 for x in d)}"
            out.append(f"| {label} | {s} | {'; '.join(cells)} | {summary} | {signs} |")
    return out


def metrics(bundle_path: Path) -> dict:
    sys.path.insert(0, f"{REPO}/src")
    from chronicler.bundle_codec import load_bundle
    b = load_bundle(bundle_path)
    hist = b["history"]
    last = hist[-1]
    m = {"turns": len(hist),
         "population": sum(v["population"] for v in last["civ_stats"].values()),
         "treasury": sum(v["treasury"] for v in last["civ_stats"].values()),
         "alive_civs": sum(1 for v in last["civ_stats"].values() if v.get("population", 0) > 0)}
    regions = b["world_state"]["regions"]
    m["crafts_stock_end"] = sum(r.get("stockpile", {}).get("goods", {}).get("crafts", 0.0) for r in regions)
    m["timber_goods_end"] = sum(r.get("stockpile", {}).get("goods", {}).get("timber", 0.0) for r in regions)
    w = {"site_turns": 0, "operating": 0, "building": 0, "idle": 0, "alloc": 0.0, "real": 0.0, "out": 0.0, "paid": 0}
    f = {"scarce": 0, "short": 0.0, "sp": 0.0, "pp": 0, "sr": 0.0, "pr": 0, "sc": 0.0, "pc": 0, "relief_t": 0.0, "relief_unknown": 0, "unalloc": 0.0}
    t = {"extraction": 0.0, "regrowth": 0.0, "cleared": 0.0, "overdraft": 0.0, "capped": 0, "stock_end": None, "cap_end": None}
    for s in hist:
        liv = s.get("livelihoods") or {}
        ws = liv.get("workshops")
        for r in (ws or {}).get("receipts") or []:
            w["site_turns"] += 1; w["alloc"] += r["allocated"]; w["real"] += r["realized"]
            w["out"] += r["region_craft_output"] or 0.0; w["paid"] += sum((r.get("paid") or {}).values())
            if r.get("craft_ceiling"): w["operating"] += 1
            if (r.get("paid") or {}).get("construction"): w["building"] += 1
            if r.get("asset") == "idle": w["idle"] += 1
        fa = liv.get("food_allocation")
        for r in (fa or {}).get("regions") or []:
            f["scarce"] += 1; f["short"] += r["shortfall"]; f["sp"] += r["shortfall_poorer_half"]; f["pp"] += r["people_poorer_half"]
            f["sr"] += r["shortfall_richer_half"]; f["pr"] += r["people_richer_half"]; f["sc"] += r["shortfall_children"]
            f["pc"] += r["children"]; f["unalloc"] += r["unallocated"]
            if r.get("relief_to_targeted") is None:
                f["relief_unknown"] += 1  # unknown pre-release sufficiency: not zero
            else:
                f["relief_t"] += r["relief_to_targeted"]
        ts = liv.get("timber_stock")
        if ts and ts.get("totals"):
            tt = ts["totals"]
            for k in ("extraction", "regrowth", "cleared", "overdraft"): t[k] += tt[k]
            t["capped"] += tt["capped_slots"]; t["stock_end"] = tt["stock"]; t["cap_end"] = tt["capacity"]
    if any(s.get("livelihoods", {}).get("workshops") for s in hist): m["workshops"] = w
    if any(s.get("livelihoods", {}).get("food_allocation") for s in hist): m["food"] = f
    if any(s.get("livelihoods", {}).get("timber_stock") for s in hist): m["timber"] = t
    gc = (last.get("livelihoods") or {}).get("grain_convoys")
    if gc: m["convoys"] = gc["counters"]
    services = ((last.get("scholarship") or {}).get("learning_services") or {})
    if services.get("totals"):
        seen, work, learners = set(), 0.0, 0.0
        for snap in hist:                       # each teaching receipt once, by seat and turn
            for r in (((snap.get("scholarship") or {}).get("learning_services") or {}).get("teaching_receipts") or []):
                key = (r.get("seat_id"), r.get("source_turn"))
                if key not in seen:
                    seen.add(key); work += r.get("work_delivered") or 0.0; learners += r.get("learners_delivered") or 0.0
        t = services["totals"]
        m["academy"] = {"founded": (last["scholarship"].get("counters") or {}).get("founded", 0),
                        "purchased": t.get("purchased", 0.0), "used": t.get("used", 0.0), "lost": t.get("lost", 0.0),
                        "teaching_receipts": len(seen), "work_delivered": work, "learners_delivered": learners}
    # L7 receiving pressure and service receipts, each source turn once.
    seen_turns, rel = set(), {"region_turns": 0, "dest_turns": 0, "dest_worse": 0, "dest_delta": 0.0,
                              "origin_turns": 0, "origin_relieved": 0, "origin_delta": 0.0, "arrivals": 0,
                              "departures": 0, "arr_rationed": 0, "arr_ration": 0.0, "res_rationed": 0,
                              "res_ration": 0.0}
    for snap in hist:
        rc = (snap.get("livelihoods") or {}).get("relocation_costs")
        if not rc or rc.get("source_turn") in seen_turns:
            continue
        seen_turns.add(rc.get("source_turn"))
        for r in rc.get("regions") or []:
            delta = r["pressure_after"] - r["pressure_before"]
            rel["region_turns"] += 1; rel["arrivals"] += r["arrivals"]; rel["departures"] += r["departures"]
            if r["arrivals"] > r["departures"]:
                rel["dest_turns"] += 1; rel["dest_delta"] += delta; rel["dest_worse"] += delta > 0
            elif r["departures"] > r["arrivals"]:
                rel["origin_turns"] += 1; rel["origin_delta"] += delta; rel["origin_relieved"] += delta < 0
        for v in rc.get("services") or []:
            if v.get("arrivals_mean_ration") is not None and v.get("residents_mean_ration") is not None:
                rel["arr_rationed"] += v["arrivals_rationed"]; rel["arr_ration"] += v["arrivals_mean_ration"] * v["arrivals_rationed"]
                rel["res_rationed"] += v["residents_rationed"]; rel["res_ration"] += v["residents_mean_ration"] * v["residents_rationed"]
    if seen_turns:
        m["relocation_pressure"] = rel
    storage = ((b["world_state"].get("grain_reserves") or {}).get("storage") or {})
    assets = [a for a in storage.get("assets") or [] if a and a.get("capacity", 0) > 0]
    if storage:
        m["storage_end"] = {"assets": len(assets), "capacity": sum(a["capacity"] for a in assets),
                            "mean_condition": (mean(a["condition"] for a in assets) if assets else None)}
    for name in COUNTED:
        record = (last.get("livelihoods") or {}).get(name)
        if record and isinstance(record.get("counters"), dict):
            m.setdefault("counters", {})[name] = record["counters"]
    return m


def run(out: Path, arms: dict, arm: str, stratum: str, seed: int, extra: list[str], keep: bool) -> dict:
    d = (out / "runs" / f"{arm}-{stratum}{seed}").resolve()
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    flags, _control, tuning = arms[arm]
    flags = list(flags)
    if tuning:
        (d / "tuning.yaml").write_text(_yaml(tuning))
        flags += ["--tuning", str(d / "tuning.yaml")]
    cmd = [PY, "-m", "chronicler.main", "--seed", str(seed), *BASE, *extra, *flags,
           "--output", str(d / "chronicle.md"), "--state", str(d / "state.json")]
    env = _run_env()
    t0 = time.time()
    p = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True)
    row = {"arm": arm, "stratum": stratum, "seed": seed, "rc": p.returncode, "wall_s": round(time.time() - t0, 1)}
    if p.returncode != 0:
        row["error"] = p.stderr[-2000:]
    elif arms is ARMS3:
        row.update(metrics3(d / "chronicle_bundle.json", flags))
    else:
        row.update(metrics(d / "chronicle_bundle.json"))
    if not keep:
        shutil.rmtree(d)
    return row


def _run_env() -> dict:
    """Every run imports this checkout's ``src`` (never an installed copy)."""
    return dict(os.environ, PYTHONHASHSEED="0", RAYON_NUM_THREADS="1", CHRONICLER_QUIET="1",
                PYTHONPATH=f"{REPO}/src")


_WHICH = ("import hashlib, chronicler, chronicler_agents.chronicler_agents as m\n"
          "print(chronicler.__file__)\n"
          "print(m.__file__, hashlib.sha256(open(m.__file__, 'rb').read()).hexdigest())\n")


def source_identity(out: Path) -> str:
    """Record (and check) the source tree, commit and native extension the runs use."""
    p = subprocess.run([PY, "-c", _WHICH], cwd=REPO, env=_run_env(), capture_output=True, text=True)
    lines = p.stdout.split("\n")
    if p.returncode != 0 or not lines[0].startswith(f"{REPO}/src/"):
        raise SystemExit(f"runs would not import {REPO}/src: {p.stdout} {p.stderr[-500:]}")
    rev = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True).stdout.strip()
    text = (f"source {rev}{' (dirty)' if dirty else ''}\nchronicler {lines[0]}\n"
            f"native {lines[1]}\ninterpreter {PY}\n")
    (out / "source.txt").write_text(text)
    return text


def run_main(argv):
    ap = argparse.ArgumentParser(prog="livelihoods_screens.py run")
    ap.add_argument("out"); ap.add_argument("--seeds", default="all"); ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--sprint", type=int, choices=sorted(SPRINTS), default=1)
    ap.add_argument("--arms", default=None)
    ap.add_argument("--cohort", choices=("held", "pilot"), default="held",
                    help="sprint 3: the held cohort or the timing pilot on development worlds")
    a = ap.parse_args(argv)
    sprint = SPRINTS[a.sprint]
    if a.cohort == "pilot" and "pilot" not in sprint:
        raise SystemExit(f"sprint {a.sprint} has no pilot cohort")
    arms, all_strata = sprint["arms"], sprint["pilot" if a.cohort == "pilot" else "strata"]
    check_counted()
    if a.sprint == 3:
        check_extractor3()
    chosen = a.arms.split(",") if a.arms else list(arms)
    unknown = [arm for arm in chosen if arm not in arms]
    if unknown:
        raise SystemExit(f"unknown arms for sprint {a.sprint}: {unknown}")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    print(source_identity(out), end="", flush=True)
    strata = list(all_strata) if a.seeds == "all" else [a.seeds]
    jobs = []
    for name in strata:
        for i, (tag, seed, extra) in enumerate(all_strata[name]):
            for arm in chosen:
                jobs.append((arms, arm, tag, seed, extra, i == 0))
    t0 = time.time()
    with open(out / "metrics.jsonl", "a") as fh, ThreadPoolExecutor(a.jobs) as ex:
        for row in ex.map(lambda j: run(out, *j), jobs):
            fh.write(json.dumps(row) + "\n"); fh.flush()
            print(row["arm"], row["stratum"], row["seed"], row["rc"], row["wall_s"], flush=True)
    print("total wall", round(time.time() - t0, 1))


def report_main(argv):
    ap = argparse.ArgumentParser(prog="livelihoods_screens.py report")
    ap.add_argument("metrics"); ap.add_argument("--sprint", type=int, choices=sorted(SPRINTS), default=1)
    a = ap.parse_args(argv)
    sprint_no, sprint = a.sprint, SPRINTS[a.sprint]
    rows = [json.loads(l) for l in open(a.metrics)]

    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    arms = list(dict.fromkeys(r["arm"] for r in rows))
    strata = sprint["labels"]
    fails = [r for r in rows if r["rc"] != 0]
    out = []
    out.append(f"Runs: {len(rows)}; failed: {len(fails)}; wall seconds total {sum(r['wall_s'] for r in rows):.0f}")
    for f in fails:
        out.append(f"- FAILED {f['arm']} {f['stratum']}{f['seed']}: {f.get('error','')[-300:]}")


    def rng(vals):
        return f"{mean(vals):+.1f} [{min(vals):+.0f}, {max(vals):+.0f}]" if vals else "n/a"


    out.append("\n### Paired differences vs each arm's control (mean [min, max] over worlds)\n")
    out.append("| Arm | Control | Stratum | Worlds | Population | Treasury |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for arm in arms:
        control = sprint["arms"].get(arm, (None, None, None))[1]
        if control is None:
            continue
        for s in strata:
            seeds = sorted({r["seed"] for r in rows if r["stratum"] == s})
            dp, dt = [], []
            for seed in seeds:
                a, o = by.get((arm, s, seed)), by.get((control, s, seed))
                if a and o and a["rc"] == 0 and o["rc"] == 0:
                    dp.append(a["population"] - o["population"]); dt.append(a["treasury"] - o["treasury"])
            out.append(f"| {arm} | {control} | {s} | {len(dp)} | {rng(dp)} | {rng(dt)} |")

    if sprint_no == 2:
        out.append("\n### Preregistered primary outcomes: per-world paired differences\n")
        out.extend(paired_table(rows, PAIRED2))
    if sprint_no == 3:
        out.append("\n### Preregistered primary outcomes, world by world (arm minus control, or the arm alone)\n")
        out.extend(per_world_table(rows, PAIRED3, strata))
        out.append("\n### Recovery-skills funnels (mean per world [min, max]; worlds with zero)\n")
        for s in strata:
            out.append(f"\n**{strata[s]}**\n")
            for arm in arms:
                rs = [r for r in rows if r["arm"] == arm and r["stratum"] == s and r["rc"] == 0]
                for name in OUTCOMES3:
                    cs = [r["rs"][name] for r in rs if name in r.get("rs", {})]
                    if not cs:
                        continue
                    cells = []
                    for k in OUTCOMES3[name]:
                        v = [c[k] for c in cs]
                        cells.append(f"{k} {mean(v):.4g} [{min(v):.4g}, {max(v):.4g}] z{sum(x == 0 for x in v)}")
                    out.append(f"- {arm} / {name} ({len(cs)} worlds): " + ", ".join(cells))
    out.append("\n### Activation funnels and primary outcomes (sum or mean per world)\n")
    for s in strata:
        out.append(f"\n**{strata[s]}**\n")
        for arm in arms:
            rs = [r for r in rows if r["arm"] == arm and r["stratum"] == s and r["rc"] == 0]
            if not rs:
                continue
            parts = []
            if any("workshops" in r for r in rs):
                w = [r["workshops"] for r in rs]
                act = sum(1 for x in w if x["operating"] > 0)
                parts.append(f"workshops: worlds operating {act}/{len(w)}, site-turns {mean(x['site_turns'] for x in w):.0f}, "
                             f"operating {mean(x['operating'] for x in w):.0f}, building {mean(x['building'] for x in w):.0f}, "
                             f"idle {mean(x['idle'] for x in w):.0f}, work alloc/real {mean(x['alloc'] for x in w):.1f}/{mean(x['real'] for x in w):.1f}, "
                             f"site-region craft out {mean(x['out'] for x in w):.1f}, paid {mean(x['paid'] for x in w):.0f}")
            if any("food" in r for r in rs):
                f = [r["food"] for r in rs]
                sp = sum(x["sp"] for x in f) / max(1, sum(x["pp"] for x in f))
                sr = sum(x["sr"] for x in f) / max(1, sum(x["pr"] for x in f))
                sc = sum(x["sc"] for x in f) / max(1, sum(x["pc"] for x in f))
                poorer_worse = sum(1 for x in f if x["pp"] and x["pr"] and x["sp"] / x["pp"] > x["sr"] / x["pr"])
                parts.append(f"food: scarce region-turns/world {mean(x['scarce'] for x in f):.0f}, mean shortfall poorer {sp:.3f} vs richer {sr:.3f} "
                             f"(poorer worse in {poorer_worse}/{len(f)} worlds), children {sc:.3f}, relief to targeted/world {mean(x['relief_t'] for x in f):.2f} "
                             f"(unknown region-turns {sum(x.get('relief_unknown', 0) for x in f)}), "
                             f"unallocated/world {mean(x['unalloc'] for x in f):.1f}")
            if any("timber" in r for r in rs):
                t = [r["timber"] for r in rs]
                parts.append(f"timber: extraction/world {mean(x['extraction'] for x in t):.1f}, regrowth {mean(x['regrowth'] for x in t):.1f}, "
                             f"cleared {mean(x['cleared'] for x in t):.1f}, overdraft {mean(x['overdraft'] for x in t):.3f}, "
                             f"capped slot-turns {mean(x['capped'] for x in t):.1f} (worlds binding {sum(1 for x in t if x['capped'])}/{len(t)})")
            if any("convoys" in r for r in rs):
                c = [r["convoys"] for r in rs]
                keys = ("eligible", "no_budget", "unaffordable", "dispatched", "arrived", "delivered", "captured", "lost", "returned", "stranded", "escorted", "escort_wasted")
                parts.append("convoys (sum over worlds): " + ", ".join(f"{k} {sum(x.get(k, 0) for x in c):.0f}" for k in keys))
            if any("academy" in r for r in rs):
                a = [r["academy"] for r in rs if "academy" in r]
                parts.append("academy supplies (mean/world): " + ", ".join(
                    f"{k} {mean(x[k] for x in a):.4g}" for k in ("founded", "purchased", "used", "lost",
                                                                 "teaching_receipts", "work_delivered", "learners_delivered")))
            pays = [r["counters"]["workshop_payroll"] for r in rs if "workshop_payroll" in r.get("counters", {})]
            if pays:   # wages are milli-units; replaced income is in wealth units
                net = [c.get("wages_paid", 0) / 1000 - c.get("income_replaced", 0) for c in pays]
                parts.append(f"payroll crew net income (wages paid - income replaced, wealth units): "
                             f"mean/world {mean(net):+.3f} [{min(net):+.3f}, {max(net):+.3f}]")
            rel = [r["relocation_pressure"] for r in rs if "relocation_pressure" in r]
            if rel:
                arr = sum(x["arr_ration"] for x in rel) / max(1, sum(x["arr_rationed"] for x in rel))
                res = sum(x["res_ration"] for x in rel) / max(1, sum(x["res_rationed"] for x in rel))
                parts.append("relocation pressure (sum over worlds): "
                             f"destination region-turns {sum(x['dest_turns'] for x in rel)} (more crowded "
                             f"{sum(x['dest_worse'] for x in rel)}, mean change "
                             f"{sum(x['dest_delta'] for x in rel) / max(1, sum(x['dest_turns'] for x in rel)):+.4f}), "
                             f"origin region-turns {sum(x['origin_turns'] for x in rel)} (relieved "
                             f"{sum(x['origin_relieved'] for x in rel)}, mean change "
                             f"{sum(x['origin_delta'] for x in rel) / max(1, sum(x['origin_turns'] for x in rel)):+.4f}); "
                             f"arrivals' mean ration {arr:.3f} vs residents' {res:.3f}"
                             + ("" if sum(x["arr_rationed"] for x in rel) else " (no rationed arrivals: unknown)"))
            st = [r["storage_end"] for r in rs if "storage_end" in r]
            if st:
                cond = [x["mean_condition"] for x in st if x["mean_condition"] is not None]
                parts.append(f"granary storage at end (mean/world): assets {mean(x['assets'] for x in st):.2f}, "
                             f"capacity {mean(x['capacity'] for x in st):.1f}, condition "
                             + (f"{mean(cond):.3f} ({len(cond)} worlds with assets)" if cond else "unknown (no assets)"))
            for name, keys in FUNNEL_KEYS.items():
                cs = [r["counters"][name] for r in rs if name in r.get("counters", {})]
                if cs:
                    keys = keys or sorted({k for c in cs for k in c})
                    parts.append(f"{name} (mean/world, {len(cs)} worlds): "
                                 + ", ".join(f"{k} {mean(c.get(k, 0) for c in cs):.4g}" for k in keys))
            if parts:
                out.append(f"- {arm}: " + "; ".join(parts))
    print("\n".join(out))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("run", "report"):
        print(__doc__)
        return 0 if not argv else 2
    if argv[0] == "run":
        run_main(argv[1:])
    else:
        report_main(argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
