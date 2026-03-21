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
pub const MORTALITY_ADULT: f32 = 0.005;  // M53: was 0.01 (B+C combined fix)
pub const MORTALITY_ELDER: f32 = 0.03;  // M53: was 0.05 (B+C+D combined fix)
pub const OCCUPATION_COUNT: usize = 5;

pub const MAX_CIVS: usize = 255;
const _: () = assert!(MAX_CIVS <= u8::MAX as usize);

// Fertility
pub const FERTILITY_AGE_MIN: u16 = 16;
pub const FERTILITY_FULL_AGE_MAX: u16 = 50;   // M53: full fertility up to this age
pub const FERTILITY_TAPER_AGE_MAX: u16 = 60;  // M53: linear taper to zero by this age
pub const FERTILITY_BASE_FARMER: f32 = 0.05;   // M53: was 0.03 (B+C combined fix)
pub const FERTILITY_BASE_OTHER: f32 = 0.03;    // M53: was 0.015 (B+C combined fix)
pub const FERTILITY_SATISFACTION_THRESHOLD: f32 = 0.3;  // [CALIBRATE] M47c: 0.4→0.3 (wars pushing satisfaction below threshold killed all births)

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
// M48: Memory system (reserved, not consumed in M48 — deterministic writes)
pub const MEMORY_STREAM_OFFSET: u64 = 900;
// M48: Mule promotion (reserved for Rust, but M48 uses Python-side RNG)
pub const MULE_STREAM_OFFSET: u64 = 1300;
// M50 — Relationship formation / dissolution (not consumed in M50a)
pub const RELATIONSHIP_STREAM_OFFSET: u64 = 1100;
// M53: Initial age seeding (one-time spawn path only)
pub const INITIAL_AGE_STREAM_OFFSET: u64 = 1400;

// Skill
pub const SKILL_RESET_ON_SWITCH: f32 = 0.3;
pub const SKILL_GROWTH_PER_TURN: f32 = 0.05;
pub const SKILL_MAX: f32 = 1.0;
pub const SKILL_NEWBORN: f32 = 0.1;

// War
pub const WAR_CASUALTY_MULTIPLIER: f32 = 2.0;

// Disease — multiplicative scale: mortality *= (1 + endemic_severity * SCALE)
// At baseline (0.01): 1.1x. At cap (0.15): 2.5x.
pub const DISEASE_MORTALITY_SCALE: f32 = 10.0;  // [CALIBRATE M53]

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
pub const RELIGIOUS_MISMATCH_WEIGHT: f32 = 0.05;  // [CALIBRATE] M47c: 0.10→0.05 (diverse beliefs at T1 hit too hard)
pub const SUSCEPTIBILITY_THRESHOLD: f32 = 0.4;  // satisfaction below this → 2× conversion
pub const SUSCEPTIBILITY_MULTIPLIER: f32 = 2.0;
pub const CONQUEST_CONVERSION_RATE: f32 = 0.30;  // forced flip probability

// M38b: Persecution
pub const PERSECUTION_SAT_WEIGHT: f32 = 0.15;
pub const PERSECUTION_REBEL_BOOST: f32 = 0.30;
pub const PERSECUTION_MIGRATE_BOOST: f32 = 0.20;

// M39: Parentage
pub const PARENT_NONE: u32 = 0;                 // sentinel for no parent

// M41: Wealth & Class Stratification
pub const STARTING_WEALTH: f32 = 0.5;       // [CALIBRATE] initial wealth for all agents
pub const MAX_WEALTH: f32 = 100.0;          // [CALIBRATE] wealth ceiling
pub const WEALTH_DECAY: f32 = 0.02;         // [CALIBRATE] multiplicative decay per tick
pub const BASE_FARMER_INCOME: f32 = 0.30;  // [CALIBRATE] M42: replaces FARMER_INCOME + MINER_INCOME
pub const SOLDIER_INCOME: f32 = 0.15;       // [CALIBRATE] low peacetime base
pub const AT_WAR_BONUS: f32 = 1.0;          // [CALIBRATE] doubles soldier income at war
pub const CONQUEST_BONUS: f32 = 3.0;        // [CALIBRATE] one-shot wealth spike on conquest
// MERCHANT_INCOME and MERCHANT_BASELINE removed — M42 replaces with merchant_trade_income signal
pub const SCHOLAR_INCOME: f32 = 0.20;       // [CALIBRATE] equilibrium ~10
pub const PRIEST_INCOME: f32 = 0.20;        // [CALIBRATE] equilibrium ~10; M42 adds tithe
pub const CLASS_TENSION_WEIGHT: f32 = 0.15; // [CALIBRATE] max penalty for poorest at Gini=1.0

