//! Rust-side mirror of Python Region ecology fields.
//! terrain stored as u8 — not used in M25 but present for M26 schema stability.

#[allow(dead_code)]
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Terrain {
    Plains = 0, Mountains = 1, Coast = 2, Forest = 3, Desert = 4, Tundra = 5,
}

#[allow(dead_code)]
impl Terrain {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v { 0 => Some(Self::Plains), 1 => Some(Self::Mountains), 2 => Some(Self::Coast), 3 => Some(Self::Forest), 4 => Some(Self::Desert), 5 => Some(Self::Tundra), _ => None }
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
    // M26 additions
    pub adjacency_mask: u32,     // bitmask: bit i = adjacent to region i (≤32 regions)
    pub controller_civ: u8,      // civ_id controlling region (255 = uncontrolled)
    pub trade_route_count: u8,
    // M34: Resource state
    pub resource_types: [u8; 3],
    pub resource_yields: [f32; 3],
    pub resource_reserves: [f32; 3],
    pub season: u8,
    pub season_id: u8,
    // M35a: River bitmask
    pub river_mask: u32,
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
    pub schism_convert_from: u8,
    pub schism_convert_to: u8,
    // M42: Goods economy signals
    pub farmer_income_modifier: f32,
    pub food_sufficiency: f32,
    pub merchant_margin: f32,
    pub merchant_trade_income: f32,
    // M48: Per-region transient memory signals (cleared each turn by build_region_batch)
    pub controller_changed_this_turn: bool,
    pub war_won_this_turn: bool,
    pub seceded_this_turn: bool,
}

impl RegionState {
    pub fn new(region_id: u16) -> Self {
        Self { region_id, terrain: Terrain::Plains as u8, carrying_capacity: 60, population: 0, soil: 0.8, water: 0.6, forest_cover: 0.3, adjacency_mask: 0, controller_civ: 255, trade_route_count: 0, resource_types: [255, 255, 255], resource_yields: [0.0, 0.0, 0.0], resource_reserves: [1.0, 1.0, 1.0], season: 0, season_id: 0, river_mask: 0, endemic_severity: 0.0, culture_investment_active: false, controller_values: [0xFF, 0xFF, 0xFF], conversion_rate: 0.0, conversion_target_belief: 0xFF, conquest_conversion_active: false, majority_belief: 0xFF, has_temple: false, persecution_intensity: 0.0, schism_convert_from: 0xFF, schism_convert_to: 0xFF, farmer_income_modifier: 1.0, food_sufficiency: 1.0, merchant_margin: 0.0, merchant_trade_income: 0.0, controller_changed_this_turn: false, war_won_this_turn: false, seceded_this_turn: false }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_region_new_has_m26_defaults() {
        let r = RegionState::new(5);
        assert_eq!(r.adjacency_mask, 0);
        assert_eq!(r.controller_civ, 255); // uncontrolled
        assert_eq!(r.trade_route_count, 0);
    }

    #[test]
    fn test_region_new_has_river_mask_default() {
        let r = RegionState::new(5);
        assert_eq!(r.river_mask, 0);
    }

    #[test]
    fn test_region_new_has_endemic_severity_default() {
        let r = RegionState::new(5);
        assert!((r.endemic_severity - 0.0).abs() < 0.001);
    }

    #[test]
    fn test_adjacency_mask_check() {
        let mut r = RegionState::new(0);
        r.adjacency_mask = 0b1010; // adjacent to regions 1 and 3
        assert!(r.adjacency_mask & (1 << 1) != 0);
        assert!(r.adjacency_mask & (1 << 3) != 0);
        assert!(r.adjacency_mask & (1 << 2) == 0);
    }
}
