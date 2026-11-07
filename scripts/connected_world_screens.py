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

CW2, CW5 and CW6 are **stubs**: only their cohorts are declared (CW5c, the care slice
of S4, is declared below on its own fresh cohort). Each slice
fills in its screen's base, arms, packages, outcomes (2-3 primary), activation
rule and extractor, writes its preregistration and sets ``ready=True``. Until
then every run of the screen is refused (``check`` reports it NOT READY, exit
code 2). CW4 (slice C1, quarantine rules), CW4b (slice C1b, the migration channel,
on its own reserved cohort) and CW1 (slice S1, the wage and ``paid_work``
enrollment; a two-phase screen) and CW3 (slice B2, the watershed in flow mode under
upstream forest protection; procedural stratum only) are declared below.

``DEV`` is a development-only smoke screen (no pilot or held cohort): it runs the
runner end to end on registered development worlds, e.g.

    python scripts/connected_world_screens.py run OUT --screen DEV --cohort dev --worlds t1 --turns 10 --jobs 1
"""
from __future__ import annotations

import hashlib
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


# --- CW4b: the migration channel of quarantine closure (slice C1b) ------------------
#
# Arms (one control chain QRM -> QR -> QC; root QC): QC the closure decisions and
# enforcement cost with nothing closed, QR the trade closure (C1, default channel), QRM
# the closure of trade and migration (``--quarantine-channels trade,migration``). Every
# arm: hybrid, epidemics and the contact ledger on (defaults). CW4's validated
# extractor (``cw4_extract``) supplies the epidemic, window, rules and merchant
# measures; ``cw4b_extract`` adds the channel check and the migration-closure totals.

CW4B_CHANNELS = "--quarantine-channels"
#: The migration-closure totals CW4b reads (last snapshot's rules totals, QRM only).
CW4B_MIGRATION = ("migrants_blocked", "migrants_blocked_flight", "migrants_blocked_hunger",
                  "migrants_refusal_spells")


def _cw4b_channels(flags) -> str:
    flags = list(flags)
    return flags[flags.index(CW4B_CHANNELS) + 1] if CW4B_CHANNELS in flags else "trade"


def _cw4b_expected_channels(flags) -> list[str]:
    if _cw4_mode(flags) != "closure":
        return []
    return ["trade", "migration"] if _cw4b_channels(flags) == "trade,migration" else ["trade"]


def cw4b_activation(bundle: dict, flags) -> tuple[bool | None, str]:
    """QR acts when a closure opened; QRM when a closure opened and a migrant was
    refused (both its channels acted). The root QC is not judged by the runner."""
    mode, channels = _cw4_mode(flags), _cw4b_channels(flags)
    rules = _cw4_rules(bundle)
    if not rules:
        return None, "no quarantine rules record"
    totals = rules[-1].get("totals") or {}
    opened = totals.get("closures_opened")
    if not SR._num(opened):
        return None, "quarantine rules totals carry no closures_opened"
    if channels != "trade,migration":
        return (opened > 0), f"{int(opened)} closures opened ({mode})"
    refused = totals.get("migrants_blocked")
    if not SR._num(refused):
        return None, "quarantine rules totals carry no migrants_blocked under trade,migration"
    return (opened > 0 and refused > 0), (f"{int(opened)} closures opened, {int(refused)} migrants refused "
                                          f"({mode}, trade,migration)")


def cw4b_extract(bundle: dict, flags) -> tuple[dict, list[str]]:
    """CW4's measures plus the channel check and, under trade,migration, the refusal
    totals (refusals as person-ticks, refusal spells, flight and hunger-driven shares),
    checked against the per-snapshot receipts. Outside that arm they are None (not
    recorded), never zero."""
    m, problems = cw4_extract(bundle, flags)
    want = _cw4b_expected_channels(flags)
    rules = _cw4_rules(bundle)
    if any(r.get("channels") != want for r in rules):
        problems.append(f"quarantine rules channels differ from {want}")
    migration = want == ["trade", "migration"]
    totals = (rules[-1].get("totals") or {}) if rules else {}
    if not migration:
        if any(key in totals for key in CW4B_MIGRATION):
            problems.append("migration-closure totals recorded without the migration channel")
        for key in CW4B_MIGRATION:
            m[key] = None
        return m, problems
    for key in CW4B_MIGRATION:
        if not SR._num(totals.get(key)):
            problems.append(f"quarantine rules totals lack {key} under trade,migration")
        m[key] = totals.get(key)
    receipts = [r.get("receipt") for r in rules]
    observed = [rc for rc in receipts if isinstance(rc, dict)]
    blocked = [rc.get("migrants_blocked") for rc in observed]
    if len(observed) != len(rules) or not all(SR._num(b) for b in blocked):
        problems.append("a migration receipt was not observed (null) in a snapshot under trade,migration")
    elif SR._num(m["migrants_blocked"]) and sum(blocked) != m["migrants_blocked"]:
        problems.append(f"per-snapshot refusals sum to {sum(blocked)}, totals.migrants_blocked is "
                        f"{m['migrants_blocked']}")
    for rc in observed:
        rows = rc.get("migration_refusals")
        if isinstance(rows, list) and SR._num(rc.get("migrants_blocked")) and \
                sum(r.get("persons") or 0 for r in rows if isinstance(r, dict)) != rc["migrants_blocked"]:
            problems.append(f"receipt {rc.get('turn')}: refusal rows differ from migrants_blocked")
            break
    m["turns_with_refusals"] = sum(1 for b in blocked if SR._num(b) and b > 0)
    return m, problems


SCREENS["CW4b"] = SR.Screen(
    name="CW4b", title="S3 quarantine closure of migration (C1b)",
    preregistration=PROGRESS / "connected-world-screens-cw4b.md",
    base=_CW4_BASE,
    arms={"QC": ((CW4_MODE, "cost_only"), None),
          "QR": ((CW4_MODE, "closure"), "QC"),
          "QRM": ((CW4_MODE, "closure", CW4B_CHANNELS, "trade,migration"), "QR")},
    root="QC", pilot=PILOT, held={"template": tuple(range(3101, 3107)), "procedural": tuple(range(3201, 3207))},
    outcomes=(
        # Primaries: QRM - QC, whole run, world level (unconditioned on any arm's own closures).
        SR.Outcome("cw4b_world_arrivals", "Cross-polity epidemic arrivals over the whole run, world (QRM - QC)",
                   "QRM", "QC", _m("arrivals_world"), primary=True),
        SR.Outcome("cw4b_world_death_rate", "World epidemic deaths (all) per 1,000 person-turns over the whole "
                   "run (QRM - QC)", "QRM", "QC", _m("world_deaths_per_1000_pt"), primary=True),
        # The migration channel's increment over the trade closure.
        SR.Outcome("cw4b_mig_world_arrivals", "Cross-polity arrivals, world (QRM - QR: the migration channel's "
                   "increment)", "QRM", "QR", _m("arrivals_world")),
        SR.Outcome("cw4b_mig_world_death_rate", "World epidemic deaths per 1,000 person-turns (QRM - QR: the "
                   "migration channel's increment)", "QRM", "QR", _m("world_deaths_per_1000_pt")),
        # The trade closure alone (CW4's comparison on these worlds).
        SR.Outcome("cw4b_trade_world_arrivals", "Cross-polity arrivals, world (QR - QC: trade closure alone)",
                   "QR", "QC", _m("arrivals_world")),
        SR.Outcome("cw4b_trade_world_death_rate", "World epidemic deaths per 1,000 person-turns (QR - QC: trade "
                   "closure alone)", "QR", "QC", _m("world_deaths_per_1000_pt")),
        SR.Outcome("cw4b_world_arrival_rate", "Cross-polity arrivals per 1,000 region-turns, world (QRM - QC)",
                   "QRM", "QC", _m("arrivals_world_per_1000_region_turns")),
        SR.Outcome("cw4b_world_deaths", "World epidemic deaths, count (QRM - QC)", "QRM", "QC",
                   _m("world_epidemic_deaths")),
        # Conditioned on each arm's own closures (selection): windows follow the arm's trajectory.
        SR.Outcome("cw4b_sel_arrivals", "Arrivals into closing civs' regions in their windows (QRM - QC; "
                   "conditioned on each arm's own closures: selection)", "QRM", "QC", _m("arrivals")),
        SR.Outcome("cw4b_sel_deaths", "Epidemic deaths (reported outbreaks) per 1,000 person-turns of closing "
                   "civs in their windows (QRM - QC; conditioned on each arm's own closures: selection)",
                   "QRM", "QC", _m("deaths_per_1000_pt_closing")),
        SR.Outcome("cw4b_sel_window", "Window civ-turns (QRM - QC; conditioned on each arm's own closures: "
                   "selection)", "QRM", "QC", _m("window_civ_turns")),
        # Migrants refused (QRM alone; structurally absent in QC and QR).
        SR.Outcome("cw4b_refusals", "Migrants refused, person-ticks (QRM alone)", "QRM", None,
                   _m("migrants_blocked")),
        SR.Outcome("cw4b_refusal_spells", "Refusal spells: consecutive refusals of one agent count once "
                   "(QRM alone)", "QRM", None, _m("migrants_refusal_spells")),
        SR.Outcome("cw4b_refused_flight", "Refusals of migrants fleeing war, famine or persecution, hunger-driven "
                   "moves excluded (QRM alone)", "QRM", None, _m("migrants_blocked_flight")),
        SR.Outcome("cw4b_refused_hunger", "Refusals of hunger-driven migrants: food opportunity, material need "
                   "(QRM alone)", "QRM", None, _m("migrants_blocked_hunger")),
        # Harms beside the primaries (the runner's panel shows QRM - QR and QR - QC).
        SR.Outcome("cw4b_h_food_shortfall", "Food shortfall after relief over the run (QRM - QC)", "QRM", "QC",
                   lambda r: SR.harm_value(r, "food_shortfall")),
        SR.Outcome("cw4b_h_out_migration", "Agents moving between regions over the run (QRM - QC)", "QRM", "QC",
                   lambda r: SR.harm_value(r, "out_migration")),
        SR.Outcome("cw4b_h_population", "Population at the end (QRM - QC)", "QRM", "QC",
                   lambda r: SR.harm_value(r, "population")),
        SR.Outcome("cw4b_h_treasury", "Treasury at the end (QRM - QC)", "QRM", "QC",
                   lambda r: SR.harm_value(r, "treasury")),
        SR.Outcome("cw4b_h_partner_population", "Partner civs' population at the end (QRM - QC)", "QRM", "QC",
                   _m("partner_population_end")),
        SR.Outcome("cw4b_h_partner_treasury", "Partner civs' treasury at the end (QRM - QC)", "QRM", "QC",
                   _m("partner_treasury_end")),
        SR.Outcome("cw4b_h_forgone", "Route income forgone, both sides (QRM alone; structurally 0 in QC)",
                   "QRM", None, _m("forgone_income")),
        SR.Outcome("cw4b_h_forgone_trade", "Route income forgone, both sides (QR alone)", "QR", None,
                   _m("forgone_income")),
        SR.Outcome("cw4b_h_unwinds", "Merchant unwinds, world (QRM - QC)", "QRM", "QC", _m("merchant_unwinds")),
        SR.Outcome("cw4b_h_leaked", "Deliveries still crossing a closed pair (QRM alone)", "QRM", None,
                   _m("leaked_deliveries")),
        SR.Outcome("cw4b_h_enforcement", "Enforcement paid (QRM - QC)", "QRM", "QC", _m("enforcement_paid")),
    ),
    activation=cw4b_activation, extract=cw4b_extract, ready=True, module=MODULE)


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
        # Each frame's and the world's income replaced are rounded to 1e-6 apiece.
        if SR._num(replaced) and abs(frame_income - replaced) > 1e-6 * (len(frames or ()) + 1):
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
    # P1 (Amendment 1): over the arm's region set, the wages and remittances the ledger
    # locates in the set less the set's replaced farm income. Procurement credits are left
    # out: the ledger does not locate them, and owners who moved away keep their claims,
    # so some credits reach households outside the set (procurement_world is a secondary).
    m["money_set"] = totals["located_set"] / _MILLI - income_set
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
        O("cw1_p1_wage_money", "Money credited to households over S_A, wealth units: wages + remittances "
          "- farm income replaced (A - C: the wage at A's enrollment)", "A", "C", _m("money_set"),
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


# --- CW3: the watershed in flow mode under upstream forest protection (slice B2) ----
#
# Question: does an upstream intervention (``--clearing-protection``, as configured by its
# switch) change downstream outcomes when the watershed account owns the water index
# (``--watershed-mode flow``), without creating resources? Arms (root R): R the account in
# record_only (the old water index), F flow, R_CP and F_CP the same with clearing
# protection, F_CPc flow with clearing protection in ``cost_only`` mode (the same adoption,
# planning and charges, nothing protected; Amendment 1). Every arm: hybrid, procedural
# 32x10 (the watershed refuses template worlds, so the template cohort 751-756 stays
# reserved and unused). The primaries' region sets are fixed before treatment by the
# static drainage graph, identical in every arm of a world: downstream regions receive
# inflow from at least one region (``graph.down``); upstream regions drain into a region.
# The protection arms also carry clearing protection's candidate set at enable time (turn
# 0: adopted or eligible but over the limit or unaffordable), the same in each of them; it
# defines the F_CP - F_CPc secondaries. Snapshot s records world turn s - 1.

CW3_WS = ("livelihoods", "watershed")
CW3_CP = ("livelihoods", "clearing_protection")
#: The native write-back's rounding of the index flow writes (4 decimals), with the
#: record's 6-decimal rounding.
CW3_INDEX_TOLERANCE = 5e-5 + 2e-6
#: Relative closure tolerance of the water account (the account's own CLOSURE_TOLERANCE,
#: against the opening storage plus cumulative precipitation; the record rounds nothing in
#: the cumulative residual).
CW3_CLOSURE_TOLERANCE = 1e-9


def _cw3_mode(flags) -> str:
    return _flag(flags, "--watershed-mode", "record_only")


def _cw3_cp(flags) -> bool:
    return "--clearing-protection" in list(flags)


def _cw3_cp_mode(flags) -> str:
    return _flag(flags, "--clearing-protection-mode", "enforced")


def _cw3_below(down: list[int], regions) -> set[int]:
    """Every region downstream of any of ``regions`` on the drainage graph."""
    n, below = len(down), set()
    for u in regions:
        node, hops = down[u] if 0 <= u < n else -1, 0
        while isinstance(node, int) and node >= 0 and hops <= n:
            below.add(node)
            node, hops = down[node], hops + 1
    return below


def _cw3_candidates(records: list[tuple[dict, dict]]) -> list[int] | None:
    """Clearing protection's candidate set at enable time: the regions adopted at turn 0
    and those eligible then but over the limit or unaffordable (its first planning; the
    state before it is the same in every protection arm). None without a turn-0 record."""
    first = next((r for _s, r in records if r.get("source_turn") == 0 and r.get("observed")), None)
    if first is None:
        return None
    adopted = {d.get("region_id") for d in first.get("decisions") or []
               if isinstance(d, dict) and d.get("turn") == 0 and d.get("kind") == "adopted"}
    eligible = {u.get("region_id") for u in first.get("unprotected") or []
                if isinstance(u, dict) and u.get("reason") in ("over_limit", "unaffordable")}
    return sorted(r for r in adopted | eligible if isinstance(r, int))


def _cw3_records(bundle: dict, path) -> list[tuple[dict, dict]]:
    return [(s, r) for s in bundle.get("history") or [] if isinstance(r := SR._get(s, path), dict)]


def _cw3_sets(ws: list[tuple[dict, dict]]) -> tuple[list[int], list[int], list[int]] | None:
    """(down, downstream regions, upstream regions) from the record's graph."""
    graph = next((r.get("graph") for _s, r in ws if isinstance(r.get("graph"), dict)), None)
    if not graph or not isinstance(graph.get("down"), list):
        return None
    down = graph["down"]
    n = len(down)
    downstream = sorted({d for d in down if isinstance(d, int) and 0 <= d < n})
    upstream = [r for r in range(n) if isinstance(down[r], int) and down[r] >= 0]
    return down, downstream, upstream


