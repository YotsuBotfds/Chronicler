//! Agent movements: membership, founding seeds, recruitment, spread and the
//! per-agent effects of movement outcomes.
//!
//! Python (`chronicler.agent_movements`) decides where movements are founded
//! and what happens to them (demands, reforms, crackdowns, risings, schisms,
//! secession). This pass moves people: who joins and who leaves, and what a
//! decided outcome does to the members on the next tick. It runs only after
//! Python has set a movement table (`MovementRuntime::enabled`); a world with
//! the switch off never calls it, draws nothing and keeps every member id 0.
//!
//! Identity: `pool.movement_ids[slot]` is 0 (none) or the movement's index in
//! the Python movement list + 1. Spec: docs/integration/agent-movements.md.

use std::collections::HashMap;
use std::sync::Arc;

use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

use crate::agent;
use crate::memory::{MemoryEventType, MemoryIntent};
use crate::pool::AgentPool;
use crate::region::RegionState;

// ---------------------------------------------------------------------------
// Declaration orders (append-only; Python `agent_movements_state` mirrors them)
// ---------------------------------------------------------------------------

/// Creeds: the grievance a movement carries.
pub const CREED_COMMONS: u8 = 0; // material need
pub const CREED_LIBERTY: u8 = 1; // autonomy need
pub const CREED_SECT: u8 = 2; // spiritual need
/// Creeds whose grievance is a need (the census counts these).
pub const CREED_COUNT: usize = 3;
/// Guilds (`--guilds`): a city's guild defending its privileges. Its people
/// are the civilian adult residents of one city (`MovementRow.settlement`);
/// Python founds it when the privileges are threatened, never from the census.
pub const CREED_GUILD: u8 = 3;

/// Stages sent in the table (an ended movement is not sent).
pub const STAGE_GATHERING: u8 = 0;
pub const STAGE_PRESSING: u8 = 1;
pub const STAGE_SUPPRESSED: u8 = 2;
pub const STAGE_RISING: u8 = 3;
pub const STAGE_SATISFIED: u8 = 4;

pub const NO_REGION: u16 = u16::MAX;
pub const NO_FAITH: u8 = 255;
pub const NO_RELIEF: u16 = u16::MAX;

// ---------------------------------------------------------------------------
// Parameters ([CALIBRATE]; documented in docs/integration/agent-movements.md)
// ---------------------------------------------------------------------------

/// Members and recruits are adults.
pub const ADULT_AGE: u16 = 16;
/// Aggrieved: satisfaction below this and the creed's need below its threshold.
/// Needs calibration (2026-10) moved material and autonomy: material 0.55 ->
/// 0.45 (the fed poorest settle at 0.56, a dearth's median at 0.44) and
/// autonomy 0.60 -> 0.50 (foreign rule settles at 0.61, persecution, martial
/// law and conquest well below); both stay above the behaviour thresholds
/// (0.30, 0.35). Spiritual is unchanged.
pub const GRIEVANCE_SAT: f32 = 0.45;
pub const GRIEVANCE_NEED: [f32; CREED_COUNT] = [0.45, 0.50, 0.45];

/// Founding seeds: this share of the region's adults, at least FOUND_MIN.
pub const FOUND_SHARE: f32 = 0.15;
pub const FOUND_MIN: usize = 3;

/// Recruitment: p = RATE x appeal x (0.5 + 0.5 g) x exposure x boldness x
/// loyalty x stage.
pub const RECRUIT_RATE: f32 = 0.25;
pub const RECRUIT_CAP: f32 = 0.5;
pub const BOND_WEIGHT: f32 = 1.0; // member bonds, two count fully
pub const BOND_FULL: f32 = 2.0;
pub const RESIDENCE_WEIGHT: f32 = 1.0; // members' share of the region's adults
pub const URBAN_WEIGHT: f32 = 1.0; // members' share of the agent's settlement
pub const BOLD_RECRUIT_WEIGHT: f32 = 0.5;
pub const SUPPRESSED_RECRUIT: f32 = 0.5;
pub const RISING_RECRUIT: f32 = 1.5;

/// Lapse chances per tick (combined). A member is content (and may lapse)
/// once its satisfaction or its creed need is LAPSE_MARGIN above the
/// grievance thresholds: membership has hysteresis.
pub const LAPSE_SATISFIED: f32 = 0.10;
pub const LAPSE_CONTENT: f32 = 0.04;
pub const LAPSE_MARGIN: f32 = 0.10;
pub const LAPSE_ABROAD: f32 = 0.10;
pub const LAPSE_FEAR: f32 = 0.5; // timid members (boldness < 0) in a crackdown region

/// Reform relief: the creed need regains this share of its deficit on the
/// first tick; satisfaction gains RELIEF_SAT, falling to 0 over RELIEF_TURNS.
pub const RELIEF_NEED: f32 = 0.5;
pub const RELIEF_SAT: f32 = 0.08;
pub const RELIEF_TURNS: u16 = 20;

/// Rebel utility of a member in the stronghold of a rising.
pub const RISING_REBEL_BOOST: f32 = 0.4;

/// Lasting reforms: an agent a reform in force covers reads its creed need
/// as `need + REFORM_NEED_CREDIT x (1 - need)` for grievance and commitment
/// (the institution answers part of the want; deep want stays aggrieved).
pub const REFORM_NEED_CREDIT: f32 = 0.3;

/// Guild creed: a civilian adult resident of the guild's city with
/// satisfaction (read with a guild charter's credit) below GUILD_SAT is
/// aggrieved, with intensity 0.5 + 0.5 x the normalized deficit.
pub const GUILD_SAT: f32 = 0.65;

/// Movement news (`knowledge::movement_news_for_creed`): news of a like
/// movement's founding, rising or reform elsewhere raises the chance to join
/// by up to NEWS_JOIN (x strength); news of a crackdown lowers it by up to
/// NEWS_FEAR. Without news the factor is not applied.
pub const NEWS_JOIN: f32 = 1.0;
pub const NEWS_FEAR: f32 = 0.5;

// RNG streams (registry in agent.rs).
pub use crate::agent::{MOVEMENT_LAPSE_STREAM_OFFSET, MOVEMENT_RECRUIT_STREAM_OFFSET};

// ---------------------------------------------------------------------------
// Runtime
// ---------------------------------------------------------------------------

/// One living movement as Python sends it each tick. The one-shot fields
/// (founding, relief, crackdown, rising, conversion) are cleared after the
/// tick consumes them.
#[derive(Debug, Clone)]
pub struct MovementRow {
    pub movement_id: u16,
    pub creed: u8,
    pub stage: u8,
    pub target_civ: u8,
    pub appeal: f32,
    pub found_region: u16,
    pub founder_id: u32,
    /// Turns since the reform was granted (1 on the first tick), NO_RELIEF none.
    pub relief_age: u16,
    pub crackdown_region: u16,
    pub rising_region: u16,
    pub convert_from: u8,
    pub convert_to: u8,
    /// Guild creed: the settlement id of the guild's city (0 otherwise;
    /// optional table column `settlement`).
    pub settlement: u16,
}

impl MovementRow {
    pub fn new(movement_id: u16, creed: u8, stage: u8, target_civ: u8) -> Self {
        Self {
            movement_id,
            creed,
            stage,
            target_civ,
            appeal: 1.0,
            found_region: NO_REGION,
            founder_id: 0,
            relief_age: NO_RELIEF,
            crackdown_region: NO_REGION,
            rising_region: NO_REGION,
            convert_from: NO_FAITH,
            convert_to: NO_FAITH,
            settlement: 0,
        }
    }

    fn clear_one_shots(&mut self) {
        self.found_region = NO_REGION;
        self.founder_id = 0;
        self.relief_age = NO_RELIEF;
        self.crackdown_region = NO_REGION;
        self.rising_region = NO_REGION;
        self.convert_from = NO_FAITH;
        self.convert_to = NO_FAITH;
    }
}

/// One lasting reform in force, as Python sends it each tick (one row per
/// covered region, or `region` NO_REGION for the whole realm of `civ`;
/// `faith` NO_FAITH for every believer). Standing state, rebuilt from the
/// persisted reforms every tick, not a one-shot.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ReformRow {
    pub creed: u8,
    pub civ: u8,
    pub region: u16,
    pub faith: u8,
}

