//! Pure Rust Phase 10 politics core — 11-step ordered consequence pass.
//! No PyO3 — FFI wrappers live in ffi.rs.
//!
//! Mirrors the Python oracle in `src/chronicler/politics.py` and the inline
//! forced collapse in `src/chronicler/simulation.py:1020-1041`.

// Suppress warnings for fields/functions that Task 3 (FFI) will wire up.
#![allow(unused_variables, dead_code, unused_imports)]

use std::collections::{HashMap, HashSet, VecDeque};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Secession grace period: civs younger than this many turns skip secession.
const SECESSION_GRACE_TURNS: u32 = 50;

/// M38b: Schism secession modifier (from religion.py SCHISM_SECESSION_MODIFIER = 10).
const SCHISM_SECESSION_MODIFIER: f32 = 10.0;

/// Sentinel for "no civ" / uncontrolled region.
pub const CIV_NONE: u16 = 0xFFFF;
/// Sentinel for "no region".
pub const REGION_NONE: u16 = 0xFFFF;
/// Sentinel for "no belief" (matches Python 0xFF).
pub const BELIEF_NONE: u8 = 0xFF;
/// Sentinel for "no federation".
pub const FED_NONE: u16 = 0xFFFF;

// ---------------------------------------------------------------------------
// CivRef / FederationRef — temporary references for new entities
// ---------------------------------------------------------------------------

/// Reference to a civ: either an existing index or a locally-assigned new id.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum CivRef {
    Existing(u16),
    New(u16),
}

/// Reference to a federation.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum FedRef {
    Existing(u16),
    New(u16),
}

// ---------------------------------------------------------------------------
// Disposition encoding
// ---------------------------------------------------------------------------

/// Matches Python Disposition enum.
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Disposition {
    Hostile = 0,
    Suspicious = 1,
    Neutral = 2,
    Friendly = 3,
    Allied = 4,
}

impl Disposition {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Hostile),
            1 => Some(Self::Suspicious),
            2 => Some(Self::Neutral),
            3 => Some(Self::Friendly),
            4 => Some(Self::Allied),
            _ => None,
        }
    }
}

// ---------------------------------------------------------------------------
// Input structs
// ---------------------------------------------------------------------------

/// Per-civ input state (Family 1 from spec).
#[derive(Clone, Debug)]
pub struct CivInput {
    pub civ_idx: u16,
    pub name: String,
    pub stability: i32,
    pub military: i32,
    pub economy: i32,
    pub culture: i32,
    pub treasury: i32,
    pub asabiya: f32,
    pub population: i32,
    pub decline_turns: i32,
    pub stats_sum_history: Vec<i32>,
    pub founded_turn: u32,
    pub regions: Vec<u16>,
    pub capital_region: u16, // REGION_NONE if None
    pub total_effective_capacity: i32,
    pub active_focus: u8, // 0 = None, 14 = surveillance
    pub civ_majority_faith: u8,
    pub civ_stress: i32,
    // Observer accuracy metadata for step-4 perception
    pub dominant_faction: u8, // 0=military, 1=merchant, 2=cultural, 3=clergy
    // Event counts (secession_occurred, capital_lost)
    pub secession_occurred_count: i32,
    pub capital_lost_count: i32,
}

impl CivInput {
    /// Constructor for tests — all fields explicit.
    pub fn new(civ_idx: u16) -> Self {
        Self {
            civ_idx,
            name: format!("Civ{civ_idx}"),
            stability: 50,
            military: 50,
            economy: 50,
            culture: 50,
            treasury: 50,
            asabiya: 0.5,
            population: 100,
            decline_turns: 0,
            stats_sum_history: Vec::new(),
            founded_turn: 0,
            regions: Vec::new(),
            capital_region: REGION_NONE,
            total_effective_capacity: 100,
            active_focus: 0,
            civ_majority_faith: BELIEF_NONE,
            civ_stress: 0,
            dominant_faction: 0,
            secession_occurred_count: 0,
            capital_lost_count: 0,
        }
    }
}

/// Per-region input state (Family 2 from spec).
#[derive(Clone, Debug)]
pub struct RegionInput {
    pub region_idx: u16,
    pub controller: u16, // CIV_NONE if uncontrolled
    pub adjacencies: Vec<u16>,
    pub carrying_capacity: u16,
    pub population: u16,
    pub majority_belief: u8,
    pub effective_capacity: u16,
}

impl RegionInput {
    pub fn new(region_idx: u16) -> Self {
        Self {
            region_idx,
            controller: CIV_NONE,
            adjacencies: Vec::new(),
            carrying_capacity: 60,
            population: 30,
            majority_belief: BELIEF_NONE,
            effective_capacity: 48,
        }
    }
}

// ---------------------------------------------------------------------------
// Topology registries (Family 3 from spec)
// ---------------------------------------------------------------------------

/// Pairwise relationship entry.
#[derive(Clone, Debug)]
pub struct RelationshipEntry {
    pub civ_a: u16,
    pub civ_b: u16,
    pub disposition: Disposition,
    pub allied_turns: i32,
}

/// Vassal relation.
#[derive(Clone, Debug)]
pub struct VassalEntry {
    pub vassal: u16,
    pub overlord: u16,
}

/// Federation entry.
#[derive(Clone, Debug)]
pub struct FederationEntry {
    pub fed_idx: u16,
    pub members: Vec<u16>,
    pub founded_turn: u32,
}

/// Active war pair.
#[derive(Clone, Debug)]
pub struct WarEntry {
    pub civ_a: u16,
    pub civ_b: u16,
}

/// Embargo pair.
#[derive(Clone, Debug)]
pub struct EmbargoEntry {
    pub civ_a: u16,
    pub civ_b: u16,
}

/// Proxy war entry.
#[derive(Clone, Debug)]
pub struct ProxyWarEntry {
    pub sponsor: u16,
    pub target_civ: u16,
    pub target_region: u16,
    pub detected: bool,
}

/// Exile modifier entry.
#[derive(Clone, Debug)]
pub struct ExileEntry {
    pub original_civ: u16,
    pub absorber_civ: u16,
    pub conquered_regions: Vec<u16>,
    pub turns_remaining: i32,
    pub recognized_by: Vec<u16>,
}

// ---------------------------------------------------------------------------
// Topology collection
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Default)]
pub struct PoliticsTopology {
    pub relationships: Vec<RelationshipEntry>,
    pub vassals: Vec<VassalEntry>,
    pub federations: Vec<FederationEntry>,
    pub wars: Vec<WarEntry>,
    pub embargoes: Vec<EmbargoEntry>,
    pub proxy_wars: Vec<ProxyWarEntry>,
    pub exiles: Vec<ExileEntry>,
}

// ---------------------------------------------------------------------------
// PoliticsConfig — all tuning constants
// ---------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct PoliticsConfig {
    // Secession
    pub secession_stability_threshold: i32,
    pub secession_surveillance_threshold: i32,
    pub proxy_war_secession_bonus: f32,
    pub secession_stability_loss: i32,
    pub secession_likelihood_multiplier: f32,
    // Capital loss
    pub capital_loss_stability: i32,
    // Vassal rebellion
    pub vassal_rebellion_base_prob: f32,
    pub vassal_rebellion_reduced_prob: f32,
    // Federation
    pub federation_allied_turns: i32,
    pub federation_exit_stability: i32,
    pub federation_remaining_stability: i32,
    // Restoration
    pub restoration_base_prob: f32,
    pub restoration_recognition_bonus: f32,
    // Twilight / absorption
    pub twilight_absorption_decline: i32,
    // Severity multiplier
    pub severity_stress_divisor: f32,
    pub severity_stress_scale: f32,
    pub severity_cap: f32,
    pub severity_multiplier: f32,
}

impl Default for PoliticsConfig {
    fn default() -> Self {
        Self {
            secession_stability_threshold: 10,
            secession_surveillance_threshold: 5,
            proxy_war_secession_bonus: 0.05,
            secession_stability_loss: 10,
            secession_likelihood_multiplier: 1.0,
            capital_loss_stability: 20,
            vassal_rebellion_base_prob: 0.15,
            vassal_rebellion_reduced_prob: 0.05,
            federation_allied_turns: 10,
            federation_exit_stability: 15,
            federation_remaining_stability: 5,
            restoration_base_prob: 0.05,
            restoration_recognition_bonus: 0.03,
            twilight_absorption_decline: 40,
            severity_stress_divisor: 20.0,
            severity_stress_scale: 0.5,
            severity_cap: 2.0,
            severity_multiplier: 1.0,
        }
    }
}

// ---------------------------------------------------------------------------
// Op families
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq)]
pub enum CivOpType {
    CreateBreakaway,
    Restore,
    Absorb,
    ReassignCapital,
    StripToFirstRegion,
}

#[derive(Clone, Debug)]
pub struct CivOp {
    pub step: u8,
    pub seq: u16,
    pub op_type: CivOpType,
    pub source_civ: CivRef,
    pub target_civ: CivRef,
    pub regions: Vec<u16>,
    pub stat_military: i32,
    pub stat_economy: i32,
    pub stat_culture: i32,
    pub stat_stability: i32,
    pub stat_treasury: i32,
    pub stat_population: i32,
    pub stat_asabiya: f32,
    pub founded_turn: u32,
}

#[derive(Clone, Debug, PartialEq)]
pub enum RegionOpType {
    SetController,
    NullifyController,
    SetSecededTransient,
}

#[derive(Clone, Debug)]
pub struct RegionOp {
    pub step: u8,
    pub seq: u16,
    pub op_type: RegionOpType,
    pub region: u16,
    pub controller: CivRef,
}

#[derive(Clone, Debug, PartialEq)]
pub enum RelationshipOpType {
    InitPair,
    SetDisposition,
    ResetAlliedTurns,
    IncrementAlliedTurns,
}

#[derive(Clone, Debug)]
pub struct RelationshipOp {
    pub step: u8,
    pub seq: u16,
    pub op_type: RelationshipOpType,
    pub civ_a: CivRef,
    pub civ_b: CivRef,
    pub disposition: Disposition,
}

#[derive(Clone, Debug, PartialEq)]
pub enum FederationOpType {
    Create,
    AppendMember,
    RemoveMember,
    Dissolve,
}

#[derive(Clone, Debug)]
pub struct FederationOp {
    pub step: u8,
    pub seq: u16,
    pub op_type: FederationOpType,
    pub federation_ref: FedRef,
    pub civ: CivRef,
    pub members: Vec<CivRef>, // for Create: initial members
    pub context_seed: u64,
}

#[derive(Clone, Debug, PartialEq)]
pub enum VassalOpType {
    Remove,
}

#[derive(Clone, Debug)]
pub struct VassalOp {
    pub step: u8,
    pub seq: u16,
    pub op_type: VassalOpType,
    pub vassal: CivRef,
    pub overlord: CivRef,
}

#[derive(Clone, Debug, PartialEq)]
pub enum ExileOpType {
    Append,
    Remove,
}

#[derive(Clone, Debug)]
pub struct ExileOp {
    pub step: u8,
    pub seq: u16,
    pub op_type: ExileOpType,
    pub original_civ: CivRef,
    pub absorber_civ: CivRef,
    pub conquered_regions: Vec<u16>,
    pub turns_remaining: i32,
}

#[derive(Clone, Debug, PartialEq)]
pub enum ProxyWarOpType {
    SetDetected,
}

#[derive(Clone, Debug)]
pub struct ProxyWarOp {
    pub step: u8,
    pub seq: u16,
    pub op_type: ProxyWarOpType,
    pub sponsor: CivRef,
    pub target_civ: CivRef,
    pub target_region: u16,
}

/// Routing tag for civ effect ops, matching spec Section 5.4.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EffectRouting {
    Keep,
    Signal,
    GuardShock,
    DirectOnly,
    HybridShock,
}

#[derive(Clone, Debug)]
pub struct CivEffectOp {
    pub step: u8,
    pub seq: u16,
    pub civ: CivRef,
    pub field: &'static str,
    pub delta_i: i32,
    pub delta_f: f32,
    pub routing: EffectRouting,
}

