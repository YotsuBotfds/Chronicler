//! Derived, single-turn manual-work inputs. Persistent episodes belong to
//! Python WorldState; none of these slot references enters a checkpoint.
use std::collections::{BTreeMap, BTreeSet, HashSet};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use crate::{agent, pool::AgentPool, relationships};

#[derive(Default)]
pub struct HealthWork {
    pub workers: Vec<Worker>,
    pub patients: Vec<u32>,
    pub rows: Vec<(u32, u16, u32, f32)>,
    pub losses: Vec<f32>,
    pub impaired: Vec<f64>,
    pub care: Vec<f64>,
    pub recipients: Vec<u32>,
    pub worked: Vec<bool>,
}

pub struct Worker { pub slot: usize, pub id: u32, pub region: usize, pub available: f32 }

fn eligible(pool: &AgentPool, slot: usize, excluded: &HashSet<u32>, urban: &HashSet<u16>) -> bool {
    pool.is_alive(slot) && pool.ages[slot] >= agent::AGE_ADULT
        && pool.occupations[slot] == agent::Occupation::Farmer as u8
        && !pool.is_on_trip(slot) && !excluded.contains(&pool.ids[slot])
        && !urban.contains(&pool.settlement_ids[slot])
}

pub fn prepare(pool: &mut AgentPool, ids: &[u32], excluded: &[u32], urban: &[u16],
               regions: usize, impairment: f32, care_fraction: f32) -> HealthWork {
    let lookup = pool.build_id_slots();
    let excluded: HashSet<u32> = excluded.iter().copied().collect();
    let urban: HashSet<u16> = urban.iter().copied().filter(|&x| x != 0).collect();
    let patients: HashSet<u32> = ids.iter().copied().collect();
    let mut assigned = HashSet::new();
    let mut deductions: BTreeMap<usize, f32> = BTreeMap::new();
    let mut out = HealthWork { losses: vec![0.0; regions], impaired: vec![0.0; regions],
        care: vec![0.0; regions], recipients: vec![0; regions], worked: vec![false; regions], ..Default::default() };
    let mut ordered: Vec<u32> = patients.iter().copied().collect(); ordered.sort_unstable();
    for id in ordered {
        let Some(slot) = lookup.get(id) else { continue };
        let region = pool.regions[slot] as usize;
        if region >= regions { continue; }
        out.patients.push(id);
        let mut giver = 0;
        if eligible(pool, slot, &excluded, &urban) {
            deductions.insert(slot, impairment);
            out.impaired[region] += impairment as f64;
            if care_fraction > 0.0 {
                if let Some(spouse) = relationships::get_spouse_id(pool, slot) {
                    if let Some(s) = lookup.get(spouse) {
                        if eligible(pool, s, &excluded, &urban) && pool.regions[s] == pool.regions[slot]
                            && !patients.contains(&spouse) && assigned.insert(spouse) {
                            giver = spouse;
                            deductions.insert(s, care_fraction);
                            out.care[region] += care_fraction as f64;
                            out.recipients[region] += 1;
                        }
                    }
                }
            }
        }
        out.rows.push((id, region as u16, giver, if giver == 0 { 0.0 } else { care_fraction }));
    }
    pool.health_work_loss.clear();
    if !deductions.is_empty() { pool.health_work_loss.resize(pool.capacity(), (0, 0.0)); }
    for (&slot, &loss) in &deductions {
        pool.health_work_loss[slot] = (pool.ids[slot], loss);
        let r = pool.regions[slot] as usize;
        out.losses[r] += loss;
    }
    for slot in 0..pool.capacity() {
        let r = pool.regions[slot] as usize;
        if r < regions && eligible(pool, slot, &excluded, &urban) {
            out.workers.push(Worker { slot, id: pool.ids[slot], region: r,
                available: 1.0 - pool.health_work_loss.get(slot).map_or(0.0, |x| x.1) });
        }
    }
    out
}

/// Selection policy only; never part of a native checkpoint or work record.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CarePolicy { Spouse, RetainedKin }

impl CarePolicy {
    pub fn from_name(name: &str) -> Option<Self> {
        match name {
            "spouse" => Some(Self::Spouse),
            "retained_kin" => Some(Self::RetainedKin),
            _ => None,
        }
    }
}

