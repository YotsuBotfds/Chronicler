"""Productive-recovery checkpoint-1 screens (PL6a): run, report and check.

    python scripts/productive_recovery_screens.py run OUT_DIR --cohort pilot|held [--jobs 3] [--arms a,b] [--seeds all|template|procedural] [--keep-first] [--resume]
    python scripts/productive_recovery_screens.py report OUT_DIR/metrics.jsonl
    python scripts/productive_recovery_screens.py check [--metrics OUT_DIR/metrics.jsonl --cohort pilot|held]

Run with the native interpreter whose extension matches the source under
test (every arm is hybrid). Arms, cohorts and outcomes are preregistered in
docs/superpowers/progress/productive-recovery-screens-cp1.md; worlds are the
units. Every arm is compared with its declared control on the same world.

The extractor reads package lifetime counters from the dated snapshot records
(``history[i]["livelihoods"][<package>]``) and world measures from the
bundle. Every counter it reads is checked against the package's declared
``COUNTERS`` in this checkout's source, and every run must hold exactly the
packages and modes its flags enable. A missing or malformed outcome makes the
run a visible failure (rc 3, the run and the reasons named); ``run`` and
``check --metrics`` then exit with code 3. Nothing missing reads as zero.

The shared helpers (base flags, the run environment that imports this
checkout's ``src``, source identity, shared metrics and the world-by-world
table) come from ``livelihoods_screens.py``, whose sprint 1-3 behaviour is
unchanged. A held run refuses unless the preregistration's status line reads
FROZEN. Raw outputs are deleted after extraction (``--keep-first`` keeps the
first world of each stratum). ``--resume`` continues an interrupted run in the
same OUT_DIR: it runs only the arms and worlds without a row, and refuses
unless the recorded source, ``chronicler`` path, extension and interpreter
are the current ones; no recorded run is repeated.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent))
import livelihoods_screens as LS  # noqa: E402  (shared screen helpers)

REPO = LS.REPO
PY = LS.PY
PREREGISTRATION = Path(REPO) / "docs/superpowers/progress/productive-recovery-screens-cp1.md"

# --- Arms -------------------------------------------------------------------------

#: Base for every arm: the sprint base (``--turns 200 --agents hybrid --simulate-only
#: --grain-reserves --public-grain-shipments``), the sprint-2/3 base and workshops
#: in their default operate mode.
BASE = [*LS.BASE, *LS.BASE2, "--workshops"]
TURNS = int(BASE[BASE.index("--turns") + 1])
PROCEDURAL = list(LS.PROCEDURAL)
_WEAR = ["--operating-wear"]
_RP = ["--operating-wear", "--repair-projects", "--timber-stock"]
_L9 = [*_RP, "--local-budgets"]
_CH = [*_RP, "--timber-supply", "--recovery-crews", "--veteran-reintegration"]
#: Arm -> (flags added to the base, control arm). ``W`` is the root.
ARMS: dict[str, tuple[list[str], str | None]] = {
    "W": ([], None),
    "W_wear": (_WEAR, "W"),
    "TR2": (["--apprenticeship"], "NQ2"),
    "NQ2": (["--apprenticeship", "--apprenticeship-mode", "no_qualification"], "W_wear"),
    "RP": (_RP, "W_wear"),
    "TS": ([*_RP, "--timber-supply"], "TS_cost"),
    "TS_cost": ([*_RP, "--timber-supply", "--timber-supply-mode", "cost_only"], "RP"),
    "RC": ([*_RP, "--recovery-crews"], "RC_unpaid"),
    "RC_unpaid": ([*_RP, "--recovery-crews", "--recovery-crew-mode", "unpaid"], "RP"),
    "L9": (_L9, "RP"),
    "MO": ([*_L9, "--maintenance-obligation"], "MO_ro"),
    "MO_ro": ([*_L9, "--maintenance-obligation", "--maintenance-obligation-mode", "reserve_only"], "L9"),
    "CH": (_CH, "CH_rec"),
    "CH_rec": ([*_CH, "--veteran-mode", "record_only"], "RP"),
}

#: Livelihoods switches the base or an arm enables: switch -> (snapshot key, mode
#: option, default mode). A package without modes has neither.
PACKAGES: dict[str, tuple[str, str | None, str | None]] = {
    "--workshops": ("workshops", "--workshop-mode", "operate"),
    "--operating-wear": ("operating_wear", None, None),
    "--apprenticeship": ("apprenticeship", "--apprenticeship-mode", "train"),
    "--repair-projects": ("repair_projects", "--repair-mode", "repair"),
    "--timber-stock": ("timber_stock", None, None),
    "--timber-supply": ("timber_supply", "--timber-supply-mode", "supply"),
    "--recovery-crews": ("recovery_crews", "--recovery-crew-mode", "paid"),
    "--local-budgets": ("local_budgets", "--local-budget-mode", "bargained"),
    "--maintenance-obligation": ("maintenance_obligation", "--maintenance-obligation-mode", "reserve"),
    "--veteran-reintegration": ("veteran_reintegration", "--veteran-mode", "priority"),
}

# --- Seeds (per stratum; procedural 32x10 seed numbers are separate worlds) --------

PILOT = {"template": (5,), "procedural": (19,)}
HELD = {"template": tuple(range(701, 707)), "procedural": tuple(range(801, 807))}
#: Earlier held cohorts and pilots: never run again.
NEVER_RUN = {"template": frozenset({2, *range(101, 107), *range(301, 307), *range(501, 507)}),
             "procedural": frozenset({*range(201, 207), *range(401, 407), *range(601, 607)})}
#: This phase's other held cohorts (checkpoints 2 and 3).
RESERVED = {"template": frozenset({*range(711, 717), *range(721, 727)}),
            "procedural": frozenset({*range(811, 817), *range(821, 827)})}
#: Development worlds, inspected freely by the lanes.
DEVELOPMENT = {"template": frozenset({1, 3, 7, 9, 11, 23, 42}),
               "procedural": frozenset({7, 11, 13, 17, 21, 31, 302, 303})}
TAGS = {"template": "t", "procedural": "p"}
COHORTS = {"pilot": PILOT, "held": HELD}
LABELS = {"pilot": {"t": "template 8x4 (seed 5)", "p": "procedural 32x10 (seed 19)"},
          "held": {"t": "template 8x4 (seeds 701-706)", "p": "procedural 32x10 (seeds 801-806)"}}

# --- Counters the report reads (validated against each package's COUNTERS) --------

OUTCOMES: dict[str, tuple[str, ...]] = {
    "operating_wear": ("turns", "operating_site_turns", "wear", "upkeep_offset", "net_wear",
                       "full_offset_site_turns", "covered_site_turns", "repairs"),
    "apprenticeship": ("operating_site_turns", "covered_site_turns", "full_offset_site_turns",
                       "graduate_crew_turns", "qualified_crew_turns", "graduates", "graduates_died",
                       "completions", "completions_granted", "qualified_apprenticeship", "qualified_service",
                       "upkeep_offset", "upkeep_offset_apprenticeship", "upkeep_offset_service",
                       "upkeep_offset_graduates", "wear", "enrolled", "veterans_enrolled",
                       "apprentice_turns_attended", "apprentice_turns_on_crew", "apprentice_turns_attached",
                       "income_forgone", "transferred", "end_long_absence", "end_died", "end_completed"),
    "repair_projects": ("opened_granary", "opened_workshop", "progress_turns", "stalled_turns",
                        "stalled_no_timber", "stalled_no_coins", "stalled_no_labor", "stalled_no_envelope",
                        "stalled_no_people", "work_delivered", "granary_work", "workshop_work", "timber_used",
                        "charged", "wages_milli", "crew_person_turns", "veterans_placed", "completed"),
    "timber_supply": ("launched", "launched_veterans", "delivered_expeditions", "ended", "need_rows", "gap",
                      "cut", "delivered", "lost", "abandoned_cargo", "released", "store_held", "store_returned",
                      "person_turns", "away_requested", "away_delivered", "crew_labor", "wages_milli", "charged",
                      "income_withheld", "ended_wages_milli", "ended_person_turns", "ended_away", "ended_cut",
                      "ended_delivered", "recalls", "unpaid_turns", "veterans_placed",
                      "refused_no_forest", "refused_too_far", "refused_forest_depleted", "refused_forest_busy",
                      "refused_no_crew", "refused_no_coins"),
    "recovery_crews": ("granary_crews", "granary_crew_person_turns", "granary_work_planned", "granary_work_named",
                       "granary_crew_short", "granary_no_crew", "granary_coin_cost_milli", "granary_wages_due_milli",
                       "granary_wages_milli", "granary_sunk_milli", "workshop_crews", "workshop_crew_person_turns",
                       "workshop_members_veteran", "farm_time_removed", "income_replaced", "veterans_placed"),
    "maintenance_obligation": ("decision_civ_turns", "planned_coins", "capped_coins", "reserved_coins",
                               "cap_binding", "execution_civ_turns", "used_coins", "returned_coins",
                               "envelope_spent_coins", "charged_coins"),
    "veteran_reintegration": ("captured", "offered", "placements", "placements_crew", "placements_apprentice",
                              "placements_repair", "people_placed", "placed_prioritised", "waiting_turns",
                              "unmet_no_site", "unmet_site_idle", "unmet_not_crew_eligible", "unmet_crew_full"),
}

#: L9 award groups reported for crowding out (services of the declared L9 providers).
L9_GROUPS = {"workshop": ("workshop",), "granary": ("granary_maintain", "granary_expand"), "relief": ("relief",)}
REPAIRS_SERVICE = "repairs"


def _src() -> None:
    if f"{REPO}/src" not in sys.path:
        sys.path.insert(0, f"{REPO}/src")


def declared_counters() -> dict[str, frozenset[str]]:
    """Each counted package's declared lifetime counter names, from this checkout's source."""
    _src()
    from chronicler import apprenticeship_state, maintenance_obligation_state, operating_wear_state
    from chronicler import recovery_crews_state, repair_projects_state, timber_supply_state
    from chronicler import veteran_reintegration_state
    mods = {"operating_wear": operating_wear_state, "apprenticeship": apprenticeship_state,
            "repair_projects": repair_projects_state, "timber_supply": timber_supply_state,
            "recovery_crews": recovery_crews_state, "maintenance_obligation": maintenance_obligation_state,
            "veteran_reintegration": veteran_reintegration_state}
    return {name: frozenset(mod.COUNTERS) for name, mod in mods.items()}


def declared_services() -> frozenset[str]:
    """Every service an L9 provider of this checkout can award."""
    _src()
    from importlib import import_module
    from chronicler import local_budgets, local_budgets_state
    out = set(local_budgets_state.SERVICES)
    for path in local_budgets.PROVIDERS:
        module, attr = path.split(":")
        out.update(getattr(getattr(import_module(module), attr), "services", ()) or ())
    return frozenset(out)


def expected_packages(flags) -> dict[str, str | None]:
    """{snapshot key: mode} of the livelihoods packages the base plus ``flags`` enable
    (None for a package without modes)."""
    flags = [*BASE, *flags]
    out = {}
    for flag, (name, mode_flag, default) in PACKAGES.items():
        if flag in flags:
            out[name] = (flags[flags.index(mode_flag) + 1] if mode_flag and mode_flag in flags else default)
    return out


def _known_flags() -> set[str]:
    known = set(BASE) | set(PACKAGES)
    for _name, mode_flag, _default in PACKAGES.values():
        if mode_flag:
            known.add(mode_flag)
    return known


def check_seeds() -> None:
    """Pilot and held seeds are disjoint from every earlier cohort and pilot, from
    this phase's other reserved cohorts, from development worlds and from each other
    (per stratum), and the earlier cohorts include every sprint 1-3 cohort and pilot."""
    problems = []
    earlier = {"template": set(), "procedural": set()}
    for strata in (LS.STRATA, LS.STRATA2, LS.STRATA3, LS.PILOT3):
        for stratum, rows in strata.items():
            earlier[stratum].update(seed for _t, seed, _x in rows)
    for stratum in ("template", "procedural"):
        # The sprint-3 pilot ran procedural 7, a development world; every other
        # earlier seed must be listed as never run.
        missing = earlier[stratum] - NEVER_RUN[stratum] - DEVELOPMENT[stratum]
        if missing:
            problems.append(f"{stratum}: earlier cohort seeds {sorted(missing)} not in NEVER_RUN")
        pilot, held = set(PILOT[stratum]), set(HELD[stratum])
        for label, seeds in (("pilot", pilot), ("held", held)):
            for other_label, other in (("earlier cohorts and pilots", NEVER_RUN[stratum] | earlier[stratum]),
                                       ("reserved cohorts", RESERVED[stratum]),
                                       ("development worlds", DEVELOPMENT[stratum])):
                if seeds & other:
                    problems.append(f"{stratum} {label} seeds {sorted(seeds & other)} are in the {other_label}")
        if pilot & held:
            problems.append(f"{stratum}: pilot and held overlap {sorted(pilot & held)}")
    if problems:
        raise SystemExit("seed cohorts are not disjoint: " + "; ".join(problems))


def check_extractor() -> None:
    """Every counter the report reads is declared by its package, every package is a
    livelihoods switch whose option and default mode match the registry, every arm's
    flags are known and its control exists (a tree rooted at W), and every outcome
    names known arms. Raises SystemExit naming each problem."""
    _src()
    from chronicler.livelihoods import LIVELIHOODS_ARG_KEYS, LIVELIHOODS_CHOICES
    from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES
    declared = declared_counters()
    problems = [f"{name} is not a livelihoods switch" for name in OUTCOMES if name not in LIVELIHOODS_SWITCHES]
    problems += [f"{name}.{key} is not a declared counter" for name, keys in OUTCOMES.items()
                 for key in keys if key not in declared.get(name, ())]
    for flag, (name, mode_flag, default) in PACKAGES.items():
        dest = flag[2:].replace("-", "_")
        if dest != name or name not in LIVELIHOODS_SWITCHES or dest not in LIVELIHOODS_ARG_KEYS:
            problems.append(f"{flag} is not the switch of livelihoods package {name}")
        if mode_flag is not None:
            choices = LIVELIHOODS_CHOICES.get(mode_flag[2:].replace("-", "_"))
            if not choices or choices[0] != default:
                problems.append(f"{mode_flag}: default {default!r} is not the registry default {choices}")
        elif any(k.startswith(name) and k != name for k in LIVELIHOODS_CHOICES):
            problems.append(f"{name} has registered modes the screen does not check")
    known = _known_flags()
    for arm, (flags, control) in ARMS.items():
        bad = [f for f in flags if f.startswith("--") and f not in known]
        if bad:
            problems.append(f"arm {arm}: unknown flags {bad}")
        if control is not None and control not in ARMS:
            problems.append(f"arm {arm}: unknown control {control}")
        seen, a = set(), arm
        while a is not None and a in ARMS and a not in seen:
            seen.add(a)
            a = ARMS[a][1]
        if a is not None:
            problems.append(f"arm {arm}: its controls do not lead to the root W")
    roots = [arm for arm, (_f, control) in ARMS.items() if control is None]
    if roots != ["W"]:
        problems.append(f"the root arms are {roots}, not ['W']")
    for label, arm, control, _f in PAIRED:
        problems += [f"outcome {label!r}: unknown arm {a}" for a in (arm, control) if a and a not in ARMS]
    for label, arm, control, _f in PAIRED:
        if control is not None and (arm, control) not in DECLARED_PAIRS:
            problems.append(f"outcome {label!r}: {arm} - {control} is not a declared comparison")
    if problems:
        raise SystemExit("productive-recovery extractor does not match the source: " + "; ".join(problems))


def check_arm_flags() -> None:
    """Every arm's command line parses and passes the livelihoods prerequisite checks
    on a constructed hybrid world with cities, grain reserves and storage, enabling
    exactly the packages and modes ``expected_packages`` names."""
    _src()
    from chronicler.cities_state import CityState
    from chronicler.grain_reserves import set_grain_reserves_enabled
    from chronicler.grain_storage import enable_storage
    from chronicler.livelihoods import configure_livelihoods
    from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES
    from chronicler.main import _build_parser
    from chronicler.world_gen import generate_world
    parser = _build_parser()
    problems = []
    for arm, (flags, _control) in ARMS.items():
        for extra in ([], PROCEDURAL):
            args = parser.parse_args(["--seed", "1", *BASE, *extra, *flags])
            world = generate_world(seed=11, num_regions=6, num_civs=2)
            world.cities = CityState()
            world.agent_mode = "hybrid"
            set_grain_reserves_enabled(world, True)
            enable_storage(world)
            try:
                configure_livelihoods(world, args, agent_mode=args.agents)
            except ValueError as error:
                problems.append(f"arm {arm}: {error}")
                continue
            state = world.livelihoods
            enabled = {}
            for name in LIVELIHOODS_SWITCHES:
                sub = getattr(state, name, None) if state is not None else None
                if sub is not None and getattr(sub, "enabled", True):
                    enabled[name] = getattr(sub, "mode", None)
            if enabled != expected_packages(flags):
                problems.append(f"arm {arm}: enables {enabled}, expected {expected_packages(flags)}")
    if problems:
        raise SystemExit("arm flags do not configure as declared: " + "; ".join(problems))


# --- Extraction -------------------------------------------------------------------

def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _site_conditions(sites) -> list[float]:
    """Condition of built open workshop sites (sprint 3's rule)."""
    return [x["condition"] for x in sites if x.get("status") == "open" and x.get("asset") != "building"
            and _num(x.get("condition"))]


def _granary_conditions(assets) -> list[float]:
    """Condition of granaries with capacity (sprint 3's rule)."""
    return [a["condition"] for a in assets if a and _num(a.get("capacity")) and a["capacity"] > 0
            and _num(a.get("condition"))]


def extract(bundle: dict, flags, declared: dict, services: frozenset[str]) -> tuple[dict, list[str]]:
    """The checkpoint-1 outcomes of one run and the reasons any is missing or malformed.

    The run must have one snapshot per turn (1..TURNS), and the last snapshot must hold
    exactly the packages the arm enables, each observed for the completed turn, in the
    arm's mode, with numeric counters its package declares. Every dated frame the
    report sums (granaries, workshop sites and receipts, food accounting, woodcutting
    receipts, L9 decisions) must be present in every snapshot. Any failure is returned,
    never read as zero. A measure of an event that never happened (no built site, no
    cutting turn, no ended expedition) is None: unknown, shown as such."""
    hist = bundle.get("history") or []
    if not hist:
        return {}, ["no snapshots"]
    problems: list[str] = []
    turns = [s.get("turn") for s in hist]
    if turns != list(range(1, TURNS + 1)):
        problems.append(f"snapshots are not turns 1..{TURNS} (got {len(turns)}, last {turns[-1]!r})")
    last = hist[-1]
    liv = last.get("livelihoods") or {}
    expected = expected_packages(flags)
    present = sorted(k for k in liv if k != "schema_version")
    if present != sorted(expected):
        problems.append(f"packages {present} recorded, expected exactly {sorted(expected)}")
    out: dict = {"packages": dict(expected), "pk": {}}
    for name, mode in expected.items():
        rec = liv.get(name)
        if not isinstance(rec, dict):
            problems.append(f"{name}: no record in the last snapshot")
            continue
        if rec.get("source_turn") != last.get("turn", 0) - 1:
            problems.append(f"{name}: source_turn {rec.get('source_turn')!r} is not the completed turn")
        if mode is not None and rec.get("mode") != mode:
            problems.append(f"{name}: mode {rec.get('mode')!r}, expected {mode!r}")
        if name not in OUTCOMES:
            continue
        counters = rec.get("counters")
        if not isinstance(counters, dict):
            problems.append(f"{name}: counters missing")
            continue
        unknown = sorted(set(counters) - declared[name])
        if unknown:
            problems.append(f"{name}: undeclared counters {unknown[:5]}")
        bad = sorted(k for k, v in counters.items() if not _num(v))
        if bad:
            problems.append(f"{name}: non-numeric counters {bad[:5]}")
        # A declared counter absent from the record was never incremented: every
        # record starts empty when its switch is enabled (the sprint-3 rule).
        out["pk"][name] = {k: counters.get(k, 0) for k in OUTCOMES[name]}

    regions = (bundle.get("world_state") or {}).get("regions") or []
    n_regions = len(regions)
    if not n_regions:
        problems.append("world state has no regions")

    # Granaries (grain storage is in the base), per turn and at the end.
    run_means, missing = [], []
    for snap in hist:
        assets = ((snap.get("grain_reserves") or {}).get("storage") or {}).get("assets")
        if not isinstance(assets, list):
            missing.append(snap.get("turn"))
            continue
        conds = _granary_conditions(assets)
        if conds:
            run_means.append(mean(conds))
    if missing:
        problems.append(f"granary storage missing at turns {missing[:5]}")
    end_assets = (((bundle.get("world_state") or {}).get("grain_reserves") or {}).get("storage") or {}).get("assets")
    if not isinstance(end_assets, list):
        problems.append("granary storage missing from the final world state")
        end_assets = []
    end_conds = _granary_conditions(end_assets)
    out["granary"] = {"run_mean": mean(run_means) if run_means else None,
                      "end": mean(end_conds) if end_conds else None, "turns_with_assets": len(run_means)}

    # Workshop sites (workshops are in the base), per turn and at the end; lump repairs.
    run_means, missing, lump = [], [], 0
    for snap in hist:
        ws = (snap.get("livelihoods") or {}).get("workshops") or {}
        sites, receipts = ws.get("sites"), ws.get("receipts")
        if not isinstance(sites, list) or not isinstance(receipts, list):
            missing.append(snap.get("turn"))
            continue
        conds = _site_conditions(sites)
        if conds:
            run_means.append(mean(conds))
        lump += sum(1 for r in receipts if (r.get("paid") or {}).get("repair"))
    if missing:
        problems.append(f"workshop sites or receipts missing at turns {missing[:5]}")
    end_sites = (((bundle.get("world_state") or {}).get("livelihoods") or {}).get("workshops") or {}).get("sites")
    if not isinstance(end_sites, list):
        problems.append("workshop sites missing from the final world state")
        end_sites = []
    end_conds = _site_conditions(end_sites)
    out["workshop"] = {"run_mean": mean(run_means) if run_means else None,
                       "end": mean(end_conds) if end_conds else None, "turns_with_sites": len(run_means)}
    out["lump_repairs"] = lump

    # Food accounting: unmet demand after public relief, per region over the run.
    short = [0.0] * n_regions
    demand = [0.0] * n_regions
    cells: dict[tuple[int, int], tuple[float, float, float]] = {}
    bad_turns = []
    for snap in hist:
        fa = snap.get("food_accounting") or {}
        rows = fa.get("regions")
        if fa.get("source_turn") != snap.get("turn", 0) - 1 or not isinstance(rows, list) or len(rows) != n_regions:
            bad_turns.append(snap.get("turn"))
            continue
        for i, row in enumerate(rows):
            d = (row.get("native") or {}).get("demand")
            s = row.get("sufficiency_after_relief")
            if row.get("region_id") != i or not _num(d) or not _num(s):
                bad_turns.append(snap.get("turn"))
                break
            gap = d * max(0.0, 1.0 - min(1.0, s))
            short[i] += gap
            demand[i] += d
            cells[(fa["source_turn"], i)] = (gap, d, s)
    if bad_turns:
        problems.append(f"food accounting missing or incomplete at turns {bad_turns[:5]}")
    out["food"] = {"region_shortfall": short, "region_demand": demand,
                   "shortfall": sum(short), "demand": sum(demand)}

    # Woodcutting: sending regions, food on away turns, forest guard.
    if "timber_supply" in expected:
        homes, away = set(), [0.0] * n_regions
        a_cells = a_short = a_demand = a_below = 0
        share, missing = None, []
        for snap in hist:
            rec = (snap.get("livelihoods") or {}).get("timber_supply") or {}
            receipts = rec.get("receipts")
            if not isinstance(receipts, list):
                missing.append(snap.get("turn"))
                continue
            for r in receipts:
                home = r.get("home")
                if not isinstance(home, int) or not 0 <= home < n_regions or not _num(r.get("away_delivered")):
                    problems.append(f"timber_supply: malformed receipt at turn {snap.get('turn')}")
                    break
                homes.add(home)
                away[home] += r["away_delivered"]
                if r["away_delivered"] > 0:
                    cell = cells.get((r.get("turn"), home))
                    if cell is None:
                        problems.append(f"timber_supply: no food accounting for region {home} at turn {r.get('turn')}")
                        break
                    a_cells += 1
                    a_short += cell[0]
                    a_demand += cell[1]
                    a_below += cell[2] < 1.0
                if r.get("stage") == "cutting" and _num(r.get("stock_after")) and _num(r.get("capacity")) \
                        and r["capacity"] > 0:
                    value = r["stock_after"] / r["capacity"]
                    share = value if share is None else min(share, value)
        if missing:
            problems.append(f"timber_supply: receipts missing at turns {missing[:5]}")
        c = out["pk"].get("timber_supply") or {}
        ended = c.get("ended", 0)
        out["ts"] = {"homes": sorted(homes), "region_away": away, "away_cells": a_cells,
                     "away_shortfall": a_short, "away_demand": a_demand, "away_below_one": a_below,
                     "away_shortfall_share": (a_short / a_demand) if a_demand else None,
                     "min_stock_share": share,
                     "wages_per_ended": (c.get("ended_wages_milli", 0) / 1000 / ended) if ended else None,
                     "person_turns_per_ended": (c.get("ended_person_turns", 0) / ended) if ended else None,
                     "away_per_ended": (c.get("ended_away", 0) / ended) if ended else None}

    # L9 awards by service, summed over the dated decision frames.
    if "local_budgets" in expected:
        awards, missing = {}, []
        for snap in hist:
            decisions = ((snap.get("livelihoods") or {}).get("local_budgets") or {}).get("decisions")
            if not isinstance(decisions, list):
                missing.append(snap.get("turn"))
                continue
            for d in decisions:
                service_of = {p.get("pid"): p.get("service") for p in d.get("proposals") or []}
                for a in d.get("awards") or []:
                    service = service_of.get(a.get("pid"))
                    if service not in services or not _num(a.get("amount")):
                        problems.append(f"local_budgets: award {a!r} names no declared service at turn {snap.get('turn')}")
                        continue
                    awards[service] = awards.get(service, 0) + a["amount"]
        if missing:
            problems.append(f"local_budgets: decisions missing at turns {missing[:5]}")
        out["l9"] = {"awards": awards,
                     "other": sum(v for k, v in awards.items() if k != REPAIRS_SERVICE),
                     **{group: sum(awards.get(s, 0) for s in members) for group, members in L9_GROUPS.items()}}
    return out, problems


def metrics_row(bundle_path: Path, flags) -> dict:
    """The shared sprint metrics plus the validated checkpoint-1 outcomes.
    A missing or malformed outcome makes the row a visible failure (rc 3)."""
    _src()
    from chronicler.bundle_codec import load_bundle
    m = LS.metrics(bundle_path)
    extra, problems = extract(load_bundle(bundle_path), flags, declared_counters(), declared_services())
    m.update(extra)
    if "--timber-stock" in flags and "timber" not in m:
        problems.append("timber_stock: no totals in any snapshot")
    if problems:
        m["rc"], m["error"] = 3, "missing or malformed outcomes: " + "; ".join(problems)
    return m


# --- Outcomes ---------------------------------------------------------------------

_get = LS._get


def _c(r, pkg, key):
    """A counter of a package the arm enables (None if the row has none)."""
    return _get(r, "pk", pkg, key)


def _z(r, pkg, key):
    """A counter, or a structural zero for a package the arm's flags leave off (the
    extractor checked that such a package wrote no record)."""
    if "packages" not in r:
        return None
    return _c(r, pkg, key) if pkg in r["packages"] else 0.0


def _coins(v):
    return v / 1000 if v is not None else None


def _ratio(a, b):
    return (a / b) if (a is not None and b) else None


def _wages(r):
    """Coins paid to named repair workers: RS2 workshop crews, PL3 granary crews and PL1
    woodcutters (structural zero for a channel the arm leaves off)."""
    parts = [_z(r, "repair_projects", "wages_milli"), _z(r, "recovery_crews", "granary_wages_milli"),
             _z(r, "timber_supply", "wages_milli")]
    return None if any(p is None for p in parts) else sum(parts) / 1000


def _pair(key):
    return lambda r: _get(r, "pair", key)


#: Comparisons the arm table declares (arm, control) plus the cross-arm contrasts the
#: preregistration names; any other pairing in PAIRED is refused by check_extractor.
DECLARED_PAIRS = {(arm, control) for arm, (_f, control) in ARMS.items() if control} | {("CH", "RP"), ("TS", "RP")}

_GR = lambda r: _get(r, "granary", "run_mean")  # noqa: E731
_GE = lambda r: _get(r, "granary", "end")  # noqa: E731
_WR = lambda r: _get(r, "workshop", "run_mean")  # noqa: E731
_WE = lambda r: _get(r, "workshop", "end")  # noqa: E731

#: Preregistered outcomes: (label, arm, control or None, value). "[primary]" marks the
#: primary outcome of a comparison.
PAIRED = [
 # W_wear - W: the maintenance assumption alone.
 ("[primary] W_wear lump repairs (W_wear - W)", "W_wear", "W", lambda r: r.get("lump_repairs")),
 ("W_wear workshop mean condition, run mean (W_wear - W)", "W_wear", "W", _WR),
 ("W_wear workshop mean condition at end (W_wear - W)", "W_wear", "W", _WE),
 ("W_wear operating site-turns (W_wear - W)", "W_wear", "W", lambda r: _get(r, "workshops", "operating")),
 # TR2 - NQ2: training under the shared wear (RS1 rules version 2).
 ("[primary] TR2 share of operating site-turns covered by a qualified crew member (TR2 - NQ2)", "TR2", "NQ2",
  lambda r: _ratio(_c(r, "apprenticeship", "covered_site_turns"), _c(r, "apprenticeship", "operating_site_turns"))),
 ("TR2 graduate crew-turns (TR2 - NQ2)", "TR2", "NQ2", lambda r: _c(r, "apprenticeship", "graduate_crew_turns")),
 ("TR2 completions (TR2 - NQ2)", "TR2", "NQ2", lambda r: _c(r, "apprenticeship", "completions")),
 ("TR2 lump repairs (TR2 - NQ2)", "TR2", "NQ2", lambda r: r.get("lump_repairs")),
 ("TR2 upkeep offset (TR2 - NQ2)", "TR2", "NQ2", lambda r: _c(r, "apprenticeship", "upkeep_offset")),
 ("TR2 full-offset site-turns (TR2 - NQ2)", "TR2", "NQ2", lambda r: _c(r, "apprenticeship", "full_offset_site_turns")),
 ("TR2 qualified through apprenticeship (TR2 - NQ2)", "TR2", "NQ2", lambda r: _c(r, "apprenticeship", "qualified_apprenticeship")),
 ("TR2 qualified through service (TR2 - NQ2; crowding out)", "TR2", "NQ2", lambda r: _c(r, "apprenticeship", "qualified_service")),
 ("TR2 workshop mean condition, run mean (TR2 - NQ2)", "TR2", "NQ2", _WR),
 ("NQ2 lump repairs (NQ2 - W_wear; seats and attachment under the shared wear)", "NQ2", "W_wear", lambda r: r.get("lump_repairs")),
 ("NQ2 workshop mean condition, run mean (NQ2 - W_wear)", "NQ2", "W_wear", _WR),
 # RP - W_wear: RS2 workshop and granary repair under the shared wear.
 ("RP granary mean condition, run mean (RP - W_wear)", "RP", "W_wear", _GR),
 ("RP workshop mean condition, run mean (RP - W_wear)", "RP", "W_wear", _WR),
 # TS - TS_cost: timber supply against its cost-retaining control.
 ("[primary] TS granary mean condition, run mean (TS - TS_cost)", "TS", "TS_cost", _GR),
 ("TS granary mean condition at end (TS - TS_cost)", "TS", "TS_cost", _GE),
 ("TS RS2 no_timber stalled project-turns (TS - TS_cost)", "TS", "TS_cost", lambda r: _c(r, "repair_projects", "stalled_no_timber")),
 ("TS RS2 timber used (TS - TS_cost)", "TS", "TS_cost", lambda r: _c(r, "repair_projects", "timber_used")),
 ("TS timber cut (TS - TS_cost)", "TS", "TS_cost", lambda r: _c(r, "timber_supply", "cut")),
 ("TS timber delivered (TS - TS_cost)", "TS", "TS_cost", lambda r: _c(r, "timber_supply", "delivered")),
 ("TS transit loss (TS - TS_cost)", "TS", "TS_cost", lambda r: _c(r, "timber_supply", "lost")),
 ("TS abandoned cargo deposited at the forest (TS - TS_cost)", "TS", "TS_cost", lambda r: _c(r, "timber_supply", "abandoned_cargo")),
 ("TS L3 extraction (TS - TS_cost)", "TS", "TS_cost", lambda r: _get(r, "timber", "extraction")),
 ("TS minimum L3 stock share after a cutting turn (TS - TS_cost)", "TS", "TS_cost", lambda r: _get(r, "ts", "min_stock_share")),
 ("TS minimum L3 stock share after a cutting turn (TS)", "TS", None, lambda r: _get(r, "ts", "min_stock_share")),
 ("TS home farm labour away, farmer-turns (TS - TS_cost)", "TS", "TS_cost", lambda r: _c(r, "timber_supply", "away_delivered")),
 ("TS woodcutting wages, coins (TS - TS_cost)", "TS", "TS_cost", lambda r: _coins(_c(r, "timber_supply", "wages_milli"))),
 ("TS expeditions launched (TS - TS_cost)", "TS", "TS_cost", lambda r: _c(r, "timber_supply", "launched")),
 ("TS wages per ended expedition, coins (TS - TS_cost)", "TS", "TS_cost", lambda r: _get(r, "ts", "wages_per_ended")),
 ("TS person-turns per ended expedition (TS - TS_cost)", "TS", "TS_cost", lambda r: _get(r, "ts", "person_turns_per_ended")),
 ("TS farmer-turns away per ended expedition (TS - TS_cost)", "TS", "TS_cost", lambda r: _get(r, "ts", "away_per_ended")),
 ("TS food shortfall after relief in the regions that sent crews in either arm, food (TS - TS_cost)", "TS", "TS_cost", _pair("TS|TS_cost")),
 ("TS_cost food shortfall after relief in its crews' home regions, food (TS_cost - RP; the expeditions' cost without timber)", "TS_cost", "RP", _pair("TS_cost|RP")),
 ("TS food shortfall after relief in its crews' home regions, food (TS - RP; net)", "TS", "RP", _pair("TS|RP")),
 ("TS home-region shortfall share on turns a crew was away (TS)", "TS", None, lambda r: _get(r, "ts", "away_shortfall_share")),
 ("TS_cost home-region shortfall share on turns a crew was away (TS_cost)", "TS_cost", None, lambda r: _get(r, "ts", "away_shortfall_share")),
 ("TS_cost granary mean condition, run mean (TS_cost - RP)", "TS_cost", "RP", _GR),
 # RC - RC_unpaid: the wage channel to households.
 ("[primary] RC granary-crew wages paid to named members, coins (RC - RC_unpaid)", "RC", "RC_unpaid", lambda r: _coins(_c(r, "recovery_crews", "granary_wages_milli"))),
 ("RC granary coins sunk, coins (RC - RC_unpaid)", "RC", "RC_unpaid", lambda r: _coins(_c(r, "recovery_crews", "granary_sunk_milli"))),
 ("RC RS2 workshop-crew wages, coins (RC - RC_unpaid)", "RC", "RC_unpaid", lambda r: _coins(_c(r, "repair_projects", "wages_milli"))),
 ("RC granary mean condition, run mean (RC - RC_unpaid; expected near zero)", "RC", "RC_unpaid", _GR),
 ("RC granary mean condition at end (RC - RC_unpaid)", "RC", "RC_unpaid", _GE),
 ("RC_unpaid granary mean condition, run mean (RC_unpaid - RP; named crews' labour limit)", "RC_unpaid", "RP", _GR),
 ("RC_unpaid workshop mean condition, run mean (RC_unpaid - RP; the wider workshop pool)", "RC_unpaid", "RP", _WR),
 # MO - MO_ro: the maintenance obligation against its crowding-out control.
 ("[primary] MO workshop mean condition, run mean (MO - MO_ro)", "MO", "MO_ro", _WR),
 ("[primary] MO granary mean condition, run mean (MO - MO_ro)", "MO", "MO_ro", _GR),
 ("MO reserved, coins (MO - MO_ro)", "MO", "MO_ro", lambda r: _c(r, "maintenance_obligation", "reserved_coins")),
 ("MO reservation used, coins (MO - MO_ro)", "MO", "MO_ro", lambda r: _c(r, "maintenance_obligation", "used_coins")),
 ("MO reservation returned, coins (MO - MO_ro)", "MO", "MO_ro", lambda r: _c(r, "maintenance_obligation", "returned_coins")),
 ("MO RS2 no_envelope stalled project-turns (MO - MO_ro)", "MO", "MO_ro", lambda r: _c(r, "repair_projects", "stalled_no_envelope")),
 ("MO other L9 envelopes awarded, coins (MO - MO_ro)", "MO", "MO_ro", lambda r: _get(r, "l9", "other")),
 ("MO_ro other L9 envelopes awarded, coins (MO_ro - L9; crowding out)", "MO_ro", "L9", lambda r: _get(r, "l9", "other")),
 ("MO_ro L9 workshop envelopes awarded, coins (MO_ro - L9)", "MO_ro", "L9", lambda r: _get(r, "l9", "workshop")),
 ("MO_ro L9 granary envelopes awarded, coins (MO_ro - L9)", "MO_ro", "L9", lambda r: _get(r, "l9", "granary")),
 ("MO_ro L9 relief envelopes awarded, coins (MO_ro - L9)", "MO_ro", "L9", lambda r: _get(r, "l9", "relief")),
 ("MO_ro granary mean condition, run mean (MO_ro - L9)", "MO_ro", "L9", _GR),
 # L9 - RP: the penalty of bargained envelopes.
 ("L9 workshop mean condition, run mean (L9 - RP)", "L9", "RP", _WR),
 ("L9 granary mean condition, run mean (L9 - RP)", "L9", "RP", _GR),
 ("L9 RS2 no_envelope stalled project-turns (L9)", "L9", None, lambda r: _c(r, "repair_projects", "stalled_no_envelope")),
 # CH - CH_rec and CH - RP: the recovery chain.
 ("[primary] CH veteran placements (CH - CH_rec)", "CH", "CH_rec", lambda r: _c(r, "veteran_reintegration", "placements")),
 ("CH people placed (CH - CH_rec)", "CH", "CH_rec", lambda r: _c(r, "veteran_reintegration", "people_placed")),
 ("CH repair placements (CH - CH_rec)", "CH", "CH_rec", lambda r: _c(r, "veteran_reintegration", "placements_repair")),
 ("[primary] CH granary mean condition, run mean (CH - RP)", "CH", "RP", _GR),
 ("CH wages to named repair workers, coins (CH - RP)", "CH", "RP", _wages),
 ("CH timber delivered (CH - RP)", "CH", "RP", lambda r: _z(r, "timber_supply", "delivered")),
 ("CH_rec granary mean condition, run mean (CH_rec - RP)", "CH_rec", "RP", _GR),
]


def annotate_pairs(rows) -> None:
    """Food shortfall over a fixed region set per world, so both arms of a pair are
    compared on the same communities over the same turns: the regions that sent a crew
    in either arm (TS, TS_cost), or the regions the woodcutting arm's crews came from
    (TS_cost against RP, TS against RP). A row without food totals gets None."""
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}

    def total(row, regions):
        short = _get(row, "food", "region_shortfall")
        if row is None or row.get("rc") != 0 or short is None or any(i >= len(short) for i in regions):
            return None
        return sum(short[i] for i in regions)

    for (arm, stratum, seed), row in by.items():
        if arm not in ("TS", "TS_cost"):
            continue
        homes = set(_get(row, "ts", "homes") or ()) if row.get("rc") == 0 else None
        pairs = [("RP", f"{arm}|RP")]
        if arm == "TS":
            other = by.get(("TS_cost", stratum, seed))
            union = None
            if homes is not None and other is not None and other.get("rc") == 0:
                union = homes | set(_get(other, "ts", "homes") or ())
            for target in (row, other):
                if target is not None:
                    target.setdefault("pair", {})["TS|TS_cost"] = total(target, sorted(union)) \
                        if union is not None else None
        for control, key in pairs:
            ctl = by.get((control, stratum, seed))
            regions = sorted(homes) if homes is not None else None
            for target in (row, ctl):
                if target is not None:
                    target.setdefault("pair", {})[key] = total(target, regions) if regions is not None else None