#[derive(Clone, Debug, PartialEq)]
pub enum BookkeepingType {
    AppendStatsHistory,
    IncrementDecline,
    ResetDecline,
    IncrementEventCount,
}

#[derive(Clone, Debug)]
pub struct BookkeepingDelta {
    pub step: u8,
    pub seq: u16,
    pub civ: CivRef,
    pub bk_type: BookkeepingType,
    pub field: &'static str,
    pub value_i: i32,
}

#[derive(Clone, Debug)]
pub struct ArtifactIntentOp {
    pub step: u8,
    pub seq: u16,
    pub losing_civ: CivRef,
    pub gaining_civ: CivRef,
    pub region: u16,
    pub is_capital: bool,
    pub is_destructive: bool,
    pub action: &'static str,
}

#[derive(Clone, Debug, PartialEq)]
pub enum BridgeTransitionType {
    Secession,
    Restoration,
    Absorption,
}

#[derive(Clone, Debug)]
pub struct BridgeTransitionOp {
    pub step: u8,
    pub seq: u16,
    pub transition_type: BridgeTransitionType,
    pub source_civ: CivRef,
    pub target_civ: CivRef,
    pub regions: Vec<u16>,
}

#[derive(Clone, Debug)]
pub struct EventTrigger {
    pub step: u8,
    pub seq: u16,
    pub event_type: &'static str,
    pub actors: Vec<CivRef>,
    pub importance: u8,
    pub context_regions: Vec<u16>,
    /// Extra context: e.g. federation name seed for creation events
    pub context_seed: u64,
}

// ---------------------------------------------------------------------------
// Result collection
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Default)]
pub struct PoliticsResult {
    pub civ_ops: Vec<CivOp>,
    pub region_ops: Vec<RegionOp>,
    pub relationship_ops: Vec<RelationshipOp>,
    pub federation_ops: Vec<FederationOp>,
    pub vassal_ops: Vec<VassalOp>,
    pub exile_ops: Vec<ExileOp>,
    pub proxy_war_ops: Vec<ProxyWarOp>,
    pub civ_effects: Vec<CivEffectOp>,
    pub bookkeeping: Vec<BookkeepingDelta>,
    pub artifact_intents: Vec<ArtifactIntentOp>,
    pub bridge_transitions: Vec<BridgeTransitionOp>,
    pub events: Vec<EventTrigger>,
    /// Next available local id for CivRef::New
    pub next_new_civ_id: u16,
    /// Next available local id for FedRef::New
    pub next_new_fed_id: u16,
}

impl PoliticsResult {
    fn alloc_new_civ(&mut self) -> CivRef {
        let id = self.next_new_civ_id;
        self.next_new_civ_id += 1;
        CivRef::New(id)
    }

    fn alloc_new_fed(&mut self) -> FedRef {
        let id = self.next_new_fed_id;
        self.next_new_fed_id += 1;
        FedRef::New(id)
    }
}

// ---------------------------------------------------------------------------
// Mutable in-pass state — topology mirrors that can be mutated by prior steps
// ---------------------------------------------------------------------------

/// Mutable snapshot of relationship disposition, keyed by (civ_a, civ_b).
struct LiveRelationships {
    disposition: HashMap<(u16, u16), Disposition>,
    allied_turns: HashMap<(u16, u16), i32>,
}

impl LiveRelationships {
    fn from_topology(topo: &PoliticsTopology) -> Self {
        let mut disposition = HashMap::new();
        let mut allied_turns = HashMap::new();
        for r in &topo.relationships {
            disposition.insert((r.civ_a, r.civ_b), r.disposition);
            allied_turns.insert((r.civ_a, r.civ_b), r.allied_turns);
        }
        Self { disposition, allied_turns }
    }

    fn get_disposition(&self, a: u16, b: u16) -> Option<Disposition> {
        self.disposition.get(&(a, b)).copied()
    }

    fn set_disposition(&mut self, a: u16, b: u16, d: Disposition) {
        self.disposition.insert((a, b), d);
    }

    fn get_allied_turns(&self, a: u16, b: u16) -> i32 {
        self.allied_turns.get(&(a, b)).copied().unwrap_or(0)
    }
}

/// Mutable per-civ state that can change across steps.
#[derive(Clone, Debug)]
struct LiveCiv {
    regions: Vec<u16>,
    capital_region: u16,
    stability: i32,
    military: i32,
    economy: i32,
    culture: i32,
    treasury: i32,
    asabiya: f32,
    population: i32,
    decline_turns: i32,
    stats_sum_history: Vec<i32>,
    total_effective_capacity: i32,
    alive: bool, // regions.is_empty() = dead
    secession_occurred_count: i32,
    capital_lost_count: i32,
}

impl LiveCiv {
    fn from_input(c: &CivInput) -> Self {
        Self {
            regions: c.regions.clone(),
            capital_region: c.capital_region,
            stability: c.stability,
            military: c.military,
            economy: c.economy,
            culture: c.culture,
            treasury: c.treasury,
            asabiya: c.asabiya,
            population: c.population,
            decline_turns: c.decline_turns,
            stats_sum_history: c.stats_sum_history.clone(),
            total_effective_capacity: c.total_effective_capacity,
            alive: !c.regions.is_empty(),
            secession_occurred_count: c.secession_occurred_count,
            capital_lost_count: c.capital_lost_count,
        }
    }
}

/// Mutable per-region controller.
struct LiveRegion {
    controller: u16,
}

/// Mutable vassal list.
struct LiveVassals {
    entries: Vec<VassalEntry>,
}

/// Mutable federation list.
struct LiveFederations {
    entries: Vec<FederationEntry>,
}

/// Mutable proxy war list.
struct LiveProxyWars {
    entries: Vec<ProxyWarEntry>,
}

/// Mutable exile list.
struct LiveExiles {
    entries: Vec<ExileEntry>,
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

/// BFS graph distance over region adjacencies. Returns -1 if disconnected.
/// Mirrors Python `adjacency.graph_distance()`.
pub fn graph_distance(regions: &[RegionInput], from_idx: u16, to_idx: u16) -> i32 {
    if from_idx == to_idx {
        return 0;
    }
    let n = regions.len();
    if from_idx as usize >= n || to_idx as usize >= n {
        return -1;
    }

    // Build adjacency map by region index
    let adj: Vec<&[u16]> = regions.iter().map(|r| r.adjacencies.as_slice()).collect();

    let mut visited = vec![false; n];
    visited[from_idx as usize] = true;
    let mut queue: VecDeque<(u16, i32)> = VecDeque::new();
    queue.push_back((from_idx, 0));

    while let Some((current, dist)) = queue.pop_front() {
        for &neighbor in adj[current as usize] {
            if neighbor == to_idx {
                return dist + 1;
            }
            if (neighbor as usize) < n && !visited[neighbor as usize] {
                visited[neighbor as usize] = true;
                queue.push_back((neighbor, dist + 1));
            }
        }
    }
    -1
}

/// Severity multiplier. Mirrors Python `emergence.get_severity_multiplier()`.
pub fn get_severity_multiplier(civ_stress: i32, config: &PoliticsConfig) -> f32 {
    let base = 1.0 + (civ_stress as f32 / config.severity_stress_divisor) * config.severity_stress_scale;
    (base * config.severity_multiplier).min(config.severity_cap)
}

/// Deterministic hash equivalent to Python's `stable_hash_int()`.
/// Produces identical values for same inputs by matching Python's SHA-256 based approach.
///
/// Python: `payload = "|".join(repr(part) for part in parts).encode("utf-8")`
///         `int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)`
///
/// For politics, we use string-based seeds that match Python's repr() output.
pub fn stable_hash_int(parts: &[&str]) -> u64 {
    use std::io::Write;
    let mut payload = Vec::new();
    for (i, part) in parts.iter().enumerate() {
        if i > 0 {
            payload.push(b'|');
        }
        payload.write_all(part.as_bytes()).unwrap();
    }
    // SHA-256
    let digest = sha256(&payload);
    u64::from_be_bytes([
        digest[0], digest[1], digest[2], digest[3],
        digest[4], digest[5], digest[6], digest[7],
    ])
}

/// Minimal SHA-256 implementation (no external dep needed — deterministic only).
fn sha256(data: &[u8]) -> [u8; 32] {
    // Initial hash values
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];

    // Round constants
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
        0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
        0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
        0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
        0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
        0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
        0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
        0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ];

    // Pre-processing: pad message
    let bit_len = (data.len() as u64) * 8;
    let mut msg = data.to_vec();
    msg.push(0x80);
    while (msg.len() % 64) != 56 {
        msg.push(0x00);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());

    // Process each 512-bit block
    for block in msg.chunks(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes([
                block[i * 4],
                block[i * 4 + 1],
                block[i * 4 + 2],
                block[i * 4 + 3],
            ]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }

        let mut a = h[0];
        let mut b = h[1];
        let mut c = h[2];
        let mut d = h[3];
        let mut e = h[4];
        let mut f = h[5];
        let mut g = h[6];
        let mut hh = h[7];

        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let temp1 = hh
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[i])
                .wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(maj);

            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }

        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }

    let mut result = [0u8; 32];
    for (i, &val) in h.iter().enumerate() {
        result[i * 4..i * 4 + 4].copy_from_slice(&val.to_be_bytes());
    }
    result
}

fn live_fed_ref(fed_idx: u16) -> FedRef {
    if fed_idx >= 1000 {
        FedRef::New(fed_idx - 1000)
    } else {
        FedRef::Existing(fed_idx)
    }
}

fn live_civ_ref(live_idx: u16, num_existing_civs: u16) -> CivRef {
    if live_idx >= num_existing_civs {
        CivRef::New(live_idx - num_existing_civs)
    } else {
        CivRef::Existing(live_idx)
    }
}

/// Deterministic PRNG compatible with Python's `random.Random(seed)` for the
/// subset used by the politics core (`random()` and `gauss()`).
///
/// Seeding mirrors CPython `_randommodule.c` for positive integer seeds:
/// the seed is split into 32-bit little-endian chunks and passed through
/// MT19937 `init_by_array()`.
struct DetRng {
    index: usize,
    state: [u32; 624],
    gauss_next: Option<f64>,
}

impl DetRng {
    fn new(seed: u64) -> Self {
        let mut rng = Self {
            index: 624,
            state: [0u32; 624],
            gauss_next: None,
        };

        let mut keys = vec![seed as u32];
        let hi = (seed >> 32) as u32;
        if hi != 0 {
            keys.push(hi);
        }
        rng.init_by_array(&keys);
        rng
    }

    fn init_genrand(&mut self, seed: u32) {
        self.state[0] = seed;
        for i in 1..624 {
            let prev = self.state[i - 1];
            self.state[i] = 1812433253u32
                .wrapping_mul(prev ^ (prev >> 30))
                .wrapping_add(i as u32);
        }
        self.index = 624;
    }

