"""Tests for M38b persecution detection, martyrdom boost lifecycle."""
from __future__ import annotations

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
    """intensity = minority_ratio (larger minorities → higher intensity)."""

    def _get_intensity(self, minority_count: int, total: int, world=None) -> float:
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
            persecuted_regions=set(), world=world,
        )
        return region.persecution_intensity

    def test_intensity_multiplier_scales_below_cap(self):
        from types import SimpleNamespace
        world = SimpleNamespace(tuning_overrides={"multiplier.religion_intensity": 1.5})
        intensity = self._get_intensity(minority_count=2, total=10, world=world)
        assert intensity == pytest.approx(0.30, abs=1e-9)

    def test_intensity_clamped_to_one_under_high_multiplier(self):
        """Audit T3-4: multiplier.religion_intensity must not push intensity past 1.0."""
        from types import SimpleNamespace
        world = SimpleNamespace(tuning_overrides={"multiplier.religion_intensity": 2.0})
        for minority_count in (5, 7, 9):
            intensity = self._get_intensity(minority_count=minority_count, total=10, world=world)
            assert 0.0 < intensity <= 1.0
        assert self._get_intensity(minority_count=9, total=10, world=world) == 1.0

    def test_intensity_at_10_percent(self):
        # 1 minority out of 10 → ratio = 0.10 → intensity = 0.10
        intensity = self._get_intensity(minority_count=1, total=10)
        assert intensity == pytest.approx(0.10, abs=1e-9)

    def test_intensity_at_40_percent(self):
        # 4 minority out of 10 → ratio = 0.40 → intensity = 0.40
        intensity = self._get_intensity(minority_count=4, total=10)
        assert intensity == pytest.approx(0.40, abs=1e-9)

    def test_intensity_at_50_percent(self):
        # 5 minority out of 10 → ratio = 0.50 → intensity = 0.50
        intensity = self._get_intensity(minority_count=5, total=10)
        assert intensity == pytest.approx(0.50, abs=1e-9)

    def test_intensity_monotonically_increases_with_minority_ratio(self):
        """B-2 regression: larger minorities must produce higher intensity."""
        ratios = [0.05, 0.10, 0.20, 0.30, 0.40, 0.50]
        intensities = []
        for ratio in ratios:
            total = 100
            minority_count = int(ratio * total)
            intensities.append(self._get_intensity(minority_count, total))
        for i in range(len(intensities) - 1):
            assert intensities[i] < intensities[i + 1], (
                f"Intensity should increase: {ratios[i]} → {intensities[i]}, "
                f"{ratios[i + 1]} → {intensities[i + 1]}"
            )


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


# ---------------------------------------------------------------------------
# TestPersecutionFollowsCurrentRuler
# ---------------------------------------------------------------------------

def _agents(region: int, civ: int, belief: int, n: int, start: int) -> list[dict]:
    return [{"id": start + i, "region": region, "civ": civ, "occupation": 0, "belief": belief}
            for i in range(n)]


