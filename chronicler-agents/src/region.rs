//! Rust-side mirror of Python Region ecology fields.
//! terrain stored as u8 — not used in M25 but present for M26 schema stability.

#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Terrain {
    Plains = 0, Mountains = 1, Coast = 2, Forest = 3, Desert = 4, Tundra = 5,
}

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
}

impl RegionState {
    pub fn new(region_id: u16) -> Self {
        Self { region_id, terrain: Terrain::Plains as u8, carrying_capacity: 60, population: 0, soil: 0.8, water: 0.6, forest_cover: 0.3 }
    }
}
