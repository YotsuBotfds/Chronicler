use chronicler_agents::{
    AgentPool, Occupation, BELIEF_NONE, MEMORY_SLOTS,
    MemoryEventType, MemoryIntent,
    factor_from_half_life, half_life_from_factor,
    decay_memories, write_single_memory, write_all_memories,
    clear_memory_gates, compute_memory_satisfaction_score,
    compute_memory_utility_modifiers, agents_share_memory,
    GATE_BIT_BATTLE, GATE_BIT_PROSPERITY, GATE_BIT_FAMINE, GATE_BIT_PERSECUTION,
    RegionState,
};

// ---------------------------------------------------------------------------
// Test helper: spawn an agent with default params using the real signature
// ---------------------------------------------------------------------------

fn test_spawn_agent(pool: &mut AgentPool) -> usize {
    pool.spawn(
        0,                    // region
        0,                    // civ_affinity
        Occupation::Farmer,   // occupation
        25,                   // age
        0.5,                  // boldness
        0.5,                  // ambition
        0.5,                  // loyalty_trait
        0,                    // cultural_value_0
        1,                    // cultural_value_1
        2,                    // cultural_value_2
        BELIEF_NONE,          // belief
    )
}

// ===========================================================================
// Task 1: Foundation tests
// ===========================================================================

#[test]
fn test_memory_spawn_zeroed() {
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    // All memory fields should be zero-initialized
    assert_eq!(pool.memory_count[slot], 0);
    assert_eq!(pool.memory_gates[slot], 0);
    assert_eq!(pool.memory_event_types[slot], [0u8; 8]);
    assert_eq!(pool.memory_source_civs[slot], [0u8; 8]);
    assert_eq!(pool.memory_turns[slot], [0u16; 8]);
    assert_eq!(pool.memory_intensities[slot], [0i8; 8]);
    assert_eq!(pool.memory_decay_factors[slot], [0u8; 8]);
}

#[test]
fn test_memory_reuse_zeroed() {
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    // Write some non-zero data into memory fields
    pool.memory_count[slot] = 3;
    pool.memory_gates[slot] = 0xFF;
    pool.memory_event_types[slot] = [1, 2, 3, 4, 5, 6, 7, 8];
    pool.memory_source_civs[slot] = [10; 8];
    pool.memory_turns[slot] = [100; 8];
    pool.memory_intensities[slot] = [-80; 8];
    pool.memory_decay_factors[slot] = [50; 8];

    // Kill and respawn into same slot
    pool.kill(slot);
    let reused = test_spawn_agent(&mut pool);
    assert_eq!(reused, slot, "should reuse the same slot");

    // All memory fields should be zero after reuse
    assert_eq!(pool.memory_count[reused], 0);
    assert_eq!(pool.memory_gates[reused], 0);
    assert_eq!(pool.memory_event_types[reused], [0u8; 8]);
    assert_eq!(pool.memory_source_civs[reused], [0u8; 8]);
    assert_eq!(pool.memory_turns[reused], [0u16; 8]);
    assert_eq!(pool.memory_intensities[reused], [0i8; 8]);
    assert_eq!(pool.memory_decay_factors[reused], [0u8; 8]);
}

// ===========================================================================
// Task 2: Half-life utility tests
// ===========================================================================

#[test]
fn test_halflife_roundtrip() {
    // For half-lives 1..100, factor_from_half_life -> half_life_from_factor
    // should roundtrip within tolerance.
    for n in 1..=100 {
        let hl = n as f32;
        let factor = factor_from_half_life(hl);
        if factor == 0 {
            // Very large half-life quantized to 0 = infinity, skip
            continue;
        }
        let recovered = half_life_from_factor(factor);
        let tolerance = if n <= 50 { 0.15 } else { 0.25 };
        let rel_error = ((recovered - hl) / hl).abs();
        assert!(
            rel_error <= tolerance,
            "half-life {}: factor={}, recovered={:.2}, rel_error={:.4} > {}",
            n, factor, recovered, rel_error, tolerance
        );
    }
}

#[test]
fn test_halflife_edge_cases() {
    // Infinity half-life -> factor 0
    assert_eq!(factor_from_half_life(f32::INFINITY), 0);
    // Zero half-life -> factor 0
    assert_eq!(factor_from_half_life(0.0), 0);
    // Negative half-life -> factor 0
    assert_eq!(factor_from_half_life(-5.0), 0);

    // factor 0 -> infinity half-life
    assert_eq!(half_life_from_factor(0), f32::INFINITY);

    // factor 255 -> ~1 turn half-life
    let hl = half_life_from_factor(255);
    assert!(hl >= 0.5 && hl <= 2.0, "factor 255 gave half-life {}", hl);
}

// ===========================================================================
// Task 2: Decay tests
// ===========================================================================

