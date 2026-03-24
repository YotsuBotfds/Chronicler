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
    ((h >> 33) as f32) / (u32::MAX as f32)
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

    // Enforce minimum separation: up to 20 iterations.
    // Symmetric push: both attractors move apart. If one is boundary-clamped,
    // try orthogonal displacement to escape.
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
