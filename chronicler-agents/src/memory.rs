/// M48 Agent Memory System
/// Spec: docs/superpowers/specs/2026-03-19-m48-agent-memory-design.md
///
/// Each agent has an 8-slot ring buffer of memories. Each slot stores an event
/// type, source civ, turn recorded, intensity (signed), and per-slot decay factor.
/// A gate byte tracks frequency-gated event types to avoid duplicates per tick.

use crate::agent;
use crate::pool::AgentPool;

pub const MEMORY_SLOTS: usize = 8;

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MemoryEventType {
    Famine = 0,
    Battle = 1,
    Conquest = 2,
    Persecution = 3,
    Migration = 4,
    Prosperity = 5,
    Victory = 6,
    Promotion = 7,
    BirthOfKin = 8,
    DeathOfKin = 9,
    Conversion = 10,
    Secession = 11,
    // 12-13 reserved for Phase 8
    Legacy = 14,
    // 15 reserved
}

impl MemoryEventType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Famine),
            1 => Some(Self::Battle),
            2 => Some(Self::Conquest),
            3 => Some(Self::Persecution),
            4 => Some(Self::Migration),
            5 => Some(Self::Prosperity),
            6 => Some(Self::Victory),
            7 => Some(Self::Promotion),
            8 => Some(Self::BirthOfKin),
            9 => Some(Self::DeathOfKin),
            10 => Some(Self::Conversion),
            11 => Some(Self::Secession),
            14 => Some(Self::Legacy),
            _ => None,
        }
    }
}

/// Gate bit assignments for frequency-gated event types.
pub const GATE_BIT_BATTLE: u8 = 1 << 0;
pub const GATE_BIT_PROSPERITY: u8 = 1 << 1;
pub const GATE_BIT_FAMINE: u8 = 1 << 2;
pub const GATE_BIT_PERSECUTION: u8 = 1 << 3;

pub fn gate_bit_for(event_type: u8) -> u8 {
    match event_type {
        1 => GATE_BIT_BATTLE,
        5 => GATE_BIT_PROSPERITY,
        0 => GATE_BIT_FAMINE,
        3 => GATE_BIT_PERSECUTION,
        _ => 0,
    }
}

/// Intent struct for deferred memory writes.
#[derive(Debug, Clone)]
pub struct MemoryIntent {
    pub agent_slot: usize,
    pub event_type: u8,
    pub source_civ: u8,
    pub intensity: i8,
    pub is_legacy: bool,
    pub decay_factor_override: Option<u8>,
}

/// Convert half-life in turns to per-tick decay factor (u8).
/// Returns 0 for infinite or non-positive half-life (no decay).
pub fn factor_from_half_life(half_life: f32) -> u8 {
    if half_life == f32::INFINITY || half_life <= 0.0 {
        return 0;
    }
    let rate = 1.0 - 0.5_f32.powf(1.0 / half_life);
    (rate * 255.0).round().min(255.0) as u8
}

/// Convert per-tick decay factor back to half-life in turns.
/// Returns INFINITY for factor 0 (no decay).
pub fn half_life_from_factor(factor: u8) -> f32 {
    if factor == 0 {
        return f32::INFINITY;
    }
    let rate = factor as f32 / 255.0;
    let base = 1.0 - rate;
    if base <= 0.0 {
        return 1.0;
    }
    (0.5_f32.ln() / base.ln()).abs()
}

/// Lookup table: event_type → precomputed decay_factor.
pub fn default_decay_factor(event_type: u8) -> u8 {
    match event_type {
        0 => factor_from_half_life(agent::FAMINE_HALF_LIFE),
        1 => factor_from_half_life(agent::BATTLE_HALF_LIFE),
        2 => factor_from_half_life(agent::CONQUEST_HALF_LIFE),
        3 => factor_from_half_life(agent::PERSECUTION_HALF_LIFE),
        4 => factor_from_half_life(agent::MIGRATION_HALF_LIFE),
        5 => factor_from_half_life(agent::PROSPERITY_HALF_LIFE),
        6 => factor_from_half_life(agent::VICTORY_HALF_LIFE),
        7 => factor_from_half_life(agent::PROMOTION_HALF_LIFE),
        8 => factor_from_half_life(agent::BIRTHOFKIN_HALF_LIFE),
        9 => factor_from_half_life(agent::DEATHOFKIN_HALF_LIFE),
        10 => factor_from_half_life(agent::CONVERSION_HALF_LIFE),
        11 => factor_from_half_life(agent::SECESSION_HALF_LIFE),
        14 => factor_from_half_life(agent::LEGACY_HALF_LIFE), // Vestigial: M51 legacy memories use original event_type + decay_factor_override
        _ => 0,
    }
}

