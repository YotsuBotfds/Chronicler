"""Tests for M16a cultural foundations."""
import pytest
from chronicler.models import Civilization, Region, Relationship, Leader, TechEra, Disposition, WorldState
from chronicler.models import ActiveCondition
from chronicler.culture import (
    VALUE_OPPOSITIONS, apply_value_drift,
    tick_cultural_assimilation, ASSIMILATION_THRESHOLD, ASSIMILATION_GUARD_TURNS, RECONQUEST_COOLDOWN,
    tick_prestige,
)


class TestModelFields:
    def test_civilization_has_prestige_field(self):
        civ = Civilization(
            name="Test", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade"], regions=["R1"],
        )
        assert civ.prestige == 0

    def test_region_has_cultural_identity_field(self):
        region = Region(name="R1", terrain="plains", carrying_capacity=5, resources="fertile")
        assert region.cultural_identity is None
        assert region.foreign_control_turns == 0

    def test_relationship_has_disposition_drift_field(self):
        rel = Relationship()
        assert rel.disposition_drift == 0


@pytest.fixture
def drift_world():
    """Two civs with known value relationships."""
    regions = [
        Region(name="R1", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivA"),
        Region(name="R2", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivB"),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LA", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade", "Order"], regions=["R1"],
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LB", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade", "Freedom"], regions=["R2"],
        ),
    ]
    relationships = {
        "CivA": {"CivB": Relationship(disposition=Disposition.NEUTRAL)},
        "CivB": {"CivA": Relationship(disposition=Disposition.NEUTRAL)},
    }
    return WorldState(
        name="test", seed=42, regions=regions,
        civilizations=civs, relationships=relationships,
    )


class TestValueOppositions:
    def test_freedom_opposes_order(self):
        assert VALUE_OPPOSITIONS["Freedom"] == "Order"

    def test_neutral_values_not_in_table(self):
        assert "Strength" not in VALUE_OPPOSITIONS
        assert "Destiny" not in VALUE_OPPOSITIONS


class TestValueDrift:
    def test_shared_value_positive_drift(self, drift_world):
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 0  # shared=1, opposing=1 -> net=0

    def test_pure_shared_values_drift(self, drift_world):
        drift_world.civilizations[1].values = ["Trade", "Order"]
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 4  # shared=2, opposing=0

    def test_drift_upgrades_disposition_at_threshold(self, drift_world):
        drift_world.civilizations[1].values = ["Trade", "Order"]
        drift_world.relationships["CivA"]["CivB"].disposition_drift = 8
        drift_world.relationships["CivB"]["CivA"].disposition_drift = 8
        apply_value_drift(drift_world)
        rel_ab = drift_world.relationships["CivA"]["CivB"]
        assert rel_ab.disposition == Disposition.FRIENDLY
        assert rel_ab.disposition_drift == 0

    def test_drift_downgrades_disposition_at_negative_threshold(self, drift_world):
        drift_world.civilizations[0].values = ["Freedom"]
        drift_world.civilizations[1].values = ["Order"]
        drift_world.relationships["CivA"]["CivB"].disposition_drift = -9
        drift_world.relationships["CivB"]["CivA"].disposition_drift = -9
        apply_value_drift(drift_world)
        rel_ab = drift_world.relationships["CivA"]["CivB"]
        assert rel_ab.disposition == Disposition.SUSPICIOUS
        assert rel_ab.disposition_drift == 0

    def test_empty_values_no_drift(self, drift_world):
        drift_world.civilizations[0].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 0

    def test_agent_value_drift_is_stable_across_snapshot_row_order(self, drift_world):
        class _FakeColumn:
            def __init__(self, values):
                self._values = values

            def to_pylist(self):
                return list(self._values)

        class _FakeSnapshot:
            def __init__(self, columns):
                self._columns = columns
                self.num_rows = len(next(iter(columns.values()))) if columns else 0

            def column(self, name):
                return _FakeColumn(self._columns[name])

        columns_a = {
            "civ_affinity": [0, 0, 1, 1],
            "cultural_value_0": [0, 0, 0, 0],
            "cultural_value_1": [1, 1, 1, 1],
            "cultural_value_2": [2, 2, 3, 3],
        }
        columns_b = {
            "civ_affinity": [1, 0, 1, 0],
            "cultural_value_0": [0, 0, 0, 0],
            "cultural_value_1": [1, 1, 1, 1],
            "cultural_value_2": [3, 2, 3, 2],
        }

        world_a = drift_world.model_copy(deep=True)
        world_b = drift_world.model_copy(deep=True)

        apply_value_drift(world_a, agent_snapshot=_FakeSnapshot(columns_a))
        apply_value_drift(world_b, agent_snapshot=_FakeSnapshot(columns_b))

        assert world_a.relationships["CivA"]["CivB"].disposition_drift == 3
        assert (
            world_a.relationships["CivA"]["CivB"].disposition_drift
            == world_b.relationships["CivA"]["CivB"].disposition_drift
        )


