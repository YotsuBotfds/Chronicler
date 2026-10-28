"""Ablation components of the needs (method 7) and cohort (method 4) oracles.

A plain batch and its ablation arms (``chronicler.ablation_arms``): every
seed forked at turns T (``fork_turns``) from the plain run's exact
checkpoint, with one decision term switched off from tick T+1. Up to tick T
both arms are the same run (checked here, row for row, on the agent event
stream), so a cohort fixed at T from the plain run's turn-T sidecars is the
same set of agents in the same state in both arms; what they do over ticks
T+1 .. T+W differs only through the ablated term, its consequences and
chance. Per pairing the estimate is the ratio of the cohort's events in the
plain arm to those in the ablated arm, pooled over forks and seeds, with a
seed-clustered (ratio estimator) standard error: the forks of one seed share
a world, seeds do not. Each pairing has a pre-registered direction and
minimum effect (docs/integration/ablation-oracles.md).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .ablation_arms import (
    ABLATION_DESIGNS,
    ABLATION_FIRST_FORK,
    ABLATION_MANIFEST_FILENAME,
    ABLATION_MANIFEST_KIND,
    ABLATION_WINDOW_TURNS,
    FORK_EVENTS_FILENAME,
    FORK_INFO_FILENAME,
    batch_worldgen,
    fork_every,
    fork_turns as rule_fork_turns,
)

ABLATION_CONFIDENCE = 0.95

# Needs (method 7): the need terms of the decision (arm "needs"). Each
# pairing: agents whose need is below its behavioural threshold at the fork
# (the terms act only there), and the event that need's term pushes. The
# five of NEEDS_PAIRINGS decide; spiritual is reported (as in method 6).
NEEDS_ABLATION_ARM = "needs"
NEEDS_ABLATION_MIN_EFFECT = 0.10  # M49 spec, tier 2: 10-20% more likely than baseline
NEEDS_ABLATION_PAIRINGS = (
    ("autonomy", 0.35, "rebellion", True),
    ("social", 0.35, "migration", True),
    ("purpose", 0.35, "occupation_switch", True),
    ("material", 0.30, "migration", True),
    ("safety", 0.30, "migration", True),
    ("spiritual", 0.30, "migration", False),
)
_ALL_NEEDS_THRESHOLDS = {
    "safety": 0.30, "material": 0.30, "social": 0.35, "spiritual": 0.30, "autonomy": 0.35, "purpose": 0.35,
}

# Cohort (method 4): the relationship part of migrants' roots (arm
# "kin_roots"). Community members at the fork migrate less with the term.
COHORT_ABLATION_ARM = "kin_roots"
COHORT_ABLATION_MIN_EFFECT = 0.15  # M53 spec, oracle 4: members show 15-30% less migration

PLACEBO_ARM = "placebo"

# Community anchoring (cohort method 5's community component; arm
# "community_anchor", the anchor of --community-anchoring switched off).
# Community ties as the native decision counts them
# (chronicler-agents/src/community.rs; ``community_ties`` mirrors it from the
# turn-T sidecars): positive-valence bonds other than marriage (the native
# BondType codes: mentor 0, exile bond 3, co-religionist 4, kin 5, friend 6),
# sentiment >= 20, to a living agent of the same region, sharing a memory key
# (event type, memory turn // 5); counted up to 4 when one tie is non-kin.
COMMUNITY_ABLATION_ARM = "community_anchor"
COMMUNITY_TIE_BOND_TYPES = frozenset({0, 3, 4, 5, 6})
COMMUNITY_KIN_BOND = 5
COMMUNITY_TIE_MIN_SENTIMENT = 20
COMMUNITY_MEMORY_BUCKET = 5
COMMUNITY_FULL_TIES = 4
# Pre-registered (docs/integration/community-anchoring.md, section 3): the
# M53 band (15-30% less migration) for agents with the full ties, no effect
# beyond spillover (within 3%) for agents without a counted tie, and an
# effect that grows with the ties.
COMMUNITY_FULL_TIES_BAND = (0.70, 0.85)
COMMUNITY_NO_TIES_TOLERANCE = 0.03
# Communities as M53 oracle 1's text specifies them (informational): label
# propagation over friend, co-religionist and kin edges weighted by
# sentiment, positive and within a region; 5+ members, >= 80% of them sharing
# a memory, and a non-kin positive edge (by the native kin code).
SPEC_COMMUNITY_BOND_TYPES = frozenset({4, 5, 6})

_COUNTED = {"migration": 1, "rebellion": 2, "occupation_switch": 3}
_CODE_NAMES = {code: name for name, code in _COUNTED.items()}


class AblationInputError(ValueError):
    """Ablation arms that do not belong to the batch or do not match their manifest."""


# ---------------------------------------------------------------------------
# Loading and checking the arms
# ---------------------------------------------------------------------------

def _read_table(path: Path):
    import pyarrow.ipc as ipc
    return ipc.open_file(path).read_all()


def _prefix(table, last_turn: int):
    import pyarrow.compute as pc
    return table.filter(pc.less_equal(table.column("turn"), last_turn))


def _window_counts(table, first: int, last: int) -> dict[tuple[int, int], list[int]]:
    """{(agent id, event code): sorted turns} of counted events on turns first .. last."""
    import pyarrow.compute as pc
    mask = pc.and_(pc.greater_equal(table.column("turn"), first), pc.less_equal(table.column("turn"), last))
    rows = table.filter(mask)
    out: dict[tuple[int, int], list[int]] = defaultdict(list)
    for turn, agent, name in zip(rows.column("turn").to_pylist(), rows.column("agent_id").to_pylist(),
                                 rows.column("event_type").to_pylist()):
        code = _COUNTED.get(name)
        if code is not None:
            out[(int(agent), code)].append(int(turn))
    return out


def load_ablation_arms(ablation_dir: Path, batch_dir: Path) -> dict:
    """Check ``ablation_dir`` against its manifest and the plain batch, and
    load every fork's window events.

    Returns ``{"summary": <report entry>, "design": D, "arms": {arm:
    {"window": W, "design": D, "forks": {seed: {fork turn: window counts}}}}}``
    where D is the manifest's fork design (``schema_version`` 1 or 2,
    ``chronicler.ablation_arms``): its fork turns must be that design's for
    the plain batch's turns and world. Refuses (``AblationInputError``) arms
    forked from another batch (the plain manifest's SHA-256), other seeds, an
    incomplete or failed run, a changed file, a fork whose recorded ablation
    is not its arm's, and a fork whose event stream differs from the plain
    run's on any row up to the fork turn.
    """
    from .batch_manifest import file_sha256

    ablation_dir = Path(ablation_dir)
    batch_dir = Path(batch_dir)
    path = ablation_dir / ABLATION_MANIFEST_FILENAME
    if not path.is_file():
        raise AblationInputError(f"no {ABLATION_MANIFEST_FILENAME} in {ablation_dir}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    design = manifest.get("schema_version")
    if manifest.get("kind") != ABLATION_MANIFEST_KIND or design not in ABLATION_DESIGNS or isinstance(design, bool):
        raise AblationInputError(f"{path} is not an ablation manifest of schema {' or '.join(map(str, ABLATION_DESIGNS))}")
    if design >= 2 and manifest.get("design") != design:
        raise AblationInputError(f"{path} records design {manifest.get('design')!r} under schema {design}")
    if manifest.get("status") != "complete":
        raise AblationInputError(f"ablation arms status is {manifest.get('status')!r}, not 'complete'")
    plain_manifest_path = batch_dir / "batch_manifest.json"
    if file_sha256(plain_manifest_path) != manifest.get("plain_manifest_sha256"):
        raise AblationInputError("the ablation arms were forked from another batch (plain manifest SHA-256 differs)")
    plain = json.loads(plain_manifest_path.read_text(encoding="utf-8"))
    plain_seeds = sorted(int(run["seed"]) for run in plain.get("runs", []))
    if sorted(int(seed) for seed in manifest.get("seeds", [])) != plain_seeds:
        raise AblationInputError("the ablation arms cover other seeds than the batch")
    window = int(manifest.get("window_turns", 0))
    plain_turns = int(plain.get("turns") or 0)
    every = fork_every(batch_worldgen(plain), design)
    expected_forks = rule_fork_turns(plain_turns, window, every)
    if window != ABLATION_WINDOW_TURNS or list(manifest.get("fork_turns", [])) != expected_forks:
        raise AblationInputError(
            f"fork turns {manifest.get('fork_turns')} / window {window} are not the pre-registered rule's "
            f"{expected_forks} / {ABLATION_WINDOW_TURNS} for {plain_turns} turns (design {design})")
    arms_named = list(manifest.get("arms", []))
    records = manifest.get("forks", [])
    by_seed: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        by_seed[int(record["seed"])].append(record)
    expected_count = len(plain_seeds) * len(expected_forks) * len(arms_named)
    if len(records) != expected_count:
        raise AblationInputError(f"{len(records)} forks recorded, {expected_count} expected")
    run_dirs = {int(run["seed"]): run["dir"] for run in plain.get("runs", [])}
    arms: dict[str, dict] = {arm: {"window": window, "forks": defaultdict(dict)} for arm in arms_named}
    checked = 0
    for seed in plain_seeds:
        plain_events = _read_table(batch_dir / run_dirs[seed] / "agent_events.arrow")
        for record in by_seed.get(seed, []):
            arm, fork_turn = record["arm"], int(record["fork_turn"])
            if arm not in arms or fork_turn not in expected_forks:
                raise AblationInputError(f"unexpected fork {arm} seed {seed} turn {fork_turn}")
            fork_path = ablation_dir / record["dir"]
            for name, digest in (record.get("files") or {}).items():
                if file_sha256(fork_path / name) != digest:
                    raise AblationInputError(f"{fork_path / name} changed since the arms ran")
            info = json.loads((fork_path / FORK_INFO_FILENAME).read_text(encoding="utf-8"))
            ablation = info.get("decision_ablation") or {}
            if (ablation.get("name") != arm or ablation.get("start_turn") != fork_turn + 1
                    or ablation.get("forked_at") != fork_turn + 1):
                raise AblationInputError(f"fork {record['dir']} records ablation {ablation!r}, not {arm} from {fork_turn + 1}")
            fork_events = _read_table(fork_path / FORK_EVENTS_FILENAME)
            if not _prefix(fork_events, fork_turn).equals(_prefix(plain_events, fork_turn)):
                raise AblationInputError(
                    f"fork {record['dir']} differs from the plain run before its fork turn {fork_turn}: "
                    "the arms do not share their history")
            arms[arm]["forks"][seed][fork_turn] = _window_counts(fork_events, fork_turn + 1, fork_turn + window)
            checked += 1
        del plain_events
    summary = {
        "status": "verified",
        "manifest_sha256": file_sha256(path),
        "arms": arms_named,
        "fork_turns": expected_forks,
        "window_turns": window,
        "forks": checked,
        "fork_rule": f"every {every} turns from {ABLATION_FIRST_FORK} while T + {window} < turns",
        "history_identity": "every fork's agent events equal the plain run's up to the fork turn",
        "native_sha256": (manifest.get("native") or {}).get("sha256"),
    }
    if design >= 2:
        # Design 1 reports keep their bytes without the key.
        summary["design"] = design
    return {"summary": summary, "design": design,
            "arms": {arm: {"window": window, "design": design, "forks": dict(data["forks"])}
                     for arm, data in arms.items()}}


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _t(probability: float, df: int) -> float:
    from scipy.stats import t as student_t
    return float(student_t.ppf(probability, df))


def _r(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def ablation_ratio(per_seed: list[tuple[int, int, int]], confidence: float = ABLATION_CONFIDENCE) -> dict:
    """Plain-arm events over ablated-arm events of a cohort, pooled over seeds.

    ``per_seed``: (cohort size, plain events, ablated events) of each seed
    (its forks summed). The ``S`` informative seeds are those whose cohort
    had an event in either arm (as in ``_pooled_net_concordance``); the ratio
    estimator's seed-clustered variance is ``S / (S - 1) * sum((P_s - RR *
    A_s)^2) / A^2`` over them; bounds use Student t with ``S - 1`` degrees of
    freedom: one-sided at ``confidence`` and a two-sided interval at the same
    level. No bound with fewer than two informative seeds.
    """
    with_cohort = [(n, p, a) for n, p, a in per_seed if n > 0]
    clusters = [(n, p, a) for n, p, a in with_cohort if p + a > 0]
    cohort = sum(n for n, _p, _a in with_cohort)
    plain = sum(p for _n, p, _a in clusters)
    ablated = sum(a for _n, _p, a in clusters)
    out = {
        "cohort": cohort,
        "seeds_with_cohort": len(with_cohort),
        "informative_seeds": len(clusters),
        "plain_events": plain,
        "ablated_events": ablated,
        "plain_rate": _r(plain / cohort) if cohort else None,
        "ablated_rate": _r(ablated / cohort) if cohort else None,
        "seeds_more_with_term": sum(1 for _n, p, a in clusters if p > a),
        "seeds_fewer_with_term": sum(1 for _n, p, a in clusters if p < a),
        "rate_ratio": None,
        "effect": None,
        "standard_error": None,
        "lower_bound": None,
        "upper_bound": None,
        "interval": None,
    }
    if ablated <= 0:
        return out
    rr = plain / ablated
    out["rate_ratio"] = _r(rr)
    out["effect"] = _r(rr - 1.0)
    count = len(clusters)
    if count < 2:
        return out
    residual = sum((p - rr * a) ** 2 for _n, p, a in clusters)
    se = (count / (count - 1) * residual) ** 0.5 / ablated
    one = _t(confidence, count - 1) * se
    two = _t(0.5 + confidence / 2.0, count - 1) * se
    out["standard_error"] = _r(se)
    out["lower_bound"] = _r(rr - one)
    out["upper_bound"] = _r(rr + one)
    out["interval"] = [_r(rr - two), _r(rr + two)]
    return out


def judge(stats: dict, direction: str, min_effect: float) -> tuple[str, list[str]]:
    """PASS when the one-sided bound clears no effect in ``direction`` and
    the estimate reaches ``min_effect``; the failed criteria otherwise."""
    rr = stats.get("rate_ratio")
    failed = []
    if rr is None or stats.get("standard_error") is None:
        return "FAIL", ["not_measured"]
    if direction == "increase":
        if not stats["lower_bound"] > 1.0:
            failed.append("lower_bound")
        if not rr - 1.0 >= min_effect - 1e-12:
            failed.append("minimum_effect")
    else:
        if not stats["upper_bound"] < 1.0:
            failed.append("upper_bound")
        if not 1.0 - rr >= min_effect - 1e-12:
            failed.append("minimum_effect")
    return ("FAIL" if failed else "PASS"), failed


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------



def _offset_counts(turns_by_key, keys, code: int, first: int, window: int) -> list[int]:
    out = [0] * window
    for agent in keys:
        for turn in turns_by_key.get((agent, code), ()):
            offset = turn - first
            if 0 <= offset < window:
                out[offset] += 1
    return out


def _plain_turns(events: list[dict], first: int, last: int) -> dict[tuple[int, int], list[int]]:
    out: dict[tuple[int, int], list[int]] = defaultdict(list)
    for event in events:
        turn = int(event.get("turn", -1))
        if first <= turn <= last and event["event_type"] in _CODE_NAMES:
            out[(int(event["agent_id"]), int(event["event_type"]))].append(turn)
    return out


def _windowed(turns_by_key: dict, first: int, last: int) -> dict[tuple[int, int], list[int]]:
    """The arm's counted events on turns first .. last only."""
    out = {}
    for key, turns in turns_by_key.items():
        kept = [turn for turn in turns if first <= turn <= last]
        if kept:
            out[key] = kept
    return out


