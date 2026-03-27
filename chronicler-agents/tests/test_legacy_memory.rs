use chronicler_agents::memory::{MemoryIntent, compute_memory_utility_modifiers, compute_memory_satisfaction_score, agents_share_memory};
use chronicler_agents::{AgentPool, Occupation, BELIEF_NONE, factor_from_half_life, write_single_memory, write_all_memories, extract_legacy_memories, LEGACY_HALF_LIFE};

#[test]
fn test_memory_intent_legacy_fields() {
    let intent = MemoryIntent {
        agent_slot: 0,
        expected_agent_id: 0,
        event_type: 0, // Famine
        source_civ: 1,
        intensity: -45,
        is_legacy: true,
        decay_factor_override: Some(7), // ~100 turn half-life
    };
    assert!(intent.is_legacy);
    assert_eq!(intent.decay_factor_override, Some(7));
}

fn spawn_test_agent(pool: &mut AgentPool) -> usize {
    pool.spawn(
        0,                  // region
        0,                  // civ_affinity
        Occupation::Farmer, // occupation
        25,                 // age
        0.5,                // boldness
        0.5,                // ambition
        0.5,                // loyalty_trait
        0,                  // cultural_value_0
        1,                  // cultural_value_1
        2,                  // cultural_value_2
        BELIEF_NONE,        // belief
    )
}

#[test]
fn test_write_legacy_memory_decay_override() {
    // Legacy memory uses decay_factor_override, not the default for its event_type.
    // The legacy bit for the written slot should be set.
    // The event_type in the slot should remain the original type (Famine = 0).
    let mut pool = AgentPool::new(8);
    let slot = spawn_test_agent(&mut pool);

    // LEGACY_HALF_LIFE = 100.0 turns
    let legacy_factor = factor_from_half_life(100.0);

    let intent = MemoryIntent {
        agent_slot: slot,
        expected_agent_id: pool.ids[slot],
        event_type: 0, // Famine — default factor would be famine rate, not legacy rate
        source_civ: 1,
        intensity: -45,
        is_legacy: true,
        decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent, 100);

    // Decay factor should be the legacy override, NOT the famine default
    assert_eq!(
        pool.memory_decay_factors[slot][0],
        legacy_factor,
        "decay factor should be legacy override, not famine default"
    );
    // Legacy bitmask should have bit 0 set (slot 0 is legacy)
    assert_eq!(
        pool.memory_is_legacy[slot] & 1,
        1,
        "legacy bitmask bit 0 should be set"
    );
    // Event type is preserved as Famine (0), not Legacy (14)
    assert_eq!(
        pool.memory_event_types[slot][0],
        0,
        "event_type should be Famine (0), not Legacy (14)"
    );
    // Intensity and other fields preserved
    assert_eq!(pool.memory_intensities[slot][0], -45);
    assert_eq!(pool.memory_source_civs[slot][0], 1);
    assert_eq!(pool.memory_turns[slot][0], 100);
}

#[test]
fn test_non_legacy_memory_clears_bit() {
    // Writing a non-legacy memory to a slot should clear the legacy bit for that slot.
    let mut pool = AgentPool::new(8);
    let slot = spawn_test_agent(&mut pool);

    // Write a non-legacy memory to slot 0
    let intent = MemoryIntent {
        agent_slot: slot,
        expected_agent_id: pool.ids[slot],
        event_type: 1, // Battle
        source_civ: 0,
        intensity: -60,
        is_legacy: false,
        decay_factor_override: None,
    };
    write_single_memory(&mut pool, &intent, 10);

    // Bit 0 should be 0 (not legacy)
    assert_eq!(
        pool.memory_is_legacy[slot] & 1,
        0,
        "non-legacy write should leave bit 0 clear"
    );
}