#[test]
fn test_memory_decay_basic() {
    // Intensity -80 with half-life 10 turns: after 10 ticks should be ~-40 (within 25%)
    let mut pool = AgentPool::new(4);
    let slot = test_spawn_agent(&mut pool);

    let intent = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Famine as u8,
        source_civ: 0,
        intensity: -80,
    };
    write_single_memory(&mut pool, &intent, 1);

    // Override the decay factor to correspond to half-life = 10 turns
    let factor = factor_from_half_life(10.0);
    pool.memory_decay_factors[slot][0] = factor;

    // Apply 10 ticks of decay
    let alive_slots = vec![slot];
    for _ in 0..10 {
        decay_memories(&mut pool, &alive_slots);
    }

    let remaining = pool.memory_intensities[slot][0];
    // Should be approximately -40 (within 25%)
    let expected = -40.0_f32;
    let actual = remaining as f32;
    let rel_error = ((actual - expected) / expected).abs();
    assert!(
        rel_error <= 0.25,
        "After 10 ticks with hl=10: expected ~{}, got {}, rel_error={:.3}",
        expected, remaining, rel_error
    );
}

#[test]
fn test_memory_decay_permanent() {
    // decay_factor = 0 means no decay — intensity should be unchanged after 100 ticks
    let mut pool = AgentPool::new(4);
    let slot = test_spawn_agent(&mut pool);

    // Manually set a memory with decay_factor = 0
    pool.memory_count[slot] = 1;
    pool.memory_event_types[slot][0] = MemoryEventType::Legacy as u8;
    pool.memory_intensities[slot][0] = -80;
    pool.memory_decay_factors[slot][0] = 0;

    let alive_slots = vec![slot];
    for _ in 0..100 {
        decay_memories(&mut pool, &alive_slots);
    }

    assert_eq!(pool.memory_intensities[slot][0], -80);
}

#[test]
fn test_decay_integer_truncation() {
    // Intensity 1 with any nonzero factor should decay to 0 in one tick
    // because (1 * (255 - factor)) / 255 < 1 for any factor > 0
    let mut pool = AgentPool::new(4);
    let slot = test_spawn_agent(&mut pool);

    pool.memory_count[slot] = 1;
    pool.memory_intensities[slot][0] = 1;
    pool.memory_decay_factors[slot][0] = 5; // small but nonzero

    let alive_slots = vec![slot];
    decay_memories(&mut pool, &alive_slots);

    assert_eq!(
        pool.memory_intensities[slot][0], 0,
        "Intensity 1 with factor 5 should truncate to 0 in one tick"
    );
}

// ===========================================================================
// Task 2: Eviction tests
// ===========================================================================

#[test]
fn test_memory_eviction_min_intensity() {
    // Fill 8 slots with varying intensities, then write a 9th.
    // Should evict the slot with lowest |intensity|.
    let mut pool = AgentPool::new(4);
    let slot = test_spawn_agent(&mut pool);

    // Fill all 8 slots: intensities [-80, -70, -60, -50, -10, 50, 60, 70]
    let intensities: [i8; 8] = [-80, -70, -60, -50, -10, 50, 60, 70];
    for (i, &intensity) in intensities.iter().enumerate() {
        let intent = MemoryIntent {
            agent_slot: slot,
            event_type: i as u8,
            source_civ: 0,
            intensity,
        };
        write_single_memory(&mut pool, &intent, i as u16);
    }
    assert_eq!(pool.memory_count[slot], 8);

    // Write a 9th memory — should evict slot 4 (intensity -10, lowest |intensity|)
    let new_intent = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Victory as u8,
        source_civ: 1,
        intensity: 90,
    };
    write_single_memory(&mut pool, &new_intent, 100);

    // Count should still be 8
    assert_eq!(pool.memory_count[slot], 8);
    // Slot 4 should now contain the new memory
    assert_eq!(pool.memory_event_types[slot][4], MemoryEventType::Victory as u8);
    assert_eq!(pool.memory_intensities[slot][4], 90);
    assert_eq!(pool.memory_source_civs[slot][4], 1);
    assert_eq!(pool.memory_turns[slot][4], 100);
}

#[test]
fn test_memory_eviction_tiebreak() {
    // All 8 slots same intensity — evicts lowest index (0)
    let mut pool = AgentPool::new(4);
    let slot = test_spawn_agent(&mut pool);

    for i in 0..8 {
        let intent = MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Battle as u8,
            source_civ: 0,
            intensity: -50,
        };
        write_single_memory(&mut pool, &intent, i as u16);
    }
    assert_eq!(pool.memory_count[slot], 8);

    // All have |intensity| = 50, so tiebreak picks index 0
    let new_intent = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Prosperity as u8,
        source_civ: 2,
        intensity: 80,
    };
    write_single_memory(&mut pool, &new_intent, 200);

    // Index 0 should now be the new memory
    assert_eq!(pool.memory_event_types[slot][0], MemoryEventType::Prosperity as u8);
    assert_eq!(pool.memory_intensities[slot][0], 80);
    assert_eq!(pool.memory_source_civs[slot][0], 2);
    assert_eq!(pool.memory_turns[slot][0], 200);

    // All other slots should still be Battle/-50
    for i in 1..8 {
        assert_eq!(pool.memory_event_types[slot][i], MemoryEventType::Battle as u8);
        assert_eq!(pool.memory_intensities[slot][i], -50);
    }
}

#[test]
fn test_memory_count_lifecycle() {
    // Count increments 0..8, then stays at 8 after eviction
    let mut pool = AgentPool::new(4);
    let slot = test_spawn_agent(&mut pool);

    for i in 0..MEMORY_SLOTS {
        assert_eq!(pool.memory_count[slot], i as u8);
        let intent = MemoryIntent {
            agent_slot: slot,
            event_type: (i % 12) as u8,
            source_civ: 0,
            intensity: -50,
        };
        write_single_memory(&mut pool, &intent, i as u16);
    }
    assert_eq!(pool.memory_count[slot], 8);

    // Write 3 more — count should stay at 8
    for i in 0..3 {
        let intent = MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Victory as u8,
            source_civ: 0,
            intensity: 90,
        };
        write_single_memory(&mut pool, &intent, (100 + i) as u16);
        assert_eq!(pool.memory_count[slot], 8);
    }
}

