//! M59a: Information packet substrate — types, helpers, knowledge phase.

use crate::agent;
use crate::pool::AgentPool;
use crate::region::RegionState;

// ---------------------------------------------------------------------------
// InfoType
// ---------------------------------------------------------------------------

#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InfoType {
    Empty           = 0,
    ThreatWarning   = 1,
    TradeOpportunity = 2,
    ReligiousSignal = 3,
    /// Guilds (`--guilds`): news of a movement's founding, rising, reform or
    /// crackdown. It never displaces a packet of another type and yields its
    /// slot to one (see `admit_packet_from_civ`), so the other types' packets
    /// are those of a world without news.
    MovementNews    = 4,
}

impl InfoType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Empty),
            1 => Some(Self::ThreatWarning),
            2 => Some(Self::TradeOpportunity),
            3 => Some(Self::ReligiousSignal),
            4 => Some(Self::MovementNews),
            _ => None,
        }
    }

    /// Retention priority for eviction ranking. Higher = harder to evict.
    pub fn retention_priority(self) -> u8 {
        match self {
            Self::Empty => 0,
            Self::ThreatWarning => 3,
            Self::TradeOpportunity => 2,
            Self::ReligiousSignal => 1,
            Self::MovementNews => 0,
        }
    }
}

// ---------------------------------------------------------------------------
// Packet field encoding
// ---------------------------------------------------------------------------

/// Pack info_type (upper 3 bits) and hop_count (lower 5 bits) into a u8.
#[inline]
pub fn pack_type_hops(info_type: u8, hop_count: u8) -> u8 {
    (info_type << 5) | (hop_count & 0x1F)
}

/// Extract info_type from packed type_and_hops byte.
#[inline]
pub fn unpack_type(type_and_hops: u8) -> u8 {
    type_and_hops >> 5
}

/// Extract hop_count from packed type_and_hops byte.
#[inline]
pub fn unpack_hops(type_and_hops: u8) -> u8 {
    type_and_hops & 0x1F
}

/// Check if a packet slot is empty.
#[inline]
pub fn is_empty_slot(type_and_hops: u8) -> bool {
    unpack_type(type_and_hops) == InfoType::Empty as u8
}

// ---------------------------------------------------------------------------
// Decay constants
// ---------------------------------------------------------------------------

pub const DECAY_THREAT: u8 = 15;
pub const DECAY_TRADE: u8 = 8;
pub const DECAY_RELIGIOUS: u8 = 5;
pub const DECAY_NEWS: u8 = 10;

pub fn decay_rate(info_type: u8) -> u8 {
    match info_type {
        1 => DECAY_THREAT,
        2 => DECAY_TRADE,
        3 => DECAY_RELIGIOUS,
        4 => DECAY_NEWS,
        _ => 0,
    }
}

// ---------------------------------------------------------------------------
// Propagation constants
// ---------------------------------------------------------------------------

pub const BASE_RATE_THREAT: f32 = 0.7;
pub const BASE_RATE_TRADE: f32 = 0.4;
pub const BASE_RATE_RELIGIOUS: f32 = 0.25;
pub const BASE_RATE_NEWS: f32 = 0.35;
pub const HOP_ATTENUATION: f32 = 0.85;

pub fn base_rate(info_type: u8) -> f32 {
    match info_type {
        1 => BASE_RATE_THREAT,
        2 => BASE_RATE_TRADE,
        3 => BASE_RATE_RELIGIOUS,
        4 => BASE_RATE_NEWS,
        _ => 0.0,
    }
}

// ---------------------------------------------------------------------------
// Direct observation intensity constants
// ---------------------------------------------------------------------------

pub const INTENSITY_CONTROLLER_CHANGED: u8 = 200;
pub const INTENSITY_WAR_WON: u8 = 180;
pub const INTENSITY_SECESSION: u8 = 150;
pub const INTENSITY_SCHISM: u8 = 160;

/// Minimum market signal (`merchant::market_signal`: the observed region's
/// dearest good above balance, in margin units) to emit a trade_opportunity
/// packet. Until the 2026-10 city-markets correction the packet carried the
/// region's export margin (`merchant_route_margin`), which is high where a
/// region is cheap, so cheap and empty regions were advertised as markets.
pub const TRADE_MARGIN_THRESHOLD: f32 = 0.10;

/// Minimum conversion_rate to emit a religious_signal packet.
pub const CONVERSION_RATE_THRESHOLD: f32 = 0.05;

/// `pkt_source_civ` value for an uncontrolled source region, an empty slot, or
/// a packet admitted without provenance (`admit_packet`).
pub const PKT_CIV_NONE: u8 = 255;

// ---------------------------------------------------------------------------
// Movement news (guilds, docs/integration/guilds.md)
// ---------------------------------------------------------------------------

/// Kinds of movement news (append-only; Python `guilds.NEWS_KINDS`).
pub const NEWS_FOUNDING: u8 = 0;
pub const NEWS_RISING: u8 = 1;
pub const NEWS_REFORM: u8 = 2;
pub const NEWS_CRACKDOWN: u8 = 3;
pub const NEWS_KIND_COUNT: u8 = 4;
/// `RegionState.movement_news` without news.
pub const NO_NEWS: u8 = 255;

/// The news code a movement-news packet carries in `pkt_source_civ` (its
/// provenance byte): creed x NEWS_KIND_COUNT + kind.
#[inline]
pub fn news_code(creed: u8, kind: u8) -> u8 {
    creed * NEWS_KIND_COUNT + kind
}

#[inline]
pub fn news_creed(code: u8) -> u8 {
    code / NEWS_KIND_COUNT
}

#[inline]
pub fn news_kind(code: u8) -> u8 {
    code % NEWS_KIND_COUNT
}

// ---------------------------------------------------------------------------
// Channel filter + weight tables
// ---------------------------------------------------------------------------

/// Returns the channel weight for a (bond_type, info_type) pair, or None if
/// this bond does not carry this packet type.
pub fn channel_weight(bond_type: u8, info_type: u8) -> Option<f32> {
    match (bond_type, info_type) {
        // threat_warning (type 1): all positive-valence bonds
        (0, 1) => Some(1.0),  // Mentor
        (2, 1) => Some(1.0),  // Marriage
        (3, 1) => Some(0.8),  // ExileBond
        (4, 1) => Some(0.9),  // CoReligionist
        (5, 1) => Some(1.0),  // Kin
        (6, 1) => Some(0.9),  // Friend
        // trade_opportunity (type 2): Friend, Mentor, Marriage, Kin
        (0, 2) => Some(0.8),  // Mentor
        (2, 2) => Some(0.9),  // Marriage
        (5, 2) => Some(0.7),  // Kin
        (6, 2) => Some(1.0),  // Friend
        // religious_signal (type 3): CoReligionist primary, Kin + Marriage secondary
        (2, 3) => Some(0.6),  // Marriage
        (4, 3) => Some(1.0),  // CoReligionist
        (5, 3) => Some(0.7),  // Kin
        // movement_news (type 4): what friends, kin and family tell each other
        (0, 4) => Some(0.7),  // Mentor
        (2, 4) => Some(0.8),  // Marriage
        (4, 4) => Some(0.6),  // CoReligionist
        (5, 4) => Some(0.8),  // Kin
        (6, 4) => Some(1.0),  // Friend
        // Everything else: not eligible
        _ => None,
    }
}

// ---------------------------------------------------------------------------
// KnowledgeStats
// ---------------------------------------------------------------------------

