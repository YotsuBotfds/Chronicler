//! M59a: Information packet substrate tests.

use chronicler_agents::{AgentPool, Occupation};
use chronicler_agents::knowledge::{
    pack_type_hops, unpack_type, unpack_hops, is_empty_slot, InfoType,
    channel_weight, decay_rate,
    admit_packet, AdmitResult, PacketCandidate,
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

#[test]
fn test_admit_into_empty_slots() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 5, source_turn: 10, intensity: 200, hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Inserted);
    assert_eq!(unpack_type(pool.pkt_type_and_hops[slot][0]), 1);
    assert_eq!(pool.pkt_source_region[slot][0], 5);
    assert_eq!(pool.pkt_intensity[slot][0], 200);
}

#[test]
fn test_refresh_same_identity_newer_turn() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Insert initial
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 5, source_turn: 10, intensity: 150, hop_count: 3,
    });
    // Refresh with newer turn
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 5, source_turn: 12, intensity: 180, hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Refreshed);
    assert_eq!(pool.pkt_source_turn[slot][0], 12);
    assert_eq!(pool.pkt_intensity[slot][0], 180);
    assert_eq!(unpack_hops(pool.pkt_type_and_hops[slot][0]), 0);
}

#[test]
fn test_drop_same_identity_older_turn() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 5, source_turn: 12, intensity: 200, hop_count: 0,
    });
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 5, source_turn: 10, intensity: 250, hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Dropped);
    assert_eq!(pool.pkt_source_turn[slot][0], 12); // unchanged
}

#[test]
fn test_same_turn_keeps_higher_intensity() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 3, source_turn: 10, intensity: 100, hop_count: 2,
    });
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 3, source_turn: 10, intensity: 150, hop_count: 1,
    });
    assert_eq!(result, AdmitResult::Refreshed);
    assert_eq!(pool.pkt_intensity[slot][0], 150);
}

#[test]
fn test_same_turn_same_intensity_keeps_lower_hops() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 3, source_turn: 10, intensity: 100, hop_count: 5,
    });
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 3, source_turn: 10, intensity: 100, hop_count: 2,
    });
    assert_eq!(result, AdmitResult::Refreshed);
    assert_eq!(unpack_hops(pool.pkt_type_and_hops[slot][0]), 2);
}

#[test]
fn test_evict_stalest_when_full() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Fill all 4 slots with different identities
    for i in 0..4u16 {
        admit_packet(&mut pool, slot, &PacketCandidate {
            info_type: 1, source_region: i, source_turn: 10 + i, intensity: 200, hop_count: 0,
        });
    }

    // New packet at turn 15 — should evict the stalest (region 0, turn 10)
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 99, source_turn: 15, intensity: 100, hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Evicted);
    // Region 0 should be gone
    let has_region_0 = (0..4).any(|i| pool.pkt_source_region[slot][i] == 0);
    assert!(!has_region_0, "stalest packet (region 0) should have been evicted");
}

#[test]
fn test_admission_guard_drops_stale_incoming() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Fill with fresh packets at turn 20
    for i in 0..4u16 {
        admit_packet(&mut pool, slot, &PacketCandidate {
            info_type: 1, source_region: i, source_turn: 20, intensity: 200, hop_count: 0,
        });
    }

    // Stale incoming at turn 5 should be dropped
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 3, source_region: 99, source_turn: 5, intensity: 250, hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Dropped);
}
