"""Batch admission, bundle and sidecar loading, and the oracles bound to them.

Besides the loaders, this module holds the needs, cohort, community and
determinism oracles, which call helpers that tests patch here (for example
``chronicler.validation_io._read_arrow_columns``) or re-enter themselves
through their module-level names, and ``_run_oracles`` and ``_cli_main``, the
one orchestration and CLI of ``validation_io`` and ``chronicler.validate``.
The era and arc, artifact and regression oracles live in
``validation_trajectories``, ``validation_artifacts`` and
``validation_regression``, shared helpers in ``validation_common``; every
name is re-exported here (docs/integration/validation-split.md).
"""
from __future__ import annotations
import argparse
from array import array
from bisect import bisect_left, bisect_right
import json
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import ceil, comb  # noqa: F401  (ceil: every name bound here before the split stays bound)
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .artifact_io import ArtifactIOError, strict_json_dumps, strict_json_loads
from .batch_manifest import (
    MANIFEST_FILENAME,
    BatchManifestError,
    batch_cohort,
    file_sha256,
    load_batch_manifest,
    _run_fact_problems,
    _verify_batch_manifest_inputs,
    verify_batch_manifest,
)
from .validation_gate import (
    CAUSAL_ORACLES_FLAG, NEEDS_BINDING_REQUIRED_PROFILES, PROFILE_CHOICES, causal_oracles_required,
)
from .snapshot_pruning import restore_bundle
from .validation_common import (  # noqa: F401  (split out; every name stays importable here)
    EVENT_NAME_TO_CODE, required_seed_count, _mean,
)
from .validation_artifacts import (  # noqa: F401  (split out; every name stays importable here)
    ARTIFACT_CREATION_RATE_MIN, ARTIFACT_CREATION_RATE_TOLERANCE_MIN, ARTIFACT_CREATION_RATE_MAX,
    ARTIFACT_TEMPLATE_STARTING_CIVS, ARTIFACT_LOSS_RATE_MIN, ARTIFACT_LOSS_RATE_MAX, check_artifact_lifecycle,
    run_artifact_oracle,
)
from .validation_trajectories import (  # noqa: F401  (split out; every name stays importable here)
    ERA_INFLECTION_SEED_FRACTION_MIN, ERA_SILENT_COLLAPSE_SEED_FRACTION_MAX, ERA_COLLAPSE_DROP_FRACTION,
    ERA_COLLAPSE_SMOOTHING_WINDOW, ERA_SIGNAL_SLACK_TURNS, _collapse_nearby_points, _trajectory_metric_series,
    _trajectory_composite_series, _smoothed_series, _significant_slope_pattern, detect_inflection_points,
    _legacy_classify_civ_arc, _classify_series_by_thirds, _has_material_rags_growth,
    _classify_material_arc_when_prestige_masks_growth, _classify_rags_candidate, classify_civ_arc,
    detect_collapse_episodes, run_era_oracle, run_arc_oracle,
)
from .validation_regression import (  # noqa: F401  (split out; every name stays importable here)
    REGRESSION_SATISFACTION_MEAN_MIN, REGRESSION_SATISFACTION_MEAN_CALIBRATED_MIN, REGRESSION_SATISFACTION_MEAN_MAX,
    REGRESSION_LATEST_SATISFACTION_WINDOW_TURNS, REGRESSION_MIGRATION_RATE_MIN,
    REGRESSION_MIGRATION_RATE_CALIBRATED_MIN, REGRESSION_MIGRATION_RATE_MAX, REGRESSION_REBELLION_RATE_MIN,
    REGRESSION_REBELLION_RATE_MAX, REGRESSION_OCCUPATION_SHARE_MAX, REGRESSION_OCCUPATION_VIOLATION_FRACTION_MAX,
    REGRESSION_LATEST_OCCUPATION_VIOLATION_AGENT_FRACTION_MAX, REGRESSION_OCCUPATION_EVIDENCE_RUN_MIN,
    _rounded_delta, _floor_diagnostic, _agent_count_by_turn, _final_ginis_from_validation_summary,
    _population_count, _aggregate_turn_key, _aggregate_turns_descending, _final_living_population,
    _late_satisfaction_window, run_regression_summary,
)

SCRUB_KEYS = {"generated_at"}
BUNDLE_FILENAME = "chronicle_bundle.json"
# Agent event codes any oracle counts (needs, cohort, regression).
_ORACLE_COUNTED_EVENT_CODES = frozenset(
    EVENT_NAME_TO_CODE[name] for name in ("migration", "rebellion", "occupation_switch")
)

# Needs oracle (M53 oracle 2). A rebellion raises the rebel's autonomy by 0.10
# (chronicler-agents/src/tick.rs, rebellion apply step), so a high autonomy
# reading often marks a past rebel, and past rebels rebel again. The
# autonomy -> rebellion pairing therefore pairs only agents that have not
# rebelled by the snapshot turn (inclusive: sidecars are written after that
# turn's agent tick). No finite window suffices: one rebellion still reads
# +0.035 after 20-29 turns, two or more +0.07 to +0.11 after 20-34, and where
# autonomy is not restored (displaced, or foreign rule plus persecution) the
# shift does not decay.
# See docs/integration/needs-oracle-autonomy.md. False restores the old pairing.
NEEDS_AUTONOMY_EXCLUDES_PRIOR_REBELS = True

# Needs oracle method 2 (docs/integration/needs-oracle-power.md). Pairs are
# matched as before (same civ affinity, region and occupation; boldness,
# ambition and loyalty trait within 0.1; prior rebels left out of the autonomy
# pairing), at every snapshot whose 20-turn outcome window fits the run, for
# every pairing below. A pair is concordant when its lower-need agent has more
# of the paired event than its partner, discordant when fewer. The verdict
# pools all pairs of all seeds, with the seed as the unit of replication.
# Method 1 kept one best snapshot and pairing per seed (``run_needs_oracle_best_of``).
#
# Method 3 (docs/integration/needs-followups.md) keeps method 2 and adds a
# required binding component. The need-driven terms act only below a need's
# behavioural threshold (needs.rs), and any positive push opens the decision
# gate, so the contrast that isolates them is a pair whose lower-need agent is
# below the threshold and whose partner is at or above it: the term pushes one
# and not the other. Binding pairs are matched like method 2's pairs (cell,
# traits, prior rebels) among such agents, with a need gap above
# NEEDS_BINDING_DIVERGENCE, and need their own seed-clustered lower bound
# above zero. Above the threshold the terms do nothing, and an association
# there comes from other channels (conditions, age, wealth).
#
# Method 4 (docs/integration/validation-integrity.md) keeps method 3 and
# counts outcomes strictly after the snapshot: turns t+1 .. t+window. A
# turn-t snapshot is written after turn t's agent tick (agent_bridge), whose
# decisions already moved the agent (region), changed its occupation or
# raised its autonomy (rebellion); the matching cell is observed after them,
# so a turn-t action is not an outcome of the turn-t reading. A snapshot is
# eligible when turn t + window was simulated (t + window < total turns:
# a run of N turns ticks turns 0 .. N-1). The autonomy pairing's prior-rebel
# rule (rebelled on or before t) already treats a turn-t rebellion this way.
# Methods 2 and 3 counted turns t .. t+window-1.
#
# Method 5 (docs/integration/procedural-drift.md) keeps method 4 and counts a
# pair's outcomes only over the turns both agents were alive: the window ends
# at the pair's first death (that turn's own events count; a dead agent has
# none after it). Method 4 counted each agent over the whole window, so the
# agent that died had less time to act and a pair was decided by who died: in
# a world where needs say nothing about behaviour but the higher-need agent
# dies more often (an older agent), method 4 passes the full profile. On the
# procedural full gate 52% of method 4's informative pairs had a death in
# the window. Deaths come from the agent event stream (``run["deaths"]``); a
# run without that key is scored as if no agent died.
#
# Method 6 (docs/integration/oracle-followups.md) keeps method 5's pairs,
# criteria and verdict and also reports the spiritual -> migration pairing
# (NEEDS_INFORMATIONAL_PAIRINGS): its pairs and binding pairs, matched and
# counted as the five paired needs' are, with their own seed-clustered
# bounds. It never decides the verdict and is not in the pooled totals.
# Matching on age was measured and not adopted (the same document).
#
# Method 7 (docs/integration/ablation-oracles.md) keeps method 6's result as
# its observational component and adds a causal one: every seed is forked at
# turns T from the plain run's exact checkpoint with the need terms of the
# native decision switched off from tick T+1 (``chronicler.ablation_arms``,
# arm ``needs``); agents below a need's threshold at T are followed over
# ticks T+1 .. T+20 in both arms, and the need terms must raise each
# pairing's event by at least 10% with a seed-clustered lower bound above no
# effect (``chronicler.validation_ablation``). The observational component
# decides and the ablation is reported as causal evidence, not yet required
# (``validation_gate.CAUSAL_ORACLES_REQUIRED``); with causal oracles required
# the profile decides (``validation_gate.NEEDS_COMPONENTS_REQUIRED``): the
# ablation in the full profile, the observational one in the subset.
#
# Method 8 (docs/integration/community-anchoring.md, section 6) is method 7
# on arms of fork design 2 (``chronicler.ablation_arms``): procedural worlds
# fork every 20 turns from turn 100 instead of every 100, template worlds as
# before. Estimator, cohorts, window and criteria are method 7's. Arms of
# design 1 are scored by method 7 (``run_needs_oracle(...,
# method_version=7)``, chosen by ``run_oracles`` from the arms' manifest).
NEEDS_ORACLE_METHOD_VERSION = 8
NEEDS_ABLATION_DESIGN1_METHOD_VERSION = 7
NEEDS_INFORMATIONAL_METHOD_VERSION = 6
NEEDS_DEATH_CENSORED_METHOD_VERSION = 5
NEEDS_POST_SNAPSHOT_METHOD_VERSION = 4
NEEDS_BINDING_METHOD_VERSION = 3
NEEDS_POOLED_METHOD_VERSION = 2
NEEDS_METHOD_VERSIONS = (
    NEEDS_POOLED_METHOD_VERSION, NEEDS_BINDING_METHOD_VERSION,
    NEEDS_POST_SNAPSHOT_METHOD_VERSION, NEEDS_DEATH_CENSORED_METHOD_VERSION,
    NEEDS_INFORMATIONAL_METHOD_VERSION, NEEDS_ABLATION_DESIGN1_METHOD_VERSION, NEEDS_ORACLE_METHOD_VERSION,
)
# The ablation methods and the fork design of the arms each reads.
NEEDS_ABLATION_METHOD_DESIGNS = {NEEDS_ABLATION_DESIGN1_METHOD_VERSION: 1, NEEDS_ORACLE_METHOD_VERSION: 2}
NEEDS_PAIRINGS = (
    ("autonomy", EVENT_NAME_TO_CODE["rebellion"]),
    ("social", EVENT_NAME_TO_CODE["migration"]),
    ("purpose", EVENT_NAME_TO_CODE["occupation_switch"]),
    ("material", EVENT_NAME_TO_CODE["migration"]),
    ("safety", EVENT_NAME_TO_CODE["migration"]),
)
# Pairings reported beside the verdict, never deciding it (method 6). A
# spiritual deficit below its threshold pushes migration (needs.rs,
# SPIRITUAL_THRESHOLD 0.30 and SPIRITUAL_WEIGHT 0.4 in agent.rs). Conversion
# does not read the need (conversion_tick.rs reads satisfaction), and sect
# recruitment, which does (movements.rs), is not in the agent event stream.
NEEDS_INFORMATIONAL_PAIRINGS = (
    ("spiritual", EVENT_NAME_TO_CODE["migration"]),
)
NEEDS_INFORMATIONAL_THRESHOLDS = {"spiritual": 0.30}
NEEDS_OUTCOME_WINDOW_TURNS = 20
NEEDS_PERSONALITY_TOLERANCE = 0.1
# The need gap a pair must exceed. Method 1 used 0.2: within a matched cell a
# need's spread is 0.03-0.10 (median standard deviation), so a 0.2 gap left
# about three informative pairs per 200-turn template world. The gap sets the
# contrast, not a confound control; the matching above does that.
NEEDS_NEED_DIVERGENCE = 0.1
NEEDS_LEGACY_NEED_DIVERGENCE = 0.2
# PASS needs both: the one-sided 95% lower bound of the pooled net concordance
# above zero (seed-clustered standard error, Student t with one degree of
# freedom fewer than the seeds with informative pairs), and at least 60% of
# analyzed seeds with more concordant than discordant pairs (the M53 seed
# fraction, now on each seed's pooled pairs instead of its best candidate).
NEEDS_CONFIDENCE = 0.95
NEEDS_SEED_FRACTION_MIN = 0.60
# Behavioural thresholds of the paired needs: chronicler-agents/src/agent.rs
# (SAFETY_THRESHOLD and the rest; tests/test_validate.py checks the mirror).
NEEDS_BEHAVIOUR_THRESHOLDS = {
    "autonomy": 0.35,
    "social": 0.35,
    "purpose": 0.35,
    "material": 0.30,
    "safety": 0.30,
}
# The need gap of a binding pair. The threshold sets its contrast; the gap,
# half of method 2's, leaves out pairs whose two needs sit at the threshold
# and swap sides within a few turns.
NEEDS_BINDING_DIVERGENCE = 0.05

# M53 oracle 4 (cohort distinctiveness). Method 1 (results without a
# ``method_version``) counted each snapshot's migrations and rebellions on
# turns t .. t+19, its window starting at the graph and needs snapshot turn.
# Those sidecars are written after turn t's agent tick (agent_bridge), as the
# needs oracle's are: the tick's decisions have already moved the migrants
# (the matched region), raised the rebels' autonomy and written the turn's
# memories, whose (event type, turn, valence) signatures form the
# communities. Method 2 (docs/integration/consistency-followups.md) counts
# turns t+1 .. t+20 (eligible when t + 20 < total turns: a run of N turns
# ticks turns 0 .. N-1); communities, matching, criteria and thresholds are
# method 1's. ``run_cohort_oracle(..., method_version=1)`` re-scores method 1.
#
# Method 3 (docs/integration/oracle-followups.md) keeps method 2 and compares
# each community member with its matched control over the turns both were
# alive: the pair's window ends at the first death of either (that turn's own
# events count; a dead agent has none after it), as the needs oracle's method
# 5 does. Method 2 counted every member over its own lifetime in the window
# against the controls over theirs, so the side that died more had less time
# to act: members die more often than their controls (32% against 27% of
# member and control rows over a window on the template subset), which reads
# as members migrating and rebelling less. A member without a matched control
# has no partner to share its turns with and is left out (method 2 counted it
# against the other members' controls). Deaths come from the agent event
# stream (``run["deaths"]``); a run without that key is scored as if no agent
# died.
#
# Method 4 (docs/integration/ablation-oracles.md) keeps method 3's result as
# its observational component, which cannot fail (best of every snapshot,
# either behaviour, the larger effect: every synthetic world passed, reversed
# ones included; ``validation_gate.COHORT_OBSERVATIONAL_NOTE``), and adds an
# ablation: every seed is forked at turns T with the relationship part of
# migrants' roots switched off from tick T+1 (arm ``kin_roots``), and the
# community members at T must migrate at least 15% less over ticks
# T+1 .. T+20 with the term than without it, with a seed-clustered upper
# bound below no effect. Rebellion is reported, not deciding: no community
# term enters the rebel decision. Until causal oracles are required
# (``validation_gate.CAUSAL_ORACLES_REQUIRED``) method 3's verdict decides and
# the ablation is reported. ``method_version=3`` re-scores method 3.
#
# Method 5 (docs/integration/community-anchoring.md) is method 4 on arms of
# fork design 2 (procedural worlds fork every 20 turns) with a reported
# community component: the community anchor's arm (``community_anchor``,
# batches run with --community-anchoring; ``NOT_RUN`` otherwise), scored on
# the same members by method 4's criterion and by the anchor's own exposure
# (``validation_ablation.community_ablation_result``). It never decides.
# Arms of design 1 are scored by method 4.
#
# Method 6 (docs/integration/spec-communities.md) is method 5 with the
# communities of community oracle method 2 (M53 oracle 1 as specified:
# friend, co-religionist and kin edges weighted by sentiment within a
# region, the native kin code; ``validation_communities``) as the member
# cohort of every component: the observational one (method 3's estimator,
# matching and criteria, with a ``matching`` summary), the kin-roots
# ablation, its placebo and the community anchor's component. Method 5
# (``method_version=5``) re-scores the communities of method 1.
COHORT_ORACLE_METHOD_VERSION = 6
COHORT_LEGACY_COMMUNITY_METHOD_VERSION = 5
COHORT_ABLATION_DESIGN1_METHOD_VERSION = 4
COHORT_DEATH_CENSORED_METHOD_VERSION = 3
COHORT_POST_SNAPSHOT_METHOD_VERSION = 2
COHORT_LEGACY_METHOD_VERSION = 1
COHORT_METHOD_VERSIONS = (
    COHORT_LEGACY_METHOD_VERSION, COHORT_POST_SNAPSHOT_METHOD_VERSION, COHORT_DEATH_CENSORED_METHOD_VERSION,
    COHORT_ABLATION_DESIGN1_METHOD_VERSION, COHORT_LEGACY_COMMUNITY_METHOD_VERSION, COHORT_ORACLE_METHOD_VERSION,
)
COHORT_ABLATION_METHOD_DESIGNS = {
    COHORT_ABLATION_DESIGN1_METHOD_VERSION: 1, COHORT_LEGACY_COMMUNITY_METHOD_VERSION: 2,
    COHORT_ORACLE_METHOD_VERSION: 2,
}
# The cohort methods whose members are community method 2's communities.
COHORT_SPEC_COMMUNITY_METHODS = frozenset({COHORT_ORACLE_METHOD_VERSION})


