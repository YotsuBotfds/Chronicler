//! Pure Rust ecology core — Phase 9 soil/water/forest tick, disease, depletion,
//! river cascade, and yield computation.  No PyO3 — FFI wrappers live in ffi.rs.

use crate::region::RegionState;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Uncontrolled region sentinel.
const UNCONTROLLED: u8 = 255;
/// Empty resource slot sentinel.
const EMPTY_SLOT: u8 = 255;

// TechFocus encoding — matches Python mapper.
#[allow(dead_code)]
const FOCUS_NONE: u8 = 0;
const FOCUS_AGRICULTURE: u8 = 1;
const FOCUS_METALLURGY: u8 = 2;
const FOCUS_MECHANIZATION: u8 = 3;

// Terrain encoding — matches region::Terrain.
const TERRAIN_PLAINS: u8 = 0;
#[allow(dead_code)]
const TERRAIN_MOUNTAINS: u8 = 1;
#[allow(dead_code)]
const TERRAIN_COAST: u8 = 2;
#[allow(dead_code)]
const TERRAIN_FOREST: u8 = 3;
const TERRAIN_DESERT: u8 = 4;
const TERRAIN_TUNDRA: u8 = 5;

// ResourceType encoding — matches Python ResourceType(int, Enum).
const RT_GRAIN: u8 = 0;
const RT_TIMBER: u8 = 1;
const RT_BOTANICALS: u8 = 2;
const RT_FISH: u8 = 3;
const RT_SALT: u8 = 4;
const RT_ORE: u8 = 5;
const RT_PRECIOUS: u8 = 6;
const RT_EXOTIC: u8 = 7;

// Resource classes for CLIMATE_CLASS_MOD indexing.
const CLASS_CROP: usize = 0;
const CLASS_FORESTRY: usize = 1;
const CLASS_MARINE: usize = 2;
const CLASS_MINERAL: usize = 3;
const CLASS_EVAPORITE: usize = 4;

/// Per-resource-type season modifier.  SEASON_MOD[resource_type][season_id]
/// Season IDs: 0=spring, 1=summer, 2=autumn, 3=winter
const SEASON_MOD: [[f32; 4]; 8] = [
    [0.8, 1.2, 1.5, 0.3],   // GRAIN
    [0.6, 1.0, 1.2, 0.8],   // TIMBER
    [1.2, 0.8, 0.6, 0.2],   // BOTANICALS
    [1.0, 1.0, 0.8, 0.6],   // FISH
    [0.8, 1.2, 1.0, 1.0],   // SALT
    [0.9, 1.0, 1.0, 0.9],   // ORE
    [0.9, 1.0, 1.0, 1.0],   // PRECIOUS
    [1.0, 0.8, 1.2, 0.6],   // EXOTIC
];

/// Per-resource-class climate modifier.  CLIMATE_CLASS_MOD[class][climate_phase]
/// Classes: 0=Crop, 1=Forestry, 2=Marine, 3=Mineral, 4=Evaporite
/// Phases:  0=TEMPERATE, 1=WARMING, 2=DROUGHT, 3=COOLING
const CLIMATE_CLASS_MOD: [[f32; 4]; 5] = [
    [1.0, 0.9, 0.5, 0.7],   // Crop
    [1.0, 0.9, 0.7, 0.8],   // Forestry
    [1.0, 1.0, 0.8, 0.9],   // Marine
    [1.0, 1.0, 1.0, 1.0],   // Mineral
    [1.0, 1.1, 1.2, 0.9],   // Evaporite
];

// Climate phase encoding.
const CLIMATE_TEMPERATE: u8 = 0;
const CLIMATE_WARMING: u8 = 1;
const CLIMATE_DROUGHT: u8 = 2;
const CLIMATE_COOLING: u8 = 3;

