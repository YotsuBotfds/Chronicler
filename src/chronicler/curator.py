"""Narrative curator: selects the most important moments from a simulation.

Pure Python — no LLM calls. Scores events, discovers causal links, clusters
them into narrative moments, and assigns dramatic-arc roles.

M20a Tasks 3-7.
"""
from __future__ import annotations

import bisect
import math
from collections import Counter
from typing import Sequence

from chronicler.models import (
    CausalChain,
    CausalLink,
    ChainStep,
    Event,
    GapSummary,
    NamedEvent,
    NarrativeMoment,
    NarrativeRole,
    TurnSnapshot,
)
from chronicler.utils import stable_hash_int

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
    ("cultural_renaissance", "movement_adoption", 10, 2.0),
    ("discovery", "war", 15, 2.0),
    # M43b: Supply shock causal patterns
    ("drought", "supply_shock", 5, 3.0),
    ("war", "supply_shock", 3, 2.0),
    ("embargo", "supply_shock", 3, 3.0),
    ("supply_shock", "famine", 5, 3.0),
    ("supply_shock", "rebellion", 10, 2.0),
    ("supply_shock", "migration", 10, 2.0),
    ("supply_shock", "supply_shock", 3, 2.5),
    # Phase 8 governance (events exist only when the governance runtime is on)
    ("elite_overproduction", "psi_crisis", 40, 2.5),
    ("fiscal_crisis", "institution_repealed", 15, 2.5),
    ("fiscal_crisis", "psi_crisis", 30, 2.0),
    ("psi_crisis", "revolt", 10, 3.0),
    ("psi_crisis", "secession", 20, 3.0),
    ("psi_crisis", "civil_war", 20, 3.5),
    ("revolt", "civil_war", 5, 3.0),
    ("civil_war", "succession_crisis_resolved", 10, 2.5),
    ("ambition_failed", "legitimacy_crisis", 10, 2.0),
    ("legitimacy_crisis", "civil_war", 15, 3.0),
    ("institution_enacted", "institution_repealed", 50, 1.5),
    ("psi_crisis", "psi_recovery", 60, 2.0),
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

    Ties are broken deterministically via a stable SHA256-derived hash.
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
    return min(tied, key=lambda n: stable_hash_int("dominant_power", seed, n))


# ---------------------------------------------------------------------------
# 2. compute_base_scores
# ---------------------------------------------------------------------------

