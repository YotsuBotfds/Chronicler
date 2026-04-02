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

# M38b: Persecution
# NOTE: Satisfaction penalty owned by Rust (PERSECUTION_SAT_WEIGHT in agent.rs).
PERSECUTION_REBEL_BOOST = 0.30       # max rebel utility boost
PERSECUTION_MIGRATE_BOOST = 0.20     # max migrate utility boost
MASS_MIGRATION_THRESHOLD = 0.15      # ratio of persecuted agents to trigger event
MARTYRDOM_BOOST_PER_EVENT = 0.05     # added per turn with persecution deaths
MARTYRDOM_BOOST_CAP = 0.20           # max regional martyrdom boost
MARTYRDOM_DECAY_TURNS = 10           # linear decay duration

# M38b: Schisms
SCHISM_MINORITY_THRESHOLD = 0.30
SCHISM_SECESSION_MODIFIER = 10
REFORMATION_THRESHOLD = 0.60
MAX_FAITHS = 16

SCHISM_NEUTRAL_POLE_MAP = {
    DOCTRINE_STANCE: -1,
    DOCTRINE_STRUCTURE: -1,
    DOCTRINE_OUTREACH: -1,
    DOCTRINE_ETHICS: 1,
}

# M38b: Pilgrimages
PILGRIMAGE_DURATION_MIN = 5
PILGRIMAGE_DURATION_MAX = 10
PILGRIMAGE_SKILL_BOOST = 0.10

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


def compute_civ_majority_faith(snapshot) -> dict[int, tuple[int, float]]:
    """Compute the majority faith per civ from an agent snapshot.

    Args:
        snapshot: PyArrow RecordBatch with 'civ_affinity' (uint16) and 'belief' (uint8) columns.

    Returns:
        dict mapping civ_id → (majority_faith_id, ratio).  Ties break to the lower faith_id.
        ratio = max_count / total_agents_in_civ (agents with valid belief).
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

    result: dict[int, tuple[int, float]] = {}
    for civ_id, faith_counts in counts.items():
        if not faith_counts:
            continue
        total = sum(faith_counts.values())
        max_count = max(faith_counts.values())
        winners = [fid for fid, cnt in faith_counts.items() if cnt == max_count]
        majority_faith_id = min(winners)
        ratio = max_count / total if total > 0 else 0.0
        result[civ_id] = (majority_faith_id, ratio)

    return result


def compute_conversion_signals(
    regions: list[Region],
    majority_beliefs: dict[int, int],
    belief_registry: list[Belief],
    snapshot,
    named_agents: dict[int, str] | None = None,
    civ_majority_faiths: dict[int, int] | None = None,
    civ_name_to_id: dict[str, int] | None = None,
    world: "WorldState | None" = None,
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

            from chronicler.tuning import get_multiplier, K_RELIGION_INTENSITY
            religion_mult = get_multiplier(world, K_RELIGION_INTENSITY) if world is not None else 1.0
            rate = (
                BASE_CONVERSION_RATE
                * priest_ratio
                * doctrine_multiplier
                * prophet_multiplier
                * religion_mult
            )

        # M38b: Martyrdom boost (adds directly to conversion rate)
        conversion_rate = rate
        conversion_rate += region.martyrdom_boost
        rate = conversion_rate

        # M52: Relic conversion bonus
        if world is not None:
            from chronicler.artifacts import get_relic_conversion_modifier
            relic_mod = get_relic_conversion_modifier(world, region)
            rate *= relic_mod

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

        # M38a: temple conversion boost — faith-bound guard clause
        from chronicler.infrastructure import TEMPLE_CONVERSION_BOOST
        from chronicler.models import InfrastructureType
        for infra in region.infrastructure:
            if (infra.type == InfrastructureType.TEMPLES
                    and infra.active
                    and getattr(infra, 'faith_id', -1) == target_faith_id):
                rate *= (1.0 + TEMPLE_CONVERSION_BOOST)
                break

        # Write to region fields
        region.conversion_rate_signal = rate
        region.conversion_target_signal = target_faith_id

        results.append((region_idx, rate, target_faith_id, conquest_active))

    return results


def compute_conversion_deltas(current_beliefs, prev_beliefs, civ_majority_faiths, regions):
    """Per-region count of agents who converted to controller's faith this turn."""
    deltas = {}
    for region_id, curr_dist in current_beliefs.items():
        if region_id >= len(regions):
            continue
        region = regions[region_id]
        controller = getattr(region, 'controller', None)
        if controller is None:
            continue
        target_faith = civ_majority_faiths.get(controller, -1)
        if target_faith < 0:
            continue
        curr_count = curr_dist.get(target_faith, 0)
        prev_count = prev_beliefs.get(region_id, {}).get(target_faith, 0)
        delta = curr_count - prev_count
        if delta > 0:
            deltas[region_id] = delta
    return deltas


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