class TestPersecutionFollowsCurrentRuler:
    """The builder owns every region's intensity: persecution is the current
    ruler's policy, never a value left from an earlier ruler or faith."""

    def _world(self):
        regions = [_make_region("r0"), _make_region("r1")]
        regions[0].controller = "Militant"
        regions[1].controller = "Calm"
        beliefs = [_make_belief(0, stance=+1), _make_belief(1, stance=0), _make_belief(2, stance=-1)]
        militant = _make_civ("Militant", faith_id=0, region_names=["r0"])
        calm = _make_civ("Calm", faith_id=1, region_names=["r1"])
        # r0: 8 of the militant faith, 2 of a minority faith; r1: 10 of faith 1.
        snap = _make_snapshot(_agents(0, 0, 0, 8, 0) + _agents(0, 0, 2, 2, 8)
                              + _agents(1, 1, 1, 10, 10))
        return regions, [militant, calm], beliefs, snap

    @staticmethod
    def _persecute(regions, civs, beliefs, snap, turn, seen=None):
        return compute_persecution(regions, civs, beliefs, snap, turn=turn,
                                   persecuted_regions=set() if seen is None else seen)

    def test_militant_ruler_persecutes(self):
        regions, civs, beliefs, snap = self._world()
        self._persecute(regions, civs, beliefs, snap, 1)
        assert regions[0].persecution_intensity == pytest.approx(0.2)
        assert regions[1].persecution_intensity == 0.0

    def test_reset_when_the_rulers_faith_is_no_longer_militant(self):
        regions, civs, beliefs, snap = self._world()
        self._persecute(regions, civs, beliefs, snap, 1)
        civs[0].civ_majority_faith = 2  # the realm's majority left the militant faith
        events = self._persecute(regions, civs, beliefs, snap, 2)
        assert regions[0].persecution_intensity == 0.0
        assert events == []

    def test_reset_when_the_faith_itself_stops_being_militant(self):
        regions, civs, beliefs, snap = self._world()
        self._persecute(regions, civs, beliefs, snap, 1)
        beliefs[0].doctrines[DOCTRINE_STANCE] = 0
        self._persecute(regions, civs, beliefs, snap, 2)
        assert regions[0].persecution_intensity == 0.0

    def test_reset_when_the_region_changes_hands(self):
        regions, civs, beliefs, snap = self._world()
        self._persecute(regions, civs, beliefs, snap, 1)
        assert regions[0].persecution_intensity > 0.0
        # The calm realm takes r0; the militant realm keeps no land.
        civs[0].regions = []
        civs[1].regions = ["r1", "r0"]
        regions[0].controller = "Calm"
        self._persecute(regions, civs, beliefs, snap, 2)
        assert regions[0].persecution_intensity == 0.0

    def test_reset_when_the_region_loses_its_ruler(self):
        regions, civs, beliefs, snap = self._world()
        self._persecute(regions, civs, beliefs, snap, 1)
        civs[0].regions = []
        regions[0].controller = None
        self._persecute(regions, civs, beliefs, snap, 2)
        assert regions[0].persecution_intensity == 0.0

    def test_a_militant_conqueror_persecutes_its_new_region(self):
        regions, civs, beliefs, snap = self._world()
        # The militant realm conquers r1: its 10 agents of faith 1 are now a
        # minority under a militant ruler; r0 stays persecuted.
        civs[0].regions = ["r0", "r1"]
        civs[1].regions = []
        regions[1].controller = "Militant"
        self._persecute(regions, civs, beliefs, snap, 1)
        assert regions[0].persecution_intensity == pytest.approx(0.2)
        assert regions[1].persecution_intensity == pytest.approx(1.0)

    def test_multi_turn_intensity_follows_the_ruler_and_restarts(self):
        """Live -> reset -> stays reset -> live again, with the one-shot event
        firing again once the region was cleared (the H-14 set filter)."""
        regions, civs, beliefs, snap = self._world()
        seen: set[str] = set()
        observed = []
        fired = []
        for turn, faith in enumerate([0, 2, 2, 0, 0], start=1):
            civs[0].civ_majority_faith = faith
            # simulation.py's H-14 filter: forget regions whose persecution ended
            seen = {name for name in seen
                    if any(r.name == name and r.persecution_intensity > 0 for r in regions)}
            events = self._persecute(regions, civs, beliefs, snap, turn, seen)
            observed.append(round(regions[0].persecution_intensity, 6))
            fired.append([e.event_type for e in events if e.event_type == "Persecution"])
            assert regions[1].persecution_intensity == 0.0
        assert observed == [0.2, 0.0, 0.0, 0.2, 0.2]
        assert fired == [["Persecution"], [], [], ["Persecution"], []]


