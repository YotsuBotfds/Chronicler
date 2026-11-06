//! Connected-world C1b (default off): a quarantine closes migration.
//!
//! Under `--quarantine-mode closure --quarantine-channels trade,migration`
//! Python installs, before each native tick, the tick's closure: the
//! controlling civilization of every region (as Python reads it at the agent
//! tick, the same reading that cuts the merchant graph) and the closed
//! polity pairs (both directions of each pair are closed). [`gate`] runs
//! after household consolidation and before the liquid-reserve and fare
//! gates: a decided migration whose origin and destination are ruled by the
//! two polities of a closed pair is refused, so the mover stays where it is
//! (its labour and food demand stay at home) and its followers stay with it.
//! A follower whose own rebellion or occupation switch the consolidator
//! replaced gets it back, as the other household gates do.
//!
//! Policies (recorded in `docs/integration/quarantine-rules.md`):
//!
//! * Refused at the border, not diverted: the decision (target, utilities and
//!   the four Gumbel draws per agent) is the unconstrained one; only the
//!   application of a closed crossing is refused. The count is then exact for
//!   the tick: these moves were decided and would otherwise have been made.
//!   A refused agent decides afresh next tick.
//! * No journey is in flight: a native migration is decided and applied in
//!   the same tick, so a move applied before the closure's first tick is
//!   complete and is never reversed, and every new move during the closure is
//!   refused. Merchants on a trip are not migrants (their border edges leave
//!   the merchant graph instead).
//! * Refugees are not exempt: a move driven by famine, war, conquest or
//!   persecution memories, persecution or the safety need is refused like any
//!   other, and the receipt keeps each refused move's driver so the harm can
//!   be reported separately.
//!
//! Uncontrolled regions (255) belong to no polity and are never closed. No
//! RNG; the closure and its receipt are transient (taken by the tick and by
//! Python respectively) and never checkpointed.
use std::collections::BTreeMap;

use crate::behavior::PendingDecisions;
use crate::pool::AgentPool;

/// `RegionState::controller_civ` of a region nobody rules.
pub const UNCONTROLLED: u8 = 255;

#[derive(Clone, Debug, PartialEq)]
pub struct MigrationClosure {
    pub turn: u32,
    /// Per region: the controlling civilization index (255: none).
    pub region_civ: Vec<u8>,
    /// Closed polity pairs, low index first, sorted and distinct.
    pub pairs: Vec<(u8, u8)>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct MigrationClosureReceipt {
    pub turn: u32,
    /// Refused moves: (origin, destination, driver code, persons), sorted.
    pub blocked: Vec<(u16, u16, u8, u32)>,
}

impl MigrationClosure {
    /// Whether a move from region `from` to region `to` crosses a closed pair.
    pub fn blocks(&self, from: u16, to: u16) -> bool {
        let civ = |r: u16| self.region_civ.get(r as usize).copied().unwrap_or(UNCONTROLLED);
        let (a, b) = (civ(from), civ(to));
        if a == UNCONTROLLED || b == UNCONTROLLED || a == b {
            return false;
        }
        self.pairs.binary_search(&(a.min(b), a.max(b))).is_ok()
    }
}

/// Validate and install the closure of `turn`; refuses a pending one.
pub fn install(pool: &mut AgentPool, turn: u32, region_civ: Vec<u8>, pairs: Vec<(u8, u8)>,
               num_regions: usize) -> Result<(), &'static str> {
    if pool.migration_closure.is_some() {
        return Err("migration closure already pending");
    }
    if region_civ.len() != num_regions {
        return Err("migration closure controllers must match the region count");
    }
    if pairs.iter().any(|&(a, b)| a == b || a == UNCONTROLLED || b == UNCONTROLLED) {
        return Err("a closed pair names two distinct civilizations");
    }
    let mut canonical: Vec<(u8, u8)> = pairs.into_iter().map(|(a, b)| (a.min(b), a.max(b))).collect();
    canonical.sort_unstable();
    canonical.dedup();
    pool.migration_closure = Some(MigrationClosure { turn, region_civ, pairs: canonical });
    pool.migration_closure_receipt = None;
    Ok(())
}

/// The tick refuses a closure installed for another turn.
pub fn check_tick(pool: &AgentPool, turn: u32) -> Result<(), &'static str> {
    match &pool.migration_closure {
        Some(c) if c.turn != turn => Err("migration closure must be installed for this tick"),
        _ => Ok(()),
    }
}

/// Refuse every consolidated move across a closed pair; returns the refused
/// slots per bucket and the receipt rows (origin, destination, driver,
/// persons), sorted.
pub fn gate(closure: &MigrationClosure, pending: &mut [PendingDecisions])
    -> (Vec<Vec<usize>>, Vec<(u16, u16, u8, u32)>) {
    let mut blocked_by_bucket = vec![Vec::new(); pending.len()];
    let mut rows: BTreeMap<(u16, u16, u8), u32> = BTreeMap::new();
    for (bucket_index, bucket) in pending.iter_mut().enumerate() {
        let mut refused: Vec<usize> = Vec::new();
        for &(slot, from, to) in &bucket.migrations {
            if closure.blocks(from, to) && !refused.contains(&slot) {
                refused.push(slot);
                *rows.entry((from, to, bucket.migration_driver_of(slot))).or_insert(0) += 1;
            }
        }
        if !refused.is_empty() {
            bucket.migrations.retain(|m| !refused.contains(&m.0));
            blocked_by_bucket[bucket_index] = refused;
        }
    }
    let rows = rows.into_iter().map(|((from, to, driver), n)| (from, to, driver, n)).collect();
    (blocked_by_bucket, rows)
}

