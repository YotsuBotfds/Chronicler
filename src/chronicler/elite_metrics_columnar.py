"""Columnar single-civ M65a elite counts (same results as ``elite_metrics``).

``elite_metrics.compute_elite_metrics`` builds one frozen record per agent and
returns every qualifier, office holder and aspirant identity. The live
governance tick only reads the counts, the consumption index and EMP, so at
tens of thousands of agents per civ the per-row records dominated a turn.

``compute_civ_elite_counts`` takes one civ's snapshot rows as NumPy columns
and returns those scalars. It applies the kernel's validation, wealth
percentile, candidate and ranking rules exactly:

* wealth qualifiers: an agent's LOWER (UPPER) rank is the number of the civ's
  rows with strictly smaller (smaller or equal) wealth, which is the start
  (end) of its equal-wealth group in the kernel's sorted order; ``rank / n``
  is the same IEEE division;
* candidates are sorted by the kernel's total order ``(-wealth, kind,
  agent id, GP key)`` with one ``lexsort`` (GP keys enter as their lexical
  rank, agent ids are unique, GP keys are unique after deduplication);
* the counts and the ratchet/EMP arithmetic are the kernel's Python
  expressions on Python ints and floats.

GreatPerson overlays are few and are processed row by row, mirroring the
kernel. ``tests/test_elite_metrics_columnar.py`` checks every output against
``compute_elite_metrics`` on randomized inputs for all conventions.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

import numpy as np

from chronicler.elite_metrics import (
    CivEliteInput,
    EliteCalibration,
    EliteConventions,
    EliteRatchetState,
    EqualWealthOrder,
    GreatPersonEliteInput,
    PositionRounding,
    WealthPercentileConvention,
    _integer,
    _number,
    _validate_configuration,
)

# Snapshot occupation codes of Occupation.MERCHANT/SCHOLAR/PRIEST.
_SKILLED_CODES = (2, 3, 4)


@dataclass(frozen=True)
class CivEliteCounts:
    """The scalar part of ``elite_metrics.CivEliteMetrics``."""

    civ_id: int
    elite_positions: int
    elite_qualifier_count: int
    elite_office_holder_count: int
    frustrated_aspirant_count: int
    conspicuous_consumption_index: float
    emp: float
    next_ratchet_state: EliteRatchetState


def _check_unit(name: str, values: np.ndarray) -> None:
    if values.size and not (np.isfinite(values).all()
                            and (values >= 0).all() and (values <= 1).all()):
        raise ValueError(f"{name} must be in [0, 1]")


def compute_civ_elite_counts(
    *, turn: int, civilization: CivEliteInput,
    agent_ids: np.ndarray, wealth: np.ndarray, occupation: np.ndarray,
    skill: np.ndarray, satisfaction: np.ndarray,
    great_persons: Sequence[GreatPersonEliteInput],
    calibration: EliteCalibration, conventions: EliteConventions,
) -> CivEliteCounts:
    """One civ's ``compute_elite_metrics`` result, from columnar agent rows.

    All rows belong to ``civilization``. ``occupation`` holds the snapshot
    codes 0-4 (``Occupation`` declaration order); ``wealth``, ``skill`` and
    ``satisfaction`` are validated like the kernel's per-row inputs.
    """
    _integer("turn", turn)
    _validate_configuration(calibration, conventions)
    civ = civilization
    _integer("civ_id", civ.civ_id)
    _integer("population", civ.population)
    _integer("previous snapshot_turn", civ.previous_ratchet.snapshot_turn, minimum=-1)
    if civ.previous_ratchet.snapshot_turn != turn - 1:
        raise ValueError("previous ratchet must come from turn N-1")
    _number("previous consumption index",
            civ.previous_ratchet.conspicuous_consumption_index, nonnegative=True)

    ids = np.asarray(agent_ids, dtype=np.int64)
    wealth = np.asarray(wealth, dtype=np.float64)
    occupation = np.asarray(occupation, dtype=np.int64)
    skill = np.asarray(skill, dtype=np.float64)
    satisfaction = np.asarray(satisfaction, dtype=np.float64)
    n = len(ids)
    if not (len(wealth) == len(occupation) == len(skill) == len(satisfaction) == n):
        raise ValueError("agent columns must have equal lengths")
    if n:
        if (ids < 0).any():
            raise ValueError("agent_id must be an integer >= 0")
        if ((occupation < 0) | (occupation > 4)).any():
            raise ValueError("occupation must be an Occupation")
        if not np.isfinite(wealth).all():
            raise ValueError("wealth must be finite")
        _check_unit("skill", skill)
        _check_unit("satisfaction", satisfaction)
    order_by_id = np.argsort(ids, kind="stable")
    sorted_ids = ids[order_by_id]
    if n > 1 and (sorted_ids[1:] == sorted_ids[:-1]).any():
        duplicate = int(sorted_ids[1:][sorted_ids[1:] == sorted_ids[:-1]][0])
        raise ValueError(f"duplicate agent_id {duplicate}")

    def backing_row(agent_id: int) -> int | None:
        pos = int(np.searchsorted(sorted_ids, agent_id))
        if pos < n and int(sorted_ids[pos]) == agent_id:
            return int(order_by_id[pos])
        return None

    # GreatPerson overlays: the kernel's loop, with row lookups by id.
    gp_keys: dict[str, tuple[object, ...]] = {}
    gp_candidates: dict[tuple[str, int | str], tuple[str, float, float]] = {}
    backed_rows: list[int] = []
    for gp in great_persons:
        if not isinstance(gp.great_person_key, str) or not gp.great_person_key:
            raise ValueError("great_person_key must be a nonempty stable string")
        _integer("civ_id", gp.civ_id)
        if gp.civ_id != civ.civ_id:
            raise ValueError(f"unknown civ_id {gp.civ_id}")
        if gp.agent_id is not None:
            _integer("GP agent_id", gp.agent_id)
        row = backing_row(gp.agent_id) if gp.agent_id is not None else None
        if row is not None:
            gp_wealth, gp_satisfaction = float(wealth[row]), float(satisfaction[row])
            backed_rows.append(row)
        else:
            gp_wealth = _number("absent GP wealth", gp.wealth)
            gp_satisfaction = _number("absent GP satisfaction", gp.satisfaction, unit=True)
        signature = (gp.civ_id, gp.agent_id, gp_wealth, gp_satisfaction)
        if gp.great_person_key in gp_keys and gp_keys[gp.great_person_key] != signature:
            raise ValueError("conflicting duplicate GreatPerson key")
        gp_keys[gp.great_person_key] = signature
        if row is not None:
            continue
        key = ("agent", gp.agent_id) if gp.agent_id is not None else ("gp", gp.great_person_key)
        previous = gp_candidates.get(key)
        if previous is not None:
            if (previous[1], previous[2]) != (gp_wealth, gp_satisfaction):
                raise ValueError("conflicting duplicate GreatPerson backing ID")
            if previous[0] < gp.great_person_key:
                continue
        gp_candidates[key] = (gp.great_person_key, gp_wealth, gp_satisfaction)

    # Wealth qualifiers: rank = start (LOWER) or end (UPPER) of the row's
    # equal-wealth group in ascending order.
    if n:
        sorted_wealth = np.sort(wealth)
        side = "left" if conventions.wealth_percentile is WealthPercentileConvention.LOWER else "right"
        rank = np.searchsorted(sorted_wealth, wealth, side=side)
        candidate = rank.astype(np.float64) / n > calibration.elite_wealth_percentile
        candidate |= (np.isin(occupation, _SKILLED_CODES)
                      & (skill >= calibration.elite_skill_threshold))
        if backed_rows:
            candidate[np.asarray(backed_rows, dtype=np.int64)] = True
    else:
        candidate = np.zeros(0, dtype=bool)

    agents_first = conventions.equal_wealth_order is EqualWealthOrder.AGENTS_FIRST
    synthetic = list(gp_candidates.values())
    key_rank = {key: i + 1 for i, key in enumerate(sorted(k for k, _, _ in synthetic))}
    cand_wealth = np.concatenate([wealth[candidate],
                                  np.array([w for _, w, _ in synthetic], dtype=np.float64)])
    cand_satisfaction = np.concatenate([satisfaction[candidate],
                                        np.array([s for _, _, s in synthetic], dtype=np.float64)])
    n_agent_candidates = int(np.count_nonzero(candidate))
    kind = np.empty(len(cand_wealth), dtype=np.int64)
    kind[:n_agent_candidates] = 0 if agents_first else 1
    kind[n_agent_candidates:] = 1 if agents_first else 0
    tie_id = np.concatenate([ids[candidate], np.zeros(len(synthetic), dtype=np.int64)])
    tie_key = np.concatenate([np.zeros(n_agent_candidates, dtype=np.int64),
                              np.array([key_rank[k] for k, _, _ in synthetic], dtype=np.int64)])
    # Kernel rank: (-wealth, kind, agent id or 0, GP key or ""). Adding 0.0
    # maps -0.0 to 0.0, which the kernel's comparisons already treat as equal.
    order = np.lexsort((tie_key, tie_id, kind, -cand_wealth + 0.0))

    quotient, remainder = divmod(civ.population, calibration.elite_positions_divisor)
    if conventions.position_rounding is PositionRounding.CEIL and remainder:
        quotient += 1
    positions = max(calibration.elite_positions_min, quotient)
    qualifier_count = len(cand_wealth)
    holder_count = min(positions, qualifier_count)
    surplus = cand_satisfaction[order[positions:]]
    frustrated_count = int(np.count_nonzero(
        surplus < calibration.frustrated_aspirant_satisfaction_threshold))
    pressure = qualifier_count / max(positions, 1)
    index = (civ.previous_ratchet.conspicuous_consumption_index
             + calibration.ratchet_up_rate * max(0.0, pressure - 1.0)
             - calibration.ratchet_down_rate)
    if not isfinite(index):
        raise ValueError("ratchet arithmetic overflow")
    index = min(calibration.ratchet_cap, max(0.0, index))
    emp = (frustrated_count / max(positions, 1)) * index
    if not isfinite(emp):
        raise ValueError("EMP arithmetic overflow")
    return CivEliteCounts(civ.civ_id, positions, qualifier_count, holder_count,
                          frustrated_count, index, emp, EliteRatchetState(turn, index))
