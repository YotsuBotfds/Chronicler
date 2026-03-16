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
}

impl RegionState {
    pub fn new(region_id: u16) -> Self {
        Self { region_id, terrain: Terrain::Plains as u8, carrying_capacity: 60, population: 0, soil: 0.8, water: 0.6, forest_cover: 0.3, adjacency_mask: 0, controller_civ: 255, trade_route_count: 0, resource_types: [255, 255, 255], resource_yields: [0.0, 0.0, 0.0], resource_reserves: [1.0, 1.0, 1.0], season: 0, season_id: 0 }
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
    fn test_adjacency_mask_check() {
        let mut r = RegionState::new(0);
        r.adjacency_mask = 0b1010; // adjacent to regions 1 and 3
        assert!(r.adjacency_mask & (1 << 1) != 0);
        assert!(r.adjacency_mask & (1 << 3) != 0);
        assert!(r.adjacency_mask & (1 << 2) == 0);
    }
}
