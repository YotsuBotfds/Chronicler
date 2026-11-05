//! RS5 clearing protection (`--clearing-protection`,
//! docs/integration/clearing-protection.md): a funded protection p in [0, 1]
//! applied at the authoritative population-driven clearing decision
//! (`ecology::tick_forest_controlled_protected`): the tick removes
//! `forest_clearing x (1 - p)`. Absent (`None`) is the old flat loss bit for
//! bit; cooling, regrowth and every other ecology step are untouched; the
//! input is consumed by the tick and never checkpointed.

use chronicler_agents::ecology::{
    tick_ecology_with_ledger, tick_forest_controlled_protected, EcologyConfig, ExtractionLedger,
    RiverTopology,
};
use chronicler_agents::{persist, EcologySimulator, RegionState};

const TEMPERATE: u8 = 0;
const DROUGHT: u8 = 2;
const COOLING: u8 = 3;
const FOREST: u8 = 3;
const RT_TIMBER: u8 = 1;
const EMPTY: u8 = 255;

/// A controlled forest region under clearing pressure (population above half
/// its carrying capacity), with water above the regrowth gate.
fn forest(id: u16, population: u16) -> RegionState {
    let mut r = RegionState::new(id);
    r.terrain = FOREST;
    r.carrying_capacity = 60;
    r.population = population;
    r.controller_civ = 0;
    r.soil = 0.6;
    r.water = 0.7;
    r.forest_cover = 0.5;
    r.resource_types = [RT_TIMBER, EMPTY, EMPTY];
    r.resource_base_yield = [1.0, 0.0, 0.0];
    r.resource_effective_yield = [1.0, 0.0, 0.0];
    r.resource_reserves = [1.0, 1.0, 1.0];
    r.prev_turn_water = 0.7;
    r
}

fn tick(regions: &mut [RegionState], phase: u8, turn: u32) -> (Vec<[f32; 3]>, Vec<ExtractionLedger>) {
    let n = regions.len();
    let config = EcologyConfig::default();
    let (yields, _, ledgers) = tick_ecology_with_ledger(
        regions, &config, turn, phase, &vec![false; n], &vec![false; n], &RiverTopology::default(),
    );
    (yields, ledgers)
}

fn state_bits(r: &RegionState) -> Vec<u32> {
    let mut v = vec![r.soil.to_bits(), r.water.to_bits(), r.forest_cover.to_bits(),
                     r.endemic_severity.to_bits(), r.prev_turn_water.to_bits()];
    v.extend(r.resource_effective_yield.iter().map(|x| x.to_bits()));
    v.extend(r.resource_reserves.iter().map(|x| x.to_bits()));
    v
}

#[test]
fn an_absent_column_is_the_flat_clearing_bit_for_bit() {
    // The forest step itself: None removes exactly forest_clearing.
    let config = EcologyConfig::default();
    let mut r = forest(0, 40);
    let before = r.forest_cover;
    let receipt = tick_forest_controlled_protected(&mut r, &config, TEMPERATE, None);
    assert_eq!(r.forest_cover.to_bits(), (before - config.forest_clearing).to_bits());
    assert!(receipt.active);
    assert_eq!(receipt.cover_not_cleared, 0.0);

    // Whole ticks over every phase: no column, and a column of zeros, give the
    // same state, yields and ledger (apart from the input flag) on every turn.
    let mut absent = vec![forest(0, 40), forest(1, 10)];
    let mut zero = absent.clone();
    for turn in 0..48u32 {
        let phase = (turn / 6 % 4) as u8;
        for r in zero.iter_mut() {
            r.clearing_protection = Some(0.0);
        }
        let (ya, la) = tick(&mut absent, phase, turn);
        let (yz, lz) = tick(&mut zero, phase, turn);
        for i in 0..2 {
            assert_eq!(state_bits(&absent[i]), state_bits(&zero[i]), "turn {turn} region {i}");
            assert_eq!(ya[i].map(f32::to_bits), yz[i].map(f32::to_bits));
            assert!(!la[i].protection_input && lz[i].protection_input);
            assert_eq!(la[i].clearing_active, lz[i].clearing_active);
            assert_eq!(lz[i].cover_not_cleared, 0.0);
            let mut flag = lz[i];
            flag.protection_input = false;
            assert_eq!(la[i], flag);
        }
    }
}

