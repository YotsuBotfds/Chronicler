"""Tests for M38b persecution detection, martyrdom boost lifecycle."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Stub out the Rust extension so tests run without a compiled wheel
if "chronicler_agents" not in sys.modules:
    sys.modules["chronicler_agents"] = MagicMock()

import pytest
import pyarrow as pa

from chronicler.models import (
    Belief,
    Region,
    DOCTRINE_STANCE,
)
from chronicler.religion import (
    compute_persecution,
    compute_martyrdom_boosts,
    decay_martyrdom_boosts,
    MASS_MIGRATION_THRESHOLD,
    MARTYRDOM_BOOST_PER_EVENT,
    MARTYRDOM_BOOST_CAP,
    MARTYRDOM_DECAY_TURNS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_belief(faith_id: int, stance: int = 0) -> Belief:
    """Build a Belief with the given stance at DOCTRINE_STANCE index (2)."""
    doctrines = [0, 0, stance, 0, 0]
    return Belief(
        name=f"Faith{faith_id}",
        doctrines=doctrines,
        faith_id=faith_id,
        civ_origin=faith_id,
    )


def _make_region(name: str = "r", population: int = 100) -> Region:
    return Region(
        name=name,
        terrain="plains",
        resources="fertile",
        carrying_capacity=100,
        population=population,
    )


def _make_snapshot(agents: list[dict]) -> pa.RecordBatch:
    """Build a minimal PyArrow RecordBatch snapshot from agent dicts."""
    return pa.record_batch({
        "id":           pa.array([a["id"]         for a in agents], type=pa.uint32()),
        "region":       pa.array([a["region"]     for a in agents], type=pa.uint16()),
        "civ_affinity": pa.array([a["civ"]        for a in agents], type=pa.uint16()),
        "occupation":   pa.array([a["occupation"] for a in agents], type=pa.uint8()),
        "belief":       pa.array([a["belief"]     for a in agents], type=pa.uint8()),
    })


def _make_civ(name: str, faith_id: int, region_names: list[str]):
    """Build a minimal Civilization-like object via Pydantic."""
    from chronicler.models import Civilization, Leader, TechEra
    return Civilization(
        name=name,
        population=50,
        military=30,
        economy=40,
        culture=30,
        stability=50,
        tech_era=TechEra.IRON,
        treasury=50,
        leader=Leader(name=f"Leader of {name}", trait="cautious", reign_start=0),
        regions=region_names,
        civ_majority_faith=faith_id,
    )


# ---------------------------------------------------------------------------
# TestPersecutionGate
# ---------------------------------------------------------------------------

class TestPersecutionGate:
    """Militant (+1) persecutes; Pacifist (-1) and Neutral (0) do not."""

    def _run(self, stance: int) -> list:
        """Build a one-civ, one-region world with 9 majority agents + 1 minority."""
        region = _make_region("r0")
        majority_faith = _make_belief(0, stance=stance)
        minority_faith = _make_belief(1, stance=0)
        belief_registry = [majority_faith, minority_faith]

        civ = _make_civ("CivA", faith_id=0, region_names=["r0"])
        regions = [region]
        civilizations = [civ]

        # 9 agents on faith 0 (majority), 1 on faith 1 (minority)
        agents = [
            {"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
            for i in range(9)
        ] + [{"id": 9, "region": 0, "civ": 0, "occupation": 0, "belief": 1}]
        snap = _make_snapshot(agents)

        persecuted_regions: set[str] = set()
        events = compute_persecution(
            regions, civilizations, belief_registry, snap, turn=1,
            persecuted_regions=persecuted_regions,
        )
        return events

    def test_militant_persecutes(self):
        events = self._run(stance=+1)
        assert len(events) > 0, "Militant faith should trigger Persecution event"

    def test_pacifist_does_not_persecute(self):
        events = self._run(stance=-1)
        assert len(events) == 0, "Pacifist faith should not trigger persecution"

    def test_neutral_does_not_persecute(self):
        events = self._run(stance=0)
        assert len(events) == 0, "Neutral faith should not trigger persecution"


# ---------------------------------------------------------------------------
# TestIntensityFormula
# ---------------------------------------------------------------------------

class TestIntensityFormula:
    """intensity = 1.0 * (1.0 - minority_ratio) at various minority fractions."""

    def _get_intensity(self, minority_count: int, total: int) -> float:
        region = _make_region("r0")
        belief_registry = [_make_belief(0, stance=+1), _make_belief(1)]
        civ = _make_civ("CivA", faith_id=0, region_names=["r0"])

        majority_count = total - minority_count
        agents = (
            [{"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
             for i in range(majority_count)]
            + [{"id": majority_count + i, "region": 0, "civ": 0, "occupation": 0, "belief": 1}
               for i in range(minority_count)]
        )
        snap = _make_snapshot(agents)

        compute_persecution(
            [region], [civ], belief_registry, snap, turn=1,
            persecuted_regions=set(),
        )
        return region.persecution_intensity

    def test_intensity_at_10_percent(self):
        # 1 minority out of 10 → ratio = 0.10 → intensity = 0.90
        intensity = self._get_intensity(minority_count=1, total=10)
        assert intensity == pytest.approx(0.90, abs=1e-9)

    def test_intensity_at_40_percent(self):
        # 4 minority out of 10 → ratio = 0.40 → intensity = 0.60
        intensity = self._get_intensity(minority_count=4, total=10)
        assert intensity == pytest.approx(0.60, abs=1e-9)

    def test_intensity_at_50_percent(self):
        # 5 minority out of 10 → ratio = 0.50 → intensity = 0.50
        intensity = self._get_intensity(minority_count=5, total=10)
        assert intensity == pytest.approx(0.50, abs=1e-9)


# ---------------------------------------------------------------------------
# TestMassMigration
# ---------------------------------------------------------------------------

class TestMassMigration:
    """Mass Migration event fires when minority_ratio > MASS_MIGRATION_THRESHOLD."""

    def _run_with_ratio(self, minority_count: int, total: int) -> list:
        region = _make_region("r0")
        belief_registry = [_make_belief(0, stance=+1), _make_belief(1)]
        civ = _make_civ("CivA", faith_id=0, region_names=["r0"])

        majority_count = total - minority_count
        agents = (
            [{"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
             for i in range(majority_count)]
            + [{"id": majority_count + i, "region": 0, "civ": 0, "occupation": 0, "belief": 1}
               for i in range(minority_count)]
        )
        snap = _make_snapshot(agents)

        return compute_persecution(
            [region], [civ], belief_registry, snap, turn=1,
            persecuted_regions=set(),
        )

    def test_no_mass_migration_below_threshold(self):
        # 1 out of 10 → ratio = 0.10, below MASS_MIGRATION_THRESHOLD (0.15)
        events = self._run_with_ratio(minority_count=1, total=10)
        event_types = [e.event_type for e in events]
        assert "Mass Migration" not in event_types

    def test_mass_migration_above_threshold(self):
        # 2 out of 10 → ratio = 0.20, above MASS_MIGRATION_THRESHOLD (0.15)
        events = self._run_with_ratio(minority_count=2, total=10)
        event_types = [e.event_type for e in events]
        assert "Mass Migration" in event_types, (
            f"Expected 'Mass Migration' event; got: {event_types}"
        )


# ---------------------------------------------------------------------------
# TestMartyrdomBoost
# ---------------------------------------------------------------------------

class TestMartyrdomBoost:
    """Martyrdom boost: set, stack to cap, decay linearly over MARTYRDOM_DECAY_TURNS."""

    def test_boost_set_on_persecution_deaths(self):
        region = _make_region("r0")
        # M-AF1 #12: Region must be persecuted and death must be minority-faith
        region.persecution_intensity = 0.5
        region.majority_belief = 0  # Majority is belief 0
        assert region.martyrdom_boost == 0.0

        dead_agents = [{"region_idx": 0, "belief": 1}]  # Minority faith
        compute_martyrdom_boosts([region], dead_agents)

        assert region.martyrdom_boost == pytest.approx(MARTYRDOM_BOOST_PER_EVENT, abs=1e-9)

    def test_boost_stacks_to_cap(self):
        region = _make_region("r0")
        # M-AF1 #12: Region must be persecuted and death must be minority-faith
        region.persecution_intensity = 0.5
        region.majority_belief = 0  # Majority is belief 0
        # Each call adds MARTYRDOM_BOOST_PER_EVENT; cap is MARTYRDOM_BOOST_CAP
        calls_needed = int(MARTYRDOM_BOOST_CAP / MARTYRDOM_BOOST_PER_EVENT) + 5  # overshoot
        dead_agents = [{"region_idx": 0, "belief": 1}]  # Minority faith

        for _ in range(calls_needed):
            compute_martyrdom_boosts([region], dead_agents)

        assert region.martyrdom_boost == pytest.approx(MARTYRDOM_BOOST_CAP, abs=1e-9)

    def test_no_boost_without_dead_agents(self):
        region = _make_region("r0")
        compute_martyrdom_boosts([region], dead_agents=None)
        assert region.martyrdom_boost == 0.0

        compute_martyrdom_boosts([region], dead_agents=[])
        assert region.martyrdom_boost == 0.0

    def test_decay_linear_over_turns(self):
        region = _make_region("r0")
        region.martyrdom_boost = MARTYRDOM_BOOST_CAP  # set to max

        decay_step = MARTYRDOM_BOOST_CAP / MARTYRDOM_DECAY_TURNS

        for tick in range(MARTYRDOM_DECAY_TURNS):
            decay_martyrdom_boosts([region])
            expected = max(0.0, MARTYRDOM_BOOST_CAP - (tick + 1) * decay_step)
            assert region.martyrdom_boost == pytest.approx(expected, abs=1e-9), (
                f"Tick {tick + 1}: expected {expected:.6f}, got {region.martyrdom_boost:.6f}"
            )

        assert region.martyrdom_boost == pytest.approx(0.0, abs=1e-9)

    def test_decay_never_negative(self):
        region = _make_region("r0")
        region.martyrdom_boost = 0.01  # small value

        for _ in range(MARTYRDOM_DECAY_TURNS + 5):
            decay_martyrdom_boosts([region])

        assert region.martyrdom_boost == 0.0
