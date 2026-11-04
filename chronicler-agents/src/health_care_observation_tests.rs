//! Source-only contracts: these tests require the instrumented crate's own fresh
//! build before they can supply evidence. They were not executed during authoring.
use super::*;
use crate::{agent, health_care, Occupation};

fn farmer(pool: &mut AgentPool, region: u16) -> usize {
    pool.spawn(region, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, agent::BELIEF_NONE)
}
fn edge(pool: &mut AgentPool, source: usize, kind: u8, target: u32) {
    let i = pool.rel_count[source] as usize;
    pool.rel_bond_types[source][i] = kind;
    pool.rel_target_ids[source][i] = target;
    pool.rel_count[source] += 1;
}
fn recorder(regions: usize) -> CareObservation {
    CareObservation::configure(20, 32, regions, [0xa5; 32]).unwrap()
}
fn count(bytes: &[u8], i: usize) -> usize {
    u32::from_le_bytes(bytes[28 + 4 * i..32 + 4 * i].try_into().unwrap()) as usize
}
fn failure(bytes: &[u8]) -> u16 { u16::from_le_bytes(bytes[26..28].try_into().unwrap()) }
fn assert_prefix(bytes: &[u8], code: u16) {
    assert_eq!(&bytes[..8], b"CAREOBS1");
    assert_eq!(u16::from_le_bytes(bytes[8..10].try_into().unwrap()), 1);
    assert_eq!(u16::from_le_bytes(bytes[10..12].try_into().unwrap()), 256);
    assert_eq!(failure(bytes), code);
    assert_eq!(u32::from_le_bytes(bytes[20..24].try_into().unwrap()) as usize, bytes.len());
    assert!(bytes.len() <= 131_072);
    assert_eq!(bytes[12] & 1, 0); // native evidence can never claim joined completeness
    assert_eq!(bytes[24] & 48, 0);
    assert_eq!(bytes[12] & 4, if code == 0 { 0 } else { 4 });
    assert!(bytes[124..196].iter().all(|&x| x == 0)); // provisional predecessor/body hash/entry-exit
    assert!(bytes[204..256].iter().all(|&x| x == 0));
}

/// Deliberately follows the published byte layout, rather than recorder offsets.
struct Decode<'a> { bytes: &'a [u8], at: usize, ids: Vec<u32> }
impl<'a> Decode<'a> {
    fn u8(&mut self) -> u8 { let x = self.bytes[self.at]; self.at += 1; x }
    fn u16(&mut self) -> u16 {
        let x = u16::from_le_bytes(self.bytes[self.at..self.at + 2].try_into().unwrap());
        self.at += 2; x
    }
    fn u32(&mut self) -> u32 {
        let x = u32::from_le_bytes(self.bytes[self.at..self.at + 4].try_into().unwrap());
        self.at += 4; x
    }
    fn u64(&mut self) -> u64 {
        let x = u64::from_le_bytes(self.bytes[self.at..self.at + 8].try_into().unwrap());
        self.at += 8; x
    }
    fn raw_ref(&mut self) -> (u16, Option<u32>) {
        let tag = self.u16();
        (tag, if tag == 65535 { Some(self.u32()) } else { None })
    }
    fn resolve(&self, value: (u16, Option<u32>)) -> u32 {
        match value { (0, None) => 0, (65535, Some(x)) => x,
            (tag, None) => self.ids[tag as usize - 1], _ => panic!("invalid IDref") }
    }
    fn idref(&mut self) -> u32 { let value = self.raw_ref(); self.resolve(value) }
    fn skip(&mut self, bytes: usize) { self.at += bytes; assert!(self.at <= self.bytes.len()); }
}
#[derive(Debug)]
struct Preparation {
    inputs: Vec<u32>, excluded: Vec<u32>, urban: Vec<u16>,
    ids: Vec<u32>, regions: Vec<u16>, marriage: Vec<u8>, kin: Vec<u8>,
    alive: Vec<u8>, targets: Vec<u32>, workers: Vec<(u16, u32)>,
    assignments: Vec<(u32, u16, u32, u32)>,
}
fn preparation(bytes: &[u8]) -> (Preparation, Decode<'_>) {
    let n = count(bytes, 0);
    let mut d = Decode { bytes, at: 256, ids: Vec::new() };
    d.skip(8); // raw constants
    let inputs = (0..count(bytes, 2)).map(|_| d.raw_ref()).collect::<Vec<_>>();
    let excluded = (0..count(bytes, 3)).map(|_| d.raw_ref()).collect::<Vec<_>>();
    let urban = (0..count(bytes, 4)).map(|_| d.u16()).collect();
    d.ids = (0..n).map(|_| d.u32()).collect();
    d.skip(2 * n); // ages
    let regions = (0..n).map(|_| d.u16()).collect();
    d.skip(2 * n); // settlements
    d.skip(3 * n); // occupation, trip, raw relationship count
    let marriage = (0..n).map(|_| d.u8()).collect();
    let kin = (0..n).map(|_| d.u8()).collect();
    let alive = (0..n.div_ceil(8)).map(|_| d.u8()).collect();
    let targets = (0..count(bytes, 15)).map(|_| d.idref()).collect();
    let workers = (0..count(bytes, 5)).map(|_| (d.u16(), d.u32())).collect();
    let assignments = (0..count(bytes, 6)).map(|_| (d.idref(), d.u16(), d.idref(), d.u32())).collect();
    d.skip(24 * count(bytes, 1));
    let inputs = inputs.into_iter().map(|x| d.resolve(x)).collect();
    let excluded = excluded.into_iter().map(|x| d.resolve(x)).collect();
    (Preparation { inputs, excluded, urban, ids: d.ids.clone(), regions, marriage, kin,
        alive, targets, workers, assignments }, d)
}
fn economy(rec: &mut CareObservation, work: &HealthWork) {
    rec.economy_begin(work.losses.len());
    for (r, &loss) in work.losses.iter().enumerate() {
        rec.economy_before(r, 0, 1.0, Some(loss));
    }
    rec.economy_outputs_begin(work.losses.len());
    for r in 0..work.losses.len() {
        rec.economy_output(r as u16, [0.0; 3], 0.0, Some(false));
    }
}
fn complete_empty(rec: &mut CareObservation, turn: u32) {
    let pool = AgentPool::new(0);
    let work = HealthWork::default();
    rec.prepare(&pool, &work, &[], &[], &[], 0, 0.0, 0.0, CarePolicy::Spouse);
    economy(rec, &work);
    rec.wealth_begin(&pool, &[], &[]);
    rec.wealth_end();
    rec.finish(&pool, turn, 0.0, &(vec![], vec![], vec![]));
}