/// Terrain ecology caps: [soil_cap, water_cap, forest_cap].
/// Index matches Terrain enum.  Sourced from Python TERRAIN_ECOLOGY_CAPS.
const TERRAIN_CAPS: [[f32; 3]; 6] = [
    [0.95, 0.70, 0.40],  // Plains
    [0.50, 0.90, 0.40],  // Mountains
    [0.80, 0.90, 0.40],  // Coast
    [0.80, 0.80, 0.95],  // Forest
    [0.30, 0.20, 0.10],  // Desert
    [0.20, 0.60, 0.15],  // Tundra
];

/// Terrain ecology floors.
/// Matches Python _FLOOR_SOIL=0.05, _FLOOR_WATER=0.10, _FLOOR_FOREST=0.00.
const TERRAIN_FLOORS: [f32; 3] = [0.05, 0.10, 0.00];

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

/// All ecology tuning knobs.  Constructed Python-side from YAML overrides,
/// passed to Rust once.  No YAML parsing on the Rust side.
#[derive(Clone, Debug)]
pub struct EcologyConfig {
    // Soil
    pub soil_degradation: f32,
    pub soil_recovery: f32,
    pub mine_soil_degradation: f32,
    pub soil_recovery_pop_ratio: f32,
    pub agriculture_soil_bonus: f32,
    pub metallurgy_mine_reduction: f32,
    pub mechanization_mine_mult: f32,
    pub soil_pressure_threshold: f32,
    pub soil_pressure_streak_limit: i32,
    pub soil_pressure_degradation_mult: f32,
    // Water
    pub water_drought: f32,
    pub water_recovery: f32,
    pub irrigation_water_bonus: f32,
    pub irrigation_drought_mult: f32,
    pub cooling_water_loss: f32,
    pub warming_tundra_water_gain: f32,
    pub water_factor_denominator: f32,
    // Forest
    pub forest_clearing: f32,
    pub forest_regrowth: f32,
    pub cooling_forest_damage: f32,
    pub forest_pop_ratio: f32,
    pub forest_regrowth_water_gate: f32,
    pub cross_effect_forest_soil: f32,
    pub cross_effect_forest_threshold: f32,
    // Disease
    pub disease_severity_cap: f32,
    pub disease_decay_rate: f32,
    pub flare_overcrowding_threshold: f32,
    pub flare_overcrowding_spike: f32,
    pub flare_army_spike: f32,
    pub flare_water_spike: f32,
    pub flare_season_spike: f32,
    // Depletion & yields
    pub depletion_rate: f32,
    pub exhausted_trickle_fraction: f32,
    pub reserve_ramp_threshold: f32,
    pub resource_abundance_multiplier: f32,
    pub overextraction_streak_limit: i32,
    pub overextraction_yield_penalty: f32,
    pub workers_per_yield_unit: i32,
    // River cascade
    pub deforestation_threshold: f32,
    pub deforestation_water_loss: f32,
}

impl Default for EcologyConfig {
    fn default() -> Self {
        Self {
            soil_degradation: 0.005,
            soil_recovery: 0.05,
            mine_soil_degradation: 0.03,
            soil_recovery_pop_ratio: 0.75,
            agriculture_soil_bonus: 0.02,
            metallurgy_mine_reduction: 0.5,
            mechanization_mine_mult: 2.0,
            soil_pressure_threshold: 0.7,
            soil_pressure_streak_limit: 30,
            soil_pressure_degradation_mult: 2.0,
            water_drought: 0.04,
            water_recovery: 0.03,
            irrigation_water_bonus: 0.03,
            irrigation_drought_mult: 1.5,
            cooling_water_loss: 0.02,
            warming_tundra_water_gain: 0.05,
            water_factor_denominator: 0.5,
            forest_clearing: 0.02,
            forest_regrowth: 0.01,
            cooling_forest_damage: 0.01,
            forest_pop_ratio: 0.5,
            forest_regrowth_water_gate: 0.3,
            cross_effect_forest_soil: 0.01,
            cross_effect_forest_threshold: 0.5,
            disease_severity_cap: 0.15,
            disease_decay_rate: 0.25,
            flare_overcrowding_threshold: 0.8,
            flare_overcrowding_spike: 0.04,
            flare_army_spike: 0.03,
            flare_water_spike: 0.02,
            flare_season_spike: 0.02,
            depletion_rate: 0.009,
            exhausted_trickle_fraction: 0.04,
            reserve_ramp_threshold: 0.25,
            resource_abundance_multiplier: 1.0,
            overextraction_streak_limit: 35,
            overextraction_yield_penalty: 0.10,
            workers_per_yield_unit: 200,
            deforestation_threshold: 0.2,
            deforestation_water_loss: 0.05,
        }
    }
}

