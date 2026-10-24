"""M65b Political Stress Index and the M67 regime classifiers (pure functions).

Turchin's structural-demographic PSI is the product of three sub-indices:

* MMP, mass mobilization potential: ``(1 / relative_wage) * urbanization *
  youth_bulge`` with ``relative_wage = median_wealth / mean_wealth``.
* EMP, elite mobilization potential: ``frustrated_aspirants / elite_positions *
  conspicuous_consumption_index`` (computed by the M65a kernel).
* SFD, state fiscal distress: ``governing_cost / treasury * (1 +
  enforcement_ratio * (1 - institutional_legitimacy))`` (roadmap decision D5).

The raw roadmap quantities have unrelated scales, so each is divided by a
reference scale, clamped and smoothed with a short EMA before composition::

    PSI = (floor + s_mmp)^a * (floor + s_emp)^b * (floor + s_sfd)^c

The ``floor`` is the runtime's explicit answer to the roadmap's "multiplicative
calibration cliff" (risk R5): a single absent sub-index halves the indicator
instead of zeroing it, while a crisis still needs at least two elevated
sub-indices. Exponents default to 1.0 (decision D6). All constants are
runtime calibration, documented in ``docs/governance/runtime-integration.md``.

Nothing here reads simulation state; callers pass plain numbers.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


@dataclass(frozen=True)
class StressCalibration:
    mmp_reference: float = 0.10
    emp_reference: float = 2.0
    sfd_reference: float = 0.04
    subindex_cap: float = 4.0
    floor: float = 0.5
    exponent_mmp: float = 1.0
    exponent_emp: float = 1.0
    exponent_sfd: float = 1.0
    smoothing_alpha: float = 0.2
    crisis_threshold: float = 2.6
    recovery_threshold: float = 1.7
    elevated_subindex: float = 1.0
    youth_min_age: int = 15
    youth_max_age: int = 30


DEFAULT_STRESS = StressCalibration()


def _finite(value: float, default: float = 0.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def mmp_components(relative_wage: float, urbanization: float, youth: float) -> float:
    """Raw roadmap MMP from already-extracted fractions."""
    relative_wage = max(_finite(relative_wage, 1.0), 0.01)
    return (1.0 / relative_wage) * min(max(_finite(urbanization), 0.0), 1.0) * min(max(_finite(youth), 0.0), 1.0)


def mmp_from_agents(wealth: Sequence[float], ages: Sequence[int], settlement_ids: Sequence[int],
                    calibration: StressCalibration = DEFAULT_STRESS) -> tuple[float, float, float, float]:
    """Return ``(mmp, relative_wage, urbanization, youth)`` from one civ's rows.

    ``settlement_id`` 0 means "not in a detected settlement" (the snapshot's
    sentinel); any other value counts as urban.
    """
    n = len(wealth)
    if n == 0:
        return 0.0, 1.0, 0.0, 0.0
    ordered = sorted(_finite(w) for w in wealth)
    mid = n // 2
    median = ordered[mid] if n % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])
    mean = math.fsum(ordered) / n
    relative_wage = (median / mean) if mean > 0 else 1.0
    urbanization = sum(1 for s in settlement_ids if s) / n
    youth = sum(1 for a in ages if calibration.youth_min_age <= a <= calibration.youth_max_age) / n
    return mmp_components(relative_wage, urbanization, youth), relative_wage, urbanization, youth


def mmp_from_agent_arrays(wealth, ages, settlement_ids,
                          calibration: StressCalibration = DEFAULT_STRESS) -> tuple[float, float, float, float]:
    """``mmp_from_agents`` on NumPy columns, with the same result.

    The sorted values and their exact ``fsum`` are the same; equal values may
    sit in another order, which only the sign of a zero median could show, and
    ``mmp_components`` floors a zero relative wage either way.
    """
    import numpy as np

    n = len(wealth)
    if n == 0:
        return 0.0, 1.0, 0.0, 0.0
    values = np.asarray(wealth, dtype=np.float64)
    ordered = np.sort(np.where(np.isfinite(values), values, 0.0))
    mid = n // 2
    median = float(ordered[mid]) if n % 2 else 0.5 * (float(ordered[mid - 1]) + float(ordered[mid]))
    mean = math.fsum(ordered.tolist()) / n
    relative_wage = (median / mean) if mean > 0 else 1.0
    urbanization = int(np.count_nonzero(np.asarray(settlement_ids))) / n
    ages = np.asarray(ages)
    youth = int(np.count_nonzero((ages >= calibration.youth_min_age)
                                 & (ages <= calibration.youth_max_age))) / n
    return mmp_components(relative_wage, urbanization, youth), relative_wage, urbanization, youth


def sfd_raw(governing_cost: float, treasury: float, enforcement_cost: float,
            institutional_legitimacy: float) -> float:
    """Roadmap D5 proxy: no-institution polities are neutral, not distressed."""
    denominator = max(_finite(treasury), 1.0)
    fiscal_ratio = max(_finite(governing_cost), 0.0) / denominator
    enforcement_ratio = max(_finite(enforcement_cost), 0.0) / denominator
    legitimacy = min(max(_finite(institutional_legitimacy, 1.0), 0.0), 1.0)
    return fiscal_ratio * (1.0 + enforcement_ratio * (1.0 - legitimacy))


def normalize(raw: float, reference: float, cap: float) -> float:
    if reference <= 0:
        return 0.0
    return min(max(_finite(raw) / reference, 0.0), cap)


def smooth(previous: float, raw: float, alpha: float) -> float:
    """EMA ``lerp(previous, raw, alpha)``."""
    return previous + (raw - previous) * alpha


def compose_psi(mmp: float, emp: float, sfd: float,
                calibration: StressCalibration = DEFAULT_STRESS) -> float:
    f = calibration.floor
    return ((f + mmp) ** calibration.exponent_mmp
            * (f + emp) ** calibration.exponent_emp
            * (f + sfd) ** calibration.exponent_sfd)


def update_crisis(in_crisis: bool, psi: float, calibration: StressCalibration = DEFAULT_STRESS) -> bool:
    """Hysteresis: enter above the crisis threshold, leave below recovery."""
    if in_crisis:
        return psi >= calibration.recovery_threshold
    return psi > calibration.crisis_threshold


@dataclass(frozen=True)
class StressUpdate:
    mmp: float
    emp: float
    sfd: float
    psi: float
    crisis: bool


def advance_stress(previous: tuple[float, float, float], raw: tuple[float, float, float],
                   in_crisis: bool, calibration: StressCalibration = DEFAULT_STRESS) -> StressUpdate:
    """Normalize, smooth and compose one turn of PSI from raw sub-indices."""
    refs = (calibration.mmp_reference, calibration.emp_reference, calibration.sfd_reference)
    smoothed = tuple(
        smooth(prev, normalize(value, ref, calibration.subindex_cap), calibration.smoothing_alpha)
        for prev, value, ref in zip(previous, raw, refs)
    )
    psi = compose_psi(*smoothed, calibration=calibration)
    return StressUpdate(smoothed[0], smoothed[1], smoothed[2], psi, update_crisis(in_crisis, psi, calibration))


# --- M67 institutional regime classifier -----------------------------------

REGIME_WINDOW = 100
REGIME_MIN_SPAN = 30
FLUCTUATING_MAX_TENURE = 10.0
FLUCTUATING_MIN_CHANGES = 4
CYCLING_MIN_CHANGES = 3


@dataclass(frozen=True)
class RegimeMetrics:
    label: str
    span: int
    changes: int
    changes_per_100: float
    mean_tenure: float | None
    mean_active: float
    distinct_configurations: int


def classify_institutional_regime(
    log: Iterable[Sequence], active: dict[str, int], turn: int, start_turn: int,
    window: int = REGIME_WINDOW,
) -> RegimeMetrics:
    """Label a civ's trailing-window institutional regime.

    Conventions (the M67 preregistration left these open; locked here):

    * Window: trailing ``window`` turns ending at ``turn``, clipped at the civ's
      governance start; fewer than ``REGIME_MIN_SPAN`` observed turns is
      ``nascent``. "Per 100 turns" rates are scaled to the observed span.
    * An institution change is any enactment, forced repeal or neglect collapse.
    * Tenure: completed spells that ended inside the window plus active spells
      censored at ``turn`` (a lower bound). Spells may start before the window.
    * Mean active count is the time-average over the window.
    * Labels are mutually exclusive with precedence fluctuating > cycling >
      frozen > inert > transitional.

    ``log`` holds ``[turn, institution_type, kind]`` entries in turn order with
    kind ``enacted``, ``repealed`` or ``collapsed``; ``active`` maps the active
    institution types to their enacted turn.
    """
    window_start = max(start_turn, turn - window + 1)
    span = turn - window_start + 1
    history = [(int(e[0]), str(e[1]), str(e[2])) for e in log]
    entries = [e for e in history if e[0] >= window_start]
    changes = len(entries)
    rate = changes * 100.0 / max(span, 1)

    # Tenure: completed spells ending inside the window (start from the full
    # retained log; spells whose start was truncated away are skipped) plus
    # active spells censored at ``turn``.
    tenures: list[float] = [float(turn - enacted) for enacted in active.values()]
    enacted_at: dict[str, int] = {}
    for e_turn, e_type, kind in history:
        if kind == "enacted":
            enacted_at[e_type] = e_turn
        elif e_type in enacted_at:
            start = enacted_at.pop(e_type)
            if e_turn >= window_start:
                tenures.append(float(e_turn - start))

    # Changes resolve late in turn t and are effective from t+1. Undo them from
    # newest to oldest to recover the configuration of every window segment.
    config = set(active)
    segments: list[tuple[int, int, frozenset]] = []
    seg_end = turn + 1  # exclusive
    for e_turn, e_type, kind in reversed(entries):
        seg_start = e_turn + 1
        segments.append((seg_start, seg_end, frozenset(config)))
        if kind == "enacted":
            config.discard(e_type)
        else:
            config.add(e_type)
        seg_end = seg_start
    segments.append((window_start, seg_end, frozenset(config)))
    active_area = 0.0
    configurations: set[frozenset] = set()
    for seg_start, seg_stop, cfg in segments:
        length = max(0, min(seg_stop, turn + 1) - max(seg_start, window_start))
        if length:
            active_area += length * len(cfg)
            configurations.add(cfg)
    mean_active = active_area / max(span, 1)
    mean_tenure = (sum(tenures) / len(tenures)) if tenures else None

    if span < REGIME_MIN_SPAN:
        label = "nascent"
    elif (mean_tenure is not None and mean_tenure < FLUCTUATING_MAX_TENURE
          and changes >= FLUCTUATING_MIN_CHANGES):
        label = "highly_fluctuating"
    elif changes >= CYCLING_MIN_CHANGES and len(configurations) >= 2:
        label = "complex_cycling"
    elif rate <= 1.0 and mean_active >= 1.0:
        label = "frozen_stable"
    elif rate <= 1.0:
        label = "inert"
    else:
        label = "transitional"
    return RegimeMetrics(label, span, changes, rate, mean_tenure, mean_active, len(configurations))


# --- Secular-cycle phase label ---------------------------------------------

DEPRESSION_TURNS = 30
RECOVERY_TURNS = 100


def classify_cycle_phase(psi_history: Sequence[float], in_crisis: bool, turn: int,
                         last_crisis_end: int | None,
                         calibration: StressCalibration = DEFAULT_STRESS) -> str:
    """Turchin phase label: integrative, stagflation, crisis, depression, recovery."""
    if in_crisis:
        return "crisis"
    if last_crisis_end is not None and turn - last_crisis_end <= DEPRESSION_TURNS:
        return "depression"
    psi = psi_history[-1] if psi_history else 0.0
    rising = len(psi_history) >= 10 and psi_history[-1] > psi_history[-10]
    if psi >= 0.75 * calibration.crisis_threshold and rising:
        return "stagflation"
    if last_crisis_end is not None and turn - last_crisis_end <= RECOVERY_TURNS:
        return "recovery"
    return "integrative"
