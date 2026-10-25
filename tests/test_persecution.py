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


# ---------------------------------------------------------------------------
# TestPersecutingFaith: who is persecuted
# ---------------------------------------------------------------------------

class TestPersecutingFaith:
    """Persecution targets everyone outside the militant ruler's faith (the
    faith the builder measured the minority against), also where that faith
    is itself a local minority."""

    def _conquest(self):
        # A militant realm (faith 0) rules r0, where faith 1 is the majority.
        region = _make_region("r0")
        region.controller = "Militant"
        beliefs = [_make_belief(0, stance=+1), _make_belief(1, stance=0)]
        civ = _make_civ("Militant", faith_id=0, region_names=["r0"])
        snap = _make_snapshot(_agents(0, 0, 0, 3, 0) + _agents(0, 1, 1, 7, 3))
        return region, civ, beliefs, snap

    def test_builder_records_the_rulers_faith_and_clears_it(self):
        region, civ, beliefs, snap = self._conquest()
        compute_persecution([region], [civ], beliefs, snap, turn=1, persecuted_regions=set())
        assert region.persecution_intensity == pytest.approx(0.7)
        assert region.persecuting_faith == 0
        civ.civ_majority_faith = 1  # no longer militant
        compute_persecution([region], [civ], beliefs, snap, turn=2, persecuted_regions=set())
        assert region.persecution_intensity == 0.0
        assert region.persecuting_faith is None

    def test_no_persecuting_faith_without_a_minority(self):
        region, civ, beliefs, _ = self._conquest()
        region.persecuting_faith = 1
        snap = _make_snapshot(_agents(0, 0, 0, 5, 0))
        compute_persecution([region], [civ], beliefs, snap, turn=1, persecuted_regions=set())
        assert region.persecution_intensity == 0.0
        assert region.persecuting_faith is None

    def test_region_batch_carries_the_persecuting_faith_each_turn(self, sample_world):
        from chronicler.agent_bridge import build_region_batch
        batch = build_region_batch(sample_world)
        assert batch.schema.field("persecuting_faith").type == pa.uint8()
        assert set(batch.column("persecuting_faith").to_pylist()) == {0xFF}
        sample_world.regions[1].persecution_intensity = 0.4
        sample_world.regions[1].persecuting_faith = 3
        first = build_region_batch(sample_world).column("persecuting_faith").to_pylist()
        assert first[1] == 3 and set(first[:1] + first[2:]) == {0xFF}
        # A persisted field, not a one-shot signal: unchanged until Phase 10
        # recomputes it, then cleared together with the intensity.
        assert build_region_batch(sample_world).column("persecuting_faith").to_pylist() == first
        compute_persecution(sample_world.regions, sample_world.civilizations, [], None,
                            turn=1, persecuted_regions=set())
        cleared = build_region_batch(sample_world)
        assert set(cleared.column("persecuting_faith").to_pylist()) == {0xFF}
        assert set(cleared.column("persecution_intensity").to_pylist()) == {0.0}

    def test_region_omits_persecuting_faith_while_none_and_old_saves_load(self):
        region = _make_region("r0")
        assert "persecuting_faith" not in region.model_dump()
        assert "persecuting_faith" not in region.model_dump_json()
        region.persecution_intensity = 0.5
        region.persecuting_faith = 2
        data = region.model_dump()
        assert data["persecuting_faith"] == 2
        assert Region.model_validate(data).persecuting_faith == 2
        del data["persecuting_faith"]  # a save from before the field
        assert Region.model_validate(data).persecuting_faith is None

    def test_martyrdom_counts_the_persecuted_not_the_rulers_faith(self):
        region, civ, beliefs, snap = self._conquest()
        compute_persecution([region], [civ], beliefs, snap, turn=1, persecuted_regions=set())
        region.majority_belief = 1
        # A death of the ruler's own faith is no martyrdom, even where that
        # faith is a local minority.
        compute_martyrdom_boosts([region], [{"region_idx": 0, "belief": 0}])
        assert region.martyrdom_boost == 0.0
        # A death of the persecuted local majority is.
        compute_martyrdom_boosts([region], [{"region_idx": 0, "belief": 1}])
        assert region.martyrdom_boost == pytest.approx(MARTYRDOM_BOOST_PER_EVENT)

    def test_martyrdom_without_a_persecuting_faith_uses_the_region_majority(self):
        region = _make_region("r0")
        region.persecution_intensity = 0.5
        region.majority_belief = 0
        compute_martyrdom_boosts([region], [{"region_idx": 0, "belief": 0}])
        assert region.martyrdom_boost == 0.0
        compute_martyrdom_boosts([region], [{"region_idx": 0, "belief": 1}])
        assert region.martyrdom_boost == pytest.approx(MARTYRDOM_BOOST_PER_EVENT)


