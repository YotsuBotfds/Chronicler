"""Tests for M38b schism subsystem: axis determination, faith splitting, reformation."""
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
    Civilization,
    Leader,
    TechEra,
    FactionType,
    DOCTRINE_THEOLOGY,
    DOCTRINE_ETHICS,
    DOCTRINE_STANCE,
    DOCTRINE_OUTREACH,
    DOCTRINE_STRUCTURE,
)
from chronicler.religion import (
    determine_schism_axis,
    detect_schisms,
    fire_schism,
    detect_reformation,
    SCHISM_MINORITY_THRESHOLD,
    SCHISM_NEUTRAL_POLE_MAP,
    MAX_FAITHS,
    REFORMATION_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_belief(
    faith_id: int,
    doctrines: list[int] | None = None,
    name: str | None = None,
    civ_origin: int = 0,
) -> Belief:
    """Build a Belief with given doctrines (default all zeros)."""
    if doctrines is None:
        doctrines = [0, 0, 0, 0, 0]
    return Belief(
        name=name or f"Faith{faith_id}",
        doctrines=doctrines,
        faith_id=faith_id,
        civ_origin=civ_origin,
    )


def _make_region(
    name: str = "r",
    population: int = 100,
    persecution_intensity: float = 0.0,
    last_conquered_turn: int = -1,
) -> Region:
    region = Region(
        name=name,
        terrain="plains",
        resources="fertile",
        carrying_capacity=100,
        population=population,
    )
    region.persecution_intensity = persecution_intensity
    region.last_conquered_turn = last_conquered_turn
    return region


def _make_civ(
    name: str = "CivA",
    faith_id: int = 0,
    region_names: list[str] | None = None,
    clergy_influence: float = 0.25,
) -> Civilization:
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


def _make_snapshot(agents: list[dict]) -> pa.RecordBatch:
    return pa.record_batch({
        "id":           pa.array([a["id"]         for a in agents], type=pa.uint32()),
        "region":       pa.array([a["region"]     for a in agents], type=pa.uint16()),
        "civ_affinity": pa.array([a["civ"]        for a in agents], type=pa.uint16()),
        "occupation":   pa.array([a["occupation"] for a in agents], type=pa.uint8()),
        "belief":       pa.array([a["belief"]     for a in agents], type=pa.uint8()),
    })


# ---------------------------------------------------------------------------
# TestSchismTrigger: threshold is strictly > 0.30, not >=
# ---------------------------------------------------------------------------

class TestSchismTrigger:
    """detect_schisms fires only when minority_ratio > SCHISM_MINORITY_THRESHOLD."""

    def _run(self, minority_count: int, total: int) -> list:
        """One civ, one region, 2 faiths."""
        region = _make_region("r0")
        majority_count = total - minority_count

        agents = (
            [{"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
             for i in range(majority_count)]
            + [{"id": majority_count + i, "region": 0, "civ": 0, "occupation": 0, "belief": 1}
               for i in range(minority_count)]
        )
        snap = _make_snapshot(agents)

        civ = _make_civ("CivA", faith_id=0, region_names=["r0"])
        registry = [
            _make_belief(0, name="Faith of CivA"),
            _make_belief(1, name="Faith1"),
        ]

        return detect_schisms([region], [civ], registry, snap, current_turn=1)

    def test_exactly_at_threshold_does_not_trigger(self):
        """minority_ratio == SCHISM_MINORITY_THRESHOLD (0.30) must NOT trigger."""
        # 3 out of 10 → ratio == 0.30 exactly
        events = self._run(minority_count=3, total=10)
        assert len(events) == 0, (
            f"Ratio exactly at threshold should not fire schism; got {events}"
        )

    def test_above_threshold_triggers(self):
        """minority_ratio > SCHISM_MINORITY_THRESHOLD (e.g. 0.40) must trigger."""
        # 4 out of 10 → ratio == 0.40
        events = self._run(minority_count=4, total=10)
        assert len(events) == 1
        assert events[0].event_type == "Schism"

    def test_below_threshold_does_not_trigger(self):
        """minority_ratio < SCHISM_MINORITY_THRESHOLD (e.g. 0.20) must NOT trigger."""
        # 2 out of 10 → ratio == 0.20
        events = self._run(minority_count=2, total=10)
        assert len(events) == 0


# ---------------------------------------------------------------------------
# TestAxisMapping: axis selection from priority rules
# ---------------------------------------------------------------------------

class TestAxisMapping:
    """determine_schism_axis picks axis by priority: persecution→STANCE,
    clergy→STRUCTURE, conquest→OUTREACH, fallback→lowest abs."""

    def test_persecution_gives_stance_axis(self):
        region = _make_region("r", persecution_intensity=0.5)
        belief = _make_belief(0)  # all zeros
        axis, pole = determine_schism_axis(region, belief, current_turn=5, clergy_influence=0.0)
        assert axis == DOCTRINE_STANCE

    def test_clergy_gives_structure_axis(self):
        region = _make_region("r", persecution_intensity=0.0)
        belief = _make_belief(0)
        axis, pole = determine_schism_axis(region, belief, current_turn=5, clergy_influence=0.50)
        assert axis == DOCTRINE_STRUCTURE

    def test_conquest_gives_outreach_axis(self):
        region = _make_region("r", persecution_intensity=0.0, last_conquered_turn=0)
        belief = _make_belief(0)
        axis, pole = determine_schism_axis(region, belief, current_turn=5, clergy_influence=0.0)
        assert axis == DOCTRINE_OUTREACH

    def test_conquest_expired_does_not_give_outreach(self):
        """If last_conquered_turn is 10+ turns ago, conquest rule does not apply."""
        region = _make_region("r", persecution_intensity=0.0, last_conquered_turn=0)
        belief = _make_belief(0)
        # current_turn=15, 15-0=15 >= 10 → rule does not apply
        axis, pole = determine_schism_axis(region, belief, current_turn=15, clergy_influence=0.0)
        assert axis != DOCTRINE_OUTREACH

    def test_fallback_gives_lowest_abs_axis(self):
        """P5 fallback: axis with lowest |doctrine value| among candidates."""
        region = _make_region("r", persecution_intensity=0.0)
        # Ethics=0, Stance=+1, Outreach=-1, Structure=+1 → lowest abs is Ethics
        doctrines = [0, 0, +1, -1, +1]  # theology, ethics, stance, outreach, structure
        belief = _make_belief(0, doctrines=doctrines)
        axis, _pole = determine_schism_axis(region, belief, current_turn=5, clergy_influence=0.0)
        assert axis == DOCTRINE_ETHICS

    def test_persecution_takes_priority_over_clergy(self):
        """P1 (persecution) beats P2 (clergy)."""
        region = _make_region("r", persecution_intensity=0.8)
        belief = _make_belief(0)
        axis, pole = determine_schism_axis(region, belief, current_turn=5, clergy_influence=0.60)
        assert axis == DOCTRINE_STANCE


# ---------------------------------------------------------------------------
# TestNeutralAxisHandling: axis_value == 0 → use SCHISM_NEUTRAL_POLE_MAP
# ---------------------------------------------------------------------------

class TestNeutralAxisHandling:
    """When the chosen axis is 0 in original doctrines, use SCHISM_NEUTRAL_POLE_MAP."""

    def test_persecution_axis_at_zero_uses_neutral_map(self):
        """Persecution → STANCE; if doctrines[STANCE] == 0, pole = map[STANCE] = -1."""
        region = _make_region("r", persecution_intensity=0.5)
        doctrines = [0, 0, 0, 0, 0]  # STANCE is 0
        belief = _make_belief(0, doctrines=doctrines)
        _axis, pole = determine_schism_axis(region, belief, current_turn=1, clergy_influence=0.0)
        assert pole == SCHISM_NEUTRAL_POLE_MAP[DOCTRINE_STANCE]

    def test_clergy_axis_at_zero_uses_neutral_map(self):
        """Clergy → STRUCTURE; if doctrines[STRUCTURE] == 0, pole = map[STRUCTURE] = -1."""
        region = _make_region("r", persecution_intensity=0.0)
        doctrines = [0, 0, 0, 0, 0]  # STRUCTURE is 0
        belief = _make_belief(0, doctrines=doctrines)
        _axis, pole = determine_schism_axis(region, belief, current_turn=1, clergy_influence=0.50)
        assert pole == SCHISM_NEUTRAL_POLE_MAP[DOCTRINE_STRUCTURE]

    def test_nonzero_axis_negates_value(self):
        """If axis value != 0, pole = negated value."""
        region = _make_region("r", persecution_intensity=0.5)
        doctrines = [0, 0, +1, 0, 0]  # STANCE = +1
        belief = _make_belief(0, doctrines=doctrines)
        _axis, pole = determine_schism_axis(region, belief, current_turn=1, clergy_influence=0.0)
        assert pole == -1  # negate +1

    def test_negative_axis_value_negates_to_positive(self):
        """If axis value == -1, pole = +1."""
        region = _make_region("r", persecution_intensity=0.5)
        doctrines = [0, 0, -1, 0, 0]  # STANCE = -1
        belief = _make_belief(0, doctrines=doctrines)
        _axis, pole = determine_schism_axis(region, belief, current_turn=1, clergy_influence=0.0)
        assert pole == +1  # negate -1


# ---------------------------------------------------------------------------
# TestRegistryCap: MAX_FAITHS == 16; schisms blocked when registry is full
# ---------------------------------------------------------------------------

class TestRegistryCap:
    """detect_schisms returns [] immediately when len(belief_registry) >= MAX_FAITHS."""

    def test_max_faiths_constant(self):
        assert MAX_FAITHS == 16

    def test_full_registry_blocks_schism(self):
        """16 faiths in registry → detect_schisms returns [] without firing."""
        # Build 16 beliefs (IDs 0-15)
        registry = [_make_belief(i) for i in range(MAX_FAITHS)]
        assert len(registry) == MAX_FAITHS

        region = _make_region("r0")
        civ = _make_civ("CivA", faith_id=0, region_names=["r0"])

        # Build snapshot with 60% minority → would trigger without the cap
        agents = (
            [{"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
             for i in range(4)]
            + [{"id": 4 + i, "region": 0, "civ": 0, "occupation": 0, "belief": 1}
               for i in range(6)]
        )
        snap = _make_snapshot(agents)

        events = detect_schisms([region], [civ], registry, snap, current_turn=1)
        assert events == []
        assert len(registry) == MAX_FAITHS  # registry unchanged

    def test_one_below_cap_allows_schism(self):
        """15 faiths in registry → schism can fire (adds to 16)."""
        registry = [_make_belief(i) for i in range(MAX_FAITHS - 1)]
        assert len(registry) == 15

        region = _make_region("r0")
        civ = _make_civ("CivA", faith_id=0, region_names=["r0"])

        agents = (
            [{"id": i, "region": 0, "civ": 0, "occupation": 0, "belief": 0}
             for i in range(4)]
            + [{"id": 4 + i, "region": 0, "civ": 0, "occupation": 0, "belief": 1}
               for i in range(6)]
        )
        snap = _make_snapshot(agents)

        events = detect_schisms([region], [civ], registry, snap, current_turn=1)
        assert len(events) == 1
        assert len(registry) == MAX_FAITHS  # now full


# ---------------------------------------------------------------------------
# TestReformationThreshold: fires at >= 0.60, not below
# ---------------------------------------------------------------------------

class TestReformationThreshold:
    """detect_reformation fires only when ratio >= REFORMATION_THRESHOLD (0.60)."""

    def _make_civ_with_faith_shift(
        self,
        previous_faith: int,
        current_faith: int,
        ratio: float,
        region_names: list[str] | None = None,
    ) -> Civilization:
        regions = ["r0"] if region_names is None else region_names
        civ = _make_civ("CivA", faith_id=current_faith, region_names=regions)
        civ.previous_majority_faith = previous_faith
        civ._majority_faith_ratio = ratio
        return civ

    def test_at_threshold_fires(self):
        """ratio == REFORMATION_THRESHOLD (0.60) must fire reformation."""
        civ = self._make_civ_with_faith_shift(
            previous_faith=0, current_faith=1, ratio=REFORMATION_THRESHOLD,
        )
        registry = [_make_belief(0, name="OldFaith"), _make_belief(1, name="NewFaith")]
        events = detect_reformation([civ], registry)
        assert len(events) == 1
        assert events[0].event_type == "Reformation"
        assert events[0].importance == 8

    def test_above_threshold_fires(self):
        """ratio > REFORMATION_THRESHOLD must fire reformation."""
        civ = self._make_civ_with_faith_shift(
            previous_faith=0, current_faith=1, ratio=0.80,
        )
        registry = [_make_belief(0), _make_belief(1)]
        events = detect_reformation([civ], registry)
        assert len(events) == 1

    def test_below_threshold_does_not_fire(self):
        """ratio < REFORMATION_THRESHOLD must NOT fire reformation."""
        civ = self._make_civ_with_faith_shift(
            previous_faith=0, current_faith=1, ratio=0.59,
        )
        registry = [_make_belief(0), _make_belief(1)]
        events = detect_reformation([civ], registry)
        assert len(events) == 0

    def test_same_faith_does_not_fire(self):
        """No shift in majority faith → no reformation even at high ratio."""
        civ = self._make_civ_with_faith_shift(
            previous_faith=0, current_faith=0, ratio=0.90,
        )
        registry = [_make_belief(0)]
        events = detect_reformation([civ], registry)
        assert len(events) == 0

    def test_previous_faith_updated_after_event(self):
        """After firing, previous_majority_faith is updated to current."""
        civ = self._make_civ_with_faith_shift(
            previous_faith=0, current_faith=1, ratio=0.70,
        )
        registry = [_make_belief(0), _make_belief(1)]
        detect_reformation([civ], registry)
        assert civ.previous_majority_faith == 1

    def test_dead_civ_skipped(self):
        """Civ with no regions is skipped."""
        civ = self._make_civ_with_faith_shift(
            previous_faith=0, current_faith=1, ratio=0.90, region_names=[],
        )
        registry = [_make_belief(0), _make_belief(1)]
        events = detect_reformation([civ], registry)
        assert len(events) == 0


# ---------------------------------------------------------------------------
# TestFireSchism: faith naming, doctrine flip, registry append
# ---------------------------------------------------------------------------

class TestFireSchism:
    """Unit tests for fire_schism directly."""

    def test_splinter_faith_added_to_registry(self):
        region = _make_region("r0")
        civ = _make_civ("CivA", faith_id=0)
        civ._civ_id = 0

        original = _make_belief(0, doctrines=[0, 0, +1, 0, 0], name="Faith of CivA")
        registry = [original]

        new_belief = fire_schism(region, 0, registry, civ, current_turn=1)

        assert new_belief is not None
        assert len(registry) == 2
        assert new_belief in registry

    def test_splinter_name_is_reformed(self):
        region = _make_region("r0")
        civ = _make_civ("CivA", faith_id=0)
        civ._civ_id = 0

        original = _make_belief(0, name="Faith of CivA")
        registry = [original]

        new_belief = fire_schism(region, 0, registry, civ, current_turn=1)
        assert new_belief.name == "Faith of CivA (Reformed)"

    def test_splinter_name_increments_on_collision(self):
        region = _make_region("r0")
        civ = _make_civ("CivA", faith_id=0)
        civ._civ_id = 0

        original = _make_belief(0, name="Faith of CivA")
        reformed = _make_belief(1, name="Faith of CivA (Reformed)")
        registry = [original, reformed]

        new_belief = fire_schism(region, 0, registry, civ, current_turn=1)
        assert new_belief.name == "Faith of CivA (Reformed 2)"

    def test_region_schism_flags_set(self):
        region = _make_region("r0")
        civ = _make_civ("CivA", faith_id=0)
        civ._civ_id = 0

        original = _make_belief(0, name="Faith of CivA")
        registry = [original]

        new_belief = fire_schism(region, 0, registry, civ, current_turn=1)
        assert region.schism_convert_from == 0
        assert region.schism_convert_to == new_belief.faith_id

    def test_returns_none_when_registry_full(self):
        region = _make_region("r0")
        civ = _make_civ("CivA", faith_id=0)
        civ._civ_id = 0

        registry = [_make_belief(i) for i in range(MAX_FAITHS)]

        result = fire_schism(region, 0, registry, civ, current_turn=1)
        assert result is None

    def test_returns_none_for_unknown_faith(self):
        region = _make_region("r0")
        civ = _make_civ("CivA", faith_id=99)
        civ._civ_id = 0
        registry = [_make_belief(0)]

        result = fire_schism(region, 99, registry, civ, current_turn=1)
        assert result is None
