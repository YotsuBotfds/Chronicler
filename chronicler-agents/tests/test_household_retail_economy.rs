//! Livelihoods L6b household retail (option R), native economy (N1).
//!
//! Pilot regions pass the title share θ and their owned food stock; owned
//! food counts in availability, prices and sufficiency, decays and is capped
//! with the commons, and the consumption draw-down takes the commons only.
//! Without the inputs (or for a non-pilot region) every output keeps its bits.

use chronicler_agents::economy::{
    tick_economy_core, tick_economy_core_full, EconomyExtras, WoodcutInput, EconomyConfig, EconomyOutput, EconomyRegionInput, HybridDeliveryInput, RegionAgentCounts,
    RetailRegionInput, TradeRouteInput, CAT_FOOD, GOOD_CATEGORY, NUM_GOODS, RETAIL_FOOD_SLOTS,
    SLOT_BOTANICALS, SLOT_EXOTIC, SLOT_FISH, SLOT_GRAIN, SLOT_SALT, SLOT_TIMBER,
};
use chronicler_agents::merchant::DeliveryBuffer;

fn region(region_id: u16, rt: u8, yield_0: f32) -> EconomyRegionInput {
    EconomyRegionInput {
        region_id,
        terrain: 0,
        storage_population: 100,
        resource_types: [rt, 255, 255],
        resource_yields: [yield_0, 0.0, 0.0],
        production_caps: [None; 3],
        stockpile: [0.0; NUM_GOODS],
        subsistence_yield: 0.0,
        farm_labor_factor: 1.0,
        craft_raw_demand: 0.0,
        craft_demand: 0.0,
        farm_labor_ref: 0.0,
        farm_labor_half: 0.0,
        slot_curves: false,
        slot_labor_ref: [0.0; 3],
        slot_labor_half: [0.0; 3],
    }
}

fn agents(pop: u32, farmers: u32) -> RegionAgentCounts {
    RegionAgentCounts { population: pop, farmer_count: farmers, soldier_count: 2, merchant_count: 1, wealthy_count: 1 }
}

fn owned(values: [(usize, f32); 5]) -> [f32; NUM_GOODS] {
    let mut out = [0.0; NUM_GOODS];
    for (g, v) in values {
        out[g] = v;
    }
    out
}

/// Three regions, a binding cap, salt, timber, merchant arrivals, returns and
/// departures, and routes so the oracle shadow runs.
fn scenario() -> (Vec<EconomyRegionInput>, Vec<RegionAgentCounts>, Vec<TradeRouteInput>, DeliveryBuffer) {
    let mut a = region(0, 0, 1.3);
    a.stockpile[SLOT_GRAIN] = 11.0;
    a.stockpile[SLOT_SALT] = 2.0;
    a.stockpile[SLOT_FISH] = 3.5;
    a.stockpile[SLOT_TIMBER] = 4.0;
    a.storage_population = 4; // cap 10: grain binds
    let mut b = region(1, 3, 0.9); // fish
    b.stockpile[SLOT_BOTANICALS] = 1.25;
    b.stockpile[SLOT_EXOTIC] = 0.75;
    let mut c = region(2, 2, 0.6); // botanicals
    c.subsistence_yield = 0.3;
    let counts = vec![agents(30, 14), agents(18, 9), agents(9, 4)];
    let routes = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
        TradeRouteInput { origin_region_id: 1, dest_region_id: 0, is_river: true },
        TradeRouteInput { origin_region_id: 1, dest_region_id: 2, is_river: false },
    ];
    let mut buf = DeliveryBuffer::new(3);
    buf.record_departure(0, SLOT_GRAIN, 2.0);
    buf.record_arrival(0, 1, SLOT_GRAIN as u8, 1.5);
    buf.record_arrival(1, 2, SLOT_FISH as u8, 0.8);
    buf.return_credits[1][SLOT_FISH] = 0.3;
    (vec![a, b, c], counts, routes, buf)
}

fn run(retail: Option<&[Option<RetailRegionInput>]>) -> EconomyOutput {
    let (regions, counts, routes, buf) = scenario();
    let delivery = HybridDeliveryInput::from_buffer(&buf, 3);
    tick_economy_core_full(&regions, &counts, &routes, &[3.0, 1.0], &[2, 1], 2, &[0, 1, 0],
        &EconomyConfig::default(), 1.0, false, Some(&delivery), &EconomyExtras { retail, ..Default::default() })
}