#[test]
fn test_legacy_bit_cleared_on_eviction() {
    // Fill slot 0 with a weak legacy memory, then fill remaining slots with stronger
    // non-legacy memories. When a 9th memory arrives (stronger than slot 0), slot 0
    // gets evicted and its legacy bit should be cleared.
    let mut pool = AgentPool::new(8);
    let slot = spawn_test_agent(&mut pool);

    let legacy_factor = factor_from_half_life(100.0);

    // Write weak legacy memory to slot 0 (intensity -10)
    let legacy_intent = MemoryIntent {
        agent_slot: slot,
        expected_agent_id: pool.ids[slot],
        event_type: 0, // Famine
        source_civ: 1,
        intensity: -10,
        is_legacy: true,
        decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &legacy_intent, 100);

    // Verify legacy bit is set for slot 0
    assert_eq!(pool.memory_is_legacy[slot] & 1, 1, "slot 0 should be legacy after first write");

    // Fill slots 1-7 with stronger non-legacy memories (intensity -50)
    for i in 1..8 {
        let intent = MemoryIntent {
            agent_slot: slot,
            expected_agent_id: pool.ids[slot],
            event_type: 1, // Battle
            source_civ: 1,
            intensity: -50,
            is_legacy: false,
            decay_factor_override: None,
        };
        write_single_memory(&mut pool, &intent, 100 + i as u16);
    }

    // All 8 slots full. Slot 0 has |intensity| = 10 (weakest).
    assert_eq!(pool.memory_count[slot], 8);
    assert_eq!(pool.memory_is_legacy[slot] & 1, 1, "slot 0 should still be legacy");

    // Write a 9th memory with intensity -80 — should evict slot 0 (weakest at |-10|)
    let strong_intent = MemoryIntent {
        agent_slot: slot,
        expected_agent_id: pool.ids[slot],
        event_type: 2, // Conquest
        source_civ: 1,
        intensity: -80,
        is_legacy: false,
        decay_factor_override: None,
    };
    write_single_memory(&mut pool, &strong_intent, 200);

    // Count stays at 8 (eviction, not growth)
    assert_eq!(pool.memory_count[slot], 8);
    // Legacy bit for evicted slot 0 should be cleared
    assert_eq!(
        pool.memory_is_legacy[slot],
        0,
        "all legacy bits should be 0 after evicting the only legacy slot"
    );
    // Slot 0 now holds the new conquest memory
    assert_eq!(pool.memory_event_types[slot][0], 2); // Conquest
    assert_eq!(pool.memory_intensities[slot][0], -80);
}

#[test]
fn test_legacy_bit_uses_slot_index() {
    // Write legacy to slot 2, verify only bit 2 is set (not bit 0 or bit 1).
    let mut pool = AgentPool::new(8);
    let slot = spawn_test_agent(&mut pool);

    let legacy_factor = factor_from_half_life(100.0);

    // Fill slots 0 and 1 with non-legacy memories first
    for i in 0..2 {
        let intent = MemoryIntent {
            agent_slot: slot,
            expected_agent_id: pool.ids[slot],
            event_type: 1,
            source_civ: 0,
            intensity: -50,
            is_legacy: false,
            decay_factor_override: None,
        };
        write_single_memory(&mut pool, &intent, i as u16);
    }

    // Write legacy to slot 2 (third write)
    let intent = MemoryIntent {
        agent_slot: slot,
        expected_agent_id: pool.ids[slot],
        event_type: 0,
        source_civ: 1,
        intensity: -45,
        is_legacy: true,
        decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent, 10);

    // Only bit 2 should be set
    assert_eq!(
        pool.memory_is_legacy[slot],
        1 << 2,
        "only bit 2 should be set when legacy written to slot 2"
    );
}

// ── M51: extract_legacy_memories tests ────────────────────────────────────────

#[test]
fn test_extract_legacy_memories_top_2() {
    // Create agent with 4 memories of varying intensities
    // extract_legacy_memories should return top 2 by |intensity|
    // Intensities: [-30, -90, 50, -10] → sorted by |.|: 90, 50, 30, 10
    // Top 2: (-90→-45, 50→25) — both pass LEGACY_MIN_INTENSITY (10)
    let mut pool = AgentPool::new(8);
    let slot = spawn_test_agent(&mut pool);

    let intensities: &[(u8, u8, i8)] = &[
        (0, 1, -30),  // Famine, civ 1, intensity -30
        (1, 2, -90),  // Battle, civ 2, intensity -90
        (5, 1, 50),   // Prosperity, civ 1, intensity +50
        (3, 0, -10),  // Persecution, civ 0, intensity -10
    ];
    let slot_id = pool.ids[slot];
    for (turn, &(event_type, source_civ, intensity)) in intensities.iter().enumerate() {
        write_single_memory(&mut pool, &MemoryIntent {
            agent_slot: slot,
            expected_agent_id: slot_id,
            event_type,
            source_civ,
            intensity,
            is_legacy: false,
            decay_factor_override: None,
        }, turn as u16);
    }

    let result = extract_legacy_memories(&pool, slot);
    assert_eq!(result.len(), 2, "should extract top 2 memories");

    // Strongest by |intensity|: -90→halved to -45, 50→halved to 25
    // Order: strongest first
    let event_types_in_result: Vec<u8> = result.iter().map(|&(et, _, _)| et).collect();
    assert!(event_types_in_result.contains(&1), "Battle (intensity=-90) should be in result");
    assert!(event_types_in_result.contains(&5), "Prosperity (intensity=50) should be in result");

    // Verify halved intensities
    for &(event_type, _source_civ, halved_intensity) in &result {
        if event_type == 1 {
            assert_eq!(halved_intensity, -45, "Battle intensity should be halved: -90/2 = -45");
        }
        if event_type == 5 {
            assert_eq!(halved_intensity, 25, "Prosperity intensity should be halved: 50/2 = 25");
        }
    }
}