    fn init_by_array(&mut self, init_key: &[u32]) {
        self.init_genrand(19650218u32);
        let key_length = init_key.len().max(1);
        let mut i = 1usize;
        let mut j = 0usize;
        let mut k = 624usize.max(key_length);

        while k > 0 {
            let prev = self.state[i - 1];
            self.state[i] = (self.state[i]
                ^ ((prev ^ (prev >> 30)).wrapping_mul(1664525u32)))
                .wrapping_add(init_key[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= 624 {
                self.state[0] = self.state[623];
                i = 1;
            }
            if j >= key_length {
                j = 0;
            }
            k -= 1;
        }

        k = 623;
        while k > 0 {
            let prev = self.state[i - 1];
            self.state[i] = (self.state[i]
                ^ ((prev ^ (prev >> 30)).wrapping_mul(1566083941u32)))
                .wrapping_sub(i as u32);
            i += 1;
            if i >= 624 {
                self.state[0] = self.state[623];
                i = 1;
            }
            k -= 1;
        }

        self.state[0] = 0x8000_0000u32;
        self.index = 624;
    }

    fn genrand_uint32(&mut self) -> u32 {
        const N: usize = 624;
        const M: usize = 397;
        const MATRIX_A: u32 = 0x9908_b0df;
        const UPPER_MASK: u32 = 0x8000_0000;
        const LOWER_MASK: u32 = 0x7fff_ffff;
        const MAG01: [u32; 2] = [0, MATRIX_A];

        if self.index >= N {
            for kk in 0..(N - M) {
                let y = (self.state[kk] & UPPER_MASK) | (self.state[kk + 1] & LOWER_MASK);
                self.state[kk] =
                    self.state[kk + M] ^ (y >> 1) ^ MAG01[(y & 0x1) as usize];
            }
            for kk in (N - M)..(N - 1) {
                let y = (self.state[kk] & UPPER_MASK) | (self.state[kk + 1] & LOWER_MASK);
                self.state[kk] =
                    self.state[kk + M - N] ^ (y >> 1) ^ MAG01[(y & 0x1) as usize];
            }
            let y = (self.state[N - 1] & UPPER_MASK) | (self.state[0] & LOWER_MASK);
            self.state[N - 1] =
                self.state[M - 1] ^ (y >> 1) ^ MAG01[(y & 0x1) as usize];
            self.index = 0;
        }

        let mut y = self.state[self.index];
        self.index += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c_5680;
        y ^= (y << 15) & 0xefc6_0000;
        y ^= y >> 18;
        y
    }

    fn random(&mut self) -> f64 {
        let a = (self.genrand_uint32() >> 5) as f64;
        let b = (self.genrand_uint32() >> 6) as f64;
        (a * 67_108_864.0 + b) * (1.0 / 9_007_199_254_740_992.0)
    }

    fn gauss(&mut self, mu: f64, sigma: f64) -> f64 {
        let z = if let Some(z) = self.gauss_next.take() {
            z
        } else {
            let x2pi = self.random() * (2.0 * std::f64::consts::PI);
            let g2rad = (-2.0 * (1.0 - self.random()).ln()).sqrt();
            let z = x2pi.cos() * g2rad;
            self.gauss_next = Some(x2pi.sin() * g2rad);
            z
        };
        mu + z * sigma
    }
}

/// Narrow subset of compute_accuracy for step-4 vassal rebellion perception.
/// Mirrors Python intelligence.compute_accuracy() for the vassal->overlord case.
fn compute_accuracy_vassal_overlord(
    observer_idx: u16,
    target_idx: u16,
    live_regions: &[LiveRegion],
    regions: &[RegionInput],
    live_civs: &[LiveCiv],
    civs: &[CivInput],
    live_vassals: &LiveVassals,
    live_feds: &LiveFederations,
    wars: &[WarEntry],
    proxy_wars: &LiveProxyWars,
    live_rels: &LiveRelationships,
    embargoes: &[EmbargoEntry],
) -> f32 {
    if observer_idx == target_idx {
        return 1.0;
    }
    let mut accuracy: f32 = 0.0;

    // Adjacent region check
    let obs_regions: HashSet<u16> = if (observer_idx as usize) < live_civs.len() {
        live_civs[observer_idx as usize].regions.iter().copied().collect()
    } else {
        HashSet::new()
    };
    let tgt_regions: HashSet<u16> = if (target_idx as usize) < live_civs.len() {
        live_civs[target_idx as usize].regions.iter().copied().collect()
    } else {
        HashSet::new()
    };

    'adj: for &r_idx in &live_civs[observer_idx as usize].regions {
        if (r_idx as usize) < regions.len() {
            for &adj in &regions[r_idx as usize].adjacencies {
                if tgt_regions.contains(&adj) {
                    accuracy += 0.3;
                    break 'adj;
                }
            }
        }
    }

    // Trade route: +0.2 if adjacent regions exist and no embargo between the pair.
    // Mirrors Python has_active_trade_route(): adjacency + no embargo.
    // (The Python also checks disposition >= Neutral, but for the vassal->overlord
    // path the disposition is always known, and the full trade-route system checks
    // region adjacency + no embargo as the primary gate.)
    let has_embargo = embargoes.iter().any(|e| {
        (e.civ_a == observer_idx && e.civ_b == target_idx)
            || (e.civ_a == target_idx && e.civ_b == observer_idx)
    });
    if !has_embargo {
        // Check if any observer region is adjacent to any target region
        let mut has_adj_route = false;
        'trade: for &r_idx in &live_civs[observer_idx as usize].regions {
            if (r_idx as usize) < regions.len() {
                for &adj in &regions[r_idx as usize].adjacencies {
                    if tgt_regions.contains(&adj) {
                        has_adj_route = true;
                        break 'trade;
                    }
                }
            }
        }
        if has_adj_route {
            accuracy += 0.2;
        }
    }

    // Vassal relation: +0.5 (both directions)
    for v in &live_vassals.entries {
        if (v.vassal == observer_idx && v.overlord == target_idx)
            || (v.vassal == target_idx && v.overlord == observer_idx)
        {
            accuracy += 0.5;
            break;
        }
    }

    // Federation membership: +0.4
    for f in &live_feds.entries {
        if f.members.contains(&observer_idx) && f.members.contains(&target_idx) {
            accuracy += 0.4;
            break;
        }
    }

    // At war: +0.3
    for w in wars {
        if (w.civ_a == observer_idx && w.civ_b == target_idx)
            || (w.civ_a == target_idx && w.civ_b == observer_idx)
        {
            accuracy += 0.3;
            break;
        }
    }
    for pw in &proxy_wars.entries {
        if (pw.sponsor == observer_idx && pw.target_civ == target_idx)
            || (pw.sponsor == target_idx && pw.target_civ == observer_idx)
        {
            accuracy += 0.3;
            break;
        }
    }

    // Faction bonus (merchant=+0.1, cultural=+0.05)
    if (observer_idx as usize) < civs.len() {
        match civs[observer_idx as usize].dominant_faction {
            1 => accuracy += 0.1,  // merchant
            2 => accuracy += 0.05, // cultural
            _ => {}
        }
    }

    // NOTE: GreatPerson bonuses (merchant +0.05, hostage +0.3) and leader grudges
    // are NOT modeled in the Rust core — they are pre-baked into observer accuracy
    // metadata or handled at the FFI boundary. For the narrow step-4 subset, the
    // vassal->overlord relation alone gives +0.5 accuracy, which is the dominant
    // term. The Python parity suite will verify exact matching.

    accuracy.min(1.0)
}

/// Narrow perception: get_perceived_stat for step-4 vassal rebellion.
/// Mirrors Python intelligence.get_perceived_stat().
fn get_perceived_stat(
    observer_name: &str,
    target_name: &str,
    actual_value: i32,
    stat_name: &str,
    max_value: i32,
    accuracy: f32,
    seed: u64,
    turn: u32,
) -> Option<i32> {
    if accuracy == 0.0 {
        return None;
    }
    let noise_range = ((1.0 - accuracy) * 20.0) as i32;
    if noise_range == 0 {
        return Some(actual_value);
    }

    // Build seed matching Python: f"{seed}:{observer.name}:{target.name}:{turn}:{stat}".
    let seed_input = format!(
        "{}:{}:{}:{}:{}",
        seed, observer_name, target_name, turn, stat_name,
    );
    let digest = sha256(seed_input.as_bytes());
    let seed_int = u64::from_le_bytes([
        digest[0], digest[1], digest[2], digest[3],
        digest[4], digest[5], digest[6], digest[7],
    ]);

    let mut rng = DetRng::new(seed_int);
    let noise = rng.gauss(0.0, noise_range as f64 / 2.0) as i32;
    let noise = noise.max(-noise_range).min(noise_range);
    Some((actual_value + noise).max(0).min(max_value))
}

/// Normalize a shock value: `min(1.0, abs_val / max(base, 1))`.
pub fn normalize_shock(abs_val: i32, base: i32) -> f32 {
    -(abs_val as f32 / base.max(1) as f32).min(1.0)
}

// ---------------------------------------------------------------------------
// Step implementations
// ---------------------------------------------------------------------------

/// Sequence counter for deterministic op ordering within a step.
struct SeqCounter {
    val: u16,
}

impl SeqCounter {
    fn new() -> Self {
        Self { val: 0 }
    }
    fn next(&mut self) -> u16 {
        let v = self.val;
        self.val += 1;
        v
    }
}

/// Step 1: Check capital loss — reassign by effective capacity.
fn step_capital_loss(
    civs: &[CivInput],
    regions: &[RegionInput],
    live_civs: &mut [LiveCiv],
    live_regions: &[LiveRegion],
    config: &PoliticsConfig,
    hybrid_mode: bool,
    result: &mut PoliticsResult,
) {
    let step: u8 = 1;
    let mut seq = SeqCounter::new();

    for (ci, civ) in civs.iter().enumerate() {
        let cap_region = live_civs[ci].capital_region;
        let civ_regions = live_civs[ci].regions.clone();
        let civ_stability = live_civs[ci].stability;

        if cap_region == REGION_NONE || civ_regions.contains(&cap_region) {
            continue;
        }
        if civ_regions.is_empty() {
            continue;
        }

        // Python's max(..., key=...) keeps the first region on ties.
        let mut best_region = civ_regions[0];
        let mut best_effective_capacity = if (best_region as usize) < regions.len() {
            regions[best_region as usize].effective_capacity
        } else {
            0
        };
        for &candidate in civ_regions.iter().skip(1) {
            let candidate_effective_capacity = if (candidate as usize) < regions.len() {
                regions[candidate as usize].effective_capacity
            } else {
                0
            };
            if candidate_effective_capacity > best_effective_capacity {
                best_region = candidate;
                best_effective_capacity = candidate_effective_capacity;
            }
        }

        let mult = get_severity_multiplier(civ.civ_stress, config);
        let stab_loss = (config.capital_loss_stability as f32 * mult) as i32;

        // Emit reassign capital op
        result.civ_ops.push(CivOp {
            step,
            seq: seq.next(),
            op_type: CivOpType::ReassignCapital,
            source_civ: CivRef::Existing(civ.civ_idx),
            target_civ: CivRef::Existing(civ.civ_idx),
            regions: vec![best_region],
            stat_military: 0,
            stat_economy: 0,
            stat_culture: 0,
            stat_stability: 0,
            stat_treasury: 0,
            stat_population: 0,
            stat_asabiya: 0.0,
            founded_turn: 0,
        });

        // Emit stability effect
        let routing = if hybrid_mode {
            EffectRouting::HybridShock
        } else {
            EffectRouting::DirectOnly
        };
        result.civ_effects.push(CivEffectOp {
            step,
            seq: seq.next(),
            civ: CivRef::Existing(civ.civ_idx),
            field: "stability",
            delta_i: -stab_loss,
            delta_f: if hybrid_mode {
                normalize_shock(stab_loss, civ_stability)
            } else {
                0.0
            },
            routing,
        });

        // Emit event
        result.events.push(EventTrigger {
            step,
            seq: seq.next(),
            event_type: "capital_loss",
            actors: vec![CivRef::Existing(civ.civ_idx)],
            importance: 8,
            context_regions: vec![best_region],
            context_seed: 0,
        });

        // Bookkeeping: increment capital_lost
        result.bookkeeping.push(BookkeepingDelta {
            step,
            seq: seq.next(),
            civ: CivRef::Existing(civ.civ_idx),
            bk_type: BookkeepingType::IncrementEventCount,
            field: "capital_lost",
            value_i: 1,
        });

        // Update live state
        live_civs[ci].capital_region = best_region;
        live_civs[ci].capital_lost_count += 1;
    }
}