# ---------------------------------------------------------------------------
# M38b: Persecution
# ---------------------------------------------------------------------------

def compute_persecution(
    regions: list[Region],
    civilizations,
    belief_registry: list[Belief],
    snapshot,
    turn: int,
    persecuted_regions: set[str],
    world=None,
) -> list:
    """Detect religious persecution and fire events.

    For each civilization whose majority faith is Militant (DOCTRINE_STANCE == +1),
    inspect every region that civ controls and compute a persecution intensity based
    on the minority ratio among agents.

    Args:
        regions:            List of Region objects (indexed by position).
        civilizations:      List of Civilization objects.
        belief_registry:    List of Belief objects (indexed by faith_id).
        snapshot:           PyArrow RecordBatch with 'region' (uint16) and
                            'belief' (uint8) columns, or None.
        turn:               Current simulation turn number.
        persecuted_regions: Mutable set of region names already seen; used to
                            fire the one-shot "Persecution" event per region.

    Returns:
        List of Event objects generated this call.
    """
    from chronicler.models import Event

    events: list = []

    if snapshot is None or snapshot.num_rows == 0:
        return events

    # Build region name → index mapping
    region_map: dict[str, int] = {r.name: i for i, r in enumerate(regions)}

    # Tally per-region belief counts from snapshot
    snap_regions = snapshot.column("region").to_pylist()
    snap_beliefs = snapshot.column("belief").to_pylist()

    region_belief_counts: dict[int, Counter] = {}
    for region_idx, faith_id in zip(snap_regions, snap_beliefs):
        if faith_id == 0xFF:
            continue
        if region_idx not in region_belief_counts:
            region_belief_counts[region_idx] = Counter()
        region_belief_counts[region_idx][faith_id] += 1

    for civ in civilizations:
        # Skip dead civs
        if len(civ.regions) == 0:
            continue

        # Only Militant faiths persecute
        majority_faith_id = getattr(civ, 'civ_majority_faith', 0xFF)
        if majority_faith_id == 0xFF:
            continue
        majority_belief = next(
            (b for b in belief_registry if b.faith_id == majority_faith_id), None
        )
        if majority_belief is None:
            continue
        if majority_belief.doctrines[DOCTRINE_STANCE] != +1:
            continue

        # Inspect each region this civ controls
        for region_name in civ.regions:
            region_idx = region_map.get(region_name)
            if region_idx is None:
                continue
            region = regions[region_idx]

            counts = region_belief_counts.get(region_idx, Counter())
            total = sum(counts.values())
            if total == 0:
                continue

            majority_count = counts.get(majority_faith_id, 0)
            minority_count = total - majority_count
            if minority_count <= 0:
                # No minority present — clear persecution
                region.persecution_intensity = 0.0
                continue

            minority_ratio = minority_count / total
            from chronicler.tuning import get_multiplier as _gm, K_RELIGION_INTENSITY as _KRI
            # Larger minorities are more threatening → higher persecution intensity.
            # Scale with minority_ratio, not against it.
            intensity = minority_ratio * (_gm(world, _KRI) if world else 1.0)
            region.persecution_intensity = intensity

            # One-shot "Persecution" event per region
            if region_name not in persecuted_regions:
                persecuted_regions.add(region_name)
                events.append(Event(
                    event_type="Persecution",
                    turn=turn,
                    actors=[civ.name],
                    description=(
                        f"{civ.name} persecutes religious minorities in {region_name} "
                        f"(intensity={intensity:.2f})"
                    ),
                    importance=6,
                ))

            # "Mass Migration" event when minority ratio exceeds threshold
            if minority_ratio > MASS_MIGRATION_THRESHOLD:
                events.append(Event(
                    event_type="Mass Migration",
                    turn=turn,
                    actors=[civ.name],
                    description=(
                        f"Religious minorities flee {region_name} due to persecution "
                        f"(minority_ratio={minority_ratio:.2f})"
                    ),
                    importance=6,
                ))

    return events


