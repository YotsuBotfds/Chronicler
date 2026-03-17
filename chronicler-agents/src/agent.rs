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

// Utility-based decision model (M32) [CALIBRATE: M47]
// Three-tier calibration: 1) CAP ratios  2) DECISION_TEMPERATURE  3) Weights
pub const STAY_BASE: f32 = 0.5;
pub const REBEL_CAP: f32 = 1.5;
pub const MIGRATE_CAP: f32 = 1.0;
pub const SWITCH_CAP: f32 = 0.6;
pub const DECISION_TEMPERATURE: f32 = 0.3;
pub const W_REBEL: f32 = 3.75;
pub const W_MIGRATE_SAT: f32 = 1.67;
pub const W_MIGRATE_OPP: f32 = 1.67;
pub const W_SWITCH: f32 = 0.03;
pub const MIGRATE_HYSTERESIS: f32 = 0.05;
// Derived from Phase 5 constants for use in utility functions:
pub const SWITCH_OVERSUPPLY_THRESH: f32 = 1.0 / OCCUPATION_SWITCH_OVERSUPPLY; // 2.0
pub const SWITCH_UNDERSUPPLY_FACTOR: f32 = OCCUPATION_SWITCH_UNDERSUPPLY; // 1.5

// Personality multipliers (M33) [CALIBRATE: M47]
// Applied to utility outputs: modifier = (1.0 + dimension * WEIGHT).max(0.0)
pub const BOLD_REBEL_WEIGHT: f32 = 0.3;
pub const BOLD_MIGRATE_WEIGHT: f32 = 0.3;
pub const AMBITION_SWITCH_WEIGHT: f32 = 0.3;
pub const LOYALTY_TRAIT_WEIGHT: f32 = 0.3;
pub const SPAWN_PERSONALITY_NOISE: f32 = 0.3;
pub const BIRTH_PERSONALITY_NOISE: f32 = 0.15;
pub const PERSONALITY_LABEL_THRESHOLD: f32 = 0.5;

// RNG stream offsets — central registry to prevent collisions.
// Each system gets a range of 100 offsets. Stream for region r at turn t:
//   stream = r as u64 * 1000 + t as u64 + OFFSET
pub const DECISION_STREAM_OFFSET: u64     = 0;
pub const DEMOGRAPHICS_STREAM_OFFSET: u64 = 100;
pub const MIGRATION_STREAM_OFFSET: u64    = 200;
// Phase 6 additions (reserved, wired when systems land):
pub const CULTURE_DRIFT_OFFSET: u64       = 500;
pub const CONVERSION_STREAM_OFFSET: u64   = 600;
pub const PERSONALITY_STREAM_OFFSET: u64  = 700;
pub const GOODS_ALLOC_STREAM_OFFSET: u64  = 800;

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

// M36: Cultural identity
pub const IS_NAMED: u8 = 1 << 5;  // bit 5 of life_events

/// Number of cultural value enum variants (Freedom=0..Cunning=5).
pub const NUM_CULTURAL_VALUES: usize = 6;

/// Sentinel for empty cultural value slot.
pub const CULTURAL_VALUE_EMPTY: u8 = 0xFF;

// --- M36 cultural drift tuning constants ---
pub const CULTURAL_DRIFT_RATE: f32 = 0.06;
pub const DRIFT_SLOT_WEIGHTS: [f32; 3] = [1.0 / 3.0, 2.0 / 3.0, 1.0];
pub const CULTURAL_MISMATCH_WEIGHT: f32 = 0.05;
pub const PENALTY_CAP: f32 = 0.40;
pub const NAMED_CULTURE_WEIGHT: u16 = 5;
pub const ENV_BIAS_FRACTION: f32 = 0.05;
pub const ENV_SLOT_WEIGHTS: [f32; 3] = [1.0, 0.5, 0.25];
pub const DISSATISFIED_DRIFT_BONUS: f32 = 0.03;
pub const DISSATISFIED_THRESHOLD: f32 = 0.4;
pub const INVEST_CULTURE_BONUS: f32 = 0.10;

// M37: Religion constants
pub const LIFE_EVENT_CONVERSION: u8 = 1 << 6;  // bit 6 of life_events
pub const BELIEF_NONE: u8 = 0xFF;              // sentinel for no belief assigned
pub const RELIGIOUS_MISMATCH_WEIGHT: f32 = 0.10;
pub const SUSCEPTIBILITY_THRESHOLD: f32 = 0.4;  // satisfaction below this → 2× conversion
pub const SUSCEPTIBILITY_MULTIPLIER: f32 = 2.0;
pub const CONQUEST_CONVERSION_RATE: f32 = 0.30;  // forced flip probability

// M38b: Persecution
pub const PERSECUTION_SAT_WEIGHT: f32 = 0.15;
pub const PERSECUTION_REBEL_BOOST: f32 = 0.30;
pub const PERSECUTION_MIGRATE_BOOST: f32 = 0.20;

// Named character promotion thresholds (M30) [CALIBRATE: post-M28]
pub const PROMOTION_SKILL_THRESHOLD: f32 = 0.9;
pub const PROMOTION_DURATION_TURNS: u8 = 20;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_utility_constants_valid() {
        // CAP ordering: REBEL > MIGRATE > SWITCH > STAY
        assert!(REBEL_CAP > MIGRATE_CAP, "REBEL_CAP must exceed MIGRATE_CAP");
        assert!(MIGRATE_CAP > SWITCH_CAP, "MIGRATE_CAP must exceed SWITCH_CAP");
        assert!(SWITCH_CAP > STAY_BASE, "SWITCH_CAP must exceed STAY_BASE");

        // All CAPs and base must be positive
        assert!(REBEL_CAP > 0.0);
        assert!(MIGRATE_CAP > 0.0);
        assert!(SWITCH_CAP > 0.0);
        assert!(STAY_BASE > 0.0);

        // Temperature non-negative
        assert!(DECISION_TEMPERATURE >= 0.0);

        // Weights positive
        assert!(W_REBEL > 0.0);
        assert!(W_MIGRATE_SAT > 0.0);
        assert!(W_MIGRATE_OPP > 0.0);
        assert!(W_SWITCH > 0.0);

        // Hysteresis positive
        assert!(MIGRATE_HYSTERESIS > 0.0);
    }

    #[test]
    fn test_stream_offsets_no_collision() {
        let offsets = [
            DECISION_STREAM_OFFSET,
            DEMOGRAPHICS_STREAM_OFFSET,
            MIGRATION_STREAM_OFFSET,
            CULTURE_DRIFT_OFFSET,
            CONVERSION_STREAM_OFFSET,
            PERSONALITY_STREAM_OFFSET,
            GOODS_ALLOC_STREAM_OFFSET,
        ];
        // All offsets must be distinct
        for i in 0..offsets.len() {
            for j in (i + 1)..offsets.len() {
                assert_ne!(
                    offsets[i], offsets[j],
                    "Stream offset collision: index {} and {} both equal {}",
                    i, j, offsets[i]
                );
            }
        }
    }
}
