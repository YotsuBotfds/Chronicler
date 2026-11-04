"""The artifact oracle (M53 oracle 5): artifact creation and loss rates and
type diversity over a batch's final world states.

Split out of ``validation_io`` verbatim; ``validation_io`` re-exports every
name here (docs/integration/validation-split.md).
"""
from __future__ import annotations


# Full-gate balance uses strict historical thresholds plus explicitly reported
# calibrated tolerances for stochastic 500-turn batches.  The tolerance path is
# meant to distinguish near-threshold control-compatible drift from oracle errors
# without hiding the raw metric or whether the strict floor was missed.
ARTIFACT_CREATION_RATE_MIN = 1.00
ARTIFACT_CREATION_RATE_TOLERANCE_MIN = 0.90
ARTIFACT_CREATION_RATE_MAX = 3.00
# Recalibrated 2026-10 for living worlds (docs/integration/extinction-fix-2026-10.md):
# the old 10% floor was met only through extinction-era turnover (civs dying
# without an absorber mark every artifact LOST). Living 500-turn worlds lose
# 2-3%; a broken lifecycle loses ~0%, which the floor plus loss_channels_ok
# (both LOST and DESTROYED present) still rejects. The 30% ceiling is unchanged.
# Starting civs of the template world, the artifact creation band's
# denominator when a seed run records no world shape.
ARTIFACT_TEMPLATE_STARTING_CIVS = 4
ARTIFACT_LOSS_RATE_MIN = 0.02
ARTIFACT_LOSS_RATE_MAX = 0.30


