"""Tests for M55b spatial asabiya."""
import pytest
from chronicler.models import Region, RegionAsabiya, Civilization, CivSnapshot, Leader, TechEra


def test_region_asabiya_defaults():
    ra = RegionAsabiya()
    assert ra.asabiya == 0.5
    assert ra.frontier_fraction == 0.0
    assert ra.different_civ_count == 0
    assert ra.uncontrolled_count == 0


def test_region_has_asabiya_state():
    r = Region(name="Test", terrain="plains", carrying_capacity=60, resources="fertile")
    assert r.asabiya_state.asabiya == 0.5
    assert r.asabiya_state.frontier_fraction == 0.0


def test_civilization_has_asabiya_variance():
    civ = Civilization(
        name="Test", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50,
        leader=Leader(name="L", trait="cautious", reign_start=0),
    )
    assert civ.asabiya_variance == 0.0


def test_civ_snapshot_asabiya_variance_default():
    snap = CivSnapshot(
        population=50, military=30, economy=40, culture=30, stability=50,
        treasury=50, asabiya=0.5, tech_era=TechEra.IRON, trait="cautious",
        regions=["r1"], leader_name="L", alive=True,
    )
    assert snap.asabiya_variance == 0.0


# --- Frontier fraction tests ---

from chronicler.models import Region, WorldState, Relationship, RegionAsabiya
from chronicler.simulation import apply_asabiya_dynamics


def _make_region(name, controller=None, adjacencies=None):
    return Region(
        name=name, terrain="plains", carrying_capacity=60,
        resources="fertile", controller=controller, population=50,
        adjacencies=adjacencies or [],
    )


def _make_test_world(regions, civs=None):
    """Minimal WorldState for asabiya tests."""
    from chronicler.models import Civilization, Leader, TechEra
    if civs is None:
        civs = []
    return WorldState(
        name="Test", seed=42, turn=1,
        regions=regions, civilizations=civs, relationships={},
    )


def test_frontier_fraction_mixed_neighbors():
    """1 same-civ, 1 different-civ, 1 uncontrolled -> f = 2/3."""
    r_target = _make_region("Target", controller="A", adjacencies=["Same", "Enemy", "Wild"])
    r_same = _make_region("Same", controller="A")
    r_enemy = _make_region("Enemy", controller="B")
    r_wild = _make_region("Wild", controller=None)
    world = _make_test_world([r_target, r_same, r_enemy, r_wild])
    apply_asabiya_dynamics(world)
    assert r_target.asabiya_state.frontier_fraction == pytest.approx(2 / 3)
    assert r_target.asabiya_state.different_civ_count == 1
    assert r_target.asabiya_state.uncontrolled_count == 1


def test_frontier_fraction_all_same():
    """All same-civ neighbors -> f = 0.0 (pure interior)."""
    r = _make_region("Center", controller="A", adjacencies=["N1", "N2"])
    n1 = _make_region("N1", controller="A")
    n2 = _make_region("N2", controller="A")
    world = _make_test_world([r, n1, n2])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.frontier_fraction == 0.0


def test_frontier_fraction_all_foreign():
    """All different-civ neighbors -> f = 1.0."""
    r = _make_region("Center", controller="A", adjacencies=["E1", "E2"])
    e1 = _make_region("E1", controller="B")
    e2 = _make_region("E2", controller="C")
    world = _make_test_world([r, e1, e2])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.frontier_fraction == 1.0
    assert r.asabiya_state.different_civ_count == 2


def test_frontier_fraction_no_valid_neighbors():
    """Stale adjacency names not in region_map -> f = 0.0."""
    r = _make_region("Isolated", controller="A", adjacencies=["Ghost1", "Ghost2"])
    world = _make_test_world([r])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.frontier_fraction == 0.0


def test_frontier_fraction_uncontrolled_region_still_computed():
    """Uncontrolled regions get frontier fraction computed but asabiya not ticked."""
    r = _make_region("Wild", controller=None, adjacencies=["Owned"])
    owned = _make_region("Owned", controller="A")
    world = _make_test_world([r, owned])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.frontier_fraction == 1.0
    assert r.asabiya_state.asabiya == 0.5