fn bits(out: &EconomyOutput) -> Vec<u64> {
    let mut v: Vec<u64> = Vec::new();
    let f = |x: f32| x.to_bits() as u64;
    for r in &out.region_results {
        v.push(r.region_id as u64);
        v.extend(r.food_ledger.map(f64::to_bits));
        v.push(f(r.granary_work_delivered));
        v.extend(r.stockpile.map(f));
        v.extend([f(r.farmer_income_modifier), f(r.food_sufficiency), f(r.merchant_margin),
            f(r.merchant_trade_income), r.trade_route_count as u64]);
        v.extend(r.market_demand.map(f));
        v.extend(r.market_supply.map(f));
        v.extend(r.market_price.map(f));
        v.extend([f(r.farm_productivity), f(r.craft_output), f(r.craft_sufficiency), f(r.forage_output)]);
        v.extend(r.slot_output.map(f));
        v.extend(r.craft_input.map(f));
    }
    for c in &out.civ_results {
        v.extend([c.civ_id as u64, f(c.treasury_tax), f(c.tithe_base), f(c.priest_tithe_share)]);
    }
    for o in &out.observability {
        v.extend([o.region_id as u64, f(o.imports_food), f(o.imports_raw_material), f(o.imports_luxury),
            f(o.imports_craft), f(o.stockpile_food), f(o.stockpile_raw_material), f(o.stockpile_luxury),
            f(o.stockpile_craft), f(o.import_share), o.trade_dependent as u64]);
    }
    for u in &out.upstream_sources {
        v.extend([u.dest_region_id as u64, u.source_ordinal as u64, u.source_region_id as u64]);
    }
    let c = &out.conservation;
    v.extend([c.production, c.transit_loss, c.consumption, c.storage_loss, c.cap_overflow,
        c.clamp_floor_loss, c.in_transit_delta.unwrap_or(f64::NAN)].map(f64::to_bits));
    for x in out.oracle_trade_volume.iter().flatten() { v.extend(x.map(f)); }
    for x in out.oracle_margins.iter().flatten() { v.push(f(*x)); }
    for x in out.oracle_food_sufficiency.iter().flatten() { v.push(f(*x)); }
    for x in out.transit_decay_by_region.iter().flatten() { v.extend(x.map(f)); }
    v
}

/// In a pilot region the carried owned stock's decay and overflow (`early`)
/// fall before `food_pre_consumption`; the ten-term balance closes as before.
fn assert_food_balance_with(ledger: &[f64; 10], early: f64) {
    let expected = ledger[0] + ledger[1] + ledger[2] - ledger[3] + ledger[4] - ledger[6] - ledger[7] - ledger[8];
    assert!((expected - ledger[9]).abs() < 1e-4, "ledger: {ledger:?}");
    let pre = ledger[0] + ledger[1] + ledger[2] - ledger[3] + ledger[4] - early;
    assert!((pre - ledger[5]).abs() < 1e-4, "ledger: {ledger:?}");
}

fn early(row: &chronicler_agents::economy::RetailRegionResult) -> f64 {
    (0..NUM_GOODS).map(|g| row.owned_decay[g] as f64 + row.owned_overflow[g] as f64).sum()
}

/// The commons' share of the opening cap overflow (in the ledger's cap term
/// only): the cap holds the commons net of this tick's departures and the
/// carried owned stock together.
fn commons_opening_overflow(input: &EconomyRegionInput, row: &chronicler_agents::economy::RetailRegionResult,
                            open: &RetailRegionInput, departures: &[f32; NUM_GOODS]) -> f64 {
    let cap = EconomyConfig::default().per_good_cap_factor * input.storage_population as f32;
    RETAIL_FOOD_SLOTS.iter().map(|&g| {
        let carried = open.owned[g] - row.owned_decay[g];
        let net = (input.stockpile[g] - departures[g]).max(0.0);
        let total = net + carried;
        if total > cap { (net - net * (cap / total)) as f64 } else { 0.0 }
    }).sum()
}

#[test]
fn retail_food_slots_are_exactly_the_food_goods() {
    for g in 0..NUM_GOODS {
        assert_eq!(RETAIL_FOOD_SLOTS.contains(&g), GOOD_CATEGORY[g] == CAT_FOOD, "slot {g}");
    }
    assert_eq!(RETAIL_FOOD_SLOTS, [SLOT_GRAIN, SLOT_FISH, SLOT_SALT, SLOT_BOTANICALS, SLOT_EXOTIC]);
}

