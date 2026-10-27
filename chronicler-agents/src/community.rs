//! Community anchoring (`--community-anchoring`, default off).
//!
//! M53 oracle 4 expects community members to migrate 15-30% less than
//! matched non-members ("social anchoring"). A community in the sense of
//! M53 oracle 1 is a group of five or more agents joined by mutual bonds
//! who share memories, and not a pure family clump. This module gives each
//! agent the local counterpart of membership:
//!
//! - **Community ties**: positive-valence bonds (mentor, exile bond,
//!   co-religionist, kin, friend; marriage excepted, since the spouse moves
//!   with the household) of sentiment at least `COMMUNITY_TIE_MIN_SENTIMENT`
//!   to a living agent in the agent's own region (a merchant away on a trade
//!   trip still belongs to it) with whom the agent shares a memory: the same
//!   event type with both memory turns in one `COMMUNITY_MEMORY_BUCKET`-turn
//!   bucket, the key oracle 1 compares. The validator recomputes the same
//!   ties from the sidecars (`chronicler.validation_ablation.community_ties`).
//! - **Kin-only exclusion**: at least one tie must be non-kin. An agent whose
//!   only ties are kin is held by its kin roots (`migration_drivers::roots`)
//!   and household, as before, and gets no community anchor.
//! - **Anchor**: `COMMUNITY_ANCHOR` times the ties counted up to
//!   `COMMUNITY_FULL_TIES` (four: with the agent, a group of five, oracle
//!   1's smallest community), over `COMMUNITY_FULL_TIES`.
//!
//! The decision (`behavior.rs`) subtracts the anchor from the migrate
//! utility of an agent that has a reason to move, after the migrate gate:
//! with the decision's Gumbel draw at `DECISION_TEMPERATURE` T the odds of
//! moving against each other action fall by `exp(-anchor / T)`. The anchor
//! never closes the gate (it does not remove the reason to move) and never
//! touches rebellion, occupation switches or staying. It is a deterministic
//! function of the agent's bonds and memories: no random draw, and the
//! decision keeps its four Gumbel draws per agent. With the switch off it is
//! never computed. See docs/integration/community-anchoring.md.

use crate::memory::MEMORY_SLOTS;
use crate::pool::{AgentPool, SlotLookup};
use crate::relationships::{is_positive_valence, BondType, REL_SLOTS};

// ---------------------------------------------------------------------------
// Constants [CALIBRATE community-anchoring] — docs/integration/community-anchoring.md
// ---------------------------------------------------------------------------

/// Bonds below this sentiment are not community ties (the migration
/// drivers' `BOND_MIN_SENTIMENT`: they neither anchor nor pull there).
pub const COMMUNITY_TIE_MIN_SENTIMENT: i8 = crate::migration_drivers::BOND_MIN_SENTIMENT;
/// Two memories are shared when their event types are equal and their turns
/// fall in the same bucket of this many turns (oracle 1's `turn // 5`).
pub const COMMUNITY_MEMORY_BUCKET: u16 = 5;
/// Ties counted toward the full anchor: with the agent, five people, the
/// smallest community oracle 1 counts.
pub const COMMUNITY_FULL_TIES: u8 = 4;
/// Odds of moving of a fully anchored agent against the same agent without
/// its community: 0.67 gives an agent with the gate open (move probability
/// about 0.2) 22.5% fewer moves over 20 turns through the 5-turn settling
/// lock, the midpoint of M53's 15-30% (docs/integration/community-anchoring.md,
/// section 2).
pub const COMMUNITY_FULL_ANCHOR_ODDS: f32 = 0.67;
/// The full anchor in utility units: `-DECISION_TEMPERATURE * ln(COMMUNITY_FULL_ANCHOR_ODDS)`
/// (0.3 x 0.40048; a test checks the two agree).
pub const COMMUNITY_ANCHOR: f32 = 0.120_143;

/// Community ties of one agent (`community_ties`).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct CommunityTies {
    /// Qualifying ties, kin included.
    pub ties: u8,
    /// Of which non-kin.
    pub non_kin: u8,
}