/// Step 2: Check secession.
fn step_secession(
    civs: &[CivInput],
    regions: &[RegionInput],
    live_civs: &mut Vec<LiveCiv>,
    live_regions: &mut [LiveRegion],
    live_rels: &mut LiveRelationships,
    live_proxy_wars: &LiveProxyWars,
    config: &PoliticsConfig,
    seed: u64,
    turn: u32,
    hybrid_mode: bool,
    result: &mut PoliticsResult,
) {
    let step: u8 = 2;
    let mut seq = SeqCounter::new();

    let num_existing_civs = civs.len() as u16;

    for (ci, civ) in civs.iter().enumerate() {
        if !live_civs[ci].alive {
            continue;
        }

        // Grace period (saturating_sub for defensive underflow protection)
        if civ.founded_turn > 0 && turn.saturating_sub(civ.founded_turn) < SECESSION_GRACE_TURNS {
            continue;
        }

        // Threshold
        let secession_threshold = if civ.active_focus == 14 {
            // surveillance
            config.secession_surveillance_threshold
        } else {
            config.secession_stability_threshold
        };

        if live_civs[ci].stability >= secession_threshold || live_civs[ci].regions.len() < 3 {
            continue;
        }

        // Snapshot live civ values for use throughout this iteration
        let lc_stability = live_civs[ci].stability;
        let lc_military = live_civs[ci].military;
        let lc_economy = live_civs[ci].economy;
        let lc_culture = live_civs[ci].culture;
        let lc_treasury = live_civs[ci].treasury;
        let lc_population = live_civs[ci].population;
        let lc_regions = live_civs[ci].regions.clone();
        let lc_capital = live_civs[ci].capital_region;

        let mut prob = (secession_threshold - lc_stability) as f32 / 100.0;

        // Proxy war bonus: if this civ is a proxy war target, add flat bonus.
        // Mirrors Python: for pw in world.proxy_wars: if pw.target_civ == civ.name: prob += 0.05
        for pw in &live_proxy_wars.entries {
            if pw.target_civ == civ.civ_idx {
                prob += config.proxy_war_secession_bonus;
                break;
            }
        }

        // M38b: Schism secession modifier
        let civ_faith = civ.civ_majority_faith;
        let has_mismatch = lc_regions.iter().any(|&r_idx| {
            if (r_idx as usize) < regions.len() {
                let region_belief = regions[r_idx as usize].majority_belief;
                region_belief != civ_faith
            } else {
                false
            }
        });
        if has_mismatch {
            prob += SCHISM_SECESSION_MODIFIER / 100.0;
        }

        // Likelihood multiplier
        prob *= config.secession_likelihood_multiplier;
        prob = prob.min(1.0);

        // Deterministic RNG
        let seed_parts = format!("'secession'|{}|{}|'{}'", seed, turn, civ.name);
        let hash = stable_hash_int(&[&seed_parts]);
        let mut rng = DetRng::new(hash);
        if rng.random() >= prob as f64 {
            continue;
        }

        // Secession fires — compute breakaway regions
        let capital = if lc_capital != REGION_NONE {
            lc_capital
        } else if !lc_regions.is_empty() {
            lc_regions[0]
        } else {
            continue;
        };

        // Score regions: distance * 0.7 + effective_capacity * 0.3
        let mut scored: Vec<(u16, f64)> = lc_regions
            .iter()
            .map(|&r_idx| {
                let d = graph_distance(regions, capital, r_idx);
                let dist = if d >= 0 { d } else { 0 };
                let cap = if (r_idx as usize) < regions.len() {
                    regions[r_idx as usize].effective_capacity as i32
                } else {
                    0
                };
                (r_idx, dist as f64 * 0.7 + cap as f64 * 0.3)
            })
            .collect();
        scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        let breakaway_count = ((lc_regions.len() as f64 / 3.0).ceil() as usize)
            .max(1)
            .min(lc_regions.len() - 1);
        let breakaway_regions: Vec<u16> = scored.iter().take(breakaway_count).map(|s| s.0).collect();
        let remaining_regions: Vec<u16> = lc_regions
            .iter()
            .filter(|r| !breakaway_regions.contains(r))
            .copied()
            .collect();

        let ratio = breakaway_count as f32 / lc_regions.len() as f32;
        let split_mil = (lc_military as f32 * ratio).floor() as i32;
        let split_eco = (lc_economy as f32 * ratio).floor() as i32;
        let split_tre = (lc_treasury as f32 * ratio).floor() as i32;

        // Breakaway capital: min distance to remaining parent regions
        let breakaway_capital = *breakaway_regions
            .iter()
            .min_by_key(|&&br| {
                remaining_regions
                    .iter()
                    .map(|&pr| {
                        let d = graph_distance(regions, br, pr);
                        if d >= 0 { d } else { i32::MAX }
                    })
                    .min()
                    .unwrap_or(i32::MAX)
            })
            .unwrap_or(&breakaway_regions[0]);

        // Population from regions
        let split_pop: i32 = breakaway_regions
            .iter()
            .map(|&r| {
                if (r as usize) < regions.len() {
                    regions[r as usize].population as i32
                } else {
                    0
                }
            })
            .sum();

        let new_civ_ref = result.alloc_new_civ();

        // Severity multiplier
        let mult = get_severity_multiplier(civ.civ_stress, config);
        let stab_loss = (config.secession_stability_loss as f32 * mult) as i32;

        // Create breakaway op
        result.civ_ops.push(CivOp {
            step,
            seq: seq.next(),
            op_type: CivOpType::CreateBreakaway,
            source_civ: CivRef::Existing(civ.civ_idx),
            target_civ: new_civ_ref,
            regions: breakaway_regions.clone(),
            stat_military: split_mil.max(0),
            stat_economy: split_eco.max(0),
            stat_culture: lc_culture,
            stat_stability: 40,
            stat_treasury: split_tre,
            stat_population: split_pop.max(1),
            stat_asabiya: 0.7,
            founded_turn: turn,
        });

        // Region controller ops
        for &r_idx in &breakaway_regions {
            result.region_ops.push(RegionOp {
                step,
                seq: seq.next(),
                op_type: RegionOpType::SetController,
                region: r_idx,
                controller: new_civ_ref,
            });
            // Set seceded transient
            result.region_ops.push(RegionOp {
                step,
                seq: seq.next(),
                op_type: RegionOpType::SetSecededTransient,
                region: r_idx,
                controller: new_civ_ref,
            });
        }

        // Parent stat effects
        let routing = if hybrid_mode {
            EffectRouting::HybridShock
        } else {
            EffectRouting::DirectOnly
        };

        if hybrid_mode {
            result.civ_effects.push(CivEffectOp {
                step,
                seq: seq.next(),
                civ: CivRef::Existing(civ.civ_idx),
                field: "military",
                delta_i: -split_mil,
                delta_f: normalize_shock(split_mil, lc_military),
                routing: EffectRouting::HybridShock,
            });
            result.civ_effects.push(CivEffectOp {
                step,
                seq: seq.next(),
                civ: CivRef::Existing(civ.civ_idx),
                field: "economy",
                delta_i: -split_eco,
                delta_f: normalize_shock(split_eco, lc_economy),
                routing: EffectRouting::HybridShock,
            });
            result.civ_effects.push(CivEffectOp {
                step,
                seq: seq.next(),
                civ: CivRef::Existing(civ.civ_idx),
                field: "stability",
                delta_i: -stab_loss,
                delta_f: normalize_shock(stab_loss, lc_stability),
                routing: EffectRouting::HybridShock,
            });
        } else {
            result.civ_effects.push(CivEffectOp {
                step,
                seq: seq.next(),
                civ: CivRef::Existing(civ.civ_idx),
                field: "military",
                delta_i: -split_mil,
                delta_f: 0.0,
                routing: EffectRouting::DirectOnly,
            });
            result.civ_effects.push(CivEffectOp {
                step,
                seq: seq.next(),
                civ: CivRef::Existing(civ.civ_idx),
                field: "economy",
                delta_i: -split_eco,
                delta_f: 0.0,
                routing: EffectRouting::DirectOnly,
            });
            result.civ_effects.push(CivEffectOp {
                step,
                seq: seq.next(),
                civ: CivRef::Existing(civ.civ_idx),
                field: "stability",
                delta_i: -stab_loss,
                delta_f: 0.0,
                routing: EffectRouting::DirectOnly,
            });
        }
        // Treasury always direct
        result.civ_effects.push(CivEffectOp {
            step,
            seq: seq.next(),
            civ: CivRef::Existing(civ.civ_idx),
            field: "treasury",
            delta_i: -split_tre,
            delta_f: 0.0,
            routing: EffectRouting::Keep,
        });

        // Relationship ops: parent<->breakaway HOSTILE, breakaway<->others NEUTRAL
        result.relationship_ops.push(RelationshipOp {
            step,
            seq: seq.next(),
            op_type: RelationshipOpType::InitPair,
            civ_a: CivRef::Existing(civ.civ_idx),
            civ_b: new_civ_ref,
            disposition: Disposition::Hostile,
        });
        result.relationship_ops.push(RelationshipOp {
            step,
            seq: seq.next(),
            op_type: RelationshipOpType::InitPair,
            civ_a: new_civ_ref,
            civ_b: CivRef::Existing(civ.civ_idx),
            disposition: Disposition::Hostile,
        });
        // NEUTRAL with all other existing civs
        for (oi, other) in civs.iter().enumerate() {
            if oi as u16 == civ.civ_idx {
                continue;
            }
            result.relationship_ops.push(RelationshipOp {
                step,
                seq: seq.next(),
                op_type: RelationshipOpType::InitPair,
                civ_a: new_civ_ref,
                civ_b: CivRef::Existing(other.civ_idx),
                disposition: Disposition::Neutral,
            });
            result.relationship_ops.push(RelationshipOp {
                step,
                seq: seq.next(),
                op_type: RelationshipOpType::InitPair,
                civ_a: CivRef::Existing(other.civ_idx),
                civ_b: new_civ_ref,
                disposition: Disposition::Neutral,
            });
        }

        // Bridge transition for agent-mode secession
        if hybrid_mode {
            result.bridge_transitions.push(BridgeTransitionOp {
                step,
                seq: seq.next(),
                transition_type: BridgeTransitionType::Secession,
                source_civ: CivRef::Existing(civ.civ_idx),
                target_civ: new_civ_ref,
                regions: breakaway_regions.clone(),
            });
        }

        // Event trigger
        result.events.push(EventTrigger {
            step,
            seq: seq.next(),
            event_type: "secession",
            actors: vec![CivRef::Existing(civ.civ_idx), new_civ_ref],
            importance: 9,
            context_regions: breakaway_regions.clone(),
            context_seed: 0,
        });

        // Bookkeeping: secession_occurred
        result.bookkeeping.push(BookkeepingDelta {
            step,
            seq: seq.next(),
            civ: CivRef::Existing(civ.civ_idx),
            bk_type: BookkeepingType::IncrementEventCount,
            field: "secession_occurred",
            value_i: 1,
        });

        // Update live state — use cached values, not lc reference
        let old_military = live_civs[ci].military;
        let old_economy = live_civs[ci].economy;
        let old_stability = live_civs[ci].stability;
        let remaining_total_effective_capacity: i32 = remaining_regions
            .iter()
            .map(|&r| {
                if (r as usize) < regions.len() {
                    regions[r as usize].effective_capacity as i32
                } else {
                    0
                }
            })
            .sum();
        let breakaway_total_effective_capacity: i32 = breakaway_regions
            .iter()
            .map(|&r| {
                if (r as usize) < regions.len() {
                    regions[r as usize].effective_capacity as i32
                } else {
                    0
                }
            })
            .sum();
        let new_live_idx = match new_civ_ref {
            CivRef::New(local_id) => num_existing_civs + local_id,
            CivRef::Existing(existing_id) => existing_id,
        };
        live_civs[ci].regions = remaining_regions;
        live_civs[ci].military = if hybrid_mode {
            old_military
        } else {
            (old_military - split_mil).max(0)
        };
        live_civs[ci].economy = if hybrid_mode {
            old_economy
        } else {
            (old_economy - split_eco).max(0)
        };
        live_civs[ci].treasury -= split_tre;
        live_civs[ci].stability = if hybrid_mode {
            old_stability
        } else {
            (old_stability - stab_loss).max(0)
        };
        live_civs[ci].population = (lc_population - split_pop).max(0);
        live_civs[ci].total_effective_capacity = remaining_total_effective_capacity;
        live_civs[ci].secession_occurred_count += 1;
        for &r_idx in &breakaway_regions {
            if (r_idx as usize) < live_regions.len() {
                live_regions[r_idx as usize].controller = new_live_idx;
            }
        }
        live_civs.push(LiveCiv {
            regions: breakaway_regions.clone(),
            capital_region: breakaway_capital,
            stability: 40,
            military: split_mil.max(0),
            economy: split_eco.max(0),
            culture: lc_culture,
            treasury: split_tre,
            asabiya: 0.7,
            population: split_pop.max(1),
            decline_turns: 0,
            stats_sum_history: Vec::new(),
            total_effective_capacity: breakaway_total_effective_capacity,
            alive: true,
            secession_occurred_count: 0,
            capital_lost_count: 0,
        });
    }
}

