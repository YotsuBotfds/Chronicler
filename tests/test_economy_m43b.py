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
