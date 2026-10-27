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
    ABLATION_FIRST_FORK,
    ABLATION_FORK_EVERY,
    ABLATION_MANIFEST_FILENAME,
    ABLATION_MANIFEST_KIND,
    ABLATION_MANIFEST_SCHEMA_VERSION,
    ABLATION_WINDOW_TURNS,
    FORK_EVENTS_FILENAME,
    FORK_INFO_FILENAME,
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

    Returns ``{"summary": <report entry>, "arms": {arm: {"window": W,
    "forks": {seed: {fork turn: window counts}}}}}``. Refuses
    (``AblationInputError``) arms forked from another batch (the plain
    manifest's SHA-256), other seeds, an incomplete or failed run, a changed
    file, a fork whose recorded ablation is not its arm's, and a fork whose
    event stream differs from the plain run's on any row up to the fork turn.
    """
    from .batch_manifest import file_sha256

    ablation_dir = Path(ablation_dir)
    batch_dir = Path(batch_dir)
    path = ablation_dir / ABLATION_MANIFEST_FILENAME
    if not path.is_file():
        raise AblationInputError(f"no {ABLATION_MANIFEST_FILENAME} in {ablation_dir}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("kind") != ABLATION_MANIFEST_KIND or manifest.get("schema_version") != ABLATION_MANIFEST_SCHEMA_VERSION:
        raise AblationInputError(f"{path} is not an ablation manifest of schema {ABLATION_MANIFEST_SCHEMA_VERSION}")
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
    expected_forks = rule_fork_turns(plain_turns, window)
    if window != ABLATION_WINDOW_TURNS or list(manifest.get("fork_turns", [])) != expected_forks:
        raise AblationInputError(
            f"fork turns {manifest.get('fork_turns')} / window {window} are not the pre-registered rule's "
            f"{expected_forks} / {ABLATION_WINDOW_TURNS} for {plain_turns} turns")
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
        "fork_rule": f"every {ABLATION_FORK_EVERY} turns from {ABLATION_FIRST_FORK} while T + {window} < turns",
        "history_identity": "every fork's agent events equal the plain run's up to the fork turn",
        "native_sha256": (manifest.get("native") or {}).get("sha256"),
    }
    return {"summary": summary, "arms": {arm: {"window": window, "forks": dict(data["forks"])}
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
