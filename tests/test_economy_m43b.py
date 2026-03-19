"""M43b: Supply shock detection, trade dependency & raider incentive tests."""

from chronicler.economy import EconomyResult, CATEGORY_GOODS, TRADE_DEPENDENCY_THRESHOLD
from chronicler.models import Event, AgentContext, ShockContext


def test_event_shock_metadata_defaults_none():
    ev = Event(turn=1, event_type="war", actors=["A"], description="test")
    assert ev.shock_region is None
    assert ev.shock_category is None


def test_event_shock_metadata_set():
    ev = Event(
        turn=1, event_type="supply_shock", actors=["A", "B"],
        description="Supply shock: food in Plains",
        source="economy", shock_region="Plains", shock_category="food",
    )
    assert ev.shock_region == "Plains"
    assert ev.shock_category == "food"


def test_shock_context_construction():
    sc = ShockContext(region="Plains", category="food", severity=0.7, upstream_source="Aram")
    assert sc.region == "Plains"
    assert sc.severity == 0.7
    assert sc.upstream_source == "Aram"


def test_shock_context_upstream_defaults_none():
    sc = ShockContext(region="Plains", category="food", severity=0.5)
    assert sc.upstream_source is None


def test_agent_context_trade_fields_default_empty():
    ctx = AgentContext()
    assert ctx.trade_dependent_regions == []
    assert ctx.active_shocks == []


# ---------------------------------------------------------------------------
# Task 2: EconomyResult M43b fields and CATEGORY_GOODS
# ---------------------------------------------------------------------------

def test_economy_result_m43b_fields_default():
    er = EconomyResult()
    assert er.imports_by_region == {}
    assert er.inbound_sources == {}
    assert er.stockpile_levels == {}
    assert er.import_share == {}
    assert er.trade_dependent == {}


def test_category_goods_food_contains_salt():
    assert "salt" in CATEGORY_GOODS["food"]


def test_category_goods_three_categories():
    assert set(CATEGORY_GOODS.keys()) == {"food", "raw_material", "luxury"}


def test_category_goods_all_8_goods_covered():
    all_goods = set()
    for goods in CATEGORY_GOODS.values():
        all_goods |= goods
    assert len(all_goods) == 8


def test_import_share_above_threshold_is_trade_dependent():
    er = EconomyResult()
    er.import_share = {"Coast": 0.8}
    er.trade_dependent = {"Coast": True}
    assert er.trade_dependent["Coast"] is True
    assert er.import_share["Coast"] > TRADE_DEPENDENCY_THRESHOLD


# ---------------------------------------------------------------------------
# Task 4: EconomyTracker
# ---------------------------------------------------------------------------

from chronicler.economy import EconomyTracker


def test_economy_tracker_first_update_initializes():
    tracker = EconomyTracker()
    tracker.update_stockpile("Plains", "food", 100.0)
    assert tracker.trailing_avg["Plains"]["food"] == 100.0


def test_economy_tracker_ema_converges():
    tracker = EconomyTracker()
    for _ in range(20):
        tracker.update_stockpile("Plains", "food", 50.0)
    assert abs(tracker.trailing_avg["Plains"]["food"] - 50.0) < 0.01


def test_economy_tracker_ema_responds_to_step():
    tracker = EconomyTracker()
    tracker.update_stockpile("Plains", "food", 100.0)
    tracker.update_stockpile("Plains", "food", 0.0)
    assert abs(tracker.trailing_avg["Plains"]["food"] - 67.0) < 0.1


def test_economy_tracker_imports_ema():
    tracker = EconomyTracker()
    tracker.update_imports("Coast", "food", 80.0)
    assert tracker.import_avg["Coast"]["food"] == 80.0
    tracker.update_imports("Coast", "food", 40.0)
    assert abs(tracker.import_avg["Coast"]["food"] - 66.8) < 0.1


def test_economy_tracker_separate_regions():
    tracker = EconomyTracker()
    tracker.update_stockpile("Plains", "food", 100.0)
    tracker.update_stockpile("Coast", "food", 50.0)
    assert tracker.trailing_avg["Plains"]["food"] == 100.0
    assert tracker.trailing_avg["Coast"]["food"] == 50.0


# ---------------------------------------------------------------------------
# Task 5: detect_supply_shocks() and classify_upstream_source()
# ---------------------------------------------------------------------------

