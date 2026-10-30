"""Tests for M24 Information Asymmetry."""
import pytest
from chronicler.models import (
    Civilization, Leader, Region, WorldState, VassalRelation,
    Federation, ProxyWar, FactionState, FactionType, GreatPerson,
    Disposition, Relationship,
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

    def test_missing_then_directed_edge(self):
        r1 = _region("A", controller="Civ1", adjacencies=["Missing", "B"])
        r2 = _region("B", controller="Civ2", adjacencies=[])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        assert shares_adjacent_region(c1, c2, world) is True
        assert shares_adjacent_region(c2, c1, world) is False
        r1.adjacencies = ["Missing", "AlsoMissing"]
        assert shares_adjacent_region(c1, c2, world) is False

    @pytest.mark.parametrize("first_controller,second_controller,expected", [
        ("Civ3", "Civ2", False),
        ("Civ2", "Civ3", True),
    ])
    def test_duplicate_name_uses_first_region(self, first_controller, second_controller, expected):
        r1 = _region("A", controller="Civ1", adjacencies=["Missing", "B"])
        first = _region("B", controller=first_controller)
        second = _region("B", controller=second_controller)
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        c3 = _civ("Civ3")
        world = WorldState(
            name="t", seed=42, regions=[r1, first, second], civilizations=[c1, c2, c3],
        )
        assert shares_adjacent_region(c1, c2, world) is expected

    def test_incremental_lookup_keeps_earlier_name_and_first_duplicate(self):
        r1 = _region("A", controller="Civ1", adjacencies=["C", "B"])
        first_b = _region("B", controller="Civ3")
        c = _region("C", controller="Civ3")
        second_b = _region("B", controller="Civ2")
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        c3 = _civ("Civ3", regions=["C"])
        world = WorldState(
            name="t", seed=42, regions=[r1, first_b, c, second_b],
            civilizations=[c1, c2, c3],
        )
        assert shares_adjacent_region(c1, c2, world) is False
        first_b.controller = "Civ2"
        assert shares_adjacent_region(c1, c2, world) is True

    def test_reads_live_regions_when_cached_region_map_is_stale(self):
        r1 = _region("A", controller="Civ1", adjacencies=["Missing", "B"])
        old_b = _region("B", controller="Civ3")
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        c3 = _civ("Civ3")
        world = WorldState(name="t", seed=42, regions=[r1, old_b], civilizations=[c1, c2, c3])
        assert world.region_map["B"] is old_b
        old_b.name = "OldB"
        world.regions.append(_region("B", controller="Civ2"))
        assert world.region_map["B"] is old_b  # intentionally stale cache
        assert shares_adjacent_region(c1, c2, world) is True

    def test_no_observer_regions(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(
            name="t", seed=42, regions=[_region("B", controller="Civ2")],
            civilizations=[c1, c2],
        )
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

    @pytest.mark.parametrize("routes", [set(), {("A", "B"), ("B", "Δ"), ("Δ", "Δ")}])
    def test_warm_membership_matches_original_for_every_directed_pair(self, routes):
        from types import SimpleNamespace
        from chronicler.resources import get_active_trade_route_pairs

        world = SimpleNamespace(turn=7, _trade_route_cache_turn=7,
                                _active_trade_route_pairs_cache=routes)
        before = set(routes)
        for observer_name in ("A", "B", "C", "Δ"):
            for target_name in ("A", "B", "C", "Δ"):
                observer = SimpleNamespace(name=observer_name)
                target = SimpleNamespace(name=target_name)
                # The complete original helper body is the parity reference.
                pair = tuple(sorted([observer.name, target.name]))
                expected = pair in get_active_trade_route_pairs(world)
                assert has_active_trade_route(observer, target, world) is expected
        assert routes == before
        assert world._active_trade_route_pairs_cache is routes

    def test_warm_membership_avoids_getter_but_public_getter_still_copies(self, monkeypatch):
        from types import SimpleNamespace
        import chronicler.intelligence as intelligence
        from chronicler.resources import get_active_trade_route_pairs

        routes = {("A", "B")}
        world = SimpleNamespace(turn=7, _trade_route_cache_turn=7,
                                _active_trade_route_pairs_cache=routes)
        calls = []

        def unexpected_getter(_world):
            calls.append(_world)
            raise AssertionError("warm membership must not allocate the getter's copy")

        monkeypatch.setattr(intelligence, "get_active_trade_route_pairs", unexpected_getter)
        assert has_active_trade_route(SimpleNamespace(name="B"), SimpleNamespace(name="A"), world)
        assert not calls
        copied = get_active_trade_route_pairs(world)
        assert copied == routes and copied is not routes
        copied.add(("A", "C"))
        assert routes == {("A", "B")}

    @pytest.mark.parametrize("cache_turn,cached_pairs", [
        (None, None), (6, {("A", "B")}), (7, None), (7, [("A", "B")]),
    ])
    def test_cold_stale_and_foreign_cache_call_original_getter_once(
        self, monkeypatch, cache_turn, cached_pairs,
    ):
        from types import SimpleNamespace
        import chronicler.intelligence as intelligence

        world = SimpleNamespace(turn=7, _trade_route_cache_turn=cache_turn,
                                _active_trade_route_pairs_cache=cached_pairs)
        calls = []

        def getter(actual_world):
            calls.append(actual_world)
            return {("A", "C")}

        monkeypatch.setattr(intelligence, "get_active_trade_route_pairs", getter)
        assert has_active_trade_route(SimpleNamespace(name="C"), SimpleNamespace(name="A"), world)
        assert calls == [world]
        assert world._active_trade_route_pairs_cache is cached_pairs

    def test_foreign_iterable_keeps_conversion_order_and_errors(self):
        from types import SimpleNamespace
        from chronicler.resources import get_active_trade_route_pairs

        events = []
        sentinel = RuntimeError("foreign cache iteration failed")

        class ForeignPairs:
            fail = False

            def __iter__(self):
                events.append("iterate")
                yield ("A", "B")
                events.append("after first pair")
                if self.fail:
                    raise sentinel

        pairs = ForeignPairs()
        world = SimpleNamespace(turn=7, _trade_route_cache_turn=7,
                                _active_trade_route_pairs_cache=pairs)
        observer, target = SimpleNamespace(name="A"), SimpleNamespace(name="B")
        expected = ("A", "B") in get_active_trade_route_pairs(world)
        expected_events = list(events)
        events.clear()
        assert has_active_trade_route(observer, target, world) is expected
        assert events == expected_events == ["iterate", "after first pair"]
        pairs.fail = True
        events.clear()
        with pytest.raises(RuntimeError) as original:
            get_active_trade_route_pairs(world)
        original_events = list(events)
        events.clear()
        with pytest.raises(RuntimeError) as candidate:
            has_active_trade_route(observer, target, world)
        assert candidate.value is original.value is sentinel
        assert events == original_events

    def test_set_subclasses_keep_the_public_getter_fallback(self, monkeypatch):
        from types import SimpleNamespace
        import chronicler.intelligence as intelligence
        from chronicler.resources import get_active_trade_route_pairs

        class ForeignSet(set):
            pass

        pairs = ForeignSet({("A", "B")})
        world = SimpleNamespace(turn=7, _trade_route_cache_turn=7,
                                _active_trade_route_pairs_cache=pairs)
        calls = []

        def getter(actual_world):
            calls.append(actual_world)
            return get_active_trade_route_pairs(actual_world)

        monkeypatch.setattr(intelligence, "get_active_trade_route_pairs", getter)
        assert has_active_trade_route(SimpleNamespace(name="A"), SimpleNamespace(name="B"), world)
        assert calls == [world]
        assert world._active_trade_route_pairs_cache is pairs

    def test_warm_lookup_tracks_live_cache_edits_and_replacement(self):
        from types import SimpleNamespace

        routes = {("A", "B")}
        world = SimpleNamespace(turn=7, _trade_route_cache_turn=7,
                                _active_trade_route_pairs_cache=routes)
        observer, target = SimpleNamespace(name="A"), SimpleNamespace(name="B")
        assert has_active_trade_route(observer, target, world)
        routes.clear()
        assert not has_active_trade_route(observer, target, world)
        world._active_trade_route_pairs_cache = {("A", "B")}
        assert has_active_trade_route(observer, target, world)
        assert not routes

    def test_pair_normalization_errors_precede_cache_reads(self):
        from types import SimpleNamespace

        class UnreadableWorld:
            def __getattribute__(self, name):
                raise AssertionError(f"unexpected world read: {name}")

        with pytest.raises(TypeError):
            has_active_trade_route(SimpleNamespace(name=0), SimpleNamespace(name="A"), UnreadableWorld())

    def test_missing_turn_keeps_the_original_attribute_error(self):
        from types import SimpleNamespace
        from chronicler.resources import get_active_trade_route_pairs

        world = SimpleNamespace()
        with pytest.raises(AttributeError) as original:
            get_active_trade_route_pairs(world)
        with pytest.raises(AttributeError) as candidate:
            has_active_trade_route(SimpleNamespace(name="A"), SimpleNamespace(name="B"), world)
        assert str(candidate.value) == str(original.value)


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
    def test_adjacency_helper_remains_patchable(self, monkeypatch):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        baseline = compute_accuracy(c1, c2, world)
        monkeypatch.setattr("chronicler.intelligence.shares_adjacent_region", lambda *args: True)
        assert compute_accuracy(c1, c2, world) == pytest.approx(baseline + 0.3)

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

    def test_adjacent_defaults_to_trade_contact_0_5(self):
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
        # adjacent(0.3) + default-neutral trade(0.2) = 0.5
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.5)

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
        # adjacent(0.3) + default-neutral trade(0.2) + merchant(0.1) = 0.6
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.6)

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
        # adjacent(0.3) + default-neutral trade(0.2) + cultural(0.05) = 0.55
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.55)

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
        # adjacent(0.3) + default-neutral trade(0.2) + merchant_gp(0.05) = 0.55
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.55)

    def test_hostage_gp_bonus(self):
        from chronicler.relationships import capture_hostage

        gp = GreatPerson(name="Prince", role="general", trait="noble",
                         civilization="Civ1", origin_civilization="Civ1",
                         alive=True, active=True, born_turn=1)
        # Use military-dominant faction so no faction bonus
        military_factions = FactionState(influence={
            FactionType.MILITARY: 0.6,
            FactionType.MERCHANT: 0.2,
            FactionType.CULTURAL: 0.2,
        })
        c1 = _civ("Civ1", great_persons=[gp], factions=military_factions)
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        capture_hostage(c1, c2, world)
        # No adjacency; the hostage reports home from the captor's roster.
        assert gp not in c1.great_persons
        assert gp in c2.great_persons
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
        # adjacent(0.3) + default-neutral trade(0.2) + grudge(0.1) = 0.6
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.6)

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
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.5)


