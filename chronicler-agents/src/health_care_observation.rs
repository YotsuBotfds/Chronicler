//! Dormant care evidence: bounded primitive copies, never an input to physics.
//!
//! The saved bytes are a provisional CAREOBS1 native prefix. COMPLETE and the
//! Python stage bits are always clear. Only the later independent Python join
//! can bind entry/exit turns, predecessor and episodes within the same byte cap.
use crate::{health_care::{CarePolicy, HealthWork}, pool::AgentPool, region::RegionState};

pub(crate) const BYTE_CAP: usize = 131_072;
pub(crate) const ROW_CAP: usize = 4_096;
pub(crate) const REL_CAP: usize = 32_768;
const HEADER: usize = 256;
const NONE: u32 = u32::MAX;
const OFFSET_BITS: u32 = 18;
const OFFSET_MASK: u32 = (1 << OFFSET_BITS) - 1;

/// One enabled recorder owns exactly three bounded primitive allocations.
/// The AgentPool field is None by default and after persistence restoration.
pub struct CareObservation {
    bytes: Vec<u8>,
    id_slots: Vec<u64>,
    scope_offsets: Vec<u32>,
    manifest: [u8; 32],
    start_turn: u32,
    turns: u32,
    regions: usize,
    next_ordinal: u32,
    ordinal: u32,
    started: bool,
    sealed: bool,
    failure: u16,
    stage: u8,
    calls: [u8; 4],
    counts: [u32; 16],
    policy: u8,
    finish_turn: u32,
    prepare_regions_offset: usize,
    economy_rows: usize,
    economy_row_offset: usize,
    economy_outputs: usize,
    economy_outputs_started: bool,
    wealth_closed: bool,
    wealth_header_offset: usize,
    wealth_capacity: usize,
    visited: usize,
    scoped_visited: usize,
    unscoped_visited: usize,
}

impl CareObservation {
    /// Allocation failure leaves recording unavailable, without entering physics.
    pub(crate) fn configure(start_turn: u32, turns: u32, regions: usize,
                            manifest: [u8; 32]) -> Option<Self> {
        if turns == 0 || turns > 32 || regions > ROW_CAP
            || start_turn.checked_add(turns - 1).is_none() { return None; }
        let mut bytes = Vec::new();
        let mut id_slots = Vec::new();
        let mut scope_offsets = Vec::new();
        bytes.try_reserve_exact(BYTE_CAP).ok()?;
        id_slots.try_reserve_exact(ROW_CAP).ok()?;
        scope_offsets.try_reserve_exact(ROW_CAP).ok()?;
        Some(Self { bytes, id_slots, scope_offsets, manifest, start_turn, turns, regions,
            next_ordinal: 0, ordinal: 0, started: false, sealed: false, failure: 0,
            stage: 0, calls: [0; 4], counts: [0; 16], policy: 0, finish_turn: 0,
            prepare_regions_offset: 0, economy_rows: 0, economy_row_offset: 0,
            economy_outputs: 0, economy_outputs_started: false, wealth_closed: false,
            wealth_header_offset: 0, wealth_capacity: 0,
            visited: 0, scoped_visited: 0, unscoped_visited: 0 })
    }

    pub(crate) fn saved_bytes(&self) -> Option<&[u8]> {
        if self.sealed { Some(&self.bytes) } else { None }
    }