// ===========================================================================
// Task 2: Satisfaction score tests
// ===========================================================================

#[test]
fn test_memory_satisfaction_score_empty() {
    let mut pool = AgentPool::new(4);
    let slot = test_spawn_agent(&mut pool);
    assert_eq!(compute_memory_satisfaction_score(&pool, slot), 0.0);
}

#[test]
fn test_memory_satisfaction_score_positive() {
    let mut pool = AgentPool::new(4);
    let slot = test_spawn_agent(&mut pool);

    // Write a positive memory
    let intent = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Prosperity as u8,
        source_civ: 0,
        intensity: 50,
    };
    write_single_memory(&mut pool, &intent, 1);

    let score = compute_memory_satisfaction_score(&pool, slot);
    // 50 / 1024 * 0.12 ≈ 0.00586
    assert!(score > 0.0, "positive memory should give positive score");
    assert!(score < 0.01, "score {} too large", score);
}

#[test]
fn test_memory_satisfaction_score_negative() {
    let mut pool = AgentPool::new(4);
    let slot = test_spawn_agent(&mut pool);

    // Write a negative memory
    let intent = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Famine as u8,
        source_civ: 0,
        intensity: -80,
    };
    write_single_memory(&mut pool, &intent, 1);

    let score = compute_memory_satisfaction_score(&pool, slot);
    assert!(score < 0.0, "negative memory should give negative score");
}

#[test]
fn test_memory_satisfaction_score_mixed() {
    let mut pool = AgentPool::new(4);
    let slot = test_spawn_agent(&mut pool);

    // Write opposing memories that roughly cancel
    let positive = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Victory as u8,
        source_civ: 0,
        intensity: 60,
    };
    let negative = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Battle as u8,
        source_civ: 0,
        intensity: -60,
    };
    write_single_memory(&mut pool, &positive, 1);
    write_single_memory(&mut pool, &negative, 2);

    let score = compute_memory_satisfaction_score(&pool, slot);
    // 60 + (-60) = 0
    assert!(
        score.abs() < 0.001,
        "opposing memories should cancel: score={}",
        score
    );
}

// ===========================================================================
// Task 4: Consolidated write and gate clearing tests
// ===========================================================================

#[test]
fn test_consolidated_write_ordering() {
    // Multiple intents from different "phases" all write correctly
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    let intents = vec![
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Famine as u8,
            source_civ: 0,
            intensity: -80,
        },
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Battle as u8,
            source_civ: 1,
            intensity: -60,
        },
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Prosperity as u8,
            source_civ: 0,
            intensity: 50,
        },
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Migration as u8,
            source_civ: 2,
            intensity: -30,
        },
    ];

    write_all_memories(&mut pool, &intents, 10);

    // All 4 should be written
    assert_eq!(pool.memory_count[slot], 4);

    // Verify each was written in order (slots 0..3)
    assert_eq!(pool.memory_event_types[slot][0], MemoryEventType::Famine as u8);
    assert_eq!(pool.memory_intensities[slot][0], -80);
    assert_eq!(pool.memory_source_civs[slot][0], 0);

    assert_eq!(pool.memory_event_types[slot][1], MemoryEventType::Battle as u8);
    assert_eq!(pool.memory_intensities[slot][1], -60);
    assert_eq!(pool.memory_source_civs[slot][1], 1);

    assert_eq!(pool.memory_event_types[slot][2], MemoryEventType::Prosperity as u8);
    assert_eq!(pool.memory_intensities[slot][2], 50);

    assert_eq!(pool.memory_event_types[slot][3], MemoryEventType::Migration as u8);
    assert_eq!(pool.memory_intensities[slot][3], -30);
    assert_eq!(pool.memory_source_civs[slot][3], 2);

    // All turns should be 10
    for i in 0..4 {
        assert_eq!(pool.memory_turns[slot][i], 10);
    }
}

#[test]
fn test_consolidated_write_multiple_agents() {
    // Intents spread across different agents all land correctly
    let mut pool = AgentPool::new(8);
    let slot_a = test_spawn_agent(&mut pool);
    let slot_b = pool.spawn(1, 1, Occupation::Soldier, 30, 0.5, 0.5, 0.5, 0, 1, 2, BELIEF_NONE);

    let intents = vec![
        MemoryIntent {
            agent_slot: slot_a,
            event_type: MemoryEventType::Famine as u8,
            source_civ: 0,
            intensity: -80,
        },
        MemoryIntent {
            agent_slot: slot_b,
            event_type: MemoryEventType::Battle as u8,
            source_civ: 1,
            intensity: -60,
        },
        MemoryIntent {
            agent_slot: slot_a,
            event_type: MemoryEventType::Victory as u8,
            source_civ: 0,
            intensity: 60,
        },
    ];

    write_all_memories(&mut pool, &intents, 5);

    assert_eq!(pool.memory_count[slot_a], 2);
    assert_eq!(pool.memory_count[slot_b], 1);

    assert_eq!(pool.memory_event_types[slot_a][0], MemoryEventType::Famine as u8);
    assert_eq!(pool.memory_event_types[slot_a][1], MemoryEventType::Victory as u8);
    assert_eq!(pool.memory_event_types[slot_b][0], MemoryEventType::Battle as u8);
}

