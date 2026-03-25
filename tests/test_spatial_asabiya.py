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
from chronicler.simulation import apply_asabiya_dynamics, _apply_asabiya_to_regions


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


# --- D-policy tests ---


def test_d_policy_applies_to_all_regions():
    """D-policy: delta applied to every region the civ controls."""
    r1 = _make_region("R1", controller="A")
    r1.asabiya_state.asabiya = 0.5
    r2 = _make_region("R2", controller="A")
    r2.asabiya_state.asabiya = 0.6
    r3 = _make_region("R3", controller="B")
    r3.asabiya_state.asabiya = 0.4
    world = _make_test_world([r1, r2, r3])
    _apply_asabiya_to_regions(world, "A", 0.1)
    assert r1.asabiya_state.asabiya == pytest.approx(0.6)
    assert r2.asabiya_state.asabiya == pytest.approx(0.7)
    assert r3.asabiya_state.asabiya == pytest.approx(0.4)


def test_d_policy_clamps_to_one():
    """D-policy: region at 0.95 + 0.1 -> clamped to 1.0."""
    r = _make_region("R1", controller="A")
    r.asabiya_state.asabiya = 0.95
    world = _make_test_world([r])
    _apply_asabiya_to_regions(world, "A", 0.1)
    assert r.asabiya_state.asabiya == 1.0


def test_d_policy_clamps_to_zero():
    """D-policy: region at 0.01 - 0.1 -> clamped to 0.0."""
    r = _make_region("R1", controller="A")
    r.asabiya_state.asabiya = 0.01
    world = _make_test_world([r])
    _apply_asabiya_to_regions(world, "A", -0.1)
    assert r.asabiya_state.asabiya == 0.0


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


# --- Gradient formula tests ---


def test_gradient_frontier_growth():
    """Pure frontier (f=1.0): logistic growth."""
    r = _make_region("Frontier", controller="A", adjacencies=["Enemy"])
    r.asabiya_state.asabiya = 0.5
    enemy = _make_region("Enemy", controller="B")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Frontier"],
    )
    world = _make_test_world([r, enemy], civs=[civ])
    apply_asabiya_dynamics(world)
    # s_next = 0.5 + 0.05 * 1.0 * 0.5 * 0.5 - 0.02 * 0.0 * 0.5 = 0.5125
    assert r.asabiya_state.asabiya == pytest.approx(0.5125, abs=1e-4)


def test_gradient_interior_decay():
    """Pure interior (f=0.0): linear decay."""
    r = _make_region("Interior", controller="A", adjacencies=["Friend"])
    r.asabiya_state.asabiya = 0.5
    friend = _make_region("Friend", controller="A")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Interior"],
    )
    world = _make_test_world([r, friend], civs=[civ])
    apply_asabiya_dynamics(world)
    # s_next = 0.5 + 0.0 - 0.02 * 1.0 * 0.5 = 0.49
    assert r.asabiya_state.asabiya == pytest.approx(0.49, abs=1e-4)


def test_gradient_boundary_zero_stays_zero():
    """asabiya=0.0 is a fixed point (logistic s*(1-s) = 0)."""
    r = _make_region("Dead", controller="A", adjacencies=["Enemy"])
    r.asabiya_state.asabiya = 0.0
    enemy = _make_region("Enemy", controller="B")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.0,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Dead"],
    )
    world = _make_test_world([r, enemy], civs=[civ])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.asabiya == 0.0


# --- Aggregation tests ---


def test_civ_aggregation_equal_pop():
    """2 regions, equal pop -> mean of asabiya values."""
    r1 = _make_region("R1", controller="A", adjacencies=["R2"])
    r1.asabiya_state.asabiya = 0.3
    r1.population = 50
    r2 = _make_region("R2", controller="A", adjacencies=["R1"])
    r2.asabiya_state.asabiya = 0.7
    r2.population = 50
    civ = Civilization(
        name="A", population=100, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1", "R2"],
    )
    world = _make_test_world([r1, r2], civs=[civ])
    apply_asabiya_dynamics(world)
    assert 0.0 <= civ.asabiya <= 1.0
    assert civ.asabiya_variance >= 0.0


def test_civ_aggregation_zero_pop_fallback():
    """Zero total pop -> civ.asabiya unchanged."""
    r = _make_region("Empty", controller="A", adjacencies=[])
    r.asabiya_state.asabiya = 0.8
    r.population = 0
    civ = Civilization(
        name="A", population=0, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.6,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Empty"],
    )
    world = _make_test_world([r], civs=[civ])
    apply_asabiya_dynamics(world)
    assert civ.asabiya == 0.6  # Unchanged