def _native_world(make_world, *, intensity: float, persecuting_faith):
    """One hybrid region of faith-1 agents; the region carries the given
    persecution as Phase 10 would leave it for the next tick."""
    world = make_world(num_civs=1)
    world.agent_mode = "hybrid"
    world.belief_registry = [_make_belief(0, stance=+1), _make_belief(1, stance=0)]
    world.civilizations[0].civ_majority_faith = 1
    region = world.regions[0]
    region.population = 30
    world.civilizations[0].population = 30
    region.majority_belief = 1
    region.persecution_intensity = intensity
    region.persecuting_faith = persecuting_faith
    return world


def _persecution_memories(bridge) -> int:
    snap = bridge.get_snapshot()
    ids = snap.column("id").to_pylist()
    return sum(1 for agent_id in ids
               for memory in bridge._sim.get_agent_memories(agent_id) if memory[0] == 3)


def test_native_tick_persecutes_everyone_outside_the_rulers_faith_across_turns(make_world):
    """Multi-turn consumption by the Rust tick: a militant ruler of faith 0
    persecutes this faith-1 majority; a ruler of faith 1 persecutes nobody
    here; once Phase 10 resets the region the next ticks persecute nobody, and
    a restart writes new persecution memories (the gate was cleared)."""
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")
    from chronicler.agent_bridge import AgentBridge

    worlds = {
        "foreign": _native_world(make_world, intensity=0.8, persecuting_faith=0),
        "own": _native_world(make_world, intensity=0.8, persecuting_faith=1),
    }
    bridges = {k: AgentBridge(w, mode="hybrid") for k, w in worlds.items()}
    memories = {k: [] for k in worlds}
    satisfaction = {k: [] for k in worlds}
    for turn, (intensity, foreign_faith) in enumerate(
            [(0.8, 0), (0.0, None), (0.0, None), (0.8, 0)], start=1):
        for key, world in worlds.items():
            region = world.regions[0]
            region.persecution_intensity = intensity
            region.persecuting_faith = (foreign_faith if key == "foreign" else 1) if intensity else None
            world.turn = turn
            bridges[key].tick(world)
            memories[key].append(_persecution_memories(bridges[key]))
            sats = bridges[key].get_snapshot().column("satisfaction").to_pylist()
            satisfaction[key].append(sum(sats) / len(sats))
    # Only the foreign ruler's persecution reaches the faith-1 majority.
    assert memories["own"] == [0, 0, 0, 0]
    assert memories["foreign"][0] > 0
    assert satisfaction["foreign"][0] < satisfaction["own"][0]
    # Reset: no new persecution memories while the region is clear, and the
    # satisfaction gap shrinks to what the memories leave behind ...
    assert memories["foreign"][1] <= memories["foreign"][0]
    assert memories["foreign"][2] <= memories["foreign"][1]
    gap = [own - foreign for own, foreign in zip(satisfaction["own"], satisfaction["foreign"])]
    assert gap[2] < gap[0] / 2
    # ... and a restart writes them again.
    assert memories["foreign"][3] > memories["foreign"][2]
