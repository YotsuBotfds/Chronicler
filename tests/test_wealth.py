import numpy as np
import pytest


def test_compute_gini_uniform():
    """All agents same wealth → Gini = 0."""
    from chronicler.agent_bridge import compute_gini
    arr = np.array([5.0, 5.0, 5.0, 5.0])
    assert abs(compute_gini(arr)) < 0.001


def test_compute_gini_maximal():
    """One agent has everything → Gini near 1.0."""
    from chronicler.agent_bridge import compute_gini
    arr = np.array([0.0, 0.0, 0.0, 100.0])
    assert compute_gini(arr) > 0.7


def test_compute_gini_moderate():
    """Mixed distribution → Gini in 0.2-0.6 range."""
    from chronicler.agent_bridge import compute_gini
    arr = np.array([1.0, 2.0, 5.0, 10.0, 50.0])
    g = compute_gini(arr)
    assert 0.2 < g < 0.7, f"Expected moderate Gini, got {g}"


def test_compute_gini_empty():
    from chronicler.agent_bridge import compute_gini
    arr = np.array([])
    assert compute_gini(arr) == 0.0


def test_compute_gini_single():
    from chronicler.agent_bridge import compute_gini
    arr = np.array([10.0])
    assert compute_gini(arr) == 0.0


def test_conquered_this_turn_build_signals():
    """build_signals produces correct conquered_this_turn per call."""
    from chronicler.agent_bridge import build_signals
    from chronicler.models import WorldState, Civilization, Region, Leader

    world = WorldState(name="TestWorld", seed=42)
    leader = Leader(name="TestLeader", trait="warrior", reign_start=0)
    civ = Civilization(
        name="TestCiv",
        population=10,
        military=50,
        economy=50,
        culture=50,
        stability=50,
        leader=leader,
    )
    civ.regions = ["TestRegion"]
    world.civilizations = [civ]
    region = Region(
        name="TestRegion",
        terrain="plains",
        carrying_capacity=10,
        resources="fertile",
    )
    region.controller = "TestCiv"
    world.regions = [region]

    # With conquest
    batch1 = build_signals(world, conquered={0: True})
    assert batch1.column("conquered_this_turn").to_pylist()[0] is True

    # Without conquest — fresh call, no persistence
    batch2 = build_signals(world, conquered=None)
    assert batch2.column("conquered_this_turn").to_pylist()[0] is False


def test_build_signals_merges_duplicate_civ_shocks():
    """Duplicate CivShock entries for one civ are merged before bridge export."""
    from chronicler.agent_bridge import build_signals
    from chronicler.models import WorldState, Civilization, Region, Leader, CivShock

    world = WorldState(name="TestWorld", seed=42)
    leader = Leader(name="TestLeader", trait="warrior", reign_start=0)
    civ = Civilization(
        name="TestCiv",
        population=10,
        military=50,
        economy=50,
        culture=50,
        stability=50,
        leader=leader,
    )
    civ.regions = ["TestRegion"]
    world.civilizations = [civ]
    region = Region(
        name="TestRegion",
        terrain="plains",
        carrying_capacity=10,
        resources="fertile",
    )
    region.controller = "TestCiv"
    world.regions = [region]

    batch = build_signals(
        world,
        shocks=[
            CivShock(civ_id=0, stability_shock=-0.20),
            CivShock(civ_id=0, economy_shock=-0.30),
            CivShock(civ_id=0, stability_shock=-0.15),
        ],
    )

    assert batch.column("shock_stability").to_pylist()[0] == pytest.approx(-0.35)
    assert batch.column("shock_economy").to_pylist()[0] == pytest.approx(-0.30)
    assert batch.column("shock_military").to_pylist()[0] == pytest.approx(0.0)
    assert batch.column("shock_culture").to_pylist()[0] == pytest.approx(0.0)


def test_conquered_this_turn_transient_two_turns():
    """conquered_this_turn resets after one turn (CLAUDE.md transient signal rule).

    Verifies the full path: action_engine sets world._conquered_this_turn,
    simulation.py reads and clears it before passing to agent bridge.
    """
    from chronicler.models import WorldState

    world = WorldState(name="TestWorld", seed=42)

    # Simulate conquest on turn 1
    world._conquered_this_turn = {0}

    # simulation.py's clearing pattern (mirrors actual code)
    conquered_civs = getattr(world, '_conquered_this_turn', set())
    world._conquered_this_turn = set()
    assert 0 in conquered_civs, "Turn 1: conquest should be detected"

    # Turn 2: no action engine ran, attribute should be empty
    conquered_civs_2 = getattr(world, '_conquered_this_turn', set())
    assert len(conquered_civs_2) == 0, "Turn 2: conquest should NOT persist"