/// The receipt of `turn`, taken once.
pub fn take(pool: &mut AgentPool, turn: u32) -> Option<MigrationClosureReceipt> {
    if pool.migration_closure_receipt.as_ref().is_some_and(|r| r.turn == turn) {
        pool.migration_closure_receipt.take()
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::migration_drivers::{MIGRATION_TERMS, TERM_FAMINE_MEMORY, TERM_WAGE};

    fn closure(pairs: Vec<(u8, u8)>) -> MigrationClosure {
        // Regions 0, 1 ruled by civ 0; 2 by civ 1; 3 by civ 2; 4 uncontrolled.
        let mut pool = AgentPool::new(4);
        install(&mut pool, 7, vec![0, 0, 1, 2, UNCONTROLLED], pairs, 5).unwrap();
        pool.migration_closure.take().unwrap()
    }

    fn bucket(moves: &[(usize, u16, u16)]) -> PendingDecisions {
        let mut p = PendingDecisions::new();
        p.migrations = moves.to_vec();
        p
    }

    #[test]
    fn a_closed_pair_blocks_both_directions_and_nothing_else() {
        let c = closure(vec![(1, 0)]);
        assert_eq!(c.pairs, vec![(0, 1)]);
        assert!(c.blocks(0, 2) && c.blocks(1, 2) && c.blocks(2, 0) && c.blocks(2, 1));
        // Inside a polity, an open pair, uncontrolled land and unknown regions stay open.
        assert!(!c.blocks(0, 1) && !c.blocks(1, 0));
        assert!(!c.blocks(0, 3) && !c.blocks(3, 2) && !c.blocks(2, 3));
        assert!(!c.blocks(2, 4) && !c.blocks(4, 2) && !c.blocks(9, 2));
    }

    #[test]
    fn the_gate_refuses_closed_moves_with_their_drivers_and_keeps_open_ones() {
        let c = closure(vec![(0, 1)]);
        let mut a = bucket(&[(0, 0, 2), (1, 0, 1), (2, 0, 3)]);
        a.migration_dominant = vec![(0, TERM_FAMINE_MEMORY as u8), (1, TERM_WAGE as u8)];
        let mut b = bucket(&[(5, 2, 0), (6, 2, 3), (7, 2, 1)]);
        b.migration_followers = vec![(7, TERM_WAGE as u8)];
        let mut pending = vec![a, b];
        let (blocked, rows) = gate(&c, &mut pending);
        assert_eq!(blocked, vec![vec![0], vec![5, 7]]);
        assert_eq!(pending[0].migrations, vec![(1, 0, 1), (2, 0, 3)]);
        assert_eq!(pending[1].migrations, vec![(6, 2, 3)]);
        assert_eq!(rows, vec![
            (0, 2, TERM_FAMINE_MEMORY as u8, 1),
            (2, 0, MIGRATION_TERMS as u8, 1),
            (2, 1, TERM_WAGE as u8, 1),
        ]);
    }

    #[test]
    fn no_closed_pair_changes_nothing() {
        let c = closure(vec![]);
        let moves = [(0, 0, 2), (1, 2, 3), (2, 3, 4)];
        let mut pending = vec![bucket(&moves)];
        let (blocked, rows) = gate(&c, &mut pending);
        assert_eq!(blocked, vec![Vec::<usize>::new()]);
        assert!(rows.is_empty());
        assert_eq!(pending[0].migrations, moves.to_vec());
    }

    #[test]
    fn install_validates_and_the_receipt_is_taken_once_for_its_turn() {
        let mut pool = AgentPool::new(2);
        assert!(install(&mut pool, 3, vec![0, 1], vec![(0, 0)], 2).is_err());
        assert!(install(&mut pool, 3, vec![0, 1], vec![(0, UNCONTROLLED)], 2).is_err());
        assert!(install(&mut pool, 3, vec![0], vec![(0, 1)], 2).is_err());
        assert!(pool.migration_closure.is_none());
        install(&mut pool, 3, vec![0, 1], vec![(0, 1), (1, 0)], 2).unwrap();
        assert_eq!(pool.migration_closure.as_ref().unwrap().pairs, vec![(0, 1)]);
        assert_eq!(install(&mut pool, 3, vec![0, 1], vec![], 2), Err("migration closure already pending"));
        assert!(check_tick(&pool, 3).is_ok());
        assert!(check_tick(&pool, 4).is_err());
        pool.migration_closure_receipt = Some(MigrationClosureReceipt { turn: 3, blocked: vec![(0, 1, 0, 2)] });
        assert!(take(&mut pool, 2).is_none());
        assert_eq!(take(&mut pool, 3).unwrap().blocked, vec![(0, 1, 0, 2)]);
        assert!(take(&mut pool, 3).is_none());
    }
}
