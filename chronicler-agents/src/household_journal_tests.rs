//! Differential contract and opt-in phase measurements, not production code.
use super::*;
use crate::agent::{Occupation, PARENT_NONE, TRIP_PHASE_TRANSIT};
use crate::relationships::{upsert_symmetric, BondType};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;

fn copy_pending(p: &PendingDecisions) -> PendingDecisions {
    // Exhaustive: a future decision field must join the differential contract.
    let PendingDecisions {
        rebellions, migrations, occupation_switches, loyalty_flips, loyalty_drifts,
        migration_changed_by_religion, loyalty_drifts_damped_by_rally,
        migration_drivers, migration_dominant, migration_followers,
    } = p;
    PendingDecisions {
        rebellions: rebellions.clone(), migrations: migrations.clone(),
        occupation_switches: occupation_switches.clone(), loyalty_flips: loyalty_flips.clone(),
        loyalty_drifts: loyalty_drifts.clone(),
        migration_changed_by_religion: *migration_changed_by_religion,
        loyalty_drifts_damped_by_rally: *loyalty_drifts_damped_by_rally,
        migration_drivers: migration_drivers.clone(), migration_dominant: migration_dominant.clone(),
        migration_followers: migration_followers.clone(),
    }
}

fn pending_bytes(p: &PendingDecisions) -> Vec<u8> {
    use crate::persist::{Persist, Writer};
    let PendingDecisions {
        rebellions, migrations, occupation_switches, loyalty_flips, loyalty_drifts,
        migration_changed_by_religion, loyalty_drifts_damped_by_rally,
        migration_drivers, migration_dominant, migration_followers,
    } = p;
    let mut w = Writer::new();
    rebellions.put(&mut w); migrations.put(&mut w); occupation_switches.put(&mut w);
    loyalty_flips.put(&mut w); loyalty_drifts.put(&mut w);
    migration_changed_by_religion.put(&mut w); loyalty_drifts_damped_by_rally.put(&mut w);
    migration_drivers.put(&mut w); migration_dominant.put(&mut w); migration_followers.put(&mut w);
    w.buf
}

fn compare<L: crate::pool::SlotLookup>(pool: &AgentPool, input: &[PendingDecisions],
                                      regions: &[RegionState], contested: &[bool], lookup: &L) {
    let mut base: Vec<_> = input.iter().map(copy_pending).collect();
    let mut head: Vec<_> = input.iter().map(copy_pending).collect();
    let mut old_stats = HouseholdStats::default();
    let mut new_stats = HouseholdStats::default();
    for _ in 0..2 {
        reference::consolidate_household_migrations_reference(pool, &mut base, regions,
                                                              contested, lookup, &mut old_stats);
        consolidate_household_migrations(pool, &mut head, regions, contested, lookup, &mut new_stats);
        assert_eq!(base.iter().map(pending_bytes).collect::<Vec<_>>(),
                   head.iter().map(pending_bytes).collect::<Vec<_>>());
        assert_eq!(crate::persist::encode(77, &old_stats), crate::persist::encode(77, &new_stats));
    }
}

fn spawn(pool: &mut AgentPool, region: u16, age: u16) -> usize {
    pool.spawn(region, 0, Occupation::Farmer, age, 0.5, 0.5, 0.5, 0, 0, 0, 255)
}

fn family(pool: &mut AgentPool, region: u16, dependents: usize) -> Vec<usize> {
    let a = spawn(pool, region, 30);
    let b = spawn(pool, region, 28);
    upsert_symmetric(pool, a, b, BondType::Marriage as u8, 50, 1);
    let mut slots = vec![a, b];
    for _ in 0..dependents {
        let child = spawn(pool, region, 10);
        pool.parent_id_0[child] = pool.ids[a];
        pool.parent_id_1[child] = pool.ids[b];
        slots.push(child);
    }
    slots
}

#[test]
fn journal_retains_first_lookup_last_emission_and_reinsert_order() {
    let mut j = MigrationJournal::new(vec![(1, 0, 1), (2, 0, 2), (1, 0, 3)]);
    assert_eq!(j.first(1), Some((1, 0, 1)));
    j.remove(1);
    assert_eq!(j.first(1), None);
    j.remove(1);
    j.push((1, 0, 4));
    j.push((1, 0, 5));
    assert_eq!(j.first(1), Some((1, 0, 4)));
    assert_eq!(j.finish(), vec![(2, 0, 2), (1, 0, 5)]);
}