def _check_arm_designs(oracle: str, method_version: int, designs: dict[int, int], *arms: dict | None) -> None:
    """Refuse arms of another fork design than the ablation method reads."""
    want = designs[method_version]
    for arm in arms:
        if arm is None:
            continue
        got = arm.get("design", 1)
        if got != want:
            raise ValueError(
                f"{oracle} oracle method {method_version} reads arms of fork design {want}, not {got}; "
                f"score them with method " + str(max(v for v, d in designs.items() if d == got)))
COHORT_OUTCOME_WINDOW_TURNS = 20

# Recorded crises that mark a collapse in a civ's history: what takes its
# people (hunger, disease, war, flight, disaster) or records its breakdown
# (unrest, the fall of the state). Fiscal, cultural and routine events do not.
ERA_CRISIS_EVENT_GROUPS = {
    "hunger": ("famine", "dearth", "supply_shock", "drought", "drought_intensification", "locust_swarm",
               "soil_exhaustion", "fishery_collapse", "demographic_crisis"),
    "disease": ("plague", "epidemic", "epidemic_arrival", "pandemic", "pandemic_spread"),
    "war": ("war", "war_declared", "battle", "siege_begun", "occupation", "army_destroyed",
            "scorched_earth", "capital_loss", "civ_conquered", "annexation"),
    "flight": ("migration", "mass_migration", "notable_migration", "Mass Migration",
               "Persecution", "brain_drain"),
    "disaster": ("earthquake", "flood", "wildfire", "sandstorm", "supervolcano", "mine_collapse"),
    "unrest": ("rebellion", "local_rebellion", "revolt", "civil_war", "secession", "coup",
               "psi_crisis", "vassal_rebellion", "loyalty_cascade", "succession_crisis",
               "legitimacy_crisis"),
    "fall": ("collapse", "twilight", "twilight_absorption", "union_annexation", "vassalization"),
}
ERA_CRISIS_EVENT_TYPES = frozenset(
    event_type for group in ERA_CRISIS_EVENT_GROUPS.values() for event_type in group
)


class ValidationRequestError(ValueError):
    """Invalid validation request or batch path."""


class ValidationDependencyError(RuntimeError):
    """Required optional dependency is missing for a requested oracle."""


def _has_pyarrow() -> bool:
    try:
        import pyarrow.ipc  # noqa: F401
    except ImportError:
        return False
    return True


def _iter_seed_dirs(batch_dir: Path) -> list[Path]:
    if batch_dir.is_file():
        return [batch_dir.parent]
    return sorted(path.parent for path in batch_dir.rglob(BUNDLE_FILENAME))


def _requires_pyarrow_for_selected_inputs(batch_dir: Path, selected_oracles: set[str] | None) -> str | None:
    if selected_oracles is None or _has_pyarrow():
        return None
    selected = set(selected_oracles)
    seed_dirs = _iter_seed_dirs(batch_dir)
    if "regression" in selected and any((seed_dir / "agent_events.arrow").exists() for seed_dir in seed_dirs):
        return "regression oracle requires pyarrow"
    if "needs" in selected and any(
        (seed_dir / "validation_needs.arrow").exists()
        and (seed_dir / "agent_events.arrow").exists()
        for seed_dir in seed_dirs
    ):
        return "needs oracle requires pyarrow"
    if "cohort" in selected and any(
        (seed_dir / "validation_relationships.arrow").exists()
        and (seed_dir / "validation_needs.arrow").exists()
        and (seed_dir / "agent_events.arrow").exists()
        for seed_dir in seed_dirs
    ):
        return "cohort oracle requires pyarrow"
    return None

def scrubbed_equal(a: dict, b: dict) -> bool:
    """Compare two bundles ignoring transient metadata fields."""
    def _scrub(d):
        if isinstance(d, dict):
            return {k: _scrub(v) for k, v in d.items() if k not in SCRUB_KEYS}
        if isinstance(d, list):
            return [_scrub(x) for x in d]
        return d
    return _scrub(a) == _scrub(b)


def _bundle_paths(batch_dir: Path) -> list[Path]:
    if not batch_dir.exists():
        raise ValidationRequestError(f"batch path does not exist: {batch_dir}")
    if batch_dir.is_file():
        return [batch_dir]
    return sorted(batch_dir.rglob(BUNDLE_FILENAME))


def _load_bundle(bundle_path: Path, *, _strict: bool = False) -> dict:
    """Load a bundle with every civ row in its history.

    Version-6 files are decoded (``bundle_codec``). Version-5 bundles leave
    dead civilizations out of the history snapshots; the oracles measure over
    every civ row (dead civs' series included), so the omitted rows are
    restored exactly (``snapshot_pruning.restore_bundle`` does both).
    """
    try:
        text = bundle_path.read_text(encoding="utf-8")
        return restore_bundle(strict_json_loads(text) if _strict else json.loads(text))
    except Exception as exc:
        raise RuntimeError(f"Failed to load bundle: {bundle_path}") from exc


def iter_bundles(batch_dir: Path, *, _admission=None):
    """Yield ``(path, bundle)`` one at a time, in ``load_bundles`` order.

    A full-profile batch (200 living 500-turn worlds, ~18 MB of JSON each)
    does not fit in memory when every bundle is parsed at once.
    """
    paths = _admission.paths if _admission is not None else _bundle_paths(batch_dir)
    for bundle_path in paths:
        try:
            bundle = _load_bundle(bundle_path, _strict=_admission is not None and _admission.has_manifest)
        except RuntimeError as exc:
            if _admission is not None and _admission.has_manifest:
                raise ValidationRequestError(str(exc)) from exc
            raise
        if _admission is not None:
            _admission.observe(bundle_path, bundle)
        yield bundle_path, bundle


def load_bundles(batch_dir: Path) -> list[tuple[Path, dict]]:
    """Load chronicle bundles from a batch directory or bundle path."""
    return list(iter_bundles(batch_dir))


LEGACY_BATCH_FLAG = "--legacy-batch"


class _BatchAdmission:
    """Frozen expectations plus observations; preflight alone verifies nothing."""

    def __init__(self, batch_dir: Path, paths: list[Path], manifest: dict | None):
        self.batch_dir = batch_dir
        self.paths = tuple(paths)
        self._manifest = manifest
        self._manifest_sha256 = file_sha256(batch_dir / MANIFEST_FILENAME) if manifest is not None else None
        self._expected = MappingProxyType({
            run["bundle"]: MappingProxyType({key: run[key] for key in ("seed", "dir", "total_turns")})
            for run in manifest["runs"]
        } if manifest is not None else {})
        self._observed: set[str] = set()

    @property
    def has_manifest(self) -> bool:
        return self._manifest is not None

    def observe(self, path: Path, bundle: dict) -> None:
        if self._manifest is None:
            return
        relative = path.relative_to(self.batch_dir).as_posix()
        expected = self._expected.get(relative)
        if expected is None:
            raise ValidationRequestError(f"bundle is not in the manifest: {relative}")
        problems = _run_fact_problems(expected, bundle)
        if problems:
            raise ValidationRequestError("batch bundle does not match its manifest: " + "; ".join(problems))
        self._observed.add(relative)

    def finish(self) -> dict:
        if self._manifest is None:
            return {"status": "unchecked", "reason": f"no {MANIFEST_FILENAME} ({LEGACY_BATCH_FLAG})"}
        if self._expected.keys() - self._observed:
            # Empty selections or a substituted oracle runner still cannot
            # publish verified facts without observing every payload.
            for _path, _bundle in iter_bundles(self.batch_dir, _admission=self):
                pass
        return batch_cohort(self._manifest, self._manifest_sha256)


def _prepare_batch_admission(batch_dir: Path, *, legacy_batch: bool = False) -> _BatchAdmission:
    """Check inventory/hashes before readers; defer facts to their decode."""
    batch_dir = Path(batch_dir)
    if not batch_dir.exists():
        raise ValidationRequestError(f"batch path does not exist: {batch_dir}")
    try:
        manifest = load_batch_manifest(batch_dir) if batch_dir.is_dir() else None
    except BatchManifestError as exc:
        raise ValidationRequestError(str(exc)) from exc
    if manifest is None:
        if legacy_batch:
            return _BatchAdmission(batch_dir, _bundle_paths(batch_dir), None)
        raise ValidationRequestError(
            f"no {MANIFEST_FILENAME} in {batch_dir}: a batch written by chronicler.batch records its "
            f"expected runs there. To validate a directory written before manifests (or a single bundle) "
            f"without checking which runs it holds, pass {LEGACY_BATCH_FLAG}."
        )
    paths = _bundle_paths(batch_dir)
    problems = _verify_batch_manifest_inputs(batch_dir, manifest, paths)
    if problems:
        raise ValidationRequestError(f"batch directory {batch_dir} does not match its manifest: " + "; ".join(problems))
    return _BatchAdmission(batch_dir, paths, manifest)


def check_batch_manifest(batch_dir: Path, *, legacy_batch: bool = False) -> dict:
    """The report's ``batch_manifest`` entry for ``batch_dir``, after
    checking the directory against its ``batch_manifest.json``.

    The batch must be complete and its bundles exactly the manifest's runs,
    each run as long as the requested turns, every validation input
    unchanged (``batch_manifest.verify_batch_manifest``); otherwise
    ``ValidationRequestError``. A directory without a manifest (written
    before manifests, or a single bundle) is refused unless
    ``legacy_batch``; its entry is then ``unchecked``. A manifest that is
    present is always checked.
    """
    return _prepare_batch_admission(Path(batch_dir), legacy_batch=legacy_batch).finish()


# Bundle fields the seed-run oracles read: metadata, these per-snapshot
# civ_stats fields, and the terminal world_state turn/agent_mode/regions/
# artifacts. (World population and civ trajectories are derived from the full
# bundle before it is narrowed.)
_ORACLE_CIV_STAT_KEYS = ("population", "treasury", "stability", "regions", "prestige", "gini")
_ORACLE_WORLD_STATE_KEYS = ("turn", "agent_mode", "regions", "artifacts")


def _oracle_civ_stats_view(civ_stats):
    if not isinstance(civ_stats, dict):
        return civ_stats
    return {
        name: ({key: stats[key] for key in _ORACLE_CIV_STAT_KEYS if key in stats}
               if isinstance(stats, dict) else stats)
        for name, stats in civ_stats.items()
    }


def _oracle_bundle_view(bundle: dict) -> dict:
    """Keep only the bundle fields that seed-run oracles consume."""
    view: dict = {}
    if "metadata" in bundle:
        view["metadata"] = bundle["metadata"]
    if "history" in bundle:
        history = bundle["history"]
        view["history"] = [
            {"civ_stats": _oracle_civ_stats_view(snapshot["civ_stats"])}
            if isinstance(snapshot, dict) and "civ_stats" in snapshot
            else ({} if isinstance(snapshot, dict) else snapshot)
            for snapshot in history
        ] if isinstance(history, list) else history
    if "world_state" in bundle:
        world = bundle["world_state"]
        view["world_state"] = (
            {key: world[key] for key in _ORACLE_WORLD_STATE_KEYS if key in world}
            if isinstance(world, dict) else world
        )
    return view


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot_turns(sidecar_dir: Path, prefix: str) -> list[int]:
    turns = []
    for path in sorted(sidecar_dir.glob(f"{prefix}_turn_*.json")):
        try:
            turns.append(int(path.stem.rsplit("_", 1)[-1]))
        except ValueError:
            continue
    return turns


def _choose_snapshot_turn(available_turns: list[int], target_turn: int) -> int | None:
    if not available_turns:
        return None
    return min(available_turns, key=lambda turn: (abs(turn - target_turn), turn))


def _load_graph_snapshot(sidecar_dir: Path, turn: int | None) -> dict | None:
    if turn is None:
        return None
    path = sidecar_dir / f"graph_turn_{turn:03d}.json"
    if not path.exists():
        return None
    raw = _read_json(path)
    return {
        "turn": raw["turn"],
        "edges": [tuple(edge) for edge in raw.get("edges", [])],
        "memory_signatures": {
            int(agent_id): [tuple(sig) for sig in sigs]
            for agent_id, sigs in raw.get("memory_signatures", {}).items()
        },
    }


def _load_needs_snapshot(sidecar_dir: Path, turn: int | None) -> dict | None:
    if turn is None:
        return None
    path = sidecar_dir / f"needs_turn_{turn:03d}.json"
    if not path.exists():
        return None
    return _read_json(path)


@dataclass(frozen=True, slots=True)
class _TurnRows:
    """Immutable row selection for one loaded table, separate from its schema.

    Normal sidecars have monotonic turns: each turn is one range, so index
    space scales with sampled turns. Legacy shuffled rows retain their source
    order in compact, read-only uint64 index buffers. Nothing is keyed by a
    file path or object id outside the lifetime of the loaded columns.
    """

    rows: Mapping
    turns: tuple[int, ...]


def _build_turn_rows(columns: dict) -> _TurnRows:
    values = columns.get("turn")
    if not values:
        return _TurnRows(MappingProxyType({}), ())
    spans = {}
    previous = None
    start = 0
    monotonic = True
    for row, value in enumerate(values):
        turn = int(value)
        if previous is not None and turn != previous:
            spans[previous] = range(start, row)
            start = row
            if turn < previous:
                monotonic = False
        previous = turn
    spans[previous] = range(start, len(values))
    if monotonic:
        return _TurnRows(MappingProxyType(spans), tuple(spans))
    # A turn can occur in several disjoint runs. Never sort the source table:
    # graph edge order, duplicate rows and first-occurrence ties are observable.
    indexes = defaultdict(lambda: array("Q"))
    for row, value in enumerate(values):
        indexes[int(value)].append(row)
    frozen = {turn: memoryview(rows).toreadonly() for turn, rows in indexes.items()}
    return _TurnRows(MappingProxyType(frozen), tuple(sorted(frozen)))


class _IndexedColumns(dict):
    """Reader-owned columns plus their private immutable row index.

    Loaded columns are read-only inputs throughout validation. The index is
    metadata, never a synthetic column. Plain caller-owned dictionaries are
    not wrapped or cached by the selection helpers, so later edits to those
    dictionaries are always observed. Every file read creates a fresh owner.
    """

    __slots__ = ("_turn_rows",)

    def __init__(self, columns: dict):
        super().__init__(columns)
        self._turn_rows = _build_turn_rows(self)

    def __reduce__(self):
        # Copy/pickle the data, not mappingproxy/memoryview metadata. A restored
        # owner indexes its own arrays rather than retaining another's index.
        return type(self), (dict(self),)


def _rows_for_turn(columns: dict | None, turn: int):
    if not columns or not columns.get("turn"):
        return ()
    if isinstance(columns, _IndexedColumns):
        return columns._turn_rows.rows.get(turn, ())
    # Caller dictionaries may be edited between calls. Keep the old one-shot
    # predicate selection, without caching or building an unused full index.
    return [row for row, value in enumerate(columns["turn"]) if int(value) == turn]


def _read_arrow_columns(path: Path) -> dict | None:
    if not path.exists():
        return None
    if not _has_pyarrow():
        return None
    import pyarrow.ipc as ipc
    table = ipc.open_file(path).read_all()
    return _IndexedColumns({name: _compact_column(table.column(name)) for name in table.column_names})