/// Members to re-seed in a region (a resumed world whose native pool was
/// rebuilt from region populations). Consumed by the next tick.
#[derive(Debug, Clone)]
pub struct MovementSeed {
    pub movement_id: u16,
    pub region: u16,
    pub count: u32,
}

/// What the last pass observed: per region the adults and the aggrieved per
/// creed (before any change); per row the members after the pass and the
/// joins, lapses and founding seeds.
#[derive(Debug, Clone, Default)]
pub struct MovementStats {
    pub adults: Vec<u32>,
    pub aggrieved: Vec<[u32; CREED_COUNT]>,
    /// Per region and creed, the aggrieved holding inspiring news of a like
    /// movement elsewhere (guilds' movement news; all 0 without news).
    pub informed: Vec<[u32; CREED_COUNT]>,
    pub movement_ids: Vec<u16>,
    pub members: Vec<u32>,
    pub joined: Vec<u32>,
    pub lapsed: Vec<u32>,
    pub founded: Vec<u32>,
    pub released: u32,
}

#[derive(Debug, Clone, Default)]
pub struct MovementRuntime {
    /// Set by the first `set_movement_table`; the pass never runs before.
    pub enabled: bool,
    pub rows: Vec<MovementRow>,
    pub seeds: Vec<MovementSeed>,
    pub stats: MovementStats,
    /// Lasting reforms in force (`set_movement_reforms`).
    pub reforms: Vec<ReformRow>,
    /// Per region, the (creed, faith) the reforms cover there, derived from
    /// `reforms` and the controllers by the last pass for its census.
    pub cover: Vec<Vec<(u8, u8)>>,
}

/// Per-agent effects for the later tick steps. Empty vectors mean none.
#[derive(Debug, Default)]
pub struct MovementEffects {
    /// Satisfaction added after step 1 (reform relief), per slot.
    pub relief: Vec<f32>,
    /// Rebel utility added in step 3 (a rising), per slot.
    pub rebel_boost: Vec<f32>,
    /// Crackdown persecution memories, written with the tick's other intents.
    pub memory_intents: Vec<MemoryIntent>,
}

// ---------------------------------------------------------------------------
// Grievance
// ---------------------------------------------------------------------------

/// Grievance intensity of an agent for a creed: 0 unless it is an adult whose
/// satisfaction is below GRIEVANCE_SAT and whose creed need is below its
/// threshold; else the mean of the two normalized deficits (0..1].
#[inline]
pub fn grievance(pool: &AgentPool, slot: usize, creed: u8) -> f32 {
    grievance_credited(pool, slot, creed, 0.0)
}

/// The creed's need of an agent, read with a reform's credit (0 none).
#[inline]
fn creed_need(pool: &AgentPool, slot: usize, creed: u8, credit: f32) -> Option<f32> {
    let need = match creed {
        CREED_COMMONS => pool.need_material[slot],
        CREED_LIBERTY => pool.need_autonomy[slot],
        CREED_SECT => pool.need_spiritual[slot],
        _ => return None,
    };
    Some(if credit > 0.0 { need + credit * (1.0 - need) } else { need })
}

/// [`grievance`] for an agent a lasting reform covers (`credit`, 0 none).
#[inline]
pub fn grievance_credited(pool: &AgentPool, slot: usize, creed: u8, credit: f32) -> f32 {
    if pool.ages[slot] < ADULT_AGE {
        return 0.0;
    }
    let sat = pool.satisfactions[slot];
    if sat >= GRIEVANCE_SAT {
        return 0.0;
    }
    let Some(need) = creed_need(pool, slot, creed, credit) else {
        return 0.0;
    };
    let threshold = GRIEVANCE_NEED[creed as usize];
    if need >= threshold {
        return 0.0;
    }
    0.5 * (GRIEVANCE_SAT - sat) / GRIEVANCE_SAT + 0.5 * (threshold - need) / threshold
}

/// Whether a member is still committed to its creed: satisfaction and the
/// creed need within LAPSE_MARGIN of the grievance thresholds.
#[inline]
pub fn committed(pool: &AgentPool, slot: usize, creed: u8) -> bool {
    committed_credited(pool, slot, creed, 0.0)
}

/// [`committed`] for an agent a lasting reform covers (`credit`, 0 none).
#[inline]
pub fn committed_credited(pool: &AgentPool, slot: usize, creed: u8, credit: f32) -> bool {
    let Some(need) = creed_need(pool, slot, creed, credit) else {
        return false;
    };
    pool.satisfactions[slot] < GRIEVANCE_SAT + LAPSE_MARGIN
        && need < GRIEVANCE_NEED[creed as usize] + LAPSE_MARGIN
}

/// Per region, the (creed, faith) the reforms in force cover: a row covers
/// the regions its civ controls (all of them, or its own region).
pub fn reform_cover(reforms: &[ReformRow], regions: &[RegionState]) -> Vec<Vec<(u8, u8)>> {
    let mut cover = vec![Vec::new(); regions.len()];
    for row in reforms {
        if row.civ == 255 {
            continue;
        }
        for (r, region) in regions.iter().enumerate() {
            if region.controller_civ == row.civ && (row.region == NO_REGION || row.region as usize == r) {
                cover[r].push((row.creed, row.faith));
            }
        }
    }
    cover
}

/// The reform credit an agent has for a creed: REFORM_NEED_CREDIT when a
/// reform covers its region, creed and faith, else 0.
#[inline]
pub fn reform_credit(cover: &[Vec<(u8, u8)>], pool: &AgentPool, slot: usize, creed: u8) -> f32 {
    match cover.get(pool.regions[slot] as usize) {
        Some(list)
            if list
                .iter()
                .any(|&(c, f)| c == creed && (f == NO_FAITH || f == pool.beliefs[slot])) =>
        {
            REFORM_NEED_CREDIT
        }
        _ => 0.0,
    }
}

/// Guild creed grievance of an agent for the guild of `settlement` (`credit`:
/// a guild charter in force there).
#[inline]
pub fn guild_grievance(pool: &AgentPool, slot: usize, settlement: u16, credit: f32) -> f32 {
    if settlement == 0
        || pool.settlement_ids[slot] != settlement
        || pool.ages[slot] < ADULT_AGE
        || pool.occupations[slot] == agent::Occupation::Soldier as u8
    {
        return 0.0;
    }
    let sat = pool.satisfactions[slot];
    let sat = if credit > 0.0 { sat + credit * (1.0 - sat) } else { sat };
    if sat >= GUILD_SAT {
        return 0.0;
    }
    0.5 + 0.5 * (GUILD_SAT - sat) / GUILD_SAT
}

/// Grievance of an agent for a table row: the creed's need, or for a guild
/// its city and satisfaction.
#[inline]
pub fn row_grievance(pool: &AgentPool, slot: usize, row: &MovementRow, cover: &[Vec<(u8, u8)>]) -> f32 {
    let credit = reform_credit(cover, pool, slot, row.creed);
    if row.creed == CREED_GUILD {
        guild_grievance(pool, slot, row.settlement, credit)
    } else {
        grievance_credited(pool, slot, row.creed, credit)
    }
}

/// [`committed_credited`] for a table row (a guild member stays committed
/// while it lives in the city with satisfaction within LAPSE_MARGIN).
#[inline]
pub fn row_committed(pool: &AgentPool, slot: usize, row: &MovementRow, cover: &[Vec<(u8, u8)>]) -> bool {
    let credit = reform_credit(cover, pool, slot, row.creed);
    if row.creed == CREED_GUILD {
        let sat = pool.satisfactions[slot];
        let sat = if credit > 0.0 { sat + credit * (1.0 - sat) } else { sat };
        return row.settlement != 0
            && pool.settlement_ids[slot] == row.settlement
            && sat < GUILD_SAT + LAPSE_MARGIN;
    }
    committed_credited(pool, slot, row.creed, credit)
}