#[test]
fn disabled_recording_and_native_restore_preserve_persistence_and_schema() {
    let mut pool = AgentPool::new(4);
    let patient = farmer(&mut pool, 0);
    assert!(pool.health_care_observation.is_none());
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &pool);
    pool.health_care_observation = Some(recorder(1));
    let mut rec = pool.health_care_observation.take().unwrap();
    let id = pool.ids[patient];
    let work = health_care::prepare(&mut pool, &[id], &[], &[], 1, 0.5, 0.2);
    rec.prepare(&pool, &work, &[id], &[], &[], 1, 0.5, 0.2, CarePolicy::Spouse);
    pool.health_care_observation = Some(rec);
    assert_eq!(before, crate::persist::encode(crate::persist::KIND_AGENT, &pool));
    let restored: AgentPool = crate::persist::decode(crate::persist::KIND_AGENT, &before).unwrap();
    assert!(restored.health_care_observation.is_none());
    assert!(restored.health_work_loss.is_empty());
    assert!(!crate::persist::schema_of::<AgentPool>().contains("health_care_observation"));
    assert!(!crate::persist::schema_of::<crate::AgentSimulator>().contains("CareObservation"));
    assert!(CareObservation::configure(0, 0, 1, [0; 32]).is_none());
    assert!(CareObservation::configure(0, 33, 1, [0; 32]).is_none());
    assert!(CareObservation::configure(u32::MAX, 2, 1, [0; 32]).is_none());
    assert!(CareObservation::configure(0, 1, 4097, [0; 32]).is_none());
}