// Named character promotion thresholds (M30) [CALIBRATE: post-M28]
pub const PROMOTION_SKILL_THRESHOLD: f32 = 0.9;
pub const PROMOTION_DURATION_TURNS: u8 = 20;

// M48: Memory event default intensities [CALIBRATE M53]
pub const FAMINE_DEFAULT_INTENSITY: i8 = -80;        // [CALIBRATE M53]
pub const BATTLE_DEFAULT_INTENSITY: i8 = -60;         // [CALIBRATE M53]
pub const CONQUEST_DEFAULT_INTENSITY: i8 = -70;       // [CALIBRATE M53]
pub const PERSECUTION_DEFAULT_INTENSITY: i8 = -90;    // [CALIBRATE M53]
pub const MIGRATION_DEFAULT_INTENSITY: i8 = -30;      // [CALIBRATE M53]
pub const PROSPERITY_DEFAULT_INTENSITY: i8 = 50;      // [CALIBRATE M53]
pub const VICTORY_DEFAULT_INTENSITY: i8 = 60;         // [CALIBRATE M53]
pub const PROMOTION_DEFAULT_INTENSITY: i8 = 70;       // [CALIBRATE M53]
pub const BIRTHOFKIN_DEFAULT_INTENSITY: i8 = 40;      // [CALIBRATE M53]
pub const DEATHOFKIN_DEFAULT_INTENSITY: i8 = -80;     // [CALIBRATE M53]
pub const CONVERSION_DEFAULT_INTENSITY: i8 = 50;      // [CALIBRATE M53]
pub const SECESSION_DEFAULT_INTENSITY: i8 = -60;      // [CALIBRATE M53]

// M48: Memory event default half-lives in turns [CALIBRATE M53]
pub const FAMINE_HALF_LIFE: f32 = 40.0;              // [CALIBRATE M53]
pub const BATTLE_HALF_LIFE: f32 = 25.0;              // [CALIBRATE M53]
pub const CONQUEST_HALF_LIFE: f32 = 30.0;            // [CALIBRATE M53]
pub const PERSECUTION_HALF_LIFE: f32 = 50.0;         // [CALIBRATE M53]
pub const MIGRATION_HALF_LIFE: f32 = 15.0;           // [CALIBRATE M53]
pub const PROSPERITY_HALF_LIFE: f32 = 20.0;          // [CALIBRATE M53]
pub const VICTORY_HALF_LIFE: f32 = 20.0;             // [CALIBRATE M53]
pub const PROMOTION_HALF_LIFE: f32 = 30.0;           // [CALIBRATE M53]
pub const BIRTHOFKIN_HALF_LIFE: f32 = 25.0;          // [CALIBRATE M53]
pub const DEATHOFKIN_HALF_LIFE: f32 = 35.0;          // [CALIBRATE M53]
pub const CONVERSION_HALF_LIFE: f32 = 20.0;          // [CALIBRATE M53]
pub const SECESSION_HALF_LIFE: f32 = 20.0;           // [CALIBRATE M53]
pub const LEGACY_HALF_LIFE: f32 = 100.0;             // [CALIBRATE M53]
pub const LEGACY_MIN_INTENSITY: i8 = 10;   // [CALIBRATE M53] post-halving threshold
pub const LEGACY_MAX_MEMORIES: usize = 2;  // [CALIBRATE M53] top-N extracted on death

// M48: Memory behavioral constants [CALIBRATE M53]
pub const MEMORY_SATISFACTION_WEIGHT: f32 = 0.12;    // [CALIBRATE M53]
pub const FAMINE_MEMORY_THRESHOLD: f32 = 0.6;        // [CALIBRATE M53]
pub const PROSPERITY_THRESHOLD: f32 = 3.0;           // [CALIBRATE M53]

// M48: Memory utility modifier magnitudes [CALIBRATE M53]
pub const FAMINE_MIGRATE_BOOST: f32 = 0.2;                    // [CALIBRATE M53]
pub const BATTLE_BOLD_STAY_BOOST: f32 = 0.1;                  // [CALIBRATE M53]
pub const BATTLE_CAUTIOUS_MIGRATE_BOOST: f32 = 0.15;          // [CALIBRATE M53]
pub const CONQUEST_CONQUERED_MIGRATE_BOOST: f32 = 0.3;        // [CALIBRATE M53]
pub const CONQUEST_CONQUEROR_STAY_BOOST: f32 = 0.1;           // [CALIBRATE M53]
pub const PERSECUTION_REBEL_BOOST_MEMORY: f32 = 0.15;         // [CALIBRATE M53]
pub const PERSECUTION_MIGRATE_BOOST_MEMORY: f32 = 0.2;        // [CALIBRATE M53]
pub const PROSPERITY_MIGRATE_PENALTY: f32 = 0.2;              // [CALIBRATE M53]
pub const PROSPERITY_SWITCH_PENALTY: f32 = 0.1;               // [CALIBRATE M53]
pub const VICTORY_STAY_BOOST: f32 = 0.1;                      // [CALIBRATE M53]
pub const DEATHOFKIN_MIGRATE_PENALTY: f32 = 0.15;             // [CALIBRATE M53]