def _cw3_mean(values) -> float | None:
    values = [v for v in values if SR._num(v)]
    return sum(values) / len(values) if values else None


def _cw3_food(bundle: dict, regions: list[int]) -> tuple[float | None, float | None, int]:
    """Demand-weighted food shortfall share after relief (sum of demand x max(0, 1 -
    min(1, sufficiency after relief)) over sum of demand) and demand-weighted mean of
    min(1, sufficiency after relief), over the given regions and every snapshot with a
    food account; and the snapshots read. A region-turn without demand counts nothing."""
    unmet = demand = met = 0.0
    turns = 0
    wanted = set(regions)
    for s in bundle.get("history") or []:
        fa = s.get("food_accounting")
        if not isinstance(fa, dict) or not isinstance(fa.get("regions"), list):
            continue
        turns += 1
        for row in fa["regions"]:
            if not isinstance(row, dict) or row.get("region_id") not in wanted:
                continue
            d = (row.get("native") or {}).get("demand")
            suff = row.get("sufficiency_after_relief")
            if not (SR._num(d) and d > 0 and SR._num(suff)):
                continue
            demand += d
            unmet += d * max(0.0, 1.0 - min(1.0, suff))
            met += d * min(1.0, suff)
    if demand <= 0:
        return None, None, turns
    return unmet / demand, met / demand, turns


def cw3_activation(bundle: dict, flags) -> tuple[bool | None, str]:
    """F: the account owns the index (flow records settled, index used = derived, or the
    derived index capped at a recorded cap change). R_CP: clearing protection kept cover
    (cover not cleared > 0). F_CP: both. F_CPc (cost_only): flow, and protections were paid
    for clearing they would have stopped (cover it would have kept > 0) while keeping none.
    The root R is not judged."""
    mode, cp = _cw3_mode(flags), _cw3_cp(flags)
    ws = _cw3_records(bundle, CW3_WS)
    if not ws:
        return None, "no watershed record"
    texts, acted = [], True
    if mode == "flow":
        observed = [r for _s, r in ws if r.get("observed") and r.get("mode") == "flow"]
        if not observed:
            return None, "no settled flow record"
        gap = _cw3_flow_gap(observed)
        if gap is None:
            return None, "flow records without the index columns"
        acted = acted and gap <= CW3_INDEX_TOLERANCE
        texts.append(f"{len(observed)} settled flow turns, index used - derived (capped) at most {gap:.2e}")
    if cp:
        records = _cw3_records(bundle, CW3_CP)
        if not records:
            return None, "no clearing protection record"
        counters = records[-1][1].get("counters") or {}
        kept, prt = counters.get("cover_not_cleared"), counters.get("protected_region_turns")
        would = counters.get("cover_would_keep")
        if not (SR._num(kept) and SR._num(prt) and SR._num(would)):
            return None, "clearing protection counters lack cover_not_cleared, cover_would_keep or protected_region_turns"
        if _cw3_cp_mode(flags) == "cost_only":
            acted = acted and would > 0 and kept == 0
            texts.append(f"{int(prt)} protected region-turns paid for, would have kept {would:.3f} cover, kept "
                         f"{kept:.3f} (cost_only)")
        else:
            acted = acted and kept > 0
            texts.append(f"{int(prt)} protected region-turns kept {kept:.3f} cover")
    if not texts:
        return None, "the root arm is not judged"
    return acted, "; ".join(texts)


def _cw3_flow_gap(observed: list[dict]) -> float | None:
    worst = 0.0
    for r in observed:
        cols = r.get("regions") or {}
        used, derived = cols.get("index_observed"), cols.get("index_derived")
        if not (isinstance(used, list) and isinstance(derived, list) and len(used) == len(derived)):
            return None
        capped = {c.get("region"): c.get("cap_after") for c in r.get("cap_changes") or [] if isinstance(c, dict)}
        for i, (o, d) in enumerate(zip(used, derived)):
            expected = min(d, capped[i]) if i in capped and SR._num(capped[i]) else d
            worst = max(worst, abs(o - expected))
    return worst


def cw3_extract(bundle: dict, flags) -> tuple[dict, list[str]]:
    """Downstream and upstream food and water, floods and droughts by cause, the forest,
    clearing protection's cost and cover kept, and the water account's closure (the
    validity check: no water is created; a failure is a problem, never a value)."""
    problems: list[str] = []
    m: dict = {}
    mode, cp = _cw3_mode(flags), _cw3_cp(flags)
    ws = _cw3_records(bundle, CW3_WS)
    if not ws:
        return m, ["no watershed record"]
    if any(r.get("mode") != mode for _s, r in ws):
        problems.append(f"a watershed record is not in mode {mode}")
    for s, r in ws:
        if r.get("source_turn") != s.get("turn", 0) - 1:
            problems.append(f"watershed record of snapshot {s.get('turn')} misdated")
            break
    sets = _cw3_sets(ws)
    if sets is None:
        return m, problems + ["watershed records carry no drainage graph"]
    down, downstream, upstream = sets
    n = len(down)
    names = [r.get("name") for r in (bundle.get("world_state") or {}).get("regions") or []]
    if len(names) != n:
        problems.append(f"{len(names)} regions in the world state, {n} in the drainage graph")
    m["regions"], m["downstream_regions"], m["upstream_regions"] = n, len(downstream), len(upstream)
    observed = [r for _s, r in ws if r.get("observed")]
    m["settled_turns"] = len(observed)
    # Water index the simulation used (the record's index_observed), means over settled turns.
    def index_mean(regions):
        return _cw3_mean(v for r in observed for i, v in enumerate((r.get("regions") or {}).get("index_observed") or [])
                         if i in set(regions))
    m["water_downstream"] = index_mean(downstream)
    m["water_upstream"] = index_mean(upstream)
    m["water_all"] = index_mean(range(n))
    # Food (demand-weighted shortfall share after relief, and mean min(1, sufficiency)).
    for label, regions in (("downstream", downstream), ("upstream", upstream), ("all", list(range(n)))):
        share, met, turns = _cw3_food(bundle, regions)
        m[f"food_shortfall_{label}"], m[f"food_met_{label}"] = share, met
    m["food_turns"] = turns
    # Forest cover (the stand proxy: mean cover; timber stock is off), at the end.
    last_eco = (bundle.get("history") or [{}])[-1].get("ecology") or {}
    covers = {i: (last_eco.get(name) or {}).get("forest_cover") for i, name in enumerate(names)}
    m["cover_upstream_end"] = _cw3_mean(covers.get(i) for i in upstream)
    m["cover_all_end"] = _cw3_mean(covers.values())
    # Floods and droughts. Account flood events: onsets, what acted, withheld (flow).
    last = ws[-1][1]
    counters = last.get("counters") or {}
    for key in ("floods_started", "flood_region_turns", "droughts_declared", "drought_region_turns",
                "terrain_cap_changes"):
        if not SR._num(counters.get(key)):
            problems.append(f"watershed counters lack {key}")
        m[key] = counters.get(key)
    if mode == "flow":
        for key in ("flood_consequences", "flood_consequences_withheld", "superseded_river_floods"):
            if not SR._num(counters.get(key)):
                problems.append(f"flow counters lack {key}")
            m[key] = counters.get(key)
    else:
        for key in ("flood_consequences", "flood_consequences_withheld", "superseded_river_floods"):
            m[key] = None
    events = bundle.get("events_timeline") or []
    m["coastal_floods"] = sum(1 for e in events if e.get("event_type") == "flood"
                              and "Flooding devastates" in (e.get("description") or ""))
    m["river_floods_old"] = sum(1 for e in events if e.get("event_type") == "flood"
                                and "river floods" in (e.get("description") or ""))
    downs = set(downstream)
    onsets = [f for r in observed for f in r.get("floods") or [] if isinstance(f, dict)]
    m["flood_onsets_downstream"] = sum(1 for f in onsets if f.get("region") in downs)
    m["droughts_downstream"] = sum(1 for r in observed for d in (r.get("droughts") or {}).get("declared") or []
                                   if isinstance(d, dict) and d.get("region") in downs)
    # Validity: the water account closes (cumulative, every snapshot) and, in flow, the index
    # used is the derived one (capped at recorded cap changes).
    worst = 0.0
    for _s, r in ws:
        cum = r.get("cumulative") or {}
        res, scale = cum.get("closure_residual"), (cum.get("opening_storage") or 0) + (cum.get("precipitation") or 0)
        if not SR._num(res):
            problems.append("a watershed record lacks its cumulative closure residual")
            break
        worst = max(worst, abs(res) / max(scale, 1.0))
    m["closure_worst_relative"] = worst
    if worst > CW3_CLOSURE_TOLERANCE:
        problems.append(f"the water account does not close (worst relative residual {worst:.2e})")
    if mode == "flow":
        gap = _cw3_flow_gap(observed)
        m["index_gap_worst"] = gap
        if gap is None or gap > CW3_INDEX_TOLERANCE:
            problems.append(f"flow: the index used is not the derived index (worst gap {gap})")
    else:
        m["index_gap_worst"] = None
    # Clearing protection: cost and cover kept; the protected regions and their downstream.
    if cp:
        records = _cw3_records(bundle, CW3_CP)
        if not records:
            problems.append("no clearing protection record")
        else:
            c = records[-1][1].get("counters") or {}
            for key in ("adopted", "protected_region_turns", "cover_not_cleared", "cover_would_keep", "charged"):
                if not SR._num(c.get(key)):
                    problems.append(f"clearing protection counters lack {key}")
                m[f"cp_{key}"] = c.get(key)
            cp_mode = _cw3_cp_mode(flags)
            if any(r.get("mode") != cp_mode for _s, r in records):
                problems.append(f"a clearing protection record is not in mode {cp_mode}")
            if cp_mode == "cost_only" and SR._num(c.get("cover_not_cleared")) and c["cover_not_cleared"] != 0:
                problems.append("cost_only clearing protection kept cover (it must keep none)")
            protected = sorted({rc.get("region_id") for _s, r in records for rc in r.get("receipts") or []
                                if isinstance(rc, dict) and isinstance(rc.get("region_id"), int)})
            below = _cw3_below(down, protected)
            # The candidate set at enable time (pre-treatment, the same in every protection arm).
            candidates = _cw3_candidates(records)
            if candidates is None:
                problems.append("no observed clearing protection record of turn 0 (the candidate set)")
                m["cand_regions"] = m["cand_below"] = None
                m["cand_food_shortfall_below"] = m["cand_water_below"] = None
            else:
                cand_below = sorted(_cw3_below(down, candidates))
                m["cand_regions"], m["cand_below"] = len(candidates), len(cand_below)
                m["cand_digest"] = ",".join(map(str, candidates))
                m["cand_food_shortfall_below"] = _cw3_food(bundle, cand_below)[0] if cand_below else None
                m["cand_water_below"] = index_mean(cand_below) if cand_below else None
            m["cp_protected_regions"] = len(protected)
            m["cp_protected_with_downstream"] = sum(1 for u in protected if 0 <= u < n and down[u] >= 0)
            m["cp_downstream_of_protected"] = len(below)
            # Selection (this arm's own protections): food and water below its protected regions.
            share, _met, _t = _cw3_food(bundle, sorted(below)) if below else (None, None, 0)
            m["sel_food_shortfall_below_protected"] = share
            m["sel_water_below_protected"] = index_mean(sorted(below)) if below else None
    else:
        for key in ("cp_adopted", "cp_protected_region_turns", "cp_cover_not_cleared", "cp_cover_would_keep",
                    "cp_charged", "cp_protected_regions", "cp_protected_with_downstream", "cp_downstream_of_protected",
                    "sel_food_shortfall_below_protected", "sel_water_below_protected", "cand_regions", "cand_below",
                    "cand_food_shortfall_below", "cand_water_below"):
            m[key] = None
        if _cw3_records(bundle, CW3_CP):
            problems.append("a clearing protection record without the switch")
    for key in ("water_downstream", "water_upstream", "food_shortfall_downstream", "food_shortfall_upstream"):
        if m.get(key) is None:
            problems.append(f"{key} could not be measured")
    return m, problems