def compute_base_scores(
    events: Sequence[Event],
    named_events: Sequence[NamedEvent],
    dominant_power: str,
    seed: int,
    named_characters: set[str] | None = None,
    gp_by_name: dict | None = None,  # M45
) -> list[float]:
    """Score each event based on importance, named-event match, dominant
    power involvement, and rarity.

    # M40: Relationship-aware scoring (1.2x boost for events involving related characters)
    # deferred to M45 — requires civ-to-agent mapping not yet available at curation time.

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

        # M45: Arc involvement bonus
        if gp_by_name:
            for actor in ev.actors:
                _gp = gp_by_name.get(actor)
                if _gp is None:
                    continue
                if _gp.arc_phase is not None or _gp.arc_type is not None:
                    score += 1.5
                    break

            # Arc completion bonus — the defining moment
            for actor in ev.actors:
                _gp = gp_by_name.get(actor)
                if _gp and _gp.arc_type_turn == ev.turn:
                    score += 2.5
                    break

        scores.append(score)

    return scores


# ---------------------------------------------------------------------------
# 3. Cause graph (recorded provenance) and causal links
# ---------------------------------------------------------------------------

# Chronic-episode bookkeeping events never anchor a moment or extend a chain:
# a folded repeat ("repeat", legacy timelines only) or a closing event ("end")
# belongs to its onset. A "tick" is a real new report (a renewed famine strike
# with its own causes) and counts like any other event.
_EPISODE_FOLLOWERS = frozenset({"repeat", "end"})

# Chain-score weights (see compute_chain_scores).
ROOT_DEPTH_WEIGHT = 1.5
ROOT_FANOUT_WEIGHT = 1.0
EFFECT_DEPTH_WEIGHT = 0.75
EFFECT_FANOUT_WEIGHT = 0.5
EXPLAINED_WEIGHT = 0.5
CHAIN_BONUS_CAP = 12.0
DESCENDANT_CAP = 64
MAX_CHAIN_STEPS = 6
MAX_CHAINS_PER_MOMENT = 3


class CauseGraph:
    """Recorded cause -> effect edges over one event list (by index).

    Only ``Event.causes`` that resolve to an event in the list are edges;
    unresolved ids (events outside the list) are ignored.
    """

    def __init__(self, events: Sequence[Event]) -> None:
        self.events = events
        self.index: dict[str, int] = {}
        for i, ev in enumerate(events):
            if ev.event_id and ev.event_id not in self.index:
                self.index[ev.event_id] = i
        n = len(events)
        self.parents: list[list[int]] = [[] for _ in range(n)]
        self.children: list[list[int]] = [[] for _ in range(n)]
        for j, ev in enumerate(events):
            for cid in ev.causes:
                i = self.index.get(cid)
                if i is None or i == j or i in self.parents[j]:
                    continue
                self.parents[j].append(i)
                self.children[i].append(j)
        self._down: list[int] | None = None
        self._up: list[int] | None = None

    @property
    def edge_count(self) -> int:
        return sum(len(p) for p in self.parents)

    def substantive(self, i: int) -> bool:
        return self.events[i].episode not in _EPISODE_FOLLOWERS

    def _longest(self, nbrs: list[list[int]]) -> list[int]:
        """Longest path (in substantive steps) along ``nbrs`` from each node."""
        n = len(self.events)
        memo = [-1] * n
        for start in range(n):
            if memo[start] >= 0:
                continue
            stack = [(start, 0)]
            on_path = {start}
            while stack:
                node, k = stack[-1]
                nxt = nbrs[node]
                if k < len(nxt):
                    stack[-1] = (node, k + 1)
                    child = nxt[k]
                    if memo[child] < 0 and child not in on_path:
                        on_path.add(child)
                        stack.append((child, 0))
                    continue
                best = 0
                for child in nxt:
                    if memo[child] < 0:
                        continue  # cycle guard (ids are emission-ordered; defensive)
                    step = 1 if self.substantive(child) else 0
                    best = max(best, step + memo[child])
                memo[node] = best
                on_path.discard(node)
                stack.pop()
        return memo

    def depth_down(self) -> list[int]:
        """Longest recorded consequence chain from each event."""
        if self._down is None:
            self._down = self._longest(self.children)
        return self._down

    def depth_up(self) -> list[int]:
        """Longest recorded cause chain leading to each event."""
        if self._up is None:
            self._up = self._longest(self.parents)
        return self._up

    def descendants(self, i: int, cap: int = DESCENDANT_CAP) -> int:
        """Distinct substantive consequences of event ``i`` (capped)."""
        seen = {i}
        frontier = [i]
        count = 0
        while frontier and count < cap:
            nxt = []
            for node in frontier:
                for child in self.children[node]:
                    if child in seen:
                        continue
                    seen.add(child)
                    nxt.append(child)
                    if self.substantive(child):
                        count += 1
            frontier = nxt
        return min(count, cap)

    def chain_to(self, j: int, max_steps: int = MAX_CHAIN_STEPS) -> list[int]:
        """The deepest recorded cause chain ending at ``j``, root first."""
        up = self.depth_up()
        chain = [j]
        seen = {j}
        node = j
        while self.parents[node] and len(chain) < max_steps:
            # Follow the parent with the longest history; ties -> earliest event.
            parent = max(self.parents[node], key=lambda p: (up[p], -p))
            if parent in seen:
                break
            chain.append(parent)
            seen.add(parent)
            node = parent
        chain.reverse()
        return chain


def compute_chain_scores(graph: CauseGraph) -> list[float]:
    """Score bonus per event from its place in the recorded cause graph.

    Root causes (no recorded cause of their own) with long, wide consequence
    chains rank highest: ``1.5 * depth + 1.0 * log2(1 + descendants)``.
    Effects with consequences of their own score at half weight, plus a
    small bonus for being explained (``0.5 * cause depth``). Episode
    repeats and closing events score nothing. Capped at CHAIN_BONUS_CAP.
    """
    down = graph.depth_down()
    up = graph.depth_up()
    bonus: list[float] = []
    for i in range(len(graph.events)):
        if not graph.substantive(i) or (not graph.parents[i] and not graph.children[i]):
            bonus.append(0.0)
            continue
        fan = math.log2(1 + graph.descendants(i))
        if not graph.parents[i]:
            b = ROOT_DEPTH_WEIGHT * down[i] + ROOT_FANOUT_WEIGHT * fan
        else:
            b = EFFECT_DEPTH_WEIGHT * down[i] + EFFECT_FANOUT_WEIGHT * fan + EXPLAINED_WEIGHT * up[i]
        bonus.append(min(CHAIN_BONUS_CAP, b))
    return bonus


def _link(cause: Event, effect: Event, pattern: str, provenance: str) -> CausalLink:
    return CausalLink(
        cause_turn=cause.turn,
        cause_event_type=cause.event_type,
        effect_turn=effect.turn,
        effect_event_type=effect.event_type,
        pattern=pattern,
        cause_id=cause.event_id,
        effect_id=effect.event_id,
        provenance=provenance,
    )


def _pattern_links(
    events: Sequence[Event],
    scores: list[float],
    pairs: list[tuple[int, int]] | None = None,
) -> list[CausalLink]:
    """Type-pair fallback for effects without recorded provenance.

    Only effects that carry no provenance at all (no ``event_id`` and no
    ``causes``: old saves and bundles) are linked. For each such effect and
    matching pattern, link the most recent cause of the pattern's type within
    ``max_gap`` turns that shares an actor (one link per effect per pattern,
    not every pair). The cause event's score receives the pattern bonus.
    """
    by_type: dict[str, list[int]] = {}
    for i, ev in enumerate(events):
        if ev.episode in _EPISODE_FOLLOWERS:
            continue
        by_type.setdefault(ev.event_type, []).append(i)
    found: list[tuple[int, int, int, CausalLink, int, float]] = []
    for p_idx, (cause_type, effect_type, max_gap, bonus) in enumerate(CAUSAL_PATTERNS):
        causes = by_type.get(cause_type)
        effects = by_type.get(effect_type)
        if not causes or not effects:
            continue
        cause_turns = [events[i].turn for i in causes]
        for j in effects:
            effect = events[j]
            if effect.causes or effect.event_id:
                # Recorded provenance exists: an observed event with no causes
                # has none the simulation knows of; do not guess one.
                continue
            actors = set(effect.actors)
            if not actors:
                continue
            # Causes precede the effect in list order (events are turn-sorted).
            hi = bisect.bisect_right(cause_turns, effect.turn)
            for k in range(hi - 1, -1, -1):
                i = causes[k]
                if effect.turn - events[i].turn > max_gap:
                    break
                if i >= j or not (actors & set(events[i].actors)):
                    continue
                found.append((i, j, p_idx, _link(
                    events[i], effect, f"{cause_type}\u2192{effect_type}", "pattern"), i, bonus))
                break
    found.sort(key=lambda item: (item[0], item[1], item[2]))
    for i, j, _p, _link_obj, cause_idx, bonus in found:
        scores[cause_idx] += bonus
        if pairs is not None:
            pairs.append((i, j))
    return [item[3] for item in found]


def compute_causal_links(
    events: Sequence[Event],
    scores: list[float],
    graph: "CauseGraph | None" = None,
    pairs: list[tuple[int, int]] | None = None,
) -> list[CausalLink]:
    """Causal links: recorded provenance first, type-pair patterns as fallback.

    * Recorded links are the ``Event.causes`` edges that resolve within
      ``events`` (``provenance="recorded"``); their weight enters the score
      through :func:`compute_chain_scores`, not here.
    * ``CAUSAL_PATTERNS`` link only effects without provenance (no id and no
      causes: old saves/bundles); an observed event with no causes has none
      the simulation knows of and is not guessed at. Cause and effect must
      share an actor; the cause event's score is mutated in place (bonus).
    * ``pairs``, when given, receives the (cause, effect) index of each link.
    """
    if graph is None:
        graph = CauseGraph(events)
    links: list[CausalLink] = []
    for j, parents in enumerate(graph.parents):
        for i in parents:
            cause, effect = events[i], events[j]
            links.append(_link(cause, effect,
                               f"{cause.event_type}\u2192{effect.event_type}", "recorded"))
            if pairs is not None:
                pairs.append((i, j))
    links.extend(_pattern_links(events, scores, pairs))
    return links


# Labels for hazard-rolled events, which carry no description (the narrator
# fills it in): "{a}" is the first actor, "{b}" the second, "{all}" all.
_HAZARD_LABELS: dict[str, str] = {
    "drought": "drought strikes {all}",
    "plague": "plague strikes {all}",
    "earthquake": "an earthquake shakes {all}",
    "border_incident": "a border incident between {a} and {b}",
    "rebellion": "rebellion breaks out in {a}",
    "migration": "a wave of emigration leaves {a}",
    "religious_movement": "a religious movement stirs {a}",
    "discovery": "{a} makes a discovery",
    "cultural_renaissance": "a cultural renaissance flowers in {a}",
    "leader_death": "the ruler of {a} dies",
}


def event_label(ev: Event) -> str:
    """A readable one-line label (hazard events carry no description)."""
    if ev.description:
        return ev.description
    actors = [a for a in ev.actors if a]
    template = _HAZARD_LABELS.get(ev.event_type)
    if template is not None and actors:
        return template.format(a=actors[0], b=actors[1] if len(actors) > 1 else "its neighbours",
                               all=" and ".join(actors))
    what = ev.event_type.replace("_", " ")
    return f"{what} in {', '.join(actors)}" if actors else what


def build_causal_chain(graph: CauseGraph, j: int) -> CausalChain:
    """The recorded "because" chain ending at event index ``j`` (root first)."""
    steps = []
    for i in graph.chain_to(j):
        ev = graph.events[i]
        steps.append(ChainStep(
            event_id=ev.event_id, turn=ev.turn, event_type=ev.event_type,
            description=event_label(ev), region=ev.region or ev.shock_region,
        ))
    return CausalChain(steps=steps)


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
        if events[idx].turn - events[current_cluster[0]].turn <= CLUSTER_MERGE_THRESHOLD:
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
        return snap_by_turn[best] if best is not None else None
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
    gp_by_name: dict | None = None,  # M45
    contested: dict[str, float] | None = None,
) -> tuple[list[NarrativeMoment], list[GapSummary]]:
    """Top-level curation pipeline.

    ``contested`` (``historiography.AccountIndex.contested_bonus``) maps the
    ids of events the in-world chroniclers tell differently to a score bonus,
    so moments where the accounts diverge are picked more often. None (the
    default) leaves curation exactly as it was.

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
                                  named_characters=named_characters,
                                  gp_by_name=gp_by_name)

    # 3. Cause graph: recorded provenance scores by chain depth and fan-out;
    # type-pair patterns link only effects without recorded causes.
    graph = CauseGraph(sorted_events)
    for i, bonus in enumerate(compute_chain_scores(graph)):
        scores[i] += bonus
    if contested:
        for i, ev in enumerate(sorted_events):
            if ev.event_id and ev.event_id in contested:
                scores[i] += contested[ev.event_id]
    for i, ev in enumerate(sorted_events):
        if ev.episode in _EPISODE_FOLLOWERS:
            # Repeats and closing events of a chronic episode never anchor.
            scores[i] = min(scores[i], max(1.0, float(ev.importance) - 3.0))
    link_pairs: list[tuple[int, int]] = []
    causal_links = compute_causal_links(sorted_events, scores, graph=graph, pairs=link_pairs)

    # 4. Clustering
    clusters = build_clusters(sorted_events, scores)

    # 5. Select top budget clusters
    clusters.sort(key=lambda c: c["score"], reverse=True)
    selected_clusters = clusters[:budget]
    unselected_clusters = clusters[budget:]

    # 6. Convert to NarrativeMoments
    # Map each event index to the links it takes part in (cause or effect).
    link_map: dict[int, list[CausalLink]] = {}
    for link, (ci, ei) in zip(causal_links, link_pairs):
        link_map.setdefault(ci, []).append(link)
        if ei != ci:
            link_map.setdefault(ei, []).append(link)

    def _moment_chains(indices: list[int]) -> list[CausalChain]:
        """Deepest recorded "because" chains ending in this moment."""
        up = graph.depth_up()
        candidates = [i for i in indices if graph.parents[i] and graph.substantive(i)]
        candidates.sort(key=lambda i: (-up[i], -scores[i], i))
        chains: list[CausalChain] = []
        covered: set[int] = set()
        for i in candidates:
            if len(chains) >= MAX_CHAINS_PER_MOMENT:
                break
            path = graph.chain_to(i)
            if len(path) < 2 or i in covered:
                continue
            covered.update(path)
            chains.append(build_causal_chain(graph, i))
        return chains

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
                if link.cause_id and link.effect_id:
                    link_key: tuple = (link.cause_id, link.effect_id)
                else:
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
            causal_chains=_moment_chains(indices),
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
