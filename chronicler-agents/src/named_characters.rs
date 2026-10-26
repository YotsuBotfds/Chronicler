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
    /// Reserved wire id 4, kept so the enum matches Python `ROLE_MAP` and its
    /// declaration order. Never produced by promotion: on a GreatPerson
    /// `exile` means a deposed-leader pretender (Python `succession.py`),
    /// which an agent promotion must not create; Python rejects role 4 in
    /// promotion batches.
    Exile = 4,
}

impl CharacterRole {
    /// The roles a movement leader can take (general, prophet, or a merchant
    /// for a guild's movement), from the wire id; None for any other id.
    pub fn from_leader_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::General),
            1 => Some(Self::Merchant),
            3 => Some(Self::Prophet),
            _ => None,
        }
    }
}

/// Promotion trigger of an agent movement's leader (queued by Python
/// through `queue_movement_leaders`); 0 skill, 1 rebellion, 2-4 reserved.
pub const TRIGGER_MOVEMENT_LEADER: u8 = 5;

/// Compact record of a promoted named character.
#[derive(Clone, Debug)]
pub struct NamedCharacter {
    pub agent_id: u32,
    pub role: CharacterRole,
    pub civ_id: u8,
    pub origin_civ_id: u8,
    pub born_turn: u16,
    pub promotion_turn: u16,
    pub promotion_trigger: u8, // 0=skill, 1=rebellion; 2-4 reserved (Python relabels roles, not triggers); 5=movement leader
    pub parent_id_0: u32,
    pub parent_id_1: u32,
    pub history: Vec<(u16, u8, u16)>, // (turn, event_type, region)
}

// 2026-10 correction (docs/integration/procedural-gates.md): the caps used
// to count every character ever named, dead included, so the registry filled
// within the first 50 turns of every world (often in one rebellion's batch)
// and agent-born great persons stopped for the rest of the run. They now
// count living characters, scale with each civ's living agents, and hold
// within a batch.

/// Most living named characters a civ may hold.
pub const PER_CIV_CAP: usize = 10;
/// Most living named characters in the world (a safety valve).
pub const GLOBAL_CAP: usize = 50;
/// Regular promotions: a civ holds one living named character per this many
/// of its living agents, at least `MIN_NAMED_PER_CIV` and at most `PER_CIV_CAP`.
pub const AGENTS_PER_NAMED: usize = 50;
/// Regular promotions: living named characters any civ may hold.
pub const MIN_NAMED_PER_CIV: usize = 1;

/// Living named characters, in all and per civ (by the agent's current civ),
/// counted once per promotion pass and raised as candidates are accepted, so
/// the caps also hold within one turn's batch.
pub struct LivingNamed {
    pub per_civ: [usize; 256],
    pub total: usize,
    /// Living agents per civ (the population a civ's regular cap scales with).
    pub agents_per_civ: [usize; 256],
}

impl LivingNamed {
    /// A civ's cap for regular promotions: one per `AGENTS_PER_NAMED` living
    /// agents, clamped to [`MIN_NAMED_PER_CIV`, `PER_CIV_CAP`].
    pub fn regular_cap(&self, civ_id: u8) -> usize {
        (self.agents_per_civ[civ_id as usize] / AGENTS_PER_NAMED).clamp(MIN_NAMED_PER_CIV, PER_CIV_CAP)
    }

    /// Room for one more regular promotion in `civ_id`.
    pub fn admits_regular(&self, civ_id: u8) -> bool {
        self.total < GLOBAL_CAP && self.per_civ[civ_id as usize] < self.regular_cap(civ_id)
    }

    /// Room for a movement leader: the fixed caps over living characters
    /// (a movement asks for its leader; the population cap does not apply).
    pub fn admits_leader(&self, civ_id: u8) -> bool {
        self.total < GLOBAL_CAP && self.per_civ[civ_id as usize] < PER_CIV_CAP
    }

    pub fn add(&mut self, civ_id: u8) {
        self.total += 1;
        self.per_civ[civ_id as usize] += 1;
    }
}

/// Registry of all promoted named characters.
///
/// The registry keeps every character, dead or alive, for history and
/// provenance, and an agent id is never registered twice (pool ids are never
/// reused). The caps count living characters only: a character's slot opens
/// when its agent dies.
pub struct NamedCharacterRegistry {
    pub characters: Vec<NamedCharacter>,
}

impl NamedCharacterRegistry {
    pub fn new() -> Self {
        Self {
            characters: Vec::new(),
        }
    }