class TestPersecutionResetReachesTheAgentTick:
    """Multi-turn consumption: Phase 10 recomputes persecution and the next
    turn's region batch (the Rust tick's input) carries the current value."""

    @staticmethod
    def _snapshot(rows: list[tuple[int, int, int]]) -> pa.RecordBatch:
        n = len(rows)
        return pa.record_batch({
            "id": pa.array(list(range(n)), type=pa.uint32()),
            "region": pa.array([r for r, _, _ in rows], type=pa.uint16()),
            "civ_affinity": pa.array([c for _, c, _ in rows], type=pa.uint16()),
            "occupation": pa.array([0] * n, type=pa.uint8()),
            "belief": pa.array([b for _, _, b in rows], type=pa.uint8()),
            "cultural_value_0": pa.array([0] * n, type=pa.uint8()),
            "cultural_value_1": pa.array([255] * n, type=pa.uint8()),
            "cultural_value_2": pa.array([255] * n, type=pa.uint8()),
            "loyalty_trait": pa.array([0.5] * n, type=pa.float32()),
            "loyalty": pa.array([0.5] * n, type=pa.float32()),
            "x": pa.array([0.5] * n, type=pa.float32()),
            "y": pa.array([0.5] * n, type=pa.float32()),
        })

    def test_reset_survives_turns_and_restarts(self):
        from chronicler.agent_bridge import build_region_batch
        from chronicler.models import Relationship, WorldState
        from chronicler.simulation import phase_consequences

        regions = [_make_region("A"), _make_region("B"), _make_region("C")]
        regions[0].controller = regions[2].controller = "Sword"
        regions[1].controller = "Calm"
        civs = [_make_civ("Sword", faith_id=0xFF, region_names=["A", "C"]),
                _make_civ("Calm", faith_id=0xFF, region_names=["B"])]
        world = WorldState(
            name="T", seed=1, turn=0, regions=regions, civilizations=civs,
            relationships={"Sword": {"Calm": Relationship()}, "Calm": {"Sword": Relationship()}},
        )
        world.agent_mode = "off"
        world.belief_registry = [_make_belief(0, stance=+1), _make_belief(1, stance=0),
                                 _make_belief(2, stance=-1)]
        # A: 8 of the militant faith and 2 of a minority; B: faith 1; C: the
        # militant faith only. Minorities stay under the schism threshold.
        base = [(0, 0, 0)] * 8 + [(0, 0, 2)] * 2 + [(1, 1, 1)] * 10 + [(2, 0, 0)] * 10
        # 40 Sword agents of the pacifist faith living in B move the realm's
        # majority off the militant faith without a regional schism.
        lapsed = base + [(1, 0, 2)] * 40

        def turn(rows, *, conquest=False):
            if conquest:
                civs[0].regions = ["C"]
                civs[1].regions = ["B", "A"]
                regions[0].controller = "Calm"
            world._agent_snapshot = self._snapshot(rows)
            events = phase_consequences(world)
            world.turn += 1
            batch = build_region_batch(world)
            sent = [round(v, 6) for v in batch.column("persecution_intensity").to_pylist()]
            assert sent == [round(r.persecution_intensity, 6) for r in regions]
            return sent, [e for e in events if e.event_type == "Persecution"]

        sent, fired = turn(base)
        assert civs[0].civ_majority_faith == 0
        assert sent == [0.2, 0.0, 0.0] and len(fired) == 1
        sent, fired = turn(lapsed)       # the realm's faith left militancy
        assert civs[0].civ_majority_faith == 2
        assert sent == [0.0, 0.0, 0.0] and fired == []
        sent, fired = turn(lapsed)       # and the region stays clear
        assert sent == [0.0, 0.0, 0.0] and fired == []
        sent, fired = turn(base)         # the militant faith returns
        assert civs[0].civ_majority_faith == 0
        assert sent == [0.2, 0.0, 0.0] and len(fired) == 1
        sent, fired = turn(base, conquest=True)  # A passes to the calm realm
        assert sent == [0.0, 0.0, 0.0] and fired == []
        sent, fired = turn(base)
        assert sent == [0.0, 0.0, 0.0] and fired == []