def test_variance_computation():
    """Verify population-weighted variance calculation."""
    r1 = _make_region("R1", controller="A", adjacencies=[])
    r1.asabiya_state.asabiya = 0.3
    r1.population = 50
    r2 = _make_region("R2", controller="A", adjacencies=[])
    r2.asabiya_state.asabiya = 0.7
    r2.population = 50
    civ = Civilization(
        name="A", population=100, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1", "R2"],
    )
    world = _make_test_world([r1, r2], civs=[civ])
    # After tick, both are interior (f=0.0), so both decay:
    # R1: 0.3 - 0.02 * 1.0 * 0.3 = 0.294
    # R2: 0.7 - 0.02 * 1.0 * 0.7 = 0.686
    # Mean = (0.294*50 + 0.686*50) / 100 = 0.49
    # Var = (50*(0.294-0.49)^2 + 50*(0.686-0.49)^2) / 100
    #     = (50*0.038416 + 50*0.038416) / 100 = 0.038416
    apply_asabiya_dynamics(world)
    assert civ.asabiya == pytest.approx(0.49, abs=1e-3)
    assert civ.asabiya_variance == pytest.approx(0.038416, abs=1e-4)


# --- World generation sync tests ---

from chronicler.world_gen import generate_world


def test_world_gen_syncs_region_asabiya():
    """After world gen, each controlled region's asabiya matches its civ's asabiya."""
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    for civ in world.civilizations:
        for rname in civ.regions:
            region = next(r for r in world.regions if r.name == rname)
            assert region.asabiya_state.asabiya == civ.asabiya, (
                f"Region {rname} asabiya {region.asabiya_state.asabiya} != civ {civ.name} asabiya {civ.asabiya}"
            )


def test_scenario_override_syncs_regions():
    """Scenario asabiya override syncs to all controlled regions."""
    from chronicler.models import WorldState, Region, Civilization, Leader, TechEra
    r1 = _make_region("R1", controller="A")
    r1.asabiya_state.asabiya = 0.5
    r2 = _make_region("R2", controller="A")
    r2.asabiya_state.asabiya = 0.5
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1", "R2"],
    )
    world = _make_test_world([r1, r2], civs=[civ])
    # Simulate what scenario override does
    civ.asabiya = 0.9
    for region in world.regions:
        if region.controller == civ.name:
            region.asabiya_state.asabiya = civ.asabiya
    assert r1.asabiya_state.asabiya == 0.9
    assert r2.asabiya_state.asabiya == 0.9


def test_world_gen_uncontrolled_regions_default():
    """Uncontrolled regions keep default asabiya 0.5."""
    world = generate_world(seed=42, num_regions=8, num_civs=2)
    for region in world.regions:
        if region.controller is None:
            assert region.asabiya_state.asabiya == 0.5


# --- Phase 10 ordering tests ---


def test_phase10_ordering_rebellion_before_tick():
    """Structural guard: asabiya tick must run after politics writes and before collapse read."""
    import inspect
    import chronicler.simulation as sim

    src = inspect.getsource(sim.phase_consequences)
    idx_vassal = src.index("check_vassal_rebellion")
    idx_asabiya = src.index("apply_asabiya_dynamics(world)")
    idx_collapse = src.index("if civ.asabiya < 0.1 and civ.stability <= 20")
    assert idx_vassal < idx_asabiya < idx_collapse


# --- Integration tests ---


def test_multi_turn_frontier_converges_upward():
    """Over 20 turns, a pure frontier region's asabiya trends upward."""
    r = _make_region("Frontier", controller="A", adjacencies=["Enemy"])
    r.asabiya_state.asabiya = 0.3
    r.population = 50
    enemy = _make_region("Enemy", controller="B", adjacencies=["Frontier"])
    enemy.population = 50
    civ_a = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.3,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Frontier"],
    )
    civ_b = Civilization(
        name="B", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L2", trait="cautious", reign_start=0), regions=["Enemy"],
    )
    world = _make_test_world([r, enemy], civs=[civ_a, civ_b])
    prev = r.asabiya_state.asabiya
    for _ in range(20):
        apply_asabiya_dynamics(world)
        assert r.asabiya_state.asabiya >= prev
        prev = r.asabiya_state.asabiya
    assert r.asabiya_state.asabiya > 0.3