    /// Living named characters and living agents, per civ, in one pool pass.
    pub fn living_named(&self, pool: &AgentPool) -> LivingNamed {
        let named: std::collections::HashSet<u32> =
            self.characters.iter().map(|c| c.agent_id).collect();
        let mut out = LivingNamed { per_civ: [0; 256], total: 0, agents_per_civ: [0; 256] };
        for slot in 0..pool.capacity() {
            if !pool.is_alive(slot) {
                continue;
            }
            let civ = pool.civ_affinity(slot);
            out.agents_per_civ[civ as usize] += 1;
            if named.contains(&pool.id(slot)) {
                out.add(civ);
            }
        }
        out
    }

    /// Find promotion candidates from the pool.
    ///
    /// Returns (slot, CharacterRole, trigger) tuples for agents that qualify,
    /// in slot order, while their civ has room under the living caps
    /// (`living` is raised for each accepted candidate).
    pub fn find_candidates(&self, pool: &AgentPool, turn: u32) -> Vec<(usize, CharacterRole, u8)> {
        let mut living = self.living_named(pool);
        self.find_candidates_with(pool, turn, &mut living, &std::collections::HashSet::new())
    }

    /// [`find_candidates`](Self::find_candidates) against counts the caller
    /// already holds, skipping the agent ids in `skip`.
    pub fn find_candidates_with(
        &self,
        pool: &AgentPool,
        turn: u32,
        living: &mut LivingNamed,
        skip: &std::collections::HashSet<u32>,
    ) -> Vec<(usize, CharacterRole, u8)> {
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
            if already_promoted.contains(&agent_id) || skip.contains(&agent_id) {
                continue;
            }
            // Life-event gate — must have at least one qualifying event
            if pool.life_events[slot] == 0 {
                continue;
            }

            let civ_id = pool.civ_affinity(slot);
            if !living.admits_regular(civ_id) {
                continue;
            }

            // Check bypass triggers first (skip skill gate)
            if let Some((role, trigger)) = self.check_bypass_triggers(pool, slot, turn) {
                candidates.push((slot, role, trigger));
                living.add(civ_id);
                continue;
            }

            // Two-gate: skill gate
            if pool.promotion_progress[slot] >= PROMOTION_DURATION_TURNS {
                let occ = pool.occupations[slot];
                // Map occupation to CharacterRole via Occupation::from_u8 instead of
                // raw integer literals.  Farmer (0) has no dedicated CharacterRole,
                // so it falls through to Merchant as default.
                let role = match crate::agent::Occupation::from_u8(occ) {
                    Some(crate::agent::Occupation::Soldier)  => CharacterRole::General,
                    Some(crate::agent::Occupation::Merchant) => CharacterRole::Merchant,
                    Some(crate::agent::Occupation::Scholar)  => CharacterRole::Scientist,
                    Some(crate::agent::Occupation::Priest)   => CharacterRole::Prophet,
                    Some(crate::agent::Occupation::Farmer) | None => CharacterRole::Merchant,
                };
                candidates.push((slot, role, 0)); // trigger 0 = skill
                living.add(civ_id);
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

        // Triggers 2-4 stay out of Rust by design. The pool keeps life-event
        // bits and `displacement_turns` (a short decrementing cooldown), not
        // lifetime migration/switch counts, so Rust cannot evaluate them.
        // Python relabels the role of skill-gated candidates (trigger 0) from
        // its full agent event history: 3+ migrations -> Merchant, 3+
        // occupation switches -> Scientist. These relabel; they do not bypass
        // this gate. "Long displacement -> Exile" was dropped: Exile is the
        // deposed-leader pretender role and must not come from promotion.

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

    /// Deferred backlog: promotion never emits the reserved Exile role, and
    /// only triggers 0 (skill) and 1 (rebellion) come from Rust.
    #[test]
    fn test_promotion_never_emits_exile_role() {
        let occupations = [
            Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
            Occupation::Scholar, Occupation::Priest,
        ];
        // One agent per pool: each civ's cap admits one regular promotion.
        for (i, &occ) in occupations.iter().enumerate() {
            for life in [LIFE_EVENT_REBELLION, LIFE_EVENT_MIGRATION, 0xFF] {
                let mut pool = AgentPool::new(4);
                let slot = pool.spawn(0, (i % 3) as u8, occ, 30, 0.0, 0.0, 0.0, 0, 1, 2, BELIEF_NONE);
                pool.life_events[slot] = life;
                pool.promotion_progress[slot] = PROMOTION_DURATION_TURNS;
                pool.displacement_turns[slot] = u8::MAX;
                let candidates = NamedCharacterRegistry::new().find_candidates(&pool, 500);
                assert_eq!(candidates.len(), 1);
                let (_, role, trigger) = candidates[0];
                assert_ne!(role, CharacterRole::Exile);
                assert!(trigger <= 1, "unexpected Rust trigger {trigger}");
            }
        }
    }

    /// Spawn `n` rebels (bypass candidates) of `civ`; returns their slots.
    fn spawn_rebels(pool: &mut AgentPool, civ: u8, n: usize) -> Vec<usize> {
        (0..n)
            .map(|_| {
                let slot = pool.spawn(0, civ, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, BELIEF_NONE);
                pool.life_events[slot] |= LIFE_EVENT_REBELLION;
                slot
            })
            .collect()
    }

    fn promote(registry: &mut NamedCharacterRegistry, pool: &AgentPool, turn: u32) -> usize {
        let found = registry.find_candidates(pool, turn);
        for &(slot, role, trigger) in &found {
            let civ = pool.civ_affinity(slot);
            registry.register(pool.id(slot), role, civ, civ, 0, turn as u16, trigger, 0, 0);
        }
        found.len()
    }

    #[test]
    fn test_regular_cap_scales_with_the_civs_living_agents() {
        let mut living = LivingNamed { per_civ: [0; 256], total: 0, agents_per_civ: [0; 256] };
        living.agents_per_civ[0] = AGENTS_PER_NAMED - 1;
        living.agents_per_civ[1] = 2 * AGENTS_PER_NAMED;
        living.agents_per_civ[2] = 1000 * AGENTS_PER_NAMED;
        assert_eq!(living.regular_cap(0), 1);
        assert_eq!(living.regular_cap(1), 2);
        assert_eq!(living.regular_cap(2), PER_CIV_CAP);
        assert_eq!(living.regular_cap(3), MIN_NAMED_PER_CIV); // a civ with no agents
    }

    /// The caps hold within one batch: a rebellion of thirty promotes only
    /// as many as the civ's cap (before 2026-10 all thirty were named at once).
    #[test]
    fn test_caps_hold_within_one_batch() {
        let mut pool = AgentPool::new(256);
        spawn_rebels(&mut pool, 0, 30);
        for _ in 0..(2 * AGENTS_PER_NAMED - 30) {
            pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, BELIEF_NONE);
        }
        let mut registry = NamedCharacterRegistry::new();
        assert_eq!(promote(&mut registry, &pool, 10), 2);
        assert_eq!(registry.living_named(&pool).per_civ[0], 2);
        assert_eq!(promote(&mut registry, &pool, 11), 0); // full while both live
    }

    /// The registry keeps the dead (history, provenance) but their slots
    /// open: promotions continue for the whole run, and no agent id is named
    /// twice.
    #[test]
    fn test_dead_characters_free_their_slots_and_keep_their_records() {
        let mut pool = AgentPool::new(256);
        spawn_rebels(&mut pool, 0, 40); // under AGENTS_PER_NAMED: one at a time
        let mut registry = NamedCharacterRegistry::new();
        let mut named = 0;
        for turn in 0..20u32 {
            assert_eq!(promote(&mut registry, &pool, turn), 1, "turn {turn}");
            named += 1;
            // The living character dies: the next turn names another.
            for c in &registry.characters {
                if let Some(slot) = pool.find_slot_by_id(c.agent_id) {
                    pool.kill(slot);
                }
            }
        }
        assert_eq!(registry.characters.len(), named);
        let ids: std::collections::HashSet<u32> = registry.characters.iter().map(|c| c.agent_id).collect();
        assert_eq!(ids.len(), named);
        assert_eq!(registry.living_named(&pool).total, 0);
        // A new agent reusing a dead character's slot gets a new id and may be named.
        let slot = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, BELIEF_NONE);
        pool.life_events[slot] |= LIFE_EVENT_REBELLION;
        assert!(!ids.contains(&pool.id(slot)));
    }

    #[test]
    fn test_leaders_use_the_fixed_living_caps() {
        let mut living = LivingNamed { per_civ: [0; 256], total: 0, agents_per_civ: [0; 256] };
        living.agents_per_civ[0] = 10;
        living.per_civ[0] = MIN_NAMED_PER_CIV;
        living.total = MIN_NAMED_PER_CIV;
        assert!(!living.admits_regular(0));
        assert!(living.admits_leader(0));
        living.per_civ[0] = PER_CIV_CAP;
        assert!(!living.admits_leader(0));
        living.per_civ[0] = 0;
        living.total = GLOBAL_CAP;
        assert!(!living.admits_leader(0) && !living.admits_regular(0));
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