def _compact_column(column):
    """Python values of an arrow column, packed when that is lossless.

    Null-free integer and float columns become ``array('q')``/``array('d')``:
    indexing and iteration yield the same Python ints and floats as
    ``to_pylist()`` at about a quarter of the memory, which keeps a 200-seed
    full-profile batch within memory. Anything else stays a list.
    """
    import pyarrow as pa
    values = column.to_pylist()
    if column.null_count == 0:
        try:
            if pa.types.is_integer(column.type):
                return array("q", values)
            if pa.types.is_floating(column.type):
                return array("d", values)
        except OverflowError:
            return values
    return values


def _load_canonical_graph_snapshot(seed_dir: Path, target_turn: int) -> dict | None:
    rel_cols = _read_arrow_columns(seed_dir / "validation_relationships.arrow")
    mem_cols = _read_arrow_columns(seed_dir / "validation_memory_signatures.arrow")
    if rel_cols is None and mem_cols is None:
        return None

    available_turns: set[int] = set()
    if rel_cols and rel_cols.get("turn"):
        available_turns.update(_available_turns_from_columns(rel_cols))
    if mem_cols and mem_cols.get("turn"):
        available_turns.update(_available_turns_from_columns(mem_cols))
    chosen_turn = _choose_snapshot_turn(sorted(available_turns), target_turn)
    if chosen_turn is None:
        return None

    return _graph_snapshot_from_columns(rel_cols, mem_cols, chosen_turn)


def _load_canonical_needs_snapshot(seed_dir: Path, target_turn: int) -> dict | None:
    cols = _read_arrow_columns(seed_dir / "validation_needs.arrow")
    if not cols or not cols.get("turn"):
        return None
    chosen_turn = _choose_snapshot_turn(_available_turns_from_columns(cols), target_turn)
    if chosen_turn is None:
        return None

    return _needs_snapshot_from_columns(cols, chosen_turn)


def _available_turns_from_columns(columns: dict | None) -> list[int]:
    if not columns or not columns.get("turn"):
        return []
    if isinstance(columns, _IndexedColumns):
        return list(columns._turn_rows.turns)
    return sorted({int(turn) for turn in columns["turn"]})


def _sample_turns(turns: list[int], min_turn: int = 100) -> list[int]:
    steady_state = [turn for turn in turns if turn >= min_turn]
    return steady_state or turns


def _columns_for_turn(columns: dict | None, turn: int) -> dict | None:
    if not columns or not columns.get("turn"):
        return None
    indexes = _rows_for_turn(columns, turn)
    if not indexes:
        return None
    return {
        name: [values[idx] for idx in indexes]
        for name, values in columns.items()
        if name != "turn"
    }


def _graph_snapshot_from_columns(
    relationship_columns: dict | None,
    memory_columns: dict | None,
    turn: int,
) -> dict | None:
    edges: list[tuple[int, int, int, int]] = []
    if relationship_columns and relationship_columns.get("turn"):
        for idx in _rows_for_turn(relationship_columns, turn):
            edges.append((
                int(relationship_columns["agent_id"][idx]),
                int(relationship_columns["target_id"][idx]),
                int(relationship_columns["bond_type"][idx]),
                int(relationship_columns["sentiment"][idx]),
            ))

    memory_signatures: dict[int, list[tuple[int, int, int]]] = {}
    if memory_columns and memory_columns.get("turn"):
        for idx in _rows_for_turn(memory_columns, turn):
            agent_id = int(memory_columns["agent_id"][idx])
            memory_signatures.setdefault(agent_id, []).append((
                int(memory_columns["event_type"][idx]),
                int(memory_columns["memory_turn"][idx]),
                int(memory_columns["valence_sign"][idx]),
            ))

    if not edges and not memory_signatures:
        return None
    return {
        "turn": turn,
        "edges": edges,
        "memory_signatures": memory_signatures,
    }


def _needs_snapshot_from_columns(columns: dict | None, turn: int) -> dict | None:
    filtered = _columns_for_turn(columns, turn)
    if filtered is None:
        return None
    return {"turn": turn, "columns": filtered}


def _load_validation_summary(seed_dir: Path) -> dict | None:
    path = seed_dir / "validation_summary.json"
    if not path.exists():
        return None
    return _read_json(path)


def _load_validation_community_summary(seed_dir: Path) -> dict | None:
    path = seed_dir / "validation_community_summary.json"
    if not path.exists():
        return None
    return _read_json(path)


def _load_agent_deaths(seed_dir: Path) -> dict[int, int]:
    """Each agent's death turn, from the agent event stream (needs oracle
    method 5 and cohort oracle method 3 count a pair only while both agents
    live). Empty without the stream or pyarrow."""
    path = seed_dir / "agent_events.arrow"
    if not path.exists() or not _has_pyarrow():
        return {}
    import pyarrow.compute as pc
    import pyarrow.ipc as ipc

    table = ipc.open_file(path).read_all()
    return _agent_deaths_from_table(table, pc)


def _agent_deaths_from_table(table, pc) -> dict[int, int]:
    if "event_type" not in table.column_names:
        return {}
    dead = table.filter(pc.equal(table.column("event_type"), "death"))
    deaths: dict[int, int] = {}
    for agent_id, turn in zip(dead.column("agent_id").to_pylist(), dead.column("turn").to_pylist()):
        agent_id, turn = int(agent_id), int(turn)
        if agent_id not in deaths or turn < deaths[agent_id]:
            deaths[agent_id] = turn
    return deaths


def _load_agent_events(seed_dir: Path) -> list[dict]:
    path = seed_dir / "agent_events.arrow"
    if not path.exists():
        return []
    if not _has_pyarrow():
        return []
    import pyarrow.ipc as ipc

    table = ipc.open_file(path).read_all()
    return _agent_events_from_table(table)


def _agent_events_from_table(table) -> list[dict]:
    data = table.to_pydict()
    events: list[dict] = []
    first_uncounted: dict | None = None
    event_names = data.get("event_type", [])
    for idx, event_name in enumerate(event_names):
        mapped_type = EVENT_NAME_TO_CODE.get(event_name)
        if mapped_type is None:
            continue
        if mapped_type not in _ORACLE_COUNTED_EVENT_CODES:
            # Oracles only count migration/rebellion/occupation_switch; drop the
            # rest (births, deaths, dissolutions are most of a living batch),
            # keeping one so "has agent events" is unchanged.
            if first_uncounted is None:
                first_uncounted = {
                    "turn": data["turn"][idx],
                    "agent_id": data["agent_id"][idx],
                    "event_type": mapped_type,
                }
            continue
        events.append({
            "turn": data["turn"][idx],
            "agent_id": data["agent_id"][idx],
            "event_type": mapped_type,
        })
    if not events and first_uncounted is not None:
        events.append(first_uncounted)
    return events


def _load_agent_events_and_deaths(seed_dir: Path) -> tuple[list[dict], dict[int, int]]:
    """Derive both views from one seed-local table; retain no shared cache."""
    path = seed_dir / "agent_events.arrow"
    if not path.exists() or not _has_pyarrow():
        return [], {}
    import pyarrow.ipc as ipc

    table = ipc.open_file(path).read_all()
    events = _agent_events_from_table(table)
    import pyarrow.compute as pc

    return events, _agent_deaths_from_table(table, pc)


def _world_population_series(bundle: dict) -> list[int]:
    series: list[int] = []
    for snapshot in bundle.get("history", []):
        civ_stats = snapshot.get("civ_stats", {})
        series.append(sum(stats.get("population", 0) for stats in civ_stats.values()))
    return series


def _civ_trajectories(bundle: dict) -> list[dict]:
    histories: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {
            "turn": [],
            "population": [],
            "treasury": [],
            "stability": [],
            "territory": [],
            "prestige": [],
        }
    )
    for index, snapshot in enumerate(bundle.get("history", [])):
        turn = snapshot.get("turn", index)
        for civ_name, civ_stats in snapshot.get("civ_stats", {}).items():
            # A civ that appears late (a secession) starts its series late:
            # its own index is not a world turn, so the turn travels along.
            histories[civ_name]["turn"].append(turn if isinstance(turn, int) else index)
            histories[civ_name]["population"].append(civ_stats.get("population", 0))
            histories[civ_name]["treasury"].append(civ_stats.get("treasury", 0))
            histories[civ_name]["stability"].append(civ_stats.get("stability", 0))
            histories[civ_name]["territory"].append(len(civ_stats.get("regions", []) or []))
            histories[civ_name]["prestige"].append(civ_stats.get("prestige", 0))
    return [
        {"civ_name": civ_name, **signals}
        for civ_name, signals in histories.items()
    ]


def _civ_crisis_event_turns(bundle: dict) -> dict[str, list[int]]:
    """Turns of the recorded crises that name each civ (era oracle input).

    Only ``ERA_CRISIS_EVENT_TYPES`` count: events that take people from a
    civ (hunger, disease, war, flight, disaster) or record its breakdown
    (unrest, the fall of the state). A civ is named by an event's ``actors``
    or ``civs``.
    """
    turns: dict[str, set[int]] = defaultdict(set)
    for event in bundle.get("events_timeline", []) or []:
        if not isinstance(event, dict) or event.get("event_type") not in ERA_CRISIS_EVENT_TYPES:
            continue
        turn = event.get("turn")
        if not isinstance(turn, int) or isinstance(turn, bool):
            continue
        for name in list(event.get("actors") or []) + list(event.get("civs") or []):
            if isinstance(name, str):
                turns[name].add(turn)
    return {name: sorted(values) for name, values in turns.items()}


TEMPLATE_WORLD_GENERATOR = "template"


def _world_shape(bundle: dict) -> dict:
    """The world a seed ran on: its generator (``template`` without Geography
    2.0 metadata), its region count and its starting civilizations (the civ
    rows of the first history snapshot)."""
    world = bundle.get("world_state")
    world = world if isinstance(world, dict) else {}
    geography = world.get("geography")
    generator = (
        str(geography.get("generator") or "procedural")
        if isinstance(geography, dict) else TEMPLATE_WORLD_GENERATOR
    )
    regions = world.get("regions")
    history = bundle.get("history")
    first = history[0] if isinstance(history, list) and history and isinstance(history[0], dict) else {}
    civ_stats = first.get("civ_stats")
    return {
        "generator": generator,
        "regions": len(regions) if isinstance(regions, list) else None,
        "civs": len(civ_stats) if isinstance(civ_stats, dict) and civ_stats else None,
    }


def summarize_world_shapes(seed_runs: list[dict]) -> list[dict] | None:
    """Distinct world shapes of a batch with their seed counts, or None when
    every seed ran on the template world (template reports keep their bytes)."""
    counts: Counter[tuple[str, int | None, int | None]] = Counter()
    for run in seed_runs:
        shape = run.get("world")
        if not isinstance(shape, dict):
            continue
        counts[(str(shape.get("generator")), shape.get("regions"), shape.get("civs"))] += 1
    if not counts or all(generator == TEMPLATE_WORLD_GENERATOR for generator, _r, _c in counts):
        return None
    return [
        {"generator": generator, "regions": regions, "civs": civs, "seeds": seeds}
        for (generator, regions, civs), seeds in sorted(
            counts.items(), key=lambda item: (item[0][0], item[0][1] or 0, item[0][2] or 0)
        )
    ]


def load_seed_runs(batch_dir: Path, selected_oracles: set[str] | None = None, *, _admission=None) -> list[dict]:
    """Load exported bundle + sidecar data for each seed in a batch."""
    if not batch_dir.exists():
        raise ValidationRequestError(f"batch path does not exist: {batch_dir}")
    dependency_reason = _requires_pyarrow_for_selected_inputs(batch_dir, selected_oracles)
    if dependency_reason is not None:
        raise ValidationDependencyError(dependency_reason)
    runs: list[dict] = []
    for bundle_path, bundle in iter_bundles(batch_dir, _admission=_admission):
        seed_dir = bundle_path.parent
        sidecar_dir = seed_dir / "validation_summary"
        total_turns = int(bundle.get("metadata", {}).get("total_turns", 0) or 0)
        target_turn = max(10, int(round(total_turns / 20.0) * 10)) if total_turns else 10
        relationship_columns = _read_arrow_columns(seed_dir / "validation_relationships.arrow")
        memory_columns = _read_arrow_columns(seed_dir / "validation_memory_signatures.arrow")
        needs_columns = _read_arrow_columns(seed_dir / "validation_needs.arrow")
        graph_snapshot = None
        graph_turn = _choose_snapshot_turn(
            sorted(
                set(_available_turns_from_columns(relationship_columns))
                | set(_available_turns_from_columns(memory_columns))
            ),
            target_turn,
        )
        if graph_turn is not None:
            graph_snapshot = _graph_snapshot_from_columns(
                relationship_columns,
                memory_columns,
                graph_turn,
            )
        if graph_snapshot is None and sidecar_dir.exists():
            graph_turn = _choose_snapshot_turn(_snapshot_turns(sidecar_dir, "graph"), target_turn)
            graph_snapshot = _load_graph_snapshot(sidecar_dir, graph_turn)
        needs_snapshot = None
        needs_turn = _choose_snapshot_turn(
            _available_turns_from_columns(needs_columns),
            target_turn,
        )
        if needs_turn is not None:
            needs_snapshot = _needs_snapshot_from_columns(needs_columns, needs_turn)
        if needs_snapshot is None and sidecar_dir.exists():
            needs_turn = _choose_snapshot_turn(_snapshot_turns(sidecar_dir, "needs"), target_turn)
            needs_snapshot = _load_needs_snapshot(sidecar_dir, needs_turn)
        run = {
            "bundle_path": bundle_path,
            "seed_dir": seed_dir,
            "seed": bundle.get("metadata", {}).get("seed"),
            "world": _world_shape(bundle),
            "bundle": _oracle_bundle_view(bundle),
        }
        events, deaths = _load_agent_events_and_deaths(seed_dir)
        run.update({
            "events": events,
            "deaths": deaths,
            "relationship_columns": relationship_columns,
            "memory_columns": memory_columns,
            "needs_columns": needs_columns,
            "graph_snapshot": graph_snapshot,
            "needs_snapshot": needs_snapshot,
            "validation_summary": _load_validation_summary(seed_dir),
            "validation_community_summary": _load_validation_community_summary(seed_dir),
            "world_population": _world_population_series(bundle),
            "civ_trajectories": _civ_trajectories(bundle),
            "civ_crisis_event_turns": _civ_crisis_event_turns(bundle),
        })
        runs.append(run)
    return runs


def _total_turns(run: dict) -> int:
    return int(run.get("bundle", {}).get("metadata", {}).get("total_turns", 0) or 0)


