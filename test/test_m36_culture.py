"""Tier 1 tests for M36 cultural identity."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Stub out the Rust extension so tests run without a compiled wheel
if "chronicler_agents" not in sys.modules:
    sys.modules["chronicler_agents"] = MagicMock()

import pytest
import pyarrow as pa
from collections import Counter

from chronicler.culture import (
    compute_civ_cultural_profile,
    tick_cultural_assimilation,
    ASSIMILATION_THRESHOLD,
    ASSIMILATION_AGENT_THRESHOLD,
    ASSIMILATION_GUARD_TURNS,
)
from chronicler.agent_bridge import VALUE_TO_ID


def _make_snapshot(agents):
    """Create a minimal Arrow RecordBatch snapshot from agent dicts."""
    return pa.record_batch({
        "id": pa.array([a["id"] for a in agents], type=pa.uint32()),
        "region": pa.array([a["region"] for a in agents], type=pa.uint16()),
        "civ_affinity": pa.array([a["civ"] for a in agents], type=pa.uint16()),
        "cultural_value_0": pa.array([a["cv0"] for a in agents], type=pa.uint8()),
        "cultural_value_1": pa.array([a["cv1"] for a in agents], type=pa.uint8()),
        "cultural_value_2": pa.array([a["cv2"] for a in agents], type=pa.uint8()),
    })


# ---------------------------------------------------------------------------
# TestComputeCivCulturalProfile
# ---------------------------------------------------------------------------
class TestComputeCivCulturalProfile:
    def test_basic_aggregation(self):
        """Agents are grouped by civ; valid cultural values are counted."""
        agents = [
            {"id": 1, "region": 0, "civ": 0, "cv0": 0, "cv1": 1, "cv2": 0xFF},
            {"id": 2, "region": 0, "civ": 0, "cv0": 0, "cv1": 0, "cv2": 2},
            {"id": 3, "region": 1, "civ": 1, "cv0": 3, "cv1": 3, "cv2": 4},
        ]
        snap = _make_snapshot(agents)
        profiles = compute_civ_cultural_profile(snap)

        assert 0 in profiles
        assert 1 in profiles
        # Civ 0: value 0 appears 3 times (agent1 cv0 + agent2 cv0 + agent2 cv1),
        #         value 1 appears 1 time, value 2 appears 1 time
        assert profiles[0][0] == 3
        assert profiles[0][1] == 1
        assert profiles[0][2] == 1
        # Civ 1: value 3 appears 2 times, value 4 appears 1 time
        assert profiles[1][3] == 2
        assert profiles[1][4] == 1

    def test_empty_snapshot(self):
        """None or zero-row snapshot returns empty dict."""
        assert compute_civ_cultural_profile(None) == {}
        empty = pa.record_batch({
            "id": pa.array([], type=pa.uint32()),
            "region": pa.array([], type=pa.uint16()),
            "civ_affinity": pa.array([], type=pa.uint16()),
            "cultural_value_0": pa.array([], type=pa.uint8()),
            "cultural_value_1": pa.array([], type=pa.uint8()),
            "cultural_value_2": pa.array([], type=pa.uint8()),
        })
        assert compute_civ_cultural_profile(empty) == {}

    def test_invalid_values_ignored(self):
        """Values >= 6 or == 0xFF are not counted."""
        agents = [
            {"id": 1, "region": 0, "civ": 0, "cv0": 0xFF, "cv1": 7, "cv2": 5},
        ]
        snap = _make_snapshot(agents)
        profiles = compute_civ_cultural_profile(snap)
        # Only value 5 should be counted (< 6 and != 0xFF)
        assert profiles[0][5] == 1
        assert sum(profiles[0].values()) == 1


# ---------------------------------------------------------------------------
# TestAgentDrivenAssimilation
# ---------------------------------------------------------------------------
class TestAgentDrivenAssimilation:
    def _make_world(self, regions, civs):
        """Build a MagicMock world with given regions and civilizations."""
        world = MagicMock()
        world.regions = regions
        world.civilizations = civs
        world.named_events = []
        world.active_conditions = []
        world.turn = 50
        return world

    def _make_region(self, name, controller, cultural_identity, foreign_control_turns=0):
        """Build a MagicMock region."""
        r = MagicMock()
        r.name = name
        r.controller = controller
        r.cultural_identity = cultural_identity
        r.foreign_control_turns = foreign_control_turns
        return r

    def _make_civ(self, name, values, stability=80):
        """Build a MagicMock civilization."""
        c = MagicMock()
        c.name = name
        c.values = values
        c.stability = stability
        return c

    def test_above_threshold_flips(self):
        """70% of agents hold controller's primary value -> assimilation fires."""
        controller_civ = self._make_civ("Rome", ["Honor", "Order"], stability=80)
        defender_civ = self._make_civ("Gaul", ["Freedom"], stability=60)
        region = self._make_region(
            "Gallia", controller="Rome", cultural_identity="Gaul",
            foreign_control_turns=6,
        )
        world = self._make_world([region], [controller_civ, defender_civ])

        # 7 out of 10 agents hold Honor (VALUE_TO_ID["Honor"] == 4) -> 70%
        honor_id = VALUE_TO_ID["Honor"]
        agents = []
        for i in range(7):
            agents.append({"id": i, "region": 0, "civ": 0,
                           "cv0": honor_id, "cv1": 0xFF, "cv2": 0xFF})
        for i in range(7, 10):
            agents.append({"id": i, "region": 0, "civ": 1,
                           "cv0": 0xFF, "cv1": 0xFF, "cv2": 0xFF})
        snap = _make_snapshot(agents)

        tick_cultural_assimilation(world, acc=None, agent_snapshot=snap)

        assert region.cultural_identity == "Rome"
        assert region.foreign_control_turns == 0
        assert len(world.named_events) == 1
        assert world.named_events[0].event_type == "cultural_assimilation"

    def test_below_threshold_no_flip(self):
        """50% hold controller's value -> no assimilation."""
        controller_civ = self._make_civ("Rome", ["Honor", "Order"], stability=80)
        defender_civ = self._make_civ("Gaul", ["Freedom"], stability=60)
        region = self._make_region(
            "Gallia", controller="Rome", cultural_identity="Gaul",
            foreign_control_turns=10,
        )
        world = self._make_world([region], [controller_civ, defender_civ])

        honor_id = VALUE_TO_ID["Honor"]
        agents = []
        for i in range(5):
            agents.append({"id": i, "region": 0, "civ": 0,
                           "cv0": honor_id, "cv1": 0xFF, "cv2": 0xFF})
        for i in range(5, 10):
            agents.append({"id": i, "region": 0, "civ": 1,
                           "cv0": 0xFF, "cv1": 0xFF, "cv2": 0xFF})
        snap = _make_snapshot(agents)

        tick_cultural_assimilation(world, acc=None, agent_snapshot=snap)

        # Still Gaul — 50% is below 60% threshold
        assert region.cultural_identity == "Gaul"
        assert len(world.named_events) == 0

    def test_guard_clause_blocks_early_assimilation(self):
        """foreign_control_turns=3 (< 5) with 100% match -> no assimilation."""
        controller_civ = self._make_civ("Rome", ["Honor"], stability=80)
        region = self._make_region(
            "Gallia", controller="Rome", cultural_identity="Gaul",
            foreign_control_turns=3,
        )
        world = self._make_world([region], [controller_civ])

        honor_id = VALUE_TO_ID["Honor"]
        agents = [{"id": i, "region": 0, "civ": 0,
                   "cv0": honor_id, "cv1": 0xFF, "cv2": 0xFF}
                  for i in range(10)]
        snap = _make_snapshot(agents)

        tick_cultural_assimilation(world, acc=None, agent_snapshot=snap)

        # Guard blocks: foreign_control_turns < 5
        assert region.cultural_identity == "Gaul"
        assert len(world.named_events) == 0

    def test_timer_fallback_when_snapshot_none(self):
        """snapshot=None, foreign_control_turns=15 -> timer-based flip."""
        controller_civ = self._make_civ("Rome", ["Honor"], stability=80)
        region = self._make_region(
            "Gallia", controller="Rome", cultural_identity="Gaul",
            foreign_control_turns=14,  # Will be incremented to 15 in the function
        )
        world = self._make_world([region], [controller_civ])

        tick_cultural_assimilation(world, acc=None, agent_snapshot=None)

        # Timer path: 14 + 1 = 15 >= ASSIMILATION_THRESHOLD
        assert region.cultural_identity == "Rome"
        assert region.foreign_control_turns == 0
        assert len(world.named_events) == 1
        assert world.named_events[0].event_type == "cultural_assimilation"