_CW3_BASE = ("--turns", "200", "--agents", "hybrid", "--simulate-only")
_CW3_R = ("--watershed", "--watershed-mode", "record_only")
_CW3_F = ("--watershed", "--watershed-mode", "flow")
_CW3_CP = ("--clearing-protection",)
_CW3_CPC = ("--clearing-protection", "--clearing-protection-mode", "cost_only")


def _cw3_outcomes() -> tuple[SR.Outcome, ...]:
    ds_short, ds_water = _m("food_shortfall_downstream"), _m("water_downstream")
    return (
        # Primaries (chosen on the development worlds, see the preregistration): the downstream water
        # protection leaves under flow (the channel; the most consistent development signal), the
        # downstream food it buys or costs (the welfare question), and whether the water effect
        # exists only with flow (the interaction with the same contrast under the old index).
        SR.Outcome("cw3_ds_water_flow", "Downstream regions' water index used, mean over settled turns (F_CP - F: "
                   "protection's downstream effect under flow)", "F_CP", "F", ds_water, primary=True),
        SR.Outcome("cw3_ds_food_flow", "Downstream regions' food shortfall share after relief over the run "
                   "(F_CP - F)", "F_CP", "F", ds_short, primary=True),
        SR.Outcome("cw3_ds_water_interaction", "Downstream water index used: (F_CP - F) - (R_CP - R), the part of "
                   "protection's downstream water effect that exists only with flow", "F_CP", "F", ds_water,
                   primary=True, minus=("R_CP", "R")),
        # The same contrasts under the old index, the food interaction, and the flow effect itself.
        SR.Outcome("cw3_ds_water_old", "Downstream water index used (R_CP - R: under the old index)", "R_CP", "R",
                   ds_water),
        SR.Outcome("cw3_ds_food_old", "Downstream food shortfall share (R_CP - R: under the old index)", "R_CP", "R",
                   ds_short),
        SR.Outcome("cw3_ds_food_interaction", "Downstream food shortfall share: (F_CP - F) - (R_CP - R)", "F_CP", "F",
                   ds_short, minus=("R_CP", "R")),
        SR.Outcome("cw3_ds_water_mode", "Downstream water index used (F - R: flow itself)", "F", "R", ds_water),
        SR.Outcome("cw3_ds_food_mode", "Downstream food shortfall share (F - R: flow itself)", "F", "R", ds_short),
        SR.Outcome("cw3_ds_food_met_flow", "Downstream demand-weighted mean of min(1, sufficiency) (F_CP - F)",
                   "F_CP", "F", _m("food_met_downstream")),
        # Upstream versus downstream trade-off.
        SR.Outcome("cw3_up_food_flow", "Upstream regions' food shortfall share (F_CP - F)", "F_CP", "F",
                   _m("food_shortfall_upstream")),
        SR.Outcome("cw3_up_water_flow", "Upstream water index used (F_CP - F)", "F_CP", "F", _m("water_upstream")),
        SR.Outcome("cw3_all_food_flow", "All regions' food shortfall share (F_CP - F)", "F_CP", "F",
                   _m("food_shortfall_all")),
        # Floods and droughts by cause (account flood events follow forest loss; coastal floods are a
        # separate authority; droughts through the account).
        SR.Outcome("cw3_floods_flow", "Account flood events (onsets) (F_CP - F)", "F_CP", "F", _m("floods_started")),
        SR.Outcome("cw3_floods_acted", "Account flood events that acted (F_CP - F)", "F_CP", "F",
                   _m("flood_consequences")),
        SR.Outcome("cw3_ds_floods_flow", "Account flood onsets in downstream regions (F_CP - F)", "F_CP", "F",
                   _m("flood_onsets_downstream")),
        SR.Outcome("cw3_droughts_flow", "Droughts declared (F_CP - F)", "F_CP", "F", _m("droughts_declared")),
        SR.Outcome("cw3_ds_droughts_flow", "Droughts declared in downstream regions (F_CP - F)", "F_CP", "F",
                   _m("droughts_downstream")),
        SR.Outcome("cw3_coastal_floods", "Coastal floods (F_CP - F; a separate authority)", "F_CP", "F",
                   _m("coastal_floods")),
        SR.Outcome("cw3_superseded", "River floods superseded (F_CP alone)", "F_CP", None, _m("superseded_river_floods")),
        # The forest and protection's cost.
        SR.Outcome("cw3_cover_up_flow", "Upstream mean forest cover at the end (F_CP - F)", "F_CP", "F",
                   _m("cover_upstream_end")),
        SR.Outcome("cw3_cover_kept", "Cover protection kept, total (F_CP alone)", "F_CP", None,
                   _m("cp_cover_not_cleared")),
        SR.Outcome("cw3_cp_charged", "Warden pay charged, total (F_CP alone)", "F_CP", None, _m("cp_charged")),
        SR.Outcome("cw3_cp_downstream", "Regions downstream of a region F_CP protected (F_CP alone)", "F_CP", None,
                   _m("cp_downstream_of_protected")),
        # Selection: below this arm's own protected regions (no counterpart in an arm without protection).
        SR.Outcome("cw3_sel_food_below", "Food shortfall share below F_CP's own protected regions (F_CP alone; "
                   "selection)", "F_CP", None, _m("sel_food_shortfall_below_protected")),
        SR.Outcome("cw3_sel_water_below", "Water index below F_CP's own protected regions (F_CP alone; selection)",
                   "F_CP", None, _m("sel_water_below_protected")),
        # Validity (structurally ~0; a breach fails the run): no water created.
        SR.Outcome("cw3_closure", "Water account worst relative closure residual (F_CP alone; validity)", "F_CP",
                   None, _m("closure_worst_relative")),
        SR.Outcome("cw3_index_gap", "Worst |index used - derived (capped)| (F_CP alone; validity)", "F_CP", None,
                   _m("index_gap_worst")),
        # Amendment 1: protection's effect apart from its treasury cost (F_CP - F_CPc: the same
        # adoption, planning and charges, only the cover kept differs), on the graph's sets and
        # below the candidate set at enable time (pre-treatment, the same in both arms); and the
        # cost itself (F_CPc - F).
        SR.Outcome("cw3_cpc_ds_water", "Downstream water index used (F_CP - F_CPc: the cover kept, cost held "
                   "equal)", "F_CP", "F_CPc", ds_water),
        SR.Outcome("cw3_cpc_ds_food", "Downstream food shortfall share (F_CP - F_CPc)", "F_CP", "F_CPc", ds_short),
        SR.Outcome("cw3_cpc_cand_water", "Water index below the turn-0 candidate set (F_CP - F_CPc)", "F_CP",
                   "F_CPc", _m("cand_water_below")),
        SR.Outcome("cw3_cpc_cand_food", "Food shortfall share below the turn-0 candidate set (F_CP - F_CPc)",
                   "F_CP", "F_CPc", _m("cand_food_shortfall_below")),
        SR.Outcome("cw3_cpc_up_water", "Upstream water index used (F_CP - F_CPc)", "F_CP", "F_CPc",
                   _m("water_upstream")),
        SR.Outcome("cw3_cpc_cover", "Upstream mean forest cover at the end (F_CP - F_CPc)", "F_CP", "F_CPc",
                   _m("cover_upstream_end")),
        SR.Outcome("cw3_cpc_droughts", "Droughts declared (F_CP - F_CPc)", "F_CP", "F_CPc", _m("droughts_declared")),
        SR.Outcome("cw3_cost_ds_food", "Downstream food shortfall share (F_CPc - F: protection's cost alone)",
                   "F_CPc", "F", ds_short),
        SR.Outcome("cw3_cost_ds_water", "Downstream water index used (F_CPc - F: the cost alone)", "F_CPc", "F",
                   ds_water),
        SR.Outcome("cw3_cost_treasury", "Treasury at the end (F_CPc - F: the cost alone)", "F_CPc", "F",
                   lambda r: SR.harm_value(r, "treasury")),
        SR.Outcome("cw3_cpc_would_keep", "Cover protection would have kept (F_CPc alone; it keeps none)", "F_CPc",
                   None, _m("cp_cover_would_keep")),
        # Harms beside the primaries (the runner's panel shows each arm against its control).
        SR.Outcome("cw3_h_food_shortfall", "Food shortfall after relief over the run, world (F_CP - F)", "F_CP", "F",
                   lambda r: SR.harm_value(r, "food_shortfall")),
        SR.Outcome("cw3_h_population", "Population at the end (F_CP - F)", "F_CP", "F",
                   lambda r: SR.harm_value(r, "population")),
        SR.Outcome("cw3_h_treasury", "Treasury at the end (F_CP - F)", "F_CP", "F",
                   lambda r: SR.harm_value(r, "treasury")),
        SR.Outcome("cw3_h_out_migration", "Agents moving between regions over the run (F_CP - F)", "F_CP", "F",
                   lambda r: SR.harm_value(r, "out_migration")),
    )


