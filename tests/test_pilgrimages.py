"""Tests for M38b pilgrimage subsystem: candidate guards, destination selection,
return lifecycle, and duration constants."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Stub out the Rust extension so tests run without a compiled wheel
if "chronicler_agents" not in sys.modules:
    sys.modules["chronicler_agents"] = MagicMock()

import pyarrow as pa
import pytest

from chronicler.models import GreatPerson, Infrastructure, InfrastructureType
from chronicler.great_persons import check_pilgrimages
from chronicler.religion import (
    PILGRIMAGE_DURATION_MIN,
    PILGRIMAGE_DURATION_MAX,
    PILGRIMAGE_SKILL_BOOST,
    _PRIEST_OCCUPATION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gp(name="Pilgrim", role="prophet", trait="pious",
             civilization="CivA", agent_id=1) -> GreatPerson:
    return GreatPerson(
        name=name,
        role=role,
        trait=trait,
        civilization=civilization,
        origin_civilization=civilization,
        born_turn=0,
        agent_id=agent_id,
    )


def _make_snapshot(
    agent_id: int,
    occupation: int,
    loyalty_trait: float,
    loyalty: float,
    belief: int,
) -> pa.RecordBatch:
    """Build a minimal per-agent snapshot RecordBatch for one agent."""
    return pa.record_batch({
        "id": pa.array([agent_id], type=pa.uint32()),
        "region": pa.array([0], type=pa.uint16()),
        "origin_region": pa.array([0], type=pa.uint16()),
        "civ_affinity": pa.array([0], type=pa.uint16()),
        "occupation": pa.array([occupation], type=pa.uint8()),
        "loyalty": pa.array([loyalty], type=pa.float32()),
        "satisfaction": pa.array([0.5], type=pa.float32()),
        "skill": pa.array([0.5], type=pa.float32()),
        "age": pa.array([10], type=pa.uint16()),
        "displacement_turn": pa.array([0], type=pa.uint16()),
        "boldness": pa.array([0.0], type=pa.float32()),
        "ambition": pa.array([0.0], type=pa.float32()),
        "loyalty_trait": pa.array([loyalty_trait], type=pa.float32()),
        "belief": pa.array([belief], type=pa.uint8()),
    })


def _make_temple(faith_id: int, prestige: int) -> Infrastructure:
    return Infrastructure(
        type=InfrastructureType.TEMPLES,
        builder_civ="CivA",
        built_turn=0,
        faith_id=faith_id,
        temple_prestige=prestige,
    )


# ---------------------------------------------------------------------------
# TestCandidateGuards
# ---------------------------------------------------------------------------

class TestCandidateGuards:
    def test_already_on_pilgrimage_skipped(self):
        """A GP already on pilgrimage must not be given a second pilgrimage."""
        gp = _make_gp(agent_id=1)
        gp.pilgrimage_return_turn = 99  # already on pilgrimage
        gp.pilgrimage_destination = "Holy City"

        snap = _make_snapshot(
            agent_id=1,
            occupation=_PRIEST_OCCUPATION,
            loyalty_trait=0.8,
            loyalty=0.8,
            belief=0,
        )
        temple = _make_temple(faith_id=0, prestige=10)
        temples = [("SomeRegion", temple)]

        events = check_pilgrimages([gp], temples, snap, current_turn=5, belief_registry=[])

        # Only a return event is possible at turn 5 < 99; no departure
        departure_events = [e for e in events if e.event_type == "pilgrimage_departure"]
        assert departure_events == [], "GP already on pilgrimage must not depart again"
        # destination unchanged
        assert gp.pilgrimage_destination == "Holy City"

    def test_already_prophet_skipped(self):
        """A GP with arc_type=='Prophet' must not depart."""
        gp = _make_gp(agent_id=1)
        gp.arc_type = "Prophet"

        snap = _make_snapshot(
            agent_id=1,
            occupation=_PRIEST_OCCUPATION,
            loyalty_trait=0.8,
            loyalty=0.8,
            belief=0,
        )
        temple = _make_temple(faith_id=0, prestige=10)
        temples = [("HolyCity", temple)]

        events = check_pilgrimages([gp], temples, snap, current_turn=5, belief_registry=[])

        departure_events = [e for e in events if e.event_type == "pilgrimage_departure"]
        assert departure_events == []
        assert gp.pilgrimage_destination is None


# ---------------------------------------------------------------------------
# TestDestinationSelection
# ---------------------------------------------------------------------------

class TestDestinationSelection:
    def test_highest_prestige_temple_wins(self):
        """When multiple temples share the same faith, the highest-prestige one wins."""
        gp = _make_gp(agent_id=1)

        snap = _make_snapshot(
            agent_id=1,
            occupation=_PRIEST_OCCUPATION,
            loyalty_trait=0.0,  # priest so no loyalty_trait requirement
            loyalty=0.9,
            belief=0,
        )

        low_temple = _make_temple(faith_id=0, prestige=5)
        high_temple = _make_temple(faith_id=0, prestige=20)
        other_faith_temple = _make_temple(faith_id=1, prestige=100)

        temples = [
            ("LowPrestigeRegion", low_temple),
            ("HighPrestigeRegion", high_temple),
            ("WrongFaithRegion", other_faith_temple),
        ]

        events = check_pilgrimages([gp], temples, snap, current_turn=1, belief_registry=[])

        departure_events = [e for e in events if e.event_type == "pilgrimage_departure"]
        assert len(departure_events) == 1
        assert gp.pilgrimage_destination == "HighPrestigeRegion"

    def test_no_matching_temple_no_departure(self):
        """If no temple matches the GP's faith, no pilgrimage departs."""
        gp = _make_gp(agent_id=1)

        snap = _make_snapshot(
            agent_id=1,
            occupation=_PRIEST_OCCUPATION,
            loyalty_trait=0.0,
            loyalty=0.9,
            belief=2,  # faith 2
        )

        temple = _make_temple(faith_id=0, prestige=10)  # faith 0 — wrong
        temples = [("SomeRegion", temple)]

        events = check_pilgrimages([gp], temples, snap, current_turn=1, belief_registry=[])

        departure_events = [e for e in events if e.event_type == "pilgrimage_departure"]
        assert departure_events == []
        assert gp.pilgrimage_destination is None

    def test_one_departure_per_faith_per_turn(self):
        """Only one GP per faith may depart per turn."""
        gp1 = _make_gp(name="GpOne", agent_id=1)
        gp2 = _make_gp(name="GpTwo", agent_id=2)

        snap = pa.record_batch({
            "id": pa.array([1, 2], type=pa.uint32()),
            "region": pa.array([0, 0], type=pa.uint16()),
            "origin_region": pa.array([0, 0], type=pa.uint16()),
            "civ_affinity": pa.array([0, 0], type=pa.uint16()),
            "occupation": pa.array([_PRIEST_OCCUPATION, _PRIEST_OCCUPATION], type=pa.uint8()),
            "loyalty": pa.array([0.9, 0.9], type=pa.float32()),
            "satisfaction": pa.array([0.5, 0.5], type=pa.float32()),
            "skill": pa.array([0.5, 0.5], type=pa.float32()),
            "age": pa.array([10, 10], type=pa.uint16()),
            "displacement_turn": pa.array([0, 0], type=pa.uint16()),
            "boldness": pa.array([0.0, 0.0], type=pa.float32()),
            "ambition": pa.array([0.0, 0.0], type=pa.float32()),
            "loyalty_trait": pa.array([0.0, 0.0], type=pa.float32()),
            "belief": pa.array([0, 0], type=pa.uint8()),  # same faith
        })

        temple = _make_temple(faith_id=0, prestige=10)
        temples = [("HolyCity", temple)]

        events = check_pilgrimages([gp1, gp2], temples, snap, current_turn=1, belief_registry=[])

        departure_events = [e for e in events if e.event_type == "pilgrimage_departure"]
        assert len(departure_events) == 1, "Only one departure per faith per turn"


