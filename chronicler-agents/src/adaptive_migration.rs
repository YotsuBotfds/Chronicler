//! A6 dated per-person destination score adjustments. Input only; Python owns
//! dated experience. No random draws and no move outside the native authority.
use std::sync::atomic::{AtomicU32, Ordering};
pub struct AdaptiveMigration {
    pub turn: u32,
    pub rows: Vec<(u32, u16, f32)>,
    pub used: AtomicU32,
    pub changed: AtomicU32,
}
impl AdaptiveMigration {
    pub fn new(turn: u32, rows: Vec<(u32,u16,f32)>) -> Self {
        Self { turn, rows, used: AtomicU32::new(0), changed: AtomicU32::new(0) }
    }
    pub fn score(&self, id: u32, destination: u16) -> f32 {
        self.rows.binary_search_by_key(&(id,destination), |r| (r.0,r.1)).ok().map_or(0.0, |i| {
            self.used.fetch_add(1, Ordering::Relaxed); self.rows[i].2
        })
    }
    pub fn changed(&self) { self.changed.fetch_add(1, Ordering::Relaxed); }
}
pub struct AdaptiveReceipt {
    pub turn: u32,
    /// Gate 0: quarantine closure; 1: relocation fare / household liquidity.
    /// Only a primary decision is recorded, never its household follower.
    pub refused: Vec<(u32,u16,u16,u8)>,
    pub used: u32,
    pub changed: u32,
}
pub fn removed(pool: &crate::pool::AgentPool, original: &[(usize,u16,u16)],
               current: &[crate::behavior::PendingDecisions], gate: u8) -> Vec<(u32,u16,u16,u8)> {
    original.iter().filter(|&&(s,f,t)| !current.iter().any(|p| p.migrations.contains(&(s,f,t))))
        .map(|&(s,f,t)| (pool.ids[s],f,t,gate)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn scores_are_bound_to_person_and_destination_and_count_use() {
        let a = AdaptiveMigration::new(3,vec![(1,2,-0.3),(3,4,0.2)]);
        assert_eq!(a.score(1,2),-0.3);
        assert_eq!(a.score(1,4),0.0);
        assert_eq!(a.score(3,4),0.2);
        assert_eq!(a.used.load(Ordering::Relaxed),2);
    }
}