SCREENS["CW3"] = SR.Screen(
    name="CW3", title="S3 watershed flow and upstream forest protection (B2)",
    preregistration=PROGRESS / "connected-world-screens-cw3.md",
    base=_CW3_BASE,
    arms={"R": (_CW3_R, None),
          "F": (_CW3_F, "R"),
          "R_CP": (_CW3_R + _CW3_CP, "R"),
          "F_CPc": (_CW3_F + _CW3_CPC, "F"),
          "F_CP": (_CW3_F + _CW3_CP, "F_CPc")},
    root="R", pilot={"procedural": (19,)}, held={"procedural": tuple(range(851, 857))},
    outcomes=_cw3_outcomes(),
    activation=cw3_activation, extract=cw3_extract, ready=True, module=MODULE)


# --- CW5c: bounded epidemic care capacity (slice C2) -------------------------------
#
# Arms (one control chain EF -> EC -> E0; root E0): E0 epidemics on with L9 local budgets
# and no care (the control), EC the cost control (the same carers, farm time, withheld
# income and wages, no effect on case fatality), EF care. Every arm: hybrid, epidemics and
# the contact ledger on (defaults), --grain-reserves --local-budgets. World turn w is
# recorded by the snapshot labelled w + 1 (``source_turn`` w; its ``tick`` is the epidemic
# tick of w, which applied the capacity of the carers named in w - 1). A cell is a
# region-turn (w, j); its infectious person-turns are the tick's mean infectious people
# (``tick.regions[*].infectious_pt``: sum over pathogens of burden x n after the tick).
# Fatality per infectious person-turn is a pooled ratio: sum of deaths over sum of
# infectious person-turns (about SUBSTEPS x recovery x case fatality; less phase-dependent
# than deaths per new infection, though not phase-free: deaths come from each season's
# starting infectious share, ``burden`` is the mean after each season). Cells are also kept
# per pathogen, so the mechanism check can be read within pathogen.

CW5C_CARE = "--epidemic-care"
CW5C_MODE = "--epidemic-care-mode"
_CW5C_BASE = ("--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves", "--local-budgets")
#: Region-turns where food sufficiency after relief is below this are famine region-turns
#: (``ecology.FAMINE_SEVERE_SUFFICIENCY``, the severity line of the famine component).
CW5C_FAMINE = 0.6
#: Lifetime counters the extractor checks its frame sums against (last snapshot), and the
#: capacity refusals that must stay zero in a natural run.
CW5C_COUNTERS = ("covered_region_turns", "carer_turns", "farm_time_removed", "wages_paid_milli", "unpaid_bills",
                 "envelope_coins", "capacity_stale", "capacity_future", "capacity_out_of_range",
                 "capacity_unconsumed")
#: The care factor at full coverage (``epidemic_care.CARE_CFR_REDUCTION``), for the reports.
CW5C_REDUCTION = 0.3
#: ``epidemiology.PATHOGENS`` names by index (append only; a test checks the order).
CW5C_PATHOGENS = ("plague", "pox", "fever", "flux", "pestilence")
#: Per-cell fields kept only in the full metrics (outside the repository); the committed
#: compact metrics keep each world's paired values instead (``cw5c_compact``).
CW5C_CELL_KEYS = ("cells", "cells_by_pathogen", "covered_cells")


def _cw5c_mode(flags) -> str | None:
    flags = list(flags)
    if CW5C_CARE not in flags:
        return None
    return flags[flags.index(CW5C_MODE) + 1] if CW5C_MODE in flags else "care"


def _cw5c_care(snapshots: dict[int, dict]) -> dict[int, dict]:
    """World turn w -> the care record of its snapshot (only where recorded)."""
    return {w: r for w, s in snapshots.items() if isinstance(r := SR._get(s, ("livelihoods", "epidemic_care")), dict)}


def cw5c_activation(bundle: dict, flags) -> tuple[bool | None, str]:
    """EC and EF act when care capacity reached an epidemic tick with infectious people
    (coverage > 0); E0 acts when an outbreak was reported (it has no care by rule)."""
    mode = _cw5c_mode(flags)
    snaps = _cw4_snapshots(bundle)
    reported = sum(1 for s in snaps.values() if isinstance(SR._get(s, ("epidemics", "active")), list)
                   and s["epidemics"]["active"])
    if mode is None:
        return (reported > 0), f"{reported} snapshots with a reported outbreak; no care by rule"
    care = _cw5c_care(snaps)
    if not care:
        return None, "no epidemic care record"
    covered = sum(1 for r in care.values() for a in ((r.get("tick") or {}).get("applied") or [])
                  if isinstance(a, dict) and SR._num(a.get("coverage")) and a["coverage"] > 0)
    staffed = sum(1 for r in care.values() for row in (r.get("frame") or [])
                  if isinstance(row, dict) and row.get("carers"))
    return (covered > 0), f"{covered} covered region-turns, {staffed} staffed region envelopes ({mode})"


def _cw5c_rate(num: float, den: float, per: float = 1.0) -> float | None:
    return per * num / den if den > 0 else None


def _cw5c_at(row: dict, cells, pathogen: int | None = None) -> float | None:
    """Fatality per infectious person-turn of one run at the given cells (``[w, j]``):
    sum of its deaths over sum of its infectious person-turns there (a cell where the run
    had no infection counts zero of both); of one pathogen when ``pathogen`` is given."""
    m = row.get("m") or {}
    table = m.get("cells") if pathogen is None else m.get("cells_by_pathogen")
    if not isinstance(table, list) or cells is None:
        return None
    if pathogen is None:
        index = {(w, j): (d, i) for w, j, d, i in table}
    else:
        index = {(w, j): (d, i) for w, j, k, d, i in table if k == pathogen}
    deaths = infectious = 0.0
    for w, j in cells:
        d, i = index.get((w, j), (0, 0.0))
        deaths += d
        infectious += i
    return _cw5c_rate(deaths, infectious)


def _cw5c_pair(key: str, pathogen: int | None = None):
    """A paired reading at the control's (EC's) covered cells. A compact row (committed
    metrics without cells, ``cw5c_compact``) carries the two values in ``m.pairs[key]``."""
    def pair(arm_row: dict, control_row: dict) -> tuple[float | None, float | None]:
        stored = (arm_row.get("m") or {}).get("pairs")
        if "cells" not in (arm_row.get("m") or {}) and isinstance(stored, dict):
            got = stored.get(key)
            return (got[0], got[1]) if isinstance(got, list) and len(got) == 2 else (None, None)
        cells = (control_row.get("m") or {}).get("covered_cells")
        return _cw5c_at(arm_row, cells, pathogen), _cw5c_at(control_row, cells, pathogen)
    pair.__name__ = f"cw5c_pair_{key}"
    return pair


#: Primary 2: both arms read at the cells the control (EC) covered.
cw5c_itt_pair = _cw5c_pair("cw5c_itt_cfr")
#: The mechanism check within pathogen, at EC's covered cells (both arms).
CW5C_PATHOGEN_PAIRS = {name: _cw5c_pair(f"cw5c_mech_{name}", k) for k, name in enumerate(CW5C_PATHOGENS)}


