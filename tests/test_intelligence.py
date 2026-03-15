"""Tests for M24 Information Asymmetry."""
import pytest
from chronicler.models import (
    Civilization, Leader, Region, WorldState, VassalRelation,
    Federation, ProxyWar, FactionState, FactionType,
)
from chronicler.intelligence import (
    shares_adjacent_region, has_active_trade_route, in_same_federation,
    is_vassal_of, at_war,
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