#[test]
fn test_gate_blocks_duplicate_write() {
    // Write BATTLE twice — second is blocked by gate
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    let intents = vec![
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Battle as u8,
            source_civ: 0,
            intensity: -60,
        },
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Battle as u8,
            source_civ: 1,
            intensity: -50, // different intensity to distinguish
        },
    ];

    write_all_memories(&mut pool, &intents, 10);

    // Only one should be written
    assert_eq!(pool.memory_count[slot], 1);
    assert_eq!(pool.memory_event_types[slot][0], MemoryEventType::Battle as u8);
    assert_eq!(pool.memory_intensities[slot][0], -60); // first intent
    assert_eq!(pool.memory_source_civs[slot][0], 0); // first intent's source_civ

    // Gate bit should be set
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_BATTLE, 0);
}

#[test]
fn test_gate_blocks_famine_duplicate() {
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    let intents = vec![
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Famine as u8,
            source_civ: 0,
            intensity: -80,
        },
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Famine as u8,
            source_civ: 0,
            intensity: -70,
        },
    ];

    write_all_memories(&mut pool, &intents, 10);

    assert_eq!(pool.memory_count[slot], 1);
    assert_eq!(pool.memory_intensities[slot][0], -80);
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_FAMINE, 0);
}

#[test]
fn test_non_gated_types_allow_duplicates() {
    // Non-gated types (e.g. Migration) can be written multiple times
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    let intents = vec![
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Migration as u8,
            source_civ: 0,
            intensity: -30,
        },
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Migration as u8,
            source_civ: 1,
            intensity: -25,
        },
    ];

    write_all_memories(&mut pool, &intents, 10);

    // Both should be written (Migration is not gated)
    assert_eq!(pool.memory_count[slot], 2);
    assert_eq!(pool.memory_event_types[slot][0], MemoryEventType::Migration as u8);
    assert_eq!(pool.memory_event_types[slot][1], MemoryEventType::Migration as u8);
}

#[test]
fn test_gate_clearing_battle() {
    // Set BATTLE gate, then clear when agent is not in contested region
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Soldier, 25, 0.5, 0.5, 0.5, 0, 1, 2, BELIEF_NONE);

    // Manually set gate bit
    pool.memory_gates[slot] = GATE_BIT_BATTLE;

    let regions = vec![RegionState::new(0)];
    let contested = vec![false]; // NOT contested

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    // Gate should be cleared because region is not contested
    assert_eq!(pool.memory_gates[slot] & GATE_BIT_BATTLE, 0);
}

#[test]
fn test_gate_not_cleared_battle_still_contested() {
    // Battle gate stays if soldier IS in contested region
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Soldier, 25, 0.5, 0.5, 0.5, 0, 1, 2, BELIEF_NONE);

    pool.memory_gates[slot] = GATE_BIT_BATTLE;

    let regions = vec![RegionState::new(0)];
    let contested = vec![true]; // still contested

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    // Gate should remain because soldier is still in contested region
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_BATTLE, 0);
}

#[test]
fn test_gate_clearing_battle_not_soldier() {
    // Battle gate clears if agent is NOT a soldier (even if contested)
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, BELIEF_NONE);

    pool.memory_gates[slot] = GATE_BIT_BATTLE;

    let regions = vec![RegionState::new(0)];
    let contested = vec![true]; // contested but agent is not soldier

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    // Gate should clear because agent is not a soldier
    assert_eq!(pool.memory_gates[slot] & GATE_BIT_BATTLE, 0);
}

#[test]
fn test_gate_clearing_famine() {
    // Famine gate clears when food_sufficiency >= 1.0
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    pool.memory_gates[slot] = GATE_BIT_FAMINE;

    let mut region = RegionState::new(0);
    region.food_sufficiency = 1.0; // sufficient food
    let regions = vec![region];
    let contested = vec![false];

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    assert_eq!(pool.memory_gates[slot] & GATE_BIT_FAMINE, 0);
}

#[test]
fn test_gate_not_cleared_famine_still_starving() {
    // Famine gate stays when food_sufficiency < 1.0
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    pool.memory_gates[slot] = GATE_BIT_FAMINE;

    let mut region = RegionState::new(0);
    region.food_sufficiency = 0.5; // still starving
    let regions = vec![region];
    let contested = vec![false];

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    assert_ne!(pool.memory_gates[slot] & GATE_BIT_FAMINE, 0);
}

#[test]
fn test_gate_clearing_prosperity() {
    // Prosperity gate clears when wealth drops below threshold
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    pool.memory_gates[slot] = GATE_BIT_PROSPERITY;
    pool.wealth[slot] = 1.0; // below PROSPERITY_THRESHOLD (3.0)

    let regions = vec![RegionState::new(0)];
    let contested = vec![false];

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    assert_eq!(pool.memory_gates[slot] & GATE_BIT_PROSPERITY, 0);
}