def cw5c_extract(bundle: dict, flags) -> tuple[dict, list[str]]:
    """The CW5c measures of one run (see the preregistration for every definition)."""
    mode = _cw5c_mode(flags)
    snaps = _cw4_snapshots(bundle)
    regions = (bundle.get("world_state") or {}).get("regions") or []
    names = [r.get("name") for r in regions]
    index = {n: i for i, n in enumerate(names)}
    m: dict = {}
    problems: list[str] = []
    # --- epidemic measures defined in every arm (as CW4) ------------------------------
    world_deaths = world_pt = 0.0
    deaths_at: dict[int, float] = {}
    reported_rt = cont_rt = 0
    cont_deaths = cont_cases = 0.0
    previous: set[int] = set()
    for w, snap in sorted(snaps.items()):
        epi = snap.get("epidemics")
        if not isinstance(epi, dict) or not isinstance(epi.get("active"), list):
            problems.append(f"no epidemics record at snapshot {w + 1}")
            previous = set()
            continue
        if SR._num(epi.get("deaths")):
            world_deaths += epi["deaths"]
            deaths_at[w] = epi["deaths"]
        else:
            problems.append(f"epidemics.deaths missing at snapshot {w + 1}")
        regional = snap.get("regional_population")
        counts = regional.get("counts") if isinstance(regional, dict) else None
        if not isinstance(counts, list) or len(counts) != len(names) or not all(SR._num(c) for c in counts) \
                or regional.get("source_turn") != w:
            problems.append(f"regional_population counts missing or misdated at snapshot {w + 1}")
        else:
            world_pt += sum(counts)
        by_region: dict[int, list[float]] = {}
        for row in epi["active"]:
            j = index.get(row.get("region"))
            if j is None or not SR._num(row.get("deaths")) or not SR._num(row.get("cases")):
                problems.append(f"malformed active outbreak row at snapshot {w + 1}")
                continue
            cell = by_region.setdefault(j, [0.0, 0.0])
            cell[0] += row["deaths"]
            cell[1] += row["cases"]
        reported_rt += len(by_region)
        for j, (d, c) in by_region.items():
            if j in previous:
                cont_rt += 1
                cont_deaths += d
                cont_cases += c
        previous = set(by_region)
    m["world_epidemic_deaths"] = SR.harm_value({"harm": {"d": SR.harm_epidemic_deaths(bundle)}}, "d")
    if m["world_epidemic_deaths"] is not None and world_deaths != m["world_epidemic_deaths"]:
        problems.append(f"per-turn epidemic deaths sum to {world_deaths}, deaths_total is "
                        f"{m['world_epidemic_deaths']}")
    m["world_person_turns"] = world_pt
    m["world_deaths_per_1000_pt"] = _cw5c_rate(world_deaths, world_pt, 1000.0)
    m["reported_region_turns"] = reported_rt
    # Continuing-outbreak region-turns (reported at this tick and the one before), every arm.
    m["continuing_region_turns"] = cont_rt
    m["continuing_deaths_per_case"] = _cw5c_rate(cont_deaths, cont_cases)
    # --- hunger, stability and unrest (every arm) --------------------------------------
    dearth = famine = 0
    stab, stab_n = 0.0, 0
    unrest, unrest_n = 0.0, 0
    for w, snap in sorted(snaps.items()):
        for city in (SR._get(snap, ("cities", "cities")) or []):
            if isinstance(city, dict) and SR._num(city.get("unrest")):
                unrest += city["unrest"]
                unrest_n += 1
        fa = snap.get("food_accounting")
        if isinstance(fa, dict) and fa.get("source_turn") == w and isinstance(fa.get("regions"), list):
            for row in fa["regions"]:
                s = row.get("sufficiency_after_relief") if isinstance(row, dict) else None
                if SR._num(s):
                    dearth += s < 1.0
                    famine += s < CW5C_FAMINE
        for civ in (snap.get("civ_stats") or {}).values():
            if isinstance(civ, dict) and SR._num(civ.get("stability")) and (civ.get("population") or 0) > 0:
                stab += civ["stability"]
                stab_n += 1
    m["dearth_region_turns"] = dearth
    m["famine_region_turns"] = famine
    m["stability_mean"] = stab / stab_n if stab_n else None
    m["city_unrest_mean"] = unrest / unrest_n if unrest_n else None
    # --- L9 envelopes by service (every arm: displacement within the one budget) -------
    care_coins = other_coins = 0
    awarded: dict[str, int] = {}
    for w, snap in sorted(snaps.items()):
        budget = SR._get(snap, ("livelihoods", "local_budgets"))
        if not isinstance(budget, dict):
            problems.append(f"no local budgets record at snapshot {w + 1}")
            continue
        for d in budget.get("decisions") or []:
            services = {p.get("pid"): p.get("service") for p in d.get("proposals") or [] if isinstance(p, dict)}
            for a in d.get("awards") or []:
                service = services.get(a.get("pid"))
                amount = a.get("amount") if SR._num(a.get("amount")) else 0
                awarded[service] = awarded.get(service, 0) + amount
                if service == "epidemic_care":
                    care_coins += amount
                else:
                    other_coins += amount
    m["l9_care_coins"] = care_coins
    m["l9_other_coins"] = other_coins
    m["l9_relief_coins"] = awarded.get("relief", 0)
    # --- the care records (EC, EF) ------------------------------------------------------
    care = _cw5c_care(snaps)
    keys = ("world_infectious_pt", "world_deaths_per_ipt", "cells", "cells_by_pathogen", "covered_cells",
            "covered_region_turns",
            "covered_deaths", "covered_infectious_pt", "covered_dpi", "covered_death_share", "mean_relative_factor",
            "floored_region_turns", "applied_region_turns", "mean_coverage", "staffed_envelopes", "envelopes",
            "carers_named", "care_time", "farm_time_removed", "farm_time_unpaid", "wages_paid", "wages_due",
            "unpaid_bills", "income_withheld", "envelope_coins_executed", "care_coins_unspent", "refused_capacity")
    if mode is None:
        if care:
            problems.append("an epidemic care record in an arm without care")
        for key in keys:
            m[key] = None          # not recorded: no care in this arm - never zero
        return m, problems
    if len(care) != len(snaps):
        problems.append(f"epidemic care recorded in {len(care)} of {len(snaps)} snapshots under {mode}")
    cells: list[list] = []
    cells_by_pathogen: list[list] = []
    covered_cells: list[list[int]] = []
    world_ipt = 0.0
    covered = applied = staffed = envelopes = carers = unpaid = refused = floored = 0
    c_deaths = c_ipt = care_time = farm = paid = due = withheld = coverage_sum = relative_sum = unpaid_farm = 0.0
    paid_milli = executed = 0
    for w, r in sorted(care.items()):
        if r.get("mode") != mode or r.get("source_turn") != w:
            problems.append(f"care record at snapshot {w + 1}: mode {r.get('mode')!r} or source turn "
                            f"{r.get('source_turn')!r} differs")
            continue
        tick, frame = r.get("tick"), r.get("frame")
        if not isinstance(tick, dict) or not isinstance(frame, list) or not isinstance(tick.get("regions"), list):
            problems.append(f"care record at snapshot {w + 1} not observed (tick, its regions or frame null)")
            continue
        refused += len(tick.get("refused") or [])
        tick_deaths = 0
        for row in tick["regions"]:
            j, d, i = row.get("region"), row.get("deaths"), row.get("infectious_pt")
            if not isinstance(j, int) or not 0 <= j < len(names) or not SR._num(d) or not SR._num(i):
                problems.append(f"malformed care tick region at snapshot {w + 1}")
                continue
            tick_deaths += d
            world_ipt += i
            if d or i:
                cells.append([w, j, int(d), round(float(i), 6)])
            split = row.get("pathogens")
            if not isinstance(split, list) or sum(x[1] for x in split) != d \
                    or abs(sum(x[2] for x in split) - i) > 1e-6 * max(1.0, i):
                problems.append(f"care tick region {j} at snapshot {w + 1}: the pathogen split does not sum to it")
                continue
            for k, dk, ik in split:
                if dk or ik:
                    cells_by_pathogen.append([w, j, int(k), int(dk), round(float(ik), 6)])
        if w in deaths_at and tick_deaths != deaths_at[w]:
            problems.append(f"care tick regions' deaths {tick_deaths} differ from epidemics.deaths {deaths_at[w]} "
                            f"at snapshot {w + 1}")
        for a in tick.get("applied") or []:
            applied += 1
            j = a.get("region")
            if not SR._num(a.get("coverage")) or not isinstance(j, int) or not 0 <= j < len(names):
                problems.append(f"malformed care tick row at snapshot {w + 1}")
                continue
            coverage_sum += a["coverage"]
            if a["coverage"] <= 0:
                continue
            if not SR._num(a.get("deaths")) or not SR._num(a.get("infectious_after")) \
                    or not SR._num(a.get("combined_factor")):
                problems.append(f"covered region {j} at snapshot {w + 1}: deaths or infectious not observed")
                continue
            covered += 1
            covered_cells.append([w, j])
            c_deaths += a["deaths"]
            c_ipt += a["infectious_after"]
            tech = a.get("techniques_factor") if SR._num(a.get("techniques_factor")) else 1.0
            # The care part of the factor applied (cost_only: 1), after the one floor.
            relative_sum += a["combined_factor"] / tech
            floored += bool(a.get("floored"))
        for row in frame:
            envelopes += 1
            if row.get("carers"):
                staffed += 1
            carers += len(row.get("carers") or [])
            care_time += row.get("care_time") or 0.0
            farm += row.get("farm_time_removed") or 0.0
            paid_milli += row.get("wages_paid_milli") or 0
            due += (row.get("wages_due_milli") or 0) / _MILLI
            withheld += sum(c.get("income_withheld") or 0.0 for c in row.get("carers") or [])
            if row.get("unpaid_reason"):
                unpaid_farm += row.get("care_time") or 0.0
        for row in r.get("ledger") or []:
            unpaid += str(row.get("status", "")).startswith("refused")
            executed += row.get("envelope_coins") or 0
    paid = paid_milli / _MILLI
    m.update(world_infectious_pt=world_ipt, world_deaths_per_ipt=_cw5c_rate(world_deaths, world_ipt),
             cells=cells, cells_by_pathogen=cells_by_pathogen, covered_cells=covered_cells,
             covered_region_turns=covered, covered_deaths=c_deaths,
             covered_infectious_pt=c_ipt, covered_dpi=_cw5c_rate(c_deaths, c_ipt),
             covered_death_share=_cw5c_rate(c_deaths, world_deaths),
             mean_relative_factor=relative_sum / covered if covered else None, floored_region_turns=floored,
             applied_region_turns=applied, mean_coverage=coverage_sum / applied if applied else None,
             staffed_envelopes=staffed, envelopes=envelopes, carers_named=carers, care_time=care_time,
             farm_time_removed=farm, farm_time_unpaid=unpaid_farm, wages_paid=paid, wages_due=due,
             unpaid_bills=unpaid, income_withheld=withheld, envelope_coins_executed=executed,
             care_coins_unspent=executed - paid, refused_capacity=refused)
    # The frames are summed per snapshot; the lifetime counters must agree (no frame lost).
    last = care.get(max(care)) if care else None
    counters = (last or {}).get("counters") or {}
    checks = {"covered_region_turns": covered, "carer_turns": carers, "farm_time_removed": farm,
              "wages_paid_milli": paid_milli, "unpaid_bills": unpaid, "envelope_coins": executed,
              "farm_time_unpaid": unpaid_farm}
    for key, value in checks.items():
        got = counters.get(key, 0)
        if not SR._num(got) or abs(got - value) > 1e-4 * max(1.0, abs(value)):
            problems.append(f"care counter {key} is {got}, the frames sum to {value}")
    for key in ("capacity_stale", "capacity_future", "capacity_out_of_range", "capacity_unconsumed"):
        if counters.get(key, 0):
            problems.append(f"care counters record {counters[key]} {key} capacity rows (never expected)")
    if refused:
        problems.append(f"{refused} capacity rows refused at a tick in a natural run")
    return m, problems


def _cw5c_report(rows, strata) -> list[str]:
    """The mechanism check and the reach and attenuation of care, per world (EC, EF)."""
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}

    def fmt(v, spec=".4g"):
        return "n/a" if v is None else format(v, spec)

    out = ["\n## CW5c mechanism check (not evidence that care works: coverage is about 1 by construction)\n",
           "Fatality per infectious person-turn in each arm's own covered region-turns, the EF/EC ratio, and the "
           "mean care factor EF applied there (combined / techniques: 1 - 0.3 x coverage under the floor) with its "
           "floored count. Within a pathogen the ratio should sit near the factor; pooled over pathogens it also "
           "carries the arms' different pathogen mix after they diverge (see the table by pathogen below).\n",
           "| World | EC own covered | EF own covered | EF / EC | EF mean applied factor | EF floored | EF mean coverage |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    reach = ["\n## CW5c reach and attenuation\n",
             "Reach: the share of EC's epidemic deaths in EC's covered region-turns. Implied maximum: reach x (1 - "
             "EF's mean applied factor), the fall in world deaths if care cut every covered death by that factor and "
             "nothing else changed. Realized: the EF - EC change of the world epidemic death rate, relative to EC.\n",
             "| World | EC reach | EF mean applied factor | Implied maximum fall | Realized change |",
             "| --- | --- | --- | --- | --- |"]
    for tag, seeds in strata.items():
        for seed in seeds:
            ec, ef = by.get(("EC", tag, seed)), by.get(("EF", tag, seed))
            if ec is None or ef is None or ec["rc"] != 0 or ef["rc"] != 0:
                out.append(f"| {tag}{seed} | not run or failed | | | | | |")
                reach.append(f"| {tag}{seed} | not run or failed | | | |")
                continue
            a, b = ec.get("m") or {}, ef.get("m") or {}
            ratio = (b["covered_dpi"] / a["covered_dpi"]) if a.get("covered_dpi") and b.get("covered_dpi") is not None \
                else None
            factor = b.get("mean_relative_factor")
            out.append(f"| {tag}{seed} | {fmt(a.get('covered_dpi'))} | {fmt(b.get('covered_dpi'))} | {fmt(ratio)} | "
                       f"{fmt(factor)} | {b.get('floored_region_turns')} | {fmt(b.get('mean_coverage'))} |")
            share = a.get("covered_death_share")
            implied = share * (1 - factor) if share is not None and factor is not None else None
            r0, r1 = a.get("world_deaths_per_1000_pt"), b.get("world_deaths_per_1000_pt")
            realized = (r1 - r0) / r0 if r0 and r1 is not None else None
            reach.append(f"| {tag}{seed} | {fmt(share)} | {fmt(factor)} | "
                         f"{fmt(-implied if implied is not None else None, '+.3f')} | {fmt(realized, '+.3f')} |")
    pathogens = ["\n## CW5c mechanism check by pathogen (EC's covered cells, both arms)\n",
                 "Deaths per infectious person-turn of each pathogen at the cells EC covered, in EC and in EF, and "
                 "the EF/EC ratio (n/a: no infectious person-turn of that pathogen there in an arm).\n",
                 "| World | Pathogen | EC | EF | EF / EC |", "| --- | --- | --- | --- | --- |"]
    for tag, seeds in strata.items():
        for seed in seeds:
            ec, ef = by.get(("EC", tag, seed)), by.get(("EF", tag, seed))
            if ec is None or ef is None or ec["rc"] != 0 or ef["rc"] != 0:
                continue
            for name, pair in CW5C_PATHOGEN_PAIRS.items():
                a_val, c_val = pair(ef, ec)
                if a_val is None and c_val is None:
                    continue
                ratio = a_val / c_val if a_val is not None and c_val else None
                pathogens.append(f"| {tag}{seed} | {name} | {fmt(c_val)} | {fmt(a_val)} | {fmt(ratio)} |")
    return out + pathogens + reach


def cw5c_compact(full: Path, out: Path) -> dict:
    """The committed metrics of a CW5c run: every row without its per-cell fields, each
    care row with the paired values of its world's paired outcomes (EF rows: EF and EC at
    EC's covered cells), so every outcome and the report reproduce from the compact file.
    Returns {"rows", "sha256_full"}; the full file stays outside the repository."""
    import hashlib
    import json
    rows = [json.loads(line) for line in Path(full).read_text(encoding="utf-8").splitlines() if line.strip()]
    by = {(r.get("arm"), r.get("stratum"), r.get("seed")): r for r in rows}
    paired = [o for o in SCREENS["CW5c"].outcomes if o.pair is not None]
    lines = []
    for r in rows:
        m = dict(r.get("m") or {})
        if r.get("arm") == "EF" and r.get("rc") == 0:
            control = by.get(("EC", r.get("stratum"), r.get("seed")))
            if control is not None and control.get("rc") == 0:
                m["pairs"] = {o.id: list(o.pair(r, control)) for o in paired}
        for key in CW5C_CELL_KEYS:
            m.pop(key, None)
        lines.append(json.dumps({**r, "m": m}, sort_keys=False))
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    digest = hashlib.sha256(Path(full).read_bytes()).hexdigest()
    return {"rows": len(rows), "sha256_full": digest}