/// Complete every legacy spouse allocation before filling any uncared row.
/// The original preparer owns patient/worker eligibility and all old sums.
pub fn prepare_with_policy(pool: &mut AgentPool, ids: &[u32], excluded: &[u32], urban: &[u16],
                           regions: usize, impairment: f32, care_fraction: f32,
                           policy: CarePolicy) -> HealthWork {
    let mut work = prepare(pool, ids, excluded, urban, regions, impairment, care_fraction);
    if policy == CarePolicy::Spouse || care_fraction <= 0.0
        || !work.rows.iter().any(|row| row.2 == 0) {
        return work;
    }
    // These workers were just resolved from the same live pool and exclusions.
    // No liveness, ID, region or eligibility fields change between the passes.
    // Ordered collections avoid additional randomized hasher construction.
    let lookup: BTreeMap<u32, usize> = work.workers.iter().map(|w| (w.id, w.slot)).collect();
    let patients: BTreeSet<u32> = ids.iter().copied().collect();
    let mut assigned: BTreeSet<u32> = work.rows.iter().filter(|row| row.2 != 0).map(|row| row.2).collect();
    let mut kin_assigned = BTreeSet::new();
    for row in &mut work.rows {
        if row.2 != 0 { continue; }
        let Some(&slot) = lookup.get(&row.0) else { continue; };
        let mut targets = [0; relationships::REL_SLOTS];
        let mut count = 0;
        for i in 0..(pool.rel_count[slot] as usize).min(relationships::REL_SLOTS) {
            let target = pool.rel_target_ids[slot][i];
            if pool.rel_bond_types[slot][i] == relationships::BondType::Kin as u8
                && target != 0 && target != row.0 {
                targets[count] = target;
                count += 1;
            }
        }
        targets[..count].sort_unstable();
        let mut previous = 0;
        for &target in &targets[..count] {
            if target == previous { continue; }
            previous = target;
            if patients.contains(&target) || assigned.contains(&target) { continue; }
            let Some(&giver) = lookup.get(&target) else { continue; };
            if pool.regions[giver] != pool.regions[slot] { continue; }
            let reciprocal = (0..(pool.rel_count[giver] as usize).min(relationships::REL_SLOTS))
                .any(|i| pool.rel_target_ids[giver][i] == row.0
                    && pool.rel_bond_types[giver][i] == relationships::BondType::Kin as u8);
            if !reciprocal { continue; }
            assigned.insert(target);
            kin_assigned.insert(target);
            row.2 = target;
            row.3 = care_fraction;
            if pool.health_work_loss.len() < pool.capacity() {
                pool.health_work_loss.resize(pool.capacity(), (0, 0.0));
            }
            pool.health_work_loss[giver] = (target, care_fraction);
            let region = row.1 as usize;
            work.losses[region] += care_fraction;
            work.care[region] += care_fraction as f64;
            work.recipients[region] += 1;
            break;
        }
    }
    for worker in &mut work.workers {
        if kin_assigned.contains(&worker.id) {
            worker.available = 1.0 - pool.health_work_loss.get(worker.slot).map_or(0.0, |x| x.1);
        }
    }
    work
}

