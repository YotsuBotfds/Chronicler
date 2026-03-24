use chronicler_agents::spatial::{SpatialGrid, GRID_SIZE};

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