#[test]
fn without_the_retail_inputs_every_output_keeps_its_bits() {
    let (regions, counts, routes, buf) = scenario();
    let delivery = HybridDeliveryInput::from_buffer(&buf, 3);
    let plain = tick_economy_core(&regions, &counts, &routes, &[3.0, 1.0], &[2, 1], 2, &[0, 1, 0],
        &EconomyConfig::default(), 1.0, false, Some(&delivery));
    let granary = tick_economy_core_full(&regions, &counts, &routes, &[3.0, 1.0], &[2, 1], 2,
        &[0, 1, 0], &EconomyConfig::default(), 1.0, false, Some(&delivery), &EconomyExtras::default());
    let absent = run(None);
    let no_pilot = run(Some(&[None, None, None]));
    assert!(plain.retail.is_none() && absent.retail.is_none());
    assert_eq!(no_pilot.retail, Some(vec![None, None, None]));
    // The scenario exercises the cap, salt, imports, departures and the oracle.
    assert!(plain.conservation.cap_overflow > 0.0 && plain.conservation.transit_loss > 0.0);
    assert!(plain.oracle_food_sufficiency.is_some());
    let reference = bits(&plain);
    assert_eq!(bits(&granary), reference);
    assert_eq!(bits(&absent), reference);
    assert_eq!(bits(&no_pilot), reference);
    // A pilot region leaves a non-pilot region's own stock and ledger untouched.
    let theta = RetailRegionInput { title_share: 0.9, owned: owned([(SLOT_GRAIN, 2.0), (SLOT_FISH, 0.0),
        (SLOT_SALT, 0.0), (SLOT_BOTANICALS, 0.0), (SLOT_EXOTIC, 0.0)]) };
    let mixed = run(Some(&[Some(theta), None, None]));
    for ri in 1..3 {
        let (a, b) = (&mixed.region_results[ri], &plain.region_results[ri]);
        assert_eq!(a.stockpile.map(f32::to_bits), b.stockpile.map(f32::to_bits));
        assert_eq!(a.food_ledger.map(f64::to_bits), b.food_ledger.map(f64::to_bits));
        assert_eq!(a.food_sufficiency.to_bits(), b.food_sufficiency.to_bits());
        assert_eq!(a.market_price[CAT_FOOD].to_bits(), b.market_price[CAT_FOOD].to_bits());
        assert!(mixed.retail.as_ref().unwrap()[ri].is_none());
    }
}

/// One isolated hybrid region: `farmers` at grain yield 1, `pop` eaters.
fn one(stock: [f32; NUM_GOODS], pop: u32, farmers: u32, storage_population: u16,
       retail: Option<RetailRegionInput>) -> EconomyOutput {
    let mut r = region(0, 0, 1.0);
    r.stockpile = stock;
    r.storage_population = storage_population;
    let counts = [RegionAgentCounts { population: pop, farmer_count: farmers, soldier_count: 0,
        merchant_count: 0, wealthy_count: 0 }];
    let delivery = HybridDeliveryInput::from_buffer(&DeliveryBuffer::new(1), 1);
    let rows = [retail];
    tick_economy_core_full(&[r], &counts, &[], &[0.0], &[0], 1, &[0], &EconomyConfig::default(),
        1.0, false, Some(&delivery), &EconomyExtras { retail: retail.map(|_| &rows[..]), ..Default::default() })
}

fn pilot(theta: f32, own: [f32; NUM_GOODS]) -> Option<RetailRegionInput> {
    Some(RetailRegionInput { title_share: theta, owned: own })
}

#[test]
fn theta_one_titles_the_whole_harvest_and_the_draw_down_takes_commons_only() {
    let mut commons = [0.0; NUM_GOODS];
    commons[SLOT_GRAIN] = 2.0;
    let own = owned([(SLOT_GRAIN, 6.0), (SLOT_FISH, 1.0), (SLOT_SALT, 0.0), (SLOT_BOTANICALS, 0.0), (SLOT_EXOTIC, 0.0)]);
    // 10 farmers grow 10 grain; 20 people want 10.
    let out = one(commons, 20, 10, 100, pilot(1.0, own));
    let rr = &out.region_results[0];
    let rt = out.retail.as_ref().unwrap()[0].as_ref().unwrap();
    assert_eq!(rt.titled[SLOT_GRAIN], 10.0);
    assert_eq!(rt.titled[SLOT_FISH], 0.0);
    // Only the 2 commons grain was eaten: the commons is empty. The carried
    // 6 grain and 1 fish decay at opening; the 10 titled are not decayed.
    assert_eq!(rt.commons_consumed, 2.0);
    assert_eq!(rr.food_ledger[6], 2.0);
    assert_eq!(rr.stockpile[SLOT_GRAIN], 0.0);
    assert!((rt.commons_sufficiency - 0.2).abs() < 1e-6);
    assert_eq!(rt.owned_decay[SLOT_GRAIN], 6.0 - 6.0 * (1.0 - 0.03));
    assert_eq!(rt.owned_close[SLOT_GRAIN], 6.0 * (1.0 - 0.03) + 10.0);
    assert_eq!(rt.owned_close[SLOT_FISH], 1.0 * (1.0 - 0.06));
    // Availability counts exactly the food on offer at 0.7: (2 + 15.82 + 0.94) / 10.
    let offered: f32 = rt.owned_close.iter().sum();
    assert!((rr.food_sufficiency - (2.0 + offered) / 10.0).abs() < 1e-6);
    assert!((rr.food_sufficiency - 1.876).abs() < 1e-5);
    assert_food_balance_with(&rr.food_ledger, early(rt));
    // With no commons at all, nothing is drawn down however much is owned.
    let none = one([0.0; NUM_GOODS], 20, 10, 100, pilot(1.0, own));
    let rt = none.retail.as_ref().unwrap()[0].as_ref().unwrap();
    assert_eq!((rt.commons_consumed, rt.commons_sufficiency), (0.0, 0.0));
    assert_eq!(none.conservation.consumption, 0.0);
    assert!((none.region_results[0].food_sufficiency - 1.676).abs() < 1e-5);
    // θ = 0.9 leaves a tenth of the harvest in the commons.
    let tenth = one([0.0; NUM_GOODS], 20, 10, 100, pilot(0.9, [0.0; NUM_GOODS]));
    let rt = tenth.retail.as_ref().unwrap()[0].as_ref().unwrap();
    assert!((rt.titled[SLOT_GRAIN] - 9.0).abs() < 1e-5);
    assert!((rt.commons_consumed - 1.0).abs() < 1e-5);
    assert_eq!(tenth.region_results[0].stockpile[SLOT_GRAIN], 0.0);
}

