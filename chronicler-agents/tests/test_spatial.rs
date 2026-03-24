use chronicler_agents::spatial::{SpatialGrid, GRID_SIZE};
use chronicler_agents::spatial::{
    init_attractors, update_attractor_weights, AttractorType, MAX_ATTRACTORS,
    MIN_ATTRACTOR_SEPARATION, OCCUPATION_AFFINITY,
};
use chronicler_agents::RegionState;

#[test]
fn test_grid_insert_and_query() {
    let mut grid = SpatialGrid::new();
    grid.insert(0, 0.15, 0.15);  // cell (1, 1)
    grid.insert(1, 0.16, 0.16);  // cell (1, 1)
    grid.insert(2, 0.85, 0.85);  // cell (8, 8) — far away

    let neighbors = grid.query_neighbors(0.15, 0.15, 0);
    assert!(neighbors.contains(&1));
    assert!(!neighbors.contains(&0));  // self excluded
    assert!(!neighbors.contains(&2));  // far away
}

#[test]
fn test_grid_boundary_clamp() {
    let mut grid = SpatialGrid::new();
    grid.insert(0, 0.0, 0.0);     // cell (0, 0) — corner
    grid.insert(1, 0.05, 0.05);   // cell (0, 0) — same cell
    let neighbors = grid.query_neighbors(0.0, 0.0, 0);
    assert!(neighbors.contains(&1));
}

#[test]
fn test_grid_clear_reuse() {
    let mut grid = SpatialGrid::new();
    grid.insert(0, 0.5, 0.5);
    grid.clear();
    let neighbors = grid.query_neighbors(0.5, 0.5, 99);
    assert!(neighbors.is_empty());
    // Reinsert after clear:
    grid.insert(1, 0.5, 0.5);
    let neighbors = grid.query_neighbors(0.5, 0.5, 99);
    assert_eq!(neighbors, vec![1]);
}

#[test]
fn test_neighbors_sorted_by_slot() {
    let mut grid = SpatialGrid::new();
    grid.insert(5, 0.5, 0.5);
    grid.insert(2, 0.51, 0.51);
    grid.insert(9, 0.49, 0.49);
    let neighbors = grid.query_neighbors(0.5, 0.5, 99);
    assert_eq!(neighbors, vec![2, 5, 9]);  // sorted
}

#[test]
fn test_grid_cell_count() {
    let grid = SpatialGrid::new();
    assert_eq!(grid.cells.len(), GRID_SIZE * GRID_SIZE);
}

#[test]
fn test_negative_coords_clamp() {
    let mut grid = SpatialGrid::new();
    // Negative f32 coords: (-0.5 * 10.0) as usize = 0 (saturating since Rust 1.45+)
    // Then .min(GRID_SIZE - 1) = 0, so lands in cell (0, 0)
    grid.insert(0, -0.5, -0.5);
    // Should land in some cell without panicking
    let neighbors = grid.query_neighbors(0.0, 0.0, 99);
    assert!(neighbors.contains(&0));
}

#[test]
fn test_coords_at_one_clamp() {
    let mut grid = SpatialGrid::new();
    grid.insert(0, 1.0, 1.0);
    // x=1.0 -> (1.0 * 10) = 10 -> .min(9) = cell 9
    let neighbors = grid.query_neighbors(0.95, 0.95, 99);
    assert!(neighbors.contains(&0));
}

// ---------------------------------------------------------------------------
// Attractor model tests
// ---------------------------------------------------------------------------

fn make_test_region_with_features() -> RegionState {
    let mut r = RegionState::new(5);
    r.river_mask = 1;
    r.resource_effective_yield = [0.5, 0.3, 0.0];
    r.has_temple = true;
    r.is_capital = true;
    r.temple_prestige = 0.5;
    r
}

#[test]
fn test_attractor_determinism() {
    let region = make_test_region_with_features();
    let a1 = init_attractors(42, 5, &region);
    let a2 = init_attractors(42, 5, &region);
    assert_eq!(a1.count, a2.count);
    for i in 0..a1.count as usize {
        assert_eq!(a1.positions[i], a2.positions[i]);
        assert_eq!(a1.types[i], a2.types[i]);
    }
}

