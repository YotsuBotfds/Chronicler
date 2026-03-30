//! M59a: Information packet substrate tests.

use chronicler_agents::{AgentPool, Occupation};
use chronicler_agents::knowledge::{
    pack_type_hops, unpack_type, unpack_hops, is_empty_slot, InfoType,
    channel_weight, decay_rate,
};
use chronicler_agents::relationships::BondType;

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

#[test]
fn test_pack_unpack_type_hops() {
    // ThreatWarning (1) with 5 hops
    let packed = pack_type_hops(1, 5);
    assert_eq!(unpack_type(packed), 1);
    assert_eq!(unpack_hops(packed), 5);

    // Empty (0) with 0 hops
    let packed = pack_type_hops(0, 0);
    assert_eq!(packed, 0);
    assert!(is_empty_slot(packed));

    // Max hop count (31)
    let packed = pack_type_hops(3, 31);
    assert_eq!(unpack_type(packed), 3);
    assert_eq!(unpack_hops(packed), 31);

    // Hop count overflow is masked to 5 bits
    let packed = pack_type_hops(1, 33); // 33 & 0x1F = 1
    assert_eq!(unpack_hops(packed), 1);
}

#[test]
fn test_retention_priority_order() {
    assert!(InfoType::ThreatWarning.retention_priority() > InfoType::TradeOpportunity.retention_priority());
    assert!(InfoType::TradeOpportunity.retention_priority() > InfoType::ReligiousSignal.retention_priority());
    assert!(InfoType::ReligiousSignal.retention_priority() > InfoType::Empty.retention_priority());
}

#[test]
fn test_channel_weight_filters() {
    // Threat: Mentor eligible, Rival not
    assert!(channel_weight(BondType::Mentor as u8, 1).is_some());
    assert!(channel_weight(BondType::Rival as u8, 1).is_none());
    assert!(channel_weight(BondType::Grudge as u8, 1).is_none());

    // Trade: Friend eligible, CoReligionist not
    assert!(channel_weight(BondType::Friend as u8, 2).is_some());
    assert!(channel_weight(BondType::CoReligionist as u8, 2).is_none());

    // Religious: CoReligionist eligible, Friend not
    assert!(channel_weight(BondType::CoReligionist as u8, 3).is_some());
    assert!(channel_weight(BondType::Friend as u8, 3).is_none());
}

#[test]
fn test_decay_rates() {
    assert_eq!(decay_rate(1), 15); // threat
    assert_eq!(decay_rate(2), 8);  // trade
    assert_eq!(decay_rate(3), 5);  // religious
    assert_eq!(decay_rate(0), 0);  // empty
}
