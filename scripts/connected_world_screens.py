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

CW1-CW3, CW5 and CW6 are **stubs**: only their cohorts are declared. Each slice
fills in its screen's base, arms, packages, outcomes (2-3 primary), activation
rule and extractor, writes its preregistration and sets ``ready=True``. Until
then every run of the screen is refused (``check`` reports it NOT READY, exit
code 2). CW4 (slice C1, quarantine rules) is declared below.

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
