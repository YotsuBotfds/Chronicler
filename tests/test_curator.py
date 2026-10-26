"""Tests for the narrative curator module (M20a Tasks 3-7)."""
from __future__ import annotations

import pytest

from chronicler.models import (
    CausalLink,
    CivSnapshot,
    Event,
    GapSummary,
    NamedEvent,
    NarrativeMoment,
    NarrativeRole,
    TechEra,
    TurnSnapshot,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_snapshot(turn: int, region_control: dict[str, str | None]) -> TurnSnapshot:
    return TurnSnapshot(
        turn=turn,
        civ_stats={
            name: CivSnapshot(
                population=100, military=50, economy=50, culture=50,
                stability=50, treasury=100, asabiya=0.5,
                tech_era=TechEra.CLASSICAL, trait="aggressive",
                regions=[r for r, c in region_control.items() if c == name],
                leader_name="Leader", alive=True,
            )
            for name in set(c for c in region_control.values() if c)
        },
        region_control=region_control,
        relationships={},
    )


def _make_event(turn: int, event_type: str, actors: list[str],
                importance: int = 5) -> Event:
    return Event(
        turn=turn,
        event_type=event_type,
        actors=actors,
        description=f"{event_type} at turn {turn}",
        importance=importance,
    )


def _make_named(turn: int, event_type: str, actors: list[str],
                importance: int = 5) -> NamedEvent:
    return NamedEvent(
        name=f"The Great {event_type.title()}",
        event_type=event_type,
        turn=turn,
        actors=actors,
        description=f"Named {event_type} at turn {turn}",
        importance=importance,
    )


# ---------------------------------------------------------------------------
# 1. compute_dominant_power
# ---------------------------------------------------------------------------

class TestDominantPower:
    def test_dominant_power_cumulative(self):
        """A holds 5 regions for 3 turns, B holds 3 for 1 turn -> A wins."""
        from chronicler.curator import compute_dominant_power

        rc_a5 = {"r1": "A", "r2": "A", "r3": "A", "r4": "A", "r5": "A"}
        rc_b3 = {"r1": "B", "r2": "B", "r3": "B", "r4": None, "r5": None}
        history = [
            _make_snapshot(1, rc_a5),
            _make_snapshot(2, rc_a5),
            _make_snapshot(3, rc_a5),
            _make_snapshot(4, rc_b3),
        ]
        assert compute_dominant_power(history, seed=0) == "A"

    def test_dominant_power_tiebreak(self):
        """Equal region-turns, deterministic hash tiebreak."""
        from chronicler.curator import compute_dominant_power

        rc = {"r1": "Alpha", "r2": "Beta"}
        history = [_make_snapshot(1, rc), _make_snapshot(2, rc)]
        result = compute_dominant_power(history, seed=42)
        assert result in ("Alpha", "Beta")
        # Deterministic: same seed always yields same result
        assert compute_dominant_power(history, seed=42) == result
        # Different seed may yield different result (or same, but must be deterministic)
        result2 = compute_dominant_power(history, seed=99)
        assert result2 in ("Alpha", "Beta")
        assert compute_dominant_power(history, seed=99) == result2


# ---------------------------------------------------------------------------
# 2. compute_base_scores
# ---------------------------------------------------------------------------

class TestBaseScoring:
    def test_base_scoring_importance(self):
        """Base score starts at event.importance."""
        from chronicler.curator import compute_base_scores

        events = [_make_event(1, "war", ["A"], importance=7)]
        scores = compute_base_scores(events, [], dominant_power="X", seed=0)
        # No bonuses should apply: not named, not dominant, war appears <3 times so +2 rarity
        assert scores[0] == 7 + 2  # importance + rarity (only 1 war < 3)

    def test_base_scoring_named_event_bonus(self):
        """Named event matching by turn + actors gives +3."""
        from chronicler.curator import compute_base_scores

        events = [_make_event(5, "battle", ["A", "B"], importance=5)]
        named = [_make_named(5, "battle", ["A", "B"])]
        scores = compute_base_scores(events, named, dominant_power="X", seed=0)
        # 5 (base) + 3 (named) + 2 (rarity, <3) = 10
        assert scores[0] == 10

    def test_base_scoring_dominant_power_bonus(self):
        """Dominant power involvement gives +2."""
        from chronicler.curator import compute_base_scores

        events = [_make_event(1, "war", ["DomPow", "B"], importance=5)]
        scores = compute_base_scores(events, [], dominant_power="DomPow", seed=0)
        # 5 (base) + 2 (dominant) + 2 (rarity) = 9
        assert scores[0] == 9

    def test_base_scoring_rarity_bonus(self):
        """Event types occurring <3 times get +2; types with >=3 don't."""
        from chronicler.curator import compute_base_scores

        events = [
            _make_event(1, "war", ["A"], importance=5),
            _make_event(2, "war", ["A"], importance=5),
            _make_event(3, "war", ["A"], importance=5),  # 3 wars -> not rare
            _make_event(4, "plague", ["A"], importance=5),  # 1 plague -> rare
        ]
        scores = compute_base_scores(events, [], dominant_power="X", seed=0)
        # War events (3 occurrences) -> no rarity bonus
        assert scores[0] == 5  # war, not rare
        assert scores[1] == 5
        assert scores[2] == 5
        # Plague (1 occurrence) -> +2 rarity
        assert scores[3] == 7


# ---------------------------------------------------------------------------
# 3. compute_causal_links
# ---------------------------------------------------------------------------

class TestCausalLinks:
    def test_causal_link_within_max_gap(self):
        """Drought->famine within max_gap=10: should link."""
        from chronicler.curator import compute_causal_links

        events = [
            _make_event(5, "drought", ["A"], importance=5),
            _make_event(12, "famine", ["A"], importance=5),
        ]
        scores = [5.0, 5.0]
        links = compute_causal_links(events, scores)
        assert len(links) == 1
        assert links[0].cause_event_type == "drought"
        assert links[0].effect_event_type == "famine"
        assert links[0].pattern == "drought→famine"
        # Cause event gets bonus
        assert scores[0] == 5.0 + 3.0  # drought->famine bonus is 3.0

    def test_causal_link_beyond_max_gap(self):
        """Drought->famine beyond max_gap=10: no link."""
        from chronicler.curator import compute_causal_links

        events = [
            _make_event(5, "drought", ["A"], importance=5),
            _make_event(20, "famine", ["A"], importance=5),  # gap = 15 > 10
        ]
        scores = [5.0, 5.0]
        links = compute_causal_links(events, scores)
        assert len(links) == 0
        assert scores[0] == 5.0  # no bonus

    def test_causal_link_spatial_filter(self):
        """Different actors: no link even if within max_gap."""
        from chronicler.curator import compute_causal_links

        events = [
            _make_event(5, "drought", ["A"], importance=5),
            _make_event(10, "famine", ["B"], importance=5),  # different actor
        ]
        scores = [5.0, 5.0]
        links = compute_causal_links(events, scores)
        assert len(links) == 0

    def test_causal_link_multiple_bonuses(self):
        """War->leader_death + war->collapse: cause gets both bonuses."""
        from chronicler.curator import compute_causal_links

        events = [
            _make_event(10, "war", ["A", "B"], importance=5),
            _make_event(14, "leader_death", ["A"], importance=5),  # gap=4 <= 5
            _make_event(25, "collapse", ["A"], importance=5),  # gap=15 <= 20
        ]
        scores = [5.0, 5.0, 5.0]
        links = compute_causal_links(events, scores)
        # war->leader_death (max_gap=5, bonus=2.0) + war->collapse (max_gap=20, bonus=4.0)
        assert len(links) == 2
        assert scores[0] == 5.0 + 2.0 + 4.0  # both bonuses on cause


# ---------------------------------------------------------------------------
# 4. build_clusters
# ---------------------------------------------------------------------------

class TestClusters:
    def test_cluster_merge_within_threshold(self):
        """Events within CLUSTER_MERGE_THRESHOLD turns merge."""
        from chronicler.curator import build_clusters

        events = [
            _make_event(10, "war", ["A"], importance=5),
            _make_event(12, "battle", ["A"], importance=7),
            _make_event(14, "famine", ["A"], importance=3),
        ]
        scores = [5.0, 7.0, 3.0]
        clusters = build_clusters(events, scores)
        # All within 5 turns, should be one cluster
        assert len(clusters) == 1
        assert clusters[0]["turn_range"] == (10, 14)
        assert set(clusters[0]["event_indices"]) == {0, 1, 2}

    def test_cluster_anchor_turn(self):
        """Anchor is the turn of the highest-scoring event."""
        from chronicler.curator import build_clusters

        events = [
            _make_event(10, "war", ["A"], importance=5),
            _make_event(12, "battle", ["A"], importance=7),
            _make_event(14, "famine", ["A"], importance=3),
        ]
        scores = [5.0, 9.0, 3.0]  # event at turn 12 has highest score
        clusters = build_clusters(events, scores)
        assert clusters[0]["anchor_turn"] == 12

    def test_cluster_score_top3(self):
        """Cluster score = best member + half the second + a quarter of the third."""
        from chronicler.curator import build_clusters

        events = [
            _make_event(10, "a", ["A"], importance=5),
            _make_event(11, "b", ["A"], importance=7),
            _make_event(12, "c", ["A"], importance=3),
            _make_event(13, "d", ["A"], importance=8),
        ]
        scores = [5.0, 7.0, 3.0, 8.0]
        clusters = build_clusters(events, scores)
        # 8.0 + 0.5 * 7.0 + 0.25 * 5.0 = 12.75
        assert clusters[0]["score"] == 12.75

    def test_one_great_event_outweighs_a_crowd_of_middling_ones(self):
        from chronicler.curator import build_clusters

        events = [_make_event(10, "a", ["A"]), _make_event(11, "b", ["A"]), _make_event(12, "c", ["A"]),
                  _make_event(30, "d", ["B"])]
        clusters = build_clusters(events, [7.0, 7.0, 7.0, 13.0])
        assert clusters[1]["score"] > clusters[0]["score"]  # 13 > 7 + 3.5 + 1.75

    def test_separate_clusters(self):
        """Events far apart form separate clusters."""
        from chronicler.curator import build_clusters

        events = [
            _make_event(10, "war", ["A"], importance=5),
            _make_event(30, "famine", ["A"], importance=7),
        ]
        scores = [5.0, 7.0]
        clusters = build_clusters(events, scores)
        assert len(clusters) == 2


# ---------------------------------------------------------------------------
# 5. apply_diversity_penalty
# ---------------------------------------------------------------------------

class TestDiversityPenalty:
    def test_diversity_penalty_civ(self):
        """If >40% of moments involve same civ, lowest-scored is demoted."""
        from chronicler.curator import apply_diversity_penalty

        # 3 of 5 moments (60%) involve "A" -> should trigger penalty
        def _moment(turn: int, actors: list[str], score: float,
                    is_named: bool = False) -> NarrativeMoment:
            evts = [_make_event(turn, "war", actors, importance=5)]
            named = [_make_named(turn, "war", actors)] if is_named else []
            return NarrativeMoment(
                anchor_turn=turn,
                turn_range=(turn, turn),
                events=evts,
                named_events=named,
                score=score,
                causal_links=[],
                narrative_role=NarrativeRole.ESCALATION,
                bonus_applied=0.0,
            )

        selected = [
            _moment(1, ["A"], 10.0),
            _moment(2, ["A"], 8.0),
            _moment(3, ["A"], 6.0),  # lowest A-involved, should be demoted
            _moment(4, ["B"], 5.0),
            _moment(5, ["C"], 4.0),
        ]
        unselected = [
            _moment(6, ["D"], 3.0),
            _moment(7, ["E"], 2.0),
        ]
        result = apply_diversity_penalty(selected, unselected)
        # After demotion, A should appear in <=40% (i.e., <=2 of 5)
        a_count = sum(
            1 for m in result
            if any("A" in e.actors for e in m.events)
        )
        assert a_count <= 2

    def test_diversity_penalty_named_exempt(self):
        """Moments with a landmark (a named event of importance 7+) are not demoted."""
        from chronicler.curator import apply_diversity_penalty

        def _moment(turn: int, actors: list[str], score: float,
                    is_named: bool = False) -> NarrativeMoment:
            evts = [_make_event(turn, "war", actors, importance=5)]
            named = [_make_named(turn, "war", actors, importance=7)] if is_named else []
            return NarrativeMoment(
                anchor_turn=turn,
                turn_range=(turn, turn),
                events=evts,
                named_events=named,
                score=score,
                causal_links=[],
                narrative_role=NarrativeRole.ESCALATION,
                bonus_applied=0.0,
            )

        selected = [
            _moment(1, ["A"], 10.0, is_named=True),
            _moment(2, ["A"], 8.0, is_named=True),
            _moment(3, ["A"], 6.0, is_named=True),  # named, cannot be demoted
            _moment(4, ["B"], 5.0),
            _moment(5, ["C"], 4.0),
        ]
        unselected = [
            _moment(6, ["D"], 3.0),
        ]
        result = apply_diversity_penalty(selected, unselected)
        # All named A moments should remain
        a_named = sum(
            1 for m in result
            if m.named_events and any("A" in e.actors for e in m.events)
        )
        assert a_named == 3

    def test_minor_named_events_do_not_exempt_a_moment(self):
        """A treaty or a legacy (importance 5) falls in nearly every window of a long run."""
        from chronicler.curator import apply_diversity_penalty

        def _moment(turn: int, actors: list[str], score: float) -> NarrativeMoment:
            return NarrativeMoment(
                anchor_turn=turn, turn_range=(turn, turn),
                events=[_make_event(turn, "war", actors, importance=5)],
                named_events=[_make_named(turn, "treaty", actors, importance=5)],
                score=score, causal_links=[], narrative_role=NarrativeRole.ESCALATION,
                bonus_applied=0.0,
            )

        selected = [_moment(1, ["A"], 10.0), _moment(2, ["A"], 8.0), _moment(3, ["A"], 6.0),
                    _moment(4, ["B"], 5.0), _moment(5, ["C"], 4.0)]
        result = apply_diversity_penalty(selected, [_moment(6, ["D"], 3.0), _moment(7, ["E"], 2.0)])
        assert sum(1 for m in result if any("A" in e.actors for e in m.events)) <= 2

    def test_dominant_type_ignores_routine_events(self):
        """A window full of routine actions is dominated by its one famine."""
        from chronicler.curator import _dominant_type

        events = [_make_event(1, "develop", ["A"], importance=3) for _ in range(9)]
        events.append(_make_event(2, "famine", ["A"], importance=8))
        m = NarrativeMoment(anchor_turn=2, turn_range=(1, 2), events=events, named_events=[],
                            score=1.0, causal_links=[], narrative_role=NarrativeRole.CLIMAX,
                            bonus_applied=0.0)
        assert _dominant_type(m) == "famine"

    def test_moment_civs_are_its_main_actors(self):
        """Every civ named by some event is not every civ the moment is about."""
        from chronicler.curator import _moment_civs

        events = [_make_event(1, "famine", ["A"], importance=8),
                  _make_event(1, "war", ["A", "B"], importance=7),
                  _make_event(1, "plague", ["C"], importance=6),
                  _make_event(1, "develop", ["D"], importance=3)]
        m = NarrativeMoment(anchor_turn=1, turn_range=(1, 1), events=events, named_events=[],
                            score=1.0, causal_links=[], narrative_role=NarrativeRole.CLIMAX,
                            bonus_applied=0.0)
        assert _moment_civs(m) == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# 6. assign_roles
# ---------------------------------------------------------------------------

class TestRoleAssignment:
    def _moment(self, turn: int, score: float) -> NarrativeMoment:
        return NarrativeMoment(
            anchor_turn=turn,
            turn_range=(turn, turn),
            events=[_make_event(turn, "war", ["A"], importance=5)],
            named_events=[],
            score=score,
            causal_links=[],
            narrative_role=NarrativeRole.RESOLUTION,  # placeholder
            bonus_applied=0.0,
        )

    def test_role_assignment_basic(self):
        """Standard 5-moment arc: INCITING, ESCALATION, CLIMAX, RESOLUTION, CODA."""
        from chronicler.curator import assign_roles

        moments = [
            self._moment(1, 5.0),
            self._moment(10, 6.0),
            self._moment(20, 10.0),  # highest = CLIMAX
            self._moment(30, 4.0),
            self._moment(40, 3.0),
        ]
        assign_roles(moments)
        assert moments[0].narrative_role == NarrativeRole.INCITING
        assert moments[1].narrative_role == NarrativeRole.ESCALATION
        assert moments[2].narrative_role == NarrativeRole.CLIMAX
        assert moments[3].narrative_role == NarrativeRole.RESOLUTION
        assert moments[4].narrative_role == NarrativeRole.CODA

    def test_role_assignment_climax_first(self):
        """Climax is first moment -> no INCITING/ESCALATION before it."""
        from chronicler.curator import assign_roles

        moments = [
            self._moment(1, 10.0),  # highest = CLIMAX
            self._moment(10, 5.0),
            self._moment(20, 3.0),
        ]
        assign_roles(moments)
        assert moments[0].narrative_role == NarrativeRole.CLIMAX
        assert moments[1].narrative_role == NarrativeRole.RESOLUTION
        assert moments[2].narrative_role == NarrativeRole.CODA

    def test_role_assignment_climax_last(self):
        """Climax is last moment -> CODA doesn't override."""
        from chronicler.curator import assign_roles

        moments = [
            self._moment(1, 3.0),
            self._moment(10, 5.0),
            self._moment(20, 10.0),  # highest = CLIMAX, last position
        ]
        assign_roles(moments)
        assert moments[0].narrative_role == NarrativeRole.INCITING
        assert moments[1].narrative_role == NarrativeRole.ESCALATION
        assert moments[2].narrative_role == NarrativeRole.CLIMAX

    def test_role_assignment_single_moment(self):
        """Single moment = CLIMAX."""
        from chronicler.curator import assign_roles

        moments = [self._moment(1, 5.0)]
        assign_roles(moments)
        assert moments[0].narrative_role == NarrativeRole.CLIMAX


# ---------------------------------------------------------------------------
# 7. build_gap_summaries
# ---------------------------------------------------------------------------

class TestGapSummary:
    def test_gap_summary_between_moments(self):
        """Gap between moments has correct turn ranges and event counts."""
        from chronicler.curator import build_gap_summaries

        m1 = NarrativeMoment(
            anchor_turn=5, turn_range=(3, 7),
            events=[_make_event(5, "war", ["A"])],
            named_events=[], score=5.0, causal_links=[],
            narrative_role=NarrativeRole.INCITING, bonus_applied=0.0,
        )
        m2 = NarrativeMoment(
            anchor_turn=15, turn_range=(13, 17),
            events=[_make_event(15, "famine", ["A"])],
            named_events=[], score=5.0, causal_links=[],
            narrative_role=NarrativeRole.CLIMAX, bonus_applied=0.0,
        )
        all_events = [
            _make_event(5, "war", ["A"]),
            _make_event(9, "trade", ["A"]),
            _make_event(10, "trade", ["B"]),
            _make_event(11, "trade", ["A"]),
            _make_event(15, "famine", ["A"]),
        ]
        history = [
            _make_snapshot(7, {"r1": "A"}),
            _make_snapshot(13, {"r1": "A"}),
        ]
        gaps = build_gap_summaries([m1, m2], all_events, history)
        assert len(gaps) == 1
        assert gaps[0].turn_range == (8, 12)
        assert gaps[0].event_count == 3  # turns 9, 10, 11
        assert gaps[0].top_event_type == "trade"

    def test_gap_summary_stat_deltas(self):
        """Per-civ stat diffs computed from snapshots."""
        from chronicler.curator import build_gap_summaries

        m1 = NarrativeMoment(
            anchor_turn=5, turn_range=(3, 7),
            events=[_make_event(5, "war", ["A"])],
            named_events=[], score=5.0, causal_links=[],
            narrative_role=NarrativeRole.INCITING, bonus_applied=0.0,
        )
        m2 = NarrativeMoment(
            anchor_turn=15, turn_range=(13, 17),
            events=[_make_event(15, "famine", ["A"])],
            named_events=[], score=5.0, causal_links=[],
            narrative_role=NarrativeRole.CLIMAX, bonus_applied=0.0,
        )
        snap1 = _make_snapshot(7, {"r1": "A"})
        # Modify snap2 to have different stats
        snap2 = _make_snapshot(13, {"r1": "A"})
        snap2.civ_stats["A"].population = 120  # was 100, delta = +20
        snap2.civ_stats["A"].military = 30   # was 50, delta = -20

        history = [snap1, snap2]
        gaps = build_gap_summaries([m1, m2], [], history)
        assert len(gaps) == 1
        assert gaps[0].stat_deltas["A"]["population"] == 20
        assert gaps[0].stat_deltas["A"]["military"] == -20

    def test_gap_summary_territory_changes(self):
        """Territory changes counted from region controller changes."""
        from chronicler.curator import build_gap_summaries

        m1 = NarrativeMoment(
            anchor_turn=5, turn_range=(3, 7),
            events=[_make_event(5, "war", ["A"])],
            named_events=[], score=5.0, causal_links=[],
            narrative_role=NarrativeRole.INCITING, bonus_applied=0.0,
        )
        m2 = NarrativeMoment(
            anchor_turn=15, turn_range=(13, 17),
            events=[_make_event(15, "famine", ["A"])],
            named_events=[], score=5.0, causal_links=[],
            narrative_role=NarrativeRole.CLIMAX, bonus_applied=0.0,
        )
        snap1 = _make_snapshot(7, {"r1": "A", "r2": "A"})
        snap2 = _make_snapshot(13, {"r1": "B", "r2": "A"})  # r1 changed

        history = [snap1, snap2]
        gaps = build_gap_summaries([m1, m2], [], history)
        assert gaps[0].territory_changes == 1


# ---------------------------------------------------------------------------
# 8. curate (end-to-end)
# ---------------------------------------------------------------------------

class TestCurate:
    def test_curate_end_to_end(self):
        """Full pipeline produces moments + gaps."""
        from chronicler.curator import curate

        events = [
            _make_event(1, "war", ["A", "B"], importance=8),
            _make_event(5, "drought", ["A"], importance=6),
            _make_event(12, "famine", ["A"], importance=7),
            _make_event(20, "rebellion", ["A"], importance=9),
            _make_event(25, "collapse", ["B"], importance=10),
            _make_event(30, "trade", ["A", "C"], importance=4),
            _make_event(35, "plague", ["C"], importance=6),
            _make_event(40, "migration", ["A"], importance=5),
        ]
        named = [_make_named(20, "rebellion", ["A"], importance=9)]
        history = [
            _make_snapshot(t, {"r1": "A", "r2": "B", "r3": "C"})
            for t in range(0, 45, 5)
        ]
        moments, gaps = curate(events, named, history, budget=5, seed=42)
        assert len(moments) >= 1
        assert len(moments) <= 5
        # Moments should be sorted by anchor_turn
        for i in range(len(moments) - 1):
            assert moments[i].anchor_turn <= moments[i + 1].anchor_turn
        # Should have roles assigned
        roles = {m.narrative_role for m in moments}
        assert NarrativeRole.CLIMAX in roles
        # Gaps between moments
        if len(moments) > 1:
            assert len(gaps) == len(moments) - 1

    def test_curate_degenerate_narrate_this(self):
        """budget=1: role=RESOLUTION, no diversity penalty."""
        from chronicler.curator import curate

        events = [
            _make_event(5, "war", ["A", "B"], importance=8),
            _make_event(10, "famine", ["A"], importance=7),
        ]
        history = [
            _make_snapshot(0, {"r1": "A", "r2": "B"}),
            _make_snapshot(10, {"r1": "A", "r2": "B"}),
        ]
        moments, gaps = curate(events, [], history, budget=1, seed=0)
        assert len(moments) == 1
        assert moments[0].narrative_role == NarrativeRole.RESOLUTION
        assert gaps == []

    def test_curate_empty_events(self):
        """No events produces no moments."""
        from chronicler.curator import curate

        history = [_make_snapshot(0, {"r1": "A"})]
        moments, gaps = curate([], [], history, budget=5, seed=0)
        assert moments == []
        assert gaps == []


# ---------------------------------------------------------------------------
# 9. M40: Relationship boost — deferred to M45
# ---------------------------------------------------------------------------
# Relationship-aware scoring (1.2x boost) requires civ-to-agent mapping
# not yet available at curation time. See compute_base_scores docstring.


# ---------------------------------------------------------------------------
# 10. Temporal spread
# ---------------------------------------------------------------------------

class TestSpread:
    @staticmethod
    def _m(turn: int, score: float, landmark: bool = False, great: bool = False) -> NarrativeMoment:
        return NarrativeMoment(
            anchor_turn=turn, turn_range=(turn, turn + 5),
            events=[_make_event(turn, "war", ["A"], importance=9 if great else 5)],
            named_events=[_make_named(turn, "war", ["A"], importance=7)] if landmark else [],
            score=score, causal_links=[], narrative_role=NarrativeRole.ESCALATION,
            bonus_applied=0.0)

    def test_a_long_untold_stretch_gets_its_best_moment_in_place_of_the_weakest(self):
        from chronicler.curator import spread_moments
        # Four moments crowd turns 0-23; turns 24-59 are untold (limit 2 x 60 / 4 = 30).
        sel = [self._m(0, 20), self._m(6, 19), self._m(12, 18), self._m(18, 30)]
        pool = [self._m(30, 10), self._m(42, 15), self._m(54, 12)]
        out = spread_moments(sel, pool, 0, 59)
        assert [m.anchor_turn for m in out] == [0, 6, 18, 42]
        # Not at any price: a stretch whose best scores under 75% stays untold.
        weak = [self._m(30, 10), self._m(42, 13), self._m(54, 12)]
        assert [m.anchor_turn for m in spread_moments(sel, weak, 0, 59)] == [0, 6, 12, 18]

    def test_great_events_stay_and_a_spread_run_is_left_alone(self):
        from chronicler.curator import spread_moments
        sel = [self._m(0, 20, great=True), self._m(6, 19, great=True), self._m(12, 18, great=True),
               self._m(18, 30)]
        # Every moment holds an importance-9 event or borders the stretch: nothing can go.
        assert [m.anchor_turn for m in spread_moments(sel, [self._m(42, 29)], 0, 59)] == [0, 6, 12, 18]
        # A minor landmark (a named event of importance 7) is weighed by its score.
        minor = [self._m(0, 20, landmark=True), self._m(6, 19, great=True), self._m(12, 18, great=True),
                 self._m(18, 30)]
        assert [m.anchor_turn for m in spread_moments(minor, [self._m(42, 29)], 0, 59)] == [6, 12, 18, 42]
        even = [self._m(t, 20) for t in (0, 15, 30, 45)]
        assert spread_moments(even, [self._m(6, 50)], 0, 59) == even

    def test_curate_is_deterministic_and_spreads_a_clustered_run(self, monkeypatch):
        import chronicler.curator as C
        events = [_make_event(t, "famine" if t < 40 else "drought", ["A" if t % 2 else "B"],
                              importance=8 if t < 40 else 6) for t in range(120)]
        hist = [_make_snapshot(t, {"r": "A"}) for t in range(0, 120, 10)]
        first, _ = C.curate(events, [], hist, budget=8, seed=1)
        again, _ = C.curate(events, [], hist, budget=8, seed=1)
        assert [m.turn_range for m in first] == [m.turn_range for m in again]
        monkeypatch.setattr(C, "SPREAD_GAP", 0.0)
        before, _ = C.curate(events, [], hist, budget=8, seed=1)

        def longest(moments):
            return max(e - s + 1 for s, e in C._untold(moments, 0, 119))
        assert longest(first) < longest(before)
