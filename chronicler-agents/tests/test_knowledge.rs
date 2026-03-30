//! M59a: Information packet substrate tests.

use chronicler_agents::{AgentPool, Occupation};
use chronicler_agents::knowledge::{
    pack_type_hops, unpack_type, unpack_hops, is_empty_slot, InfoType,
    channel_weight, decay_rate, decay_packets,
    admit_packet, AdmitResult, PacketCandidate,
    observe_packets,
    propagate_packets, commit_buffered,
};
use chronicler_agents::RegionState;
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

#[test]
fn test_decay_reduces_intensity() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 1, intensity: 200, hop_count: 0,
    });

    let expired = decay_packets(&mut pool, &[slot]);
    assert_eq!(expired, 0);
    assert_eq!(pool.pkt_intensity[slot][0], 200 - 15); // threat decay = 15
}

#[test]
fn test_decay_clears_expired_packet() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Insert with low intensity that will expire on first decay
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 1, intensity: 10, hop_count: 0,
    });

    let expired = decay_packets(&mut pool, &[slot]);
    assert_eq!(expired, 1);
    assert!(is_empty_slot(pool.pkt_type_and_hops[slot][0]));
    assert_eq!(pool.pkt_intensity[slot][0], 0);
    assert_eq!(pool.pkt_source_region[slot][0], 0);
    assert_eq!(pool.pkt_source_turn[slot][0], 0);
}

#[test]
fn test_decay_rates_differ_by_type() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Insert one of each type
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 1, intensity: 100, hop_count: 0,
    });
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 1, source_turn: 1, intensity: 100, hop_count: 0,
    });
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 3, source_region: 2, source_turn: 1, intensity: 100, hop_count: 0,
    });

    decay_packets(&mut pool, &[slot]);

    assert_eq!(pool.pkt_intensity[slot][0], 85);  // 100 - 15 (threat)
    assert_eq!(pool.pkt_intensity[slot][1], 92);  // 100 - 8 (trade)
    assert_eq!(pool.pkt_intensity[slot][2], 95);  // 100 - 5 (religious)
}

// ---------------------------------------------------------------------------
// Direct observation tests
// ---------------------------------------------------------------------------

#[test]
fn test_observe_threat_from_controller_change() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_changed_this_turn = true;

    let (created, _, created_threat, _, _) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 1);
    assert_eq!(created_threat, 1);
    assert_eq!(unpack_type(pool.pkt_type_and_hops[slot][0]), InfoType::ThreatWarning as u8);
    assert_eq!(pool.pkt_intensity[slot][0], 200);
    assert_eq!(pool.pkt_source_turn[slot][0], 5);
    assert_eq!(unpack_hops(pool.pkt_type_and_hops[slot][0]), 0);
}

#[test]
fn test_observe_threat_uses_max_intensity() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_changed_this_turn = true; // 200
    regions[0].war_won_this_turn = true;             // 180
    regions[0].seceded_this_turn = true;             // 150

    observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(pool.pkt_intensity[slot][0], 200);
}

#[test]
fn test_observe_trade_requires_arrival_and_margin() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions = vec![RegionState::new(0)];
    regions[0].merchant_route_margin = 0.5;

    // No arrival flag — should not emit
    let (created, _, _, _, _) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 0);

    // Set arrival flag
    pool.arrived_this_turn[slot] = true;
    let (created, _, _, created_trade, _) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 1);
    assert_eq!(created_trade, 1);
}

#[test]
fn test_observe_trade_below_margin_threshold_no_packet() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.arrived_this_turn[slot] = true;

    let mut regions = vec![RegionState::new(0)];
    regions[0].merchant_route_margin = 0.05; // below 0.10 threshold

    let (created, _, _, _, _) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 0);
}

#[test]
fn test_observe_religious_from_persecution() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions = vec![RegionState::new(0)];
    regions[0].persecution_intensity = 0.5;

    let (created, _, _, _, created_religious) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 1);
    assert_eq!(created_religious, 1);
    assert_eq!(unpack_type(pool.pkt_type_and_hops[slot][0]), InfoType::ReligiousSignal as u8);
}

// ---------------------------------------------------------------------------
// Propagation + commit tests
// ---------------------------------------------------------------------------

/// Helper: set up a relationship bond between two agents.
fn set_bond(pool: &mut AgentPool, from_slot: usize, to_id: u32, bond_type: u8, sentiment: i8) {
    let idx = pool.rel_count[from_slot] as usize;
    pool.rel_target_ids[from_slot][idx] = to_id;
    pool.rel_bond_types[from_slot][idx] = bond_type;
    pool.rel_sentiments[from_slot][idx] = sentiment;
    pool.rel_formed_turns[from_slot][idx] = 0;
    pool.rel_count[from_slot] += 1;
}