    fn fault(&mut self, code: u16) { if self.failure == 0 { self.failure = code; } }
    fn count(&mut self, index: usize, n: usize) -> bool {
        let cap = if index == 15 { REL_CAP } else { ROW_CAP };
        if n > cap { self.fault(1); return false; }
        self.counts[index] = n as u32;
        true
    }
    fn stage(&mut self, bit: u8, call: usize, expected: u8) {
        match self.calls[call].checked_add(1) {
            Some(n) => self.calls[call] = n,
            None => self.fault(6),
        }
        if self.stage != expected || self.calls[call] != 1 { self.fault(6); }
        self.stage |= bit;
        self.sealed = false;
    }
    fn append(&mut self, data: &[u8]) {
        if self.failure != 0 { return; }
        let Some(end) = self.bytes.len().checked_add(data.len()) else { self.fault(2); return; };
        if end > BYTE_CAP || end > self.bytes.capacity() { self.fault(2); return; }
        self.bytes.extend_from_slice(data);
    }
    fn u8(&mut self, x: u8) { self.append(&[x]); }
    fn u16(&mut self, x: u16) { self.append(&x.to_le_bytes()); }
    fn u32(&mut self, x: u32) { self.append(&x.to_le_bytes()); }
    fn f32(&mut self, x: f32) { self.u32(x.to_bits()); }
    fn f64(&mut self, x: f64) { self.append(&x.to_bits().to_le_bytes()); }
    fn patch(&mut self, offset: usize, data: &[u8]) {
        if self.failure != 0 { return; }
        let Some(end) = offset.checked_add(data.len()) else { self.fault(4); return; };
        if end > self.bytes.len() { self.fault(4); return; }
        self.bytes[offset..end].copy_from_slice(data);
    }
    fn raw_u32(&self, offset: usize) -> Option<u32> {
        let end = offset.checked_add(4)?;
        Some(u32::from_le_bytes(self.bytes.get(offset..end)?.try_into().ok()?))
    }
    fn idref(&mut self, id: u32) {
        if id == 0 { self.u16(0); return; }
        let key = (id as u64) << 16;
        let index = self.id_slots.partition_point(|&entry| entry < key);
        match self.id_slots.get(index).copied() {
            Some(entry) if entry >> 16 == id as u64 => self.u16((entry as u16) + 1),
            _ => { self.u16(u16::MAX); self.u32(id); }
        }
    }
    fn bitmap(&mut self, alive: &[bool]) {
        for chunk in alive.chunks(8) {
            let mut bits = 0;
            for (i, &value) in chunk.iter().enumerate() { if value { bits |= 1 << i; } }
            self.u8(bits);
        }
    }

    pub(crate) fn prepare(&mut self, pool: &AgentPool, work: &HealthWork,
                         ids: &[u32], excluded: &[u32], urban: &[u16], regions: usize,
                         impairment: f32, care_fraction: f32, policy: CarePolicy) {
        if self.started && !self.sealed { self.stage(1, 0, 0); return; }
        if self.next_ordinal >= self.turns {
            self.fault(8); self.stage(1, 0, 0); return;
        }
        self.ordinal = self.next_ordinal;
        self.next_ordinal += 1; // configure bounds this at 32
        self.started = true;
        self.sealed = false;
        // A failed ordinal cannot be healed by starting another frame.
        if self.failure != 0 { self.stage(1, 0, 0); return; }
        self.bytes.clear(); self.bytes.resize(HEADER, 0);
        self.id_slots.clear(); self.scope_offsets.clear();
        self.stage = 0; self.calls = [0; 4]; self.counts = [0; 16];
        self.economy_rows = 0; self.economy_outputs = 0; self.finish_turn = 0;
        self.economy_outputs_started = false; self.wealth_closed = false;
        self.policy = if policy == CarePolicy::Spouse { 0 } else { 1 };
        self.stage(1, 0, 0);
        let n = pool.capacity();
        if !self.count(0, n) || !self.count(1, regions) || !self.count(2, ids.len())
            || !self.count(3, excluded.len()) || !self.count(4, urban.len())
            || !self.count(5, work.workers.len()) || !self.count(6, work.rows.len()) { return; }
        if regions != self.regions || work.losses.len() != regions || work.impaired.len() != regions
            || work.care.len() != regions || work.recipients.len() != regions
            || work.worked.len() != regions || work.patients.len() != work.rows.len()
            || [pool.ages.len(), pool.regions.len(), pool.settlement_ids.len(),
                pool.occupations.len(), pool.trip_phase.len(), pool.rel_count.len(),
                pool.rel_bond_types.len(), pool.rel_target_ids.len(), pool.alive.len()]
                .iter().any(|&length| length != n) { self.fault(4); return; }
        if work.patients.iter().zip(&work.rows).any(|(&id, row)| id != row.0)
            || work.worked.iter().any(|&worked| worked) { self.fault(5); return; }
        let mut active = 0usize;
        let mut relevant = 0usize;
        for slot in 0..n {
            let count = pool.rel_count[slot] as usize;
            if count > crate::relationships::REL_SLOTS { self.fault(4); return; }
            let Some(total) = active.checked_add(count) else { self.fault(1); return; };
            active = total;
            if active > REL_CAP { self.fault(1); return; }
            for i in 0..count {
                let kind = pool.rel_bond_types[slot][i];
                if kind == 2 || kind == 5 { relevant += 1; }
            }
            self.id_slots.push(((pool.ids[slot] as u64) << 16) | slot as u64);
        }
        if !self.count(15, relevant) { return; }
        self.id_slots.sort_unstable(); // in-place; canonical smallest physical slot
        self.f32(impairment); self.f32(care_fraction);
        for &id in ids { self.idref(id); }
        for &id in excluded { self.idref(id); }
        for &id in urban { self.u16(id); }
        for &id in &pool.ids { self.u32(id); }
        for &age in &pool.ages { self.u16(age); }
        for &region in &pool.regions { self.u16(region); }
        for &settlement in &pool.settlement_ids { self.u16(settlement); }
        self.append(&pool.occupations); self.append(&pool.trip_phase); self.append(&pool.rel_count);
        for kind in [2, 5] {
            for slot in 0..n {
                let mut mask = 0u8;
                for i in 0..pool.rel_count[slot] as usize {
                    if pool.rel_bond_types[slot][i] == kind { mask |= 1 << i; }
                }
                self.u8(mask);
            }
        }
        self.bitmap(&pool.alive);
        // Exhaust every active position. Only source-proven non-2/non-5 fields
        // are elided; zeros, self targets and every duplicate remain in order.
        for slot in 0..n {
            for i in 0..pool.rel_count[slot] as usize {
                let kind = pool.rel_bond_types[slot][i];
                if kind == 2 || kind == 5 { self.idref(pool.rel_target_ids[slot][i]); }
            }
        }
        for worker in &work.workers {
            if worker.slot >= n || worker.id != pool.ids[worker.slot]
                || worker.region != pool.regions[worker.slot] as usize { self.fault(5); return; }
            self.u16(worker.slot as u16); self.f32(worker.available);
        }
        for &(patient, region, giver, care) in &work.rows {
            self.idref(patient); self.u16(region); self.idref(giver); self.f32(care);
        }
        self.prepare_regions_offset = self.bytes.len();
        for r in 0..regions {
            self.f32(work.losses[r]); self.f64(work.impaired[r]); self.f64(work.care[r]);
            self.u32(work.recipients[r]);
        }
    }

