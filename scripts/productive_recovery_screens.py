"""Productive-recovery checkpoint screens (PL6a, PL6c, PL6d): run, report and check.

    python scripts/productive_recovery_screens.py run OUT_DIR --cohort pilot|held [--checkpoint 1|2|3] [--jobs 3] [--arms a,b] [--seeds all|template|procedural] [--keep-first] [--resume]
    python scripts/productive_recovery_screens.py report OUT_DIR/metrics.jsonl [--checkpoint 1|2|3]
    python scripts/productive_recovery_screens.py check [--checkpoint 1|2|3] [--metrics OUT_DIR/metrics.jsonl --cohort pilot|held]

Run with the native interpreter whose extension matches the source under
test (every arm is hybrid). ``--checkpoint`` (default 1) picks the arms,
outcomes, seeds and preregistration: checkpoint 1 (recovery) in
docs/superpowers/progress/productive-recovery-screens-cp1.md, checkpoint 2
(household food retail) in docs/superpowers/progress/productive-recovery-screens-cp2.md,
checkpoint 3 (the integrated chain) in
docs/superpowers/progress/productive-recovery-screens-cp3.md.
Worlds are the units. Every arm is compared with its declared control on the same world.
Rows of checkpoints 2 and 3 carry ``"checkpoint": 2`` or ``3``; a report, check or resume
refuses rows of another checkpoint.

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
unchanged. A held run refuses unless its checkpoint's preregistration's status
line reads FROZEN. Raw outputs are deleted after extraction (``--keep-first`` keeps the
first world of each stratum). ``--resume`` continues an interrupted run in the
same OUT_DIR: it runs only the arms and worlds without a row, and refuses
unless the recorded source, ``chronicler`` path, extension and interpreter
are the current ones; no recorded run is repeated.
"""
from __future__ import annotations

import argparse
import hashlib
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
CHECKPOINT = 1
#: The arm every control chain leads to.
ROOT = "W"


class _ModuleCheckpoint:
    """Checkpoint 1 is this module's own globals, read when used (so tests can patch
    them). Checkpoint 2 is the ``CP2`` namespace below; both offer the same names."""

    def __getattr__(self, name):
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(name) from None


CP1 = _ModuleCheckpoint()


def _cp(cp):
    return CP1 if cp is None else cp

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
#: Further choices of a package checked like its mode: switch -> ((option, record
#: attribute, default), ...). Checkpoint 1 has none.
OPTIONS: dict[str, tuple[tuple[str, str, str], ...]] = {}
#: Packages whose mode is recorded under another attribute than ``mode``.
MODE_KEYS: dict[str, str] = {}
#: Rules versions a checkpoint ran, by switch: switch -> (option, value). Each run
#: passes them explicitly (after its outputs), so a rerun at a later source keeps the
#: checkpoint's rules; the extractor counts them as checked. Checkpoint 1 has none.
RULES: dict[str, tuple[str, str]] = {}

# --- Seeds (per stratum; procedural 32x10 seed numbers are separate worlds) --------

PILOT = {"template": (5,), "procedural": (19,)}
HELD = {"template": tuple(range(701, 707)), "procedural": tuple(range(801, 807))}
#: Earlier held cohorts and pilots: never run again.
NEVER_RUN = {"template": frozenset({2, *range(101, 107), *range(301, 307), *range(501, 507)}),
             "procedural": frozenset({*range(201, 207), *range(401, 407), *range(601, 607)})}
#: This phase's other held cohorts (checkpoints 2 and 3).
RESERVED = {"template": frozenset({*range(711, 717), *range(721, 727)}),
            "procedural": frozenset({*range(811, 817), *range(821, 827)})}
#: Earlier checkpoints' held cohorts, which NEVER_RUN must contain (none before checkpoint 1).
PRIOR_HELD: tuple[dict, ...] = ()
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


def source_problems() -> list[str]:
    """Checkpoint-specific source checks (checkpoint 1: none beyond ``check_extractor``)."""
    return []


def expected_packages(flags, cp=None) -> dict[str, str | None]:
    """{snapshot key: mode} of the livelihoods packages the base plus ``flags`` enable
    (None for a package without modes)."""
    cp = _cp(cp)
    flags = [*cp.BASE, *flags]
    out = {}
    for flag, (name, mode_flag, default) in cp.PACKAGES.items():
        if flag in flags:
            out[name] = (flags[flags.index(mode_flag) + 1] if mode_flag and mode_flag in flags else default)
    return out


def expected_options(flags, cp=None) -> dict[str, dict[str, str]]:
    """{snapshot key: {record attribute: value}} of the further choices (``OPTIONS``)
    of the packages the base plus ``flags`` enable."""
    cp = _cp(cp)
    flags = [*cp.BASE, *flags]
    out = {}
    for flag, options in cp.OPTIONS.items():
        if flag in flags:
            out[cp.PACKAGES[flag][0]] = {attr: (flags[flags.index(option) + 1] if option in flags else default)
                                         for option, attr, default in options}
    return out


def _known_flags(cp=None) -> set[str]:
    cp = _cp(cp)
    known = set(cp.BASE) | set(cp.PACKAGES)
    for _name, mode_flag, _default in cp.PACKAGES.values():
        if mode_flag:
            known.add(mode_flag)
    for options in cp.OPTIONS.values():
        known.update(option for option, _attr, _default in options)
    known.update(option for option, _value in cp.RULES.values())
    return known


def rules_flags(flags, cp=None) -> list[str]:
    """The ``RULES`` options of the packages ``flags`` (the full command line) enable."""
    cp = _cp(cp)
    return [part for flag, (option, value) in cp.RULES.items() if flag in flags for part in (option, value)]


def check_seeds(cp=None) -> None:
    """Pilot and held seeds are disjoint from every earlier cohort and pilot, from
    this phase's other reserved cohorts, from development worlds and from each other
    (per stratum), and the earlier cohorts include every sprint 1-3 cohort and pilot
    and every earlier checkpoint's held cohort."""
    cp = _cp(cp)
    problems = []
    earlier = {"template": set(), "procedural": set()}
    for strata in (LS.STRATA, LS.STRATA2, LS.STRATA3, LS.PILOT3):
        for stratum, rows in strata.items():
            earlier[stratum].update(seed for _t, seed, _x in rows)
    for stratum in ("template", "procedural"):
        # The sprint-3 pilot ran procedural 7, a development world; every other
        # earlier seed must be listed as never run.
        missing = earlier[stratum] - cp.NEVER_RUN[stratum] - cp.DEVELOPMENT[stratum]
        if missing:
            problems.append(f"{stratum}: earlier cohort seeds {sorted(missing)} not in NEVER_RUN")
        for prior in cp.PRIOR_HELD:
            missing = set(prior[stratum]) - cp.NEVER_RUN[stratum]
            if missing:
                problems.append(f"{stratum}: earlier checkpoint's held seeds {sorted(missing)} not in NEVER_RUN")
        pilot, held = set(cp.PILOT[stratum]), set(cp.HELD[stratum])
        for label, seeds in (("pilot", pilot), ("held", held)):
            for other_label, other in (("earlier cohorts and pilots", cp.NEVER_RUN[stratum] | earlier[stratum]),
                                       ("reserved cohorts", cp.RESERVED[stratum]),
                                       ("development worlds", cp.DEVELOPMENT[stratum])):
                if seeds & other:
                    problems.append(f"{stratum} {label} seeds {sorted(seeds & other)} are in the {other_label}")
        if pilot & held:
            problems.append(f"{stratum}: pilot and held overlap {sorted(pilot & held)}")
    if problems:
        raise SystemExit("seed cohorts are not disjoint: " + "; ".join(problems))


def check_extractor(cp=None) -> None:
    """Every counter the report reads is declared by its package, every package is a
    livelihoods switch whose option and default mode (and further options) match the
    registry, every arm's flags are known and its control exists (a tree rooted at the
    checkpoint's root), every outcome names known arms in a declared comparison, and
    the checkpoint's own source checks pass. Raises SystemExit naming each problem."""
    cp = _cp(cp)
    _src()
    from chronicler.livelihoods import LIVELIHOODS_ARG_KEYS, LIVELIHOODS_CHOICES
    from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES
    declared = cp.declared_counters()
    problems = [f"{name} is not a livelihoods switch" for name in cp.OUTCOMES if name not in LIVELIHOODS_SWITCHES]
    problems += [f"{name}.{key} is not a declared counter" for name, keys in cp.OUTCOMES.items()
                 for key in keys if key not in declared.get(name, ())]
    for flag, (name, mode_flag, default) in cp.PACKAGES.items():
        dest = flag[2:].replace("-", "_")
        if dest != name or name not in LIVELIHOODS_SWITCHES or dest not in LIVELIHOODS_ARG_KEYS:
            problems.append(f"{flag} is not the switch of livelihoods package {name}")
        if mode_flag is not None:
            choices = LIVELIHOODS_CHOICES.get(mode_flag[2:].replace("-", "_"))
            if not choices or choices[0] != default:
                problems.append(f"{mode_flag}: default {default!r} is not the registry default {choices}")
        elif any(k.startswith(name) and k != name for k in LIVELIHOODS_CHOICES):
            problems.append(f"{name} has registered modes the screen does not check")
    for flag, options in cp.OPTIONS.items():
        if flag not in cp.PACKAGES:
            problems.append(f"options of {flag}, which is not a package of the screen")
        for option, _attr, default in options:
            choices = LIVELIHOODS_CHOICES.get(option[2:].replace("-", "_"))
            if not choices or choices[0] != default:
                problems.append(f"{option}: default {default!r} is not the registry default {choices}")
    known = _known_flags(cp)
    for arm, (flags, control) in cp.ARMS.items():
        bad = [f for f in flags if f.startswith("--") and f not in known]
        if bad:
            problems.append(f"arm {arm}: unknown flags {bad}")
        if control is not None and control not in cp.ARMS:
            problems.append(f"arm {arm}: unknown control {control}")
        seen, a = set(), arm
        while a is not None and a in cp.ARMS and a not in seen:
            seen.add(a)
            a = cp.ARMS[a][1]
        if a is not None:
            problems.append(f"arm {arm}: its controls do not lead to the root {cp.ROOT}")
    roots = [arm for arm, (_f, control) in cp.ARMS.items() if control is None]
    if roots != [cp.ROOT]:
        problems.append(f"the root arms are {roots}, not {[cp.ROOT]}")
    for label, arm, control, _f in cp.PAIRED:
        problems += [f"outcome {label!r}: unknown arm {a}" for a in (arm, control) if a and a not in cp.ARMS]
    for label, arm, control, _f in cp.PAIRED:
        if control is not None and (arm, control) not in cp.DECLARED_PAIRS:
            problems.append(f"outcome {label!r}: {arm} - {control} is not a declared comparison")
    problems += cp.source_problems()
    if problems:
        raise SystemExit("productive-recovery extractor does not match the source: " + "; ".join(problems))