/// Recruitment factor from movement news of the row's creed (None without
/// news, so the probability keeps its bits).
#[inline]
fn news_factor(pool: &AgentPool, slot: usize, creed: u8) -> Option<f32> {
    let (inspire, fear) = crate::knowledge::movement_news_for_creed(pool, slot, creed);
    if inspire <= 0.0 && fear <= 0.0 {
        return None;
    }
    Some((1.0 + NEWS_JOIN * inspire) * (1.0 - NEWS_FEAR * fear))
}

fn stream(region: usize, turn: u32, offset: u64) -> u64 {
    ((region as u64) << 48) | ((turn as u64) << 16) | offset
}

fn founding_score(pool: &AgentPool, slot: usize, g: f32) -> f32 {
    g * (1.5 + pool.boldness[slot])
}

/// Agents of `slots` without a movement, ordered for seeding: aggrieved
/// first by founding score, then (when `fill`) the rest by boldness; ties by
/// agent id.
fn seed_candidates(
    pool: &AgentPool,
    slots: &[usize],
    row: &MovementRow,
    fill: bool,
    cover: &[Vec<(u8, u8)>],
) -> Vec<usize> {
    let mut ranked: Vec<(f32, f32, u32, usize)> = Vec::new();
    for &slot in slots {
        if !pool.is_alive(slot) || pool.movement_ids[slot] != 0 || pool.ages[slot] < ADULT_AGE {
            continue;
        }
        let g = row_grievance(pool, slot, row, cover);
        if g > 0.0 {
            ranked.push((1.0, founding_score(pool, slot, g), pool.ids[slot], slot));
        } else if fill
            && (row.creed != CREED_GUILD
                || (pool.settlement_ids[slot] == row.settlement
                    && pool.occupations[slot] != agent::Occupation::Soldier as u8))
        {
            ranked.push((0.0, pool.boldness[slot], pool.ids[slot], slot));
        }
    }
    ranked.sort_by(|a, b| {
        b.0.partial_cmp(&a.0)
            .unwrap()
            .then(b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal))
            .then(a.2.cmp(&b.2))
    });
    ranked.into_iter().map(|(_, _, _, slot)| slot).collect()
}

// ---------------------------------------------------------------------------
// The pass
// ---------------------------------------------------------------------------

/// Run the movement pass (after the knowledge phase, before delivering
/// merchants return home). Returns the per-agent effects for the rest of the
/// tick; updates `runtime.stats` and clears the table's one-shots.
pub fn movement_pass(
    pool: &mut AgentPool,
    regions: &[RegionState],
    runtime: &mut MovementRuntime,
    master_seed: [u8; 32],
    turn: u32,
) -> MovementEffects {
    let mut effects = MovementEffects::default();
    if !runtime.enabled {
        return effects;
    }
    let num_regions = regions.len();
    let groups = pool.partition_by_region(num_regions as u16);
    let cover = reform_cover(&runtime.reforms, regions);
    let rows = &runtime.rows;
    let nrows = rows.len();

    // Row of each movement id (u16 ids, small table).
    let max_id = rows.iter().map(|r| r.movement_id as usize).max().unwrap_or(0);
    let mut row_of: Vec<usize> = vec![usize::MAX; max_id + 1];
    for (i, row) in rows.iter().enumerate() {
        if row.movement_id >= 1 {
            row_of[row.movement_id as usize] = i;
        }
    }
    let row_index = |mid: u16| -> Option<usize> {
        let i = *row_of.get(mid as usize)?;
        if i == usize::MAX { None } else { Some(i) }
    };

    let mut stats = MovementStats {
        adults: vec![0; num_regions],
        aggrieved: vec![[0; CREED_COUNT]; num_regions],
        informed: vec![[0; CREED_COUNT]; num_regions],
        movement_ids: rows.iter().map(|r| r.movement_id).collect(),
        members: vec![0; nrows],
        joined: vec![0; nrows],
        lapsed: vec![0; nrows],
        founded: vec![0; nrows],
        released: 0,
    };

    // Adults per region (for seed sizes and exposure).
    for (r, slots) in groups.iter().enumerate() {
        stats.adults[r] = slots.iter().filter(|&&s| pool.ages[s] >= ADULT_AGE).count() as u32;
    }

    // A. Release (movement ended) and lapse.
    for (r, slots) in groups.iter().enumerate() {
        let mut rng = ChaCha8Rng::from_seed(master_seed);
        rng.set_stream(stream(r, turn, MOVEMENT_LAPSE_STREAM_OFFSET));
        let controller = regions[r].controller_civ;
        for &slot in slots {
            let mid = pool.movement_ids[slot];
            if mid == 0 {
                continue;
            }
            let Some(i) = row_index(mid) else {
                pool.movement_ids[slot] = 0;
                stats.released += 1;
                continue;
            };
            let row = &rows[i];
            let mut stay = 1.0f32;
            if row.stage == STAGE_SATISFIED {
                stay *= 1.0 - LAPSE_SATISFIED;
            }
            if !row_committed(pool, slot, row, &cover) {
                stay *= 1.0 - LAPSE_CONTENT;
            }
            let travelling = pool.is_on_trip(slot)
                || pool.trip_home_region[slot] != agent::TRIP_HOME_NONE;
            if controller != row.target_civ && !travelling {
                stay *= 1.0 - LAPSE_ABROAD;
            }
            if row.crackdown_region as usize == r && pool.boldness[slot] < 0.0 {
                stay *= 1.0 - LAPSE_FEAR;
            }
            let leave = 1.0 - stay;
            if leave > 0.0 && rng.gen::<f32>() < leave {
                pool.movement_ids[slot] = 0;
                stats.lapsed[i] += 1;
            }
        }
    }

    // B. Founding seeds, then re-seeding after a resume.
    for (i, row) in rows.iter().enumerate() {
        let r = row.found_region as usize;
        if row.found_region == NO_REGION || r >= num_regions {
            continue;
        }
        if row.founder_id != 0 {
            if let Some(slot) = pool.find_slot_by_id(row.founder_id) {
                if pool.movement_ids[slot] == 0 {
                    pool.movement_ids[slot] = row.movement_id;
                    stats.founded[i] += 1;
                }
            }
        }
        let size = FOUND_MIN.max((FOUND_SHARE * stats.adults[r] as f32).ceil() as usize);
        for slot in seed_candidates(pool, &groups[r], row, false, &cover).into_iter().take(size) {
            pool.movement_ids[slot] = row.movement_id;
            stats.founded[i] += 1;
        }
    }
    for seed in &runtime.seeds {
        let (Some(i), r) = (row_index(seed.movement_id), seed.region as usize) else {
            continue;
        };
        if r >= num_regions {
            continue;
        }
        for slot in seed_candidates(pool, &groups[r], &rows[i], true, &cover).into_iter().take(seed.count as usize) {
            pool.movement_ids[slot] = seed.movement_id;
            stats.founded[i] += 1;
        }
    }

    // C. Recruitment, against the membership after A and B.
    let recruiting: Vec<bool> = rows.iter().map(|r| r.stage != STAGE_SATISFIED).collect();
    let any_member = pool.movement_ids.iter().any(|&m| m != 0);
    if any_member && recruiting.iter().any(|&b| b) {
        let before: Vec<u16> = pool.movement_ids.clone();
        let mut region_members = vec![vec![0u32; nrows]; num_regions];
        let mut settlement_members: HashMap<(u16, usize), u32> = HashMap::new();
        let mut settlement_adults: HashMap<u16, u32> = HashMap::new();
        let mut id_to_slot: HashMap<u32, usize> = HashMap::with_capacity(pool.count);
        for (r, slots) in groups.iter().enumerate() {
            for &slot in slots {
                id_to_slot.insert(pool.ids[slot], slot);
                let sid = pool.settlement_ids[slot];
                if sid != 0 && pool.ages[slot] >= ADULT_AGE {
                    *settlement_adults.entry(sid).or_insert(0) += 1;
                }
                if let Some(i) = row_index(before[slot]) {
                    region_members[r][i] += 1;
                    if sid != 0 {
                        *settlement_members.entry((sid, i)).or_insert(0) += 1;
                    }
                }
            }
        }
        for (r, slots) in groups.iter().enumerate() {
            let controller = regions[r].controller_civ;
            let candidates: Vec<usize> = (0..nrows)
                .filter(|&i| recruiting[i] && rows[i].target_civ == controller && controller != 255)
                .collect();
            if candidates.is_empty() || stats.adults[r] == 0 {
                continue;
            }
            let mut rng = ChaCha8Rng::from_seed(master_seed);
            rng.set_stream(stream(r, turn, MOVEMENT_RECRUIT_STREAM_OFFSET));
            let adults = stats.adults[r] as f32;
            let mut offers: Vec<(usize, f32)> = Vec::with_capacity(candidates.len());
            for &slot in slots {
                if before[slot] != 0 || pool.ages[slot] < ADULT_AGE {
                    continue;
                }
                offers.clear();
                for &i in &candidates {
                    let row = &rows[i];
                    let g = row_grievance(pool, slot, row, &cover);
                    if g <= 0.0 {
                        continue;
                    }
                    let mut member_bonds = 0u32;
                    for b in 0..pool.rel_count[slot] as usize {
                        if !crate::relationships::is_positive_valence(pool.rel_bond_types[slot][b])
                            || pool.rel_sentiments[slot][b] <= 0
                        {
                            continue;
                        }
                        if let Some(&other) = id_to_slot.get(&pool.rel_target_ids[slot][b]) {
                            if before[other] == row.movement_id {
                                member_bonds += 1;
                            }
                        }
                    }
                    let share_r = region_members[r][i] as f32 / adults;
                    let sid = pool.settlement_ids[slot];
                    let share_s = if sid != 0 {
                        let n = settlement_adults.get(&sid).copied().unwrap_or(0);
                        let m = settlement_members.get(&(sid, i)).copied().unwrap_or(0);
                        if n > 0 { m as f32 / n as f32 } else { 0.0 }
                    } else {
                        0.0
                    };
                    let exposure = BOND_WEIGHT * (member_bonds as f32).min(BOND_FULL) / BOND_FULL
                        + RESIDENCE_WEIGHT * share_r
                        + URBAN_WEIGHT * share_s;
                    if exposure <= 0.0 {
                        continue;
                    }
                    let loyalty = if pool.civ_affinities[slot] == row.target_civ {
                        (1.5 - pool.loyalties[slot]).clamp(0.5, 1.5)
                    } else {
                        1.0
                    };
                    let stage = match row.stage {
                        STAGE_SUPPRESSED => SUPPRESSED_RECRUIT,
                        STAGE_RISING => RISING_RECRUIT,
                        _ => 1.0,
                    };
                    let mut p = RECRUIT_RATE
                        * row.appeal
                        * (0.5 + 0.5 * g)
                        * exposure
                        * crate::behavior::personality_modifier(pool.boldness[slot], BOLD_RECRUIT_WEIGHT)
                        * loyalty
                        * stage;
                    if let Some(f) = news_factor(pool, slot, row.creed) {
                        p *= f;
                    }
                    let p = p.min(RECRUIT_CAP);
                    if p > 0.0 {
                        offers.push((i, p));
                    }
                }
                if offers.is_empty() {
                    continue;
                }
                let total: f32 = offers.iter().map(|o| o.1).sum();
                let scale = if total > 1.0 { 1.0 / total } else { 1.0 };
                let u: f32 = rng.gen();
                let mut cumulative = 0.0f32;
                for &(i, p) in &offers {
                    cumulative += p * scale;
                    if u < cumulative {
                        pool.movement_ids[slot] = rows[i].movement_id;
                        stats.joined[i] += 1;
                        break;
                    }
                }
            }
        }
    }

    // D. Effects of decided outcomes on the members.
    let relief_rows: Vec<bool> = rows
        .iter()
        .map(|r| r.relief_age != NO_RELIEF && r.relief_age >= 1 && r.relief_age <= RELIEF_TURNS)
        .collect();
    let any_relief = relief_rows.iter().any(|&b| b);
    let any_rising = rows.iter().any(|r| r.rising_region != NO_REGION);
    if any_relief {
        effects.relief = vec![0.0; pool.capacity()];
    }
    if any_rising {
        effects.rebel_boost = vec![0.0; pool.capacity()];
    }
    for (r, slots) in groups.iter().enumerate() {
        for &slot in slots {
            let Some(i) = row_index(pool.movement_ids[slot]) else {
                continue;
            };
            let row = &rows[i];
            stats.members[i] += 1;
            if relief_rows[i] {
                let age = (row.relief_age - 1) as f32;
                effects.relief[slot] = RELIEF_SAT * (1.0 - age / RELIEF_TURNS as f32);
                if row.relief_age == 1 && row.creed != CREED_GUILD {
                    // A guild's relief is its members' satisfaction alone.
                    let need = match row.creed {
                        CREED_COMMONS => &mut pool.need_material[slot],
                        CREED_LIBERTY => &mut pool.need_autonomy[slot],
                        _ => &mut pool.need_spiritual[slot],
                    };
                    *need = (*need + RELIEF_NEED * (1.0 - *need)).min(1.0);
                }
            }
            if row.crackdown_region as usize == r {
                effects.memory_intents.push(MemoryIntent {
                    agent_slot: slot,
                    expected_agent_id: pool.ids[slot],
                    event_type: MemoryEventType::Persecution as u8,
                    source_civ: row.target_civ,
                    intensity: agent::PERSECUTION_DEFAULT_INTENSITY,
                    is_legacy: false,
                    decay_factor_override: None,
                });
            }
            if row.rising_region as usize == r {
                effects.rebel_boost[slot] = RISING_REBEL_BOOST;
            }
            if row.convert_to != NO_FAITH && pool.beliefs[slot] == row.convert_from {
                pool.beliefs[slot] = row.convert_to;
                pool.life_events[slot] |= agent::LIFE_EVENT_CONVERSION;
            }
        }
    }

    // The grievance census is taken at the end of the tick (`census`).
    stats.aggrieved = runtime.stats.aggrieved.clone();
    stats.informed = runtime.stats.informed.clone();
    runtime.stats = stats;
    runtime.cover = cover;
    runtime.seeds.clear();
    for row in runtime.rows.iter_mut() {
        row.clear_one_shots();
    }
    effects
}