    pub(crate) fn economy_begin(&mut self, regions: usize) {
        self.stage(2, 1, 1);
        if regions != self.regions { self.fault(4); }
    }
    pub(crate) fn economy_before(&mut self, r: usize, farmers: u32, factor: f32, loss: Option<f32>) {
        if self.failure != 0 { return; }
        if self.stage != 3 || self.economy_outputs_started { self.fault(6); return; }
        if r != self.economy_rows || r >= self.regions { self.fault(4); return; }
        let Some(loss) = loss else { self.fault(4); return; };
        let offset = r.checked_mul(24).and_then(|row| self.prepare_regions_offset.checked_add(row));
        if offset.and_then(|o| self.raw_u32(o)) != Some(loss.to_bits()) { self.fault(5); return; }
        self.economy_row_offset = self.bytes.len();
        self.u32(farmers); self.f32(factor); self.f32(factor); self.u8(0);
        self.economy_rows += 1;
    }
    pub(crate) fn economy_adjusted(&mut self, factor: f32) {
        if self.failure != 0 { return; }
        if self.stage != 3 || self.economy_rows == 0 || self.economy_outputs_started
            || self.bytes.get(self.economy_row_offset + 12) != Some(&0) {
            self.fault(6); return;
        }
        let offset = self.economy_row_offset;
        self.patch(offset + 8, &factor.to_bits().to_le_bytes()); self.patch(offset + 12, &[1]);
    }
    pub(crate) fn economy_outputs_begin(&mut self, outputs: usize) {
        if self.stage != 3 || self.economy_outputs_started { self.fault(6); }
        self.economy_outputs_started = true;
        if self.economy_rows != self.regions { self.fault(7); }
        self.count(9, outputs);
        if outputs != self.regions { self.fault(4); }
    }
    pub(crate) fn economy_output(&mut self, region: u16, slots: [f32; 3], forage: f32,
                                worked: Option<bool>) {
        if self.failure != 0 { return; }
        if self.stage != 3 || !self.economy_outputs_started { self.fault(6); return; }
        if self.economy_outputs >= self.counts[9] as usize { self.fault(4); return; }
        let Some(worked) = worked else { self.fault(4); return; };
        self.u16(region);
        for value in slots { self.f32(value); }
        self.f32(forage); self.u8(worked as u8);
        self.economy_outputs += 1;
    }

