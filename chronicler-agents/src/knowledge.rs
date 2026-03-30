//! M59a: Information packet substrate — types, helpers, knowledge phase.

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
