"""Validation oracle algorithm re-exports.

The implementations currently live in ``validation_io`` to preserve the
recovered pre-split behavior and keep monkeypatch targets such as
``chronicler.validation_io._load_agent_events`` effective.
"""

from __future__ import annotations

from .validation_io import (
    detect_communities,
    compute_needs_diversity,
    _needs_candidate_priority,
    detect_inflection_points,
    compute_cohort_distinctiveness,
    _cohort_candidate_priority,
    check_artifact_lifecycle,
    _legacy_classify_civ_arc,
    _classify_series_by_thirds,
    classify_civ_arc,
    run_determinism_gate,
    run_community_oracle,
    run_needs_oracle,
    run_era_oracle,
    run_cohort_oracle,
    run_artifact_oracle,
    run_arc_oracle,
    run_regression_summary,
)

__all__ = ['detect_communities', 'compute_needs_diversity', '_needs_candidate_priority', 'detect_inflection_points', 'compute_cohort_distinctiveness', '_cohort_candidate_priority', 'check_artifact_lifecycle', '_legacy_classify_civ_arc', '_classify_series_by_thirds', 'classify_civ_arc', 'run_determinism_gate', 'run_community_oracle', 'run_needs_oracle', 'run_era_oracle', 'run_cohort_oracle', 'run_artifact_oracle', 'run_arc_oracle', 'run_regression_summary']