/// End-of-tick grievance census for Python's emergence decision: adults and
/// the aggrieved per creed in each region, as Phase 10 will see them.
pub fn census(pool: &AgentPool, num_regions: usize, runtime: &mut MovementRuntime) {
    if !runtime.enabled {
        return;
    }
    let mut adults = vec![0u32; num_regions];
    let mut aggrieved = vec![[0u32; CREED_COUNT]; num_regions];
    let mut informed = vec![[0u32; CREED_COUNT]; num_regions];
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) || pool.ages[slot] < ADULT_AGE {
            continue;
        }
        let r = pool.regions[slot] as usize;
        if r >= num_regions {
            continue;
        }
        adults[r] += 1;
        for creed in 0..CREED_COUNT as u8 {
            let credit = reform_credit(&runtime.cover, pool, slot, creed);
            if grievance_credited(pool, slot, creed, credit) > 0.0 {
                aggrieved[r][creed as usize] += 1;
                if crate::knowledge::movement_news_for_creed(pool, slot, creed).0 > 0.0 {
                    informed[r][creed as usize] += 1;
                }
            }
        }
    }
    runtime.stats.adults = adults;
    runtime.stats.aggrieved = aggrieved;
    runtime.stats.informed = informed;
}

// ---------------------------------------------------------------------------
// Arrow I/O (FFI)
// ---------------------------------------------------------------------------

use arrow::array::{Array, Float32Array, UInt16Array, UInt32Array, UInt8Array};
use arrow::array::{UInt16Builder, UInt32Builder};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;