impl CommunityTies {
    /// The ties that count toward the anchor: none without a non-kin tie,
    /// else every tie up to `COMMUNITY_FULL_TIES`.
    #[inline]
    pub fn counted(self) -> u8 {
        if self.non_kin == 0 {
            0
        } else {
            self.ties.min(COMMUNITY_FULL_TIES)
        }
    }

    /// The anchor subtracted from the migrate utility, at the calibrated
    /// strength.
    #[inline]
    pub fn anchor(self) -> f32 {
        self.anchor_with(COMMUNITY_ANCHOR)
    }

    /// The anchor for a full anchor of `full_anchor` (`scale::CommunityAnchoring`).
    #[inline]
    pub fn anchor_with(self, full_anchor: f32) -> f32 {
        let counted = self.counted();
        if counted == 0 {
            0.0
        } else {
            full_anchor * counted as f32 / COMMUNITY_FULL_TIES as f32
        }
    }
}

/// Whether two agents share a memory: an equal event type with both turns
/// in one `COMMUNITY_MEMORY_BUCKET` bucket.
#[inline]
fn share_memory(pool: &AgentPool, a: usize, b: usize) -> bool {
    let na = (pool.memory_count[a] as usize).min(MEMORY_SLOTS);
    let nb = (pool.memory_count[b] as usize).min(MEMORY_SLOTS);
    for i in 0..na {
        let event = pool.memory_event_types[a][i];
        let bucket = pool.memory_turns[a][i] / COMMUNITY_MEMORY_BUCKET;
        for j in 0..nb {
            if pool.memory_event_types[b][j] == event
                && pool.memory_turns[b][j] / COMMUNITY_MEMORY_BUCKET == bucket
            {
                return true;
            }
        }
    }
    false
}

