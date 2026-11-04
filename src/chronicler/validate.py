"""Validation CLI facade with backwards-compatible re-exports."""
from __future__ import annotations

import sys
from pathlib import Path

# Re-exported, and the collaborators run_oracles and main read from this module.
from .artifact_io import ArtifactIOError, strict_json_dumps  # noqa: F401
from .validation_gate import CAUSAL_ORACLES_FLAG, PROFILE_CHOICES, causal_oracles_required  # noqa: F401
from .validation_io import *  # noqa: F401,F403
from .validation_io import __all__ as _validation_io_all
from .validation_io import (  # noqa: F401
    ABLATION_DIR_FLAG, LEGACY_BATCH_FLAG, MANIFEST_FILENAME, _load_arms, ablation_methods, check_batch_manifest,
    summarize_world_shapes, _prepare_batch_admission,
)
from .validation_io import (  # noqa: F401
    _cli_main, _dump_report, _error_report, _normalize_oracle_selection, _run_oracles, _serialization_error_report,
)
from .validation_oracles import *  # noqa: F401,F403
from .validation_oracles import __all__ as _validation_oracle_all

ORACLE_RUNNERS = {
    "determinism": run_determinism_gate,
    "community": run_community_oracle,
    "needs": run_needs_oracle,
    "era": run_era_oracle,
    "cohort": run_cohort_oracle,
    "artifacts": run_artifact_oracle,
    "arcs": run_arc_oracle,
    "regression": run_regression_summary,
}

SEED_RUN_ORACLES = set(ORACLE_RUNNERS) - {"determinism"}


def _normalize_requested_oracles(oracles: list[str]) -> set[str]:
    return _normalize_oracle_selection(oracles, ORACLE_RUNNERS)


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
    ablation arms of ``ablation_dir`` against theirs and the batch.
    ``require_causal``: whether the ablation components decide (default
    ``CAUSAL_ORACLES_REQUIRED``; recorded as ``causal_oracles_required``)."""
    # validation_io._run_oracles, dispatching through ORACLE_RUNNERS and
    # reading its other collaborators from this module.
    return _run_oracles(sys.modules[__name__], ORACLE_RUNNERS, SEED_RUN_ORACLES, batch_dir, oracles, profile,
                        legacy_batch=legacy_batch, ablation_dir=ablation_dir, require_causal=require_causal)


# This CLI's --require-causal-oracles help names needs method 8 and cohort
# method 5; validation_io's names the design-1 methods. Each keeps its text.
_CAUSAL_ORACLES_HELP = ("let the ablation components (needs method 8, cohort method 5) decide "
                        "(default: validation_gate.CAUSAL_ORACLES_REQUIRED, off: they are reported as "
                        "causal evidence, not yet required)")


def main(argv: list[str] | None = None) -> int:
    return _cli_main(sys.modules[__name__], argv, causal_help=_CAUSAL_ORACLES_HELP)


__all__ = list(_validation_io_all) + list(_validation_oracle_all) + [
    "ORACLE_RUNNERS",
    "SEED_RUN_ORACLES",
    "_normalize_requested_oracles",
    "run_oracles",
    "_error_report",
    "_dump_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