#[test]
fn test_gate_not_cleared_prosperity_still_wealthy() {
    // Prosperity gate stays when wealth >= threshold
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    pool.memory_gates[slot] = GATE_BIT_PROSPERITY;
    pool.wealth[slot] = 5.0; // above PROSPERITY_THRESHOLD (3.0)

    let regions = vec![RegionState::new(0)];
    let contested = vec![false];

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    assert_ne!(pool.memory_gates[slot] & GATE_BIT_PROSPERITY, 0);
}

#[test]
fn test_gate_clearing_persecution() {
    // Persecution gate clears when persecution_intensity is 0
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    pool.memory_gates[slot] = GATE_BIT_PERSECUTION;

    let mut region = RegionState::new(0);
    region.persecution_intensity = 0.0;
    let regions = vec![region];
    let contested = vec![false];

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    assert_eq!(pool.memory_gates[slot] & GATE_BIT_PERSECUTION, 0);
}

#[test]
fn test_gate_not_cleared_persecution_active() {
    // Persecution gate stays when persecution is active
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    pool.memory_gates[slot] = GATE_BIT_PERSECUTION;

    let mut region = RegionState::new(0);
    region.persecution_intensity = 0.5;
    let regions = vec![region];
    let contested = vec![false];

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    assert_ne!(pool.memory_gates[slot] & GATE_BIT_PERSECUTION, 0);
}

#[test]
fn test_gate_clearing_multiple_bits() {
    // Multiple gate bits — only the ones whose conditions are met get cleared
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Soldier, 25, 0.5, 0.5, 0.5, 0, 1, 2, BELIEF_NONE);

    // Set all 4 gate bits
    pool.memory_gates[slot] = GATE_BIT_BATTLE | GATE_BIT_PROSPERITY | GATE_BIT_FAMINE | GATE_BIT_PERSECUTION;
    pool.wealth[slot] = 1.0; // below prosperity threshold → clear

    let mut region = RegionState::new(0);
    region.food_sufficiency = 1.0; // sufficient → clear famine
    region.persecution_intensity = 0.5; // active → keep persecution
    let regions = vec![region];
    let contested = vec![true]; // contested + soldier → keep battle

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    // Battle: still contested + soldier → stays
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_BATTLE, 0, "battle gate should remain");
    // Prosperity: wealth < threshold → cleared
    assert_eq!(pool.memory_gates[slot] & GATE_BIT_PROSPERITY, 0, "prosperity gate should clear");
    // Famine: food sufficient → cleared
    assert_eq!(pool.memory_gates[slot] & GATE_BIT_FAMINE, 0, "famine gate should clear");
    // Persecution: still active → stays
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_PERSECUTION, 0, "persecution gate should remain");
}

#[test]
fn test_gate_skip_when_zero() {
    // Agent with gates=0 is skipped (no mutations)
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);
    pool.memory_gates[slot] = 0;

    let regions = vec![RegionState::new(0)];
    let contested = vec![false];

    let alive = vec![slot];
    clear_memory_gates(&mut pool, &alive, &regions, &contested);

    assert_eq!(pool.memory_gates[slot], 0);
}

#[test]
fn test_write_all_memories_respects_pre_existing_gate() {
    // If gate is already set from a previous tick, new intents of that type are blocked
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    // Pre-set the famine gate (from a previous tick)
    pool.memory_gates[slot] = GATE_BIT_FAMINE;

    let intents = vec![
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Famine as u8,
            source_civ: 0,
            intensity: -80,
        },
        MemoryIntent {
            agent_slot: slot,
            event_type: MemoryEventType::Victory as u8,
            source_civ: 0,
            intensity: 60,
        },
    ];

    write_all_memories(&mut pool, &intents, 10);

    // Famine should be blocked, Victory should be written
    assert_eq!(pool.memory_count[slot], 1);
    assert_eq!(pool.memory_event_types[slot][0], MemoryEventType::Victory as u8);
}

// ===========================================================================
// Task 5: Gate bit tests — verify write_all_memories blocks gated duplicates
// ===========================================================================

#[test]
fn test_memory_gate_battle() {
    // Write BATTLE, gate set, second BATTLE blocked
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    let intent1 = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Battle as u8,
        source_civ: 0,
        intensity: -60,
    };
    write_all_memories(&mut pool, &[intent1], 1);

    assert_eq!(pool.memory_count[slot], 1);
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_BATTLE, 0, "gate should be set after first BATTLE");

    // Second BATTLE should be blocked by the gate
    let intent2 = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Battle as u8,
        source_civ: 1,
        intensity: -50,
    };
    write_all_memories(&mut pool, &[intent2], 2);

    // Still only one BATTLE memory
    assert_eq!(pool.memory_count[slot], 1);
    assert_eq!(pool.memory_intensities[slot][0], -60, "original BATTLE should be preserved");
}

#[test]
fn test_memory_gate_famine() {
    // Write FAMINE, gate set, second FAMINE blocked
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    let intent1 = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Famine as u8,
        source_civ: 0,
        intensity: -80,
    };
    write_all_memories(&mut pool, &[intent1], 1);

    assert_eq!(pool.memory_count[slot], 1);
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_FAMINE, 0, "gate should be set after first FAMINE");

    // Second FAMINE should be blocked by the gate
    let intent2 = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Famine as u8,
        source_civ: 0,
        intensity: -70,
    };
    write_all_memories(&mut pool, &[intent2], 2);

    assert_eq!(pool.memory_count[slot], 1);
    assert_eq!(pool.memory_intensities[slot][0], -80, "original FAMINE should be preserved");
}