/// Per-turn diagnostics accumulated during the knowledge phase.
#[derive(Clone, Debug, Default)]
pub struct KnowledgeStats {
    pub packets_created: u32,
    pub packets_refreshed: u32,
    pub packets_transmitted: u32,
    pub packets_expired: u32,
    pub packets_evicted: u32,
    pub packets_dropped: u32,
    pub live_packet_count: u32,
    pub agents_with_packets: u32,
    pub created_threat: u32,
    pub created_trade: u32,
    pub created_religious: u32,
    pub created_news: u32,
    pub transmitted_threat: u32,
    pub transmitted_trade: u32,
    pub transmitted_religious: u32,
    pub transmitted_news: u32,
    pub mean_age: f32,
    pub max_age: u32,
    pub mean_hops: f32,
    pub max_hops: u32,
    // M59b: Consumer counters (accumulated outside knowledge_phase, merged in tick.rs)
    pub merchant_plans_packet_driven: u32,
    pub merchant_plans_bootstrap: u32,
    pub merchant_no_usable_packets: u32,
    pub migration_choices_changed_by_threat: u32,
    // Deferred-backlog consumers (religious signal migration bias, loyalty rally)
    pub migration_choices_changed_by_religion: u32,
    pub loyalty_drifts_damped_by_rally: u32,
}

// ---------------------------------------------------------------------------
// Admission policy
// ---------------------------------------------------------------------------

/// Incoming packet candidate for admission into an agent's slots.
#[derive(Clone, Debug)]
pub struct PacketCandidate {
    pub info_type: u8,
    pub source_region: u16,
    pub source_turn: u16,
    pub intensity: u8,
    pub hop_count: u8,
}

/// Result of an admission attempt.
#[derive(Debug, PartialEq, Eq)]
pub enum AdmitResult {
    Refreshed,
    Inserted,
    Evicted,
    Dropped,
}

/// Try to admit a packet into the agent's 4 slots without source-civ
/// provenance (`pkt_source_civ` = `PKT_CIV_NONE`). Returns the admission outcome.
pub fn admit_packet(pool: &mut AgentPool, slot: usize, candidate: &PacketCandidate) -> AdmitResult {
    admit_packet_from_civ(pool, slot, candidate, PKT_CIV_NONE)
}

/// Try to admit a packet, recording `source_civ` (the civ controlling the
/// source region when the packet was observed) wherever the packet is written.
/// Identity, freshness and eviction rules are unchanged: provenance never
/// affects whether a packet is admitted.
pub fn admit_packet_from_civ(
    pool: &mut AgentPool,
    slot: usize,
    candidate: &PacketCandidate,
    source_civ: u8,
) -> AdmitResult {
    let info_type = candidate.info_type;
    let source_region = candidate.source_region;

    // Step 1: Check for same identity (info_type, source_region)
    for i in 0..agent::PACKET_SLOTS {
        let existing_type = unpack_type(pool.pkt_type_and_hops[slot][i]);
        if existing_type == info_type && pool.pkt_source_region[slot][i] == source_region {
            // Same identity — compare freshness
            let existing_turn = pool.pkt_source_turn[slot][i];
            if candidate.source_turn > existing_turn {
                // Incoming is newer — refresh in place
                pool.pkt_type_and_hops[slot][i] = pack_type_hops(info_type, candidate.hop_count);
                pool.pkt_source_region[slot][i] = source_region;
                pool.pkt_source_turn[slot][i] = candidate.source_turn;
                pool.pkt_intensity[slot][i] = candidate.intensity;
                pool.pkt_source_civ[slot][i] = source_civ;
                return AdmitResult::Refreshed;
            } else if candidate.source_turn == existing_turn {
                // Same turn — keep higher intensity; if tied, keep lower hop_count
                let existing_intensity = pool.pkt_intensity[slot][i];
                let existing_hops = unpack_hops(pool.pkt_type_and_hops[slot][i]);
                if candidate.intensity > existing_intensity
                    || (candidate.intensity == existing_intensity && candidate.hop_count < existing_hops)
                {
                    pool.pkt_type_and_hops[slot][i] = pack_type_hops(info_type, candidate.hop_count);
                    pool.pkt_intensity[slot][i] = candidate.intensity;
                    pool.pkt_source_civ[slot][i] = source_civ;
                    return AdmitResult::Refreshed;
                }
            }
            // Incoming is older or weaker — drop
            return AdmitResult::Dropped;
        }
    }

    // Movement news yields to every other type: it only takes an empty slot
    // or another news slot, and another type takes a news slot as if it were
    // empty. News therefore only ever holds slots that would be empty without
    // it, and the other types' packets (slot by slot) are those of a world
    // without news.
    let news = info_type == InfoType::MovementNews as u8;
    if news {
        return admit_news(pool, slot, candidate, source_civ);
    }

    // Step 2: Check for empty slot (a news slot counts as empty)
    for i in 0..agent::PACKET_SLOTS {
        let th = pool.pkt_type_and_hops[slot][i];
        if is_empty_slot(th) || unpack_type(th) == InfoType::MovementNews as u8 {
            pool.pkt_type_and_hops[slot][i] = pack_type_hops(info_type, candidate.hop_count);
            pool.pkt_source_region[slot][i] = source_region;
            pool.pkt_source_turn[slot][i] = candidate.source_turn;
            pool.pkt_intensity[slot][i] = candidate.intensity;
            pool.pkt_source_civ[slot][i] = source_civ;
            return AdmitResult::Inserted;
        }
    }

    // Step 3: All slots full — find lowest-ranked incumbent
    let incoming_priority = InfoType::from_u8(info_type)
        .map(|t| t.retention_priority())
        .unwrap_or(0);

    let mut worst_idx: usize = 0;
    let mut worst_turn: u16 = pool.pkt_source_turn[slot][0];
    let mut worst_priority: u8 = InfoType::from_u8(unpack_type(pool.pkt_type_and_hops[slot][0]))
        .map(|t| t.retention_priority())
        .unwrap_or(0);

    for i in 1..agent::PACKET_SLOTS {
        let i_turn = pool.pkt_source_turn[slot][i];
        let i_priority = InfoType::from_u8(unpack_type(pool.pkt_type_and_hops[slot][i]))
            .map(|t| t.retention_priority())
            .unwrap_or(0);

        // Older source_turn = easier to evict
        // Lower retention priority = easier to evict
        // Higher slot_index = easier to evict (tie-break)
        if i_turn < worst_turn
            || (i_turn == worst_turn && i_priority < worst_priority)
            || (i_turn == worst_turn && i_priority == worst_priority && i > worst_idx)
        {
            worst_idx = i;
            worst_turn = i_turn;
            worst_priority = i_priority;
        }
    }

    // Admission guard: incoming must outrank the worst incumbent
    let incoming_outranks = candidate.source_turn > worst_turn
        || (candidate.source_turn == worst_turn && incoming_priority > worst_priority);

    if incoming_outranks {
        pool.pkt_type_and_hops[slot][worst_idx] = pack_type_hops(info_type, candidate.hop_count);
        pool.pkt_source_region[slot][worst_idx] = source_region;
        pool.pkt_source_turn[slot][worst_idx] = candidate.source_turn;
        pool.pkt_intensity[slot][worst_idx] = candidate.intensity;
        pool.pkt_source_civ[slot][worst_idx] = source_civ;
        return AdmitResult::Evicted;
    }

    AdmitResult::Dropped
}

