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
    assert!(row.sold_fair_milli + row.sold_open_milli > 0 && row.paid_milli > 0);
    assert_eq!(row.paid_milli, row.credited_milli + row.refunded_milli);
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

#[test]
fn two_consecutive_retail_ticks_settle_once_each_and_carry_the_claims() {
    let (mut pool, regions) = world();
    let owners: Vec<u32> = (0..pool.capacity()).filter(|&s| pool.regions[s] == 0).map(|s| pool.ids[s]).take(2).collect();
    let mut claims = vec![(owners[0], 0u16, 1500i64), (owners[1], 0, 200)];
    for turn in [5u32, 6] {
        pool.food_allocation_config = Some(l2(turn, &pool));
        pool.retail_config = Some(RetailConfig::new(turn, RETAIL_MODE_RETAIL, 500, vec![(0, 300, 0.6)],
            claims.clone(), 2).unwrap());
        install_retail_income(&mut pool, turn, &[0], 2).unwrap();
        tick(&mut pool, &regions, turn);
        let frame = pool.retail_frame.take().expect("each tick runs retail");
        let row = &frame.regions[0];
        assert_eq!(frame.source_turn, turn);
        assert_eq!(row.paid_milli, row.credited_milli + row.refunded_milli);
        assert_eq!(row.offered_milli, claims.iter().map(|c| c.2).sum::<i64>());
        assert!(pool.retail_income_receipt.take().is_some_and(|r| r.turn == turn));
        assert!(pool.wealth_transfer_log.contains(&(turn, PURPOSE_FOOD_PURCHASE, 0)));
        // Python's part: what is neither eaten nor sold is carried to the next turn.
        claims = frame.claims.iter().zip(&claims)
            .map(|(&(o, r, eaten, sold), &(_, _, held))| (o, r, held - eaten - sold)).collect();
    }
    assert!(claims.iter().map(|c| c.2).sum::<i64>() < 1700);
}

/// The fair share is reachable from the Phase 2 split: with nothing withheld,
/// the free food and the owned food Phase 2 leaves on offer cover `cf` for
/// everyone (reviewer D's B1: the owned stock was counted before its decay).
#[test]
fn the_fair_share_the_economy_reports_is_on_offer_at_phase_0_7() {
    use chronicler_agents::economy::{tick_economy_core_full, EconomyConfig, EconomyExtras, EconomyRegionInput,
        HybridDeliveryInput, RegionAgentCounts, RetailRegionInput, NUM_GOODS, RETAIL_FOOD_SLOTS, SLOT_FISH,
        SLOT_GRAIN, SLOT_SALT};
    use chronicler_agents::merchant::DeliveryBuffer;
    use chronicler_agents::provisioning::retail;
    // (commons grain, owned grain, owned fish, owned salt, farmers, people, storage population, θ)
    let cases = [(2.0, 6.0, 1.0, 0.0, 10, 50, 100, 0.9), (0.0, 12.0, 3.0, 2.0, 6, 60, 100, 1.0),
                 (5.0, 30.0, 0.0, 0.0, 8, 90, 6, 0.9), (1.0, 0.0, 0.0, 0.0, 12, 40, 100, 0.0),
                 (0.0, 40.0, 4.0, 1.0, 0, 120, 100, 0.9), (3.0, 9.0, 2.5, 0.5, 14, 70, 20, 0.5)];
    for (case, &(commons, grain, fish, salt, farmers, people, storage, theta)) in cases.iter().enumerate() {
        let mut stock = [0.0f32; NUM_GOODS];
        stock[SLOT_GRAIN] = commons;
        let mut owned = [0.0f32; NUM_GOODS];
        owned[SLOT_GRAIN] = grain;
        owned[SLOT_FISH] = fish;
        owned[SLOT_SALT] = salt;
        let region = EconomyRegionInput {
            region_id: 0, terrain: 0, storage_population: storage, resource_types: [0, 255, 255],
            resource_yields: [1.0, 0.0, 0.0], production_caps: [None; 3], stockpile: stock, subsistence_yield: 0.0,
            farm_labor_factor: 1.0, craft_raw_demand: 0.0, craft_demand: 0.0, farm_labor_ref: 0.0,
            farm_labor_half: 0.0, slot_curves: false, slot_labor_ref: [0.0; 3], slot_labor_half: [0.0; 3],
        };
        let counts = [RegionAgentCounts { population: people, farmer_count: farmers, soldier_count: 0,
                                          merchant_count: 0, wealthy_count: 0 }];
        let delivery = HybridDeliveryInput::from_buffer(&DeliveryBuffer::new(1), 1);
        let rows = [Some(RetailRegionInput { title_share: theta, owned })];
        let economy = tick_economy_core_full(&[region], &counts, &[], &[0.0], &[0], 1, &[0],
            &EconomyConfig::default(), 1.0, false, Some(&delivery),
            &EconomyExtras { retail: Some(&rows), ..Default::default() });
        let result = &economy.region_results[0];
        let rt = economy.retail.as_ref().unwrap()[0].as_ref().unwrap();
        assert!(result.food_sufficiency < 1.0, "case {case} must be short");
        // Python's part: owned food in whole milli-food (nearest, as Python
        // titles), split over the first `farmers` people; free rations from the
        // commons draw-down.
        let offered: i64 = RETAIL_FOOD_SLOTS.iter().map(|&g| (rt.owned_close[g] as f64 * 1000.0).round() as i64).sum();
        let mut pool = AgentPool::new(people as usize);
        for _ in 0..people {
            let s = pool.spawn(0, 0, Occupation::Farmer, 30, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
            pool.wealth[s] = 50.0;
        }
        let owners: Vec<u32> = pool.ids[..(farmers.max(1) as usize)].to_vec();
        let share = offered / owners.len() as i64;
        let claims: Vec<(u32, u16, i64)> = owners.iter().enumerate()
            .map(|(i, &o)| (o, 0, share + if (i as i64) < offered % owners.len() as i64 { 1 } else { 0 })).collect();
        let mut regions = vec![RegionState::new(0)];
        regions[0].food_sufficiency = result.food_sufficiency;
        let l2 = ProvisionConfig { source_turn: 1, regime: REGIME_EQUAL, floor: 0.5, target_share: 0.5,
                                   pre_release: vec![f32::NAN], phase2_alive: vec![people] };
        let free = rt.commons_consumed / 0.5;
        let cfg = RetailConfig::new(1, RETAIL_MODE_RETAIL, 500, vec![(0, 300, free)], claims, 1).unwrap();
        let (access, ids, _) = chronicler_agents::provisioning::allocate(&pool, &regions, &l2);
        pool.food_access_regions = pool.regions.clone();
        pool.food_access = access;
        pool.food_access_ids = ids;
        let frame = retail(&mut pool, &regions, &l2, &cfg, 1).unwrap();
        let row = &frame.regions[0];
        assert_eq!(row.withheld_dead_milli, 0);
        // The invariant (a few milli-food of rounding at most).
        let need = row.fair_share * row.persons as f64;
        let on_offer = row.free_living + row.offered_milli as f64 / 500.0;
        assert!(on_offer >= need - 6.0 / 500.0, "case {case}: {on_offer} < {need}");
        // With cash in hand nobody is left short for want of an offer.
        assert_eq!(row.priced_out_persons, 0, "case {case}");
        assert!(row.offer_short_deficit <= 6.0 / 500.0 + 1e-9, "case {case}: {row:?}");
        assert!(row.fed_fair + row.offer_short_persons == row.persons);
    }
}