def _seed_forks(seed_runs: list[dict], arm: dict) -> list[tuple[dict, dict[int, dict]]]:
    forks = arm.get("forks") or {}
    out = []
    for run in seed_runs:
        seed = run.get("seed")
        if seed is None or int(seed) not in forks:
            continue
        out.append((run, forks[int(seed)]))
    return out


def needs_ablation_component(seed_runs: list[dict], arm: dict | None, *, confidence: float = ABLATION_CONFIDENCE,
                             min_effect: float = NEEDS_ABLATION_MIN_EFFECT, arm_name: str = NEEDS_ABLATION_ARM) -> dict:
    """The needs oracle's ablation component (method 7) for one arm."""
    from .validation_io import _needs_snapshot_from_columns

    if arm is None:
        return {"status": "NOT_RUN", "reason": f"no {arm_name} ablation arm", "arm": arm_name}
    window = int(arm["window"])
    per_pairing: dict[str, list[tuple[int, int, int]]] = {need: [] for need, *_ in NEEDS_ABLATION_PAIRINGS}
    offsets = {need: ([0] * window, [0] * window) for need, *_ in NEEDS_ABLATION_PAIRINGS}
    unexposed: dict[str, list[tuple[int, int, int]]] = {name: [] for name in _COUNTED}
    per_seed = []
    missing = []
    for run, forks in _seed_forks(seed_runs, arm):
        seed_tallies = {need: [0, 0, 0] for need, *_ in NEEDS_ABLATION_PAIRINGS}
        unexposed_tallies = {name: [0, 0, 0] for name in _COUNTED}
        for fork_turn, ablated_turns in sorted(forks.items()):
            snapshot = _needs_snapshot_from_columns(run.get("needs_columns"), fork_turn)
            if snapshot is None:
                missing.append(f"seed {run.get('seed')} turn {fork_turn}")
                continue
            columns = snapshot["columns"]
            first, last = fork_turn + 1, fork_turn + window
            plain_turns = _plain_turns(run["events"], first, last)
            ablated_turns = _windowed(ablated_turns, first, last)
            ids = [int(agent) for agent in columns["agent_id"]]
            for need, threshold, event_name, _required in NEEDS_ABLATION_PAIRINGS:
                code = _COUNTED[event_name]
                values = columns[need]
                cohort = [agent for agent, value in zip(ids, values) if value < threshold]
                plain = sum(len(plain_turns.get((agent, code), ())) for agent in cohort)
                ablated = sum(len(ablated_turns.get((agent, code), ())) for agent in cohort)
                tally = seed_tallies[need]
                tally[0] += len(cohort)
                tally[1] += plain
                tally[2] += ablated
                plain_offsets, ablated_offsets = offsets[need]
                for k, value in enumerate(_offset_counts(plain_turns, cohort, code, first, window)):
                    plain_offsets[k] += value
                for k, value in enumerate(_offset_counts(ablated_turns, cohort, code, first, window)):
                    ablated_offsets[k] += value
            exposed_none = [
                agent for i, agent in enumerate(ids)
                if all(columns[need][i] >= threshold for need, threshold in _ALL_NEEDS_THRESHOLDS.items())
            ]
            for event_name, code in _COUNTED.items():
                tally = unexposed_tallies[event_name]
                tally[0] += len(exposed_none)
                tally[1] += sum(len(plain_turns.get((agent, code), ())) for agent in exposed_none)
                tally[2] += sum(len(ablated_turns.get((agent, code), ())) for agent in exposed_none)
        for need, tally in seed_tallies.items():
            per_pairing[need].append(tuple(tally))
        for event_name, tally in unexposed_tallies.items():
            unexposed[event_name].append(tuple(tally))
        per_seed.append({
            "seed": run.get("seed"),
            "forks": sorted(forks),
            "by_pairing": {need: list(tally) for need, tally in seed_tallies.items() if tally[0]},
        })
    if missing:
        return {"status": "ERROR", "reason": "no needs snapshot at fork turn: " + ", ".join(missing[:5]),
                "arm": arm_name}
    if not per_seed:
        return {"status": "NOT_RUN", "reason": "no seed of the batch has a fork in the arm", "arm": arm_name}
    by_pairing = {}
    failed = []
    for need, threshold, event_name, required in NEEDS_ABLATION_PAIRINGS:
        stats = ablation_ratio(per_pairing[need], confidence)
        status, criteria = judge(stats, "increase", min_effect)
        by_pairing[need] = {
            "event_type": event_name,
            "threshold": threshold,
            "required": required,
            "direction": "more with the term",
            "status": status,
            "failed_criteria": criteria,
            **stats,
            "plain_by_window_turn": offsets[need][0],
            "ablated_by_window_turn": offsets[need][1],
        }
        if required and status != "PASS":
            failed.append(need)
    return {
        "status": "FAIL" if failed else "PASS",
        "arm": arm_name,
        "comparison": "plain_vs_ablated_fork",
        "criterion": (
            f"each required pairing: agents below the need's threshold at the fork have more of its event "
            f"over the {window} turns after it with the need terms than without: one-sided "
            f"{confidence:.0%} seed-clustered lower bound of the rate ratio above 1 and the ratio at least "
            f"{1 + min_effect:.2f}"
        ),
        "minimum_effect": min_effect,
        "confidence": confidence,
        "window_turns": window,
        "failed_pairings": failed,
        "seeds": len(per_seed),
        "forks": sum(len(record["forks"]) for record in per_seed),
        "by_pairing": by_pairing,
        "unexposed": {
            name: {"event_type": name, **ablation_ratio(unexposed[name], confidence)} for name in _COUNTED
        },
        "per_seed": per_seed,
    }