/// Admission of a movement-news packet (after the identity check): an empty
/// slot, else the oldest news slot when the incoming news is newer (or as
/// new and stronger), never a slot of another type.
fn admit_news(pool: &mut AgentPool, slot: usize, candidate: &PacketCandidate, source_civ: u8) -> AdmitResult {
    let write = |pool: &mut AgentPool, i: usize| {
        pool.pkt_type_and_hops[slot][i] = pack_type_hops(candidate.info_type, candidate.hop_count);
        pool.pkt_source_region[slot][i] = candidate.source_region;
        pool.pkt_source_turn[slot][i] = candidate.source_turn;
        pool.pkt_intensity[slot][i] = candidate.intensity;
        pool.pkt_source_civ[slot][i] = source_civ;
    };
    for i in 0..agent::PACKET_SLOTS {
        if is_empty_slot(pool.pkt_type_and_hops[slot][i]) {
            write(pool, i);
            return AdmitResult::Inserted;
        }
    }
    let mut worst: Option<usize> = None;
    for i in 0..agent::PACKET_SLOTS {
        if unpack_type(pool.pkt_type_and_hops[slot][i]) != InfoType::MovementNews as u8 {
            continue;
        }
        let older = match worst {
            None => true,
            Some(w) => {
                let (wt, it) = (pool.pkt_source_turn[slot][w], pool.pkt_source_turn[slot][i]);
                it < wt || (it == wt && pool.pkt_intensity[slot][i] < pool.pkt_intensity[slot][w])
            }
        };
        if older {
            worst = Some(i);
        }
    }
    if let Some(w) = worst {
        let (wt, wi) = (pool.pkt_source_turn[slot][w], pool.pkt_intensity[slot][w]);
        if candidate.source_turn > wt || (candidate.source_turn == wt && candidate.intensity > wi) {
            write(pool, w);
            return AdmitResult::Evicted;
        }
    }
    AdmitResult::Dropped
}

// ---------------------------------------------------------------------------
// Decay phase
// ---------------------------------------------------------------------------

/// Decay all non-empty packets. Returns the number of packets expired (cleared).
pub fn decay_packets(pool: &mut AgentPool, alive_slots: &[usize]) -> u32 {
    let mut expired = 0u32;
    for &slot in alive_slots {
        for i in 0..agent::PACKET_SLOTS {
            let th = pool.pkt_type_and_hops[slot][i];
            if is_empty_slot(th) {
                continue;
            }
            let info_type = unpack_type(th);
            let rate = decay_rate(info_type);
            let intensity = pool.pkt_intensity[slot][i];
            if intensity <= rate {
                // Expired — clear slot to all-zero
                pool.pkt_type_and_hops[slot][i] = 0;
                pool.pkt_source_region[slot][i] = 0;
                pool.pkt_source_turn[slot][i] = 0;
                pool.pkt_intensity[slot][i] = 0;
                pool.pkt_source_civ[slot][i] = PKT_CIV_NONE;
                expired += 1;
            } else {
                pool.pkt_intensity[slot][i] = intensity - rate;
            }
        }
    }
    expired
}

// ---------------------------------------------------------------------------
// Direct observation phase
// ---------------------------------------------------------------------------

/// Run direct observation for all alive agents. Each agent checks their
/// current region's state and their arrival flag to produce/refresh packets.
/// Returns
/// (created_count, refreshed_count, evicted_count, dropped_count,
///  created_threat, created_trade, created_religious).
pub fn observe_packets(
    pool: &mut AgentPool,
    regions: &[RegionState],
    alive_slots: &[usize],
    current_turn: u16,
) -> (u32, u32, u32, u32, u32, u32, u32) {
    let mut created = 0u32;
    let mut refreshed = 0u32;
    let mut evicted = 0u32;
    let mut dropped = 0u32;
    let mut created_threat = 0u32;
    let mut created_trade = 0u32;
    let mut created_religious = 0u32;

    for &slot in alive_slots {
        let region_idx = pool.regions[slot] as usize;
        if region_idx >= regions.len() {
            continue;
        }
        let region = &regions[region_idx];

        // --- Threat warning ---
        let mut threat_intensity: u8 = 0;
        if region.controller_changed_this_turn {
            threat_intensity = threat_intensity.max(INTENSITY_CONTROLLER_CHANGED);
        }
        if region.war_won_this_turn {
            threat_intensity = threat_intensity.max(INTENSITY_WAR_WON);
        }
        if region.seceded_this_turn {
            threat_intensity = threat_intensity.max(INTENSITY_SECESSION);
        }
        if threat_intensity > 0 {
            let result = admit_packet_from_civ(pool, slot, &PacketCandidate {
                info_type: InfoType::ThreatWarning as u8,
                source_region: region.region_id,
                source_turn: current_turn,
                intensity: threat_intensity,
                hop_count: 0,
            }, region.controller_civ);
            match result {
                AdmitResult::Inserted => { created += 1; created_threat += 1; }
                AdmitResult::Refreshed => { refreshed += 1; }
                AdmitResult::Evicted => {
                    created += 1;
                    evicted += 1;
                    created_threat += 1;
                }
                AdmitResult::Dropped => { dropped += 1; }
            }
        }

        // --- Trade opportunity ---
        // M59b: Broaden to idle/loading merchants (not just arrivals).
        // Skip transit merchants (intermediate hops) and arrived_this_turn
        // (arrival path already fires — dedup to prevent dropped-packet noise).
        let is_merchant = pool.occupations[slot] == crate::agent::Occupation::Merchant as u8;
        let is_trade_eligible = if pool.arrived_this_turn[slot] {
            // Arrival path: original M59a behavior
            true
        } else if is_merchant
            && (pool.trip_phase[slot] == crate::agent::TRIP_PHASE_IDLE
                || pool.trip_phase[slot] == crate::agent::TRIP_PHASE_LOADING)
        {
            // M59b: Idle/loading merchant local observation
            true
        } else {
            false
        };
        let market = if is_trade_eligible { crate::merchant::market_signal(region) } else { 0.0 };
        if is_trade_eligible && market > TRADE_MARGIN_THRESHOLD {
            let scaled = ((market - TRADE_MARGIN_THRESHOLD) / 0.90 * 230.0).clamp(0.0, 255.0) as u8;
            let intensity = scaled.max(50).min(230);
            let result = admit_packet_from_civ(pool, slot, &PacketCandidate {
                info_type: InfoType::TradeOpportunity as u8,
                source_region: region.region_id,
                source_turn: current_turn,
                intensity,
                hop_count: 0,
            }, region.controller_civ);
            match result {
                AdmitResult::Inserted => { created += 1; created_trade += 1; }
                AdmitResult::Refreshed => { refreshed += 1; }
                AdmitResult::Evicted => {
                    created += 1;
                    evicted += 1;
                    created_trade += 1;
                }
                AdmitResult::Dropped => { dropped += 1; }
            }
        }

        // --- Religious signal ---
        let mut religious_intensity: u8 = 0;
        if region.persecution_intensity > 0.0 {
            let scaled = (region.persecution_intensity * 200.0).clamp(0.0, 255.0) as u8;
            religious_intensity = religious_intensity.max(scaled.max(40).min(200));
        }
        if region.conversion_rate > CONVERSION_RATE_THRESHOLD {
            let scaled = (region.conversion_rate * 300.0).clamp(0.0, 255.0) as u8;
            religious_intensity = religious_intensity.max(scaled.max(40).min(180));
        }
        if region.schism_convert_from != region.schism_convert_to
            && region.schism_convert_from != 255
        {
            religious_intensity = religious_intensity.max(INTENSITY_SCHISM);
        }
        if religious_intensity > 0 {
            let result = admit_packet_from_civ(pool, slot, &PacketCandidate {
                info_type: InfoType::ReligiousSignal as u8,
                source_region: region.region_id,
                source_turn: current_turn,
                intensity: religious_intensity,
                hop_count: 0,
            }, region.controller_civ);
            match result {
                AdmitResult::Inserted => { created += 1; created_religious += 1; }
                AdmitResult::Refreshed => { refreshed += 1; }
                AdmitResult::Evicted => {
                    created += 1;
                    evicted += 1;
                    created_religious += 1;
                }
                AdmitResult::Dropped => { dropped += 1; }
            }
        }
    }

    (
        created,
        refreshed,
        evicted,
        dropped,
        created_threat,
        created_trade,
        created_religious,
    )
}