def compute_martyrdom_boosts(
    regions: list[Region],
    dead_agents: "list[dict | object] | None",
) -> None:
    """Add martyrdom boost to regions where persecuted minority-faith agents died.

    Only deaths that meet BOTH conditions count as martyrdoms:
      1. The region has active persecution (persecution_intensity > 0).
      2. The dead agent's belief differs from the region's majority faith.

    Args:
        regions:     List of Region objects.
        dead_agents: List of dicts with 'region_idx' (int) and 'belief' (int) keys,
                     or None / empty list if no deaths occurred.
    """
    if not dead_agents:
        return

    for agent in dead_agents:
        if isinstance(agent, dict):
            region_idx = agent.get("region_idx", agent.get("region"))
            belief = agent.get("belief")
        else:
            region_idx = getattr(agent, "region_idx", None)
            if region_idx is None:
                region_idx = getattr(agent, "region", None)
            belief = getattr(agent, "belief", None)
        if region_idx is None:
            continue
        try:
            region_idx_int = int(region_idx)
        except (TypeError, ValueError):
            continue
        if region_idx_int < 0 or region_idx_int >= len(regions):
            continue
        region = regions[region_idx_int]

        # M-AF1 #12: Only minority-faith deaths in persecuted regions count
        if region.persecution_intensity <= 0:
            continue
        if belief is None or belief == region.majority_belief:
            continue

        region.martyrdom_boost = min(
            MARTYRDOM_BOOST_CAP,
            region.martyrdom_boost + MARTYRDOM_BOOST_PER_EVENT,
        )


def decay_martyrdom_boosts(regions: list[Region]) -> None:
    """Linearly decay each region's ``martyrdom_boost`` toward zero.

    Each call reduces the boost by 1/MARTYRDOM_DECAY_TURNS of the cap,
    clamped to [0, ∞).
    """
    decay_step = MARTYRDOM_BOOST_CAP / MARTYRDOM_DECAY_TURNS
    for region in regions:
        if region.martyrdom_boost > 0:
            region.martyrdom_boost = max(
                0.0, region.martyrdom_boost - decay_step
            )


# ---------------------------------------------------------------------------
# M38b: Schisms
# ---------------------------------------------------------------------------

def determine_schism_axis(
    region,
    original_belief: "Belief",
    current_turn: int = 0,
    clergy_influence: float = 0.0,
) -> tuple[int, int]:
    """Determine the doctrine axis and pole direction for a schism split.

    Priority-ordered trigger matching:
      P1: persecution_intensity > 0 → DOCTRINE_STANCE
      P2: clergy_influence > 0.40   → DOCTRINE_STRUCTURE
      P3: (inert until M43)
      P4: last_conquered_turn >= 0 and current_turn - last_conquered_turn < 10
              → DOCTRINE_OUTREACH
      P5: fallback → axis with lowest absolute value

    If the chosen axis value in original_belief is 0, use SCHISM_NEUTRAL_POLE_MAP;
    else negate the existing value.

    Returns:
        (axis, pole) where axis is a DOCTRINE_* int and pole is +1 or -1.
    """
    axis: int | None = None

    # P1: Persecution
    if getattr(region, 'persecution_intensity', 0.0) > 0:
        axis = DOCTRINE_STANCE
    # P2: Clergy dominance
    elif clergy_influence > 0.40:
        axis = DOCTRINE_STRUCTURE
    # P3: (reserved for M43)
    # P4: Recent conquest
    elif (
        getattr(region, 'last_conquered_turn', -1) >= 0
        and current_turn - region.last_conquered_turn < 10
    ):
        axis = DOCTRINE_OUTREACH
    else:
        # P5: Fallback — axis with lowest absolute doctrine value
        # Exclude DOCTRINE_THEOLOGY (index 0) from fallback candidates per design
        candidates = [DOCTRINE_ETHICS, DOCTRINE_STANCE, DOCTRINE_OUTREACH, DOCTRINE_STRUCTURE]
        axis = min(candidates, key=lambda a: abs(original_belief.doctrines[a]))

    # Determine pole direction
    axis_value = original_belief.doctrines[axis]
    if axis_value == 0:
        pole = SCHISM_NEUTRAL_POLE_MAP.get(axis, -1)
    else:
        pole = -axis_value  # negate existing value

    return (axis, pole)