# ---------------------------------------------------------------------------
# TestPilgrimageReturn
# ---------------------------------------------------------------------------

class TestPilgrimageReturn:
    def test_skill_bonus_cached_on_return(self):
        """Returning pilgrims gain skill bonus."""
        gp = _make_gp(agent_id=1)
        gp.pilgrimage_destination = "Distant Shrine"
        gp.pilgrimage_return_turn = 5

        events = check_pilgrimages([gp], [], None, current_turn=5, belief_registry=[])

        return_events = [e for e in events if e.event_type == "pilgrimage_return"]
        assert len(return_events) == 1
        assert gp.pilgrimage_skill_bonus == PILGRIMAGE_SKILL_BOOST

    def test_arc_type_set_to_prophet_on_return(self):
        """Returning pilgrim arc_type becomes 'Prophet'."""
        gp = _make_gp(agent_id=1)
        gp.pilgrimage_destination = "Sacred Peak"
        gp.pilgrimage_return_turn = 3

        check_pilgrimages([gp], [], None, current_turn=10, belief_registry=[])

        assert gp.arc_type == "Prophet"

    def test_pilgrimage_fields_cleared_on_return(self):
        """destination and return_turn are cleared after return."""
        gp = _make_gp(agent_id=1)
        gp.pilgrimage_destination = "The Holy Mount"
        gp.pilgrimage_return_turn = 7

        check_pilgrimages([gp], [], None, current_turn=7, belief_registry=[])

        assert gp.pilgrimage_destination is None
        assert gp.pilgrimage_return_turn is None

    def test_return_event_importance_is_5(self):
        """Return event has importance=5."""
        gp = _make_gp(agent_id=1)
        gp.pilgrimage_destination = "Golden Temple"
        gp.pilgrimage_return_turn = 1

        events = check_pilgrimages([gp], [], None, current_turn=1, belief_registry=[])

        return_events = [e for e in events if e.event_type == "pilgrimage_return"]
        assert return_events[0].importance == 5

    def test_no_return_before_due_turn(self):
        """GP does not return before pilgrimage_return_turn."""
        gp = _make_gp(agent_id=1)
        gp.pilgrimage_destination = "Far Shrine"
        gp.pilgrimage_return_turn = 20

        events = check_pilgrimages([gp], [], None, current_turn=10, belief_registry=[])

        return_events = [e for e in events if e.event_type == "pilgrimage_return"]
        assert return_events == []
        assert gp.pilgrimage_destination == "Far Shrine"