def _iter_graph_snapshots(run: dict, min_turn: int = 100) -> list[dict]:
    relationship_columns = run.get("relationship_columns")
    memory_columns = run.get("memory_columns")
    if relationship_columns or memory_columns:
        turns = _sample_turns(
            sorted(
                set(_available_turns_from_columns(relationship_columns))
                | set(_available_turns_from_columns(memory_columns))
            ),
            min_turn=min_turn,
        )
        snapshots = []
        for turn in turns:
            snapshot = _graph_snapshot_from_columns(
                relationship_columns,
                memory_columns,
                turn,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
        if snapshots:
            return snapshots
    graph_snapshot = run.get("graph_snapshot")
    return [graph_snapshot] if graph_snapshot else []


def _iter_needs_snapshots(run: dict, min_turn: int = 100) -> list[dict]:
    needs_columns = run.get("needs_columns")
    if needs_columns:
        turns = _sample_turns(_available_turns_from_columns(needs_columns), min_turn=min_turn)
        snapshots = []
        for turn in turns:
            snapshot = _needs_snapshot_from_columns(needs_columns, turn)
            if snapshot is not None:
                snapshots.append(snapshot)
        if snapshots:
            return snapshots
    needs_snapshot = run.get("needs_snapshot")
    return [needs_snapshot] if needs_snapshot else []


def _iter_joint_sample_turns(run: dict, min_turn: int = 100) -> list[int]:
    graph_turns = {
        int(snapshot["turn"])
        for snapshot in _iter_graph_snapshots(run, min_turn=min_turn)
    }
    needs_turns = {
        int(snapshot["turn"])
        for snapshot in _iter_needs_snapshots(run, min_turn=min_turn)
    }
    shared_turns = sorted(graph_turns & needs_turns)
    if shared_turns:
        return shared_turns
    single_graph = run.get("graph_snapshot")
    single_needs = run.get("needs_snapshot")
    if single_graph and single_needs and int(single_graph["turn"]) == int(single_needs["turn"]):
        return [int(single_graph["turn"])]
    return []


def _filter_events_window(events: list[dict], start_turn: int, window: int = 20) -> list[dict]:
    end_turn = start_turn + window
    return [
        event for event in events
        if start_turn <= int(event.get("turn", -1)) < end_turn
    ]


def _cohen_d(sample_a: list[float], sample_b: list[float]) -> float:
    if not sample_a or not sample_b:
        return 0.0
    mean_a = _mean(sample_a)
    mean_b = _mean(sample_b)
    if len(sample_a) == 1 and len(sample_b) == 1:
        return mean_a - mean_b
    var_a = statistics.pvariance(sample_a) if len(sample_a) > 1 else 0.0
    var_b = statistics.pvariance(sample_b) if len(sample_b) > 1 else 0.0
    pooled_num = ((len(sample_a) - 1) * var_a) + ((len(sample_b) - 1) * var_b)
    pooled_den = max(1, len(sample_a) + len(sample_b) - 2)
    pooled_var = pooled_num / pooled_den
    pooled_std = pooled_var ** 0.5
    if pooled_std == 0.0:
        return mean_a - mean_b
    return (mean_a - mean_b) / pooled_std

def detect_communities(
    edges: list[tuple[int, int, int, int]],
    mem_sigs: dict[int, list[tuple[int, int, int]]],
) -> list[set[int]]:
    """Detect emergent social communities via deterministic label propagation.

    Community oracle method 1, kept unchanged: the validation sidecar's
    in-run community summary is built with it, and community method 2 keeps
    its result as the legacy component (``validation_communities``, which
    detects communities as M53 oracle 1 specifies them). It propagates over
    every edge, rivals and grudges included, unweighted and across regions,
    and its kin-only exclusion tests ``bond_type != 0``: the native code 0
    is the mentor and kin is 5 (``ffi_constants.BOND_TYPES``), so a pure
    kin clump passes it.

    Parameters
    ----------
    edges:
        List of (agent_a, agent_b, bond_type, sentiment), bond types as in
        ``ffi_constants.BOND_TYPES`` (rule 2 below treats 0 as kin).
    mem_sigs:
        Mapping agent_id → list of (event_type, turn, severity) memory tuples.

    Returns
    -------
    List of sets, each set being the agent_ids in a qualifying community.
    """
    if not edges:
        return []

    # --- Build undirected adjacency list ----------------------------------
    # adjacency: agent_id -> list of (neighbor_id, bond_type, sentiment)
    adjacency: dict[int, list[tuple[int, int, int]]] = {}
    all_nodes: set[int] = set()
    for a, b, bond_type, sentiment in edges:
        all_nodes.add(a)
        all_nodes.add(b)
        adjacency.setdefault(a, []).append((b, bond_type, sentiment))
        adjacency.setdefault(b, []).append((a, bond_type, sentiment))

    # Also include nodes that appear only in mem_sigs with no edges
    # (they stay in their own singleton label throughout)
    for node in mem_sigs:
        all_nodes.add(node)

    sorted_nodes = sorted(all_nodes)

    # --- Label propagation ------------------------------------------------
    # Initialize each node with its own label (= agent_id for determinism)
    labels: dict[int, int] = {n: n for n in sorted_nodes}

    for _ in range(20):
        changed = False
        for node in sorted_nodes:
            neighbors = adjacency.get(node, [])
            if not neighbors:
                continue
            # Count neighbor labels
            label_counts: dict[int, int] = {}
            for neighbor, _bt, _sent in neighbors:
                lbl = labels[neighbor]
                label_counts[lbl] = label_counts.get(lbl, 0) + 1
            # Most common label; tie-break by minimum label ID
            best_label = min(
                label_counts,
                key=lambda lbl: (-label_counts[lbl], lbl),
            )
            if best_label != labels[node]:
                labels[node] = best_label
                changed = True
        if not changed:
            break

    # --- Group by label ---------------------------------------------------
    groups: dict[int, set[int]] = {}
    for node, lbl in labels.items():
        groups.setdefault(lbl, set()).add(node)

    # --- Edge lookup sets for fast filtering ------------------------------
    # positive_non_kin_pairs: frozenset pairs with bond_type != 0 and sentiment > 0
    positive_non_kin: set[frozenset] = set()
    for a, b, bond_type, sentiment in edges:
        if bond_type != 0 and sentiment > 0:
            positive_non_kin.add(frozenset({a, b}))

    # --- Filter communities -----------------------------------------------
    result: list[set[int]] = []
    for members in groups.values():
        # Rule 1: size >= 5
        if len(members) < 5:
            continue

        # Rule 2: at least 1 non-kin positive edge within the community
        members_list = sorted(members)
        has_positive_non_kin = False
        for i, a in enumerate(members_list):
            for b in members_list[i + 1:]:
                if frozenset({a, b}) in positive_non_kin:
                    has_positive_non_kin = True
                    break
            if has_positive_non_kin:
                break
        if not has_positive_non_kin:
            continue

        # Rule 3: >= 80% of members share at least one common memory
        # signature with at least one other member.
        # Two agents share a memory if they have same event_type and turns
        # within 5 of each other.
        def _mem_key_set(agent_id: int) -> set[tuple[int, int]]:
            """Return set of (event_type, turn) for agent, bucketed by //5."""
            sigs = mem_sigs.get(agent_id, [])
            return {(et, t // 5) for et, t, _sev in sigs}

        mem_keys = {agent: _mem_key_set(agent) for agent in members}

        # An agent "has a shared memory" if its key set intersects with any
        # other member's key set.
        shared_count = 0
        for agent in members:
            my_keys = mem_keys[agent]
            if not my_keys:
                continue
            for other in members:
                if other == agent:
                    continue
                if my_keys & mem_keys[other]:
                    shared_count += 1
                    break

        if shared_count / len(members) < 0.80:
            continue

        result.append(members)

    return result


def _match_needs_pairs(
    needs_data: dict,
    need_name: str,
    need_divergence: float,
    personality_tolerance: float,
) -> list[tuple[int, int]]:
    """Matched ``(low_need_id, high_need_id)`` pairs of one needs snapshot.

    Two agents match when civ_affinity, region and occupation are equal,
    boldness, ambition and loyalty_trait each differ by at most
    ``personality_tolerance``, and the need differs by more than
    ``need_divergence``. Greedy first match in snapshot order; each agent is
    in at most one pair. Candidates are scanned within the agent's own
    (civ, region, occupation) cell, which gives the same pairs as scanning
    every later agent.
    """
    ids = needs_data["agent_id"]
    need_vals = needs_data[need_name]
    boldness = needs_data["boldness"]
    ambition = needs_data["ambition"]
    loyalty = needs_data["loyalty_trait"]
    cells: dict[tuple, list[int]] = defaultdict(list)
    position: list[int] = []
    keys = list(zip(needs_data["civ_affinity"], needs_data["region"], needs_data["occupation"]))
    for index, key in enumerate(keys):
        members = cells[key]
        position.append(len(members))
        members.append(index)

    pairs: list[tuple[int, int]] = []
    used: set = set()
    for i, aid in enumerate(ids):
        if aid in used:
            continue
        members = cells[keys[i]]
        for j in members[position[i] + 1:]:
            bid = ids[j]
            if bid in used:
                continue
            if (
                abs(boldness[i] - boldness[j]) > personality_tolerance
                or abs(ambition[i] - ambition[j]) > personality_tolerance
                or abs(loyalty[i] - loyalty[j]) > personality_tolerance
            ):
                continue
            if abs(need_vals[i] - need_vals[j]) <= need_divergence:
                continue
            used.add(aid)
            used.add(bid)
            pairs.append((aid, bid) if need_vals[i] < need_vals[j] else (bid, aid))
            break  # each agent used in at most one pair
    return pairs


def _match_binding_pairs(
    needs_data: dict,
    need_name: str,
    threshold: float,
    need_divergence: float,
    personality_tolerance: float,
) -> list[tuple[int, int]]:
    """Binding ``(low_need_id, high_need_id)`` pairs of one needs snapshot.

    The low agent's need is below ``threshold``, its partner's at or above it
    and higher by more than ``need_divergence``; civ_affinity, region and
    occupation are equal and boldness, ambition and loyalty_trait each differ
    by at most ``personality_tolerance``. Greedy first match: agents below the
    threshold in snapshot order, partners in snapshot order within the cell;
    each agent is in at most one pair.
    """
    ids = needs_data["agent_id"]
    need_vals = needs_data[need_name]
    boldness = needs_data["boldness"]
    ambition = needs_data["ambition"]
    loyalty = needs_data["loyalty_trait"]
    partners: dict[tuple, list[int]] = defaultdict(list)
    keys = list(zip(needs_data["civ_affinity"], needs_data["region"], needs_data["occupation"]))
    for index, key in enumerate(keys):
        if need_vals[index] >= threshold:
            partners[key].append(index)

    pairs: list[tuple[int, int]] = []
    used: set = set()
    for i, aid in enumerate(ids):
        if need_vals[i] >= threshold:
            continue
        for j in partners.get(keys[i], ()):
            bid = ids[j]
            if bid in used:
                continue
            if (
                abs(boldness[i] - boldness[j]) > personality_tolerance
                or abs(ambition[i] - ambition[j]) > personality_tolerance
                or abs(loyalty[i] - loyalty[j]) > personality_tolerance
            ):
                continue
            if need_vals[j] - need_vals[i] <= need_divergence:
                continue
            used.add(bid)
            pairs.append((aid, bid))
            break
    return pairs


def compute_needs_diversity(
    needs_data: dict,
    events_data: list[dict],
    need_name: str,
    event_type: int = 1,
    need_divergence: float = NEEDS_LEGACY_NEED_DIVERGENCE,
    personality_tolerance: float = NEEDS_PERSONALITY_TOLERANCE,
) -> dict:
    """Oracle 2: Validate that need levels influence agent behavioral event rates.

    Uses a matched-cohort approach: pairs agents that are identical on
    civ_affinity, region, occupation, and personality traits, but diverge on
    the specified need. Compares event rates between low-need and high-need
    halves of each pair.

    Parameters
    ----------
    needs_data:
        Dict of column lists from bulk FFI snapshot. Required keys:
        agent_id, <need_name>, civ_affinity, region, occupation,
        boldness, ambition, loyalty_trait.
    events_data:
        List of dicts with keys: agent_id, event_type, turn.
    need_name:
        The need column to test (e.g. "safety").
    event_type:
        Event type code to count (default 1 = migration).
    need_divergence:
        Minimum absolute difference in need value to qualify a pair
        (default 0.2).
    personality_tolerance:
        Maximum allowed difference in boldness, ambition, loyalty_trait
        for a pair to be considered matched (default 0.1).

    Returns
    -------
    dict with keys:
        pairs_found         – number of matched pairs
        low_need_event_rate – events per agent in low-need group
        high_need_event_rate – events per agent in high-need group
        rate_difference     – low - high (positive = low-need has more events)
    """
    # --- Count events per agent --------------------------------------------
    event_counts: dict[int, int] = {}
    for ev in events_data:
        if ev["event_type"] == event_type:
            aid = ev["agent_id"]
            event_counts[aid] = event_counts.get(aid, 0) + 1

    # --- Find matched pairs ------------------------------------------------
    pairs = _match_needs_pairs(needs_data, need_name, need_divergence, personality_tolerance)
    pairs_found = len(pairs)
    low_ids = [low for low, _high in pairs]
    high_ids = [high for _low, high in pairs]

    # --- Compute event rates -----------------------------------------------
    def _rate(id_list: list[int]) -> float:
        if not id_list:
            return 0.0
        total = sum(event_counts.get(aid, 0) for aid in id_list)
        return total / len(id_list)

    low_counts = [event_counts.get(aid, 0) for aid in low_ids]
    high_counts = [event_counts.get(aid, 0) for aid in high_ids]
    low_rate = _rate(low_ids)
    high_rate = _rate(high_ids)

    return {
        "pairs_found": pairs_found,
        "low_need_event_rate": low_rate,
        "high_need_event_rate": high_rate,
        "rate_difference": low_rate - high_rate,
        "effect_size": _cohen_d(low_counts, high_counts),
    }


def _needs_candidate_priority(result: dict, snapshot_turn: int) -> tuple:
    pairs_found = int(result.get("pairs_found", 0))
    rate_difference = float(result.get("rate_difference", 0.0))
    effect_size = abs(float(result.get("effect_size", 0.0)))
    expected = pairs_found > 0 and rate_difference > 0 and effect_size > 0.10
    return (
        1 if expected else 0,
        pairs_found,
        effect_size,
        abs(rate_difference),
        -snapshot_turn,
    )


def compute_cohort_distinctiveness(
    communities: list[set[int]],
    events_data: list[dict],
    agent_data: dict,
    event_type: int = 1,
    satisfaction_tolerance: float = 0.10,
    *,
    pair_window: tuple[int, int] | None = None,
    deaths: dict[int, int] | None = None,
    matched_pairs_out: list | None = None,
) -> dict:
    """Oracle 4: Validate that community membership anchors behavior.

    ``matched_pairs_out``, when a list, receives the (member, control)
    pairs (cohort method 6 reports the matching's quality).

    Compares migration (or other behavioral event) rates between community
    members and a matched control group of non-community agents drawn from
    the same demographic profile (civ_affinity, region, occupation).

    With ``pair_window`` (first, last turn; cohort method 3) only matched
    (member, control) pairs are compared, each over the turns both agents
    were alive: the window ends at the first death of either (``deaths``,
    agent id -> turn; that turn's events count). ``pairs`` and
    ``censored_pairs`` are added to the result.

    Parameters
    ----------
    communities:
        List of sets of agent_ids, as returned by detect_communities().
    events_data:
        List of dicts with keys: agent_id, event_type, turn.
    agent_data:
        Dict of column lists. Required keys:
        agent_id, civ_affinity, region, occupation.
    event_type:
        Event type code to count (default 1 = migration).

    Returns
    -------
    dict with keys:
        communities_analyzed  – number of communities processed
        community_event_rate  – mean migration rate across all community members
        control_event_rate    – mean migration rate across matched control agents
        effect_direction      – "community_lower", "community_higher", or "equal"
    """
    # --- Build per-agent demographic lookup --------------------------------
    ids = agent_data["agent_id"]
    civ_aff = agent_data["civ_affinity"]
    regions = agent_data["region"]
    occupations = agent_data["occupation"]
    satisfactions = agent_data.get("satisfaction", [0.0] * len(ids))

    demo: dict[int, tuple] = {}  # agent_id -> (civ_affinity, region, occupation, satisfaction)
    for i, aid in enumerate(ids):
        demo[aid] = (civ_aff[i], regions[i], occupations[i], satisfactions[i])

    # --- Count events per agent --------------------------------------------
    event_counts: dict[int, int] = {}
    for ev in events_data:
        if ev["event_type"] == event_type:
            aid = ev["agent_id"]
            event_counts[aid] = event_counts.get(aid, 0) + 1

    # --- Identify all community members ------------------------------------
    all_community_ids: set[int] = set()
    for community in communities:
        all_community_ids.update(community)

    # Non-community agents available as controls
    all_agent_ids = set(ids)
    non_community_ids = all_agent_ids - all_community_ids

    # --- For each community, find matched control agents -------------------
    community_ids_used: list[int] = []
    control_ids_used: list[int] = []
    matched_pairs: list[tuple[int, int]] = []
    communities_analyzed = 0

    for community in communities:
        communities_analyzed += 1
        members = list(community)

        # Build demographic profile: bucket counts for majority matching
        # Strategy: for each community member, find a non-community agent
        # with the exact same (civ_affinity, region, occupation).
        available_controls = list(non_community_ids)
        used_controls: set[int] = set()

        for member_id in members:
            member_demo = demo.get(member_id)
            if member_demo is None:
                continue
            member_civ, member_region, member_occ, member_sat = member_demo
            for ctrl_id in available_controls:
                if ctrl_id in used_controls:
                    continue
                ctrl_demo = demo.get(ctrl_id)
                if ctrl_demo is None:
                    continue
                ctrl_civ, ctrl_region, ctrl_occ, ctrl_sat = ctrl_demo
                if (
                    ctrl_civ == member_civ
                    and ctrl_region == member_region
                    and ctrl_occ == member_occ
                    and abs(float(ctrl_sat) - float(member_sat)) <= satisfaction_tolerance
                ):
                    used_controls.add(ctrl_id)
                    matched_pairs.append((member_id, ctrl_id))
                    break

        community_ids_used.extend(members)
        control_ids_used.extend(used_controls)
    if matched_pairs_out is not None:
        matched_pairs_out.extend(matched_pairs)

    # --- Compute event rates -----------------------------------------------
    def _rate(id_list: list[int]) -> float:
        if not id_list:
            return 0.0
        total = sum(event_counts.get(aid, 0) for aid in id_list)
        return total / len(id_list)

    censored_pairs = 0
    if pair_window is None:
        community_counts = [event_counts.get(aid, 0) for aid in community_ids_used]
        control_counts = [event_counts.get(aid, 0) for aid in control_ids_used]
        community_rate = _rate(community_ids_used)
        control_rate = _rate(control_ids_used)
    else:
        # Method 3: each matched pair over the turns both agents lived.
        first_turn, last_turn = pair_window
        deaths = deaths or {}
        event_turns: dict[int, list[int]] = defaultdict(list)
        for ev in events_data:
            if ev["event_type"] == event_type:
                event_turns[ev["agent_id"]].append(int(ev["turn"]))
        for turns in event_turns.values():
            turns.sort()
        community_counts, control_counts = [], []
        for member_id, ctrl_id in matched_pairs:
            end = last_turn
            for agent_id in (member_id, ctrl_id):
                died = deaths.get(agent_id)
                if died is not None and died < end:
                    end = died
            if end < last_turn:
                censored_pairs += 1
            for agent_id, counts in ((member_id, community_counts), (ctrl_id, control_counts)):
                turns = event_turns.get(agent_id, ())
                counts.append(max(0, bisect_right(turns, end) - bisect_left(turns, first_turn)))
        community_rate = _mean(community_counts)
        control_rate = _mean(control_counts)

    if community_rate < control_rate:
        direction = "community_lower"
    elif community_rate > control_rate:
        direction = "community_higher"
    else:
        direction = "equal"

    result = {
        "communities_analyzed": communities_analyzed,
        "community_event_rate": community_rate,
        "control_event_rate": control_rate,
        "effect_direction": direction,
        "effect_size": _cohen_d(control_counts, community_counts),
    }
    if pair_window is not None:
        result["pairs"] = len(matched_pairs)
        result["censored_pairs"] = censored_pairs
    return result


def _cohort_candidate_priority(
    migration_result: dict,
    rebellion_result: dict,
    snapshot_turn: int,
) -> tuple:
    strongest_effect = max(
        abs(float(migration_result.get("effect_size", 0.0))),
        abs(float(rebellion_result.get("effect_size", 0.0))),
    )
    expected = (
        migration_result.get("effect_direction") == "community_lower"
        or rebellion_result.get("effect_direction") == "community_higher"
    )
    return (
        1 if expected and strongest_effect > 0.10 else 0,
        strongest_effect,
        -snapshot_turn,
    )


def run_determinism_gate(batch_dir: Path, *, _admission=None) -> dict:
    """Run determinism smoke gate: 2 identical seeds must produce scrubbed-equal output."""
    # Index seeds one bundle at a time, then re-read only duplicate groups, so
    # a large batch never holds every parsed bundle at once.
    paths_by_seed: dict[int, list[Path]] = defaultdict(list)
    for bundle_path, bundle in iter_bundles(batch_dir, _admission=_admission):
        seed = bundle.get("metadata", {}).get("seed")
        if seed is None:
            continue
        paths_by_seed[int(seed)].append(bundle_path)

    duplicate_seed_groups = {
        seed: [(path, _load_bundle(path)) for path in paths]
        for seed, paths in paths_by_seed.items() if len(paths) >= 2
    }
    if not duplicate_seed_groups:
        return {
            "status": "SKIP",
            "reason": "no_duplicate_seed_pairs",
            "pairs_checked": 0,
            "duplicate_seeds": [],
            "mismatches": [],
        }

    pairs_checked = 0
    mismatches: list[dict] = []
    for seed, items in sorted(duplicate_seed_groups.items()):
        ref_path, ref_bundle = items[0]
        for other_path, other_bundle in items[1:]:
            pairs_checked += 1
            if not scrubbed_equal(ref_bundle, other_bundle):
                mismatches.append({
                    "seed": seed,
                    "reference": str(ref_path),
                    "candidate": str(other_path),
                })

    return {
        "status": "PASS" if not mismatches else "FAIL",
        "reason": "bundles_match" if not mismatches else "scrubbed_bundle_mismatch",
        "pairs_checked": pairs_checked,
        "duplicate_seeds": sorted(duplicate_seed_groups.keys()),
        "mismatches": mismatches,
    }


def run_community_oracle(seed_runs: list[dict], method_version: int | None = None, *,
                         spec_required: bool | None = None) -> dict:
    """M53 oracle 1. Method 2 (``validation_communities``,
    docs/integration/spec-communities.md): method 1's result as its legacy
    component and the communities as the spec defines them, judged by the
    spec's acceptance criteria, as its spec component; the legacy component
    decides unless ``spec_required`` (default
    ``validation_gate.COMMUNITY_SPEC_REQUIRED``). ``method_version=1``
    re-scores method 1 exactly: a community of 5+ (``detect_communities``)
    at some snapshot from turn 100 in 75% of the seeds."""
    from .validation_communities import (
        COMMUNITY_LEGACY_METHOD_VERSION, COMMUNITY_METHOD_VERSIONS, COMMUNITY_ORACLE_METHOD_VERSION,
        community_method_2_result, spec_component,
    )

    if method_version is None:
        method_version = COMMUNITY_ORACLE_METHOD_VERSION
    if isinstance(method_version, bool) or method_version not in COMMUNITY_METHOD_VERSIONS:
        raise ValueError(f"community oracle method_version must be one of {COMMUNITY_METHOD_VERSIONS}: "
                         f"{method_version!r}")
    if method_version == COMMUNITY_ORACLE_METHOD_VERSION:
        if not seed_runs:
            return {"status": "SKIP", "reason": "no_bundles"}
        return community_method_2_result(
            run_community_oracle(seed_runs, method_version=COMMUNITY_LEGACY_METHOD_VERSION),
            spec_component(seed_runs), spec_required=spec_required)
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}

    qualifying_seed_count = 0
    analyzed_seeds = 0
    per_seed: list[dict] = []

    for run in seed_runs:
        community_summary = run.get("validation_community_summary")
        graph_snapshots = _iter_graph_snapshots(run, min_turn=100)
        if graph_snapshots:
            analyzed_seeds += 1
            best_turn = None
            best_count = 0
            for graph_snapshot in graph_snapshots:
                communities = detect_communities(
                    graph_snapshot["edges"],
                    graph_snapshot["memory_signatures"],
                )
                qualifying = [community for community in communities if len(community) >= 5]
                qualifying_count = len(qualifying)
                if (qualifying_count, -(int(graph_snapshot["turn"]))) > (best_count, -(best_turn or 10**9)):
                    best_turn = int(graph_snapshot["turn"])
                    best_count = qualifying_count
            if best_count > 0:
                qualifying_seed_count += 1
            per_seed.append({
                "seed": run.get("seed"),
                "snapshot_turn": best_turn,
                "qualifying_communities": best_count,
                "sampled_turn_count": len(graph_snapshots),
                "source": "raw",
            })
            continue
        if not community_summary:
            continue
        turns = _sample_turns(
            sorted(int(turn) for turn in community_summary.get("community_summary_by_turn", {}).keys()),
            min_turn=100,
        )
        if not turns:
            continue
        analyzed_seeds += 1
        best_turn = None
        best_count = 0
        structural_issue = False
        for turn in turns:
            summary = community_summary["community_summary_by_turn"].get(str(turn), {})
            cluster_count = sum(int(region.get("cluster_count", 0)) for region in summary.values())
            turn_structural_issue = any(
                float(region.get("max_cluster_fraction", 0.0)) > 0.05
                for region in summary.values()
            )
            score = cluster_count if not turn_structural_issue else 0
            if (score, -turn) > (best_count, -(best_turn or 10**9)):
                best_turn = turn
                best_count = score
                structural_issue = turn_structural_issue
        if best_count > 0 and not structural_issue:
            qualifying_seed_count += 1
        per_seed.append({
            "seed": run.get("seed"),
            "snapshot_turn": best_turn,
            "qualifying_communities": best_count,
            "structural_issue": structural_issue,
            "sampled_turn_count": len(turns),
            "source": "summary",
        })

    if analyzed_seeds == 0:
        return {"status": "SKIP", "reason": "no_community_inputs"}

    required = required_seed_count(analyzed_seeds, 0.75)
    return {
        "status": "PASS" if qualifying_seed_count >= required else "FAIL",
        "analyzed_seeds": analyzed_seeds,
        "required_seed_count": required,
        "qualifying_seed_count": qualifying_seed_count,
        "per_seed": per_seed,
    }


def _first_event_turns(events: list[dict], event_type: int) -> dict[int, int]:
    """Each agent's first turn with an event of ``event_type`` (agent IDs are never reused)."""
    first: dict[int, int] = {}
    for event in events:
        if event["event_type"] == event_type:
            agent_id = int(event["agent_id"])
            turn = int(event["turn"])
            if agent_id not in first or turn < first[agent_id]:
                first[agent_id] = turn
    return first


def _without_agents_with_event_by(columns: dict, first_event_turn: dict[int, int], snapshot_turn: int) -> dict:
    """Drop rows of agents whose first event falls on or before ``snapshot_turn``."""
    keep = [
        idx for idx, agent_id in enumerate(columns["agent_id"])
        if first_event_turn.get(int(agent_id), snapshot_turn + 1) > snapshot_turn
    ]
    if len(keep) == len(columns["agent_id"]):
        return columns
    return {name: [values[idx] for idx in keep] for name, values in columns.items()}


def _student_t_quantile(probability: float, degrees_of_freedom: int) -> float:
    from scipy.stats import t as student_t

    return float(student_t.ppf(probability, degrees_of_freedom))


def _sign_test_p(concordant: int, discordant: int) -> float:
    """One-sided exact sign test: P(X >= concordant) for X ~ Binomial(n, 1/2)."""
    n = concordant + discordant
    if n == 0:
        return 1.0
    return sum(comb(n, k) for k in range(concordant, n + 1)) / 2 ** n


def _pooled_net_concordance(per_seed: list[tuple[int, int]], confidence: float) -> dict:
    """Pooled (C - D) / (C + D) over seeds, with a seed-clustered bound.

    Each seed is a cluster: its pairs share agents across snapshots and
    overlapping outcome windows, seeds do not. The ratio estimator's variance
    is ``S / (S - 1) * sum((C_s - D_s - net * n_s)^2) / n^2`` over the ``S``
    seeds with informative pairs; the bound is one-sided Student t with
    ``S - 1`` degrees of freedom.
    """
    clusters = [(c, d) for c, d in per_seed if c + d > 0]
    total = sum(c + d for c, d in clusters)
    if not clusters:
        return {"net_concordance": None, "standard_error": None, "lower_bound": None, "clusters": 0}
    net = sum(c - d for c, d in clusters) / total
    count = len(clusters)
    if count < 2:
        return {"net_concordance": net, "standard_error": None, "lower_bound": None, "clusters": count}
    residual = sum(((c - d) - net * (c + d)) ** 2 for c, d in clusters)
    standard_error = (count / (count - 1) * residual) ** 0.5 / total
    lower_bound = net - _student_t_quantile(confidence, count - 1) * standard_error
    return {
        "net_concordance": net,
        "standard_error": standard_error,
        "lower_bound": lower_bound,
        "clusters": count,
    }


def _needs_seed_pairs(
    run: dict,
    needs_snapshots: list[dict],
    *,
    exclude_prior_rebels: bool,
    need_divergence: float,
    personality_tolerance: float,
    window: int,
    thresholds: dict[str, float] | None = None,
    binding_divergence: float = NEEDS_BINDING_DIVERGENCE,
    outcome_offset: int = 1,
    censor_at_death: bool = False,
    censored: list[int] | None = None,
    pairings: tuple[tuple[str, int], ...] = NEEDS_PAIRINGS,
) -> tuple[int, dict[str, list[tuple[int, int]]], dict[str, list[tuple[int, int]]]]:
    """Every matched pair of one seed: eligible snapshot count, and per need
    the (low-need agent's, high-need agent's) event counts in the window, for
    method 2's pairs and for the binding pairs (``_match_binding_pairs``).

    The window of a turn-t snapshot is turns t + ``outcome_offset`` ..
    t + ``outcome_offset`` + window - 1: 1 (method 4) counts strictly after
    the snapshot, 0 (methods 2 and 3) from the snapshot turn. A snapshot is
    eligible when the window's last turn was simulated (before total turns).
    ``censor_at_death`` (method 5) ends a pair's window at the first death of
    either agent (``run["deaths"]``, agent id -> turn; that turn's events
    count), so both agents are counted over the same turns; ``censored``
    (pooled pairs, binding pairs) counts the pairs whose window was cut;
    pairs of a pairing outside ``NEEDS_PAIRINGS`` (method 6's informational
    pairings) are not counted there. ``pairings`` are the (need, event)
    pairs scored.
    """
    thresholds = NEEDS_BEHAVIOUR_THRESHOLDS if thresholds is None else thresholds
    total_turns = _total_turns(run)
    first_rebellion = _first_event_turns(run["events"], EVENT_NAME_TO_CODE["rebellion"])
    events_by_turn: dict[int, list[dict]] = defaultdict(list)
    for event in run["events"]:
        events_by_turn[int(event.get("turn", -1))].append(event)
    deaths: dict[int, int] = (run.get("deaths") or {}) if censor_at_death else {}
    event_turns: dict[tuple[int, int], list[int]] = defaultdict(list)
    if deaths:
        for event in run["events"]:
            event_turns[(event["agent_id"], event["event_type"])].append(int(event.get("turn", -1)))
        for turns in event_turns.values():
            turns.sort()
    outcomes: dict[str, list[tuple[int, int]]] = {need: [] for need, _event in pairings}
    binding: dict[str, list[tuple[int, int]]] = {need: [] for need, _event in pairings}
    snapshots = 0
    for needs_snapshot in needs_snapshots:
        snapshot_turn = int(needs_snapshot["turn"])
        first_turn = snapshot_turn + outcome_offset
        if total_turns and first_turn + window > total_turns:
            continue
        snapshots += 1
        last_turn = first_turn + window - 1
        counts: dict[tuple[int, int], int] = defaultdict(int)
        for turn in range(first_turn, first_turn + window):
            for event in events_by_turn.get(turn, ()):
                counts[(event["agent_id"], event["event_type"])] += 1

        def pair_counts(low: int, high: int, event_type: int, kind: int | None) -> tuple[int, int]:
            end = last_turn
            for agent in (low, high):
                died = deaths.get(agent)
                if died is not None and died < end:
                    end = died
            if end == last_turn:
                return counts.get((low, event_type), 0), counts.get((high, event_type), 0)
            if censored is not None and kind is not None:
                censored[kind] += 1
            return tuple(
                max(0, bisect_right(event_turns.get((agent, event_type), ()), end)
                    - bisect_left(event_turns.get((agent, event_type), ()), first_turn))
                for agent in (low, high)
            )

        for need_name, event_type in pairings:
            columns = needs_snapshot["columns"]
            if need_name not in columns:
                continue
            if need_name == "autonomy" and exclude_prior_rebels:
                columns = _without_agents_with_event_by(columns, first_rebellion, snapshot_turn)
            gate_pairing = (need_name, event_type) in NEEDS_PAIRINGS
            for low, high in _match_needs_pairs(columns, need_name, need_divergence, personality_tolerance):
                outcomes[need_name].append(pair_counts(low, high, event_type, 0 if gate_pairing else None))
            threshold = thresholds.get(need_name)
            if threshold is None:
                continue
            for low, high in _match_binding_pairs(
                columns, need_name, threshold, binding_divergence, personality_tolerance
            ):
                binding[need_name].append(pair_counts(low, high, event_type, 1 if gate_pairing else None))
    return snapshots, outcomes, binding


def _concordance(outcomes: list[tuple[int, int]]) -> tuple[int, int]:
    concordant = sum(1 for low, high in outcomes if low > high)
    discordant = sum(1 for low, high in outcomes if low < high)
    return concordant, discordant


def run_needs_oracle(
    seed_runs: list[dict],
    exclude_prior_rebels: bool = NEEDS_AUTONOMY_EXCLUDES_PRIOR_REBELS,
    *,
    need_divergence: float = NEEDS_NEED_DIVERGENCE,
    personality_tolerance: float = NEEDS_PERSONALITY_TOLERANCE,
    window: int = NEEDS_OUTCOME_WINDOW_TURNS,
    confidence: float = NEEDS_CONFIDENCE,
    seed_fraction: float = NEEDS_SEED_FRACTION_MIN,
    thresholds: dict[str, float] | None = None,
    binding_divergence: float = NEEDS_BINDING_DIVERGENCE,
    require_binding: bool = True,
    profile: str | None = None,
    method_version: int | None = None,
    ablation: dict | None = None,
    placebo: dict | None = None,
    require_causal: bool | None = None,
) -> dict:
    """M53 oracle 2, method 7: method 6's observational result and an ablation.

    Method 7 (``NEEDS_ORACLE_METHOD_VERSION``) is method 6's result (the
    observational component, ``observational_status``) with the ablation
    component of the ``needs`` arm (``ablation``, from
    ``validation_ablation.load_ablation_arms``; without it the component is
    ``NOT_RUN``) and, when given, the same component scored against the
    ``placebo`` arm. ``status`` is PASS when every component that decides
    passes (``validation_gate.needs_components_required``): the
    observational one unless ``require_causal`` (default
    ``validation_gate.CAUSAL_ORACLES_REQUIRED``), then the profile's.

    Method 6, lower need, more of its event, pooled over seeds:

    Hypothesis: an agent whose need is lower than a matched agent's has more
    of the event that need drives over the next ``window`` turns (autonomy:
    rebellion; social, material, safety: migration; purpose: occupation
    switch). Every eligible snapshot and pairing of every seed contributes its
    matched pairs. Method 2's criteria: the one-sided ``confidence`` lower
    bound of the pooled net concordance is above zero and at least
    ``seed_fraction`` of the analyzed seeds have more concordant than
    discordant pairs. Method 3 adds: the binding pairs, whose lower-need agent
    is below its behavioural threshold (``thresholds``) and whose partner is
    at or above it (``_match_binding_pairs``), have a pooled net concordance
    whose seed-clustered lower bound is above zero. Method 4 counts the events
    of turns t+1 .. t+window after a turn-t snapshot, not t .. t+window-1:
    the snapshot is taken after turn t's actions. Method 5 counts a pair over
    the turns both agents were alive: its window ends at the first death of
    either (``run["deaths"]``). Method 6 (``NEEDS_ORACLE_METHOD_VERSION``)
    keeps method 5's verdict and reports ``NEEDS_INFORMATIONAL_PAIRINGS``
    (spiritual -> migration) beside it (``informational_pairings``, and per
    seed ``informational``), scored as the other pairings are; it never
    decides the status.

    The binding component decides PASS only when ``profile`` is in
    ``NEEDS_BINDING_REQUIRED_PROFILES`` (the full gate) or is None; in the
    subset profile it is computed and reported (``binding.status``,
    ``informational_failed_criteria``) but does not decide. The gate applies
    the same rule to any method 3 or later result (``validation_gate``).

    ``method_version`` re-scores an earlier method exactly, for re-scoring
    and comparison: 5 is method 6 without the informational pairings, 4
    counts each agent over the whole window t+1 ..
    t+window, 3 has method 4's criteria with the window t .. t+window-1, 2 is
    method 3 without the binding component. ``require_binding=False`` is
    method 2.
    """
    if method_version is None:
        method_version = NEEDS_ORACLE_METHOD_VERSION if require_binding else NEEDS_POOLED_METHOD_VERSION
    if isinstance(method_version, bool) or method_version not in NEEDS_METHOD_VERSIONS:
        raise ValueError(f"needs oracle method_version must be one of {NEEDS_METHOD_VERSIONS}: {method_version!r}")
    if not require_binding and method_version != NEEDS_POOLED_METHOD_VERSION:
        raise ValueError(f"require_binding=False is method {NEEDS_POOLED_METHOD_VERSION}, not {method_version}")
    if method_version in NEEDS_ABLATION_METHOD_DESIGNS:
        _check_arm_designs("needs", method_version, NEEDS_ABLATION_METHOD_DESIGNS, ablation, placebo)
        observational = run_needs_oracle(
            seed_runs, exclude_prior_rebels, need_divergence=need_divergence,
            personality_tolerance=personality_tolerance, window=window, confidence=confidence,
            seed_fraction=seed_fraction, thresholds=thresholds, binding_divergence=binding_divergence,
            profile=profile, method_version=NEEDS_INFORMATIONAL_METHOD_VERSION,
        )
        return _needs_with_ablation(observational, seed_runs, profile, ablation, placebo, require_causal,
                                    method_version=method_version)
    require_binding = method_version >= NEEDS_BINDING_METHOD_VERSION
    outcome_offset = 1 if method_version >= NEEDS_POST_SNAPSHOT_METHOD_VERSION else 0
    censor_at_death = method_version >= NEEDS_DEATH_CENSORED_METHOD_VERSION
    informational_pairings = (
        NEEDS_INFORMATIONAL_PAIRINGS if method_version >= NEEDS_INFORMATIONAL_METHOD_VERSION else ()
    )
    censored = [0, 0]
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}
    thresholds = dict(NEEDS_BEHAVIOUR_THRESHOLDS if thresholds is None else thresholds)
    scored_thresholds = {
        **{need: NEEDS_INFORMATIONAL_THRESHOLDS[need] for need, _event in informational_pairings},
        **thresholds,
    }

    per_seed: list[dict] = []
    seed_counts: list[tuple[int, int]] = []
    binding_counts: list[tuple[int, int]] = []

    def _pairing_totals(pairings=NEEDS_PAIRINGS) -> dict[str, dict]:
        return {
            need: {"event_type": event, "pairs": 0, "concordant": 0, "discordant": 0,
                   "low_need_events": 0, "high_need_events": 0}
            for need, event in pairings
        }

    by_pairing = _pairing_totals()
    binding_by_pairing = _pairing_totals()
    informational_by_pairing = _pairing_totals(informational_pairings)
    informational_binding_by_pairing = _pairing_totals(informational_pairings)
    for run in seed_runs:
        needs_snapshots = _iter_needs_snapshots(run, min_turn=0)
        if not needs_snapshots:
            continue
        snapshots, all_outcomes, all_binding = _needs_seed_pairs(
            run,
            needs_snapshots,
            exclude_prior_rebels=exclude_prior_rebels,
            need_divergence=need_divergence,
            personality_tolerance=personality_tolerance,
            window=window,
            thresholds=scored_thresholds,
            binding_divergence=binding_divergence,
            outcome_offset=outcome_offset,
            censor_at_death=censor_at_death,
            censored=censored,
            pairings=NEEDS_PAIRINGS + informational_pairings,
        )
        outcomes = {need: all_outcomes[need] for need, _event in NEEDS_PAIRINGS}
        binding = {need: all_binding[need] for need, _event in NEEDS_PAIRINGS}

        def _tally(pair_outcomes: dict[str, list[tuple[int, int]]], totals_by_need: dict[str, dict]):
            pairs_found = concordant_sum = discordant_sum = 0
            seed_by_pairing: dict[str, list[int]] = {}
            for need_name, pairs in pair_outcomes.items():
                concordant, discordant = _concordance(pairs)
                pairs_found += len(pairs)
                concordant_sum += concordant
                discordant_sum += discordant
                if pairs:
                    seed_by_pairing[need_name] = [len(pairs), concordant, discordant]
                totals = totals_by_need[need_name]
                totals["pairs"] += len(pairs)
                totals["concordant"] += concordant
                totals["discordant"] += discordant
                totals["low_need_events"] += sum(low for low, _high in pairs)
                totals["high_need_events"] += sum(high for _low, high in pairs)
            return pairs_found, concordant_sum, discordant_sum, seed_by_pairing

        seed_pairs, seed_concordant, seed_discordant, seed_by_pairing = _tally(outcomes, by_pairing)
        binding_pairs, binding_concordant, binding_discordant, binding_seed_by_pairing = _tally(
            binding, binding_by_pairing
        )
        informative = seed_concordant + seed_discordant
        seed_counts.append((seed_concordant, seed_discordant))
        binding_counts.append((binding_concordant, binding_discordant))
        record = {
            "seed": run.get("seed"),
            "snapshots": snapshots,
            "pairs_found": seed_pairs,
            "informative_pairs": informative,
            "concordant": seed_concordant,
            "discordant": seed_discordant,
            "net_concordance": round((seed_concordant - seed_discordant) / informative, 4) if informative else None,
            "sign_test_p": round(_sign_test_p(seed_concordant, seed_discordant), 4),
            "by_pairing": seed_by_pairing,
        }
        if require_binding:
            # [pairs, concordant, discordant], and per pairing.
            record["binding"] = [binding_pairs, binding_concordant, binding_discordant]
            record["binding_by_pairing"] = binding_seed_by_pairing
        if informational_pairings:
            # Method 6: the informational pairings' [pairs, concordant,
            # discordant], all pairs and binding pairs.
            _p, _c, _d, info_pooled = _tally(
                {need: all_outcomes[need] for need, _event in informational_pairings}, informational_by_pairing)
            _p, _c, _d, info_binding = _tally(
                {need: all_binding[need] for need, _event in informational_pairings},
                informational_binding_by_pairing)
            record["informational"] = {
                need: {"pairs": info_pooled.get(need, [0, 0, 0]), "binding": info_binding.get(need, [0, 0, 0])}
                for need, _event in informational_pairings
            }
        per_seed.append(record)

    analyzed_seeds = len(per_seed)
    if analyzed_seeds == 0:
        return {"status": "SKIP", "reason": "no_needs_sidecars"}

    def _rounded(value: float | None) -> float | None:
        return round(value, 4) if value is not None else None

    def _pairing_bounds(totals_by_need: dict[str, dict], key: str) -> None:
        # Per pairing, informational: the same estimate and bound on its own pairs.
        for need_name, totals in totals_by_need.items():
            pairing_counts = [
                tuple(record[key].get(need_name, (0, 0, 0))[1:]) for record in per_seed
            ]
            pairing_pooled = _pooled_net_concordance(pairing_counts, confidence)
            totals["net_concordance"] = _rounded(pairing_pooled["net_concordance"])
            totals["net_concordance_lower_bound"] = _rounded(pairing_pooled["lower_bound"])

    pooled = _pooled_net_concordance(seed_counts, confidence)
    required = required_seed_count(analyzed_seeds, seed_fraction)
    seeds_with_expected_sign = sum(1 for c, d in seed_counts if c > d)
    seeds_with_reversed_sign = sum(1 for c, d in seed_counts if c < d)
    lower_bound = pooled["lower_bound"]
    bound_ok = lower_bound is not None and lower_bound > 0.0
    seeds_ok = seeds_with_expected_sign >= required
    failed_criteria = []
    if not bound_ok:
        failed_criteria.append("net_concordance_lower_bound")
    if not seeds_ok:
        failed_criteria.append("seed_fraction")
    _pairing_bounds(by_pairing, "by_pairing")

    criterion = (
        f"one-sided {confidence:.0%} lower bound of pooled net concordance > 0 "
        f"and >= {seed_fraction:.0%} of analyzed seeds with net concordance > 0"
    )
    pooled_status = "PASS" if bound_ok and seeds_ok else "FAIL"
    binding_ok = True
    binding_decides = False
    informational_failed_criteria: list[str] = []
    binding_result = None
    if require_binding:
        binding_decides = profile is None or profile in NEEDS_BINDING_REQUIRED_PROFILES
        binding_pooled = _pooled_net_concordance(binding_counts, confidence)
        binding_lower = binding_pooled["lower_bound"]
        binding_ok = binding_lower is not None and binding_lower > 0.0
        if not binding_ok:
            (failed_criteria if binding_decides else informational_failed_criteria).append("binding_lower_bound")
        _pairing_bounds(binding_by_pairing, "binding_by_pairing")
        criterion += (
            f"; binding pairs (lower-need agent below its threshold, partner at or above it): "
            f"one-sided {confidence:.0%} lower bound of pooled net concordance > 0"
            + ("" if binding_decides else f" (informational in profile {profile})")
        )
        binding_result = {
            "status": "PASS" if binding_ok else "FAIL",
            "required": binding_decides,
            "thresholds": thresholds,
            "need_divergence": binding_divergence,
            "total_pairs": sum(record["binding"][0] for record in per_seed),
            "informative_pairs": sum(c + d for c, d in binding_counts),
            "concordant_pairs": sum(c for c, _d in binding_counts),
            "discordant_pairs": sum(d for _c, d in binding_counts),
            "seeds_with_informative_pairs": binding_pooled["clusters"],
            "seeds_with_expected_sign": sum(1 for c, d in binding_counts if c > d),
            "seeds_with_reversed_sign": sum(1 for c, d in binding_counts if c < d),
            "net_concordance": _rounded(binding_pooled["net_concordance"]),
            "net_concordance_se": _rounded(binding_pooled["standard_error"]),
            "net_concordance_lower_bound": _rounded(binding_lower),
            "by_pairing": binding_by_pairing,
        }

    result = {
        "status": "PASS" if bound_ok and seeds_ok and (binding_ok or not binding_decides) else "FAIL",
        "method": "pooled_matched_pairs",
        "method_version": method_version,
        "criterion": criterion,
        "failed_criteria": failed_criteria,
        "analyzed_seeds": analyzed_seeds,
        "seeds_with_informative_pairs": pooled["clusters"],
        "required_seed_count": required,
        "seeds_with_expected_sign": seeds_with_expected_sign,
        "seeds_with_reversed_sign": seeds_with_reversed_sign,
        "total_pairs": sum(record["pairs_found"] for record in per_seed),
        "informative_pairs": sum(c + d for c, d in seed_counts),
        "concordant_pairs": sum(c for c, _d in seed_counts),
        "discordant_pairs": sum(d for _c, d in seed_counts),
        "net_concordance": _rounded(pooled["net_concordance"]),
        "net_concordance_se": _rounded(pooled["standard_error"]),
        "net_concordance_lower_bound": _rounded(lower_bound),
        "confidence": confidence,
        "need_divergence": need_divergence,
        "personality_tolerance": personality_tolerance,
        "outcome_window_turns": window,
        "autonomy_excludes_prior_rebels": exclude_prior_rebels,
        "by_pairing": by_pairing,
    }
    if outcome_offset:
        # Method 4: the window's first turn after the snapshot (methods 2
        # and 3, 0, keep their report bytes without the key).
        result["outcome_window_start_offset"] = outcome_offset
    if censor_at_death:
        # Method 5: each pair counted while both agents lived; the pairs whose
        # window a death cut short (method 4 keeps its report bytes).
        result["outcome_censoring"] = "first_death_in_pair"
        result["censored_pairs"] = censored[0]
        if binding_result is not None:
            binding_result["censored_pairs"] = censored[1]
    if informational_pairings:
        # Method 6: pairings reported beside the verdict (methods 2-5 keep
        # their report bytes without the key).
        informational = {}
        for need_name, event_type in informational_pairings:
            entry = {"event_type": event_type, "required": False}
            for key, totals_by_need, threshold in (
                ("pairs", informational_by_pairing, None),
                ("binding", informational_binding_by_pairing, scored_thresholds.get(need_name)),
            ):
                totals = dict(totals_by_need[need_name])
                totals.pop("event_type")
                counts = [tuple(record["informational"][need_name][key][1:]) for record in per_seed]
                pooled_info = _pooled_net_concordance(counts, confidence)
                totals["informative_pairs"] = totals["concordant"] + totals["discordant"]
                totals["seeds_with_informative_pairs"] = pooled_info["clusters"]
                totals["net_concordance"] = _rounded(pooled_info["net_concordance"])
                totals["net_concordance_se"] = _rounded(pooled_info["standard_error"])
                totals["net_concordance_lower_bound"] = _rounded(pooled_info["lower_bound"])
                if threshold is not None:
                    totals["threshold"] = threshold
                entry[key] = totals
            informational[need_name] = entry
        result["informational_pairings"] = informational
    if binding_result is not None:
        result["profile"] = profile
        result["binding_required"] = binding_decides
        result["binding_required_profiles"] = list(NEEDS_BINDING_REQUIRED_PROFILES)
        result["pooled_status"] = pooled_status
        result["informational_failed_criteria"] = informational_failed_criteria
        result["binding"] = binding_result
    result["per_seed"] = per_seed
    return result


def _needs_with_ablation(observational: dict, seed_runs: list[dict], profile: str | None,
                         ablation: dict | None, placebo: dict | None, require_causal: bool | None = None, *,
                         method_version: int = NEEDS_ORACLE_METHOD_VERSION) -> dict:
    """Methods 7 and 8: method 6's ``observational`` result with the
    ablation component; the status from the components that decide
    (``validation_gate.needs_components_required``)."""
    from .validation_ablation import needs_ablation_component

    if observational.get("status") not in ("PASS", "FAIL"):
        return observational
    return needs_ablation_method_result(
        observational, needs_ablation_component(seed_runs, ablation), profile,
        placebo=needs_ablation_component(seed_runs, placebo, arm_name="placebo") if placebo is not None else None,
        require_causal=require_causal, method_version=method_version,
    )


def needs_method_7_result(observational: dict, component: dict, profile: str | None, *,
                          placebo: dict | None = None, require_causal: bool | None = None) -> dict:
    """Needs method 7 from method 6's ``observational`` result and the
    ablation ``component`` (``validation_ablation.needs_ablation_component``;
    ``placebo`` the same against the placebo arm). Pure: it re-scores the
    verdict of a saved method 7 result under another mode."""
    return needs_ablation_method_result(observational, component, profile, placebo=placebo,
                                        require_causal=require_causal,
                                        method_version=NEEDS_ABLATION_DESIGN1_METHOD_VERSION)


def needs_ablation_method_result(observational: dict, component: dict, profile: str | None, *,
                                 placebo: dict | None = None, require_causal: bool | None = None,
                                 method_version: int = NEEDS_ORACLE_METHOD_VERSION) -> dict:
    """Needs method 7 or 8 (``method_version``) from method 6's
    ``observational`` result and the ablation ``component`` of arms of the
    method's fork design. Method 8's components also name their design
    (``fork_design``); method 7's keep their fields. Pure."""
    from .validation_gate import causal_label, causal_oracles_required, combined_status, needs_components_required

    if method_version not in NEEDS_ABLATION_METHOD_DESIGNS:
        raise ValueError(f"needs ablation method must be one of {tuple(NEEDS_ABLATION_METHOD_DESIGNS)}")
    require_causal = causal_oracles_required(None, require_causal)
    component = {**component, "label": causal_label(require_causal)}
    design = NEEDS_ABLATION_METHOD_DESIGNS[method_version]
    if design >= 2:
        component["fork_design"] = design
        if placebo is not None:
            placebo = {**placebo, "fork_design": design}
    required = needs_components_required(profile, require_causal)
    statuses = {"observational": observational["status"], "ablation": component.get("status")}
    result = {
        "status": combined_status(statuses, required),
        "method": "observational_and_ablation",
        "method_version": method_version,
        "causal_oracles_required": require_causal,
        "required_components": list(required),
        "component_statuses": statuses,
        "observational_status": observational["status"],
        "observational_method": observational.get("method"),
        "observational_criterion": observational.get("criterion"),
    }
    for key, value in observational.items():
        if key in ("status", "method", "method_version", "criterion", "per_seed"):
            continue
        result[key] = value
    result["ablation"] = component
    if placebo is not None:
        result["placebo"] = placebo
    result["per_seed"] = observational.get("per_seed", [])
    return result


def run_needs_oracle_best_of(
    seed_runs: list[dict],
    exclude_prior_rebels: bool = NEEDS_AUTONOMY_EXCLUDES_PRIOR_REBELS,
) -> dict:
    """Needs oracle method 1 (before 2026-10-25), kept for re-scoring old batches.

    Per seed, the best (snapshot, pairing) candidate by ``_needs_candidate_priority``;
    PASS when 60% of seeds have a positive rate difference with |d| > 0.10 and
    the median |d| exceeds 0.10. Output equals the method 1 reports.
    """
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}

    analyzed_seeds = 0
    seeds_with_expected_sign = 0
    total_pairs = 0
    effect_sizes: list[float] = []
    per_seed: list[dict] = []
    need_event_configs = list(NEEDS_PAIRINGS)

    for run in seed_runs:
        needs_snapshots = _iter_needs_snapshots(run, min_turn=0)
        if not needs_snapshots:
            continue
        analyzed_seeds += 1
        best_turn = None
        best_need = None
        best_event_type = None
        best_result = {"pairs_found": 0, "rate_difference": 0.0, "effect_size": 0.0}
        total_turns = _total_turns(run)
        first_rebellion = _first_event_turns(run["events"], EVENT_NAME_TO_CODE["rebellion"])
        for needs_snapshot in needs_snapshots:
            snapshot_turn = int(needs_snapshot["turn"])
            if total_turns and snapshot_turn + 20 > total_turns:
                continue
            events_window = _filter_events_window(run["events"], snapshot_turn, window=20)
            for need_name, event_type in need_event_configs:
                if need_name not in needs_snapshot["columns"]:
                    continue
                columns = needs_snapshot["columns"]
                if need_name == "autonomy" and exclude_prior_rebels:
                    columns = _without_agents_with_event_by(columns, first_rebellion, snapshot_turn)
                result = compute_needs_diversity(
                    columns,
                    events_window,
                    need_name,
                    event_type=event_type,
                )
                candidate = _needs_candidate_priority(result, snapshot_turn)
                current = _needs_candidate_priority(best_result, best_turn or 10**9)
                if candidate > current:
                    best_turn = snapshot_turn
                    best_need = need_name
                    best_event_type = event_type
                    best_result = result

        pairs_found = int(best_result.get("pairs_found", 0))
        rate_difference = float(best_result.get("rate_difference", 0.0))
        effect_size = abs(float(best_result.get("effect_size", 0.0)))
        total_pairs += pairs_found
        effect_sizes.append(effect_size)
        if pairs_found > 0 and rate_difference > 0 and effect_size > 0.10:
            seeds_with_expected_sign += 1
        per_seed.append({
            "seed": run.get("seed"),
            "snapshot_turn": best_turn,
            "pairs_found": pairs_found,
            "need_name": best_need,
            "event_type": best_event_type,
            "rate_difference": rate_difference,
            "effect_size": round(effect_size, 4),
        })

    if analyzed_seeds == 0:
        return {"status": "SKIP", "reason": "no_needs_sidecars"}

    required = required_seed_count(analyzed_seeds, 0.60)
    median_effect_size = statistics.median(effect_sizes) if effect_sizes else 0.0
    return {
        "status": "PASS" if seeds_with_expected_sign >= required and median_effect_size > 0.10 else "FAIL",
        "analyzed_seeds": analyzed_seeds,
        "required_seed_count": required,
        "seeds_with_expected_sign": seeds_with_expected_sign,
        "total_pairs": total_pairs,
        "median_effect_size": median_effect_size,
        "autonomy_excludes_prior_rebels": exclude_prior_rebels,
        "per_seed": per_seed,
    }