#[test]
fn test_memory_gate_prosperity() {
    // Write PROSPERITY, gate set, second PROSPERITY blocked
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    let intent1 = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Prosperity as u8,
        source_civ: 0,
        intensity: 50,
    };
    write_all_memories(&mut pool, &[intent1], 1);

    assert_eq!(pool.memory_count[slot], 1);
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_PROSPERITY, 0, "gate should be set after first PROSPERITY");

    // Second PROSPERITY should be blocked by the gate
    let intent2 = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Prosperity as u8,
        source_civ: 0,
        intensity: 40,
    };
    write_all_memories(&mut pool, &[intent2], 2);

    assert_eq!(pool.memory_count[slot], 1);
    assert_eq!(pool.memory_intensities[slot][0], 50, "original PROSPERITY should be preserved");
}

#[test]
fn test_memory_gate_persecution() {
    // Write PERSECUTION, gate set, second PERSECUTION blocked
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    let intent1 = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Persecution as u8,
        source_civ: 0,
        intensity: -90,
    };
    write_all_memories(&mut pool, &[intent1], 1);

    assert_eq!(pool.memory_count[slot], 1);
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_PERSECUTION, 0, "gate should be set after first PERSECUTION");

    // Second PERSECUTION should be blocked by the gate
    let intent2 = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Persecution as u8,
        source_civ: 1,
        intensity: -85,
    };
    write_all_memories(&mut pool, &[intent2], 2);

    assert_eq!(pool.memory_count[slot], 1);
    assert_eq!(pool.memory_intensities[slot][0], -90, "original PERSECUTION should be preserved");
}

// ===========================================================================
// Task 6: Satisfaction modifier tests
// ===========================================================================

#[test]
fn test_memory_satisfaction_inside_cap() {
    // When other penalties consume full 0.40 budget, negative memory is absorbed
    use chronicler_agents::satisfaction::{SatisfactionInputs, compute_satisfaction_with_culture};
    use chronicler_agents::signals::CivShock;

    // Max cultural mismatch (0.15) + religious mismatch (0.05) + persecution (0.15) + class tension (0.05)
    // = 0.40 total → no budget left for memory
    let sat_with_neg_mem = compute_satisfaction_with_culture(&SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
        civ_at_war: false, region_contested: false, occ_matches_faction: false,
        is_displaced: false, trade_routes: 0, faction_influence: 0.0,
        shock: CivShock::default(),
        agent_values: [4, 3, 2], controller_values: [0, 1, 5], // max cultural mismatch = 0.15
        agent_belief: 3, majority_belief: 5,                    // religious mismatch = 0.05
        has_temple: false, persecution_intensity: 1.0,           // persecution = 0.15
        gini_coefficient: 1.0, wealth_percentile: 0.0,           // class tension fills remaining 0.05
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: -0.20, // negative memory — should be absorbed (no budget)
    });

    let sat_no_mem = compute_satisfaction_with_culture(&SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
        civ_at_war: false, region_contested: false, occ_matches_faction: false,
        is_displaced: false, trade_routes: 0, faction_influence: 0.0,
        shock: CivShock::default(),
        agent_values: [4, 3, 2], controller_values: [0, 1, 5],
        agent_belief: 3, majority_belief: 5,
        has_temple: false, persecution_intensity: 1.0,
        gini_coefficient: 1.0, wealth_percentile: 0.0,
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: 0.0,
    });

    // Memory should have no effect when budget is fully consumed
    assert!((sat_with_neg_mem - sat_no_mem).abs() < 0.001,
        "negative memory should be absorbed when budget full: with_mem={}, no_mem={}",
        sat_with_neg_mem, sat_no_mem);
}

#[test]
fn test_memory_satisfaction_partial_budget() {
    // When budget remains, negative memory reduces satisfaction
    use chronicler_agents::satisfaction::{SatisfactionInputs, compute_satisfaction_with_culture};
    use chronicler_agents::signals::CivShock;

    // No other penalties → full 0.40 budget available for memory
    let sat_no_mem = compute_satisfaction_with_culture(&SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
        civ_at_war: false, region_contested: false, occ_matches_faction: false,
        is_displaced: false, trade_routes: 0, faction_influence: 0.0,
        shock: CivShock::default(),
        agent_values: [0, 1, 2], controller_values: [0, 1, 2],
        agent_belief: 0xFF, majority_belief: 0xFF,
        has_temple: false, persecution_intensity: 0.0,
        gini_coefficient: 0.0, wealth_percentile: 0.5,
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: 0.0,
    });

    let sat_neg_mem = compute_satisfaction_with_culture(&SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
        civ_at_war: false, region_contested: false, occ_matches_faction: false,
        is_displaced: false, trade_routes: 0, faction_influence: 0.0,
        shock: CivShock::default(),
        agent_values: [0, 1, 2], controller_values: [0, 1, 2],
        agent_belief: 0xFF, majority_belief: 0xFF,
        has_temple: false, persecution_intensity: 0.0,
        gini_coefficient: 0.0, wealth_percentile: 0.5,
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: -0.10, // negative memory
    });

    let diff = sat_no_mem - sat_neg_mem;
    assert!(diff > 0.0, "negative memory should reduce satisfaction: no_mem={}, neg_mem={}", sat_no_mem, sat_neg_mem);
    assert!((diff - 0.10).abs() < 0.001,
        "expected 0.10 penalty, got {}", diff);
}

