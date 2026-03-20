use chronicler_agents::AgentPool;
use chronicler_agents::Occupation;

#[test]
fn test_needs_spawn_at_starting_value() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    assert!((pool.need_safety[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_material[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_social[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_spiritual[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_autonomy[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_purpose[slot] - 0.5).abs() < 0.001);
}

#[test]
fn test_needs_reuse_reset() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_safety[slot] = 0.1;
    pool.need_purpose[slot] = 0.9;
    pool.kill(slot);
    let slot2 = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    assert_eq!(slot, slot2);
    assert!((pool.need_safety[slot2] - 0.5).abs() < 0.001);
    assert!((pool.need_purpose[slot2] - 0.5).abs() < 0.001);
}
