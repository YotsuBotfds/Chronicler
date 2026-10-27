//! Rust-side mirror of Python Region ecology fields.
//! terrain stored as u8 — not used in M25 but present for M26 schema stability.

#[allow(dead_code)]
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Terrain {
    Plains = 0, Mountains = 1, Coast = 2, Forest = 3, Desert = 4, Tundra = 5,
    // Geography 2.0 (append only; mirrors Python ffi_constants.TERRAIN_MAP).
    Steppe = 6, Jungle = 7, Marsh = 8,
}

#[allow(dead_code)]
impl Terrain {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Plains), 1 => Some(Self::Mountains), 2 => Some(Self::Coast),
            3 => Some(Self::Forest), 4 => Some(Self::Desert), 5 => Some(Self::Tundra),
            6 => Some(Self::Steppe), 7 => Some(Self::Jungle), 8 => Some(Self::Marsh),
            _ => None,
        }
    }
}

#[derive(Clone, Debug)]
pub struct RegionState {
    pub region_id: u16,
    pub terrain: u8,
    pub carrying_capacity: u16,  // Python max is 100
    pub population: u16,
    pub soil: f32,
    pub water: f32,
    pub forest_cover: f32,
    // M26 additions. Geography 2.0: adjacency list (sorted ascending, no
    // duplicates) replacing the former u32 bitmask, so worlds are no longer
    // capped at 32 regions. Iterating the list visits neighbours in the same
    // ascending order the bitmask walk (bit 0..31) did.
    pub adjacency: Vec<u16>,
    pub controller_civ: u8,      // civ_id controlling region (255 = uncontrolled)
    pub trade_route_count: u8,
    // M34: Resource state
    pub resource_types: [u8; 3],
    pub resource_yields: [f32; 3],
    pub resource_reserves: [f32; 3],
    /// Goods each resource slot produced in this turn's economy tick
    /// (`economy::EconomyRegionResult::slot_output`), which the Phase 9
    /// ecology tick depletes mineral reserves by. `None` without an economy
    /// tick this turn (`EcologySimulator`, `--agents off`): the aggregate
    /// labour proxy (population / 5) is used. Transient: set by
    /// `AgentSimulator::tick_economy`, consumed and cleared by its
    /// `tick_ecology`, never read from or written to a batch.
    pub realized_extraction: Option<[f32; 3]>,
    pub season: u8,
    pub season_id: u8,
    // M35a rivers. Geography 2.0: sorted river ids this region lies on
    // (formerly a u32 bitmask, bit i = river i). Two regions share a river
    // exactly when the lists intersect, matching the old `mask & mask != 0`.
    pub rivers: Vec<u16>,
    // M35b: Endemic disease severity
    pub endemic_severity: f32,
    // M36: Cultural identity signals
    pub culture_investment_active: bool,
    pub controller_values: [u8; 3],  // Controlling civ's cultural values, 0xFF = empty
    // M37: Conversion signals (Python-computed, per-region)
    pub conversion_rate: f32,              // 0.0 = no conversion pressure
    pub conversion_target_belief: u8,      // dominant converting faith
    pub conquest_conversion_active: bool,  // Militant holy war forced flip
    pub majority_belief: u8,               // for satisfaction comparison
    // M38a:
    pub has_temple: bool,
    // M38b: Persecution
    pub persecution_intensity: f32,
    /// The faith the persecuting (militant) ruler enforces here: Python's
    /// builder measures the persecuted minority against it. BELIEF_NONE when
    /// the batch carries no `persecuting_faith` column (see `persecuted_belief`).
    pub persecuting_faith: u8,
    pub schism_convert_from: u8,
    pub schism_convert_to: u8,
    // M42: Goods economy signals
    pub farmer_income_modifier: f32,
    pub food_sufficiency: f32,
    pub merchant_margin: f32,
    pub merchant_route_margin: f32,
    pub merchant_trade_income: f32,
    /// Output per farmer against constant returns (economy `farm_productivity`;
    /// 1.0 without the column): scales farmer income.
    pub farm_productivity: f32,
    // M48: Per-region transient memory signals (cleared each turn by Python via set_region_state)
    pub controller_changed_this_turn: bool,
    pub war_won_this_turn: bool,
    pub seceded_this_turn: bool,
    pub catastrophe_deaths_this_turn: u16,
    // M54a: Ecology schema — read-only inputs from Python
    pub disease_baseline: f32,           // set by world_gen, immutable after init
    pub capacity_modifier: f32,          // set by climate phase each turn
    pub resource_base_yield: [f32; 3],   // set by world_gen
    pub resource_effective_yield: [f32; 3], // persistent degradation track
    pub resource_suspension: [bool; 3],  // Python pre-computes suspension per slot
    pub has_irrigation: bool,            // from infrastructure
    pub has_mines: bool,                 // from infrastructure
    pub active_focus: u8,                // TechFocus enum, 0 = None
    // M54a: Ecology schema — Rust-owned persistent state
    pub prev_turn_water: f32,            // previous turn's water, set after ecology tick
    pub soil_pressure_streak: i32,       // depletion counter
    pub overextraction_streak: [i32; 3], // per-slot extraction streak
    // M55a: Spatial substrate signals
    pub is_capital: bool,
    pub temple_prestige: f32,
    // M58a: Per-good stockpile levels (from Python RegionStockpile)
    pub stockpile: [f32; crate::economy::NUM_GOODS],
    // Geography 2.0: latitude-band scale on climate-driven ecology losses
    // (drought water, cooling water and forest). 1.0 = unscaled, which keeps
    // template-world arithmetic bit-identical.
    pub climate_exposure: f32,
    /// Regional climate: this turn's harvest shock, the crop loss of the
    /// region's bad harvest year (Python `climate.region_harvest_shocks`;
    /// 0.0 without the `harvest_shock` column).
    pub harvest_shock: f32,
    /// Cities (`--cities`): this region's draw on rural migrants of the realm
    /// (`migration_drivers` urban pull), recomputed by Python for every batch.
    /// 0 when the batch carries no `city_pull` column (the switch off).
    pub city_pull: f32,
    /// Seats of learning (`--scholarship`): this region's draw on the scholar
    /// agents of the realm (`migration_drivers` learning pull), recomputed by
    /// Python for every batch. 0 when the batch carries no `seat_pull`
    /// column (the switch off).
    pub seat_pull: f32,
    /// Seats of learning: a seat here fell within the last few turns and none
    /// stands now, so its scholars may cross a border to a seat next door.
    /// false without the `seat_flight` column.
    pub seat_flight: bool,
    /// Guilds (`--guilds`): news of a movement event in this region last
    /// turn (`knowledge::news_code`: creed and kind), observed as a
    /// movement-news packet by the agents here. `knowledge::NO_NEWS` when the
    /// batch carries no `movement_news` column (the switch off) or nothing
    /// happened; recomputed by Python for every batch.
    pub movement_news: u8,
    /// Intensity of that news (0 none).
    pub movement_news_intensity: u8,
    /// The goods economy's demand and post-trade supply per category (food,
    /// raw material, luxury; `economy::GOOD_CATEGORY`) at the last economy
    /// tick: the merchant planner's market prices (`merchant::market_price`).
    /// 0 when the batch carries no `market_demand_*` / `market_supply_*`
    /// columns: no non-food market, and food prices without the delivery
    /// tally.
    pub market_demand: [f32; crate::economy::NUM_CATEGORIES],
    pub market_supply: [f32; crate::economy::NUM_CATEGORIES],
    /// Crafts: wares on hand over the people's demand at the last economy
    /// tick (`economy::EconomyRegionResult::craft_sufficiency`, 0..2); 0
    /// without the `craft_sufficiency` column (no wares market). Restores the
    /// material need (`needs::restore_needs`).
    pub craft_sufficiency: f32,
    /// Consecutive turns, up to the previous turn, that the region's food
    /// sufficiency stayed below the famine severity threshold (Python's
    /// `Region.food_severe_turns`, written in Phase 9 after this batch was
    /// built). The demographic tick adds this turn when sufficiency is still
    /// below it (`demographics::hunger_components`). 0 when the batch carries
    /// no `food_severe_turns` column.
    pub food_severe_turns: u16,
    /// Harsh rule by the region's controller, 0..1 (1 under martial law):
    /// pressure on its people's autonomy need. 0 when the batch carries no
    /// `harsh_rule` column.
    pub harsh_rule: f32,
    /// A successful raid struck the region this turn (one-turn signal,
    /// cleared by Python's builder). False when the batch has no
    /// `raided_this_turn` column.
    pub raided_this_turn: bool,
}