def check_arm_flags(cp=None) -> None:
    """Every arm's command line parses and passes the livelihoods prerequisite checks
    on a constructed hybrid world with cities, grain reserves and storage, enabling
    exactly the packages and modes ``expected_packages`` names (and the options
    ``expected_options`` names)."""
    cp = _cp(cp)
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
    for arm, (flags, _control) in cp.ARMS.items():
        for extra in ([], cp.PROCEDURAL):
            args = parser.parse_args(["--seed", "1", *cp.BASE, *extra, *flags,
                                      *rules_flags([*cp.BASE, *extra, *flags], cp)])
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
                    enabled[name] = getattr(sub, cp.MODE_KEYS.get(name, "mode"), None)
            if enabled != expected_packages(flags, cp):
                problems.append(f"arm {arm}: enables {enabled}, expected {expected_packages(flags, cp)}")
            for name, attrs in expected_options(flags, cp).items():
                sub = getattr(state, name, None) if state is not None else None
                got = {attr: getattr(sub, attr, None) for attr in attrs}
                if got != attrs:
                    problems.append(f"arm {arm}: {name} configures {got}, expected {attrs}")
            for flag, (option, value) in cp.RULES.items():
                name = cp.PACKAGES[flag][0]
                sub = getattr(state, name, None) if state is not None and flag in [*cp.BASE, *flags] else None
                if sub is not None and getattr(sub, "rules", None) != value:
                    problems.append(f"arm {arm}: {name} runs rules {getattr(sub, 'rules', None)!r}, expected {value!r}")
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


def _granary_measures(hist, bundle: dict, problems: list[str]) -> dict:
    """Granaries (grain storage is in the base), per turn and at the end: the run mean
    of each turn's mean condition over granaries with capacity, and the end value."""
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
    return {"run_mean": mean(run_means) if run_means else None,
            "end": mean(end_conds) if end_conds else None, "turns_with_assets": len(run_means)}


def _workshop_measures(hist, bundle: dict, problems: list[str]) -> tuple[dict, int]:
    """Workshop sites (workshops are in the base), per turn and at the end, and the
    L1 lump repairs paid over all snapshots."""
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
    return ({"run_mean": mean(run_means) if run_means else None,
             "end": mean(end_conds) if end_conds else None, "turns_with_sites": len(run_means)}, lump)


def _woodcut_measures(hist, n_regions: int, cells: dict, counters: dict, problems: list[str]) -> dict:
    """Woodcutting: the regions that sent a crew, home farm labour away per region, the
    home region's food on away turns (``cells``: (source turn, region) -> (shortfall,
    demand, sufficiency after relief)), the forest guard and the per-expedition means."""
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
    c = counters
    ended = c.get("ended", 0)
    return {"homes": sorted(homes), "region_away": away, "away_cells": a_cells,
            "away_shortfall": a_short, "away_demand": a_demand, "away_below_one": a_below,
            "away_shortfall_share": (a_short / a_demand) if a_demand else None,
            "min_stock_share": share,
            "wages_per_ended": (c.get("ended_wages_milli", 0) / 1000 / ended) if ended else None,
            "person_turns_per_ended": (c.get("ended_person_turns", 0) / ended) if ended else None,
            "away_per_ended": (c.get("ended_away", 0) / ended) if ended else None}


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

    out["granary"] = _granary_measures(hist, bundle, problems)
    out["workshop"], out["lump_repairs"] = _workshop_measures(hist, bundle, problems)

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
        out["ts"] = _woodcut_measures(hist, n_regions, cells, out["pk"].get("timber_supply") or {}, problems)

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


def report_extra(rows) -> list[str]:
    """Checkpoint-specific report sections (checkpoint 1: none)."""
    return []


# --- Checkpoint 2: household food retail (PL4) -------------------------------------
#
# Preregistered in docs/superpowers/progress/productive-recovery-screens-cp2.md. The
# ``CP2`` namespace at the end of this section offers every name checkpoint 1 keeps as
# a module global, so the shared check, run and report code serves both checkpoints.

#: Retail modes that provision pilot regions (``record_only`` provisions none).
PROVISIONED_MODES = ("retail", "no_relief", "free_exchange")
#: Native retail frame columns (``provisioning`` of a frame row) summed over an arm's
#: own pilot region-turns; validated against ``RETAIL_REGION_COLUMNS`` in the Rust source.
RETAIL_SUMS = ("persons", "children", "rations", "fed_fair", "deficit",
               "priced_out_households", "priced_out_persons", "priced_out_children", "priced_out_deficit",
               "offer_short_persons", "offer_short_children", "offer_short_deficit",
               "withheld_dead_persons", "withheld_dead_children", "withheld_dead_deficit",
               "free_given", "own_eaten_milli", "sold_milli", "paid_milli", "credited_milli", "refunded_milli")
#: Sums over the frames that must equal the lifetime counter of the same name: a frame
#: missing for a provisioned pilot region-turn shows here.
CHECKED_SUMS = ("priced_out_persons", "offer_short_persons", "own_eaten_milli", "sold_milli",
                "paid_milli", "credited_milli", "refunded_milli")
#: L2 frame columns read (validated against ``REGION_COLUMNS``). L2 lists only scarce
#: regions; elsewhere everyone has a full ration, so a ration shortfall of zero.
L2_COLUMNS = ("region", "alive", "allocated", "shortfall")
#: Retail frame-row fields read (validated against ``RegionFrame``).
FRAME_FIELDS = ("region", "provisioning", "would_be", "merchant_food_departing", "owned_food_unloadable_milli")
#: Food-accounting native fields read (validated against ``FOOD_LEDGER_FIELDS``).
FOOD_FIELDS = ("demand", "transport_net")
PROVISIONING_RS = "chronicler-agents/src/provisioning.rs"
#: Checkpoint 1's held cohort, which checkpoint 2 must never run.
CP1_HELD = HELD