# ---------------------------------------------------------------------------
# TestDuration
# ---------------------------------------------------------------------------

class TestDuration:
    def test_duration_constants_range(self):
        """PILGRIMAGE_DURATION_MIN == 5 and PILGRIMAGE_DURATION_MAX == 10."""
        assert PILGRIMAGE_DURATION_MIN == 5
        assert PILGRIMAGE_DURATION_MAX == 10

    def test_departure_sets_return_turn_in_range(self):
        """Departure sets pilgrimage_return_turn within [turn+5, turn+10]."""
        gp = _make_gp(agent_id=1)

        snap = _make_snapshot(
            agent_id=1,
            occupation=_PRIEST_OCCUPATION,
            loyalty_trait=0.0,
            loyalty=0.9,
            belief=0,
        )
        temple = _make_temple(faith_id=0, prestige=10)
        temples = [("HolyCity", temple)]

        current_turn = 50
        check_pilgrimages([gp], temples, snap, current_turn=current_turn, belief_registry=[])

        assert gp.pilgrimage_return_turn is not None
        assert current_turn + PILGRIMAGE_DURATION_MIN <= gp.pilgrimage_return_turn <= current_turn + PILGRIMAGE_DURATION_MAX

    def test_departure_return_turn_is_deterministic(self):
        """Identical departure inputs should produce the same return turn."""
        gp_a = _make_gp(agent_id=1)
        gp_b = _make_gp(agent_id=1)

        snap = _make_snapshot(
            agent_id=1,
            occupation=_PRIEST_OCCUPATION,
            loyalty_trait=0.0,
            loyalty=0.9,
            belief=0,
        )
        temple = _make_temple(faith_id=0, prestige=10)
        temples = [("HolyCity", temple)]

        check_pilgrimages([gp_a], temples, snap, current_turn=50, belief_registry=[])
        check_pilgrimages([gp_b], temples, snap, current_turn=50, belief_registry=[])

        assert gp_a.pilgrimage_return_turn == gp_b.pilgrimage_return_turn

    def test_departure_event_importance_is_4(self):
        """Departure event has importance=4."""
        gp = _make_gp(agent_id=1)

        snap = _make_snapshot(
            agent_id=1,
            occupation=_PRIEST_OCCUPATION,
            loyalty_trait=0.0,
            loyalty=0.9,
            belief=0,
        )
        temple = _make_temple(faith_id=0, prestige=10)
        temples = [("HolyCity", temple)]

        events = check_pilgrimages([gp], temples, snap, current_turn=1, belief_registry=[])

        departure_events = [e for e in events if e.event_type == "pilgrimage_departure"]
        assert len(departure_events) == 1
        assert departure_events[0].importance == 4