#[test]
fn owned_stock_counts_in_sufficiency_supply_and_price() {
    // Commons 1 grain, owned 3 grain and 1 fish carried in (θ = 0: no title).
    let mut commons = [0.0; NUM_GOODS];
    commons[SLOT_GRAIN] = 1.0;
    let own = owned([(SLOT_GRAIN, 3.0), (SLOT_FISH, 1.0), (SLOT_SALT, 0.0), (SLOT_BOTANICALS, 0.0), (SLOT_EXOTIC, 0.0)]);
    let split = one(commons, 30, 6, 100, pilot(0.0, own));
    let without = one(commons, 30, 6, 100, pilot(0.0, [0.0; NUM_GOODS]));
    let (b, c) = (&split.region_results[0], &without.region_results[0]);
    let rt = split.retail.as_ref().unwrap()[0].as_ref().unwrap();
    // The carried owned stock, after its opening decay, is supply and availability.
    let carried: f32 = rt.owned_close.iter().sum();
    assert!((carried - (3.0 * 0.97 + 0.94)).abs() < 1e-5);
    assert!((b.market_supply[CAT_FOOD] - c.market_supply[CAT_FOOD] - carried).abs() < 1e-5);
    assert!(c.market_price[CAT_FOOD] > b.market_price[CAT_FOOD]);
    assert!((b.food_ledger[5] - c.food_ledger[5] - carried as f64).abs() < 1e-5);
    assert!(c.food_sufficiency < b.food_sufficiency);
    // ...but the draw-down is limited to the commons (1 + 6 harvest at θ = 0).
    assert!((b.food_ledger[6] - 7.0).abs() < 1e-5 && (c.food_ledger[6] - 7.0).abs() < 1e-5);
    // The same food held as commons would not have decayed before the draw-down.
    let mut all = [0.0; NUM_GOODS];
    all[SLOT_GRAIN] = 1.0 + 3.0 * 0.97;
    all[SLOT_FISH] = 0.94;
    let base = one(all, 30, 6, 100, None);
    let a = &base.region_results[0];
    assert!((a.market_supply[CAT_FOOD] - b.market_supply[CAT_FOOD]).abs() < 1e-5);
    assert!((a.food_sufficiency - b.food_sufficiency).abs() < 1e-5);
    // The oracle shadow sees the owned food too.
    let oracle = |o: &EconomyOutput| o.oracle_food_sufficiency.as_ref().unwrap()[0];
    assert!((oracle(&base) - oracle(&split)).abs() < 1e-5);
    assert_food_balance_with(&b.food_ledger, early(rt));
}

