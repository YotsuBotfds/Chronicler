use chronicler_agents::memory::MemoryIntent;

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