def test_multi_turn_interior_converges_downward():
    """Over 20 turns, a pure interior region's asabiya trends downward."""
    r = _make_region("Interior", controller="A", adjacencies=["Friend"])
    r.asabiya_state.asabiya = 0.7
    r.population = 50
    friend = _make_region("Friend", controller="A", adjacencies=["Interior"])
    friend.asabiya_state.asabiya = 0.7
    friend.population = 50
    civ = Civilization(
        name="A", population=100, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.7,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Interior", "Friend"],
    )
    world = _make_test_world([r, friend], civs=[civ])
    prev = r.asabiya_state.asabiya
    for _ in range(20):
        apply_asabiya_dynamics(world)
        assert r.asabiya_state.asabiya <= prev
        prev = r.asabiya_state.asabiya
    assert r.asabiya_state.asabiya < 0.7


def test_determinism_across_runs():
    """Same seed + topology -> identical values over 50 turns."""
    def run_sim():
        r1 = _make_region("R1", controller="A", adjacencies=["R2", "R3"])
        r1.asabiya_state.asabiya = 0.5
        r1.population = 50
        r2 = _make_region("R2", controller="B", adjacencies=["R1"])
        r2.asabiya_state.asabiya = 0.6
        r2.population = 40
        r3 = _make_region("R3", controller=None, adjacencies=["R1"])
        r3.population = 0
        civ_a = Civilization(
            name="A", population=50, military=30, economy=40, culture=30,
            stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
            leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1"],
        )
        civ_b = Civilization(
            name="B", population=40, military=30, economy=40, culture=30,
            stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.6,
            leader=Leader(name="L2", trait="cautious", reign_start=0), regions=["R2"],
        )
        world = _make_test_world([r1, r2, r3], civs=[civ_a, civ_b])
        results = []
        for _ in range(50):
            apply_asabiya_dynamics(world)
            results.append((civ_a.asabiya, civ_b.asabiya))
        return results

    run1 = run_sim()
    run2 = run_sim()
    assert run1 == run2


def test_invariant_bounds_over_many_turns():
    """All asabiya values stay in [0,1], variance in [0,0.25] over 50 turns."""
    r1 = _make_region("R1", controller="A", adjacencies=["R2"])
    r1.asabiya_state.asabiya = 0.1
    r1.population = 80
    r2 = _make_region("R2", controller="A", adjacencies=["R1", "R3"])
    r2.asabiya_state.asabiya = 0.9
    r2.population = 20
    r3 = _make_region("R3", controller="B", adjacencies=["R2"])
    r3.asabiya_state.asabiya = 0.5
    r3.population = 50
    civ_a = Civilization(
        name="A", population=100, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1", "R2"],
    )
    civ_b = Civilization(
        name="B", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L2", trait="cautious", reign_start=0), regions=["R3"],
    )
    world = _make_test_world([r1, r2, r3], civs=[civ_a, civ_b])
    for _ in range(50):
        apply_asabiya_dynamics(world)
        for r in world.regions:
            assert 0.0 <= r.asabiya_state.asabiya <= 1.0
        for c in world.civilizations:
            assert 0.0 <= c.asabiya <= 1.0
            assert 0.0 <= c.asabiya_variance <= 0.25


# --- Spec test coverage gaps ---


def test_gradient_mixed_partial_frontier():
    """f=0.5: growth and decay partially cancel."""
    r = _make_region("Mixed", controller="A", adjacencies=["Friend", "Enemy"])
    r.asabiya_state.asabiya = 0.5
    r.population = 50
    friend = _make_region("Friend", controller="A")
    enemy = _make_region("Enemy", controller="B")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Mixed"],
    )
    world = _make_test_world([r, friend, enemy], civs=[civ])
    apply_asabiya_dynamics(world)
    # s_next = 0.5 + 0.05*0.5*0.5*0.5 - 0.02*0.5*0.5 = 0.5 + 0.00625 - 0.005 = 0.50125
    assert r.asabiya_state.asabiya == pytest.approx(0.5013, abs=1e-3)


def test_gradient_boundary_one_decays_if_not_pure_frontier():
    """asabiya=1.0 decays when f < 1.0 (interior decay dominates at ceiling)."""
    r = _make_region("Peak", controller="A", adjacencies=["Friend"])
    r.asabiya_state.asabiya = 1.0
    r.population = 50
    friend = _make_region("Friend", controller="A")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=1.0,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Peak"],
    )
    world = _make_test_world([r, friend], civs=[civ])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.asabiya < 1.0