#[test]
fn actual_spouse_first_and_reciprocal_kin_rows_keep_raw_relation_order() {
    let mut pool = AgentPool::new(5);
    let p = farmer(&mut pool, 0); let q = farmer(&mut pool, 0);
    let spouse = farmer(&mut pool, 0); let kin = farmer(&mut pool, 0);
    let excluded_slot = farmer(&mut pool, 0);
    let p_id = pool.ids[p]; let q_id = pool.ids[q];
    let spouse_id = pool.ids[spouse]; let kin_id = pool.ids[kin];
    edge(&mut pool, p, 1, u32::MAX); // source-proven unrelated target is omitted
    edge(&mut pool, p, 2, spouse_id);
    edge(&mut pool, p, 5, kin_id);
    edge(&mut pool, q, 5, 0);
    edge(&mut pool, q, 5, q_id);
    edge(&mut pool, q, 5, kin_id);
    edge(&mut pool, q, 5, kin_id); // duplicate remains a raw position
    edge(&mut pool, kin, 5, p_id);
    edge(&mut pool, kin, 5, q_id);
    let input = [q_id, p_id, q_id, 9000];
    let excluded = [pool.ids[excluded_slot], pool.ids[excluded_slot]];
    let urban = [0, 42, 42];
    let mut rec = recorder(1);
    let work = health_care::prepare_with_policy(&mut pool, &input, &excluded, &urban,
        1, 0.5, 0.2, CarePolicy::RetainedKin);
    assert_eq!(work.rows, vec![(p_id, 0, spouse_id, 0.2), (q_id, 0, kin_id, 0.2)]);
    rec.prepare(&pool, &work, &input, &excluded, &urban, 1, 0.5, 0.2, CarePolicy::RetainedKin);
    assert_eq!(rec.failure, 0);
    let expected_assignments = work.rows.iter().map(|r| (r.0, r.1, r.2, r.3.to_bits())).collect::<Vec<_>>();
    let expected_workers = work.workers.iter().map(|w| (w.slot as u16, w.available.to_bits())).collect::<Vec<_>>();
    economy(&mut rec, &work);
    pool.health_care_observation = Some(rec);
    let signals = crate::signals::TickSignals { civs: vec![], contested_regions: vec![false] };
    let mut ranks = vec![0.0; pool.capacity()];
    crate::tick::wealth_tick(&mut pool, &[RegionState::new(0)], &signals, &mut ranks);
    let mut rec = pool.health_care_observation.take().unwrap();
    let result = health_care::finish(work, &pool, [42; 32], 20, 0.0);
    rec.finish(&pool, 20, 0.0, &result);
    let bytes = rec.saved_bytes().unwrap();
    assert_prefix(bytes, 0);
    assert_eq!(bytes[25], 1);
    let (got, _) = preparation(bytes);
    assert_eq!(got.inputs, input);
    assert_eq!(got.excluded, excluded);
    assert_eq!(got.urban, urban);
    assert_eq!(got.ids, pool.ids);
    assert_eq!(got.regions, pool.regions);
    assert_eq!(got.marriage, vec![2, 0, 0, 0, 0]);
    assert_eq!(got.kin, vec![4, 15, 0, 3, 0]);
    assert_eq!(got.targets, vec![spouse_id, kin_id, 0, q_id, kin_id, kin_id, p_id, q_id]);
    assert_eq!(got.assignments, expected_assignments);
    assert_eq!(got.workers, expected_workers);
    assert_eq!(got.alive, vec![31]);
}

#[test]
fn dictionary_restores_raw_zero_and_dead_duplicate_but_care_uses_last_live_slot() {
    let mut pool = AgentPool::new(4);
    let dead = farmer(&mut pool, 0); let zero = farmer(&mut pool, 0);
    let later = farmer(&mut pool, 1); farmer(&mut pool, 0);
    pool.ids[dead] = 77; pool.ids[zero] = 0; pool.ids[later] = 77;
    pool.kill(dead);
    let input = [77, 0, 77, 404];
    let work = health_care::prepare(&mut pool, &input, &[], &[], 2, 0.5, 0.0);
    assert_eq!(work.rows, vec![(0, 0, 0, 0.0), (77, 1, 0, 0.0)]);
    let mut rec = recorder(2);
    rec.prepare(&pool, &work, &input, &[], &[], 2, 0.5, 0.0, CarePolicy::Spouse);
    assert_eq!(&rec.bytes[264..276], &[1, 0, 0, 0, 1, 0, 255, 255, 148, 1, 0, 0]);
    economy(&mut rec, &work);
    let regions = [RegionState::new(0), RegionState::new(1)];
    pool.health_care_observation = Some(rec);
    let signals = crate::signals::TickSignals { civs: vec![], contested_regions: vec![false; 2] };
    let mut ranks = vec![0.0; pool.capacity()];
    crate::tick::wealth_tick(&mut pool, &regions, &signals, &mut ranks);
    let mut rec = pool.health_care_observation.take().unwrap();
    // Reuse the dead slot, then append a later live duplicate. Both boundaries
    // must retain their own complete capacity and physical slot facts.
    farmer(&mut pool, 0);
    let added = farmer(&mut pool, 0); pool.ids[added] = 77;
    let result = health_care::finish(work, &pool, [42; 32], 20, 0.0);
    assert_eq!(result.0, vec![(0, 0), (77, 0)]);
    rec.finish(&pool, 20, 0.0, &result);
    let bytes = rec.saved_bytes().unwrap();
    assert_prefix(bytes, 0);
    let (got, mut d) = preparation(bytes);
    assert_eq!(got.inputs, input);
    d.skip(13 * 2 + 19 * 2);
    d.skip(8); // coverage
    for _ in 0..count(bytes, 8) { d.skip(2); d.idref(); d.skip(38); }
    d.skip(12 * 2);
    assert_eq!(d.u32(), 20); assert_eq!(d.u32(), 0);
    let current_capacity = d.u16() as usize;
    assert_eq!(current_capacity, pool.capacity());
    let current_ids = (0..current_capacity).map(|_| d.u32()).collect::<Vec<_>>();
    let current_regions = (0..current_capacity).map(|_| d.u16()).collect::<Vec<_>>();
    let live = d.u8();
    assert_eq!(current_ids, pool.ids);
    assert_eq!(current_regions, pool.regions);
    let mut live_77 = None;
    for slot in 0..current_capacity {
        if live & (1 << slot) != 0 && current_ids[slot] == 77 { live_77 = Some(slot); }
    }
    assert_eq!(current_regions[live_77.unwrap()], 0);
    assert_eq!(d.idref(), 0); assert_eq!(d.u16(), 0);
    assert_eq!(d.idref(), 77); assert_eq!(d.u16(), 0);
    d.skip(22 * 2);
    assert_eq!(d.at, bytes.len());
}