/// Per-tick decay for all occupied memory slots.
/// Applies exponential decay: new = old * (255 - factor) / 255.
pub fn decay_memories(pool: &mut AgentPool, alive_slots: &[usize]) {
    for &slot in alive_slots {
        let count = pool.memory_count[slot] as usize;
        for i in 0..count {
            let factor = pool.memory_decay_factors[slot][i];
            if factor == 0 {
                continue;
            }
            let intensity = pool.memory_intensities[slot][i] as i16;
            let new_val = (intensity * (255 - factor as i16)) / 255;
            pool.memory_intensities[slot][i] = new_val as i8;
        }
    }
}

/// Write a single memory intent into agent's ring buffer.
/// If all 8 slots are occupied, evicts the slot with lowest |intensity|
/// (ties broken by lowest index).
pub fn write_single_memory(pool: &mut AgentPool, intent: &MemoryIntent, turn: u16) {
    let slot = intent.agent_slot;
    let count = pool.memory_count[slot] as usize;
    let write_idx = if count < MEMORY_SLOTS {
        pool.memory_count[slot] += 1;
        count
    } else {
        // Evict: find slot with minimum |intensity|, tiebreak lowest index.
        let mut min_abs = pool.memory_intensities[slot][0].unsigned_abs();
        let mut min_idx = 0;
        for i in 1..MEMORY_SLOTS {
            let abs = pool.memory_intensities[slot][i].unsigned_abs();
            if abs < min_abs {
                min_abs = abs;
                min_idx = i;
            }
        }
        // Clear legacy bit for evicted slot before overwriting.
        pool.memory_is_legacy[slot] &= !(1 << min_idx);
        min_idx
    };
    pool.memory_event_types[slot][write_idx] = intent.event_type;
    pool.memory_source_civs[slot][write_idx] = intent.source_civ;
    pool.memory_turns[slot][write_idx] = turn;
    pool.memory_intensities[slot][write_idx] = intent.intensity;
    pool.memory_decay_factors[slot][write_idx] = intent
        .decay_factor_override
        .unwrap_or_else(|| default_decay_factor(intent.event_type));
    if intent.is_legacy {
        pool.memory_is_legacy[slot] |= 1 << write_idx;
    } else {
        pool.memory_is_legacy[slot] &= !(1 << write_idx);
    }
}

/// Process all collected memory intents in a single pass.
/// Gate checks happen here (not at collection time).
pub fn write_all_memories(pool: &mut AgentPool, intents: &[MemoryIntent], turn: u16) {
    for intent in intents {
        let slot = intent.agent_slot;
        let gate = gate_bit_for(intent.event_type);
        if gate != 0 && (pool.memory_gates[slot] & gate) != 0 {
            continue; // gated — skip
        }
        write_single_memory(pool, intent, turn);
        if gate != 0 {
            pool.memory_gates[slot] |= gate;
        }
    }
}