#[test]
fn test_extract_legacy_memories_filters_below_threshold() {
    // Memory with intensity 15 → halved to 7 → below LEGACY_MIN_INTENSITY (10)
    // Should return empty
    let mut pool = AgentPool::new(8);
    let slot = spawn_test_agent(&mut pool);

    let slot_id = pool.ids[slot];
    write_single_memory(&mut pool, &MemoryIntent {
        agent_slot: slot,
        expected_agent_id: slot_id,
        event_type: 0, // Famine
        source_civ: 1,
        intensity: 15, // halved = 7 < 10 threshold
        is_legacy: false,
        decay_factor_override: None,
    }, 10);

    let result = extract_legacy_memories(&pool, slot);
    assert!(result.is_empty(), "memories below threshold after halving should be filtered out");
}

#[test]
fn test_extract_legacy_memories_empty_buffer() {
    // Agent with no memories → empty result
    let mut pool = AgentPool::new(8);
    let slot = spawn_test_agent(&mut pool);

    let result = extract_legacy_memories(&pool, slot);
    assert!(result.is_empty(), "agent with no memories should return empty");
}

#[test]
fn test_legacy_utility_preservation() {
    // Legacy Famine memory should produce same utility modifiers as direct Famine (at lower intensity)
    // Setup: agent with a direct Famine memory at -80
    // Compare: same event_type Famine at lower intensity -40 → should still push migrate
    let mut pool = AgentPool::new(8);
    let slot = spawn_test_agent(&mut pool);

    let slot_id = pool.ids[slot];
    write_single_memory(&mut pool, &MemoryIntent {
        agent_slot: slot,
        expected_agent_id: slot_id,
        event_type: 0, // Famine
        source_civ: 0,
        intensity: -40,
        is_legacy: true,
        decay_factor_override: Some(factor_from_half_life(LEGACY_HALF_LIFE)),
    }, 10);

    let mods = compute_memory_utility_modifiers(&pool, slot);
    // Famine memory should produce a positive migrate boost
    assert!(mods.migrate > 0.0, "legacy famine memory should push migrate utility up: got {}", mods.migrate);
}

#[test]
fn test_legacy_satisfaction_preservation() {
    // Legacy memory contributes to satisfaction score at inherited intensity
    let mut pool = AgentPool::new(8);
    let slot = spawn_test_agent(&mut pool);

    // Write a positive legacy memory
    let slot_id = pool.ids[slot];
    write_single_memory(&mut pool, &MemoryIntent {
        agent_slot: slot,
        expected_agent_id: slot_id,
        event_type: 5, // Prosperity
        source_civ: 0,
        intensity: 50,
        is_legacy: true,
        decay_factor_override: Some(factor_from_half_life(LEGACY_HALF_LIFE)),
    }, 10);

    let score = compute_memory_satisfaction_score(&pool, slot);
    assert!(score > 0.0, "positive legacy memory should yield positive satisfaction score: got {}", score);
}

// ── M51 Task 13: Multi-generational integration tests ─────────────────────────