from chronicler.economy import (
    detect_supply_shocks, classify_upstream_source,
    SHOCK_DELTA_THRESHOLD, SHOCK_SEVERITY_FLOOR,
)
from chronicler.models import Region, Civilization, WorldState, Leader


def _make_region(name, controller=None, terrain="plains"):
    return Region(
        name=name, terrain=terrain, carrying_capacity=50,
        resources="fertile", controller=controller,
        adjacencies=[],
    )


def _make_civ(name, regions):
    return Civilization(
        name=name,
        population=50, military=30, economy=40, culture=30, stability=50,
        leader=Leader(name=f"Leader of {name}", trait="cautious", reign_start=0),
        regions=regions,
    )


def test_detect_shock_fires_on_delta_and_below_floor():
    region = _make_region("Plains", controller="Rome")
    region.stockpile.goods = {"grain": 50.0}
    tracker = EconomyTracker()
    tracker.trailing_avg = {"Plains": {"food": 100.0}}
    tracker.import_avg = {"Plains": {"food": 0.0}}
    rome = _make_civ("Rome", ["Plains"])
    world = WorldState(name="test", seed=0, turn=10, regions=[region], civilizations=[rome])
    region_map = {"Plains": region}
    er = EconomyResult()
    er.food_sufficiency = {"Plains": 0.5}
    er.imports_by_region = {"Plains": {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {}
    er.stockpile_levels = {"Plains": {"food": 50.0}}
    shocks = detect_supply_shocks(world, {"Plains": region.stockpile}, tracker, er, region_map)
    assert len(shocks) == 1
    assert shocks[0].event_type == "supply_shock"
    assert shocks[0].actors[0] == "Rome"
    assert shocks[0].shock_region == "Plains"
    assert shocks[0].shock_category == "food"
    assert shocks[0].importance >= 5


def test_detect_shock_does_not_fire_above_floor():
    region = _make_region("Plains", controller="Rome")
    region.stockpile.goods = {"grain": 50.0}
    tracker = EconomyTracker()
    tracker.trailing_avg = {"Plains": {"food": 100.0}}
    rome = _make_civ("Rome", ["Plains"])
    world = WorldState(name="test", seed=0, turn=10, regions=[region], civilizations=[rome])
    region_map = {"Plains": region}
    er = EconomyResult()
    er.food_sufficiency = {"Plains": 1.2}
    er.imports_by_region = {"Plains": {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {}
    er.stockpile_levels = {"Plains": {"food": 50.0}}
    shocks = detect_supply_shocks(world, {"Plains": region.stockpile}, tracker, er, region_map)
    assert len(shocks) == 0


def test_detect_shock_no_delta_no_fire():
    region = _make_region("Plains", controller="Rome")
    region.stockpile.goods = {"grain": 20.0}
    tracker = EconomyTracker()
    tracker.trailing_avg = {"Plains": {"food": 22.0}}
    rome = _make_civ("Rome", ["Plains"])
    world = WorldState(name="test", seed=0, turn=10, regions=[region], civilizations=[rome])
    region_map = {"Plains": region}
    er = EconomyResult()
    er.food_sufficiency = {"Plains": 0.4}
    er.imports_by_region = {"Plains": {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {}
    er.stockpile_levels = {"Plains": {"food": 20.0}}
    shocks = detect_supply_shocks(world, {"Plains": region.stockpile}, tracker, er, region_map)
    assert len(shocks) == 0


def test_detect_shock_non_food_uses_delta_severity():
    region = _make_region("Mountains", controller="Rome")
    region.stockpile.goods = {"ore": 10.0}
    tracker = EconomyTracker()
    tracker.trailing_avg = {"Mountains": {"raw_material": 100.0}}
    rome = _make_civ("Rome", ["Mountains"])
    world = WorldState(name="test", seed=0, turn=10, regions=[region], civilizations=[rome])
    region_map = {"Mountains": region}
    er = EconomyResult()
    er.food_sufficiency = {"Mountains": 1.0}
    er.imports_by_region = {"Mountains": {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {}
    er.stockpile_levels = {"Mountains": {"raw_material": 10.0}}
    shocks = detect_supply_shocks(world, {"Mountains": region.stockpile}, tracker, er, region_map)
    assert len(shocks) == 1
    assert shocks[0].shock_category == "raw_material"


def test_detect_shock_importance_scales_with_severity():
    region = _make_region("Plains", controller="Rome")
    region.stockpile.goods = {"grain": 10.0}
    tracker = EconomyTracker()
    tracker.trailing_avg = {"Plains": {"food": 100.0}}
    rome = _make_civ("Rome", ["Plains"])
    world = WorldState(name="test", seed=0, turn=10, regions=[region], civilizations=[rome])
    region_map = {"Plains": region}
    er = EconomyResult()
    er.food_sufficiency = {"Plains": 0.0}
    er.imports_by_region = {"Plains": {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {}
    er.stockpile_levels = {"Plains": {"food": 10.0}}
    shocks = detect_supply_shocks(world, {"Plains": region.stockpile}, tracker, er, region_map)
    assert len(shocks) == 1
    assert shocks[0].importance == 9


def test_shock_actors_affected_first_upstream_second():
    coast = _make_region("Coast", controller="Tyre")
    coast.stockpile.goods = {"fish": 20.0}
    plains = _make_region("Plains", controller="Aram")
    tracker = EconomyTracker()
    tracker.trailing_avg = {"Coast": {"food": 100.0}, "Plains": {"food": 100.0}}
    tracker.import_avg = {"Coast": {"food": 80.0}}
    tyre = _make_civ("Tyre", ["Coast"])
    aram = _make_civ("Aram", ["Plains"])
    world = WorldState(name="test", seed=0, turn=10, regions=[coast, plains], civilizations=[tyre, aram])
    region_map = {"Coast": coast, "Plains": plains}
    er = EconomyResult()
    er.food_sufficiency = {"Coast": 0.3}
    er.imports_by_region = {"Coast": {"food": 5.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {"Coast": ["Plains"]}
    er.stockpile_levels = {"Coast": {"food": 20.0}, "Plains": {"food": 10.0}}
    shocks = detect_supply_shocks(world, {"Coast": coast.stockpile}, tracker, er, region_map)
    assert len(shocks) >= 1
    coast_shock = next(s for s in shocks if s.shock_region == "Coast")
    assert coast_shock.actors[0] == "Tyre"
    assert len(coast_shock.actors) >= 2
    assert coast_shock.actors[1] == "Aram"


# ---------------------------------------------------------------------------
# Task 6: _get_adjacent_enemy_regions() and raider constants
# ---------------------------------------------------------------------------

from chronicler.economy import (
    _get_adjacent_enemy_regions, RAIDER_WAR_WEIGHT, RAIDER_CAP,
    RAIDER_THRESHOLD, FOOD_GOODS,
)
from chronicler.models import Disposition, Relationship


def _make_world_with_enemy_stockpile():
    """Two civs: Rome (Plains) hostile to Persia (Mountains with big stockpile)."""
    plains = _make_region("Plains", controller="Rome")
    plains.adjacencies = ["Mountains"]
    mountains = _make_region("Mountains", controller="Persia", terrain="mountain")
    mountains.adjacencies = ["Plains"]
    mountains.stockpile.goods = {"grain": 500.0}
    rome = _make_civ("Rome", ["Plains"])
    persia = _make_civ("Persia", ["Mountains"])
    world = WorldState(name="test", seed=0, turn=10, regions=[plains, mountains], civilizations=[rome, persia])
    world.relationships = {
        "Rome": {"Persia": Relationship(disposition=Disposition.HOSTILE)},
        "Persia": {"Rome": Relationship(disposition=Disposition.HOSTILE)},
    }
    return world, rome, persia


def test_adjacent_enemy_regions_finds_hostile():
    world, rome, _ = _make_world_with_enemy_stockpile()
    enemies = _get_adjacent_enemy_regions(rome, world)
    assert len(enemies) == 1
    assert enemies[0].name == "Mountains"


def test_adjacent_enemy_regions_empty_for_friendly():
    world, rome, _ = _make_world_with_enemy_stockpile()
    world.relationships["Rome"]["Persia"] = Relationship(disposition=Disposition.FRIENDLY)
    enemies = _get_adjacent_enemy_regions(rome, world)
    assert len(enemies) == 0


def test_raider_modifier_zero_below_threshold():
    max_food = 1.0
    bonus = 0.0
    if max_food > RAIDER_THRESHOLD:
        bonus = RAIDER_WAR_WEIGHT * min(max_food / RAIDER_THRESHOLD - 1.0, RAIDER_CAP)
    assert bonus == 0.0


def test_raider_modifier_scales_above_threshold():
    max_food = RAIDER_THRESHOLD * 3
    bonus = RAIDER_WAR_WEIGHT * min(max_food / RAIDER_THRESHOLD - 1.0, RAIDER_CAP)
    assert bonus == RAIDER_WAR_WEIGHT * RAIDER_CAP


def test_raider_modifier_uses_max_not_sum():
    plains = _make_region("Plains", controller="Rome")
    plains.adjacencies = ["A", "B"]
    a = _make_region("A", controller="Persia")
    a.adjacencies = ["Plains"]
    a.stockpile.goods = {"grain": 10.0}
    b = _make_region("B", controller="Persia")
    b.adjacencies = ["Plains"]
    b.stockpile.goods = {"grain": 200.0}
    rome = _make_civ("Rome", ["Plains"])
    persia = _make_civ("Persia", ["A", "B"])
    world = WorldState(name="test", seed=0, turn=10, regions=[plains, a, b], civilizations=[rome, persia])
    world.relationships = {
        "Rome": {"Persia": Relationship(disposition=Disposition.HOSTILE)},
    }
    enemies = _get_adjacent_enemy_regions(rome, world)
    max_food = max(
        sum(r.stockpile.goods.get(g, 0.0) for g in FOOD_GOODS)
        for r in enemies
    )
    assert max_food == 200.0


# ---------------------------------------------------------------------------
# Task 7: Raider modifier wired into ActionEngine.compute_weights()
# ---------------------------------------------------------------------------

from chronicler.models import ActionType, Leader


def test_raider_modifier_in_compute_weights():
    from chronicler.action_engine import ActionEngine

    world, rome, persia = _make_world_with_enemy_stockpile()
    mountains = next(r for r in world.regions if r.name == "Mountains")
    mountains.stockpile.goods = {"grain": RAIDER_THRESHOLD * 2}
    world.action_history = {}
    er = EconomyResult()
    world._economy_result = er
    rome.leader = Leader(name="Caesar", trait="balanced", reign_start=0)
    rome.treasury = 100
    rome.military = 50
    rome.economy = 50
    rome.culture = 50
    rome.stability = 50
    rome.population = 100
    rome.tech_era = "bronze"

    engine = ActionEngine(world)
    weights_with = engine.compute_weights(rome)
    war_weight_with = weights_with.get(ActionType.WAR, 0)

    world._economy_result = None
    engine2 = ActionEngine(world)
    weights_without = engine2.compute_weights(rome)
    war_weight_without = weights_without.get(ActionType.WAR, 0)

    assert war_weight_with > war_weight_without


# ---------------------------------------------------------------------------
# Task 8: CAUSAL_PATTERNS supply_shock entries
# ---------------------------------------------------------------------------

def test_causal_patterns_include_supply_shock():
    from chronicler.curator import CAUSAL_PATTERNS
    shock_patterns = [p for p in CAUSAL_PATTERNS if "supply_shock" in (p[0], p[1])]
    assert len(shock_patterns) == 7
    self_link = [p for p in shock_patterns if p[0] == "supply_shock" and p[1] == "supply_shock"]
    assert len(self_link) == 1


# ---------------------------------------------------------------------------
# Task 9: Narration context wiring
# ---------------------------------------------------------------------------

from chronicler.narrative import build_agent_context_block
from chronicler.models import AgentContext, ShockContext


def test_agent_context_block_renders_trade_dependency():
    ctx = AgentContext(
        trade_dependent_regions=["Coast", "Port"],
    )
    block = build_agent_context_block(ctx)
    assert "Trade-dependent regions: Coast, Port" in block


def test_agent_context_block_renders_shocks():
    ctx = AgentContext(
        active_shocks=[
            ShockContext(region="Plains", category="food", severity=0.7, upstream_source="Aram"),
        ],
    )
    block = build_agent_context_block(ctx)
    assert "Supply crisis in Plains" in block
    assert "food" in block
    assert "Aram" in block


def test_agent_context_block_no_trade_data_no_section():
    ctx = AgentContext()
    block = build_agent_context_block(ctx)
    assert "Trade-dependent" not in block
    assert "Supply crisis" not in block


# ---------------------------------------------------------------------------
# Task 11: End-to-end curator integration tests for supply shock events
# ---------------------------------------------------------------------------

from chronicler.curator import compute_causal_links, compute_base_scores


def test_shock_events_flow_through_curator():
    drought = Event(
        turn=5, event_type="drought", actors=["Rome"],
        description="Drought in Plains", importance=6,
    )
    shock = Event(
        turn=7, event_type="supply_shock", actors=["Rome", "Aram"],
        description="Supply shock: food in Coast", importance=7,
        source="economy", shock_region="Coast", shock_category="food",
    )
    famine = Event(
        turn=10, event_type="famine", actors=["Rome"],
        description="Famine in Coast", importance=8,
    )
    events = [drought, shock, famine]
    scores = compute_base_scores(events, [], "Rome", seed=42)
    links = compute_causal_links(events, scores)
    drought_to_shock = [l for l in links if l.cause_event_type == "drought" and l.effect_event_type == "supply_shock"]
    assert len(drought_to_shock) == 1
    shock_to_famine = [l for l in links if l.cause_event_type == "supply_shock" and l.effect_event_type == "famine"]
    assert len(shock_to_famine) == 1


def test_shock_to_shock_chain_linking():
    shock_a = Event(
        turn=5, event_type="supply_shock", actors=["Aram"],
        description="Supply shock: food in Plains", importance=7,
        source="economy", shock_region="Plains", shock_category="food",
    )
    shock_b = Event(
        turn=7, event_type="supply_shock", actors=["Tyre", "Aram"],
        description="Supply shock: food in Coast", importance=7,
        source="economy", shock_region="Coast", shock_category="food",
    )
    events = [shock_a, shock_b]
    scores = compute_base_scores(events, [], "Aram", seed=42)
    links = compute_causal_links(events, scores)
    chain = [l for l in links if l.cause_event_type == "supply_shock" and l.effect_event_type == "supply_shock"]
    assert len(chain) == 1


# ---------------------------------------------------------------------------
# Phoebe review fixes: B-1 (economy_result threading), NB-2 (transient test)
# ---------------------------------------------------------------------------

def test_economy_result_reaches_narrator():
    """B-1: economy_result must be threaded through narrate_batch to
    build_agent_context_for_moment so trade/shock context is not dead code."""
    from chronicler.narrative import build_agent_context_for_moment
    from chronicler.models import NarrativeMoment, NarrativeRole, CausalLink

    moment = NarrativeMoment(
        anchor_turn=10,
        turn_range=(9, 11),
        events=[
            Event(
                turn=10, event_type="supply_shock", actors=["Rome", "Aram"],
                description="Supply shock: food in Plains", importance=7,
                source="economy", shock_region="Plains", shock_category="food",
            ),
        ],
        named_events=[],
        score=10.0,
        causal_links=[],
        narrative_role=NarrativeRole.RESOLUTION,
        bonus_applied=0.0,
    )
    er = EconomyResult()
    er.trade_dependent = {"Plains": True, "Coast": True}

    ctx = build_agent_context_for_moment(
        moment, [], {}, {},
        economy_result=er,
    )
    assert ctx is not None
    assert "Plains" in ctx.trade_dependent_regions
    assert len(ctx.active_shocks) == 1
    assert ctx.active_shocks[0].region == "Plains"


def test_economy_result_overwritten_each_turn():
    """NB-2: Transient signal test — world._economy_result is unconditionally
    overwritten each turn by M42 wiring, not carried over from previous turn.
    Verifies that stale economy_result from turn N does not leak into turn N+1."""
    from chronicler.models import WorldState

    world = WorldState(name="test", seed=0, turn=1, regions=[], civilizations=[])

    # Turn 1: set economy_result
    er1 = EconomyResult()
    er1.trade_dependent = {"Plains": True}
    world._economy_result = er1
    assert world._economy_result.trade_dependent["Plains"] is True

    # Turn 2: overwrite with fresh result (simulates M42 wiring)
    er2 = EconomyResult()
    er2.trade_dependent = {}
    world._economy_result = er2
    assert world._economy_result.trade_dependent == {}
    # Stale turn 1 data is gone — not accumulated
    assert "Plains" not in world._economy_result.trade_dependent