#[test]
fn decay_reads_salt_in_both_pools_and_the_cap_splits_overflow_pro_rata() {
    // Salt held only as owned stock preserves the commons grain as well.
    let mut commons = [0.0; NUM_GOODS];
    commons[SLOT_GRAIN] = 10.0;
    let salted = owned([(SLOT_GRAIN, 10.0), (SLOT_FISH, 0.0), (SLOT_SALT, 8.0), (SLOT_BOTANICALS, 0.0), (SLOT_EXOTIC, 0.0)]);
    let plain = owned([(SLOT_GRAIN, 10.0), (SLOT_FISH, 0.0), (SLOT_SALT, 0.0), (SLOT_BOTANICALS, 0.0), (SLOT_EXOTIC, 0.0)]);
    let a = one(commons, 0, 0, 100, pilot(0.9, salted));
    let b = one(commons, 0, 0, 100, pilot(0.9, plain));
    let (ra, rb) = (a.retail.as_ref().unwrap()[0].as_ref().unwrap(), b.retail.as_ref().unwrap()[0].as_ref().unwrap());
    assert!(a.region_results[0].stockpile[SLOT_GRAIN] > b.region_results[0].stockpile[SLOT_GRAIN]);
    assert!(ra.owned_decay[SLOT_GRAIN] < rb.owned_decay[SLOT_GRAIN]);
    assert_eq!(ra.owned_decay[SLOT_SALT], 0.0);
    // Without salt the carried owned grain decays at the commons' rate (at
    // opening; the commons after consumption, here none).
    assert_eq!(rb.owned_decay[SLOT_GRAIN], 10.0 - b.region_results[0].stockpile[SLOT_GRAIN]);
    assert!((rb.owned_decay[SLOT_GRAIN] - 10.0 * 0.03).abs() < 1e-5);
    // This turn's title is never decayed: 4 farmers grow 4 grain, θ = 1.
    let titled = one([0.0; NUM_GOODS], 0, 4, 100, pilot(1.0, [0.0; NUM_GOODS]));
    let rt = titled.retail.as_ref().unwrap()[0].as_ref().unwrap();
    assert_eq!((rt.titled[SLOT_GRAIN], rt.owned_decay[SLOT_GRAIN], rt.owned_close[SLOT_GRAIN]), (4.0, 0.0, 4.0));
    // Cap 2.5 x 4 = 10 per good, enforced at opening on both pools together:
    // the carried 30 grain decays to 29.1, and with the 10 commons (39.1) both
    // keep their pro-rata share of the cap; the commons then decay as usual.
    let mut c = [0.0; NUM_GOODS];
    c[SLOT_GRAIN] = 10.0;
    let big = owned([(SLOT_GRAIN, 30.0), (SLOT_FISH, 0.0), (SLOT_SALT, 0.0), (SLOT_BOTANICALS, 0.0), (SLOT_EXOTIC, 0.0)]);
    let capped = one(c, 0, 0, 4, pilot(0.9, big));
    let rr = &capped.region_results[0];
    let rt = capped.retail.as_ref().unwrap()[0].as_ref().unwrap();
    let carried = 30.0f32 * 0.97;
    let share = 10.0 / (10.0 + carried);
    assert!((rt.owned_close[SLOT_GRAIN] - carried * share).abs() < 1e-5, "{}", rt.owned_close[SLOT_GRAIN]);
    assert!((rt.owned_overflow[SLOT_GRAIN] - carried * (1.0 - share)).abs() < 1e-5);
    assert!((rr.stockpile[SLOT_GRAIN] - 10.0 * share * 0.97).abs() < 1e-5);
    // The opening holds exactly the cap; the ledger carries both overflows.
    assert!((carried * share + 10.0 * share - 10.0).abs() < 1e-5);
    assert!((rr.food_ledger[8] - (10.0 + carried as f64 - 10.0)).abs() < 1e-4);
    // In a pilot region commons over the cap at opening are capped there too
    // (owned or not), then decay; at close they are capped as in every region.
    let mut full = [0.0; NUM_GOODS];
    full[SLOT_GRAIN] = 12.0;
    let over = one(full, 0, 0, 4, pilot(0.9, [0.0; NUM_GOODS]));
    assert!((over.region_results[0].stockpile[SLOT_GRAIN] - 10.0 * 0.97).abs() < 1e-5);
    let plain = one(full, 0, 0, 4, None);
    assert_eq!(plain.region_results[0].stockpile[SLOT_GRAIN], 10.0);
    let input = region(0, 0, 1.0);
    let mut input = input;
    input.stockpile = c;
    input.storage_population = 4;
    assert_food_balance_with(&rr.food_ledger, early(rt) + commons_opening_overflow(&input, rt, &pilot(0.9, big).unwrap(), &[0.0; NUM_GOODS]));
}

