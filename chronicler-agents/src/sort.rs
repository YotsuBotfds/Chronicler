//! Index-sort infrastructure: radix sort on u64 keys, region-key and Morton Z-curve orderings.

use crate::pool::AgentPool;

pub const SPATIAL_SORT_AGENT_THRESHOLD: usize = 100_000; // [CALIBRATE M61b]

/// Interleave 8-bit x and y into 16-bit Morton/Z-curve code.
pub fn morton_interleave(x: u8, y: u8) -> u16 {
    let mut x32 = x as u32;
    let mut y32 = y as u32;
    // Standard bit-interleave for 8-bit inputs
    x32 = (x32 | (x32 << 8)) & 0x00FF00FF;
    x32 = (x32 | (x32 << 4)) & 0x0F0F0F0F;
    x32 = (x32 | (x32 << 2)) & 0x33333333;
    x32 = (x32 | (x32 << 1)) & 0x55555555;
    y32 = (y32 | (y32 << 8)) & 0x00FF00FF;
    y32 = (y32 | (y32 << 4)) & 0x0F0F0F0F;
    y32 = (y32 | (y32 << 2)) & 0x33333333;
    y32 = (y32 | (y32 << 1)) & 0x55555555;
    (x32 | (y32 << 1)) as u16
}

/// Stable radix sort on u64 keys. Returns sorted indices (not the keys themselves).
/// Processes 8 bits at a time (LSD radix sort, 8 passes of 256 buckets).
pub fn radix_sort_u64(keys: &[u64]) -> Vec<usize> {
    let n = keys.len();
    if n == 0 {
        return Vec::new();
    }

    let mut indices: Vec<usize> = (0..n).collect();
    let mut scratch: Vec<usize> = vec![0; n];

    for pass in 0..8u32 {
        let shift = pass * 8;
        let mut counts = [0u32; 256];

        // Count occurrences
        for &idx in &indices {
            let byte = ((keys[idx] >> shift) & 0xFF) as usize;
            counts[byte] += 1;
        }

        // Prefix sum
        let mut offsets = [0u32; 256];
        let mut running = 0u32;
        for i in 0..256 {
            offsets[i] = running;
            running += counts[i];
        }

        // Scatter
        for &idx in &indices {
            let byte = ((keys[idx] >> shift) & 0xFF) as usize;
            scratch[offsets[byte] as usize] = idx;
            offsets[byte] += 1;
        }

        std::mem::swap(&mut indices, &mut scratch);
    }

    indices
}

/// Region-key sort: (region_index << 32) | agent_id
/// Groups agents by region, tiebroken by agent_id.
pub fn sort_by_region(pool: &AgentPool) -> Vec<usize> {
    let mut keys = Vec::new();
    let mut slots = Vec::new();

    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            let key = ((pool.regions[slot] as u64) << 32) | (pool.ids[slot] as u64);
            keys.push(key);
            slots.push(slot);
        }
    }

    let sorted_indices = radix_sort_u64(&keys);
    sorted_indices.iter().map(|&i| slots[i]).collect()
}

/// Morton sort: (region_index << 48) | (morton << 32) | agent_id
/// Groups by region, then by spatial locality (Z-curve), tiebroken by agent_id.
pub fn sort_by_morton(pool: &AgentPool) -> Vec<usize> {
    let mut keys = Vec::new();
    let mut slots = Vec::new();

    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            let qx = (pool.x[slot].clamp(0.0, 1.0 - f32::EPSILON) * 256.0) as u8;
            let qy = (pool.y[slot].clamp(0.0, 1.0 - f32::EPSILON) * 256.0) as u8;
            let morton = morton_interleave(qx, qy) as u64;
            let key = ((pool.regions[slot] as u64) << 48)
                | (morton << 32)
                | (pool.ids[slot] as u64);
            keys.push(key);
            slots.push(slot);
        }
    }

    let sorted_indices = radix_sort_u64(&keys);
    sorted_indices.iter().map(|&i| slots[i]).collect()
}

/// Public entry point. Below threshold: identity (alive slots in ascending order).
/// Above: Morton sort.
pub fn sorted_iteration_order(pool: &AgentPool) -> Vec<usize> {
    if pool.alive_count() < SPATIAL_SORT_AGENT_THRESHOLD {
        // Identity order: alive slots in ascending slot index
        (0..pool.capacity()).filter(|&s| pool.is_alive(s)).collect()
    } else {
        sort_by_morton(pool)
    }
}