#[test]
fn journal_matches_reference_for_conflicting_shared_households() {
    let mut pool = AgentPool::new(20);
    let a = family(&mut pool, 0, 2);
    let b = family(&mut pool, 0, 2);
    // One dependent belongs to both households; the later pair replaces its move.
    pool.parent_id_1[a[2]] = pool.ids[b[0]];
    let mut input: Vec<_> = (0..3).map(|_| PendingDecisions::new()).collect();
    input[0].migrations = vec![(a[0], 0, 1), (a[0], 0, 2), (a[1], 0, 2),
                              (b[0], 0, 2), (a[2], 0, 1), (b[1], 0, 1)];
    input[0].occupation_switches = vec![(a[1], 3), (a[2], 4), (a[1], 2)];
    input[0].rebellions = vec![(a[2], 0), (a[2], 2)];
    input[0].loyalty_flips = vec![(a[1], 4)];
    input[0].loyalty_drifts = vec![(a[1], -0.0), (a[2], f32::from_bits(0x7fc00001))];
    input[0].migration_dominant = vec![(a[0], 1), (b[0], 2)];
    input[0].migration_followers = vec![(a[2], 5)];
    let regions: Vec<_> = (0..3).map(RegionState::new).collect();
    compare(&pool, &input, &regions, &[false; 3], &pool.build_id_slots());
}

#[test]
fn journal_matches_reference_when_later_pairs_read_replaced_lead_decisions() {
    let mut pool = AgentPool::new(8);
    let slots: Vec<_> = (0..4).map(|_| spawn(&mut pool, 0, 30)).collect();
    // A stale/asymmetric relationship chain can yield overlapping canonical
    // pairs without giving any single agent multiple Marriage bonds.
    for i in 0..3 {
        pool.rel_count[slots[i]] = 1;
        pool.rel_bond_types[slots[i]][0] = BondType::Marriage as u8;
        pool.rel_target_ids[slots[i]][0] = pool.ids[slots[i + 1]];
    }
    let mut input = vec![PendingDecisions::new()];
    input[0].migrations = vec![(slots[0], 0, 1), (slots[1], 0, 2),
                              (slots[2], 0, 2), (slots[1], 0, 0)];
    let regions: Vec<_> = (0..3).map(RegionState::new).collect();
    compare(&pool, &input, &regions, &[false; 3], &pool.build_id_slots());
    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut input, &regions, &[false; 3],
                                     &pool.build_id_slots(), &mut stats);
    assert_eq!(input[0].migrations, slots.iter().map(|&s| (s, 0, 1)).collect::<Vec<_>>());
    let unknown = crate::migration_drivers::MIGRATION_TERMS as u8;
    assert_eq!(input[0].migration_followers,
               vec![(slots[1], unknown), (slots[2], unknown), (slots[3], unknown)]);
}

#[test]
fn journal_matches_reference_for_seeded_conflicts_stale_and_recycled_slots() {
    for seed in 0..768 {
        let mut rng = ChaCha8Rng::seed_from_u64(seed);
        let mut pool = AgentPool::new(64);
        let mut families = Vec::new();
        for _ in 0..8 {
            families.push(family(&mut pool, rng.gen_range(0..3), 2));
        }
        let stale = pool.build_id_to_slot();
        let removed = families[2][1];
        pool.kill(removed);
        if seed % 2 == 0 {
            assert_eq!(spawn(&mut pool, 0, 25), removed);
        }
        pool.kill(families[4][2]);
        // Married minors, shared parents and travelling spouses exercise the
        // unchanged eligibility checks rather than assuming a well-formed tree.
        upsert_symmetric(&mut pool, families[0][2], families[1][2],
                         BondType::Marriage as u8, 50, 1);
        pool.parent_id_1[families[0][3]] = pool.ids[families[1][0]];
        pool.parent_id_0[families[3][2]] = PARENT_NONE;
        pool.trip_phase[families[5][1]] = TRIP_PHASE_TRANSIT;
        let mut regions: Vec<_> = (0..3).map(RegionState::new).collect();
        regions[2].food_sufficiency = 0.0;
        let contested = [false, false, seed % 3 == 0];
        let mut input: Vec<_> = (0..4).map(|_| PendingDecisions::new()).collect();
        for bucket in &mut input {
            for _ in 0..rng.gen_range(0..80) {
                let s = rng.gen_range(0..pool.capacity());
                // Duplicate and out-of-region declarations are deliberate.
                bucket.migrations.push((s, rng.gen_range(0..3), rng.gen_range(0..5)));
            }
            for _ in 0..rng.gen_range(0..25) {
                bucket.rebellions.push((rng.gen_range(0..pool.capacity()), 0));
                bucket.occupation_switches.push((rng.gen_range(0..pool.capacity()), 3));
            }
            bucket.migration_dominant = (0..pool.capacity()).map(|s| (s, (s % 6) as u8)).collect();
            bucket.migration_followers = vec![(0, 1), (0, 2)];
            bucket.loyalty_drifts = vec![(0, -0.0), (1, 0.125)];
            bucket.migration_drivers.decided = 11;
            bucket.migration_changed_by_religion = 7;
            bucket.loyalty_drifts_damped_by_rally = 4;
        }
        compare(&pool, &input, &regions, &contested, &stale);
        compare(&pool, &input, &regions, &contested, &pool.build_id_slots());
    }
}