#[test]
fn test_attractor_separation() {
    // Region with many features to fill attractor slots
    let mut region = RegionState::new(0);
    region.river_mask = 1;
    region.terrain = 2; // Coast
    region.resource_effective_yield = [0.5, 0.3, 0.1];
    region.has_temple = true;
    region.is_capital = true;
    region.temple_prestige = 0.5;

    let a = init_attractors(42, 0, &region);
    // Should have 6 attractors: River, Coast, Resource0, Resource1, Resource2, Temple, Capital
    assert!(a.count >= 6, "Expected at least 6 attractors, got {}", a.count);
    // Check no two attractors closer than MIN_ATTRACTOR_SEPARATION
    for i in 0..a.count as usize {
        for j in (i + 1)..a.count as usize {
            let dx = a.positions[i].0 - a.positions[j].0;
            let dy = a.positions[i].1 - a.positions[j].1;
            let dist = (dx * dx + dy * dy).sqrt();
            // Allow small tolerance for separation enforcement
            assert!(
                dist >= MIN_ATTRACTOR_SEPARATION - 0.01,
                "Attractors {} ({:?}) and {} ({:?}) too close: {} (positions: {:?} vs {:?})",
                i,
                a.types[i],
                j,
                a.types[j],
                dist,
                a.positions[i],
                a.positions[j]
            );
        }
    }
}

#[test]
fn test_attractor_weight_dynamics() {
    let mut region = RegionState::new(0);
    region.resource_effective_yield = [0.8, 0.0, 0.0];
    region.river_mask = 1;
    region.water = 0.7;

    let mut a = init_attractors(42, 0, &region);
    update_attractor_weights(&mut a, &region);

    // Find resource0 attractor and check weight
    let res0_idx = (0..a.count as usize).find(|&i| a.types[i] == AttractorType::Resource0);
    assert!(res0_idx.is_some(), "Resource0 attractor should exist");
    assert!(
        a.weights[res0_idx.unwrap()] > 0.0,
        "Resource0 weight should be positive"
    );

    // Drop yield to 0
    region.resource_effective_yield[0] = 0.0;
    update_attractor_weights(&mut a, &region);
    assert!(
        (a.weights[res0_idx.unwrap()] - 0.0).abs() < f32::EPSILON,
        "Resource0 weight should be 0 after yield drops"
    );
}

#[test]
fn test_empty_region_no_attractors() {
    let region = RegionState::new(0); // all defaults
    let a = init_attractors(42, 0, &region);
    assert_eq!(a.count, 0, "Empty region should have no attractors");
}

#[test]
fn test_attractor_types_correct() {
    let region = make_test_region_with_features();
    let a = init_attractors(99, 5, &region);
    // Should have: River, Resource0, Resource1, Temple, Capital (5 active)
    // No Coast (terrain is Plains by default in make_test_region_with_features)
    let types: Vec<AttractorType> = (0..a.count as usize).map(|i| a.types[i]).collect();
    assert!(types.contains(&AttractorType::River));
    assert!(types.contains(&AttractorType::Resource0));
    assert!(types.contains(&AttractorType::Resource1));
    assert!(types.contains(&AttractorType::Temple));
    assert!(types.contains(&AttractorType::Capital));
    assert!(!types.contains(&AttractorType::Coast));
    assert!(!types.contains(&AttractorType::Resource2)); // yield is 0.0
    assert!(!types.contains(&AttractorType::Market)); // always inactive
}

#[test]
fn test_attractor_positions_in_bounds() {
    let mut region = RegionState::new(3);
    region.river_mask = 1;
    region.terrain = 2;
    region.resource_effective_yield = [1.0, 1.0, 1.0];
    region.has_temple = true;
    region.is_capital = true;
    region.temple_prestige = 0.8;

    // Test across multiple seeds
    for seed in [0u64, 1, 42, 999, u64::MAX] {
        let a = init_attractors(seed, 3, &region);
        for i in 0..a.count as usize {
            assert!(
                a.positions[i].0 >= 0.0 && a.positions[i].0 < 1.0,
                "seed={} idx={} x={} out of bounds",
                seed,
                i,
                a.positions[i].0
            );
            assert!(
                a.positions[i].1 >= 0.0 && a.positions[i].1 < 1.0,
                "seed={} idx={} y={} out of bounds",
                seed,
                i,
                a.positions[i].1
            );
        }
    }
}

#[test]
fn test_attractor_weight_river_tracks_water() {
    let mut region = RegionState::new(0);
    region.river_mask = 1;
    region.water = 0.3;

    let mut a = init_attractors(42, 0, &region);
    update_attractor_weights(&mut a, &region);

    let river_idx = (0..a.count as usize)
        .find(|&i| a.types[i] == AttractorType::River)
        .unwrap();
    assert!(
        (a.weights[river_idx] - 0.3).abs() < f32::EPSILON,
        "River weight should track water level"
    );

    region.water = 0.9;
    update_attractor_weights(&mut a, &region);
    assert!(
        (a.weights[river_idx] - 0.9).abs() < f32::EPSILON,
        "River weight should update with water"
    );
}