/// Decode a legacy u32 bitmask into the ascending id list it denotes.
pub fn mask_to_ids(mask: u32) -> Vec<u16> {
    (0..32u16).filter(|bit| mask & (1u32 << bit) != 0).collect()
}

/// Normalize an id list in place: ascending order, duplicates removed.
pub fn normalize_ids(ids: &mut Vec<u16>) {
    ids.sort_unstable();
    ids.dedup();
}

/// True when two ascending id lists share an element (two-pointer walk).
#[inline]
pub fn sorted_ids_intersect(a: &[u16], b: &[u16]) -> bool {
    let (mut i, mut j) = (0usize, 0usize);
    while i < a.len() && j < b.len() {
        match a[i].cmp(&b[j]) {
            std::cmp::Ordering::Less => i += 1,
            std::cmp::Ordering::Greater => j += 1,
            std::cmp::Ordering::Equal => return true,
        }
    }
    false
}

/// M38b: whether an agent of `agent_belief` is among the people a persecuting
/// ruler targets. Python's builder measures the persecuted minority against
/// the militant ruler's majority faith (`persecuting_faith`), so the tick
/// targets the same agents: every faith but the ruler's. Agents without a
/// faith are never persecuted. Without a persecuting faith (BELIEF_NONE, a
/// batch with no `persecuting_faith` column) the region's majority belief
/// stands in for it, the rule before the column existed. The intensity is the
/// caller's: this only says who, not how much.
#[inline]
pub fn persecuted_belief(agent_belief: u8, persecuting_faith: u8, majority_belief: u8) -> bool {
    if agent_belief == crate::agent::BELIEF_NONE {
        return false;
    }
    let enforced = if persecuting_faith != crate::agent::BELIEF_NONE {
        persecuting_faith
    } else {
        majority_belief
    };
    agent_belief != enforced
}

