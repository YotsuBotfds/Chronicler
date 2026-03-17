import pytest
from chronicler.models import FactionType, FactionState
from chronicler.factions import normalize_influence, FACTION_FLOOR, FACTION_WEIGHTS, FACTION_CANDIDATE_TYPE, GP_ROLE_TO_FACTION
from chronicler.models import ActionType

def test_faction_type_has_clergy():
    assert hasattr(FactionType, "CLERGY")
    assert FactionType.CLERGY.value == "clergy"

def test_faction_state_default_has_clergy():
    fs = FactionState()
    assert FactionType.CLERGY in fs.influence
    assert len(fs.influence) == 4

def test_normalize_4_factions_sum_to_one():
    fs = FactionState()
    normalize_influence(fs)
    total = sum(fs.influence.values())
    assert abs(total - 1.0) < 1e-6

def test_normalize_4_factions_floor():
    fs = FactionState()
    fs.influence[FactionType.CLERGY] = 0.01
    normalize_influence(fs)
    for ft in FactionType:
        assert fs.influence[ft] >= FACTION_FLOOR - 1e-6

def test_clergy_faction_weights_exist():
    assert FactionType.CLERGY in FACTION_WEIGHTS
    weights = FACTION_WEIGHTS[FactionType.CLERGY]
    assert ActionType.INVEST_CULTURE in weights
    assert ActionType.BUILD in weights
    assert weights[ActionType.WAR] < 1.0

def test_clergy_candidate_type():
    assert FactionType.CLERGY in FACTION_CANDIDATE_TYPE
    assert FACTION_CANDIDATE_TYPE[FactionType.CLERGY] == "clergy"

def test_prophet_maps_to_clergy():
    assert GP_ROLE_TO_FACTION["prophet"] == FactionType.CLERGY

def test_backward_compat_missing_clergy():
    """Pre-M38a FactionState without CLERGY gets it injected."""
    fs = FactionState(influence={
        FactionType.MILITARY: 0.40,
        FactionType.MERCHANT: 0.35,
        FactionType.CULTURAL: 0.25,
    })
    assert FactionType.CLERGY in fs.influence
    assert fs.influence[FactionType.CLERGY] == 0.08
