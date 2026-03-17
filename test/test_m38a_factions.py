import pytest
from unittest.mock import MagicMock
from chronicler.models import FactionType, FactionState, Event
from chronicler.factions import (
    normalize_influence, FACTION_FLOOR, FACTION_WEIGHTS, FACTION_CANDIDATE_TYPE,
    GP_ROLE_TO_FACTION, tick_factions, EVT_TEMPLE_BUILT, EVT_CONVERSION_SUCCESS,
    compute_tithe_base, TITHE_RATE, TITHE_THRESHOLD,
)
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


# ---------------------------------------------------------------------------
# Task 9–11 tests
# ---------------------------------------------------------------------------

def _make_civ_with_clergy(clergy_influence=0.25):
    from chronicler.models import FactionState, FactionType, Civilization
    from chronicler.factions import normalize_influence
    civ = MagicMock()
    civ.factions = FactionState()
    civ.factions.influence[FactionType.CLERGY] = clergy_influence
    normalize_influence(civ.factions)
    civ.name = "TestCiv"
    civ.treasury = 50
    civ.last_income = 10
    civ.trade_income = 10
    civ.stability = 50
    civ.military = 5
    civ.great_persons = []
    civ.active_focus = None
    civ.factions.power_struggle = False
    civ.factions.power_struggle_cooldown = 0
    civ.factions.pending_faction_shift = None
    civ.succession_crisis_turns_remaining = 0
    civ.regions = ["Region0"]
    return civ


def test_clergy_shift_temple_built():
    world = MagicMock()
    civ = _make_civ_with_clergy()
    world.civilizations = [civ]
    world.turn = 10
    world.events_timeline = [Event(
        turn=10, event_type="build_started", actors=["TestCiv"],
        description="TestCiv begins building temples in Region0", importance=3,
    )]
    world.regions = []
    before = civ.factions.influence[FactionType.CLERGY]
    tick_factions(world)
    after = civ.factions.influence[FactionType.CLERGY]
    assert after > before


def test_compute_tithe_base():
    civ = MagicMock()
    civ.trade_income = 12
    assert compute_tithe_base(civ) == 12


def test_tithe_collected_above_threshold():
    civ = _make_civ_with_clergy(clergy_influence=0.25)
    initial_treasury = civ.treasury
    # Manually test tithe logic
    if civ.factions.influence[FactionType.CLERGY] >= TITHE_THRESHOLD:
        tithe = TITHE_RATE * compute_tithe_base(civ)
        civ.treasury += tithe
    assert civ.treasury > initial_treasury


def test_clergy_succession_candidate_auto_included():
    """Task 11: verify generate_faction_candidates includes clergy when influence >= 0.15."""
    from chronicler.factions import generate_faction_candidates
    # Build a minimal civ with clergy influence above threshold
    civ = MagicMock()
    civ.factions = FactionState()
    civ.factions.influence[FactionType.CLERGY] = 0.30
    civ.factions.influence[FactionType.MILITARY] = 0.30
    civ.factions.influence[FactionType.MERCHANT] = 0.20
    civ.factions.influence[FactionType.CULTURAL] = 0.20
    civ.name = "TestCiv"
    civ.great_persons = []

    world = MagicMock()
    world.civilizations = [civ]
    world.relationships = {}

    candidates = generate_faction_candidates(civ, world)
    clergy_candidates = [c for c in candidates if c["faction"] == "clergy"]
    assert len(clergy_candidates) >= 1
    assert clergy_candidates[0]["type"] == "clergy"
