import pytest
from chronicler.models import Civilization, Leader, TechEra, Event, WorldState, Region
from chronicler.tech import TECH_REQUIREMENTS, ERA_BONUSES, check_tech_advancement, apply_era_bonus, tech_war_multiplier


@pytest.fixture
def tribal_civ():
    return Civilization(
        name="Test Civ", population=5, military=3, economy=4, culture=4, stability=5,
        tech_era=TechEra.TRIBAL, treasury=15,
        leader=Leader(name="Leader", trait="bold", reign_start=0), regions=["Region A"],
    )

@pytest.fixture
def tech_world(tribal_civ):
    return WorldState(
        name="Test", seed=42, turn=5,
        regions=[Region(name="Region A", terrain="plains", carrying_capacity=8, resources="fertile")],
        civilizations=[tribal_civ],
    )

def test_tech_requirements_defined_for_all_transitions():
    for era in TechEra:
        if era != TechEra.INDUSTRIAL:
            assert era in TECH_REQUIREMENTS

def test_advancement_tribal_to_bronze(tribal_civ, tech_world):
    event = check_tech_advancement(tribal_civ, tech_world)
    assert event is not None
    assert event.event_type == "tech_advancement"
    assert event.importance == 7
    assert tribal_civ.tech_era == TechEra.BRONZE
    assert tribal_civ.treasury == 5

def test_no_advancement_insufficient_culture(tribal_civ, tech_world):
    tribal_civ.culture = 3
    assert check_tech_advancement(tribal_civ, tech_world) is None
    assert tribal_civ.tech_era == TechEra.TRIBAL

def test_no_advancement_insufficient_economy(tribal_civ, tech_world):
    tribal_civ.economy = 3
    assert check_tech_advancement(tribal_civ, tech_world) is None
    assert tribal_civ.tech_era == TechEra.TRIBAL

def test_no_advancement_insufficient_treasury(tribal_civ, tech_world):
    tribal_civ.treasury = 9
    assert check_tech_advancement(tribal_civ, tech_world) is None
    assert tribal_civ.tech_era == TechEra.TRIBAL

def test_no_advancement_at_industrial(tribal_civ, tech_world):
    tribal_civ.tech_era = TechEra.INDUSTRIAL
    tribal_civ.culture = 10
    tribal_civ.economy = 10
    tribal_civ.treasury = 50
    assert check_tech_advancement(tribal_civ, tech_world) is None

def test_era_bonus_bronze():
    civ = Civilization(name="Test", population=5, military=3, economy=5, culture=5, stability=5,
        tech_era=TechEra.BRONZE, treasury=10, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old = civ.military
    apply_era_bonus(civ, TechEra.BRONZE)
    assert civ.military == old + 1

def test_era_bonus_iron():
    civ = Civilization(name="Test", population=5, military=3, economy=5, culture=5, stability=5,
        tech_era=TechEra.IRON, treasury=10, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old = civ.economy
    apply_era_bonus(civ, TechEra.IRON)
    assert civ.economy == old + 1

def test_era_bonus_classical():
    civ = Civilization(name="Test", population=5, military=3, economy=5, culture=5, stability=5,
        tech_era=TechEra.CLASSICAL, treasury=10, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old = civ.culture
    apply_era_bonus(civ, TechEra.CLASSICAL)
    assert civ.culture == old + 1

def test_era_bonus_medieval():
    civ = Civilization(name="Test", population=5, military=3, economy=5, culture=5, stability=5,
        tech_era=TechEra.MEDIEVAL, treasury=10, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old = civ.military
    apply_era_bonus(civ, TechEra.MEDIEVAL)
    assert civ.military == old + 1

def test_era_bonus_renaissance():
    civ = Civilization(name="Test", population=5, military=3, economy=5, culture=5, stability=5,
        tech_era=TechEra.RENAISSANCE, treasury=10, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old_e, old_c = civ.economy, civ.culture
    apply_era_bonus(civ, TechEra.RENAISSANCE)
    assert civ.economy == old_e + 2
    assert civ.culture == old_c + 1

def test_era_bonus_industrial():
    civ = Civilization(name="Test", population=5, military=3, economy=3, culture=5, stability=5,
        tech_era=TechEra.INDUSTRIAL, treasury=10, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    old_e, old_m = civ.economy, civ.military
    apply_era_bonus(civ, TechEra.INDUSTRIAL)
    assert civ.economy == old_e + 2
    assert civ.military == old_m + 2

def test_era_bonus_clamped_to_10():
    civ = Civilization(name="Test", population=5, military=10, economy=5, culture=5, stability=5,
        tech_era=TechEra.BRONZE, treasury=10, leader=Leader(name="L", trait="bold", reign_start=0), regions=["R"])
    apply_era_bonus(civ, TechEra.BRONZE)
    assert civ.military == 10

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