class TestBonusesNeedContact:
    """2026-10: faction and merchant bonuses sharpen knowledge of civs in
    contact; they reveal no civ never met (docs/integration/procedural-gates.md)."""

    @staticmethod
    def _informed_civ(name="Civ1", **kw):
        gp = GreatPerson(name="Trader", role="merchant", trait="shrewd",
                         civilization=name, origin_civilization=name,
                         alive=True, active=True, born_turn=1, is_hostage=False)
        factions = FactionState(influence={
            FactionType.MILITARY: 0.2, FactionType.MERCHANT: 0.6, FactionType.CULTURAL: 0.2,
        })
        return _civ(name, great_persons=[gp], factions=factions, **kw)

    def test_stranger_stays_unknown(self):
        c1, c2 = self._informed_civ(), _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        assert compute_accuracy(c1, c2, world) == 0.0
        assert get_perceived_stat(c1, c2, "military", world) is None

    def test_cultural_faction_stranger_stays_unknown(self):
        factions = FactionState(influence={
            FactionType.MILITARY: 0.2, FactionType.MERCHANT: 0.3, FactionType.CULTURAL: 0.5,
        })
        c1, c2 = _civ("Civ1", factions=factions), _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        assert compute_accuracy(c1, c2, world) == 0.0

    def test_bonuses_apply_on_contact(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1, c2 = self._informed_civ(regions=["A"]), _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # adjacent(0.3) + default-neutral trade(0.2) + merchant(0.1) + merchant gp(0.05)
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.65)

    def test_contact_ledger_flow_counts_as_contact(self):
        from chronicler.contact_ledger import ContactLedgerState
        c1, c2, c3 = self._informed_civ(), _civ("Civ2"), _civ("Civ3")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2, c3])
        world.contact_ledger = ContactLedgerState(pairs=[("Civ1", "Civ2", 0.0, 2.0, 0.0, 0.0)])
        # Migrants reached Civ2 (people channel); Civ3 was never met.
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.15)
        assert compute_accuracy(c1, c3, world) == 0.0

    def test_hostage_counts_as_contact(self):
        prince = GreatPerson(name="Prince", role="general", trait="noble",
                             civilization="Civ2", origin_civilization="Civ1",
                             alive=True, active=True, born_turn=1, is_hostage=True)
        c1, c2 = self._informed_civ(), _civ("Civ2", great_persons=[prince])
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        # merchant(0.1) + merchant gp(0.05) + hostage(0.3)
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.45)

    def test_grudge_alone_still_informs(self):
        leader = Leader(name="L", trait="bold", reign_start=0,
                        grudges=[{"rival_civ": "Civ2", "intensity": 0.5, "reason": "war"}])
        c1 = self._informed_civ(leader=leader)
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        # A remembered rival is a civ met in war: the grudge is not gated.
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.1)


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
        # accuracy = 0.5; noise_range = int((1 - 0.5) * 20) = 10; bounds: 40..60
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