#[derive(Debug)]
struct Scoped {
    slot: u16, consumed: u32, loss: u32, current: u32, region: u16, occupation: u8,
    flags: u8, reason: u8, mask: u8, numeric: [u32; 6],
}
fn scope<'a>(bytes: &'a [u8]) -> (Vec<Scoped>, [u16; 4], Decode<'a>) {
    let (_, mut d) = preparation(bytes);
    d.skip(13 * count(bytes, 1) + 19 * count(bytes, 9));
    let coverage = [d.u16(), d.u16(), d.u16(), d.u16()];
    let rows = (0..count(bytes, 8)).map(|_| Scoped {
        slot: d.u16(), consumed: d.idref(), loss: d.u32(), current: d.u32(),
        region: d.u16(), occupation: d.u8(), flags: d.u8(), reason: d.u8(), mask: d.u8(),
        numeric: [d.u32(), d.u32(), d.u32(), d.u32(), d.u32(), d.u32()],
    }).collect();
    (rows, coverage, d)
}

#[test]
fn actual_wealth_tick_preserves_scoped_edge_cases_and_every_operation_witness() {
    let mut pool = AgentPool::new(9);
    for _ in 0..9 { farmer(&mut pool, 0); }
    pool.occupations[3] = Occupation::Soldier as u8;
    pool.kill(4); pool.regions[5] = 99;
    pool.wealth[0] = -0.0;
    pool.wealth[4] = f32::from_bits(0x7fc0_0456);
    pool.wealth[5] = -0.0;
    let nan = f32::from_bits(0x7fc0_1234);
    let loss = vec![(pool.ids[0], -0.0), (pool.ids[1], nan), (u32::MAX, 0.5),
        (pool.ids[3], 0.5), (pool.ids[4], 0.5), (pool.ids[5], 0.5), (0, 0.0),
        (0, -0.0), (pool.ids[8], 0.5), (u32::MAX - 1, nan)];
    let work = health_care::prepare(&mut pool, &[], &[], &[], 1, 0.5, 0.2);
    let mut rec = recorder(1);
    rec.prepare(&pool, &work, &[], &[], &[], 1, 0.5, 0.2, CarePolicy::Spouse);
    economy(&mut rec, &work);
    pool.health_work_loss = loss;
    let encoded_before = crate::persist::encode(crate::persist::KIND_AGENT, &pool);
    let mut control: AgentPool = crate::persist::decode(crate::persist::KIND_AGENT, &encoded_before).unwrap();
    control.health_work_loss = pool.health_work_loss.clone();
    pool.health_care_observation = Some(rec);
    let mut region = RegionState::new(0);
    region.resource_yields[0] = 1.3; region.farmer_income_modifier = 0.8; region.farm_productivity = 1.75;
    let signals = crate::signals::TickSignals { civs: vec![], contested_regions: vec![false] };
    let mut ranks = vec![0.0; pool.capacity()];
    let mut control_ranks = ranks.clone();
    crate::tick::wealth_tick(&mut pool, &[region.clone()], &signals, &mut ranks);
    crate::tick::wealth_tick(&mut control, &[region.clone()], &signals, &mut control_ranks);
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &pool),
        crate::persist::encode(crate::persist::KIND_AGENT, &control));
    assert_eq!(ranks.iter().map(|x| x.to_bits()).collect::<Vec<_>>(),
        control_ranks.iter().map(|x| x.to_bits()).collect::<Vec<_>>());
    assert!(pool.health_work_loss.is_empty());
    let mut rec = pool.health_care_observation.take().unwrap();
    let result = health_care::finish(work, &pool, [42; 32], 20, 0.0);
    rec.finish(&pool, 20, 0.0, &result);
    let bytes = rec.saved_bytes().unwrap();
    assert_prefix(bytes, 0);
    assert_eq!(count(bytes, 7), 10); assert_eq!(count(bytes, 8), 9);
    let (rows, coverage, mut d) = scope(bytes);
    assert_eq!(coverage, [9, 9, 8, 1]);
    assert_eq!(rows.iter().map(|r| r.slot).collect::<Vec<_>>(), vec![0, 1, 2, 3, 4, 5, 7, 8, 9]);
    assert_eq!(rows.iter().map(|r| r.reason).collect::<Vec<_>>(), vec![1, 0, 2, 3, 4, 5, 2, 0, 6]);
    assert_eq!(rows.iter().map(|r| r.mask).collect::<Vec<_>>(), vec![63, 63, 63, 63, 33, 33, 63, 63, 0]);
    assert_eq!(rows[0].loss, 0x8000_0000);
    assert_eq!(rows[1].loss, 0x7fc0_1234);
    assert_eq!(rows[6].consumed, 0); assert_eq!(rows[6].loss, 0x8000_0000);
    assert_eq!(rows[2].consumed, u32::MAX); assert_eq!(rows[2].current, pool.ids[2]);
    assert_eq!(rows[3].occupation, Occupation::Soldier as u8);
    assert_eq!(rows[4].flags, 5); assert_eq!(rows[5].flags, 3);
    assert_eq!(rows[5].region, 99);
    assert_eq!(rows[4].numeric, [0x7fc0_0456, 0, 0, 0, 0, 0x7fc0_0456]);
    assert_eq!(rows[5].numeric, [0x8000_0000, 0, 0, 0, 0, 0x8000_0000]);
    assert_eq!(rows[8].numeric, [0; 6]); assert_eq!(rows[8].flags, 0);
    let base = agent::BASE_FARMER_INCOME * region.farmer_income_modifier * region.resource_yields[0]
        * region.farm_productivity;
    assert_eq!(rows[0].numeric[1], base.to_bits());
    assert_eq!(rows[7].numeric[1], base.to_bits());
    assert_eq!(rows[7].numeric[2], (base * (1.0 - 0.5)).to_bits());
    assert_ne!(rows[7].numeric[1], rows[7].numeric[2]);
    assert_eq!(rows[0].numeric[1], rows[0].numeric[2]);
    assert_eq!(rows[2].numeric[1], rows[2].numeric[2]); // stale id cannot charge
    assert_eq!(rows[3].numeric[1], rows[3].numeric[2]); // nonfarmer cannot charge
    for row in rows.iter().filter(|r| r.mask == 63) {
        assert_eq!(row.numeric[5], pool.wealth[row.slot as usize].to_bits());
        // Nonfinite arithmetic qualification is separate from faithful capture;
        // the raw consumed NaN payload and actual final bits are checked above.
        if f32::from_bits(row.numeric[2]).is_finite() {
            let added = f32::from_bits(row.numeric[0]) + f32::from_bits(row.numeric[2]);
            let decayed = f32::from_bits(row.numeric[3]) * (1.0 - agent::WEALTH_DECAY);
            assert_eq!(row.numeric[3], added.to_bits());
            assert_eq!(row.numeric[4], decayed.to_bits());
        }
    }
    assert_eq!(d.u32(), region.resource_yields[0].to_bits());
    assert_eq!(d.u32(), region.farmer_income_modifier.to_bits());
    assert_eq!(d.u32(), region.farm_productivity.to_bits());
}

