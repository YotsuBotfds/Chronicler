"""Validation oracle algorithm re-exports.

Every name here comes from ``validation_io`` (the same objects). The era and
arc, artifact and regression oracles are defined in
``validation_trajectories``, ``validation_artifacts`` and
``validation_regression``; the others stay in ``validation_io``,
where tests patch the helpers they call (for example
``chronicler.validation_io._read_arrow_columns``) and where the needs,
community and cohort runners re-enter themselves
(docs/integration/validation-split.md).
"""

from __future__ import annotations

from .validation_io import (
    detect_communities,
    compute_needs_diversity,
    _needs_candidate_priority,
    detect_inflection_points,
    detect_collapse_episodes,
    compute_cohort_distinctiveness,
    _cohort_candidate_priority,
    check_artifact_lifecycle,
    _legacy_classify_civ_arc,
    _classify_series_by_thirds,
    classify_civ_arc,
    run_determinism_gate,
    run_community_oracle,
    run_needs_oracle,
    run_needs_oracle_best_of,
    run_era_oracle,
    run_cohort_oracle,
    run_artifact_oracle,
    run_arc_oracle,
    run_regression_summary,
)

__all__ = ['detect_communities', 'compute_needs_diversity', '_needs_candidate_priority', 'detect_inflection_points', 'detect_collapse_episodes', 'compute_cohort_distinctiveness', '_cohort_candidate_priority', 'check_artifact_lifecycle', '_legacy_classify_civ_arc', '_classify_series_by_thirds', 'classify_civ_arc', 'run_determinism_gate', 'run_community_oracle', 'run_needs_oracle', 'run_needs_oracle_best_of', 'run_era_oracle', 'run_cohort_oracle', 'run_artifact_oracle', 'run_arc_oracle', 'run_regression_summary']
