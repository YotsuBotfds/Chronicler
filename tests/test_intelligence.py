"""Tests for M24 Information Asymmetry."""
import pytest
from chronicler.models import (
    Civilization, Leader, Region, WorldState, VassalRelation,
    Federation, ProxyWar, FactionState, FactionType, GreatPerson,
)
from chronicler.intelligence import (
    shares_adjacent_region, has_active_trade_route, in_same_federation,
    is_vassal_of, at_war, compute_accuracy, get_perceived_stat,
    emit_intelligence_failure,
)


def _leader():
    return Leader(name="L", trait="bold", reign_start=0)


def _civ(name, **kw):
    defaults = dict(population=50, military=30, economy=40, culture=30,
                    stability=50, leader=_leader(), regions=[])
    defaults.update(kw)
    return Civilization(name=name, **defaults)


def _region(name, controller=None, adjacencies=None):
    return Region(name=name, terrain="plains", carrying_capacity=50,
                  resources="fertile", adjacencies=adjacencies or [],
                  controller=controller)


class TestSharesAdjacentRegion:
    def test_adjacent_returns_true(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        assert shares_adjacent_region(c1, c2, world) is True

    def test_not_adjacent_returns_false(self):
        r1 = _region("A", controller="Civ1", adjacencies=[])
        r2 = _region("B", controller="Civ2", adjacencies=[])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        assert shares_adjacent_region(c1, c2, world) is False


class TestHasActiveTradeRoute:
    def test_trade_route_exists(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        from chronicler.models import Disposition, Relationship
        world.relationships = {
            "Civ1": {"Civ2": Relationship(disposition=Disposition.NEUTRAL)},
            "Civ2": {"Civ1": Relationship(disposition=Disposition.NEUTRAL)},
        }
        assert has_active_trade_route(c1, c2, world) is True

    def test_no_trade_when_embargoed(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        from chronicler.models import Disposition, Relationship
        world.relationships = {
            "Civ1": {"Civ2": Relationship(disposition=Disposition.NEUTRAL)},
            "Civ2": {"Civ1": Relationship(disposition=Disposition.NEUTRAL)},
        }
        world.embargoes = [("Civ1", "Civ2")]
        assert has_active_trade_route(c1, c2, world) is False


class TestInSameFederation:
    def test_same_federation(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.federations = [Federation(name="Alliance",
                                        members=["Civ1", "Civ2"], founded_turn=1)]
        assert in_same_federation(c1, c2, world) is True

    def test_different_federations(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.federations = [
            Federation(name="A", members=["Civ1"], founded_turn=1),
            Federation(name="B", members=["Civ2"], founded_turn=1),
        ]
        assert in_same_federation(c1, c2, world) is False


class TestIsVassalOf:
    def test_vassal_relation_exists(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.vassal_relations = [VassalRelation(vassal="Civ1", overlord="Civ2")]
        assert is_vassal_of(c1, c2, world) is True

    def test_no_vassal_relation(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        assert is_vassal_of(c1, c2, world) is False


class TestAtWar:
    def test_direct_war(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.active_wars = [("Civ1", "Civ2")]
        assert at_war(c1, c2, world) is True

    def test_proxy_war(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.proxy_wars = [ProxyWar(sponsor="Civ1", target_civ="Civ2", target_region="X")]
        assert at_war(c1, c2, world) is True

    def test_no_war(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        assert at_war(c1, c2, world) is False


# --- Task 3: compute_accuracy tests ---

class TestComputeAccuracy:
    def test_self_accuracy_is_1(self):
        c = _civ("Civ1")
        world = WorldState(name="t", seed=42, civilizations=[c])
        assert compute_accuracy(c, c, world) == 1.0

    def test_zero_contact_returns_0(self):
        # Use military-dominant faction so no faction bonus is applied
        military_factions = FactionState(influence={
            FactionType.MILITARY: 0.6,
            FactionType.MERCHANT: 0.2,
            FactionType.CULTURAL: 0.2,
        })
        c1 = _civ("Civ1", factions=military_factions)
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        assert compute_accuracy(c1, c2, world) == 0.0

    def test_adjacent_gives_0_3(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        # Use military-dominant faction so no faction bonus
        military_factions = FactionState(influence={
            FactionType.MILITARY: 0.6,
            FactionType.MERCHANT: 0.2,
            FactionType.CULTURAL: 0.2,
        })
        c1 = _civ("Civ1", regions=["A"], factions=military_factions)
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.3)

    def test_sources_stack_and_cap_at_1(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        from chronicler.models import Disposition, Relationship
        world.relationships = {
            "Civ1": {"Civ2": Relationship(disposition=Disposition.NEUTRAL)},
            "Civ2": {"Civ1": Relationship(disposition=Disposition.NEUTRAL)},
        }
        world.federations = [Federation(name="Alliance", members=["Civ1", "Civ2"], founded_turn=1)]
        world.active_wars = [("Civ1", "Civ2")]
        # adjacent(0.3) + trade(0.2) + federation(0.4) + war(0.3) = 1.2 -> capped at 1.0
        assert compute_accuracy(c1, c2, world) == 1.0

    def test_merchant_faction_bonus(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        c1.factions = FactionState(influence={
            FactionType.MILITARY: 0.2,
            FactionType.MERCHANT: 0.6,
            FactionType.CULTURAL: 0.2,
        })
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1.regions = ["A"]
        c2.regions = ["B"]
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # adjacent(0.3) + merchant(0.1) = 0.4
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.4)

    def test_cultural_faction_bonus(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        c1.factions = FactionState(influence={
            FactionType.MILITARY: 0.2,
            FactionType.MERCHANT: 0.3,
            FactionType.CULTURAL: 0.5,
        })
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1.regions = ["A"]
        c2.regions = ["B"]
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # adjacent(0.3) + cultural(0.05) = 0.35
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.35)

    def test_merchant_gp_bonus(self):
        gp = GreatPerson(name="Trader", role="merchant", trait="shrewd",
                         civilization="Civ1", origin_civilization="Civ1",
                         alive=True, active=True, born_turn=1, is_hostage=False)
        # Use military-dominant faction so no faction bonus
        military_factions = FactionState(influence={
            FactionType.MILITARY: 0.6,
            FactionType.MERCHANT: 0.2,
            FactionType.CULTURAL: 0.2,
        })
        c1 = _civ("Civ1", great_persons=[gp], factions=military_factions)
        c2 = _civ("Civ2")
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1.regions = ["A"]
        c2.regions = ["B"]
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # adjacent(0.3) + merchant_gp(0.05) = 0.35
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.35)

    def test_hostage_gp_bonus(self):
        gp = GreatPerson(name="Prince", role="hostage", trait="noble",
                         civilization="Civ2", origin_civilization="Civ2",
                         alive=True, active=True, born_turn=1, is_hostage=True)
        # Use military-dominant faction so no faction bonus
        military_factions = FactionState(influence={
            FactionType.MILITARY: 0.6,
            FactionType.MERCHANT: 0.2,
            FactionType.CULTURAL: 0.2,
        })
        c1 = _civ("Civ1", great_persons=[gp], factions=military_factions)
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        # no adjacency, just hostage(0.3)
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.3)

    def test_grudge_bonus(self):
        leader = Leader(name="L", trait="bold", reign_start=0,
                        grudges=[{"rival_civ": "Civ2", "intensity": 0.5, "reason": "war"}])
        # Use military-dominant faction so no faction bonus
        military_factions = FactionState(influence={
            FactionType.MILITARY: 0.6,
            FactionType.MERCHANT: 0.2,
            FactionType.CULTURAL: 0.2,
        })
        c1 = _civ("Civ1", leader=leader, factions=military_factions)
        c2 = _civ("Civ2")
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1.regions = ["A"]
        c2.regions = ["B"]
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # adjacent(0.3) + grudge(0.1) = 0.4
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.4)

    def test_grudge_below_threshold_no_bonus(self):
        leader = Leader(name="L", trait="bold", reign_start=0,
                        grudges=[{"rival_civ": "Civ2", "intensity": 0.2, "reason": "war"}])
        # Use military-dominant faction so no faction bonus
        military_factions = FactionState(influence={
            FactionType.MILITARY: 0.6,
            FactionType.MERCHANT: 0.2,
            FactionType.CULTURAL: 0.2,
        })
        c1 = _civ("Civ1", leader=leader, factions=military_factions)
        c2 = _civ("Civ2")
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1.regions = ["A"]
        c2.regions = ["B"]
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # adjacent(0.3) only — grudge intensity 0.2 < threshold 0.3
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.3)


# --- Task 4: get_perceived_stat tests ---

class TestGetPerceivedStat:
    def test_none_for_unknown_civ(self):
        # Use military-dominant faction so no faction bonus applies (accuracy stays 0.0)
        military_factions = FactionState(influence={
            FactionType.MILITARY: 0.6,
            FactionType.MERCHANT: 0.2,
            FactionType.CULTURAL: 0.2,
        })
        c1 = _civ("Civ1", factions=military_factions)
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        assert get_perceived_stat(c1, c2, "military", world) is None

    def test_self_returns_exact(self):
        c = _civ("Civ1", military=55)
        world = WorldState(name="t", seed=42, civilizations=[c])
        assert get_perceived_stat(c, c, "military", world) == 55

    def test_perfect_accuracy_returns_exact(self):
        c1 = _civ("Civ1", military=60)
        c2 = _civ("Civ2", military=60)
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        # vassal + adjacent + federation → accuracy >= 1.0
        world.vassal_relations = [VassalRelation(vassal="Civ1", overlord="Civ2")]
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        world.regions = [r1, r2]
        world.federations = [Federation(name="F", members=["Civ1", "Civ2"], founded_turn=1)]
        assert get_perceived_stat(c1, c2, "military", world) == 60

    def test_deterministic_same_inputs(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"], military=50)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        result1 = get_perceived_stat(c1, c2, "military", world)
        result2 = get_perceived_stat(c1, c2, "military", world)
        assert result1 == result2

    def test_noise_within_bounds(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"], military=50)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # accuracy = 0.3; noise_range = int((1 - 0.3) * 20) = 14; bounds: 36..64
        perceived = get_perceived_stat(c1, c2, "military", world)
        assert perceived is not None
        assert 36 <= perceived <= 64

    def test_clamp_to_0_100(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"], military=5)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        perceived = get_perceived_stat(c1, c2, "military", world)
        assert perceived is not None
        assert 0 <= perceived <= 100

    def test_different_stats_different_noise(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"], military=50, economy=50)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        mil = get_perceived_stat(c1, c2, "military", world)
        eco = get_perceived_stat(c1, c2, "economy", world)
        # Different stat seeds → likely different noise values
        # (They could coincidentally be equal, but with hash-based RNG, very unlikely)
        # We just verify both are in range
        assert mil is not None and 0 <= mil <= 100
        assert eco is not None and 0 <= eco <= 100


# --- Task 5: emit_intelligence_failure tests ---

class TestEmitIntelligenceFailure:
    def test_emits_event(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, turn=10, civilizations=[c1, c2])
        event = emit_intelligence_failure(c1, c2, perceived_mil=30, actual_mil=60, world=world)
        assert event.event_type == "intelligence_failure"
        assert event.importance == 7
        assert "Civ1" in event.actors
        assert "Civ2" in event.actors
        assert event.turn == 10

    def test_event_description_includes_gap(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, turn=5, civilizations=[c1, c2])
        event = emit_intelligence_failure(c1, c2, perceived_mil=25, actual_mil=75, world=world)
        assert "25" in event.description
        assert "75" in event.description
