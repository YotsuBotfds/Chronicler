"""M43b: Supply shock detection, trade dependency & raider incentive tests."""

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
