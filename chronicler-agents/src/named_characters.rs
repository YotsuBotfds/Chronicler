//! Named character registry for M30 agent narrative promotion.
//!
//! Tracks which agents have been promoted to named characters.
//! Names are owned by Python — Rust tracks agent_id, role, and history only.

use crate::agent::PROMOTION_DURATION_TURNS;
use crate::pool::AgentPool;

/// Character roles map to GreatPerson roles, not agent occupations.
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CharacterRole {
    General = 0,
    Merchant = 1,
    Scientist = 2,
    Prophet = 3,
    Exile = 4,
}

/// Compact record of a promoted named character.
#[derive(Clone, Debug)]
pub struct NamedCharacter {
    pub agent_id: u32,
    pub role: CharacterRole,
    pub civ_id: u8,
    pub origin_civ_id: u8,
    pub born_turn: u16,
    pub promotion_turn: u16,
    pub promotion_trigger: u8, // 0=skill, 1=rebellion, 2=displacement, 3=migration, 4=versatility
    pub parent_id_0: u32,
    pub parent_id_1: u32,
    pub history: Vec<(u16, u8, u16)>, // (turn, event_type, region)
}

/// Per-civ cap on named characters.
const PER_CIV_CAP: usize = 10;
/// Global cap on named characters.
const GLOBAL_CAP: usize = 50;

/// Registry of all promoted named characters.
pub struct NamedCharacterRegistry {
    pub characters: Vec<NamedCharacter>,
}

impl NamedCharacterRegistry {
    pub fn new() -> Self {
        Self {
            characters: Vec::new(),
        }
    }

    /// Count characters belonging to a specific civ.
    pub fn count_for_civ(&self, civ_id: u8) -> usize {
        self.characters.iter().filter(|c| c.civ_id == civ_id).count()
    }

    /// Check if adding a character for this civ would exceed caps.
    pub fn can_promote(&self, civ_id: u8) -> bool {
        self.characters.len() < GLOBAL_CAP && self.count_for_civ(civ_id) < PER_CIV_CAP
    }

    /// Find promotion candidates from the pool.
    ///
    /// Returns (slot, CharacterRole, trigger) tuples for agents that qualify.
    pub fn find_candidates(&self, pool: &AgentPool, turn: u32) -> Vec<(usize, CharacterRole, u8)> {
        let mut candidates = Vec::new();
        let already_promoted: std::collections::HashSet<u32> = self
            .characters
            .iter()
            .map(|c| c.agent_id)
            .collect();

        for slot in 0..pool.capacity() {
            if !pool.is_alive(slot) {
                continue;
            }
            let agent_id = pool.id(slot);
            if already_promoted.contains(&agent_id) {
                continue;
            }
            // Life-event gate — must have at least one qualifying event
            if pool.life_events[slot] == 0 {
                continue;
            }

            let civ_id = pool.civ_affinity(slot);
            if !self.can_promote(civ_id) {
                continue;
            }

            // Check bypass triggers first (skip skill gate)
            if let Some((role, trigger)) = self.check_bypass_triggers(pool, slot, turn) {
                candidates.push((slot, role, trigger));
                continue;
            }

            // Two-gate: skill gate
            if pool.promotion_progress[slot] >= PROMOTION_DURATION_TURNS {
                let occ = pool.occupations[slot];
                let role = match occ {
                    1 => CharacterRole::General,  // Soldier
                    2 => CharacterRole::Merchant,
                    3 => CharacterRole::Scientist, // Scholar
                    4 => CharacterRole::Prophet,   // Priest
                    _ => CharacterRole::Merchant,  // Farmer → default Merchant
                };
                candidates.push((slot, role, 0)); // trigger 0 = skill
            }
        }
        candidates
    }

    /// Check bypass triggers for a single agent.
    /// Returns (CharacterRole, trigger_id) if a bypass fires.
    fn check_bypass_triggers(
        &self,
        pool: &AgentPool,
        slot: usize,
        _turn: u32,
    ) -> Option<(CharacterRole, u8)> {
        let life = pool.life_events[slot];
        let occ = pool.occupations[slot];

        // Bypass 1: Rebellion leader (bit 0 set)
        // In practice, the "led" distinction needs Python context.
        // Rust checks: participated in rebellion.
        if life & crate::agent::LIFE_EVENT_REBELLION != 0 {
            let role = if occ == 1 {
                CharacterRole::General
            } else {
                CharacterRole::Prophet
            };
            return Some((role, 1));
        }

        // Bypasses 2-4 (long displacement, serial migrant, occupation versatility)
        // are deferred to Python which can count from event history.
        // displacement_turns is a short decrementing cooldown, not an accumulator,
        // so checking it here would be dead code.

        None
    }

