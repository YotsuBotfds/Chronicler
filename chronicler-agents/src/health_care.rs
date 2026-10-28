//! Derived, single-turn manual-work inputs. Persistent episodes belong to
//! Python WorldState; none of these slot references enters a checkpoint.
use std::collections::{BTreeMap, HashSet};
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
                available: 1.0 - deductions.get(&slot).copied().unwrap_or(0.0) });
        }
    }
    out
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
}
