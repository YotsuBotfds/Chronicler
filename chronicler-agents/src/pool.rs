//! AgentPool: struct-of-arrays storage for all agent fields.
//! Arena free-list added in Task 11.

use std::collections::HashMap;
use std::sync::Arc;

use arrow::array::{Float32Builder, UInt16Builder, UInt32Builder, UInt8Builder};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;

use crate::agent::Occupation;
use crate::ffi;
use crate::region::RegionState;

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
    // Named character promotion (M30)
    pub life_events: Vec<u8>,
    pub promotion_progress: Vec<u8>,
    // Personality (M33) — immutable after spawn
    pub boldness: Vec<f32>,
    pub ambition: Vec<f32>,
    pub loyalty_trait: Vec<f32>,
    // Cultural identity (M36) — 3 ranked value slots, distinct enum indices
    pub cultural_value_0: Vec<u8>,   // Primary (stickiest, 1/3× drift rate)
    pub cultural_value_1: Vec<u8>,   // Secondary (2/3× drift rate)
    pub cultural_value_2: Vec<u8>,   // Tertiary (base drift rate)
    // Belief (M37)—indexes into Python-side belief_registry
    pub beliefs: Vec<u8>,
    // Parentage (M39/M57a) — stable agent_ids of biological parents
    pub parent_id_0: Vec<u32>,  // birth parent
    pub parent_id_1: Vec<u32>,  // other parent (spouse at birth time), PARENT_NONE if unknown
    // Wealth (M41) — personal economic accumulation
    pub wealth: Vec<f32>,
    // M48: Memory ring buffer (8 slots per agent)
    pub memory_event_types: Vec<[u8; 8]>,
    pub memory_source_civs: Vec<[u8; 8]>,
    pub memory_turns: Vec<[u16; 8]>,
    pub memory_intensities: Vec<[i8; 8]>,
    pub memory_decay_factors: Vec<[u8; 8]>,
    pub memory_gates: Vec<u8>,
    pub memory_count: Vec<u8>,
    // M51: Per-agent bitmask — bit N = slot N is a legacy (inherited) memory
    pub memory_is_legacy: Vec<u8>,
    // M49: Needs system (6 × f32 per agent)
    pub need_safety: Vec<f32>,
    pub need_material: Vec<f32>,
    pub need_social: Vec<f32>,
    pub need_spiritual: Vec<f32>,
    pub need_autonomy: Vec<f32>,
    pub need_purpose: Vec<f32>,
    // M50a: Per-agent relationship store (8 slots)
    pub rel_target_ids:   Vec<[u32; 8]>,
    pub rel_sentiments:   Vec<[i8; 8]>,
    pub rel_bond_types:   Vec<[u8; 8]>,
    pub rel_formed_turns: Vec<[u16; 8]>,
    pub rel_count:        Vec<u8>,
    // M50b: Synthesis budget — dormant field (no decrement logic yet)
    pub synthesis_budget: Vec<u8>,
    // M55a: Spatial position (unit square per region)
    pub x: Vec<f32>,
    pub y: Vec<f32>,
    // M56b: Per-agent settlement assignment (0 = rural, >0 = settlement_id)
    pub settlement_ids: Vec<u16>,
    // M58a: Merchant mobility trip state
    pub trip_phase: Vec<u8>,           // Idle=0, Loading=1, Transit=2
    pub trip_dest_region: Vec<u16>,
    pub trip_origin_region: Vec<u16>,
    pub trip_good_slot: Vec<u8>,       // good slot 0..7, 255=none
    pub trip_cargo_qty: Vec<f32>,
    pub trip_turns_elapsed: Vec<u16>,
    pub trip_path: Vec<[u16; crate::agent::MAX_PATH_LEN]>,
    pub trip_path_len: Vec<u8>,
    pub trip_path_cursor: Vec<u8>,
    // M59a: Information packet slots (4 per agent)
    pub pkt_type_and_hops: Vec<[u8; 4]>,
    pub pkt_source_region: Vec<[u16; 4]>,
    pub pkt_source_turn: Vec<[u16; 4]>,
    pub pkt_intensity: Vec<[u8; 4]>,
    // M59a: Merchant arrival transient (set by 0.9 merchant mobility, cleared by 0.95 knowledge phase)
    pub arrived_this_turn: Vec<bool>,
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
            life_events: Vec::with_capacity(capacity),
            promotion_progress: Vec::with_capacity(capacity),
            boldness: Vec::with_capacity(capacity),
            ambition: Vec::with_capacity(capacity),
            loyalty_trait: Vec::with_capacity(capacity),
            cultural_value_0: Vec::with_capacity(capacity),
            cultural_value_1: Vec::with_capacity(capacity),
            cultural_value_2: Vec::with_capacity(capacity),
            beliefs: Vec::with_capacity(capacity),
            parent_id_0: Vec::with_capacity(capacity),
            parent_id_1: Vec::with_capacity(capacity),
            wealth: Vec::with_capacity(capacity),
            memory_event_types: Vec::with_capacity(capacity),
            memory_source_civs: Vec::with_capacity(capacity),
            memory_turns: Vec::with_capacity(capacity),
            memory_intensities: Vec::with_capacity(capacity),
            memory_decay_factors: Vec::with_capacity(capacity),
            memory_gates: Vec::with_capacity(capacity),
            memory_count: Vec::with_capacity(capacity),
            memory_is_legacy: Vec::with_capacity(capacity),
            need_safety: Vec::with_capacity(capacity),
            need_material: Vec::with_capacity(capacity),
            need_social: Vec::with_capacity(capacity),
            need_spiritual: Vec::with_capacity(capacity),
            need_autonomy: Vec::with_capacity(capacity),
            need_purpose: Vec::with_capacity(capacity),
            rel_target_ids: Vec::with_capacity(capacity),
            rel_sentiments: Vec::with_capacity(capacity),
            rel_bond_types: Vec::with_capacity(capacity),
            rel_formed_turns: Vec::with_capacity(capacity),
            rel_count: Vec::with_capacity(capacity),
            synthesis_budget: Vec::with_capacity(capacity),
            x: Vec::with_capacity(capacity),
            y: Vec::with_capacity(capacity),
            settlement_ids: Vec::with_capacity(capacity),
            trip_phase: Vec::with_capacity(capacity),
            trip_dest_region: Vec::with_capacity(capacity),
            trip_origin_region: Vec::with_capacity(capacity),
            trip_good_slot: Vec::with_capacity(capacity),
            trip_cargo_qty: Vec::with_capacity(capacity),
            trip_turns_elapsed: Vec::with_capacity(capacity),
            trip_path: Vec::with_capacity(capacity),
            trip_path_len: Vec::with_capacity(capacity),
            trip_path_cursor: Vec::with_capacity(capacity),
            pkt_type_and_hops: Vec::with_capacity(capacity),
            pkt_source_region: Vec::with_capacity(capacity),
            pkt_source_turn: Vec::with_capacity(capacity),
            pkt_intensity: Vec::with_capacity(capacity),
            arrived_this_turn: Vec::with_capacity(capacity),
            alive: Vec::with_capacity(capacity),
            count: 0,
            next_id: 1,
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
        boldness: f32,
        ambition: f32,
        loyalty_trait: f32,
        cultural_value_0: u8,
        cultural_value_1: u8,
        cultural_value_2: u8,
        belief: u8,
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
            self.life_events[slot] = 0;
            self.promotion_progress[slot] = 0;
            self.boldness[slot] = boldness;
            self.ambition[slot] = ambition;
            self.loyalty_trait[slot] = loyalty_trait;
            self.cultural_value_0[slot] = cultural_value_0;
            self.cultural_value_1[slot] = cultural_value_1;
            self.cultural_value_2[slot] = cultural_value_2;
            self.beliefs[slot] = belief;
            self.parent_id_0[slot] = crate::agent::PARENT_NONE;
            self.parent_id_1[slot] = crate::agent::PARENT_NONE;
            self.wealth[slot] = crate::agent::STARTING_WEALTH;
            self.memory_event_types[slot] = [0; 8];
            self.memory_source_civs[slot] = [0; 8];
            self.memory_turns[slot] = [0; 8];
            self.memory_intensities[slot] = [0; 8];
            self.memory_decay_factors[slot] = [0; 8];
            self.memory_gates[slot] = 0;
            self.memory_count[slot] = 0;
            self.memory_is_legacy[slot] = 0;
            self.need_safety[slot] = crate::agent::STARTING_NEED;
            self.need_material[slot] = crate::agent::STARTING_NEED;
            self.need_social[slot] = crate::agent::STARTING_NEED;
            self.need_spiritual[slot] = crate::agent::STARTING_NEED;
            self.need_autonomy[slot] = crate::agent::STARTING_NEED;
            self.need_purpose[slot] = crate::agent::STARTING_NEED;
            // M50a relationship init
            self.rel_target_ids[slot] = [0u32; 8];
            self.rel_sentiments[slot] = [0i8; 8];
            self.rel_bond_types[slot] = [255u8; 8]; // 255 = empty sentinel (not 0, since Kin=5)
            self.rel_formed_turns[slot] = [0u16; 8];
            self.rel_count[slot] = 0;
            self.synthesis_budget[slot] = crate::agent::SYNTHESIS_BUDGET_MAX;
            self.x[slot] = 0.5;
            self.y[slot] = 0.5;
            self.settlement_ids[slot] = 0;
            self.trip_phase[slot] = crate::agent::TRIP_PHASE_IDLE;
            self.trip_dest_region[slot] = 0;
            self.trip_origin_region[slot] = 0;
            self.trip_good_slot[slot] = crate::agent::TRIP_GOOD_SLOT_NONE;
            self.trip_cargo_qty[slot] = 0.0;
            self.trip_turns_elapsed[slot] = 0;
            self.trip_path[slot] = [u16::MAX; crate::agent::MAX_PATH_LEN];
            self.trip_path_len[slot] = 0;
            self.trip_path_cursor[slot] = 0;
            self.pkt_type_and_hops[slot] = [0; 4];
            self.pkt_source_region[slot] = [0; 4];
            self.pkt_source_turn[slot] = [0; 4];
            self.pkt_intensity[slot] = [0; 4];
            self.arrived_this_turn[slot] = false;
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
            self.life_events.push(0);
            self.promotion_progress.push(0);
            self.boldness.push(boldness);
            self.ambition.push(ambition);
            self.loyalty_trait.push(loyalty_trait);
            self.cultural_value_0.push(cultural_value_0);
            self.cultural_value_1.push(cultural_value_1);
            self.cultural_value_2.push(cultural_value_2);
            self.beliefs.push(belief);
            self.parent_id_0.push(crate::agent::PARENT_NONE);
            self.parent_id_1.push(crate::agent::PARENT_NONE);
            self.wealth.push(crate::agent::STARTING_WEALTH);
            self.memory_event_types.push([0; 8]);
            self.memory_source_civs.push([0; 8]);
            self.memory_turns.push([0; 8]);
            self.memory_intensities.push([0; 8]);
            self.memory_decay_factors.push([0; 8]);
            self.memory_gates.push(0);
            self.memory_count.push(0);
            self.memory_is_legacy.push(0);
            self.need_safety.push(crate::agent::STARTING_NEED);
            self.need_material.push(crate::agent::STARTING_NEED);
            self.need_social.push(crate::agent::STARTING_NEED);
            self.need_spiritual.push(crate::agent::STARTING_NEED);
            self.need_autonomy.push(crate::agent::STARTING_NEED);
            self.need_purpose.push(crate::agent::STARTING_NEED);
            // M50a relationship init
            self.rel_target_ids.push([0u32; 8]);
            self.rel_sentiments.push([0i8; 8]);
            self.rel_bond_types.push([255u8; 8]);
            self.rel_formed_turns.push([0u16; 8]);
            self.rel_count.push(0);
            self.synthesis_budget.push(crate::agent::SYNTHESIS_BUDGET_MAX);
            self.x.push(0.5);
            self.y.push(0.5);
            self.settlement_ids.push(0);
            self.trip_phase.push(crate::agent::TRIP_PHASE_IDLE);
            self.trip_dest_region.push(0);
            self.trip_origin_region.push(0);
            self.trip_good_slot.push(crate::agent::TRIP_GOOD_SLOT_NONE);
            self.trip_cargo_qty.push(0.0);
            self.trip_turns_elapsed.push(0);
            self.trip_path.push([u16::MAX; crate::agent::MAX_PATH_LEN]);
            self.trip_path_len.push(0);
            self.trip_path_cursor.push(0);
            self.pkt_type_and_hops.push([0; 4]);
            self.pkt_source_region.push([0; 4]);
            self.pkt_source_turn.push([0; 4]);
            self.pkt_intensity.push([0; 4]);
            self.arrived_this_turn.push(false);
            self.alive.push(true);
            self.count += 1;
            slot
        }
    }

    /// Kill an agent by slot. Zeros key fields, decrements live count, and
    /// returns slot to free-list. Zeroing prevents stale data from leaking
    /// if dead slots are accidentally accessed before reuse.
    pub fn kill(&mut self, slot: usize) {
        if self.is_alive(slot) {
            self.set_dead(slot);
            // Zero out key fields to prevent stale data leaks (M-4 audit)
            self.wealth[slot] = 0.0;
            self.satisfactions[slot] = 0.0;
            self.loyalties[slot] = 0.0;
            self.beliefs[slot] = crate::agent::BELIEF_NONE;
            self.occupations[slot] = 0;
            self.civ_affinities[slot] = 255;
            self.life_events[slot] = 0;
            self.displacement_turns[slot] = 0;
            self.promotion_progress[slot] = 0;
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

    // --- Setters (M26) ---

    #[inline]
    pub fn set_satisfaction(&mut self, slot: usize, val: f32) {
        self.satisfactions[slot] = val;
    }

    #[inline]
    pub fn set_loyalty(&mut self, slot: usize, val: f32) {
        self.loyalties[slot] = val;
    }

    #[inline]
    pub fn set_occupation(&mut self, slot: usize, occ: u8) {
        self.occupations[slot] = occ;
    }

    #[inline]
    pub fn set_region(&mut self, slot: usize, region: u16) {
        self.regions[slot] = region;
    }

    #[inline]
    pub fn set_civ_affinity(&mut self, slot: usize, civ: u8) {
        self.civ_affinities[slot] = civ;
    }

    #[inline]
    pub fn set_displacement_turns(&mut self, slot: usize, turns: u8) {
        self.displacement_turns[slot] = turns;
    }

    // --- Additional accessors (M26) ---

    #[inline]
    pub fn loyalty(&self, slot: usize) -> f32 {
        self.loyalties[slot]
    }

    #[inline]
    pub fn origin_region(&self, slot: usize) -> u16 {
        self.origin_regions[slot]
    }

    #[inline]
    pub fn displacement_turns(&self, slot: usize) -> u8 {
        self.displacement_turns[slot]
    }

    #[inline]
    pub fn boldness(&self, slot: usize) -> f32 {
        self.boldness[slot]
    }

    #[inline]
    pub fn ambition(&self, slot: usize) -> f32 {
        self.ambition[slot]
    }

    #[inline]
    pub fn loyalty_trait(&self, slot: usize) -> f32 {
        self.loyalty_trait[slot]
    }

    #[inline]
    pub fn cultural_value_0(&self, slot: usize) -> u8 { self.cultural_value_0[slot] }
    #[inline]
    pub fn cultural_value_1(&self, slot: usize) -> u8 { self.cultural_value_1[slot] }
    #[inline]
    pub fn cultural_value_2(&self, slot: usize) -> u8 { self.cultural_value_2[slot] }
    #[inline]
    pub fn is_named(&self, slot: usize) -> bool {
        self.life_events[slot] & crate::agent::IS_NAMED != 0
    }
    #[inline]
    pub fn parent_id_0(&self, slot: usize) -> u32 {
        self.parent_id_0[slot]
    }
    #[inline]
    pub fn parent_id_1(&self, slot: usize) -> u32 {
        self.parent_id_1[slot]
    }
    #[inline]
    pub fn parent_ids(&self, slot: usize) -> [u32; 2] {
        [self.parent_id_0[slot], self.parent_id_1[slot]]
    }
    /// Check if `agent_id` is either parent of the agent at `slot`.
    #[inline]
    pub fn has_parent(&self, slot: usize, agent_id: u32) -> bool {
        agent_id != crate::agent::PARENT_NONE
            && (self.parent_id_0[slot] == agent_id || self.parent_id_1[slot] == agent_id)
    }

    /// M58a: Check if agent is currently on a merchant trip.
    #[inline]
    pub fn is_on_trip(&self, slot: usize) -> bool {
        self.trip_phase[slot] != crate::agent::TRIP_PHASE_IDLE
    }

    // --- Skill (M26) ---

    /// Grow current occupation's skill by SKILL_GROWTH_PER_TURN, capped at SKILL_MAX.
    pub fn grow_skill(&mut self, slot: usize) {
        use crate::agent::{SKILL_GROWTH_PER_TURN, SKILL_MAX};
        let occ = self.occupations[slot] as usize;
        let idx = slot * 5 + occ;
        self.skills[idx] = (self.skills[idx] + SKILL_GROWTH_PER_TURN).min(SKILL_MAX);
    }

    /// Get skill value for a specific occupation.
    pub fn skill(&self, slot: usize, occ: usize) -> f32 {
        self.skills[slot * 5 + occ]
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

    /// Linear scan to find the slot index for a given agent_id.
    /// Returns None if not found or not alive.
    pub fn find_slot_by_id(&self, agent_id: u32) -> Option<usize> {
        if agent_id == 0 { return None; } // PARENT_NONE sentinel
        for slot in 0..self.capacity() {
            if self.alive[slot] && self.ids[slot] == agent_id {
                return Some(slot);
            }
        }
        None
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
        let mut boldness_col = Float32Builder::with_capacity(live);
        let mut ambition_col = Float32Builder::with_capacity(live);
        let mut loyalty_trait_col = Float32Builder::with_capacity(live);
        let mut cultural_value_0_col = UInt8Builder::with_capacity(live);
        let mut cultural_value_1_col = UInt8Builder::with_capacity(live);
        let mut cultural_value_2_col = UInt8Builder::with_capacity(live);
        let mut belief_col = UInt8Builder::with_capacity(live);
        let mut parent_id_0_col = UInt32Builder::with_capacity(live);
        let mut parent_id_1_col = UInt32Builder::with_capacity(live);
        let mut wealth_col = Float32Builder::with_capacity(live);
        let mut x_col = Float32Builder::with_capacity(live);
        let mut y_col = Float32Builder::with_capacity(live);
        let mut settlement_id_col = UInt16Builder::with_capacity(live);

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
            boldness_col.append_value(self.boldness[slot]);
            ambition_col.append_value(self.ambition[slot]);
            loyalty_trait_col.append_value(self.loyalty_trait[slot]);
            cultural_value_0_col.append_value(self.cultural_value_0[slot]);
            cultural_value_1_col.append_value(self.cultural_value_1[slot]);
            cultural_value_2_col.append_value(self.cultural_value_2[slot]);
            belief_col.append_value(self.beliefs[slot]);
            parent_id_0_col.append_value(self.parent_id_0[slot]);
            parent_id_1_col.append_value(self.parent_id_1[slot]);
            wealth_col.append_value(self.wealth[slot]);
            x_col.append_value(self.x[slot]);
            y_col.append_value(self.y[slot]);
            settlement_id_col.append_value(self.settlement_ids[slot]);
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
                Arc::new(boldness_col.finish()) as _,
                Arc::new(ambition_col.finish()) as _,
                Arc::new(loyalty_trait_col.finish()) as _,
                Arc::new(cultural_value_0_col.finish()) as _,
                Arc::new(cultural_value_1_col.finish()) as _,
                Arc::new(cultural_value_2_col.finish()) as _,
                Arc::new(belief_col.finish()) as _,
                Arc::new(parent_id_0_col.finish()) as _,
                Arc::new(parent_id_1_col.finish()) as _,
                Arc::new(wealth_col.finish()) as _,
                Arc::new(x_col.finish()) as _,
                Arc::new(y_col.finish()) as _,
                Arc::new(settlement_id_col.finish()) as _,
            ],
        )
    }

    /// Return a per-civ aggregate RecordBatch.
    /// Normalization uses civ carrying capacity (sum of controlled regions'
    /// capacity) rather than live population.
    pub fn compute_aggregates(&self, regions: &[RegionState]) -> Result<RecordBatch, ArrowError> {
        // First pass: build civ -> controlled-region capacity mapping.
        let mut civ_capacity: HashMap<u8, f64> = HashMap::new();
        for r in regions {
            if r.controller_civ != 255 {
                *civ_capacity.entry(r.controller_civ).or_insert(0.0) += r.carrying_capacity as f64;
            }
        }

        // Second pass: accumulate per-polity stats from alive agents.
        // Controlled regions contribute to their current controller, while
        // uncontrolled regions fall back to the agent's own affinity so we
        // still expose stable rows in diagnostics/tests.
        struct CivAccum {
            population: u32,
            soldier_skill_sum: f64,
            merchant_skill_sum: f64,
            scholar_skill_sum: f64,
            priest_skill_sum: f64,
            satisfaction_sum: f64,
            loyalty_sum: f64,
        }

        let mut accums: HashMap<u8, CivAccum> = HashMap::new();
        for slot in 0..self.capacity() {
            if !self.is_alive(slot) {
                continue;
            }
            let civ = regions
                .get(self.regions[slot] as usize)
                .and_then(|region| {
                    if region.controller_civ != 255 {
                        Some(region.controller_civ)
                    } else {
                        None
                    }
                })
                .unwrap_or(self.civ_affinities[slot]);
            let a = accums.entry(civ).or_insert(CivAccum {
                population: 0,
                soldier_skill_sum: 0.0,
                merchant_skill_sum: 0.0,
                scholar_skill_sum: 0.0,
                priest_skill_sum: 0.0,
                satisfaction_sum: 0.0,
                loyalty_sum: 0.0,
            });
            a.population += 1;
            let occ = self.occupations[slot] as usize;
            let active_skill = self.skills[slot * 5 + occ] as f64;
            match occ {
                1 => a.soldier_skill_sum += active_skill,
                2 => a.merchant_skill_sum += active_skill,
                3 => a.scholar_skill_sum += active_skill,
                4 => a.priest_skill_sum += active_skill,
                _ => {}
            }
            a.satisfaction_sum += self.satisfactions[slot] as f64;
            a.loyalty_sum += self.loyalties[slot] as f64;
        }

        // M-AF1 #7: Emit zero-rows for civs that control regions but have no
        // alive agents.  This prevents Python _write_back from skipping a civ
        // (leaving stale stats from the previous turn).
        for &civ_id in civ_capacity.keys() {
            accums.entry(civ_id).or_insert(CivAccum {
                population: 0,
                soldier_skill_sum: 0.0,
                merchant_skill_sum: 0.0,
                scholar_skill_sum: 0.0,
                priest_skill_sum: 0.0,
                satisfaction_sum: 0.0,
                loyalty_sum: 0.0,
            });
        }

        // Sort by civ_id for deterministic output.
        let mut sorted: Vec<u8> = accums.keys().copied().collect();
        sorted.sort();

        let n = sorted.len();
        let mut civ_ids = UInt8Builder::with_capacity(n);  // M-5: standardized to UInt8
        let mut populations = UInt32Builder::with_capacity(n);
        let mut military_b = UInt32Builder::with_capacity(n);
        let mut economy_b = UInt32Builder::with_capacity(n);
        let mut culture_b = UInt32Builder::with_capacity(n);
        let mut stability_b = UInt32Builder::with_capacity(n);

        for civ in sorted {
            let a = &accums[&civ];
            let cap = civ_capacity.get(&civ).copied().unwrap_or(0.0);

            civ_ids.append_value(civ);
            populations.append_value(a.population);

            if cap > 0.0 && a.population > 0 {
                let mil = ((a.soldier_skill_sum / (cap * 0.15)).min(1.0) * 100.0) as u32;
                let eco = ((a.merchant_skill_sum / (cap * 0.10)).min(1.0) * 100.0) as u32;
                let cul = (((a.scholar_skill_sum + a.priest_skill_sum * 0.3) / (cap * 0.13)).min(1.0) * 100.0) as u32;
                let mean_sat = a.satisfaction_sum / a.population as f64;
                let mean_loy = a.loyalty_sum / a.population as f64;
                let stab = ((mean_sat * mean_loy * 100.0).min(100.0)) as u32;

                military_b.append_value(mil);
                economy_b.append_value(eco);
                culture_b.append_value(cul);
                stability_b.append_value(stab);
            } else {
                military_b.append_value(0);
                economy_b.append_value(0);
                culture_b.append_value(0);
                stability_b.append_value(0);
            }
        }

        let schema = Arc::new(ffi::aggregates_schema());
        RecordBatch::try_new(
            schema,
            vec![
                Arc::new(civ_ids.finish()) as _,
                Arc::new(populations.finish()) as _,
                Arc::new(military_b.finish()) as _,
                Arc::new(economy_b.finish()) as _,
                Arc::new(culture_b.finish()) as _,
                Arc::new(stability_b.finish()) as _,
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
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(slot, 0);
        assert!(pool.is_alive(slot));
        assert_eq!(pool.alive_count(), 1);
        assert_eq!(pool.capacity(), 1);
        assert_eq!(pool.age(slot), 25);
        assert_eq!(pool.region(slot), 0);
        assert_eq!(pool.occupation(slot), Occupation::Farmer as u8);
        assert_eq!(pool.id(slot), 1); // M39: first agent id must be 1, not 0 (PARENT_NONE sentinel)
    }

    #[test]
    fn test_kill_marks_dead_and_decrements_count() {
        let mut pool = AgentPool::new(8);
        let s0 = pool.spawn(0, 0, Occupation::Soldier, 30, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let s1 = pool.spawn(1, 1, Occupation::Merchant, 40, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
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
        let slot = pool.spawn(0, 0, Occupation::Scholar, 59, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
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
        let s0 = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let s1 = pool.spawn(1, 0, Occupation::Priest, 35, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let s2 = pool.spawn(0, 0, Occupation::Merchant, 28, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);

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
        let s0 = pool.spawn(0, 0, Occupation::Farmer, 10, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let s1 = pool.spawn(0, 0, Occupation::Soldier, 20, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let s2 = pool.spawn(0, 0, Occupation::Scholar, 30, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert!(pool.id(s0) < pool.id(s1));
        assert!(pool.id(s1) < pool.id(s2));
    }

    // --- Arrow round-trip tests (Task 9) ---

    #[test]
    fn test_to_record_batch_filters_dead() {
        use arrow::array::{UInt16Array, UInt32Array, UInt8Array};

        let mut pool = AgentPool::new(8);
        let s0 = pool.spawn(0, 1, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let s1 = pool.spawn(1, 2, Occupation::Soldier, 30, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let s2 = pool.spawn(0, 1, Occupation::Merchant, 40, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);

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
    fn test_compute_aggregates_no_controlled_regions() {
        use arrow::array::{UInt32Array};
        use crate::region::RegionState;

        let mut pool = AgentPool::new(8);
        // civ 0: 2 agents
        pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.spawn(0, 0, Occupation::Soldier, 30, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        // civ 1: 1 agent
        pool.spawn(1, 1, Occupation::Scholar, 35, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);

        // No civ controls any region (controller_civ = 255 default).
        let regions = vec![RegionState::new(0), RegionState::new(1)];
        let batch = pool.compute_aggregates(&regions).expect("compute_aggregates failed");

        // Two civs.
        assert_eq!(batch.num_rows(), 2);

        let schema = batch.schema();
        assert_eq!(schema.field(0).name(), "civ_id");
        assert_eq!(schema.field(1).name(), "population");
        assert_eq!(schema.field(2).name(), "military");
        assert_eq!(schema.field(5).name(), "stability");

        // M-5: civ_id standardized to UInt8
        let civ_ids = batch
            .column(0)
            .as_any()
            .downcast_ref::<arrow::array::UInt8Array>()
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

        // No controlled regions -> zero capacity -> zeroed metrics.
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
    fn test_compute_aggregates_populated() {
        use arrow::array::UInt32Array;
        use crate::region::RegionState;

        let mut pool = AgentPool::new(16);

        // Spawn 10 agents for civ 0, all in region 0.
        // 3 soldiers, 2 merchants, 2 scholars, 1 priest, 2 farmers.
        for _ in 0..3 {
            pool.spawn(0, 0, Occupation::Soldier, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        for _ in 0..2 {
            pool.spawn(0, 0, Occupation::Merchant, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        for _ in 0..2 {
            pool.spawn(0, 0, Occupation::Scholar, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        pool.spawn(0, 0, Occupation::Priest, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        for _ in 0..2 {
            pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }

        // Set known skills for all agents of each occupation.
        // Each soldier gets skill 0.8 at occ 1, each merchant 0.6 at occ 2, etc.
        for slot in 0..pool.capacity() {
            if !pool.is_alive(slot) { continue; }
            match pool.occupation(slot) {
                1 => pool.skills[slot * 5 + 1] = 0.8,  // soldier
                2 => pool.skills[slot * 5 + 2] = 0.6,  // merchant
                3 => pool.skills[slot * 5 + 3] = 0.7,  // scholar
                4 => pool.skills[slot * 5 + 4] = 0.5,  // priest
                _ => {}
            }
            pool.set_satisfaction(slot, 0.8);
            pool.set_loyalty(slot, 0.6);
        }

        // Region controlled by civ 0, capacity = 100.
        let mut region = RegionState::new(0);
        region.carrying_capacity = 100;
        region.controller_civ = 0;
        let regions = vec![region];

        let batch = pool.compute_aggregates(&regions).expect("compute_aggregates failed");
        assert_eq!(batch.num_rows(), 1);

        let populations = batch.column(1).as_any().downcast_ref::<UInt32Array>().unwrap();
        assert_eq!(populations.value(0), 10);

        // military = soldier_skill_sum / (cap * 0.15) capped at 1.0, * 100
        // soldier_skill_sum = 3 * 0.8 = 2.4; cap * 0.15 = 100 * 0.15 = 15
        // military = (2.4 / 15).min(1.0) * 100 = 16
        let military = batch.column(2).as_any().downcast_ref::<UInt32Array>().unwrap();
        assert_eq!(military.value(0), 16);

        // economy = merchant_skill_sum / (cap * 0.10) capped at 1.0, * 100
        // merchant_skill_sum = 2 * 0.6 = 1.2; cap * 0.10 = 10
        // economy = (1.2 / 10).min(1.0) * 100 = 12
        let economy = batch.column(3).as_any().downcast_ref::<UInt32Array>().unwrap();
        assert_eq!(economy.value(0), 12);

        // culture = (scholar_skill_sum + priest_skill_sum * 0.3) / (cap * 0.13), capped at 1.0, * 100
        // scholar_skill_sum = 2 * 0.7 = 1.4; priest_skill_sum = 1 * 0.5 = 0.5
        // culture = (1.4 + 0.5 * 0.3) / (100 * 0.13) = (1.4 + 0.15) / 13 = 1.55/13 = 0.1192...
        // -> (0.1192 * 100) as u32 = 11
        let culture = batch.column(4).as_any().downcast_ref::<UInt32Array>().unwrap();
        assert_eq!(culture.value(0), 11);

        // stability = mean(satisfaction) * mean(loyalty) * 100, capped at 100
        // mean_sat = 0.8, mean_loy = 0.6 -> 0.8 * 0.6 * 100 = 48
        let stability = batch.column(5).as_any().downcast_ref::<UInt32Array>().unwrap();
        assert_eq!(stability.value(0), 48);
    }

    #[test]
    fn test_compute_aggregates_groups_controlled_regions_under_controller() {
        use arrow::array::UInt32Array;
        use crate::region::RegionState;

        let mut pool = AgentPool::new(8);

        pool.spawn(0, 1, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.spawn(0, 1, Occupation::Soldier, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.spawn(1, 1, Occupation::Merchant, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.spawn(1, 1, Occupation::Scholar, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.spawn(1, 1, Occupation::Priest, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);

        let mut region_0 = RegionState::new(0);
        region_0.carrying_capacity = 60;
        region_0.controller_civ = 0;

        let mut region_1 = RegionState::new(1);
        region_1.carrying_capacity = 60;
        region_1.controller_civ = 1;

        let batch = pool
            .compute_aggregates(&[region_0, region_1])
            .expect("compute_aggregates failed");

        // M-5: civ_id standardized to UInt8
        let civ_ids = batch
            .column(0)
            .as_any()
            .downcast_ref::<arrow::array::UInt8Array>()
            .unwrap();
        let populations = batch
            .column(1)
            .as_any()
            .downcast_ref::<UInt32Array>()
            .unwrap();

        assert_eq!(batch.num_rows(), 2);
        assert_eq!(civ_ids.value(0), 0);
        assert_eq!(populations.value(0), 2);
        assert_eq!(civ_ids.value(1), 1);
        assert_eq!(populations.value(1), 3);
    }

    #[test]
    fn test_compute_aggregates_zero_agents_with_controlled_region() {
        // M-AF1 #7: A civ controls a region but has zero alive agents.
        // compute_aggregates must emit a zero-row for that civ.
        use arrow::array::{UInt32Array, UInt8Array};
        use crate::region::RegionState;

        let pool = AgentPool::new(4); // No agents spawned at all.

        // Region 0 is controlled by civ 0, but pool has no alive agents.
        let mut region = RegionState::new(0);
        region.carrying_capacity = 60;
        region.controller_civ = 0;

        let batch = pool
            .compute_aggregates(&[region])
            .expect("compute_aggregates failed");

        // Must have exactly one row for civ 0.
        assert_eq!(batch.num_rows(), 1);

        let civ_ids = batch
            .column(0)
            .as_any()
            .downcast_ref::<UInt8Array>()
            .unwrap();
        assert_eq!(civ_ids.value(0), 0);

        let populations = batch
            .column(1)
            .as_any()
            .downcast_ref::<UInt32Array>()
            .unwrap();
        assert_eq!(populations.value(0), 0);

        // All metric columns should be zero.
        for col_idx in 2..=5 {
            let col = batch
                .column(col_idx)
                .as_any()
                .downcast_ref::<UInt32Array>()
                .unwrap();
            assert_eq!(col.value(0), 0, "col {} should be zero", col_idx);
        }
    }

    #[test]
    fn test_compute_aggregates_mixed_zero_and_populated_civs() {
        // M-AF1 #7: civ 0 has agents, civ 1 controls a region but has no agents.
        // Both must appear in the output.
        use arrow::array::{UInt32Array, UInt8Array};
        use crate::region::RegionState;

        let mut pool = AgentPool::new(8);
        // Spawn 2 agents for civ 0 in region 0.
        pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.spawn(0, 0, Occupation::Soldier, 30, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);

        let mut region_0 = RegionState::new(0);
        region_0.carrying_capacity = 60;
        region_0.controller_civ = 0;

        // Region 1 controlled by civ 1 -- no agents.
        let mut region_1 = RegionState::new(1);
        region_1.carrying_capacity = 40;
        region_1.controller_civ = 1;

        let batch = pool
            .compute_aggregates(&[region_0, region_1])
            .expect("compute_aggregates failed");

        assert_eq!(batch.num_rows(), 2);

        let civ_ids = batch
            .column(0)
            .as_any()
            .downcast_ref::<UInt8Array>()
            .unwrap();
        let populations = batch
            .column(1)
            .as_any()
            .downcast_ref::<UInt32Array>()
            .unwrap();

        assert_eq!(civ_ids.value(0), 0);
        assert_eq!(populations.value(0), 2); // civ 0 has 2 agents

        assert_eq!(civ_ids.value(1), 1);
        assert_eq!(populations.value(1), 0); // civ 1 has zero agents

        // civ 1's metrics should all be zero.
        for col_idx in 2..=5 {
            let col = batch
                .column(col_idx)
                .as_any()
                .downcast_ref::<UInt32Array>()
                .unwrap();
            assert_eq!(col.value(1), 0, "civ 1 col {} should be zero", col_idx);
        }
    }

    #[test]
    fn test_region_populations() {
        use arrow::array::{UInt16Array, UInt32Array};

        let mut pool = AgentPool::new(8);
        let s0 = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);  // region 0
        let s1 = pool.spawn(1, 0, Occupation::Soldier, 30, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE); // region 1
        let _s2 = pool.spawn(0, 0, Occupation::Merchant, 35, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE); // region 0
        let _s3 = pool.spawn(2, 0, Occupation::Scholar, 40, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);  // region 2

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
            pool.spawn(0, 0, Occupation::Farmer, 0, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
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
            pool.spawn(0, 0, Occupation::Soldier, 0, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        assert_eq!(pool.alive_count(), 800);
        assert_eq!(pool.capacity(), capacity_before); // no growth!
        assert_eq!(pool.free_slot_count(), 200);

        let batch = pool.to_record_batch().unwrap();
        assert_eq!(batch.num_rows(), 800);
    }

    #[test]
    fn test_set_satisfaction() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert!((pool.satisfaction(slot) - 0.5).abs() < 0.01);
        pool.set_satisfaction(slot, 0.8);
        assert!((pool.satisfaction(slot) - 0.8).abs() < 0.01);
    }

    #[test]
    fn test_set_loyalty() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Soldier, 30, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.set_loyalty(slot, 0.2);
        assert!((pool.loyalty(slot) - 0.2).abs() < 0.01);
    }

    #[test]
    fn test_set_occupation() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.set_occupation(slot, Occupation::Merchant as u8);
        assert_eq!(pool.occupation(slot), Occupation::Merchant as u8);
    }

    #[test]
    fn test_set_region() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.set_region(slot, 3);
        assert_eq!(pool.region(slot), 3);
    }

    #[test]
    fn test_set_civ_affinity() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.set_civ_affinity(slot, 5);
        assert_eq!(pool.civ_affinity(slot), 5);
    }

    #[test]
    fn test_set_displacement_turns() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        pool.set_displacement_turns(slot, 3);
        assert_eq!(pool.displacement_turns(slot), 3);
    }

    #[test]
    fn test_grow_skill() {
        use crate::agent::{SKILL_GROWTH_PER_TURN, SKILL_MAX};
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Soldier, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert!((pool.skills[slot * 5 + 1]).abs() < 0.01);
        pool.grow_skill(slot);
        assert!((pool.skills[slot * 5 + 1] - SKILL_GROWTH_PER_TURN).abs() < 0.01);
        pool.skills[slot * 5 + 1] = SKILL_MAX - 0.01;
        pool.grow_skill(slot);
        assert!((pool.skills[slot * 5 + 1] - SKILL_MAX).abs() < 0.01);
    }

    #[test]
    fn test_loyalty_accessor() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert!((pool.loyalty(slot) - 0.5).abs() < 0.01);
    }

    #[test]
    fn test_origin_region_accessor() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(3, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(pool.origin_region(slot), 3);
    }

    #[test]
    fn test_displacement_turns_accessor() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(pool.displacement_turns(slot), 0);
    }

    #[test]
    fn test_life_events_bitflag() {
        use crate::agent::*;
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(pool.life_events[slot], 0);
        pool.life_events[slot] |= LIFE_EVENT_REBELLION;
        assert_eq!(pool.life_events[slot], 1);
        pool.life_events[slot] |= LIFE_EVENT_MIGRATION;
        assert_eq!(pool.life_events[slot], 0b00000011);
        pool.life_events[slot] |= LIFE_EVENT_WAR_SURVIVAL | LIFE_EVENT_LOYALTY_FLIP | LIFE_EVENT_OCC_SWITCH;
        assert_eq!(pool.life_events[slot], 0b00011111);
    }

    #[test]
    fn test_promotion_progress_increments() {
        use crate::agent::*;
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Soldier, 20, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(pool.promotion_progress[slot], 0);
        let occ = pool.occupations[slot] as usize;
        pool.skills[slot * 5 + occ] = 0.95;
        if pool.skills[slot * 5 + occ] > PROMOTION_SKILL_THRESHOLD {
            pool.promotion_progress[slot] = pool.promotion_progress[slot].saturating_add(1);
        }
        assert_eq!(pool.promotion_progress[slot], 1);
        pool.skills[slot * 5 + occ] = 0.5;
        if pool.skills[slot * 5 + occ] <= PROMOTION_SKILL_THRESHOLD {
            pool.promotion_progress[slot] = 0;
        }
        assert_eq!(pool.promotion_progress[slot], 0);
        pool.promotion_progress[slot] = 15;
        pool.occupations[slot] = Occupation::Merchant as u8;
        pool.promotion_progress[slot] = 0;
        assert_eq!(pool.promotion_progress[slot], 0);
    }

    #[test]
    fn test_spawn_cultural_values() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, 4, 3, 2, crate::agent::BELIEF_NONE);
        assert_eq!(pool.cultural_value_0[slot], 4);
        assert_eq!(pool.cultural_value_1[slot], 3);
        assert_eq!(pool.cultural_value_2[slot], 2);
    }

    #[test]
    fn test_spawn_reuse_slot_cultural_values() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, 4, 3, 2, crate::agent::BELIEF_NONE);
        pool.kill(slot);
        let reused = pool.spawn(0, 1, Occupation::Soldier, 18, 0.6, 0.4, 0.5, 0, 1, 5, crate::agent::BELIEF_NONE);
        assert_eq!(reused, slot);
        assert_eq!(pool.cultural_value_0[reused], 0);
        assert_eq!(pool.cultural_value_1[reused], 1);
        assert_eq!(pool.cultural_value_2[reused], 5);
    }

    #[test]
    fn test_is_named_bit() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert!(!pool.is_named(slot));
        pool.life_events[slot] |= crate::agent::IS_NAMED;
        assert!(pool.is_named(slot));
        pool.life_events[slot] |= crate::agent::LIFE_EVENT_REBELLION;
        assert!(pool.is_named(slot)); // IS_NAMED survives other bits
    }

    #[test]
    fn test_spawn_sets_belief() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 0, 0.0, 0.0, 0.0, 0, 0, 0, 3);
        assert_eq!(pool.beliefs[slot], 3);
    }

    #[test]
    fn test_spawn_reuse_sets_belief() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 0, 0.0, 0.0, 0.0, 0, 0, 0, 5);
        pool.kill(slot);
        let slot2 = pool.spawn(0, 0, Occupation::Farmer, 0, 0.0, 0.0, 0.0, 0, 0, 0, 7);
        assert_eq!(slot, slot2);
        assert_eq!(pool.beliefs[slot2], 7);
    }

    #[test]
    fn test_parent_id_defaults_to_none() {
        let mut pool = AgentPool::new(4);
        let s0 = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(pool.parent_id_0(s0), crate::agent::PARENT_NONE);
        assert_eq!(pool.parent_id_1(s0), crate::agent::PARENT_NONE);

        // Kill and reuse slot — parent_ids should reset to PARENT_NONE
        pool.kill(s0);
        let s1 = pool.spawn(0, 0, Occupation::Soldier, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(s1, s0); // reused slot
        assert_eq!(pool.parent_id_0(s1), crate::agent::PARENT_NONE);
        assert_eq!(pool.parent_id_1(s1), crate::agent::PARENT_NONE);
    }

    // M-4 audit: kill() zeros key fields to prevent stale data leaks
    #[test]
    fn test_kill_zeros_fields() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Merchant, 25, 0.0, 0.0, 0.0, 0, 1, 2, 3);
        // Set some non-zero state
        pool.wealth[slot] = 42.0;
        pool.set_satisfaction(slot, 0.8);
        pool.set_loyalty(slot, 0.9);
        pool.life_events[slot] = 0xFF;
        pool.promotion_progress[slot] = 10;
        pool.set_displacement_turns(slot, 5);

        pool.kill(slot);

        // All key fields should be zeroed
        assert!(!pool.is_alive(slot));
        assert_eq!(pool.wealth[slot], 0.0);
        assert_eq!(pool.satisfaction(slot), 0.0);
        assert_eq!(pool.loyalty(slot), 0.0);
        assert_eq!(pool.beliefs[slot], crate::agent::BELIEF_NONE);
        assert_eq!(pool.occupations[slot], 0);
        assert_eq!(pool.civ_affinities[slot], 255);
        assert_eq!(pool.life_events[slot], 0);
        assert_eq!(pool.displacement_turns(slot), 0);
        assert_eq!(pool.promotion_progress[slot], 0);
    }
}