    /// Register a promoted character.
    pub fn register(
        &mut self,
        agent_id: u32,
        role: CharacterRole,
        civ_id: u8,
        origin_civ_id: u8,
        born_turn: u16,
        promotion_turn: u16,
        promotion_trigger: u8,
        parent_id_0: u32,
        parent_id_1: u32,
    ) {
        self.characters.push(NamedCharacter {
            agent_id,
            role,
            civ_id,
            origin_civ_id,
            born_turn,
            promotion_turn,
            promotion_trigger,
            parent_id_0,
            parent_id_1,
            history: Vec::new(),
        });
    }

    /// Update civ_id for a character (conquest/secession sync).
    pub fn set_character_civ(&mut self, agent_id: u32, new_civ_id: u8) {
        for c in &mut self.characters {
            if c.agent_id == agent_id {
                c.civ_id = new_civ_id;
                break;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::*;
    use crate::pool::AgentPool;

    #[test]
    fn test_promotion_two_gates() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Soldier, 20, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let registry = NamedCharacterRegistry::new();

        // No life events, no promotion progress → no candidates
        assert!(registry.find_candidates(&pool, 100).is_empty());

        // Skill gate passes, life-event gate fails → no candidates
        pool.promotion_progress[slot] = PROMOTION_DURATION_TURNS;
        assert!(registry.find_candidates(&pool, 100).is_empty());

        // Both gates pass → candidate found
        pool.life_events[slot] |= LIFE_EVENT_MIGRATION;
        let candidates = registry.find_candidates(&pool, 100);
        assert_eq!(candidates.len(), 1);
        assert_eq!(candidates[0].1, CharacterRole::General); // soldier → general
    }

    #[test]
    fn test_bypass_triggers() {
        let mut pool = AgentPool::new(4);
        // Priest with rebellion → Prophet
        let slot = pool.spawn(0, 0, Occupation::Priest, 20, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.life_events[slot] |= LIFE_EVENT_REBELLION;
        let registry = NamedCharacterRegistry::new();
        let candidates = registry.find_candidates(&pool, 100);
        assert_eq!(candidates.len(), 1);
        assert_eq!(candidates[0].1, CharacterRole::Prophet);
        assert_eq!(candidates[0].2, 1); // trigger 1 = rebellion
    }

    #[test]
    fn test_promotion_caps() {
        let mut registry = NamedCharacterRegistry::new();
        // Fill per-civ cap for civ 0
        for i in 0..10 {
            registry.register(i, CharacterRole::General, 0, 0, 0, 100, 0, 0, 0);
        }
        assert!(!registry.can_promote(0)); // civ 0 full
        assert!(registry.can_promote(1));  // civ 1 still has room

        // Fill global cap
        for i in 10..50 {
            registry.register(i, CharacterRole::Merchant, (i % 5) as u8 + 1, 0, 0, 100, 0, 0, 0);
        }
        assert!(!registry.can_promote(1)); // global cap hit
    }

    #[test]
    fn test_character_role_mapping() {
        assert_eq!(CharacterRole::General as u8, 0);
        assert_eq!(CharacterRole::Merchant as u8, 1);
        assert_eq!(CharacterRole::Scientist as u8, 2);
        assert_eq!(CharacterRole::Prophet as u8, 3);
        assert_eq!(CharacterRole::Exile as u8, 4);
    }

    #[test]
    fn test_set_agent_civ() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(pool.civ_affinity(slot), 0);
        pool.set_civ_affinity(slot, 3);
        assert_eq!(pool.civ_affinity(slot), 3);
        let mut registry = NamedCharacterRegistry::new();
        registry.register(pool.id(slot), CharacterRole::General, 0, 0, 0, 100, 0, 0, 0);
        registry.set_character_civ(pool.id(slot), 3);
        assert_eq!(registry.characters[0].civ_id, 3);
    }

    #[test]
    fn test_named_character_parent_id() {
        let mut registry = NamedCharacterRegistry::new();
        registry.register(42, CharacterRole::General, 0, 0, 0, 100, 0, 7, 8);
        assert_eq!(registry.characters[0].parent_id_0, 7);
        assert_eq!(registry.characters[0].parent_id_1, 8);

        // PARENT_NONE case
        registry.register(43, CharacterRole::Merchant, 1, 1, 0, 110, 0, crate::agent::PARENT_NONE, crate::agent::PARENT_NONE);
        assert_eq!(registry.characters[1].parent_id_0, crate::agent::PARENT_NONE);
        assert_eq!(registry.characters[1].parent_id_1, crate::agent::PARENT_NONE);
    }
}
