"""M37: Religion system — faith generation, belief aggregation, conversion signals.

Religion is event-driven (stable by default), unlike M36's ambient cultural drift.
"""
from __future__ import annotations

import random
from collections import Counter
from typing import TYPE_CHECKING

from chronicler.models import (
    Belief,
    DOCTRINE_THEOLOGY,
    DOCTRINE_ETHICS,
    DOCTRINE_STANCE,
    DOCTRINE_OUTREACH,
    DOCTRINE_STRUCTURE,
)

if TYPE_CHECKING:
    from chronicler.models import Region

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_CONVERSION_RATE = 0.03
PROSELYTIZING_MULTIPLIER = 2.0
INSULAR_RESISTANCE = 0.5
NAMED_PROPHET_MULTIPLIER = 2.0
CONQUEST_BOOST_RATE = 0.05
CONQUEST_BOOST_DURATION = 10
HOLY_WAR_WEIGHT_BONUS = 0.15
HOLY_WAR_DEFENDER_STABILITY = 5
DOCTRINE_BIAS_RANDOM_CHANCE = 0.20

# Occupation id for priests (matches OCCUPATION_NAMES in agent_bridge)
_PRIEST_OCCUPATION = 4

# ---------------------------------------------------------------------------
# Doctrine bias table
# ---------------------------------------------------------------------------

# Maps civ value name → list of (doctrine_axis, direction, probability)
_DOCTRINE_BIAS_TABLE: dict[str, list[tuple[int, int, float]]] = {
    "Honor":     [(DOCTRINE_STANCE, +1, 0.6)],                             # Militant
    "Freedom":   [(DOCTRINE_STRUCTURE, +1, 0.4), (DOCTRINE_OUTREACH, +1, 0.4)],
    "Order":     [(DOCTRINE_STRUCTURE, -1, 0.4), (DOCTRINE_THEOLOGY, -1, 0.4)],
    "Tradition": [(DOCTRINE_OUTREACH, -1, 0.4), (DOCTRINE_ETHICS, -1, 0.4)],
    "Knowledge": [(DOCTRINE_STRUCTURE, -1, 0.5)],
    "Cunning":   [(DOCTRINE_ETHICS, +1, 0.4), (DOCTRINE_OUTREACH, +1, 0.4)],
}

_NUM_DOCTRINES = 5  # [Theology, Ethics, Stance, Outreach, Structure]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_doctrines(values: list[str], rng: random.Random) -> list[int]:
    """Generate a 5-element doctrine array biased by civ values.

    Each element is in {-1, 0, +1}.  For each civ value that appears in the
    bias table, roll each listed axis at its stated probability.  After all
    value-driven rolls, any axis still at 0 gets a 20% random fill to either
    +1 or -1.

    Returns a list[int] of length 5.
    """
    doctrines = [0] * _NUM_DOCTRINES

    for value in values:
        biases = _DOCTRINE_BIAS_TABLE.get(value, [])
        for axis, direction, prob in biases:
            if rng.random() < prob:
                # Only overwrite if not already set (first value wins)
                if doctrines[axis] == 0:
                    doctrines[axis] = direction

    # 20% random fill for axes still neutral
    for axis in range(_NUM_DOCTRINES):
        if doctrines[axis] == 0 and rng.random() < DOCTRINE_BIAS_RANDOM_CHANCE:
            doctrines[axis] = rng.choice([-1, +1])

    return doctrines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_faiths(
    civ_values: list[list[str]],
    civ_names: list[str],
    seed: int,
) -> list[Belief]:
    """Generate one Belief per civ with culture-biased doctrines.

    Args:
        civ_values: List of value-lists, one per civ (parallel to civ_names).
        civ_names:  Civ names used to derive faith names.
        seed:       World seed for determinism.

    Returns:
        List of Belief objects (one per civ), in civ order.
    """
    beliefs: list[Belief] = []
    for civ_idx, (values, name) in enumerate(zip(civ_values, civ_names)):
        rng = random.Random(seed ^ (civ_idx * 2654435761))
        doctrines = _generate_doctrines(values, rng)
        faith_name = f"Faith of {name}"
        belief = Belief(
            faith_id=civ_idx,
            name=faith_name,
            civ_origin=civ_idx,
            doctrines=doctrines,
        )
        beliefs.append(belief)
    return beliefs