#[test]
fn test_multi_generational_legacy_decay() {
    let mut pool = AgentPool::new(32);
    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);

    // Gen 1: parent with Persecution at -90
    let parent = spawn_test_agent(&mut pool);
    let orig = MemoryIntent {
        agent_slot: parent,
        expected_agent_id: pool.ids[parent],
        event_type: 3, // Persecution
        source_civ: 1,
        intensity: -90,
        is_legacy: false,
        decay_factor_override: None,
    };
    write_single_memory(&mut pool, &orig, 10);
    assert_eq!(pool.memory_intensities[parent][0], -90);

    // Gen 2: child inherits -90 / 2 = -45
    let child = spawn_test_agent(&mut pool);
    let legacies = extract_legacy_memories(&pool, parent);
    assert_eq!(legacies.len(), 1, "parent should yield 1 legacy memory");
    assert_eq!(legacies[0].2, -45, "Gen2 intensity should be -45 (-90/2)");
    let intent2 = MemoryIntent {
        agent_slot: child,
        expected_agent_id: pool.ids[child],
        event_type: legacies[0].0,
        source_civ: legacies[0].1,
        intensity: legacies[0].2,
        is_legacy: true,
        decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent2, 50);
    assert_eq!(pool.memory_intensities[child][0], -45);

    // Gen 3: grandchild inherits -45 / 2 = -22
    let grandchild = spawn_test_agent(&mut pool);
    let legacies2 = extract_legacy_memories(&pool, child);
    assert_eq!(legacies2.len(), 1, "child should yield 1 legacy memory");
    assert_eq!(legacies2[0].2, -22, "Gen3 intensity should be -22 (-45/2 truncated)");
    let intent3 = MemoryIntent {
        agent_slot: grandchild,
        expected_agent_id: pool.ids[grandchild],
        event_type: legacies2[0].0,
        source_civ: legacies2[0].1,
        intensity: legacies2[0].2,
        is_legacy: true,
        decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent3, 100);
    assert_eq!(pool.memory_intensities[grandchild][0], -22);

    // Gen 4: great-grandchild inherits -22 / 2 = -11
    let great = spawn_test_agent(&mut pool);
    let legacies3 = extract_legacy_memories(&pool, grandchild);
    assert_eq!(legacies3.len(), 1, "grandchild should yield 1 legacy memory");
    assert_eq!(legacies3[0].2, -11, "Gen4 intensity should be -11 (-22/2 truncated)");
    let intent4 = MemoryIntent {
        agent_slot: great,
        expected_agent_id: pool.ids[great],
        event_type: legacies3[0].0,
        source_civ: legacies3[0].1,
        intensity: legacies3[0].2,
        is_legacy: true,
        decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent4, 150);
    assert_eq!(pool.memory_intensities[great][0], -11);

    // Gen 5: -11 / 2 = -5, below LEGACY_MIN_INTENSITY (10) → filtered out
    let legacies4 = extract_legacy_memories(&pool, great);
    assert!(legacies4.is_empty(), "-11/2 = -5, below threshold (10), should be filtered");
}

#[test]
fn test_death_of_kin_and_legacy_same_consolidated_write() {
    let mut pool = AgentPool::new(32);
    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);

    // Parent with a strong Battle memory (-60)
    let parent = spawn_test_agent(&mut pool);
    let battle = MemoryIntent {
        agent_slot: parent,
        expected_agent_id: pool.ids[parent],
        event_type: 1, // Battle
        source_civ: 1,
        intensity: -60,
        is_legacy: false,
        decay_factor_override: None,
    };
    write_single_memory(&mut pool, &battle, 10);
    assert_eq!(pool.memory_intensities[parent][0], -60);

    // Child starts empty
    let child = spawn_test_agent(&mut pool);
    assert_eq!(pool.memory_count[child], 0);

    // Collect both DeathOfKin and legacy Battle intents for same tick
    let mut intents = Vec::new();

    // DeathOfKin intent (event_type=9, not gated)
    intents.push(MemoryIntent {
        agent_slot: child,
        expected_agent_id: pool.ids[child],
        event_type: 9, // DeathOfKin
        source_civ: pool.civ_affinities[parent],
        intensity: -80,
        is_legacy: false,
        decay_factor_override: None,
    });

    // Legacy Battle intent from parent (Battle = event_type 1, -60/2 = -30)
    let legacies = extract_legacy_memories(&pool, parent);
    assert_eq!(legacies.len(), 1, "parent should yield 1 legacy memory");
    assert_eq!(legacies[0].2, -30, "Battle legacy intensity should be -30 (-60/2)");
    for (et, sc, halved) in &legacies {
        intents.push(MemoryIntent {
            agent_slot: child,
            expected_agent_id: pool.ids[child],
            event_type: *et,
            source_civ: *sc,
            intensity: *halved,
            is_legacy: true,
            decay_factor_override: Some(legacy_factor),
        });
    }

    // Consolidated write — both intents should land
    // DeathOfKin (9) is not gated; Battle (1) gate is clear at start
    write_all_memories(&mut pool, &intents, 50);

    // Child should have exactly 2 memories: DeathOfKin + legacy Battle
    assert_eq!(pool.memory_count[child], 2, "child should have 2 memories after consolidated write");
    // At least one slot should be marked legacy (bitmask non-zero)
    assert_ne!(
        pool.memory_is_legacy[child], 0,
        "at least one memory should be marked as legacy"
    );
    // DeathOfKin slot should not be legacy; Battle slot should be legacy
    // Slot 0 = DeathOfKin (first written), Slot 1 = Battle legacy (second written)
    assert_eq!(
        (pool.memory_is_legacy[child] >> 0) & 1, 0,
        "slot 0 (DeathOfKin) should not be legacy"
    );
    assert_eq!(
        (pool.memory_is_legacy[child] >> 1) & 1, 1,
        "slot 1 (Battle legacy) should be legacy"
    );
}