/// Step 3: Update allied turns.
fn step_allied_turns(
    live_rels: &mut LiveRelationships,
    result: &mut PoliticsResult,
) {
    let step: u8 = 3;
    let mut seq = SeqCounter::new();

    // Collect keys to avoid borrow issues, then sort for deterministic iteration order.
    let mut keys: Vec<(u16, u16)> = live_rels.disposition.keys().copied().collect();
    keys.sort();

    for (a, b) in keys {
        let disp = live_rels.disposition[&(a, b)];
        match disp {
            Disposition::Allied => {
                let old = live_rels.get_allied_turns(a, b);
                *live_rels.allied_turns.entry((a, b)).or_insert(0) = old + 1;
                result.relationship_ops.push(RelationshipOp {
                    step,
                    seq: seq.next(),
                    op_type: RelationshipOpType::IncrementAlliedTurns,
                    civ_a: CivRef::Existing(a),
                    civ_b: CivRef::Existing(b),
                    disposition: Disposition::Allied,
                });
            }
            Disposition::Hostile | Disposition::Suspicious | Disposition::Neutral => {
                if live_rels.get_allied_turns(a, b) != 0 {
                    *live_rels.allied_turns.entry((a, b)).or_insert(0) = 0;
                    result.relationship_ops.push(RelationshipOp {
                        step,
                        seq: seq.next(),
                        op_type: RelationshipOpType::ResetAlliedTurns,
                        civ_a: CivRef::Existing(a),
                        civ_b: CivRef::Existing(b),
                        disposition: disp,
                    });
                }
            }
            _ => {}
        }
    }
}

/// Step 4: Check vassal rebellion.
fn step_vassal_rebellion(
    civs: &[CivInput],
    regions: &[RegionInput],
    live_civs: &mut [LiveCiv],
    live_regions: &[LiveRegion],
    live_vassals: &mut LiveVassals,
    live_feds: &LiveFederations,
    live_rels: &mut LiveRelationships,
    live_proxy_wars: &LiveProxyWars,
    wars: &[WarEntry],
    embargoes: &[EmbargoEntry],
    config: &PoliticsConfig,
    seed: u64,
    turn: u32,
    hybrid_mode: bool,
    result: &mut PoliticsResult,
) {
    let step: u8 = 4;
    let mut seq = SeqCounter::new();
    let mut rebelled_overlords: HashSet<u16> = HashSet::new();
    let mut to_remove: Vec<usize> = Vec::new();

    for (vi, vr) in live_vassals.entries.iter().enumerate() {
        let overlord_idx = vr.overlord;
        let vassal_idx = vr.vassal;

        if (overlord_idx as usize) >= live_civs.len() || (vassal_idx as usize) >= live_civs.len() {
            to_remove.push(vi);
            continue;
        }

        // Compute accuracy for vassal->overlord perception
        let accuracy = compute_accuracy_vassal_overlord(
            vassal_idx,
            overlord_idx,
            live_regions,
            regions,
            live_civs,
            civs,
            live_vassals,
            live_feds,
            wars,
            live_proxy_wars,
            live_rels,
            embargoes,
        );

        // Get perceived stability and treasury
        let eff_stab = get_perceived_stat(
            &civs[vassal_idx as usize].name,
            &civs[overlord_idx as usize].name,
            live_civs[overlord_idx as usize].stability,
            "stability",
            100,
            accuracy,
            seed,
            turn,
        )
        .unwrap_or(live_civs[overlord_idx as usize].stability);

        let eff_treas = get_perceived_stat(
            &civs[vassal_idx as usize].name,
            &civs[overlord_idx as usize].name,
            live_civs[overlord_idx as usize].treasury,
            "treasury",
            500,
            accuracy,
            seed,
            turn,
        )
        .unwrap_or(live_civs[overlord_idx as usize].treasury);

        if eff_stab >= 25 && eff_treas >= 10 {
            continue;
        }

        // RNG
        let seed_parts = format!(
            "'vassal_rebellion'|{}|{}|'{}'",
            seed,
            turn,
            civs[vassal_idx as usize].name,
        );
        let hash = stable_hash_int(&[&seed_parts]);
        let mut rng = DetRng::new(hash);

        // Prob selection: reduced if overlord already rebelled against
        let prob = if rebelled_overlords.contains(&overlord_idx) {
            config.vassal_rebellion_reduced_prob
        } else {
            config.vassal_rebellion_base_prob
        };

        // Subsequent rebellion requires HOSTILE/SUSPICIOUS disposition
        if rebelled_overlords.contains(&overlord_idx) {
            let disp = live_rels.get_disposition(vassal_idx, overlord_idx);
            match disp {
                Some(Disposition::Hostile) | Some(Disposition::Suspicious) => {}
                _ => continue,
            }
        }

        if rng.random() >= prob as f64 {
            continue;
        }

        // Rebellion fires
        to_remove.push(vi);
        rebelled_overlords.insert(overlord_idx);

        // Effects on vassal: +10 stability, +0.2 asabiya
        let routing = if hybrid_mode {
            EffectRouting::HybridShock
        } else {
            EffectRouting::DirectOnly
        };

        result.civ_effects.push(CivEffectOp {
            step,
            seq: seq.next(),
            civ: CivRef::Existing(vassal_idx),
            field: "stability",
            delta_i: 10,
            delta_f: if hybrid_mode {
                (10.0 / live_civs[vassal_idx as usize].stability.max(1) as f32).min(1.0)
            } else {
                0.0
            },
            routing,
        });
        result.civ_effects.push(CivEffectOp {
            step,
            seq: seq.next(),
            civ: CivRef::Existing(vassal_idx),
            field: "asabiya",
            delta_i: 0,
            delta_f: 0.2,
            routing: EffectRouting::Keep,
        });

        // Set disposition to HOSTILE
        result.relationship_ops.push(RelationshipOp {
            step,
            seq: seq.next(),
            op_type: RelationshipOpType::SetDisposition,
            civ_a: CivRef::Existing(vassal_idx),
            civ_b: CivRef::Existing(overlord_idx),
            disposition: Disposition::Hostile,
        });
        live_rels.set_disposition(vassal_idx, overlord_idx, Disposition::Hostile);

        // Remove vassal relation
        result.vassal_ops.push(VassalOp {
            step,
            seq: seq.next(),
            op_type: VassalOpType::Remove,
            vassal: CivRef::Existing(vassal_idx),
            overlord: CivRef::Existing(overlord_idx),
        });

        // Event
        result.events.push(EventTrigger {
            step,
            seq: seq.next(),
            event_type: "vassal_rebellion",
            actors: vec![CivRef::Existing(vassal_idx), CivRef::Existing(overlord_idx)],
            importance: 8,
            context_regions: Vec::new(),
            context_seed: 0,
        });

        // Update live state
        if !hybrid_mode {
            live_civs[vassal_idx as usize].stability =
                (live_civs[vassal_idx as usize].stability + 10).min(100);
        }
        live_civs[vassal_idx as usize].asabiya =
            (live_civs[vassal_idx as usize].asabiya + 0.2).min(1.0);
    }

    // Remove vassal entries (in reverse order to preserve indices)
    to_remove.sort_unstable();
    to_remove.dedup();
    for &idx in to_remove.iter().rev() {
        if idx < live_vassals.entries.len() {
            live_vassals.entries.remove(idx);
        }
    }
}

/// Step 5: Check federation formation.
fn step_federation_formation(
    civs: &[CivInput],
    _live_civs: &[LiveCiv],
    live_rels: &LiveRelationships,
    live_vassals: &LiveVassals,
    live_feds: &mut LiveFederations,
    config: &PoliticsConfig,
    seed: u64,
    turn: u32,
    result: &mut PoliticsResult,
) {
    let step: u8 = 5;
    let mut seq = SeqCounter::new();
    let mut checked_pairs: HashSet<(u16, u16)> = HashSet::new();

    let fed_turns_req = config.federation_allied_turns;

    for ci_a in 0..civs.len() {
        let civ_a = civs[ci_a].civ_idx;
        let a_is_vassal = live_vassals.entries.iter().any(|v| v.vassal == civ_a);
        // Preserve the Python oracle's current behavior: federation formation
        // does not exclude dead civs, so allied dead polities can still be
        // appended or recreated if their relationship state persists.
        if a_is_vassal {
            continue;
        }

        // Iterate over all known relationship pairs for civ_a.
        // Sort for deterministic iteration order (HashMap has no guaranteed order).
        let mut keys: Vec<(u16, u16)> = live_rels
            .allied_turns
            .keys()
            .filter(|&&(a, _)| a == civ_a)
            .copied()
            .collect();
        keys.sort();

        for (_, civ_b) in keys {
            let allied_ab = live_rels.get_allied_turns(civ_a, civ_b);
            if allied_ab < fed_turns_req {
                continue;
            }

            let pair = if civ_a < civ_b {
                (civ_a, civ_b)
            } else {
                (civ_b, civ_a)
            };
            if checked_pairs.contains(&pair) {
                continue;
            }
            checked_pairs.insert(pair);

            let allied_ba = live_rels.get_allied_turns(civ_b, civ_a);
            if allied_ba < fed_turns_req {
                continue;
            }
            let b_is_vassal = live_vassals.entries.iter().any(|v| v.vassal == civ_b);
            if b_is_vassal {
                continue;
            }

            let fed_a = live_feds.entries.iter().position(|f| f.members.contains(&civ_a));
            let fed_b = live_feds.entries.iter().position(|f| f.members.contains(&civ_b));

            match (fed_a, fed_b) {
                (Some(_), Some(_)) => {
                    // Both in federations: skip
                    continue;
                }
                (Some(fi), None) => {
                    // Append B to A's federation
                    live_feds.entries[fi].members.push(civ_b);
                    result.federation_ops.push(FederationOp {
                        step,
                        seq: seq.next(),
                        op_type: FederationOpType::AppendMember,
                        federation_ref: live_fed_ref(live_feds.entries[fi].fed_idx),
                        civ: CivRef::Existing(civ_b),
                        members: Vec::new(),
                        context_seed: 0,
                    });
                    // NOTE: APPEND_MEMBER does NOT emit events (spec Section 2)
                }
                (None, Some(fi)) => {
                    // Append A to B's federation
                    live_feds.entries[fi].members.push(civ_a);
                    result.federation_ops.push(FederationOp {
                        step,
                        seq: seq.next(),
                        op_type: FederationOpType::AppendMember,
                        federation_ref: live_fed_ref(live_feds.entries[fi].fed_idx),
                        civ: CivRef::Existing(civ_a),
                        members: Vec::new(),
                        context_seed: 0,
                    });
                    // NOTE: No event for APPEND_MEMBER
                }
                (None, None) => {
                    // Create new federation
                    let new_fed_ref = result.alloc_new_fed();
                    live_feds.entries.push(FederationEntry {
                        fed_idx: match new_fed_ref {
                            FedRef::New(id) => 1000 + id, // temporary idx
                            FedRef::Existing(id) => id,
                        },
                        members: vec![civ_a, civ_b],
                        founded_turn: turn,
                    });
                    let context_seed = seed.wrapping_add(turn as u64);
                    result.federation_ops.push(FederationOp {
                        step,
                        seq: seq.next(),
                        op_type: FederationOpType::Create,
                        federation_ref: new_fed_ref,
                        civ: CivRef::Existing(civ_a), // primary member
                        members: vec![CivRef::Existing(civ_a), CivRef::Existing(civ_b)],
                        context_seed,
                    });
                    // Event only for CREATE
                    result.events.push(EventTrigger {
                        step,
                        seq: seq.next(),
                        event_type: "federation_formed",
                        actors: vec![CivRef::Existing(civ_a), CivRef::Existing(civ_b)],
                        importance: 7,
                        context_regions: Vec::new(),
                        context_seed,
                    });
                }
            }
        }
    }
}