fn benchmark_fixture(agents: usize, concentrated: bool, shock: bool, dependents: usize,
                     cancel: bool) -> (AgentPool, Vec<PendingDecisions>, Vec<RegionState>, Vec<bool>) {
    let n_regions = (agents.div_ceil(5_000)).max(4);
    let mut pool = AgentPool::new(agents);
    let mut input: Vec<_> = (0..n_regions).map(|_| PendingDecisions::new()).collect();
    let mut regions: Vec<_> = (0..n_regions).map(|r| RegionState::new(r as u16)).collect();
    let mut contested = vec![false; n_regions];
    let families = agents / (dependents + 2);
    for f in 0..families {
        let region = if concentrated && f < (families / 2).min(50_000 / (dependents + 2)) { 0 } else { 1 + f % (n_regions - 1) };
        let slots = family(&mut pool, region as u16, dependents);
        let stride = if shock { 4 } else { 100 };
        if f % stride == 0 {
            let target = (region + 1) % n_regions;
            input[region].migrations.push((slots[0], region as u16, target as u16));
            input[region].migration_dominant.push((slots[0], 1));
            input[region].occupation_switches.push((slots[1], 3));
            if cancel && f % 8 == 0 {
                input[region].rebellions.push((slots[1], region as u16));
            }
            if cancel && f % 8 == 4 {
                contested[target] = true;
                regions[target].food_sufficiency = 0.0;
            }
        }
    }
    (pool, input, regions, contested)
}

/// Run under an external process-CPU/RSS recorder, one CPU, after admission.
/// Each invocation can select one size/case/arm for separate memory receipts.
#[test]
#[ignore = "prospective phase benchmark; root allocates CPU before running"]
fn benchmark_household_journal() {
    use std::time::Instant;
    let agents = std::env::var("HOUSEHOLD_BENCH_AGENTS").ok().map(|s| s.parse().unwrap()).unwrap_or(1_000);
    let case = std::env::var("HOUSEHOLD_BENCH_CASE").unwrap_or_else(|_| "normal-spread".into());
    let arm = std::env::var("HOUSEHOLD_BENCH_ARM").unwrap_or_else(|_| "both".into());
    let concentrated = case.contains("concentrated");
    let shock = case.contains("shock");
    let cancel = case.contains("cancel");
    let dependents = if case.contains("one-dependent") { 1 } else { 2 };
    let (pool, input, regions, contested) = benchmark_fixture(agents, concentrated, shock, dependents, cancel);
    let lookup = pool.build_id_slots();
    if arm == "both" { compare(&pool, &input, &regions, &contested, &lookup); }
    let mut digest = None;
    for pair in 0..5 {
        let arms = if pair % 2 == 0 { ["base", "head"] } else { ["head", "base"] };
        for side in arms {
            if arm != "both" && arm != side { continue; }
            let mut decisions: Vec<_> = input.iter().map(copy_pending).collect();
            let mut stats = HouseholdStats::default();
            let start = Instant::now();
            if side == "base" {
                reference::consolidate_household_migrations_reference(&pool, &mut decisions,
                    &regions, &contested, &lookup, &mut stats);
            } else {
                consolidate_household_migrations(&pool, &mut decisions, &regions, &contested,
                                                 &lookup, &mut stats);
            }
            let nanos = start.elapsed().as_nanos();
            let bytes: Vec<_> = decisions.iter().flat_map(pending_bytes)
                .chain(crate::persist::encode(77, &stats)).collect();
            let hash = bytes.iter().fold(0xcbf29ce484222325u64, |h, b| (h ^ *b as u64).wrapping_mul(0x100000001b3));
            assert_eq!(*digest.get_or_insert(hash), hash);
            println!("household_bench agents={} regions={} case={} arm={} pair={} phase_ns={} input_migrations={} output_migrations={} followers={} digest={:016x}",
                pool.alive_count(), regions.len(), case, side, pair, nanos,
                input.iter().map(|p| p.migrations.len()).sum::<usize>(),
                decisions.iter().map(|p| p.migrations.len()).sum::<usize>(),
                stats.household_migrations_follow, hash);
        }
    }
}