# --- Running ----------------------------------------------------------------------

def preregistration_frozen(path: Path = PREREGISTRATION) -> bool:
    """Whether the preregistration's status line reads FROZEN (the lead's freeze)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(line.startswith("Status:") and "FROZEN" in line and "DRAFT" not in line
               for line in text.splitlines())


def jobs_for(cohort: str, seeds: str, arms: list[str]) -> list[tuple[str, str, int, list[str], bool]]:
    """(arm, stratum tag, seed, extra world flags, first world of its stratum) per run;
    procedural worlds first (they take longest)."""
    strata = ["procedural", "template"] if seeds == "all" else [seeds]
    out = []
    for stratum in strata:
        for i, seed in enumerate(COHORTS[cohort][stratum]):
            for arm in arms:
                out.append((arm, TAGS[stratum], seed, PROCEDURAL if stratum == "procedural" else [], i == 0))
    return out


def simulate(cmd: list[str]) -> subprocess.CompletedProcess:
    """One simulation of this checkout's ``src`` (the shared run environment)."""
    return subprocess.run(cmd, cwd=REPO, env=LS._run_env(), capture_output=True, text=True)


def run_one(out: Path, cohort: str, arm: str, stratum: str, seed: int, extra: list[str], keep: bool) -> dict:
    d = (out / "runs" / f"{arm}-{stratum}{seed}").resolve()
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    flags = list(ARMS[arm][0])
    cmd = [PY, "-m", "chronicler.main", "--seed", str(seed), *BASE, *extra, *flags,
           "--output", str(d / "chronicle.md"), "--state", str(d / "state.json")]
    t0 = time.time()
    p = simulate(cmd)
    row = {"cohort": cohort, "arm": arm, "stratum": stratum, "seed": seed, "rc": p.returncode,
           "wall_s": round(time.time() - t0, 1)}
    if p.returncode != 0:
        row["error"] = (p.stderr or "")[-2000:]
    else:
        t1 = time.time()
        try:
            row.update(metrics_row(d / "chronicle_bundle.json", flags))
        except Exception as error:  # an unreadable bundle is a missing outcome, never zero
            row["rc"], row["error"] = 3, f"missing or malformed outcomes: {type(error).__name__}: {error}"
        row["extract_s"] = round(time.time() - t1, 1)
    if not keep:
        shutil.rmtree(d)
    return row