impl RegionState {
    /// M38b: whether this region's persecution reaches an agent of `belief`
    /// (see `persecuted_belief`); false when the region is not persecuted.
    #[inline]
    pub fn persecutes(&self, belief: u8) -> bool {
        self.persecution_intensity > 0.0
            && persecuted_belief(belief, self.persecuting_faith, self.majority_belief)
    }

    /// True when this region and `other` lie on a common river.
    #[inline]
    pub fn shares_river(&self, other: &RegionState) -> bool {
        sorted_ids_intersect(&self.rivers, &other.rivers)
    }

    /// True when the region lies on any river.
    #[inline]
    pub fn has_river(&self) -> bool {
        !self.rivers.is_empty()
    }

    /// True when `region_id` is in the adjacency list.
    #[inline]
    pub fn is_adjacent_to(&self, region_id: u16) -> bool {
        self.adjacency.binary_search(&region_id).is_ok()
    }

    pub fn new(region_id: u16) -> Self {
        Self {
            region_id,
            terrain: Terrain::Plains as u8,
            carrying_capacity: 60,
            population: 0,
            soil: 0.8,
            water: 0.6,
            forest_cover: 0.3,
            adjacency: Vec::new(),
            controller_civ: 255,
            trade_route_count: 0,
            resource_types: [255, 255, 255],
            resource_yields: [0.0, 0.0, 0.0],
            resource_reserves: [1.0, 1.0, 1.0],
            realized_extraction: None,
            season: 0,
            season_id: 0,
            rivers: Vec::new(),
            endemic_severity: 0.0,
            culture_investment_active: false,
            controller_values: [0xFF, 0xFF, 0xFF],
            conversion_rate: 0.0,
            conversion_target_belief: 0xFF,
            conquest_conversion_active: false,
            majority_belief: 0xFF,
            has_temple: false,
            persecution_intensity: 0.0,
            persecuting_faith: 0xFF,
            schism_convert_from: 0xFF,
            schism_convert_to: 0xFF,
            farmer_income_modifier: 1.0,
            food_sufficiency: 1.0,
            merchant_margin: 0.0,
            merchant_route_margin: 0.0,
            merchant_trade_income: 0.0,
            farm_productivity: 1.0,
            controller_changed_this_turn: false,
            war_won_this_turn: false,
            seceded_this_turn: false,
            catastrophe_deaths_this_turn: 0,
            // M54a ecology defaults
            disease_baseline: 0.0,
            capacity_modifier: 1.0,
            resource_base_yield: [0.0, 0.0, 0.0],
            resource_effective_yield: [0.0, 0.0, 0.0],
            resource_suspension: [false, false, false],
            has_irrigation: false,
            has_mines: false,
            active_focus: 0,
            prev_turn_water: 0.0,
            soil_pressure_streak: 0,
            overextraction_streak: [0, 0, 0],
            // M55a: Spatial substrate
            is_capital: false,
            temple_prestige: 0.0,
            // M58a: Stockpile
            stockpile: [0.0; crate::economy::NUM_GOODS],
            climate_exposure: 1.0,
            harvest_shock: 0.0,
            city_pull: 0.0,
            seat_pull: 0.0,
            seat_flight: false,
            movement_news: crate::knowledge::NO_NEWS,
            movement_news_intensity: 0,
            market_demand: [0.0; crate::economy::NUM_CATEGORIES],
            market_supply: [0.0; crate::economy::NUM_CATEGORIES],
            craft_sufficiency: 0.0,
            food_severe_turns: 0,
            harsh_rule: 0.0,
            raided_this_turn: false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_region_new_has_m26_defaults() {
        let r = RegionState::new(5);
        assert!(r.adjacency.is_empty());
        assert_eq!(r.controller_civ, 255); // uncontrolled
        assert_eq!(r.trade_route_count, 0);
    }

    #[test]
    fn test_persecution_targets_everyone_outside_the_rulers_faith() {
        const RULER: u8 = 2;
        const LOCAL: u8 = 5;
        let mut r = RegionState::new(0);
        assert_eq!(r.persecuting_faith, crate::agent::BELIEF_NONE);
        r.persecution_intensity = 0.8;
        r.persecuting_faith = RULER;
        // The ruler's faith is a local minority: the local majority and any
        // third faith are persecuted, the ruler's co-religionists are not.
        r.majority_belief = LOCAL;
        assert!(r.persecutes(LOCAL));
        assert!(r.persecutes(7));
        assert!(!r.persecutes(RULER));
        assert!(!r.persecutes(crate::agent::BELIEF_NONE));
        // The ruler's faith is the majority: the same rule.
        r.majority_belief = RULER;
        assert!(r.persecutes(LOCAL));
        assert!(!r.persecutes(RULER));
        // No intensity, no persecution.
        r.persecution_intensity = 0.0;
        assert!(!r.persecutes(LOCAL));
    }

    #[test]
    fn test_persecution_without_a_persecuting_faith_uses_the_region_majority() {
        // Batches without the persecuting_faith column keep the earlier rule.
        let mut r = RegionState::new(0);
        r.persecution_intensity = 0.5;
        r.majority_belief = 3;
        assert!(r.persecutes(4));
        assert!(!r.persecutes(3));
        assert!(!r.persecutes(crate::agent::BELIEF_NONE));
        assert!(persecuted_belief(4, crate::agent::BELIEF_NONE, 3));
        assert!(!persecuted_belief(3, crate::agent::BELIEF_NONE, 3));
    }

    #[test]
    fn test_region_new_has_river_mask_default() {
        let r = RegionState::new(5);
        assert!(r.rivers.is_empty());
        assert!(!r.has_river());
    }

    #[test]
    fn test_region_new_has_endemic_severity_default() {
        let r = RegionState::new(5);
        assert!((r.endemic_severity - 0.0).abs() < 0.001);
    }

    #[test]
    fn test_adjacency_mask_check() {
        let mut r = RegionState::new(0);
        r.adjacency = mask_to_ids(0b1010); // adjacent to regions 1 and 3
        assert_eq!(r.adjacency, vec![1, 3]);
        assert!(r.is_adjacent_to(1));
        assert!(r.is_adjacent_to(3));
        assert!(!r.is_adjacent_to(2));
    }

    #[test]
    fn test_terrain_discriminants_append_only() {
        assert_eq!(Terrain::Tundra as u8, 5);
        assert_eq!(Terrain::Steppe as u8, 6);
        assert_eq!(Terrain::Jungle as u8, 7);
        assert_eq!(Terrain::Marsh as u8, 8);
        for v in 0..9u8 {
            assert_eq!(Terrain::from_u8(v).map(|t| t as u8), Some(v));
        }
        assert!(Terrain::from_u8(9).is_none());
    }

    #[test]
    fn test_mask_to_ids_matches_bit_walk() {
        for mask in [0u32, 1, 0b1010, 0x8000_0001, u32::MAX, 0xDEAD_BEEF] {
            let walked: Vec<u16> = (0..32u16).filter(|b| mask & (1 << b) != 0).collect();
            assert_eq!(mask_to_ids(mask), walked);
        }
    }

    #[test]
    fn test_adjacency_list_beyond_32_regions() {
        let mut r = RegionState::new(0);
        r.adjacency = vec![199, 3, 64, 33, 3];
        normalize_ids(&mut r.adjacency);
        assert_eq!(r.adjacency, vec![3, 33, 64, 199]);
        assert!(r.is_adjacent_to(199));
        assert!(r.is_adjacent_to(33));
        assert!(!r.is_adjacent_to(32));
    }

    #[test]
    fn test_shares_river_matches_mask_intersection() {
        let masks = [0u32, 1, 2, 3, 0b1100, 0x8000_0000, 0x8000_0001, u32::MAX];
        for &a in &masks {
            for &b in &masks {
                let mut ra = RegionState::new(0);
                let mut rb = RegionState::new(1);
                ra.rivers = mask_to_ids(a);
                rb.rivers = mask_to_ids(b);
                assert_eq!(ra.shares_river(&rb), a & b != 0, "{a:#x} {b:#x}");
                assert_eq!(ra.has_river(), a != 0);
            }
        }
        let mut ra = RegionState::new(0);
        let mut rb = RegionState::new(1);
        ra.rivers = vec![5, 40, 77];
        rb.rivers = vec![6, 77];
        assert!(ra.shares_river(&rb));
        rb.rivers = vec![41, 78];
        assert!(!ra.shares_river(&rb));
    }

    #[test]
    fn test_region_new_has_m54a_ecology_defaults() {
        let r = RegionState::new(7);
        // Read-only ecology inputs
        assert!((r.disease_baseline - 0.0).abs() < f32::EPSILON);
        assert!((r.capacity_modifier - 1.0).abs() < f32::EPSILON);
        assert_eq!(r.resource_base_yield, [0.0, 0.0, 0.0]);
        assert_eq!(r.resource_effective_yield, [0.0, 0.0, 0.0]);
        assert_eq!(r.resource_suspension, [false, false, false]);
        assert!(!r.has_irrigation);
        assert!(!r.has_mines);
        assert_eq!(r.active_focus, 0);
        assert_eq!(r.catastrophe_deaths_this_turn, 0);
        // Rust-owned persistent state
        assert!((r.prev_turn_water - 0.0).abs() < f32::EPSILON);
        assert_eq!(r.soil_pressure_streak, 0);
        assert_eq!(r.overextraction_streak, [0, 0, 0]);
    }

    #[test]
    fn test_region_m54a_fields_mutable() {
        let mut r = RegionState::new(0);
        r.disease_baseline = 0.05;
        r.capacity_modifier = 0.85;
        r.resource_base_yield = [1.2, 0.8, 0.0];
        r.resource_effective_yield = [1.0, 0.6, 0.0];
        r.resource_suspension = [false, true, false];
        r.has_irrigation = true;
        r.has_mines = true;
        r.active_focus = 3;
        r.prev_turn_water = 0.55;
        r.soil_pressure_streak = 2;
        r.overextraction_streak = [0, 3, 0];
        assert!((r.disease_baseline - 0.05).abs() < f32::EPSILON);
        assert!(r.has_irrigation);
        assert_eq!(r.overextraction_streak[1], 3);
    }
}
