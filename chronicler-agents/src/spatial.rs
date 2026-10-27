//! Spatial substrate: per-region grid for neighbor queries and attractor-based drift.

use crate::agent::OCCUPATION_COUNT;
use crate::pool::AgentPool;
use crate::region::RegionState;

pub const GRID_SIZE: usize = 10;

pub struct SpatialGrid {
    pub cells: Vec<Vec<u32>>,  // GRID_SIZE x GRID_SIZE, each cell holds slot indices
}

impl SpatialGrid {
    pub fn new() -> Self {
        Self {
            cells: (0..GRID_SIZE * GRID_SIZE).map(|_| Vec::new()).collect(),
        }
    }

    pub fn clear(&mut self) {
        for cell in &mut self.cells {
            cell.clear();
        }
    }

    /// Insert an agent at (x, y) into the grid.
    pub fn insert(&mut self, slot: u32, x: f32, y: f32) {
        let cx = ((x * GRID_SIZE as f32) as usize).min(GRID_SIZE - 1);
        let cy = ((y * GRID_SIZE as f32) as usize).min(GRID_SIZE - 1);
        self.cells[cy * GRID_SIZE + cx].push(slot);
    }

    /// Query neighbors: returns slot indices from 9 cells around (x, y),
    /// sorted by slot index, excluding `exclude_slot`.
    pub fn query_neighbors(&self, x: f32, y: f32, exclude_slot: u32) -> Vec<u32> {
        let cx = ((x * GRID_SIZE as f32) as usize).min(GRID_SIZE - 1);
        let cy = ((y * GRID_SIZE as f32) as usize).min(GRID_SIZE - 1);

        let mut result = Vec::new();
        let x_min = cx.saturating_sub(1);
        let x_max = (cx + 1).min(GRID_SIZE - 1);
        let y_min = cy.saturating_sub(1);
        let y_max = (cy + 1).min(GRID_SIZE - 1);

        for row in y_min..=y_max {
            for col in x_min..=x_max {
                for &slot in &self.cells[row * GRID_SIZE + col] {
                    if slot != exclude_slot {
                        result.push(slot);
                    }
                }
            }
        }
        result.sort_unstable();
        result
    }
}