#[test]
fn row_byte_and_required_equality_faults_retain_only_bounded_incomplete_prefixes() {
    let pool = AgentPool::new(0);
    let work = HealthWork::default();
    let mut rows = recorder(0);
    rows.prepare(&pool, &work, &vec![0; 4097], &[], &[], 0, 0.0, 0.0, CarePolicy::Spouse);
    rows.missing_finish(20);
    assert_prefix(rows.saved_bytes().unwrap(), 1);
    assert_eq!(rows.saved_bytes().unwrap().len(), 256);

    let mut full = AgentPool::new(4096);
    for _ in 0..4096 { farmer(&mut full, 0); }
    for slot in 0..full.capacity() {
        full.rel_count[slot] = 8;
        full.rel_bond_types[slot] = [5; 8];
        full.rel_target_ids[slot] = [u32::MAX; 8];
    }
    let work = health_care::prepare(&mut full, &[], &[], &[], 1, 0.5, 0.2);
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &full);
    let mut bytes = recorder(1);
    bytes.prepare(&full, &work, &[], &[], &[], 1, 0.5, 0.2, CarePolicy::Spouse);
    bytes.missing_finish(20);
    assert_prefix(bytes.saved_bytes().unwrap(), 2);
    assert_eq!(before, crate::persist::encode(crate::persist::KIND_AGENT, &full));
    assert_eq!(bytes.id_slots.len(), 4096);
    assert!(bytes.bytes.len() <= 131_072);

    let mut pool = AgentPool::new(1); let slot = farmer(&mut pool, 0); let id = pool.ids[slot];
    for kind in 0..3 {
        let mut work = health_care::prepare(&mut pool, &[id], &[], &[], 1, 0.5, 0.2);
        match kind {
            0 => work.patients[0] = u32::MAX,
            1 => work.workers[0].id = u32::MAX,
            _ => work.worked[0] = true,
        }
        let mut rec = recorder(1);
        rec.prepare(&pool, &work, &[id], &[], &[], 1, 0.5, 0.2, CarePolicy::Spouse);
        rec.missing_finish(20);
        assert_prefix(rec.saved_bytes().unwrap(), 5);
    }
}