@pytest.fixture
def assimilation_world():
    regions = [
        Region(
            name="Contested", terrain="plains", carrying_capacity=5,
            resources="fertile", controller="CivB",
            cultural_identity="CivA", foreign_control_turns=0,
        ),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LA", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade"], regions=[],
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LB", trait="cautious", reign_start=0),
            domains=["trade"], values=["Order"], regions=["Contested"],
        ),
    ]
    return WorldState(
        name="test", seed=42, regions=regions, civilizations=civs,
        relationships={"CivA": {"CivB": Relationship()}, "CivB": {"CivA": Relationship()}},
    )


class TestCulturalAssimilation:
    class _FakeColumn:
        def __init__(self, values):
            self._values = values

        def to_pylist(self):
            return list(self._values)

    class _FakeSnapshot:
        def __init__(self, columns):
            self._columns = columns
            self.num_rows = len(next(iter(columns.values()))) if columns else 0

        def column(self, name):
            return TestCulturalAssimilation._FakeColumn(self._columns[name])

    def test_foreign_control_increments(self, assimilation_world):
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].foreign_control_turns == 1

    def test_assimilation_flips_identity_at_threshold(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = ASSIMILATION_THRESHOLD - 1
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].cultural_identity == "CivB"
        assert assimilation_world.regions[0].foreign_control_turns == 0

    def test_assimilation_generates_named_event(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = ASSIMILATION_THRESHOLD - 1
        tick_cultural_assimilation(assimilation_world)
        assert any(
            ne.event_type == "cultural_assimilation"
            for ne in assimilation_world.named_events
        )

    def test_stability_drain_per_mismatched_region(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = RECONQUEST_COOLDOWN
        initial_stability = assimilation_world.civilizations[1].stability
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.civilizations[1].stability == initial_stability - 3

    def test_reconquest_cooldown_exempts_drain(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = 5
        initial_stability = assimilation_world.civilizations[1].stability
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.civilizations[1].stability == initial_stability

    def test_first_control_sets_identity_immediately(self, assimilation_world):
        assimilation_world.regions[0].cultural_identity = None
        assimilation_world.regions[0].controller = "CivB"
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].cultural_identity == "CivB"
        assert assimilation_world.regions[0].foreign_control_turns == 0

    def test_matching_identity_resets_counter(self, assimilation_world):
        assimilation_world.regions[0].controller = "CivA"
        assimilation_world.regions[0].cultural_identity = "CivA"
        assimilation_world.regions[0].foreign_control_turns = 10
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].foreign_control_turns == 0

    def test_agent_path_falls_back_to_timer_threshold(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = ASSIMILATION_THRESHOLD - 1
        snapshot = self._FakeSnapshot(
            {
                "region": [0, 0, 0],
                "cultural_value_0": [0, 0, 0],
                "cultural_value_1": [0, 0, 0],
                "cultural_value_2": [0, 0, 0],
            }
        )

        tick_cultural_assimilation(assimilation_world, agent_snapshot=snapshot)

        assert assimilation_world.regions[0].cultural_identity == "CivB"
        assert assimilation_world.regions[0].foreign_control_turns == 0

    def test_agent_path_sets_passive_culture_pressure_after_guard_turns(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = ASSIMILATION_GUARD_TURNS - 1
        snapshot = self._FakeSnapshot(
            {
                "region": [0, 0, 0],
                "cultural_value_0": [0, 0, 0],
                "cultural_value_1": [0, 0, 0],
                "cultural_value_2": [0, 0, 0],
            }
        )

        tick_cultural_assimilation(assimilation_world, agent_snapshot=snapshot)

        assert getattr(assimilation_world.regions[0], "_culture_investment_active", False) is True

    def test_reconquest_applies_restless_population(self, assimilation_world):
        assimilation_world.regions[0].cultural_identity = "CivA"
        assimilation_world.regions[0].controller = "CivA"
        assimilation_world.regions[0].foreign_control_turns = 5
        tick_cultural_assimilation(assimilation_world)
        restless = [
            c for c in assimilation_world.active_conditions
            if c.condition_type == "restless_population"
        ]
        assert len(restless) == 1
        assert restless[0].duration == RECONQUEST_COOLDOWN


class TestPrestige:
    def test_prestige_decays(self, drift_world):
        drift_world.civilizations[0].prestige = 10
        tick_prestige(drift_world)
        assert drift_world.civilizations[0].prestige == 9

    def test_prestige_minimum_zero(self, drift_world):
        drift_world.civilizations[0].prestige = 0
        tick_prestige(drift_world)
        assert drift_world.civilizations[0].prestige == 0

    def test_prestige_trade_income_bonus(self, drift_world):
        drift_world.civilizations[0].prestige = 11  # after decay: 10 -> bonus = 2
        initial_treasury = drift_world.civilizations[0].treasury
        tick_prestige(drift_world)
        assert drift_world.civilizations[0].treasury == initial_treasury + 2


class TestCulturalWorksEnhancement:
    def test_cultural_work_boosts_prestige(self, drift_world):
        drift_world.civilizations[0].culture = 80
        initial_prestige = drift_world.civilizations[0].prestige
        from chronicler.simulation import phase_cultural_milestones
        phase_cultural_milestones(drift_world)
        assert drift_world.civilizations[0].prestige == initial_prestige + 2

    def test_cultural_work_boosts_asabiya(self, drift_world):
        drift_world.civilizations[0].culture = 80
        initial_region_asabiya = drift_world.regions[0].asabiya_state.asabiya
        from chronicler.simulation import phase_cultural_milestones
        phase_cultural_milestones(drift_world)
        # M55b D-policy: delta applied to region-level asabiya, not civ-level
        assert drift_world.regions[0].asabiya_state.asabiya == pytest.approx(initial_region_asabiya + 0.05)


class TestWorldGenCulture:
    def test_controlled_regions_get_cultural_identity(self):
        from chronicler.world_gen import generate_world
        world = generate_world(seed=42, num_civs=4)
        for region in world.regions:
            if region.controller is not None:
                assert region.cultural_identity == region.controller

    def test_uncontrolled_regions_have_no_identity(self):
        from chronicler.world_gen import generate_world
        world = generate_world(seed=42, num_civs=4)
        for region in world.regions:
            if region.controller is None:
                assert region.cultural_identity is None


class TestM16aPhaseIntegration:
    def test_prestige_runs_in_phase_production(self, drift_world):
        drift_world.civilizations[0].prestige = 10
        from chronicler.simulation import phase_production
        phase_production(drift_world)
        assert drift_world.civilizations[0].prestige == 9

    def test_value_drift_runs_in_consequences(self, drift_world):
        drift_world.civilizations[0].values = ["Trade", "Order"]
        drift_world.civilizations[1].values = ["Trade", "Order"]
        from chronicler.simulation import phase_consequences
        phase_consequences(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 4


from chronicler.models import Movement
from chronicler.movements import SCHISM_DIVERGENCE_THRESHOLD


class TestMovementDispositionEffects:
    def test_co_adopters_get_positive_drift(self, drift_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": 1},
        )
        drift_world.movements.append(m)
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 5

    def test_schism_co_adopters_get_negative_drift(self, drift_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": SCHISM_DIVERGENCE_THRESHOLD},
        )
        drift_world.movements.append(m)
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == -5

    def test_non_adopter_no_effect(self, drift_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0},
        )
        drift_world.movements.append(m)
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 0

    def test_multiple_movements_stack(self, drift_world):
        m1 = Movement(id="movement_0", origin_civ="CivA", origin_turn=0,
                       value_affinity="Trade", adherents={"CivA": 0, "CivB": 0})
        m2 = Movement(id="movement_1", origin_civ="CivA", origin_turn=0,
                       value_affinity="Order", adherents={"CivA": 0, "CivB": 0})
        drift_world.movements.extend([m1, m2])
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 10


def test_agent_snapshot_value_drift_sorts_value_keys_before_summing(drift_world, monkeypatch):
    import builtins
    from collections import Counter
    import chronicler.culture as culture

    observed_value_sort = []
    real_sorted = builtins.sorted

    def fake_profiles(_snapshot):
        return {
            0: Counter({"Trade": 2, "Order": 1}),
            1: Counter({"Order": 2, "Trade": 1}),
        }

    def tracking_sorted(iterable, *args, **kwargs):
        items = list(iterable)
        if set(items) == {"Trade", "Order"}:
            observed_value_sort.append(tuple(items))
        return real_sorted(items, *args, **kwargs)

    monkeypatch.setattr(culture, "compute_civ_cultural_profile", fake_profiles)
    monkeypatch.setattr(builtins, "sorted", tracking_sorted)

    apply_value_drift(drift_world, agent_snapshot=object())

    assert observed_value_sort, "Expected deterministic sorting of cultural profile keys"


from chronicler.tech import get_era_bonus


class TestEraBonus:
    def test_existing_stat_bonus(self):
        assert get_era_bonus(TechEra.IRON, "economy", default=0.0) == 10

    def test_multiplier_key(self):
        assert get_era_bonus(TechEra.IRON, "military_multiplier", default=1.0) == 1.3

    def test_missing_key_returns_default(self):
        assert get_era_bonus(TechEra.BRONZE, "culture_projection_range", default=1) == 1

    def test_fortification_multiplier(self):
        assert get_era_bonus(TechEra.MEDIEVAL, "fortification_multiplier", default=1.0) == 2.0


from chronicler.models import ActionType
from chronicler.action_engine import ActionEngine


class TestInvestCultureAction:
    def test_invest_culture_in_action_type_enum(self):
        assert hasattr(ActionType, "INVEST_CULTURE")

    def test_invest_culture_eligible_at_culture_60(self, drift_world):
        drift_world.civilizations[0].culture = 60
        drift_world.regions[0].adjacencies = ["R2"]
        drift_world.regions[1].adjacencies = ["R1"]
        drift_world.regions[1].cultural_identity = "CivB"
        engine = ActionEngine(drift_world)
        eligible = engine.get_eligible_actions(drift_world.civilizations[0])
        assert ActionType.INVEST_CULTURE in eligible

    def test_invest_culture_not_eligible_below_60(self, drift_world):
        drift_world.civilizations[0].culture = 59
        engine = ActionEngine(drift_world)
        eligible = engine.get_eligible_actions(drift_world.civilizations[0])
        assert ActionType.INVEST_CULTURE not in eligible

    def test_visionary_weights_invest_culture_highest(self, drift_world):
        drift_world.civilizations[0].culture = 60
        drift_world.civilizations[0].leader.trait = "visionary"
        drift_world.regions[0].adjacencies = ["R2"]
        drift_world.regions[1].adjacencies = ["R1"]
        drift_world.regions[1].cultural_identity = "CivB"
        engine = ActionEngine(drift_world)
        weights = engine.compute_weights(drift_world.civilizations[0])
        assert ActionType.INVEST_CULTURE in weights
        assert weights[ActionType.INVEST_CULTURE] > 0


from chronicler.culture import (
    resolve_invest_culture, PROPAGANDA_COST, PROPAGANDA_ACCELERATION,
    COUNTER_PROPAGANDA_COST,
)


@pytest.fixture
def propaganda_world():
    regions = [
        Region(name="Home", terrain="plains", carrying_capacity=50, resources="fertile",
               controller="CivA", cultural_identity="CivA", adjacencies=["Target"]),
        Region(name="Target", terrain="plains", carrying_capacity=50, resources="fertile",
               controller="CivB", cultural_identity="CivB", adjacencies=["Home"]),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=70,
            stability=50, treasury=20,
            leader=Leader(name="LA", trait="visionary", reign_start=0),
            domains=["trade"], values=["Trade"], regions=["Home"],
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=30,
            stability=50, treasury=20,
            leader=Leader(name="LB", trait="aggressive", reign_start=0),
            domains=["warfare"], values=["Honor"], regions=["Target"],
        ),
    ]
    return WorldState(
        name="test", seed=42, regions=regions, civilizations=civs,
        relationships={
            "CivA": {"CivB": Relationship()},
            "CivB": {"CivA": Relationship()},
        },
    )


class TestInvestCultureResolution:
    def test_propaganda_costs_treasury(self, propaganda_world):
        initial = propaganda_world.civilizations[0].treasury
        resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        assert propaganda_world.civilizations[0].treasury == initial - PROPAGANDA_COST

    def test_propaganda_accelerates_assimilation(self, propaganda_world):
        initial_fct = propaganda_world.regions[1].foreign_control_turns
        resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        expected = initial_fct + PROPAGANDA_ACCELERATION
        if propaganda_world.civilizations[1].treasury >= COUNTER_PROPAGANDA_COST:
            expected = initial_fct
        assert propaganda_world.regions[1].foreign_control_turns == expected

    def test_defender_counter_spend_deducts_treasury(self, propaganda_world):
        initial_def_treasury = propaganda_world.civilizations[1].treasury
        resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        assert propaganda_world.civilizations[1].treasury == initial_def_treasury - COUNTER_PROPAGANDA_COST

    def test_defender_no_counter_when_broke(self, propaganda_world):
        propaganda_world.civilizations[1].treasury = 0
        resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        assert propaganda_world.regions[1].foreign_control_turns == PROPAGANDA_ACCELERATION

    def test_cannot_target_own_cultural_region(self, propaganda_world):
        propaganda_world.regions[1].cultural_identity = "CivA"
        event = resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        assert propaganda_world.civilizations[0].treasury == 20

    def test_generates_named_event(self, propaganda_world):
        resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        assert any(
            ne.event_type == "propaganda_campaign"
            for ne in propaganda_world.named_events
        )


from chronicler.culture import check_cultural_victories


class TestCulturalVictories:
    def test_hegemony_when_culture_exceeds_all_others(self, drift_world):
        drift_world.civilizations[0].culture = 90
        drift_world.civilizations[1].culture = 10
        check_cultural_victories(drift_world)
        assert any(
            ne.event_type == "cultural_hegemony" and "CivA" in ne.actors
            for ne in drift_world.named_events
        )

    def test_no_hegemony_when_not_dominant(self, drift_world):
        drift_world.civilizations[0].culture = 50
        drift_world.civilizations[1].culture = 50
        check_cultural_victories(drift_world)
        assert not any(
            ne.event_type == "cultural_hegemony"
            for ne in drift_world.named_events
        )

    def test_hegemony_fire_once(self, drift_world):
        drift_world.civilizations[0].culture = 90
        drift_world.civilizations[1].culture = 10
        check_cultural_victories(drift_world)
        count = len(drift_world.named_events)
        check_cultural_victories(drift_world)
        assert len(drift_world.named_events) == count

    def test_universal_enlightenment(self, drift_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": 0},
        )
        drift_world.movements.append(m)
        check_cultural_victories(drift_world)
        assert any(
            ne.event_type == "universal_enlightenment"
            for ne in drift_world.named_events
        )

    def test_universal_enlightenment_fire_once(self, drift_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": 0},
        )
        drift_world.movements.append(m)
        check_cultural_victories(drift_world)
        count = len(drift_world.named_events)
        check_cultural_victories(drift_world)
        assert len(drift_world.named_events) == count


class TestM16cIntegration:
    def test_check_cultural_victories_runs_last_in_phase_10(self, drift_world):
        drift_world.civilizations[0].culture = 90
        drift_world.civilizations[1].culture = 10
        from chronicler.simulation import phase_consequences
        phase_consequences(drift_world)
        assert any(
            ne.event_type == "cultural_hegemony"
            for ne in drift_world.named_events
        )


class TestSnapshotChanges:
    def test_civ_snapshot_has_prestige(self):
        from chronicler.models import CivSnapshot
        snap = CivSnapshot(
            population=50, military=50, economy=50, culture=50, stability=50,
            treasury=10, asabiya=0.5, tech_era=TechEra.IRON, trait="cautious",
            regions=["R1"], leader_name="L", alive=True, prestige=10,
        )
        assert snap.prestige == 10


from chronicler.named_events import (
    generate_movement_name, generate_schism_name,
    generate_propaganda_name, generate_cultural_milestone_name,
)


class TestNameGenerators:
    def test_generate_movement_name_returns_string(self, drift_world):
        name = generate_movement_name(drift_world.civilizations[0], drift_world, seed=42)
        assert isinstance(name, str)
        assert len(name) > 0

    def test_generate_movement_name_deterministic(self, drift_world):
        a = generate_movement_name(drift_world.civilizations[0], drift_world, seed=42)
        b = generate_movement_name(drift_world.civilizations[0], drift_world, seed=42)
        assert a == b

    def test_generate_schism_name_returns_string(self, drift_world):
        name = generate_schism_name(["CivA", "CivB"], drift_world, seed=42)
        assert isinstance(name, str)
        assert len(name) > 0

    def test_generate_propaganda_name_returns_string(self, drift_world):
        name = generate_propaganda_name(
            drift_world.civilizations[0], drift_world.regions[0], drift_world, seed=42,
        )
        assert isinstance(name, str)
        assert len(name) > 0

    def test_generate_cultural_milestone_name_returns_string(self, drift_world):
        name = generate_cultural_milestone_name(
            drift_world.civilizations[0], "hegemony", drift_world, seed=42,
        )
        assert isinstance(name, str)
        assert len(name) > 0


from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world


class TestM16EndToEnd:
    def test_5_turn_simulation_with_culture(self):
        world = generate_world(seed=42, num_civs=4)

        def dummy_narrator(world, events):
            return "Turn narration."

        for _ in range(5):
            from chronicler.action_engine import ActionEngine
            engine = ActionEngine(world)
            run_turn(
                world,
                action_selector=lambda civ, w: engine.select_action(civ, seed=w.seed + w.turn),
                narrator=dummy_narrator,
                seed=world.seed,
            )

        assert world.turn == 5
        assert all(r.cultural_identity is not None for r in world.regions if r.controller is not None)

    def test_31_turn_simulation_produces_movement(self):
        world = generate_world(seed=42, num_civs=4)

        def dummy_narrator(world, events):
            return "Turn narration."

        for _ in range(31):
            from chronicler.action_engine import ActionEngine
            engine = ActionEngine(world)
            run_turn(
                world,
                action_selector=lambda civ, w: engine.select_action(civ, seed=w.seed + w.turn),
                narrator=dummy_narrator,
                seed=world.seed,
            )

        assert world.turn == 31
        assert len(world.movements) >= 1, "At least one movement should emerge by turn 31"
