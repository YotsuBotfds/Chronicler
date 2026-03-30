//! M59a: Information packet substrate — types, helpers, knowledge phase.

use crate::agent;
use crate::pool::AgentPool;
use crate::region::RegionState;
use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

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
}

impl InfoType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Empty),
            1 => Some(Self::ThreatWarning),
            2 => Some(Self::TradeOpportunity),
            3 => Some(Self::ReligiousSignal),
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

pub fn decay_rate(info_type: u8) -> u8 {
    match info_type {
        1 => DECAY_THREAT,
        2 => DECAY_TRADE,
        3 => DECAY_RELIGIOUS,
        _ => 0,
    }
}

// ---------------------------------------------------------------------------
// Propagation constants
// ---------------------------------------------------------------------------

pub const BASE_RATE_THREAT: f32 = 0.7;
pub const BASE_RATE_TRADE: f32 = 0.4;
pub const BASE_RATE_RELIGIOUS: f32 = 0.25;
pub const HOP_ATTENUATION: f32 = 0.85;

pub fn base_rate(info_type: u8) -> f32 {
    match info_type {
        1 => BASE_RATE_THREAT,
        2 => BASE_RATE_TRADE,
        3 => BASE_RATE_RELIGIOUS,
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

/// Minimum merchant_route_margin to emit a trade_opportunity packet.
pub const TRADE_MARGIN_THRESHOLD: f32 = 0.10;

/// Minimum conversion_rate to emit a religious_signal packet.
pub const CONVERSION_RATE_THRESHOLD: f32 = 0.05;

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
    pub transmitted_threat: u32,
    pub transmitted_trade: u32,
    pub transmitted_religious: u32,
    pub mean_age: f32,
    pub max_age: u32,
    pub mean_hops: f32,
    pub max_hops: u32,
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

/// Try to admit a packet into the agent's 4 slots.
/// Returns the admission outcome.
pub fn admit_packet(pool: &mut AgentPool, slot: usize, candidate: &PacketCandidate) -> AdmitResult {
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
                    return AdmitResult::Refreshed;
                }
            }
            // Incoming is older or weaker — drop
            return AdmitResult::Dropped;
        }
    }

    // Step 2: Check for empty slot
    for i in 0..agent::PACKET_SLOTS {
        if is_empty_slot(pool.pkt_type_and_hops[slot][i]) {
            pool.pkt_type_and_hops[slot][i] = pack_type_hops(info_type, candidate.hop_count);
            pool.pkt_source_region[slot][i] = source_region;
            pool.pkt_source_turn[slot][i] = candidate.source_turn;
            pool.pkt_intensity[slot][i] = candidate.intensity;
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
        || (candidate.source_turn == worst_turn && incoming_priority > worst_priority)
        || (candidate.source_turn == worst_turn && incoming_priority == worst_priority);

    if incoming_outranks {
        pool.pkt_type_and_hops[slot][worst_idx] = pack_type_hops(info_type, candidate.hop_count);
        pool.pkt_source_region[slot][worst_idx] = source_region;
        pool.pkt_source_turn[slot][worst_idx] = candidate.source_turn;
        pool.pkt_intensity[slot][worst_idx] = candidate.intensity;
        return AdmitResult::Evicted;
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
/// Returns (created_count, refreshed_count, created_threat, created_trade, created_religious).
pub fn observe_packets(
    pool: &mut AgentPool,
    regions: &[RegionState],
    alive_slots: &[usize],
    current_turn: u16,
) -> (u32, u32, u32, u32, u32) {
    let mut created = 0u32;
    let mut refreshed = 0u32;
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
            let result = admit_packet(pool, slot, &PacketCandidate {
                info_type: InfoType::ThreatWarning as u8,
                source_region: region.region_id,
                source_turn: current_turn,
                intensity: threat_intensity,
                hop_count: 0,
            });
            match result {
                AdmitResult::Inserted => { created += 1; created_threat += 1; }
                AdmitResult::Refreshed => { refreshed += 1; }
                _ => {}
            }
        }

        // --- Trade opportunity ---
        if pool.arrived_this_turn[slot] && region.merchant_route_margin > TRADE_MARGIN_THRESHOLD {
            let scaled = ((region.merchant_route_margin - TRADE_MARGIN_THRESHOLD) / 0.90 * 230.0) as u8;
            let intensity = scaled.max(50).min(230);
            let result = admit_packet(pool, slot, &PacketCandidate {
                info_type: InfoType::TradeOpportunity as u8,
                source_region: region.region_id,
                source_turn: current_turn,
                intensity,
                hop_count: 0,
            });
            match result {
                AdmitResult::Inserted => { created += 1; created_trade += 1; }
                AdmitResult::Refreshed => { refreshed += 1; }
                _ => {}
            }
        }

        // --- Religious signal ---
        let mut religious_intensity: u8 = 0;
        if region.persecution_intensity > 0.0 {
            let scaled = (region.persecution_intensity * 200.0) as u8;
            religious_intensity = religious_intensity.max(scaled.max(40).min(200));
        }
        if region.conversion_rate > CONVERSION_RATE_THRESHOLD {
            let scaled = (region.conversion_rate * 300.0) as u8;
            religious_intensity = religious_intensity.max(scaled.max(40).min(180));
        }
        if region.schism_convert_from != region.schism_convert_to
            && region.schism_convert_from != 255
        {
            religious_intensity = religious_intensity.max(INTENSITY_SCHISM);
        }
        if religious_intensity > 0 {
            let result = admit_packet(pool, slot, &PacketCandidate {
                info_type: InfoType::ReligiousSignal as u8,
                source_region: region.region_id,
                source_turn: current_turn,
                intensity: religious_intensity,
                hop_count: 0,
            });
            match result {
                AdmitResult::Inserted => { created += 1; created_religious += 1; }
                AdmitResult::Refreshed => { refreshed += 1; }
                _ => {}
            }
        }
    }

    (created, refreshed, created_threat, created_trade, created_religious)
}

// ---------------------------------------------------------------------------
// Propagation phase (buffered)
// ---------------------------------------------------------------------------

/// A buffered packet received during propagation, pending commit.
#[derive(Clone, Debug)]
pub struct BufferedReceive {
    pub receiver_slot: usize,
    pub candidate: PacketCandidate,
}

/// Run propagation: each agent tries to share non-empty packets with bonded agents.
/// Uses the post-observation snapshot. Returns (buffer, transmitted_count, transmitted_threat, transmitted_trade, transmitted_religious).
///
/// `slot_lookup` maps agent_id -> slot index for relationship target resolution.
pub fn propagate_packets(
    pool: &AgentPool,
    alive_slots: &[usize],
    master_seed: &[u8; 32],
    current_turn: u32,
    slot_lookup: &std::collections::HashMap<u32, usize>,
) -> (Vec<BufferedReceive>, u32, u32, u32, u32) {
    let mut buffer: Vec<BufferedReceive> = Vec::new();
    let mut transmitted = 0u32;
    let mut transmitted_threat = 0u32;
    let mut transmitted_trade = 0u32;
    let mut transmitted_religious = 0u32;

    for &sender_slot in alive_slots {
        let rel_count = pool.rel_count[sender_slot] as usize;
        if rel_count == 0 {
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

            // Collect unique receivers with their best eligible bond
            let mut best_per_receiver: std::collections::HashMap<usize, (f32, f32, i8, u8)> =
                std::collections::HashMap::new();

            for rel_idx in 0..rel_count {
                let target_id = pool.rel_target_ids[sender_slot][rel_idx];
                let bond_type = pool.rel_bond_types[sender_slot][rel_idx];
                let sentiment = pool.rel_sentiments[sender_slot][rel_idx];

                if bond_type == crate::relationships::EMPTY_BOND_TYPE {
                    continue;
                }

                let weight = match channel_weight(bond_type, info_type) {
                    Some(w) => w,
                    None => continue,
                };

                let receiver_slot = match slot_lookup.get(&target_id) {
                    Some(&s) if pool.is_alive(s) => s,
                    _ => continue,
                };

                let sentiment_factor = (sentiment.max(0) as f32) / 127.0;
                let chance = base_rate(info_type) * weight * sentiment_factor;

                let entry = best_per_receiver.entry(receiver_slot).or_insert((0.0, 0.0, 0, 255));
                if chance > entry.0
                    || (chance == entry.0 && weight > entry.1)
                    || (chance == entry.0 && weight == entry.1 && sentiment > entry.2)
                    || (chance == entry.0 && weight == entry.1 && sentiment == entry.2 && bond_type < entry.3)
                {
                    *entry = (chance, weight, sentiment, bond_type);
                }
            }

            for (&receiver_slot, &(chance, _, _, _)) in &best_per_receiver {
                if chance <= 0.0 {
                    continue;
                }

                let sender_id = pool.ids[sender_slot];
                let receiver_id = pool.ids[receiver_slot];

                let mut key_seed = *master_seed;
                let key_hash = {
                    let mut h: u64 = sender_id as u64;
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(receiver_id as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(info_type as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(source_region as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(source_turn as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(current_turn as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(agent::KNOWLEDGE_STREAM_OFFSET);
                    h
                };
                let hash_bytes = key_hash.to_le_bytes();
                for i in 0..8 {
                    key_seed[i] ^= hash_bytes[i];
                }
                let mut rng = ChaCha8Rng::from_seed(key_seed);
                let roll: f32 = rng.gen();

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
        let result = admit_packet(pool, receive.receiver_slot, &receive.candidate);
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
    let mut stats = KnowledgeStats::default();
    let current_turn = turn as u16;

    // Collect alive slots
    let alive_slots: Vec<usize> = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s))
        .collect();

    if alive_slots.is_empty() {
        return stats;
    }

    // Step 1: Decay + expire
    stats.packets_expired = decay_packets(pool, &alive_slots);

    // Step 2: Direct observation
    let (created, refreshed_obs, ct, ctr, cr) =
        observe_packets(pool, regions, &alive_slots, current_turn);
    stats.packets_created = created;
    stats.packets_refreshed = refreshed_obs;
    stats.created_threat = ct;
    stats.created_trade = ctr;
    stats.created_religious = cr;

    // Step 3: Propagation (buffered, reads post-observation snapshot)
    let slot_lookup: std::collections::HashMap<u32, usize> = alive_slots
        .iter()
        .map(|&s| (pool.ids[s], s))
        .collect();

    let (buffer, transmitted, tt, ttr, tr) =
        propagate_packets(pool, &alive_slots, master_seed, turn, &slot_lookup);
    stats.packets_transmitted = transmitted;
    stats.transmitted_threat = tt;
    stats.transmitted_trade = ttr;
    stats.transmitted_religious = tr;

    // Step 4: Commit buffered receives
    let (commit_refreshed, evicted, dropped) = commit_buffered(pool, buffer);
    stats.packets_refreshed += commit_refreshed;
    stats.packets_evicted = evicted;
    stats.packets_dropped = dropped;

    // Step 5: Compute post-commit live stats
    let mut total_age: u64 = 0;
    let mut total_hops: u64 = 0;
    let mut max_age: u32 = 0;
    let mut max_hops: u32 = 0;
    let mut live_count: u32 = 0;
    let mut agents_with: u32 = 0;

    for &slot in &alive_slots {
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
    for &slot in &alive_slots {
        pool.arrived_this_turn[slot] = false;
    }

    stats
}