// ---------------------------------------------------------------------------
// River topology
// ---------------------------------------------------------------------------

/// Rivers as lists of region-id indices (upstream to downstream order).
#[derive(Clone, Debug, Default)]
pub struct RiverTopology {
    pub rivers: Vec<Vec<u16>>,
}

// ---------------------------------------------------------------------------
// Ecology event
// ---------------------------------------------------------------------------

/// Lightweight ecology trigger — Python materializes into full Event objects.
#[derive(Clone, Debug, PartialEq)]
pub struct EcologyEvent {
    /// 0 = soil_exhaustion, 1 = resource_depletion
    pub event_type: u8,
    pub region_id: u16,
    /// Resource slot index (255 = N/A for soil_exhaustion)
    pub slot: u8,
    /// Severity / penalty magnitude
    pub magnitude: f32,
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

/// Compute effective capacity for a region.
/// Mirrors Python: max(int(carrying_capacity * capacity_modifier * soil * water_factor), 1)
#[inline]
pub fn effective_capacity(region: &RegionState, config: &EcologyConfig) -> u16 {
    let water_factor = (region.water / config.water_factor_denominator).min(1.0);
    let raw = region.carrying_capacity as f32
        * region.capacity_modifier
        * region.soil
        * water_factor;
    (raw as u16).max(1)
}

/// Pressure multiplier used for recovery rate scaling.
/// Mirrors Python: max(0.1, 1.0 - population / effective_capacity)
#[inline]
pub fn pressure_multiplier(region: &RegionState, config: &EcologyConfig) -> f32 {
    let eff = effective_capacity(region, config);
    if eff == 0 {
        return 1.0;
    }
    (1.0 - region.population as f32 / eff as f32).max(0.1)
}

/// Map ResourceType u8 to class index for CLIMATE_CLASS_MOD.
#[inline]
fn resource_class_index(rtype: u8) -> usize {
    match rtype {
        RT_GRAIN | RT_BOTANICALS | RT_EXOTIC => CLASS_CROP,
        RT_TIMBER => CLASS_FORESTRY,
        RT_FISH => CLASS_MARINE,
        RT_ORE | RT_PRECIOUS => CLASS_MINERAL,
        RT_SALT => CLASS_EVAPORITE,
        _ => CLASS_CROP,
    }
}

/// Is this resource type a mineral (depletable reserves)?
#[inline]
fn is_mineral(rtype: u8) -> bool {
    rtype == RT_ORE || rtype == RT_PRECIOUS
}

/// Is this resource type depletable (for overextraction tracking)?
/// Matches Python DEPLETABLE = {GRAIN, BOTANICALS, FISH, ORE, PRECIOUS}
#[inline]
fn is_depletable(rtype: u8) -> bool {
    matches!(rtype, RT_GRAIN | RT_BOTANICALS | RT_FISH | RT_ORE | RT_PRECIOUS)
}

/// Is this resource type a crop for soil pressure tracking?
/// Matches Python: ResourceType.GRAIN, ResourceType.BOTANICALS
#[inline]
fn is_crop_for_soil_pressure(rtype: u8) -> bool {
    rtype == RT_GRAIN || rtype == RT_BOTANICALS
}

/// Round to 4 decimal places, matching Python's round(x, 4).
#[inline]
fn round4(x: f32) -> f32 {
    (x * 10000.0).round() / 10000.0
}

/// Clamp ecology values to terrain caps/floors with round(x,4) quantization.
#[inline]
fn clamp_ecology(region: &mut RegionState) {
    let t = region.terrain as usize;
    let caps = if t < TERRAIN_CAPS.len() {
        &TERRAIN_CAPS[t]
    } else {
        &TERRAIN_CAPS[TERRAIN_PLAINS as usize]
    };
    region.soil = round4(region.soil).clamp(TERRAIN_FLOORS[0], caps[0]);
    region.water = round4(region.water).clamp(TERRAIN_FLOORS[1], caps[1]);
    region.forest_cover = round4(region.forest_cover).clamp(TERRAIN_FLOORS[2], caps[2]);
}

/// Derive season_id from turn: (turn % 12) / 3
#[inline]
pub fn season_id_from_turn(turn: u32) -> u8 {
    ((turn % 12) / 3) as u8
}

// ---------------------------------------------------------------------------
// Step 1: Disease severity
// ---------------------------------------------------------------------------

fn tick_disease(
    region: &mut RegionState,
    config: &EcologyConfig,
    pandemic_suppressed: bool,
    army_arrived: bool,
    season_id: u8,
) {
    let baseline = region.disease_baseline;
    let mut severity = region.endemic_severity;
    let mut triggered = false;

    // Overcrowding
    if region.carrying_capacity > 0
        && region.population as f32
            > config.flare_overcrowding_threshold * region.carrying_capacity as f32
    {
        severity += config.flare_overcrowding_spike;
        triggered = true;
    }

    // Army passage (mask pre-computed by Python)
    if army_arrived {
        severity += config.flare_army_spike;
        triggered = true;
    }

    // Water quality: low water on non-desert terrain
    let pre_water = region.water;
    if region.terrain != TERRAIN_DESERT && pre_water < 0.3 {
        severity += config.flare_water_spike;
        triggered = true;
    }

    // Water quality: inter-turn water drop > 0.1 (don't double-count with low-water)
    if region.terrain != TERRAIN_DESERT && region.prev_turn_water >= 0.0 {
        let water_delta = region.prev_turn_water - pre_water;
        if water_delta > 0.1 && !(pre_water < 0.3) {
            severity += config.flare_water_spike;
            triggered = true;
        }
    }

    // Seasonal peak (disease vector based on baseline + terrain)
    let is_cholera = region.terrain == TERRAIN_DESERT;
    let is_fever = region.disease_baseline >= 0.02;
    if is_fever && !is_cholera && season_id == 1 {
        // Summer peak for Fever
        severity += config.flare_season_spike;
        triggered = true;
    } else if !is_fever && !is_cholera && region.disease_baseline <= 0.01 && season_id == 3 {
        // Winter peak for Plague
        severity += config.flare_season_spike;
        triggered = true;
    }

    // Pandemic suppression: reset to pre-trigger value
    if pandemic_suppressed {
        severity = region.endemic_severity;
        triggered = false;
    }

    if triggered {
        region.endemic_severity = severity.min(config.disease_severity_cap);
    } else {
        // Exponential decay toward baseline
        region.endemic_severity -=
            config.disease_decay_rate * (region.endemic_severity - baseline);
    }

    // Floor at baseline
    if region.endemic_severity < baseline {
        region.endemic_severity = baseline;
    }
}

// ---------------------------------------------------------------------------
// Step 2: Depletion feedback / streak updates (controlled only)
// ---------------------------------------------------------------------------

fn tick_depletion_feedback(
    region: &mut RegionState,
    config: &EcologyConfig,
    events: &mut Vec<EcologyEvent>,
) {
    // --- Soil exhaustion (population pressure) ---
    let has_crop = region.resource_types.iter().any(|&rt| {
        rt != EMPTY_SLOT && is_crop_for_soil_pressure(rt)
    });

    if has_crop
        && region.carrying_capacity > 0
        && region.population as f32
            > config.soil_pressure_threshold * region.carrying_capacity as f32
    {
        region.soil_pressure_streak += 1;
        if region.soil_pressure_streak >= config.soil_pressure_streak_limit {
            events.push(EcologyEvent {
                event_type: 0, // soil_exhaustion
                region_id: region.region_id,
                slot: 255,
                magnitude: config.soil_pressure_degradation_mult,
            });
        }
    } else {
        region.soil_pressure_streak = 0;
    }

    // --- Overextraction (per-resource) ---
    let workers_per_unit = config.workers_per_yield_unit;
    let pop = region.population;
    let worker_count = if pop > 0 { pop as i32 / 5 } else { 0 };

    for slot in 0..3_usize {
        let rtype = region.resource_types[slot];
        if rtype == EMPTY_SLOT || !is_depletable(rtype) {
            continue;
        }
        let eff_yield = region.resource_effective_yield[slot];
        let sustainable = eff_yield * workers_per_unit as f32;
        if sustainable > 0.0 && worker_count as f32 > sustainable {
            region.overextraction_streak[slot] += 1;
            if region.overextraction_streak[slot] >= config.overextraction_streak_limit {
                region.resource_effective_yield[slot] *= 1.0 - config.overextraction_yield_penalty;
                region.overextraction_streak[slot] = 0;
                events.push(EcologyEvent {
                    event_type: 1, // resource_depletion
                    region_id: region.region_id,
                    slot: slot as u8,
                    magnitude: config.overextraction_yield_penalty,
                });
            }
        } else {
            region.overextraction_streak[slot] = 0;
        }
    }
}

// ---------------------------------------------------------------------------
// Step 3: Soil / Water / Forest tick
// ---------------------------------------------------------------------------

fn tick_soil_controlled(
    region: &mut RegionState,
    config: &EcologyConfig,
    degradation_mult: f32,
) {
    let eff = effective_capacity(region, config);

    // Degradation: overpopulation
    if region.population > eff {
        region.soil -= config.soil_degradation * degradation_mult;
    }

    // Degradation: active mines
    if region.has_mines {
        let mut mine_rate = config.mine_soil_degradation;
        if region.active_focus == FOCUS_METALLURGY {
            mine_rate *= config.metallurgy_mine_reduction;
        } else if region.active_focus == FOCUS_MECHANIZATION {
            mine_rate *= config.mechanization_mine_mult;
        }
        region.soil -= mine_rate;
    }

    // Recovery: pressure-gated
    if (region.population as f32) < eff as f32 * config.soil_recovery_pop_ratio {
        let mut rate = config.soil_recovery;
        rate *= pressure_multiplier(region, config);
        if region.active_focus == FOCUS_AGRICULTURE {
            rate += config.agriculture_soil_bonus;
        }
        region.soil += rate;
    }
}

fn tick_soil_uncontrolled(region: &mut RegionState, config: &EcologyConfig) {
    let eff = effective_capacity(region, config);
    if (region.population as f32) < eff as f32 * config.soil_recovery_pop_ratio {
        let rate = config.soil_recovery * pressure_multiplier(region, config);
        region.soil += rate;
    }
}

fn tick_water_controlled(
    region: &mut RegionState,
    config: &EcologyConfig,
    climate_phase: u8,
) {
    // Degradation / phase effects
    if climate_phase == CLIMATE_DROUGHT {
        let mut rate = config.water_drought;
        if region.has_irrigation {
            rate *= config.irrigation_drought_mult;
        }
        region.water -= rate;
    } else if climate_phase == CLIMATE_COOLING {
        region.water -= config.cooling_water_loss;
    } else if climate_phase == CLIMATE_WARMING && region.terrain == TERRAIN_TUNDRA {
        region.water += config.warming_tundra_water_gain;
    }

    // Recovery (temperate only)
    if climate_phase == CLIMATE_TEMPERATE {
        let rate = config.water_recovery * pressure_multiplier(region, config);
        region.water += rate;
    }

    // Irrigation bonus (always except drought)
    if region.has_irrigation && climate_phase != CLIMATE_DROUGHT {
        let bonus = config.irrigation_water_bonus * pressure_multiplier(region, config);
        region.water += bonus;
    }
}

fn tick_water_uncontrolled(
    region: &mut RegionState,
    config: &EcologyConfig,
    climate_phase: u8,
) {
    if climate_phase == CLIMATE_DROUGHT {
        region.water -= config.water_drought;
    } else if climate_phase == CLIMATE_COOLING {
        region.water -= config.cooling_water_loss;
    } else if climate_phase == CLIMATE_WARMING && region.terrain == TERRAIN_TUNDRA {
        region.water += config.warming_tundra_water_gain;
    } else if climate_phase == CLIMATE_TEMPERATE {
        let rate = config.water_recovery * pressure_multiplier(region, config);
        region.water += rate;
    }
}

fn tick_forest_controlled(
    region: &mut RegionState,
    config: &EcologyConfig,
    climate_phase: u8,
) {
    let pop_threshold = region.carrying_capacity as f32 * config.forest_pop_ratio;

    if region.population as f32 > pop_threshold {
        region.forest_cover -= config.forest_clearing;
    }

    if climate_phase == CLIMATE_COOLING {
        region.forest_cover -= config.cooling_forest_damage;
    }

    if (region.population as f32) < pop_threshold
        && region.water >= config.forest_regrowth_water_gate
    {
        let rate = config.forest_regrowth * pressure_multiplier(region, config);
        region.forest_cover += rate;
    }
}

fn tick_forest_uncontrolled(
    region: &mut RegionState,
    config: &EcologyConfig,
    climate_phase: u8,
) {
    let pop_threshold = region.carrying_capacity as f32 * config.forest_pop_ratio;

    if (region.population as f32) < pop_threshold
        && region.water >= config.forest_regrowth_water_gate
    {
        let rate = config.forest_regrowth * pressure_multiplier(region, config);
        region.forest_cover += rate;
    }

    if climate_phase == CLIMATE_COOLING {
        region.forest_cover -= config.cooling_forest_damage;
    }
}

// ---------------------------------------------------------------------------
// Step 4: Cross-effects
// ---------------------------------------------------------------------------

#[inline]
fn apply_cross_effects(region: &mut RegionState, config: &EcologyConfig) {
    if region.forest_cover > config.cross_effect_forest_threshold {
        region.soil += config.cross_effect_forest_soil;
    }
}

// ---------------------------------------------------------------------------
// Step 6: River cascade
// ---------------------------------------------------------------------------

fn river_cascade(
    regions: &mut [RegionState],
    config: &EcologyConfig,
    river_topology: &RiverTopology,
) {
    let n = regions.len();
    let mut affected = vec![false; n];

    // Deduplicate (source, downstream) pairs across rivers.
    let mut seen: Vec<(u16, u16)> = Vec::new();

    for river in &river_topology.rivers {
        for (i, &upstream_id) in river.iter().enumerate() {
            let uid = upstream_id as usize;
            if uid >= n {
                continue;
            }
            if regions[uid].forest_cover < config.deforestation_threshold {
                for &downstream_id in &river[i + 1..] {
                    let did = downstream_id as usize;
                    if did >= n {
                        continue;
                    }
                    let pair = (upstream_id, downstream_id);
                    if seen.contains(&pair) {
                        continue;
                    }
                    seen.push(pair);
                    regions[did].water -= config.deforestation_water_loss;
                    affected[did] = true;
                }
            }
        }
    }

    // Second clamp pass for cascade-affected regions.
    for (i, &was_affected) in affected.iter().enumerate() {
        if was_affected {
            clamp_ecology(&mut regions[i]);
        }
    }
}

// ---------------------------------------------------------------------------
// Step 7: Resource yield computation
// ---------------------------------------------------------------------------

pub fn compute_yields(
    region: &mut RegionState,
    config: &EcologyConfig,
    season_id: u8,
    climate_phase: u8,
) -> [f32; 3] {
    let mut yields = [0.0_f32; 3];
    let phase_idx = (climate_phase as usize).min(3);

    for slot in 0..3_usize {
        let rtype = region.resource_types[slot];
        if rtype == EMPTY_SLOT {
            continue;
        }

        // Suspension check
        if region.resource_suspension[slot] {
            continue;
        }

        let base = region.resource_base_yield[slot];
        let sid = (season_id as usize).min(3);
        let rt_idx = (rtype as usize).min(7);
        let season_mod = SEASON_MOD[rt_idx][sid];
        let class_idx = resource_class_index(rtype);
        let climate_mod = CLIMATE_CLASS_MOD[class_idx][phase_idx];

        // Ecology mod by class
        let ecology_mod = match class_idx {
            CLASS_CROP => region.soil * region.water,
            CLASS_FORESTRY => region.forest_cover,
            _ => 1.0,
        };

        // Reserve ramp (minerals only)
        let mut reserve_ramp = 1.0_f32;
        if is_mineral(rtype) {
            let reserves = region.resource_reserves[slot];
            // Depletion — only if there are workers and reserves remain
            if reserves > 0.01 && region.population > 0 {
                let eff = effective_capacity(region, config);
                let target_workers = (eff / 3).max(1);
                let worker_count = region.population / 5;
                let extraction =
                    base * (worker_count as f32 / target_workers as f32);
                region.resource_reserves[slot] =
                    (reserves - extraction * config.depletion_rate).max(0.0);
            }

            let reserves = region.resource_reserves[slot];
            if reserves < 0.01 {
                // Exhausted trickle
                yields[slot] = base * config.exhausted_trickle_fraction;
                region.resource_yields[slot] = yields[slot];
                continue;
            }

            reserve_ramp = (reserves / config.reserve_ramp_threshold).min(1.0);
        }

        let y = base * season_mod * climate_mod * ecology_mod * reserve_ramp
            * config.resource_abundance_multiplier;

        yields[slot] = y;
        region.resource_yields[slot] = y;
    }

    yields
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

/// Execute a full ecology tick.  Mutates `regions` in-place and returns:
///   - `Vec<[f32; 3]>`: per-region current-turn yields
///   - `Vec<EcologyEvent>`: ecology trigger events (sorted by region_id, event_type, slot)
pub fn tick_ecology(
    regions: &mut [RegionState],
    config: &EcologyConfig,
    turn: u32,
    climate_phase: u8,
    pandemic_mask: &[bool],
    army_arrived_mask: &[bool],
    river_topology: &RiverTopology,
) -> (Vec<[f32; 3]>, Vec<EcologyEvent>) {
    let n = regions.len();
    let season_id = season_id_from_turn(turn);
    let mut all_events: Vec<EcologyEvent> = Vec::new();
    let mut all_yields: Vec<[f32; 3]> = vec![[0.0; 3]; n];

    // -----------------------------------------------------------------------
    // Steps 1-5: Per-region, independent (ready for par_iter_mut later)
    // -----------------------------------------------------------------------
    for i in 0..n {
        let region = &mut regions[i];
        let pandemic = pandemic_mask.get(i).copied().unwrap_or(false);
        let army = army_arrived_mask.get(i).copied().unwrap_or(false);
        let controlled = region.controller_civ != UNCONTROLLED;

        // Step 1: Disease (both controlled and uncontrolled)
        tick_disease(region, config, pandemic, army, season_id);

        if controlled {
            // Step 2a: Compute soil_mult from CURRENT streak (before this turn's
            // depletion feedback modifies it).  Matches Python ordering where
            // soil_mult is read before update_depletion_feedback runs.
            let soil_mult = if region.soil_pressure_streak >= config.soil_pressure_streak_limit {
                config.soil_pressure_degradation_mult
            } else {
                1.0
            };

            // Step 2b: Depletion feedback (may increment/reset streak, emit events)
            tick_depletion_feedback(region, config, &mut all_events);

            // Step 3: Soil/water/forest (controlled path)
            tick_soil_controlled(region, config, soil_mult);
            tick_water_controlled(region, config, climate_phase);
            tick_forest_controlled(region, config, climate_phase);
        } else {
            // Step 3: Soil/water/forest (uncontrolled — natural recovery only)
            tick_soil_uncontrolled(region, config);
            tick_water_uncontrolled(region, config, climate_phase);
            tick_forest_uncontrolled(region, config, climate_phase);
        }

        // Step 4: Cross-effects (both)
        apply_cross_effects(region, config);

        // Step 5: Clamp (both)
        clamp_ecology(region);
    }

    // -----------------------------------------------------------------------
    // Step 6: River cascade (sequential, cross-region)
    // -----------------------------------------------------------------------
    river_cascade(regions, config, river_topology);

    // -----------------------------------------------------------------------
    // Step 7: Resource yield computation (per-region)
    // -----------------------------------------------------------------------
    for i in 0..n {
        let region = &mut regions[i];
        all_yields[i] = compute_yields(region, config, season_id, climate_phase);
    }

    // -----------------------------------------------------------------------
    // Step 8: Finalize — set prev_turn_water
    // -----------------------------------------------------------------------
    for region in regions.iter_mut() {
        region.prev_turn_water = region.water;
    }

    // Sort events deterministically by (region_id, event_type, slot).
    all_events.sort_by(|a, b| {
        a.region_id
            .cmp(&b.region_id)
            .then(a.event_type.cmp(&b.event_type))
            .then(a.slot.cmp(&b.slot))
    });

    (all_yields, all_events)
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn make_plains_region(id: u16) -> RegionState {
        let mut r = RegionState::new(id);
        r.terrain = TERRAIN_PLAINS;
        r.soil = 0.80;
        r.water = 0.60;
        r.forest_cover = 0.20;
        r.carrying_capacity = 60;
        r.population = 30;
        r.controller_civ = 0;
        r.capacity_modifier = 1.0;
        r.prev_turn_water = 0.60;
        r
    }

    #[test]
    fn test_effective_capacity_basic() {
        let config = EcologyConfig::default();
        let r = make_plains_region(0);
        let eff = effective_capacity(&r, &config);
        // 60 * 1.0 * 0.80 * min(1.0, 0.60/0.50) = 60 * 0.80 * 1.0 = 48
        assert_eq!(eff, 48);
    }

    #[test]
    fn test_pressure_multiplier_basic() {
        let config = EcologyConfig::default();
        let r = make_plains_region(0);
        let pm = pressure_multiplier(&r, &config);
        // eff = 48, pop = 30: 1.0 - 30/48 = 0.375
        assert!((pm - 0.375).abs() < 0.001);
    }

    #[test]
    fn test_round4() {
        assert!((round4(0.12345) - 0.1235).abs() < f32::EPSILON);
        assert!((round4(0.0) - 0.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_clamp_ecology_plains() {
        let mut r = make_plains_region(0);
        r.soil = 1.5;
        r.water = -0.1;
        r.forest_cover = 0.6;
        clamp_ecology(&mut r);
        assert!((r.soil - 0.95).abs() < f32::EPSILON);
        assert!((r.water - 0.10).abs() < f32::EPSILON);
        assert!((r.forest_cover - 0.40).abs() < f32::EPSILON);
    }

    #[test]
    fn test_season_id_from_turn() {
        assert_eq!(season_id_from_turn(0), 0);
        assert_eq!(season_id_from_turn(3), 1);
        assert_eq!(season_id_from_turn(6), 2);
        assert_eq!(season_id_from_turn(9), 3);
        assert_eq!(season_id_from_turn(12), 0);
    }

    #[test]
    fn test_resource_class_index_mapping() {
        assert_eq!(resource_class_index(RT_GRAIN), CLASS_CROP);
        assert_eq!(resource_class_index(RT_BOTANICALS), CLASS_CROP);
        assert_eq!(resource_class_index(RT_EXOTIC), CLASS_CROP);
        assert_eq!(resource_class_index(RT_TIMBER), CLASS_FORESTRY);
        assert_eq!(resource_class_index(RT_FISH), CLASS_MARINE);
        assert_eq!(resource_class_index(RT_ORE), CLASS_MINERAL);
        assert_eq!(resource_class_index(RT_PRECIOUS), CLASS_MINERAL);
        assert_eq!(resource_class_index(RT_SALT), CLASS_EVAPORITE);
    }
}