def cohort_ablation_result(seed_runs: list[dict], arm: dict | None, *, confidence: float = ABLATION_CONFIDENCE,
                           min_effect: float = COHORT_ABLATION_MIN_EFFECT, arm_name: str = COHORT_ABLATION_ARM) -> dict:
    """Cohort oracle method 4 for one arm: community members at the fork
    migrate less with the kin roots than without them."""
    from .validation_io import _graph_snapshot_from_columns, _needs_snapshot_from_columns, detect_communities

    if arm is None:
        return {"status": "NOT_RUN", "reason": f"no {arm_name} ablation arm", "arm": arm_name}
    window = int(arm["window"])
    groups = ("members", "non_members")
    tallies: dict[tuple[str, str], list[tuple[int, int, int]]] = {
        (group, event): [] for group in groups for event in ("migration", "rebellion")
    }
    offsets = ([0] * window, [0] * window)
    per_seed = []
    missing = []
    for run, forks in _seed_forks(seed_runs, arm):
        seed_tally = {key: [0, 0, 0] for key in tallies}
        communities_seen = 0
        for fork_turn, ablated_turns in sorted(forks.items()):
            needs = _needs_snapshot_from_columns(run.get("needs_columns"), fork_turn)
            graph = _graph_snapshot_from_columns(run.get("relationship_columns"), run.get("memory_columns"), fork_turn)
            if needs is None:
                missing.append(f"seed {run.get('seed')} turn {fork_turn}")
                continue
            alive = {int(agent) for agent in needs["columns"]["agent_id"]}
            members: set[int] = set()
            if graph is not None:
                communities = detect_communities(graph["edges"], graph["memory_signatures"])
                communities_seen += len(communities)
                for community in communities:
                    members.update(int(agent) for agent in community)
            members &= alive
            cohorts = {"members": sorted(members), "non_members": sorted(alive - members)}
            first, last = fork_turn + 1, fork_turn + window
            plain_turns = _plain_turns(run["events"], first, last)
            ablated_turns = _windowed(ablated_turns, first, last)
            for (group, event_name), _values in tallies.items():
                code = _COUNTED[event_name]
                cohort = cohorts[group]
                tally = seed_tally[(group, event_name)]
                tally[0] += len(cohort)
                tally[1] += sum(len(plain_turns.get((agent, code), ())) for agent in cohort)
                tally[2] += sum(len(ablated_turns.get((agent, code), ())) for agent in cohort)
            code = _COUNTED["migration"]
            for k, value in enumerate(_offset_counts(plain_turns, cohorts["members"], code, first, window)):
                offsets[0][k] += value
            for k, value in enumerate(_offset_counts(ablated_turns, cohorts["members"], code, first, window)):
                offsets[1][k] += value
        for key, tally in seed_tally.items():
            tallies[key].append(tuple(tally))
        per_seed.append({
            "seed": run.get("seed"),
            "forks": sorted(forks),
            "communities": communities_seen,
            "members_migration": list(seed_tally[("members", "migration")]),
        })
    if missing:
        return {"status": "ERROR", "reason": "no needs snapshot at fork turn: " + ", ".join(missing[:5]),
                "arm": arm_name}
    if not per_seed:
        return {"status": "NOT_RUN", "reason": "no seed of the batch has a fork in the arm", "arm": arm_name}
    members_migration = ablation_ratio(tallies[("members", "migration")], confidence)
    status, failed = judge(members_migration, "decrease", min_effect)
    extra = {}
    if status != "PASS":
        extra["reason"] = (
            f"members' migration rate ratio {members_migration['rate_ratio']} (upper bound "
            f"{members_migration['upper_bound']}); needs at most {1 - min_effect:.2f} and a bound below 1"
        )
    return {
        "status": status,
        **extra,
        "arm": arm_name,
        "comparison": "plain_vs_ablated_fork",
        "criterion": (
            f"community members at the fork migrate less over the {window} turns after it with the kin "
            f"roots than without: one-sided {confidence:.0%} seed-clustered upper bound of the rate ratio "
            f"below 1 and the ratio at most {1 - min_effect:.2f}"
        ),
        "minimum_effect": min_effect,
        "confidence": confidence,
        "window_turns": window,
        "failed_criteria": failed,
        "seeds": len(per_seed),
        "forks": sum(len(record["forks"]) for record in per_seed),
        "members_migration": {
            "direction": "fewer with the term",
            **members_migration,
            "plain_by_window_turn": offsets[0],
            "ablated_by_window_turn": offsets[1],
        },
        "informational": {
            "members_rebellion": ablation_ratio(tallies[("members", "rebellion")], confidence),
            "non_members_migration": ablation_ratio(tallies[("non_members", "migration")], confidence),
            "non_members_rebellion": ablation_ratio(tallies[("non_members", "rebellion")], confidence),
        },
        "per_seed": per_seed,
    }