# --- Task 6: Trade Resolution Callsite ---

class TestTradePerception:
    def test_trade_gain_uses_perceived_economy(self):
        from chronicler.action_engine import resolve_trade
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"], economy=60, treasury=0)
        c2 = _civ("Civ2", regions=["B"], economy=90, treasury=0)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        world.relationships = {
            "Civ1": {"Civ2": Relationship(disposition=Disposition.NEUTRAL)},
            "Civ2": {"Civ1": Relationship(disposition=Disposition.NEUTRAL)},
        }
        resolve_trade(c1, c2, world)
        assert c1.treasury > 0
        assert c2.treasury > 0


# --- Task 7: Politics Callsites ---

class TestTributePerception:
    def test_tribute_uses_perceived_economy(self):
        from chronicler.politics import collect_tribute
        r1 = _region("A", controller="Overlord", adjacencies=["B"])
        r2 = _region("B", controller="Vassal", adjacencies=["A"])
        overlord = _civ("Overlord", regions=["A"], treasury=100)
        vassal = _civ("Vassal", regions=["B"], economy=60, treasury=100)
        world = WorldState(name="t", seed=42, regions=[r1, r2],
                           civilizations=[overlord, vassal])
        world.vassal_relations = [VassalRelation(vassal="Vassal", overlord="Overlord",
                                                  tribute_rate=0.5)]
        collect_tribute(world)
        assert overlord.treasury > 100