def exit_code(rows) -> int:
    """3 if any outcome is missing or malformed, else 1 if any simulation failed, else 0."""
    if any(r["rc"] == 3 for r in rows):
        return 3
    return 1 if any(r["rc"] != 0 for r in rows) else 0


def run_main(argv) -> int:
    ap = argparse.ArgumentParser(prog="productive_recovery_screens.py run")
    ap.add_argument("out")
    ap.add_argument("--cohort", choices=sorted(COHORTS), required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--arms", default=None, help="comma-separated arms (default: all 14)")
    ap.add_argument("--seeds", choices=("all", "template", "procedural"), default="all")
    ap.add_argument("--keep-first", action="store_true", help="keep the first world of each stratum")
    ap.add_argument("--resume", action="store_true",
                    help="continue an interrupted run in OUT_DIR on the same source (rows already written are kept)")
    a = ap.parse_args(argv)
    check_seeds()
    check_extractor()
    if a.cohort == "held" and not preregistration_frozen():
        raise SystemExit(f"held run refused: {PREREGISTRATION.relative_to(REPO)} is not marked FROZEN")
    chosen = a.arms.split(",") if a.arms else list(ARMS)
    unknown = [arm for arm in chosen if arm not in ARMS]
    if unknown:
        raise SystemExit(f"unknown arms: {unknown}")
    if a.jobs < 1:
        raise SystemExit("--jobs must be at least 1")
    out = Path(a.out)
    metrics = out / "metrics.jsonl"
    done: set = set()
    if metrics.exists() and not a.resume:
        raise SystemExit(f"{metrics} exists: pass --resume to continue it, or choose a new OUT_DIR")
    if a.resume:
        if not metrics.exists() or not (out / "source.txt").exists():
            raise SystemExit(f"nothing to resume in {out}")
        recorded = (out / "source.txt").read_text(encoding="utf-8")
        for line in metrics.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("cohort") != a.cohort:
                    raise SystemExit(f"{metrics} holds a row of cohort {r.get('cohort')}, not {a.cohort}")
                done.add((r["arm"], r["stratum"], r["seed"]))
    out.mkdir(parents=True, exist_ok=True)
    if a.resume:
        probe = out / "resume-probe"
        probe.mkdir(exist_ok=True)
        text = LS.source_identity(probe)
        shutil.rmtree(probe)
        if recorded.splitlines()[:4] != text.splitlines()[:4]:
            raise SystemExit("resume refused: the source, chronicler path, extension or interpreter changed:\n"
                             + text)
    else:
        text = LS.source_identity(out)
    with open(out / "source.txt", "a", encoding="utf-8") as fh:
        fh.write(f"{'resumed' if a.resume else 'cohort'} {a.cohort}; seeds {a.seeds}; arms {','.join(chosen)}; "
                 f"jobs {a.jobs}; rows already written {len(done)}\n"
                 f"started {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
    print(text, end="", flush=True)
    jobs = [j for j in jobs_for(a.cohort, a.seeds, chosen) if (j[0], j[1], j[2]) not in done]
    rows, t0 = [], time.time()
    with open(metrics, "a", encoding="utf-8") as fh, ThreadPoolExecutor(a.jobs) as ex:
        # Each row is written as soon as its run finishes, so a killed run loses only
        # the runs still in flight (``--resume`` runs those).
        futures = [ex.submit(run_one, out, a.cohort, j[0], j[1], j[2], j[3], a.keep_first and j[4]) for j in jobs]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            note = f" FAILED: {row.get('error', '')[-300:]}" if row["rc"] else ""
            print(row["arm"], f"{row['stratum']}{row['seed']}", row["rc"], row["wall_s"], note, flush=True)
    wall = round(time.time() - t0, 1)
    with open(out / "source.txt", "a", encoding="utf-8") as fh:
        fh.write(f"finished {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}: {len(rows)} runs, "
                 f"{sum(r['rc'] != 0 for r in rows)} failed, {sum(r['wall_s'] for r in rows):.0f} s of simulation, "
                 f"{sum(r.get('extract_s', 0) for r in rows):.0f} s of extraction, {wall} s wall\n")
    print("total wall", wall)
    for r in rows:
        if r["rc"]:
            print(f"FAILED run {r['arm']} {r['stratum']}{r['seed']} (rc {r['rc']}): {r.get('error', '')[-500:]}")
    return exit_code(rows)


# --- Report -----------------------------------------------------------------------

def _rng(vals, fmt="{:+.4g}"):
    if not vals:
        return "n/a"
    return f"{fmt.format(mean(vals))} [{fmt.format(min(vals))}, {fmt.format(max(vals))}]"


def report_lines(rows) -> list[str]:
    cohorts = sorted({r.get("cohort", "held") for r in rows})
    labels = LABELS[cohorts[0]] if len(cohorts) == 1 else {"t": "template", "p": "procedural"}
    annotate_pairs(rows)
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    fails = [r for r in rows if r["rc"] != 0]
    seconds = sum(_run_seconds(r) for r in rows)
    out = [f"Runs: {len(rows)}; failed: {len(fails)} (missing outcomes: {sum(r['rc'] == 3 for r in rows)}); "
           f"simulation and extraction seconds total {seconds:.0f} ({seconds / 3600:.3f} core-hours)"]
    for f in fails:
        out.append(f"- FAILED {f['arm']} {f['stratum']}{f['seed']} (rc {f['rc']}): {f.get('error', '')[-300:]}")
    for arm in ARMS:
        for s in labels:
            cohort = cohorts[0] if len(cohorts) == 1 else "held"
            stratum = "template" if s == "t" else "procedural"
            for seed in COHORTS[cohort][stratum]:
                if (arm, s, seed) not in by:
                    out.append(f"- INCOMPLETE {arm} {s}{seed}: not run")

    out.append("\n### Run time per arm (simulation and extraction seconds per run: mean [min, max])\n")
    out.append("| Arm | " + " | ".join(labels[s] for s in labels) + " |")
    out.append("| --- | " + " | ".join("---" for _ in labels) + " |")
    for arm in ARMS:
        cells = [_rng([_run_seconds(r) for r in rows if r["arm"] == arm and r["stratum"] == s], "{:.1f}")
                 for s in labels]
        out.append(f"| {arm} | " + " | ".join(cells) + " |")

    out.append("\n### Shared outcomes vs each arm's control (mean [min, max] over worlds)\n")
    out.append("| Arm | Control | Stratum | Worlds | Population | Treasury |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for arm, (_flags, control) in ARMS.items():
        if control is None:
            continue
        for s in labels:
            dp, dt = [], []
            for seed in sorted({k[2] for k in by if k[1] == s}):
                a, c = by.get((arm, s, seed)), by.get((control, s, seed))
                if a and c and a["rc"] == 0 and c["rc"] == 0:
                    dp.append(a["population"] - c["population"])
                    dt.append(a["treasury"] - c["treasury"])
            out.append(f"| {arm} | {control} | {s} | {len(dp)} | {_rng(dp, '{:+.1f}')} | {_rng(dt, '{:+.1f}')} |")

    out.append("\n### Preregistered outcomes, world by world (arm minus control, or the arm alone)\n")
    out.extend(LS.per_world_table(rows, PAIRED, labels))

    out.append("\n### Activation funnels (mean per world [min, max]; z = worlds at zero)\n")
    for s in labels:
        out.append(f"\n**{labels[s]}**\n")
        for arm in ARMS:
            rs = [r for r in rows if r["arm"] == arm and r["stratum"] == s and r["rc"] == 0]
            for name in OUTCOMES:
                cs = [r["pk"][name] for r in rs if name in r.get("pk", {})]
                if not cs:
                    continue
                cells = []
                for k in OUTCOMES[name]:
                    v = [c[k] for c in cs]
                    cells.append(f"{k} {mean(v):.4g} [{min(v):.4g}, {max(v):.4g}] z{sum(x == 0 for x in v)}")
                out.append(f"- {arm} / {name} ({len(cs)} worlds): " + ", ".join(cells))
            l9 = [r["l9"]["awards"] for r in rs if "l9" in r]
            if l9:
                services = sorted({k for a in l9 for k in a})
                out.append(f"- {arm} / L9 awards by service, coins ({len(l9)} worlds): " + ", ".join(
                    f"{k} {mean(a.get(k, 0) for a in l9):.4g}" for k in services))
    return out


def _run_seconds(r) -> float:
    """A run's simulation and extraction seconds (extraction ran in the runner process)."""
    return r["wall_s"] + r.get("extract_s", 0.0)


def projected_held_core_hours(rows) -> float | None:
    """Pilot run time (simulation and extraction) per arm and stratum times the held worlds
    per stratum, in core-hours (None if a pilot arm is missing)."""
    total = 0.0
    for arm in ARMS:
        for stratum, tag in TAGS.items():
            walls = [_run_seconds(r) for r in rows if r["arm"] == arm and r["stratum"] == tag]
            if not walls:
                return None
            total += mean(walls) * len(HELD[stratum])
    return total / 3600


def report_main(argv) -> int:
    ap = argparse.ArgumentParser(prog="productive_recovery_screens.py report")
    ap.add_argument("metrics")
    a = ap.parse_args(argv)
    rows = [json.loads(line) for line in open(a.metrics, encoding="utf-8") if line.strip()]
    lines = report_lines(rows)
    if all(r.get("cohort") == "pilot" for r in rows):
        hours = projected_held_core_hours(rows)
        lines.insert(1, "Projected held run time from this pilot: "
                     + (f"{hours:.3f} core-hours for {len(ARMS) * sum(map(len, HELD.values()))} runs"
                        if hours is not None else "unknown (an arm or stratum is missing)"))
    print("\n".join(lines))
    return 0


# --- Check ------------------------------------------------------------------------

def check_metrics(rows, cohort: str) -> list[str]:
    """Every arm and world of the cohort has exactly one row, and none failed."""
    problems = []
    seen: dict = {}
    for r in rows:
        key = (r["arm"], r["stratum"], r["seed"])
        seen[key] = seen.get(key, 0) + 1
        if r.get("cohort", cohort) != cohort:
            problems.append(f"{r['arm']} {r['stratum']}{r['seed']}: row of cohort {r.get('cohort')}")
        if r["rc"] != 0:
            problems.append(f"{r['arm']} {r['stratum']}{r['seed']}: rc {r['rc']}: {r.get('error', '')[-300:]}")
    for stratum, tag in TAGS.items():
        for seed in COHORTS[cohort][stratum]:
            for arm in ARMS:
                n = seen.get((arm, tag, seed), 0)
                if n != 1:
                    problems.append(f"{arm} {tag}{seed}: {n} rows")
    extra = sorted(k for k in seen if k[0] not in ARMS or k[2] not in COHORTS[cohort]["template" if k[1] == "t" else "procedural"])
    problems += [f"{a} {s}{seed}: not in the cohort" for a, s, seed in extra]
    return problems


def check_main(argv) -> int:
    ap = argparse.ArgumentParser(prog="productive_recovery_screens.py check")
    ap.add_argument("--metrics", default=None)
    ap.add_argument("--cohort", choices=sorted(COHORTS), default=None)
    a = ap.parse_args(argv)
    check_seeds()
    check_extractor()
    check_arm_flags()
    print(f"extractor, seeds and {len(ARMS)} arms: OK")
    if a.metrics:
        if a.cohort is None:
            raise SystemExit("--metrics needs --cohort")
        rows = [json.loads(line) for line in open(a.metrics, encoding="utf-8") if line.strip()]
        problems = check_metrics(rows, a.cohort)
        for p in problems:
            print("FAILED", p)
        if any(r["rc"] == 3 for r in rows):
            return 3
        if problems:
            return 1
        print(f"{len(rows)} runs: complete, every outcome extracted")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"run": run_main, "report": report_main, "check": check_main}
    if not argv or argv[0] not in commands:
        print(__doc__)
        return 0 if not argv else 2
    return commands[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
