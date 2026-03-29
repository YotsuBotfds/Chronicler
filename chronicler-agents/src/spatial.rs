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
    [0.2, 0.3, 0.3, 0.3, 0.3, 0.05, 0.5, 0.0], // Merchant
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
            active: region.river_mask != 0,
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
        // Market: never active (reserved)
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
            AttractorType::Market => unreachable!(),
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
            AttractorType::Market => 0.0,
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
use crate::agent::SPATIAL_POSITION_STREAM_OFFSET;

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
pub fn compute_drift_for_agent(
    agent_x: f32,
    agent_y: f32,
    occupation: u8,
    agent_id: u32,
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
    for &(neighbor_id, nx, ny) in neighbor_positions {
        let dx = agent_x - nx; // AWAY from neighbor
        let dy = agent_y - ny;
        let dist = (dx * dx + dy * dy).sqrt();
        if dist > REPULSION_RADIUS {
            continue;
        }
        let (dir_x, dir_y, force);
        if dist < REPULSION_MIN_DIST {
            // Deterministic zero-distance fallback
            let mut angle = ((agent_id ^ neighbor_id) % 360) as f32
                * (std::f32::consts::PI / 180.0);
            if agent_id < neighbor_id {
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

/// Two-pass spatial drift for all alive agents.
/// Reads old positions, computes new positions, writes back.
pub fn spatial_drift_step(
    pool: &mut AgentPool,
    grids: &[SpatialGrid],
    attractors: &[RegionAttractors],
    diag: &mut SpatialDiagnostics,
) {
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

    // Attractor occupancy — count agents within radius 0.1 of each attractor
    let attractor_radius = 0.1f32;
    for (r, att) in attractors.iter().enumerate() {
        for a_idx in 0..att.count as usize {
            let (ax, ay) = att.positions[a_idx];
            let mut count = 0u32;
            let mut total_agents = 0u32;
            // Count agents in this region near this attractor
            if r < grids.len() {
                for cell in &grids[r].cells {
                    for &slot in cell {
                        total_agents += 1;
                        let dx = pool.x[slot as usize] - ax;
                        let dy = pool.y[slot as usize] - ay;
                        if dx * dx + dy * dy <= attractor_radius * attractor_radius {
                            count += 1;
                        }
                    }
                }
            }
            diag.attractor_occupancy[r][a_idx] = if total_agents > 0 { count as f32 / total_agents as f32 } else { 0.0 };
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
    // 1. Snapshot all (x, y) into scratch buffers
    let old_x: Vec<f32> = pool.x[..cap].to_vec();
    let old_y: Vec<f32> = pool.y[..cap].to_vec();

    // 2. Compute new positions for each alive agent, storing results
    let mut new_x = old_x.clone();
    let mut new_y = old_y.clone();

    for slot in 0..cap {
        if !pool.is_alive(slot) {
            continue;
        }
        let region = pool.regions[slot] as usize;
        if region >= grids.len() || region >= attractors.len() {
            continue;
        }

        // Query grid for neighbors using OLD positions (grid was built from old positions)
        let neighbor_slots = grids[region].query_neighbors(old_x[slot], old_y[slot], slot as u32);

        // Build neighbor_positions from the SNAPSHOT (old positions)
        let neighbor_positions: Vec<(u32, f32, f32)> = neighbor_slots
            .iter()
            .map(|&ns| (ns, old_x[ns as usize], old_y[ns as usize]))
            .collect();

        let (nx, ny) = compute_drift_for_agent(
            old_x[slot],
            old_y[slot],
            pool.occupations[slot],
            pool.ids[slot],
            &attractors[region],
            &neighbor_positions,
        );
        new_x[slot] = nx;
        new_y[slot] = ny;
    }

    // 3. Write all new positions back to pool
    for slot in 0..cap {
        if pool.is_alive(slot) {
            pool.x[slot] = new_x[slot];
            pool.y[slot] = new_y[slot];
        }
    }
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

    let mut rng = ChaCha8Rng::from_seed(*master_seed);
    rng.set_stream(
        agent_id as u64 * 1000
            + dest_region_id as u64 * 100
            + turn as u64
            + SPATIAL_POSITION_STREAM_OFFSET,
    );
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
    let mut rng = ChaCha8Rng::from_seed(*master_seed);
    rng.set_stream(
        child_id as u64 * 1000
            + region_id as u64 * 100
            + turn as u64
            + SPATIAL_POSITION_STREAM_OFFSET,
    );
    let jx: f32 = rng.gen::<f32>() * 2.0 * BIRTH_JITTER - BIRTH_JITTER;
    let jy: f32 = rng.gen::<f32>() * 2.0 * BIRTH_JITTER - BIRTH_JITTER;

    let x = (parent_pos.0 + jx).clamp(0.0, POS_MAX);
    let y = (parent_pos.1 + jy).clamp(0.0, POS_MAX);
    (x, y)
}

/// Compute an entry position for a merchant transiting into `to_region` from `from_region`.
/// TODO(Task 9): Replace placeholder with proper edge-biased position based on
/// relative region layout. Currently returns center (0.5, 0.5).
pub fn transit_entry_position(_seed: u64, _to_region: u16, _from_region: u16) -> (f32, f32) {
    (0.5, 0.5)
}