def compute_majority_belief(snapshot) -> dict[int, int]:
    """Compute the majority faith per region from an agent snapshot.

    Args:
        snapshot: PyArrow RecordBatch with 'region' (uint16) and 'belief' (uint8) columns.

    Returns:
        dict mapping region_id → majority_faith_id.  Ties break to the lower faith_id.
    """
    if snapshot is None or snapshot.num_rows == 0:
        return {}

    regions = snapshot.column("region").to_pylist()
    beliefs = snapshot.column("belief").to_pylist()

    # Accumulate per-region faith counts
    counts: dict[int, Counter] = {}
    for region_id, faith_id in zip(regions, beliefs):
        if faith_id == 0xFF:
            continue
        if region_id not in counts:
            counts[region_id] = Counter()
        counts[region_id][faith_id] += 1

    result: dict[int, int] = {}
    for region_id, faith_counts in counts.items():
        if not faith_counts:
            continue
        max_count = max(faith_counts.values())
        # All faiths tied at max_count — pick lowest id
        winners = [fid for fid, cnt in faith_counts.items() if cnt == max_count]
        result[region_id] = min(winners)

    return result


def compute_civ_majority_faith(snapshot) -> dict[int, int]:
    """Compute the majority faith per civ from an agent snapshot.

    Args:
        snapshot: PyArrow RecordBatch with 'civ_affinity' (uint16) and 'belief' (uint8) columns.

    Returns:
        dict mapping civ_id → majority_faith_id.  Ties break to the lower faith_id.
    """
    if snapshot is None or snapshot.num_rows == 0:
        return {}

    civs = snapshot.column("civ_affinity").to_pylist()
    beliefs = snapshot.column("belief").to_pylist()

    counts: dict[int, Counter] = {}
    for civ_id, faith_id in zip(civs, beliefs):
        if faith_id == 0xFF:
            continue
        if civ_id not in counts:
            counts[civ_id] = Counter()
        counts[civ_id][faith_id] += 1

    result: dict[int, int] = {}
    for civ_id, faith_counts in counts.items():
        if not faith_counts:
            continue
        max_count = max(faith_counts.values())
        winners = [fid for fid, cnt in faith_counts.items() if cnt == max_count]
        result[civ_id] = min(winners)

    return result


