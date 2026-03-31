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
fn test_admission_guard_drops_equal_rank_incoming() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    for i in 0..4u16 {
        admit_packet(&mut pool, slot, &PacketCandidate {
            info_type: InfoType::TradeOpportunity as u8,
            source_region: i,
            source_turn: 20,
            intensity: 120,
            hop_count: 0,
        });
    }

    let before_regions = pool.pkt_source_region[slot];
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: InfoType::TradeOpportunity as u8,
        source_region: 99,
        source_turn: 20,
        intensity: 180,
        hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Dropped);
    assert_eq!(pool.pkt_source_region[slot], before_regions, "equal-rank incoming should not evict");
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

    let (created, _, _, _, created_threat, _, _) = observe_packets(&mut pool, &regions, &[slot], 5);
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
    let (created, _, _, _, _, _, _) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 0);

    // Set arrival flag
    pool.arrived_this_turn[slot] = true;
    let (created, _, _, _, _, created_trade, _) = observe_packets(&mut pool, &regions, &[slot], 5);
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

    let (created, _, _, _, _, _, _) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 0);
}

#[test]
fn test_observe_religious_from_persecution() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions = vec![RegionState::new(0)];
    regions[0].persecution_intensity = 0.5;

    let (created, _, _, _, _, _, created_religious) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 1);
    assert_eq!(created_religious, 1);
    assert_eq!(unpack_type(pool.pkt_type_and_hops[slot][0]), InfoType::ReligiousSignal as u8);
}

#[test]
fn test_observe_eviction_counts_as_created_and_evicted() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    for i in 0..4u16 {
        admit_packet(&mut pool, slot, &PacketCandidate {
            info_type: InfoType::ReligiousSignal as u8,
            source_region: i,
            source_turn: 5,
            intensity: 100,
            hop_count: 0,
        });
    }

    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_changed_this_turn = true;

    let (created, refreshed, evicted, dropped, created_threat, _, _) =
        observe_packets(&mut pool, &regions, &[slot], 10);

    assert_eq!(created, 1);
    assert_eq!(refreshed, 0);
    assert_eq!(evicted, 1);
    assert_eq!(dropped, 0);
    assert_eq!(created_threat, 1);
    assert!(
        (0..4).any(|i| {
            unpack_type(pool.pkt_type_and_hops[slot][i]) == InfoType::ThreatWarning as u8
                && pool.pkt_source_region[slot][i] == 0
                && pool.pkt_source_turn[slot][i] == 10
        }),
        "freshly observed threat should replace the stalest incumbent",
    );
}

#[test]
fn test_observe_drop_counts_when_full_and_not_better() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.arrived_this_turn[slot] = true;

    for i in 0..4u16 {
        admit_packet(&mut pool, slot, &PacketCandidate {
            info_type: InfoType::ThreatWarning as u8,
            source_region: i,
            source_turn: 20,
            intensity: 200,
            hop_count: 0,
        });
    }

    let mut regions = vec![RegionState::new(0)];
    regions[0].merchant_route_margin = 0.5;

    let (created, refreshed, evicted, dropped, _, created_trade, _) =
        observe_packets(&mut pool, &regions, &[slot], 20);

    assert_eq!(created, 0);
    assert_eq!(refreshed, 0);
    assert_eq!(evicted, 0);
    assert_eq!(dropped, 1);
    assert_eq!(created_trade, 0);
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

// ---------------------------------------------------------------------------
// Determinism + compatibility tests
// ---------------------------------------------------------------------------

