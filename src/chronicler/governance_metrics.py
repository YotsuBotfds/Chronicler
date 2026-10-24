"""M67 measurement-first extractor over viewer bundles with governance stats.

``extract_governance_metrics(bundles)`` reads ``history[*].civ_stats[*].governance``
(written by ``governance_runtime.governance_snapshot``) plus the event timeline
and reports the M67 quantities that now have a production producer:
institution counts/tenure/churn, regime-label reachability, legitimacy and
political-capital distributions, elite counts, MMP/EMP/SFD/PSI series
summaries, PSI crisis predictiveness, sub-index co-occurrence and recovery.

Bundles without governance stats are skipped; with none, ``{"runs": 0}``.
These are run diagnostics, not M67 qualification (which needs the 200-seed
x 500-turn campaign and M61b scale validation).
"""
from __future__ import annotations

from collections import Counter

CRISIS_OUTCOMES = frozenset({"secession", "civil_war", "revolt", "succession_crisis", "collapse",
                             "institution_repealed", "twilight_absorption"})
OUTCOME_WINDOW = (10, 40)
COOCCURRENCE_WINDOW = 20
RECOVERY_WINDOW = 120
LABELS = ("frozen_stable", "highly_fluctuating", "complex_cycling")


def _percentiles(values: list[float]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))]  # noqa: E731
    return {"p10": pick(0.1), "p25": pick(0.25), "median": pick(0.5), "p75": pick(0.75),
            "p90": pick(0.9), "mean": sum(ordered) / len(ordered), "n": len(ordered)}


def _civ_series(bundle: dict) -> dict[str, list[tuple[int, dict, dict]]]:
    series: dict[str, list[tuple[int, dict, dict]]] = {}
    for snap in bundle.get("history", []):
        for name, civ in snap.get("civ_stats", {}).items():
            gov = civ.get("governance")
            if gov is not None and civ.get("regions"):
                series.setdefault(name, []).append((snap["turn"], civ, gov))
    return series


def extract_governance_metrics(bundles: list[dict]) -> dict:
    runs = 0
    legit, capital, psi, mmp, emp, sfd, active_counts = [], [], [], [], [], [], []
    qualifiers, holders, aspirants = [], [], []
    tenures: list[int] = []
    final_labels: Counter = Counter()
    label_runs: Counter = Counter()
    phases: Counter = Counter()
    event_totals: Counter = Counter()
    crisis_turns = civ_turns = 0
    onsets = followed = cooccur = recovered = 0
    crisis_runs = runs_with_followed = 0
    for bundle in bundles:
        series = _civ_series(bundle)
        if not series:
            continue
        runs += 1
        events_by_civ: dict[str, list[tuple[int, str]]] = {}
        for event in bundle.get("events_timeline", []):
            event_totals[event["event_type"]] += 1
            for actor in event.get("actors", [])[:2]:
                events_by_civ.setdefault(actor, []).append((event["turn"], event["event_type"]))
        run_labels = set()
        run_crisis = run_followed = False
        for name, rows in series.items():
            spells: dict[str, int] = {}
            prev_crisis = False
            for turn, civ, gov in rows:
                civ_turns += 1
                legit.append(gov["ruler_legitimacy"])
                capital.append(gov["political_capital"])
                psi.append(gov["psi"])
                mmp.append(gov["mmp"])
                emp.append(gov["emp"])
                sfd.append(gov["sfd"])
                active_counts.append(len(gov["institutions"]))
                qualifiers.append(gov["elite_qualifiers"])
                holders.append(gov["office_holders"])
                aspirants.append(gov["frustrated_aspirants"])
                phases[gov["cycle_phase"]] += 1
                run_labels.add(gov["institutional_regime"])
                current = set(gov["institutions"])
                for t in list(spells):
                    if t not in current:
                        tenures.append(turn - spells.pop(t))
                for t in current:
                    spells.setdefault(t, turn)
                crisis = bool(gov["psi_crisis"])
                crisis_turns += crisis
                if crisis and not prev_crisis:
                    onsets += 1
                    run_crisis = True
                    lo, hi = turn + OUTCOME_WINDOW[0], turn + OUTCOME_WINDOW[1]
                    if any(lo <= t <= hi and et in CRISIS_OUTCOMES for t, et in events_by_civ.get(name, ())):
                        followed += 1
                        run_followed = True
                    window = [g for t, _c, g in rows if turn - COOCCURRENCE_WINDOW < t <= turn]
                    if all(any(g[k] >= 1.0 for g in window) for k in ("mmp", "emp", "sfd")):
                        cooccur += 1
                    if any(t > turn and t - turn <= RECOVERY_WINDOW and et == "psi_recovery"
                           for t, et in events_by_civ.get(name, ())):
                        recovered += 1
                prev_crisis = crisis
            final_labels[rows[-1][2]["institutional_regime"]] += 1
        for label in LABELS:
            label_runs[label] += label in run_labels
        crisis_runs += run_crisis
        runs_with_followed += run_followed
    if runs == 0:
        return {"runs": 0}
    fired = ("institution_enacted", "institution_repealed", "fiscal_crisis", "ambition_fulfilled",
             "ambition_failed", "legitimacy_crisis", "elite_overproduction", "psi_crisis", "psi_recovery",
             "revolt", "civil_war", "secession_suppressed", "reform_pressure", "institutional_regime_shift")
    completed, failed = event_totals["ambition_fulfilled"], event_totals["ambition_failed"]
    return {
        "runs": runs,
        "civ_turns": civ_turns,
        "institutions": {"active_count": _percentiles(active_counts), "tenure": _percentiles(tenures)},
        "regime_reachability": {label: label_runs[label] / runs for label in LABELS},
        "final_regimes": dict(final_labels),
        "cycle_phases": dict(phases),
        "legitimacy": _percentiles(legit),
        "political_capital": _percentiles(capital),
        "elites": {"qualifiers": _percentiles(qualifiers), "office_holders": _percentiles(holders),
                   "frustrated_aspirants": _percentiles(aspirants)},
        "psi": _percentiles(psi), "mmp": _percentiles(mmp), "emp": _percentiles(emp), "sfd": _percentiles(sfd),
        "psi_crisis_share": crisis_turns / max(1, civ_turns),
        "psi_crisis_onsets": onsets,
        "crisis_predictiveness": {"onsets_followed": followed / onsets if onsets else None,
                                  "crisis_runs": crisis_runs,
                                  "runs_followed": runs_with_followed / crisis_runs if crisis_runs else None},
        "subindex_cooccurrence": cooccur / onsets if onsets else None,
        "crisis_recovery_within_120": recovered / onsets if onsets else None,
        "ambition_completion_rate": completed / (completed + failed) if completed + failed else None,
        "events_per_run": {k: event_totals[k] / runs for k in fired},
    }
