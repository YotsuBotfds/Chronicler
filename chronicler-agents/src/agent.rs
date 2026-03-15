//! Agent field definitions and constants — no AoS Agent struct at runtime.
//! Fields are stored as struct-of-arrays in `AgentPool`.

/// Occupation types. repr(u8) for Arrow serialization and SoA storage.
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Occupation {
    Farmer = 0,
    Soldier = 1,
    Merchant = 2,
    Scholar = 3,
    Priest = 4,
}

impl Occupation {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Farmer),
            1 => Some(Self::Soldier),
            2 => Some(Self::Merchant),
            3 => Some(Self::Scholar),
            4 => Some(Self::Priest),
            _ => None,
        }
    }
}

pub const AGE_ADULT: u16 = 20;
pub const AGE_ELDER: u16 = 60;
pub const MORTALITY_YOUNG: f32 = 0.005;
pub const MORTALITY_ADULT: f32 = 0.01;
pub const MORTALITY_ELDER: f32 = 0.05;
pub const OCCUPATION_COUNT: usize = 5;
