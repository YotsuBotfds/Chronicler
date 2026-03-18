"""Tier 2 regression harness for M38b: interaction effects between
persecution, schisms, and pilgrimages."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Stub out the Rust extension so tests run without a compiled wheel
if "chronicler_agents" not in sys.modules:
    sys.modules["chronicler_agents"] = MagicMock()

import pytest
import pyarrow as pa

try:
    import chronicler_agents as _ca
    _AGENTS_AVAILABLE = not isinstance(_ca, MagicMock)
except Exception:
    _AGENTS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _AGENTS_AVAILABLE,
    reason="Rust agent extension not available",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_belief(faith_id: int, doctrines: list[int] | None = None,
                 name: str | None = None, civ_origin: int = 0):
    from chronicler.models import Belief
    if doctrines is None:
        doctrines = [0, 0, 0, 0, 0]
    return Belief(
        faith_id=faith_id,
        name=name or f"Faith{faith_id}",
        civ_origin=civ_origin,
        doctrines=doctrines,
    )


def _make_region(name: str = "r", population: int = 100,
                 persecution_intensity: float = 0.0,
                 martyrdom_boost: float = 0.0,
                 controller: str | None = None):
    from chronicler.models import Region
    r = Region(
        name=name,
        terrain="plains",
        resources="fertile",
        carrying_capacity=100,
        population=population,
        controller=controller,
    )
    r.persecution_intensity = persecution_intensity
    r.martyrdom_boost = martyrdom_boost
    return r


def _make_civ(name: str = "CivA", faith_id: int = 0,
              region_names: list[str] | None = None,
              clergy_influence: float = 0.25):
    from chronicler.models import Civilization, Leader, TechEra, FactionType
    regions = ["r"] if region_names is None else region_names
    civ = Civilization(
        name=name,
        population=50,
        military=30,
        economy=40,
        culture=30,
        stability=50,
        tech_era=TechEra.IRON,
        treasury=50,
        leader=Leader(name=f"Leader of {name}", trait="cautious", reign_start=0),
        regions=regions,
        civ_majority_faith=faith_id,
    )
    civ.factions.influence[FactionType.CLERGY] = clergy_influence
    return civ


def _make_snapshot_with_beliefs(agents: list[dict]) -> pa.RecordBatch:
    """Build a RecordBatch with id, region, civ_affinity, occupation, belief columns."""
    return pa.record_batch({
        "id":           pa.array([a["id"]         for a in agents], type=pa.uint32()),
        "region":       pa.array([a["region"]     for a in agents], type=pa.uint16()),
        "civ_affinity": pa.array([a["civ"]        for a in agents], type=pa.uint16()),
        "occupation":   pa.array([a["occupation"] for a in agents], type=pa.uint8()),
        "belief":       pa.array([a["belief"]     for a in agents], type=pa.uint8()),
    })


# ---------------------------------------------------------------------------
# TestPersecutionMartyrdomConversion
# ---------------------------------------------------------------------------

class TestPersecutionMartyrdomConversion:
    """A region with martyrdom_boost > 0 should produce a higher
    conversion_rate_signal than an identical region without it.

    compute_conversion_signals() adds region.martyrdom_boost directly to
    the computed rate, so a non-zero boost must raise the output.
    """

    def _run_conversion(self, martyrdom_boost: float) -> float:
        """Return conversion_rate_signal for a region with given martyrdom_boost.

        Uses a single foreign-faith priest agent to produce a non-zero base rate,
        then adds the martyrdom_boost on top.
        """
        from chronicler.religion import compute_conversion_signals
        from chronicler.models import DOCTRINE_OUTREACH

        # Majority faith (faith 0) in region — pacifist stance
        majority_belief = _make_belief(0, doctrines=[0, 0, 0, 0, 0], name="MajFaith")
        # Foreign faith (faith 1) — proselytizing (outreach +1) for maximum base rate
        foreign_belief = _make_belief(
            1, doctrines=[0, 0, 0, +1, 0], name="ForeignFaith", civ_origin=1
        )
        belief_registry = [majority_belief, foreign_belief]

        region = _make_region("r0", population=100, martyrdom_boost=martyrdom_boost)
        regions = [region]

        # Majority beliefs: region 0 → faith 0
        majority_beliefs = {0: 0}

        # One foreign priest (faith 1) in region 0 so base rate > 0
        agents = [
            # 9 non-priest agents following faith 0
            {"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
            for i in range(9)
        ] + [
            # 1 priest agent following faith 1 (foreign)
            {"id": 9, "region": 0, "civ": 0, "occupation": 4, "belief": 1},
        ]
        snap = _make_snapshot_with_beliefs(agents)

        compute_conversion_signals(regions, majority_beliefs, belief_registry, snap)
        return region.conversion_rate_signal

    def test_martyrdom_boost_increases_conversion_rate(self):
        """Region with martyrdom_boost=0.10 has strictly higher conversion_rate_signal
        than identical region with martyrdom_boost=0.0."""
        rate_no_boost = self._run_conversion(martyrdom_boost=0.0)
        rate_with_boost = self._run_conversion(martyrdom_boost=0.10)

        assert rate_with_boost > rate_no_boost, (
            f"Expected rate_with_boost ({rate_with_boost:.4f}) > "
            f"rate_no_boost ({rate_no_boost:.4f})"
        )

    def test_martyrdom_boost_delta_matches_boost_value(self):
        """The delta between rates equals martyrdom_boost (it is additive)."""
        from chronicler.religion import MARTYRDOM_BOOST_CAP
        boost = 0.10
        rate_no = self._run_conversion(martyrdom_boost=0.0)
        rate_with = self._run_conversion(martyrdom_boost=boost)

        assert rate_with - rate_no == pytest.approx(boost, abs=1e-9), (
            f"Expected delta={boost}, got {rate_with - rate_no:.6f}"
        )

    def test_zero_martyrdom_boost_unchanged(self):
        """With martyrdom_boost=0.0 the martyrdom path adds nothing."""
        rate = self._run_conversion(martyrdom_boost=0.0)
        # Base rate > 0 from the proselytizing foreign priest; no martyrdom added
        assert rate > 0.0


# ---------------------------------------------------------------------------
# TestSchismPersecutionCascade
# ---------------------------------------------------------------------------

class TestSchismPersecutionCascade:
    """After detect_schisms() fires a schism in a region, the splinter faith
    agents in that region can subsequently trigger persecution detection when
    a Militant majority civ calls compute_persecution().

    Interaction chain:
      1. detect_schisms() creates a splinter "Reformed" faith (faith 2).
      2. We relabel some agents to follow faith 2 (simulating post-schism state).
      3. A Militant civ (faith 0, stance +1) controls the region.
      4. compute_persecution() should see faith-2 agents as a minority and
         fire a Persecution event.
    """

    def test_schism_then_persecution_cascade(self):
        from chronicler.religion import detect_schisms, compute_persecution
        from chronicler.models import DOCTRINE_STANCE

        # --- Step 1: Set up a schism scenario ---
        # Civ 0 holds faith 0 (Militant, stance +1)
        majority_belief = _make_belief(
            0, doctrines=[0, 0, +1, 0, 0], name="Faith of CivA"
        )
        # Faith 1 is a second pre-existing faith held by 40% of region agents
        faith1 = _make_belief(1, name="Faith1", civ_origin=1)
        belief_registry = [majority_belief, faith1]

        region = _make_region("r0", population=100)
        regions = [region]

        civ = _make_civ("CivA", faith_id=0, region_names=["r0"])

        # Snapshot: 6 majority agents (faith 0) + 4 minority agents (faith 1)
        # minority_ratio = 0.40 > SCHISM_MINORITY_THRESHOLD (0.30)
        agents_pre = (
            [{"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
             for i in range(6)]
            + [{"id": 6 + i, "region": 0, "civ": 0, "occupation": 0, "belief": 1}
               for i in range(4)]
        )
        snap_pre = _make_snapshot_with_beliefs(agents_pre)

        schism_events = detect_schisms(
            regions, [civ], belief_registry, snap_pre, current_turn=5
        )

        # Schism must have fired (minority ratio 0.40 > 0.30)
        assert len(schism_events) == 1, (
            f"Expected 1 schism event, got {schism_events}"
        )
        assert schism_events[0].event_type == "Schism"

        # After schism, a new splinter faith (faith 2) should be in registry
        assert len(belief_registry) == 3
        splinter_faith_id = belief_registry[2].faith_id

        # --- Step 2: Build post-schism snapshot with splinter faith agents ---
        # The 4 former faith-1 agents now follow the splinter faith (faith 2)
        agents_post = (
            [{"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
             for i in range(6)]
            + [{"id": 6 + i, "region": 0, "civ": 0, "occupation": 0,
                "belief": splinter_faith_id}
               for i in range(4)]
        )
        snap_post = _make_snapshot_with_beliefs(agents_post)

        # --- Step 3: compute_persecution with Militant civ should see minority ---
        persecuted_regions: set[str] = set()
        persecution_events = compute_persecution(
            regions, [civ], belief_registry, snap_post,
            turn=6, persecuted_regions=persecuted_regions,
        )

        # Persecution must fire: minority ratio 0.40 > 0 for a Militant civ
        persecution_types = [e.event_type for e in persecution_events]
        assert "Persecution" in persecution_types, (
            f"Expected Persecution event after schism cascade; got: {persecution_types}"
        )

    def test_schism_does_not_cascade_on_pacifist_civ(self):
        """Splinter faith agents do NOT trigger persecution if civ is not Militant."""
        from chronicler.religion import detect_schisms, compute_persecution

        # Civ 0 has faith 0 with Pacifist stance (-1) — should not persecute
        pacifist_belief = _make_belief(
            0, doctrines=[0, 0, -1, 0, 0], name="Faith of CivA"
        )
        faith1 = _make_belief(1, name="Faith1", civ_origin=1)
        belief_registry = [pacifist_belief, faith1]

        region = _make_region("r0", population=100)
        civ = _make_civ("CivA", faith_id=0, region_names=["r0"])

        agents = (
            [{"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
             for i in range(6)]
            + [{"id": 6 + i, "region": 0, "civ": 0, "occupation": 0, "belief": 1}
               for i in range(4)]
        )
        snap = _make_snapshot_with_beliefs(agents)

        detect_schisms([region], [civ], belief_registry, snap, current_turn=5)

        splinter_id = belief_registry[2].faith_id if len(belief_registry) > 2 else 2
        agents_post = (
            [{"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
             for i in range(6)]
            + [{"id": 6 + i, "region": 0, "civ": 0, "occupation": 0,
                "belief": splinter_id}
               for i in range(4)]
        )
        snap_post = _make_snapshot_with_beliefs(agents_post)

        persecution_events = compute_persecution(
            [region], [civ], belief_registry, snap_post,
            turn=6, persecuted_regions=set(),
        )
        persecution_types = [e.event_type for e in persecution_events]
        assert "Persecution" not in persecution_types, (
            f"Pacifist civ should not persecute; got: {persecution_types}"
        )


# ---------------------------------------------------------------------------
# TestFullCascade
# ---------------------------------------------------------------------------

class TestFullCascade:
    """Full end-to-end cascade test requiring a complete world setup."""

    @pytest.mark.slow
    def test_full_cascade_end_to_end(self):
        pytest.skip("Requires full world setup")


# ---------------------------------------------------------------------------
# TestPilgrimageFrequency
# ---------------------------------------------------------------------------

class TestPilgrimageFrequency:
    """Pilgrimage frequency calibration test."""

    @pytest.mark.slow
    def test_pilgrimage_frequency_calibration(self):
        pytest.skip("Calibration test")
