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
    assert_eq!(a.count, 1, "Empty region should have 1 attractor (Market, always active)");
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
    assert!(types.contains(&AttractorType::Market)); // M58a: always active
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
fn test_interior_positions_can_reach_upper_half() {
    let mut region = RegionState::new(2);
    region.resource_effective_yield = [1.0, 0.0, 0.0];

    let mut saw_upper = false;
    for seed in 0u64..128 {
        let a = init_attractors(seed, 2, &region);
        let idx = (0..a.count as usize).find(|&i| a.types[i] == AttractorType::Resource0);
        if let Some(i) = idx {
            let (x, y) = a.positions[i];
            if x > 0.65 || y > 0.65 {
                saw_upper = true;
                break;
            }
        }
    }

    assert!(
        saw_upper,
        "Interior attractor positions should span into the upper half of [0.1, 0.9]"
    );
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
    // Market column: Merchant (idx 2) has 0.4, all others have 0.0
    let market_col = AttractorType::Market as usize;
    for (occ_idx, row) in OCCUPATION_AFFINITY.iter().enumerate() {
        if occ_idx == 2 {
            // Merchant — M58a activated Market affinity
            assert!(
                (row[market_col] - 0.4).abs() < f32::EPSILON,
                "Merchant Market affinity should be 0.4"
            );
        } else {
            assert!(
                (row[market_col] - 0.0).abs() < f32::EPSILON,
                "Non-Merchant occupation {} Market affinity should be 0",
                occ_idx
            );
        }
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
    rebuild_spatial_grids, RegionAttractors, SpatialDiagnostics, MAX_DRIFT_PER_TICK,
    MIGRATION_JITTER, BIRTH_JITTER,
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

    let mut diag = SpatialDiagnostics::default();
    for _ in 0..20 {
        rebuild_spatial_grids(&pool, &mut grids, 1);
        spatial_drift_step(&mut pool, &grids, &attractors_list, &mut diag);
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
    let mut diag = SpatialDiagnostics::default();
    rebuild_spatial_grids(&pool, &mut grids, 1);
    spatial_drift_step(&mut pool, &grids, &attractors_list, &mut diag);

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

// ---------------------------------------------------------------------------
// Determinism + integration gate tests (M55a Task 10)
// ---------------------------------------------------------------------------

use chronicler_agents::sort::sort_by_morton;

/// Two identical pools run through the same drift steps must produce
/// bit-identical (x, y) positions. Tests determinism of the two-pass
/// drift + force computation.
#[test]
fn test_spatial_drift_determinism() {
    // 10 agents across 2 regions, varied occupations
    let agent_defs: [(u16, f32, f32, u8); 10] = [
        (0, 0.10, 0.20, 0), // Farmer
        (0, 0.30, 0.40, 1), // Soldier
        (0, 0.50, 0.60, 2), // Merchant
        (0, 0.70, 0.80, 3), // Scholar
        (0, 0.90, 0.10, 4), // Priest
        (1, 0.15, 0.25, 0),
        (1, 0.35, 0.45, 1),
        (1, 0.55, 0.65, 2),
        (1, 0.75, 0.85, 3),
        (1, 0.95, 0.05, 4),
    ];

    // Build two region states with attractors
    let mut r0 = RegionState::new(0);
    r0.river_mask = 1;
    r0.resource_effective_yield = [0.5, 0.3, 0.0];
    r0.water = 0.6;
    let mut r1 = RegionState::new(1);
    r1.is_capital = true;
    r1.resource_effective_yield = [0.0, 0.4, 0.2];
    r1.population = 30;
    r1.carrying_capacity = 60;

    let att0 = init_attractors(42, 0, &r0);
    let att1 = init_attractors(42, 1, &r1);
    let attractors_list = vec![att0, att1];

    // Run A
    let mut pool_a = make_pool_with_agents(&agent_defs);
    let mut grids_a: Vec<SpatialGrid> = Vec::new();
    let mut diag_a = SpatialDiagnostics::default();
    for _ in 0..5 {
        rebuild_spatial_grids(&pool_a, &mut grids_a, 2);
        spatial_drift_step(&mut pool_a, &grids_a, &attractors_list, &mut diag_a);
    }

    // Run B — identical setup
    let mut pool_b = make_pool_with_agents(&agent_defs);
    let mut grids_b: Vec<SpatialGrid> = Vec::new();
    let mut diag_b = SpatialDiagnostics::default();
    for _ in 0..5 {
        rebuild_spatial_grids(&pool_b, &mut grids_b, 2);
        spatial_drift_step(&mut pool_b, &grids_b, &attractors_list, &mut diag_b);
    }

    // Bit-exact comparison
    for slot in 0..10 {
        assert!(
            pool_a.x[slot].to_bits() == pool_b.x[slot].to_bits(),
            "x mismatch at slot {}: {} vs {}",
            slot, pool_a.x[slot], pool_b.x[slot]
        );
        assert!(
            pool_a.y[slot].to_bits() == pool_b.y[slot].to_bits(),
            "y mismatch at slot {}: {} vs {}",
            slot, pool_a.y[slot], pool_b.y[slot]
        );
    }
}

/// Same seed/agent_id/region/attractors called twice must produce
/// identical migration reset positions.
#[test]
fn test_migration_reset_determinism() {
    let attractor_pos = (0.6, 0.4);
    let attractors = make_single_resource_attractors(attractor_pos.0, attractor_pos.1);
    let master_seed = [99u8; 32];

    let (x1, y1) = migration_reset_position(7, 0, &attractors, &master_seed, 3, 15);
    let (x2, y2) = migration_reset_position(7, 0, &attractors, &master_seed, 3, 15);

    assert!(
        x1.to_bits() == x2.to_bits() && y1.to_bits() == y2.to_bits(),
        "migration_reset_position not deterministic: ({}, {}) vs ({}, {})",
        x1, y1, x2, y2
    );
}

/// Verify that if a parent dies and its slot is reused, newborn placement
/// still works correctly because it uses a snapshot of the parent position
/// taken before the death pass — not the live pool slot.
#[test]
fn test_parent_death_newborn_placement_safety() {
    let mut pool = AgentPool::new(4);

    // Spawn parent at a known position
    let parent_slot = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0xFF, 0xFF, 0xFF, 0xFF);
    pool.x[parent_slot] = 0.7;
    pool.y[parent_slot] = 0.3;
    let parent_id = pool.ids[parent_slot];
    let parent_pos = (pool.x[parent_slot], pool.y[parent_slot]);

    // Kill parent — slot goes to free-list
    pool.kill(parent_slot);

    // Spawn a different agent that reuses the parent's slot
    let reused_slot = pool.spawn(1, 1, Occupation::Soldier, 20, 0.0, 0.0, 0.0, 0xFF, 0xFF, 0xFF, 0xFF);
    // Free-list reuse: reused_slot should be the old parent_slot
    assert_eq!(reused_slot, parent_slot, "Expected slot reuse from free-list");
    // The reused slot now has different position
    pool.x[reused_slot] = 0.1;
    pool.y[reused_slot] = 0.9;

    // Place newborn using the SNAPSHOT of parent position (not the live slot)
    let master_seed = [42u8; 32];
    let child_id = parent_id + 10;
    let (bx, by) = newborn_position(child_id, 0, parent_pos, &master_seed, 5);

    // Newborn should be near the ORIGINAL parent position (0.7, 0.3),
    // not near the reused slot's position (0.1, 0.9)
    let dx_parent = bx - parent_pos.0;
    let dy_parent = by - parent_pos.1;
    let dist_to_parent = (dx_parent * dx_parent + dy_parent * dy_parent).sqrt();

    let dx_reused = bx - pool.x[reused_slot];
    let dy_reused = by - pool.y[reused_slot];
    let dist_to_reused = (dx_reused * dx_reused + dy_reused * dy_reused).sqrt();

    let max_dist = BIRTH_JITTER * 2.0_f32.sqrt() + 1e-6;
    assert!(
        dist_to_parent <= max_dist,
        "Newborn at ({}, {}) should be near parent's original pos {:?}, dist={} > max={}",
        bx, by, parent_pos, dist_to_parent, max_dist
    );
    // Sanity: it should be far from the reused slot's new position
    assert!(
        dist_to_reused > max_dist,
        "Newborn should NOT be near the reused slot's new position ({}, {}), dist={}",
        pool.x[reused_slot], pool.y[reused_slot], dist_to_reused
    );
}

/// Full tick_agents with spatial data: two runs with identical inputs must
/// produce bit-identical (x, y) for all alive agents.
#[test]
fn test_full_tick_with_spatial_determinism() {
    use chronicler_agents::{tick_agents, CivSignals, TickSignals};

    let mut seed = [0u8; 32];
    seed[0] = 42;

    // Set up regions with spatial features
    let mut r0 = RegionState::new(0);
    r0.population = 20;
    r0.carrying_capacity = 40;
    r0.soil = 0.6;
    r0.water = 0.5;
    r0.river_mask = 1;
    r0.resource_effective_yield = [0.5, 0.2, 0.0];

    let mut r1 = RegionState::new(1);
    r1.population = 15;
    r1.carrying_capacity = 30;
    r1.soil = 0.5;
    r1.water = 0.4;
    r1.is_capital = true;
    r1.resource_effective_yield = [0.3, 0.0, 0.1];

    let regions = vec![r0, r1];

    let signals = TickSignals {
        civs: vec![CivSignals {
            civ_id: 0,
            stability: 50,
            is_at_war: false,
            dominant_faction: 0,
            faction_military: 0.25,
            faction_merchant: 0.35,
            faction_cultural: 0.25,
            shock_stability: 0.0,
            shock_economy: 0.0,
            shock_military: 0.0,
            shock_culture: 0.0,
            demand_shift_farmer: 0.0,
            demand_shift_soldier: 0.0,
            demand_shift_merchant: 0.0,
            demand_shift_scholar: 0.0,
            demand_shift_priest: 0.0,
            mean_boldness: 0.0,
            mean_ambition: 0.0,
            mean_loyalty_trait: 0.0,
            faction_clergy: 0.0,
            gini_coefficient: 0.0,
            conquered_this_turn: false,
            priest_tithe_share: 0.0,
            cultural_drift_multiplier: 1.0,
            religion_intensity_multiplier: 1.0,
        }],
        contested_regions: vec![false, false],
    };

    // Build attractors for the regions
    let att0 = init_attractors(42, 0, &regions[0]);
    let att1 = init_attractors(42, 1, &regions[1]);
    let attractors = vec![att0, att1];

    // Helper to create a pool, run 3 ticks, return alive (x, y) pairs
    let run = || {
        let mut pool = AgentPool::new(0);
        for r in &regions {
            for _ in 0..r.population {
                pool.spawn(
                    r.region_id, 0, Occupation::Farmer, 20,
                    0.0, 0.0, 0.0, 0xFF, 0xFF, 0xFF, 0xFF,
                );
            }
        }
        let mut percentiles = vec![0.0f32; pool.capacity()];
        let mut grids: Vec<SpatialGrid> = Vec::new();
        let mut diag = SpatialDiagnostics::default();
        for turn in 0..3u32 {
            if percentiles.len() < pool.capacity() {
                percentiles.resize(pool.capacity(), 0.0);
            }
            tick_agents(
                &mut pool, &regions, &signals, seed, turn,
                &mut percentiles, &mut grids, &attractors, &mut diag, &[], None,
            );
        }
        // Collect alive agent (id, x_bits, y_bits) for deterministic comparison
        let mut results: Vec<(u32, u32, u32)> = Vec::new();
        for slot in 0..pool.capacity() {
            if pool.is_alive(slot) {
                results.push((
                    pool.ids[slot],
                    pool.x[slot].to_bits(),
                    pool.y[slot].to_bits(),
                ));
            }
        }
        results.sort_by_key(|r| r.0);
        results
    };

    let run_a = run();
    let run_b = run();

    assert!(!run_a.is_empty(), "Should have alive agents after 3 ticks");
    assert_eq!(
        run_a.len(), run_b.len(),
        "Alive count differs: {} vs {}", run_a.len(), run_b.len()
    );
    for (i, (a, b)) in run_a.iter().zip(run_b.iter()).enumerate() {
        assert_eq!(
            a, b,
            "Agent mismatch at index {}: id={} ({:#010x}, {:#010x}) vs id={} ({:#010x}, {:#010x})",
            i, a.0, a.1, a.2, b.0, b.1, b.2
        );
    }
}

/// sort_by_morton is deterministic: two calls on the same pool produce
/// identical ordering.
#[test]
fn test_sort_by_morton_determinism() {
    let mut pool = AgentPool::new(8);
    // Scatter agents at different positions in the same region
    let positions = [
        (0.9, 0.1), (0.1, 0.9), (0.5, 0.5), (0.3, 0.7),
        (0.7, 0.3), (0.2, 0.2), (0.8, 0.8), (0.4, 0.6),
    ];
    for &(x, y) in &positions {
        let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0xFF, 0xFF, 0xFF, 0xFF);
        pool.x[slot] = x;
        pool.y[slot] = y;
    }

    let order1 = sort_by_morton(&pool);
    let order2 = sort_by_morton(&pool);
    assert_eq!(order1, order2, "sort_by_morton should be deterministic");
    assert_eq!(order1.len(), 8, "All 8 agents should appear in sort output");
}