def cohort_method_4_result(observational: dict, component: dict, *, placebo: dict | None = None,
                           require_causal: bool | None = None) -> dict:
    """Cohort method 4 from method 3's ``observational`` result and the
    kin-roots ``component`` (``validation_ablation.cohort_ablation_result``;
    ``placebo`` the same against the placebo arm). Method 3's fields stay at
    the top level, as method 7 keeps method 6's; ``status`` (and ``reason``)
    come from the component that decides
    (``validation_gate.cohort_components_required``). Pure: it re-scores the
    verdict of saved components under another mode."""
    return cohort_ablation_method_result(observational, component, placebo=placebo, require_causal=require_causal,
                                         method_version=COHORT_ABLATION_DESIGN1_METHOD_VERSION)


def cohort_ablation_method_result(observational: dict, component: dict, *, placebo: dict | None = None,
                                  require_causal: bool | None = None, community: dict | None = None,
                                  method_version: int = COHORT_ORACLE_METHOD_VERSION) -> dict:
    """Cohort method 4, 5 or 6 (``method_version``). Method 5 adds the
    community anchor's ``community`` component
    (``validation_ablation.community_ablation_result``; reported, never
    deciding; ``NOT_RUN`` without its arm) and names the fork design in its
    components; method 4's fields are unchanged. Method 6 takes components
    scored on community method 2's communities (its observational result
    names ``community_method_version`` and its ``matching``). Pure."""
    from .validation_gate import (
        COHORT_OBSERVATIONAL_NOTE, causal_label, causal_oracles_required, cohort_components_required,
        combined_status,
    )

    if method_version not in COHORT_ABLATION_METHOD_DESIGNS:
        raise ValueError(f"cohort ablation method must be one of {tuple(COHORT_ABLATION_METHOD_DESIGNS)}")
    require_causal = causal_oracles_required(None, require_causal)
    component = {**component, "label": causal_label(require_causal)}
    design = COHORT_ABLATION_METHOD_DESIGNS[method_version]
    if design >= 2:
        component["fork_design"] = design
        if placebo is not None:
            placebo = {**placebo, "fork_design": design}
    required = cohort_components_required(require_causal)
    statuses = {"observational": str(observational.get("status") or "MISSING"),
                "ablation": str(component.get("status") or "MISSING")}
    status = combined_status(statuses, required)
    result = {
        "status": status,
        "method": "observational_and_ablation",
        "method_version": method_version,
        "causal_oracles_required": require_causal,
        "required_components": list(required),
        "component_statuses": statuses,
        "observational_status": statuses["observational"],
        "observational_method": observational.get("method"),
        "observational_method_version": observational.get("method_version"),
        "observational_note": COHORT_OBSERVATIONAL_NOTE,
    }
    if observational.get("reason"):
        result["observational_reason"] = observational["reason"]
    for key, value in observational.items():
        if key in ("status", "method", "method_version", "reason", "per_seed"):
            continue
        result[key] = value
    deciding = component if required == ("ablation",) else observational
    if status != "PASS" and deciding.get("reason"):
        result["reason"] = deciding["reason"]
    result["ablation"] = component
    if placebo is not None:
        result["placebo"] = placebo
    if design >= 2:
        community = community if community is not None else {
            "status": "NOT_RUN", "reason": "no community_anchor ablation arm", "arm": "community_anchor"}
        result["community_ablation"] = {
            **community, "fork_design": design,
            "label": "causal evidence (reported; the community anchor of --community-anchoring)",
        }
    if "per_seed" in observational:
        result["per_seed"] = observational["per_seed"]
    return result