#[test]
fn test_memory_satisfaction_positive_reduces_penalty() {
    // Positive memory reduces total penalty but cannot go below 0 total penalty
    use chronicler_agents::satisfaction::{SatisfactionInputs, compute_satisfaction_with_culture};
    use chronicler_agents::signals::CivShock;

    // Cultural mismatch = 0.10 (2 values differ)
    let sat_no_mem = compute_satisfaction_with_culture(&SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
        civ_at_war: false, region_contested: false, occ_matches_faction: false,
        is_displaced: false, trade_routes: 0, faction_influence: 0.0,
        shock: CivShock::default(),
        agent_values: [4, 3, 2], controller_values: [4, 0, 1], // 1 overlap -> distance 2 -> 0.10 penalty
        agent_belief: 0xFF, majority_belief: 0xFF,
        has_temple: false, persecution_intensity: 0.0,
        gini_coefficient: 0.0, wealth_percentile: 0.5,
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: 0.0,
    });

    // Positive memory = +0.05 should reduce the 0.10 cultural penalty
    let sat_pos_mem = compute_satisfaction_with_culture(&SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
        civ_at_war: false, region_contested: false, occ_matches_faction: false,
        is_displaced: false, trade_routes: 0, faction_influence: 0.0,
        shock: CivShock::default(),
        agent_values: [4, 3, 2], controller_values: [4, 0, 1],
        agent_belief: 0xFF, majority_belief: 0xFF,
        has_temple: false, persecution_intensity: 0.0,
        gini_coefficient: 0.0, wealth_percentile: 0.5,
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: 0.05,
    });

    assert!(sat_pos_mem > sat_no_mem,
        "positive memory should increase satisfaction: pos={}, no={}", sat_pos_mem, sat_no_mem);
    assert!((sat_pos_mem - sat_no_mem - 0.05).abs() < 0.001,
        "expected +0.05 boost, got {}", sat_pos_mem - sat_no_mem);

    // Huge positive memory should not make total penalty negative (clamped at 0)
    let sat_huge_pos = compute_satisfaction_with_culture(&SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
        civ_at_war: false, region_contested: false, occ_matches_faction: false,
        is_displaced: false, trade_routes: 0, faction_influence: 0.0,
        shock: CivShock::default(),
        agent_values: [4, 3, 2], controller_values: [4, 0, 1],
        agent_belief: 0xFF, majority_belief: 0xFF,
        has_temple: false, persecution_intensity: 0.0,
        gini_coefficient: 0.0, wealth_percentile: 0.5,
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: 0.50, // much larger than the 0.10 cultural penalty
    });

    // Should recover the full 0.10 cultural penalty but not more
    let sat_zero_pen = compute_satisfaction_with_culture(&SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
        civ_at_war: false, region_contested: false, occ_matches_faction: false,
        is_displaced: false, trade_routes: 0, faction_influence: 0.0,
        shock: CivShock::default(),
        agent_values: [0, 1, 2], controller_values: [0, 1, 2], // no cultural penalty
        agent_belief: 0xFF, majority_belief: 0xFF,
        has_temple: false, persecution_intensity: 0.0,
        gini_coefficient: 0.0, wealth_percentile: 0.5,
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: 0.0,
    });

    // huge positive memory with cultural penalty should equal zero-penalty baseline
    assert!((sat_huge_pos - sat_zero_pen).abs() < 0.001,
        "huge positive memory should zero out penalty, not grant bonus: huge_pos={}, zero_pen={}",
        sat_huge_pos, sat_zero_pen);
}

// ===========================================================================
// Task 7: Utility modifier tests
// ===========================================================================

#[test]
fn test_utility_modifier_famine() {
    // FAMINE memory boosts migrate
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    let intent = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Famine as u8,
        source_civ: 0,
        intensity: -80,
    };
    write_single_memory(&mut pool, &intent, 1);

    let mods = compute_memory_utility_modifiers(&pool, slot);
    assert!(mods.migrate > 0.0, "famine should boost migrate: {}", mods.migrate);
    assert!((mods.rebel).abs() < 0.001, "famine should not affect rebel");
    assert!((mods.switch).abs() < 0.001, "famine should not affect switch");
    assert!((mods.stay).abs() < 0.001, "famine should not affect stay");
}

#[test]
fn test_utility_modifier_conquest_sides() {
    // Conquered vs conqueror get different modifiers
    let mut pool = AgentPool::new(8);
    // Agent in civ 0
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, BELIEF_NONE);

    // Conquest memory from civ 0 (conqueror side — source matches agent's civ)
    let intent_conqueror = MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Conquest as u8,
        source_civ: 0, // same as agent's civ
        intensity: -70,
    };
    write_single_memory(&mut pool, &intent_conqueror, 1);

    let mods_conqueror = compute_memory_utility_modifiers(&pool, slot);
    assert!(mods_conqueror.stay > 0.0, "conqueror should get stay boost: {}", mods_conqueror.stay);
    assert!((mods_conqueror.migrate).abs() < 0.001, "conqueror should not get migrate boost");

    // Reset for conquered test
    pool.kill(slot);
    let slot2 = pool.spawn(0, 1, Occupation::Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, BELIEF_NONE);

    // Conquest memory from civ 0 (conquered side — source doesn't match agent's civ 1)
    let intent_conquered = MemoryIntent {
        agent_slot: slot2,
        event_type: MemoryEventType::Conquest as u8,
        source_civ: 0, // different from agent's civ 1
        intensity: -70,
    };
    write_single_memory(&mut pool, &intent_conquered, 1);

    let mods_conquered = compute_memory_utility_modifiers(&pool, slot2);
    assert!(mods_conquered.migrate > 0.0, "conquered should get migrate boost: {}", mods_conquered.migrate);
    assert!((mods_conquered.stay).abs() < 0.001, "conquered should not get stay boost");
}