#[test]
fn stage_missing_duplicate_stale_and_saturating_calls_never_claim_complete() {
    let pool = AgentPool::new(0); let work = HealthWork::default();
    let mut missing = recorder(0);
    missing.missing_finish(20);
    assert_prefix(missing.saved_bytes().unwrap(), 7);
    assert_eq!(missing.saved_bytes().unwrap().len(), 256);
    let mut duplicated = recorder(0);
    duplicated.prepare(&pool, &work, &[], &[], &[], 0, 0.0, 0.0, CarePolicy::Spouse);
    duplicated.prepare(&pool, &work, &[], &[], &[], 0, 0.0, 0.0, CarePolicy::Spouse);
    duplicated.missing_finish(20);
    assert_prefix(duplicated.saved_bytes().unwrap(), 6);
    assert_eq!(duplicated.saved_bytes().unwrap()[196], 2);
    let mut saturated = recorder(0);
    saturated.prepare(&pool, &work, &[], &[], &[], 0, 0.0, 0.0, CarePolicy::Spouse);
    for _ in 0..300 { saturated.economy_begin(0); }
    saturated.missing_finish(20);
    assert_prefix(saturated.saved_bytes().unwrap(), 6);
    assert_eq!(saturated.saved_bytes().unwrap()[197], 255);
    let mut stale = recorder(0);
    complete_empty(&mut stale, 21);
    assert_prefix(stale.saved_bytes().unwrap(), 8);
    let mut wrong_loss = recorder(1);
    let work = HealthWork { losses: vec![-0.0], impaired: vec![0.0], care: vec![0.0],
        recipients: vec![0], worked: vec![false], ..HealthWork::default() };
    wrong_loss.prepare(&pool, &work, &[], &[], &[], 1, 0.0, 0.0, CarePolicy::Spouse);
    wrong_loss.economy_begin(1);
    wrong_loss.economy_before(0, 0, 1.0, Some(0.0));
    wrong_loss.missing_finish(20);
    assert_prefix(wrong_loss.saved_bytes().unwrap(), 5); // numeric zero equality is insufficient
}

#[test]
fn immutable_export_and_the_thirty_two_ordinal_window_are_exact() {
    let mut rec = recorder(0);
    assert!(rec.saved_bytes().is_none());
    for ordinal in 0..32u32 {
        complete_empty(&mut rec, 20 + ordinal);
        let first = rec.saved_bytes().unwrap().to_vec();
        let pointer = rec.saved_bytes().unwrap().as_ptr();
        assert_prefix(&first, 0);
        assert_eq!(first[24], 15);
        assert_eq!(&first[92..124], &[0xa5; 32]);
        assert_eq!(&first[196..200], &[1, 1, 1, 1]);
        assert_eq!(u32::from_le_bytes(first[200..204].try_into().unwrap()), ordinal);
        assert_eq!(rec.saved_bytes().unwrap(), first);
        assert_eq!(rec.saved_bytes().unwrap().as_ptr(), pointer);
    }
    complete_empty(&mut rec, 52);
    assert_prefix(rec.saved_bytes().unwrap(), 8);
    assert_eq!(u32::from_le_bytes(rec.saved_bytes().unwrap()[200..204].try_into().unwrap()), 31);
}

#[test]
fn missing_stage_completion_and_missing_wealth_witnesses_refuse_evidence() {
    let pool = AgentPool::new(0); let work = HealthWork::default();
    let mut unclosed = recorder(0);
    unclosed.prepare(&pool, &work, &[], &[], &[], 0, 0.0, 0.0, CarePolicy::Spouse);
    economy(&mut unclosed, &work);
    unclosed.wealth_begin(&pool, &[], &[]);
    unclosed.finish(&pool, 20, 0.0, &(vec![], vec![], vec![]));
    assert_prefix(unclosed.saved_bytes().unwrap(), 7);

    let mut no_outputs = recorder(0);
    no_outputs.prepare(&pool, &work, &[], &[], &[], 0, 0.0, 0.0, CarePolicy::Spouse);
    no_outputs.economy_begin(0);
    no_outputs.wealth_begin(&pool, &[], &[]);
    no_outputs.wealth_end();
    no_outputs.finish(&pool, 20, 0.0, &(vec![], vec![], vec![]));
    assert_prefix(no_outputs.saved_bytes().unwrap(), 7);

    let mut double_end = recorder(0);
    double_end.prepare(&pool, &work, &[], &[], &[], 0, 0.0, 0.0, CarePolicy::Spouse);
    economy(&mut double_end, &work);
    double_end.wealth_begin(&pool, &[], &[]);
    double_end.wealth_end(); double_end.wealth_end();
    double_end.finish(&pool, 20, 0.0, &(vec![], vec![], vec![]));
    assert_prefix(double_end.saved_bytes().unwrap(), 6);

    let mut pool = AgentPool::new(1); let slot = farmer(&mut pool, 0);
    let id = pool.ids[slot];
    let work = health_care::prepare(&mut pool, &[id], &[], &[], 1, 0.5, 0.0);
    let mut incomplete = recorder(1);
    incomplete.prepare(&pool, &work, &[id], &[], &[], 1, 0.5, 0.0, CarePolicy::Spouse);
    economy(&mut incomplete, &work);
    incomplete.wealth_begin(&pool, &[RegionState::new(0)], &pool.health_work_loss);
    incomplete.wealth_visit(slot);
    incomplete.wealth_value(slot, 1, 0.0); // later actual operation sites were never supplied
    incomplete.wealth_end();
    incomplete.missing_finish(20);
    assert_prefix(incomplete.saved_bytes().unwrap(), 7);
}

