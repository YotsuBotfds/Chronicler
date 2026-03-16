"""Narrative curator: selects the most important moments from a simulation.

Pure Python — no LLM calls. Scores events, discovers causal links, clusters
them into narrative moments, and assigns dramatic-arc roles.

M20a Tasks 3-7.
"""
from __future__ import annotations

from collections import Counter
from typing import Sequence

from chronicler.models import (
    CausalLink,
    Event,
    GapSummary,
    NamedEvent,
    NarrativeMoment,
    NarrativeRole,
    TurnSnapshot,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLUSTER_MERGE_THRESHOLD = 5  # turns; tunable

CAUSAL_PATTERNS: list[tuple[str, str, int, float]] = [
    # (cause_type, effect_type, max_gap, bonus)
    ("drought", "famine", 10, 3.0),
    ("drought", "migration", 15, 2.0),
    ("famine", "rebellion", 10, 3.0),
    ("famine", "secession", 15, 3.0),
    ("war", "collapse", 20, 4.0),
    ("war", "leader_death", 5, 2.0),
    ("leader_death", "succession_crisis", 1, 3.0),
    ("succession_crisis", "coup", 5, 3.0),
    ("plague", "famine", 10, 2.0),
    ("embargo", "rebellion", 15, 2.0),
    ("tech_advancement", "war", 10, 2.0),
    ("cultural_renaissance", "movement", 10, 2.0),
    ("discovery", "war", 15, 2.0),
]

# Stat fields used in gap summaries
_STAT_FIELDS = ("population", "military", "economy", "culture", "stability")


# ---------------------------------------------------------------------------
# 1. compute_dominant_power
# ---------------------------------------------------------------------------

def compute_dominant_power(
    history: Sequence[TurnSnapshot],
    seed: int,
) -> str:
    """Find the civ with the most cumulative region-turns across history.

    Ties are broken deterministically via ``hash((seed, civ_name))``.
    """
    region_turns: Counter[str] = Counter()
    for snap in history:
        for _region, controller in snap.region_control.items():
            if controller:
                region_turns[controller] += 1

    if not region_turns:
        return ""

    max_rt = max(region_turns.values())
    tied = [name for name, rt in region_turns.items() if rt == max_rt]

    if len(tied) == 1:
        return tied[0]

    # Deterministic tiebreak
    return min(tied, key=lambda n: hash((seed, n)))


# ---------------------------------------------------------------------------
# 2. compute_base_scores
# ---------------------------------------------------------------------------

def compute_base_scores(
    events: Sequence[Event],
    named_events: Sequence[NamedEvent],
    dominant_power: str,
    seed: int,
    named_characters: set[str] | None = None,
) -> list[float]:
    """Score each event based on importance, named-event match, dominant
    power involvement, and rarity.

    Returns a parallel list of float scores (one per event).
    """
    # Pre-compute type counts for rarity
    type_counts: Counter[str] = Counter(e.event_type for e in events)

    # Index named events by (turn, frozenset(actors)) for O(1) lookup
    named_keys: set[tuple[int, frozenset[str]]] = {
        (ne.turn, frozenset(ne.actors)) for ne in named_events
    }

    scores: list[float] = []
    for ev in events:
        score = float(ev.importance)

        # Named-event bonus
        key = (ev.turn, frozenset(ev.actors))
        if key in named_keys:
            score += 3.0

        # Dominant-power bonus
        if dominant_power and dominant_power in ev.actors:
            score += 2.0

        # Rarity bonus
        if type_counts[ev.event_type] < 3:
            score += 2.0

        # Character-reference bonus (M30) — +2.0 if any actor is a named character
        # Saturation guard: max once per event regardless of how many characters
        if named_characters:
            if any(actor in named_characters for actor in ev.actors):
                score += 2.0

        scores.append(score)

    return scores


# ---------------------------------------------------------------------------
# 3. compute_causal_links
# ---------------------------------------------------------------------------

def compute_causal_links(
    events: Sequence[Event],
    scores: list[float],
) -> list[CausalLink]:
    """Discover causal links between events using ``CAUSAL_PATTERNS``.

    * Cause and effect must share at least one actor (spatial filter).
    * The cause event's score is mutated in place (bonus added).
    * Returns a list of ``CausalLink`` objects.
    """
    links: list[CausalLink] = []

    for i, cause in enumerate(events):
        cause_actors = set(cause.actors)
        for j in range(i + 1, len(events)):
            effect = events[j]
            gap = effect.turn - cause.turn
            # Early exit: events are assumed sorted by turn.
            # If gap exceeds the largest max_gap in any pattern we can skip,
            # but to keep it simple, we check each pattern individually.
            effect_actors = set(effect.actors)

            # Spatial filter: must share at least one actor
            if not cause_actors & effect_actors:
                continue

            for cause_type, effect_type, max_gap, bonus in CAUSAL_PATTERNS:
                if (
                    cause.event_type == cause_type
                    and effect.event_type == effect_type
                    and gap <= max_gap
                ):
                    scores[i] += bonus
                    links.append(CausalLink(
                        cause_turn=cause.turn,
                        cause_event_type=cause.event_type,
                        effect_turn=effect.turn,
                        effect_event_type=effect.event_type,
                        pattern=f"{cause_type}\u2192{effect_type}",
                    ))

    return links


# ---------------------------------------------------------------------------
# 4. build_clusters
# ---------------------------------------------------------------------------

def build_clusters(
    events: Sequence[Event],
    scores: Sequence[float],
) -> list[dict]:
    """Group events within ``CLUSTER_MERGE_THRESHOLD`` turns into clusters.

    Returns a list of cluster dicts, each with:
    * ``turn_range``: (min_turn, max_turn)
    * ``anchor_turn``: turn of highest-scoring event
    * ``score``: sum of top 3 member scores
    * ``event_indices``: list of indices into *events*
    """
    if not events:
        return []

    # Events must already be sorted by turn
    clusters: list[list[int]] = []
    current_cluster: list[int] = [0]

    for idx in range(1, len(events)):
        if events[idx].turn - events[current_cluster[-1]].turn <= CLUSTER_MERGE_THRESHOLD:
            current_cluster.append(idx)
        else:
            clusters.append(current_cluster)
            current_cluster = [idx]
    clusters.append(current_cluster)

    result: list[dict] = []
    for indices in clusters:
        member_scores = [scores[i] for i in indices]
        top3 = sorted(member_scores, reverse=True)[:3]
        best_idx = max(indices, key=lambda i: scores[i])
        turn_min = events[indices[0]].turn
        turn_max = events[indices[-1]].turn
        result.append({
            "turn_range": (turn_min, turn_max),
            "anchor_turn": events[best_idx].turn,
            "score": sum(top3),
            "event_indices": list(indices),
        })

    return result


# ---------------------------------------------------------------------------
# 5. apply_diversity_penalty
# ---------------------------------------------------------------------------

def apply_diversity_penalty(
    selected: list[NarrativeMoment],
    unselected: list[NarrativeMoment],
) -> list[NarrativeMoment]:
    """Demote over-represented civs/event-types among selected moments.

    * >40% same civ → demote lowest-scored non-named moment with that civ
    * >30% same dominant event type → same treatment
    * Named events are exempt from demotion
    * Iterate up to 3 times to convergence
    """
    sel = list(selected)
    unsorted_pool = list(unselected)

    for _iteration in range(3):
        changed = False

        # --- Civ diversity ---
        civ_counts: Counter[str] = Counter()
        for m in sel:
            civs_in_moment = set()
            for ev in m.events:
                for actor in ev.actors:
                    civs_in_moment.add(actor)
            for civ in civs_in_moment:
                civ_counts[civ] += 1

        threshold_civ = 0.40 * len(sel)
        for civ, count in civ_counts.most_common():
            if count <= threshold_civ:
                break
            # Find lowest-scored non-named moment involving this civ
            candidates = [
                (idx, m) for idx, m in enumerate(sel)
                if not m.named_events
                and any(civ in ev.actors for ev in m.events)
            ]
            if not candidates or not unsorted_pool:
                continue
            candidates.sort(key=lambda x: x[1].score)
            demote_idx, demote_m = candidates[0]
            # Replace with best from pool
            unsorted_pool.sort(key=lambda m: m.score, reverse=True)
            replacement = unsorted_pool.pop(0)
            sel[demote_idx] = replacement
            unsorted_pool.append(demote_m)
            changed = True

        # --- Event-type diversity ---
        type_counts: Counter[str] = Counter()
        for m in sel:
            # Dominant event type per moment = most common type in events
            if m.events:
                moment_types = Counter(ev.event_type for ev in m.events)
                dominant_type = moment_types.most_common(1)[0][0]
                type_counts[dominant_type] += 1

        threshold_type = 0.30 * len(sel)
        for etype, count in type_counts.most_common():
            if count <= threshold_type:
                break
            candidates = [
                (idx, m) for idx, m in enumerate(sel)
                if not m.named_events
                and m.events
                and Counter(ev.event_type for ev in m.events).most_common(1)[0][0] == etype
            ]
            if not candidates or not unsorted_pool:
                continue
            candidates.sort(key=lambda x: x[1].score)
            demote_idx, demote_m = candidates[0]
            # Find a replacement whose dominant type differs
            unsorted_pool.sort(key=lambda m: m.score, reverse=True)
            replacement = None
            replacement_idx = None
            for ri, rm in enumerate(unsorted_pool):
                if rm.events:
                    rt = Counter(ev.event_type for ev in rm.events).most_common(1)[0][0]
                    if rt != etype:
                        replacement = rm
                        replacement_idx = ri
                        break
            if replacement is None or replacement_idx is None:
                continue
            unsorted_pool.pop(replacement_idx)
            sel[demote_idx] = replacement
            unsorted_pool.append(demote_m)
            changed = True

        if not changed:
            break

    return sel


# ---------------------------------------------------------------------------
# 6. assign_roles
# ---------------------------------------------------------------------------

def assign_roles(moments: list[NarrativeMoment]) -> None:
    """Assign ``NarrativeRole`` to each moment in place.

    * Moments must already be sorted by ``anchor_turn``.
    * Highest score = CLIMAX.
    * Before climax: first = INCITING, rest = ESCALATION.
    * After climax: last = CODA, rest = RESOLUTION.
    * Single moment = CLIMAX.
    """
    if not moments:
        return

    if len(moments) == 1:
        moments[0].narrative_role = NarrativeRole.CLIMAX
        return

    # Sort by anchor_turn (should already be, but ensure)
    moments.sort(key=lambda m: m.anchor_turn)

    # Find climax index (highest score)
    climax_idx = max(range(len(moments)), key=lambda i: moments[i].score)

    moments[climax_idx].narrative_role = NarrativeRole.CLIMAX

    # Before climax
    for i in range(climax_idx):
        if i == 0:
            moments[i].narrative_role = NarrativeRole.INCITING
        else:
            moments[i].narrative_role = NarrativeRole.ESCALATION

    # After climax
    after_count = len(moments) - climax_idx - 1
    if after_count > 0:
        for i in range(climax_idx + 1, len(moments)):
            moments[i].narrative_role = NarrativeRole.RESOLUTION
        # Last one after climax = CODA (only if it's not the climax itself)
        if climax_idx < len(moments) - 1:
            moments[-1].narrative_role = NarrativeRole.CODA


# ---------------------------------------------------------------------------
# 7. build_gap_summaries
# ---------------------------------------------------------------------------

def build_gap_summaries(
    moments: list[NarrativeMoment],
    events: Sequence[Event],
    history: Sequence[TurnSnapshot],
) -> list[GapSummary]:
    """Build summaries for the turns between consecutive moments.

    Each gap covers the turns strictly between two moment turn_ranges.
    """
    if len(moments) < 2:
        return []

    # Sort moments by anchor_turn
    sorted_moments = sorted(moments, key=lambda m: m.anchor_turn)

    # Index snapshots by turn for lookup
    snap_by_turn: dict[int, TurnSnapshot] = {s.turn: s for s in history}
    sorted_snap_turns = sorted(snap_by_turn.keys())

    gaps: list[GapSummary] = []

    for i in range(len(sorted_moments) - 1):
        gap_start = sorted_moments[i].turn_range[1] + 1
        gap_end = sorted_moments[i + 1].turn_range[0] - 1

        if gap_start > gap_end:
            # No gap (moments overlap or are adjacent)
            gaps.append(GapSummary(
                turn_range=(gap_start, gap_end),
                event_count=0,
                top_event_type="none",
                stat_deltas={},
                territory_changes=0,
            ))
            continue

        # Count events in gap
        gap_events = [
            e for e in events
            if gap_start <= e.turn <= gap_end
        ]
        event_count = len(gap_events)

        # Most common event type
        if gap_events:
            type_counts = Counter(e.event_type for e in gap_events)
            top_event_type = type_counts.most_common(1)[0][0]
        else:
            top_event_type = "none"

        # Find snapshots closest to gap boundaries
        snap_before = _find_closest_snap(sorted_snap_turns, snap_by_turn, gap_start, before=True)
        snap_after = _find_closest_snap(sorted_snap_turns, snap_by_turn, gap_end, before=False)

        # Stat deltas
        stat_deltas: dict[str, dict[str, int]] = {}
        territory_changes = 0

        if snap_before and snap_after:
            # Compute stat deltas for each civ present in both snapshots
            all_civs = set(snap_before.civ_stats.keys()) | set(snap_after.civ_stats.keys())
            for civ in all_civs:
                if civ in snap_before.civ_stats and civ in snap_after.civ_stats:
                    before_stats = snap_before.civ_stats[civ]
                    after_stats = snap_after.civ_stats[civ]
                    deltas: dict[str, int] = {}
                    for field in _STAT_FIELDS:
                        delta = getattr(after_stats, field) - getattr(before_stats, field)
                        if delta != 0:
                            deltas[field] = delta
                    if deltas:
                        stat_deltas[civ] = deltas

            # Territory changes
            all_regions = set(snap_before.region_control.keys()) | set(snap_after.region_control.keys())
            for region in all_regions:
                ctrl_before = snap_before.region_control.get(region)
                ctrl_after = snap_after.region_control.get(region)
                if ctrl_before != ctrl_after:
                    territory_changes += 1

        gaps.append(GapSummary(
            turn_range=(gap_start, gap_end),
            event_count=event_count,
            top_event_type=top_event_type,
            stat_deltas=stat_deltas,
            territory_changes=territory_changes,
        ))

    return gaps


def _find_closest_snap(
    sorted_turns: list[int],
    snap_by_turn: dict[int, TurnSnapshot],
    target: int,
    before: bool,
) -> TurnSnapshot | None:
    """Find the snapshot closest to ``target``.

    If ``before=True``, find the snapshot at or before target.
    If ``before=False``, find the snapshot at or after target.
    """
    if not sorted_turns:
        return None

    if before:
        # Find largest turn <= target
        best = None
        for t in sorted_turns:
            if t <= target:
                best = t
            else:
                break
        return snap_by_turn[best] if best is not None else snap_by_turn[sorted_turns[0]]
    else:
        # Find smallest turn >= target
        for t in sorted_turns:
            if t >= target:
                return snap_by_turn[t]
        return snap_by_turn[sorted_turns[-1]]


# ---------------------------------------------------------------------------
# 8. curate (top-level)
# ---------------------------------------------------------------------------

def curate(
    events: Sequence[Event],
    named_events: Sequence[NamedEvent],
    history: Sequence[TurnSnapshot],
    budget: int = 50,
    seed: int = 0,
    named_characters: set[str] | None = None,
) -> tuple[list[NarrativeMoment], list[GapSummary]]:
    """Top-level curation pipeline.

    1. Sort events by turn
    2. Compute dominant power
    3. Base scoring → causal linking → clustering
    4. Select top *budget* clusters
    5. Convert to NarrativeMoments
    6. If budget > 1: diversity penalty + role assignment
    7. If budget == 1: role = RESOLUTION (degenerate path)
    8. Build gap summaries
    """
    if not events:
        return [], []

    # Sort events by turn
    sorted_events = sorted(events, key=lambda e: e.turn)

    # 1. Dominant power
    dominant = compute_dominant_power(history, seed)

    # 2. Base scores
    scores = compute_base_scores(sorted_events, named_events, dominant, seed,
                                  named_characters=named_characters)

    # 3. Causal links
    causal_links = compute_causal_links(sorted_events, scores)

    # 4. Clustering
    clusters = build_clusters(sorted_events, scores)

    # 5. Select top budget clusters
    clusters.sort(key=lambda c: c["score"], reverse=True)
    selected_clusters = clusters[:budget]
    unselected_clusters = clusters[budget:]

    # 6. Convert to NarrativeMoments
    # Build a map from event index to causal links involving that event
    link_map: dict[int, list[CausalLink]] = {}
    for link in causal_links:
        for idx, ev in enumerate(sorted_events):
            if ev.turn == link.cause_turn and ev.event_type == link.cause_event_type:
                link_map.setdefault(idx, []).append(link)
            if ev.turn == link.effect_turn and ev.event_type == link.effect_event_type:
                link_map.setdefault(idx, []).append(link)

    def _cluster_to_moment(cluster: dict) -> NarrativeMoment:
        indices = cluster["event_indices"]
        cluster_events = [sorted_events[i] for i in indices]
        cluster_named = [
            ne for ne in named_events
            if any(
                ne.turn == ev.turn and set(ne.actors) == set(ev.actors)
                for ev in cluster_events
            )
        ]
        cluster_links: list[CausalLink] = []
        seen_links: set[tuple] = set()
        for i in indices:
            for link in link_map.get(i, []):
                link_key = (link.cause_turn, link.cause_event_type,
                            link.effect_turn, link.effect_event_type)
                if link_key not in seen_links:
                    cluster_links.append(link)
                    seen_links.add(link_key)

        return NarrativeMoment(
            anchor_turn=cluster["anchor_turn"],
            turn_range=cluster["turn_range"],
            events=cluster_events,
            named_events=cluster_named,
            score=cluster["score"],
            causal_links=cluster_links,
            narrative_role=NarrativeRole.RESOLUTION,  # placeholder
            bonus_applied=0.0,
        )

    selected_moments = [_cluster_to_moment(c) for c in selected_clusters]
    unselected_moments = [_cluster_to_moment(c) for c in unselected_clusters]

    if budget == 1:
        # Degenerate "Narrate This" path
        selected_moments[0].narrative_role = NarrativeRole.RESOLUTION
        return selected_moments, []

    # 7. Diversity + roles
    if len(selected_moments) > 1:
        selected_moments = apply_diversity_penalty(selected_moments, unselected_moments)
        # Sort by anchor_turn before role assignment
        selected_moments.sort(key=lambda m: m.anchor_turn)
        assign_roles(selected_moments)

    # 8. Gap summaries
    selected_moments.sort(key=lambda m: m.anchor_turn)
    gap_summaries = build_gap_summaries(selected_moments, sorted_events, history)

    return selected_moments, gap_summaries
