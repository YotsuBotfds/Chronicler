"""M43b: Supply shock detection, trade dependency & raider incentive tests."""

from chronicler.economy import EconomyResult, CATEGORY_GOODS, TRADE_DEPENDENCY_THRESHOLD
from chronicler.models import Event, AgentContext, CivThematicContext, ShockContext


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


def test_civ_thematic_context_trade_dependency_default_none():
    ctx = CivThematicContext(
        name="Rome", trait="expansionist", domains=["plains"],
        dominant_terrain="plains", tech_era="bronze",
    )
    assert ctx.trade_dependency_summary is None


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