/// Share of a movement event's news intensity that the agents of the
/// adjacent regions observe (word along the roads and through the markets).
pub const NEWS_NEIGHBOUR_SHARE: f32 = 0.5;

/// Guilds: every agent in a region with movement news this turn observes a
/// movement-news packet (`news_code` in the provenance byte) at the news'
/// intensity, and every agent of an adjacent region at NEWS_NEIGHBOUR_SHARE
/// of it (its own region's news first, then its neighbours' by region id).
/// Returns (created, refreshed, evicted, dropped). No-op where
/// `movement_news` is NO_NEWS (every region with the switch off).
pub fn observe_news(
    pool: &mut AgentPool,
    regions: &[RegionState],
    alive_slots: &[usize],
    current_turn: u16,
) -> (u32, u32, u32, u32) {
    let (mut created, mut refreshed, mut evicted, mut dropped) = (0u32, 0u32, 0u32, 0u32);
    let has_news = |r: &RegionState| r.movement_news != NO_NEWS && r.movement_news_intensity > 0;
    if !regions.iter().any(has_news) {
        return (0, 0, 0, 0);
    }
    for &slot in alive_slots {
        let Some(region) = regions.get(pool.regions[slot] as usize) else {
            continue;
        };
        let mut heard: Vec<(&RegionState, u8)> = Vec::new();
        if has_news(region) {
            heard.push((region, region.movement_news_intensity));
        }
        for &n in &region.adjacency {
            if let Some(near) = regions.get(n as usize) {
                if has_news(near) {
                    let intensity = (near.movement_news_intensity as f32 * NEWS_NEIGHBOUR_SHARE) as u8;
                    if intensity > 0 {
                        heard.push((near, intensity));
                    }
                }
            }
        }
        for (source, intensity) in heard {
            let result = admit_packet_from_civ(pool, slot, &PacketCandidate {
                info_type: InfoType::MovementNews as u8,
                source_region: source.region_id,
                source_turn: current_turn,
                intensity,
                hop_count: 0,
            }, source.movement_news);
            match result {
                AdmitResult::Inserted => created += 1,
                AdmitResult::Refreshed => refreshed += 1,
                AdmitResult::Evicted => {
                    created += 1;
                    evicted += 1;
                }
                AdmitResult::Dropped => dropped += 1,
            }
        }
    }
    (created, refreshed, evicted, dropped)
}

/// Guilds: the strongest nonlocal movement news an agent holds about a
/// creed, as (inspiring, fearful) strengths in 0..1: a founding, rising or
/// reform inspires, a crackdown frightens. (0, 0) without news.
pub fn movement_news_for_creed(pool: &AgentPool, slot: usize, creed: u8) -> (f32, f32) {
    let own = pool.regions[slot];
    let (mut inspire, mut fear) = (0.0f32, 0.0f32);
    for i in 0..agent::PACKET_SLOTS {
        let th = pool.pkt_type_and_hops[slot][i];
        if unpack_type(th) != InfoType::MovementNews as u8 || pool.pkt_source_region[slot][i] == own {
            continue;
        }
        let code = pool.pkt_source_civ[slot][i];
        if news_creed(code) != creed {
            continue;
        }
        let strength = pool.pkt_intensity[slot][i] as f32 / 255.0;
        if news_kind(code) == NEWS_CRACKDOWN {
            fear = fear.max(strength);
        } else {
            inspire = inspire.max(strength);
        }
    }
    (inspire, fear)
}

/// Guilds: where the strongest inspiring nonlocal news an agent holds about
/// a creed came from, as (source region, source turn, kind); None without
/// any. Ties: the newer, then the lower region. Read only: the census uses
/// it to name the like movement whose news the aggrieved hold.
pub fn movement_news_source(pool: &AgentPool, slot: usize, creed: u8) -> Option<(u16, u16, u8)> {
    let own = pool.regions[slot];
    let mut best: Option<(u8, u16, u16, u8)> = None; // (intensity, turn, region, kind)
    for i in 0..agent::PACKET_SLOTS {
        let th = pool.pkt_type_and_hops[slot][i];
        if unpack_type(th) != InfoType::MovementNews as u8 || pool.pkt_source_region[slot][i] == own {
            continue;
        }
        let code = pool.pkt_source_civ[slot][i];
        let intensity = pool.pkt_intensity[slot][i];
        if news_creed(code) != creed || news_kind(code) == NEWS_CRACKDOWN || intensity == 0 {
            continue;
        }
        let cand = (intensity, pool.pkt_source_turn[slot][i], pool.pkt_source_region[slot][i], news_kind(code));
        let better = match best {
            None => true,
            Some(b) => cand.0 > b.0 || (cand.0 == b.0 && (cand.1 > b.1 || (cand.1 == b.1 && cand.2 < b.2))),
        };
        if better {
            best = Some(cand);
        }
    }
    best.map(|(_, turn, region, kind)| (region, turn, kind))
}

// ---------------------------------------------------------------------------
// Propagation phase (buffered)
// ---------------------------------------------------------------------------

/// A buffered packet received during propagation, pending commit.
#[derive(Clone, Debug)]
pub struct BufferedReceive {
    pub receiver_slot: usize,
    pub candidate: PacketCandidate,
    /// Provenance copied from the sender's slot (see `pkt_source_civ`).
    pub source_civ: u8,
}

/// Key words of a ChaCha seed, as `ChaCha8Rng::from_seed` reads them.
#[inline]
fn chacha_key(seed: &[u8; 32]) -> [u32; 8] {
    let mut key = [0u32; 8];
    for (i, word) in key.iter_mut().enumerate() {
        *word = u32::from_le_bytes([seed[4 * i], seed[4 * i + 1], seed[4 * i + 2], seed[4 * i + 3]]);
    }
    key
}

