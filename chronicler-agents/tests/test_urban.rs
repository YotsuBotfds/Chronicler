//! M56b: Urban effects tests

use chronicler_agents::{AgentPool, Occupation, assign_settlement_ids, build_settlement_grids};

#[test]
fn test_grid_construction_basic() {
    let grids = build_settlement_grids(
        2,
        &[0, 0],
        &[1, 1],
        &[3, 4],
        &[7, 7],
    );
    assert_eq!(grids.len(), 2);
    assert_eq!(grids[0][7 * 10 + 3], 1);
    assert_eq!(grids[0][7 * 10 + 4], 1);
    assert_eq!(grids[0][0], 0);
    assert_eq!(grids[1][0], 0);
}

#[test]
fn test_grid_tiebreak_lowest_id_wins() {
    let grids = build_settlement_grids(
        1,
        &[0, 0],
        &[2, 5],
        &[3, 3],
        &[7, 7],
    );
    assert_eq!(grids[0][7 * 10 + 3], 2);
}

#[test]
fn test_assignment_basic() {
    let mut pool = AgentPool::new(4);
    let s0 = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let s1 = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.x[s0] = 0.35;
    pool.y[s0] = 0.72;
    pool.x[s1] = 0.95;
    pool.y[s1] = 0.95;

    let grids = build_settlement_grids(1, &[0], &[1], &[3], &[7]);
    assign_settlement_ids(&mut pool, &grids);

    assert_eq!(pool.settlement_ids[s0], 1);
    assert_eq!(pool.settlement_ids[s1], 0);
}