def run_cohort_oracle(seed_runs: list[dict], method_version: int | None = None, *,
                      ablation: dict | None = None, placebo: dict | None = None,
                      require_causal: bool | None = None, community: dict | None = None) -> dict:
    """M53 oracle 4, method 4: method 3's observational result
    (``COHORT_OBSERVATIONAL_NOTE``: it passes synthetic null and reversed
    worlds) and the kin-roots ablation: community members at a fork migrate
    less with the kin roots than without them
    (``validation_ablation.cohort_ablation_result`` on the ``kin_roots`` arm
    ``ablation``; ``NOT_RUN`` without it). ``placebo`` scores the same
    comparison against the placebo arm (reported). Method 3 decides unless
    ``require_causal`` (``cohort_method_4_result``). Method 5 adds the
    community anchor's component (``community``, its arm); method 6 (the
    default) is method 5 with community method 2's communities as the
    members of every component (``validation_communities``).

    Methods 1-3, re-scored with ``method_version``: community members
    migrate less and rebel more than matched non-members over the
    ``COHORT_OUTCOME_WINDOW_TURNS`` turns after a snapshot.

    Per seed, the best eligible graph and needs snapshot
    (``_cohort_candidate_priority``); PASS when 60% of analyzed seeds show an
    expected direction with an effect above 0.10 and the median strongest
    effect is above 0.10. Method 2 counts turns t+1 .. t+20 after a turn-t
    snapshot; method 3 (``COHORT_DEATH_CENSORED_METHOD_VERSION``) compares each
    member with its matched control over the turns both were alive (the
    window ends at the first death of either, ``run["deaths"]``).
    ``method_version=2`` re-scores method 2 exactly, ``method_version=1``
    method 1 (turns t .. t+19, results without a ``method_version`` key).
    """
    if method_version is None:
        method_version = COHORT_ORACLE_METHOD_VERSION
    if isinstance(method_version, bool) or method_version not in COHORT_METHOD_VERSIONS:
        raise ValueError(f"cohort oracle method_version must be one of {COHORT_METHOD_VERSIONS}: {method_version!r}")
    if method_version in COHORT_ABLATION_METHOD_DESIGNS:
        from .validation_ablation import cohort_ablation_result, community_ablation_result
        _check_arm_designs("cohort", method_version, COHORT_ABLATION_METHOD_DESIGNS, ablation, placebo, community)
        if not seed_runs:
            return {"status": "SKIP", "reason": "no_bundles"}
        spec = method_version in COHORT_SPEC_COMMUNITY_METHODS
        cohort_kw = {"spec_communities": True} if spec else {}
        community_component = None
        if COHORT_ABLATION_METHOD_DESIGNS[method_version] >= 2:
            community_component = community_ablation_result(seed_runs, community, **cohort_kw)
        observational = (_cohort_observational(seed_runs, COHORT_DEATH_CENSORED_METHOD_VERSION, spec_communities=True)
                         if spec else run_cohort_oracle(seed_runs, method_version=COHORT_DEATH_CENSORED_METHOD_VERSION))
        return cohort_ablation_method_result(
            observational,
            cohort_ablation_result(seed_runs, ablation, **cohort_kw),
            placebo=(cohort_ablation_result(seed_runs, placebo, arm_name="placebo", **cohort_kw)
                     if placebo is not None else None),
            require_causal=require_causal, community=community_component, method_version=method_version,
        )
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}
    return _cohort_observational(seed_runs, method_version)