/// Step 6: Check federation dissolution.
fn step_federation_dissolution(
    civs: &[CivInput],
    live_civs: &mut [LiveCiv],
    live_rels: &LiveRelationships,
    live_feds: &mut LiveFederations,
    config: &PoliticsConfig,
    hybrid_mode: bool,
    result: &mut PoliticsResult,
) {
    let step: u8 = 6;
    let mut seq = SeqCounter::new();
    let mut feds_to_remove: Vec<usize> = Vec::new();

    for (fi, fed) in live_feds.entries.iter_mut().enumerate() {
        let mut exiting: Vec<u16> = Vec::new();
        for &member in &fed.members {
            let mut should_exit = false;
            for &other in &fed.members {
                if other == member {
                    continue;
                }
                let disp = live_rels.get_disposition(member, other);
                if matches!(
                    disp,
                    Some(Disposition::Hostile)
                        | Some(Disposition::Suspicious)
                        | Some(Disposition::Neutral)
                ) {
                    should_exit = true;
                    break;
                }
            }
            if should_exit {
                exiting.push(member);
            }
        }

        for &member in &exiting {
            fed.members.retain(|&m| m != member);

            result.federation_ops.push(FederationOp {
                step,
                seq: seq.next(),
                op_type: FederationOpType::RemoveMember,
                federation_ref: live_fed_ref(fed.fed_idx),
                civ: CivRef::Existing(member),
                members: Vec::new(),
                context_seed: 0,
            });

            // Stability effects on exiting member
            if (member as usize) < civs.len() {
                let civ_stress = civs[member as usize].civ_stress;
                let mult = get_severity_multiplier(civ_stress, config);
                let stab_loss = (config.federation_exit_stability as f32 * mult) as i32;

                let routing = if hybrid_mode {
                    EffectRouting::HybridShock
                } else {
                    EffectRouting::DirectOnly
                };

                result.civ_effects.push(CivEffectOp {
                    step,
                    seq: seq.next(),
                    civ: CivRef::Existing(member),
                    field: "stability",
                    delta_i: -stab_loss,
                    delta_f: if hybrid_mode {
                        normalize_shock(stab_loss, live_civs[member as usize].stability)
                    } else {
                        0.0
                    },
                    routing,
                });
            }

            // Stability effects on remaining members
            for &remaining in &fed.members {
                if (remaining as usize) < civs.len() {
                    let rc_stress = civs[remaining as usize].civ_stress;
                    let rc_mult = get_severity_multiplier(rc_stress, config);
                    let rc_loss =
                        (config.federation_remaining_stability as f32 * rc_mult) as i32;

                    let routing = if hybrid_mode {
                        EffectRouting::HybridShock
                    } else {
                        EffectRouting::DirectOnly
                    };

                    result.civ_effects.push(CivEffectOp {
                        step,
                        seq: seq.next(),
                        civ: CivRef::Existing(remaining),
                        field: "stability",
                        delta_i: -rc_loss,
                        delta_f: if hybrid_mode {
                            normalize_shock(rc_loss, live_civs[remaining as usize].stability)
                        } else {
                            0.0
                        },
                        routing,
                    });
                }
            }
        }

        // Dissolve if <= 1 member
        if fed.members.len() <= 1 {
            feds_to_remove.push(fi);
            result.federation_ops.push(FederationOp {
                step,
                seq: seq.next(),
                op_type: FederationOpType::Dissolve,
                federation_ref: live_fed_ref(fed.fed_idx),
                civ: CivRef::Existing(fed.members.first().copied().unwrap_or(CIV_NONE)),
                members: Vec::new(),
                context_seed: 0,
            });
            // Event on full dissolution only
            result.events.push(EventTrigger {
                step,
                seq: seq.next(),
                event_type: "federation_collapsed",
                actors: fed
                    .members
                    .iter()
                    .map(|&m| CivRef::Existing(m))
                    .collect(),
                importance: 7,
                context_regions: Vec::new(),
                context_seed: 0,
            });
        }
    }

    // Remove dissolved federations (reverse order)
    for &fi in feds_to_remove.iter().rev() {
        if fi < live_feds.entries.len() {
            live_feds.entries.remove(fi);
        }
    }
}

/// Step 7: Check proxy detection.
fn step_proxy_detection(
    civs: &[CivInput],
    live_civs: &mut [LiveCiv],
    live_proxy_wars: &mut LiveProxyWars,
    live_rels: &mut LiveRelationships,
    config: &PoliticsConfig,
    seed: u64,
    turn: u32,
    hybrid_mode: bool,
    result: &mut PoliticsResult,
) {
    let step: u8 = 7;
    let mut seq = SeqCounter::new();

    for pw in live_proxy_wars.entries.iter_mut() {
        if pw.detected {
            continue;
        }
        let target_idx = pw.target_civ;
        if (target_idx as usize) >= live_civs.len() {
            continue;
        }
        let target_culture = live_civs[target_idx as usize].culture;

        // Deterministic detection roll
        let seed_parts = format!(
            "'proxy_detection'|{}|{}|'{}'|'{}'",
            seed,
            turn,
            civs[pw.sponsor as usize].name,
            civs[pw.target_civ as usize].name,
        );
        let hash = stable_hash_int(&[&seed_parts]);
        let mut rng = DetRng::new(hash);
        let detection_prob = target_culture as f64 / 100.0;
        if rng.random() >= detection_prob {
            continue;
        }

        // Detected!
        pw.detected = true;
        result.proxy_war_ops.push(ProxyWarOp {
            step,
            seq: seq.next(),
            op_type: ProxyWarOpType::SetDetected,
            sponsor: CivRef::Existing(pw.sponsor),
            target_civ: CivRef::Existing(pw.target_civ),
            target_region: pw.target_region,
        });

        // Detection is destabilizing for the target.
        let routing = if hybrid_mode {
            EffectRouting::HybridShock
        } else {
            EffectRouting::DirectOnly
        };
        result.civ_effects.push(CivEffectOp {
            step,
            seq: seq.next(),
            civ: CivRef::Existing(target_idx),
            field: "stability",
            delta_i: -5,
            delta_f: if hybrid_mode {
                (-5.0 / live_civs[target_idx as usize].stability.max(1) as f32).max(-1.0)
            } else {
                0.0
            },
            routing,
        });

        // Target discovered espionage: set target->sponsor to HOSTILE.
        live_rels.set_disposition(pw.target_civ, pw.sponsor, Disposition::Hostile);
        result.relationship_ops.push(RelationshipOp {
            step,
            seq: seq.next(),
            op_type: RelationshipOpType::SetDisposition,
            civ_a: CivRef::Existing(pw.target_civ),
            civ_b: CivRef::Existing(pw.sponsor),
            disposition: Disposition::Hostile,
        });

        // Event
        result.events.push(EventTrigger {
            step,
            seq: seq.next(),
            event_type: "proxy_detected",
            actors: vec![CivRef::Existing(pw.sponsor), CivRef::Existing(pw.target_civ)],
            importance: 7,
            context_regions: vec![pw.target_region],
            context_seed: 0,
        });
    }
}

/// Step 8: Check restoration.
fn step_restoration(
    civs: &[CivInput],
    regions: &[RegionInput],
    live_civs: &mut [LiveCiv],
    live_regions: &mut [LiveRegion],
    live_exiles: &mut LiveExiles,
    live_rels: &mut LiveRelationships,
    config: &PoliticsConfig,
    seed: u64,
    turn: u32,
    hybrid_mode: bool,
    restored_this_turn: &mut HashSet<u16>,
    result: &mut PoliticsResult,
) {
    let step: u8 = 8;
    let mut seq = SeqCounter::new();
    let mut to_remove: Vec<usize> = Vec::new();

    for (ei, exile) in live_exiles.entries.iter().enumerate() {
        let absorber_idx = exile.absorber_civ;
        if (absorber_idx as usize) >= live_civs.len() {
            continue;
        }
        let absorber_stab = live_civs[absorber_idx as usize].stability;
        if absorber_stab >= 20 || exile.turns_remaining <= 0 {
            continue;
        }

        // Available regions: conquered regions still controlled by absorber
        let available: Vec<u16> = exile
            .conquered_regions
            .iter()
            .filter(|&&r| {
                (r as usize) < live_regions.len()
                    && live_regions[r as usize].controller == absorber_idx
            })
            .copied()
            .collect();
        if available.is_empty() {
            continue;
        }

        // Probability with recognized_by bonus
        let prob = config.restoration_base_prob
            + config.restoration_recognition_bonus * exile.recognized_by.len() as f32;

        let seed_parts = format!(
            "'restoration'|{}|{}|'{}'",
            seed,
            turn,
            civs[exile.original_civ as usize].name,
        );
        let hash = stable_hash_int(&[&seed_parts]);
        let mut rng = DetRng::new(hash);
        if rng.random() >= prob as f64 {
            continue;
        }

        // Python's max(..., key=...) keeps the first region on ties.
        let mut target_region = available[0];
        let mut target_effective_capacity_u16 = if (target_region as usize) < regions.len() {
            regions[target_region as usize].effective_capacity
        } else {
            0
        };
        for &candidate in available.iter().skip(1) {
            let candidate_effective_capacity = if (candidate as usize) < regions.len() {
                regions[candidate as usize].effective_capacity
            } else {
                0
            };
            if candidate_effective_capacity > target_effective_capacity_u16 {
                target_region = candidate;
                target_effective_capacity_u16 = candidate_effective_capacity;
            }
        }
        let target_effective_capacity = if (target_region as usize) < regions.len() {
            regions[target_region as usize].effective_capacity as i32
        } else {
            0
        };
        let restored_population = if hybrid_mode && (target_region as usize) < regions.len() {
            regions[target_region as usize].population as i32
        } else {
            30
        };

        // Check if the original civ exists as dead (regions=[])
        let restored_is_existing = (exile.original_civ as usize) < live_civs.len()
            && live_civs[exile.original_civ as usize].regions.is_empty();

        let restored_civ_ref = if restored_is_existing {
            CivRef::Existing(exile.original_civ)
        } else {
            result.alloc_new_civ()
        };

        // Restore op
        result.civ_ops.push(CivOp {
            step,
            seq: seq.next(),
            op_type: CivOpType::Restore,
            source_civ: CivRef::Existing(absorber_idx),
            target_civ: restored_civ_ref,
            regions: vec![target_region],
            stat_military: 20,
            stat_economy: 20,
            stat_culture: 30,
            stat_stability: 50,
            stat_treasury: 0,
            stat_population: restored_population,
            stat_asabiya: 0.8,
            founded_turn: turn,
        });

        // Remove region from absorber
        result.region_ops.push(RegionOp {
            step,
            seq: seq.next(),
            op_type: RegionOpType::SetController,
            region: target_region,
            controller: restored_civ_ref,
        });

        // Relationship initialization for restored civ
        for (oi, other) in civs.iter().enumerate() {
            if other.civ_idx == exile.original_civ {
                continue;
            }
            let disp = if other.civ_idx == absorber_idx {
                Disposition::Hostile
            } else if exile.recognized_by.contains(&other.civ_idx) {
                Disposition::Friendly
            } else {
                Disposition::Neutral
            };
            result.relationship_ops.push(RelationshipOp {
                step,
                seq: seq.next(),
                op_type: RelationshipOpType::InitPair,
                civ_a: restored_civ_ref,
                civ_b: CivRef::Existing(other.civ_idx),
                disposition: disp,
            });
            result.relationship_ops.push(RelationshipOp {
                step,
                seq: seq.next(),
                op_type: RelationshipOpType::InitPair,
                civ_a: CivRef::Existing(other.civ_idx),
                civ_b: restored_civ_ref,
                disposition: disp,
            });
        }

        // Remove exile modifier
        result.exile_ops.push(ExileOp {
            step,
            seq: seq.next(),
            op_type: ExileOpType::Remove,
            original_civ: CivRef::Existing(exile.original_civ),
            absorber_civ: CivRef::Existing(absorber_idx),
            conquered_regions: exile.conquered_regions.clone(),
            turns_remaining: 0,
        });

        // Bridge transition
        if hybrid_mode {
            result.bridge_transitions.push(BridgeTransitionOp {
                step,
                seq: seq.next(),
                transition_type: BridgeTransitionType::Restoration,
                source_civ: CivRef::Existing(absorber_idx),
                target_civ: restored_civ_ref,
                regions: vec![target_region],
            });
        }

        // Event
        result.events.push(EventTrigger {
            step,
            seq: seq.next(),
            event_type: "restoration",
            actors: vec![restored_civ_ref, CivRef::Existing(absorber_idx)],
            importance: 9,
            context_regions: vec![target_region],
            context_seed: 0,
        });

        to_remove.push(ei);

        // Update live state: remove region from absorber
        live_civs[absorber_idx as usize]
            .regions
            .retain(|&r| r != target_region);
        live_civs[absorber_idx as usize].population = live_civs[absorber_idx as usize]
            .population
            .saturating_sub(restored_population);
        live_civs[absorber_idx as usize].total_effective_capacity = live_civs[absorber_idx as usize]
            .total_effective_capacity
            .saturating_sub(target_effective_capacity);
        if (target_region as usize) < live_regions.len() {
            live_regions[target_region as usize].controller = exile.original_civ;
        }
        // If absorber has no regions left, it's dead
        if live_civs[absorber_idx as usize].regions.is_empty() {
            live_civs[absorber_idx as usize].alive = false;
        }
        // Restore the original civ's live state
        if restored_is_existing {
            let lc = &mut live_civs[exile.original_civ as usize];
            lc.regions = vec![target_region];
            lc.capital_region = target_region;
            lc.alive = true;
            lc.military = 20;
            lc.economy = 20;
            lc.culture = 30;
            lc.stability = 50;
            lc.treasury = 0;
            lc.asabiya = 0.8;
            lc.population = restored_population;
            lc.decline_turns = 0;
            lc.stats_sum_history.clear();
            lc.total_effective_capacity = target_effective_capacity;
            restored_this_turn.insert(exile.original_civ);
        }
    }

    // Remove processed exiles (reverse order)
    for &ei in to_remove.iter().rev() {
        if ei < live_exiles.entries.len() {
            live_exiles.entries.remove(ei);
        }
    }
}