#[test]
fn primitive_copies_keep_signed_zero_and_nan_payloads_in_every_float_width() {
    let mut pool = AgentPool::new(1); farmer(&mut pool, 0);
    let mut work = health_care::prepare(&mut pool, &[], &[], &[], 1, 0.0, 0.0);
    work.losses[0] = -0.0;
    work.impaired[0] = f64::from_bits(0x7ff8_0000_1234_5678);
    work.care[0] = -0.0;
    let mut rec = recorder(1);
    rec.prepare(&pool, &work, &[], &[], &[], 1, -0.0, -0.0, CarePolicy::Spouse);
    economy(&mut rec, &work);
    rec.wealth_begin(&pool, &[RegionState::new(0)], &[]);
    rec.wealth_visit(0); rec.wealth_end();
    let result = (vec![], vec![], vec![(0, work.impaired[0], work.care[0], 0)]);
    rec.finish(&pool, 20, -0.0, &result);
    let bytes = rec.saved_bytes().unwrap();
    assert_prefix(bytes, 0);
    let mut d = Decode { bytes, at: 256, ids: vec![] };
    assert_eq!(d.u32(), 0x8000_0000); assert_eq!(d.u32(), 0x8000_0000);
    let (_, after_preparation) = preparation(bytes);
    d.at = after_preparation.at - 24;
    assert_eq!(d.u32(), 0x8000_0000);
    assert_eq!(d.u64(), 0x7ff8_0000_1234_5678);
    assert_eq!(d.u64(), 0x8000_0000_0000_0000);
    assert_eq!(d.u32(), 0);
    d.skip(13 + 19 + 8 + 12);
    assert_eq!(d.u32(), 20); assert_eq!(d.u32(), 0x8000_0000);
    assert_eq!(d.u16(), 1);
    d.skip(4 + 2 + 1); // complete finish ID, region and alive columns
    assert_eq!(d.u16(), 0);
    assert_eq!(d.u64(), 0x7ff8_0000_1234_5678);
    assert_eq!(d.u64(), 0x8000_0000_0000_0000);
    assert_eq!(d.u32(), 0);
    assert_eq!(d.at, bytes.len());
}

#[test]
fn actual_slot_reuse_copies_old_consumed_id_without_charging_the_replacement() {
    let mut pool = AgentPool::new(2);
    let patient = farmer(&mut pool, 0); let giver = farmer(&mut pool, 0);
    let patient_id = pool.ids[patient]; let giver_id = pool.ids[giver];
    edge(&mut pool, patient, 2, giver_id);
    let work = health_care::prepare(&mut pool, &[patient_id], &[], &[], 1, 0.5, 0.2);
    assert_eq!(work.rows, vec![(patient_id, 0, giver_id, 0.2)]);
    let mut rec = recorder(1);
    rec.prepare(&pool, &work, &[patient_id], &[], &[], 1, 0.5, 0.2, CarePolicy::Spouse);
    economy(&mut rec, &work);
    pool.kill(giver);
    let replacement = farmer(&mut pool, 0);
    assert_eq!(replacement, giver);
    assert_ne!(pool.ids[replacement], giver_id);
    pool.health_care_observation = Some(rec);
    let mut region = RegionState::new(0);
    region.resource_yields[0] = 1.0; region.farmer_income_modifier = 1.0; region.farm_productivity = 1.0;
    let signals = crate::signals::TickSignals { civs: vec![], contested_regions: vec![false] };
    let mut ranks = vec![0.0; 2];
    crate::tick::wealth_tick(&mut pool, &[region], &signals, &mut ranks);
    let mut rec = pool.health_care_observation.take().unwrap();
    let result = health_care::finish(work, &pool, [42; 32], 20, 0.0);
    rec.finish(&pool, 20, 0.0, &result);
    let bytes = rec.saved_bytes().unwrap();
    assert_prefix(bytes, 0);
    let (rows, coverage, _) = scope(bytes);
    assert_eq!(coverage, [2, 2, 2, 0]);
    assert_eq!(rows[0].reason, 0);
    assert_eq!(rows[1].reason, 2);
    assert_eq!(rows[1].consumed, giver_id);
    assert_eq!(rows[1].current, pool.ids[replacement]);
    assert_eq!(rows[1].loss, 0.2f32.to_bits());
    assert_eq!(rows[1].numeric[1], agent::BASE_FARMER_INCOME.to_bits());
    assert_eq!(rows[1].numeric[1], rows[1].numeric[2]);
    assert_eq!(rows[1].numeric[5], pool.wealth[replacement].to_bits());
}