def _cohort_observational(seed_runs: list[dict], method_version: int, *, spec_communities: bool = False) -> dict:
    """Cohort methods 1-3 (``method_version``) on the communities of
    community method 1 (``detect_communities``), or with
    ``spec_communities`` on those of community method 2
    (``validation_communities.oracle1_communities``: method 6's
    observational component, which also reports its ``matching``)."""
    outcome_offset = 1 if method_version >= COHORT_POST_SNAPSHOT_METHOD_VERSION else 0
    censor_at_death = method_version >= COHORT_DEATH_CENSORED_METHOD_VERSION
    window = COHORT_OUTCOME_WINDOW_TURNS
    if not seed_runs:
        return {"status": "SKIP", "reason": "no_bundles"}
    if spec_communities:
        from .validation_communities import oracle1_needs_columns, oracle1_snapshot, oracle1_turns
    matching = {"snapshots": 0, "members": 0, "pairs": 0, "satisfaction_gap": 0.0}
    chosen_matching = {"members": 0, "pairs": 0}

    analyzed_seeds = 0
    seeds_with_expected_direction = 0
    effect_sizes: list[float] = []
    per_seed: list[dict] = []

    for run in seed_runs:
        total_turns = _total_turns(run)
        turns = oracle1_turns(run) if spec_communities else _iter_joint_sample_turns(run, min_turn=0)
        if not turns:
            continue
        best_turn = None
        best_migration_result = None
        best_rebellion_result = None
        best_strongest_effect = -1.0
        best_members = 0
        for turn in turns:
            # The window's last turn, turn + offset + window - 1, must have been simulated.
            if total_turns and turn + outcome_offset + window > total_turns:
                continue
            if spec_communities:
                snapshot = oracle1_snapshot(run, turn)
                if snapshot is None:
                    continue
                communities = snapshot["communities"]
                needs_snapshot = {"turn": turn, "columns": oracle1_needs_columns(run, turn)}
            else:
                graph_snapshot = _graph_snapshot_from_columns(
                    run.get("relationship_columns"),
                    run.get("memory_columns"),
                    turn,
                ) or run.get("graph_snapshot")
                needs_snapshot = _needs_snapshot_from_columns(
                    run.get("needs_columns"),
                    turn,
                ) or run.get("needs_snapshot")
                if not graph_snapshot or not needs_snapshot:
                    continue
                communities = detect_communities(
                    graph_snapshot["edges"],
                    graph_snapshot["memory_signatures"],
                )
            if not communities:
                continue
            events_window = _filter_events_window(run["events"], turn + outcome_offset, window=window)
            censoring = {}
            if censor_at_death:
                first_turn = turn + outcome_offset
                censoring = {
                    "pair_window": (first_turn, first_turn + window - 1),
                    "deaths": run.get("deaths") or {},
                }
            matched: list[tuple[int, int]] | None = [] if spec_communities else None
            migration_result = compute_cohort_distinctiveness(
                communities,
                events_window,
                needs_snapshot["columns"],
                event_type=EVENT_NAME_TO_CODE["migration"],
                matched_pairs_out=matched,
                **censoring,
            )
            members = sum(len(community) for community in communities)
            if spec_communities:
                satisfaction = dict(zip(needs_snapshot["columns"]["agent_id"],
                                        needs_snapshot["columns"].get("satisfaction") or ()))
                matching["snapshots"] += 1
                matching["members"] += members
                matching["pairs"] += len(matched)
                matching["satisfaction_gap"] += sum(
                    abs(float(satisfaction.get(a, 0.0)) - float(satisfaction.get(b, 0.0))) for a, b in matched)
            rebellion_result = compute_cohort_distinctiveness(
                communities,
                events_window,
                needs_snapshot["columns"],
                event_type=EVENT_NAME_TO_CODE["rebellion"],
                **censoring,
            )
            del events_window
            strongest_effect = max(
                abs(float(migration_result.get("effect_size", 0.0))),
                abs(float(rebellion_result.get("effect_size", 0.0))),
            )
            if _cohort_candidate_priority(migration_result, rebellion_result, turn) > _cohort_candidate_priority(
                best_migration_result or {},
                best_rebellion_result or {},
                best_turn or 10**9,
            ):
                best_turn = turn
                best_strongest_effect = strongest_effect
                best_migration_result = migration_result
                best_rebellion_result = rebellion_result
                best_members = members
        if best_turn is None or best_migration_result is None or best_rebellion_result is None:
            continue
        analyzed_seeds += 1
        expected = (
            best_migration_result.get("effect_direction") == "community_lower"
            or best_rebellion_result.get("effect_direction") == "community_higher"
        )
        effect_sizes.append(best_strongest_effect)
        if expected and best_strongest_effect > 0.10:
            seeds_with_expected_direction += 1
        record = {
            "seed": run.get("seed"),
            "snapshot_turn": best_turn,
            "communities_analyzed": best_migration_result.get("communities_analyzed", 0),
            "migration_effect_direction": best_migration_result.get("effect_direction"),
            "migration_effect_size": round(float(best_migration_result.get("effect_size", 0.0)), 4),
            "rebellion_effect_direction": best_rebellion_result.get("effect_direction"),
            "rebellion_effect_size": round(float(best_rebellion_result.get("effect_size", 0.0)), 4),
        }
        if censor_at_death:
            # Method 3: the chosen snapshot's matched pairs and those a death cut short.
            record["pairs"] = best_migration_result.get("pairs", 0)
            record["censored_pairs"] = best_migration_result.get("censored_pairs", 0)
        if spec_communities:
            record["members"] = best_members
            chosen_matching["members"] += best_members
            chosen_matching["pairs"] += best_migration_result.get("pairs", 0)
        per_seed.append(record)

    if analyzed_seeds == 0:
        return {"status": "SKIP", "reason": "no_community_seed_pairs"}

    required = required_seed_count(analyzed_seeds, 0.60)
    median_effect_size = statistics.median(effect_sizes) if effect_sizes else 0.0
    result = {
        "status": "PASS" if seeds_with_expected_direction >= required and median_effect_size > 0.10 else "FAIL",
    }
    if outcome_offset:
        # Method 2; method 1 results keep their bytes without these keys.
        result["method_version"] = method_version
        result["outcome_window_start_offset"] = outcome_offset
        result["outcome_window_turns"] = window
    if censor_at_death:
        # Method 3; method 2 results keep their bytes without these keys.
        result["comparison"] = "matched_pairs"
        result["outcome_censoring"] = "first_death_in_pair"
    if spec_communities:
        # Method 6's observational component (method 5's keeps its bytes).
        from .validation_communities import COMMUNITY_ORACLE_METHOD_VERSION
        result["community_method_version"] = COMMUNITY_ORACLE_METHOD_VERSION
    result.update({
        "analyzed_seeds": analyzed_seeds,
        "required_seed_count": required,
        "seeds_with_expected_direction": seeds_with_expected_direction,
        "median_effect_size": median_effect_size,
    })
    if spec_communities:
        members, pairs = matching["members"], matching["pairs"]
        result["matching"] = {
            "rule": "each member with a non-member of the same civ affinity, region and occupation, "
                    "satisfaction within 0.10 (method 3)",
            "snapshots": matching["snapshots"],
            "members": members,
            "matched_members": pairs,
            "match_rate": round(pairs / members, 4) if members else None,
            "mean_satisfaction_gap": round(matching["satisfaction_gap"] / pairs, 4) if pairs else None,
            "chosen_snapshots": {
                "members": chosen_matching["members"],
                "matched_members": chosen_matching["pairs"],
                "match_rate": (round(chosen_matching["pairs"] / chosen_matching["members"], 4)
                               if chosen_matching["members"] else None),
            },
        }
    result["per_seed"] = per_seed
    return result