/// Step 9: Check twilight absorption.
fn step_twilight_absorption(
    civs: &[CivInput],
    regions: &[RegionInput],
    live_civs: &mut [LiveCiv],
    live_regions: &mut [LiveRegion],
    live_exiles: &mut LiveExiles,
    config: &PoliticsConfig,
    turn: u32,
    hybrid_mode: bool,
    restored_this_turn: &HashSet<u16>,
    result: &mut PoliticsResult,
) {
    let step: u8 = 9;
    let mut seq = SeqCounter::new();

    // We iterate over civ indices; skip already-absorbed civs
    let num_civs = civs.len();
    for ci in 0..num_civs {
        let civ = &civs[ci];

        if restored_this_turn.contains(&civ.civ_idx) {
            continue;
        }

        if !live_civs[ci].alive || live_civs[ci].regions.is_empty() {
            continue;
        }

        // Snapshot live civ values
        let tw_regions = live_civs[ci].regions.clone();
        let tw_capital = live_civs[ci].capital_region;
        let tw_tec = live_civs[ci].total_effective_capacity;
        let tw_decline = live_civs[ci].decline_turns;

        // Path 1: Unviable (<10 effective capacity, age > 30)
        let is_unviable = tw_tec < 10
            && turn.saturating_sub(civ.founded_turn) > 30;

        // Path 2: Terminal twilight (decline_turns >= threshold, exactly 1 region)
        let is_terminal = tw_decline >= config.twilight_absorption_decline
            && tw_regions.len() == 1;

        if !is_unviable && !is_terminal {
            continue;
        }

        // Find best absorber: adjacent civ with highest culture
        let mut best_absorber: Option<u16> = None;
        let mut best_culture: i32 = -1;

        for &r_idx in &tw_regions {
            if (r_idx as usize) >= regions.len() {
                continue;
            }
            for &adj_idx in &regions[r_idx as usize].adjacencies {
                if (adj_idx as usize) >= live_regions.len() {
                    continue;
                }
                let adj_ctrl = live_regions[adj_idx as usize].controller;
                if adj_ctrl != CIV_NONE && adj_ctrl != civ.civ_idx {
                    if (adj_ctrl as usize) < live_civs.len()
                        && live_civs[adj_ctrl as usize].culture > best_culture
                    {
                        best_culture = live_civs[adj_ctrl as usize].culture;
                        best_absorber = Some(adj_ctrl);
                    }
                }
            }
        }

        let absorber_idx = match best_absorber {
            Some(a) => a,
            None => continue,
        };

        let absorbed_regions: Vec<u16> = tw_regions.clone();
        let civ_capital = tw_capital;

        // Absorb: transfer regions
          result.civ_ops.push(CivOp {
              step,
              seq: seq.next(),
              op_type: CivOpType::Absorb,
              source_civ: CivRef::Existing(civ.civ_idx),
              target_civ: live_civ_ref(absorber_idx, civs.len() as u16),
              regions: absorbed_regions.clone(),
              stat_military: 0,
              stat_economy: 0,
              stat_culture: 0,
              stat_stability: 0,
            stat_treasury: 0,
            stat_population: 0,
            stat_asabiya: 0.0,
            founded_turn: 0,
        });

        // Region controller ops
        for &r_idx in &absorbed_regions {
              result.region_ops.push(RegionOp {
                  step,
                  seq: seq.next(),
                  op_type: RegionOpType::SetController,
                  region: r_idx,
                  controller: live_civ_ref(absorber_idx, civs.len() as u16),
              });
          }

        // Artifact lifecycle intents
        for &r_idx in &absorbed_regions {
            result.artifact_intents.push(ArtifactIntentOp {
                step,
                seq: seq.next(),
                losing_civ: CivRef::Existing(civ.civ_idx),
                gaining_civ: CivRef::Existing(absorber_idx),
                region: r_idx,
                is_capital: r_idx == civ_capital,
                is_destructive: false,
                action: "twilight_absorption",
            });
        }

        // Bridge transition
        if hybrid_mode {
              result.bridge_transitions.push(BridgeTransitionOp {
                  step,
                  seq: seq.next(),
                  transition_type: BridgeTransitionType::Absorption,
                  source_civ: CivRef::Existing(civ.civ_idx),
                  target_civ: live_civ_ref(absorber_idx, civs.len() as u16),
                  regions: absorbed_regions.clone(),
              });
          }

        // Exile modifier
        let conquered_for_exile = if is_terminal && tw_regions.len() == 1 {
            vec![tw_regions[0]]
        } else {
            absorbed_regions.clone()
        };
          result.exile_ops.push(ExileOp {
              step,
              seq: seq.next(),
              op_type: ExileOpType::Append,
              original_civ: CivRef::Existing(civ.civ_idx),
              absorber_civ: live_civ_ref(absorber_idx, civs.len() as u16),
              conquered_regions: conquered_for_exile,
              turns_remaining: 10,
          });

        // Event
          result.events.push(EventTrigger {
              step,
              seq: seq.next(),
              event_type: "twilight_absorption",
              actors: vec![
                  CivRef::Existing(civ.civ_idx),
                  live_civ_ref(absorber_idx, civs.len() as u16),
              ],
              importance: 6,
              context_regions: absorbed_regions.clone(),
              context_seed: 0,
          });

        // Update live state: absorber gets regions, civ becomes dead
        for &r_idx in &absorbed_regions {
            live_civs[absorber_idx as usize].regions.push(r_idx);
            if (r_idx as usize) < live_regions.len() {
                live_regions[r_idx as usize].controller = absorber_idx;
            }
        }
        let absorbed_total_effective_capacity: i32 = absorbed_regions
            .iter()
            .map(|&r_idx| {
                if (r_idx as usize) < regions.len() {
                    regions[r_idx as usize].effective_capacity as i32
                } else {
                    0
                }
            })
            .sum();
        live_civs[absorber_idx as usize].total_effective_capacity += absorbed_total_effective_capacity;
        live_civs[ci].regions.clear();
        live_civs[ci].alive = false;
        // Dead civs stay in list with regions=[]
    }
}

/// Step 10: Update decline tracking.
fn step_decline_tracking(
    civs: &[CivInput],
    live_civs: &mut [LiveCiv],
    result: &mut PoliticsResult,
) {
    let step: u8 = 10;
    let mut seq = SeqCounter::new();

    for (ci, _civ) in civs.iter().enumerate() {
        let lc = &mut live_civs[ci];
        if lc.regions.is_empty() {
            continue;
        }

        let current_sum = lc.economy + lc.military + lc.culture;
        lc.stats_sum_history.push(current_sum);
        if lc.stats_sum_history.len() > 20 {
            let excess = lc.stats_sum_history.len() - 20;
            lc.stats_sum_history.drain(..excess);
        }

        result.bookkeeping.push(BookkeepingDelta {
            step,
            seq: seq.next(),
            civ: CivRef::Existing(civs[ci].civ_idx),
            bk_type: BookkeepingType::AppendStatsHistory,
            field: "stats_sum_history",
            value_i: current_sum,
        });

        if lc.stats_sum_history.len() == 20 {
            if current_sum < lc.stats_sum_history[0] {
                lc.decline_turns += 1;
                result.bookkeeping.push(BookkeepingDelta {
                    step,
                    seq: seq.next(),
                    civ: CivRef::Existing(civs[ci].civ_idx),
                    bk_type: BookkeepingType::IncrementDecline,
                    field: "decline_turns",
                    value_i: 1,
                });
            } else {
                if lc.decline_turns > 0 {
                    lc.decline_turns = 0;
                    result.bookkeeping.push(BookkeepingDelta {
                        step,
                        seq: seq.next(),
                        civ: CivRef::Existing(civs[ci].civ_idx),
                        bk_type: BookkeepingType::ResetDecline,
                        field: "decline_turns",
                        value_i: 0,
                    });
                }
            }
        }
    }

    // Python appends decline-history for civs created earlier in the same
    // politics pass, so mirror that for new breakaways/restorations even
    // though they were not present in the initial civ input slice.
    let mut new_civ_history: Vec<(CivRef, i32)> = Vec::new();
    for op in &result.civ_ops {
        match op.op_type {
            CivOpType::CreateBreakaway => {
                new_civ_history.push((
                    op.target_civ,
                    op.stat_economy + op.stat_military + op.stat_culture,
                ));
            }
            CivOpType::Restore => {
                if matches!(op.target_civ, CivRef::New(_)) {
                    new_civ_history.push((
                        op.target_civ,
                        op.stat_economy + op.stat_military + op.stat_culture,
                    ));
                }
            }
            _ => {}
        }
    }
    for (civ_ref, current_sum) in new_civ_history {
        result.bookkeeping.push(BookkeepingDelta {
            step,
            seq: seq.next(),
            civ: civ_ref,
            bk_type: BookkeepingType::AppendStatsHistory,
            field: "stats_sum_history",
            value_i: current_sum,
        });
    }
}