#[test]
fn full_protection_removes_no_cover_to_clearing() {
    let config = EcologyConfig::default();
    let mut rs = vec![forest(0, 40)];
    rs[0].clearing_protection = Some(1.0);
    let before = rs[0].forest_cover;
    let (_, ledgers) = tick(&mut rs, TEMPERATE, 0);
    // Regrowth stays blocked while the population is above the threshold, so
    // the cover is frozen, not restored.
    assert_eq!(rs[0].forest_cover.to_bits(), before.to_bits());
    assert!(ledgers[0].clearing_active);
    assert_eq!(ledgers[0].cover_not_cleared.to_bits(), config.forest_clearing.to_bits());

    let mut open = vec![forest(0, 40)];
    tick(&mut open, TEMPERATE, 0);
    assert!((before - open[0].forest_cover - config.forest_clearing).abs() < 1e-6);
}

#[test]
fn half_protection_halves_the_clearing_loss() {
    let config = EcologyConfig::default();
    let mut half = vec![forest(0, 40)];
    let mut open = vec![forest(0, 40)];
    half[0].clearing_protection = Some(0.5);
    let before = half[0].forest_cover;
    let (_, lh) = tick(&mut half, TEMPERATE, 0);
    tick(&mut open, TEMPERATE, 0);
    let lost_half = before - half[0].forest_cover;
    let lost_open = before - open[0].forest_cover;
    assert!((lost_half - 0.5 * config.forest_clearing).abs() < 1e-6, "{lost_half}");
    assert!((lost_open - config.forest_clearing).abs() < 1e-6, "{lost_open}");
    assert!((lh[0].cover_not_cleared - 0.5 * config.forest_clearing).abs() < 1e-9);
}

#[test]
fn cooling_damage_and_drought_are_untouched_by_protection() {
    let config = EcologyConfig::default();
    for &phase in &[COOLING, DROUGHT] {
        let mut protected = vec![forest(0, 40)];
        let mut open = vec![forest(0, 40)];
        protected[0].clearing_protection = Some(1.0);
        let before = protected[0].forest_cover;
        tick(&mut protected, phase, 0);
        tick(&mut open, phase, 0);
        let lost_protected = before - protected[0].forest_cover;
        let lost_open = before - open[0].forest_cover;
        let cooling = if phase == COOLING { config.cooling_forest_damage } else { 0.0 };
        assert!((lost_protected - cooling).abs() < 1e-6, "phase {phase}: {lost_protected}");
        assert!((lost_open - cooling - config.forest_clearing).abs() < 1e-6, "phase {phase}: {lost_open}");
        // Water and soil follow their own steps, identical with or without p.
        assert_eq!(protected[0].water.to_bits(), open[0].water.to_bits());
    }
    // Without clearing pressure a protection changes nothing at all (cooling
    // and regrowth alike).
    for &phase in &[TEMPERATE, COOLING] {
        let mut protected = vec![forest(0, 10)];
        let mut open = vec![forest(0, 10)];
        protected[0].clearing_protection = Some(1.0);
        let (_, lp) = tick(&mut protected, phase, 0);
        tick(&mut open, phase, 0);
        assert_eq!(state_bits(&protected[0]), state_bits(&open[0]));
        assert!(!lp[0].clearing_active);
        assert_eq!(lp[0].cover_not_cleared, 0.0);
    }
}

#[test]
fn uncontrolled_regions_never_clear_and_the_input_is_consumed() {
    let mut rs = vec![forest(0, 40), forest(1, 40)];
    rs[0].controller_civ = 255;
    rs[0].clearing_protection = Some(1.0);
    rs[1].clearing_protection = Some(1.0);
    let (_, ledgers) = tick(&mut rs, TEMPERATE, 0);
    assert!(!ledgers[0].clearing_active);
    assert_eq!(ledgers[0].cover_not_cleared, 0.0);
    assert!(ledgers[0].protection_input && ledgers[1].protection_input);
    // The tick consumed the transient input: a second tick without a new
    // batch is unprotected and clears in full.
    assert!(rs.iter().all(|r| r.clearing_protection.is_none()));
    let before = rs[1].forest_cover;
    let (_, again) = tick(&mut rs, TEMPERATE, 1);
    assert!(!again[1].protection_input);
    assert!((before - rs[1].forest_cover - EcologyConfig::default().forest_clearing).abs() < 1e-6);
}

#[test]
fn protection_is_never_checkpointed() {
    let mut with = vec![forest(0, 40), forest(1, 40)];
    let without = with.clone();
    with[0].clearing_protection = Some(0.75);
    let a = persist::encode(persist::KIND_ECOLOGY, &with);
    let b = persist::encode(persist::KIND_ECOLOGY, &without);
    assert_eq!(a, b, "the transient input changes neither payload nor schema");
    let back: Vec<RegionState> = persist::decode(persist::KIND_ECOLOGY, &a).unwrap();
    assert!(back[0].clearing_protection.is_none());
    let (_, _, schema) = EcologySimulator::checkpoint_schema();
    assert!(!schema.contains("clearing_protection"));
}