def compute_conversion_signals(
    regions: list[Region],
    majority_beliefs: dict[int, int],
    belief_registry: list[Belief],
    snapshot,
    named_agents: dict[int, str] | None = None,
    civ_majority_faiths: dict[int, int] | None = None,
    civ_name_to_id: dict[str, int] | None = None,
) -> list[tuple[int, float, int, bool]]:
    """Compute per-region conversion signals and write to region fields.

    For each region:
    - Counts priests (occupation == 4) per faith.
    - The dominant *foreign* faith (most priests, not majority) wins the
      conversion slot.
    - Rate = BASE_CONVERSION_RATE × priest_ratio × doctrine modifiers
             × named-prophet bonus + conquest boost.
    - Reads and clears the one-shot ``conquest_conversion_active`` flag.
    - Falls back to the controller civ's majority faith when no priests
      are present but a conquest boost > 0 is active.
    - Writes results to ``region.conversion_rate_signal`` and
      ``region.conversion_target_signal``.

    Args:
        regions:             List of Region objects (indexed by position).
        majority_beliefs:    dict[region_id, majority_faith_id].
        belief_registry:     List of Belief objects (indexed by faith_id).
        snapshot:            PyArrow RecordBatch with agent data, or None.
        named_agents:        Optional dict[agent_id, name] for prophet detection.
        civ_majority_faiths: Optional dict[civ_id, faith_id] for conquest fallback.
        civ_name_to_id:      Optional dict[civ_name, civ_id] for lookup.

    Returns:
        list of (region_idx, rate, target_faith_id, conquest_active) tuples
        for backward compatibility.
    """
    if named_agents is None:
        named_agents = {}
    if civ_majority_faiths is None:
        civ_majority_faiths = {}
    if civ_name_to_id is None:
        civ_name_to_id = {}

    # Build per-region priest counts: region_id → Counter[faith_id → count]
    priest_faith_by_region: dict[int, Counter] = {}
    # Also track which named agents (prophets) are in each region
    prophet_regions: set[int] = set()

    if snapshot is not None and snapshot.num_rows > 0:
        agent_ids = snapshot.column("id").to_pylist()
        snap_regions = snapshot.column("region").to_pylist()
        occupations = snapshot.column("occupation").to_pylist()
        beliefs_col = snapshot.column("belief").to_pylist()

        for i in range(snapshot.num_rows):
            occ = occupations[i]
            if occ != _PRIEST_OCCUPATION:
                continue
            region_id = snap_regions[i]
            faith_id = beliefs_col[i]
            if faith_id == 0xFF:
                continue
            if region_id not in priest_faith_by_region:
                priest_faith_by_region[region_id] = Counter()
            priest_faith_by_region[region_id][faith_id] += 1

            # Check if this priest agent is a named prophet
            agent_id = agent_ids[i]
            if agent_id in named_agents:
                prophet_regions.add(region_id)

    results: list[tuple[int, float, int, bool]] = []

    for region_idx, region in enumerate(regions):
        # One-shot conquest flag — read and clear
        conquest_active = region.conquest_conversion_active
        if conquest_active:
            region.conquest_conversion_active = False

        majority_faith = majority_beliefs.get(region_idx, 0xFF)
        priest_counts = priest_faith_by_region.get(region_idx, Counter())
        total_priests = sum(priest_counts.values())

        # Find dominant foreign faith (most priests, not the majority faith)
        foreign_counts = {
            fid: cnt for fid, cnt in priest_counts.items()
            if fid != majority_faith
        }

        target_faith_id = 0xFF
        rate = 0.0

        if foreign_counts:
            # Dominant foreign faith wins
            max_foreign = max(foreign_counts.values())
            candidates = [fid for fid, cnt in foreign_counts.items() if cnt == max_foreign]
            target_faith_id = min(candidates)  # tie-break to lower id

            # Priest ratio
            priest_ratio = foreign_counts[target_faith_id] / max(total_priests, 1)

            # Doctrine modifiers
            doctrine_multiplier = 1.0
            target_belief = next(
                (b for b in belief_registry if b.faith_id == target_faith_id), None
            )
            if target_belief is not None:
                # DOCTRINE_OUTREACH (+1) → proselytizing → 2× rate
                if target_belief.doctrines[DOCTRINE_OUTREACH] == +1:
                    doctrine_multiplier *= PROSELYTIZING_MULTIPLIER
            # Insular resistance: defender's faith (majority) resists conversion
            majority_belief_obj = next(
                (b for b in belief_registry if b.faith_id == majority_faith), None
            )
            if majority_belief_obj is not None and majority_belief_obj.doctrines[DOCTRINE_OUTREACH] == -1:
                doctrine_multiplier *= INSULAR_RESISTANCE

            # Named prophet bonus
            prophet_multiplier = NAMED_PROPHET_MULTIPLIER if region_idx in prophet_regions else 1.0

            rate = (
                BASE_CONVERSION_RATE
                * priest_ratio
                * doctrine_multiplier
                * prophet_multiplier
            )

        # Conquest boost
        boost = region.conquest_conversion_boost
        if boost > 0:
            rate += boost * CONQUEST_BOOST_RATE

            # If no priests chose a target, use controller civ's majority faith
            if target_faith_id == 0xFF and region.controller is not None:
                civ_id = civ_name_to_id.get(region.controller)
                if civ_id is not None:
                    fallback = civ_majority_faiths.get(civ_id, 0xFF)
                    if fallback != 0xFF:
                        target_faith_id = fallback

        # Write to region fields
        region.conversion_rate_signal = rate
        region.conversion_target_signal = target_faith_id

        results.append((region_idx, rate, target_faith_id, conquest_active))

    return results


def decay_conquest_boosts(regions: list[Region]) -> None:
    """Linearly decay each region's ``conquest_conversion_boost`` toward zero.

    Each call reduces the boost by 1/CONQUEST_BOOST_DURATION of the *initial*
    full boost (CONQUEST_BOOST_RATE treated as one unit), clamped to [0, ∞).
    """
    decay_step = 1.0 / CONQUEST_BOOST_DURATION
    for region in regions:
        if region.conquest_conversion_boost > 0:
            region.conquest_conversion_boost = max(
                0.0, region.conquest_conversion_boost - decay_step
            )