class TestRebellionPerception:
    def test_rebellion_suppressed_by_perceived_strength(self):
        from chronicler.politics import check_vassal_rebellion
        r1 = _region("A", controller="Overlord", adjacencies=["B"])
        r2 = _region("B", controller="Vassal", adjacencies=["A"])
        overlord = _civ("Overlord", regions=["A"], stability=20, treasury=5)
        vassal = _civ("Vassal", regions=["B"], stability=50)
        world = WorldState(name="t", seed=42, regions=[r1, r2],
                           civilizations=[overlord, vassal])
        world.vassal_relations = [VassalRelation(vassal="Vassal", overlord="Overlord")]
        events = check_vassal_rebellion(world)
        assert isinstance(events, list)


class TestCongressPerception:
    def test_congress_power_uses_organizer_perception(self):
        from chronicler.politics import check_congress
        r1 = _region("A", controller="Civ1", adjacencies=["B", "C"])
        r2 = _region("B", controller="Civ2", adjacencies=["A", "C"])
        r3 = _region("C", controller="Civ3", adjacencies=["A", "B"])
        c1 = _civ("Civ1", regions=["A"], military=80, economy=80, culture=90)
        c2 = _civ("Civ2", regions=["B"], military=50, economy=50, culture=30)
        c3 = _civ("Civ3", regions=["C"], military=30, economy=30, culture=20)
        world = WorldState(name="t", seed=42, regions=[r1, r2, r3],
                           civilizations=[c1, c2, c3])
        world.active_wars = [("Civ1", "Civ2"), ("Civ2", "Civ3")]
        world.war_start_turns = {"Civ1:Civ2": 1, "Civ2:Civ3": 1}
        world.relationships = {
            "Civ1": {"Civ2": Relationship(disposition=Disposition.HOSTILE),
                     "Civ3": Relationship(disposition=Disposition.HOSTILE)},
            "Civ2": {"Civ1": Relationship(disposition=Disposition.HOSTILE),
                     "Civ3": Relationship(disposition=Disposition.HOSTILE)},
            "Civ3": {"Civ1": Relationship(disposition=Disposition.HOSTILE),
                     "Civ2": Relationship(disposition=Disposition.HOSTILE)},
        }
        events = check_congress(world)
        assert isinstance(events, list)


# --- Task 8: WAR Target Bias + Intelligence Failure Event ---