#[test]
fn the_combined_cap_holds_at_every_opening_when_nothing_is_sold() {
    // Reviewer D's case: cap 2.5 x 4 = 10 grain, 20 grain grown every turn,
    // nobody eats or buys (Phase 0.7 would leave every claim whole). Before the
    // fix the pilot closed at 32.6-34.4 grain every turn against L2's 10.
    let (mut commons, mut owned_open) = ([0.0f32; NUM_GOODS], [0.0f32; NUM_GOODS]);
    for turn in 0..10 {
        let out = one(commons, 0, 20, 4, pilot(0.9, owned_open));
        let rr = &out.region_results[0];
        let rt = out.retail.as_ref().unwrap()[0].as_ref().unwrap();
        // What the opening held after the cap: Phase A supply less the harvest.
        let held = rr.market_supply[CAT_FOOD] - rr.food_ledger[1] as f32;
        assert!(held <= 10.0 + 1e-4, "turn {turn}: opening holds {held}");
        let expected = (0..NUM_GOODS).map(|g| commons[g] + owned_open[g] - rt.owned_decay[g]).sum::<f32>().min(10.0);
        assert!((held - expected).abs() < 1e-4, "turn {turn}: {held} {expected}");
        // Between close and the next opening the region holds at most one
        // turn's harvest above the cap: the title (uncapped until the next
        // opening) and the commons' growth since the opening cut (the commons
        // alone are capped at close, as in every region).
        let close = rr.stockpile[SLOT_GRAIN] + rt.owned_close[SLOT_GRAIN];
        assert!(close <= 10.0 + rr.food_ledger[1] as f32 + 1e-4, "turn {turn}: closes at {close}");
        assert!(rr.stockpile[SLOT_GRAIN] <= 10.0 && rt.owned_close[SLOT_GRAIN] <= 10.0 + rt.titled[SLOT_GRAIN] + 1e-4);
        let ledger = &rr.food_ledger;
        let balance = ledger[0] + ledger[1] + ledger[2] - ledger[3] + ledger[4] - ledger[6] - ledger[7] - ledger[8];
        assert!((balance - ledger[9]).abs() < 1e-4, "turn {turn}: {ledger:?}");
        commons = rr.stockpile;
        owned_open = rt.owned_close;
    }
    // L2 alone closes at the cap.
    let plain = one(commons, 0, 20, 4, None);
    assert_eq!(plain.region_results[0].stockpile[SLOT_GRAIN], 10.0);
}

fn assert_owned_closes(out: &EconomyOutput, opening: &[Option<RetailRegionInput>]) {
    for (row, input) in out.retail.as_ref().unwrap().iter().zip(opening) {
        let (Some(row), Some(input)) = (row, input) else { continue };
        for g in 0..NUM_GOODS {
            let expected = input.owned[g] + row.titled[g] - row.owned_decay[g] - row.owned_overflow[g];
            assert!((expected - row.owned_close[g]).abs() < 1e-5, "good {g}: {row:?}");
            assert!(row.owned_close[g] >= 0.0);
            if !RETAIL_FOOD_SLOTS.contains(&g) {
                assert_eq!((row.titled[g], row.owned_close[g]), (0.0, 0.0));
            }
        }
    }
}

#[test]
fn the_food_ledger_and_conservation_close_with_owned_stock() {
    let own = owned([(SLOT_GRAIN, 5.0), (SLOT_FISH, 2.0), (SLOT_SALT, 1.0), (SLOT_BOTANICALS, 0.5), (SLOT_EXOTIC, 0.25)]);
    let rows = [Some(RetailRegionInput { title_share: 0.9, owned: own }), None,
                Some(RetailRegionInput { title_share: 0.5, owned: [0.0; NUM_GOODS] })];
    let out = run(Some(&rows));
    let (regions, ..) = scenario();
    assert_owned_closes(&out, &rows);
    for (ri, rr) in out.region_results.iter().enumerate() {
        let opening = match (&out.retail.as_ref().unwrap()[ri], rows[ri]) {
            (Some(rt), Some(open)) => early(rt) + commons_opening_overflow(&regions[ri], rt, &open,
                &scenario().3.departure_debits[ri]),
            _ => 0.0,
        };
        assert_food_balance_with(&rr.food_ledger, opening);
        let owned_open: f32 = rows[ri].map_or(0.0, |r| r.owned.iter().sum());
        let commons_open: f32 = RETAIL_FOOD_SLOTS.iter().map(|&g| regions[ri].stockpile[g]).sum();
        assert!((rr.food_ledger[0] - (commons_open + owned_open) as f64).abs() < 1e-5);
        let commons_close: f32 = RETAIL_FOOD_SLOTS.iter().map(|&g| rr.stockpile[g]).sum();
        let owned_close: f32 = out.retail.as_ref().unwrap()[ri].as_ref()
            .map_or(0.0, |r| r.owned_close.iter().sum());
        assert!((rr.food_ledger[9] - (commons_close + owned_close) as f64).abs() < 1e-4);
        if let Some(rt) = &out.retail.as_ref().unwrap()[ri] {
            assert_eq!(rt.commons_consumed, rr.food_ledger[6]);
        }
    }
    // World conservation with owned stock on both sides.
    let c = &out.conservation;
    let open: f64 = regions.iter().flat_map(|r| r.stockpile).map(f64::from).sum::<f64>()
        + rows.iter().flatten().flat_map(|r| r.owned).map(f64::from).sum::<f64>();
    let close: f64 = out.region_results.iter().flat_map(|r| r.stockpile).map(f64::from).sum::<f64>()
        + out.retail.as_ref().unwrap().iter().flatten().flat_map(|r| r.owned_close).map(f64::from).sum::<f64>();
    let residual = open + c.production - close - c.consumption - c.storage_loss - c.transit_loss
        - c.cap_overflow - c.in_transit_delta.unwrap() - c.clamp_floor_loss;
    assert!(residual.abs() < 1e-3, "{residual}");
}

