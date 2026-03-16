//! AgentPool: struct-of-arrays storage for all agent fields.
//! Arena free-list added in Task 11.

use std::collections::HashMap;
use std::sync::Arc;

use arrow::array::{Float32Builder, UInt16Builder, UInt32Builder, UInt8Builder};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;

use crate::agent::Occupation;
use crate::ffi;

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

    /// Free-list: indices of dead slots available for reuse.
    free_slots: Vec<usize>,
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
            free_slots: Vec::new(),
        }
    }

    /// Spawn a new agent. Returns the slot index.
    /// Reuses a dead slot from the free-list if available; otherwise grows vecs.
    pub fn spawn(
        &mut self,
        region: u16,
        civ_affinity: u8,
        occupation: Occupation,
        age: u16,
    ) -> usize {
        let id = self.next_id;
        self.next_id += 1;

        if let Some(slot) = self.free_slots.pop() {
            // Reuse dead slot — overwrite all fields.
            self.ids[slot] = id;
            self.regions[slot] = region;
            self.origin_regions[slot] = region;
            self.civ_affinities[slot] = civ_affinity;
            self.occupations[slot] = occupation as u8;
            self.loyalties[slot] = 0.5;
            self.satisfactions[slot] = 0.5;
            let skill_base = slot * 5;
            for i in 0..5 {
                self.skills[skill_base + i] = 0.0;
            }
            self.ages[slot] = age;
            self.displacement_turns[slot] = 0;
            self.alive[slot] = true;
            self.count += 1;
            slot
        } else {
            // No free slot — grow vecs.
            let slot = self.ids.len();
            self.ids.push(id);
            self.regions.push(region);
            self.origin_regions.push(region);
            self.civ_affinities.push(civ_affinity);
            self.occupations.push(occupation as u8);
            self.loyalties.push(0.5);
            self.satisfactions.push(0.5);
            for _ in 0..5 {
                self.skills.push(0.0);
            }
            self.ages.push(age);
            self.displacement_turns.push(0);
            self.alive.push(true);
            self.count += 1;
            slot
        }
    }

    /// Kill an agent by slot. Decrements live count and returns slot to free-list.
    pub fn kill(&mut self, slot: usize) {
        if self.is_alive(slot) {
            self.set_dead(slot);
            self.count -= 1;
            self.free_slots.push(slot);
        }
    }

    /// Number of dead slots available for reuse.
    #[inline]
    pub fn free_slot_count(&self) -> usize {
        self.free_slots.len()
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
// Arrow serialization
// ---------------------------------------------------------------------------

impl AgentPool {
    /// Return an Arrow RecordBatch containing one row per alive agent.
    /// Dead slots are filtered out.
    pub fn to_record_batch(&self) -> Result<RecordBatch, ArrowError> {
        let live: usize = self.count;

        let mut ids = UInt32Builder::with_capacity(live);
        let mut regions = UInt16Builder::with_capacity(live);
        let mut origin_regions = UInt16Builder::with_capacity(live);
        let mut civ_affinities = UInt16Builder::with_capacity(live);
        let mut occupations = UInt8Builder::with_capacity(live);
        let mut loyalties = Float32Builder::with_capacity(live);
        let mut satisfactions = Float32Builder::with_capacity(live);
        let mut skills = Float32Builder::with_capacity(live);
        let mut ages = UInt16Builder::with_capacity(live);
        let mut displacement_turns = UInt16Builder::with_capacity(live);

        for slot in 0..self.capacity() {
            if !self.is_alive(slot) {
                continue;
            }
            ids.append_value(self.ids[slot]);
            regions.append_value(self.regions[slot]);
            origin_regions.append_value(self.origin_regions[slot]);
            // stored as u8, schema says UInt16
            civ_affinities.append_value(self.civ_affinities[slot] as u16);
            occupations.append_value(self.occupations[slot]);
            loyalties.append_value(self.loyalties[slot]);
            satisfactions.append_value(self.satisfactions[slot]);
            // Use occupation-specific skill (slot * 5 + occ_idx)
            let occ_idx = self.occupations[slot] as usize;
            let skill_val = self.skills[slot * 5 + occ_idx];
            skills.append_value(skill_val);
            ages.append_value(self.ages[slot]);
            // stored as u8, schema says UInt16
            displacement_turns.append_value(self.displacement_turns[slot] as u16);
        }

        let schema = Arc::new(ffi::snapshot_schema());
        RecordBatch::try_new(
            schema,
            vec![
                Arc::new(ids.finish()) as _,
                Arc::new(regions.finish()) as _,
                Arc::new(origin_regions.finish()) as _,
                Arc::new(civ_affinities.finish()) as _,
                Arc::new(occupations.finish()) as _,
                Arc::new(loyalties.finish()) as _,
                Arc::new(satisfactions.finish()) as _,
                Arc::new(skills.finish()) as _,
                Arc::new(ages.finish()) as _,
                Arc::new(displacement_turns.finish()) as _,
            ],
        )
    }

    /// Return a per-civ aggregate RecordBatch.
    /// `population` is populated; `military`/`economy`/`culture`/`stability`
    /// are zeroed in M25 and will be populated in M26.
    pub fn compute_aggregates(&self) -> Result<RecordBatch, ArrowError> {
        // Count live agents per civ.
        let mut counts: HashMap<u8, u32> = HashMap::new();
        for slot in 0..self.capacity() {
            if self.is_alive(slot) {
                *counts.entry(self.civ_affinities[slot]).or_insert(0) += 1;
            }
        }

        // Sort by civ_id for deterministic output.
        let mut sorted: Vec<(u8, u32)> = counts.into_iter().collect();
        sorted.sort_by_key(|(civ, _)| *civ);

        let n = sorted.len();
        let mut civ_ids = UInt16Builder::with_capacity(n);
        let mut populations = UInt32Builder::with_capacity(n);
        let mut military = UInt32Builder::with_capacity(n);
        let mut economy = UInt32Builder::with_capacity(n);
        let mut culture = UInt32Builder::with_capacity(n);
        let mut stability = UInt32Builder::with_capacity(n);

        for (civ, pop) in sorted {
            civ_ids.append_value(civ as u16);
            populations.append_value(pop);
            military.append_value(0);
            economy.append_value(0);
            culture.append_value(0);
            stability.append_value(0);
        }

        let schema = Arc::new(ffi::aggregates_schema());
        RecordBatch::try_new(
            schema,
            vec![
                Arc::new(civ_ids.finish()) as _,
                Arc::new(populations.finish()) as _,
                Arc::new(military.finish()) as _,
                Arc::new(economy.finish()) as _,
                Arc::new(culture.finish()) as _,
                Arc::new(stability.finish()) as _,
            ],
        )
    }

    /// Return a per-region alive-count RecordBatch.
    /// Rows are in region_id order (0..num_regions).
    pub fn region_populations(&self, num_regions: usize) -> Result<RecordBatch, ArrowError> {
        let mut counts = vec![0u32; num_regions];
        for slot in 0..self.capacity() {
            if self.is_alive(slot) {
                let r = self.regions[slot] as usize;
                if r < num_regions {
                    counts[r] += 1;
                }
            }
        }

        let mut region_ids = UInt16Builder::with_capacity(num_regions);
        let mut alive_counts = UInt32Builder::with_capacity(num_regions);
        for (i, c) in counts.iter().enumerate() {
            region_ids.append_value(i as u16);
            alive_counts.append_value(*c);
        }

        let schema = Arc::new(ffi::region_populations_schema());
        RecordBatch::try_new(
            schema,
            vec![
                Arc::new(region_ids.finish()) as _,
                Arc::new(alive_counts.finish()) as _,
            ],
        )
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

    // --- Arrow round-trip tests (Task 9) ---

    #[test]
    fn test_to_record_batch_filters_dead() {
        use arrow::array::{UInt16Array, UInt32Array, UInt8Array};

        let mut pool = AgentPool::new(8);
        let s0 = pool.spawn(0, 1, Occupation::Farmer, 20);
        let s1 = pool.spawn(1, 2, Occupation::Soldier, 30);
        let s2 = pool.spawn(0, 1, Occupation::Merchant, 40);

        // Kill the second agent; only s0 and s2 should appear in the batch.
        pool.kill(s1);

        let batch = pool.to_record_batch().expect("to_record_batch failed");

        // Two live rows, dead slot filtered out.
        assert_eq!(batch.num_rows(), 2, "expected 2 alive rows");

        // Schema column names.
        let schema = batch.schema();
        assert_eq!(schema.field(0).name(), "id");
        assert_eq!(schema.field(1).name(), "region");
        assert_eq!(schema.field(2).name(), "origin_region");
        assert_eq!(schema.field(3).name(), "civ_affinity");
        assert_eq!(schema.field(4).name(), "occupation");
        assert_eq!(schema.field(8).name(), "age");

        // Verify values for the two surviving rows (s0 first, s2 second).
        let ids = batch
            .column(0)
            .as_any()
            .downcast_ref::<UInt32Array>()
            .unwrap();
        assert_eq!(ids.value(0), pool.id(s0));
        assert_eq!(ids.value(1), pool.id(s2));

        let regions = batch
            .column(1)
            .as_any()
            .downcast_ref::<UInt16Array>()
            .unwrap();
        assert_eq!(regions.value(0), 0); // s0 in region 0
        assert_eq!(regions.value(1), 0); // s2 in region 0

        let civ_affinities = batch
            .column(3)
            .as_any()
            .downcast_ref::<UInt16Array>()
            .unwrap();
        assert_eq!(civ_affinities.value(0), 1);
        assert_eq!(civ_affinities.value(1), 1);

        let occupations = batch
            .column(4)
            .as_any()
            .downcast_ref::<UInt8Array>()
            .unwrap();
        assert_eq!(occupations.value(0), Occupation::Farmer as u8);
        assert_eq!(occupations.value(1), Occupation::Merchant as u8);
    }

    #[test]
    fn test_compute_aggregates_zeroes_non_population() {
        use arrow::array::{UInt16Array, UInt32Array};

        let mut pool = AgentPool::new(8);
        // civ 0: 2 agents
        pool.spawn(0, 0, Occupation::Farmer, 25);
        pool.spawn(0, 0, Occupation::Soldier, 30);
        // civ 1: 1 agent
        pool.spawn(1, 1, Occupation::Scholar, 35);

        let batch = pool.compute_aggregates().expect("compute_aggregates failed");

        // Two civs.
        assert_eq!(batch.num_rows(), 2);

        let schema = batch.schema();
        assert_eq!(schema.field(0).name(), "civ_id");
        assert_eq!(schema.field(1).name(), "population");
        assert_eq!(schema.field(2).name(), "military");
        assert_eq!(schema.field(5).name(), "stability");

        let civ_ids = batch
            .column(0)
            .as_any()
            .downcast_ref::<UInt16Array>()
            .unwrap();
        assert_eq!(civ_ids.value(0), 0);
        assert_eq!(civ_ids.value(1), 1);

        let populations = batch
            .column(1)
            .as_any()
            .downcast_ref::<UInt32Array>()
            .unwrap();
        assert_eq!(populations.value(0), 2); // civ 0 has 2
        assert_eq!(populations.value(1), 1); // civ 1 has 1

        // military, economy, culture, stability — all zero in M25.
        for col_idx in 2..=5 {
            let col = batch
                .column(col_idx)
                .as_any()
                .downcast_ref::<UInt32Array>()
                .unwrap();
            for row in 0..batch.num_rows() {
                assert_eq!(col.value(row), 0, "col {} row {} should be zero", col_idx, row);
            }
        }
    }

    #[test]
    fn test_region_populations() {
        use arrow::array::{UInt16Array, UInt32Array};

        let mut pool = AgentPool::new(8);
        let s0 = pool.spawn(0, 0, Occupation::Farmer, 25);  // region 0
        let s1 = pool.spawn(1, 0, Occupation::Soldier, 30); // region 1
        let _s2 = pool.spawn(0, 0, Occupation::Merchant, 35); // region 0
        let _s3 = pool.spawn(2, 0, Occupation::Scholar, 40);  // region 2

        // Kill s1 — region 1 should now have 0 live agents.
        pool.kill(s1);
        // Kill s0 — region 0 should now have 1 live agent.
        pool.kill(s0);

        let batch = pool
            .region_populations(3)
            .expect("region_populations failed");

        // 3 rows (one per region).
        assert_eq!(batch.num_rows(), 3);

        let schema = batch.schema();
        assert_eq!(schema.field(0).name(), "region_id");
        assert_eq!(schema.field(1).name(), "alive_count");

        let region_ids = batch
            .column(0)
            .as_any()
            .downcast_ref::<UInt16Array>()
            .unwrap();
        assert_eq!(region_ids.value(0), 0);
        assert_eq!(region_ids.value(1), 1);
        assert_eq!(region_ids.value(2), 2);

        let alive_counts = batch
            .column(1)
            .as_any()
            .downcast_ref::<UInt32Array>()
            .unwrap();
        assert_eq!(alive_counts.value(0), 1); // region 0: _s2 alive
        assert_eq!(alive_counts.value(1), 0); // region 1: s1 dead
        assert_eq!(alive_counts.value(2), 1); // region 2: _s3 alive
    }

    #[test]
    fn test_arena_stress_spawn_kill_respawn() {
        let mut pool = AgentPool::new(0);
        // Spawn 1000
        for _ in 0..1000 {
            pool.spawn(0, 0, Occupation::Farmer, 0);
        }
        assert_eq!(pool.alive_count(), 1000);
        assert_eq!(pool.capacity(), 1000);

        // Kill 800 in scattered pattern
        let mut kill_order: Vec<usize> = (0..1000).step_by(5).collect();
        for i in 0..1000 {
            if kill_order.len() >= 800 {
                break;
            }
            if !kill_order.contains(&i) {
                kill_order.push(i);
            }
        }
        kill_order.truncate(800);
        for &slot in &kill_order {
            pool.kill(slot);
        }
        assert_eq!(pool.alive_count(), 200);
        assert_eq!(pool.free_slot_count(), 800);

        // Respawn 600 — should reuse dead slots, no vec growth
        let capacity_before = pool.capacity();
        for _ in 0..600 {
            pool.spawn(0, 0, Occupation::Soldier, 0);
        }
        assert_eq!(pool.alive_count(), 800);
        assert_eq!(pool.capacity(), capacity_before); // no growth!
        assert_eq!(pool.free_slot_count(), 200);

        let batch = pool.to_record_batch().unwrap();
        assert_eq!(batch.num_rows(), 800);
    }
}