/// Rebuild per-region spatial grids from pool positions.
pub fn rebuild_spatial_grids(pool: &AgentPool, grids: &mut Vec<SpatialGrid>, num_regions: u16) {
    if grids.len() != num_regions as usize {
        grids.clear();
        grids.resize_with(num_regions as usize, SpatialGrid::new);
    }
    for g in grids.iter_mut() {
        g.clear();
    }
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            // M58a: Skip non-idle merchants from spatial grid (on trip)
            if pool.is_on_trip(slot) {
                continue;
            }
            let r = pool.regions[slot] as usize;
            if r < grids.len() {
                grids[r].insert(slot as u32, pool.x[slot], pool.y[slot]);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Attractor model
// ---------------------------------------------------------------------------

pub const MAX_ATTRACTORS: usize = 8;
pub const MIN_ATTRACTOR_SEPARATION: f32 = 0.15; // [CALIBRATE M61b]

/// Position clamp upper bound: just below 1.0 to keep positions strictly in [0, 1).
const POS_MAX: f32 = 1.0 - f32::EPSILON;

#[derive(Clone, Copy, Debug, PartialEq)]
#[repr(u8)]
pub enum AttractorType {
    River = 0,
    Coast = 1,
    Resource0 = 2,
    Resource1 = 3,
    Resource2 = 4,
    Temple = 5,
    Capital = 6,
    Market = 7, // reserved, inactive
}

impl AttractorType {
    fn discriminant(self) -> u64 {
        self as u64
    }
}

pub struct RegionAttractors {
    pub positions: [(f32, f32); MAX_ATTRACTORS],
    pub weights: [f32; MAX_ATTRACTORS],
    pub types: [AttractorType; MAX_ATTRACTORS],
    pub count: u8,
}

/// Occupation affinity table: [OCCUPATION_COUNT x MAX_ATTRACTORS]
/// Indexed by [occupation][attractor_type]
/// All values [CALIBRATE M61b]
pub const OCCUPATION_AFFINITY: [[f32; MAX_ATTRACTORS]; OCCUPATION_COUNT] = [
    // River, Coast, Res0, Res1, Res2, Temple, Capital, Market
    [0.4, 0.1, 0.8, 0.8, 0.8, 0.05, 0.1, 0.0], // Farmer
    [0.1, 0.1, 0.1, 0.1, 0.1, 0.05, 0.7, 0.0], // Soldier
    [0.2, 0.3, 0.3, 0.3, 0.3, 0.05, 0.5, 0.4], // Merchant — M58a: Market activated
    [0.1, 0.1, 0.1, 0.1, 0.1, 0.5, 0.5, 0.0],  // Scholar
    [0.1, 0.05, 0.05, 0.05, 0.05, 0.8, 0.3, 0.0], // Priest
];

// LCG constants for deterministic secondary hash
const LCG_MUL: u64 = 6_364_136_223_846_793_005;
const LCG_ADD: u64 = 1_442_695_040_888_963_407;

/// Map a u64 hash to a float in [0, 1) using upper bits.
#[inline]
fn hash_to_unit(h: u64) -> f32 {
    let upper = (h >> 32) as u32;
    (upper as f64 / (u32::MAX as f64 + 1.0)) as f32
}

/// Map a u64 hash to a float in [lo, hi].
#[inline]
fn hash_to_range(h: u64, lo: f32, hi: f32) -> f32 {
    lo + hash_to_unit(h) * (hi - lo)
}

/// Deterministic base hash from seed, region_id, and attractor type discriminant.
#[inline]
fn base_hash(seed: u64, region_id: u16, disc: u64) -> u64 {
    seed.wrapping_mul((region_id as u64).wrapping_add(1))
        .wrapping_add(disc)
}

/// Compute an edge-biased position (for River, Coast).
/// Spec deviation: uses LCG-based hash instead of spec's `(seed XOR region_id XOR type) % 4`.
/// Stronger mixing avoids correlated edge choices across nearby regions.
fn edge_position(seed: u64, region_id: u16, disc: u64) -> (f32, f32) {
    let h0 = seed
        .wrapping_mul(0x517cc1b727220a95)
        .wrapping_add(region_id as u64)
        .wrapping_mul(0x6c62272e07bb0142)
        .wrapping_add(disc);
    let edge = (h0 % 4) as u8;
    let h1 = h0.wrapping_mul(LCG_MUL).wrapping_add(LCG_ADD);
    match edge {
        0 => {
            // Top edge: y in [0.85, 0.98], x varied in [0.05, 0.95]
            let x = hash_to_range(h1, 0.05, 0.95);
            let h2 = h1.wrapping_mul(LCG_MUL).wrapping_add(LCG_ADD);
            let y = hash_to_range(h2, 0.85, 0.98);
            (x, y)
        }
        1 => {
            // Bottom edge: y in [0.02, 0.15], x varied
            let x = hash_to_range(h1, 0.05, 0.95);
            let h2 = h1.wrapping_mul(LCG_MUL).wrapping_add(LCG_ADD);
            let y = hash_to_range(h2, 0.02, 0.15);
            (x, y)
        }
        2 => {
            // Left edge: x in [0.02, 0.15], y varied
            let x = hash_to_range(h1, 0.02, 0.15);
            let h2 = h1.wrapping_mul(LCG_MUL).wrapping_add(LCG_ADD);
            let y = hash_to_range(h2, 0.05, 0.95);
            (x, y)
        }
        _ => {
            // Right edge: x in [0.85, 0.98], y varied
            let x = hash_to_range(h1, 0.85, 0.98);
            let h2 = h1.wrapping_mul(LCG_MUL).wrapping_add(LCG_ADD);
            let y = hash_to_range(h2, 0.05, 0.95);
            (x, y)
        }
    }
}

/// Compute an interior position (for Resource0/1/2, Temple) in [0.1, 0.9].
fn interior_position(seed: u64, region_id: u16, disc: u64) -> (f32, f32) {
    let h = base_hash(seed, region_id, disc);
    let x = hash_to_range(h, 0.1, 0.9);
    let h2 = h.wrapping_mul(LCG_MUL).wrapping_add(LCG_ADD);
    let y = hash_to_range(h2, 0.1, 0.9);
    (x, y)
}

/// Compute a center-biased position (for Capital) in [0.35, 0.65].
fn center_position(seed: u64, region_id: u16, disc: u64) -> (f32, f32) {
    let h = base_hash(seed, region_id, disc);
    let x = hash_to_range(h, 0.35, 0.65);
    let h2 = h.wrapping_mul(LCG_MUL).wrapping_add(LCG_ADD);
    let y = hash_to_range(h2, 0.35, 0.65);
    (x, y)
}

/// Clamp a position to [0.0, POS_MAX].
#[inline]
fn clamp_pos(v: f32) -> f32 {
    v.max(0.0).min(POS_MAX)
}

/// Initialize attractors for a region based on its features.
///
/// Deterministic: same (seed, region_id, region state) always produces the same result.
pub fn init_attractors(seed: u64, region_id: u16, region: &RegionState) -> RegionAttractors {
    let mut att = RegionAttractors {
        positions: [(0.0, 0.0); MAX_ATTRACTORS],
        weights: [0.0; MAX_ATTRACTORS],
        types: [AttractorType::Market; MAX_ATTRACTORS], // placeholder
        count: 0,
    };

    // Candidate attractors: (type, activated, position_fn)
    // Check activation and push if active.
    struct Candidate {
        atype: AttractorType,
        active: bool,
    }

    let candidates = [
        Candidate {
            atype: AttractorType::River,
            active: region.has_river(),
        },
        Candidate {
            atype: AttractorType::Coast,
            active: region.terrain == 2, // Coast
        },
        Candidate {
            atype: AttractorType::Resource0,
            active: region.resource_effective_yield[0] > 0.0,
        },
        Candidate {
            atype: AttractorType::Resource1,
            active: region.resource_effective_yield[1] > 0.0,
        },
        Candidate {
            atype: AttractorType::Resource2,
            active: region.resource_effective_yield[2] > 0.0,
        },
        Candidate {
            atype: AttractorType::Temple,
            active: region.has_temple,
        },
        Candidate {
            atype: AttractorType::Capital,
            active: region.is_capital,
        },
        Candidate {
            atype: AttractorType::Market,
            active: true, // M58a: always active, weight-driven
        },
    ];

    for c in &candidates {
        if !c.active {
            continue;
        }
        if att.count as usize >= MAX_ATTRACTORS {
            break;
        }
        let idx = att.count as usize;
        att.types[idx] = c.atype;
        let disc = c.atype.discriminant();

        let pos = match c.atype {
            AttractorType::River | AttractorType::Coast => edge_position(seed, region_id, disc),
            AttractorType::Resource0 | AttractorType::Resource1 | AttractorType::Resource2
            | AttractorType::Temple => interior_position(seed, region_id, disc),
            AttractorType::Capital => center_position(seed, region_id, disc),
            AttractorType::Market => interior_position(seed, region_id, disc),
        };
        att.positions[idx] = (clamp_pos(pos.0), clamp_pos(pos.1));
        att.count += 1;
    }

    // Enforce minimum separation: up to 20 iterations (spec says 10, raised for
    // reliability with the symmetric push algorithm below).
    // Spec deviation: uses symmetric push (both attractors move apart) instead of
    // priority-based push (only lower-priority moves). Symmetric push avoids
    // systematically displacing low-priority attractors to boundaries. If one is
    // boundary-clamped, try orthogonal displacement to escape.
    for _iter in 0..20 {
        let mut any_moved = false;
        let n = att.count as usize;
        for i in 0..n {
            for j in (i + 1)..n {
                let dx = att.positions[j].0 - att.positions[i].0;
                let dy = att.positions[j].1 - att.positions[i].1;
                let dist = (dx * dx + dy * dy).sqrt();
                if dist < MIN_ATTRACTOR_SEPARATION {
                    any_moved = true;
                    if dist < 1e-6 {
                        // Coincident: push j in a deterministic direction
                        let nudge = MIN_ATTRACTOR_SEPARATION * 0.7;
                        let h = base_hash(seed, region_id, j as u64);
                        let angle = hash_to_unit(h) * std::f32::consts::TAU;
                        att.positions[j].0 =
                            clamp_pos(att.positions[j].0 + nudge * angle.cos());
                        att.positions[j].1 =
                            clamp_pos(att.positions[j].1 + nudge * angle.sin());
                    } else {
                        // Symmetric push: move both apart along displacement vector
                        let deficit = MIN_ATTRACTOR_SEPARATION - dist;
                        let half_push = deficit * 0.55;
                        let nx = dx / dist;
                        let ny = dy / dist;

                        // Push i backward (toward origin of displacement)
                        let ix_new = clamp_pos(att.positions[i].0 - nx * half_push);
                        let iy_new = clamp_pos(att.positions[i].1 - ny * half_push);
                        // Push j forward
                        let jx_new = clamp_pos(att.positions[j].0 + nx * half_push);
                        let jy_new = clamp_pos(att.positions[j].1 + ny * half_push);

                        // Check if push was effective (not clamped into no-op)
                        let new_dx = jx_new - ix_new;
                        let new_dy = jy_new - iy_new;
                        let new_dist = (new_dx * new_dx + new_dy * new_dy).sqrt();

                        if new_dist > dist + 0.001 {
                            // Normal push worked
                            att.positions[i] = (ix_new, iy_new);
                            att.positions[j] = (jx_new, jy_new);
                        } else {
                            // Boundary-clamped stall: try orthogonal displacement on j
                            let perp_x = -ny;
                            let perp_y = nx;
                            let ortho_push = MIN_ATTRACTOR_SEPARATION * 0.8;
                            // Deterministic direction choice for orthogonal push
                            let h = base_hash(seed, region_id, (i + j * 7) as u64);
                            let sign = if h % 2 == 0 { 1.0f32 } else { -1.0 };
                            att.positions[j].0 =
                                clamp_pos(att.positions[j].0 + sign * perp_x * ortho_push);
                            att.positions[j].1 =
                                clamp_pos(att.positions[j].1 + sign * perp_y * ortho_push);
                            // Also try moving i in the opposite orthogonal direction
                            att.positions[i].0 =
                                clamp_pos(att.positions[i].0 - sign * perp_x * ortho_push);
                            att.positions[i].1 =
                                clamp_pos(att.positions[i].1 - sign * perp_y * ortho_push);
                        }
                    }
                }
            }
        }
        if !any_moved {
            break;
        }
    }

    // Final clamp (belt-and-suspenders)
    for i in 0..att.count as usize {
        att.positions[i].0 = clamp_pos(att.positions[i].0);
        att.positions[i].1 = clamp_pos(att.positions[i].1);
    }

    // Weights start at 0.0 — caller should invoke update_attractor_weights().
    att
}

/// Recompute attractor weights from live region state.
pub fn update_attractor_weights(attractors: &mut RegionAttractors, region: &RegionState) {
    for i in 0..attractors.count as usize {
        let w = match attractors.types[i] {
            AttractorType::River => region.water.max(0.0).min(1.0),
            AttractorType::Coast => 1.0,
            AttractorType::Resource0 => region.resource_effective_yield[0].max(0.0).min(1.0),
            AttractorType::Resource1 => region.resource_effective_yield[1].max(0.0).min(1.0),
            AttractorType::Resource2 => region.resource_effective_yield[2].max(0.0).min(1.0),
            AttractorType::Temple => {
                if region.has_temple && region.temple_prestige <= 0.0 {
                    1.0
                } else {
                    region.temple_prestige.max(0.0).min(1.0)
                }
            }
            AttractorType::Capital => {
                let cap = region.carrying_capacity.max(1) as f32;
                (region.population as f32 / cap).min(1.0)
            }
            AttractorType::Market => {
                let planning_margin = region.merchant_route_margin;
                let raw = (region.trade_route_count as f32 * 0.3
                           + planning_margin * 0.7)
                           .clamp(0.0, 1.0);
                let prev = attractors.weights[i];
                prev + crate::agent::MARKET_WEIGHT_ALPHA * (raw - prev)
            }
        };
        attractors.weights[i] = w.max(0.0).min(1.0);
    }
}

// ---------------------------------------------------------------------------
// Drift computation
// ---------------------------------------------------------------------------

use rand::SeedableRng;
use rand::Rng;
use rand_chacha::ChaCha8Rng;
use crate::agent::{SPATIAL_POSITION_STREAM_OFFSET, NEWBORN_POSITION_STREAM_OFFSET};

// Movement constants [CALIBRATE M61b]
pub const MAX_DRIFT_PER_TICK: f32 = 0.04;
pub const DENSITY_RADIUS: f32 = 0.15;
pub const REPULSION_RADIUS: f32 = 0.05;
pub const DENSITY_ATTRACTION_MAX: f32 = 0.02;
pub const DENSITY_MIN_DIST: f32 = 0.005;
pub const REPULSION_MIN_DIST: f32 = 0.001;
pub const REPULSION_ZERO_DIST_FORCE: f32 = 5.0;
pub const REPULSION_FORCE_CAP: f32 = 50.0;
pub const ATTRACTOR_DEADZONE: f32 = 0.02;
pub const ATTRACTOR_RANGE: f32 = 0.5;
pub const W_ATTRACTOR: f32 = 0.6;
pub const W_DENSITY: f32 = 0.3;
pub const W_REPULSION: f32 = 0.5;
pub const MIGRATION_JITTER: f32 = 0.05;
pub const BIRTH_JITTER: f32 = 0.02;

/// Compute new position for a single agent given current state.
/// Returns (new_x, new_y).
///
/// `agent_slot` is the agent's pool slot, the identity space of the
/// neighbours' entries. Correction (2026-10, population-entities): the
/// zero-distance repulsion fallback hashed the focal agent's stable id
/// against the neighbour's slot, so a coincident pair (ids 1 and 2 in slots
/// 0 and 1) was pushed at 0 and 2 degrees, the same way, instead of apart.
/// Both sides are slots now, and the pair is pushed in opposite directions.
pub fn compute_drift_for_agent(
    agent_x: f32,
    agent_y: f32,
    occupation: u8,
    agent_slot: u32,
    attractors: &RegionAttractors,
    neighbor_positions: &[(u32, f32, f32)], // (slot_id, x, y) — from spatial hash query using OLD positions
) -> (f32, f32) {
    // 1. Attractor vector — sum over active attractors
    let mut att_x: f32 = 0.0;
    let mut att_y: f32 = 0.0;
    for i in 0..(attractors.count as usize) {
        let dx = attractors.positions[i].0 - agent_x;
        let dy = attractors.positions[i].1 - agent_y;
        let dist = (dx * dx + dy * dy).sqrt();
        if dist < ATTRACTOR_DEADZONE {
            continue;
        }
        let dir_x = dx / dist;
        let dir_y = dy / dist;
        let occ_idx = (occupation as usize).min(OCCUPATION_COUNT - 1);
        let affinity = OCCUPATION_AFFINITY[occ_idx][attractors.types[i] as usize];
        let pull = affinity * attractors.weights[i] * (dist.min(ATTRACTOR_RANGE) / ATTRACTOR_RANGE);
        att_x += pull * dir_x;
        att_y += pull * dir_y;
    }

    // 2. Density vector — mean direction to neighbors within DENSITY_RADIUS
    let mut dens_x: f32 = 0.0;
    let mut dens_y: f32 = 0.0;
    let mut dens_count: u32 = 0;
    for &(_, nx, ny) in neighbor_positions {
        let dx = nx - agent_x;
        let dy = ny - agent_y;
        let dist = (dx * dx + dy * dy).sqrt();
        if dist > DENSITY_RADIUS || dist < DENSITY_MIN_DIST {
            continue;
        }
        dens_x += dx / dist;
        dens_y += dy / dist;
        dens_count += 1;
    }
    if dens_count > 0 {
        dens_x /= dens_count as f32;
        dens_y /= dens_count as f32;
    }
    let dens_mag = (dens_x * dens_x + dens_y * dens_y).sqrt();
    if dens_mag > DENSITY_ATTRACTION_MAX {
        let scale = DENSITY_ATTRACTION_MAX / dens_mag;
        dens_x *= scale;
        dens_y *= scale;
    }

    // 3. Repulsion vector — sum from neighbors within REPULSION_RADIUS
    let mut rep_x: f32 = 0.0;
    let mut rep_y: f32 = 0.0;
    for &(neighbor_slot, nx, ny) in neighbor_positions {
        let dx = agent_x - nx; // AWAY from neighbor
        let dy = agent_y - ny;
        let dist = (dx * dx + dy * dy).sqrt();
        if dist > REPULSION_RADIUS {
            continue;
        }
        let (dir_x, dir_y, force);
        if dist < REPULSION_MIN_DIST {
            // Deterministic zero-distance fallback (both slots: a pair gets
            // the same angle, the lower slot flipped by half a turn)
            let mut angle = ((agent_slot ^ neighbor_slot) % 360) as f32
                * (std::f32::consts::PI / 180.0);
            if agent_slot < neighbor_slot {
                angle += std::f32::consts::PI; // flip for symmetry breaking
            }
            dir_x = angle.cos();
            dir_y = angle.sin();
            force = REPULSION_ZERO_DIST_FORCE;
        } else {
            dir_x = dx / dist;
            dir_y = dy / dist;
            force = (1.0 / (dist * dist)).min(REPULSION_FORCE_CAP);
        }
        rep_x += force * dir_x;
        rep_y += force * dir_y;
    }

    // 4. Weighted sum
    let mut drift_x = W_ATTRACTOR * att_x + W_DENSITY * dens_x + W_REPULSION * rep_x;
    let mut drift_y = W_ATTRACTOR * att_y + W_DENSITY * dens_y + W_REPULSION * rep_y;

    // 5. Clamp magnitude to MAX_DRIFT_PER_TICK
    let mag = (drift_x * drift_x + drift_y * drift_y).sqrt();
    if mag > MAX_DRIFT_PER_TICK {
        let scale = MAX_DRIFT_PER_TICK / mag;
        drift_x *= scale;
        drift_y *= scale;
    }

    // 6. Apply and boundary clamp
    let new_x = (agent_x + drift_x).clamp(0.0, POS_MAX);
    let new_y = (agent_y + drift_y).clamp(0.0, POS_MAX);
    (new_x, new_y)
}

/// One neighbour candidate: (slot, x, y) at the start of the drift step.
pub type NeighborEntry = (u32, f32, f32);

/// Compressed, slot-sorted copy of one region's neighbour grid.
///
/// Cell `c` holds `entries[starts[c]..starts[c + 1]]` in ascending slot
/// order, with the agent's position stored next to its slot so the inner
/// drift loop reads contiguous memory.
struct CellIndex {
    side: usize,
    starts: Vec<u32>,
    entries: Vec<NeighborEntry>,
}

impl CellIndex {
    /// Copy a `SpatialGrid` (fixed `GRID_SIZE`) with positions from `xs`/`ys`.
    fn from_grid(grid: &SpatialGrid, xs: &[f32], ys: &[f32]) -> Self {
        let total: usize = grid.cells.iter().map(|c| c.len()).sum();
        let mut starts = Vec::with_capacity(grid.cells.len() + 1);
        let mut entries = Vec::with_capacity(total);
        starts.push(0u32);
        for cell in &grid.cells {
            let begin = entries.len();
            entries.extend(cell.iter().map(|&s| (s, xs[s as usize], ys[s as usize])));
            // `rebuild_spatial_grids` inserts in slot order, so cells are
            // normally sorted already; hand-built grids may not be.
            let seg = &mut entries[begin..];
            if !seg.windows(2).all(|w| w[0].0 <= w[1].0) {
                seg.sort_by_key(|e| e.0);
            }
            starts.push(entries.len() as u32);
        }
        Self { side: GRID_SIZE, starts, entries }
    }

    /// Bucket `slots` into a `side x side` grid using positions `xs`/`ys`.
    /// `slots` must be ascending, which keeps every cell slot-sorted.
    fn from_slots(side: usize, slots: &[u32], xs: &[f32], ys: &[f32]) -> Self {
        let mut starts = vec![0u32; side * side + 1];
        for &s in slots {
            starts[cell_of(side, xs[s as usize], ys[s as usize]) + 1] += 1;
        }
        for c in 0..side * side {
            starts[c + 1] += starts[c];
        }
        let mut fill: Vec<u32> = starts[..side * side].to_vec();
        let mut entries = vec![(0u32, 0.0f32, 0.0f32); slots.len()];
        for &s in slots {
            let c = cell_of(side, xs[s as usize], ys[s as usize]);
            entries[fill[c] as usize] = (s, xs[s as usize], ys[s as usize]);
            fill[c] += 1;
        }
        Self { side, starts, entries }
    }
}

/// Cell of (x, y) in a `side x side` grid, with the same arithmetic as
/// `SpatialGrid::insert` / `query_neighbors`.
#[inline]
fn cell_of(side: usize, x: f32, y: f32) -> usize {
    let cx = ((x * side as f32) as usize).min(side - 1);
    let cy = ((y * side as f32) as usize).min(side - 1);
    cy * side + cx
}

/// Reusable per-thread buffers.
#[derive(Default)]
struct DriftScratch {
    /// Merged block list (all agents in the 3 x 3 block, ascending slot).
    block: Vec<NeighborEntry>,
    tmp: Vec<NeighborEntry>,
    bounds: Vec<usize>,
    next_bounds: Vec<usize>,
    /// Neighbours actually evaluated (fast mode sample).
    sample: Vec<NeighborEntry>,
    /// The evaluated neighbours as columns (slot-sorted).
    cols: NeighborColumns,
    /// Per neighbour: distance and unit direction toward the neighbour.
    geom: Geometry,
    /// Exact mode: per lane, the block indices within the repulsion radius.
    rep: [Vec<u32>; DRIFT_LANES],
}

/// Neighbour list as columns, so the distance pass vectorises.
#[derive(Default)]
struct NeighborColumns {
    slot: Vec<u32>,
    x: Vec<f32>,
    y: Vec<f32>,
}

impl NeighborColumns {
    fn fill(&mut self, entries: &[NeighborEntry]) {
        self.slot.clear();
        self.x.clear();
        self.y.clear();
        self.slot.extend(entries.iter().map(|e| e.0));
        self.x.extend(entries.iter().map(|e| e.1));
        self.y.extend(entries.iter().map(|e| e.2));
    }
}

#[derive(Default)]
struct Geometry {
    dist: Vec<f32>,
    ux: Vec<f32>,
    uy: Vec<f32>,
}

/// Stable two-way merge by slot.
#[inline]
fn merge_two(x: &[NeighborEntry], y: &[NeighborEntry], out: &mut Vec<NeighborEntry>) {
    let (mut i, mut j) = (0, 0);
    while i < x.len() && j < y.len() {
        if x[i].0 <= y[j].0 {
            out.push(x[i]);
            i += 1;
        } else {
            out.push(y[j]);
            j += 1;
        }
    }
    out.extend_from_slice(&x[i..]);
    out.extend_from_slice(&y[j..]);
}

/// Every agent in the 3 x 3 block around `cell` (clamped at the edges), in
/// ascending slot order: for each agent of that cell this is exactly the list
/// `SpatialGrid::query_neighbors` builds (it then drops the agent itself).
/// All agents of one cell share the block, so it is merged once per cell.
/// The list is left in `scratch.block`.
fn merge_block(index: &CellIndex, cell: usize, scratch: &mut DriftScratch) {
    let side = index.side;
    let (cx, cy) = (cell % side, cell / side);
    let x_min = cx.saturating_sub(1);
    let x_max = (cx + 1).min(side - 1);
    let y_min = cy.saturating_sub(1);
    let y_max = (cy + 1).min(side - 1);
    let DriftScratch { block, tmp, bounds, next_bounds, .. } = scratch;
    block.clear();
    bounds.clear();
    bounds.push(0);
    for row in y_min..=y_max {
        for col in x_min..=x_max {
            let c = row * side + col;
            let run = &index.entries[index.starts[c] as usize..index.starts[c + 1] as usize];
            if !run.is_empty() {
                block.extend_from_slice(run);
                bounds.push(block.len());
            }
        }
    }
    // Pairwise merge of the (at most 9) sorted runs.
    while bounds.len() > 2 {
        tmp.clear();
        next_bounds.clear();
        next_bounds.push(0);
        let mut k = 0;
        while k + 2 < bounds.len() {
            merge_two(&block[bounds[k]..bounds[k + 1]], &block[bounds[k + 1]..bounds[k + 2]], tmp);
            next_bounds.push(tmp.len());
            k += 2;
        }
        if k + 1 < bounds.len() {
            tmp.extend_from_slice(&block[bounds[k]..bounds[k + 1]]);
            next_bounds.push(tmp.len());
        }
        std::mem::swap(block, tmp);
        std::mem::swap(bounds, next_bounds);
    }
}

/// Same result, bit for bit, as `compute_drift_for_agent` over
/// `neighbors` with every entry whose slot is `self_slot` removed.
///
/// The reference computes each neighbour's distance twice (density loop with
/// `n - agent`, repulsion loop with `agent - n`). The two squared sums are
/// identical (IEEE negation is exact), so the distance is computed once, in a
/// vectorisable pass, and both loops then accumulate the same terms in the
/// same order. The agent itself gets an infinite distance, which both loops
/// skip exactly as if it had been left out of the list. Repulsion still
/// recomputes `agent - n` for its direction.
fn compute_drift_excluding(
    agent_x: f32,
    agent_y: f32,
    occupation: u8,
    self_slot: u32,
    attractors: &RegionAttractors,
    neighbors: &NeighborColumns,
    geom: &mut Geometry,
) -> (f32, f32) {
    // 1. Attractor vector — identical to compute_drift_for_agent.
    let (att_x, att_y) = attractor_vector(agent_x, agent_y, occupation, attractors);

    let n = neighbors.slot.len();
    let Geometry { dist, ux, uy } = geom;
    dist.clear();
    ux.clear();
    uy.clear();
    dist.resize(n, 0.0);
    ux.resize(n, 0.0);
    uy.resize(n, 0.0);
    for ((((d, u), v), &nx), &ny) in dist
        .iter_mut()
        .zip(ux.iter_mut())
        .zip(uy.iter_mut())
        .zip(&neighbors.x)
        .zip(&neighbors.y)
    {
        let dx = nx - agent_x;
        let dy = ny - agent_y;
        let r = (dx * dx + dy * dy).sqrt();
        *d = r;
        *u = dx / r;
        *v = dy / r;
    }
    // The agent itself (slots are sorted, so its entries are adjacent).
    if let Ok(found) = neighbors.slot.binary_search(&self_slot) {
        let mut k = found;
        while k > 0 && neighbors.slot[k - 1] == self_slot {
            k -= 1;
        }
        while k < n && neighbors.slot[k] == self_slot {
            dist[k] = f32::INFINITY;
            k += 1;
        }
    }

    // 2. Density vector — mean direction to neighbors within DENSITY_RADIUS
    let mut dens_x: f32 = 0.0;
    let mut dens_y: f32 = 0.0;
    let mut dens_count: u32 = 0;
    for k in 0..n {
        let r = dist[k];
        if r > DENSITY_RADIUS || r < DENSITY_MIN_DIST {
            continue;
        }
        dens_x += ux[k];
        dens_y += uy[k];
        dens_count += 1;
    }

    // 3. Repulsion vector — sum from neighbors within REPULSION_RADIUS
    let mut rep_x: f32 = 0.0;
    let mut rep_y: f32 = 0.0;
    for k in 0..n {
        let dist = dist[k];
        if dist > REPULSION_RADIUS {
            continue;
        }
        repulsion_term(agent_x, agent_y, self_slot, neighbors, k, dist, &mut rep_x, &mut rep_y);
    }

    finish_drift(agent_x, agent_y, (att_x, att_y), (dens_x, dens_y), dens_count, (rep_x, rep_y))
}

/// Attractor vector of `compute_drift_for_agent` (step 1).
#[inline(always)]
fn attractor_vector(agent_x: f32, agent_y: f32, occupation: u8, attractors: &RegionAttractors) -> (f32, f32) {
    let mut att_x: f32 = 0.0;
    let mut att_y: f32 = 0.0;
    for i in 0..(attractors.count as usize) {
        let dx = attractors.positions[i].0 - agent_x;
        let dy = attractors.positions[i].1 - agent_y;
        let dist = (dx * dx + dy * dy).sqrt();
        if dist < ATTRACTOR_DEADZONE {
            continue;
        }
        let dir_x = dx / dist;
        let dir_y = dy / dist;
        let occ_idx = (occupation as usize).min(OCCUPATION_COUNT - 1);
        let affinity = OCCUPATION_AFFINITY[occ_idx][attractors.types[i] as usize];
        let pull = affinity * attractors.weights[i] * (dist.min(ATTRACTOR_RANGE) / ATTRACTOR_RANGE);
        att_x += pull * dir_x;
        att_y += pull * dir_y;
    }
    (att_x, att_y)
}

/// Add neighbour `k`'s repulsion (step 3 of `compute_drift_for_agent`);
/// `dist` is its distance, already known not to exceed the radius.
#[inline(always)]
#[allow(clippy::too_many_arguments)]
fn repulsion_term(
    agent_x: f32,
    agent_y: f32,
    agent_slot: u32,
    neighbors: &NeighborColumns,
    k: usize,
    dist: f32,
    rep_x: &mut f32,
    rep_y: &mut f32,
) {
    let (neighbor_slot, nx, ny) = (neighbors.slot[k], neighbors.x[k], neighbors.y[k]);
    let dx = agent_x - nx; // AWAY from neighbor
    let dy = agent_y - ny;
    let (dir_x, dir_y, force);
    if dist < REPULSION_MIN_DIST {
        // Deterministic zero-distance fallback (slots on both sides, as in
        // `compute_drift_for_agent`)
        let mut angle = ((agent_slot ^ neighbor_slot) % 360) as f32
            * (std::f32::consts::PI / 180.0);
        if agent_slot < neighbor_slot {
            angle += std::f32::consts::PI; // flip for symmetry breaking
        }
        dir_x = angle.cos();
        dir_y = angle.sin();
        force = REPULSION_ZERO_DIST_FORCE;
    } else {
        dir_x = dx / dist;
        dir_y = dy / dist;
        force = (1.0 / (dist * dist)).min(REPULSION_FORCE_CAP);
    }
    *rep_x += force * dir_x;
    *rep_y += force * dir_y;
}

/// Steps 2 (mean and cap of the density sum), 4, 5 and 6 of
/// `compute_drift_for_agent`.
#[inline(always)]
fn finish_drift(
    agent_x: f32,
    agent_y: f32,
    (att_x, att_y): (f32, f32),
    (mut dens_x, mut dens_y): (f32, f32),
    dens_count: u32,
    (rep_x, rep_y): (f32, f32),
) -> (f32, f32) {
    if dens_count > 0 {
        dens_x /= dens_count as f32;
        dens_y /= dens_count as f32;
    }
    let dens_mag = (dens_x * dens_x + dens_y * dens_y).sqrt();
    if dens_mag > DENSITY_ATTRACTION_MAX {
        let scale = DENSITY_ATTRACTION_MAX / dens_mag;
        dens_x *= scale;
        dens_y *= scale;
    }

    // 4. Weighted sum
    let mut drift_x = W_ATTRACTOR * att_x + W_DENSITY * dens_x + W_REPULSION * rep_x;
    let mut drift_y = W_ATTRACTOR * att_y + W_DENSITY * dens_y + W_REPULSION * rep_y;

    // 5. Clamp magnitude to MAX_DRIFT_PER_TICK
    let mag = (drift_x * drift_x + drift_y * drift_y).sqrt();
    if mag > MAX_DRIFT_PER_TICK {
        let scale = MAX_DRIFT_PER_TICK / mag;
        drift_x *= scale;
        drift_y *= scale;
    }

    // 6. Apply and boundary clamp
    let new_x = (agent_x + drift_x).clamp(0.0, POS_MAX);
    let new_y = (agent_y + drift_y).clamp(0.0, POS_MAX);
    (new_x, new_y)
}

/// Agents of one cell evaluated together against their shared block.
const DRIFT_LANES: usize = 8;

/// A drifting agent: (slot, x, y, occupation).
type DriftAgent = (u32, f32, f32, u8);

/// `compute_drift_excluding` for up to `DRIFT_LANES` agents of one cell at
/// once, bit for bit; results are appended to `out` in `agents` order.
///
/// Each neighbour is read once for all lanes, so the distance, direction and
/// density terms of the lanes vectorise. Every lane computes exactly the
/// reference expressions. Where the reference skips a neighbour, the density
/// sums add `+0.0` instead: a sum that starts at `+0.0` is never `-0.0`
/// (round to nearest gives `-0.0` only for `-0.0 + -0.0`), so adding `+0.0`
/// leaves it unchanged and the qualifying terms are added in the same order.
/// The repulsion neighbours (at most `REPULSION_RADIUS` away, a small share
/// of the block) are listed per lane in block order and summed by the
/// reference code. A lane's own entries get an infinite distance, as in the
/// reference.
fn drift_lanes(
    agents: &[DriftAgent],
    attractors: &RegionAttractors,
    neighbors: &NeighborColumns,
    rep: &mut [Vec<u32>; DRIFT_LANES],
    out: &mut Vec<(u32, f32, f32)>,
) {
    debug_assert!(!agents.is_empty() && agents.len() <= DRIFT_LANES);
    let n = neighbors.slot.len();
    // Unused lanes repeat the first agent; their results are not used.
    let mut ax = [0.0f32; DRIFT_LANES];
    let mut ay = [0.0f32; DRIFT_LANES];
    let mut own = [0u32; DRIFT_LANES];
    for l in 0..DRIFT_LANES {
        let a = agents[if l < agents.len() { l } else { 0 }];
        ax[l] = a.1;
        ay[l] = a.2;
        own[l] = a.0;
    }
    let mut dens_x = [0.0f32; DRIFT_LANES];
    let mut dens_y = [0.0f32; DRIFT_LANES];
    let mut dens_count = [0u32; DRIFT_LANES];
    let mut rep_len = [0usize; DRIFT_LANES];
    // Entries are written before they are read (only `..rep_len` is read).
    for list in rep.iter_mut() {
        if list.len() < n + 1 {
            list.resize(n + 1, 0);
        }
    }
    let (slots, xs, ys) = (&neighbors.slot[..n], &neighbors.x[..n], &neighbors.y[..n]);
    for k in 0..n {
        let (ns, nx, ny) = (slots[k], xs[k], ys[k]);
        let mut near = [false; DRIFT_LANES];
        for l in 0..DRIFT_LANES {
            let dx = nx - ax[l];
            let dy = ny - ay[l];
            let r = (dx * dx + dy * dy).sqrt();
            let ux = dx / r;
            let uy = dy / r;
            let r = if ns == own[l] { f32::INFINITY } else { r };
            let skip = r > DENSITY_RADIUS || r < DENSITY_MIN_DIST;
            dens_x[l] += if skip { 0.0 } else { ux };
            dens_y[l] += if skip { 0.0 } else { uy };
            dens_count[l] += (!skip) as u32;
            near[l] = !(r > REPULSION_RADIUS);
        }
        for l in 0..DRIFT_LANES {
            rep[l][rep_len[l]] = k as u32;
            rep_len[l] += near[l] as usize;
        }
    }
    for (l, &(slot, x, y, occupation)) in agents.iter().enumerate() {
        let att = attractor_vector(x, y, occupation, attractors);
        let mut rep_x: f32 = 0.0;
        let mut rep_y: f32 = 0.0;
        for &k in &rep[l][..rep_len[l]] {
            let k = k as usize;
            let dx = neighbors.x[k] - x;
            let dy = neighbors.y[k] - y;
            let dist = (dx * dx + dy * dy).sqrt();
            repulsion_term(x, y, slot, neighbors, k, dist, &mut rep_x, &mut rep_y);
        }
        let pos = finish_drift(x, y, att, (dens_x[l], dens_y[l]), dens_count[l], (rep_x, rep_y));
        out.push((slot, pos.0, pos.1));
    }
}

/// Fast mode: deterministic stride sample of at most
/// `FAST_DRIFT_MAX_NEIGHBORS` block entries, offset by the agent's slot so
/// agents sharing a cell see different subsets. Left in `scratch.sample`.
fn sample_block(block: &[NeighborEntry], slot: u32, out: &mut Vec<NeighborEntry>) {
    let cap = crate::scale::FAST_DRIFT_MAX_NEIGHBORS.max(1);
    out.clear();
    if block.len() <= cap {
        out.extend_from_slice(block);
        return;
    }
    let stride = (block.len() + cap - 1) / cap;
    let mut k = slot as usize % stride;
    while k < block.len() {
        out.push(block[k]);
        k += stride;
    }
}

/// Grid side for fast-mode drift in a region with `n` agents.
pub fn fast_drift_grid_side(n: usize) -> usize {
    let per_cell = crate::scale::FAST_DRIFT_TARGET_PER_CELL.max(1);
    let side = ((n as f64 / per_cell as f64).sqrt().ceil()) as usize;
    side.clamp(crate::scale::FAST_DRIFT_MIN_SIDE, crate::scale::FAST_DRIFT_MAX_SIDE)
}

/// Agents per parallel work item; one cell's agents may span several items.
const DRIFT_CHUNK: usize = 128;

/// Below this many drifting agents the drift step runs on one thread.
const DRIFT_PARALLEL_MIN_AGENTS: usize = 4096;

/// Two-pass spatial drift for all alive agents (exact mode).
/// Reads old positions, computes new positions, writes back.
pub fn spatial_drift_step(
    pool: &mut AgentPool,
    grids: &[SpatialGrid],
    attractors: &[RegionAttractors],
    diag: &mut SpatialDiagnostics,
) {
    spatial_drift_step_with_mode(pool, grids, attractors, diag, crate::scale::AgentScaleMode::Exact)
}

/// Two-pass spatial drift for all alive agents.
///
/// Exact mode is bit-identical to the reference loop (every agent of the
/// fixed 10 x 10 grid's 3 x 3 block, ascending slot order, all from the old
/// positions). Agents are independent given the old positions, so they are
/// computed in parallel and written back afterwards; each cell's block list
/// is merged once instead of allocated and sorted per agent, and the cell's
/// agents are evaluated `DRIFT_LANES` at a time against it (`drift_lanes`).
/// Fast mode uses a population-sized grid per region and a bounded neighbour
/// sample.
pub fn spatial_drift_step_with_mode(
    pool: &mut AgentPool,
    grids: &[SpatialGrid],
    attractors: &[RegionAttractors],
    diag: &mut SpatialDiagnostics,
    mode: crate::scale::AgentScaleMode,
) {
    use rayon::prelude::*;

    let cap = pool.capacity();

    // Initialize diagnostics
    let num_regions = grids.len();
    diag.hotspot_count_by_region.clear();
    diag.hotspot_count_by_region.resize(num_regions, 0);
    diag.attractor_occupancy.clear();
    diag.attractor_occupancy.resize(num_regions, [0.0; MAX_ATTRACTORS]);
    diag.hash_max_cell_occupancy.clear();
    diag.hash_max_cell_occupancy.resize(num_regions, 0);

    // Hash max cell occupancy
    for (r, grid) in grids.iter().enumerate() {
        let max_occ = grid.cells.iter().map(|c| c.len() as u16).max().unwrap_or(0);
        diag.hash_max_cell_occupancy[r] = max_occ;

        // Hotspot: cells with occupancy > 2x mean
        let total: usize = grid.cells.iter().map(|c| c.len()).sum();
        let mean = if total > 0 { total as f32 / grid.cells.len() as f32 } else { 0.0 };
        let threshold = mean * 2.0;
        let hotspots = grid.cells.iter().filter(|c| c.len() as f32 > threshold).count();
        diag.hotspot_count_by_region[r] = hotspots as u16;
    }

    // Attractor occupancy — count agents within radius 0.1 of each attractor.
    // Integer counts per region, so the parallel computation is exact.
    let attractor_radius = 0.1f32;
    {
        let pool_ref = &*pool;
        let occupancy: Vec<[f32; MAX_ATTRACTORS]> = attractors
            .par_iter()
            .enumerate()
            .map(|(r, att)| {
                let mut out = [0.0f32; MAX_ATTRACTORS];
                if r >= grids.len() {
                    return out;
                }
                let total_agents: u32 = grids[r].cells.iter().map(|c| c.len() as u32).sum();
                for a_idx in 0..att.count as usize {
                    let (ax, ay) = att.positions[a_idx];
                    let mut count = 0u32;
                    for cell in &grids[r].cells {
                        for &slot in cell {
                            let dx = pool_ref.x[slot as usize] - ax;
                            let dy = pool_ref.y[slot as usize] - ay;
                            if dx * dx + dy * dy <= attractor_radius * attractor_radius {
                                count += 1;
                            }
                        }
                    }
                    out[a_idx] = if total_agents > 0 { count as f32 / total_agents as f32 } else { 0.0 };
                }
                out
            })
            .collect();
        for (r, occ) in occupancy.into_iter().enumerate() {
            if r < diag.attractor_occupancy.len() {
                diag.attractor_occupancy[r] = occ;
            }
        }
    }

    // Sort timing — only run above threshold to avoid wasted work on small pools.
    // The sort result is discarded in M55a (drift uses slot-index order). This timing
    // is infrastructure for M61b profiling of cache-locality benefits.
    diag.sort_time_us = 0;
    if pool.alive_count() >= crate::sort::SPATIAL_SORT_AGENT_THRESHOLD {
        let start = std::time::Instant::now();
        let _ = crate::sort::sorted_iteration_order(pool);
        diag.sort_time_us = start.elapsed().as_micros() as u64;
    }

    // 1. Neighbour indexes from the OLD positions (the grids were built from
    //    them). Exact mode copies the fixed grids; fast mode re-buckets each
    //    grid's agents into a population-sized grid.
    let fast = mode == crate::scale::AgentScaleMode::Fast;
    let indexes: Vec<CellIndex> = {
        let xs = &pool.x[..cap];
        let ys = &pool.y[..cap];
        grids
            .par_iter()
            .map(|grid| {
                if fast {
                    let mut slots: Vec<u32> = grid.cells.iter().flatten().copied().collect();
                    slots.sort_unstable();
                    slots.dedup();
                    CellIndex::from_slots(fast_drift_grid_side(slots.len()), &slots, xs, ys)
                } else {
                    CellIndex::from_grid(grid, xs, ys)
                }
            })
            .collect()
    };

    // 2. Drifting agents grouped by (region, cell of their old position).
    let mut work: Vec<(u32, u32, u32)> = Vec::with_capacity(pool.alive_count());
    for slot in 0..cap {
        if !pool.is_alive(slot) {
            continue;
        }
        // M58a: Skip non-idle merchants from spatial drift (on trip)
        if pool.is_on_trip(slot) {
            continue;
        }
        let region = pool.regions[slot] as usize;
        if region >= indexes.len() || region >= attractors.len() {
            continue;
        }
        let cell = cell_of(indexes[region].side, pool.x[slot], pool.y[slot]);
        work.push((region as u32, cell as u32, slot as u32));
    }
    work.sort_unstable();
    let mut items: Vec<&[(u32, u32, u32)]> = Vec::new();
    for group in work.chunk_by(|a, b| a.0 == b.0 && a.1 == b.1) {
        items.extend(group.chunks(DRIFT_CHUNK));
    }

    // 3. New positions from the old ones. Each result depends only on the
    //    snapshot, so the parallel map is exact.
    let results: Vec<Vec<(u32, f32, f32)>> = {
        let pool_ref = &*pool;
        let run_item = |scratch: &mut DriftScratch, item: &&[(u32, u32, u32)]| -> Vec<(u32, f32, f32)> {
            let (region, cell, _) = item[0];
            let region = region as usize;
            merge_block(&indexes[region], cell as usize, scratch);
            let DriftScratch { block, sample, cols, geom, rep, .. } = scratch;
            if !fast {
                cols.fill(block);
            }
            // Exact: the cell's agents share the block; evaluate them in lanes
            // (non-finite positions, never seen, keep the per-agent path).
            if !fast && cols.x.iter().chain(&cols.y).all(|v| v.is_finite()) {
                let mut out = Vec::with_capacity(item.len());
                let mut lane_agents: [DriftAgent; DRIFT_LANES] = [(0, 0.0, 0.0, 0); DRIFT_LANES];
                for group in item.chunks(DRIFT_LANES) {
                    for (l, &(_, _, slot)) in group.iter().enumerate() {
                        let s = slot as usize;
                        lane_agents[l] = (slot, pool_ref.x[s], pool_ref.y[s], pool_ref.occupations[s]);
                    }
                    drift_lanes(&lane_agents[..group.len()], &attractors[region], cols, rep, &mut out);
                }
                return out;
            }
            item.iter()
                .map(|&(_, _, slot)| {
                    let s = slot as usize;
                    if fast {
                        sample_block(block, slot, sample);
                        cols.fill(sample);
                    }
                    let neighbors: &NeighborColumns = cols;
                    let (nx, ny) = compute_drift_excluding(
                        pool_ref.x[s],
                        pool_ref.y[s],
                        pool_ref.occupations[s],
                        slot,
                        &attractors[region],
                        neighbors,
                        geom,
                    );
                    (slot, nx, ny)
                })
                .collect()
        };
        // Small pools (default worlds hold a few hundred agents) are cheaper
        // without the fork-join overhead; the results are the same.
        if work.len() < DRIFT_PARALLEL_MIN_AGENTS {
            let mut scratch = DriftScratch::default();
            items.iter().map(|item| run_item(&mut scratch, item)).collect()
        } else {
            items.par_iter().map_init(DriftScratch::default, run_item).collect()
        }
    };

    // 4. Write all new positions back to pool
    for (slot, nx, ny) in results.into_iter().flatten() {
        pool.x[slot as usize] = nx;
        pool.y[slot as usize] = ny;
    }
}

/// Derive a per-agent spatial seed from the master seed and agent id.
#[inline]
fn spatial_seed(master_seed: &[u8; 32], agent_id: u32) -> [u8; 32] {
    let mut seed = *master_seed;
    let id_bytes = agent_id.to_le_bytes();
    seed[0] ^= id_bytes[0];
    seed[1] ^= id_bytes[1];
    seed[2] ^= id_bytes[2];
    seed[3] ^= id_bytes[3];
    seed
}

/// Standard packed stream ID for spatial RNG.
#[inline]
fn spatial_stream(region_id: u16, turn: u32, offset: u64) -> u64 {
    debug_assert!(offset <= u16::MAX as u64, "stream offset exceeds packed RNG stream range");
    ((region_id as u64) << 48) | ((turn as u64) << 16) | offset
}

/// Reset agent position after migration: place near highest-affinity attractor
/// for the agent's occupation, with deterministic jitter.
pub fn migration_reset_position(
    agent_id: u32,
    occupation: u8,
    attractors: &RegionAttractors,
    master_seed: &[u8; 32],
    dest_region_id: u16,
    turn: u32,
) -> (f32, f32) {
    if attractors.count == 0 {
        return (0.5, 0.5);
    }

    // Find the highest-affinity attractor for this occupation
    let occ_idx = (occupation as usize).min(OCCUPATION_COUNT - 1);
    let mut best_idx = 0usize;
    let mut best_score = f32::NEG_INFINITY;
    for i in 0..(attractors.count as usize) {
        let affinity = OCCUPATION_AFFINITY[occ_idx][attractors.types[i] as usize];
        let score = affinity * attractors.weights[i];
        if score > best_score {
            best_score = score;
            best_idx = i;
        }
    }

    // M58a: If no attractor has positive score, fall back to center
    if best_score <= 0.0 {
        return (0.5, 0.5);
    }

    let seed = spatial_seed(master_seed, agent_id);
    let mut rng = ChaCha8Rng::from_seed(seed);
    rng.set_stream(spatial_stream(dest_region_id, turn, SPATIAL_POSITION_STREAM_OFFSET));
    let jx: f32 = rng.gen::<f32>() * 2.0 * MIGRATION_JITTER - MIGRATION_JITTER;
    let jy: f32 = rng.gen::<f32>() * 2.0 * MIGRATION_JITTER - MIGRATION_JITTER;

    let x = (attractors.positions[best_idx].0 + jx).clamp(0.0, POS_MAX);
    let y = (attractors.positions[best_idx].1 + jy).clamp(0.0, POS_MAX);
    (x, y)
}

/// Per-tick spatial telemetry.
#[derive(Clone, Debug, Default)]
pub struct SpatialDiagnostics {
    pub hotspot_count_by_region: Vec<u16>,
    pub attractor_occupancy: Vec<[f32; MAX_ATTRACTORS]>,
    pub hash_max_cell_occupancy: Vec<u16>,
    pub sort_time_us: u64,
}

/// Place a newborn near its parent with deterministic jitter.
pub fn newborn_position(
    child_id: u32,
    region_id: u16,
    parent_pos: (f32, f32),
    master_seed: &[u8; 32],
    turn: u32,
) -> (f32, f32) {
    let seed = spatial_seed(master_seed, child_id);
    let mut rng = ChaCha8Rng::from_seed(seed);
    rng.set_stream(spatial_stream(region_id, turn, NEWBORN_POSITION_STREAM_OFFSET));
    let jx: f32 = rng.gen::<f32>() * 2.0 * BIRTH_JITTER - BIRTH_JITTER;
    let jy: f32 = rng.gen::<f32>() * 2.0 * BIRTH_JITTER - BIRTH_JITTER;

    let x = (parent_pos.0 + jx).clamp(0.0, POS_MAX);
    let y = (parent_pos.1 + jy).clamp(0.0, POS_MAX);
    (x, y)
}

/// Position a transit merchant at an edge entry point in the destination region,
/// biased toward the direction they came from.
pub fn transit_entry_position(
    seed: u64,
    region_id: u16,
    from_region_id: u16,
) -> (f32, f32) {
    let disc = from_region_id as u64;
    let h0 = seed
        .wrapping_mul(0x517cc1b727220a95)
        .wrapping_add(region_id as u64)
        .wrapping_mul(0x6c62272e07bb0142)
        .wrapping_add(disc);
    let edge = (h0 % 4) as u8;
    let h1 = h0.wrapping_mul(LCG_MUL).wrapping_add(LCG_ADD);
    let frac = (h1 as f32 / u64::MAX as f32).clamp(0.1, 0.9);
    match edge {
        0 => (frac, 0.05),        // top edge
        1 => (frac, 0.95),        // bottom edge
        2 => (0.05, frac),        // left edge
        3 => (0.95, frac),        // right edge
        _ => (0.5, 0.5),
    }
}

#[cfg(test)]
mod scale_equivalence_tests {
    use super::*;

    /// Deterministic splitmix64 for test data.
    struct Mix(u64);
    impl Mix {
        fn next(&mut self) -> u64 {
            self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
            let mut z = self.0;
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
            z ^ (z >> 31)
        }
        fn unit(&mut self) -> f32 {
            ((self.next() >> 40) as f32) / ((1u64 << 24) as f32)
        }
    }

    fn attractors_for(seed: u64) -> RegionAttractors {
        let mut region = RegionState::new(3);
        region.terrain = 2;
        region.has_temple = true;
        region.is_capital = true;
        region.resource_effective_yield = [0.7, 0.4, 0.2];
        region.population = 50;
        region.carrying_capacity = 60;
        region.trade_route_count = 2;
        region.merchant_route_margin = 0.4;
        let mut att = init_attractors(seed, 3, &region);
        update_attractor_weights(&mut att, &region);
        att
    }

    /// Random clustered positions with exact duplicates, edge and corner
    /// points and points on cell boundaries.
    fn positions(rng: &mut Mix, n: usize) -> Vec<(f32, f32)> {
        let centres = [(0.31, 0.62), (0.5, 0.5), (0.05, 0.95), (0.9, 0.1)];
        let mut out: Vec<(f32, f32)> = Vec::with_capacity(n);
        for i in 0..n {
            let p = match i % 7 {
                0 => (rng.unit(), rng.unit()),
                1 if i > 1 => out[(rng.next() as usize) % out.len()], // exact duplicate
                2 => (0.0, POS_MAX),
                3 => ((rng.next() % 10) as f32 / 10.0, rng.unit()), // on a cell boundary
                _ => {
                    let c = centres[(rng.next() % 4) as usize];
                    let r = 0.2 * rng.unit();
                    let a = rng.unit() * std::f32::consts::TAU;
                    (
                        (c.0 + r * a.cos()).clamp(0.0, POS_MAX),
                        (c.1 + r * a.sin()).clamp(0.0, POS_MAX),
                    )
                }
            };
            out.push(p);
        }
        out
    }

    /// The per-cell merged block with the agent excluded by distance equals
    /// the reference per-agent query + compute, bit for bit.
    #[test]
    fn exact_block_path_is_bit_identical_to_reference() {
        let mut rng = Mix(7);
        for case in 0..12u64 {
            let n = [3usize, 40, 300, 1200][(case % 4) as usize];
            let pts = positions(&mut rng, n);
            let xs: Vec<f32> = pts.iter().map(|p| p.0).collect();
            let ys: Vec<f32> = pts.iter().map(|p| p.1).collect();
            let mut grid = SpatialGrid::new();
            for (s, &(x, y)) in pts.iter().enumerate() {
                grid.insert(s as u32, x, y);
            }
            let att = attractors_for(case + 11);
            let index = CellIndex::from_grid(&grid, &xs, &ys);
            let mut scratch = DriftScratch::default();
            for s in 0..n {
                let (x, y) = pts[s];
                let occ = (s % 5) as u8;
                let reference_list: Vec<(u32, f32, f32)> = grid
                    .query_neighbors(x, y, s as u32)
                    .iter()
                    .map(|&ns| (ns, xs[ns as usize], ys[ns as usize]))
                    .collect();
                let expected = compute_drift_for_agent(x, y, occ, s as u32, &att, &reference_list);
                merge_block(&index, cell_of(GRID_SIZE, x, y), &mut scratch);
                let with_self: Vec<u32> = scratch.block.iter().map(|e| e.0).collect();
                let mut ref_with_self: Vec<u32> = reference_list.iter().map(|e| e.0).collect();
                ref_with_self.push(s as u32);
                ref_with_self.sort_unstable();
                assert_eq!(with_self, ref_with_self, "case {case} slot {s}: block list");
                scratch.cols.fill(&scratch.block);
                let got = compute_drift_excluding(
                    x, y, occ, s as u32, &att, &scratch.cols, &mut scratch.geom,
                );
                assert_eq!(
                    (expected.0.to_bits(), expected.1.to_bits()),
                    (got.0.to_bits(), got.1.to_bits()),
                    "case {case} slot {s}: {expected:?} vs {got:?}"
                );
            }
        }
    }

    /// Lanes of a cell's agents against the shared block equal the reference
    /// per-agent query + compute, bit for bit, for every group size.
    #[test]
    fn exact_lanes_are_bit_identical_to_reference() {
        let mut rng = Mix(19);
        for case in 0..16u64 {
            let n = [5usize, 60, 400, 1500][(case % 4) as usize];
            let mut pts = positions(&mut rng, n);
            if case % 3 == 0 {
                // A dense knot: many agents within the repulsion radius and
                // at the zero-distance fallback.
                for p in pts.iter_mut().step_by(3) {
                    *p = (0.4 + 0.004 * rng.unit(), 0.4 + 0.004 * rng.unit());
                }
            }
            let xs: Vec<f32> = pts.iter().map(|p| p.0).collect();
            let ys: Vec<f32> = pts.iter().map(|p| p.1).collect();
            let mut grid = SpatialGrid::new();
            for (s, &(x, y)) in pts.iter().enumerate() {
                grid.insert(s as u32, x, y);
            }
            let att = attractors_for(case + 5);
            let index = CellIndex::from_grid(&grid, &xs, &ys);
            let mut scratch = DriftScratch::default();
            let occ = |s: usize| (s % 5) as u8;
            for cell in 0..GRID_SIZE * GRID_SIZE {
                let members = &grid.cells[cell];
                if members.is_empty() {
                    continue;
                }
                merge_block(&index, cell, &mut scratch);
                scratch.cols.fill(&scratch.block);
                let group = 1 + (cell + case as usize) % DRIFT_LANES;
                let mut got = Vec::new();
                for chunk in members.chunks(group) {
                    let agents: Vec<DriftAgent> = chunk
                        .iter()
                        .map(|&s| (s, xs[s as usize], ys[s as usize], occ(s as usize)))
                        .collect();
                    drift_lanes(&agents, &att, &scratch.cols, &mut scratch.rep, &mut got);
                }
                assert_eq!(got.len(), members.len());
                for (&s, &(slot, gx, gy)) in members.iter().zip(&got) {
                    assert_eq!(s, slot);
                    let su = s as usize;
                    let reference_list: Vec<(u32, f32, f32)> = grid
                        .query_neighbors(xs[su], ys[su], s)
                        .iter()
                        .map(|&ns| (ns, xs[ns as usize], ys[ns as usize]))
                        .collect();
                    let expected =
                        compute_drift_for_agent(xs[su], ys[su], occ(su), s, &att, &reference_list);
                    assert_eq!(
                        (expected.0.to_bits(), expected.1.to_bits()),
                        (gx.to_bits(), gy.to_bits()),
                        "case {case} cell {cell} slot {s}: {expected:?} vs {:?}",
                        (gx, gy)
                    );
                }
            }
        }
    }

    #[test]
    fn unsorted_hand_built_cells_are_sorted_in_the_index() {
        let mut grid = SpatialGrid::new();
        let xs = vec![0.51f32, 0.52, 0.53, 0.54];
        let ys = vec![0.5f32; 4];
        for s in [3u32, 1, 2, 0] {
            grid.insert(s, xs[s as usize], ys[s as usize]);
        }
        let index = CellIndex::from_grid(&grid, &xs, &ys);
        let mut scratch = DriftScratch::default();
        merge_block(&index, cell_of(GRID_SIZE, 0.5, 0.5), &mut scratch);
        let slots: Vec<u32> = scratch.block.iter().map(|e| e.0).collect();
        assert_eq!(slots, vec![0, 1, 2, 3]);
    }

    #[test]
    fn fast_grid_side_is_bounded() {
        assert_eq!(fast_drift_grid_side(0), crate::scale::FAST_DRIFT_MIN_SIDE);
        assert_eq!(fast_drift_grid_side(100), crate::scale::FAST_DRIFT_MIN_SIDE);
        assert_eq!(fast_drift_grid_side(10_000_000), crate::scale::FAST_DRIFT_MAX_SIDE);
        let mid = fast_drift_grid_side(2_000);
        assert!((crate::scale::FAST_DRIFT_MIN_SIDE..=crate::scale::FAST_DRIFT_MAX_SIDE).contains(&mid));
    }

    #[test]
    fn fast_sample_is_capped_and_deterministic() {
        let n = 2_000usize;
        let mut rng = Mix(3);
        let xs: Vec<f32> = (0..n).map(|_| 0.5 + 0.02 * rng.unit()).collect();
        let ys: Vec<f32> = (0..n).map(|_| 0.5 + 0.02 * rng.unit()).collect();
        let slots: Vec<u32> = (0..n as u32).collect();
        let side = fast_drift_grid_side(n);
        let index = CellIndex::from_slots(side, &slots, &xs, &ys);
        let mut scratch = DriftScratch::default();
        merge_block(&index, cell_of(side, xs[17], ys[17]), &mut scratch);
        assert!(scratch.block.windows(2).all(|w| w[0].0 < w[1].0));
        let mut a = Vec::new();
        let mut b = Vec::new();
        sample_block(&scratch.block, 17, &mut a);
        sample_block(&scratch.block, 17, &mut b);
        assert!(!a.is_empty());
        assert!(a.len() <= crate::scale::FAST_DRIFT_MAX_NEIGHBORS);
        assert_eq!(a, b);
    }
}