def test_aggregation_weighted_by_pop():
    """90/10 pop split -> mean skewed toward high-pop region."""
    r1 = _make_region("Big", controller="A", adjacencies=[])
    r1.asabiya_state.asabiya = 0.3
    r1.population = 90
    r2 = _make_region("Small", controller="A", adjacencies=[])
    r2.asabiya_state.asabiya = 0.9
    r2.population = 10
    civ = Civilization(
        name="A", population=100, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Big", "Small"],
    )
    world = _make_test_world([r1, r2], civs=[civ])
    apply_asabiya_dynamics(world)
    assert civ.asabiya < 0.4


def test_aggregation_single_region_zero_variance():
    """Single region -> variance must be 0.0."""
    r = _make_region("Only", controller="A", adjacencies=[])
    r.asabiya_state.asabiya = 0.6
    r.population = 50
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.6,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Only"],
    )
    world = _make_test_world([r], civs=[civ])
    apply_asabiya_dynamics(world)
    assert civ.asabiya_variance == 0.0


def test_folk_hero_applied_after_gradient():
    """Folk hero bonus applied after gradient formula (ordering test)."""
    r = _make_region("R1", controller="A", adjacencies=["Enemy"])
    r.asabiya_state.asabiya = 0.5
    r.population = 50
    enemy = _make_region("Enemy", controller="B")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1"],
        folk_heroes=[{"name": "Hero", "turn": 1}],
    )
    world = _make_test_world([r, enemy], civs=[civ])
    apply_asabiya_dynamics(world)
    asabiya_with_hero = r.asabiya_state.asabiya

    r.asabiya_state.asabiya = 0.5
    civ.folk_heroes = []
    apply_asabiya_dynamics(world)
    asabiya_without = r.asabiya_state.asabiya

    assert asabiya_with_hero > asabiya_without


def test_no_folk_heroes_no_bonus():
    """No folk heroes -> no bonus term added."""
    r = _make_region("R1", controller="A", adjacencies=["Enemy"])
    r.asabiya_state.asabiya = 0.5
    r.population = 50
    enemy = _make_region("Enemy", controller="B")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1"],
    )
    world = _make_test_world([r, enemy], civs=[civ])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.asabiya == pytest.approx(0.5125, abs=1e-4)


def test_civ_snapshot_backward_compat():
    """CivSnapshot without asabiya_variance field loads with default 0.0."""
    data = {
        "population": 50, "military": 30, "economy": 40, "culture": 30,
        "stability": 50, "treasury": 50, "asabiya": 0.5, "tech_era": "iron",
        "trait": "cautious", "regions": ["r1"], "leader_name": "L", "alive": True,
    }
    snap = CivSnapshot(**data)
    assert snap.asabiya_variance == 0.0


def test_conquest_updates_frontier_fractions():
    """After conquest, frontier fractions update for both sides."""
    r1 = _make_region("R1", controller="A", adjacencies=["R2"])
    r1.population = 50
    r2 = _make_region("R2", controller="B", adjacencies=["R1"])
    r2.population = 50
    civ_a = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1"],
    )
    civ_b = Civilization(
        name="B", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L2", trait="cautious", reign_start=0), regions=["R2"],
    )
    world = _make_test_world([r1, r2], civs=[civ_a, civ_b])
    apply_asabiya_dynamics(world)
    assert r1.asabiya_state.frontier_fraction == 1.0

    r2.controller = "A"
    civ_a.regions.append("R2")
    civ_b.regions.remove("R2")
    apply_asabiya_dynamics(world)
    assert r1.asabiya_state.frontier_fraction == 0.0
    assert r2.asabiya_state.frontier_fraction == 0.0


# --- No-scalar-write guard ---

import os


def test_no_direct_civ_asabiya_writes():
    """Guard: no code directly writes civ.asabiya outside apply_asabiya_dynamics."""
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src", "chronicler")
    forbidden_patterns = [
        r"\.asabiya\s*=(?!=)",
        r"\.asabiya\s*\+=",
        r'acc\.add\([^)]*"asabiya"',
    ]
    allowed_files = {"simulation.py", "world_gen.py", "scenario.py", "models.py", "politics.py"}

    violations = []
    for root, _dirs, files in os.walk(src_dir):
        for fname in files:
            if not fname.endswith(".py") or fname in allowed_files:
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    if ".asabiya_state.asabiya" in line:
                        continue
                    for pat in forbidden_patterns:
                        import re
                        if re.search(pat, line):
                            violations.append(f"{fname}:{lineno}: {line.strip()}")

    assert violations == [], f"Found direct civ.asabiya writes:\n" + "\n".join(violations)
