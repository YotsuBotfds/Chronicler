//! Exact checkpoint state: a pool saved and restored mid-run continues
//! exactly as the uninterrupted pool, and every simulator's layout is
//! described and fingerprinted.

use chronicler_agents::persist::{self, Persist};
use chronicler_agents::signals::{CivSignals, TickSignals};
use chronicler_agents::spatial::SpatialDiagnostics;
use chronicler_agents::{tick_agents, AgentPool, AgentSimulator, EcologySimulator, Occupation,
                        PoliticsSimulator, RegionState};

fn regions() -> Vec<RegionState> {
    (0..4)
        .map(|i| {
            let mut r = RegionState::new(i);
            r.population = 50;
            r.carrying_capacity = 50;
            r.soil = 0.5 + (i as f32) * 0.1;
            r.water = 0.4 + (i as f32) * 0.05;
            r.adjacency = (0..4).filter(|&j| j != i).collect();
            r
        })
        .collect()
}

fn signals() -> TickSignals {
    TickSignals {
        civs: (0..4)
            .map(|i| CivSignals {
                civ_id: i as u8,
                stability: if i == 2 { 20 } else { 55 },
                is_at_war: i == 1,
                dominant_faction: (i % 3) as u8,
                faction_military: 0.3,
                faction_merchant: 0.4,
                faction_cultural: 0.3,
                shock_stability: 0.0,
                shock_economy: 0.0,
                shock_military: 0.0,
                shock_culture: 0.0,
                demand_shift_farmer: 0.0,
                demand_shift_soldier: 0.0,
                demand_shift_merchant: 0.0,
                demand_shift_scholar: 0.0,
                demand_shift_priest: 0.0,
                mean_boldness: 0.0,
                mean_ambition: 0.0,
                mean_loyalty_trait: 0.0,
                faction_clergy: 0.0,
                gini_coefficient: 0.0,
                conquered_this_turn: false,
                priest_tithe_share: 0.0,
                cultural_drift_multiplier: 1.0,
                religion_intensity_multiplier: 1.0,
            })
            .collect(),
        contested_regions: vec![false, true, false, false],
    }
}

fn pool(regions: &[RegionState]) -> AgentPool {
    let mut pool = AgentPool::new(0);
    for r in regions {
        for k in 0..r.carrying_capacity {
            let occ = if k % 5 == 0 { Occupation::Merchant } else { Occupation::Farmer };
            pool.spawn(r.region_id, r.region_id as u8, occ, (k * 3) % 70, 0.1, -0.2, 0.3,
                       1, 2, 3, chronicler_agents::BELIEF_NONE);
        }
    }
    pool
}

fn tick(pool: &mut AgentPool, regions: &[RegionState], turn: u32, pct: &mut Vec<f32>) {
    let mut seed = [0u8; 32];
    seed[0] = 7;
    if pct.len() < pool.capacity() {
        pct.resize(pool.capacity(), 0.0);
    }
    tick_agents(pool, regions, &signals(), seed, turn, pct, &mut Vec::new(), &[],
                &mut SpatialDiagnostics::default(), &[], None);
}

fn bytes<T: Persist>(value: &T) -> Vec<u8> {
    persist::encode(persist::KIND_AGENT, value)
}

#[test]
fn restored_pool_continues_exactly() {
    let regions = regions();
    let mut straight = pool(&regions);
    let mut pct = Vec::new();
    for turn in 0..12 {
        tick(&mut straight, &regions, turn, &mut pct);
    }
    let saved = bytes(&straight);
    let saved_pct = pct.clone();
    for turn in 12..30 {
        tick(&mut straight, &regions, turn, &mut pct);
    }

    let mut resumed: AgentPool = persist::decode(persist::KIND_AGENT, &saved).unwrap();
    assert_eq!(bytes(&resumed), saved, "decode then encode is the identity");
    let mut pct = saved_pct;
    for turn in 12..30 {
        tick(&mut resumed, &regions, turn, &mut pct);
    }
    assert!(straight.alive_count() > 0);
    assert_eq!(bytes(&resumed), bytes(&straight));
    assert_eq!(resumed.to_record_batch().unwrap(), straight.to_record_batch().unwrap());
}

#[test]
fn region_states_round_trip_bit_for_bit() {
    let mut rs = regions();
    rs[1].realized_extraction = Some([0.5, f32::NAN, -0.0]);
    rs[2].stockpile[3] = 12.25;
    let blob = persist::encode(persist::KIND_ECOLOGY, &rs);
    let back: Vec<RegionState> = persist::decode(persist::KIND_ECOLOGY, &blob).unwrap();
    assert_eq!(persist::encode(persist::KIND_ECOLOGY, &back), blob);
    assert_eq!(back[1].realized_extraction.unwrap()[1].to_bits(), f32::NAN.to_bits());
    assert_eq!(back[1].realized_extraction.unwrap()[2].to_bits(), (-0.0f32).to_bits());
}

#[test]
fn simulators_describe_distinct_fingerprinted_layouts() {
    let (va, fa, sa) = AgentSimulator::checkpoint_schema();
    let (ve, fe, se) = EcologySimulator::checkpoint_schema();
    let (vp, fp, sp) = PoliticsSimulator::checkpoint_schema();
    assert_eq!((va, ve, vp), (persist::STATE_VERSION, persist::STATE_VERSION, persist::STATE_VERSION));
    assert!(sa.starts_with("AgentSimulator{pool:AgentPool{ids:Vec<u32>,"));
    assert!(sa.contains("!snapshot_cache,"), "the snapshot cache is derived and skipped");
    assert!(se.starts_with("EcologySimulator{regions:Vec<RegionState{"));
    assert!(sp.starts_with("PoliticsSimulator{politics_config:PoliticsConfig{"));
    assert_eq!(fa, format!("{:016x}", persist::fingerprint(&sa)));
    assert!(fa != fe && fe != fp && fa != fp);
}

#[test]
fn simulator_blobs_refuse_the_wrong_simulator() {
    let blob = persist::encode(persist::KIND_POLITICS, &PoliticsSimulator::new());
    let back: PoliticsSimulator = persist::decode(persist::KIND_POLITICS, &blob).unwrap();
    assert_eq!(persist::encode(persist::KIND_POLITICS, &back), blob);
    let err = match persist::decode::<EcologySimulator>(persist::KIND_ECOLOGY, &blob) {
        Ok(_) => panic!("a politics blob decoded as ecology state"),
        Err(e) => e,
    };
    assert!(err.0.contains("kind"), "{err}");
    let fresh = AgentSimulator::new(3, 42);
    let blob = persist::encode(persist::KIND_AGENT, &fresh);
    let back: AgentSimulator = persist::decode(persist::KIND_AGENT, &blob).unwrap();
    assert_eq!(persist::encode(persist::KIND_AGENT, &back), blob);
}