/// `{ let mut rng = ChaCha8Rng::from_seed(seed); rng.set_stream(stream); rng.gen::<f32>() }`,
/// bit for bit, from one ChaCha8 block instead of the generator's four.
///
/// A fresh generator's first `u32` is word 0 of keystream block 0: the
/// ChaCha state (the "expand 32-byte k" constants, the eight key words of
/// `seed`, a 64-bit block counter of 0 and the 64-bit stream as the nonce)
/// after four double rounds, plus its initial word 0. `rand`'s `f32` takes
/// that word's top 24 bits times 2^-24. `transmission_roll_matches_chacha8rng`
/// checks it against the generator.
#[inline]
fn chacha8_first_f32(key: &[u32; 8], stream: u64) -> f32 {
    const SIGMA: [u32; 4] = [0x6170_7865, 0x3320_646e, 0x7962_2d32, 0x6b20_6574];
    let mut x = [
        SIGMA[0], SIGMA[1], SIGMA[2], SIGMA[3],
        key[0], key[1], key[2], key[3], key[4], key[5], key[6], key[7],
        0, 0, stream as u32, (stream >> 32) as u32,
    ];
    macro_rules! quarter {
        ($a:expr, $b:expr, $c:expr, $d:expr) => {
            x[$a] = x[$a].wrapping_add(x[$b]);
            x[$d] = (x[$d] ^ x[$a]).rotate_left(16);
            x[$c] = x[$c].wrapping_add(x[$d]);
            x[$b] = (x[$b] ^ x[$c]).rotate_left(12);
            x[$a] = x[$a].wrapping_add(x[$b]);
            x[$d] = (x[$d] ^ x[$a]).rotate_left(8);
            x[$c] = x[$c].wrapping_add(x[$d]);
            x[$b] = (x[$b] ^ x[$c]).rotate_left(7);
        };
    }
    for _ in 0..4 {
        quarter!(0, 4, 8, 12);
        quarter!(1, 5, 9, 13);
        quarter!(2, 6, 10, 14);
        quarter!(3, 7, 11, 15);
        quarter!(0, 5, 10, 15);
        quarter!(1, 6, 11, 12);
        quarter!(2, 7, 8, 13);
        quarter!(3, 4, 9, 14);
    }
    let word = x[0].wrapping_add(SIGMA[0]);
    // rand 0.8 `Standard` for f32: 24 random bits, scale 2^-24.
    let scale = 1.0 / ((1u32 << 24) as f32);
    scale * (word >> 8) as f32
}