#[test]
fn test_utility_modifier_no_memories() {
    // All modifiers zero when no memories
    let mut pool = AgentPool::new(8);
    let slot = test_spawn_agent(&mut pool);

    let mods = compute_memory_utility_modifiers(&pool, slot);
    assert!((mods.rebel).abs() < 0.001, "rebel should be 0: {}", mods.rebel);
    assert!((mods.migrate).abs() < 0.001, "migrate should be 0: {}", mods.migrate);
    assert!((mods.switch).abs() < 0.001, "switch should be 0: {}", mods.switch);
    assert!((mods.stay).abs() < 0.001, "stay should be 0: {}", mods.stay);
}

// ===========================================================================
// Task 12: Bond formation query — agents_share_memory
// ===========================================================================

#[test]
fn test_agents_share_memory_match() {
    // Two agents with same event_type and same turn
    let mut pool = AgentPool::new(64);
    let a = test_spawn_agent(&mut pool);
    let b = test_spawn_agent(&mut pool);
    // Give both a BATTLE memory at turn 50
    pool.memory_event_types[a][0] = 1; // Battle
    pool.memory_turns[a][0] = 50;
    pool.memory_intensities[a][0] = -60;
    pool.memory_count[a] = 1;
    pool.memory_event_types[b][0] = 1;
    pool.memory_turns[b][0] = 50;
    pool.memory_intensities[b][0] = -40;
    pool.memory_count[b] = 1;
    let result = agents_share_memory(&pool, a, b);
    assert_eq!(result, Some((1, 50)));
}

#[test]
fn test_agents_share_memory_no_match() {
    let mut pool = AgentPool::new(64);
    let a = test_spawn_agent(&mut pool);
    let b = test_spawn_agent(&mut pool);
    pool.memory_event_types[a][0] = 1;
    pool.memory_turns[a][0] = 50;
    pool.memory_intensities[a][0] = -60;
    pool.memory_count[a] = 1;
    pool.memory_event_types[b][0] = 2; // different type
    pool.memory_turns[b][0] = 50;
    pool.memory_intensities[b][0] = -40;
    pool.memory_count[b] = 1;
    assert_eq!(agents_share_memory(&pool, a, b), None);
}

#[test]
fn test_agents_share_memory_turn_tolerance() {
    // Turn difference of 1 should match, difference of 2 should not
    let mut pool = AgentPool::new(64);
    let a = test_spawn_agent(&mut pool);
    let b = test_spawn_agent(&mut pool);
    pool.memory_event_types[a][0] = 1;
    pool.memory_turns[a][0] = 50;
    pool.memory_intensities[a][0] = -60;
    pool.memory_count[a] = 1;
    // turn 51 — within tolerance
    pool.memory_event_types[b][0] = 1;
    pool.memory_turns[b][0] = 51;
    pool.memory_intensities[b][0] = -40;
    pool.memory_count[b] = 1;
    assert!(agents_share_memory(&pool, a, b).is_some());
    // turn 52 — outside tolerance
    pool.memory_turns[b][0] = 52;
    assert!(agents_share_memory(&pool, a, b).is_none());
}

#[test]
fn test_agents_share_memory_empty() {
    // No memories — should return None
    let mut pool = AgentPool::new(64);
    let a = test_spawn_agent(&mut pool);
    let b = test_spawn_agent(&mut pool);
    assert_eq!(agents_share_memory(&pool, a, b), None);
}

#[test]
fn test_agents_share_memory_strongest_match() {
    // Multiple shared memories — returns the one with highest combined intensity
    let mut pool = AgentPool::new(64);
    let a = test_spawn_agent(&mut pool);
    let b = test_spawn_agent(&mut pool);
    // Shared Battle memory at turn 10 with low intensity
    pool.memory_event_types[a][0] = 1;
    pool.memory_turns[a][0] = 10;
    pool.memory_intensities[a][0] = -20;
    // Shared Famine memory at turn 50 with high intensity
    pool.memory_event_types[a][1] = 0;
    pool.memory_turns[a][1] = 50;
    pool.memory_intensities[a][1] = -80;
    pool.memory_count[a] = 2;

    pool.memory_event_types[b][0] = 1;
    pool.memory_turns[b][0] = 10;
    pool.memory_intensities[b][0] = -15;
    pool.memory_event_types[b][1] = 0;
    pool.memory_turns[b][1] = 50;
    pool.memory_intensities[b][1] = -70;
    pool.memory_count[b] = 2;

    let result = agents_share_memory(&pool, a, b);
    // Famine: 80 + 70 = 150 combined > Battle: 20 + 15 = 35
    assert_eq!(result, Some((0, 50)));
}