#[test]
fn test_attractor_weight_temple_fallback() {
    let mut region = RegionState::new(0);
    region.has_temple = true;
    region.temple_prestige = 0.0;

    let mut a = init_attractors(42, 0, &region);
    update_attractor_weights(&mut a, &region);

    let temple_idx = (0..a.count as usize)
        .find(|&i| a.types[i] == AttractorType::Temple)
        .unwrap();
    // has_temple=true and prestige=0 should give weight 1.0
    assert!(
        (a.weights[temple_idx] - 1.0).abs() < f32::EPSILON,
        "Temple with 0 prestige should have weight 1.0"
    );
}

#[test]
fn test_attractor_weight_capital_population_ratio() {
    let mut region = RegionState::new(0);
    region.is_capital = true;
    region.population = 30;
    region.carrying_capacity = 60;

    let mut a = init_attractors(42, 0, &region);
    update_attractor_weights(&mut a, &region);

    let cap_idx = (0..a.count as usize)
        .find(|&i| a.types[i] == AttractorType::Capital)
        .unwrap();
    assert!(
        (a.weights[cap_idx] - 0.5).abs() < f32::EPSILON,
        "Capital weight should be population/capacity ratio"
    );
}

#[test]
fn test_occupation_affinity_dimensions() {
    assert_eq!(OCCUPATION_AFFINITY.len(), 5);
    for row in &OCCUPATION_AFFINITY {
        assert_eq!(row.len(), MAX_ATTRACTORS);
    }
    // Market column should be 0 for all occupations
    for row in &OCCUPATION_AFFINITY {
        assert!(
            (row[AttractorType::Market as usize] - 0.0).abs() < f32::EPSILON,
            "Market affinity should be 0 for all occupations"
        );
    }
}

#[test]
fn test_different_seeds_different_positions() {
    let region = make_test_region_with_features();
    let a1 = init_attractors(42, 5, &region);
    let a2 = init_attractors(123, 5, &region);
    assert_eq!(a1.count, a2.count, "Same features should yield same count");
    // At least one attractor should differ in position
    let mut any_differ = false;
    for i in 0..a1.count as usize {
        if a1.positions[i] != a2.positions[i] {
            any_differ = true;
            break;
        }
    }
    assert!(any_differ, "Different seeds should produce different positions");
}

// ---------------------------------------------------------------------------
// Drift computation tests
// ---------------------------------------------------------------------------

use chronicler_agents::spatial::{
    compute_drift_for_agent, spatial_drift_step, migration_reset_position, newborn_position,
    rebuild_spatial_grids, RegionAttractors, MAX_DRIFT_PER_TICK, MIGRATION_JITTER, BIRTH_JITTER,
};
use chronicler_agents::AgentPool;
use chronicler_agents::Occupation;

fn make_pool_with_agents(positions: &[(u16, f32, f32, u8)]) -> AgentPool {
    let mut pool = AgentPool::new(positions.len());
    for &(region, x, y, occ) in positions {
        let occ_val = Occupation::from_u8(occ).unwrap_or(Occupation::Farmer);
        let slot = pool.spawn(region, 0, occ_val, 20, 0.0, 0.0, 0.0, 0xFF, 0xFF, 0xFF, 0xFF);
        pool.x[slot] = x;
        pool.y[slot] = y;
    }
    pool
}

fn make_single_resource_attractors(x: f32, y: f32) -> RegionAttractors {
    let mut att = RegionAttractors {
        positions: [(0.0, 0.0); MAX_ATTRACTORS],
        weights: [0.0; MAX_ATTRACTORS],
        types: [AttractorType::Market; MAX_ATTRACTORS],
        count: 1,
    };
    att.positions[0] = (x, y);
    att.weights[0] = 1.0;
    att.types[0] = AttractorType::Resource0;
    att
}

#[test]
fn test_drift_convergence() {
    // Place one farmer agent far from a single Resource0 attractor, no neighbors.
    // Run drift for 20 iterations (rebuild grid + drift step each time).
    // Verify agent moved closer to attractor.
    let attractor_pos = (0.8, 0.8);
    let agent_start = (0.2, 0.2);

    let mut pool = make_pool_with_agents(&[(0, agent_start.0, agent_start.1, 0)]); // Farmer
    let attractors_list = vec![make_single_resource_attractors(attractor_pos.0, attractor_pos.1)];
    let mut grids: Vec<SpatialGrid> = Vec::new();

    let initial_dx = attractor_pos.0 - agent_start.0;
    let initial_dy = attractor_pos.1 - agent_start.1;
    let initial_dist = (initial_dx * initial_dx + initial_dy * initial_dy).sqrt();

    for _ in 0..20 {
        rebuild_spatial_grids(&pool, &mut grids, 1);
        spatial_drift_step(&mut pool, &grids, &attractors_list);
    }

    let final_dx = attractor_pos.0 - pool.x[0];
    let final_dy = attractor_pos.1 - pool.y[0];
    let final_dist = (final_dx * final_dx + final_dy * final_dy).sqrt();

    assert!(
        final_dist < initial_dist,
        "Agent should move closer to attractor: initial_dist={}, final_dist={}",
        initial_dist, final_dist
    );
}

