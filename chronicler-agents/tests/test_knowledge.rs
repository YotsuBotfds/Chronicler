//! M59a: Information packet substrate tests.

use chronicler_agents::{AgentPool, Occupation};

#[test]
fn test_spawn_has_empty_packets() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    for i in 0..4 {
        assert_eq!(pool.pkt_type_and_hops[slot][i], 0, "slot {i} type_and_hops should be 0");
        assert_eq!(pool.pkt_source_region[slot][i], 0, "slot {i} source_region should be 0");
        assert_eq!(pool.pkt_source_turn[slot][i], 0, "slot {i} source_turn should be 0");
        assert_eq!(pool.pkt_intensity[slot][i], 0, "slot {i} intensity should be 0");
    }
    assert!(!pool.arrived_this_turn[slot], "arrived_this_turn should be false on spawn");
}