pub fn finish(work: HealthWork, pool: &AgentPool, seed: [u8; 32], turn: u32, rate: f32)
    -> (Vec<(u32, u16)>, Vec<(u32, u16, u16)>, Vec<(u16, f64, f64, u32)>) {
    let lookup = pool.build_id_slots();
    let alive = work.patients.iter().filter_map(|&id| lookup.get(id).map(|s| (id, pool.regions[s]))).collect();
    let patients: HashSet<u32> = work.patients.iter().copied().collect();
    let mut rngs: Vec<ChaCha8Rng> = (0..work.worked.len()).map(|r| {
        let mut rng = ChaCha8Rng::from_seed(seed);
        rng.set_stream(((r as u64) << 48) | ((turn as u64) << 16) | 0x4843);
        rng
    }).collect();
    let mut injuries = Vec::new();
    for w in &work.workers {
        let roll: f32 = rngs[w.region].gen();
        if work.worked[w.region] && w.available > 0.0 && !patients.contains(&w.id)
            && pool.is_alive(w.slot) && pool.ids[w.slot] == w.id && roll < rate * w.available {
            injuries.push((w.id, w.region as u16, pool.regions[w.slot]));
        }
    }
    injuries.sort_unstable();
    let stats = (0..work.losses.len()).map(|r| (r as u16, work.impaired[r], work.care[r],
        work.recipients[r])).collect();
    (alive, injuries, stats)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Occupation, RegionState};

    fn farmer(pool: &mut AgentPool, region: u16, age: u16) -> usize {
        pool.spawn(region, 0, Occupation::Farmer, age, 0.0, 0.0, 0.0, 0, 1, 2, agent::BELIEF_NONE)
    }
    fn married(pool: &mut AgentPool, a: usize, b: usize) {
        for (s, t) in [(a, b), (b, a)] {
            pool.rel_count[s] = 1;
            pool.rel_target_ids[s][0] = pool.ids[t];
            pool.rel_bond_types[s][0] = relationships::BondType::Marriage as u8;
        }
    }
    #[test]
    fn care_is_a_single_productive_work_budget_and_nonpersistent() {
        let mut pool = AgentPool::new(8);
        let a = farmer(&mut pool, 0, 30); let b = farmer(&mut pool, 0, 35);
        married(&mut pool, a, b);
        let id = pool.ids[a];
        let encoded = crate::persist::encode(crate::persist::KIND_AGENT, &pool);
        let work = prepare(&mut pool, &[id], &[], &[], 1, 0.5, 0.2);
        assert_eq!(work.rows, vec![(id, 0, pool.ids[b], 0.2)]);
        assert!((work.losses[0] - 0.7).abs() < 1e-6);
        assert_eq!(work.recipients, vec![1]);
        for w in &work.workers {
            assert!((w.available + pool.health_work_loss[w.slot].1 - 1.0).abs() < 1e-6);
        }
        assert_eq!(encoded, crate::persist::encode(crate::persist::KIND_AGENT, &pool));
        let restored: AgentPool = crate::persist::decode(crate::persist::KIND_AGENT, &encoded).unwrap();
        assert!(restored.health_work_loss.is_empty());
        assert!(!crate::persist::schema_of::<crate::AgentSimulator>().contains("health_work"));
    }
    #[test]
    fn absent_enlisted_urban_young_and_injured_spouses_supply_no_care() {
        for case in 0..5 {
            let mut pool = AgentPool::new(8);
            let a = farmer(&mut pool, 0, 30); let b = farmer(&mut pool, 0, 35);
            married(&mut pool, a, b);
            let id = pool.ids[a]; let spouse = pool.ids[b];
            let mut ids = vec![id]; let mut excluded = vec![]; let mut urban = vec![];
            match case {
                0 => pool.regions[b] = 1,
                1 => excluded.push(spouse),
                2 => { pool.settlement_ids[b] = 9; urban.push(9); },
                3 => pool.ages[b] = agent::AGE_ADULT - 1,
                _ => ids.push(spouse),
            }
            let work = prepare(&mut pool, &ids, &excluded, &urban, 2, 0.5, 0.2);
            assert!(work.rows.iter().all(|r| r.2 == 0));
            assert_eq!(work.care, vec![0.0, 0.0]);
        }
    }
    #[test]
    fn income_consumes_loss_once_and_a_reused_slot_is_protected() {
        let mut pool = AgentPool::new(8);
        let a = farmer(&mut pool, 0, 30); let id = pool.ids[a];
        pool.wealth[a] = 0.0;
        prepare(&mut pool, &[id], &[], &[], 1, 0.5, 0.0);
        let mut region = RegionState::new(0); region.resource_yields[0] = 1.0;
        region.farmer_income_modifier = 1.0; region.farm_productivity = 1.0;
        let signals = crate::signals::TickSignals { civs: vec![], contested_regions: vec![false] };
        let mut ranks = vec![0.0; pool.capacity()];
        crate::tick::wealth_tick(&mut pool, &[region.clone()], &signals, &mut ranks);
        let want = agent::BASE_FARMER_INCOME * 0.5 * (1.0 - agent::WEALTH_DECAY);
        assert_eq!(pool.wealth[a], want);
        assert!(pool.health_work_loss.is_empty());
        crate::tick::wealth_tick(&mut pool, &[region.clone()], &signals, &mut ranks);
        assert_eq!(pool.wealth[a], (want + agent::BASE_FARMER_INCOME) * (1.0 - agent::WEALTH_DECAY));
        prepare(&mut pool, &[id], &[], &[], 1, 0.5, 0.0);
        pool.kill(a); let replacement = farmer(&mut pool, 0, 30);
        assert_eq!(replacement, a); assert_ne!(pool.ids[a], id);
        pool.wealth[a] = 0.0;
        crate::tick::wealth_tick(&mut pool, &[region], &signals, &mut ranks);
        assert_eq!(pool.wealth[a], agent::BASE_FARMER_INCOME * (1.0 - agent::WEALTH_DECAY));
    }
    #[test]
    fn only_surviving_actual_workers_acquire_next_turn_episodes() {
        let mut pool = AgentPool::new(8);
        let existing = farmer(&mut pool, 0, 30); let working = farmer(&mut pool, 0, 30);
        let idle = farmer(&mut pool, 1, 30); let dead = farmer(&mut pool, 0, 30);
        let id = pool.ids[existing]; let working_id = pool.ids[working];
        let mut work = prepare(&mut pool, &[id], &[], &[], 2, 0.5, 0.0);
        work.worked[0] = true;
        pool.kill(dead); farmer(&mut pool, 0, 0);
        pool.regions[existing] = 1;
        let (alive, new, _) = finish(work, &pool, [42; 32], 1, 1.0);
        assert_eq!(alive, vec![(id, 1)]);
        assert_eq!(new, vec![(working_id, 0, 0)]);
        assert!(pool.is_alive(idle));
    }

    #[test]
    fn actual_economy_productivity_does_not_double_charge_health_income() {
        use crate::economy::{EconomyRegionInput, EconomyConfig, RegionAgentCounts,
            NUM_GOODS, tick_economy_core};
        for (curve, slots) in [(false, false), (true, false), (true, true)] {
            let mut pool = AgentPool::new(10);
            for _ in 0..10 { let s = farmer(&mut pool, 0, 30); pool.wealth[s] = 0.0; }
            married(&mut pool, 0, 1);
            let patient = pool.ids[0];
            let work = prepare(&mut pool, &[patient], &[], &[], 1, 0.5, 0.2);
            let available = 10.0 - work.losses[0];
            let input = EconomyRegionInput {
                region_id: 0, terrain: 0, storage_population: 10,
                resource_types: [0, 255, 255], resource_yields: [1.0, 0.0, 0.0],
                production_caps: [None; 3], stockpile: [0.0; NUM_GOODS], subsistence_yield: 0.0,
                farm_labor_factor: available / 10.0, craft_raw_demand: 0.0, craft_demand: 0.0,
                farm_labor_ref: if curve { 5.0 } else { 0.0 }, farm_labor_half: 5.0,
                slot_curves: slots, slot_labor_ref: [0.0; 3], slot_labor_half: [0.0; 3],
            };
            let counts = RegionAgentCounts { population: 10, farmer_count: 10,
                soldier_count: 0, merchant_count: 0, wealthy_count: 0 };
            let config = EconomyConfig::default();
            let output = tick_economy_core(&[input], &[counts], &[], &[0.0], &[0], 1,
                &[0], &config, 1.0, false, None);
            let rr = &output.region_results[0];
            assert_eq!(rr.market_demand[0], 10.0 * config.per_capita_food);
            let expected_work = if curve { crate::economy::effective_farm_labor(available, 5.0, 5.0) } else { available };
            assert!((rr.slot_output[0] - expected_work).abs() < 1e-5);
            if !curve { assert_eq!(rr.farm_productivity, 1.0); }
            let mut region = RegionState::new(0);
            region.resource_yields[0] = 1.0;
            region.farmer_income_modifier = rr.farmer_income_modifier;
            region.farm_productivity = rr.farm_productivity;
            let signals = crate::signals::TickSignals { civs: vec![], contested_regions: vec![false] };
            let mut ranks = vec![0.0; 10];
            crate::tick::wealth_tick(&mut pool, &[region], &signals, &mut ranks);
            let expected_income = agent::BASE_FARMER_INCOME * rr.farmer_income_modifier
                * expected_work * (1.0 - agent::WEALTH_DECAY);
            assert!((pool.wealth.iter().sum::<f32>() - expected_income).abs() < 1e-5,
                "curve={curve} slots={slots}: income must scale with effective work only once");
            assert!((pool.wealth[0] / pool.wealth[2] - 0.5).abs() < 1e-6);
            assert!((pool.wealth[1] / pool.wealth[2] - 0.8).abs() < 1e-6);
        }
    }
    fn recorded(pool: &mut AgentPool, a: usize, b: usize, kind: relationships::BondType) {
        let index = pool.rel_count[a] as usize;
        assert!(index < relationships::REL_SLOTS);
        pool.rel_target_ids[a][index] = pool.ids[b];
        pool.rel_bond_types[a][index] = kind as u8;
        pool.rel_count[a] += 1;
    }
    fn kin(pool: &mut AgentPool, a: usize, b: usize) {
        recorded(pool, a, b, relationships::BondType::Kin);
        recorded(pool, b, a, relationships::BondType::Kin);
    }
    fn copy_pool(pool: &AgentPool) -> AgentPool {
        crate::persist::decode(crate::persist::KIND_AGENT,
            &crate::persist::encode(crate::persist::KIND_AGENT, pool)).unwrap()
    }
    fn same_work(a: &HealthWork, b: &HealthWork) {
        assert_eq!(a.patients, b.patients);
        assert_eq!(a.rows.iter().map(|r| (r.0, r.1, r.2, r.3.to_bits())).collect::<Vec<_>>(),
            b.rows.iter().map(|r| (r.0, r.1, r.2, r.3.to_bits())).collect::<Vec<_>>());
        assert_eq!(a.workers.iter().map(|w| (w.slot, w.id, w.region, w.available.to_bits())).collect::<Vec<_>>(),
            b.workers.iter().map(|w| (w.slot, w.id, w.region, w.available.to_bits())).collect::<Vec<_>>());
        assert_eq!(a.losses.iter().map(|x| x.to_bits()).collect::<Vec<_>>(), b.losses.iter().map(|x| x.to_bits()).collect::<Vec<_>>());
        assert_eq!(a.impaired.iter().map(|x| x.to_bits()).collect::<Vec<_>>(), b.impaired.iter().map(|x| x.to_bits()).collect::<Vec<_>>());
        assert_eq!(a.care.iter().map(|x| x.to_bits()).collect::<Vec<_>>(), b.care.iter().map(|x| x.to_bits()).collect::<Vec<_>>());
        assert_eq!(a.recipients, b.recipients);
        assert_eq!(a.worked, b.worked);
    }

    #[test]
    fn legacy_policy_and_unavailable_kin_preserve_all_work_bits_and_finish_draws() {
        for policy in [CarePolicy::Spouse, CarePolicy::RetainedKin] {
            for impairment in [0.0, 0.5, 1.0] {
                for fraction in [0.0, 0.2, 1.0] {
                    for mode in 0..4 {
                        let mut original = AgentPool::new(8);
                        let a = farmer(&mut original, 0, 30);
                        let b = farmer(&mut original, 0, 35);
                        farmer(&mut original, 1, 25);
                        married(&mut original, a, b);
                        let ids = match mode {
                            0 => vec![], 1 => vec![original.ids[a]],
                            2 => vec![original.ids[b], original.ids[a]],
                            _ => vec![original.ids[a], original.ids[b], original.ids[a]],
                        };
                        let before = crate::persist::encode(crate::persist::KIND_AGENT, &original);
                        let mut candidate = copy_pool(&original);
                        let mut old = prepare(&mut original, &ids, &[], &[], 2, impairment, fraction);
                        let mut new = prepare_with_policy(&mut candidate, &ids, &[], &[], 2, impairment, fraction, policy);
                        same_work(&old, &new);
                        assert_eq!(original.health_work_loss, candidate.health_work_loss);
                        assert_eq!(before, crate::persist::encode(crate::persist::KIND_AGENT, &candidate));
                        old.worked.fill(true); new.worked.fill(true);
                        assert_eq!(finish(old, &original, [42; 32], 7, 0.25),
                            finish(new, &candidate, [42; 32], 7, 0.25));
                    }
                }
            }
        }
        assert_eq!(CarePolicy::from_name("spouse"), Some(CarePolicy::Spouse));
        assert_eq!(CarePolicy::from_name("retained_kin"), Some(CarePolicy::RetainedKin));
        for invalid in ["", "kin", "Retained_Kin", " spouse"] {
            assert_eq!(CarePolicy::from_name(invalid), None);
        }
    }

    #[test]
    fn all_spouses_are_reserved_before_an_earlier_patients_kin_fallback() {
        for spare in [false, true] {
            let mut pool = AgentPool::new(8);
            let early = farmer(&mut pool, 0, 30);
            let later = farmer(&mut pool, 0, 30);
            let spouse = farmer(&mut pool, 0, 30);
            let other = farmer(&mut pool, 0, 30);
            married(&mut pool, later, spouse);
            kin(&mut pool, early, spouse);
            if spare { kin(&mut pool, early, other); }
            let ids = [pool.ids[later], pool.ids[early]];
            let persisted = crate::persist::encode(crate::persist::KIND_AGENT, &pool);
            let work = prepare_with_policy(&mut pool, &ids, &[], &[], 1, 0.5, 0.2, CarePolicy::RetainedKin);
            assert_eq!(work.rows[1], (pool.ids[later], 0, pool.ids[spouse], 0.2));
            assert_eq!(work.rows[0].2, if spare { pool.ids[other] } else { 0 });
            assert_eq!(work.recipients, vec![if spare { 2 } else { 1 }]);
            assert_eq!(persisted, crate::persist::encode(crate::persist::KIND_AGENT, &pool));
        }
    }

    #[test]
    fn kin_targets_are_id_sorted_deduplicated_and_cannot_share_a_donor() {
        let mut pool = AgentPool::new(8);
        let a = farmer(&mut pool, 0, 30); let b = farmer(&mut pool, 0, 30);
        let low = farmer(&mut pool, 0, 30); let high = farmer(&mut pool, 0, 30);
        for patient in [a, b] {
            kin(&mut pool, patient, high); kin(&mut pool, patient, low);
            recorded(&mut pool, patient, low, relationships::BondType::Kin);
        }
        let mut permuted = copy_pool(&pool);
        for patient in [a, b] {
            permuted.rel_target_ids[patient].swap(0, 1);
            permuted.rel_bond_types[patient].swap(0, 1);
        }
        let ids = [pool.ids[b], pool.ids[a], pool.ids[a]];
        let work = prepare_with_policy(&mut pool, &ids, &[], &[], 1, 0.5, 0.2, CarePolicy::RetainedKin);
        let other = prepare_with_policy(&mut permuted, &[ids[1], ids[0]], &[], &[], 1, 0.5, 0.2, CarePolicy::RetainedKin);
        same_work(&work, &other);
        assert_eq!(work.rows, vec![(pool.ids[a], 0, pool.ids[low], 0.2), (pool.ids[b], 0, pool.ids[high], 0.2)]);
        assert_eq!(work.recipients, vec![2]);
        assert_eq!(work.care, vec![0.2_f32 as f64 + 0.2_f32 as f64]);
        assert_eq!(pool.health_work_loss[low], (pool.ids[low], 0.2));
        assert_eq!(pool.health_work_loss[high], (pool.ids[high], 0.2));
    }

    #[test]
    fn missing_asymmetric_dead_reused_or_ineligible_kin_supply_no_care() {
        for fault in 0..11 {
            let mut pool = AgentPool::new(8);
            let patient = farmer(&mut pool, 0, 30); let donor = farmer(&mut pool, 0, 30);
            kin(&mut pool, patient, donor);
            let mut ids = vec![pool.ids[patient]]; let mut excluded = vec![]; let mut urban = vec![];
            match fault {
                0 => pool.regions[donor] = 1,
                1 => pool.ages[donor] = agent::AGE_ADULT - 1,
                2 => pool.occupations[donor] = Occupation::Merchant as u8,
                3 => pool.trip_phase[donor] = agent::TRIP_PHASE_TRANSIT,
                4 => excluded.push(pool.ids[donor]),
                5 => { pool.settlement_ids[donor] = 9; urban.push(9); },
                6 => ids.push(pool.ids[donor]),
                7 => pool.rel_count[donor] = 0,
                8 => pool.kill(donor),
                9 => { pool.kill(donor); assert_eq!(farmer(&mut pool, 0, 30), donor); },
                _ => pool.rel_target_ids[patient][0] = u32::MAX - 1,
            }
            let work = prepare_with_policy(&mut pool, &ids, &excluded, &urban, 2, 0.5, 0.2, CarePolicy::RetainedKin);
            assert!(work.rows.iter().all(|row| row.2 == 0), "fault={fault}");
            assert_eq!(work.care, vec![0.0, 0.0]);
            assert_eq!(work.recipients, vec![0, 0]);
        }
    }

    #[test]
    fn parent_ids_and_full_or_self_only_stores_do_not_infer_a_caregiver() {
        for full in [false, true] {
            let mut pool = AgentPool::new(16);
            let parent = farmer(&mut pool, 0, 40); let child = farmer(&mut pool, 0, 20);
            pool.parent_id_0[child] = pool.ids[parent];
            if full {
                for _ in 0..relationships::REL_SLOTS {
                    recorded(&mut pool, parent, parent, relationships::BondType::Kin);
                }
            }
            let id = pool.ids[parent];
            let work = prepare_with_policy(&mut pool, &[id], &[], &[0], 1, 0.5, 0.2, CarePolicy::RetainedKin);
            assert_eq!(work.rows, vec![(id, 0, 0, 0.0)]);
            assert_eq!(work.recipients, vec![0]);
        }
    }

    #[test]
    fn kin_loss_is_consumed_once_and_donor_slot_reuse_keeps_full_income() {
        let mut pool = AgentPool::new(8);
        let patient = farmer(&mut pool, 0, 30); let donor = farmer(&mut pool, 0, 30);
        kin(&mut pool, patient, donor);
        let id = pool.ids[patient];
        let work = prepare_with_policy(&mut pool, &[id], &[], &[], 1, 0.5, 0.2, CarePolicy::RetainedKin);
        assert_eq!(work.losses, vec![0.5 + 0.2]);
        assert_eq!(work.impaired, vec![0.5]);
        assert_eq!(work.workers.iter().find(|w| w.id == pool.ids[donor]).unwrap().available.to_bits(), (1.0_f32 - 0.2).to_bits());
        let mut region = RegionState::new(0); region.resource_yields[0] = 1.0;
        region.farmer_income_modifier = 1.0; region.farm_productivity = 1.0;
        let signals = crate::signals::TickSignals { civs: vec![], contested_regions: vec![false] };
        let mut ranks = vec![0.0; pool.capacity()]; pool.wealth[patient] = 0.0; pool.wealth[donor] = 0.0;
        crate::tick::wealth_tick(&mut pool, &[region.clone()], &signals, &mut ranks);
        assert_eq!(pool.wealth[donor], agent::BASE_FARMER_INCOME * (1.0 - 0.2) * (1.0 - agent::WEALTH_DECAY));
        assert!(pool.health_work_loss.is_empty());
        let old = pool.wealth[donor];
        crate::tick::wealth_tick(&mut pool, &[region.clone()], &signals, &mut ranks);
        assert_eq!(pool.wealth[donor], (old + agent::BASE_FARMER_INCOME) * (1.0 - agent::WEALTH_DECAY));
        prepare_with_policy(&mut pool, &[id], &[], &[], 1, 0.5, 0.2, CarePolicy::RetainedKin);
        let old_id = pool.ids[donor]; pool.kill(donor); let replacement = farmer(&mut pool, 0, 30);
        assert_eq!(replacement, donor); assert_ne!(pool.ids[replacement], old_id);
        pool.wealth[replacement] = 0.0;
        crate::tick::wealth_tick(&mut pool, &[region], &signals, &mut ranks);
        assert_eq!(pool.wealth[replacement], agent::BASE_FARMER_INCOME * (1.0 - agent::WEALTH_DECAY));
    }

    #[test]
    fn kin_economy_work_income_and_food_budget_match_the_existing_contract() {
        use crate::economy::{EconomyRegionInput, EconomyConfig, RegionAgentCounts,
            NUM_GOODS, tick_economy_core};
        for (curve, slots) in [(false, false), (true, false), (true, true)] {
            let mut pool = AgentPool::new(10);
            for _ in 0..10 { let s = farmer(&mut pool, 0, 30); pool.wealth[s] = 0.0; }
            kin(&mut pool, 0, 1);
            let patient = pool.ids[0];
            let work = prepare_with_policy(&mut pool, &[patient], &[], &[], 1, 0.5, 0.2, CarePolicy::RetainedKin);
            let available = 10.0 - work.losses[0];
            let input = EconomyRegionInput {
                region_id: 0, terrain: 0, storage_population: 10,
                resource_types: [0, 255, 255], resource_yields: [1.0, 0.0, 0.0],
                production_caps: [None; 3], stockpile: [0.0; NUM_GOODS], subsistence_yield: 0.0,
                farm_labor_factor: available / 10.0, craft_raw_demand: 0.0, craft_demand: 0.0,
                farm_labor_ref: if curve { 5.0 } else { 0.0 }, farm_labor_half: 5.0,
                slot_curves: slots, slot_labor_ref: [0.0; 3], slot_labor_half: [0.0; 3],
            };
            let counts = RegionAgentCounts { population: 10, farmer_count: 10,
                soldier_count: 0, merchant_count: 0, wealthy_count: 0 };
            let config = EconomyConfig::default();
            let output = tick_economy_core(&[input], &[counts], &[], &[0.0], &[0], 1,
                &[0], &config, 1.0, false, None);
            let rr = &output.region_results[0];
            assert_eq!(rr.market_demand[0], 10.0 * config.per_capita_food);
            let expected_work = if curve { crate::economy::effective_farm_labor(available, 5.0, 5.0) } else { available };
            assert!((rr.slot_output[0] - expected_work).abs() < 1e-5);
            if !curve { assert_eq!(rr.farm_productivity, 1.0); }
            let mut region = RegionState::new(0);
            region.resource_yields[0] = 1.0;
            region.farmer_income_modifier = rr.farmer_income_modifier;
            region.farm_productivity = rr.farm_productivity;
            let signals = crate::signals::TickSignals { civs: vec![], contested_regions: vec![false] };
            let mut ranks = vec![0.0; 10];
            crate::tick::wealth_tick(&mut pool, &[region], &signals, &mut ranks);
            let expected_income = agent::BASE_FARMER_INCOME * rr.farmer_income_modifier
                * expected_work * (1.0 - agent::WEALTH_DECAY);
            assert!((pool.wealth.iter().sum::<f32>() - expected_income).abs() < 1e-5,
                "curve={curve} slots={slots}: income must scale with effective work only once");
            assert!((pool.wealth[0] / pool.wealth[2] - 0.5).abs() < 1e-6);
            assert!((pool.wealth[1] / pool.wealth[2] - 0.8).abs() < 1e-6);
        }
    }
    #[test]
    fn kin_transient_work_rebuilds_after_restore_movement_and_care_pause() {
        let mut pool = AgentPool::new(8);
        let patient = farmer(&mut pool, 0, 30); let donor = farmer(&mut pool, 0, 30);
        kin(&mut pool, patient, donor); let id = pool.ids[patient];
        let encoded = crate::persist::encode(crate::persist::KIND_AGENT, &pool);
        let work = prepare_with_policy(&mut pool, &[id], &[], &[], 2, 0.5, 0.2, CarePolicy::RetainedKin);
        assert_eq!(encoded, crate::persist::encode(crate::persist::KIND_AGENT, &pool));
        let mut restored = copy_pool(&pool);
        assert!(restored.health_work_loss.is_empty());
        let rebuilt = prepare_with_policy(&mut restored, &[id], &[], &[], 2, 0.5, 0.2, CarePolicy::RetainedKin);
        same_work(&work, &rebuilt);
        pool.regions[donor] = 1;
        let moved = prepare_with_policy(&mut pool, &[id], &[], &[], 2, 0.5, 0.2, CarePolicy::RetainedKin);
        assert_eq!(moved.rows, vec![(id, 0, 0, 0.0)]);
        assert_eq!(moved.care, vec![0.0, 0.0]);
        assert_eq!(moved.workers.iter().find(|w| w.id == pool.ids[donor]).unwrap().available, 1.0);
        pool.regions[donor] = 0;
        let paused = prepare_with_policy(&mut pool, &[id], &[], &[], 2, 0.5, 0.0, CarePolicy::RetainedKin);
        assert_eq!(paused.rows, vec![(id, 0, 0, 0.0)]);
        assert_eq!(paused.recipients, vec![0, 0]);
        let full = prepare_with_policy(&mut pool, &[id], &[], &[], 2, 0.5, 1.0, CarePolicy::RetainedKin);
        assert_eq!(full.rows, vec![(id, 0, pool.ids[donor], 1.0)]);
        assert_eq!(full.workers.iter().find(|w| w.id == pool.ids[donor]).unwrap().available, 0.0);
    }

}