def fire_schism(
    region,
    original_faith_id: int,
    belief_registry: list["Belief"],
    civ,
    current_turn: int,
    civ_origin: int = 0,
) -> "Belief | None":
    """Create a splinter faith and mark the region for schism conversion.

    Copies doctrines from the original faith, then flips the schism axis
    determined by determine_schism_axis.  The new faith is named
    "X (Reformed)", "X (Reformed 2)", etc., to avoid collisions.

    Sets region.schism_convert_from / schism_convert_to.

    Returns the new Belief, or None if the registry is full or the original
    faith is not found.
    """
    if len(belief_registry) >= MAX_FAITHS:
        return None

    original_belief = next(
        (b for b in belief_registry if b.faith_id == original_faith_id), None
    )
    if original_belief is None:
        return None

    # Clergy influence from faction state
    from chronicler.models import FactionType
    clergy_influence = civ.factions.influence.get(FactionType.CLERGY, 0.0)

    axis, pole = determine_schism_axis(
        region, original_belief,
        current_turn=current_turn,
        clergy_influence=clergy_influence,
    )

    # Build new doctrines — copy original, flip schism axis
    new_doctrines = list(original_belief.doctrines)
    new_doctrines[axis] = pole

    # Generate unique name
    base_name = f"{original_belief.name} (Reformed)"
    final_name = base_name
    existing_names = {b.name for b in belief_registry}
    counter = 2
    while final_name in existing_names:
        final_name = f"{original_belief.name} (Reformed {counter})"
        counter += 1

    # Assign the next available faith_id
    used_ids = {b.faith_id for b in belief_registry}
    new_faith_id = next(i for i in range(MAX_FAITHS) if i not in used_ids)

    from chronicler.models import Belief as _Belief
    new_belief = _Belief(
        faith_id=new_faith_id,
        name=final_name,
        civ_origin=civ_origin,
        doctrines=new_doctrines,
    )

    belief_registry.append(new_belief)

    # Mark region for schism-driven conversion
    region.schism_convert_from = original_faith_id
    region.schism_convert_to = new_faith_id

    return new_belief


