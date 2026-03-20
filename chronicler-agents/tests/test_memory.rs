use chronicler_agents::{
    AgentPool, Occupation, BELIEF_NONE, MEMORY_SLOTS,
    MemoryEventType, MemoryIntent,
    factor_from_half_life, half_life_from_factor,
    decay_memories, write_single_memory, compute_memory_satisfaction_score,
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
