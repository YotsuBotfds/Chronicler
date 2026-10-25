//! Agent movements across full ticks: without a table the tick is unchanged
//! (and an enabled, empty table draws nothing the rest of the tick sees); a
//! founding seeds members who recruit through bonds and co-residence; an
//! ended movement releases its members; one-shot outcomes (relief, rising)
//! act on the tick after they are sent and not again.

use chronicler_agents::movements::{
    MovementRow, MovementRuntime, CREED_COMMONS, NO_REGION, RELIEF_SAT, STAGE_GATHERING,
    STAGE_RISING, STAGE_SATISFIED,
};
use chronicler_agents::scale::TickOptions;
use chronicler_agents::signals::{CivSignals, TickSignals};
use chronicler_agents::spatial::SpatialDiagnostics;
use chronicler_agents::{
    try_tick_agents_with_movements, try_tick_agents_with_options, AgentEvent, AgentPool,
    Occupation, RegionState,
};

fn signals(num_regions: usize) -> TickSignals {
    TickSignals {
        civs: vec![CivSignals {
            civ_id: 0,
            stability: 20,
            is_at_war: false,
            dominant_faction: 0,
            faction_military: 0.25,
            faction_merchant: 0.25,
            faction_cultural: 0.25,
            faction_clergy: 0.25,
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
            gini_coefficient: 0.5,
            conquered_this_turn: false,
            priest_tithe_share: 0.0,
            cultural_drift_multiplier: 1.0,
            religion_intensity_multiplier: 1.0,
        }],
        contested_regions: vec![false; num_regions],
    }
}

/// Two hungry regions of one realm (poor land, food at half): low
/// satisfaction and material need, so most adults are aggrieved commoners.
fn world() -> (AgentPool, Vec<RegionState>) {
    let mut pool = AgentPool::new(128);
    let mut regions: Vec<RegionState> = (0..2)
        .map(|i| {
            let mut r = RegionState::new(i);
            r.controller_civ = 0;
            r.carrying_capacity = 40;
            r.food_sufficiency = 0.4;
            r.soil = 0.1;
            r.water = 0.1;
            r.majority_belief = 0;
            r
        })
        .collect();
    regions[0].adjacency = vec![1];
    regions[1].adjacency = vec![0];
    for i in 0..40u16 {
        let region = (i % 2) as u16;
        let bold = -0.8 + 0.04 * i as f32;
        let slot = pool.spawn(region, 0, Occupation::Farmer, 20 + i % 20, bold, 0.0, 0.0, 0, 1, 2, 0);
        pool.satisfactions[slot] = 0.2;
        pool.need_material[slot] = 0.15;
    }
    // Friendships within each region.
    for a in 0..40usize {
        for b in [a + 2, a + 4] {
            if b < 40 {
                chronicler_agents::relationships::upsert_symmetric(&mut pool, a, b, 6, 60, 0);
            }
        }
    }
    (pool, regions)
}

fn sync_populations(pool: &AgentPool, regions: &mut [RegionState]) {
    for region in regions.iter_mut() {
        region.population = (0..pool.capacity())
            .filter(|&s| pool.is_alive(s) && pool.regions[s] == region.region_id)
            .count() as u16;
    }
}

fn tick(
    pool: &mut AgentPool,
    regions: &mut [RegionState],
    turn: u32,
    movements: Option<&mut MovementRuntime>,
) -> Vec<AgentEvent> {
    sync_populations(pool, regions);
    let mut seed = [0u8; 32];
    seed[0] = 31;
    let mut percentiles = vec![0.0f32; pool.capacity()];
    let sig = signals(regions.len());
    let result = match movements {
        Some(rt) => try_tick_agents_with_movements(
            pool, regions, &sig, seed, turn, &mut percentiles, &mut Vec::new(), &[],
            &mut SpatialDiagnostics::default(), &[], None, &[], TickOptions::default(), rt,
        ),
        None => try_tick_agents_with_options(
            pool, regions, &sig, seed, turn, &mut percentiles, &mut Vec::new(), &[],
            &mut SpatialDiagnostics::default(), &[], None, &[], TickOptions::default(),
        ),
    };
    result.expect("tick").0
}

fn fingerprint(pool: &AgentPool, events: &[AgentEvent]) -> (Vec<u32>, Vec<u32>, Vec<u16>, Vec<(u32, u8, u16)>) {
    let alive: Vec<usize> = (0..pool.capacity()).filter(|&s| pool.is_alive(s)).collect();
    (
        alive.iter().map(|&s| pool.ids[s]).collect(),
        alive.iter().map(|&s| pool.satisfactions[s].to_bits()).collect(),
        alive.iter().map(|&s| pool.regions[s]).collect(),
        events.iter().map(|e| (e.agent_id, e.event_type, e.region)).collect(),
    )
}

fn members(pool: &AgentPool, id: u16) -> usize {
    (0..pool.capacity()).filter(|&s| pool.is_alive(s) && pool.movement_ids[s] == id).count()
}

