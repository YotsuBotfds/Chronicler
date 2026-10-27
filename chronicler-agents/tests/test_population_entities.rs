//! Population and entity-lifecycle corrections (2026-10,
//! docs/integration/population-entities.md): initial occupation shares from
//! a conserved budget, and mineral depletion from the economy's realized
//! extraction.

use chronicler_agents::demographics::{initial_occupation_counts, INITIAL_OCCUPATION_PERCENT};
use chronicler_agents::ecology::{compute_yields, effective_capacity, refresh_yields, EcologyConfig};
use chronicler_agents::RegionState;

// ---------------------------------------------------------------------------
// Initial occupations
// ---------------------------------------------------------------------------

/// The pre-correction counts: each share rounded on its own, priests the
/// positive remainder only.
fn independent_rounding(pop: usize) -> [usize; 5] {
    let mut counts = [0usize; 5];
    for (k, &p) in INITIAL_OCCUPATION_PERCENT.iter().enumerate() {
        counts[k] = (pop * p + 50) / 100;
    }
    let spawned: usize = counts[..4].iter().sum();
    counts[4] = pop.saturating_sub(spawned);
    counts
}

#[test]
fn initial_occupations_spawn_exactly_the_population() {
    for pop in 0..=100_000usize {
        let counts = initial_occupation_counts(pop);
        assert_eq!(counts.iter().sum::<usize>(), pop, "population {pop}: {counts:?}");
    }
}

#[test]
fn tiny_populations_get_a_conserved_split() {
    // The two populations the independent rounding inflated (5 -> 6, 6 -> 7).
    assert_eq!(independent_rounding(5).iter().sum::<usize>(), 6);
    assert_eq!(independent_rounding(6).iter().sum::<usize>(), 7);
    assert_eq!(initial_occupation_counts(5), [3, 1, 1, 0, 0]);
    assert_eq!(initial_occupation_counts(6), [4, 1, 1, 0, 0]);
    assert_eq!(initial_occupation_counts(0), [0, 0, 0, 0, 0]);
    assert_eq!(initial_occupation_counts(1), [1, 0, 0, 0, 0]);
    assert_eq!(initial_occupation_counts(2), [1, 0, 0, 0, 1]);
}

#[test]
fn every_population_the_old_shares_fitted_keeps_its_counts() {
    let mut changed = Vec::new();
    for pop in 0..=100_000usize {
        if initial_occupation_counts(pop) != independent_rounding(pop) {
            changed.push(pop);
        }
    }
    assert_eq!(changed, vec![5, 6]);
}

// ---------------------------------------------------------------------------
// Mineral depletion
// ---------------------------------------------------------------------------

const RT_ORE: u8 = 5;
const EMPTY_SLOT: u8 = 255;

fn mine(population: u16) -> RegionState {
    let mut r = RegionState::new(0);
    r.terrain = 1; // mountains
    r.carrying_capacity = 60;
    r.population = population;
    r.controller_civ = 0;
    r.resource_types = [RT_ORE, EMPTY_SLOT, EMPTY_SLOT];
    r.resource_base_yield = [1.0, 0.0, 0.0];
    r.resource_effective_yield = [1.0, 0.0, 0.0];
    r.resource_reserves = [1.0, 1.0, 1.0];
    r
}

#[test]
fn a_mine_nobody_works_keeps_its_reserves() {
    let config = EcologyConfig::default();
    let mut r = mine(60);
    for turn in 0..10u32 {
        r.realized_extraction = Some([0.0; 3]);
        compute_yields(&mut r, &config, (turn % 4) as u8, 0);
    }
    assert_eq!(r.resource_reserves[0], 1.0);
}

#[test]
fn realized_output_depletes_per_target_crew() {
    let config = EcologyConfig::default();
    let mut r = mine(60);
    let crew = (effective_capacity(&r, &config) / 3).max(1) as f32;
    // A target crew at the base yield extracts the base yield's worth.
    r.realized_extraction = Some([crew, 0.0, 0.0]);
    compute_yields(&mut r, &config, 0, 0);
    let expected = 1.0 - config.depletion_rate;
    assert!((r.resource_reserves[0] - expected).abs() < 1e-6, "{}", r.resource_reserves[0]);
    // Half the output, half the depletion.
    let mut half = mine(60);
    half.realized_extraction = Some([crew / 2.0, 0.0, 0.0]);
    compute_yields(&mut half, &config, 0, 0);
    assert!((1.0 - half.resource_reserves[0] - config.depletion_rate / 2.0).abs() < 1e-6);
    // The population does not enter: the same output in an empty region.
    let mut empty = mine(0);
    empty.realized_extraction = Some([crew, 0.0, 0.0]);
    compute_yields(&mut empty, &config, 0, 0);
    assert_eq!(empty.resource_reserves[0], r.resource_reserves[0]);
}

#[test]
fn without_a_goods_economy_the_labour_proxy_is_unchanged() {
    // `--agents off` (EcologySimulator): population / 5 workers, bit for bit.
    let config = EcologyConfig::default();
    let mut r = mine(60);
    assert!(r.realized_extraction.is_none());
    compute_yields(&mut r, &config, 0, 0);
    let eff = effective_capacity(&r, &config);
    let target = (eff / 3).max(1);
    let extraction = 1.0f32 * ((60u16 / 5) as f32 / target as f32);
    let expected = (1.0f32 - extraction * config.depletion_rate).max(0.0);
    assert_eq!(r.resource_reserves[0].to_bits(), expected.to_bits());
}

#[test]
fn refresh_never_depletes_and_exhausted_deposits_stay_put() {
    let config = EcologyConfig::default();
    let mut r = mine(60);
    r.realized_extraction = Some([100.0, 0.0, 0.0]);
    refresh_yields(&mut r, &config, 0, 0);
    assert_eq!(r.resource_reserves[0], 1.0);
    r.resource_reserves[0] = 0.005;
    compute_yields(&mut r, &config, 0, 0);
    assert_eq!(r.resource_reserves[0], 0.005);
}