/// Clear gate bits based on current conditions.
/// Called before write_all_memories each tick so that recurring events
/// can fire again once the triggering condition has lapsed.
pub fn clear_memory_gates(
    pool: &mut AgentPool,
    alive_slots: &[usize],
    regions: &[crate::region::RegionState],
    contested_regions: &[bool],
) {
    for &slot in alive_slots {
        let gates = pool.memory_gates[slot];
        if gates == 0 {
            continue;
        }
        let region_idx = pool.regions[slot] as usize;
        let region = &regions[region_idx];
        let mut new_gates = gates;
        // Bit 0 (BATTLE): clear if not soldier OR not contested
        if gates & GATE_BIT_BATTLE != 0 {
            let is_soldier = pool.occupations[slot] == crate::agent::Occupation::Soldier as u8;
            let is_contested = contested_regions.get(region_idx).copied().unwrap_or(false);
            if !is_soldier || !is_contested {
                new_gates &= !GATE_BIT_BATTLE;
            }
        }
        // Bit 1 (PROSPERITY): clear if wealth < threshold
        if gates & GATE_BIT_PROSPERITY != 0 {
            if pool.wealth[slot] < crate::agent::PROSPERITY_THRESHOLD {
                new_gates &= !GATE_BIT_PROSPERITY;
            }
        }
        // Bit 2 (FAMINE): clear if food_sufficiency >= 1.0
        if gates & GATE_BIT_FAMINE != 0 {
            if region.food_sufficiency >= 1.0 {
                new_gates &= !GATE_BIT_FAMINE;
            }
        }
        // Bit 3 (PERSECUTION): clear if persecution_intensity == 0
        if gates & GATE_BIT_PERSECUTION != 0 {
            if region.persecution_intensity <= 0.0 {
                new_gates &= !GATE_BIT_PERSECUTION;
            }
        }
        pool.memory_gates[slot] = new_gates;
    }
}

/// Memory-driven additive modifiers for agent decision utilities.
#[derive(Debug, Default)]
pub struct MemoryUtilityModifiers {
    pub rebel: f32,
    pub migrate: f32,
    pub switch: f32,
    pub stay: f32,
}

/// Compute memory-driven utility modifiers for an agent's decision model.
/// Each active memory slot contributes additive modifiers based on event type,
/// intensity, and agent personality/civ context.
pub fn compute_memory_utility_modifiers(pool: &AgentPool, slot: usize) -> MemoryUtilityModifiers {
    let mut mods = MemoryUtilityModifiers::default();
    let count = pool.memory_count[slot] as usize;
    let boldness = pool.boldness[slot];

    for i in 0..count {
        let intensity = pool.memory_intensities[slot][i];
        if intensity == 0 { continue; }
        let scale = intensity as f32 / 128.0;
        let abs_scale = scale.abs();
        let event_type = pool.memory_event_types[slot][i];
        let source_civ = pool.memory_source_civs[slot][i];
        let agent_civ = pool.civ_affinities[slot];

        match event_type {
            0 => { // Famine
                mods.migrate += agent::FAMINE_MIGRATE_BOOST * abs_scale;
            }
            1 => { // Battle
                if boldness > 0.0 {
                    mods.stay += agent::BATTLE_BOLD_STAY_BOOST * abs_scale;
                } else {
                    mods.migrate += agent::BATTLE_CAUTIOUS_MIGRATE_BOOST * abs_scale;
                }
            }
            2 => { // Conquest
                if source_civ == agent_civ {
                    mods.stay += agent::CONQUEST_CONQUEROR_STAY_BOOST * abs_scale;
                } else {
                    mods.migrate += agent::CONQUEST_CONQUERED_MIGRATE_BOOST * abs_scale;
                }
            }
            3 => { // Persecution
                mods.rebel += agent::PERSECUTION_REBEL_BOOST_MEMORY * abs_scale;
                mods.migrate += agent::PERSECUTION_MIGRATE_BOOST_MEMORY * abs_scale;
            }
            5 => { // Prosperity
                mods.migrate -= agent::PROSPERITY_MIGRATE_PENALTY * abs_scale;
                mods.switch -= agent::PROSPERITY_SWITCH_PENALTY * abs_scale;
            }
            6 => { // Victory
                mods.stay += agent::VICTORY_STAY_BOOST * abs_scale;
            }
            9 => { // DeathOfKin
                mods.migrate -= agent::DEATHOFKIN_MIGRATE_PENALTY * abs_scale;
            }
            _ => {}
        }
    }
    mods
}

