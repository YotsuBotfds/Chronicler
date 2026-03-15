from chronicler.models import (
    Civilization, Infrastructure, InfrastructureType, Leader, Region, Resource, TechEra,
    ActionType, WorldState,
)
from chronicler.tech_focus import (
    TechFocus, ERA_FOCUSES, select_tech_focus, _score_focus,
    apply_focus_effects, remove_focus_effects, get_focus_weight_modifiers, FOCUS_EFFECTS,
)


def _make_world(regions=None, seed=42):
    return WorldState(name="TestWorld", turn=1, seed=seed, regions=regions or [], civilizations=[], relationships={})


def _make_civ(**kwargs):
    defaults = dict(name="TestCiv", population=50, military=50, economy=50, culture=50, stability=50,
                    leader=Leader(name="L", trait="cautious", reign_start=0))
    defaults.update(kwargs)
    return Civilization(**defaults)


def _make_region(name, terrain="plains", controller=None, **kwargs):
    defaults = dict(name=name, terrain=terrain, carrying_capacity=20, resources="fertile", controller=controller, population=10)
    defaults.update(kwargs)
    return Region(**defaults)


def _make_infra(infra_type, active=True):
    return Infrastructure(type=infra_type, builder_civ="TestCiv", built_turn=0, active=active)


def test_civilization_has_tech_focus_fields():
    civ = Civilization(
        name="Test", population=50, military=50, economy=50,
        culture=50, stability=50,
        leader=Leader(name="L", trait="cautious", reign_start=0),
    )
    assert civ.tech_focuses == []
    assert civ.active_focus is None


# --- Task 3-5 tests ---


def test_tech_focus_enum_has_15_values():
    assert len(TechFocus) == 15


def test_era_focuses_maps_5_eras():
    assert len(ERA_FOCUSES) == 5
    for era, focuses in ERA_FOCUSES.items():
        assert len(focuses) == 3, f"{era} should have 3 focuses"


def test_pre_classical_eras_have_no_focuses():
    for era in [TechEra.TRIBAL, TechEra.BRONZE, TechEra.IRON]:
        assert era not in ERA_FOCUSES


def test_coastal_civ_selects_navigation():
    regions = [
        _make_region(f"coast_{i}", terrain="coast", controller="TestCiv",
                     infrastructure=[_make_infra(InfrastructureType.PORTS)])
        for i in range(3)
    ]
    world = _make_world(regions=regions)
    civ = _make_civ(tech_era=TechEra.CLASSICAL)
    result = select_tech_focus(civ, world)
    assert result == TechFocus.NAVIGATION


def test_iron_mining_civ_selects_metallurgy():
    regions = [
        _make_region(f"mountain_{i}", terrain="mountains", controller="TestCiv",
                     specialized_resources=[Resource.IRON],
                     infrastructure=[_make_infra(InfrastructureType.MINES)])
        for i in range(3)
    ]
    world = _make_world(regions=regions)
    civ = _make_civ(tech_era=TechEra.CLASSICAL)
    result = select_tech_focus(civ, world)
    assert result == TechFocus.METALLURGY


def test_pre_classical_returns_none():
    world = _make_world()
    civ = _make_civ(tech_era=TechEra.TRIBAL)
    assert select_tech_focus(civ, world) is None
    civ2 = _make_civ(tech_era=TechEra.BRONZE)
    assert select_tech_focus(civ2, world) is None
    civ3 = _make_civ(tech_era=TechEra.IRON)
    assert select_tech_focus(civ3, world) is None


def test_selection_is_deterministic():
    regions = [
        _make_region(f"coast_{i}", terrain="coast", controller="TestCiv",
                     infrastructure=[_make_infra(InfrastructureType.PORTS)])
        for i in range(3)
    ]
    world = _make_world(regions=regions)
    civ = _make_civ(tech_era=TechEra.CLASSICAL)
    first = select_tech_focus(civ, world)
    for _ in range(10):
        assert select_tech_focus(civ, world) == first


def test_all_zero_fallback_uses_highest_stat():
    # Forest-only regions (no coastal, no iron, no infrastructure) => all scores ~0
    # With high military, should fallback to METALLURGY in Classical
    regions = [
        _make_region("forest_0", terrain="forest", controller="TestCiv")
    ]
    world = _make_world(regions=regions)
    civ = _make_civ(tech_era=TechEra.CLASSICAL, military=80, economy=20, culture=20,
                    population=0)
    result = select_tech_focus(civ, world)
    assert result == TechFocus.METALLURGY


def test_focus_effects_table_has_15_entries():
    assert len(FOCUS_EFFECTS) == 15


def test_apply_focus_effects_modifies_stats():
    civ = _make_civ(military=50)
    apply_focus_effects(civ, TechFocus.METALLURGY)
    assert civ.military == 65  # +15
    assert civ.active_focus == "metallurgy"
    assert "metallurgy" in civ.tech_focuses


def test_remove_focus_effects_reverses_stats():
    civ = _make_civ(military=50)
    apply_focus_effects(civ, TechFocus.METALLURGY)
    assert civ.military == 65
    remove_focus_effects(civ, TechFocus.METALLURGY)
    assert civ.military == 50


def test_apply_remove_clamping_asymmetry():
    # Start at 95, apply METALLURGY (+15) -> clamped to 100
    # Remove METALLURGY (-15) -> 100 - 15 = 85 (NOT 95)
    civ = _make_civ(military=95)
    apply_focus_effects(civ, TechFocus.METALLURGY)
    assert civ.military == 100
    remove_focus_effects(civ, TechFocus.METALLURGY)
    assert civ.military == 85


def test_get_weight_modifiers_returns_dict():
    civ = _make_civ()
    apply_focus_effects(civ, TechFocus.METALLURGY)
    mods = get_focus_weight_modifiers(civ)
    assert ActionType.WAR in mods
    assert mods[ActionType.WAR] == 1.3


def test_get_weight_modifiers_empty_when_no_focus():
    civ = _make_civ()
    mods = get_focus_weight_modifiers(civ)
    assert mods == {}