ORACLE_RUNNER_NAMES = {
    "determinism",
    "community",
    "needs",
    "era",
    "cohort",
    "artifacts",
    "arcs",
    "regression",
}
SEED_RUN_ORACLE_NAMES = ORACLE_RUNNER_NAMES - {"determinism"}
# The module-level function that runs each oracle of ``run_oracles``.
_ORACLE_FUNCTION_NAMES = MappingProxyType({
    "determinism": "run_determinism_gate",
    "community": "run_community_oracle",
    "needs": "run_needs_oracle",
    "era": "run_era_oracle",
    "cohort": "run_cohort_oracle",
    "artifacts": "run_artifact_oracle",
    "arcs": "run_arc_oracle",
    "regression": "run_regression_summary",
})


class _ModuleRunners:
    """A module's oracle functions as the registry of ``_run_oracles``: each
    is read from the module when its oracle runs, so a patch of
    ``validation_io.run_needs_oracle`` reaches ``validation_io.run_oracles``.
    (``validate.run_oracles`` dispatches through ``validate.ORACLE_RUNNERS``.)"""

    __slots__ = ("module",)

    def __init__(self, module):
        self.module = module

    def __getitem__(self, oracle_name: str):
        return getattr(self.module, _ORACLE_FUNCTION_NAMES[oracle_name])


def _normalize_oracle_selection(oracles: list[str], names) -> set[str]:
    """The oracles ``oracles`` selects among ``names`` (``all``: every one)."""
    selected = set(oracles)
    allowed = set(names) | {"all"}
    unknown = sorted(selected - allowed)
    if unknown:
        raise ValidationRequestError(f"unknown_oracles: {', '.join(unknown)}")
    if "all" in selected:
        if len(selected) > 1:
            raise ValidationRequestError("all cannot be combined with explicit oracles")
        return set(names)
    return selected


def _normalize_requested_oracles(oracles: list[str]) -> set[str]:
    return _normalize_oracle_selection(oracles, ORACLE_RUNNER_NAMES)


def _run_oracles(
    surface,
    runners,
    seed_run_oracles: set[str],
    batch_dir: Path,
    oracles: list[str],
    profile: str | None,
    *,
    legacy_batch: bool,
    ablation_dir: Path | None,
    require_causal: bool | None,
) -> dict:
    """The orchestration of both ``validate.run_oracles`` and
    ``validation_io.run_oracles`` (docs/integration/validation-split.md).

    ``surface`` is the calling module. Its ``causal_oracles_required``,
    ``_normalize_requested_oracles``, ``_prepare_batch_admission``,
    ``_load_arms``, ``load_seed_runs``, ``ablation_methods``,
    ``summarize_world_shapes`` and ``run_determinism_gate`` are read from it
    when they are used, so a patch of one module's attribute reaches only
    that module's ``run_oracles``. ``runners`` maps each selected oracle to
    its runner (``validate.ORACLE_RUNNERS``, or ``_ModuleRunners``);
    ``seed_run_oracles`` are the oracles that read seed runs. A determinism
    runner other than ``surface.run_determinism_gate`` keeps the standalone
    ``runner(batch_dir)`` signature, after the admission has observed every
    bundle.
    """
    require_causal = surface.causal_oracles_required(None, require_causal)
    selected = surface._normalize_requested_oracles(oracles)
    admission = surface._prepare_batch_admission(batch_dir, legacy_batch=legacy_batch)
    arms, ablation_summary = surface._load_arms(ablation_dir, batch_dir)
    results: dict[str, dict] = {}
    seed_runs: list[dict] | None = None

    def ensure_seed_runs() -> list[dict]:
        nonlocal seed_runs
        if seed_runs is None:
            seed_runs = surface.load_seed_runs(
                batch_dir, selected_oracles=selected & seed_run_oracles, _admission=admission)
        return seed_runs

    for oracle_name in sorted(selected):
        runner = runners[oracle_name]
        try:
            if oracle_name == "determinism":
                if runner is surface.run_determinism_gate:
                    results[oracle_name] = runner(batch_dir, _admission=admission)
                else:
                    # Preserve the registry's standalone runner signature.
                    admission.finish()
                    results[oracle_name] = runner(batch_dir)
            elif oracle_name == "needs":
                results[oracle_name] = runner(
                    ensure_seed_runs(), profile=profile, ablation=arms.get("needs"), placebo=arms.get("placebo"),
                    require_causal=require_causal, method_version=surface.ablation_methods(ablation_summary)[0])
            elif oracle_name == "cohort":
                results[oracle_name] = runner(
                    ensure_seed_runs(), ablation=arms.get("kin_roots"), placebo=arms.get("placebo"),
                    community=arms.get("community_anchor"), require_causal=require_causal,
                    method_version=surface.ablation_methods(ablation_summary)[1])
            else:
                results[oracle_name] = runner(ensure_seed_runs())
        except (ValidationRequestError, ValidationDependencyError):
            raise
        except Exception as exc:
            results[oracle_name] = {
                "status": "ERROR",
                "reason": f"{type(exc).__name__}: {exc}",
            }

    report = {
        "batch_dir": str(batch_dir),
        "oracles": sorted(selected),
        "results": results,
    }
    # Non-template worlds are named in the report so that a comparison
    # cannot mix them with template reports (template reports keep their bytes).
    worlds = surface.summarize_world_shapes(seed_runs) if seed_runs is not None else None
    if worlds is not None:
        report["worlds"] = worlds
    report["batch_manifest"] = admission.finish()
    if ablation_summary is not None:
        report["ablation_arms"] = ablation_summary
    if profile is not None:
        report["profile"] = profile
    report["causal_oracles_required"] = require_causal
    return report


def run_oracles(
    batch_dir: Path,
    oracles: list[str],
    profile: str | None = None,
    *,
    legacy_batch: bool = False,
    ablation_dir: Path | None = None,
    require_causal: bool | None = None,
) -> dict:
    """Run specified oracles and return a structured report (``profile``:
    the gate profile the needs oracle scores for; None requires its binding
    component). The batch directory is first checked against its manifest
    (``check_batch_manifest``; ``legacy_batch`` admits one without), and the
    ablation arms of ``ablation_dir`` against theirs and the batch
    (``validation_ablation.load_ablation_arms``). ``require_causal``: whether
    the ablation components decide (default ``CAUSAL_ORACLES_REQUIRED``;
    recorded as ``causal_oracles_required``)."""
    module = sys.modules[__name__]
    return _run_oracles(module, _ModuleRunners(module), SEED_RUN_ORACLE_NAMES, batch_dir, oracles, profile,
                        legacy_batch=legacy_batch, ablation_dir=ablation_dir, require_causal=require_causal)

ABLATION_DIR_FLAG = "--ablation-dir"


def ablation_methods(ablation_summary: dict | None) -> tuple[int, int]:
    """(needs, cohort) method versions for arms with this report summary
    (``_load_arms``): design 1 arms are scored by needs method 7 and cohort
    method 4, design 2 arms and a batch without arms by the current ones."""
    if ablation_summary is not None and ablation_summary.get("design", 1) == 1:
        return NEEDS_ABLATION_DESIGN1_METHOD_VERSION, COHORT_ABLATION_DESIGN1_METHOD_VERSION
    return NEEDS_ORACLE_METHOD_VERSION, COHORT_ORACLE_METHOD_VERSION


def _load_arms(ablation_dir: Path | None, batch_dir: Path) -> tuple[dict, dict | None]:
    """Arms by name and the report's ``ablation_arms`` entry (None without a directory)."""
    if ablation_dir is None:
        return {}, None
    from .validation_ablation import AblationInputError, load_ablation_arms
    if not _has_pyarrow():
        raise ValidationDependencyError("ablation arms require pyarrow")
    try:
        loaded = load_ablation_arms(Path(ablation_dir), Path(batch_dir))
    except (AblationInputError, OSError, ValueError, KeyError) as exc:
        raise ValidationRequestError(f"ablation arms {ablation_dir}: {exc}") from exc
    return loaded["arms"], loaded["summary"]


def _error_report(batch_dir: Path, oracles: list[str], reason: str) -> dict:
    return {
        "batch_dir": str(batch_dir),
        "oracles": list(oracles),
        "results": {},
        "status": "ERROR",
        "reason": reason,
    }


def _dump_report(report: dict) -> None:
    sys.stdout.write(strict_json_dumps(report))


def _serialization_error_report(batch_dir: Path, oracles: list[str], exc: ArtifactIOError) -> dict:
    return _error_report(batch_dir, oracles, f"could not serialize validation report: {exc}")


def _cli_main(surface, argv: list[str] | None, *, causal_help: str) -> int:
    """The CLI of both ``python -m chronicler.validate`` and ``python -m
    chronicler.validation_io``. ``surface`` is the calling module: its
    ``run_oracles``, ``_dump_report``, ``_error_report`` and
    ``_serialization_error_report`` are read from it when used.
    ``causal_help`` is that CLI's ``--require-causal-oracles`` help (the
    two differ; docs/integration/validation-split.md)."""
    parser = argparse.ArgumentParser(description="M53b validation oracle runner")
    parser.add_argument("--batch-dir", required=True, type=Path)
    parser.add_argument("--oracles", nargs="+", default=["all"])
    parser.add_argument("--profile", choices=PROFILE_CHOICES, default=None,
                        help="gate profile the needs oracle scores for (default: binding required)")
    parser.add_argument(LEGACY_BATCH_FLAG, action="store_true",
                        help=f"validate a directory without {MANIFEST_FILENAME} (written before manifests, "
                             "or a single bundle); its runs are not checked")
    parser.add_argument(ABLATION_DIR_FLAG, type=Path, default=None,
                        help="the batch's ablation arms (chronicler.ablation_arms): the needs oracle's "
                             "ablation component and the cohort oracle read them")
    parser.add_argument(CAUSAL_ORACLES_FLAG, action=argparse.BooleanOptionalAction, default=None,
                        help=causal_help)
    args = parser.parse_args(argv)
    try:
        report = surface.run_oracles(args.batch_dir, args.oracles, profile=args.profile,
                                     legacy_batch=args.legacy_batch, ablation_dir=args.ablation_dir,
                                     require_causal=args.require_causal_oracles)
    except (ValidationRequestError, ValidationDependencyError) as exc:
        surface._dump_report(surface._error_report(args.batch_dir, args.oracles, str(exc)))
        return 1
    try:
        surface._dump_report(report)
    except ArtifactIOError as exc:
        surface._dump_report(surface._serialization_error_report(args.batch_dir, args.oracles, exc))
        return 1
    if any(result.get("status") == "ERROR" for result in report["results"].values()):
        return 1
    return 0


# This CLI's --require-causal-oracles help names the design-1 methods;
# validate's names needs method 8 and cohort method 5. Each keeps its text.
_CAUSAL_ORACLES_HELP = ("let the ablation components (needs method 7, cohort method 4) decide "
                        "(default: validation_gate.CAUSAL_ORACLES_REQUIRED, off: they are reported as "
                        "causal evidence, not yet required)")


def main(argv: list[str] | None = None) -> int:
    return _cli_main(sys.modules[__name__], argv, causal_help=_CAUSAL_ORACLES_HELP)

if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ['SCRUB_KEYS', 'BUNDLE_FILENAME', 'EVENT_NAME_TO_CODE', 'ValidationRequestError', 'ValidationDependencyError', '_has_pyarrow', '_iter_seed_dirs', '_requires_pyarrow_for_selected_inputs', 'scrubbed_equal', 'load_bundles', 'required_seed_count', '_read_json', '_snapshot_turns', '_choose_snapshot_turn', '_load_graph_snapshot', '_load_needs_snapshot', '_read_arrow_columns', '_load_canonical_graph_snapshot', '_load_canonical_needs_snapshot', '_available_turns_from_columns', '_sample_turns', '_columns_for_turn', '_graph_snapshot_from_columns', '_needs_snapshot_from_columns', '_load_validation_summary', '_load_validation_community_summary', '_load_agent_events', '_world_population_series', '_civ_trajectories', 'load_seed_runs', '_total_turns', '_iter_graph_snapshots', '_iter_needs_snapshots', '_iter_joint_sample_turns', '_filter_events_window', '_mean', '_cohen_d', '_collapse_nearby_points', '_trajectory_metric_series', '_trajectory_composite_series', '_smoothed_series', '_significant_slope_pattern', '_agent_count_by_turn', '_final_ginis_from_validation_summary', 'detect_communities', 'compute_needs_diversity', '_needs_candidate_priority', 'detect_inflection_points', 'detect_collapse_episodes', 'compute_cohort_distinctiveness', '_cohort_candidate_priority', 'check_artifact_lifecycle', '_legacy_classify_civ_arc', '_classify_series_by_thirds', 'classify_civ_arc', 'run_determinism_gate', 'run_community_oracle', 'run_needs_oracle', 'run_needs_oracle_best_of', 'run_era_oracle', 'run_cohort_oracle', 'needs_method_7_result', 'cohort_method_4_result', 'needs_ablation_method_result', 'cohort_ablation_method_result', 'ablation_methods', 'run_artifact_oracle', 'run_arc_oracle', 'run_regression_summary', 'run_oracles', 'check_batch_manifest', 'LEGACY_BATCH_FLAG', 'main']