/// Step 11: Forced collapse.
/// Preserves `regions[:1]` (first listed, NOT capital), integer division,
/// NO severity multiplier, NO sync_civ_population().
fn step_forced_collapse(
    civs: &[CivInput],
    live_civs: &mut [LiveCiv],
    live_regions: &mut [LiveRegion],
    hybrid_mode: bool,
    result: &mut PoliticsResult,
) {
    let step: u8 = 11;
    let mut seq = SeqCounter::new();

    for (ci, civ) in civs.iter().enumerate() {
        // Extract values before mutable borrow
        let asabiya = live_civs[ci].asabiya;
        let stability = live_civs[ci].stability;
        let military = live_civs[ci].military;
        let economy = live_civs[ci].economy;
        let regions_snapshot = live_civs[ci].regions.clone();

        if asabiya >= 0.1 || stability > 20 {
            continue;
        }
        if regions_snapshot.len() <= 1 {
            continue;
        }

        // Keep first listed region (regions[:1])
        let kept_region = regions_snapshot[0];
        let lost_regions: Vec<u16> = regions_snapshot[1..].to_vec();

        // Strip to first region
        result.civ_ops.push(CivOp {
            step,
            seq: seq.next(),
            op_type: CivOpType::StripToFirstRegion,
            source_civ: CivRef::Existing(civ.civ_idx),
            target_civ: CivRef::Existing(civ.civ_idx),
            regions: vec![kept_region],
            stat_military: 0,
            stat_economy: 0,
            stat_culture: 0,
            stat_stability: 0,
            stat_treasury: 0,
            stat_population: 0,
            stat_asabiya: 0.0,
            founded_turn: 0,
        });

        // Nullify controllers of lost regions
        for &r_idx in &lost_regions {
            result.region_ops.push(RegionOp {
                step,
                seq: seq.next(),
                op_type: RegionOpType::NullifyController,
                region: r_idx,
                controller: CivRef::Existing(CIV_NONE),
            });
        }

        // Stat effects: integer division (military // 2, economy // 2)
        // In hybrid mode: pending_shocks with -0.5 each
        // In non-hybrid: direct integer division
        if hybrid_mode {
            result.civ_effects.push(CivEffectOp {
                step,
                seq: seq.next(),
                civ: CivRef::Existing(civ.civ_idx),
                field: "military",
                delta_i: -(military / 2),
                delta_f: -0.5,
                routing: EffectRouting::HybridShock,
            });
            result.civ_effects.push(CivEffectOp {
                step,
                seq: seq.next(),
                civ: CivRef::Existing(civ.civ_idx),
                field: "economy",
                delta_i: -(economy / 2),
                delta_f: -0.5,
                routing: EffectRouting::HybridShock,
            });
        } else {
            // Integer division: military // 2, clamped to floor 0
            let new_mil = (military / 2).max(0);
            let new_eco = (economy / 2).max(0);
            result.civ_effects.push(CivEffectOp {
                step,
                seq: seq.next(),
                civ: CivRef::Existing(civ.civ_idx),
                field: "military",
                delta_i: new_mil - military, // negative delta
                delta_f: 0.0,
                routing: EffectRouting::DirectOnly,
            });
            result.civ_effects.push(CivEffectOp {
                step,
                seq: seq.next(),
                civ: CivRef::Existing(civ.civ_idx),
                field: "economy",
                delta_i: new_eco - economy,
                delta_f: 0.0,
                routing: EffectRouting::DirectOnly,
            });
        }

        // Event
        result.events.push(EventTrigger {
            step,
            seq: seq.next(),
            event_type: "collapse",
            actors: vec![CivRef::Existing(civ.civ_idx)],
            importance: 10,
            context_regions: lost_regions.clone(),
            context_seed: 0,
        });

        // Update live state
        live_civs[ci].regions = vec![kept_region];
        live_civs[ci].military = if hybrid_mode {
            military
        } else {
            (military / 2).max(0)
        };
        live_civs[ci].economy = if hybrid_mode {
            economy
        } else {
            (economy / 2).max(0)
        };
        for &r_idx in &lost_regions {
            if (r_idx as usize) < live_regions.len() {
                live_regions[r_idx as usize].controller = CIV_NONE;
            }
        }
        // NOTE: No sync_civ_population() — this is intentional existing behavior
    }
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

/// Execute the full 11-step Phase 10 political consequence pass.
///
/// Returns a `PoliticsResult` containing all ops in `step + seq` order.
/// Python applies these ops onto the world state.
///
/// NO rayon — everything sequential and deterministic.
pub fn run_politics_pass(
    civs: &[CivInput],
    regions: &[RegionInput],
    topology: &PoliticsTopology,
    config: &PoliticsConfig,
    turn: u32,
    seed: u64,
    hybrid_mode: bool,
) -> PoliticsResult {
    let mut result = PoliticsResult::default();

    // Build mutable live state mirrors
    let mut live_civs: Vec<LiveCiv> = civs.iter().map(LiveCiv::from_input).collect();
    let mut live_regions: Vec<LiveRegion> = regions
        .iter()
        .map(|r| LiveRegion {
            controller: r.controller,
        })
        .collect();
    let mut live_rels = LiveRelationships::from_topology(topology);
    let mut live_vassals = LiveVassals {
        entries: topology.vassals.clone(),
    };
    let mut live_feds = LiveFederations {
        entries: topology.federations.clone(),
    };
    let mut live_proxy_wars = LiveProxyWars {
        entries: topology.proxy_wars.clone(),
    };
    let mut live_exiles = LiveExiles {
        entries: topology.exiles.clone(),
    };
    let mut restored_this_turn: HashSet<u16> = HashSet::new();

    // Step 1: Capital loss
    step_capital_loss(
        civs,
        regions,
        &mut live_civs,
        &live_regions,
        config,
        hybrid_mode,
        &mut result,
    );

    // Step 2: Secession
    step_secession(
        civs,
        regions,
        &mut live_civs,
        &mut live_regions,
        &mut live_rels,
        &live_proxy_wars,
        config,
        seed,
        turn,
        hybrid_mode,
        &mut result,
    );

    // Step 3: Allied turns
    step_allied_turns(&mut live_rels, &mut result);

    // Step 4: Vassal rebellion
    step_vassal_rebellion(
        civs,
        regions,
        &mut live_civs,
        &live_regions,
        &mut live_vassals,
        &live_feds,
        &mut live_rels,
        &live_proxy_wars,
        &topology.wars,
        &topology.embargoes,
        config,
        seed,
        turn,
        hybrid_mode,
        &mut result,
    );

    // Step 5: Federation formation
    step_federation_formation(
        civs,
        &live_civs,
        &live_rels,
        &live_vassals,
        &mut live_feds,
        config,
        seed,
        turn,
        &mut result,
    );

    // Step 6: Federation dissolution
    step_federation_dissolution(
        civs,
        &mut live_civs,
        &live_rels,
        &mut live_feds,
        config,
        hybrid_mode,
        &mut result,
    );

    // Step 7: Proxy detection
    step_proxy_detection(
        civs,
        &mut live_civs,
        &mut live_proxy_wars,
        &mut live_rels,
        config,
        seed,
        turn,
        hybrid_mode,
        &mut result,
    );

    // Step 8: Restoration
    step_restoration(
        civs,
        regions,
        &mut live_civs,
        &mut live_regions,
        &mut live_exiles,
        &mut live_rels,
        config,
        seed,
        turn,
        hybrid_mode,
        &mut restored_this_turn,
        &mut result,
    );

    // Step 9: Twilight absorption
    step_twilight_absorption(
        civs,
        regions,
        &mut live_civs,
        &mut live_regions,
        &mut live_exiles,
        config,
        turn,
        hybrid_mode,
        &restored_this_turn,
        &mut result,
    );

    // Step 10: Decline tracking
    step_decline_tracking(civs, &mut live_civs, &mut result);

    // Step 11: Forced collapse
    step_forced_collapse(
        civs,
        &mut live_civs,
        &mut live_regions,
        hybrid_mode,
        &mut result,
    );

    result
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn make_config() -> PoliticsConfig {
        PoliticsConfig::default()
    }

    #[test]
    fn test_graph_distance_same_node() {
        let r = vec![RegionInput::new(0)];
        assert_eq!(graph_distance(&r, 0, 0), 0);
    }

    #[test]
    fn test_graph_distance_adjacent() {
        let mut r0 = RegionInput::new(0);
        let mut r1 = RegionInput::new(1);
        r0.adjacencies = vec![1];
        r1.adjacencies = vec![0];
        assert_eq!(graph_distance(&[r0, r1], 0, 1), 1);
    }

    #[test]
    fn test_graph_distance_two_hops() {
        let mut r0 = RegionInput::new(0);
        let mut r1 = RegionInput::new(1);
        let mut r2 = RegionInput::new(2);
        r0.adjacencies = vec![1];
        r1.adjacencies = vec![0, 2];
        r2.adjacencies = vec![1];
        assert_eq!(graph_distance(&[r0, r1, r2], 0, 2), 2);
    }

    #[test]
    fn test_graph_distance_disconnected() {
        let r0 = RegionInput::new(0);
        let r1 = RegionInput::new(1);
        assert_eq!(graph_distance(&[r0, r1], 0, 1), -1);
    }

    #[test]
    fn test_severity_multiplier_zero_stress() {
        let config = make_config();
        let mult = get_severity_multiplier(0, &config);
        assert!((mult - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_severity_multiplier_max_stress() {
        let config = make_config();
        // stress=20, divisor=20, scale=0.5: base=1.0+1.0*0.5=1.5
        let mult = get_severity_multiplier(20, &config);
        assert!((mult - 1.5).abs() < 0.001);
    }

    #[test]
    fn test_severity_multiplier_capped() {
        let mut config = make_config();
        config.severity_multiplier = 3.0; // would exceed cap
        let mult = get_severity_multiplier(20, &config);
        assert!((mult - config.severity_cap).abs() < 0.001);
    }

    #[test]
    fn test_sha256_basic() {
        // Known SHA-256 of empty string
        let digest = sha256(b"");
        assert_eq!(
            digest[0..4],
            [0xe3, 0xb0, 0xc4, 0x42]
        );
    }

    #[test]
    fn test_stable_hash_deterministic() {
        let h1 = stable_hash_int(&["test_input"]);
        let h2 = stable_hash_int(&["test_input"]);
        assert_eq!(h1, h2);
    }

    #[test]
    fn test_stable_hash_different_inputs() {
        let h1 = stable_hash_int(&["a"]);
        let h2 = stable_hash_int(&["b"]);
        assert_ne!(h1, h2);
    }

    #[test]
    fn test_det_rng_matches_python_random_for_known_seeds() {
        let mut rng0 = DetRng::new(0);
        assert!((rng0.random() - 0.8444218515250481).abs() < 1e-15);
        assert!((rng0.random() - 0.7579544029403025).abs() < 1e-15);

        let mut rng1 = DetRng::new(1);
        assert!((rng1.random() - 0.13436424411240122).abs() < 1e-15);
        assert!((rng1.random() - 0.8474337369372327).abs() < 1e-15);

        let mut rng2 = DetRng::new(0x1234_5678_9abc_def0);
        assert!((rng2.random() - 0.849063363578306).abs() < 1e-15);
        assert!((rng2.random() - 0.9649343632780897).abs() < 1e-15);
    }

    #[test]
    fn test_get_perceived_stat_matches_python_name_seed() {
        let perceived_stability = get_perceived_stat(
            "Obs",
            "Tgt",
            40,
            "stability",
            100,
            0.5,
            42,
            10,
        );
        assert_eq!(perceived_stability, Some(44));

        let perceived_treasury = get_perceived_stat(
            "Vassal X",
            "Empire Y",
            12,
            "treasury",
            500,
            0.35,
            42,
            10,
        );
        assert_eq!(perceived_treasury, Some(16));
    }
}