    pub(crate) fn wealth_begin(&mut self, pool: &AgentPool, regions: &[RegionState],
                               losses: &[(u32, f32)]) {
        self.stage(4, 2, 3);
        self.wealth_closed = false;
        if !self.economy_outputs_started || self.economy_outputs != self.counts[9] as usize { self.fault(7); }
        let n = pool.capacity();
        if !self.count(7, losses.len()) || n > ROW_CAP { self.fault(1); return; }
        if regions.len() != self.regions || [pool.regions.len(), pool.occupations.len(),
                pool.alive.len(), pool.wealth.len()].iter().any(|&length| length != n) {
            self.fault(4); return;
        }
        if self.failure != 0 { return; }
        self.wealth_capacity = n; self.visited = 0; self.scoped_visited = 0; self.unscoped_visited = 0;
        self.scope_offsets.resize(n, NONE);
        self.wealth_header_offset = self.bytes.len();
        self.u16(n as u16); self.u16(0); self.u16(0); self.u16(0);
        let mut scoped = 0;
        for (slot, &(id, loss)) in losses.iter().enumerate() {
            if id == 0 && loss.to_bits() == 0 { continue; }
            scoped += 1;
            self.u16(slot as u16); self.idref(id); self.f32(loss);
            let exists = slot < n;
            let alive = exists && pool.alive[slot];
            let valid = exists && (pool.regions[slot] as usize) < regions.len();
            self.u32(if exists { pool.ids[slot] } else { 0 });
            self.u16(if exists { pool.regions[slot] } else { 0 });
            self.u8(if exists { pool.occupations[slot] } else { 0 });
            self.u8(exists as u8 | ((alive as u8) << 1) | ((valid as u8) << 2));
            let reason = if !exists { 6 } else if !alive { 4 } else if !valid { 5 }
                else if pool.occupations[slot] != 0 { 3 } else if id != pool.ids[slot] { 2 }
                else if loss == 0.0 { 1 } else { 0 };
            self.u8(reason);
            let mask = if !exists { 0 } else if alive && valid { 63 } else { 33 };
            self.u8(mask);
            let numeric_offset = self.bytes.len();
            let pre = if exists { pool.wealth[slot] } else { 0.0 };
            self.f32(pre);
            for _ in 0..4 { self.u32(0); }
            self.f32(if exists && (!alive || !valid) { pre } else { 0.0 });
            if self.failure != 0 { return; }
            if exists {
                // Upper bits track which actual sites supplied numeric witnesses.
                let seen = if mask == 33 { 33u32 } else { 1u32 };
                self.scope_offsets[slot] = numeric_offset as u32 | (seen << OFFSET_BITS);
            }
        }
        self.count(8, scoped);
        for region in regions {
            self.f32(region.resource_yields[0]); self.f32(region.farmer_income_modifier);
            self.f32(region.farm_productivity);
        }
    }
    pub(crate) fn wealth_visit(&mut self, slot: usize) {
        if self.failure != 0 { return; }
        if slot != self.visited || slot >= self.wealth_capacity { self.fault(5); return; }
        self.visited += 1;
        if self.scope_offsets[slot] == NONE { self.unscoped_visited += 1; }
        else { self.scoped_visited += 1; }
    }
    pub(crate) fn wealth_value(&mut self, slot: usize, number: u32, value: f32) {
        if self.failure != 0 { return; }
        if number == 0 || number > 5 || slot >= self.scope_offsets.len() { self.fault(4); return; }
        let entry = self.scope_offsets[slot];
        if entry == NONE { return; }
        let seen = entry >> OFFSET_BITS;
        let bit = 1 << number;
        if seen & bit != 0 { self.fault(5); return; }
        let offset = (entry & OFFSET_MASK) as usize;
        self.patch(offset + number as usize * 4, &value.to_bits().to_le_bytes());
        if self.failure == 0 { self.scope_offsets[slot] = entry | (bit << OFFSET_BITS); }
    }
    pub(crate) fn wealth_end(&mut self) {
        if self.failure != 0 { return; }
        if self.stage != 7 || self.wealth_closed { self.fault(6); return; }
        if self.visited != self.wealth_capacity
            || self.scoped_visited.checked_add(self.unscoped_visited) != Some(self.wealth_capacity) {
            self.fault(7); return;
        }
        for slot in 0..self.scope_offsets.len() {
            let entry = self.scope_offsets[slot];
            if entry == NONE { continue; }
            let offset = (entry & OFFSET_MASK) as usize;
            let expected = offset.checked_sub(1).and_then(|o| self.bytes.get(o)).copied();
            if expected != Some((entry >> OFFSET_BITS) as u8) { self.fault(7); return; }
        }
        let offset = self.wealth_header_offset;
        self.patch(offset + 2, &(self.visited as u16).to_le_bytes());
        self.patch(offset + 4, &(self.scoped_visited as u16).to_le_bytes());
        self.patch(offset + 6, &(self.unscoped_visited as u16).to_le_bytes());
        self.wealth_closed = self.failure == 0;
    }