def _cw5c_outcomes() -> tuple[SR.Outcome, ...]:
    h = lambda key: (lambda r: SR.harm_value(r, key))  # noqa: E731
    unused = lambda r: None  # noqa: E731  (a paired outcome reads both rows)
    return (
        # Primaries: EF - EC (care against its cost control), unconditioned or on EC's cells.
        SR.Outcome("cw5c_world_death_rate", "World epidemic deaths per 1,000 person-turns over the whole run (EF - EC)",
                   "EF", "EC", _m("world_deaths_per_1000_pt"), primary=True),
        SR.Outcome("cw5c_itt_cfr", "Epidemic deaths per infectious person-turn in the region-turns EC covered, "
                   "read at the same cells in both arms (EF - EC; intention to treat)", "EF", "EC", unused,
                   primary=True, pair=cw5c_itt_pair),
        SR.Outcome("cw5c_world_dpi", "World epidemic deaths per infectious person-turn over the whole run (EF - EC)",
                   "EF", "EC", _m("world_deaths_per_ipt"), primary=True),
        # Secondaries.
        SR.Outcome("cw5c_world_deaths", "World epidemic deaths, count (EF - EC)", "EF", "EC", _m("world_epidemic_deaths")),
        SR.Outcome("cw5c_world_death_rate_vs_none", "World epidemic deaths per 1,000 person-turns (EF - E0)",
                   "EF", "E0", _m("world_deaths_per_1000_pt")),
        SR.Outcome("cw5c_cost_world_death_rate", "World epidemic deaths per 1,000 person-turns (EC - E0: the cost's "
                   "effect)", "EC", "E0", _m("world_deaths_per_1000_pt")),
        SR.Outcome("cw5c_continuing_deaths_per_case", "Deaths per new infection in continuing-outbreak region-turns "
                   "(EF - EC)", "EF", "EC", _m("continuing_deaths_per_case")),
        SR.Outcome("cw5c_continuing_deaths_per_case_vs_none", "Deaths per new infection in continuing-outbreak "
                   "region-turns (EF - E0)", "EF", "E0", _m("continuing_deaths_per_case")),
        SR.Outcome("cw5c_covered_region_turns", "Covered region-turns (EF - EC; selection)", "EF", "EC",
                   _m("covered_region_turns")),
        # Mechanism check (each arm's own covered cells; reported, not evidence).
        SR.Outcome("cw5c_mech_covered_dpi", "Mechanism check: deaths per infectious person-turn in each arm's own "
                   "covered region-turns (EF - EC; selection; see the ratio table)", "EF", "EC", _m("covered_dpi")),
        SR.Outcome("cw5c_mech_factor", "Mechanism check: mean care factor applied in covered region-turns (EF)", "EF",
                   None, _m("mean_relative_factor")),
        *(SR.Outcome(f"cw5c_mech_{name}", f"Mechanism check by pathogen: {name} deaths per infectious person-turn "
                     "at EC's covered cells (EF - EC)", "EF", "EC", lambda r: None, pair=pair)
          for name, pair in CW5C_PATHOGEN_PAIRS.items()),
        SR.Outcome("cw5c_mean_coverage", "Mean coverage over region-turns with capacity (EF)", "EF", None,
                   _m("mean_coverage")),
        SR.Outcome("cw5c_reach", "Reach: share of EC's epidemic deaths in its covered region-turns (EC)", "EC", None,
                   _m("covered_death_share")),
        # Fixed harm panel beside the primaries.
        SR.Outcome("cw5c_h_farm_time", "Carer farm time removed, worker-turns (EF)", "EF", None, _m("farm_time_removed")),
        SR.Outcome("cw5c_h_farm_time_cost", "Carer farm time removed, worker-turns (EC)", "EC", None,
                   _m("farm_time_removed")),
        SR.Outcome("cw5c_h_carers_held", "Carer-turns held from drafting and academy teaching (EF)", "EF", None,
                   _m("carers_named")),
        SR.Outcome("cw5c_h_carers_held_cost", "Carer-turns held from drafting and academy teaching (EC)", "EC", None,
                   _m("carers_named")),
        SR.Outcome("cw5c_h_wages", "Care wages paid, treasury units (EF)", "EF", None, _m("wages_paid")),
        SR.Outcome("cw5c_h_wages_cost", "Care wages paid, treasury units (EC)", "EC", None, _m("wages_paid")),
        SR.Outcome("cw5c_h_income_withheld", "Carers' ordinary income withheld, wealth units (EF)", "EF", None,
                   _m("income_withheld")),
        SR.Outcome("cw5c_h_income_withheld_cost", "Carers' ordinary income withheld, wealth units (EC)", "EC", None,
                   _m("income_withheld")),
        SR.Outcome("cw5c_h_unpaid_bills", "Care wage bills refused at payment (EF)", "EF", None, _m("unpaid_bills")),
        SR.Outcome("cw5c_h_unpaid_bills_cost", "Care wage bills refused at payment (EC)", "EC", None,
                   _m("unpaid_bills")),
        SR.Outcome("cw5c_h_food_shortfall", "Food shortfall after relief over the run (EF - EC)", "EF", "EC",
                   h("food_shortfall")),
        SR.Outcome("cw5c_h_food_shortfall_cost", "Food shortfall after relief over the run (EC - E0: the cost)",
                   "EC", "E0", h("food_shortfall")),
        SR.Outcome("cw5c_h_dearth", "Dearth region-turns, sufficiency after relief below 1 (EC - E0)", "EC", "E0",
                   _m("dearth_region_turns")),
        SR.Outcome("cw5c_h_famine", "Famine region-turns, sufficiency after relief below 0.6 (EC - E0)", "EC", "E0",
                   _m("famine_region_turns")),
        SR.Outcome("cw5c_h_dearth_care", "Dearth region-turns (EF - EC)", "EF", "EC", _m("dearth_region_turns")),
        SR.Outcome("cw5c_h_famine_care", "Famine region-turns (EF - EC: more survivors to feed)", "EF", "EC",
                   _m("famine_region_turns")),
        SR.Outcome("cw5c_h_care_coins", "L9 coins awarded to care envelopes (EF)", "EF", None, _m("l9_care_coins")),
        SR.Outcome("cw5c_h_care_coins_cost", "L9 coins awarded to care envelopes (EC)", "EC", None, _m("l9_care_coins")),
        SR.Outcome("cw5c_h_care_coins_unspent", "Care envelope coins executed but not paid out as wages (EC)", "EC",
                   None, _m("care_coins_unspent")),
        SR.Outcome("cw5c_h_other_coins", "L9 coins awarded to every other service (EC - E0: displacement within L9)",
                   "EC", "E0", _m("l9_other_coins")),
        SR.Outcome("cw5c_h_other_coins_care", "L9 coins awarded to every other service (EF - EC)", "EF", "EC",
                   _m("l9_other_coins")),
        SR.Outcome("cw5c_h_relief_coins", "L9 coins awarded to granary relief (EC - E0)", "EC", "E0",
                   _m("l9_relief_coins")),
        SR.Outcome("cw5c_h_treasury", "Treasury at the end (EC - E0)", "EC", "E0", h("treasury")),
        SR.Outcome("cw5c_h_treasury_care", "Treasury at the end (EF - EC)", "EF", "EC", h("treasury")),
        SR.Outcome("cw5c_h_stability", "Mean civ stability over civ-turns (EC - E0)", "EC", "E0", _m("stability_mean")),
        SR.Outcome("cw5c_h_stability_care", "Mean civ stability over civ-turns (EF - EC)", "EF", "EC",
                   _m("stability_mean")),
        SR.Outcome("cw5c_h_unrest", "Mean city unrest over city-turns (EC - E0)", "EC", "E0", _m("city_unrest_mean")),
        SR.Outcome("cw5c_h_unrest_care", "Mean city unrest over city-turns (EF - EC)", "EF", "EC",
                   _m("city_unrest_mean")),
        SR.Outcome("cw5c_h_population", "Population at the end (EF - EC)", "EF", "EC", h("population")),
        SR.Outcome("cw5c_h_population_cost", "Population at the end (EC - E0)", "EC", "E0", h("population")),
        SR.Outcome("cw5c_h_migration", "Agents moving between regions over the run (EF - EC)", "EF", "EC",
                   h("out_migration")),
        SR.Outcome("cw5c_h_migration_cost", "Agents moving between regions over the run (EC - E0)", "EC", "E0",
                   h("out_migration")),
    )


SCREENS["CW5c"] = SR.Screen(
    name="CW5c", title="S4 bounded epidemic care capacity (C2)",
    preregistration=PROGRESS / "connected-world-screens-cw5c.md",
    base=_CW5C_BASE,
    arms={"E0": ((), None),
          "EC": ((CW5C_CARE, CW5C_MODE, "cost_only"), "E0"),
          "EF": ((CW5C_CARE,), "EC")},
    root="E0", pilot=PILOT, held={"template": tuple(range(3301, 3307)), "procedural": tuple(range(3401, 3407))},
    packages=(
        SR.Package("--local-budgets", ("livelihoods", "local_budgets"), mode_flag="--local-budget-mode",
                   default_mode="bargained"),
        SR.Package(CW5C_CARE, ("livelihoods", "epidemic_care"), "chronicler.epidemic_care_state", CW5C_COUNTERS,
                   CW5C_MODE, "care"),
    ),
    outcomes=_cw5c_outcomes(),
    activation=cw5c_activation, extract=cw5c_extract, control_activation=True, report=_cw5c_report, ready=True,
    module=MODULE)


# --- CW3b: infrastructure condition and repair (slice B3) --------------------------
#
# Does funded repair keep irrigation serving, and does that keep food in irrigated
# regions, against the same wear with nothing repaired? And what do the works cost the
# repairs budget RS2 also draws on? Arms (root B): B the L9 + RS2 baseline without the
# condition switch; R the condition switch in record_only (measures condition, changes
# nothing: the measurement control, B's twin except its record); W wear_only (condition
# and service act, nothing repairs: the underfunded public works counterfactual, every
# work refused); C repair (works funded through their own L9 proposal); W_T and C_T the
# same pair without L9 and the maintenance obligation (works funded from the treasury
# alone: does repair keep service when it is paid for?). Every arm: hybrid, grain
# reserves, grain storage and RS2 repair projects. Snapshot s records world turn s - 1.
# The irrigated-region set is fixed at snapshot CW3B_FIXED, the last pre-treatment
# snapshot: an asset completes at the earliest in turn 2 (BUILD takes two turns), wears
# 0.01 a turn from its first Phase 10, so its first wear work opens in Phase 10 of turn
# 27 and spends from turn 28, and no service is lost before condition falls below 0.5,
# 50 turns after; snapshot 28 records world turn 27. A war-damage work opened before it
# is counted in ``early_war_works``. Arm B carries no record: its set is not recorded.

CW3B_IC = ("livelihoods", "infrastructure_condition")
CW3B_RS2 = ("livelihoods", "repair_projects")
CW3B_LB = ("livelihoods", "local_budgets")
#: Service at or above which an irrigation work serves (B3's gate).
CW3B_GATE = 0.5
#: The snapshot that fixes the irrigated-region set (the last pre-treatment snapshot).
CW3B_FIXED = 28
#: A stalled work counts in the underfunded-works story after this many stall turns.
CW3B_STORY_STALLS = 20


def _cw3b_mode(flags) -> str | None:
    flags = list(flags)
    if "--infrastructure-condition" not in flags:
        return None
    return _flag(flags, "--infrastructure-condition-mode", "repair")


def cw3b_activation(bundle: dict, flags) -> tuple[bool | None, str]:
    """R: assets registered. W, W_T: an irrigation asset-turn below full service. C, C_T: a
    work opened on an irrigation asset (exposure to repair; whether it was funded and
    delivered is a secondary). A world without an irrigation asset is not activated for
    W, W_T, C and C_T. The root B is not judged."""
    mode = _cw3b_mode(flags)
    if mode is None:
        return None, "the root arm is not judged"
    records = _cw3_records(bundle, CW3B_IC)
    if not records:
        return None, "no infrastructure condition record"
    counters = records[-1][1].get("counters") or {}
    opened = counters.get("assets_opened")
    if not SR._num(opened):
        return None, "counters lack assets_opened"
    if mode == "record_only":
        return opened > 0, f"{int(opened)} assets registered (record only)"
    irrigation = {a["aid"] for _s, r in records for a in (r.get("assets") or []) + (r.get("terminal") or [])
                  if a.get("kind") == "irrigation"}
    if not irrigation:
        return False, "no irrigation asset in the run"
    lost = sum(1 for _s, r in records for a in r.get("assets") or []
               if a.get("kind") == "irrigation" and SR._num(a.get("service")) and a["service"] < 1.0)
    if mode == "wear_only":
        return lost > 0, f"{lost} irrigation asset-turns below full service"
    works = {w["wid"] for _s, r in records for w in (r.get("works") or []) + (r.get("closed") or [])
             if w.get("kind") == "irrigation"}
    return len(works) > 0, (f"{len(works)} works opened on irrigation assets; {lost} irrigation asset-turns below "
                            "full service")