/// The community ties of the agent in `slot`, living in `region_id`. One
/// pass over its at most `REL_SLOTS` bonds; no allocation.
pub fn community_ties<L: SlotLookup>(
    pool: &AgentPool,
    slot: usize,
    region_id: usize,
    id_to_slot: &L,
) -> CommunityTies {
    let mut out = CommunityTies::default();
    if pool.memory_count[slot] == 0 {
        return out;
    }
    let count = (pool.rel_count[slot] as usize).min(REL_SLOTS);
    for i in 0..count {
        let bond_type = pool.rel_bond_types[slot][i];
        if bond_type == BondType::Marriage as u8
            || !is_positive_valence(bond_type)
            || pool.rel_sentiments[slot][i] < COMMUNITY_TIE_MIN_SENTIMENT
        {
            continue;
        }
        let target_id = pool.rel_target_ids[slot][i];
        let t = match id_to_slot.slot_of(target_id) {
            Some(t) if t < pool.capacity() && pool.is_alive(t) && pool.ids[t] == target_id => t,
            _ => continue,
        };
        if pool.regions[t] as usize != region_id || !share_memory(pool, slot, t) {
            continue;
        }
        out.ties = out.ties.saturating_add(1);
        if bond_type != BondType::Kin as u8 {
            out.non_kin = out.non_kin.saturating_add(1);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::{Occupation, DECISION_TEMPERATURE};
    use std::collections::HashMap;

    fn agent(pool: &mut AgentPool, region: u16) -> usize {
        pool.spawn(region, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE)
    }

    fn bond(pool: &mut AgentPool, from: usize, to: usize, bond_type: BondType, sentiment: i8) {
        let i = pool.rel_count[from] as usize;
        pool.rel_target_ids[from][i] = pool.ids[to];
        pool.rel_sentiments[from][i] = sentiment;
        pool.rel_bond_types[from][i] = bond_type as u8;
        pool.rel_count[from] += 1;
    }

    fn remember(pool: &mut AgentPool, slot: usize, event: u8, turn: u16) {
        let i = pool.memory_count[slot] as usize;
        pool.memory_event_types[slot][i] = event;
        pool.memory_turns[slot][i] = turn;
        pool.memory_intensities[slot][i] = 40;
        pool.memory_count[slot] += 1;
    }

    fn index(pool: &AgentPool) -> HashMap<u32, usize> {
        (0..pool.capacity()).filter(|&s| pool.is_alive(s)).map(|s| (pool.ids[s], s)).collect()
    }

    #[test]
    fn the_full_anchor_is_the_target_odds_at_the_decision_temperature() {
        let expected = -DECISION_TEMPERATURE * COMMUNITY_FULL_ANCHOR_ODDS.ln();
        assert!((COMMUNITY_ANCHOR - expected).abs() < 1e-5, "{COMMUNITY_ANCHOR} vs {expected}");
        let full = CommunityTies { ties: 9, non_kin: 1 };
        assert_eq!(full.counted(), COMMUNITY_FULL_TIES);
        assert_eq!(full.anchor(), COMMUNITY_ANCHOR);
        assert!(((-full.anchor() / DECISION_TEMPERATURE).exp() - COMMUNITY_FULL_ANCHOR_ODDS).abs() < 1e-5);
        let two = CommunityTies { ties: 2, non_kin: 2 };
        assert!((two.anchor() - COMMUNITY_ANCHOR / 2.0).abs() < 1e-7);
    }

    #[test]
    fn kin_only_ties_do_not_anchor() {
        assert_eq!(CommunityTies { ties: 4, non_kin: 0 }.anchor(), 0.0);
        assert_eq!(CommunityTies::default().anchor(), 0.0);
    }

    #[test]
    fn ties_need_a_shared_memory_a_home_region_and_a_positive_bond() {
        let mut pool = AgentPool::new(16);
        let me = agent(&mut pool, 0);
        let friend = agent(&mut pool, 0);
        let kin = agent(&mut pool, 0);
        let stranger = agent(&mut pool, 0); // a friend without a shared memory
        let away = agent(&mut pool, 1); // a friend in another region
        let rival = agent(&mut pool, 0);
        let weak = agent(&mut pool, 0); // sentiment below the minimum
        let spouse = agent(&mut pool, 0);
        for &s in &[me, friend, kin, away, rival, weak, spouse] {
            remember(&mut pool, s, 3, 52); // famine in the 50-54 bucket
        }
        remember(&mut pool, stranger, 3, 47); // the same event type, another bucket
        bond(&mut pool, me, friend, BondType::Friend, 60);
        bond(&mut pool, me, kin, BondType::Kin, 80);
        bond(&mut pool, me, stranger, BondType::Friend, 60);
        bond(&mut pool, me, away, BondType::Friend, 60);
        bond(&mut pool, me, rival, BondType::Rival, 60);
        bond(&mut pool, me, weak, BondType::CoReligionist, COMMUNITY_TIE_MIN_SENTIMENT - 1);
        bond(&mut pool, me, spouse, BondType::Marriage, 100);
        let ties = community_ties(&pool, me, 0, &index(&pool));
        assert_eq!(ties, CommunityTies { ties: 2, non_kin: 1 });
        assert!((ties.anchor() - COMMUNITY_ANCHOR * 2.0 / 4.0).abs() < 1e-7);
        // Shared memories are matched within a five-turn bucket.
        remember(&mut pool, stranger, 3, 54);
        assert_eq!(community_ties(&pool, me, 0, &index(&pool)).ties, 3);
        // A dead tie no longer counts.
        pool.kill(friend);
        assert_eq!(community_ties(&pool, me, 0, &index(&pool)), CommunityTies { ties: 2, non_kin: 1 });
    }

    #[test]
    fn an_agent_without_memories_has_no_ties() {
        let mut pool = AgentPool::new(4);
        let me = agent(&mut pool, 0);
        let friend = agent(&mut pool, 0);
        remember(&mut pool, friend, 3, 10);
        bond(&mut pool, me, friend, BondType::Friend, 90);
        assert_eq!(community_ties(&pool, me, 0, &index(&pool)), CommunityTies::default());
    }
}