def _index(value, n: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < n


def declared_counters_cp2() -> dict[str, frozenset[str]]:
    """Household retail's declared lifetime counters, from this checkout's source."""
    _src()
    from chronicler import household_retail_state
    return {"household_retail": frozenset(household_retail_state.COUNTERS)}


def rust_columns(path: str, const: str) -> tuple[str, ...] | None:
    """The ``pub const <const>: [&str; N]`` array of a Rust file of this checkout (None
    if it is absent or its length differs from N)."""
    try:
        text = (Path(REPO) / path).read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(rf"pub const {const}: \[&str; (\d+)\] = \[(.*?)\];", text, re.S)
    if m is None:
        return None
    names = tuple(re.findall(r'"([^"]+)"', m.group(2)))
    return names if len(names) == int(m.group(1)) else None


def source_problems_cp2() -> list[str]:
    """Every frame column, frame field and food-ledger field the extractor reads is
    declared in this checkout's source; the retail modes are the four the screen
    knows; and every registered choice of a package is checked as its mode or an
    option."""
    _src()
    from chronicler.food_accounting import FOOD_LEDGER_FIELDS
    from chronicler.household_retail_state import MODES, RegionFrame
    from chronicler.livelihoods import LIVELIHOODS_CHOICES
    problems = []
    for const, wanted in (("RETAIL_REGION_COLUMNS", RETAIL_SUMS + ("region",)), ("REGION_COLUMNS", L2_COLUMNS)):
        declared = rust_columns(PROVISIONING_RS, const)
        if declared is None:
            problems.append(f"{PROVISIONING_RS} declares no {const}")
            continue
        problems += [f"frame column {c} is not in {const}" for c in wanted if c not in declared]
    problems += [f"frame field {f} is not a RegionFrame field" for f in FRAME_FIELDS
                 if f not in RegionFrame.model_fields]
    problems += [f"food accounting field {f} is not declared" for f in FOOD_FIELDS
                 if f not in (*FOOD_LEDGER_FIELDS, "demand", "sufficiency")]
    if set(MODES) != {*PROVISIONED_MODES, "record_only"}:
        problems.append(f"household retail modes are {MODES}, not {(*PROVISIONED_MODES, 'record_only')}")
    for flag, (name, mode_flag, _default) in CP2.PACKAGES.items():
        covered = {mode_flag[2:].replace("-", "_")} if mode_flag else set()
        covered |= {option[2:].replace("-", "_") for option, _a, _d in CP2.OPTIONS.get(flag, ())}
        if flag in CP2.RULES:
            covered.add(CP2.RULES[flag][0][2:].replace("-", "_"))
        extra = sorted(k for k in LIVELIHOODS_CHOICES if k.startswith(name + "_") and k not in covered)
        if extra:
            problems.append(f"{name} has registered choices the screen does not check: {extra}")
    return problems


def trajectory_digest(bundle: dict) -> str:
    """SHA-256 of the history and the final world state with the household retail
    records removed (and the bundle metadata, which dates the run, left out): equal
    for two runs whose trajectories are identical."""
    def strip(liv):
        return {k: v for k, v in liv.items() if k != "household_retail"} if isinstance(liv, dict) else liv
    hist = [dict(s, livelihoods=strip(s["livelihoods"])) if isinstance(s, dict) and "livelihoods" in s else s
            for s in bundle.get("history") or []]
    world = bundle.get("world_state") or {}
    if isinstance(world, dict) and "livelihoods" in world:
        world = dict(world, livelihoods=strip(world["livelihoods"]))
    text = json.dumps({"history": hist, "world_state": world}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_cp2(bundle: dict, flags, declared: dict, cp=None) -> tuple[dict, list[str]]:
    """The checkpoint-2 outcomes of one run and the reasons any is missing or malformed.

    The run must have one snapshot per turn (1..TURNS); the last snapshot must hold
    exactly the packages the arm enables, for the completed turn, in the arm's mode and
    boundary, with numeric declared counters. Every snapshot must hold a complete food
    accounting row per region, L2's frame and (retail arms) the retail frame, dated by
    its source turn. A pilot region-turn is a frame row with a provisioning row (retail,
    no_relief, free_exchange) or a would-be record (record_only); their number, and the
    frame sums in ``CHECKED_SUMS``, must equal the lifetime counters. In provisioned
    modes a pilot region may not also be in L2's frame. Any failure is returned, never
    read as zero.

    ``cp`` (default checkpoint 2) supplies the arms' packages, the counters read, the
    retail frame columns also summed per region (``REGION_RETAIL``) and whether the
    trajectory digest is needed (an ``IDENTITY`` control)."""
    cp = CP2 if cp is None else cp
    region_retail = tuple(getattr(cp, "REGION_RETAIL", ()))
    hist = bundle.get("history") or []
    if not hist:
        return {}, ["no snapshots"]
    problems: list[str] = []
    turns = [s.get("turn") for s in hist]
    if turns != list(range(1, cp.TURNS + 1)):
        problems.append(f"snapshots are not turns 1..{cp.TURNS} (got {len(turns)}, last {turns[-1]!r})")
    last = hist[-1]
    liv = last.get("livelihoods") or {}
    expected = expected_packages(flags, cp)
    options = expected_options(flags, cp)
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
        key = cp.MODE_KEYS.get(name, "mode")
        if mode is not None and rec.get(key) != mode:
            problems.append(f"{name}: {key} {rec.get(key)!r}, expected {mode!r}")
        for attr, value in options.get(name, {}).items():
            if rec.get(attr) != value:
                problems.append(f"{name}: {attr} {rec.get(attr)!r}, expected {value!r}")
        if name not in cp.OUTCOMES:
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
        # A declared counter absent from the record was never incremented (every
        # record starts empty when its switch is enabled).
        out["pk"][name] = {k: counters.get(k, 0) for k in cp.OUTCOMES[name]}

    regions = (bundle.get("world_state") or {}).get("regions") or []
    n = len(regions)
    if not n:
        problems.append("world state has no regions")
    mode = expected.get("household_retail")
    provisioned = mode in PROVISIONED_MODES
    totals = {k: [0.0] * n for k in ("food_gap", "food_demand", "ration_short", "phase2_alive", "transport_net",
                                     *(f"retail_{c}" for c in region_retail))}
    pilot_turns = [0] * n
    sums = dict.fromkeys(RETAIL_SUMS, 0.0)
    departing = unloadable = 0.0
    bad_food, bad_l2, bad_retail, overlap, leaked = [], [], [], [], []
    for snap in hist:
        turn = snap.get("turn")
        source = turn - 1 if isinstance(turn, int) else None
        # Food accounting (Phase 2 availability after relief, per region).
        fa = snap.get("food_accounting") or {}
        rows = fa.get("regions")
        cells = []
        if fa.get("source_turn") == source and isinstance(rows, list) and len(rows) == n:
            for i, row in enumerate(rows):
                native = row.get("native") or {}
                d, s, t = native.get("demand"), row.get("sufficiency_after_relief"), native.get("transport_net")
                count = row.get("native_count")
                if row.get("region_id") != i or not (_num(d) and _num(s) and _num(t)) or not _index(count, 1 << 31):
                    break
                cells.append((d * max(0.0, 1.0 - min(1.0, s)), d, t, count))
        if len(cells) != n:
            bad_food.append(turn)
        else:
            for i, (gap, d, t, count) in enumerate(cells):
                totals["food_gap"][i] += gap
                totals["food_demand"][i] += d
                totals["transport_net"][i] += t
                totals["phase2_alive"][i] += count
        # L2's frame: scarce regions outside the provisioned pilot.
        l2 = (snap.get("livelihoods") or {}).get("food_allocation")
        l2_regions: set[int] = set()
        if not isinstance(l2, dict) or l2.get("source_turn") != source or not isinstance(l2.get("regions"), list):
            bad_l2.append(turn)
        else:
            for row in l2["regions"]:
                rid = row.get("region") if isinstance(row, dict) else None
                if not _index(rid, n) or rid in l2_regions or not all(_num(row.get(k)) for k in L2_COLUMNS[1:]):
                    bad_l2.append(turn)
                    break
                l2_regions.add(rid)
                totals["ration_short"][rid] += row["shortfall"]
        # The retail frame (one row per pilot region touched this turn).
        hr = (snap.get("livelihoods") or {}).get("household_retail")
        if mode is None:
            if hr is not None:
                leaked.append(turn)
            continue
        if not isinstance(hr, dict) or hr.get("source_turn") != source or not isinstance(hr.get("regions"), list):
            bad_retail.append(turn)
            continue
        seen: set[int] = set()
        for f in hr["regions"]:
            rid = f.get("region") if isinstance(f, dict) else None
            if not _index(rid, n) or rid in seen:
                bad_retail.append(turn)
                break
            seen.add(rid)
            prov, would_be = f.get("provisioning"), f.get("would_be")
            if provisioned:
                if would_be is not None:
                    bad_retail.append(turn)
                    break
                if prov is None:
                    continue        # a region closed this turn: not provisioned, not a pilot region-turn
                if not isinstance(prov, dict) or prov.get("region") != rid \
                        or not all(_num(prov.get(k)) for k in RETAIL_SUMS) \
                        or not _num(f.get("merchant_food_departing")) or not _num(f.get("owned_food_unloadable_milli")):
                    bad_retail.append(turn)
                    break
                if rid in l2_regions:
                    overlap.append(turn)
                for k in RETAIL_SUMS:
                    sums[k] += prov[k]
                for k in region_retail:
                    totals[f"retail_{k}"][rid] += prov[k]
                totals["ration_short"][rid] += prov["persons"] - prov["rations"]
                unloadable += f["owned_food_unloadable_milli"]
            else:
                if prov is not None:
                    bad_retail.append(turn)
                    break
                if would_be is None:
                    continue
                if not isinstance(would_be, dict) or not _num(f.get("merchant_food_departing")):
                    bad_retail.append(turn)
                    break
            departing += f["merchant_food_departing"]
            pilot_turns[rid] += 1
    if bad_food:
        problems.append(f"food accounting missing or incomplete at turns {bad_food[:5]}")
    if bad_l2:
        problems.append(f"food_allocation: frame missing or malformed at turns {bad_l2[:5]}")
    if bad_retail:
        problems.append(f"household_retail: frame missing or malformed at turns {bad_retail[:5]}")
    if overlap:
        problems.append(f"household_retail: a provisioned pilot region is also in L2's frame at turns {overlap[:5]}")
    if leaked:
        problems.append(f"household_retail: recorded at turns {leaked[:5]} in an arm without it")
    pk = out["pk"].get("household_retail")
    income_replaced = 0.0
    if mode is not None and pk is not None:
        if sum(pilot_turns) != pk["pilot_region_turns"]:
            problems.append(f"household_retail: {sum(pilot_turns)} pilot region-turns in the frames, "
                            f"the counter has {pk['pilot_region_turns']}")
        for k in CHECKED_SUMS:
            if abs(sums[k] - pk[k]) > 1e-6 * max(1.0, abs(pk[k])):
                problems.append(f"household_retail: frames sum {k} to {sums[k]}, the counter has {pk[k]}")
        income_replaced = (liv.get("household_retail") or {}).get("income_replaced_total")
        if not _num(income_replaced):
            problems.append("household_retail: income_replaced_total missing")
            income_replaced = None
    civs = [c for c in (last.get("civ_stats") or {}).values() if isinstance(c, dict) and (c.get("population") or 0) > 0]
    if not all(_num(c.get("gini")) for c in civs):
        problems.append("civ_stats: wealth Gini missing in the last snapshot")
    out["retail"] = {**{k: round(v, 6) for k, v in sums.items()}, "pilot_region_turns": sum(pilot_turns),
                     "merchant_food_departing": round(departing, 6), "owned_food_unloadable": unloadable / 1000}
    out["income_replaced"] = income_replaced
    out["region_totals"] = {**{k: [round(v, 6) for v in vals] for k, vals in totals.items()},
                            "pilot_turns": pilot_turns}
    out["gini"] = mean(c["gini"] for c in civs) if civs and all(_num(c.get("gini")) for c in civs) else None
    if getattr(cp, "IDENTITY", None) is not None:
        out["digest"] = trajectory_digest(bundle)
    return out, problems


def metrics_row_cp2(bundle_path: Path, flags) -> dict:
    """The shared sprint metrics plus the validated checkpoint-2 outcomes.
    A missing or malformed outcome makes the row a visible failure (rc 3)."""
    _src()
    from chronicler.bundle_codec import load_bundle
    m = LS.metrics(bundle_path)
    extra, problems = extract_cp2(load_bundle(bundle_path), flags, declared_counters_cp2())
    m.update(extra)
    if problems:
        m["rc"], m["error"] = 3, "missing or malformed outcomes: " + "; ".join(problems)
    return m


def _region_set(row, regions) -> dict | None:
    """A run's totals over a fixed region set, all turns (None if unknown)."""
    if row is None or row.get("rc") != 0 or regions is None:
        return None
    t = row.get("region_totals") or {}
    try:
        food, short, alive, transport = (math.fsum(t[k][i] for i in regions)
                                         for k in ("food_gap", "ration_short", "phase2_alive", "transport_net"))
    except (KeyError, IndexError, TypeError):
        return None
    return {"regions": len(regions), "food": food, "ration_short": short, "phase2_alive": alive,
            "mean_ration": (1.0 - short / alive) if alive else None, "transport_net": transport}


def annotate_pairs_cp2(rows) -> None:
    """Fixed region sets per world (checkpoint 1's rule): each ``REGION_SETS`` treatment
    arm's pilot regions (provisioned, or recorded in record_only, at any turn), summed over
    every turn in both that arm and its control; and, for the identity arm, whether its
    trajectory digest differs from its control's (1) or not (0)."""
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    for treat, control in CP2.REGION_SETS:
        key = f"{treat}|{control}"
        for (arm, stratum, seed), row in by.items():
            if arm != treat:
                continue
            ctl = by.get((control, stratum, seed))
            turns = _get(row, "region_totals", "pilot_turns") if row.get("rc") == 0 else None
            regions = [i for i, v in enumerate(turns) if v] if isinstance(turns, list) else None
            for target in (row, ctl):
                if target is not None:
                    target.setdefault("pair", {})[key] = _region_set(target, regions)
            if row["pair"][key] is not None:
                row["pair"][key]["coverage"] = (math.fsum(turns[i] for i in regions) / (len(regions) * CP2.TURNS)
                                                if regions else None)
            if (treat, control) == CP2.IDENTITY and ctl is not None:
                mine, theirs = row["pair"][key], ctl["pair"][key]
                known = mine is not None and theirs is not None and bool(row.get("digest")) and bool(ctl.get("digest"))
                if mine is not None:
                    mine["trajectory_differs"] = float(row["digest"] != ctl["digest"]) if known else None
                if theirs is not None:
                    theirs["trajectory_differs"] = 0.0 if known else None


def _rt(key):
    """A sum over the arm's own pilot region-turns (structural zero in an arm that
    provisions none: the extractor verified it has no provisioning row)."""
    return lambda r: _get(r, "retail", key)


def _own_mean_ration(r):
    """Mean ration of the arm's own pilot persons (person rations over person-turns)."""
    return _ratio(_get(r, "retail", "rations"), _get(r, "retail", "persons"))


def _over(key, field):
    return lambda r: _get(r, "pair", key, field)


def _retail_coins(*keys):
    """Household retail counters in milli-units, as coins (structural zero without retail)."""
    def value(r):
        parts = [_z(r, "household_retail", k) for k in keys]
        return None if any(p is None for p in parts) else sum(parts) / 1000
    return value


_REVENUE = _retail_coins("credited_milli", "procurement_credited_milli")


def _revenue_ratio(r):
    return _ratio(_REVENUE(r), r.get("income_replaced"))


def _net_money(r):
    """Procurement credited minus ordinary farm income replaced, coins: the money retail
    brings into or takes out of households (purchases move it between households)."""
    procured, replaced = _retail_coins("procurement_credited_milli")(r), r.get("income_replaced")
    return None if procured is None or replaced is None else procured - replaced


def _paired_cp2() -> list:
    """The preregistered checkpoint-2 outcomes (``PAIRED``)."""
    out = []
    for b, primary in (("", "[primary] "), ("_all", "")):
        R, F, N = f"R{b}", f"R{b}_free", f"R{b}_norelief"
        out += [
            # R - R_free: payment and income replacement, against ownership and timing without cash.
            (f"{primary}{R} priced-out person-turns in its pilot regions ({R} - {F})", R, F, _rt("priced_out_persons")),
            (f"{R} priced-out child-turns ({R} - {F})", R, F, _rt("priced_out_children")),
            (f"{R} priced-out deficit, rations ({R} - {F})", R, F, _rt("priced_out_deficit")),
            (f"{R} offer-short person-turns ({R} - {F})", R, F, _rt("offer_short_persons")),
            (f"{R} withheld-dead person-turns ({R} - {F})", R, F, _rt("withheld_dead_persons")),
            (f"{R} mean ration of pilot persons ({R} - {F})", R, F, _own_mean_ration),
            (f"{R} pilot person-turns ({R} - {F}; the denominator)", R, F, _rt("persons")),
            # R_norelief - R: what the tithe and the means test protect.
            (f"{primary}{N} priced-out person-turns ({N} - {R}; what relief protects)", N, R,
             _rt("priced_out_persons")),
            (f"{N} priced-out child-turns ({N} - {R})", N, R, _rt("priced_out_children")),
            (f"{N} priced-out deficit, rations ({N} - {R})", N, R, _rt("priced_out_deficit")),
        ]
        for A in (R, F):
            key = f"{A}|L2"
            out += [
                (f"{A} food shortfall after relief in {A}'s pilot regions, food ({A} - L2)", A, "L2", _over(key, "food")),
                (f"{A} mean ration per Phase-2 person in {A}'s pilot regions ({A} - L2)", A, "L2",
                 _over(key, "mean_ration")),
                (f"{primary if A == R else ''}{A} ration shortfall in {A}'s pilot regions, rations ({A} - L2)",
                 A, "L2", _over(key, "ration_short")),
                (f"{A} population ({A} - L2)", A, "L2", lambda r: r.get("population")),
            ]
            if A != R:
                continue
            out += [
                (f"{R} net food transport into {R}'s pilot regions, food ({R} - L2)", R, "L2",
                 _over(key, "transport_net")),
                (f"{R} treasury ({R} - L2)", R, "L2", lambda r: r.get("treasury")),
                (f"{R} mean civilization wealth Gini at the end ({R} - L2)", R, "L2", lambda r: r.get("gini")),
                (f"{R} share of its pilot regions' region-turns that were pilot turns ({R})", R, None,
                 _over(key, "coverage")),
                (f"{R} owners' sale revenue: household purchases and granary procurement credited, coins ({R})",
                 R, None, _REVENUE),
                (f"{R} household purchases credited to owners, coins ({R})", R, None,
                 _retail_coins("credited_milli")),
                (f"{R} granary procurement credited to owners, coins ({R})", R, None,
                 _retail_coins("procurement_credited_milli")),
                (f"{R} ordinary farm income replaced, coins ({R})", R, None, lambda r: r.get("income_replaced")),
                (f"{R} sale revenue / income replaced ({R})", R, None, _revenue_ratio),
                (f"{R} money into households: procurement credited minus income replaced, coins ({R})", R, None,
                 _net_money),
                (f"{R} owned food merchants could not load, summed over pilot region-turns, food ({R}; "
                 "bounds the merchant departures foregone)", R, None, _rt("owned_food_unloadable")),
            ]
        if not b:
            out.append(("R commons food merchants committed from pilot regions, food (R - R_rec; R_rec records "
                        "L2's trajectory)", "R", "R_rec", _rt("merchant_food_departing")))
            # R_rec - L2: the identity control. Every value must be zero in every world.
            key = "R_rec|L2"
            ident = [
                ("trajectory differs (1) or is identical (0)", _over(key, "trajectory_differs")),
                ("food shortfall after relief in R_rec's pilot regions, food", _over(key, "food")),
                ("mean ration per Phase-2 person in R_rec's pilot regions", _over(key, "mean_ration")),
                ("ration shortfall in R_rec's pilot regions, rations", _over(key, "ration_short")),
                ("net food transport into R_rec's pilot regions, food", _over(key, "transport_net")),
                ("population", lambda r: r.get("population")),
                ("treasury", lambda r: r.get("treasury")),
                ("mean civilization wealth Gini at the end", lambda r: r.get("gini")),
                ("priced-out person-turns", _rt("priced_out_persons")),
                ("priced-out child-turns", _rt("priced_out_children")),
                ("priced-out deficit, rations", _rt("priced_out_deficit")),
                ("offer-short person-turns", _rt("offer_short_persons")),
                ("withheld-dead person-turns", _rt("withheld_dead_persons")),
                ("owners' sale revenue, coins", _REVENUE),
                ("ordinary farm income replaced, coins", lambda r: r.get("income_replaced")),
                ("money into households, coins", _net_money),
                ("owned food merchants could not load, food", _rt("owned_food_unloadable")),
            ]
            out += [(f"[identity] R_rec {label} (R_rec - L2; must be 0)", "R_rec", "L2", f) for label, f in ident]
    return out


def report_extra_cp2(rows) -> list[str]:
    """The identity control: every R_rec - L2 outcome must be zero in every world."""
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    worlds = sorted({(s, seed) for (_a, s, seed) in by})
    out = ["\n### Identity control (R_rec - L2: every outcome must be zero in every world)\n"]
    bad = []
    for label, arm, control, f in CP2.PAIRED:
        if (arm, control) != CP2.IDENTITY:
            continue
        for s, seed in worlds:
            a, c = by.get((arm, s, seed)), by.get((control, s, seed))
            if a is None or c is None or a["rc"] != 0 or c["rc"] != 0:
                bad.append(f"{label} {s}{seed}: not run or failed")
                continue
            va, vc = f(a), f(c)
            if va is None or vc is None:
                bad.append(f"{label} {s}{seed}: unknown")
            elif va - vc != 0:
                bad.append(f"{label} {s}{seed}: {va - vc:+.6g}")
    n = sum(1 for label, a, c, _f in CP2.PAIRED if (a, c) == CP2.IDENTITY)
    if bad:
        out.append(f"**FAILED** on {len(bad)} outcome-worlds:")
        out += [f"- {b}" for b in bad]
    else:
        out.append(f"All {n} identity outcomes are zero in all {len(worlds)} worlds.")
    return out


class CP2:
    """Checkpoint 2 (household food retail): the names checkpoint 1 keeps as globals."""

    CHECKPOINT = 2
    PREREGISTRATION = Path(REPO) / "docs/superpowers/progress/productive-recovery-screens-cp2.md"
    ROOT = "L2"
    #: The sprint base, the sprint-2/3 base and L2 in its default floor_means regime
    #: (retail requires it). No workshops.
    BASE = [*LS.BASE, *LS.BASE2, "--food-allocation"]
    TURNS = int(BASE[BASE.index("--turns") + 1])
    PROCEDURAL = list(LS.PROCEDURAL)
    #: Arm -> (flags added to the base, control arm). ``L2`` is the root.
    ARMS: dict[str, tuple[list[str], str | None]] = {
        "L2": ([], None),
        "R_rec": (["--household-retail", "--household-retail-mode", "record_only"], "L2"),
        "R": (["--household-retail"], "R_free"),
        "R_free": (["--household-retail", "--household-retail-mode", "free_exchange"], "L2"),
        "R_norelief": (["--household-retail", "--household-retail-mode", "no_relief"], "R"),
        "R_all": (["--household-retail", "--household-retail-boundary", "all"], "R_all_free"),
        "R_all_free": (["--household-retail", "--household-retail-mode", "free_exchange",
                        "--household-retail-boundary", "all"], "L2"),
        "R_all_norelief": (["--household-retail", "--household-retail-mode", "no_relief",
                            "--household-retail-boundary", "all"], "R_all"),
    }
    PACKAGES: dict[str, tuple[str, str | None, str | None]] = {
        "--food-allocation": ("food_allocation", "--food-allocation-regime", "floor_means"),
        "--household-retail": ("household_retail", "--household-retail-mode", "retail"),
    }
    OPTIONS = {"--household-retail": (("--household-retail-boundary", "boundary", "market"),)}
    MODE_KEYS = {"food_allocation": "regime"}
    #: Retail's rules at this checkpoint: version 1 (named so by A5-1, which made 2 the
    #: default of a new state); a rerun passes it explicitly.
    RULES = {"--household-retail": ("--household-retail-rules", "1")}
    # Seeds (per stratum). The pilot is the phase's timing pilot, shared with checkpoint 1.
    PILOT = {"template": (5,), "procedural": (19,)}
    HELD = {"template": tuple(range(711, 717)), "procedural": tuple(range(811, 817))}
    #: Earlier held cohorts and pilots, checkpoint 1's held cohort included: never run.
    NEVER_RUN = {"template": frozenset({2, *range(101, 107), *range(301, 307), *range(501, 507), *range(701, 707)}),
                 "procedural": frozenset({*range(201, 207), *range(401, 407), *range(601, 607), *range(801, 807)})}
    #: This phase's later held cohort (checkpoint 3).
    RESERVED = {"template": frozenset(range(721, 727)), "procedural": frozenset(range(821, 827))}
    DEVELOPMENT = DEVELOPMENT
    PRIOR_HELD = (CP1_HELD,)
    TAGS = TAGS
    COHORTS = {"pilot": PILOT, "held": HELD}
    LABELS = {"pilot": {"t": "template 8x4 (seed 5)", "p": "procedural 32x10 (seed 19)"},
              "held": {"t": "template 8x4 (seeds 711-716)", "p": "procedural 32x10 (seeds 811-816)"}}
    #: Counters the funnels report (validated against household_retail_state.COUNTERS).
    OUTCOMES: dict[str, tuple[str, ...]] = {
        "household_retail": (
            "turns_settled", "turns_unobserved", "turns_not_taken", "pilot_region_turns", "regions_opened",
            "regions_closed", "claims_refused", "owners_titled", "titled_milli", "untitled_milli",
            "own_eaten_milli", "sold_milli", "procured_milli", "decay_milli", "overflow_milli", "war_loss_milli",
            "to_commons_milli", "inherited_milli", "escheat_milli", "deaths", "pool_resets", "paid_milli",
            "credited_milli", "refunded_milli", "procurement_flows", "procurement_credited_milli",
            "procurement_residual_milli", "procurement_unpaid_milli", "requisition_exempt_region_turns",
            "priced_out_persons", "offer_short_persons", "income_replaced_rows", "crew_farm_time_person_turns",
            "crew_farm_time_micro"),
    }
    #: Treatment arms compared with L2 over a fixed region set (their pilot regions).
    REGION_SETS = (("R", "L2"), ("R_free", "L2"), ("R_rec", "L2"), ("R_all", "L2"), ("R_all_free", "L2"))
    #: The identity control and its reference.
    IDENTITY = ("R_rec", "L2")
    PAIRED = _paired_cp2()
    #: The arm table's comparisons plus the cross-arm contrasts the preregistration names.
    DECLARED_PAIRS = {(arm, control) for arm, (_f, control) in ARMS.items() if control} \
        | {("R", "L2"), ("R_all", "L2"), ("R", "R_rec")}
    declared_counters = staticmethod(declared_counters_cp2)
    source_problems = staticmethod(source_problems_cp2)
    metrics_row = staticmethod(metrics_row_cp2)
    annotate_pairs = staticmethod(annotate_pairs_cp2)
    report_extra = staticmethod(report_extra_cp2)


# --- Checkpoint 3: the integrated chain (PL5, PL6) ------------------------------------
#
# Preregistered (draft until the lead freezes it) in
# docs/superpowers/progress/productive-recovery-screens-cp3.md. A community needs timber
# (RS2 stalls), sends a named, paid woodcutting crew (PL1), repairs its granary with a
# named, paid crew (PL3), and those households buy food (PL4 retail at the ``paid_work``
# boundary); RS4 remittances are the other household cash channel. Every arm carries the
# recovery reference (RS2 under the operating wear with the L3 stock) and, except CH_L2,
# retail at the ``paid_work`` boundary.

#: Retail frame columns also summed per region, so checkpoint 3 can compare arms over a
#: fixed region set (``annotate_pairs_cp3``); validated with ``RETAIL_SUMS``.
REGION_RETAIL_CP3 = ("priced_out_persons", "priced_out_children", "priced_out_deficit", "persons")
#: Record fields the checkpoint-3 extractor reads beyond checkpoint 2's: (module, model) ->
#: fields, checked against this checkout's models (pydantic or dataclass).
FIELDS_READ_CP3 = {
    ("grain_storage_state", "StorageAsset"): {"capacity", "condition"},
    ("workshops_state", "WorkshopSite"): {"status", "asset", "condition"},
    ("workshops_state", "WorkshopReceipt"): {"paid"},
    ("timber_supply_state", "ExpeditionReceipt"): {"turn", "home", "stage", "away_delivered", "stock_after",
                                                   "capacity"},
    ("food_accounting", "RegionFood"): {"region_id", "native_count", "native", "sufficiency_after_relief"},
}
#: Declared values the checkpoint-3 extractor matches: (module, tuple name) -> values.
VALUES_READ_CP3 = {("timber_supply_state", "STAGES"): {"cutting"}}
#: Checkpoint 2's held cohort, which checkpoint 3 must never run.
CP2_HELD = CP2.HELD


def declared_counters_cp3() -> dict[str, frozenset[str]]:
    """The declared lifetime counters of every package checkpoint 3 reads, from this
    checkout's source."""
    _src()
    from chronicler import household_retail_state, recovery_crews_state, remittances_state
    from chronicler import repair_projects_state, timber_supply_state
    mods = {"household_retail": household_retail_state, "repair_projects": repair_projects_state,
            "timber_supply": timber_supply_state, "recovery_crews": recovery_crews_state,
            "remittances": remittances_state}
    return {name: frozenset(mod.COUNTERS) for name, mod in mods.items()}


def _model_fields(model) -> set[str]:
    import dataclasses
    if dataclasses.is_dataclass(model):
        return {f.name for f in dataclasses.fields(model)}
    return set(model.model_fields)


def source_problems_cp3() -> list[str]:
    """Checkpoint 2's frame, field and mode checks; every registered choice of every
    package of the screen is its mode option or a checked option, recorded under the
    attribute the screen reads (the registry's choice-field map); and every record field
    and declared value the checkpoint-3 extractor reads exists in this checkout."""
    _src()
    from importlib import import_module
    from chronicler.food_accounting import FOOD_LEDGER_FIELDS
    from chronicler.household_retail_state import MODES, RegionFrame
    from chronicler.livelihoods import _CHOICE_FIELDS
    problems = []
    for const, wanted in (("RETAIL_REGION_COLUMNS", RETAIL_SUMS + ("region",)), ("REGION_COLUMNS", L2_COLUMNS)):
        declared = rust_columns(PROVISIONING_RS, const)
        if declared is None:
            problems.append(f"{PROVISIONING_RS} declares no {const}")
            continue
        problems += [f"frame column {c} is not in {const}" for c in wanted if c not in declared]
    problems += [f"per-region retail column {c} is not in RETAIL_SUMS" for c in CP3.REGION_RETAIL
                 if c not in RETAIL_SUMS]
    problems += [f"frame field {f} is not a RegionFrame field" for f in FRAME_FIELDS
                 if f not in RegionFrame.model_fields]
    problems += [f"food accounting field {f} is not declared" for f in FOOD_FIELDS
                 if f not in (*FOOD_LEDGER_FIELDS, "demand", "sufficiency")]
    if set(MODES) != {*PROVISIONED_MODES, "record_only"}:
        problems.append(f"household retail modes are {MODES}, not {(*PROVISIONED_MODES, 'record_only')}")
    names = {name: flag for flag, (name, _m, _d) in CP3.PACKAGES.items()}
    for key, (name, field) in _CHOICE_FIELDS.items():
        if name not in names:
            continue
        flag = names[name]
        mode_flag = CP3.PACKAGES[flag][1]
        if mode_flag and key == mode_flag[2:].replace("-", "_"):
            if field != CP3.MODE_KEYS.get(name, "mode"):
                problems.append(f"{name}: its mode is recorded as {field!r}, the screen reads "
                                f"{CP3.MODE_KEYS.get(name, 'mode')!r}")
            continue
        attrs = {option[2:].replace("-", "_"): attr for option, attr, _d in CP3.OPTIONS.get(flag, ())}
        if flag in CP3.RULES and key == CP3.RULES[flag][0][2:].replace("-", "_"):
            continue
        if key not in attrs:
            problems.append(f"{name} has a registered choice the screen does not check: {key}")
        elif attrs[key] != field:
            problems.append(f"{name}: {key} is recorded as {field!r}, the screen reads {attrs[key]!r}")
    for (module, model), fields in FIELDS_READ_CP3.items():
        declared = _model_fields(getattr(import_module(f"chronicler.{module}"), model))
        problems += [f"{model}.{f} is not a field" for f in sorted(fields - declared)]
    for (module, name), values in VALUES_READ_CP3.items():
        declared = set(getattr(import_module(f"chronicler.{module}"), name))
        problems += [f"{module}.{name} does not declare {v!r}" for v in sorted(values - declared)]
    return problems


def _food_cells(hist, n: int) -> dict[tuple[int, int], tuple[float, float, float]]:
    """(source turn, region) -> (shortfall after relief, demand, sufficiency after relief)
    for the well-formed food accounting rows (``extract_cp2`` names any other)."""
    cells = {}
    for snap in hist:
        fa = snap.get("food_accounting") or {}
        rows = fa.get("regions")
        if not isinstance(rows, list) or len(rows) != n or not isinstance(fa.get("source_turn"), int):
            continue
        for i, row in enumerate(rows):
            d, s = (row.get("native") or {}).get("demand"), row.get("sufficiency_after_relief")
            if row.get("region_id") == i and _num(d) and _num(s):
                cells[(fa["source_turn"], i)] = (d * max(0.0, 1.0 - min(1.0, s)), d, s)
    return cells


def extract_cp3(bundle: dict, flags, declared: dict) -> tuple[dict, list[str]]:
    """The checkpoint-3 outcomes of one run and the reasons any is missing or malformed.

    Checkpoint 2's extractor (with checkpoint 3's packages) validates the packages,
    counters, food accounting, L2 frames and retail frames, and sums the retail and food
    measures per region; checkpoint 1's measures add the granaries, the workshop sites
    and (woodcutting arms) the woodcutting receipts. Any failure is returned, never read
    as zero."""
    cp = CP3
    out, problems = extract_cp2(bundle, flags, declared, cp)
    hist = bundle.get("history") or []
    if not hist:
        return out, problems
    n = len((bundle.get("world_state") or {}).get("regions") or [])
    expected = expected_packages(flags, cp)
    out["granary"] = _granary_measures(hist, bundle, problems)
    out["workshop"], out["lump_repairs"] = _workshop_measures(hist, bundle, problems)
    if "timber_supply" in expected:
        out["ts"] = _woodcut_measures(hist, n, _food_cells(hist, n), out["pk"].get("timber_supply") or {}, problems)
    if "timber_stock" in expected:
        # The shared metrics sum L3's extraction over the snapshots that carry totals;
        # a snapshot without them would read as no extraction.
        missing = [s.get("turn") for s in hist
                   if not _num((((s.get("livelihoods") or {}).get("timber_stock") or {}).get("totals") or {})
                               .get("extraction"))]
        if missing:
            problems.append(f"timber_stock: totals missing at turns {missing[:5]}")
    return out, problems


def metrics_row_cp3(bundle_path: Path, flags) -> dict:
    """The shared sprint metrics plus the validated checkpoint-3 outcomes.
    A missing or malformed outcome makes the row a visible failure (rc 3)."""
    _src()
    from chronicler.bundle_codec import load_bundle
    m = LS.metrics(bundle_path)
    extra, problems = extract_cp3(load_bundle(bundle_path), flags, declared_counters_cp3())
    m.update(extra)
    if "timber_stock" in expected_packages(flags, CP3) and "timber" not in m:
        problems.append("timber_stock: no totals in any snapshot")
    if problems:
        m["rc"], m["error"] = 3, "missing or malformed outcomes: " + "; ".join(problems)
    return m


def _pilot_turns(row):
    """A run's pilot region-turns per region (None if the run is missing or failed)."""
    if row is None or row.get("rc") != 0:
        return None
    turns = _get(row, "region_totals", "pilot_turns")
    return turns if isinstance(turns, list) else None


def _region_set_cp3(row, regions, both) -> dict | None:
    """``_region_set`` over ``regions`` plus the retail measures: priced-out persons,
    children and deficit, pilot person-turns and region-turns, the priced-out rate and
    the coverage; and priced-out person-turns over ``both`` (the regions that are pilot
    regions in both arms; None when there is none)."""
    base = _region_set(row, regions)
    if base is None:
        return None
    t = row.get("region_totals") or {}
    try:
        sums = {k: math.fsum(t[f"retail_{k}"][i] for i in regions) for k in CP3.REGION_RETAIL}
        pilot = math.fsum(t["pilot_turns"][i] for i in regions)
        in_both = math.fsum(t["retail_priced_out_persons"][i] for i in both) if both else None
    except (KeyError, IndexError, TypeError):
        return None
    base.update({**sums, "pilot_region_turns": pilot,
                 "priced_out_rate": _ratio(sums["priced_out_persons"], sums["persons"]),
                 "coverage": (pilot / (len(regions) * CP3.TURNS)) if regions else None,
                 "both_regions": len(both), "both_priced_out_persons": in_both})
    return base


def annotate_pairs_cp3(rows) -> None:
    """Fixed region sets per world. For each ``REGION_SETS`` pair, the regions that were
    pilot regions (at any turn) in either arm, summed over every turn in both arms; it
    is checkpoint 2's rule (the treatment arm's pilot regions) when the control has
    none, and checkpoint 1's either-arm rule otherwise. The regions pilot in both arms
    are kept beside it. For CH - CH_cut, the regions that sent a woodcutting crew in
    either arm (checkpoint 1's food-cost set). A pair with a run missing or failed gets
    None."""
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    for treat, control in CP3.REGION_SETS:
        key = f"{treat}|{control}"
        for (arm, stratum, seed), row in by.items():
            if arm != treat:
                continue
            ctl = by.get((control, stratum, seed))
            mine, theirs = _pilot_turns(row), _pilot_turns(ctl)
            known = mine is not None and theirs is not None and len(mine) == len(theirs)
            union = [i for i in range(len(mine)) if mine[i] or theirs[i]] if known else None
            both = [i for i in range(len(mine)) if mine[i] and theirs[i]] if known else None
            for target in (row, ctl):
                if target is not None:
                    target.setdefault("pair", {})[key] = (_region_set_cp3(target, union, both)
                                                          if known else None)
    treat, control = CP3.HOME_SET
    key = f"{treat}|{control}|homes"
    for (arm, stratum, seed), row in by.items():
        if arm != treat:
            continue
        ctl = by.get((control, stratum, seed))
        homes = None
        if row.get("rc") == 0 and ctl is not None and ctl.get("rc") == 0:
            homes = sorted(set(_get(row, "ts", "homes") or ()) | set(_get(ctl, "ts", "homes") or ()))
        for target in (row, ctl):
            if target is None:
                continue
            gaps = _get(target, "region_totals", "food_gap")
            value = None
            if homes is not None and isinstance(gaps, list) and all(i < len(gaps) for i in homes):
                value = math.fsum(gaps[i] for i in homes)
            target.setdefault("pair", {})[key] = value


def _retail_turns(r):
    """The run's pilot region-turns (structural zero without retail)."""
    return _get(r, "retail", "pilot_region_turns")


def _pilot_regions(r):
    """The number of regions with at least one pilot region-turn."""
    turns = _get(r, "region_totals", "pilot_turns")
    return sum(1 for v in turns if v) if isinstance(turns, list) else None


def _remit_debit(r):
    """Coins remittance senders lost net of refunds: credited to recipients plus the
    courier fee (RS4 checks debited = credited + fee = sent - refunded; structural zero
    without RS4)."""
    credited, fee = _z(r, "remittances", "credited_milli"), _z(r, "remittances", "fee_milli")
    return None if credited is None or fee is None else (credited + fee) / 1000


def _money_cp3(r):
    """Money credited to households (gross), coins: wages to named repair workers (RS2 workshop crews,
    PL3 granary crews, PL1 woodcutters) + remittances credited to recipients + granary
    procurement credited to owners - ordinary farm income replaced by retail. Purchases
    and the crews' withheld ordinary income are not in it (see the preregistration)."""
    wages = _wages(r)
    remitted = _z(r, "remittances", "credited_milli")
    procured = _z(r, "household_retail", "procurement_credited_milli")
    replaced = r.get("income_replaced")
    if any(v is None for v in (wages, remitted, procured, replaced)):
        return None
    return wages + (remitted + procured) / 1000 - replaced


def _paired_cp3() -> list:
    """The preregistered checkpoint-3 outcomes (``PAIRED``)."""
    U, X, F, L, Z = "CH_unpaid", "CH_cut", "CH_free", "CH_L2", "C0"
    either = "the pilot regions of either arm"

    def over(control, field):
        return _over(f"CH|{control}", field)

    def coins(pkg, key):
        return lambda r: _coins(_z(r, pkg, key))

    out = [
        # CH - CH_unpaid: does the wage reach food?
        (f"CH priced-out person-turns in {either} (CH - {U})", "CH", U, over(U, "priced_out_persons")),
        (f"CH priced-out child-turns in {either} (CH - {U})", "CH", U, over(U, "priced_out_children")),
        (f"CH priced-out deficit in {either}, rations (CH - {U})", "CH", U, over(U, "priced_out_deficit")),
        (f"CH priced-out person-turns in the regions that are pilot regions in both arms (CH - {U})", "CH", U,
         over(U, "both_priced_out_persons")),
        (f"[primary] CH priced-out person-turns per pilot person-turn in {either} (CH - {U})", "CH", U,
         over(U, "priced_out_rate")),
        (f"CH pilot person-turns in {either} (CH - {U}; the denominator)", "CH", U, over(U, "persons")),
        (f"CH pilot region-turns in {either} (CH - {U}; coverage)", "CH", U, over(U, "pilot_region_turns")),
        (f"CH share of the set's region-turns that were pilot turns (CH; CH|{U} set)", "CH", None,
         over(U, "coverage")),
        (f"{U} share of the set's region-turns that were pilot turns ({U}; CH|{U} set)", U, None,
         over(U, "coverage")),
        (f"CH ration shortfall in {either}, rations (CH - {U})", "CH", U, over(U, "ration_short")),
        (f"CH mean ration per Phase-2 person in {either} (CH - {U})", "CH", U, over(U, "mean_ration")),
        (f"CH granary-crew wages paid to named members, coins (CH - {U})", "CH", U,
         coins("recovery_crews", "granary_wages_milli")),
        (f"CH granary coins sunk, coins (CH - {U})", "CH", U, coins("recovery_crews", "granary_sunk_milli")),
        (f"CH wages to named repair workers (RS2 workshop, PL3 granary, PL1 woodcut), coins (CH - {U})", "CH", U,
         _wages),
        (f"CH remittances credited to recipients, coins (CH - {U})", "CH", U, coins("remittances", "credited_milli")),
        (f"CH granary procurement credited to owners, coins (CH - {U})", "CH", U,
         coins("household_retail", "procurement_credited_milli")),
        (f"CH ordinary farm income replaced by retail, coins (CH - {U})", "CH", U, lambda r: r.get("income_replaced")),
        (f"CH money credited to households (gross): named wages + remittances credited + procurement - income "
         f"replaced by retail, coins (CH - {U})", "CH", U, _money_cp3),
        (f"CH ordinary income withheld for PL3 crews' paid shares (granary and workshop), coins (CH - {U})", "CH", U,
         lambda r: _z(r, "recovery_crews", "income_replaced")),
        (f"CH ordinary income withheld for RS2 workshop crews' paid shares, coins (CH - {U})", "CH", U,
         lambda r: _z(r, "repair_projects", "income_replaced")),
        (f"CH ordinary income withheld for PL1 woodcutters' paid shares, coins (CH - {U})", "CH", U,
         lambda r: _z(r, "timber_supply", "income_withheld")),
        (f"CH remittance senders' net debit: credited + courier fee, coins (CH - {U})", "CH", U,
         lambda r: _remit_debit(r)),
        (f"CH granary mean condition, run mean (CH - {U})", "CH", U, _GR),
        # CH - CH_cut: does timber matter?
        (f"[primary] CH granary mean condition, run mean (CH - {X})", "CH", X, _GR),
        (f"CH granary mean condition at end (CH - {X})", "CH", X, _GE),
        (f"CH workshop mean condition, run mean (CH - {X})", "CH", X, _WR),
        (f"CH timber delivered (CH - {X})", "CH", X, lambda r: _c(r, "timber_supply", "delivered")),
        (f"CH timber cut (CH - {X})", "CH", X, lambda r: _c(r, "timber_supply", "cut")),
        (f"CH RS2 no_timber stalled project-turns (CH - {X})", "CH", X,
         lambda r: _c(r, "repair_projects", "stalled_no_timber")),
        (f"CH RS2 timber used (CH - {X})", "CH", X, lambda r: _c(r, "repair_projects", "timber_used")),
        (f"CH L3 extraction (CH - {X})", "CH", X, lambda r: _get(r, "timber", "extraction")),
        (f"CH minimum L3 stock share after a cutting turn (CH - {X})", "CH", X,
         lambda r: _get(r, "ts", "min_stock_share")),
        ("CH minimum L3 stock share after a cutting turn (CH)", "CH", None, lambda r: _get(r, "ts", "min_stock_share")),
        (f"CH home farm labour away, farmer-turns (CH - {X})", "CH", X,
         lambda r: _c(r, "timber_supply", "away_delivered")),
        (f"CH food shortfall after relief in the regions that sent a woodcutting crew in either arm, food "
         f"(CH - {X})", "CH", X, _pair(f"CH|{X}|homes")),
        ("CH home-region shortfall share on turns a woodcutting crew was away (CH)", "CH", None,
         lambda r: _get(r, "ts", "away_shortfall_share")),
        (f"{X} home-region shortfall share on turns a woodcutting crew was away ({X})", X, None,
         lambda r: _get(r, "ts", "away_shortfall_share")),
        (f"CH woodcutting wages, coins (CH - {X})", "CH", X, coins("timber_supply", "wages_milli")),
        (f"CH expeditions launched (CH - {X})", "CH", X, lambda r: _c(r, "timber_supply", "launched")),
        (f"CH farmer-turns away per ended expedition (CH - {X})", "CH", X, lambda r: _get(r, "ts", "away_per_ended")),
        # CH - CH_free: cash pressure with the whole chain on.
        (f"CH priced-out person-turns in {either} (CH - {F})", "CH", F, over(F, "priced_out_persons")),
        (f"CH priced-out child-turns in {either} (CH - {F})", "CH", F, over(F, "priced_out_children")),
        (f"CH ration shortfall in {either}, rations (CH - {F})", "CH", F, over(F, "ration_short")),
        (f"CH mean ration per Phase-2 person in {either} (CH - {F})", "CH", F, over(F, "mean_ration")),
        (f"CH pilot region-turns in {either} (CH - {F}; coverage)", "CH", F, over(F, "pilot_region_turns")),
        # CH - CH_L2: retail against free allocation, with the chain.
        (f"CH ration shortfall in CH's pilot regions, rations (CH - {L})", "CH", L, over(L, "ration_short")),
        (f"CH population (CH - {L})", "CH", L, lambda r: r.get("population")),
        (f"CH food shortfall after relief in CH's pilot regions, food (CH - {L})", "CH", L, over(L, "food")),
        (f"CH mean ration per Phase-2 person in CH's pilot regions (CH - {L})", "CH", L, over(L, "mean_ration")),
        (f"CH share of its pilot regions' region-turns that were pilot turns (CH; CH|{L} set)", "CH", None,
         over(L, "coverage")),
        # CH - C0: the chain's total.
        (f"CH granary mean condition, run mean (CH - {Z})", "CH", Z, _GR),
        (f"CH priced-out person-turns in {either} (CH - {Z})", "CH", Z, over(Z, "priced_out_persons")),
        (f"CH ration shortfall in {either}, rations (CH - {Z})", "CH", Z, over(Z, "ration_short")),
        (f"CH pilot region-turns in {either} (CH - {Z}; coverage)", "CH", Z, over(Z, "pilot_region_turns")),
        (f"CH wages to named repair workers, coins (CH - {Z})", "CH", Z, _wages),
        (f"CH money credited to households (gross), coins (CH - {Z})", "CH", Z, _money_cp3),
        (f"CH population (CH - {Z})", "CH", Z, lambda r: r.get("population")),
    ]
    # Every fixed region set's size, the regions pilot in both arms, and each arm's
    # coverage of the set (CH_unpaid's is listed with its comparison; CH_L2 has none).
    for ctl in (U, F, L, Z):
        out += [(f"CH regions in the CH|{ctl} set (CH; the pilot regions of either arm)", "CH", None,
                 over(ctl, "regions")),
                (f"CH regions pilot in both arms (CH; CH|{ctl} set)", "CH", None, over(ctl, "both_regions"))]
    for ctl in (F, Z):
        out += [(f"CH share of the set's region-turns that were pilot turns (CH; CH|{ctl} set)", "CH", None,
                 over(ctl, "coverage")),
                (f"{ctl} share of the set's region-turns that were pilot turns ({ctl}; CH|{ctl} set)", ctl, None,
                 over(ctl, "coverage"))]
    # Coverage per arm: the paid_work boundary depends on wages.
    for arm in ("C0", "CH", U, X, F, L):
        out += [(f"{arm} pilot region-turns ({arm})", arm, None, _retail_turns),
                (f"{arm} pilot regions ({arm})", arm, None, _pilot_regions)]
    return out


class CP3:
    """Checkpoint 3 (the integrated chain): the names checkpoint 1 keeps as globals."""

    CHECKPOINT = 3
    PREREGISTRATION = Path(REPO) / "docs/superpowers/progress/productive-recovery-screens-cp3.md"
    ROOT = "C0"
    #: The flags every arm carries: the sprint base, the sprint-2/3 base, L2, workshops,
    #: the operating wear, RS2 and the L3 stock (checkpoint 1's recovery reference).
    BASE = [*LS.BASE, *LS.BASE2, "--food-allocation", "--workshops", "--operating-wear", "--repair-projects",
            "--timber-stock"]
    #: Retail at the paid_work boundary: part of the preregistered base, carried by every
    #: arm but CH_L2 (the boundary option goes with the switch).
    RETAIL = ["--household-retail", "--household-retail-boundary", "paid_work"]
    #: The chain: PL1 timber supply, PL3 recovery crews and RS4 remittances.
    CHAIN = ["--timber-supply", "--recovery-crews", "--remittances"]
    TURNS = int(BASE[BASE.index("--turns") + 1])
    PROCEDURAL = list(LS.PROCEDURAL)
    #: Arm -> (flags added to the shared flags, control arm). ``C0`` is the root.
    ARMS: dict[str, tuple[list[str], str | None]] = {
        "C0": (list(RETAIL), None),
        "CH": ([*RETAIL, *CHAIN], "CH_unpaid"),
        "CH_unpaid": ([*RETAIL, "--timber-supply", "--recovery-crews", "--recovery-crew-mode", "unpaid",
                       "--remittances"], "C0"),
        "CH_cut": ([*RETAIL, "--timber-supply", "--timber-supply-mode", "cost_only", "--recovery-crews",
                    "--remittances"], "CH"),
        "CH_free": ([*RETAIL, "--household-retail-mode", "free_exchange", *CHAIN], "CH"),
        "CH_L2": (list(CHAIN), "CH"),
    }
    PACKAGES: dict[str, tuple[str, str | None, str | None]] = {
        "--food-allocation": ("food_allocation", "--food-allocation-regime", "floor_means"),
        "--workshops": ("workshops", "--workshop-mode", "operate"),
        "--operating-wear": ("operating_wear", None, None),
        "--repair-projects": ("repair_projects", "--repair-mode", "repair"),
        "--timber-stock": ("timber_stock", None, None),
        "--household-retail": ("household_retail", "--household-retail-mode", "retail"),
        "--timber-supply": ("timber_supply", "--timber-supply-mode", "supply"),
        "--recovery-crews": ("recovery_crews", "--recovery-crew-mode", "paid"),
        "--remittances": ("remittances", "--remittance-mode", "send"),
    }
    OPTIONS = {"--household-retail": (("--household-retail-boundary", "boundary", "market"),)}
    MODE_KEYS = {"food_allocation": "regime"}
    #: Retail's rules at this checkpoint: version 1 (named so by A5-1, which made 2 the
    #: default of a new state); a rerun passes it explicitly.
    RULES = {"--household-retail": ("--household-retail-rules", "1")}
    # Seeds (per stratum). The pilot is the phase's timing pilot (checkpoints 1 and 2).
    PILOT = {"template": (5,), "procedural": (19,)}
    HELD = {"template": tuple(range(721, 727)), "procedural": tuple(range(821, 827))}
    #: Earlier held cohorts and pilots, checkpoints 1 and 2 included: never run.
    NEVER_RUN = {"template": frozenset({2, *range(101, 107), *range(301, 307), *range(501, 507), *range(701, 707),
                                        *range(711, 717)}),
                 "procedural": frozenset({*range(201, 207), *range(401, 407), *range(601, 607), *range(801, 807),
                                          *range(811, 817)})}
    #: No later held cohort is reserved in this phase.
    RESERVED = {"template": frozenset(), "procedural": frozenset()}
    DEVELOPMENT = DEVELOPMENT
    PRIOR_HELD = (CP1_HELD, CP2_HELD)
    TAGS = TAGS
    COHORTS = {"pilot": PILOT, "held": HELD}
    LABELS = {"pilot": {"t": "template 8x4 (seed 5)", "p": "procedural 32x10 (seed 19)"},
              "held": {"t": "template 8x4 (seeds 721-726)", "p": "procedural 32x10 (seeds 821-826)"}}
    #: Counters the outcomes and funnels read (validated against each package's COUNTERS).
    OUTCOMES: dict[str, tuple[str, ...]] = {
        "household_retail": CP2.OUTCOMES["household_retail"],
        "repair_projects": (*OUTCOMES["repair_projects"], "income_replaced"),
        "timber_supply": OUTCOMES["timber_supply"],
        "recovery_crews": OUTCOMES["recovery_crews"],
        "remittances": ("turns", "eligible_sender_turns", "linked_sender_turns", "rows_applied", "rows_limited",
                        "rows_absent", "requested_milli", "sent_milli", "credited_milli", "fee_milli",
                        "refunded_milli", "departures", "returns"),
    }
    REGION_RETAIL = REGION_RETAIL_CP3
    #: Pairs compared over a fixed region set (the pilot regions of either arm).
    REGION_SETS = (("CH", "CH_unpaid"), ("CH", "CH_free"), ("CH", "CH_L2"), ("CH", "C0"))
    #: The pair compared over the regions that sent a woodcutting crew in either arm.
    HOME_SET = ("CH", "CH_cut")
    #: No identity control in this checkpoint (no trajectory digest is computed).
    IDENTITY = None
    PAIRED = _paired_cp3()
    #: The arm table's comparisons plus the contrasts the preregistration names (the
    #: chain minus each control).
    DECLARED_PAIRS = {(arm, control) for arm, (_f, control) in ARMS.items() if control} \
        | {("CH", "CH_cut"), ("CH", "CH_free"), ("CH", "CH_L2"), ("CH", "C0")}
    declared_counters = staticmethod(declared_counters_cp3)
    source_problems = staticmethod(source_problems_cp3)
    metrics_row = staticmethod(metrics_row_cp3)
    annotate_pairs = staticmethod(annotate_pairs_cp3)
    report_extra = staticmethod(lambda rows: [])


CHECKPOINTS = {1: CP1, 2: CP2, 3: CP3}


# --- Running ----------------------------------------------------------------------

def preregistration_frozen(path: Path = PREREGISTRATION) -> bool:
    """Whether the preregistration's status line reads FROZEN (the lead's freeze)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(line.startswith("Status:") and "FROZEN" in line and "DRAFT" not in line
               for line in text.splitlines())


def jobs_for(cohort: str, seeds: str, arms: list[str], cp=None) -> list[tuple[str, str, int, list[str], bool]]:
    """(arm, stratum tag, seed, extra world flags, first world of its stratum) per run;
    procedural worlds first (they take longest)."""
    cp = _cp(cp)
    strata = ["procedural", "template"] if seeds == "all" else [seeds]
    out = []
    for stratum in strata:
        for i, seed in enumerate(cp.COHORTS[cohort][stratum]):
            for arm in arms:
                out.append((arm, cp.TAGS[stratum], seed, cp.PROCEDURAL if stratum == "procedural" else [], i == 0))
    return out


def simulate(cmd: list[str]) -> subprocess.CompletedProcess:
    """One simulation of this checkout's ``src`` (the shared run environment)."""
    return subprocess.run(cmd, cwd=REPO, env=LS._run_env(), capture_output=True, text=True)


def run_one(out: Path, cohort: str, arm: str, stratum: str, seed: int, extra: list[str], keep: bool,
            cp=None) -> dict:
    cp = _cp(cp)
    d = (out / "runs" / f"{arm}-{stratum}{seed}").resolve()
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    flags = list(cp.ARMS[arm][0])
    cmd = [PY, "-m", "chronicler.main", "--seed", str(seed), *cp.BASE, *extra, *flags,
           "--output", str(d / "chronicle.md"), "--state", str(d / "state.json"),
           *rules_flags([*cp.BASE, *extra, *flags], cp)]
    t0 = time.time()
    p = simulate(cmd)
    row = {"cohort": cohort, "arm": arm, "stratum": stratum, "seed": seed, "rc": p.returncode,
           "wall_s": round(time.time() - t0, 1)}
    if cp.CHECKPOINT != 1:
        row = {"checkpoint": cp.CHECKPOINT, **row}
    if p.returncode != 0:
        row["error"] = (p.stderr or "")[-2000:]
    else:
        t1 = time.time()
        try:
            row.update(cp.metrics_row(d / "chronicle_bundle.json", flags))
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


def _checkpoint_option(ap) -> None:
    ap.add_argument("--checkpoint", type=int, choices=sorted(CHECKPOINTS), default=1,
                    help="the checkpoint's arms, outcomes, seeds and preregistration (default 1)")


def _foreign_rows(rows, cp) -> list[str]:
    """Rows of another checkpoint (rows without a checkpoint are checkpoint 1's)."""
    return [f"{r['arm']} {r['stratum']}{r['seed']}: row of checkpoint {r.get('checkpoint', 1)}"
            for r in rows if r.get("checkpoint", 1) != cp.CHECKPOINT]


_RUN_HEADER = re.compile(r"^(?:checkpoint (\d+); )?cohort (\w+); ")


def recorded_run(source_text: str) -> tuple[int, str] | None:
    """The checkpoint and cohort a run directory was started with: the first run header
    ``run`` appends to ``source.txt`` (checkpoint 1 writes no checkpoint prefix). A
    resume is refused unless it matches, even when no row was written before the run
    was killed."""
    for line in source_text.splitlines():
        m = _RUN_HEADER.match(line)
        if m:
            return int(m.group(1) or 1), m.group(2)
    return None


def run_main(argv) -> int:
    ap = argparse.ArgumentParser(prog="productive_recovery_screens.py run")
    ap.add_argument("out")
    _checkpoint_option(ap)
    ap.add_argument("--cohort", choices=("held", "pilot"), required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--arms", default=None, help="comma-separated arms (default: every arm of the checkpoint)")
    ap.add_argument("--seeds", choices=("all", "template", "procedural"), default="all")
    ap.add_argument("--keep-first", action="store_true", help="keep the first world of each stratum")
    ap.add_argument("--resume", action="store_true",
                    help="continue an interrupted run in OUT_DIR on the same source (rows already written are kept)")
    a = ap.parse_args(argv)
    cp = CHECKPOINTS[a.checkpoint]
    check_seeds(cp)
    check_extractor(cp)
    if a.cohort == "held" and not preregistration_frozen(cp.PREREGISTRATION):
        raise SystemExit(f"held run refused: {cp.PREREGISTRATION.relative_to(REPO)} is not marked FROZEN")
    chosen = a.arms.split(",") if a.arms else list(cp.ARMS)
    unknown = [arm for arm in chosen if arm not in cp.ARMS]
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
        started = recorded_run(recorded)
        if started is None:
            raise SystemExit(f"resume refused: {out / 'source.txt'} records no run header")
        if started != (cp.CHECKPOINT, a.cohort):
            raise SystemExit(f"resume refused: {out} was started as checkpoint {started[0]}, cohort {started[1]}, "
                             f"not checkpoint {cp.CHECKPOINT}, cohort {a.cohort}")
        for line in metrics.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("cohort") != a.cohort:
                    raise SystemExit(f"{metrics} holds a row of cohort {r.get('cohort')}, not {a.cohort}")
                if r.get("checkpoint", 1) != cp.CHECKPOINT:
                    raise SystemExit(f"{metrics} holds a row of checkpoint {r.get('checkpoint', 1)}, "
                                     f"not {cp.CHECKPOINT}")
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
        prefix = f"checkpoint {cp.CHECKPOINT}; " if cp.CHECKPOINT != 1 else ""
        fh.write(f"{prefix}{'resumed' if a.resume else 'cohort'} {a.cohort}; seeds {a.seeds}; "
                 f"arms {','.join(chosen)}; jobs {a.jobs}; rows already written {len(done)}\n"
                 f"started {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
    print(text, end="", flush=True)
    jobs = [j for j in jobs_for(a.cohort, a.seeds, chosen, cp) if (j[0], j[1], j[2]) not in done]
    rows, t0 = [], time.time()
    with open(metrics, "a", encoding="utf-8") as fh, ThreadPoolExecutor(a.jobs) as ex:
        # Each row is written as soon as its run finishes, so a killed run loses only
        # the runs still in flight (``--resume`` runs those).
        futures = [ex.submit(run_one, out, a.cohort, j[0], j[1], j[2], j[3], a.keep_first and j[4], cp)
                   for j in jobs]
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


def report_lines(rows, cp=None) -> list[str]:
    cp = _cp(cp)
    cohorts = sorted({r.get("cohort", "held") for r in rows})
    labels = cp.LABELS[cohorts[0]] if len(cohorts) == 1 else {"t": "template", "p": "procedural"}
    cp.annotate_pairs(rows)
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    fails = [r for r in rows if r["rc"] != 0]
    seconds = sum(_run_seconds(r) for r in rows)
    out = [f"Runs: {len(rows)}; failed: {len(fails)} (missing outcomes: {sum(r['rc'] == 3 for r in rows)}); "
           f"simulation and extraction seconds total {seconds:.0f} ({seconds / 3600:.3f} core-hours)"]
    for f in fails:
        out.append(f"- FAILED {f['arm']} {f['stratum']}{f['seed']} (rc {f['rc']}): {f.get('error', '')[-300:]}")
    for arm in cp.ARMS:
        for s in labels:
            cohort = cohorts[0] if len(cohorts) == 1 else "held"
            stratum = "template" if s == "t" else "procedural"
            for seed in cp.COHORTS[cohort][stratum]:
                if (arm, s, seed) not in by:
                    out.append(f"- INCOMPLETE {arm} {s}{seed}: not run")

    out.append("\n### Run time per arm (simulation and extraction seconds per run: mean [min, max])\n")
    out.append("| Arm | " + " | ".join(labels[s] for s in labels) + " |")
    out.append("| --- | " + " | ".join("---" for _ in labels) + " |")
    for arm in cp.ARMS:
        cells = [_rng([_run_seconds(r) for r in rows if r["arm"] == arm and r["stratum"] == s], "{:.1f}")
                 for s in labels]
        out.append(f"| {arm} | " + " | ".join(cells) + " |")

    out.append("\n### Shared outcomes vs each arm's control (mean [min, max] over worlds)\n")
    out.append("| Arm | Control | Stratum | Worlds | Population | Treasury |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    for arm, (_flags, control) in cp.ARMS.items():
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
    out.extend(LS.per_world_table(rows, cp.PAIRED, labels))
    out.extend(cp.report_extra(rows))

    out.append("\n### Activation funnels (mean per world [min, max]; z = worlds at zero)\n")
    for s in labels:
        out.append(f"\n**{labels[s]}**\n")
        for arm in cp.ARMS:
            rs = [r for r in rows if r["arm"] == arm and r["stratum"] == s and r["rc"] == 0]
            for name in cp.OUTCOMES:
                cs = [r["pk"][name] for r in rs if name in r.get("pk", {})]
                if not cs:
                    continue
                cells = []
                for k in cp.OUTCOMES[name]:
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


def projected_held_core_hours(rows, cp=None) -> float | None:
    """Pilot run time (simulation and extraction) per arm and stratum times the held worlds
    per stratum, in core-hours (None if a pilot arm is missing)."""
    cp = _cp(cp)
    total = 0.0
    for arm in cp.ARMS:
        for stratum, tag in cp.TAGS.items():
            walls = [_run_seconds(r) for r in rows if r["arm"] == arm and r["stratum"] == tag]
            if not walls:
                return None
            total += mean(walls) * len(cp.HELD[stratum])
    return total / 3600


def _read_rows(path, cp) -> list[dict]:
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    foreign = _foreign_rows(rows, cp)
    if foreign:
        raise SystemExit(f"{path} holds rows of another checkpoint than {cp.CHECKPOINT}: " + "; ".join(foreign[:5]))
    return rows


def report_main(argv) -> int:
    ap = argparse.ArgumentParser(prog="productive_recovery_screens.py report")
    ap.add_argument("metrics")
    _checkpoint_option(ap)
    a = ap.parse_args(argv)
    cp = CHECKPOINTS[a.checkpoint]
    rows = _read_rows(a.metrics, cp)
    lines = report_lines(rows, cp)
    if all(r.get("cohort") == "pilot" for r in rows):
        hours = projected_held_core_hours(rows, cp)
        lines.insert(1, "Projected held run time from this pilot: "
                     + (f"{hours:.3f} core-hours for {len(cp.ARMS) * sum(map(len, cp.HELD.values()))} runs"
                        if hours is not None else "unknown (an arm or stratum is missing)"))
    print("\n".join(lines))
    return 0


# --- Check ------------------------------------------------------------------------

def check_metrics(rows, cohort: str, cp=None) -> list[str]:
    """Every arm and world of the cohort has exactly one row of the checkpoint, and none failed."""
    cp = _cp(cp)
    problems = _foreign_rows(rows, cp)
    seen: dict = {}
    for r in rows:
        key = (r["arm"], r["stratum"], r["seed"])
        seen[key] = seen.get(key, 0) + 1
        if r.get("cohort", cohort) != cohort:
            problems.append(f"{r['arm']} {r['stratum']}{r['seed']}: row of cohort {r.get('cohort')}")
        if r["rc"] != 0:
            problems.append(f"{r['arm']} {r['stratum']}{r['seed']}: rc {r['rc']}: {r.get('error', '')[-300:]}")
    for stratum, tag in cp.TAGS.items():
        for seed in cp.COHORTS[cohort][stratum]:
            for arm in cp.ARMS:
                n = seen.get((arm, tag, seed), 0)
                if n != 1:
                    problems.append(f"{arm} {tag}{seed}: {n} rows")
    extra = sorted(k for k in seen if k[0] not in cp.ARMS
                   or k[2] not in cp.COHORTS[cohort]["template" if k[1] == "t" else "procedural"])
    problems += [f"{a} {s}{seed}: not in the cohort" for a, s, seed in extra]
    return problems


def check_main(argv) -> int:
    ap = argparse.ArgumentParser(prog="productive_recovery_screens.py check")
    _checkpoint_option(ap)
    ap.add_argument("--metrics", default=None)
    ap.add_argument("--cohort", choices=("held", "pilot"), default=None)
    a = ap.parse_args(argv)
    cp = CHECKPOINTS[a.checkpoint]
    check_seeds(cp)
    check_extractor(cp)
    check_arm_flags(cp)
    print(f"extractor, seeds and {len(cp.ARMS)} arms: OK")
    if a.metrics:
        if a.cohort is None:
            raise SystemExit("--metrics needs --cohort")
        rows = [json.loads(line) for line in open(a.metrics, encoding="utf-8") if line.strip()]
        problems = check_metrics(rows, a.cohort, cp)
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
