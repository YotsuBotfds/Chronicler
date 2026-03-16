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

pub const MAX_CIVS: usize = 255;
const _: () = assert!(MAX_CIVS <= u8::MAX as usize);

// Fertility
pub const FERTILITY_AGE_MIN: u16 = 16;
pub const FERTILITY_AGE_MAX: u16 = 45;
pub const FERTILITY_BASE_FARMER: f32 = 0.03;
pub const FERTILITY_BASE_OTHER: f32 = 0.015;
pub const FERTILITY_SATISFACTION_THRESHOLD: f32 = 0.4;

// Decision thresholds
pub const REBEL_LOYALTY_THRESHOLD: f32 = 0.2;
pub const REBEL_SATISFACTION_THRESHOLD: f32 = 0.2;
pub const REBEL_MIN_COHORT: usize = 5;
pub const MIGRATE_SATISFACTION_THRESHOLD: f32 = 0.3;
pub const OCCUPATION_SWITCH_UNDERSUPPLY: f32 = 1.5;
pub const OCCUPATION_SWITCH_OVERSUPPLY: f32 = 0.5;
pub const LOYALTY_DRIFT_RATE: f32 = 0.02;
pub const LOYALTY_RECOVERY_RATE: f32 = 0.01;
pub const LOYALTY_FLIP_THRESHOLD: f32 = 0.3;

// Skill
pub const SKILL_RESET_ON_SWITCH: f32 = 0.3;
pub const SKILL_GROWTH_PER_TURN: f32 = 0.05;
pub const SKILL_MAX: f32 = 1.0;
pub const SKILL_NEWBORN: f32 = 0.1;

// War
pub const WAR_CASUALTY_MULTIPLIER: f32 = 2.0;

// Life-event bitflags for named character promotion (M30)
pub const LIFE_EVENT_REBELLION: u8     = 1 << 0;
pub const LIFE_EVENT_MIGRATION: u8     = 1 << 1;
pub const LIFE_EVENT_WAR_SURVIVAL: u8  = 1 << 2;
pub const LIFE_EVENT_LOYALTY_FLIP: u8  = 1 << 3;
pub const LIFE_EVENT_OCC_SWITCH: u8    = 1 << 4;

// Named character promotion thresholds (M30) [CALIBRATE: post-M28]
pub const PROMOTION_SKILL_THRESHOLD: f32 = 0.9;
pub const PROMOTION_DURATION_TURNS: u8 = 20;