# ---------------------------------------------------------------------------
# Community anchoring (cohort method 5's community component)
# ---------------------------------------------------------------------------

def _memory_keys(memory_signatures: dict) -> dict[int, set[tuple[int, int]]]:
    return {int(agent): {(int(sig[0]), int(sig[1]) // COMMUNITY_MEMORY_BUCKET) for sig in sigs}
            for agent, sigs in memory_signatures.items()}


def community_ties(edges, regions: dict[int, int], memory_signatures: dict) -> dict[int, tuple[int, int, int]]:
    """``{agent: (ties, non-kin ties, counted ties)}`` of every agent of
    ``regions`` (agent id -> region) with a tie, from a turn's sidecars, as
    ``community::community_ties`` counts them natively."""
    keys = _memory_keys(memory_signatures)
    ties: dict[int, list[int]] = {}
    for a, b, bond_type, sentiment in edges:
        a, b = int(a), int(b)
        if int(bond_type) not in COMMUNITY_TIE_BOND_TYPES or int(sentiment) < COMMUNITY_TIE_MIN_SENTIMENT:
            continue
        region = regions.get(a)
        if region is None or regions.get(b) != region:
            continue
        if not (keys.get(a) and keys.get(b) and keys[a] & keys[b]):
            continue
        tally = ties.setdefault(a, [0, 0])
        tally[0] += 1
        if int(bond_type) != COMMUNITY_KIN_BOND:
            tally[1] += 1
    return {agent: (t, nk, min(t, COMMUNITY_FULL_TIES) if nk else 0) for agent, (t, nk) in ties.items()}


def detect_spec_communities(edges, regions: dict[int, int], memory_signatures: dict) -> list[set[int]]:
    """Communities as M53 oracle 1's text specifies them (informational):
    deterministic label propagation (ascending ids, ties to the smaller
    label, at most 20 sweeps) over friend, co-religionist and kin edges
    weighted by sentiment, positive and joining two agents of one region;
    groups of 5+ with a non-kin positive edge in which >= 80% of members
    share a memory key with another member."""
    weights: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    non_kin_pairs: set[frozenset] = set()
    for a, b, bond_type, sentiment in edges:
        a, b = int(a), int(b)
        if int(bond_type) not in SPEC_COMMUNITY_BOND_TYPES or int(sentiment) <= 0:
            continue
        region = regions.get(a)
        if region is None or regions.get(b) != region or a == b:
            continue
        weights[a][b] += int(sentiment)
        weights[b][a] += int(sentiment)
        if int(bond_type) != COMMUNITY_KIN_BOND:
            non_kin_pairs.add(frozenset((a, b)))
    nodes = sorted(weights)
    labels = {node: node for node in nodes}
    for _sweep in range(20):
        changed = False
        for node in nodes:
            score: dict[int, float] = defaultdict(float)
            for other, weight in weights[node].items():
                score[labels[other]] += weight
            best = min(score, key=lambda label: (-score[label], label))
            if best != labels[node]:
                labels[node] = best
                changed = True
        if not changed:
            break
    groups: dict[int, set[int]] = defaultdict(set)
    for node, label in labels.items():
        groups[label].add(node)
    keys = _memory_keys(memory_signatures)
    out = []
    for label in sorted(groups):
        members = groups[label]
        if len(members) < 5:
            continue
        ordered = sorted(members)
        if not any(frozenset((x, y)) in non_kin_pairs for i, x in enumerate(ordered) for y in ordered[i + 1:]):
            continue
        shared = sum(1 for x in members
                     if keys.get(x) and any(keys[x] & keys.get(y, set()) for y in members if y != x))
        if shared / len(members) < 0.80:
            continue
        out.append(members)
    return out


_COMMUNITY_COHORTS = (
    "members", "non_members", "full_ties", "partial_ties", "no_ties", "spec_members", "spec_non_members",
)


def community_ablation_result(seed_runs: list[dict], arm: dict | None, *, confidence: float = ABLATION_CONFIDENCE,
                              min_effect: float = COHORT_ABLATION_MIN_EFFECT,
                              arm_name: str = COMMUNITY_ABLATION_ARM) -> dict:
    """Cohort method 5's community component: what the community anchor
    (arm ``community_anchor``) does to the migration of agents at the fork.

    ``status`` is the pre-registered claim of cohort method 4 on the
    oracle's community members (``detect_communities``): at least
    ``min_effect`` less migration with the anchor, upper bound below 1.
    ``restated_candidate`` (reported, pending a decision;
    docs/integration/community-anchoring.md) scores the anchor's own
    exposure: agents with ``COMMUNITY_FULL_TIES`` counted ties migrate
    15-30% less (upper bound below 1), agents without a counted tie within
    ``COMMUNITY_NO_TIES_TOLERANCE`` of no effect (95% interval), and the
    effect grows with the ties."""
    from .validation_io import _graph_snapshot_from_columns, _needs_snapshot_from_columns, detect_communities

    if arm is None:
        return {"status": "NOT_RUN", "reason": f"no {arm_name} ablation arm", "arm": arm_name}
    window = int(arm["window"])
    tallies: dict[tuple[str, str], list[tuple[int, int, int]]] = {
        (cohort, event): [] for cohort in _COMMUNITY_COHORTS for event in ("migration", "rebellion")
    }
    offsets = {cohort: ([0] * window, [0] * window) for cohort in ("members", "full_ties")}
    per_seed = []
    missing = []
    for run, forks in _seed_forks(seed_runs, arm):
        seed_tally = {key: [0, 0, 0] for key in tallies}
        for fork_turn, ablated_turns in sorted(forks.items()):
            needs = _needs_snapshot_from_columns(run.get("needs_columns"), fork_turn)
            graph = _graph_snapshot_from_columns(run.get("relationship_columns"), run.get("memory_columns"), fork_turn)
            if needs is None:
                missing.append(f"seed {run.get('seed')} turn {fork_turn}")
                continue
            columns = needs["columns"]
            alive = [int(agent) for agent in columns["agent_id"]]
            regions = {int(agent): int(region) for agent, region in zip(columns["agent_id"], columns["region"])}
            members: set[int] = set()
            spec_members: set[int] = set()
            counted: dict[int, int] = {}
            if graph is not None:
                for community in detect_communities(graph["edges"], graph["memory_signatures"]):
                    members.update(int(agent) for agent in community)
                for community in detect_spec_communities(graph["edges"], regions, graph["memory_signatures"]):
                    spec_members.update(community)
                counted = {agent: c for agent, (_t, _nk, c) in
                           community_ties(graph["edges"], regions, graph["memory_signatures"]).items()}
            cohorts = {
                "members": [a for a in alive if a in members],
                "non_members": [a for a in alive if a not in members],
                "full_ties": [a for a in alive if counted.get(a, 0) >= COMMUNITY_FULL_TIES],
                "partial_ties": [a for a in alive if 0 < counted.get(a, 0) < COMMUNITY_FULL_TIES],
                "no_ties": [a for a in alive if counted.get(a, 0) == 0],
                "spec_members": [a for a in alive if a in spec_members],
                "spec_non_members": [a for a in alive if a not in spec_members],
            }
            first, last = fork_turn + 1, fork_turn + window
            plain_turns = _plain_turns(run["events"], first, last)
            ablated_turns = _windowed(ablated_turns, first, last)
            for (cohort_name, event_name) in tallies:
                code = _COUNTED[event_name]
                cohort = cohorts[cohort_name]
                tally = seed_tally[(cohort_name, event_name)]
                tally[0] += len(cohort)
                tally[1] += sum(len(plain_turns.get((agent, code), ())) for agent in cohort)
                tally[2] += sum(len(ablated_turns.get((agent, code), ())) for agent in cohort)
            code = _COUNTED["migration"]
            for cohort_name, (plain_offsets, ablated_offsets) in offsets.items():
                for k, value in enumerate(_offset_counts(plain_turns, cohorts[cohort_name], code, first, window)):
                    plain_offsets[k] += value
                for k, value in enumerate(_offset_counts(ablated_turns, cohorts[cohort_name], code, first, window)):
                    ablated_offsets[k] += value
        for key, tally in seed_tally.items():
            tallies[key].append(tuple(tally))
        per_seed.append({
            "seed": run.get("seed"),
            "forks": sorted(forks),
            "migration": {cohort: list(seed_tally[(cohort, "migration")]) for cohort in _COMMUNITY_COHORTS},
        })
    if missing:
        return {"status": "ERROR", "reason": "no needs snapshot at fork turn: " + ", ".join(missing[:5]),
                "arm": arm_name}
    if not per_seed:
        return {"status": "NOT_RUN", "reason": "no seed of the batch has a fork in the arm", "arm": arm_name}
    migration = {cohort: ablation_ratio(tallies[(cohort, "migration")], confidence) for cohort in _COMMUNITY_COHORTS}
    rebellion = {cohort: ablation_ratio(tallies[(cohort, "rebellion")], confidence) for cohort in _COMMUNITY_COHORTS}
    status, failed = judge(migration["members"], "decrease", min_effect)
    # The candidate restated claim (reported, not deciding).
    full = migration["full_ties"]
    full_status, full_failed = judge(full, "decrease", min_effect)
    low, high = COMMUNITY_FULL_TIES_BAND
    if full.get("rate_ratio") is not None and full["rate_ratio"] < low - 1e-12:
        full_status = "FAIL"
        full_failed = [*full_failed, "beyond_band"]
    none = migration["no_ties"]
    interval = none.get("interval")
    tol = COMMUNITY_NO_TIES_TOLERANCE
    none_ok = bool(interval) and None not in interval and 1 - tol <= interval[0] and interval[1] <= 1 + tol
    ratios = [migration[c].get("rate_ratio") for c in ("full_ties", "partial_ties", "no_ties")]
    dose_ok = None not in ratios and ratios[0] < ratios[1] < ratios[2]
    restated = {
        "status": "PASS" if full_status == "PASS" and none_ok and dose_ok else "FAIL",
        "label": "candidate restated claim (pending a decision; not deciding)",
        "full_ties": {"status": full_status, "failed_criteria": full_failed, "band": [low, high]},
        "no_ties_within_tolerance": none_ok,
        "no_ties_tolerance": tol,
        "dose_response": dose_ok,
    }
    extra = {}
    if status != "PASS":
        extra["reason"] = (
            f"members' migration rate ratio {migration['members']['rate_ratio']} (upper bound "
            f"{migration['members']['upper_bound']}); needs at most {1 - min_effect:.2f} and a bound below 1"
        )
    by_cohort = {}
    for cohort, stats in migration.items():
        if cohort == "full_ties":
            stats = {**stats, "plain_by_window_turn": offsets["full_ties"][0],
                     "ablated_by_window_turn": offsets["full_ties"][1]}
        by_cohort[cohort] = stats
    return {
        "status": status,
        **extra,
        "arm": arm_name,
        "comparison": "plain_vs_ablated_fork",
        "criterion": (
            f"community members at the fork migrate less over the {window} turns after it with the "
            f"community anchor than without: one-sided {confidence:.0%} seed-clustered upper bound of the "
            f"rate ratio below 1 and the ratio at most {1 - min_effect:.2f}"
        ),
        "minimum_effect": min_effect,
        "confidence": confidence,
        "window_turns": window,
        "failed_criteria": failed,
        "seeds": len(per_seed),
        "forks": sum(len(record["forks"]) for record in per_seed),
        "members_migration": {
            "direction": "fewer with the term",
            **migration["members"],
            "plain_by_window_turn": offsets["members"][0],
            "ablated_by_window_turn": offsets["members"][1],
        },
        "migration_by_cohort": by_cohort,
        "rebellion_by_cohort": rebellion,
        "restated_candidate": restated,
        "per_seed": per_seed,
    }