/// Run propagation: each agent tries to share non-empty packets with bonded agents.
/// Uses the post-observation snapshot. Returns (buffer, transmitted_count, transmitted_threat, transmitted_trade, transmitted_religious).
///
/// `slot_lookup` maps agent_id -> slot index for relationship target resolution.
pub fn propagate_packets<L: crate::pool::SlotLookup>(
    pool: &AgentPool,
    alive_slots: &[usize],
    master_seed: &[u8; 32],
    current_turn: u32,
    slot_lookup: &L,
) -> (Vec<BufferedReceive>, u32, u32, u32, u32) {
    let mut buffer: Vec<BufferedReceive> = Vec::new();
    let mut transmitted = 0u32;
    let mut transmitted_threat = 0u32;
    let mut transmitted_trade = 0u32;
    let mut transmitted_religious = 0u32;
    let key = chacha_key(master_seed);

    for &sender_slot in alive_slots {
        let rel_count = pool.rel_count[sender_slot] as usize;
        if rel_count == 0 {
            continue;
        }
        // The sender's bonds to living agents, in bond order (the same for
        // every packet): (receiver slot, bond type, sentiment).
        let mut bonds = [(0usize, 0u8, 0i8); 8];
        let mut bond_len = 0;
        for rel_idx in 0..rel_count {
            let bond_type = pool.rel_bond_types[sender_slot][rel_idx];
            if bond_type == crate::relationships::EMPTY_BOND_TYPE {
                continue;
            }
            let target_id = pool.rel_target_ids[sender_slot][rel_idx];
            if let Some(s) = slot_lookup.slot_of(target_id) {
                if pool.is_alive(s) {
                    bonds[bond_len] = (s, bond_type, pool.rel_sentiments[sender_slot][rel_idx]);
                    bond_len += 1;
                }
            }
        }
        if bond_len == 0 {
            continue;
        }

        for pkt_idx in 0..agent::PACKET_SLOTS {
            let th = pool.pkt_type_and_hops[sender_slot][pkt_idx];
            if is_empty_slot(th) {
                continue;
            }
            let info_type = unpack_type(th);
            let hop_count = unpack_hops(th);

            // hop_count = 31 halts propagation
            if hop_count >= agent::MAX_HOP_COUNT {
                continue;
            }

            let source_region = pool.pkt_source_region[sender_slot][pkt_idx];
            let source_turn = pool.pkt_source_turn[sender_slot][pkt_idx];
            let sender_intensity = pool.pkt_intensity[sender_slot][pkt_idx];
            let source_civ = pool.pkt_source_civ[sender_slot][pkt_idx];

            // Collect unique receivers with their best eligible bond. Receivers
            // are kept in first-seen order; the commit sorts the buffer by
            // receiver first and each receiver appears once per packet here,
            // so this order does not reach any result (it used to be a
            // HashMap's).
            let mut best_per_receiver = [(0usize, (0.0f32, 0.0f32, 0i8, 0u8)); 8];
            let mut receivers = 0;
            for &(receiver_slot, bond_type, sentiment) in &bonds[..bond_len] {
                let weight = match channel_weight(bond_type, info_type) {
                    Some(w) => w,
                    None => continue,
                };

                let sentiment_factor = (sentiment.max(0) as f32) / 127.0;
                let chance = base_rate(info_type) * weight * sentiment_factor;

                let pos = match best_per_receiver[..receivers].iter().position(|e| e.0 == receiver_slot) {
                    Some(pos) => pos,
                    None => {
                        best_per_receiver[receivers] = (receiver_slot, (0.0, 0.0, 0, 255));
                        receivers += 1;
                        receivers - 1
                    }
                };
                let entry = &mut best_per_receiver[pos].1;
                if chance > entry.0
                    || (chance == entry.0 && weight > entry.1)
                    || (chance == entry.0 && weight == entry.1 && sentiment > entry.2)
                    || (chance == entry.0 && weight == entry.1 && sentiment == entry.2 && bond_type < entry.3)
                {
                    *entry = (chance, weight, sentiment, bond_type);
                }
            }

            for &(receiver_slot, (chance, _, _, _)) in &best_per_receiver[..receivers] {
                if chance <= 0.0 {
                    continue;
                }

                let sender_id = pool.ids[sender_slot];
                let receiver_id = pool.ids[receiver_slot];

                // V10: Use set_stream() discipline instead of XOR-into-seed.
                // Knowledge transmission depends on more components than the standard
                // packed stream scheme, so we hash them into a composite stream ID
                // using the same LCG constants but pass the result to set_stream().
                let stream = {
                    let mut h: u64 = sender_id as u64;
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(receiver_id as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(info_type as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(source_region as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(source_turn as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(current_turn as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(agent::KNOWLEDGE_STREAM_OFFSET);
                    h
                };
                // The first draw of `ChaCha8Rng::from_seed(*master_seed)`
                // on `stream` (`chacha8_first_f32`).
                let roll: f32 = chacha8_first_f32(&key, stream);

                if roll < chance {
                    let received_intensity = (sender_intensity as f32 * HOP_ATTENUATION) as u8;
                    if received_intensity == 0 {
                        continue;
                    }
                    buffer.push(BufferedReceive {
                        receiver_slot,
                        candidate: PacketCandidate {
                            info_type,
                            source_region,
                            source_turn,
                            intensity: received_intensity,
                            hop_count: hop_count + 1,
                        },
                        source_civ,
                    });
                    transmitted += 1;
                    match info_type {
                        1 => transmitted_threat += 1,
                        2 => transmitted_trade += 1,
                        3 => transmitted_religious += 1,
                        _ => {}
                    }
                }
            }
        }
    }

    (buffer, transmitted, transmitted_threat, transmitted_trade, transmitted_religious)
}

// ---------------------------------------------------------------------------
// Commit phase
// ---------------------------------------------------------------------------

/// Dedupe and commit buffered receives. Returns (refreshed, evicted, dropped).
pub fn commit_buffered(
    pool: &mut AgentPool,
    mut buffer: Vec<BufferedReceive>,
) -> (u32, u32, u32) {
    let mut refreshed = 0u32;
    let mut evicted = 0u32;
    let mut dropped = 0u32;

    if buffer.is_empty() {
        return (refreshed, evicted, dropped);
    }

    // Intra-turn merge: sort canonically for thread-stable admission order
    buffer.sort_by(|a, b| {
        a.receiver_slot.cmp(&b.receiver_slot)
            .then(a.candidate.info_type.cmp(&b.candidate.info_type))
            .then(a.candidate.source_region.cmp(&b.candidate.source_region))
            .then(b.candidate.source_turn.cmp(&a.candidate.source_turn))
            .then(b.candidate.intensity.cmp(&a.candidate.intensity))
            .then(a.candidate.hop_count.cmp(&b.candidate.hop_count))
    });

    // Dedupe: keep first in each (receiver_slot, info_type, source_region) group
    buffer.dedup_by(|b, a| {
        a.receiver_slot == b.receiver_slot
            && a.candidate.info_type == b.candidate.info_type
            && a.candidate.source_region == b.candidate.source_region
    });

    for receive in &buffer {
        let result = admit_packet_from_civ(
            pool, receive.receiver_slot, &receive.candidate, receive.source_civ,
        );
        match result {
            AdmitResult::Refreshed => refreshed += 1,
            AdmitResult::Evicted => evicted += 1,
            AdmitResult::Dropped => dropped += 1,
            AdmitResult::Inserted => {}
        }
    }

    (refreshed, evicted, dropped)
}

// ---------------------------------------------------------------------------
// M59b: Packet query helpers
// ---------------------------------------------------------------------------

/// M59b: Collect usable nonlocal trade_opportunity packets for a merchant.
/// Returns vec of (source_region, packet_strength) for packets where:
/// - info_type == TradeOpportunity
/// - intensity > 0
/// - source_region != current_region
/// Caller is responsible for reachability filtering.
pub fn usable_trade_packets(
    pool: &AgentPool,
    slot: usize,
    current_region: u16,
) -> Vec<(u16, f32)> {
    let mut results = Vec::new();
    for i in 0..agent::PACKET_SLOTS {
        let th = pool.pkt_type_and_hops[slot][i];
        if is_empty_slot(th) {
            continue;
        }
        if unpack_type(th) != InfoType::TradeOpportunity as u8 {
            continue;
        }
        let intensity = pool.pkt_intensity[slot][i];
        if intensity == 0 {
            continue;
        }
        let source_region = pool.pkt_source_region[slot][i];
        if source_region == current_region {
            continue;
        }
        results.push((source_region, intensity as f32 / 255.0));
    }
    results
}

/// M59b: Find the strongest threat_warning packet targeting `target_region`.
/// Returns the packet strength (intensity / 255.0) of the strongest match,
/// or 0.0 if no matching threat packet is held.
/// Excludes packets sourced from the agent's own region.
pub fn strongest_threat_for_region(
    pool: &AgentPool,
    slot: usize,
    target_region: u16,
    own_region: u16,
) -> f32 {
    let mut best: f32 = 0.0;
    for i in 0..agent::PACKET_SLOTS {
        let th = pool.pkt_type_and_hops[slot][i];
        if is_empty_slot(th) {
            continue;
        }
        if unpack_type(th) != InfoType::ThreatWarning as u8 {
            continue;
        }
        let source_region = pool.pkt_source_region[slot][i];
        if source_region != target_region {
            continue;
        }
        if source_region == own_region {
            continue;
        }
        let strength = pool.pkt_intensity[slot][i] as f32 / 255.0;
        if strength > best {
            best = strength;
        }
    }
    best
}

/// Deferred-backlog consumer: strongest nonlocal `threat_warning` packet whose
/// source region was held by `civ` when observed, i.e. news that the agent's
/// own civ took, defended or (as a new state) seceded with a distant region.
/// Packets from the agent's own region and without provenance are ignored.
pub fn strongest_own_civ_threat(pool: &AgentPool, slot: usize, own_region: u16, civ: u8) -> f32 {
    if civ == PKT_CIV_NONE {
        return 0.0;
    }
    let mut best: f32 = 0.0;
    for i in 0..agent::PACKET_SLOTS {
        let th = pool.pkt_type_and_hops[slot][i];
        if is_empty_slot(th) || unpack_type(th) != InfoType::ThreatWarning as u8 {
            continue;
        }
        if pool.pkt_source_region[slot][i] == own_region || pool.pkt_source_civ[slot][i] != civ {
            continue;
        }
        let strength = pool.pkt_intensity[slot][i] as f32 / 255.0;
        if strength > best {
            best = strength;
        }
    }
    best
}

/// Deferred-backlog consumer: strongest `religious_signal` packet about
/// `target_region` (own-region packets excluded, matching threat handling).
pub fn strongest_religious_signal_for_region(
    pool: &AgentPool,
    slot: usize,
    target_region: u16,
    own_region: u16,
) -> f32 {
    if target_region == own_region {
        return 0.0;
    }
    let mut best: f32 = 0.0;
    for i in 0..agent::PACKET_SLOTS {
        let th = pool.pkt_type_and_hops[slot][i];
        if is_empty_slot(th) || unpack_type(th) != InfoType::ReligiousSignal as u8 {
            continue;
        }
        if pool.pkt_source_region[slot][i] != target_region {
            continue;
        }
        let strength = pool.pkt_intensity[slot][i] as f32 / 255.0;
        if strength > best {
            best = strength;
        }
    }
    best
}

// ---------------------------------------------------------------------------
// Knowledge phase orchestrator (tick phase 0.95)
// ---------------------------------------------------------------------------

/// Run the full knowledge phase: decay → observe → propagate → commit → stats.
/// Clears `arrived_this_turn` as the last operation.
pub fn knowledge_phase(
    pool: &mut AgentPool,
    regions: &[RegionState],
    master_seed: &[u8; 32],
    turn: u32,
) -> KnowledgeStats {
    knowledge_phase_with_lookup(pool, regions, master_seed, turn, None)
}

/// Tick-only reuse from the same live identity set. Observation, propagation
/// and their ordering stay local to this phase; an empty pool builds no lookup.
pub(crate) fn knowledge_phase_with_lookup(
    pool: &mut AgentPool,
    regions: &[RegionState],
    master_seed: &[u8; 32],
    turn: u32,
    slot_lookup: Option<&crate::pool::IdSlots>,
) -> KnowledgeStats {
    // Collect alive slots
    let alive_slots: Vec<usize> = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s))
        .collect();
    knowledge_phase_for_slots(pool, regions, master_seed, turn, slot_lookup, &alive_slots)
}

/// Tick-only reuse of the all-live ascending set. No births, deaths, ID changes
/// or slot reuse may intervene since collection. Packet, location and
/// relationship values are read here at their original phases.
pub(crate) fn knowledge_phase_for_slots(
    pool: &mut AgentPool,
    regions: &[RegionState],
    master_seed: &[u8; 32],
    turn: u32,
    slot_lookup: Option<&crate::pool::IdSlots>,
    alive_slots: &[usize],
) -> KnowledgeStats {
    let mut stats = KnowledgeStats::default();
    let current_turn = turn as u16;
    if alive_slots.is_empty() {
        return stats;
    }

    // Step 1: Decay + expire
    stats.packets_expired = decay_packets(pool, alive_slots);

    // Step 2: Direct observation
    let (created, refreshed_obs, evicted_obs, dropped_obs, ct, ctr, cr) =
        observe_packets(pool, regions, alive_slots, current_turn);
    stats.packets_created = created;
    stats.packets_refreshed = refreshed_obs;
    stats.packets_evicted = evicted_obs;
    stats.packets_dropped = dropped_obs;
    stats.created_threat = ct;
    stats.created_trade = ctr;
    stats.created_religious = cr;
    let (news_created, news_refreshed, news_evicted, news_dropped) =
        observe_news(pool, regions, alive_slots, current_turn);
    stats.packets_created += news_created;
    stats.packets_refreshed += news_refreshed;
    stats.packets_evicted += news_evicted;
    stats.packets_dropped += news_dropped;
    stats.created_news = news_created;

    // Step 3: Propagation (buffered, reads post-observation snapshot)
    // Every live slot, the same entries as a map built from `alive_slots`.
    let fresh_lookup = if slot_lookup.is_none() { Some(pool.build_id_slots()) } else { None };
    let slot_lookup = slot_lookup.or(fresh_lookup.as_ref()).expect("knowledge slot lookup");

    let (buffer, transmitted, tt, ttr, tr) =
        propagate_packets(pool, alive_slots, master_seed, turn, slot_lookup);
    stats.packets_transmitted = transmitted;
    stats.transmitted_threat = tt;
    stats.transmitted_trade = ttr;
    stats.transmitted_religious = tr;
    stats.transmitted_news = buffer
        .iter()
        .filter(|b| b.candidate.info_type == InfoType::MovementNews as u8)
        .count() as u32;

    // Step 4: Commit buffered receives
    let (commit_refreshed, evicted, dropped) = commit_buffered(pool, buffer);
    stats.packets_refreshed += commit_refreshed;
    stats.packets_evicted += evicted;
    stats.packets_dropped += dropped;

    // Step 5: Compute post-commit live stats
    let mut total_age: u64 = 0;
    let mut total_hops: u64 = 0;
    let mut max_age: u32 = 0;
    let mut max_hops: u32 = 0;
    let mut live_count: u32 = 0;
    let mut agents_with: u32 = 0;

    for &slot in alive_slots {
        let mut has_packet = false;
        for i in 0..agent::PACKET_SLOTS {
            if !is_empty_slot(pool.pkt_type_and_hops[slot][i]) {
                has_packet = true;
                live_count += 1;
                let age = current_turn.saturating_sub(pool.pkt_source_turn[slot][i]) as u32;
                let hops = unpack_hops(pool.pkt_type_and_hops[slot][i]) as u32;
                total_age += age as u64;
                total_hops += hops as u64;
                if age > max_age { max_age = age; }
                if hops > max_hops { max_hops = hops; }
            }
        }
        if has_packet {
            agents_with += 1;
        }
    }

    stats.live_packet_count = live_count;
    stats.agents_with_packets = agents_with;
    stats.max_age = max_age;
    stats.max_hops = max_hops;
    if live_count > 0 {
        stats.mean_age = total_age as f32 / live_count as f32;
        stats.mean_hops = total_hops as f32 / live_count as f32;
    }

    // Clear arrival flags
    for &slot in alive_slots {
        pool.arrived_this_turn[slot] = false;
    }

    stats
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;
    use rand::Rng;
    use rand_chacha::ChaCha8Rng;

    /// The single-block roll equals a fresh `ChaCha8Rng`'s first `f32` on
    /// the same stream, bit for bit: random and edge seeds and streams,
    /// and the streams of real (sender, receiver, packet) tuples.
    #[test]
    fn transmission_roll_matches_chacha8rng() {
        let mut state = 0x9E37_79B9_7F4A_7C15u64;
        let mut next = || {
            state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
            let mut z = state;
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
            z ^ (z >> 31)
        };
        let mut seeds: Vec<[u8; 32]> = vec![[0u8; 32], [0xFF; 32], [42u8; 32]];
        for _ in 0..13 {
            let mut seed = [0u8; 32];
            for chunk in seed.chunks_mut(8) {
                chunk.copy_from_slice(&next().to_le_bytes());
            }
            seeds.push(seed);
        }
        for seed in &seeds {
            let key = chacha_key(seed);
            let mut streams: Vec<u64> = vec![0, 1, u32::MAX as u64, 1 << 32, u64::MAX];
            streams.extend((0..2_000).map(|_| next()));
            for sender in 1..20u64 {
                let mut h = sender;
                h = h.wrapping_mul(6364136223846793005).wrapping_add(sender * 7 + 1);
                h = h.wrapping_mul(6364136223846793005).wrapping_add(agent::KNOWLEDGE_STREAM_OFFSET);
                streams.push(h);
            }
            for &stream in &streams {
                let mut rng = ChaCha8Rng::from_seed(*seed);
                rng.set_stream(stream);
                let expected: f32 = rng.gen();
                assert_eq!(
                    chacha8_first_f32(&key, stream).to_bits(),
                    expected.to_bits(),
                    "seed {seed:?} stream {stream:#x}"
                );
            }
        }
    }

    #[test]
    fn test_knowledge_stream_via_set_stream_deterministic() {
        // V10: Verify that knowledge transmission RNG using set_stream()
        // produces deterministic results for the same input parameters.
        let seed = [42u8; 32];
        let gen_roll = |sender: u32, receiver: u32, info: u8, region: u16, sturn: u16, cturn: u32| -> f32 {
            let stream = {
                let mut h: u64 = sender as u64;
                h = h.wrapping_mul(6364136223846793005).wrapping_add(receiver as u64);
                h = h.wrapping_mul(6364136223846793005).wrapping_add(info as u64);
                h = h.wrapping_mul(6364136223846793005).wrapping_add(region as u64);
                h = h.wrapping_mul(6364136223846793005).wrapping_add(sturn as u64);
                h = h.wrapping_mul(6364136223846793005).wrapping_add(cturn as u64);
                h = h.wrapping_mul(6364136223846793005).wrapping_add(agent::KNOWLEDGE_STREAM_OFFSET);
                h
            };
            let mut rng = ChaCha8Rng::from_seed(seed);
            rng.set_stream(stream);
            rng.gen::<f32>()
        };

        // Same inputs → same result (deterministic)
        let a = gen_roll(1, 2, 1, 0, 5, 10);
        let b = gen_roll(1, 2, 1, 0, 5, 10);
        assert_eq!(a, b, "same inputs must produce identical rolls");

        // Different sender → different result
        let c = gen_roll(3, 2, 1, 0, 5, 10);
        assert_ne!(a, c, "different sender must produce different roll");

        // Different receiver → different result
        let d = gen_roll(1, 4, 1, 0, 5, 10);
        assert_ne!(a, d, "different receiver must produce different roll");

        // Different turn → different result
        let e = gen_roll(1, 2, 1, 0, 5, 11);
        assert_ne!(a, e, "different turn must produce different roll");
    }

    // --- guilds: movement news ---------------------------------------------------

    use crate::agent::Occupation;

    fn one_agent() -> (AgentPool, usize) {
        let mut pool = AgentPool::new(2);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, 0);
        (pool, slot)
    }

    fn cand(info_type: u8, source_region: u16, source_turn: u16, intensity: u8) -> PacketCandidate {
        PacketCandidate { info_type, source_region, source_turn, intensity, hop_count: 0 }
    }

    const NEWS: u8 = InfoType::MovementNews as u8;

    #[test]
    fn news_never_displaces_another_packet_and_yields_its_slot() {
        let (mut pool, s) = one_agent();
        for (t, r) in [(1u8, 1u16), (2, 2), (3, 3)] {
            assert_eq!(admit_packet(&mut pool, s, &cand(t, r, 5, 100)), AdmitResult::Inserted);
        }
        let code = news_code(0, NEWS_REFORM);
        assert_eq!(admit_packet_from_civ(&mut pool, s, &cand(NEWS, 9, 5, 200), code), AdmitResult::Inserted);
        // Full: newer news replaces the news slot only.
        assert_eq!(admit_packet_from_civ(&mut pool, s, &cand(NEWS, 8, 6, 200), code), AdmitResult::Evicted);
        let types: Vec<u8> = (0..4).map(|i| unpack_type(pool.pkt_type_and_hops[s][i])).collect();
        assert_eq!(types, vec![1, 2, 3, NEWS]);
        assert_eq!(pool.pkt_source_region[s][3], 8);
        // Older news is dropped; another type takes the news slot as if empty.
        assert_eq!(admit_packet_from_civ(&mut pool, s, &cand(NEWS, 7, 5, 255), code), AdmitResult::Dropped);
        assert_eq!(admit_packet(&mut pool, s, &cand(2, 4, 4, 60)), AdmitResult::Inserted);
        assert_eq!(unpack_type(pool.pkt_type_and_hops[s][3]), 2);
        // With four packets of other types, news finds no place.
        assert_eq!(admit_packet_from_civ(&mut pool, s, &cand(NEWS, 6, 9, 255), code), AdmitResult::Dropped);
        assert!((0..4).all(|i| unpack_type(pool.pkt_type_and_hops[s][i]) != NEWS));
    }

    #[test]
    fn with_or_without_news_the_other_packets_are_slot_for_slot_the_same() {
        // The same stream of threat/trade/religious packets, with news
        // interleaved in one pool: every slot either matches or is news where
        // the other pool's slot is empty.
        let (mut plain, a) = one_agent();
        let (mut mixed, b) = one_agent();
        let mut rng = ChaCha8Rng::seed_from_u64(17);
        for step in 0..400u32 {
            let turn = (step / 3) as u16;
            if rng.gen::<f32>() < 0.5 {
                let c = cand(rng.gen_range(1..=4), rng.gen_range(0..6), turn, rng.gen_range(1..=255));
                admit_packet_from_civ(&mut mixed, b, &c, news_code(rng.gen_range(0..4), rng.gen_range(0..4)));
                if c.info_type != NEWS {
                    admit_packet(&mut plain, a, &c);
                }
            }
            if rng.gen::<f32>() < 0.2 {
                decay_packets(&mut plain, &[a]);
                decay_packets(&mut mixed, &[b]);
            }
            for i in 0..agent::PACKET_SLOTS {
                let (tp, tm) = (pool_type(&plain, a, i), pool_type(&mixed, b, i));
                if tm == NEWS {
                    assert_eq!(tp, 0, "news holds a slot the plain pool uses (step {step})");
                    continue;
                }
                assert_eq!(plain.pkt_type_and_hops[a][i], mixed.pkt_type_and_hops[b][i], "step {step}");
                assert_eq!(plain.pkt_source_region[a][i], mixed.pkt_source_region[b][i]);
                assert_eq!(plain.pkt_source_turn[a][i], mixed.pkt_source_turn[b][i]);
                assert_eq!(plain.pkt_intensity[a][i], mixed.pkt_intensity[b][i]);
            }
        }
    }

    fn pool_type(pool: &AgentPool, slot: usize, i: usize) -> u8 {
        unpack_type(pool.pkt_type_and_hops[slot][i])
    }

    #[test]
    fn news_is_observed_only_where_a_region_has_it_and_read_by_creed() {
        let mut pool = AgentPool::new(4);
        let here = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, 0);
        let there = pool.spawn(1, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, 0);
        let mut regions = vec![RegionState::new(0), RegionState::new(1)];
        assert_eq!(observe_news(&mut pool, &regions, &[here, there], 3), (0, 0, 0, 0));
        regions[1].movement_news = news_code(1, NEWS_RISING);
        regions[1].movement_news_intensity = 180;
        assert_eq!(observe_news(&mut pool, &regions, &[here, there], 3).0, 1);
        assert_eq!(pool_type(&pool, there, 0), NEWS);
        assert_eq!(pool.pkt_source_civ[there][0], news_code(1, NEWS_RISING));
        assert_eq!(pool_type(&pool, here, 0), 0);
        // News from one's own region does not count; carried elsewhere it does.
        assert_eq!(movement_news_for_creed(&pool, there, 1), (0.0, 0.0));
        pool.regions[there] = 0;
        let (inspire, fear) = movement_news_for_creed(&pool, there, 1);
        assert!((inspire - 180.0 / 255.0).abs() < 1e-6 && fear == 0.0);
        assert_eq!(movement_news_for_creed(&pool, there, 0), (0.0, 0.0));
        assert_eq!((news_creed(news_code(3, 2)), news_kind(news_code(3, 2))), (3, 2));
        // Neighbours hear it at half the intensity.
        let mut pool = AgentPool::new(4);
        let near = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, 0);
        let far = pool.spawn(2, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 1, 2, 0);
        let mut regions = vec![RegionState::new(0), RegionState::new(1), RegionState::new(2)];
        regions[0].adjacency = vec![1];
        regions[1].adjacency = vec![0, 2];
        regions[2].adjacency = vec![1];
        regions[1].movement_news = news_code(0, NEWS_REFORM);
        regions[1].movement_news_intensity = 220;
        regions[2].movement_news = news_code(2, NEWS_FOUNDING);
        regions[2].movement_news_intensity = 120;
        assert_eq!(observe_news(&mut pool, &regions, &[near, far], 4).0, 3);
        assert_eq!((pool.pkt_source_region[near][0], pool.pkt_intensity[near][0]), (1, 110));
        assert_eq!(movement_news_for_creed(&pool, near, 0).0, 110.0 / 255.0);
        // The far agent: its own region's founding, then its neighbour's reform.
        assert_eq!((pool.pkt_source_region[far][0], pool.pkt_intensity[far][0]), (2, 120));
        assert_eq!((pool.pkt_source_region[far][1], pool.pkt_intensity[far][1]), (1, 110));
        // It decays at DECAY_NEWS and travels only on its own bonds.
        assert_eq!(decay_rate(NEWS), DECAY_NEWS);
        assert!(channel_weight(6, NEWS).is_some() && channel_weight(3, NEWS).is_none());
    }
}

// ---------------------------------------------------------------------------
// Exact checkpoint state (`crate::persist`): every field, in declaration order.
// ---------------------------------------------------------------------------

crate::persist_struct!(KnowledgeStats {
    packets_created, packets_refreshed, packets_transmitted, packets_expired, packets_evicted,
    packets_dropped, live_packet_count, agents_with_packets, created_threat, created_trade,
    created_religious, created_news, transmitted_threat, transmitted_trade,
    transmitted_religious, transmitted_news, mean_age, max_age, mean_hops, max_hops,
    merchant_plans_packet_driven, merchant_plans_bootstrap, merchant_no_usable_packets,
    migration_choices_changed_by_threat, migration_choices_changed_by_religion,
    loyalty_drifts_damped_by_rally,
});
