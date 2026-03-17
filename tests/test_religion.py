"""Tests for M37 religion.py — faith generation, belief aggregation, conversion signals."""
from __future__ import annotations

import random
import sys
from unittest.mock import MagicMock

# Stub out the Rust extension so tests run without a compiled wheel
if "chronicler_agents" not in sys.modules:
    sys.modules["chronicler_agents"] = MagicMock()

import pytest
import pyarrow as pa

from chronicler.religion import (
    _generate_doctrines,  # Import directly, NOT via generate_faiths
    generate_faiths,
    compute_majority_belief,
    compute_civ_majority_faith,
    compute_conversion_signals,
    decay_conquest_boosts,
    BASE_CONVERSION_RATE,
    CONQUEST_BOOST_RATE,
    CONQUEST_BOOST_DURATION,
)
from chronicler.models import (
    Belief,
    Region,
    DOCTRINE_STANCE,
    DOCTRINE_OUTREACH,
    DOCTRINE_STRUCTURE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(agents: list[dict]) -> pa.RecordBatch:
    """Build a minimal PyArrow RecordBatch snapshot from agent dicts.

    Agent dict keys:
        id (int), region (int), civ (int), occupation (int), belief (int).
    """
    return pa.record_batch({
        "id":          pa.array([a["id"]         for a in agents], type=pa.uint32()),
        "region":      pa.array([a["region"]     for a in agents], type=pa.uint16()),
        "civ_affinity":pa.array([a["civ"]        for a in agents], type=pa.uint16()),
        "occupation":  pa.array([a["occupation"] for a in agents], type=pa.uint8()),
        "belief":      pa.array([a["belief"]     for a in agents], type=pa.uint8()),
    })


def _make_region(**kwargs) -> Region:
    """Create a minimal Region with required fields."""
    defaults = dict(
        name="TestRegion",
        terrain="plains",
        carrying_capacity=10,
        resources="fertile",
    )
    defaults.update(kwargs)
    return Region(**defaults)


def _make_belief(faith_id: int, doctrines: list[int] | None = None) -> Belief:
    if doctrines is None:
        doctrines = [0, 0, 0, 0, 0]
    return Belief(faith_id=faith_id, name=f"Faith{faith_id}", civ_origin=faith_id, doctrines=doctrines)


# ---------------------------------------------------------------------------
# TestDoctrineGeneration
# ---------------------------------------------------------------------------

class TestDoctrineGeneration:
    def test_honor_biases_militant(self):
        """Honor value biases DOCTRINE_STANCE +1 with ~60% probability (1000 rolls)."""
        militant_count = 0
        for i in range(1000):
            rng = random.Random(i)
            doctrines = _generate_doctrines(["Honor"], rng)
            if doctrines[DOCTRINE_STANCE] == +1:
                militant_count += 1

        # Expect roughly 60%; allow a wide band [45%, 75%] for statistical noise
        rate = militant_count / 1000
        assert 0.45 <= rate <= 0.75, (
            f"Honor militant bias rate={rate:.3f} outside expected range [0.45, 0.75]"
        )

    def test_average_nonzero_axes(self):
        """With values that have biases, average non-zero axes should be 2-3."""
        # Use Honor + Freedom which has multiple biased axes
        total_nonzero = 0
        trials = 200
        for i in range(trials):
            rng = random.Random(i)
            doctrines = _generate_doctrines(["Honor", "Freedom"], rng)
            total_nonzero += sum(1 for d in doctrines if d != 0)

        avg_nonzero = total_nonzero / trials
        assert 1.5 <= avg_nonzero <= 4.0, (
            f"Average nonzero axes={avg_nonzero:.2f} outside expected range [1.5, 4.0]"
        )

    def test_generate_faiths_one_per_civ(self):
        """generate_faiths returns exactly one Belief per civ."""
        civ_values = [["Honor"], ["Freedom", "Order"], ["Knowledge"]]
        civ_names = ["CivA", "CivB", "CivC"]
        faiths = generate_faiths(civ_values, civ_names, seed=42)

        assert len(faiths) == 3
        for i, faith in enumerate(faiths):
            assert isinstance(faith, Belief)
            assert faith.faith_id == i
            assert faith.civ_origin == i
            assert len(faith.doctrines) == 5
            assert all(d in (-1, 0, 1) for d in faith.doctrines)


# ---------------------------------------------------------------------------
# TestMajorityBelief
# ---------------------------------------------------------------------------

class TestMajorityBelief:
    def test_simple_majority(self):
        """Region with 3 agents on faith 0 and 1 agent on faith 1 → majority is 0."""
        agents = [
            {"id": 0, "region": 0, "civ": 0, "occupation": 0, "belief": 0},
            {"id": 1, "region": 0, "civ": 0, "occupation": 0, "belief": 0},
            {"id": 2, "region": 0, "civ": 0, "occupation": 0, "belief": 0},
            {"id": 3, "region": 0, "civ": 1, "occupation": 1, "belief": 1},
        ]
        snap = _make_snapshot(agents)
        result = compute_majority_belief(snap)
        assert result[0] == 0

    def test_tie_breaks_to_lower_id(self):
        """Equal agents on faith 1 and faith 2 → majority is the lower id (1)."""
        agents = [
            {"id": 0, "region": 5, "civ": 0, "occupation": 0, "belief": 2},
            {"id": 1, "region": 5, "civ": 0, "occupation": 0, "belief": 1},
            {"id": 2, "region": 5, "civ": 1, "occupation": 0, "belief": 2},
            {"id": 3, "region": 5, "civ": 1, "occupation": 0, "belief": 1},
        ]
        snap = _make_snapshot(agents)
        result = compute_majority_belief(snap)
        assert result[5] == 1


# ---------------------------------------------------------------------------
# TestCivMajorityFaith
# ---------------------------------------------------------------------------

class TestCivMajorityFaith:
    def test_simple_civ_majority(self):
        """Civ 0 has 3 agents on faith 0, 1 agent on faith 1 → civ majority is 0."""
        agents = [
            {"id": 0, "region": 0, "civ": 0, "occupation": 0, "belief": 0},
            {"id": 1, "region": 0, "civ": 0, "occupation": 0, "belief": 0},
            {"id": 2, "region": 1, "civ": 0, "occupation": 0, "belief": 0},
            {"id": 3, "region": 1, "civ": 0, "occupation": 0, "belief": 1},
            {"id": 4, "region": 2, "civ": 1, "occupation": 0, "belief": 2},
        ]
        snap = _make_snapshot(agents)
        result = compute_civ_majority_faith(snap)
        assert result[0] == 0
        assert result[1] == 2


# ---------------------------------------------------------------------------
# TestConversionSignals
# ---------------------------------------------------------------------------

class TestConversionSignals:
    def test_dominant_faith_only(self):
        """When two foreign faiths compete, only the dominant one wins the slot."""
        # Region 0: majority is faith 0.
        # faith 1 has 3 priests, faith 2 has 1 priest → faith 1 wins.
        regions = [_make_region(name="R0")]
        majority_beliefs = {0: 0}  # faith 0 is majority

        belief_registry = [
            _make_belief(0),
            _make_belief(1),  # neutral doctrines
            _make_belief(2),  # neutral doctrines
        ]

        agents = [
            # 3 priests of faith 1
            {"id": 0, "region": 0, "civ": 1, "occupation": 4, "belief": 1},
            {"id": 1, "region": 0, "civ": 1, "occupation": 4, "belief": 1},
            {"id": 2, "region": 0, "civ": 1, "occupation": 4, "belief": 1},
            # 1 priest of faith 2
            {"id": 3, "region": 0, "civ": 2, "occupation": 4, "belief": 2},
        ]
        snap = _make_snapshot(agents)

        results = compute_conversion_signals(
            regions, majority_beliefs, belief_registry, snap
        )

        assert len(results) == 1
        region_idx, rate, target, conquest_active = results[0]
        assert region_idx == 0
        assert target == 1, f"Expected faith 1 to win, got {target}"
        assert rate > 0.0

        # Also verify region fields are written
        assert regions[0].conversion_target_signal == 1
        assert regions[0].conversion_rate_signal == rate

    def test_no_priests_no_boost_zero_rate(self):
        """Region with no priests and no conquest boost → rate=0 and target=0xFF."""
        regions = [_make_region(name="R0")]
        majority_beliefs = {0: 0}
        belief_registry = [_make_belief(0)]

        # Agents are farmers only (occupation 0)
        agents = [
            {"id": 0, "region": 0, "civ": 0, "occupation": 0, "belief": 1},
            {"id": 1, "region": 0, "civ": 0, "occupation": 0, "belief": 0},
        ]
        snap = _make_snapshot(agents)

        results = compute_conversion_signals(
            regions, majority_beliefs, belief_registry, snap
        )

        assert len(results) == 1
        _, rate, target, _ = results[0]
        assert rate == 0.0
        assert target == 0xFF
        assert regions[0].conversion_rate_signal == 0.0
        assert regions[0].conversion_target_signal == 0xFF


# ---------------------------------------------------------------------------
# TestConquestBoostDecay
# ---------------------------------------------------------------------------

class TestConquestBoostDecay:
    def test_decay_lifecycle(self):
        """Conquest boost decays linearly over CONQUEST_BOOST_DURATION steps to 0."""
        region = _make_region(name="R0")
        # Start at a full boost (1.0)
        region.conquest_conversion_boost = 1.0

        step = 1.0 / CONQUEST_BOOST_DURATION

        for tick in range(CONQUEST_BOOST_DURATION):
            decay_conquest_boosts([region])
            expected = max(0.0, 1.0 - (tick + 1) * step)
            assert region.conquest_conversion_boost == pytest.approx(expected, abs=1e-9), (
                f"Tick {tick + 1}: expected boost≈{expected:.6f}, "
                f"got {region.conquest_conversion_boost:.6f}"
            )

        # After full duration, boost must be exactly 0
        assert region.conquest_conversion_boost == pytest.approx(0.0, abs=1e-9)

    def test_decay_no_negative(self):
        """Boost never goes below 0 even if decay_conquest_boosts is called extra times."""
        region = _make_region(name="R0")
        region.conquest_conversion_boost = 0.05  # small starting value

        for _ in range(20):  # more than CONQUEST_BOOST_DURATION
            decay_conquest_boosts([region])

        assert region.conquest_conversion_boost == 0.0