#[test]
fn test_knowledge_phase_deterministic_same_process() {
    let seed = [42u8; 32];

    let run = || {
        let mut pool = AgentPool::new(10);
        let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let c = pool.spawn(2, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

        let b_id = pool.ids[b];
        let c_id = pool.ids[c];

        set_bond(&mut pool, a, b_id, 5, 100);
        set_bond(&mut pool, b, c_id, 6, 80);

        let mut regions = vec![RegionState::new(0), RegionState::new(1), RegionState::new(2)];
        regions[0].controller_changed_this_turn = true;
        regions[0].persecution_intensity = 0.5;

        let stats1 = knowledge_phase(&mut pool, &regions, &seed, 1);
        regions[0].controller_changed_this_turn = false;
        let stats2 = knowledge_phase(&mut pool, &regions, &seed, 2);

        (stats1, stats2, pool.pkt_type_and_hops.clone(), pool.pkt_intensity.clone())
    };

    let (s1a, s2a, th_a, int_a) = run();
    let (s1b, s2b, th_b, int_b) = run();

    assert_eq!(s1a.packets_created, s1b.packets_created);
    assert_eq!(s1a.packets_transmitted, s1b.packets_transmitted);
    assert_eq!(s2a.packets_transmitted, s2b.packets_transmitted);
    assert_eq!(th_a, th_b, "packet state should be identical across runs");
    assert_eq!(int_a, int_b, "intensity state should be identical across runs");
}

#[test]
fn test_knowledge_phase_packet_state_deterministic() {
    let seed = [42u8; 32];

    let run = || {
        let mut pool = AgentPool::new(10);
        let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let c = pool.spawn(2, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

        let b_id = pool.ids[b];
        let c_id = pool.ids[c];

        set_bond(&mut pool, a, b_id, 5, 100);
        set_bond(&mut pool, b, c_id, 6, 80);
        set_bond(&mut pool, a, c_id, 4, 60);

        let mut regions = vec![RegionState::new(0), RegionState::new(1), RegionState::new(2)];
        regions[0].controller_changed_this_turn = true;
        regions[0].persecution_intensity = 0.5;
        regions[1].merchant_route_margin = 0.4;

        for t in 1..=3u32 {
            if t > 1 { regions[0].controller_changed_this_turn = false; }
            knowledge_phase(&mut pool, &regions, &seed, t);
        }

        (
            pool.pkt_type_and_hops.clone(),
            pool.pkt_source_region.clone(),
            pool.pkt_source_turn.clone(),
            pool.pkt_intensity.clone(),
        )
    };

    let (th_a, sr_a, st_a, int_a) = run();
    let (th_b, sr_b, st_b, int_b) = run();

    assert_eq!(th_a, th_b, "pkt_type_and_hops diverged");
    assert_eq!(sr_a, sr_b, "pkt_source_region diverged");
    assert_eq!(st_a, st_b, "pkt_source_turn diverged");
    assert_eq!(int_a, int_b, "pkt_intensity diverged");
}

#[test]
fn test_propagation_independent_of_rel_slot_order() {
    let seed = [99u8; 32];

    let run = |first_bond: u8, second_bond: u8| {
        let mut pool = AgentPool::new(10);
        let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

        let b_id = pool.ids[b];

        admit_packet(&mut pool, a, &PacketCandidate {
            info_type: 1, source_region: 0, source_turn: 5, intensity: 200, hop_count: 0,
        });

        set_bond(&mut pool, a, b_id, first_bond, 100);
        set_bond(&mut pool, a, b_id, second_bond, 100);

        let lookup: std::collections::HashMap<u32, usize> =
            vec![(pool.ids[a], a), (pool.ids[b], b)].into_iter().collect();

        let (buffer, transmitted, _, _, _) = propagate_packets(&pool, &[a, b], &seed, 6, &lookup);
        (transmitted, buffer.len())
    };

    let (t1, b1) = run(5, 6); // Kin first, Friend second
    let (t2, b2) = run(6, 5); // Friend first, Kin second
    assert_eq!(t1, t2, "transmitted count should be independent of slot order");
    assert_eq!(b1, b2, "buffer size should be independent of slot order");
}

// ---------------------------------------------------------------------------
// Behavioral inertia: knowledge_phase must not modify non-packet fields
// ---------------------------------------------------------------------------

#[test]
fn test_knowledge_phase_does_not_modify_non_packet_fields() {
    let seed = [42u8; 32];
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.arrived_this_turn[b] = true;

    let b_id = pool.ids[b];
    set_bond(&mut pool, a, b_id, 5, 100);

    pool.satisfactions[a] = 0.75;
    pool.loyalties[a] = 0.6;
    pool.wealth[a] = 50.0;
    pool.need_safety[a] = 0.8;

    let mut regions = vec![RegionState::new(0), RegionState::new(1)];
    regions[0].controller_changed_this_turn = true;
    regions[0].persecution_intensity = 0.5;
    regions[1].merchant_route_margin = 0.5;

    // Snapshot ALL non-packet pool fields before knowledge_phase
    let ids_before = pool.ids.clone();
    let regions_before = pool.regions.clone();
    let origin_regions_before = pool.origin_regions.clone();
    let civ_before = pool.civ_affinities.clone();
    let occ_before = pool.occupations.clone();
    let loy_before = pool.loyalties.clone();
    let sat_before = pool.satisfactions.clone();
    let skills_before = pool.skills.clone();
    let ages_before = pool.ages.clone();
    let disp_before = pool.displacement_turns.clone();
    let life_events_before = pool.life_events.clone();
    let promo_before = pool.promotion_progress.clone();
    let bold_before = pool.boldness.clone();
    let ambi_before = pool.ambition.clone();
    let loy_trait_before = pool.loyalty_trait.clone();
    let cv0_before = pool.cultural_value_0.clone();
    let cv1_before = pool.cultural_value_1.clone();
    let cv2_before = pool.cultural_value_2.clone();
    let beliefs_before = pool.beliefs.clone();
    let p0_before = pool.parent_id_0.clone();
    let p1_before = pool.parent_id_1.clone();
    let wealth_before = pool.wealth.clone();
    let mem_et_before = pool.memory_event_types.clone();
    let mem_sc_before = pool.memory_source_civs.clone();
    let mem_t_before = pool.memory_turns.clone();
    let mem_i_before = pool.memory_intensities.clone();
    let mem_df_before = pool.memory_decay_factors.clone();
    let mem_g_before = pool.memory_gates.clone();
    let mem_c_before = pool.memory_count.clone();
    let mem_l_before = pool.memory_is_legacy.clone();
    let ns_before = pool.need_safety.clone();
    let nm_before = pool.need_material.clone();
    let nso_before = pool.need_social.clone();
    let nsp_before = pool.need_spiritual.clone();
    let na_before = pool.need_autonomy.clone();
    let np_before = pool.need_purpose.clone();
    let rt_before = pool.rel_target_ids.clone();
    let rs_before = pool.rel_sentiments.clone();
    let rb_before = pool.rel_bond_types.clone();
    let rf_before = pool.rel_formed_turns.clone();
    let rc_before = pool.rel_count.clone();
    let syn_before = pool.synthesis_budget.clone();
    let x_before = pool.x.clone();
    let y_before = pool.y.clone();
    let sid_before = pool.settlement_ids.clone();
    let tp_before = pool.trip_phase.clone();
    let tdr_before = pool.trip_dest_region.clone();
    let tor_before = pool.trip_origin_region.clone();
    let tgs_before = pool.trip_good_slot.clone();
    let tcq_before = pool.trip_cargo_qty.clone();
    let tte_before = pool.trip_turns_elapsed.clone();
    let tpath_before = pool.trip_path.clone();
    let tpl_before = pool.trip_path_len.clone();
    let tpc_before = pool.trip_path_cursor.clone();
    let alive_before = pool.alive.clone();

    let stats = knowledge_phase(&mut pool, &regions, &seed, 5);

    assert!(stats.packets_created > 0, "knowledge_phase should have created packets");

    // Verify ALL non-packet fields are unchanged
    assert_eq!(pool.ids, ids_before, "ids modified");
    assert_eq!(pool.regions, regions_before, "regions modified");
    assert_eq!(pool.origin_regions, origin_regions_before, "origin_regions modified");
    assert_eq!(pool.civ_affinities, civ_before, "civ_affinities modified");
    assert_eq!(pool.occupations, occ_before, "occupations modified");
    assert_eq!(pool.loyalties, loy_before, "loyalties modified");
    assert_eq!(pool.satisfactions, sat_before, "satisfactions modified");
    assert_eq!(pool.skills, skills_before, "skills modified");
    assert_eq!(pool.ages, ages_before, "ages modified");
    assert_eq!(pool.displacement_turns, disp_before, "displacement_turns modified");
    assert_eq!(pool.life_events, life_events_before, "life_events modified");
    assert_eq!(pool.promotion_progress, promo_before, "promotion_progress modified");
    assert_eq!(pool.boldness, bold_before, "boldness modified");
    assert_eq!(pool.ambition, ambi_before, "ambition modified");
    assert_eq!(pool.loyalty_trait, loy_trait_before, "loyalty_trait modified");
    assert_eq!(pool.cultural_value_0, cv0_before, "cultural_value_0 modified");
    assert_eq!(pool.cultural_value_1, cv1_before, "cultural_value_1 modified");
    assert_eq!(pool.cultural_value_2, cv2_before, "cultural_value_2 modified");
    assert_eq!(pool.beliefs, beliefs_before, "beliefs modified");
    assert_eq!(pool.parent_id_0, p0_before, "parent_id_0 modified");
    assert_eq!(pool.parent_id_1, p1_before, "parent_id_1 modified");
    assert_eq!(pool.wealth, wealth_before, "wealth modified");
    assert_eq!(pool.memory_event_types, mem_et_before, "memory_event_types modified");
    assert_eq!(pool.memory_source_civs, mem_sc_before, "memory_source_civs modified");
    assert_eq!(pool.memory_turns, mem_t_before, "memory_turns modified");
    assert_eq!(pool.memory_intensities, mem_i_before, "memory_intensities modified");
    assert_eq!(pool.memory_decay_factors, mem_df_before, "memory_decay_factors modified");
    assert_eq!(pool.memory_gates, mem_g_before, "memory_gates modified");
    assert_eq!(pool.memory_count, mem_c_before, "memory_count modified");
    assert_eq!(pool.memory_is_legacy, mem_l_before, "memory_is_legacy modified");
    assert_eq!(pool.need_safety, ns_before, "need_safety modified");
    assert_eq!(pool.need_material, nm_before, "need_material modified");
    assert_eq!(pool.need_social, nso_before, "need_social modified");
    assert_eq!(pool.need_spiritual, nsp_before, "need_spiritual modified");
    assert_eq!(pool.need_autonomy, na_before, "need_autonomy modified");
    assert_eq!(pool.need_purpose, np_before, "need_purpose modified");
    assert_eq!(pool.rel_target_ids, rt_before, "rel_target_ids modified");
    assert_eq!(pool.rel_sentiments, rs_before, "rel_sentiments modified");
    assert_eq!(pool.rel_bond_types, rb_before, "rel_bond_types modified");
    assert_eq!(pool.rel_formed_turns, rf_before, "rel_formed_turns modified");
    assert_eq!(pool.rel_count, rc_before, "rel_count modified");
    assert_eq!(pool.synthesis_budget, syn_before, "synthesis_budget modified");
    assert_eq!(pool.x, x_before, "x modified");
    assert_eq!(pool.y, y_before, "y modified");
    assert_eq!(pool.settlement_ids, sid_before, "settlement_ids modified");
    assert_eq!(pool.trip_phase, tp_before, "trip_phase modified");
    assert_eq!(pool.trip_dest_region, tdr_before, "trip_dest_region modified");
    assert_eq!(pool.trip_origin_region, tor_before, "trip_origin_region modified");
    assert_eq!(pool.trip_good_slot, tgs_before, "trip_good_slot modified");
    assert_eq!(pool.trip_cargo_qty, tcq_before, "trip_cargo_qty modified");
    assert_eq!(pool.trip_turns_elapsed, tte_before, "trip_turns_elapsed modified");
    assert_eq!(pool.trip_path, tpath_before, "trip_path modified");
    assert_eq!(pool.trip_path_len, tpl_before, "trip_path_len modified");
    assert_eq!(pool.trip_path_cursor, tpc_before, "trip_path_cursor modified");
    assert_eq!(pool.alive, alive_before, "alive modified");

    // arrived_this_turn IS expected to change (consumed by knowledge phase)
    assert!(!pool.arrived_this_turn[b], "arrived_this_turn should be cleared");
}

// ---------------------------------------------------------------------------
// Multi-turn chain diffusion
// ---------------------------------------------------------------------------

#[test]
fn test_multi_turn_chain_diffusion() {
    let seed = [7u8; 32];
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let c = pool.spawn(2, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let d = pool.spawn(3, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let _a_id = pool.ids[a];
    let b_id = pool.ids[b];
    let c_id = pool.ids[c];
    let d_id = pool.ids[d];

    set_bond(&mut pool, a, b_id, 5, 127);
    set_bond(&mut pool, b, c_id, 5, 127);
    set_bond(&mut pool, c, d_id, 5, 127);

    let mut regions: Vec<RegionState> = (0..4).map(|i| RegionState::new(i)).collect();
    regions[0].controller_changed_this_turn = true;

    let _s1 = knowledge_phase(&mut pool, &regions, &seed, 1);
    regions[0].controller_changed_this_turn = false;

    let a_pkt = (0..4).find(|&i| unpack_type(pool.pkt_type_and_hops[a][i]) == 1);
    assert!(a_pkt.is_some(), "A should have threat packet");
    assert_eq!(pool.pkt_source_turn[a][a_pkt.unwrap()], 1);
    assert_eq!(unpack_hops(pool.pkt_type_and_hops[a][a_pkt.unwrap()]), 0);

    let _s2 = knowledge_phase(&mut pool, &regions, &seed, 2);
    let _s3 = knowledge_phase(&mut pool, &regions, &seed, 3);
    let _s4 = knowledge_phase(&mut pool, &regions, &seed, 4);

    for agent_slot in [b, c, d] {
        for i in 0..4 {
            if unpack_type(pool.pkt_type_and_hops[agent_slot][i]) == 1 {
                assert_eq!(
                    pool.pkt_source_turn[agent_slot][i], 1,
                    "source_turn should be preserved through propagation"
                );
                assert!(
                    unpack_hops(pool.pkt_type_and_hops[agent_slot][i]) > 0,
                    "propagated packets should have hop_count > 0"
                );
            }
        }
    }
}

#[test]
fn test_arrival_flag_consumed_by_knowledge_phase() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.arrived_this_turn[a] = true;

    let mut regions = vec![RegionState::new(0)];
    regions[0].merchant_route_margin = 0.5;

    let stats = knowledge_phase(&mut pool, &regions, &[0u8; 32], 1);
    assert!(!pool.arrived_this_turn[a], "flag should be cleared");
    assert!(stats.packets_created > 0, "should have created trade packet");

    let stats2 = knowledge_phase(&mut pool, &regions, &[0u8; 32], 2);
    assert_eq!(stats2.created_trade, 0, "no arrival = no new trade packet");
}