#[test]
fn zero_production_and_empty_regions() {
    // Nobody farms or eats and nothing is held: every flow is zero.
    let out = one([0.0; NUM_GOODS], 0, 0, 100, pilot(0.9, [0.0; NUM_GOODS]));
    let rr = &out.region_results[0];
    let rt = out.retail.as_ref().unwrap()[0].as_ref().unwrap();
    assert_eq!(rr.food_ledger, [0.0; 10]);
    assert_eq!(rr.food_sufficiency, 0.0);
    assert_eq!(*rt, Default::default());
    // Eaters, no harvest, only owned food: they are not fed by the economy.
    let own = owned([(SLOT_GRAIN, 3.0), (SLOT_FISH, 0.0), (SLOT_SALT, 0.0), (SLOT_BOTANICALS, 0.0), (SLOT_EXOTIC, 0.0)]);
    let out = one([0.0; NUM_GOODS], 12, 0, 100, pilot(0.9, own));
    let rt = out.retail.as_ref().unwrap()[0].as_ref().unwrap();
    assert_eq!(rt.titled, [0.0; NUM_GOODS]);
    assert_eq!(rt.commons_consumed, 0.0);
    assert!((out.region_results[0].food_sufficiency - 3.0 * 0.97 / 6.0).abs() < 1e-6);
    assert_eq!(rt.owned_close[SLOT_GRAIN], 3.0 * (1.0 - 0.03));
    assert_food_balance_with(&out.region_results[0].food_ledger, early(rt));
    // Owned food but nobody to feed: demand floors at SUPPLY_FLOOR.
    let out = one([0.0; NUM_GOODS], 0, 0, 100, pilot(1.0, own));
    assert_eq!(out.region_results[0].food_sufficiency, 2.0);
    assert_eq!(out.retail.as_ref().unwrap()[0].as_ref().unwrap().commons_sufficiency, 0.0);
}

#[test]
fn woodcutting_crews_and_retail_combine_without_touching_each_other() {
    // A home region (grain; its pilot farmers send a crew away) and a forest
    // (grain and timber) the crew works.
    let home = region(0, 0, 1.0);
    let mut forest = region(1, 0, 1.0);
    forest.resource_types = [0, 1, 255];
    forest.resource_yields = [1.0, 2.0, 0.0];
    forest.stockpile[SLOT_TIMBER] = 3.0;
    let regions = [home, forest];
    let counts = [agents(20, 12), agents(10, 8)];
    let delivery = HybridDeliveryInput::from_buffer(&DeliveryBuffer::new(2), 2);
    let crew = WoodcutInput { labor_away: &[3.0, 0.0], labor: &[0.0, 3.0] };
    let rows = [pilot(0.9, owned([(SLOT_GRAIN, 2.0), (SLOT_FISH, 0.0), (SLOT_SALT, 0.0), (SLOT_BOTANICALS, 0.0),
                                  (SLOT_EXOTIC, 0.0)])), None];
    let config = EconomyConfig::default();
    let woodcut_only = tick_economy_core_full(&regions, &counts, &[], &[0.0], &[0], 1, &[0, 0], &config, 1.0,
        false, Some(&delivery), &EconomyExtras { woodcut: Some(&crew), ..Default::default() });
    let null_retail = tick_economy_core_full(&regions, &counts, &[], &[0.0], &[0], 1, &[0, 0], &config, 1.0,
        false, Some(&delivery),
        &EconomyExtras { woodcut: Some(&crew), retail: Some(&[None, None]), ..Default::default() });
    let both = tick_economy_core_full(&regions, &counts, &[], &[0.0], &[0], 1, &[0, 0], &config, 1.0,
        false, Some(&delivery), &EconomyExtras { woodcut: Some(&crew), retail: Some(&rows), ..Default::default() });
    assert_eq!(bits(&null_retail), bits(&woodcut_only));
    let (w, b) = (&woodcut_only.region_results, &both.region_results);
    assert!(w[1].woodcut_output > 0.0 && w[0].woodcut_labor_away_delivered == 3.0);
    // Retail changes neither the labour nor what the land and the crew produce.
    for ri in 0..2 {
        assert_eq!(b[ri].slot_output.map(f32::to_bits), w[ri].slot_output.map(f32::to_bits));
        assert_eq!(b[ri].woodcut_output.to_bits(), w[ri].woodcut_output.to_bits());
        assert_eq!(b[ri].woodcut_labor_away_delivered.to_bits(), w[ri].woodcut_labor_away_delivered.to_bits());
    }
    // The forest (not a pilot) keeps every food output; the crew-reduced home
    // harvest (9 of 12 farmers) is titled at θ.
    assert_eq!(b[1].stockpile.map(f32::to_bits), w[1].stockpile.map(f32::to_bits));
    assert_eq!(b[1].food_ledger.map(f64::to_bits), w[1].food_ledger.map(f64::to_bits));
    let rt = both.retail.as_ref().unwrap()[0].as_ref().unwrap();
    assert_eq!(w[0].slot_output[0], 9.0);
    assert!((rt.titled[SLOT_GRAIN] - 0.9 * 9.0).abs() < 1e-5);
    assert_owned_closes(&both, &rows);
    assert_food_balance_with(&b[0].food_ledger, early(rt));
    assert!(both.retail.as_ref().unwrap()[1].is_none());
}