def detect_schisms(
    regions: list,
    civs: list,
    belief_registry: list["Belief"],
    snapshot,
    current_turn: int,
    world=None,
) -> list:
    """Detect and fire at most one schism per civilization per turn.

    For each living civilization (len(civ.regions) > 0), examine its regions
    and compute the minority faith ratio.  The region with the highest minority
    ratio above SCHISM_MINORITY_THRESHOLD triggers a schism.

    Guards:
    - len(belief_registry) >= MAX_FAITHS → return [] immediately.
    - snapshot is None or empty → return [].

    Args:
        regions:          List of Region objects.
        civs:             List of Civilization objects.
        belief_registry:  Mutable list of Belief objects (extended in-place).
        snapshot:         PyArrow RecordBatch with 'region', 'civ_affinity',
                          'belief' columns, or None.
        current_turn:     Current simulation turn number.

    Returns:
        List of Event objects generated this call.
    """
    from chronicler.models import Event, FactionType

    if len(belief_registry) >= MAX_FAITHS:
        return []

    if snapshot is None or snapshot.num_rows == 0:
        return []

    # Build region_map: name → Region object
    region_map = {r.name: r for r in regions}

    # Tally per-region belief counts from snapshot
    snap_regions = snapshot.column("region").to_pylist()
    snap_beliefs = snapshot.column("belief").to_pylist()

    region_belief_counts: dict[int, Counter] = {}
    for region_idx, faith_id in zip(snap_regions, snap_beliefs):
        if faith_id == 0xFF:
            continue
        if region_idx not in region_belief_counts:
            region_belief_counts[region_idx] = Counter()
        region_belief_counts[region_idx][faith_id] += 1

    # Build region index map (name → index)
    region_idx_map: dict[str, int] = {r.name: i for i, r in enumerate(regions)}

    events: list = []

    for civ_idx, civ in enumerate(civs):
        if len(civ.regions) == 0:
            continue

        majority_faith_id = getattr(civ, 'civ_majority_faith', 0xFF)
        if majority_faith_id == 0xFF:
            continue

        # Find region with highest minority ratio above threshold
        best_region = None
        from chronicler.tuning import get_multiplier, K_RELIGION_INTENSITY
        effective_threshold = max(
            SCHISM_MINORITY_THRESHOLD / (get_multiplier(world, K_RELIGION_INTENSITY) if world else 1.0),
            0.10,
        )
        best_minority_ratio = effective_threshold  # strictly greater than threshold
        best_region_idx = -1

        for region_name in civ.regions:
            ridx = region_idx_map.get(region_name)
            if ridx is None:
                continue
            counts = region_belief_counts.get(ridx, Counter())
            total = sum(counts.values())
            if total == 0:
                continue
            majority_count = counts.get(majority_faith_id, 0)
            minority_count = total - majority_count
            if minority_count <= 0:
                continue
            minority_ratio = minority_count / total
            if minority_ratio > best_minority_ratio:
                best_minority_ratio = minority_ratio
                best_region = region_map.get(region_name)
                best_region_idx = ridx

        if best_region is None:
            continue

        # Guard: registry may have grown during this call
        if len(belief_registry) >= MAX_FAITHS:
            break

        new_belief = fire_schism(
            best_region,
            majority_faith_id,
            belief_registry,
            civ,
            current_turn,
            civ_origin=civ_idx,
        )
        if new_belief is None:
            continue

        # H-13: Verify the new faith has at least one potential follower.
        # Under stale-order conditions the snapshot may show minority presence
        # that no longer exists.  Roll back if zero followers would result.
        counts_for_region = region_belief_counts.get(best_region_idx, Counter())
        potential_followers = sum(
            c for fid, c in counts_for_region.items() if fid != majority_faith_id
        )
        if potential_followers == 0:
            belief_registry.remove(new_belief)
            best_region.schism_convert_from = 0xFF
            best_region.schism_convert_to = 0xFF
            continue

        events.append(Event(
            event_type="Schism",
            turn=current_turn,
            actors=[civ.name],
            description=(
                f"A schism fractures {civ.name}: '{new_belief.name}' "
                f"splits from the majority faith in {best_region.name} "
                f"(minority_ratio={best_minority_ratio:.2f})"
            ),
            importance=7,
        ))

    return events


def detect_reformation(
    civs: list,
    belief_registry: list["Belief"],
    current_turn: int | None = None,
) -> list:
    """Fire reformation events when a civ's majority faith has shifted significantly.

    Triggers when:
    - civ.civ_majority_faith != civ.previous_majority_faith
    - civ._majority_faith_ratio >= REFORMATION_THRESHOLD

    Updates previous_majority_faith after firing the event.

    Returns:
        List of Event objects (importance=8).
    """
    from chronicler.models import Event

    events: list = []

    for civ in civs:
        if len(civ.regions) == 0:
            continue

        current_faith = getattr(civ, 'civ_majority_faith', 0xFF)
        previous_faith = getattr(civ, 'previous_majority_faith', current_faith)

        if current_faith == previous_faith:
            continue

        ratio = getattr(civ, '_majority_faith_ratio', 0.0)
        if ratio < REFORMATION_THRESHOLD:
            continue

        # Lookup faith name
        new_belief = next(
            (b for b in belief_registry if b.faith_id == current_faith), None
        )
        faith_name = new_belief.name if new_belief else f"Faith {current_faith}"

        events.append(Event(
            event_type="Reformation",
            turn=current_turn if current_turn is not None else 0,
            actors=[civ.name],
            description=(
                f"{civ.name} undergoes a Reformation: '{faith_name}' "
                f"now holds majority faith (ratio={ratio:.2f})"
            ),
            importance=8,
        ))

        # Advance the previous faith baseline
        civ.previous_majority_faith = current_faith

    return events