#[test]
fn test_repulsion_separates_colocated() {
    // Place two agents at identical position. Run one drift step.
    // Verify they are now at different positions.
    let mut pool = make_pool_with_agents(&[
        (0, 0.5, 0.5, 0), // Farmer
        (0, 0.5, 0.5, 0), // Farmer — same position
    ]);

    // Use an empty attractor set so only repulsion acts
    let attractors_list = vec![RegionAttractors {
        positions: [(0.0, 0.0); MAX_ATTRACTORS],
        weights: [0.0; MAX_ATTRACTORS],
        types: [AttractorType::Market; MAX_ATTRACTORS],
        count: 0,
    }];
    let mut grids: Vec<SpatialGrid> = Vec::new();
    rebuild_spatial_grids(&pool, &mut grids, 1);
    spatial_drift_step(&mut pool, &grids, &attractors_list);

    let different = pool.x[0] != pool.x[1] || pool.y[0] != pool.y[1];
    assert!(
        different,
        "Colocated agents should separate after one drift step: ({}, {}) vs ({}, {})",
        pool.x[0], pool.y[0], pool.x[1], pool.y[1]
    );
}

#[test]
fn test_drift_displacement_cap() {
    // Place agent very far from a strong attractor.
    // Verify single-step displacement <= MAX_DRIFT_PER_TICK + epsilon.
    let attractor_pos = (0.95, 0.95);
    let agent_start = (0.05, 0.05);

    let attractors = make_single_resource_attractors(attractor_pos.0, attractor_pos.1);
    let neighbor_positions: Vec<(u32, f32, f32)> = vec![];

    let (new_x, new_y) = compute_drift_for_agent(
        agent_start.0,
        agent_start.1,
        0, // Farmer
        1, // agent_id
        &attractors,
        &neighbor_positions,
    );

    let dx = new_x - agent_start.0;
    let dy = new_y - agent_start.1;
    let displacement = (dx * dx + dy * dy).sqrt();

    let epsilon = 1e-6;
    assert!(
        displacement <= MAX_DRIFT_PER_TICK + epsilon,
        "Displacement {} exceeds MAX_DRIFT_PER_TICK {}",
        displacement, MAX_DRIFT_PER_TICK
    );
}

#[test]
fn test_migration_reset_near_attractor() {
    // Create attractors with a Resource0 attractor.
    // Reset a Farmer agent -> should land near the Resource0 attractor.
    let attractor_pos = (0.7, 0.3);
    let attractors = make_single_resource_attractors(attractor_pos.0, attractor_pos.1);

    let master_seed = [42u8; 32];
    let (x, y) = migration_reset_position(
        1,    // agent_id
        0,    // Farmer occupation
        &attractors,
        &master_seed,
        0,    // dest_region_id
        10,   // turn
    );

    let dx = x - attractor_pos.0;
    let dy = y - attractor_pos.1;
    let dist = (dx * dx + dy * dy).sqrt();

    // Should be within MIGRATION_JITTER * sqrt(2) of attractor
    let max_dist = MIGRATION_JITTER * 2.0_f32.sqrt() + 1e-6;
    assert!(
        dist <= max_dist,
        "Migration reset at ({}, {}) is too far from attractor at {:?}: dist={} > max={}",
        x, y, attractor_pos, dist, max_dist
    );
}

#[test]
fn test_newborn_near_parent() {
    // Place newborn near parent position. Verify within BIRTH_JITTER range.
    let parent_pos = (0.5, 0.5);
    let master_seed = [7u8; 32];
    let (x, y) = newborn_position(
        100,  // child_id
        0,    // region_id
        parent_pos,
        &master_seed,
        5,    // turn
    );

    let dx = x - parent_pos.0;
    let dy = y - parent_pos.1;
    let dist = (dx * dx + dy * dy).sqrt();

    let max_dist = BIRTH_JITTER * 2.0_f32.sqrt() + 1e-6;
    assert!(
        dist <= max_dist,
        "Newborn at ({}, {}) is too far from parent at {:?}: dist={} > max={}",
        x, y, parent_pos, dist, max_dist
    );
}