def _cw3b_after(bundle: dict, regions: list[int], after: int):
    """``_cw3_food`` over the snapshots after ``after`` only."""
    trimmed = {**bundle, "history": [s for s in bundle.get("history") or [] if s.get("turn", 0) > after]}
    return _cw3_food(trimmed, regions)


def _cw3b_pretreatment(records: list[tuple[dict, dict]]) -> tuple[bool, list[str]]:
    """The snapshot-CW3B_FIXED pre-treatment check, from every record up to it: no work
    delivered, no work opened by world turn CW3B_FIXED - 1 (every record's open and closed
    works, so a work closed early is seen), and every irrigation asset at full service."""
    reasons = []
    upto = [(s, r) for s, r in records if s.get("turn", 0) <= CW3B_FIXED]
    fixed = next((r for s, r in upto if s.get("turn") == CW3B_FIXED), None)
    if fixed is None:
        return False, [f"no record at snapshot {CW3B_FIXED}"]
    delivered = (fixed.get("counters") or {}).get("work_delivered", 0)
    if not SR._num(delivered) or delivered > 0:
        reasons.append(f"work delivered by snapshot {CW3B_FIXED}: {delivered}")
    early = sorted({w["wid"] for _s, r in upto for w in (r.get("works") or []) + (r.get("closed") or [])
                    if w.get("opened_turn", CW3B_FIXED) <= CW3B_FIXED - 1})
    if early:
        reasons.append(f"works opened by turn {CW3B_FIXED - 1}: {early}")
    below = [a["aid"] for a in fixed.get("assets") or []
             if a.get("kind") == "irrigation" and a.get("condition_service") != 1.0]
    if below:
        reasons.append(f"irrigation assets below full service at snapshot {CW3B_FIXED}: {below}")
    return not reasons, reasons


def cw3b_extract(bundle: dict, flags) -> tuple[dict, list[str]]:
    """Irrigation service, food in the fixed irrigated regions (after the pre-treatment
    snapshots, and over the whole run), the pre-treatment check and the region set's
    identity, the works and their funding, RS2's delivery (the budget displaced), coins
    destroyed and the underfunded-works story. Arm B carries no record: its condition
    measures are None (not recorded), never zero. A world without irrigation reads None
    for the irrigation measures (its activation says so), not a problem."""
    problems: list[str] = []
    m: dict = {}
    mode = _cw3b_mode(flags)
    history = bundle.get("history") or []
    records = _cw3_records(bundle, CW3B_IC)
    if mode is None:
        if records:
            problems.append("an infrastructure condition record without the switch")
    elif not records:
        return m, ["no infrastructure condition record"]
    for s, r in records:
        if r.get("source_turn") != s.get("turn", 0) - 1 or r.get("mode") != mode:
            problems.append(f"infrastructure record of snapshot {s.get('turn')} misdated or not in mode {mode}")
            break
    names = [r.get("name") for r in (bundle.get("world_state") or {}).get("regions") or []]
    irrigated: list[int] = []
    if mode is not None:
        fixed = next((r for s, r in records if s.get("turn") == CW3B_FIXED), None)
        if fixed is None:
            problems.append(f"no infrastructure record at snapshot {CW3B_FIXED}")
        else:
            irrigated = sorted({a["region"] for a in fixed.get("assets") or [] if a.get("kind") == "irrigation"})
        ok, reasons = _cw3b_pretreatment(records)
        m["pre_ok"], m["pre_reasons"] = ok, "; ".join(reasons)
        text = ",".join(map(str, irrigated))
        m["irrigated_set"] = text
        m["irrigated_set_sha"] = hashlib.sha256(text.encode()).hexdigest()[:16]
    else:
        m["pre_ok"] = m["pre_reasons"] = m["irrigated_set"] = m["irrigated_set_sha"] = None
    m["irrigated_regions"] = len(irrigated) if mode is not None else None
    if irrigated:
        m["food_shortfall_irrigated_after"], m["food_met_irrigated_after"], _t = _cw3b_after(bundle, irrigated,
                                                                                               CW3B_FIXED)
        m["food_shortfall_irrigated"], m["food_met_irrigated"], _t = _cw3_food(bundle, irrigated)
    else:
        for key in ("food_shortfall_irrigated_after", "food_met_irrigated_after", "food_shortfall_irrigated",
                    "food_met_irrigated"):
            m[key] = None
    m["food_shortfall_all"] = _cw3_food(bundle, list(range(len(names))))[0] if names else None
    # Irrigation service (condition_service, the same in every mode: R records what W would read),
    # after the pre-treatment snapshots and over the whole run.
    for label, after in (("_after", CW3B_FIXED), ("", -1)):
        serving = total = 0
        for s, r in records:
            if s.get("turn", 0) <= after:
                continue
            for a in r.get("assets") or []:
                if a.get("kind") != "irrigation" or not SR._num(a.get("condition_service")):
                    continue
                total += 1
                serving += a["condition_service"] >= CW3B_GATE
        m[f"irrigation_asset_turns{label}"] = total if mode is not None else None
        m[f"irrigation_serving_share{label}"] = (serving / total if total else None) if mode is not None else None
    last = records[-1][1] if records else {}
    c = last.get("counters") or {}
    for key in ("assets_opened", "assets_failed", "assets_restored", "wear", "damage", "work_delivered",
                "work_credited", "charged", "progress_turns", "stalled_turns", "completed", "damages_flood",
                "damages_conquest", "damages_sack", "damages_skipped_same_turn"):
        m[f"ic_{key}"] = c.get(key, 0) if mode is not None else None
    for reason in ("no_timber", "no_coins", "no_labor", "no_envelope", "granary_first"):
        m[f"ic_stalled_{reason}"] = c.get(f"stalled_{reason}", 0) if mode is not None else None
    m["coins_destroyed"] = (last.get("sink_milli", 0) / 1000.0) if mode is not None else None
    # Every record's works (closed keeps only the last 16), not the last record's.
    works = {w["wid"]: w for _s, r in records for w in (r.get("works") or []) + (r.get("closed") or [])}
    m["works_opened"] = len(works) if mode is not None else None
    m["works_opened_irrigation"] = (sum(1 for w in works.values() if w.get("kind") == "irrigation")
                                    if mode is not None else None)
    m["early_war_works"] = (sum(1 for w in works.values() if w.get("cause") == "war"
                                and w.get("opened_turn", CW3B_FIXED) < CW3B_FIXED) if mode is not None else None)
    # The underfunded public works story: a work stalled at least CW3B_STORY_STALLS turns on
    # an asset that failed (directly recorded; the viewer's story).
    failed = {a["aid"] for _s, r in records for a in (r.get("assets") or []) + (r.get("terminal") or [])
              if a.get("failed_turn") is not None}
    m["story_works"] = (sum(1 for w in works.values() if w.get("stalled_turns", 0) >= CW3B_STORY_STALLS
                            and w.get("aid") in failed) if mode in ("repair", "cost_only") else None)
    # RS2's delivery (the repairs budget the works may displace) and L9's awards.
    rs2 = _cw3_records(bundle, CW3B_RS2)
    rc = rs2[-1][1].get("counters") or {} if rs2 else {}
    m["rs2_work_delivered"] = rc.get("work_delivered") if rs2 else None
    m["rs2_charged"] = rc.get("charged") if rs2 else None
    m["rs2_stalled_no_timber"] = rc.get("stalled_no_timber", 0) if rs2 else None
    awards = {"repairs": 0, "infrastructure_works": 0}
    awarded_coins = {"repairs": 0, "infrastructure_works": 0}
    for _s, r in _cw3_records(bundle, CW3B_LB):
        for d in r.get("decisions") or []:
            amounts = {a.get("pid"): a.get("amount", 0) for a in d.get("awards") or []}
            for p in d.get("proposals") or []:
                if p.get("service") in awards and p.get("pid") in amounts:
                    awards[p["service"]] += 1
                    awarded_coins[p["service"]] += amounts[p["pid"]]
    l9 = "--local-budgets" in list(flags)
    for svc in awards:
        m[f"l9_awards_{svc}"] = awards[svc] if l9 else None
        m[f"l9_award_coins_{svc}"] = awarded_coins[svc] if l9 else None
    # The timber supply (PL1): expeditions dispatched and timber delivered to the store.
    ts = _cw3_records(bundle, ("livelihoods", "timber_supply"))
    tc = ts[-1][1].get("counters") or {} if ts else {}
    m["pl1_launched"] = tc.get("launched", 0) if ts else None
    m["pl1_delivered"] = tc.get("delivered", 0) if ts else None
    m["pl1_person_turns"] = tc.get("person_turns", 0) if ts else None
    # The works' timber need, served after RS2's (B3's rows): expeditions launched for the works
    # and their woodcutter person-turns (each expedition's largest count seen in any record).
    works_mode = mode in ("repair", "cost_only") and bool(ts)
    eids = {row.get("eid") for _s, r in records for row in r.get("timber_needs") or []
            if row.get("status") == "launched"}
    person: dict = {}
    for _s, r in ts:
        for e in (r.get("expeditions") or []) + (r.get("closed") or []):
            person[e.get("eid")] = max(person.get(e.get("eid"), 0), e.get("person_turns") or 0)
    m["pl1_works_launched"] = len(eids) if works_mode else None
    m["pl1_works_person_turns"] = sum(person.get(e, 0) for e in eids) if works_mode else None
    m["ic_timber_refused"] = (sum(v for k, v in c.items() if k.startswith("timber_refused_"))
                              if works_mode else None)
    # Stability (mean over living civs at the end), beside the harm panel's treasury.
    stats = (history[-1].get("civ_stats") if history else None) or {}
    vals = [v.get("stability") for v in (stats.values() if isinstance(stats, dict) else stats)
            if isinstance(v, dict) and SR._num(v.get("stability")) and (v.get("population") or 0) > 0]
    m["stability_end"] = sum(vals) / len(vals) if vals else None
    if irrigated and m["food_shortfall_irrigated"] is None:
        problems.append("food in the irrigated regions could not be measured")
    return m, problems


def _cw3b_gated(key):
    """A primary's per-row reading where the run passed the pre-treatment check (``read``;
    the pairs below use :func:`_cw3b_pair`, which the runner prefers)."""
    return lambda row: (row.get("m") or {}).get(key) if (row.get("m") or {}).get("pre_ok") is True else None


def _cw3b_pair(key):
    """A gated pair reading (``Outcome.pair``, stateless): ``(arm value, control value)``
    where both runs passed the pre-treatment check and recorded the same irrigated-region
    set; otherwise the failing side's value is missing: a run that failed the check reads
    None on its own side, and with both passing but different sets the control's value is
    missing. A world failing either rule is excluded from the pair, as the report's pair
    table says (:func:`_cw3b_why` labels the cell)."""
    def pair(arm_row, control_row):
        a, c = arm_row.get("m") or {}, control_row.get("m") or {}
        if a.get("pre_ok") is not True:
            return None, c.get(key)
        if c.get("pre_ok") is not True:
            return a.get(key), None
        if a.get("irrigated_set_sha") != c.get("irrigated_set_sha"):
            return a.get(key), None
        return a.get(key), c.get(key)
    return pair


def _cw3b_why(key):
    """The report's label for a missing gated value (the row whose value is missing)."""
    def why(row):
        m = row.get("m") or {}
        if m.get("pre_ok") is not True:
            return "excluded: pre-treatment check"
        if m.get(key) is None:
            return "unknown"
        return "excluded: sets differ"
    return why