#[test]
fn duplicate_outputs_finish_and_unbounded_relationship_domain_are_rejected() {
    let pool = AgentPool::new(0); let work = HealthWork::default();
    let mut duplicate_outputs = recorder(0);
    duplicate_outputs.prepare(&pool, &work, &[], &[], &[], 0, 0.0, 0.0, CarePolicy::Spouse);
    duplicate_outputs.economy_begin(0);
    duplicate_outputs.economy_outputs_begin(0); duplicate_outputs.economy_outputs_begin(0);
    duplicate_outputs.missing_finish(20);
    assert_prefix(duplicate_outputs.saved_bytes().unwrap(), 6);
    let mut duplicate_finish = recorder(0);
    complete_empty(&mut duplicate_finish, 20);
    duplicate_finish.finish(&pool, 20, 0.0, &(vec![], vec![], vec![]));
    assert_prefix(duplicate_finish.saved_bytes().unwrap(), 6);
    assert_eq!(duplicate_finish.saved_bytes().unwrap()[199], 2);

    let mut pool = AgentPool::new(1); farmer(&mut pool, 0);
    pool.rel_count[0] = 9;
    let work = health_care::prepare(&mut pool, &[], &[], &[], 1, 0.0, 0.0);
    let mut invalid = recorder(1);
    invalid.prepare(&pool, &work, &[], &[], &[], 1, 0.0, 0.0, CarePolicy::Spouse);
    invalid.missing_finish(20);
    assert_prefix(invalid.saved_bytes().unwrap(), 4);
}

#[test]
fn successive_actual_wealth_calls_consume_health_once_and_reset_scope_coverage() {
    let mut pool = AgentPool::new(1); let patient = farmer(&mut pool, 0);
    let id = pool.ids[patient];
    let mut rec = recorder(1);
    let mut region = RegionState::new(0);
    region.resource_yields[0] = 1.0; region.farmer_income_modifier = 1.0; region.farm_productivity = 1.0;
    let signals = crate::signals::TickSignals { civs: vec![], contested_regions: vec![false] };
    let mut previous_saved = None;
    for ordinal in 0..2u32 {
        let ids = if ordinal == 0 { vec![id] } else { vec![] };
        let work = health_care::prepare(&mut pool, &ids, &[], &[], 1, 0.5, 0.0);
        rec.prepare(&pool, &work, &ids, &[], &[], 1, 0.5, 0.0, CarePolicy::Spouse);
        economy(&mut rec, &work);
        let pre = pool.wealth[patient];
        pool.health_care_observation = Some(rec);
        crate::tick::wealth_tick(&mut pool, &[region.clone()], &signals, &mut [0.0]);
        assert!(pool.health_work_loss.is_empty());
        rec = pool.health_care_observation.take().unwrap();
        let result = health_care::finish(work, &pool, [42; 32], 20 + ordinal, 0.0);
        rec.finish(&pool, 20 + ordinal, 0.0, &result);
        let bytes = rec.saved_bytes().unwrap();
        assert_prefix(bytes, 0);
        let (rows, coverage, _) = scope(bytes);
        if ordinal == 0 {
            assert_eq!(coverage, [1, 1, 1, 0]);
            assert_eq!(rows.len(), 1);
            assert_eq!(rows[0].numeric[2], (agent::BASE_FARMER_INCOME * 0.5).to_bits());
            previous_saved = Some(bytes.to_vec());
        } else {
            assert_eq!(count(bytes, 7), 0); assert_eq!(count(bytes, 8), 0);
            assert!(rows.is_empty()); assert_eq!(coverage, [1, 1, 0, 1]);
            let expected = (pre + agent::BASE_FARMER_INCOME) * (1.0 - agent::WEALTH_DECAY);
            assert_eq!(pool.wealth[patient].to_bits(), expected.to_bits());
            let first = previous_saved.as_ref().unwrap();
            assert_eq!(count(first, 7), 1); assert_eq!(count(first, 8), 1);
            assert_eq!(u32::from_le_bytes(first[200..204].try_into().unwrap()), 0);
            assert_eq!(u32::from_le_bytes(bytes[200..204].try_into().unwrap()), 1);
        }
    }
}