    pub(crate) fn finish(&mut self, pool: &AgentPool, turn: u32, rate: f32,
                         result: &(Vec<(u32, u16)>, Vec<(u32, u16, u16)>, Vec<(u16, f64, f64, u32)>)) {
        if !self.started { self.tombstone(); self.fault(7); }
        if self.stage & 8 != 0 { self.fault(6); }
        else if self.stage != 7 || !self.wealth_closed { self.fault(7); }
        self.stage(8, 3, 7);
        self.finish_turn = turn;
        if self.start_turn.checked_add(self.ordinal) != Some(turn) { self.fault(8); }
        let n = pool.capacity();
        if n > ROW_CAP { self.fault(1); }
        if !self.count(10, result.0.len()) || !self.count(11, result.1.len())
            || !self.count(12, result.2.len()) { self.seal(); return; }
        if result.2.len() != self.regions || pool.regions.len() != n || pool.alive.len() != n {
            self.fault(4);
        }
        if self.failure == 0 {
            self.u32(turn); self.f32(rate); self.u16(n as u16);
            for &id in &pool.ids { self.u32(id); }
            for &region in &pool.regions { self.u16(region); }
            self.bitmap(&pool.alive);
            for &(id, region) in &result.0 { self.idref(id); self.u16(region); }
            for &(id, work_region, current_region) in &result.1 {
                self.idref(id); self.u16(work_region); self.u16(current_region);
            }
            for &(region, impaired, care, recipients) in &result.2 {
                self.u16(region); self.f64(impaired); self.f64(care); self.u32(recipients);
            }
        }
        self.seal();
    }
    pub(crate) fn missing_finish(&mut self, turn: u32) {
        if !self.started { self.tombstone(); }
        if self.stage & 8 != 0 { self.fault(6); } else { self.fault(7); }
        self.stage(8, 3, 7); self.finish_turn = turn; self.seal();
    }
    fn tombstone(&mut self) {
        self.bytes.clear(); self.bytes.resize(HEADER, 0); self.started = true;
    }
    fn seal(&mut self) {
        if self.bytes.len() < HEADER { self.tombstone(); self.fault(7); }
        // Header writes are bounded even after a payload fault. COMPLETE stays 0.
        self.bytes[..HEADER].fill(0);
        self.bytes[0..8].copy_from_slice(b"CAREOBS1");
        self.bytes[8..10].copy_from_slice(&1u16.to_le_bytes());
        self.bytes[10..12].copy_from_slice(&(HEADER as u16).to_le_bytes());
        self.bytes[12..16].copy_from_slice(&(if self.failure == 0 { 0u32 } else { 4u32 }).to_le_bytes());
        self.bytes[16..20].copy_from_slice(&self.finish_turn.to_le_bytes());
        let length = self.bytes.len() as u32;
        self.bytes[20..24].copy_from_slice(&length.to_le_bytes());
        self.bytes[24] = self.stage; self.bytes[25] = self.policy;
        self.bytes[26..28].copy_from_slice(&self.failure.to_le_bytes());
        for (i, count) in self.counts.iter().enumerate() {
            self.bytes[28 + i * 4..32 + i * 4].copy_from_slice(&count.to_le_bytes());
        }
        self.bytes[92..124].copy_from_slice(&self.manifest);
        // Provisional digest slot stays zero; the final join hashes the full body.
        self.bytes[196..200].copy_from_slice(&self.calls);
        self.bytes[200..204].copy_from_slice(&self.ordinal.to_le_bytes());
        self.sealed = true;
    }
}

#[cfg(test)]
#[path = "health_care_observation_tests.rs"]
mod tests;
