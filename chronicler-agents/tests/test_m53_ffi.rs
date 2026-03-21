//! M53 FFI integration tests: get_all_memories() bulk Arrow export.

use chronicler_agents::AgentSimulator;
use chronicler_agents::{Occupation, MemoryEventType};

#[test]
fn test_get_all_memories_returns_record_batch() {
    let mut sim = AgentSimulator::new(2, 42);
    // Spawn some agents
    let slot_a = sim.pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let slot_b = sim.pool.spawn(0, 0, Occupation::Soldier, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Manually write memories to agents
    sim.pool.memory_event_types[slot_a][0] = MemoryEventType::Battle as u8;
    sim.pool.memory_turns[slot_a][0] = 10;
    sim.pool.memory_intensities[slot_a][0] = -60;
    sim.pool.memory_count[slot_a] = 1;

    sim.pool.memory_event_types[slot_b][0] = MemoryEventType::Famine as u8;
    sim.pool.memory_turns[slot_b][0] = 15;
    sim.pool.memory_intensities[slot_b][0] = -80;
    sim.pool.memory_event_types[slot_b][1] = MemoryEventType::Prosperity as u8;
    sim.pool.memory_turns[slot_b][1] = 20;
    sim.pool.memory_intensities[slot_b][1] = 40;
    sim.pool.memory_count[slot_b] = 2;

    let batch = sim.get_all_memories().unwrap();
    let inner = batch.as_ref();
    // Schema: agent_id, slot, event_type, turn, intensity, is_legacy, civ_affinity, region, occupation
    assert_eq!(inner.num_columns(), 9);
    assert_eq!(inner.num_rows(), 3); // 1 memory from agent a + 2 from agent b
}
