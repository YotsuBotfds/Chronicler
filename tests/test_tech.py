import pytest
from chronicler.models import Civilization, Leader, Resource, TechEra, Event, WorldState, Region
from chronicler.tech import TECH_REQUIREMENTS, ERA_BONUSES, check_tech_advancement, apply_era_bonus, tech_war_multiplier


@pytest.fixture
def tribal_civ():
    return Civilization(
        name="Test Civ", population=50, military=30, economy=40, culture=40, stability=50,
        tech_era=TechEra.TRIBAL, treasury=150,
        leader=Leader(name="Leader", trait="bold", reign_start=0), regions=["Region A"],
    )

@pytest.fixture
def tech_world(tribal_civ):
    return WorldState(
        name="Test", seed=42, turn=5,
        regions=[Region(name="Region A", terrain="plains", carrying_capacity=80, resources="fertile", controller="Test Civ", specialized_resources=[Resource.IRON, Resource.TIMBER])],
        civilizations=[tribal_civ],
    )

def test_tech_requirements_defined_for_all_transitions():
    for era in TechEra:
        if era != TechEra.INFORMATION:
            assert era in TECH_REQUIREMENTS

def test_advancement_tribal_to_bronze(tribal_civ, tech_world):
    event = check_tech_advancement(tribal_civ, tech_world)
    assert event is not None
    assert event.event_type == "tech_advancement"
    assert event.importance == 7
    assert tribal_civ.tech_era == TechEra.BRONZE
    assert tribal_civ.treasury == 50

def test_no_advancement_insufficient_culture(tribal_civ, tech_world):
    tribal_civ.culture = 30
    assert check_tech_advancement(tribal_civ, tech_world) is None
    assert tribal_civ.tech_era == TechEra.TRIBAL

def test_no_advancement_insufficient_economy(tribal_civ, tech_world):
    tribal_civ.economy = 30
    assert check_tech_advancement(tribal_civ, tech_world) is None
    assert tribal_civ.tech_era == TechEra.TRIBAL

def test_no_advancement_insufficient_treasury(tribal_civ, tech_world):
    tribal_civ.treasury = 90
    assert check_tech_advancement(tribal_civ, tech_world) is None
    assert tribal_civ.tech_era == TechEra.TRIBAL

def test_no_advancement_at_information(tribal_civ, tech_world):
    tribal_civ.tech_era = TechEra.INFORMATION
    tribal_civ.culture = 100
    tribal_civ.economy = 100
    tribal_civ.treasury = 500
    assert check_tech_advancement(tribal_civ, tech_world) is None

def test_era_bonus_bronze():
    civ = Civilization(name="Test", population=50, military=30, economy=50, culture=50, stability=50,
        tech_era=TechEra.BRONZE, treasury=100, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old = civ.military
    apply_era_bonus(civ, TechEra.BRONZE)
    assert civ.military == old + 10

def test_era_bonus_iron():
    civ = Civilization(name="Test", population=50, military=30, economy=50, culture=50, stability=50,
        tech_era=TechEra.IRON, treasury=100, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old = civ.economy
    apply_era_bonus(civ, TechEra.IRON)
    assert civ.economy == old + 10

def test_era_bonus_classical():
    civ = Civilization(name="Test", population=50, military=30, economy=50, culture=50, stability=50,
        tech_era=TechEra.CLASSICAL, treasury=100, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old = civ.culture
    apply_era_bonus(civ, TechEra.CLASSICAL)
    assert civ.culture == old + 10

def test_era_bonus_medieval():
    civ = Civilization(name="Test", population=50, military=30, economy=50, culture=50, stability=50,
        tech_era=TechEra.MEDIEVAL, treasury=100, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old = civ.military
    apply_era_bonus(civ, TechEra.MEDIEVAL)
    assert civ.military == old + 10

def test_era_bonus_renaissance():
    civ = Civilization(name="Test", population=50, military=30, economy=50, culture=50, stability=50,
        tech_era=TechEra.RENAISSANCE, treasury=100, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old_e, old_c = civ.economy, civ.culture
    apply_era_bonus(civ, TechEra.RENAISSANCE)
    assert civ.economy == old_e + 20
    assert civ.culture == old_c + 10

def test_era_bonus_industrial():
    civ = Civilization(name="Test", population=50, military=30, economy=30, culture=50, stability=50,
        tech_era=TechEra.INDUSTRIAL, treasury=100, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old_e, old_m = civ.economy, civ.military
    apply_era_bonus(civ, TechEra.INDUSTRIAL)
    assert civ.economy == old_e + 20
    assert civ.military == old_m + 20

def test_era_bonus_clamped_to_100():
    civ = Civilization(name="Test", population=50, military=100, economy=50, culture=50, stability=50,
        tech_era=TechEra.BRONZE, treasury=100, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    apply_era_bonus(civ, TechEra.BRONZE)
    assert civ.military == 100

def test_tech_war_multiplier_no_gap():
    assert tech_war_multiplier(TechEra.IRON, TechEra.IRON) == 1.0

def test_tech_war_multiplier_gap_1():
    assert tech_war_multiplier(TechEra.CLASSICAL, TechEra.IRON) == 1.0

def test_tech_war_multiplier_gap_2():
    assert tech_war_multiplier(TechEra.MEDIEVAL, TechEra.IRON) == 1.5

def test_tech_war_multiplier_gap_3():
    assert tech_war_multiplier(TechEra.RENAISSANCE, TechEra.IRON) == 1.5

def test_tech_war_multiplier_gap_4():
    assert tech_war_multiplier(TechEra.INDUSTRIAL, TechEra.IRON) == 2.0

def test_tech_war_multiplier_defender_advantage():
    mult = tech_war_multiplier(TechEra.IRON, TechEra.MEDIEVAL)
    assert mult == pytest.approx(1 / 1.5, rel=0.01)


def test_tech_blocked_without_resources(sample_world):
    from chronicler.models import Resource
    civ = sample_world.civilizations[0]
    civ.tech_era = TechEra.TRIBAL
    civ.culture = 40
    civ.economy = 40
    civ.treasury = 100
    for r in sample_world.regions:
        if r.controller == civ.name:
            r.specialized_resources = [Resource.GRAIN]
    event = check_tech_advancement(civ, sample_world)
    assert event is None


def test_tech_allowed_with_resources(sample_world):
    from chronicler.models import Resource
    civ = sample_world.civilizations[0]
    civ.tech_era = TechEra.TRIBAL
    civ.culture = 40
    civ.economy = 40
    civ.treasury = 100
    for r in sample_world.regions:
        if r.controller == civ.name:
            r.specialized_resources = [Resource.IRON, Resource.TIMBER]
            break
    event = check_tech_advancement(civ, sample_world)
    assert event is not None