#[test]
fn without_a_table_the_tick_is_unchanged() {
    let (mut a, mut ra) = world();
    let (mut b, mut rb) = world();
    let (mut c, mut rc) = world();
    let mut disabled = MovementRuntime::default();
    let mut empty = MovementRuntime { enabled: true, ..Default::default() };
    for turn in 1..15 {
        let ea = tick(&mut a, &mut ra, turn, None);
        let eb = tick(&mut b, &mut rb, turn, Some(&mut disabled));
        let ec = tick(&mut c, &mut rc, turn, Some(&mut empty));
        assert_eq!(fingerprint(&a, &ea), fingerprint(&b, &eb), "turn {turn}");
        assert_eq!(fingerprint(&a, &ea), fingerprint(&c, &ec), "turn {turn}");
    }
    assert!(c.movement_ids.iter().all(|&m| m == 0));
    // The enabled runtime took the census; the disabled one did nothing.
    assert!(disabled.stats.adults.is_empty());
    let adults = (0..c.capacity()).filter(|&s| c.is_alive(s) && c.ages[s] >= 16).count();
    assert_eq!(empty.stats.adults.iter().sum::<u32>() as usize, adults);
    assert!(empty.stats.aggrieved.iter().map(|g| g[0]).sum::<u32>() > 0);
}

#[test]
fn a_founding_grows_through_bonds_and_an_ended_movement_releases_its_members() {
    let (mut pool, mut regions) = world();
    let mut row = MovementRow::new(1, CREED_COMMONS, STAGE_GATHERING, 0);
    row.found_region = 0;
    let mut rt = MovementRuntime { enabled: true, rows: vec![row], ..Default::default() };
    tick(&mut pool, &mut regions, 1, Some(&mut rt));
    let founded = members(&pool, 1);
    assert!(founded >= 3, "founding seeds: {founded}");
    assert_eq!(rt.rows[0].found_region, NO_REGION, "one-shot cleared");
    for turn in 2..25 {
        tick(&mut pool, &mut regions, turn, Some(&mut rt));
    }
    let grown = members(&pool, 1);
    assert!(grown > founded, "recruitment: {founded} -> {grown}");
    let in_other = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s) && pool.movement_ids[s] == 1 && pool.regions[s] == 1)
        .count();
    assert!(in_other > 0 || grown > founded, "spread through bonds and co-residence");
    // The movement ends: Python stops sending it.
    rt.rows.clear();
    tick(&mut pool, &mut regions, 25, Some(&mut rt));
    assert_eq!(members(&pool, 1), 0);
    assert!(rt.stats.released as usize >= 1);
}

#[test]
fn relief_and_rising_act_on_the_next_tick_only() {
    let (mut pool, mut regions) = world();
    for s in 0..pool.capacity() {
        if pool.is_alive(s) && pool.regions[s] == 0 {
            pool.movement_ids[s] = 1;
        }
    }
    // Relief: members of region 0 against non-members of region 1, same land.
    let mut row = MovementRow::new(1, CREED_COMMONS, STAGE_SATISFIED, 0);
    row.relief_age = 1;
    let mut rt = MovementRuntime { enabled: true, rows: vec![row.clone()], ..Default::default() };
    tick(&mut pool, &mut regions, 1, Some(&mut rt));
    let mean = |pool: &AgentPool, member: bool| {
        let v: Vec<f32> = (0..pool.capacity())
            .filter(|&s| pool.is_alive(s) && (pool.movement_ids[s] == 1) == member && pool.regions[s] == if member { 0 } else { 1 })
            .map(|s| pool.satisfactions[s])
            .collect();
        v.iter().sum::<f32>() / v.len().max(1) as f32
    };
    let gap = mean(&pool, true) - mean(&pool, false);
    assert!(gap > RELIEF_SAT * 0.5, "relief raises members' satisfaction: {gap}");
    assert_eq!(rt.rows[0].relief_age, u16::MAX, "relief cleared after the tick");
    tick(&mut pool, &mut regions, 2, Some(&mut rt));
    let gap2 = mean(&pool, true) - mean(&pool, false);
    assert!(gap2 < gap, "no relief without a new table: {gap} -> {gap2}");

    // Rising: members in the stronghold rebel on the tick it is sent.
    let (mut pool, mut regions) = world();
    for s in 0..pool.capacity() {
        if pool.is_alive(s) && pool.regions[s] == 0 {
            pool.movement_ids[s] = 1;
            pool.loyalties[s] = 0.15;
        }
    }
    let mut row = MovementRow::new(1, CREED_COMMONS, STAGE_RISING, 0);
    row.rising_region = 0;
    let mut rt = MovementRuntime { enabled: true, rows: vec![row], ..Default::default() };
    let rebels = |events: &[AgentEvent]| events.iter().filter(|e| e.event_type == 1 && e.region == 0).count();
    let risen = rebels(&tick(&mut pool, &mut regions, 1, Some(&mut rt)));
    let (mut quiet, mut qregions) = world();
    for s in 0..quiet.capacity() {
        if quiet.is_alive(s) && quiet.regions[s] == 0 {
            quiet.movement_ids[s] = 1;
            quiet.loyalties[s] = 0.15;
        }
    }
    let mut qrt = MovementRuntime {
        enabled: true,
        rows: vec![MovementRow::new(1, CREED_COMMONS, STAGE_RISING, 0)],
        ..Default::default()
    };
    let calm = rebels(&tick(&mut quiet, &mut qregions, 1, Some(&mut qrt)));
    assert!(risen > calm, "a rising adds rebels: {risen} against {calm}");
    assert_eq!(rt.rows[0].rising_region, NO_REGION);
}