/// Compute memory satisfaction score for an agent.
/// Sum of all active intensities, scaled and weighted.
pub fn compute_memory_satisfaction_score(pool: &AgentPool, slot: usize) -> f32 {
    let count = pool.memory_count[slot] as usize;
    if count == 0 {
        return 0.0;
    }
    let sum: i16 = pool.memory_intensities[slot][..count]
        .iter()
        .map(|&i| i as i16)
        .sum();
    (sum as f32 / 1024.0) * agent::MEMORY_SATISFACTION_WEIGHT
}

/// Extract top LEGACY_MAX_MEMORIES memories by |intensity| for legacy transfer.
/// Returns Vec of (event_type, source_civ, halved_intensity) tuples.
/// Filters out memories where |halved_intensity| < LEGACY_MIN_INTENSITY.
/// Tiebreak: lowest slot index wins.
pub fn extract_legacy_memories(
    pool: &AgentPool,
    slot: usize,
) -> Vec<(u8, u8, i8)> {
    use crate::agent::{LEGACY_MAX_MEMORIES, LEGACY_MIN_INTENSITY};

    let count = pool.memory_count[slot] as usize;
    if count == 0 {
        return Vec::new();
    }

    // Collect (|intensity|, slot_index) pairs, sort descending by |intensity|, tiebreak ascending by index
    let mut ranked: Vec<(i8, usize)> = (0..count)
        .map(|i| (pool.memory_intensities[slot][i], i))
        .collect();
    ranked.sort_by(|a, b| {
        let abs_cmp = (b.0 as i16).unsigned_abs().cmp(&(a.0 as i16).unsigned_abs());
        if abs_cmp == std::cmp::Ordering::Equal {
            a.1.cmp(&b.1) // lower index wins tie
        } else {
            abs_cmp
        }
    });

    ranked
        .into_iter()
        .take(LEGACY_MAX_MEMORIES)
        .filter_map(|(intensity, idx)| {
            let halved = intensity / 2; // integer division truncating toward zero
            if (halved as i16).unsigned_abs() < LEGACY_MIN_INTENSITY as u16 {
                return None;
            }
            Some((
                pool.memory_event_types[slot][idx],
                pool.memory_source_civs[slot][idx],
                halved,
            ))
        })
        .collect()
}

/// M50 interface: Check if two agents share a memory (same event_type, turn within +/-1).
/// Returns (event_type, turn) of the strongest shared match, or None.
pub fn agents_share_memory(pool: &AgentPool, a: usize, b: usize) -> Option<(u8, u16)> {
    let count_a = pool.memory_count[a] as usize;
    let count_b = pool.memory_count[b] as usize;
    let mut best: Option<(u8, u16, u16)> = None; // (event_type, turn, combined_intensity)
    for i in 0..count_a {
        let et_a = pool.memory_event_types[a][i];
        let turn_a = pool.memory_turns[a][i];
        let int_a = pool.memory_intensities[a][i].unsigned_abs() as u16;
        for j in 0..count_b {
            if pool.memory_event_types[b][j] == et_a
                && turn_a.abs_diff(pool.memory_turns[b][j]) <= 1
            {
                let combined = int_a + pool.memory_intensities[b][j].unsigned_abs() as u16;
                if best.is_none() || combined > best.unwrap().2 {
                    best = Some((et_a, turn_a, combined));
                }
            }
        }
    }
    best.map(|(et, turn, _)| (et, turn))
}