def check_artifact_lifecycle(
    bundles: list[dict],
    num_civs: int = 4,
    starting_civs: list[int] | None = None,
) -> dict:
    """Oracle 5: Validate artifact lifecycle rates and diversity.

    Sub-check A (bundle-only):
    - Creation rate per civ per 100 turns should strictly be in 1-3 range;
      rates in 0.90-1.00 are accepted through an explicit stochastic-tolerance
      adjudication so duplicate-suppressed long-horizon batches do not fail on
      near-threshold noise while still reporting the strict miss.
    - No single artifact_type should exceed 50% of total.
    - Loss/destruction rate ((lost + destroyed) / total) should be 2-30%,
      with both channels alive: at least one LOST and one DESTROYED
      artifact in the batch (``loss_channels_ok``). The old 10% floor was
      only ever met through extinction-era turnover; see
      docs/integration/extinction-fix-2026-10.md.

    Parameters
    ----------
    bundles:
        List of bundle dicts, each containing world_state.artifacts and
        metadata.total_turns.
    num_civs:
        Number of civilizations (used as denominator for creation rate).
    starting_civs:
        Optional starting civilizations per bundle (aligned with ``bundles``),
        used instead of ``num_civs``: the rate is artifacts per starting civ
        per 100 turns whatever the world size. The band was calibrated on the
        4-civ template world, where both give the same denominator.

    Returns
    -------
    dict with keys:
        creation_rate_per_civ_per_100  – float
        creation_rate_ok               – bool (strict [1, 3] or calibrated [0.90, 3])
        type_diversity_ok              – bool (no single type > 50%)
        loss_destruction_count         – int
        loss_destruction_rate          – float
        loss_destruction_rate_ok       – bool (rate in [0.02, 0.30])
        lost_count / destroyed_count   – int
        loss_channels_ok               – bool (both counts > 0)
        mule_artifact_count            – int
        total_artifacts                – int
    """
    total_artifacts = 0
    loss_destruction_count = 0
    lost_count = 0
    destroyed_count = 0
    mule_artifact_count = 0
    total_turns_sum = 0
    type_counts: dict[str, int] = {}

    if starting_civs is not None and len(starting_civs) != len(bundles):
        raise ValueError("starting_civs must have one entry per bundle")
    civ_turns_sum = 0
    for index, bundle in enumerate(bundles):
        artifacts = bundle.get("world_state", {}).get("artifacts", [])
        total_turns = bundle.get("metadata", {}).get("total_turns", 0)
        total_turns_sum += total_turns
        civ_turns_sum += (starting_civs[index] if starting_civs is not None else num_civs) * total_turns

        for art in artifacts:
            total_artifacts += 1
            artifact_type = art.get("artifact_type", "unknown")
            type_counts[artifact_type] = type_counts.get(artifact_type, 0) + 1

            status = art.get("status", "active")
            if status in ("destroyed", "lost"):
                loss_destruction_count += 1
                if status == "lost":
                    lost_count += 1
                else:
                    destroyed_count += 1

            if art.get("mule_origin", False):
                mule_artifact_count += 1

    # Creation rate: artifacts per civ per 100 turns
    if civ_turns_sum > 0 and total_turns_sum > 0:
        creation_rate = total_artifacts / (civ_turns_sum / 100.0)
    else:
        creation_rate = 0.0

    creation_rate_strict_ok = ARTIFACT_CREATION_RATE_MIN <= creation_rate <= ARTIFACT_CREATION_RATE_MAX
    creation_rate_tolerance_ok = (
        ARTIFACT_CREATION_RATE_TOLERANCE_MIN
        <= creation_rate
        <= ARTIFACT_CREATION_RATE_MAX
    )
    creation_rate_ok = creation_rate_strict_ok or creation_rate_tolerance_ok
    creation_rate_adjudication = (
        "strict"
        if creation_rate_strict_ok else "stochastic_tolerance"
        if creation_rate_tolerance_ok else "fail"
    )

    # Type diversity: no single type > 50% of total
    if total_artifacts > 0:
        max_type_fraction = max(type_counts.values()) / total_artifacts
        type_diversity_ok = max_type_fraction <= 0.5
    else:
        type_diversity_ok = True

    # Loss/destruction rate: (lost + destroyed) / total
    if total_artifacts > 0:
        loss_destruction_rate = loss_destruction_count / total_artifacts
    else:
        loss_destruction_rate = 0.0

    loss_destruction_rate_ok = (
        ARTIFACT_LOSS_RATE_MIN <= loss_destruction_rate <= ARTIFACT_LOSS_RATE_MAX
    )
    loss_channels_ok = lost_count > 0 and destroyed_count > 0

    return {
        "creation_rate_per_civ_per_100": creation_rate,
        "creation_rate_ok": creation_rate_ok,
        "creation_rate_strict_ok": creation_rate_strict_ok,
        "creation_rate_adjudication": creation_rate_adjudication,
        "type_diversity_ok": type_diversity_ok,
        "loss_destruction_count": loss_destruction_count,
        "loss_destruction_rate": loss_destruction_rate,
        "loss_destruction_rate_ok": loss_destruction_rate_ok,
        "lost_count": lost_count,
        "destroyed_count": destroyed_count,
        "loss_channels_ok": loss_channels_ok,
        "mule_artifact_count": mule_artifact_count,
        "total_artifacts": total_artifacts,
    }


def run_artifact_oracle(seed_runs: list[dict]) -> dict:
    bundles = [run["bundle"] for run in seed_runs]
    if not bundles:
        return {"status": "SKIP", "reason": "no_bundles"}
    # Per starting civ: procedural worlds start with more than the template
    # world's 4 civs (docs/integration/procedural-gates.md).
    starting_civs = [
        int((run.get("world") or {}).get("civs") or ARTIFACT_TEMPLATE_STARTING_CIVS)
        for run in seed_runs
    ]
    result = check_artifact_lifecycle(bundles, starting_civs=starting_civs)
    all_pass = (
        result["creation_rate_ok"]
        and result["type_diversity_ok"]
        and result["loss_destruction_rate_ok"]
        and result["loss_channels_ok"]
    )
    any_pass = (
        result["creation_rate_ok"]
        or result["type_diversity_ok"]
        or result["loss_destruction_rate_ok"]
    )
    return {
        "status": "PASS" if all_pass else ("PARTIAL" if any_pass else "FAIL"),
        **result,
    }
