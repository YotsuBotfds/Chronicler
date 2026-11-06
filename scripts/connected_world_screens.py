"""Connected-world program screens (CW1-CW6): run, report and check them.

    python scripts/connected_world_screens.py run OUT_DIR --screen CW1 --cohort pilot|held|reserve|dev [...]
    python scripts/connected_world_screens.py report OUT_DIR/metrics.jsonl --screen CW1
    python scripts/connected_world_screens.py check --screen CW1|all [--metrics ... --cohort ...]
    python scripts/connected_world_screens.py mark-run OUT_DIR --screen CW1
    python scripts/connected_world_screens.py registry

The generic runner, the seed rules, the fixed harm panel, activation, the compute
ceiling and the identities are in ``scripts/screen_runner.py``; the seed numbers
are reserved in ``scripts/seed_registry.json``; the page is
docs/integration/connected-world-screens.md.

CW2, CW3, CW5 and CW6 are **stubs**: only their cohorts are declared. Each slice
fills in its screen's base, arms, packages, outcomes (2-3 primary), activation
rule and extractor, writes its preregistration and sets ``ready=True``. Until
then every run of the screen is refused (``check`` reports it NOT READY, exit
code 2). CW4 (slice C1, quarantine rules) and CW1 (slice S1, the wage and
``paid_work`` enrollment; a two-phase screen) are declared below.

``DEV`` is a development-only smoke screen (no pilot or held cohort): it runs the
runner end to end on registered development worlds, e.g.

    python scripts/connected_world_screens.py run OUT --screen DEV --cohort dev --worlds t1 --turns 10 --jobs 1
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen_runner as SR  # noqa: E402  (the generic runner)

MODULE = Path(__file__).resolve()
PROGRESS = SR.REPO / "docs" / "superpowers" / "progress"

#: Shared by every screen (never held): template 5, procedural 19.
PILOT = {"template": (5,), "procedural": (19,)}
#: Placeholder base until a slice declares its own (every program arm is hybrid).
BASE = ("--turns", "200", "--agents", "hybrid", "--simulate-only")

#: Screen -> (title, the slice that fills it in, template held, procedural held).
_STUBS = {
    "CW1": ("S1 accounting and wages (A1-A2)", "S1", range(731, 737), range(831, 837)),
    "CW2": ("S2 workshop economics and owned-stock lifecycle (A3, A5)", "S2", range(741, 747), range(841, 847)),
    "CW3": ("S3 watershed and infrastructure (B1-B3)", "S3", range(751, 757), range(851, 857)),
    "CW4": ("S3 quarantine and public health (C1)", "S3", range(761, 767), range(861, 867)),
    "CW5": ("S4 trade, forest-water, care, attribution, requisition", "S4", range(771, 777), range(871, 877)),
    "CW6": ("S5 adaptive decisions, cross-border organisation, war; the integrated evaluation", "S5",
            range(781, 787), range(881, 887)),
}


def _stub(name: str, title: str, slice_: str, template, procedural) -> SR.Screen:
    return SR.Screen(
        name=name, title=title, preregistration=PROGRESS / f"connected-world-screens-{name.lower()}.md",
        base=BASE, arms={}, root=None, pilot=PILOT,
        held={"template": tuple(template), "procedural": tuple(procedural)},
        ready=False, not_ready=f"a stub: slice {slice_} declares its arms, outcomes, activation and extractor",
        module=MODULE)


SCREENS: dict[str, SR.Screen] = {name: _stub(name, *spec) for name, spec in _STUBS.items()}


# --- CW4: quarantine rules (slice C1) ----------------------------------------------
#
# Arms (a control chain QR -> QC -> Q0 -> QL): QL the legacy rule (the option omitted),
# Q0 no quarantine, QC the closure decisions and enforcement cost with nothing closed,
# QR the closures. Every arm: hybrid, epidemics and the contact ledger on (defaults).
# Turns are world turns w; the snapshot labelled s records world turn w = s - 1 (its
# epidemic tick, decisions and reports; history[n].epidemics.quarantine_rules.receipt.turn
# and food_accounting.source_turn equal s - 1).

#: Turns after a closing turn whose arrivals and deaths still count (preregistered).
CW4_K = 10
CW4_MODE = "--quarantine-mode"


def _cw4_snapshots(bundle: dict) -> dict[int, dict]:
    """World turn w -> its snapshot (labelled w + 1)."""
    out = {}
    for snap in bundle.get("history") or []:
        if isinstance(snap, dict) and SR._num(snap.get("turn")):
            out[int(snap["turn"]) - 1] = snap
    return out


def _cw4_mode(flags) -> str:
    flags = list(flags)
    return flags[flags.index(CW4_MODE) + 1] if CW4_MODE in flags else "legacy"


def cw4_windows(bundle: dict) -> tuple[dict[str, set[int]], dict[str, set[int]], list[str]]:
    """({civ: closing world turns}, {civ: window world turns}, problems).

    A civ closes at world turn w when it is in ``epidemics.quarantine`` of the snapshot
    of w (closing in QR, declared in QC, the legacy closure in QL; empty in Q0). Its
    window holds every world turn u with w + 1 <= u <= w + 1 + CW4_K for some closing
    turn w: the turns whose imports the closure (or its lag) could reach."""
    snaps = _cw4_snapshots(bundle)
    closing: dict[str, set[int]] = {}
    problems = []
    for w, snap in sorted(snaps.items()):
        epi = snap.get("epidemics")
        if not isinstance(epi, dict) or not isinstance(epi.get("quarantine"), list):
            problems.append(f"no epidemics.quarantine list at snapshot {w + 1}")
            continue
        for civ in epi["quarantine"]:
            closing.setdefault(civ, set()).add(w)
    last = max(snaps) if snaps else -1
    windows = {civ: {u for w in ws for u in range(w + 1, w + 2 + CW4_K) if u <= last}
               for civ, ws in closing.items()}
    return closing, windows, problems


def _cw4_rules(bundle: dict) -> list[dict]:
    return [r for s in bundle.get("history") or []
            if isinstance(r := SR._get(s, ("epidemics", "quarantine_rules")), dict)]


def cw4_activation(bundle: dict, flags) -> tuple[bool | None, str]:
    """QC and QR act when a closure (declared in QC) opened; Q0 acts by deciding nothing
    while outbreaks are reported (activated when one was)."""
    mode = _cw4_mode(flags)
    hist = bundle.get("history") or []
    if mode == "none":
        reported = sum(1 for s in hist if isinstance(SR._get(s, ("epidemics", "active")), list)
                       and s["epidemics"]["active"])
        return (reported > 0), f"{reported} snapshots with a reported outbreak; mode none decides nothing by rule"
    rules = _cw4_rules(bundle)
    if not rules:
        return None, "no quarantine rules record"
    opened = (rules[-1].get("totals") or {}).get("closures_opened")
    if not SR._num(opened):
        return None, "quarantine rules totals carry no closures_opened"
    return (opened > 0), f"{int(opened)} closures opened ({mode})"


def _cw4_rate(num: float | None, den: float | None, per: float) -> float | None:
    if num is None or den is None:
        return None
    return per * num / den if den > 0 else 0.0


def cw4_extract(bundle: dict, flags) -> tuple[dict, list[str]]:
    """The CW4 measures of one run (see the preregistration for every definition)."""
    mode = _cw4_mode(flags)
    snaps = _cw4_snapshots(bundle)
    closing, windows, problems = cw4_windows(bundle)
    region_names = [r.get("name") for r in ((bundle.get("world_state") or {}).get("regions") or [])]
    m: dict = {}
    # Rules record: present exactly under a new mode.
    rules = _cw4_rules(bundle)
    if mode == "legacy":
        if rules:
            problems.append("a quarantine rules record in the legacy arm")
    elif len(rules) != len(snaps):
        problems.append(f"quarantine rules recorded in {len(rules)} of {len(snaps)} snapshots under {mode}")
    elif any(r.get("mode") != mode for r in rules):
        problems.append(f"quarantine rules mode differs from {mode}")
    # Primary 1 (whole run, world): every cross-polity arrival. Secondary (selection):
    # those into window civs' regions during their windows.
    arrivals = arrivals_world = 0
    for ev in bundle.get("events_timeline") or []:
        if ev.get("event_type") != "epidemic_arrival":
            continue
        actors, turn = ev.get("actors") or [], ev.get("turn")
        if not SR._num(turn) or len(actors) != 2 or actors[0] == actors[1]:
            continue   # not cross-polity (same polity, or an uncontrolled source or target)
        arrivals_world += 1
        if int(turn) in windows.get(actors[0], ()):
            arrivals += 1
    m["arrivals_world"] = arrivals_world
    window_ct = sum(len(ws) for ws in windows.values())
    m["arrivals"] = arrivals
    m["window_civ_turns"] = window_ct
    m["arrivals_per_100_window_civ_turns"] = _cw4_rate(arrivals, window_ct, 100.0)
    # Primary 2: epidemic deaths (reported outbreaks) per 1,000 person-turns of window civs.
    deaths = person_turns = 0.0
    stab = []
    reported_deaths = world_deaths = world_pt = 0.0
    region_turns = 0
    food_net = 0.0
    food_seen = False
    for w, snap in sorted(snaps.items()):
        epi = snap.get("epidemics") or {}
        control = snap.get("region_control")
        civs = snap.get("civ_stats")
        if not isinstance(control, dict) or not isinstance(civs, dict):
            problems.append(f"snapshot {w + 1} lacks region_control or civ_stats")
            continue
        active = epi.get("active") if isinstance(epi.get("active"), list) else []
        # Primary 2 (whole run, world): ALL epidemic deaths of the tick (epidemics.deaths,
        # reported or not; they sum to deaths_total) per person-turn of the whole world
        # (regional_population.counts at the end of the turn, every region).
        turn_deaths = epi.get("deaths")
        if SR._num(turn_deaths):
            world_deaths += turn_deaths
        else:
            problems.append(f"epidemics.deaths missing at snapshot {w + 1}")
        regional = snap.get("regional_population")
        counts = regional.get("counts") if isinstance(regional, dict) else None
        if not isinstance(counts, list) or not all(SR._num(c) for c in counts) \
                or regional.get("source_turn") != w:
            problems.append(f"regional_population counts missing or misdated at snapshot {w + 1}")
        else:
            world_pt += sum(counts)
            region_turns += len(counts)
        by_civ: dict[str, float] = {}
        for row in active:
            d = row.get("deaths")
            if SR._num(d):
                reported_deaths += d
                owner = control.get(row.get("region"))
                if owner is not None:
                    by_civ[owner] = by_civ.get(owner, 0.0) + d
        fa = snap.get("food_accounting")
        for civ, ws in windows.items():
            if w not in ws:
                continue
            stats = civs.get(civ)
            if isinstance(stats, dict):
                person_turns += stats.get("population") or 0
                if SR._num(stats.get("stability")):
                    stab.append(stats["stability"])
            deaths += by_civ.get(civ, 0.0)
            if isinstance(fa, dict) and isinstance(fa.get("regions"), list):
                for reg in fa["regions"]:
                    rid = reg.get("region_id")
                    native = reg.get("native") or {}
                    if (SR._num(rid) and 0 <= rid < len(region_names)
                            and control.get(region_names[int(rid)]) == civ and SR._num(native.get("transport_net"))):
                        food_net += native["transport_net"]
                        food_seen = True
    m["deaths_closing"] = deaths
    m["person_turns_closing"] = person_turns
    m["deaths_per_1000_pt_closing"] = _cw4_rate(deaths, person_turns, 1000.0)
    m["world_epidemic_deaths"] = SR.harm_value({"harm": {"d": SR.harm_epidemic_deaths(bundle)}}, "d")
    if m["world_epidemic_deaths"] is not None and world_deaths != m["world_epidemic_deaths"]:
        problems.append(f"per-turn epidemic deaths sum to {world_deaths}, deaths_total is "
                        f"{m['world_epidemic_deaths']}")
    m["world_person_turns"] = world_pt
    m["world_deaths_per_1000_pt"] = _cw4_rate(world_deaths, world_pt, 1000.0)
    m["region_turns"] = region_turns
    m["arrivals_world_per_1000_region_turns"] = _cw4_rate(arrivals_world, region_turns, 1000.0)
    m["reported_death_share"] = (reported_deaths / world_deaths) if world_deaths > 0 else None
    m["stability_closing_mean"] = (sum(stab) / len(stab)) if stab else None
    m["food_net_transport_closing"] = food_net if food_seen or not windows else None
    last = snaps[max(snaps)] if snaps else {}
    end = last.get("civ_stats") if isinstance(last.get("civ_stats"), dict) else {}
    m["treasury_closing_end"] = sum((end.get(c) or {}).get("treasury") or 0 for c in closing)
    m["closing_civs"] = len(closing)
    # Partners (QC, QR): civs closed against at any decision.
    if rules:
        partners = {c.get("target") for r in rules for c in r.get("closures") or [] if isinstance(c, dict)}
        partners.discard(None)
        m["partner_civs"] = len(partners)
        m["partner_population_end"] = sum((end.get(c) or {}).get("population") or 0 for c in partners)
        m["partner_treasury_end"] = sum((end.get(c) or {}).get("treasury") or 0 for c in partners)
        totals = rules[-1].get("totals") or {}
        for key in ("closures_opened", "closed_pair_turns", "route_turns_removed", "forgone_income",
                    "enforcement_paid", "merchant_edges_removed", "leaked_deliveries"):
            if not SR._num(totals.get(key)):
                problems.append(f"quarantine rules totals lack {key}")
            m[key] = totals.get(key)
        if mode != "closure":
            # Nothing is closed outside closure: these are recorded structural zeros there.
            m["leaked_deliveries"] = None
    else:
        for key in ("partner_civs", "partner_population_end", "partner_treasury_end", "closures_opened",
                    "closed_pair_turns", "route_turns_removed", "forgone_income", "enforcement_paid",
                    "merchant_edges_removed", "leaked_deliveries"):
            m[key] = None   # not recorded: no rules state (legacy) - never zero
    stats = (bundle.get("metadata") or {}).get("merchant_trip_stats")
    if isinstance(stats, list) and stats:
        m["merchant_replans"] = sum(t.get("disruption_replans") or 0 for t in stats if isinstance(t, dict))
        m["merchant_unwinds"] = sum(t.get("unwind_count") or 0 for t in stats if isinstance(t, dict))
        m["merchant_stalled"] = sum(t.get("stalled_trip_count") or 0 for t in stats if isinstance(t, dict))
    else:
        problems.append("metadata.merchant_trip_stats missing (hybrid runs record it every tick)")
    return m, problems


def _m(key):
    return lambda row: (row.get("m") or {}).get(key)


_CW4_BASE = ("--turns", "200", "--agents", "hybrid", "--simulate-only")
SCREENS["CW4"] = SR.Screen(
    name="CW4", title="S3 quarantine and public health (C1)",
    preregistration=PROGRESS / "connected-world-screens-cw4.md",
    base=_CW4_BASE,
    arms={"QL": ((), None),
          "Q0": ((CW4_MODE, "none"), "QL"),
          "QC": ((CW4_MODE, "cost_only"), "Q0"),
          "QR": ((CW4_MODE, "closure"), "QC")},
    root="QL", pilot=PILOT, held={"template": tuple(range(761, 767)), "procedural": tuple(range(861, 867))},
    outcomes=(
        # Primaries (Amendment 1): whole-run, world-level outcomes, unconditioned on any
        # arm's own closures.
        SR.Outcome("cw4_world_arrivals", "Cross-polity epidemic arrivals over the whole run, world (QR - QC)",
                   "QR", "QC", _m("arrivals_world"), primary=True),
        SR.Outcome("cw4_world_death_rate", "World epidemic deaths (all) per 1,000 person-turns over the whole run "
                   "(QR - QC)", "QR", "QC", _m("world_deaths_per_1000_pt"), primary=True),
        SR.Outcome("cw4_world_arrival_rate", "Cross-polity arrivals per 1,000 region-turns, world (QR - QC)",
                   "QR", "QC", _m("arrivals_world_per_1000_region_turns")),
        SR.Outcome("cw4_world_deaths", "World epidemic deaths, count (QR - QC)", "QR", "QC",
                   _m("world_epidemic_deaths")),
        # Conditioned on each arm's own closures (selection): windows follow the arm's trajectory.
        SR.Outcome("cw4_sel_arrivals", "Arrivals into closing civs' regions in their windows (QR - QC; "
                   "conditioned on each arm's own closures: selection)", "QR", "QC", _m("arrivals")),
        SR.Outcome("cw4_sel_deaths", "Epidemic deaths (reported outbreaks) per 1,000 person-turns of closing civs "
                   "in their windows (QR - QC; conditioned on each arm's own closures: selection)", "QR", "QC",
                   _m("deaths_per_1000_pt_closing")),
        SR.Outcome("cw4_sel_arrival_rate", "Arrivals per 100 window civ-turns (QR - QC; conditioned on each arm's "
                   "own closures: selection)", "QR", "QC", _m("arrivals_per_100_window_civ_turns")),
        SR.Outcome("cw4_sel_window", "Window civ-turns (QR - QC; conditioned on each arm's own closures: "
                   "selection)", "QR", "QC", _m("window_civ_turns")),
        SR.Outcome("cw4_cost_world_deaths", "World epidemic deaths per 1,000 person-turns (QC - Q0: the cost "
                   "effect)", "QC", "Q0", _m("world_deaths_per_1000_pt")),
        SR.Outcome("cw4_cost_world_arrivals", "Cross-polity arrivals, world (QC - Q0: the cost effect)", "QC", "Q0",
                   _m("arrivals_world")),
        SR.Outcome("cw4_cost_treasury", "World treasury at the end (QC - Q0: the cost effect)", "QC", "Q0",
                   lambda r: SR.harm_value(r, "treasury")),
        # The legacy comparison QL - QR, reported as QR - QL (the runner pairs an arm with a
        # control on its chain; the sign is the negative of QL - QR).
        SR.Outcome("cw4_legacy_world_arrivals", "Cross-polity arrivals, world (QR - QL)", "QR", "QL",
                   _m("arrivals_world")),
        SR.Outcome("cw4_legacy_world_death_rate", "World epidemic deaths per 1,000 person-turns (QR - QL)", "QR", "QL",
                   _m("world_deaths_per_1000_pt")),
        SR.Outcome("cw4_h_forgone", "Route income forgone, both sides (QR alone; structurally 0 in QC)", "QR", None,
                   _m("forgone_income")),
        SR.Outcome("cw4_h_food", "Net food transport into closing civs' regions in their windows (QR - QC)",
                   "QR", "QC", _m("food_net_transport_closing")),
        SR.Outcome("cw4_h_replans", "Merchant disruption replans, world (QR - QC)", "QR", "QC",
                   _m("merchant_replans")),
        SR.Outcome("cw4_h_unwinds", "Merchant unwinds, world (QR - QC)", "QR", "QC", _m("merchant_unwinds")),
        SR.Outcome("cw4_h_treasury", "Closing civs' treasury at the end (QR - QC)", "QR", "QC",
                   _m("treasury_closing_end")),
        SR.Outcome("cw4_h_stability", "Closing civs' mean stability in their windows (QR - QC)", "QR", "QC",
                   _m("stability_closing_mean")),
        SR.Outcome("cw4_h_partner_population", "Partner civs' population at the end (QR - QC)", "QR", "QC",
                   _m("partner_population_end")),
        SR.Outcome("cw4_h_partner_treasury", "Partner civs' treasury at the end (QR - QC)", "QR", "QC",
                   _m("partner_treasury_end")),
        SR.Outcome("cw4_h_leaked", "Deliveries still crossing a closed pair (QR alone)", "QR", None,
                   _m("leaked_deliveries")),
        SR.Outcome("cw4_h_enforcement", "Enforcement paid (QR - QC)", "QR", "QC", _m("enforcement_paid")),
    ),
    activation=cw4_activation, extract=cw4_extract, ready=True, module=MODULE)


# --- CW1: the wage and paid_work enrollment (slice S1: A1-A2) ----------------------
#
# AUDIT-A1-A2 section 4.2. Under the paid_work boundary a paid granary crew enrolls its
# region in retail, so payment decides enrollment. Two phases per world: A (CH@pw) and B
# (U@pw) run first; their recorded pilot intervals (S_A, S_B; exact since S1) are frozen
# and hashed by the runner (``SR.Derived``) before C (U@S_A: no wage, A's enrollment) and
# D (CH@S_B: the wage, B's enrollment) replay them with the schedule boundary. Every arm:
# the checkpoint-3 base, retail rules version 2 and the A1 wealth ledger (an observer).
# Money is in wealth units (the native balance; the ledger's milli-units / 1000).

CW1_SCHEDULE = "--household-retail-schedule"
CW1_BOUNDARY = "--household-retail-boundary"
#: Checkpoint 3's base (productive_recovery_screens.CP3.BASE), then retail rules 2 and the ledger.
CW1_BASE = ("--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves", "--public-grain-shipments",
            "--scholarship", "--techniques", "--academy-services", "--grain-storage", "--food-allocation", "--workshops",
            "--operating-wear", "--repair-projects", "--timber-stock",
            "--household-retail", "--household-retail-rules", "2", "--wealth-accounting")
CW1_CHAIN = ("--timber-supply", "--recovery-crews", "--remittances")
CW1_UNPAID = ("--timber-supply", "--recovery-crews", "--recovery-crew-mode", "unpaid", "--remittances")
CW1_NO_TS = ("--recovery-crews", "--remittances")
#: Ledger channels of wages paid to households (A1 typed flows; absent channels add 0).
CW1_WAGES = ("workshop_wage", "apprentice_stipend", "repair_wage", "granary_crew_wage", "woodcut_wage")
#: RL5 household groups read (``household_retail_state.COHORT_GROUPS``): crew households are
#: crew members and their co-resident children.
CW1_GROUPS = {"crew": ("crew", "crew_children"), "nonfarm": ("nonfarm_adults",), "children_alone": ("children_alone",)}
_MILLI = 1000


def _flag(flags, name: str, default=None):
    flags = list(flags)
    return flags[flags.index(name) + 1] if name in flags else default


def _cw1_retail(bundle: dict) -> list[tuple[dict, dict | None, dict | None]]:
    """(snapshot, retail record, ledger record) per snapshot."""
    out = []
    for snap in bundle.get("history") or []:
        lv = snap.get("livelihoods") if isinstance(snap, dict) else None
        lv = lv if isinstance(lv, dict) else {}
        out.append((snap, lv.get("household_retail"), lv.get("wealth_accounting")))
    return out


def _cw1_last(records) -> dict:
    found = [hr for _s, hr, _w in records if isinstance(hr, dict)]
    return found[-1] if found else {}


def cw1_schedule(bundle: dict, flags) -> tuple[bytes, dict]:
    """The derived file of A and B: the arm's exact pilot intervals as the canonical
    schedule JSON ``--household-retail-schedule`` reads (``household_retail.extract_schedule``)."""
    SR._src()
    from chronicler import household_retail as HR
    found = HR.extract_schedule(bundle)
    if not found["exact"]:
        raise ValueError("the bundle records no pilot intervals: its schedule would be approximate")
    data = HR.canonical_schedule(found["schedule"])
    counters = _cw1_last(_cw1_retail(bundle)).get("counters") or {}
    return data, {"canonical_sha256": found["sha256"], "regions": len(found["schedule"]),
                  "intervals": sum(len(v) for v in found["schedule"].values()),
                  "pilot_region_turns": counters.get("pilot_region_turns", 0),
                  "regions_closed": found["regions_closed"], "closures": len(found["closures"])}


def cw1_replay(bundle: dict, flags) -> dict | None:
    """A schedule arm's replay check: the intervals it recorded against the schedule it
    was given (None outside the schedule boundary)."""
    if _flag(flags, CW1_BOUNDARY) != "schedule":
        return None
    SR._src()
    from chronicler import household_retail as HR
    last = _cw1_last(_cw1_retail(bundle))
    given = last.get("schedule") or {}
    want = {int(k): v for k, v in (given.get("turns") or {}).items()}
    try:
        got = HR.extract_schedule(bundle)
    except ValueError as error:
        return {"exact": False, "given_sha256": given.get("sha256"), "recorded_sha256": None, "differ": [],
                "error": str(error)}
    differ = sorted(r for r in set(want) | set(got["schedule"]) if want.get(r) != got["schedule"].get(r))
    file_sha = None
    path = _flag(flags, CW1_SCHEDULE)
    if path and Path(path).is_file():
        file_sha = SR.sha256_file(Path(path))
    return {"exact": not differ and got["sha256"] == given.get("sha256"), "given_sha256": given.get("sha256"),
            "recorded_sha256": got["sha256"], "file_sha256": file_sha, "differ": differ[:16]}


def _cw1_typed(frame: dict) -> dict[str, dict]:
    return {row.get("channel"): row for row in frame.get("typed") or [] if isinstance(row, dict)}


def _cw1_region_set(last: dict, flags) -> set[int]:
    """The arm's region set: the regions its schedule names (C, D) or every region it ever
    enrolled (its recorded pilot intervals)."""
    if _flag(flags, CW1_BOUNDARY) == "schedule":
        return {int(k) for k in ((last.get("schedule") or {}).get("turns") or {})}
    return {int(k) for k in (last.get("intervals") or {})}


def cw1_extract(bundle: dict, flags) -> tuple[dict, list[str]]:
    """The CW1 measures of one run (the preregistration states every formula)."""
    records = _cw1_retail(bundle)
    last = _cw1_last(records)
    n = len((bundle.get("world_state") or {}).get("regions") or [])
    boundary = _flag(flags, CW1_BOUNDARY, "market")
    problems: list[str] = []
    if not last:
        return {}, ["no household retail record"]
    region_set = _cw1_region_set(last, flags)
    m: dict = {"boundary": boundary, "regions": len(region_set), "region_set": sorted(region_set)}
    counters = last.get("counters") or {}
    m["pilot_region_turns"] = counters.get("pilot_region_turns", 0)
    totals = dict.fromkeys(("wages", "remittance", "procurement", "located_set", "unlocated", "food_set",
                            *CW1_WAGES), 0)
    income_world = income_set = 0.0
    priced = persons = rations = 0.0
    groups = {g: {"priced_out": 0, "persons": 0, "known_priced_out": 0, "unknown_frames": 0, "count_known": True}
              for g in CW1_GROUPS}
    turns = wa_unobserved = hr_unobserved = unprovisioned = 0
    bad_turns: dict[str, list] = {}

    def bad(kind: str, turn) -> None:
        bad_turns.setdefault(kind, []).append(turn)

    for snap, hr, wa in records:
        turn = snap.get("turn")
        if hr is None:
            bad("no retail record", turn)
            continue
        turns += 1
        if hr.get("boundary") != boundary or hr.get("rules_version") != 2 or hr.get("mode") != "retail":
            bad("retail not in rules 2, retail mode and this arm's boundary", turn)
        frames = hr.get("regions")
        frame = wa.get("frame") if isinstance(wa, dict) else None
        if not isinstance(wa, dict):
            bad("no ledger record", turn)
            continue
        if frames is None:
            hr_unobserved += 1
        if frame is None:
            wa_unobserved += 1
            if frames:
                bad("ledger frame missing beside retail frames", turn)
            continue
        if frame.get("turn") != hr.get("source_turn") or wa.get("source_turn") != hr.get("source_turn"):
            bad("ledger and retail frames of different turns", turn)
            continue
        if not frame.get("typed_complete"):
            bad("ledger typed flows incomplete", turn)
        typed = _cw1_typed(frame)
        for c in CW1_WAGES:
            v = (typed.get(c) or {}).get("in_milli", 0)
            totals[c] += v
            totals["wages"] += v
        totals["remittance"] += (typed.get("remittance") or {}).get("in_milli", 0)
        totals["procurement"] += (typed.get("food_procurement") or {}).get("in_milli", 0)
        totals["unlocated"] += sum((typed.get(c) or {}).get("unlocated_in_milli", 0) for c in (*CW1_WAGES, "remittance"))
        withheld = frame.get("withheld") or {}
        replaced = withheld.get("retail_income_replaced")
        if frames and not SR._num(replaced):
            bad("ledger retail income replaced missing beside retail frames", turn)
        income_world += replaced if SR._num(replaced) else 0.0
        located = {int(r["region"]): int(r.get("typed_in_milli", 0)) for r in frame.get("regions") or []
                   if isinstance(r, dict) and SR._num(r.get("region"))}
        food: dict[int, int] = {}
        frame_income = 0.0
        for f in frames or ():
            rid, prov = f.get("region"), f.get("provisioning")
            if SR._num(f.get("income_replaced")):
                frame_income += f["income_replaced"]
                if rid in region_set:
                    income_set += f["income_replaced"]
            if not prov:
                unprovisioned += 1
                continue
            food[int(rid)] = food.get(int(rid), 0) + round(float(prov.get("credited_milli", 0.0)))
            if rid not in region_set:
                if prov.get("priced_out_persons"):
                    bad("priced-out persons outside the region set", turn)
                continue
            if not all(SR._num(prov.get(k)) for k in ("priced_out_persons", "persons", "rations")):
                bad("provisioning row lacks priced_out_persons, persons or rations", turn)
                continue
            priced += prov["priced_out_persons"]
            persons += prov["persons"]
            rations += prov["rations"]
            cohorts = (f.get("cohorts") or {}).get("groups")
            if not isinstance(cohorts, dict):
                bad("provisioned region without RL5 cohorts", turn)
                continue
            exact = [cohorts.get(g, {}).get("priced_out") for g in ("crew", "crew_children", "children_alone",
                                                                     "nonfarm_adults", "other")]
            if all(SR._num(v) for v in exact) and abs(sum(exact) - prov["priced_out_persons"]) > 1e-9:
                bad("RL5 cohorts' priced-out persons differ from the provisioning row", turn)
            for g, parts in CW1_GROUPS.items():
                po = [cohorts.get(p, {}).get("priced_out") for p in parts]
                ps = [cohorts.get(p, {}).get("persons") for p in parts]
                if not all(SR._num(v) for v in po):
                    groups[g]["count_known"] = False
                else:
                    groups[g]["priced_out"] += sum(po)
                if all(SR._num(v) for v in po + ps):
                    groups[g]["known_priced_out"] += sum(po)
                    groups[g]["persons"] += sum(ps)
                else:
                    groups[g]["unknown_frames"] += 1
        if SR._num(replaced) and abs(frame_income - replaced) > 1e-6 * max(1.0, abs(replaced)):
            bad("retail frames' income replaced differs from the ledger's", turn)
        # The ledger locates every typed inflow but procurement and domestic credit by region;
        # a region's inflow less its retail sales is its wages and remittances received.
        lhs = sum(v - food.get(r, 0) for r, v in located.items()) - sum(v for r, v in food.items() if r not in located)
        rhs = sum((row.get("in_milli", 0) - row.get("unlocated_in_milli", 0))
                  for c, row in typed.items() if c != "food_purchase")
        if lhs != rhs:
            bad("ledger located inflows less retail sales differ from its non-sale located channels", turn)
        for r in region_set:
            v = located.get(r, 0) - food.get(r, 0)
            if v < 0:
                bad("a region's ledger inflow below its retail sales", turn)
            totals["located_set"] += v
            totals["food_set"] += food.get(r, 0)
    for kind, ts in bad_turns.items():
        problems.append(f"{kind} at snapshots {ts[:5]}{' ...' if len(ts) > 5 else ''} ({len(ts)})")
    m["turns"] = turns
    m["wa_unobserved_turns"] = wa_unobserved
    m["hr_unobserved_turns"] = hr_unobserved
    m["unprovisioned_frames"] = unprovisioned
    for c in CW1_WAGES:
        m[f"{c}s"] = totals[c] / _MILLI
    m["wages_world"] = totals["wages"] / _MILLI
    m["remittance_world"] = totals["remittance"] / _MILLI
    m["procurement_world"] = totals["procurement"] / _MILLI
    m["income_replaced_world"] = income_world
    m["income_replaced_set"] = income_set
    m["located_in_set"] = totals["located_set"] / _MILLI
    m["money_unlocated"] = totals["unlocated"] / _MILLI
    # P2 (and the world comparisons): wages + remittances credited + procurement credited
    # - farm income replaced, every turn, the whole world (the ledger's typed channels).
    m["money_world"] = (totals["wages"] + totals["remittance"] + totals["procurement"]) / _MILLI - income_world
    # P1: the same over the arm's region set: located wages and remittances in the set,
    # procurement (credited to owners of grain in pilot regions, all in the set), less
    # the set's replaced farm income.
    m["money_set"] = (totals["located_set"] + totals["procurement"]) / _MILLI - income_set
    m["priced_out_set"] = priced
    m["persons_set"] = persons
    m["priced_out_rate_set"] = (priced / persons) if persons > 0 else None
    m["ration_mean_set"] = (rations / persons) if persons > 0 else None
    m["coverage"] = (m["pilot_region_turns"] / (n * turns)) if n and turns else None
    for g, acc in groups.items():
        m[f"rl5_{g}_priced_out"] = acc["priced_out"] if acc["count_known"] else None
        m[f"rl5_{g}_persons_known"] = acc["persons"]
        m[f"rl5_{g}_rate"] = (acc["known_priced_out"] / acc["persons"]) if acc["persons"] > 0 else None
        m[f"rl5_{g}_unknown_frames"] = acc["unknown_frames"]
    wa_last = next((w for _s, _h, w in reversed(records) if isinstance(w, dict)), {})
    wa_counters = wa_last.get("counters") or {}
    for key in ("continuity_broken", "closures_failed", "typed_incomplete_turns"):
        m[f"wa_{key}"] = wa_counters.get(key, 0)
    replay = cw1_replay(bundle, flags)
    if replay is not None:
        m["replay"] = replay
        if replay.get("file_sha256") is not None and replay["file_sha256"] != replay.get("given_sha256"):
            problems.append(f"the schedule file's sha256 {replay['file_sha256'][:12]} is not the digest the run "
                            f"recorded ({str(replay.get('given_sha256'))[:12]})")
    return m, problems


def cw1_activation(bundle: dict, flags) -> tuple[bool | None, str]:
    """Enrolled (pilot region-turns > 0); paid arms paid granary crew wages, unpaid arms
    paid none; a schedule arm replayed its schedule exactly."""
    records = _cw1_retail(bundle)
    last = _cw1_last(records)
    if not last:
        return None, "no household retail record"
    prt = (last.get("counters") or {}).get("pilot_region_turns", 0)
    granary = 0
    for _s, _h, wa in records:
        frame = wa.get("frame") if isinstance(wa, dict) else None
        if isinstance(frame, dict):
            granary += (_cw1_typed(frame).get("granary_crew_wage") or {}).get("in_milli", 0)
    paid = _flag(flags, "--recovery-crew-mode", "paid") == "paid"
    replay = cw1_replay(bundle, flags)
    acted = prt > 0 and ((granary > 0) if paid else (granary == 0))
    text = (f"{prt} pilot region-turns in {len(_cw1_region_set(last, flags))} regions; granary crew wages "
            f"{granary / _MILLI:.3f} ({'paid' if paid else 'unpaid'} arm)")
    if replay is not None:
        acted = acted and replay["exact"]
        text += "; schedule replayed " + ("exactly" if replay["exact"] else
                                          f"inexactly (regions {replay['differ']}{replay.get('error', '')})")
    return acted, text


def _cw1_report(rows, strata) -> list[str]:
    """Validity per world: enrollment, wages, the derived schedules and the replays."""
    out = ["\n## CW1 validity per world (enrollment, wages, schedules; before any effect)\n",
           ("| World | Arm | Regions | Pilot region-turns | Granary crew wages | Woodcut wages | Unlocated wages and "
            "remittances | Schedule |"), "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    arms = list(dict.fromkeys(r["arm"] for r in rows))
    order = [a for a in SCREENS["CW1"].arms if a in arms] + [a for a in arms if a not in SCREENS["CW1"].arms]
    for tag, seeds in strata.items():
        for seed in seeds:
            for arm in order:
                r = by.get((arm, tag, seed))
                if r is None:
                    continue
                if r["rc"] != 0:
                    out.append(f"| {tag}{seed} | {arm} | failed (rc {r['rc']}) | | | | | |")
                    continue
                m = r.get("m") or {}
                sched = ""
                for name, rec in (r.get("derived") or {}).items():
                    sched += f"made {name} {rec['sha256'][:12]} ({(rec.get('info') or {}).get('regions')} regions) "
                for name, rec in (r.get("inputs") or {}).items():
                    rp = m.get("replay") or {}
                    sched += (f"replays {name} {rec['sha256'][:12]}: "
                              + ("exact" if rp.get("exact") else f"INEXACT (regions {rp.get('differ')})"))
                out.append(f"| {tag}{seed} | {arm} | {m.get('regions')} | {m.get('pilot_region_turns')} | "
                           f"{m.get('granary_crew_wages', 0):.1f} | {m.get('woodcut_wages', 0):.1f} | "
                           f"{m.get('money_unlocated', 0):.3f} | {sched.strip()} |")
    return out


_CW1_S_A, _CW1_S_B = "{S_A}", "{S_B}"
_CW1_PW = (CW1_BOUNDARY, "paid_work")


def _cw1_sched(mark: str) -> tuple[str, ...]:
    return (CW1_BOUNDARY, "schedule", CW1_SCHEDULE, mark)


def _cw1_outcomes() -> tuple[SR.Outcome, ...]:
    O = SR.Outcome
    rate = "Priced-out person-turns per pilot person-turn"
    out = [
        O("cw1_p1_wage_money", "Money credited to households over S_A, wealth units: wages + remittances + "
          "procurement - farm income replaced (A - C: the wage at A's enrollment)", "A", "C", _m("money_set"),
          primary=True),
        O("cw1_p2_enrollment_money", "Money credited to households, world, wealth units (C - B: A's enrollment "
          "against B's, no wage)", "C", "B", _m("money_world"), primary=True),
        O("cw1_p3_wage_priced_out", f"{rate} over S_A (A - C)", "A", "C",
          _m("priced_out_rate_set"), primary=True),
        # The wage at A's enrollment: P1's terms and the world total.
        O("cw1_sa_money_world", "Money credited to households, world (A - C)", "A", "C", _m("money_world")),
        O("cw1_sa_wages", "Wages credited, world, all wage channels (A - C)", "A", "C", _m("wages_world")),
        O("cw1_sa_granary_wages", "Granary crew wages credited, world (A - C)", "A", "C", _m("granary_crew_wages")),
        O("cw1_sa_remittances", "Remittances credited, world (A - C)", "A", "C", _m("remittance_world")),
        O("cw1_sa_procurement", "Procurement credited, world (A - C)", "A", "C", _m("procurement_world")),
        O("cw1_sa_income_replaced", "Farm income replaced over S_A (A - C)", "A", "C", _m("income_replaced_set")),
        O("cw1_sa_priced_out", "Priced-out person-turns over S_A (A - C)", "A", "C", _m("priced_out_set")),
        O("cw1_sa_ration", "Mean ration per pilot person-turn over S_A (A - C)", "A", "C", _m("ration_mean_set")),
        # The wage at B's enrollment, and the interaction.
        O("cw1_sb_money", "Money credited to households over S_B (D - B: the wage at B's enrollment)", "D", "B",
          _m("money_set")),
        O("cw1_sb_priced_out", f"{rate} over S_B (D - B)", "D", "B", _m("priced_out_rate_set")),
        O("cw1_interaction_money", "Money credited over each schedule's set: (A - C) - (D - B)", "A", "C",
          _m("money_set"), minus=("D", "B")),
        O("cw1_interaction_priced_out", f"{rate} over each schedule's set: (A - C) - (D - B)", "A", "C",
          _m("priced_out_rate_set"), minus=("D", "B")),
        # The wage at the fixed cohorts.
        O("cw1_all_money", "Money credited to households, world (E - F: the wage at the all boundary)", "E", "F",
          _m("money_world")),
        O("cw1_all_priced_out", f"{rate}, each arm's own enrollment (E - F)", "E", "F", _m("priced_out_rate_set")),
        O("cw1_all_ration", "Mean ration per pilot person-turn (E - F)", "E", "F", _m("ration_mean_set")),
        O("cw1_mkt_money", "Money credited to households, world (G - H: the wage at the market boundary)", "G", "H",
          _m("money_world")),
        O("cw1_mkt_priced_out", f"{rate}, each arm's own enrollment (G - H)", "G", "H", _m("priced_out_rate_set")),
        # Totals and enrollment (descriptive: payment decides enrollment at paid_work).
        O("cw1_total_money", "Money credited to households, world (A - B: CP3's CH - CH_unpaid)", "A", "B",
          _m("money_world")),
        O("cw1_total_priced_out", f"{rate}, each arm's own enrollment (A - B)", "A", "B", _m("priced_out_rate_set")),
        O("cw1_coverage_enrollment", "Coverage: pilot region-turns per region-turn (C - B)", "C", "B",
          _m("coverage")),
        O("cw1_coverage_total", "Coverage: pilot region-turns per region-turn (A - B)", "A", "B", _m("coverage")),
        O("cw1_enrollment_priced_out", "Priced-out person-turns, world (C - B; only pilot regions price anyone out)", "C", "B", _m("priced_out_set")),
        O("cw1_enrollment_income_replaced", "Farm income replaced, world (C - B)", "C", "B",
          _m("income_replaced_world")),
    ]
    # RL5: priced-out rates of household groups (person-turns of the group with known persons).
    for contrast, (arm, control) in (("sa", ("A", "C")), ("sb", ("D", "B"))):
        for g, label in (("crew", "crew households (members and co-resident children)"),
                         ("nonfarm", "non-farm adults"), ("children_alone", "children without a co-resident adult")):
            out.append(O(f"cw1_rl5_{contrast}_{g}_rate", f"RL5 {label}: priced-out person-turns per person-turn "
                         f"({arm} - {control})", arm, control, _m(f"rl5_{g}_rate")))
    for g, label in (("crew", "crew households"), ("nonfarm", "non-farm adults"),
                     ("children_alone", "children without a co-resident adult")):
        out.append(O(f"cw1_rl5_sa_{g}_count", f"RL5 {label}: priced-out person-turns (A - C)", "A", "C",
                     _m(f"rl5_{g}_priced_out")))
    # RL6, the expedition-labour control: reported as CH_noTS - A (the negative of CH - CH_noTS).
    out += [
        O("cw1_nots_money", "Money credited to households, world (CH_noTS - A)", "CH_noTS", "A", _m("money_world")),
        O("cw1_nots_priced_out", f"{rate}, each arm's own enrollment (CH_noTS - A)", "CH_noTS", "A",
          _m("priced_out_rate_set")),
        O("cw1_nots_coverage", "Coverage (CH_noTS - A)", "CH_noTS", "A", _m("coverage")),
    ]
    return tuple(out)


SCREENS["CW1"] = SR.Screen(
    name="CW1", title="S1 accounting and wages (A1-A2): the wage and paid_work enrollment",
    preregistration=PROGRESS / "connected-world-screens-cw1.md",
    base=CW1_BASE,
    arms={"A": ((*_CW1_PW, *CW1_CHAIN), "C"),                     # CH@pw
          "B": ((*_CW1_PW, *CW1_UNPAID), None),                   # U@pw (root)
          "C": ((*_cw1_sched(_CW1_S_A), *CW1_UNPAID), "B"),       # U@S_A
          "D": ((*_cw1_sched(_CW1_S_B), *CW1_CHAIN), "B"),        # CH@S_B
          "E": ((CW1_BOUNDARY, "all", *CW1_CHAIN), "F"),          # CH@all
          "F": ((CW1_BOUNDARY, "all", *CW1_UNPAID), "B"),         # U@all
          "G": ((CW1_BOUNDARY, "market", *CW1_CHAIN), "H"),       # CH@mkt
          "H": ((CW1_BOUNDARY, "market", *CW1_UNPAID), "B"),      # U@mkt
          "CH_noTS": ((*_CW1_PW, *CW1_NO_TS), "A")},              # CHAIN without timber supply
    root="B", pilot=PILOT, held={"template": tuple(range(731, 737)), "procedural": tuple(range(831, 837))},
    packages=(
        SR.Package("--household-retail", ("livelihoods", "household_retail"), "chronicler.household_retail_state",
                   ("pilot_region_turns", "regions_opened", "regions_closed", "priced_out_persons", "paid_milli",
                    "credited_milli", "procurement_credited_milli", "income_replaced_rows"),
                   "--household-retail-mode", "retail"),
        SR.Package("--wealth-accounting", ("livelihoods", "wealth_accounting"), "chronicler.wealth_accounting_state",
                   ("turns_observed", "turns_unobserved", "continuity_broken", "typed_incomplete_turns",
                    "closures_failed")),
        SR.Package("--recovery-crews", ("livelihoods", "recovery_crews"), mode_flag="--recovery-crew-mode",
                   default_mode="paid"),
        SR.Package("--timber-supply", ("livelihoods", "timber_supply"), mode_flag="--timber-supply-mode",
                   default_mode="supply"),
        SR.Package("--remittances", ("livelihoods", "remittances"), mode_flag="--remittance-mode",
                   default_mode="send"),
    ),
    outcomes=_cw1_outcomes(),
    activation=cw1_activation, extract=cw1_extract, ready=True, module=MODULE,
    derived=(SR.Derived("S_A", "A", _CW1_S_A, cw1_schedule), SR.Derived("S_B", "B", _CW1_S_B, cw1_schedule)),
    control_activation=True, report=_cw1_report)


# --- DEV: the development smoke screen ---------------------------------------------

def _timber_activation(bundle: dict, flags) -> tuple[bool | None, str]:
    """The timber stock acted when any observed turn cut timber."""
    observed = [r for s in bundle.get("history") or []
                if isinstance(r := SR._get(s, ("livelihoods", "timber_stock")), dict) and r.get("observed")]
    if not observed:
        return None, "no observed timber account"
    cut = sum(SR._num((r.get("totals") or {}).get("extraction")) and r["totals"]["extraction"] > 0 for r in observed)
    return (cut > 0), f"{cut} of {len(observed)} observed turns cut timber"


SCREENS["DEV"] = SR.Screen(
    name="DEV", title="Development smoke screen (development worlds only; never evidence)",
    preregistration=None,
    base=("--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves", "--public-grain-shipments"),
    arms={"W": ((), None), "TS": (("--timber-stock",), "W")}, root="W", pilot={}, held={},
    packages=(SR.Package("--timber-stock", ("livelihoods", "timber_stock")),),
    outcomes=(
        SR.Outcome("dev_population", "Population at the end (TS - W)", "TS", "W",
                   lambda r: SR.harm_value(r, "population"), primary=True),
        SR.Outcome("dev_stand", "Timber stand share of capacity at the end (TS)", "TS", None,
                   lambda r: SR.harm_value(r, "forest_stand"), primary=True),
        SR.Outcome("dev_food", "Food shortfall after relief (TS - W)", "TS", "W",
                   lambda r: SR.harm_value(r, "food_shortfall")),
    ),
    activation=_timber_activation, ready=True, module=MODULE)


def main(argv=None) -> int:
    return SR.main(argv, SCREENS, prog="connected_world_screens.py")


if __name__ == "__main__":
    raise SystemExit(main())