// ── M51 Task 4: FFI 6-tuple tests ─────────────────────────────────────────────

#[test]
fn test_ffi_get_agent_memories_includes_legacy_flag() {
    // Verify the legacy bitmask extraction logic that FFI uses.
    // Write a legacy memory to slot 0 and a non-legacy to slot 1, then
    // confirm the per-slot bit extraction produces the correct flags.
    let mut pool = AgentPool::new(8);
    let slot = spawn_test_agent(&mut pool);

    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);

    // Write legacy memory to slot 0
    let intent = MemoryIntent {
        agent_slot: slot,
        expected_agent_id: pool.ids[slot],
        event_type: 0,
        source_civ: 1,
        intensity: -45,
        is_legacy: true,
        decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent, 100);

    // Verify bitmask extraction for slot 0: (memory_is_legacy[slot] >> 0) & 1 == 1
    let is_legacy_0 = (pool.memory_is_legacy[slot] >> 0) & 1 == 1;
    assert!(is_legacy_0, "slot 0 should be marked legacy after legacy write");

    // Write non-legacy memory to slot 1
    let intent2 = MemoryIntent {
        agent_slot: slot,
        expected_agent_id: pool.ids[slot],
        event_type: 1,
        source_civ: 1,
        intensity: -60,
        is_legacy: false,
        decay_factor_override: None,
    };
    write_single_memory(&mut pool, &intent2, 101);

    let is_legacy_0_after = (pool.memory_is_legacy[slot] >> 0) & 1 == 1;
    let is_legacy_1 = (pool.memory_is_legacy[slot] >> 1) & 1 == 1;
    assert!(is_legacy_0_after, "slot 0 should still be legacy");
    assert!(!is_legacy_1, "slot 1 should not be legacy");
}

#[test]
fn test_legacy_shared_memory_matching() {
    // Two siblings with legacy Battle from same parent should match via agents_share_memory.
    // Siblings receive Battle legacy at same turn — should share via agents_share_memory.
    let mut pool = AgentPool::new(8);
    let sibling_a = spawn_test_agent(&mut pool);
    let sibling_b = spawn_test_agent(&mut pool);

    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);
    let battle_type = 1u8; // Battle

    // Both siblings receive the same legacy Battle memory at turn 42
    let id_a = pool.ids[sibling_a];
    let id_b = pool.ids[sibling_b];
    write_single_memory(&mut pool, &MemoryIntent {
        agent_slot: sibling_a,
        expected_agent_id: id_a,
        event_type: battle_type,
        source_civ: 2,
        intensity: -45,
        is_legacy: true,
        decay_factor_override: Some(legacy_factor),
    }, 42);
    write_single_memory(&mut pool, &MemoryIntent {
        agent_slot: sibling_b,
        expected_agent_id: id_b,
        event_type: battle_type,
        source_civ: 2,
        intensity: -45,
        is_legacy: true,
        decay_factor_override: Some(legacy_factor),
    }, 42);

    let shared = agents_share_memory(&pool, sibling_a, sibling_b);
    assert!(shared.is_some(), "siblings with legacy Battle from same parent should share memory");
    let (event_type, turn) = shared.unwrap();
    assert_eq!(event_type, battle_type, "shared event type should be Battle");
    assert_eq!(turn, 42, "shared turn should be 42");
}