/// M50b interface: Check if two agents share a memory (same event_type, turn within +/-1).
/// Returns (event_type, turn, intensity_a, intensity_b) of the strongest shared match
/// (by combined absolute intensity), preserving the original signed values.
/// Used by Grudge formation gate to detect negative-valence shared experiences.
pub fn agents_share_memory_with_valence(
    pool: &AgentPool,
    a: usize,
    b: usize,
) -> Option<(u8, u16, i8, i8)> {
    let count_a = pool.memory_count[a] as usize;
    let count_b = pool.memory_count[b] as usize;
    // (event_type, turn, intensity_a, intensity_b, combined_abs)
    let mut best: Option<(u8, u16, i8, i8, u16)> = None;
    for i in 0..count_a {
        let et_a = pool.memory_event_types[a][i];
        let turn_a = pool.memory_turns[a][i];
        let int_a = pool.memory_intensities[a][i];
        let abs_a = int_a.unsigned_abs() as u16;
        for j in 0..count_b {
            if pool.memory_event_types[b][j] == et_a
                && turn_a.abs_diff(pool.memory_turns[b][j]) <= 1
            {
                let int_b = pool.memory_intensities[b][j];
                let combined = abs_a + int_b.unsigned_abs() as u16;
                if best.is_none() || combined > best.unwrap().4 {
                    best = Some((et_a, turn_a, int_a, int_b, combined));
                }
            }
        }
    }
    best.map(|(et, turn, int_a, int_b, _)| (et, turn, int_a, int_b))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_event_type_roundtrip() {
        let variants = [
            (0, MemoryEventType::Famine),
            (1, MemoryEventType::Battle),
            (2, MemoryEventType::Conquest),
            (3, MemoryEventType::Persecution),
            (4, MemoryEventType::Migration),
            (5, MemoryEventType::Prosperity),
            (6, MemoryEventType::Victory),
            (7, MemoryEventType::Promotion),
            (8, MemoryEventType::BirthOfKin),
            (9, MemoryEventType::DeathOfKin),
            (10, MemoryEventType::Conversion),
            (11, MemoryEventType::Secession),
            (14, MemoryEventType::Legacy),
        ];
        for (val, expected) in variants {
            assert_eq!(MemoryEventType::from_u8(val), Some(expected));
            assert_eq!(expected as u8, val);
        }
        // Reserved/invalid values
        assert_eq!(MemoryEventType::from_u8(12), None);
        assert_eq!(MemoryEventType::from_u8(13), None);
        assert_eq!(MemoryEventType::from_u8(15), None);
        assert_eq!(MemoryEventType::from_u8(255), None);
    }

    #[test]
    fn test_gate_bits() {
        assert_eq!(gate_bit_for(1), GATE_BIT_BATTLE);
        assert_eq!(gate_bit_for(5), GATE_BIT_PROSPERITY);
        assert_eq!(gate_bit_for(0), GATE_BIT_FAMINE);
        assert_eq!(gate_bit_for(3), GATE_BIT_PERSECUTION);
        // Non-gated types return 0
        assert_eq!(gate_bit_for(2), 0);
        assert_eq!(gate_bit_for(4), 0);
        assert_eq!(gate_bit_for(14), 0);
    }

    #[test]
    fn test_default_decay_factor_known_types() {
        // All known event types should produce a nonzero decay factor
        for et in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14] {
            assert!(default_decay_factor(et) > 0, "event type {} gave factor 0", et);
        }
        // Unknown types return 0
        assert_eq!(default_decay_factor(12), 0);
        assert_eq!(default_decay_factor(255), 0);
    }

    // ── agents_share_memory_with_valence tests ─────────────────────────────────

    fn make_pool_with_two_agents() -> (crate::pool::AgentPool, usize, usize) {
        let mut pool = crate::pool::AgentPool::new(4);
        let a = pool.spawn(0, 0, crate::agent::Occupation::Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, crate::agent::BELIEF_NONE);
        let b = pool.spawn(0, 0, crate::agent::Occupation::Farmer, 30, 0.5, 0.5, 0.5, 0, 1, 2, crate::agent::BELIEF_NONE);
        (pool, a, b)
    }

    #[test]
    fn test_valence_shared_battle_returns_correct_fields() {
        // Two agents share a Battle memory at the same turn — should return
        // (event_type=1, turn=50, intensity_a, intensity_b) with correct signed values.
        let (mut pool, a, b) = make_pool_with_two_agents();
        let battle = MemoryEventType::Battle as u8;

        write_single_memory(&mut pool, &MemoryIntent { agent_slot: a, event_type: battle, source_civ: 1, intensity: -40, is_legacy: false, decay_factor_override: None }, 50);
        write_single_memory(&mut pool, &MemoryIntent { agent_slot: b, event_type: battle, source_civ: 1, intensity: -35, is_legacy: false, decay_factor_override: None }, 50);

        let result = agents_share_memory_with_valence(&pool, a, b);
        assert!(result.is_some(), "Expected a shared memory match");
        let (et, turn, int_a, int_b) = result.unwrap();
        assert_eq!(et, battle, "event_type should be Battle");
        assert_eq!(turn, 50, "turn should be 50");
        assert_eq!(int_a, -40, "intensity_a should be -40");
        assert_eq!(int_b, -35, "intensity_b should be -35");
    }

    #[test]
    fn test_valence_different_event_types_returns_none() {
        // Agent a has a Battle memory, agent b has a Famine memory — no shared type.
        let (mut pool, a, b) = make_pool_with_two_agents();

        write_single_memory(&mut pool, &MemoryIntent { agent_slot: a, event_type: MemoryEventType::Battle as u8, source_civ: 1, intensity: -40, is_legacy: false, decay_factor_override: None }, 50);
        write_single_memory(&mut pool, &MemoryIntent { agent_slot: b, event_type: MemoryEventType::Famine as u8, source_civ: 1, intensity: -35, is_legacy: false, decay_factor_override: None }, 50);

        let result = agents_share_memory_with_valence(&pool, a, b);
        assert!(result.is_none(), "Different event types should not match");
    }

    #[test]
    fn test_valence_opposite_sign_intensities_both_returned() {
        // One agent experienced a Conquest as positive (glory), the other as negative (loss).
        // The function should preserve both signed values.
        let (mut pool, a, b) = make_pool_with_two_agents();
        let conquest = MemoryEventType::Conquest as u8;

        write_single_memory(&mut pool, &MemoryIntent { agent_slot: a, event_type: conquest, source_civ: 2, intensity: 50, is_legacy: false, decay_factor_override: None }, 80);
        write_single_memory(&mut pool, &MemoryIntent { agent_slot: b, event_type: conquest, source_civ: 2, intensity: -45, is_legacy: false, decay_factor_override: None }, 80);

        let result = agents_share_memory_with_valence(&pool, a, b);
        assert!(result.is_some(), "Expected a shared memory match");
        let (et, turn, int_a, int_b) = result.unwrap();
        assert_eq!(et, conquest);
        assert_eq!(turn, 80);
        assert_eq!(int_a, 50, "intensity_a should be positive");
        assert_eq!(int_b, -45, "intensity_b should be negative");
    }

    #[test]
    fn test_valence_no_memories_returns_none() {
        // Both agents have zero memories — should return None immediately.
        let (pool, a, b) = make_pool_with_two_agents();
        assert!(agents_share_memory_with_valence(&pool, a, b).is_none());
    }

    #[test]
    fn test_valence_picks_strongest_by_combined_abs() {
        // Agent a has two memories of same type; agent b matches both. The stronger
        // combined-abs pair should be returned.
        let (mut pool, a, b) = make_pool_with_two_agents();
        let battle = MemoryEventType::Battle as u8;

        // Weak pair: abs sum = 10 + 10 = 20
        write_single_memory(&mut pool, &MemoryIntent { agent_slot: a, event_type: battle, source_civ: 1, intensity: 10, is_legacy: false, decay_factor_override: None }, 10);
        write_single_memory(&mut pool, &MemoryIntent { agent_slot: b, event_type: battle, source_civ: 1, intensity: 10, is_legacy: false, decay_factor_override: None }, 10);

        // Strong pair: abs sum = 60 + 55 = 115
        write_single_memory(&mut pool, &MemoryIntent { agent_slot: a, event_type: battle, source_civ: 1, intensity: 60, is_legacy: false, decay_factor_override: None }, 20);
        write_single_memory(&mut pool, &MemoryIntent { agent_slot: b, event_type: battle, source_civ: 1, intensity: 55, is_legacy: false, decay_factor_override: None }, 20);

        let result = agents_share_memory_with_valence(&pool, a, b);
        assert!(result.is_some());
        let (_, turn, int_a, int_b) = result.unwrap();
        assert_eq!(turn, 20, "strongest pair should be at turn 20");
        assert_eq!(int_a, 60);
        assert_eq!(int_b, 55);
    }
}