#[test]
fn test_propagation_one_hop() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let a_id = pool.ids[a];
    let b_id = pool.ids[b];

    admit_packet(&mut pool, a, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 5, intensity: 200, hop_count: 0,
    });

    set_bond(&mut pool, a, b_id, 5, 127); // Kin, max sentiment

    let lookup: std::collections::HashMap<u32, usize> =
        vec![(a_id, a), (b_id, b)].into_iter().collect();

    let (buffer, transmitted, t_threat, _, _) =
        propagate_packets(&pool, &[a, b], &[0u8; 32], 6, &lookup);

    assert!(transmitted > 0, "should have transmitted at least one packet");
    assert!(t_threat > 0, "should have transmitted a threat packet");

    commit_buffered(&mut pool, buffer);

    let b_has_threat = (0..4).any(|i| {
        unpack_type(pool.pkt_type_and_hops[b][i]) == 1
            && pool.pkt_source_region[b][i] == 0
            && unpack_hops(pool.pkt_type_and_hops[b][i]) == 1
    });
    assert!(b_has_threat, "B should have received threat packet with hop=1");
}

#[test]
fn test_propagation_one_hop_per_turn() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let c = pool.spawn(2, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let a_id = pool.ids[a];
    let b_id = pool.ids[b];
    let c_id = pool.ids[c];

    admit_packet(&mut pool, a, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 5, intensity: 200, hop_count: 0,
    });

    set_bond(&mut pool, a, b_id, 5, 127);
    set_bond(&mut pool, b, c_id, 5, 127);

    let lookup: std::collections::HashMap<u32, usize> =
        vec![(a_id, a), (b_id, b), (c_id, c)].into_iter().collect();

    let (buffer, _, _, _, _) = propagate_packets(&pool, &[a, b, c], &[0u8; 32], 6, &lookup);
    commit_buffered(&mut pool, buffer);

    let b_has = (0..4).any(|i| unpack_type(pool.pkt_type_and_hops[b][i]) == 1);
    let c_has = (0..4).any(|i| unpack_type(pool.pkt_type_and_hops[c][i]) == 1);
    assert!(b_has, "B should have the packet after turn 1");
    assert!(!c_has, "C should NOT have the packet after turn 1 (one-hop-per-turn)");
}

#[test]
fn test_hop_count_31_halts_propagation() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let a_id = pool.ids[a];
    let b_id = pool.ids[b];

    admit_packet(&mut pool, a, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 5, intensity: 200, hop_count: 31,
    });

    set_bond(&mut pool, a, b_id, 5, 127);

    let lookup: std::collections::HashMap<u32, usize> =
        vec![(a_id, a), (b_id, b)].into_iter().collect();

    let (buffer, transmitted, _, _, _) = propagate_packets(&pool, &[a, b], &[0u8; 32], 6, &lookup);
    assert_eq!(transmitted, 0, "should not transmit at max hops");
    assert!(buffer.is_empty());
}

#[test]
fn test_propagation_channel_filtering() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let a_id = pool.ids[a];
    let b_id = pool.ids[b];

    admit_packet(&mut pool, a, &PacketCandidate {
        info_type: 3, source_region: 0, source_turn: 5, intensity: 200, hop_count: 0,
    });

    set_bond(&mut pool, a, b_id, 6, 127); // Friend -- not eligible for religious

    let lookup: std::collections::HashMap<u32, usize> =
        vec![(a_id, a), (b_id, b)].into_iter().collect();

    let (_, transmitted, _, _, _) = propagate_packets(&pool, &[a, b], &[0u8; 32], 6, &lookup);
    assert_eq!(transmitted, 0, "Friend bond should not carry religious signal");
}

// ---------------------------------------------------------------------------
// Knowledge phase orchestrator tests
// ---------------------------------------------------------------------------

use chronicler_agents::knowledge::knowledge_phase;

#[test]
fn test_knowledge_phase_full_cycle() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let b_id = pool.ids[b];

    let mut regions = vec![RegionState::new(0), RegionState::new(1)];
    regions[0].controller_changed_this_turn = true;

    // A -> B: Kin bond
    set_bond(&mut pool, a, b_id, 5, 127);

    let stats = knowledge_phase(&mut pool, &regions, &[0u8; 32], 5);

    assert!(stats.packets_created > 0, "should have created packets");
    assert!(stats.live_packet_count > 0, "should have live packets");
    assert!(stats.agents_with_packets > 0, "should have agents with packets");
}

#[test]
fn test_knowledge_phase_clears_arrival_flag() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.arrived_this_turn[a] = true;

    let regions = vec![RegionState::new(0)];
    knowledge_phase(&mut pool, &regions, &[0u8; 32], 5);

    assert!(!pool.arrived_this_turn[a], "arrived_this_turn should be cleared after knowledge phase");
}

#[test]
fn test_knowledge_phase_zero_fill_no_packets() {
    let mut pool = AgentPool::new(10);
    pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let regions = vec![RegionState::new(0)];
    // No triggers — no packets
    let stats = knowledge_phase(&mut pool, &regions, &[0u8; 32], 5);

    assert_eq!(stats.live_packet_count, 0);
    assert_eq!(stats.agents_with_packets, 0);
    assert_eq!(stats.mean_age, 0.0);
    assert_eq!(stats.max_age, 0);
}