// M49: Needs system — starting value
pub const STARTING_NEED: f32 = 0.5;  // [CALIBRATE M53]

// M49: Need decay rates [CALIBRATE M53]
pub const SAFETY_DECAY: f32 = 0.015;     // [CALIBRATE M53]
pub const MATERIAL_DECAY: f32 = 0.012;   // [CALIBRATE M53]
pub const SOCIAL_DECAY: f32 = 0.008;     // [CALIBRATE M53]
pub const SPIRITUAL_DECAY: f32 = 0.010;  // [CALIBRATE M53]
pub const AUTONOMY_DECAY: f32 = 0.015;   // [CALIBRATE M53]
pub const PURPOSE_DECAY: f32 = 0.012;    // [CALIBRATE M53]

// M49: Need behavioral thresholds [CALIBRATE M53]
pub const SAFETY_THRESHOLD: f32 = 0.3;    // [CALIBRATE M53]
pub const MATERIAL_THRESHOLD: f32 = 0.3;  // [CALIBRATE M53]
pub const SOCIAL_THRESHOLD: f32 = 0.25;   // [CALIBRATE M53]
pub const SPIRITUAL_THRESHOLD: f32 = 0.3; // [CALIBRATE M53]
pub const AUTONOMY_THRESHOLD: f32 = 0.3;  // [CALIBRATE M53]
pub const PURPOSE_THRESHOLD: f32 = 0.35;  // [CALIBRATE M53]

// M49: Need behavioral weights [CALIBRATE M53]
pub const SAFETY_WEIGHT: f32 = 0.7;     // [CALIBRATE M53]
pub const MATERIAL_WEIGHT: f32 = 0.5;   // [CALIBRATE M53]
pub const SOCIAL_WEIGHT: f32 = 0.5;     // [CALIBRATE M53]
pub const SPIRITUAL_WEIGHT: f32 = 0.4;  // [CALIBRATE M53]
pub const AUTONOMY_WEIGHT: f32 = 0.8;   // [CALIBRATE M53]
pub const PURPOSE_WEIGHT: f32 = 0.4;    // [CALIBRATE M53]

// M49: Restoration rates [CALIBRATE M53]
pub const SAFETY_RESTORE_PEACE: f32 = 0.020;          // [CALIBRATE M53]
pub const SAFETY_RESTORE_HEALTH: f32 = 0.010;         // [CALIBRATE M53]
pub const SAFETY_RESTORE_FOOD: f32 = 0.008;           // [CALIBRATE M53]
pub const BOLD_SAFETY_RESTORE_WEIGHT: f32 = 0.3;      // [CALIBRATE M53]
pub const MATERIAL_RESTORE_FOOD: f32 = 0.012;         // [CALIBRATE M53]
pub const MATERIAL_RESTORE_WEALTH: f32 = 0.015;       // [CALIBRATE M53]
pub const SOCIAL_RESTORE_POP: f32 = 0.010;            // [CALIBRATE M53]
pub const SOCIAL_RESTORE_POP_THRESHOLD: f32 = 0.3;    // [CALIBRATE M53]
pub const SOCIAL_MERCHANT_MULT: f32 = 1.5;            // [CALIBRATE M53]
pub const SOCIAL_PRIEST_MULT: f32 = 1.3;              // [CALIBRATE M53]
pub const SPIRITUAL_RESTORE_TEMPLE: f32 = 0.020;      // [CALIBRATE M53]
pub const SPIRITUAL_RESTORE_MATCH: f32 = 0.015;       // [CALIBRATE M53]
pub const AUTONOMY_RESTORE_SELF_GOV: f32 = 0.020;     // [CALIBRATE M53]
pub const AUTONOMY_RESTORE_NO_PERSC: f32 = 0.010;     // [CALIBRATE M53]
pub const PURPOSE_RESTORE_SKILL: f32 = 0.020;         // [CALIBRATE M53]
pub const PURPOSE_RESTORE_WAR: f32 = 0.015;           // [CALIBRATE M53]

// M49: Infrastructure constants [CALIBRATE M53]
pub const NEEDS_MODIFIER_CAP: f32 = 0.30;    // [CALIBRATE M53]
pub const AUTONOMY_DRIFT_WEIGHT: f32 = 2.0;  // [CALIBRATE M53]

// ── M50a: Relationship Substrate ──────────────────────────────────────────────
// Kin auto-formation initial sentiments
pub const KIN_INITIAL_PARENT: i8 = 60;   // [CALIBRATE M53] parent→child
pub const KIN_INITIAL_CHILD: i8 = 40;    // [CALIBRATE M53] child→parent

