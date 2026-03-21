use chronicler_agents::memory::MemoryIntent;
use chronicler_agents::{AgentPool, Occupation, BELIEF_NONE, factor_from_half_life, write_single_memory};

#[test]
fn test_memory_intent_legacy_fields() {
    let intent = MemoryIntent {
        agent_slot: 0,
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