#[test]
#[should_panic(expected = "household retail requires the hybrid economy")]
fn the_abstract_path_is_refused() {
    let r = region(0, 0, 1.0);
    let rows = [pilot(0.9, [0.0; NUM_GOODS])];
    tick_economy_core_full(&[r], &[agents(4, 2)], &[], &[0.0], &[0], 1, &[0], &EconomyConfig::default(),
        1.0, false, None, &EconomyExtras { retail: Some(&rows), ..Default::default() });
}

#[test]
fn the_opening_cap_reads_the_commons_net_of_merchant_departures() {
    // Reviewer D's case: the commons at the cap (10), 20 grain owned carried,
    // merchants loaded 8 of the commons grain this tick. The cap must count
    // the 2 grain left after the departures: the departures never drive the
    // cut commons negative (no clamp: no food from nothing).
    let mut r = region(0, 0, 1.0);
    r.stockpile[SLOT_GRAIN] = 10.0;
    r.storage_population = 4;
    let counts = [RegionAgentCounts { population: 0, farmer_count: 0, soldier_count: 0, merchant_count: 1,
                                      wealthy_count: 0 }];
    let mut buf = DeliveryBuffer::new(1);
    buf.record_departure(0, SLOT_GRAIN, 8.0);
    let delivery = HybridDeliveryInput::from_buffer(&buf, 1);
    let own = owned([(SLOT_GRAIN, 20.0), (SLOT_FISH, 0.0), (SLOT_SALT, 0.0), (SLOT_BOTANICALS, 0.0), (SLOT_EXOTIC, 0.0)]);
    let rows = [pilot(0.9, own)];
    let out = tick_economy_core_full(&[r], &counts, &[], &[0.0], &[0], 1, &[0], &EconomyConfig::default(),
        1.0, false, Some(&delivery), &EconomyExtras { retail: Some(&rows), ..Default::default() });
    let rr = &out.region_results[0];
    let rt = out.retail.as_ref().unwrap()[0].as_ref().unwrap();
    assert_eq!(out.conservation.clamp_floor_loss, 0.0);
    assert_eq!(rr.food_ledger[4], 0.0);
    // 2 grain of commons net of departures and 19.4 carried keep 10 together.
    let carried = 20.0f32 * 0.97;
    let share = 10.0 / (2.0 + carried);
    assert!((rt.owned_close[SLOT_GRAIN] - carried * share).abs() < 1e-5, "{}", rt.owned_close[SLOT_GRAIN]);
    assert!((rr.stockpile[SLOT_GRAIN] - 2.0 * share * 0.97).abs() < 1e-5, "{}", rr.stockpile[SLOT_GRAIN]);
    assert!(rr.stockpile[SLOT_GRAIN] >= 0.0);
    let ledger = &rr.food_ledger;
    let balance = ledger[0] + ledger[1] + ledger[2] - ledger[3] + ledger[4] - ledger[6] - ledger[7] - ledger[8];
    assert!((balance - ledger[9]).abs() < 1e-4, "{ledger:?}");
    assert!((ledger[2] + 8.0).abs() < 1e-6 && (ledger[0] - 30.0).abs() < 1e-6);
    // Without departures the cap reads the whole commons, as before.
    let none = HybridDeliveryInput::from_buffer(&DeliveryBuffer::new(1), 1);
    let plain = tick_economy_core_full(&[r_at_cap()], &counts, &[], &[0.0], &[0], 1, &[0],
        &EconomyConfig::default(), 1.0, false, Some(&none), &EconomyExtras { retail: Some(&rows), ..Default::default() });
    let pt = plain.retail.as_ref().unwrap()[0].as_ref().unwrap();
    assert!((pt.owned_close[SLOT_GRAIN] - carried * (10.0 / (10.0 + carried))).abs() < 1e-5);
}

fn r_at_cap() -> EconomyRegionInput {
    let mut r = region(0, 0, 1.0);
    r.stockpile[SLOT_GRAIN] = 10.0;
    r.storage_population = 4;
    r
}