// Sentiment drift — co-located bonds
pub const POSITIVE_COLOC_DRIFT: i16 = 1;           // [CALIBRATE M53] per-tick positive drift
pub const NEGATIVE_COLOC_DRIFT: i16 = 1;           // [CALIBRATE M53] per-tick negative deepening
pub const STRONG_TIE_THRESHOLD: i16 = 100;         // [CALIBRATE M53] cadence kicks in above this
pub const STRONG_TIE_CADENCE: u16 = 2;             // [CALIBRATE M53] drift every N ticks above threshold

// Sentiment drift — separation decay
pub const POSITIVE_SEPARATION_DECAY: i16 = 1;      // [CALIBRATE M53] per-tick positive decay
pub const NEGATIVE_DECAY_CADENCE: u16 = 4;         // [CALIBRATE M53] ticks between negative decay steps

// M50b: Formation constants [CALIBRATE M53]
pub const FORMATION_CADENCE: u32 = 6;  // [CALIBRATE M53]

// Similarity weights
pub const W_CULTURE: f32 = 0.35;     // [CALIBRATE M53]
pub const W_BELIEF: f32 = 0.35;      // [CALIBRATE M53]
pub const W_OCCUPATION: f32 = 0.15;  // [CALIBRATE M53]
pub const W_AFFINITY: f32 = 0.15;    // [CALIBRATE M53]

// Rank crossing
pub const SAME_RANK_WEIGHT: f32 = 1.0;  // [CALIBRATE M53]
pub const CROSS_RANK_WEIGHT: f32 = 0.5; // [CALIBRATE M53]

// Friend bond
pub const FRIEND_THRESHOLD: f32 = 0.50;        // [CALIBRATE M53]
pub const FRIEND_INITIAL_SENTIMENT: i8 = 30;   // [CALIBRATE M53]

// Minority coreligionist bond
pub const MINORITY_THRESHOLD: f32 = 0.40;              // [CALIBRATE M53]
pub const CORELIGIONIST_INITIAL_SENTIMENT: i8 = 25;    // [CALIBRATE M53]

// Rival bond
pub const RIVAL_WEALTH_PROXIMITY: f32 = 50.0;  // [CALIBRATE M53]
pub const RIVAL_SIMILARITY_FLOOR: f32 = 0.30;  // [CALIBRATE M53]
pub const RIVAL_MIN_AMBITION: f32 = 0.50;      // [CALIBRATE M53]
pub const RIVAL_INITIAL_SENTIMENT: i8 = -20;   // [CALIBRATE M53]

// Mentor bond
pub const MENTOR_AGE_GAP: u16 = 15;            // [CALIBRATE M53]
pub const MENTOR_INITIAL_SENTIMENT: i8 = 35;   // [CALIBRATE M53]

// Grudge bond
pub const GRUDGE_INITIAL_SENTIMENT: i8 = -30;  // [CALIBRATE M53]

// Exile solidarity bond
pub const EXILE_INITIAL_SENTIMENT: i8 = 35;    // [CALIBRATE M53]

// Triadic closure
pub const TRIADIC_MIN_SENTIMENT: i8 = 40;              // [CALIBRATE M53]
pub const TRIADIC_THRESHOLD_REDUCTION: f32 = 0.15;    // [CALIBRATE M53]

// Formation scan limits
pub const MAX_NEW_BONDS_PER_PASS: u8 = 2;       // [CALIBRATE M53]
pub const MAX_NEW_BONDS_PER_REGION: u32 = 50;   // [CALIBRATE M53]

// Social-need blend
pub const SOCIAL_BLEND_ALPHA: f32 = 0.0;     // [CALIBRATE M53]
pub const SOCIAL_RESTORE_BOND: f32 = 0.010;  // [CALIBRATE M53]
pub const SOCIAL_BOND_TARGET: f32 = 4.0;     // [CALIBRATE M53]

// Synthesis budget
pub const SYNTHESIS_BUDGET_MAX: u8 = 100;  // [CALIBRATE M53]

// Life-event dissolution cadence
pub const LIFE_EVENT_DISSOLUTION: u8 = 6;  // [CALIBRATE M53]

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
    fn test_wealth_equilibrium_farmer() {
        // At yield=1.0, modifier=1.0: equilibrium = BASE_FARMER_INCOME / WEALTH_DECAY
        let eq = BASE_FARMER_INCOME / WEALTH_DECAY;
        assert!(eq > 5.0 && eq < 50.0, "Farmer equilibrium {eq} out of range");
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
            MEMORY_STREAM_OFFSET,
            MULE_STREAM_OFFSET,
            RELATIONSHIP_STREAM_OFFSET,
            INITIAL_AGE_STREAM_OFFSET,
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