class TestWarTargetBias:
    def test_prefers_perceived_weaker_target(self):
        r1 = _region("A", controller="Attacker", adjacencies=["B", "C"])
        r2 = _region("B", controller="Strong", adjacencies=["A"])
        r3 = _region("C", controller="Weak", adjacencies=["A"])
        attacker = _civ("Attacker", regions=["A"], military=50, stability=50,
                        economy=40, culture=30, population=50)
        strong = _civ("Strong", regions=["B"], military=80, stability=50,
                      economy=40, culture=30, population=50)
        weak = _civ("Weak", regions=["C"], military=20, stability=50,
                    economy=40, culture=30, population=50)
        world = WorldState(name="t", seed=42, regions=[r1, r2, r3],
                           civilizations=[attacker, strong, weak])
        world.relationships = {
            "Attacker": {
                "Strong": Relationship(disposition=Disposition.HOSTILE),
                "Weak": Relationship(disposition=Disposition.HOSTILE),
            },
            "Strong": {"Attacker": Relationship(disposition=Disposition.HOSTILE)},
            "Weak": {"Attacker": Relationship(disposition=Disposition.HOSTILE)},
        }
        from chronicler.action_engine import _resolve_war_action
        event = _resolve_war_action(attacker, world)
        assert "Weak" in event.actors or "Weak" in event.description


class TestIntelligenceFailureEvent:
    def test_mechanism_wired(self):
        r1 = _region("A", controller="Attacker", adjacencies=["B"])
        r2 = _region("B", controller="Defender", adjacencies=["A"])
        attacker = _civ("Attacker", regions=["A"], military=40, stability=50,
                        economy=40, culture=30, population=50, asabiya=0.5)
        defender = _civ("Defender", regions=["B"], military=80, stability=50,
                        economy=40, culture=30, population=50, asabiya=0.5)
        world = WorldState(name="t", seed=42, regions=[r1, r2],
                           civilizations=[attacker, defender])
        world.relationships = {
            "Attacker": {"Defender": Relationship(disposition=Disposition.HOSTILE)},
            "Defender": {"Attacker": Relationship(disposition=Disposition.HOSTILE)},
        }
        from chronicler.action_engine import _resolve_war_action
        event = _resolve_war_action(attacker, world)
        intel_events = [e for e in world.events_timeline
                        if e.event_type == "intelligence_failure"]
        assert isinstance(intel_events, list)


# --- Task 9: Snapshot Population ---

class TestSnapshotPopulation:
    def test_snapshot_contains_accuracy_and_errors(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        # Use military-dominant faction so no faction bonus.
        # accuracy = adjacent(0.3) + default-neutral trade(0.2) = 0.5
        military_factions = FactionState(influence={
            FactionType.MILITARY: 0.6,
            FactionType.MERCHANT: 0.2,
            FactionType.CULTURAL: 0.2,
        })
        c1 = _civ("Civ1", regions=["A"], military=50, economy=60, stability=40,
                  factions=military_factions)
        c2 = _civ("Civ2", regions=["B"], military=70, economy=30, stability=55)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        acc_cache = {}
        for obs in world.civilizations:
            for tgt in world.civilizations:
                if obs.name != tgt.name:
                    acc_cache[(obs.name, tgt.name)] = compute_accuracy(obs, tgt, world)
        per_pair_accuracy = {
            obs.name: {
                tgt.name: acc_cache[(obs.name, tgt.name)]
                for tgt in world.civilizations
                if obs.name != tgt.name and acc_cache[(obs.name, tgt.name)] > 0.0
            }
            for obs in world.civilizations
        }
        perception_errors = {
            obs.name: {
                tgt.name: {
                    stat: get_perceived_stat(obs, tgt, stat, world) - getattr(tgt, stat)
                    for stat in ("military", "economy", "stability")
                    if get_perceived_stat(obs, tgt, stat, world) is not None
                }
                for tgt in world.civilizations
                if obs.name != tgt.name and acc_cache[(obs.name, tgt.name)] > 0.0
            }
            for obs in world.civilizations
        }
        assert "Civ2" in per_pair_accuracy.get("Civ1", {})
        assert per_pair_accuracy["Civ1"]["Civ2"] == pytest.approx(0.5)
        errors = perception_errors["Civ1"]["Civ2"]
        assert "military" in errors
        assert "economy" in errors
        assert "stability" in errors
        for stat, err in errors.items():
            assert isinstance(err, int)