def _cw3b_report(rows, strata) -> list[str]:
    """The pre-treatment check and the irrigated-region set per world and arm, and whether
    each pair (C, W) and (C_T, W_T) used the same set."""
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    out = [f"\n## Pre-treatment check at snapshot {CW3B_FIXED} and the irrigated-region set\n",
           "| Stratum | World | Arm | Check | Set (regions; sha) |", "| --- | --- | --- | --- | --- |"]
    pairs = []
    for tag, seeds in strata.items():
        for seed in seeds:
            for arm in ("R", "W", "C", "W_T", "C_T"):
                m = (by.get((arm, tag, seed)) or {}).get("m") or {}
                if not m:
                    continue
                check = "pass" if m.get("pre_ok") else f"FAIL: {m.get('pre_reasons')}"
                out.append(f"| {tag} | {seed} | {arm} | {check} | {m.get('irrigated_set')} ; {m.get('irrigated_set_sha')} |")
            for a, b in (("C", "W"), ("C_T", "W_T")):
                ma, mb = ((by.get((x, tag, seed)) or {}).get("m") or {} for x in (a, b))
                if ma and mb:
                    same = ma.get("irrigated_set_sha") == mb.get("irrigated_set_sha")
                    ok = ma.get("pre_ok") is True and mb.get("pre_ok") is True
                    pairs.append(f"| {tag} | {seed} | {a} - {b} | {'same set' if same else 'DIFFERENT SETS'} | "
                                 f"{'in the primaries' if ok and same else 'excluded from the primaries'} |")
    out += ["\n| Stratum | World | Pair | Set | Primaries |", "| --- | --- | --- | --- | --- |", *pairs]
    return out


_CW3B_BASE = ("--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves", "--grain-storage",
              "--repair-projects", "--timber-stock", "--timber-supply")
_CW3B_L9 = ("--local-budgets", "--maintenance-obligation")
_CW3B_IC = "--infrastructure-condition"
_CW3B_MODE = "--infrastructure-condition-mode"


def _cw3b_outcomes() -> tuple[SR.Outcome, ...]:
    service, food = "irrigation_serving_share_after", "food_shortfall_irrigated_after"
    return (
        # Primaries, over the snapshots after the pre-treatment ones (28): does exposure to repair keep
        # irrigation serving and food in the irrigated regions (C - W: works opened, funded only through
        # their own L9 proposal, against every work refused), and does repair keep service when the
        # treasury pays (C_T - W_T). A world failing the pre-treatment check in either arm, or whose two
        # arms recorded different irrigated-region sets, is excluded from that pair (_cw3b_gated).
        SR.Outcome("cw3b_service_l9", "Irrigation asset-turns at service >= 0.5 after snapshot 28, share (C - W: "
                   "works funded only through their own L9 proposal, against none)", "C", "W",
                   _cw3b_gated(service), primary=True, pair=_cw3b_pair(service), why=_cw3b_why(service)),
        SR.Outcome("cw3b_food_l9", "Food shortfall share after relief after snapshot 28, in the regions irrigated "
                   "at snapshot 28 (C - W)", "C", "W", _cw3b_gated(food), primary=True,
                   pair=_cw3b_pair(food), why=_cw3b_why(food)),
        SR.Outcome("cw3b_service_treasury", "Irrigation asset-turns at service >= 0.5 after snapshot 28, share "
                   "(C_T - W_T: works funded by the treasury against none)", "C_T", "W_T",
                   _cw3b_gated(service), primary=True, pair=_cw3b_pair(service), why=_cw3b_why(service)),
        SR.Outcome("cw3b_food_treasury", "Food shortfall share after snapshot 28 in the irrigated regions (C_T - W_T; "
                   "C_T also repairs roads, which C does not: the works' L9 proposal is irrigation-only)",
                   "C_T", "W_T", _cw3b_gated(food), pair=_cw3b_pair(food), why=_cw3b_why(food)),
        # Full-trajectory versions (pre-treatment snapshots included, every world).
        SR.Outcome("cw3b_service_l9_all", "Irrigation serving share over the whole run (C - W)", "C", "W",
                   _m("irrigation_serving_share")),
        SR.Outcome("cw3b_food_l9_all", "Food shortfall share over the whole run in the irrigated regions (C - W)",
                   "C", "W", _m("food_shortfall_irrigated")),
        SR.Outcome("cw3b_service_treasury_all", "Irrigation serving share over the whole run (C_T - W_T)", "C_T",
                   "W_T", _m("irrigation_serving_share")),
        SR.Outcome("cw3b_service_wear", "Irrigation serving share after snapshot 28 (W - R: what wear alone costs)",
                   "W", "R", _m("irrigation_serving_share_after")),
        SR.Outcome("cw3b_food_wear", "Food shortfall share after snapshot 28 in the irrigated regions (W - R)", "W",
                   "R", _m("food_shortfall_irrigated_after")),
        SR.Outcome("cw3b_food_met_l9", "Demand-weighted mean of min(1, sufficiency) after snapshot 28 in the "
                   "irrigated regions (C - W)", "C", "W", _m("food_met_irrigated_after")),
        SR.Outcome("cw3b_failed_l9", "Assets failed over the run (C - W)", "C", "W", _m("ic_assets_failed")),
        SR.Outcome("cw3b_failed_treasury", "Assets failed over the run (C_T - W_T)", "C_T", "W_T",
                   _m("ic_assets_failed")),
        # The works and their funding (delivery is a secondary: activation is exposure, a work opened).
        SR.Outcome("cw3b_works_opened", "Works opened on irrigation assets (C alone)", "C", None,
                   _m("works_opened_irrigation")),
        SR.Outcome("cw3b_works_delivered", "Work the works delivered (C alone; the farm time removed)", "C", None,
                   _m("ic_work_delivered")),
        SR.Outcome("cw3b_works_delivered_t", "Work the works delivered (C_T alone)", "C_T", None,
                   _m("ic_work_delivered")),
        SR.Outcome("cw3b_works_awards", "L9 awards to the works' own proposal (C alone)", "C", None,
                   _m("l9_awards_infrastructure_works")),
        SR.Outcome("cw3b_stalled_envelope", "Work-turns stalled without an envelope (C alone)", "C", None,
                   _m("ic_stalled_no_envelope")),
        SR.Outcome("cw3b_stalled_timber", "Work-turns stalled without timber (C alone)", "C", None,
                   _m("ic_stalled_no_timber")),
        SR.Outcome("cw3b_stalled_timber_t", "Work-turns stalled without timber (C_T alone)", "C_T", None,
                   _m("ic_stalled_no_timber")),
        SR.Outcome("cw3b_story", "Works stalled 20+ turns on an asset that failed (C alone: the underfunded public "
                   "works story)", "C", None, _m("story_works")),
        SR.Outcome("cw3b_pl1_delivered", "Timber the woodcutters delivered to the store (C alone; PL1 serves RS2's "
                   "needs first, then the works')", "C", None, _m("pl1_delivered")),
        SR.Outcome("cw3b_pl1_works_launched", "Expeditions PL1 launched for the works' timber need (C alone)", "C",
                   None, _m("pl1_works_launched")),
        SR.Outcome("cw3b_pl1_works_launched_t", "Expeditions PL1 launched for the works' timber need (C_T alone)",
                   "C_T", None, _m("pl1_works_launched")),
        SR.Outcome("cw3b_pl1_works_person_turns", "Woodcutter person-turns of the works' expeditions (C alone)", "C",
                   None, _m("pl1_works_person_turns")),
        SR.Outcome("cw3b_timber_refused", "The works' timber need rows PL1 refused, every reason (C alone)", "C",
                   None, _m("ic_timber_refused")),
        # Fixed harm panel (the runner's panel shows each arm against its control beside these).
        SR.Outcome("cw3b_h_rs2_displaced", "RS2 repair work delivered (C - W: the L9 envelope displacement)", "C",
                   "W", _m("rs2_work_delivered")),
        SR.Outcome("cw3b_h_rs2_displaced_t", "RS2 repair work delivered (C_T - W_T)", "C_T", "W_T",
                   _m("rs2_work_delivered")),
        SR.Outcome("cw3b_h_rs2_timber", "RS2 work-turns stalled without timber (C - W: woodcutters and forests "
                   "the works' expeditions took from RS2's later needs)", "C", "W", _m("rs2_stalled_no_timber")),
        SR.Outcome("cw3b_h_rs2_timber_t", "RS2 work-turns stalled without timber (C_T - W_T)", "C_T", "W_T",
                   _m("rs2_stalled_no_timber")),
        SR.Outcome("cw3b_h_woodcutter_turns", "Woodcutter person-turns away from home, every expedition (C - W)", "C",
                   "W", _m("pl1_person_turns")),
        SR.Outcome("cw3b_h_woodcutter_turns_t", "Woodcutter person-turns away from home (C_T - W_T)", "C_T", "W_T",
                   _m("pl1_person_turns")),
        SR.Outcome("cw3b_h_farm_time", "Farm time removed by the works, work units (C alone)", "C", None,
                   _m("ic_work_delivered")),
        SR.Outcome("cw3b_h_coins_destroyed", "Coins destroyed by the public-works sink (C alone)", "C", None,
                   _m("coins_destroyed")),
        SR.Outcome("cw3b_h_coins_destroyed_t", "Coins destroyed by the public-works sink (C_T alone)", "C_T", None,
                   _m("coins_destroyed")),
        SR.Outcome("cw3b_h_treasury", "Treasury at the end (C - W)", "C", "W", lambda r: SR.harm_value(r, "treasury")),
        SR.Outcome("cw3b_h_stability", "Mean stability of living civs at the end (C - W)", "C", "W",
                   _m("stability_end")),
        SR.Outcome("cw3b_h_food_shortfall", "Food shortfall after relief over the run, world (C - W)", "C", "W",
                   lambda r: SR.harm_value(r, "food_shortfall")),
        SR.Outcome("cw3b_h_population", "Population at the end (C - W)", "C", "W",
                   lambda r: SR.harm_value(r, "population")),
        SR.Outcome("cw3b_h_food_shortfall_t", "Food shortfall after relief, world (C_T - W_T)", "C_T", "W_T",
                   lambda r: SR.harm_value(r, "food_shortfall")),
        SR.Outcome("cw3b_h_population_t", "Population at the end (C_T - W_T)", "C_T", "W_T",
                   lambda r: SR.harm_value(r, "population")),
        SR.Outcome("cw3b_h_forest_stand", "Timber stand share of capacity at the end (C - W)", "C", "W",
                   lambda r: SR.harm_value(r, "forest_stand")),
        SR.Outcome("cw3b_h_record_only", "Food shortfall after relief, world (R - B: the record changes nothing; "
                   "structurally 0)", "R", "B", lambda r: SR.harm_value(r, "food_shortfall")),
    )


SCREENS["CW3b"] = SR.Screen(
    name="CW3b", title="S3 infrastructure condition and repair (B3)",
    preregistration=PROGRESS / "connected-world-screens-cw3b.md",
    base=_CW3B_BASE,
    arms={"B": (_CW3B_L9, None),
          "R": (_CW3B_L9 + (_CW3B_IC, _CW3B_MODE, "record_only"), "B"),
          "W": (_CW3B_L9 + (_CW3B_IC, _CW3B_MODE, "wear_only"), "R"),
          "C": (_CW3B_L9 + (_CW3B_IC,), "W"),
          "W_T": ((_CW3B_IC, _CW3B_MODE, "wear_only"), "W"),
          "C_T": ((_CW3B_IC,), "W_T")},
    root="B", pilot=PILOT, held={"template": tuple(range(3501, 3507)), "procedural": tuple(range(3601, 3607))},
    outcomes=_cw3b_outcomes(),
    activation=cw3b_activation, extract=cw3b_extract, report=_cw3b_report, ready=True, module=MODULE)


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
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["cw5c-compact"]:
        # cw5c-compact FULL_METRICS OUT: the committed CW5c metrics without per-cell fields.
        if len(args) != 3:
            raise SystemExit("usage: connected_world_screens.py cw5c-compact FULL_METRICS OUT")
        got = cw5c_compact(Path(args[1]), Path(args[2]))
        print(f"{got['rows']} rows; full metrics sha256 {got['sha256_full']}")
        return 0
    return SR.main(argv, SCREENS, prog="connected_world_screens.py")


if __name__ == "__main__":
    raise SystemExit(main())