fn column<'a, T: 'static>(rb: &'a RecordBatch, name: &str) -> Result<&'a T, ArrowError> {
    rb.column_by_name(name)
        .ok_or_else(|| ArrowError::SchemaError(format!("missing column: {name}")))?
        .as_any()
        .downcast_ref::<T>()
        .ok_or_else(|| ArrowError::CastError(format!("column {name} has the wrong type")))
}

/// Movement table schema (one row per living movement):
/// movement_id u16, creed u8, stage u8, target_civ u8, appeal f32,
/// found_region u16, founder_id u32, relief_age u16, crackdown_region u16,
/// rising_region u16, convert_from u8, convert_to u8.
pub fn parse_movement_table(rb: &RecordBatch) -> Result<Vec<MovementRow>, ArrowError> {
    let n = rb.num_rows();
    if n == 0 {
        return Ok(Vec::new());
    }
    let ids = column::<UInt16Array>(rb, "movement_id")?;
    let creeds = column::<UInt8Array>(rb, "creed")?;
    let stages = column::<UInt8Array>(rb, "stage")?;
    let targets = column::<UInt8Array>(rb, "target_civ")?;
    let appeals = column::<Float32Array>(rb, "appeal")?;
    let found = column::<UInt16Array>(rb, "found_region")?;
    let founders = column::<UInt32Array>(rb, "founder_id")?;
    let relief = column::<UInt16Array>(rb, "relief_age")?;
    let crackdown = column::<UInt16Array>(rb, "crackdown_region")?;
    let rising = column::<UInt16Array>(rb, "rising_region")?;
    let convert_from = column::<UInt8Array>(rb, "convert_from")?;
    let convert_to = column::<UInt8Array>(rb, "convert_to")?;
    // Guilds: optional (absent with the switch off: no guild row).
    let settlements = rb
        .column_by_name("settlement")
        .map(|c| {
            c.as_any()
                .downcast_ref::<UInt16Array>()
                .ok_or_else(|| ArrowError::CastError("column settlement has the wrong type".into()))
        })
        .transpose()?;
    let mut rows = Vec::with_capacity(n);
    for i in 0..n {
        if ids.value(i) == 0 {
            return Err(ArrowError::InvalidArgumentError("movement_id 0 is reserved".into()));
        }
        rows.push(MovementRow {
            movement_id: ids.value(i),
            creed: creeds.value(i),
            stage: stages.value(i),
            target_civ: targets.value(i),
            appeal: appeals.value(i),
            found_region: found.value(i),
            founder_id: founders.value(i),
            relief_age: relief.value(i),
            crackdown_region: crackdown.value(i),
            rising_region: rising.value(i),
            convert_from: convert_from.value(i),
            convert_to: convert_to.value(i),
            settlement: settlements.map_or(0, |a| a.value(i)),
        });
    }
    Ok(rows)
}

/// Lasting reforms in force: creed u8, civ u8, region u16 (NO_REGION the
/// realm), faith u8 (NO_FAITH every believer).
pub fn parse_reform_table(rb: &RecordBatch) -> Result<Vec<ReformRow>, ArrowError> {
    if rb.num_rows() == 0 {
        return Ok(Vec::new());
    }
    let creeds = column::<UInt8Array>(rb, "creed")?;
    let civs = column::<UInt8Array>(rb, "civ")?;
    let regions = column::<UInt16Array>(rb, "region")?;
    let faiths = column::<UInt8Array>(rb, "faith")?;
    Ok((0..rb.num_rows())
        .map(|i| ReformRow {
            creed: creeds.value(i),
            civ: civs.value(i),
            region: regions.value(i),
            faith: faiths.value(i),
        })
        .collect())
}

/// Re-seeding batch: movement_id u16, region u16, count u32.
pub fn parse_movement_seeds(rb: &RecordBatch) -> Result<Vec<MovementSeed>, ArrowError> {
    if rb.num_rows() == 0 {
        return Ok(Vec::new());
    }
    let ids = column::<UInt16Array>(rb, "movement_id")?;
    let regions = column::<UInt16Array>(rb, "region")?;
    let counts = column::<UInt32Array>(rb, "count")?;
    Ok((0..rb.num_rows())
        .map(|i| MovementSeed { movement_id: ids.value(i), region: regions.value(i), count: counts.value(i) })
        .collect())
}

/// The last pass's stats as two batches: per region (region_id, adults,
/// aggrieved_commons, aggrieved_liberty, aggrieved_sect) and per movement
/// (movement_id, members, joined, lapsed, founded). Empty before any pass.
pub fn movement_stats_batches(stats: &MovementStats) -> Result<(RecordBatch, RecordBatch), ArrowError> {
    let n = stats.adults.len();
    let mut region_id = UInt16Builder::with_capacity(n);
    let mut adults = UInt32Builder::with_capacity(n);
    let mut aggrieved: Vec<UInt32Builder> = (0..CREED_COUNT).map(|_| UInt32Builder::with_capacity(n)).collect();
    let mut informed: Vec<UInt32Builder> = (0..CREED_COUNT).map(|_| UInt32Builder::with_capacity(n)).collect();
    for r in 0..n {
        region_id.append_value(r as u16);
        adults.append_value(stats.adults[r]);
        for c in 0..CREED_COUNT {
            aggrieved[c].append_value(stats.aggrieved[r][c]);
            informed[c].append_value(stats.informed.get(r).map_or(0, |v| v[c]));
        }
    }
    let region_schema = Arc::new(Schema::new(vec![
        Field::new("region_id", DataType::UInt16, false),
        Field::new("adults", DataType::UInt32, false),
        Field::new("aggrieved_commons", DataType::UInt32, false),
        Field::new("aggrieved_liberty", DataType::UInt32, false),
        Field::new("aggrieved_sect", DataType::UInt32, false),
        Field::new("informed_commons", DataType::UInt32, false),
        Field::new("informed_liberty", DataType::UInt32, false),
        Field::new("informed_sect", DataType::UInt32, false),
    ]));
    let mut agg = aggrieved.into_iter();
    let mut inf = informed.into_iter();
    let regions = RecordBatch::try_new(region_schema, vec![
        Arc::new(region_id.finish()) as _,
        Arc::new(adults.finish()) as _,
        Arc::new(agg.next().unwrap().finish()) as _,
        Arc::new(agg.next().unwrap().finish()) as _,
        Arc::new(agg.next().unwrap().finish()) as _,
        Arc::new(inf.next().unwrap().finish()) as _,
        Arc::new(inf.next().unwrap().finish()) as _,
        Arc::new(inf.next().unwrap().finish()) as _,
    ])?;
    let m = stats.movement_ids.len();
    let mut mid = UInt16Builder::with_capacity(m);
    for &v in &stats.movement_ids {
        mid.append_value(v);
    }
    let counts = |v: &Vec<u32>| {
        let mut b = UInt32Builder::with_capacity(m);
        for &x in v {
            b.append_value(x);
        }
        Arc::new(b.finish()) as Arc<dyn Array>
    };
    let movement_schema = Arc::new(Schema::new(vec![
        Field::new("movement_id", DataType::UInt16, false),
        Field::new("members", DataType::UInt32, false),
        Field::new("joined", DataType::UInt32, false),
        Field::new("lapsed", DataType::UInt32, false),
        Field::new("founded", DataType::UInt32, false),
    ]));
    let movements = RecordBatch::try_new(movement_schema, vec![
        Arc::new(mid.finish()) as _,
        counts(&stats.members),
        counts(&stats.joined),
        counts(&stats.lapsed),
        counts(&stats.founded),
    ])?;
    Ok((regions, movements))
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    fn region(id: u16, controller: u8) -> RegionState {
        let mut r = RegionState::new(id);
        r.controller_civ = controller;
        r
    }

    /// An aggrieved adult for every creed (low satisfaction and needs).
    fn aggrieved(pool: &mut AgentPool, region: u16, boldness: f32) -> usize {
        let slot = pool.spawn(region, 0, Occupation::Farmer, 30, boldness, 0.0, 0.0, 0, 1, 2, 0);
        pool.satisfactions[slot] = 0.2;
        pool.need_material[slot] = 0.2;
        pool.need_autonomy[slot] = 0.2;
        pool.need_spiritual[slot] = 0.2;
        slot
    }

    fn content(pool: &mut AgentPool, region: u16) -> usize {
        let slot = pool.spawn(region, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, 0);
        pool.satisfactions[slot] = 0.8;
        slot
    }

    fn runtime(rows: Vec<MovementRow>) -> MovementRuntime {
        MovementRuntime { enabled: true, rows, ..Default::default() }
    }

    #[test]
    fn grievance_needs_low_satisfaction_and_a_low_need() {
        let mut pool = AgentPool::new(4);
        let a = aggrieved(&mut pool, 0, 0.0);
        let c = content(&mut pool, 0);
        assert!(grievance(&pool, a, CREED_COMMONS) > 0.0);
        assert_eq!(grievance(&pool, c, CREED_COMMONS), 0.0);
        pool.need_material[a] = 0.9;
        assert_eq!(grievance(&pool, a, CREED_COMMONS), 0.0);
        assert!(grievance(&pool, a, CREED_SECT) > 0.0);
        pool.ages[a] = 10;
        assert_eq!(grievance(&pool, a, CREED_SECT), 0.0);
    }

    #[test]
    fn disabled_runtime_changes_nothing() {
        let mut pool = AgentPool::new(8);
        for _ in 0..5 {
            aggrieved(&mut pool, 0, 0.5);
        }
        let regions = vec![region(0, 0)];
        let mut rt = MovementRuntime::default();
        let fx = movement_pass(&mut pool, &regions, &mut rt, [0; 32], 1);
        assert!(fx.relief.is_empty() && fx.rebel_boost.is_empty() && fx.memory_intents.is_empty());
        assert!(pool.movement_ids.iter().all(|&m| m == 0));
        assert!(rt.stats.adults.is_empty());
    }

    #[test]
    fn founding_seeds_the_boldest_aggrieved_and_the_leader() {
        let mut pool = AgentPool::new(16);
        let mut slots = Vec::new();
        for k in 0..10 {
            slots.push(aggrieved(&mut pool, 0, -0.5 + 0.1 * k as f32));
        }
        let leader = content(&mut pool, 0);
        let regions = vec![region(0, 0)];
        let mut row = MovementRow::new(1, CREED_COMMONS, STAGE_GATHERING, 0);
        row.found_region = 0;
        row.founder_id = pool.ids[leader];
        let mut rt = runtime(vec![row]);
        movement_pass(&mut pool, &regions, &mut rt, [7; 32], 3);
        assert_eq!(pool.movement_ids[leader], 1);
        // FOUND_MIN seeds (5% of 11 adults rounds up to 1) from the boldest.
        for &s in &slots[7..] {
            assert_eq!(pool.movement_ids[s], 1);
        }
        assert_eq!(rt.stats.founded[0], 4);
        // One-shots cleared: a second tick founds nothing more.
        assert_eq!(rt.rows[0].found_region, NO_REGION);
        movement_pass(&mut pool, &regions, &mut rt, [7; 32], 4);
        assert_eq!(rt.stats.founded[0], 0);
    }

    #[test]
    fn recruitment_follows_bonds_and_needs_a_grievance() {
        let mut pool = AgentPool::new(64);
        let member = aggrieved(&mut pool, 0, 0.5);
        pool.movement_ids[member] = 1;
        let mut friends = Vec::new();
        for _ in 0..20 {
            let f = aggrieved(&mut pool, 0, 0.5);
            crate::relationships::upsert_symmetric(&mut pool, member, f, 6, 50, 0);
            friends.push(f);
        }
        let mut happy = Vec::new();
        for _ in 0..20 {
            let h = content(&mut pool, 0);
            crate::relationships::upsert_symmetric(&mut pool, member, h, 6, 50, 0);
            happy.push(h);
        }
        let regions = vec![region(0, 0)];
        let mut rt = runtime(vec![MovementRow::new(1, CREED_COMMONS, STAGE_GATHERING, 0)]);
        for t in 1..30 {
            movement_pass(&mut pool, &regions, &mut rt, [3; 32], t);
        }
        let joined = friends.iter().filter(|&&s| pool.movement_ids[s] == 1).count();
        assert!(joined >= 5, "aggrieved friends joined: {joined}");
        assert!(happy.iter().all(|&s| pool.movement_ids[s] == 0));
    }

    #[test]
    fn no_recruitment_outside_the_target_realm() {
        let mut pool = AgentPool::new(64);
        let member = aggrieved(&mut pool, 1, 0.5);
        pool.movement_ids[member] = 1;
        let mut others = Vec::new();
        for _ in 0..20 {
            let f = aggrieved(&mut pool, 1, 0.5);
            crate::relationships::upsert_symmetric(&mut pool, member, f, 6, 50, 0);
            others.push(f);
        }
        let regions = vec![region(0, 0), region(1, 2)];
        let mut rt = runtime(vec![MovementRow::new(1, CREED_LIBERTY, STAGE_GATHERING, 0)]);
        for t in 1..20 {
            movement_pass(&mut pool, &regions, &mut rt, [3; 32], t);
        }
        assert!(others.iter().all(|&s| pool.movement_ids[s] == 0));
    }

    #[test]
    fn ended_movements_release_their_members() {
        let mut pool = AgentPool::new(8);
        let a = aggrieved(&mut pool, 0, 0.0);
        let b = aggrieved(&mut pool, 0, 0.0);
        pool.movement_ids[a] = 1;
        pool.movement_ids[b] = 2;
        let regions = vec![region(0, 0)];
        let mut rt = runtime(vec![MovementRow::new(2, CREED_SECT, STAGE_GATHERING, 0)]);
        movement_pass(&mut pool, &regions, &mut rt, [1; 32], 1);
        assert_eq!(pool.movement_ids[a], 0);
        assert_eq!(pool.movement_ids[b], 2);
        assert_eq!(rt.stats.released, 1);
    }

    #[test]
    fn relief_restores_the_need_once_and_satisfaction_while_sent() {
        let mut pool = AgentPool::new(8);
        let a = aggrieved(&mut pool, 0, 0.0);
        pool.movement_ids[a] = 1;
        let regions = vec![region(0, 0)];
        let mut row = MovementRow::new(1, CREED_COMMONS, STAGE_SATISFIED, 0);
        row.relief_age = 1;
        let mut rt = runtime(vec![row.clone()]);
        let fx = movement_pass(&mut pool, &regions, &mut rt, [1; 32], 1);
        assert!((pool.need_material[a] - 0.6).abs() < 1e-6);
        assert!((fx.relief[a] - RELIEF_SAT).abs() < 1e-6);
        // Without a new table the relief is not repeated.
        let need = pool.need_material[a];
        let fx = movement_pass(&mut pool, &regions, &mut rt, [1; 32], 2);
        assert!(fx.relief.is_empty());
        assert_eq!(pool.need_material[a], need);
        // A later age gives a smaller relief and no need restoration.
        row.relief_age = 11;
        rt.rows = vec![row];
        if pool.movement_ids[a] == 1 {
            let fx = movement_pass(&mut pool, &regions, &mut rt, [1; 32], 3);
            if pool.movement_ids[a] == 1 {
                assert!((fx.relief[a] - RELIEF_SAT * 0.5).abs() < 1e-6);
                assert_eq!(pool.need_material[a], need);
            }
        }
    }

    #[test]
    fn crackdown_writes_persecution_intents_and_rising_boosts_rebels() {
        let mut pool = AgentPool::new(8);
        let a = aggrieved(&mut pool, 0, 0.5);
        let b = aggrieved(&mut pool, 1, 0.5);
        pool.movement_ids[a] = 1;
        pool.movement_ids[b] = 1;
        let regions = vec![region(0, 0), region(1, 0)];
        let mut row = MovementRow::new(1, CREED_LIBERTY, STAGE_RISING, 0);
        row.crackdown_region = 0;
        row.rising_region = 1;
        let mut rt = runtime(vec![row]);
        let fx = movement_pass(&mut pool, &regions, &mut rt, [1; 32], 1);
        assert_eq!(fx.memory_intents.len(), 1);
        assert_eq!(fx.memory_intents[0].agent_slot, a);
        assert_eq!(fx.memory_intents[0].event_type, MemoryEventType::Persecution as u8);
        assert_eq!(fx.rebel_boost[b], RISING_REBEL_BOOST);
        assert_eq!(fx.rebel_boost[a], 0.0);
        let fx = movement_pass(&mut pool, &regions, &mut rt, [1; 32], 2);
        assert!(fx.memory_intents.is_empty() && fx.rebel_boost.is_empty());
    }

    #[test]
    fn schism_converts_members_of_the_old_faith() {
        let mut pool = AgentPool::new(8);
        let a = aggrieved(&mut pool, 0, 0.0);
        let b = aggrieved(&mut pool, 0, 0.0);
        pool.movement_ids[a] = 1;
        let regions = vec![region(0, 0)];
        let mut row = MovementRow::new(1, CREED_SECT, STAGE_GATHERING, 0);
        row.convert_from = 0;
        row.convert_to = 5;
        let mut rt = runtime(vec![row]);
        movement_pass(&mut pool, &regions, &mut rt, [1; 32], 1);
        assert_eq!(pool.beliefs[a], 5);
        assert_eq!(pool.beliefs[b], 0);
    }

    #[test]
    fn reseeding_fills_a_region_up_to_the_saved_count() {
        let mut pool = AgentPool::new(16);
        for _ in 0..3 {
            aggrieved(&mut pool, 0, 0.0);
        }
        for _ in 0..5 {
            content(&mut pool, 0);
        }
        let regions = vec![region(0, 0)];
        let mut rt = runtime(vec![MovementRow::new(1, CREED_COMMONS, STAGE_GATHERING, 0)]);
        rt.seeds.push(MovementSeed { movement_id: 1, region: 0, count: 6 });
        movement_pass(&mut pool, &regions, &mut rt, [1; 32], 1);
        assert_eq!(rt.stats.founded[0], 6);
        assert!(rt.seeds.is_empty());
    }

    #[test]
    fn a_reform_credit_lowers_grievance_where_and_for_whom_it_covers() {
        let mut pool = AgentPool::new(16);
        // Region 0 (civ 0): a want the credit answers and a deep one.
        let mild = aggrieved(&mut pool, 0, 0.0);
        pool.need_material[mild] = 0.4;
        let deep = aggrieved(&mut pool, 0, 0.0);
        // Region 1 (civ 1): believers of faiths 0 and 1.
        let believer = aggrieved(&mut pool, 1, 0.0);
        pool.need_spiritual[believer] = 0.3;
        pool.beliefs[believer] = 0;
        let heretic = aggrieved(&mut pool, 1, 0.0);
        pool.need_spiritual[heretic] = 0.3;
        pool.beliefs[heretic] = 1;
        let regions = vec![region(0, 0), region(1, 1)];
        let reforms = vec![
            ReformRow { creed: CREED_COMMONS, civ: 0, region: NO_REGION, faith: NO_FAITH },
            ReformRow { creed: CREED_SECT, civ: 1, region: NO_REGION, faith: 0 },
            ReformRow { creed: CREED_LIBERTY, civ: 1, region: 0, faith: NO_FAITH }, // not its region
        ];
        let cover = reform_cover(&reforms, &regions);
        assert_eq!(cover[0], vec![(CREED_COMMONS, NO_FAITH)]);
        assert_eq!(cover[1], vec![(CREED_SECT, 0)]);
        let credit = |slot, creed| reform_credit(&cover, &pool, slot, creed);
        assert_eq!(credit(mild, CREED_COMMONS), REFORM_NEED_CREDIT);
        assert_eq!(credit(mild, CREED_SECT), 0.0);
        assert_eq!(credit(believer, CREED_SECT), REFORM_NEED_CREDIT);
        assert_eq!(credit(heretic, CREED_SECT), 0.0);
        // 0.4 + 0.3 x 0.6 = 0.58 is above the commons threshold; 0.2 reads 0.44.
        assert!(grievance(&pool, mild, CREED_COMMONS) > 0.0);
        assert_eq!(grievance_credited(&pool, mild, CREED_COMMONS, credit(mild, CREED_COMMONS)), 0.0);
        let g = grievance_credited(&pool, deep, CREED_COMMONS, credit(deep, CREED_COMMONS));
        assert!(g > 0.0 && g < grievance(&pool, deep, CREED_COMMONS));
        assert!(!committed_credited(&pool, mild, CREED_COMMONS, REFORM_NEED_CREDIT + 0.2));
        // A zero credit is the plain reading, bit for bit.
        for slot in [mild, deep, believer, heretic] {
            for creed in 0..CREED_COUNT as u8 {
                assert_eq!(grievance_credited(&pool, slot, creed, 0.0).to_bits(),
                           grievance(&pool, slot, creed).to_bits());
            }
        }
        // The census counts with the credit the pass derived.
        let mut rt = runtime(vec![MovementRow::new(1, CREED_SECT, STAGE_GATHERING, 1)]);
        rt.reforms = reforms;
        movement_pass(&mut pool, &regions, &mut rt, [1; 32], 1);
        census(&pool, 2, &mut rt);
        assert_eq!(rt.stats.aggrieved[0][CREED_COMMONS as usize], 1); // deep only
        assert_eq!(rt.stats.aggrieved[1][CREED_SECT as usize], 1); // the heretic
        // Without reforms nothing is credited.
        rt.reforms.clear();
        movement_pass(&mut pool, &regions, &mut rt, [1; 32], 2);
        census(&pool, 2, &mut rt);
        assert_eq!(rt.stats.aggrieved[0][CREED_COMMONS as usize], 2);
        assert_eq!(rt.stats.aggrieved[1][CREED_SECT as usize], 2);
    }

    #[test]
    fn covered_agents_are_not_recruited_for_the_answered_creed() {
        let mut pool = AgentPool::new(64);
        let member = aggrieved(&mut pool, 0, 0.5);
        pool.movement_ids[member] = 1;
        let mut friends = Vec::new();
        for _ in 0..20 {
            let f = aggrieved(&mut pool, 0, 0.5);
            pool.need_material[f] = 0.4; // answered by the relief
            crate::relationships::upsert_symmetric(&mut pool, member, f, 6, 50, 0);
            friends.push(f);
        }
        let regions = vec![region(0, 0)];
        let mut rt = runtime(vec![MovementRow::new(1, CREED_COMMONS, STAGE_GATHERING, 0)]);
        rt.reforms = vec![ReformRow { creed: CREED_COMMONS, civ: 0, region: NO_REGION, faith: NO_FAITH }];
        for t in 1..30 {
            movement_pass(&mut pool, &regions, &mut rt, [3; 32], t);
        }
        assert!(friends.iter().all(|&s| pool.movement_ids[s] == 0));
    }

    #[test]
    fn the_pass_is_deterministic() {
        let build = || {
            let mut pool = AgentPool::new(64);
            let member = aggrieved(&mut pool, 0, 0.3);
            pool.movement_ids[member] = 1;
            for k in 0..30 {
                let f = aggrieved(&mut pool, 0, -0.5 + 0.03 * k as f32);
                crate::relationships::upsert_symmetric(&mut pool, member, f, 5, 40, 0);
            }
            pool
        };
        let regions = vec![region(0, 0)];
        let run = || {
            let mut pool = build();
            let mut rt = runtime(vec![MovementRow::new(1, CREED_SECT, STAGE_GATHERING, 0)]);
            for t in 1..15 {
                movement_pass(&mut pool, &regions, &mut rt, [9; 32], t);
            }
            pool.movement_ids.clone()
        };
        assert_eq!(run(), run());
    }

    // --- guilds: the guild creed and movement news ---------------------------------

    /// A city resident of settlement 7: occupation, satisfaction.
    fn resident(pool: &mut AgentPool, occ: Occupation, sat: f32) -> usize {
        let slot = pool.spawn(0, 0, occ, 30, 0.3, 0.0, 0.0, 0, 1, 2, 0);
        pool.settlement_ids[slot] = 7;
        pool.satisfactions[slot] = sat;
        slot
    }

    fn guild_row(stage: u8) -> MovementRow {
        let mut row = MovementRow::new(1, CREED_GUILD, stage, 0);
        row.settlement = 7;
        row
    }

    #[test]
    fn the_guild_creed_aggrieves_discontented_civilians_of_its_city_only() {
        let mut pool = AgentPool::new(8);
        let merchant = resident(&mut pool, Occupation::Merchant, 0.4);
        let soldier = resident(&mut pool, Occupation::Soldier, 0.4);
        let content = resident(&mut pool, Occupation::Farmer, 0.7);
        let rural = aggrieved(&mut pool, 0, 0.0); // every need low, but no city
        let row = guild_row(STAGE_GATHERING);
        let cover = vec![Vec::new()];
        let g = row_grievance(&pool, merchant, &row, &cover);
        assert!((g - (0.5 + 0.5 * (GUILD_SAT - 0.4) / GUILD_SAT)).abs() < 1e-6);
        assert_eq!(row_grievance(&pool, soldier, &row, &cover), 0.0);
        assert_eq!(row_grievance(&pool, content, &row, &cover), 0.0);
        assert_eq!(row_grievance(&pool, rural, &row, &cover), 0.0);
        // Its own need does not make anyone a guildsman; the census creeds are unchanged.
        assert_eq!(grievance(&pool, merchant, CREED_GUILD), 0.0);
        assert!(row_committed(&pool, merchant, &row, &cover));
        assert!(!row_committed(&pool, rural, &row, &cover));
        // A guild charter covering the region credits satisfaction: 0.4 reads 0.58.
        let charter = vec![vec![(CREED_GUILD, NO_FAITH)]];
        let credited = row_grievance(&pool, merchant, &row, &charter);
        assert!(credited > 0.0 && credited < g);
    }

    #[test]
    fn a_guild_founding_seeds_its_city_and_no_one_else() {
        let mut pool = AgentPool::new(32);
        let mut townsmen = Vec::new();
        for _ in 0..6 {
            townsmen.push(resident(&mut pool, Occupation::Merchant, 0.3));
        }
        let soldier = resident(&mut pool, Occupation::Soldier, 0.2);
        let mut rural = Vec::new();
        for _ in 0..10 {
            rural.push(aggrieved(&mut pool, 0, 0.9));
        }
        let regions = vec![region(0, 0)];
        let mut row = guild_row(STAGE_GATHERING);
        row.found_region = 0;
        let mut rt = runtime(vec![row]);
        movement_pass(&mut pool, &regions, &mut rt, [5; 32], 1);
        let seeded = townsmen.iter().filter(|&&s| pool.movement_ids[s] == 1).count();
        assert!(seeded >= 3, "townsmen seeded: {seeded}");
        assert_eq!(pool.movement_ids[soldier], 0);
        assert!(rural.iter().all(|&s| pool.movement_ids[s] == 0));
        // A member who leaves the city is no longer committed and may lapse.
        let member = townsmen.iter().copied().find(|&s| pool.movement_ids[s] == 1).unwrap();
        pool.settlement_ids[member] = 0;
        assert!(!row_committed(&pool, member, &rt.rows[0], &[Vec::new()]));
    }

    /// Give `slot` a movement-news packet about `source` (another region).
    fn news(pool: &mut AgentPool, slot: usize, source: u16, creed: u8, kind: u8, intensity: u8) {
        let candidate = crate::knowledge::PacketCandidate {
            info_type: crate::knowledge::InfoType::MovementNews as u8,
            source_region: source,
            source_turn: 1,
            intensity,
            hop_count: 1,
        };
        crate::knowledge::admit_packet_from_civ(pool, slot, &candidate, crate::knowledge::news_code(creed, kind));
    }

    #[test]
    fn news_of_a_like_movement_elsewhere_raises_joining_and_a_crackdown_lowers_it() {
        // 100 members among 400 adults: exposure by co-residence alone.
        let build = |with: Option<u8>| {
            let mut pool = AgentPool::new(512);
            for _ in 0..100 {
                let member = aggrieved(&mut pool, 0, 0.5);
                pool.movement_ids[member] = 1;
            }
            let mut friends = Vec::new();
            for _ in 0..300 {
                let f = aggrieved(&mut pool, 0, 0.0);
                if let Some(kind) = with {
                    news(&mut pool, f, 3, CREED_COMMONS, kind, 255);
                }
                friends.push(f);
            }
            let regions = vec![region(0, 0)];
            let mut rt = runtime(vec![MovementRow::new(1, CREED_COMMONS, STAGE_GATHERING, 0)]);
            movement_pass(&mut pool, &regions, &mut rt, [11; 32], 1);
            friends.iter().filter(|&&s| pool.movement_ids[s] == 1).count()
        };
        let none = build(None);
        let reform = build(Some(crate::knowledge::NEWS_REFORM));
        let crackdown = build(Some(crate::knowledge::NEWS_CRACKDOWN));
        assert!(reform > none, "news of a reform: {reform} joined against {none}");
        assert!(crackdown < none, "news of a crackdown: {crackdown} joined against {none}");
        // News of another creed, or from the agent's own region, changes nothing.
        let mut pool = AgentPool::new(4);
        let a = aggrieved(&mut pool, 0, 0.0);
        news(&mut pool, a, 3, CREED_SECT, crate::knowledge::NEWS_REFORM, 255);
        news(&mut pool, a, 0, CREED_COMMONS, crate::knowledge::NEWS_REFORM, 255);
        assert_eq!(news_factor(&pool, a, CREED_COMMONS), None);
        assert!(news_factor(&pool, a, CREED_SECT).unwrap() > 1.0);
    }

    #[test]
    fn the_census_counts_the_informed_aggrieved_by_creed() {
        let mut pool = AgentPool::new(8);
        let a = aggrieved(&mut pool, 0, 0.0);
        let b = aggrieved(&mut pool, 0, 0.0);
        let c = content(&mut pool, 0);
        news(&mut pool, a, 2, CREED_LIBERTY, crate::knowledge::NEWS_RISING, 200);
        news(&mut pool, b, 2, CREED_LIBERTY, crate::knowledge::NEWS_CRACKDOWN, 200);
        news(&mut pool, c, 2, CREED_LIBERTY, crate::knowledge::NEWS_RISING, 200);
        let mut rt = runtime(Vec::new());
        census(&pool, 1, &mut rt);
        assert_eq!(rt.stats.informed[0], [0, 1, 0]); // a crackdown informs no one; c is content
        assert_eq!(rt.stats.aggrieved[0], [2, 2, 2]);
        let (regions, _) = movement_stats_batches(&rt.stats).unwrap();
        let col = regions
            .column_by_name("informed_liberty")
            .unwrap()
            .as_any()
            .downcast_ref::<UInt32Array>()
            .unwrap()
            .value(0);
        assert_eq!(col, 1);
    }

    #[test]
    fn the_settlement_column_is_optional() {
        let base = |extra: bool| {
            let mut fields = vec![
                Field::new("movement_id", DataType::UInt16, false),
                Field::new("creed", DataType::UInt8, false),
                Field::new("stage", DataType::UInt8, false),
                Field::new("target_civ", DataType::UInt8, false),
                Field::new("appeal", DataType::Float32, false),
                Field::new("found_region", DataType::UInt16, false),
                Field::new("founder_id", DataType::UInt32, false),
                Field::new("relief_age", DataType::UInt16, false),
                Field::new("crackdown_region", DataType::UInt16, false),
                Field::new("rising_region", DataType::UInt16, false),
                Field::new("convert_from", DataType::UInt8, false),
                Field::new("convert_to", DataType::UInt8, false),
            ];
            let mut cols: Vec<Arc<dyn Array>> = vec![
                Arc::new(UInt16Array::from(vec![1u16])),
                Arc::new(UInt8Array::from(vec![CREED_GUILD])),
                Arc::new(UInt8Array::from(vec![0u8])),
                Arc::new(UInt8Array::from(vec![0u8])),
                Arc::new(Float32Array::from(vec![1.0f32])),
                Arc::new(UInt16Array::from(vec![NO_REGION])),
                Arc::new(UInt32Array::from(vec![0u32])),
                Arc::new(UInt16Array::from(vec![NO_RELIEF])),
                Arc::new(UInt16Array::from(vec![NO_REGION])),
                Arc::new(UInt16Array::from(vec![NO_REGION])),
                Arc::new(UInt8Array::from(vec![NO_FAITH])),
                Arc::new(UInt8Array::from(vec![NO_FAITH])),
            ];
            if extra {
                fields.push(Field::new("settlement", DataType::UInt16, false));
                cols.push(Arc::new(UInt16Array::from(vec![7u16])));
            }
            RecordBatch::try_new(Arc::new(Schema::new(fields)), cols).unwrap()
        };
        assert_eq!(parse_movement_table(&base(false)).unwrap()[0].settlement, 0);
        assert_eq!(parse_movement_table(&base(true)).unwrap()[0].settlement, 7);
    }
}
