//! AgentPool: struct-of-arrays storage for all agent fields.
//! Arena free-list added in Task 11.

use crate::agent::Occupation;

/// Struct-of-arrays agent pool. Each index is a "slot"; a slot may be dead.
/// Use `is_alive(slot)` before accessing any field.
pub struct AgentPool {
    // Identity
    pub ids: Vec<u32>,
    // Spatial
    pub regions: Vec<u16>,
    pub origin_regions: Vec<u16>,
    // Allegiance
    pub civ_affinities: Vec<u8>,
    // Role
    pub occupations: Vec<u8>,
    // Social
    pub loyalties: Vec<f32>,
    pub satisfactions: Vec<f32>,
    // Skills: OCCUPATION_COUNT floats per agent, stored flat (slot * 5 + occ_idx)
    pub skills: Vec<f32>,
    // Demographics
    pub ages: Vec<u16>,
    pub displacement_turns: Vec<u8>,
    // Liveness
    pub alive: Vec<bool>,

    /// Number of live agents (excludes dead slots).
    pub count: usize,
    next_id: u32,
}

impl AgentPool {
    /// Create an empty pool with pre-allocated capacity.
    pub fn new(capacity: usize) -> Self {
        Self {
            ids: Vec::with_capacity(capacity),
            regions: Vec::with_capacity(capacity),
            origin_regions: Vec::with_capacity(capacity),
            civ_affinities: Vec::with_capacity(capacity),
            occupations: Vec::with_capacity(capacity),
            loyalties: Vec::with_capacity(capacity),
            satisfactions: Vec::with_capacity(capacity),
            skills: Vec::with_capacity(capacity * 5),
            ages: Vec::with_capacity(capacity),
            displacement_turns: Vec::with_capacity(capacity),
            alive: Vec::with_capacity(capacity),
            count: 0,
            next_id: 0,
        }
    }

    /// Spawn a new agent. Returns the slot index.
    /// No free-list yet — always pushes a new slot.
    pub fn spawn(
        &mut self,
        region: u16,
        civ_affinity: u8,
        occupation: Occupation,
        age: u16,
    ) -> usize {
        let slot = self.ids.len();
        let id = self.next_id;
        self.next_id += 1;

        self.ids.push(id);
        self.regions.push(region);
        self.origin_regions.push(region);
        self.civ_affinities.push(civ_affinity);
        self.occupations.push(occupation as u8);
        self.loyalties.push(0.5);
        self.satisfactions.push(0.5);
        // Five skill slots defaulting to 0.0
        for _ in 0..5 {
            self.skills.push(0.0);
        }
        self.ages.push(age);
        self.displacement_turns.push(0);
        self.alive.push(true);

        self.count += 1;
        slot
    }

    /// Kill an agent by slot. Decrements live count.
    pub fn kill(&mut self, slot: usize) {
        if self.is_alive(slot) {
            self.set_dead(slot);
            self.count -= 1;
        }
    }

    // --- Liveness ---

    #[inline]
    pub fn is_alive(&self, slot: usize) -> bool {
        self.alive[slot]
    }

    #[inline]
    pub fn set_dead(&mut self, slot: usize) {
        self.alive[slot] = false;
    }

    // --- Accessors ---

    #[inline]
    pub fn id(&self, slot: usize) -> u32 {
        self.ids[slot]
    }

    #[inline]
    pub fn age(&self, slot: usize) -> u16 {
        self.ages[slot]
    }

    #[inline]
    pub fn increment_age(&mut self, slot: usize) {
        self.ages[slot] = self.ages[slot].saturating_add(1);
    }

    #[inline]
    pub fn region(&self, slot: usize) -> u16 {
        self.regions[slot]
    }

    #[inline]
    pub fn civ_affinity(&self, slot: usize) -> u8 {
        self.civ_affinities[slot]
    }

    #[inline]
    pub fn occupation(&self, slot: usize) -> u8 {
        self.occupations[slot]
    }

    #[inline]
    pub fn satisfaction(&self, slot: usize) -> f32 {
        self.satisfactions[slot]
    }

    /// Total number of allocated slots (live + dead).
    #[inline]
    pub fn capacity(&self) -> usize {
        self.ids.len()
    }

    /// Number of live agents.
    #[inline]
    pub fn alive_count(&self) -> usize {
        self.count
    }

    /// Group live slot indices by region.
    /// Returns a Vec of length `num_regions`; each inner Vec holds slot indices.
    pub fn partition_by_region(&self, num_regions: u16) -> Vec<Vec<usize>> {
        let mut buckets: Vec<Vec<usize>> = (0..num_regions as usize).map(|_| Vec::new()).collect();
        for slot in 0..self.capacity() {
            if self.is_alive(slot) {
                let r = self.region(slot) as usize;
                if r < buckets.len() {
                    buckets[r].push(slot);
                }
            }
        }
        buckets
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    #[test]
    fn test_spawn_into_empty_pool() {
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
        assert_eq!(slot, 0);
        assert!(pool.is_alive(slot));
        assert_eq!(pool.alive_count(), 1);
        assert_eq!(pool.capacity(), 1);
        assert_eq!(pool.age(slot), 25);
        assert_eq!(pool.region(slot), 0);
        assert_eq!(pool.occupation(slot), Occupation::Farmer as u8);
    }

    #[test]
    fn test_kill_marks_dead_and_decrements_count() {
        let mut pool = AgentPool::new(8);
        let s0 = pool.spawn(0, 0, Occupation::Soldier, 30);
        let s1 = pool.spawn(1, 1, Occupation::Merchant, 40);
        assert_eq!(pool.alive_count(), 2);

        pool.kill(s0);
        assert!(!pool.is_alive(s0));
        assert!(pool.is_alive(s1));
        assert_eq!(pool.alive_count(), 1);

        // Killing again should be idempotent
        pool.kill(s0);
        assert_eq!(pool.alive_count(), 1);
    }

    #[test]
    fn test_increment_age() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Scholar, 59);
        pool.increment_age(slot);
        assert_eq!(pool.age(slot), 60);
        // Saturating at u16::MAX
        pool.ages[slot] = u16::MAX;
        pool.increment_age(slot);
        assert_eq!(pool.age(slot), u16::MAX);
    }

    #[test]
    fn test_partition_by_region_with_dead_agent() {
        let mut pool = AgentPool::new(8);
        let s0 = pool.spawn(0, 0, Occupation::Farmer, 20);
        let s1 = pool.spawn(1, 0, Occupation::Priest, 35);
        let s2 = pool.spawn(0, 0, Occupation::Merchant, 28);

        pool.kill(s1);

        let buckets = pool.partition_by_region(3);
        assert_eq!(buckets.len(), 3);
        // Region 0: s0 and s2 (s1 dead, region 1 excluded)
        assert_eq!(buckets[0].len(), 2);
        assert!(buckets[0].contains(&s0));
        assert!(buckets[0].contains(&s2));
        // Region 1: empty because s1 is dead
        assert_eq!(buckets[1].len(), 0);
        // Region 2: empty
        assert_eq!(buckets[2].len(), 0);
    }

    #[test]
    fn test_ids_are_monotonic() {
        let mut pool = AgentPool::new(8);
        let s0 = pool.spawn(0, 0, Occupation::Farmer, 10);
        let s1 = pool.spawn(0, 0, Occupation::Soldier, 20);
        let s2 = pool.spawn(0, 0, Occupation::Scholar, 30);
        assert!(pool.id(s0) < pool.id(s1));
        assert!(pool.id(s1) < pool.id(s2));
    }
}
