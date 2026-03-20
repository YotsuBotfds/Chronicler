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
        14 => factor_from_half_life(agent::LEGACY_HALF_LIFE),
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
        min_idx
    };
    pool.memory_event_types[slot][write_idx] = intent.event_type;
    pool.memory_source_civs[slot][write_idx] = intent.source_civ;
    pool.memory_turns[slot][write_idx] = turn;
    pool.memory_intensities[slot][write_idx] = intent.intensity;
    pool.memory_decay_factors[slot][write_idx] = default_decay_factor(intent.event_type);
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
}
