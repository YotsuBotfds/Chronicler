//! Livelihoods L6b household retail (option R), native tick wiring (N2):
//! the farm income replacement is consumed by the 0.5 wealth phase and the
//! retail install by phase 0.7 right after L2, each exactly once; the next
//! tick runs neither.

use chronicler_agents::provisioning::{ProvisionConfig, RetailConfig, REGIME_EQUAL, RETAIL_MODE_RETAIL};
use chronicler_agents::wealth_transfer::{install_retail_income, PURPOSE_FOOD_PURCHASE};
use chronicler_agents::{tick_agents, AgentPool, CivSignals, Occupation, RegionState, TickSignals};

fn signals(n_regions: usize) -> TickSignals {
    TickSignals {
        civs: vec![CivSignals {
            civ_id: 0, stability: 50, is_at_war: false, dominant_faction: 0, faction_military: 0.33,
            faction_merchant: 0.33, faction_cultural: 0.34, faction_clergy: 0.0, shock_stability: 0.0,
            shock_economy: 0.0, shock_military: 0.0, shock_culture: 0.0, demand_shift_farmer: 0.0,
            demand_shift_soldier: 0.0, demand_shift_merchant: 0.0, demand_shift_scholar: 0.0,
            demand_shift_priest: 0.0, mean_boldness: 0.0, mean_ambition: 0.0, mean_loyalty_trait: 0.0,
            gini_coefficient: 0.0, conquered_this_turn: false, priest_tithe_share: 0.0,
            cultural_drift_multiplier: 1.0, religion_intensity_multiplier: 1.0,
        }],
        contested_regions: vec![false; n_regions],
    }
}

fn world() -> (AgentPool, Vec<RegionState>) {
    let mut regions: Vec<RegionState> = (0..2).map(|i| {
        let mut r = RegionState::new(i);
        r.population = 20;
        r.resource_types = [0, 255, 255];
        r.resource_yields = [1.0, 0.0, 0.0];
        r.food_sufficiency = 0.6;
        r
    }).collect();
    regions[1].food_sufficiency = 0.9;
    let mut pool = AgentPool::new(0);
    for i in 0..12 {
        let slot = pool.spawn((i % 2) as u16, 0, Occupation::Farmer, 30, 0.5, 0.5, 0.5, 0, 1, 2,
                              chronicler_agents::BELIEF_NONE);
        pool.wealth[slot] = 2.0 + i as f32 * 0.25;
    }
    (pool, regions)
}

fn tick(pool: &mut AgentPool, regions: &[RegionState], turn: u32) {
    let mut pct = vec![0.0f32; pool.capacity()];
    let seed = [7u8; 32];
    tick_agents(pool, regions, &signals(regions.len()), seed, turn, &mut pct, &mut Vec::new(), &[],
                &mut Default::default(), &[], None);
}

fn l2(turn: u32, pool: &AgentPool) -> ProvisionConfig {
    let mut counts = vec![0u32; 2];
    for s in 0..pool.capacity() {
        if pool.is_alive(s) { counts[pool.regions[s] as usize] += 1; }
    }
    ProvisionConfig { source_turn: turn, regime: REGIME_EQUAL, floor: 0.5, target_share: 0.5,
                      pre_release: vec![f32::NAN; 2], phase2_alive: counts }
}

#[test]
fn the_tick_consumes_retail_and_income_once_and_the_next_tick_runs_neither() {
    let (mut pool, regions) = world();
    let owners: Vec<u32> = (0..pool.capacity()).filter(|&s| pool.regions[s] == 0).map(|s| pool.ids[s]).take(2).collect();
    pool.food_allocation_config = Some(l2(5, &pool));
    pool.retail_config = Some(RetailConfig::new(5, RETAIL_MODE_RETAIL, 500, vec![(0, 300, 0.6)],
        vec![(owners[0], 0, 1500), (owners[1], 0, 200)], 2).unwrap());
    install_retail_income(&mut pool, 5, &[0], 2).unwrap();
    tick(&mut pool, &regions, 5);
    assert!(pool.retail_config.is_none() && pool.retail_income.is_none());
    assert!(pool.food_allocation_config.is_none());
    let frame = pool.retail_frame.take().expect("the tick ran retail");
    assert_eq!((frame.source_turn, frame.regions.len(), frame.regions[0].region), (5, 1, 0));
    let row = &frame.regions[0];
    assert!(row.sold_fair + row.sold_open > 0 && row.paid > 0);
    assert_eq!(row.paid, row.credited + row.refunded);
    // Six farmers of region 0 had their farm income replaced; region 1's did not.
    let receipt = pool.retail_income_receipt.take().expect("the wealth phase replaced income");
    assert_eq!((receipt.turn, receipt.rows.len()), (5, 6));
    assert!(receipt.rows.iter().all(|&(id, replaced)| replaced > 0.0
        && (0..pool.capacity()).any(|s| pool.ids[s] == id && pool.regions[s] == 0)));
    assert!(pool.wealth_transfer_log.contains(&(5, PURPOSE_FOOD_PURCHASE, 0)));
    // L2 still ran for every region and left its own receipt.
    assert_eq!(pool.provision_frame.take().unwrap().regions.len(), 2);
    // The next tick, with only L2 installed, runs no retail and replaces no income.
    pool.food_allocation_config = Some(l2(6, &pool));
    tick(&mut pool, &regions, 6);
    assert!(pool.retail_frame.is_none() && pool.retail_income_receipt.is_none());
    assert!(!pool.wealth_transfer_log.iter().any(|&(t, p, _)| t == 6 && p == PURPOSE_FOOD_PURCHASE));
    assert!(pool.provision_frame.is_some());
}

#[test]
fn an_install_without_pilot_regions_leaves_the_tick_bit_identical() {
    // L2 alone against L2 with an empty retail install and an empty income
    // install: the same people, wealth, needs and satisfaction, bit for bit.
    let (mut plain, regions) = world();
    let (mut empty, _) = world();
    for turn in 1..4 {
        plain.food_allocation_config = Some(l2(turn, &plain));
        empty.food_allocation_config = Some(l2(turn, &empty));
        empty.retail_config = Some(RetailConfig::new(turn, RETAIL_MODE_RETAIL, 500, vec![], vec![], 2).unwrap());
        install_retail_income(&mut empty, turn, &[], 2).unwrap();
        tick(&mut plain, &regions, turn);
        tick(&mut empty, &regions, turn);
        let frame = empty.retail_frame.take().unwrap();
        assert!(frame.regions.is_empty() && frame.money.is_empty() && frame.claims.is_empty());
        assert!(empty.retail_income_receipt.take().unwrap().rows.is_empty());
    }
    let bits = |p: &AgentPool| (0..p.capacity()).map(|s| (p.ids[s], p.alive[s], p.regions[s], p.wealth[s].to_bits(),
        p.need_safety[s].to_bits(), p.need_material[s].to_bits(), p.satisfactions[s].to_bits())).collect::<Vec<_>>();
    assert_eq!(bits(&plain), bits(&empty));
    assert_eq!(plain.provision_frame, empty.provision_frame);
}
