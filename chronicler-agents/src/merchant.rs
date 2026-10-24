//! M58a: Merchant mobility — shadow ledger, route graph, trip state machine.

use std::collections::VecDeque;

use crate::agent::{
    MAX_PATH_LEN, TRIP_PHASE_IDLE, TRIP_PHASE_LOADING, TRIP_PHASE_TRANSIT, TRIP_GOOD_SLOT_NONE,
};
use crate::economy::NUM_GOODS;
use crate::pool::AgentPool;
use crate::region::RegionState;

/// Shadow cargo ledger — tracks reservations and in-transit goods
/// without mutating macro stockpiles. Persistent across turns.
#[derive(Clone, Debug)]
pub struct ShadowLedger {
    pub reserved: Vec<[f32; NUM_GOODS]>,
    pub in_transit_out: Vec<[f32; NUM_GOODS]>,
    /// Cumulative monotonic counter — only incremented, never decremented.
    pub pending_delivery: Vec<[f32; NUM_GOODS]>,
}

impl ShadowLedger {
    pub fn new(num_regions: usize) -> Self {
        Self {
            reserved: vec![[0.0; NUM_GOODS]; num_regions],
            in_transit_out: vec![[0.0; NUM_GOODS]; num_regions],
            pending_delivery: vec![[0.0; NUM_GOODS]; num_regions],
        }
    }

    /// Available cargo for reservation at (region, slot).
    /// Returns max(0, stockpile - reserved - in_transit_out).
    pub fn available(&self, region: usize, slot: usize, stockpile: &[f32; NUM_GOODS]) -> f32 {
        (stockpile[slot] - self.reserved[region][slot] - self.in_transit_out[region][slot]).max(0.0)
    }

    /// Returns true if new reservations should be blocked (overcommitted).
    pub fn is_overcommitted(&self, region: usize, slot: usize, stockpile: &[f32; NUM_GOODS]) -> bool {
        self.reserved[region][slot] + self.in_transit_out[region][slot] > stockpile[slot]
    }

    /// Hybrid-mode availability: uses departure_debits instead of in_transit_out.
    /// Use when stockpile has already been debited for prior-turn departures.
    pub fn available_hybrid(&self, region: usize, slot: usize, stockpile: &[f32; NUM_GOODS], delivery_buf: &DeliveryBuffer) -> f32 {
        (stockpile[slot] - self.reserved[region][slot] - delivery_buf.departure_debits[region][slot]).max(0.0)
    }

    /// Hybrid-mode overcommitted check.
    pub fn is_overcommitted_hybrid(&self, region: usize, slot: usize, stockpile: &[f32; NUM_GOODS], delivery_buf: &DeliveryBuffer) -> bool {
        self.reserved[region][slot] + delivery_buf.departure_debits[region][slot] > stockpile[slot]
    }

    /// Reserve cargo for a Loading merchant.
    pub fn reserve(&mut self, region: usize, slot: usize, qty: f32) {
        self.reserved[region][slot] += qty;
    }

    /// Cancel a reservation (Loading → Idle on invalidation).
    pub fn cancel_reservation(&mut self, region: usize, slot: usize, qty: f32) {
        self.reserved[region][slot] = (self.reserved[region][slot] - qty).max(0.0);
    }

    /// Depart: move from reserved to in_transit_out (Loading → Transit).
    pub fn depart(&mut self, origin: usize, slot: usize, qty: f32, delivery_buf: Option<&mut DeliveryBuffer>) {
        self.reserved[origin][slot] = (self.reserved[origin][slot] - qty).max(0.0);
        self.in_transit_out[origin][slot] += qty;
        if let Some(buf) = delivery_buf {
            buf.record_departure(origin, slot, qty);
        }
    }

    /// Arrive: move from in_transit_out to pending_delivery (Transit → Idle via Arrived).
    pub fn arrive(&mut self, origin: usize, dest: usize, slot: usize, qty: f32, delivery_buf: Option<&mut DeliveryBuffer>) {
        self.in_transit_out[origin][slot] = (self.in_transit_out[origin][slot] - qty).max(0.0);
        self.pending_delivery[dest][slot] += qty;
        if let Some(buf) = delivery_buf {
            buf.record_arrival(origin as u16, dest as u16, slot as u8, qty);
        }
    }

    /// Seize: in-transit cargo taken by raiders (`LossReason::Raid`). It left
    /// its origin (the departure debit stands) and never arrives anywhere.
    pub fn seize(&mut self, origin: usize, slot: usize, qty: f32) {
        self.in_transit_out[origin][slot] = (self.in_transit_out[origin][slot] - qty).max(0.0);
    }

    /// Unwind: return in-transit cargo to origin (disruption).
    pub fn unwind(&mut self, origin: usize, slot: usize, qty: f32, delivery_buf: Option<&mut DeliveryBuffer>) {
        self.in_transit_out[origin][slot] = (self.in_transit_out[origin][slot] - qty).max(0.0);
        if let Some(buf) = delivery_buf {
            buf.record_return(origin, slot, qty);
        }
    }

    /// Clear all entries for a conquered region. Call AFTER unwinding impacted trips.
    pub fn clear_region(&mut self, region: usize) {
        self.reserved[region] = [0.0; NUM_GOODS];
        self.in_transit_out[region] = [0.0; NUM_GOODS];
        // pending_delivery is monotonic — do not clear
    }
}

/// Cumulative monotonic counters for delivery diagnostics.
/// Run-lifetime: initialized at AgentSimulator construction, never reset.
/// Per-turn deltas derived by diffing consecutive reads.
#[derive(Clone, Debug)]
pub struct DeliveryDiagnostics {
    pub total_departures: Vec<[f32; NUM_GOODS]>,
    pub total_arrivals: Vec<[f32; NUM_GOODS]>,
    pub total_returns: Vec<[f32; NUM_GOODS]>,
    pub total_transit_decay: Vec<[f32; NUM_GOODS]>,
}

impl DeliveryDiagnostics {
    pub fn new(num_regions: usize) -> Self {
        Self {
            total_departures: vec![[0.0; NUM_GOODS]; num_regions],
            total_arrivals: vec![[0.0; NUM_GOODS]; num_regions],
            total_returns: vec![[0.0; NUM_GOODS]; num_regions],
            total_transit_decay: vec![[0.0; NUM_GOODS]; num_regions],
        }
    }
}

/// Drainable delivery buffer — three streams with distinct accounting roles.
/// Consumed by economy kernel in hybrid mode. Cleared atomically on successful
/// economy tick. If economy tick fails, buffer preserved for retry.
#[derive(Clone, Debug)]
pub struct DeliveryBuffer {
    /// Physical stock rechecks apply only to the hybrid economy. Shadow mode
    /// uses the same buffer for diagnostics, but does not spend macro stocks.
    pub physical_stock: bool,
    /// Per-origin-region departure quantities (negative delta on origin stockpile).
    pub departure_debits: Vec<[f32; NUM_GOODS]>,
    /// Per-arrival: (source, dest, good, qty). Provenance required for M43b observability.
    pub arrival_imports: Vec<ArrivalRecord>,
    /// Per-origin-region return quantities (positive delta on origin stockpile, full value).
    pub return_credits: Vec<[f32; NUM_GOODS]>,
    /// Run-lifetime monotonic counters.
    pub diagnostics: DeliveryDiagnostics,
}

/// Single arrival record with source provenance.
#[derive(Clone, Debug)]
pub struct ArrivalRecord {
    pub source_region: u16,
    pub dest_region: u16,
    pub good_slot: u8,
    pub qty: f32,
}

impl DeliveryBuffer {
    pub fn new(num_regions: usize) -> Self {
        Self {
            physical_stock: false,
            departure_debits: vec![[0.0; NUM_GOODS]; num_regions],
            arrival_imports: Vec::new(),
            return_credits: vec![[0.0; NUM_GOODS]; num_regions],
            diagnostics: DeliveryDiagnostics::new(num_regions),
        }
    }

    pub fn record_departure(&mut self, origin: usize, slot: usize, qty: f32) {
        self.departure_debits[origin][slot] += qty;
        self.diagnostics.total_departures[origin][slot] += qty;
    }

    pub fn record_arrival(&mut self, source: u16, dest: u16, good_slot: u8, qty: f32) {
        self.arrival_imports.push(ArrivalRecord {
            source_region: source,
            dest_region: dest,
            good_slot,
            qty,
        });
        self.diagnostics.total_arrivals[dest as usize][good_slot as usize] += qty;
    }

    pub fn record_return(&mut self, origin: usize, slot: usize, qty: f32) {
        self.return_credits[origin][slot] += qty;
        self.diagnostics.total_returns[origin][slot] += qty;
    }

    /// Clear all drainable streams. Called after successful economy tick consumption,
    /// or to discard in non-hybrid modes. Diagnostics are NOT cleared (run-lifetime monotonic).
    pub fn clear(&mut self) {
        for arr in self.departure_debits.iter_mut() {
            *arr = [0.0; NUM_GOODS];
        }
        self.arrival_imports.clear();
        for arr in self.return_credits.iter_mut() {
            *arr = [0.0; NUM_GOODS];
        }
    }
}

/// Loss reason discriminant for loss tracking. `TransitDecay` is applied by
/// the economy kernel; `Raid` by the maritime sea-lane raids below (only when
/// the route graph carries raid risks).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum LossReason {
    TransitDecay = 0,
    Raid = 1,        // maritime: cargo seized on a sea lane
    Disruption = 2,  // dormant — M58b+
    Spoilage = 3,    // dormant — M58b+
}

/// Maritime: one merchant hop across a sea lane this tick (the sea-trade
/// measurement), and whether raiders seized the cargo on it.
#[derive(Clone, Debug, PartialEq)]
pub struct SeaCrossing {
    pub from_region: u16,
    pub to_region: u16,
    pub origin_region: u16,
    pub dest_region: u16,
    pub good_slot: u8,
    pub qty: f32,
    /// `Some(LossReason::Raid)` when the cargo was seized.
    pub loss: Option<LossReason>,
}

/// Per-turn diagnostics collected during the merchant mobility phase.
#[derive(Clone, Debug, Default)]
pub struct MerchantTripStats {
    pub active_trips: u32,
    pub completed_trips: u32,
    pub avg_trip_duration: f32,
    pub total_in_transit_qty: f32,
    pub route_utilization: f32,
    pub disruption_replans: u32,
    pub unwind_count: u32,
    pub stalled_trip_count: u32,
    pub overcommit_count: u32,
    // M59b: Packet-driven planning counters
    pub plans_packet_driven: u32,
    pub plans_bootstrap: u32,
    pub no_usable_packets: u32,
    // Maritime: this tick's sea-lane crossings (empty unless the graph has sea lanes).
    pub sea_log: Vec<SeaCrossing>,
    pub raided_trips: u32,
}

// ---------------------------------------------------------------------------
// Route graph — adjacency list built from Python edge-list batch
// ---------------------------------------------------------------------------

/// Adjacency list built from the Python edge-list batch.
#[derive(Clone, Debug)]
pub struct RouteGraph {
    /// For each region, list of (neighbor_region, is_river, transport_cost).
    pub adj: Vec<Vec<(u16, bool, f32)>>,
    pub num_regions: usize,
    /// Total directed edge count (for route_utilization normalization).
    pub edge_count: usize,
    /// Maritime: directed sea-lane edges and their per-crossing raid
    /// probability. Empty unless Python sent the optional `sea_raid_risk`
    /// column, in which case the mobility phase behaves exactly as before.
    pub sea_lanes: std::collections::HashMap<(u16, u16), f32>,
}

impl RouteGraph {
    pub fn from_edges(
        from_regions: &[u16],
        to_regions: &[u16],
        is_rivers: &[bool],
        transport_costs: &[f32],
        num_regions: usize,
    ) -> Self {
        let mut adj = vec![Vec::new(); num_regions];
        for i in 0..from_regions.len() {
            let from = from_regions[i] as usize;
            if from < num_regions {
                adj[from].push((to_regions[i], is_rivers[i], transport_costs[i]));
            }
        }
        // Sort adjacency lists for deterministic BFS
        for neighbors in &mut adj {
            neighbors.sort_by_key(|&(region, _, _)| region);
        }
        Self {
            adj,
            num_regions,
            edge_count: from_regions.len(),
            sea_lanes: std::collections::HashMap::new(),
        }
    }

    /// Maritime: mark sea-lane edges. Rows with a negative risk are land edges;
    /// a risk in [0, 1] is the chance raiders seize a cargo on that crossing.
    pub fn with_sea_lanes(mut self, from_regions: &[u16], to_regions: &[u16], risks: &[f32]) -> Self {
        for i in 0..from_regions.len().min(to_regions.len()).min(risks.len()) {
            let risk = risks[i];
            if risk >= 0.0 && risk.is_finite() {
                self.sea_lanes.insert((from_regions[i], to_regions[i]), risk.min(1.0));
            }
        }
        self
    }

    pub fn has_edge(&self, from: u16, to: u16) -> bool {
        let from_idx = from as usize;
        if from_idx >= self.num_regions {
            return false;
        }
        self.adj[from_idx].iter().any(|&(r, _, _)| r == to)
    }
}

// ---------------------------------------------------------------------------
// BFS and path tracing
// ---------------------------------------------------------------------------

/// BFS result table: distances and predecessor pointers from a single origin.
#[derive(Clone, Debug)]
pub struct PathTable {
    pub dist: Vec<u16>,
    pub pred: Vec<u16>,
}

/// Run BFS from `origin`, respecting `MAX_PATH_LEN` hop limit.
pub fn bfs_from(graph: &RouteGraph, origin: u16) -> PathTable {
    let n = graph.num_regions;
    let mut dist = vec![u16::MAX; n];
    let mut pred = vec![u16::MAX; n];
    let origin_idx = origin as usize;
    if origin_idx >= n {
        return PathTable { dist, pred };
    }
    dist[origin_idx] = 0;
    let mut queue = VecDeque::new();
    queue.push_back(origin_idx);
    while let Some(current) = queue.pop_front() {
        let current_dist = dist[current];
        if current_dist as usize >= MAX_PATH_LEN {
            continue;
        }
        for &(neighbor, _, _) in &graph.adj[current] {
            let ni = neighbor as usize;
            if ni < n && dist[ni] == u16::MAX {
                dist[ni] = current_dist + 1;
                pred[ni] = current as u16;
                queue.push_back(ni);
            }
        }
    }
    PathTable { dist, pred }
}

/// Trace a path from `origin` to `dest` using a BFS `PathTable`.
///
/// Returns `Some((path, hop_count))` where `path` is a fixed-size array
/// containing the intermediate + destination nodes (origin excluded),
/// or `None` if `dest` is unreachable or the path exceeds `MAX_PATH_LEN`.
pub fn trace_path(
    table: &PathTable,
    origin: u16,
    dest: u16,
) -> Option<([u16; MAX_PATH_LEN], u8)> {
    let dest_idx = dest as usize;
    if dest_idx >= table.dist.len() || table.dist[dest_idx] == u16::MAX {
        return None;
    }
    let hop_count = table.dist[dest_idx] as usize;
    if hop_count == 0 || hop_count > MAX_PATH_LEN {
        return None;
    }
    let mut path = [u16::MAX; MAX_PATH_LEN];
    let mut current = dest_idx;
    for i in (0..hop_count).rev() {
        path[i] = current as u16;
        current = table.pred[current] as usize;
    }
    if current != origin as usize {
        return None;
    }
    Some((path, hop_count as u8))
}

// ---------------------------------------------------------------------------
// Route selection and trip state machine
// ---------------------------------------------------------------------------

/// Minimum margin sum (origin + dest) for a trip to be worthwhile.
pub const MIN_TRIP_PROFIT: f32 = 0.05; // [CALIBRATE]
/// Maximum cargo a single merchant can carry per trip.
/// Keep aligned with the abstract economy's per-merchant carry budget so
/// realized mobility doesn't bake in a systematic volume surplus.
pub const MERCHANT_CARGO_CAP: f32 = 1.0; // [CALIBRATE]

// Correction (2026-10, food logistics): destinations are scored by what the
// destination pays for the cargo, not by its own export margin.
//
// `merchant_route_margin` is an origin-side signal: the average price gap
// from a region to its trade neighbours. M58a used it for the destination
// too ("bilateral market-activity proxy", a documented caveat M58b was to
// refine with goods-level prices), and M59 trade packets carry it as the
// destination's strength. A destination scored that way is attractive when it
// is *cheaper* than its neighbours: well supplied, or empty, since a region
// without people has no demand and every price 0 (hybrid template worlds:
// median margin 1.0, the clamp, in empty regions against 0.0 in fed ones).
// The cargo was the origin's largest stock whatever the destination needed.
// About a quarter of food deliveries landed in regions with no people and
// under a third in regions short of food.
//
// Food now travels by the food price gap, demand / supply = 1 / sufficiency
// (the economy's own post-trade price); other goods keep the activity proxy,
// which is all the planner knows about them, and never displace food. A
// region with no people is never a destination. Packets still decide which
// markets a merchant knows (M59b gating, unchanged); the price at a known
// market is read live, as M58b's perfect-information price source does.

/// Sufficiency floor in the planner's food price, the economy's supply floor
/// (`SUPPLY_FLOOR`) applied to sufficiency: a region with no food at all
/// prices it at 10.
pub const FOOD_PRICE_SUFFICIENCY_FLOOR: f32 = 0.1;
/// Scales a food price gap into the units of `merchant_route_margin` (the
/// economy's default `merchant_margin_normalizer`), so `MIN_TRIP_PROFIT`
/// means the same for food trips as for other trips.
pub const FOOD_PRICE_GAP_SCALE: f32 = 5.0;

/// The economy's food price in `region`: demand / supply, which is
/// 1 / food_sufficiency. A region without people has no demand and no price.
#[inline]
pub fn food_price(region: &RegionState) -> f32 {
    if region.population == 0 {
        return 0.0;
    }
    1.0 / region.food_sufficiency.max(FOOD_PRICE_SUFFICIENCY_FLOOR)
}

/// Score of carrying food from `origin` to `dest`: the food price gap in
/// margin units. Positive only where food is dearer at the destination.
#[inline]
pub fn food_trip_score(origin: &RegionState, dest: &RegionState) -> f32 {
    (food_price(dest) - food_price(origin)) / FOOD_PRICE_GAP_SCALE
}

#[inline]
fn is_food_slot(slot: usize) -> bool {
    slot < NUM_GOODS && crate::economy::GOOD_CATEGORY[slot] == crate::economy::CAT_FOOD
}

/// The good slot with the most uncommitted cargo at `origin` among the slots
/// `wanted` accepts (ties to the lower slot), with that quantity.
fn best_cargo_slot(
    origin: usize,
    regions: &[RegionState],
    ledger: &ShadowLedger,
    delivery_buf: Option<&DeliveryBuffer>,
    wanted: impl Fn(usize) -> bool,
) -> Option<(u8, f32)> {
    let mut best_slot: Option<u8> = None;
    let mut best_avail: f32 = 0.0;
    for slot in 0..8u8 {
        if !wanted(slot as usize) {
            continue;
        }
        let overcommitted = match delivery_buf {
            Some(buf) => ledger.is_overcommitted_hybrid(origin, slot as usize, &regions[origin].stockpile, buf),
            None => ledger.is_overcommitted(origin, slot as usize, &regions[origin].stockpile),
        };
        if overcommitted {
            continue;
        }
        let avail = match delivery_buf {
            Some(buf) => ledger.available_hybrid(origin, slot as usize, &regions[origin].stockpile, buf),
            None => ledger.available(origin, slot as usize, &regions[origin].stockpile),
        };
        if avail > best_avail || (avail == best_avail && best_slot.is_none_or(|s| slot < s)) {
            best_avail = avail;
            best_slot = Some(slot);
        }
    }
    best_slot.filter(|_| best_avail > 0.0).map(|s| (s, best_avail))
}

/// Best destination among `candidates` (region, score) above
/// `MIN_TRIP_PROFIT`, ties to the lower (region, agent) pair.
fn best_destination(
    agent_id: u32,
    candidates: impl Iterator<Item = (u16, f32)>,
) -> Option<u16> {
    let mut best_dest: Option<u16> = None;
    let mut best_score: f32 = MIN_TRIP_PROFIT;
    let mut best_tiebreak: (u16, u32) = (u16::MAX, u32::MAX);
    for (dest, score) in candidates {
        let tiebreak = (dest, agent_id);
        if score > best_score || (score == best_score && tiebreak < best_tiebreak) {
            best_score = score;
            best_dest = Some(dest);
            best_tiebreak = tiebreak;
        }
    }
    best_dest
}

fn trip_intent(
    agent_slot: usize,
    origin_region: u16,
    dest: u16,
    cargo: (u8, f32),
    path_table: &PathTable,
) -> Option<TripIntent> {
    let (path, path_len) = trace_path(path_table, origin_region, dest)?;
    Some(TripIntent {
        agent_slot,
        origin_region,
        dest_region: dest,
        good_slot: cargo.0,
        cargo_qty: cargo.1.min(MERCHANT_CARGO_CAP),
        path,
        path_len,
    })
}

/// A reservation intent collected during parallel evaluation,
/// applied in deterministic order.
#[derive(Clone, Debug)]
pub struct TripIntent {
    pub agent_slot: usize,
    pub origin_region: u16,
    pub dest_region: u16,
    pub good_slot: u8,
    pub cargo_qty: f32,
    pub path: [u16; MAX_PATH_LEN],
    pub path_len: u8,
}

/// Evaluate route candidates for an idle merchant at `origin_region`.
/// Returns a TripIntent if a profitable route with available cargo exists.
/// When `delivery_buf` is `Some`, uses hybrid availability (departure_debits).
pub fn evaluate_route(
    agent_slot: usize,
    agent_id: u32,
    origin_region: u16,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
    delivery_buf: Option<&DeliveryBuffer>,
) -> Option<TripIntent> {
    let origin = origin_region as usize;
    if origin >= regions.len() {
        return None;
    }
    let reachable = || {
        path_table.dist.iter().enumerate()
            .filter(|&(dest, &dist)| dist != 0 && dist != u16::MAX && regions[dest].population > 0)
            .map(|(dest, _)| dest as u16)
    };

    // Food goes where it is dearer than at home.
    if let Some(cargo) = best_cargo_slot(origin, regions, ledger, delivery_buf, is_food_slot) {
        let scored = reachable()
            .map(|d| (d, food_trip_score(&regions[origin], &regions[d as usize])));
        if let Some(dest) = best_destination(agent_id, scored) {
            if let Some(intent) = trip_intent(agent_slot, origin_region, dest, cargo, path_table) {
                return Some(intent);
            }
        }
    }

    // Other goods by the market-activity proxy.
    let origin_margin = regions[origin].merchant_route_margin;
    let scored = reachable()
        .map(|d| (d, origin_margin + regions[d as usize].merchant_route_margin));
    let dest = best_destination(agent_id, scored)?;
    let cargo = best_cargo_slot(origin, regions, ledger, delivery_buf, |s| !is_food_slot(s))?;
    trip_intent(agent_slot, origin_region, dest, cargo, path_table)
}

/// M59b: Packet-gated route evaluation. When usable nonlocal trade packets
/// exist (after reachability filtering), only packet-known destinations are
/// candidates. Falls back to oracle (evaluate_route) when usable set is empty.
///
/// Returns (Option<TripIntent>, had_usable_packets: bool).
/// Counter increments happen in merchant_mobility_phase AFTER apply_trip_intent
/// succeeds, not here — "successful plan" means surviving reservation.
pub fn evaluate_route_packet_aware(
    agent_slot: usize,
    agent_id: u32,
    origin_region: u16,
    pool: &AgentPool,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
    delivery_buf: Option<&DeliveryBuffer>,
) -> (Option<TripIntent>, bool) {
    let origin = origin_region as usize;
    if origin >= regions.len() {
        return (None, false);
    }

    // Collect usable nonlocal trade packets
    let raw_packets = crate::knowledge::usable_trade_packets(pool, agent_slot, origin_region);

    // Reachability filter: only keep packets whose source_region is reachable
    let reachable_packets: Vec<(u16, f32)> = raw_packets
        .into_iter()
        .filter(|&(src_region, _)| {
            let idx = src_region as usize;
            idx < path_table.dist.len()
                && path_table.dist[idx] != 0
                && path_table.dist[idx] != u16::MAX
        })
        .collect();

    if reachable_packets.is_empty() {
        // Bootstrap fallback: no usable packets, use oracle planner
        let intent = evaluate_route(
            agent_slot, agent_id, origin_region, regions, path_table, ledger, delivery_buf,
        );
        return (intent, false); // false = no usable packets
    }

    // Packet-gated planning: only packet-known markets are candidates, and
    // when none is worth the trip there is no oracle fallback
    // (anti-omniscience rule). A market needs people to sell to.
    let known = || {
        reachable_packets.iter()
            .copied()
            .filter(|&(src_region, _)| regions[src_region as usize].population > 0)
    };

    // Food goes to a known market where it is dearer than at home.
    if let Some(cargo) = best_cargo_slot(origin, regions, ledger, delivery_buf, is_food_slot) {
        let scored = known()
            .map(|(d, _)| (d, food_trip_score(&regions[origin], &regions[d as usize])));
        if let Some(dest) = best_destination(agent_id, scored) {
            if let Some(intent) = trip_intent(agent_slot, origin_region, dest, cargo, path_table) {
                return (Some(intent), true);
            }
        }
    }

    // Other goods by the packet's strength (market-activity proxy).
    let origin_margin = regions[origin].merchant_route_margin;
    let scored = known().map(|(d, packet_strength)| (d, origin_margin + packet_strength));
    let intent = best_destination(agent_id, scored).and_then(|dest| {
        let cargo = best_cargo_slot(origin, regions, ledger, delivery_buf, |s| !is_food_slot(s))?;
        trip_intent(agent_slot, origin_region, dest, cargo, path_table)
    });
    (intent, true) // true = had usable packets
}

/// Apply a trip intent to the pool and shadow ledger.
/// Re-checks availability at apply time (two-phase model).
/// When `delivery_buf` is `Some`, uses hybrid availability (departure_debits).
/// Returns true if the reservation was committed, false if rejected.
pub fn apply_trip_intent(
    intent: &TripIntent,
    pool: &mut AgentPool,
    ledger: &mut ShadowLedger,
    regions: &[RegionState],
    stats: &mut MerchantTripStats,
    delivery_buf: Option<&DeliveryBuffer>,
) -> bool {
    let origin = intent.origin_region as usize;
    let slot = intent.good_slot as usize;

    // Re-check at apply time
    let overcommitted = match delivery_buf {
        Some(buf) => ledger.is_overcommitted_hybrid(origin, slot, &regions[origin].stockpile, buf),
        None => ledger.is_overcommitted(origin, slot, &regions[origin].stockpile),
    };
    if overcommitted {
        stats.overcommit_count += 1;
        return false;
    }
    let avail = match delivery_buf {
        Some(buf) => ledger.available_hybrid(origin, slot, &regions[origin].stockpile, buf),
        None => ledger.available(origin, slot, &regions[origin].stockpile),
    };
    if avail <= 0.0 {
        stats.overcommit_count += 1;
        return false;
    }
    let qty = avail.min(intent.cargo_qty);

    // Commit reservation
    ledger.reserve(origin, slot, qty);

    // Update pool fields
    let s = intent.agent_slot;
    pool.trip_phase[s] = TRIP_PHASE_LOADING;
    pool.trip_dest_region[s] = intent.dest_region;
    pool.trip_origin_region[s] = intent.origin_region;
    pool.trip_good_slot[s] = intent.good_slot;
    pool.trip_cargo_qty[s] = qty;
    pool.trip_turns_elapsed[s] = 0;
    pool.trip_path[s] = intent.path;
    pool.trip_path_len[s] = intent.path_len;
    pool.trip_path_cursor[s] = 0;

    true
}

/// Advance a Transit merchant one hop along their path.
/// Updates region and spatial position via transit_entry_position.
/// Returns the new region, or None if arrived.
pub fn advance_one_hop(pool: &mut AgentPool, slot: usize, master_seed: &[u8; 32]) -> Option<u16> {
    let cursor = pool.trip_path_cursor[slot] as usize;
    let len = pool.trip_path_len[slot] as usize;
    if cursor >= len {
        return None; // already at destination
    }

    let from_region = pool.regions[slot];
    let next_region = pool.trip_path[slot][cursor];
    pool.regions[slot] = next_region;
    pool.trip_path_cursor[slot] += 1;
    pool.trip_turns_elapsed[slot] += 1;

    // Set spatial position at edge entry point
    let seed_u64 = u64::from_le_bytes(master_seed[..8].try_into().unwrap());
    let (x, y) = crate::spatial::transit_entry_position(seed_u64, next_region, from_region);
    pool.x[slot] = x;
    pool.y[slot] = y;

    if (pool.trip_path_cursor[slot] as usize) >= len {
        None // arrived at destination
    } else {
        Some(next_region) // still in transit
    }
}

/// Transition Loading -> Transit (departure).
/// Validates the next hop. For physical (hybrid-economy) cargo it also rechecks
/// inventory after intervening economy consumption/decay: a stale reservation
/// shrinks to what is still backed or is canceled, never creating a return.
/// Shadow-mode cargo is virtual (the abstract economy owns macro stocks), so
/// its reservation departs unchanged.
pub fn depart_merchant(
    pool: &mut AgentPool,
    slot: usize,
    graph: &RouteGraph,
    regions: &[RegionState],
    ledger: &mut ShadowLedger,
    delivery_buf: Option<&mut DeliveryBuffer>,
) -> bool {
    let cursor = pool.trip_path_cursor[slot] as usize;
    let next_hop = pool.trip_path[slot][cursor];
    let current = pool.regions[slot];

    if !graph.has_edge(current, next_hop) {
        // Route invalidated before departure — cancel
        let origin = pool.trip_origin_region[slot] as usize;
        let good = pool.trip_good_slot[slot] as usize;
        ledger.cancel_reservation(origin, good, pool.trip_cargo_qty[slot]);
        reset_trip_fields(pool, slot);
        return false;
    }

    let origin = pool.trip_origin_region[slot] as usize;
    let good = pool.trip_good_slot[slot] as usize;
    let mut qty = pool.trip_cargo_qty[slot];
    if let Some(buf) = delivery_buf.as_deref().filter(|buf| buf.physical_stock) {
        // Loading reservations span turns, while the economy may consume or
        // decay stock in between. Release this reservation before measuring
        // availability, so only other Loading cargo and departures queued but
        // not yet debited (including earlier merchants this turn) are withheld.
        // Afterwards reserved + pending debits never exceed physical stock.
        ledger.cancel_reservation(origin, good, qty);
        let available = ledger.available_hybrid(origin, good, &regions[origin].stockpile, buf);
        qty = qty.min(available);
        if qty <= 0.0 {
            reset_trip_fields(pool, slot);
            return false;
        }
        pool.trip_cargo_qty[slot] = qty;
        ledger.reserve(origin, good, qty);
    }
    // Depart: reserved -> in_transit. Physical macro stock is debited once,
    // when the following economy tick consumes the delivery buffer.
    ledger.depart(origin, good, qty, delivery_buf);
    pool.trip_phase[slot] = TRIP_PHASE_TRANSIT;
    true
}

/// Send this turn's delivering merchants back to the region they set out from.
///
/// Called by the tick after the 0.95 knowledge phase, so an arrival still
/// observes the destination market (M59a) before the merchant leaves it.
/// Correction (2026-10, food balance): a merchant used to stay wherever it
/// delivered, so every completed trip permanently moved one person (and one
/// mouth) from the exporting region to the importing one, split households,
/// and left the exporter short of merchants, which it re-recruited from its
/// farmers. The return leg itself is not simulated: the outbound trip time
/// is unchanged, and the merchant plans its next trip from home the
/// following turn.
pub fn return_delivering_merchants_home(pool: &mut AgentPool, master_seed: &[u8; 32]) {
    let seed_u64 = u64::from_le_bytes(master_seed[..8].try_into().unwrap());
    for slot in 0..pool.capacity() {
        let home = pool.trip_home_region[slot];
        if home == crate::agent::TRIP_HOME_NONE {
            continue;
        }
        pool.trip_home_region[slot] = crate::agent::TRIP_HOME_NONE;
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_IDLE {
            continue;
        }
        let market = pool.regions[slot];
        if market == home {
            continue;
        }
        pool.regions[slot] = home;
        let (x, y) = crate::spatial::transit_entry_position(seed_u64, home, market);
        pool.x[slot] = x;
        pool.y[slot] = y;
    }
}

/// Reset all trip fields to Idle state.
pub fn reset_trip_fields(pool: &mut AgentPool, slot: usize) {
    pool.trip_phase[slot] = TRIP_PHASE_IDLE;
    pool.trip_dest_region[slot] = 0;
    pool.trip_origin_region[slot] = 0;
    pool.trip_good_slot[slot] = TRIP_GOOD_SLOT_NONE;
    pool.trip_cargo_qty[slot] = 0.0;
    pool.trip_turns_elapsed[slot] = 0;
    pool.trip_path[slot] = [u16::MAX; MAX_PATH_LEN];
    pool.trip_path_len[slot] = 0;
    pool.trip_path_cursor[slot] = 0;
}

/// Release a dying agent's active trip before its pool slot can be reused.
pub(crate) fn release_trip_on_death(
    pool: &mut AgentPool,
    slot: usize,
    ledger: &mut ShadowLedger,
    delivery_buf: &mut DeliveryBuffer,
) {
    let origin = pool.trip_origin_region[slot] as usize;
    let good = pool.trip_good_slot[slot] as usize;
    let qty = pool.trip_cargo_qty[slot];
    match pool.trip_phase[slot] {
        TRIP_PHASE_LOADING => ledger.cancel_reservation(origin, good, qty),
        TRIP_PHASE_TRANSIT => ledger.unwind(origin, good, qty, Some(delivery_buf)),
        _ => return,
    }
    reset_trip_fields(pool, slot);
}

// ---------------------------------------------------------------------------
// Conquest / controller-change unwind
// ---------------------------------------------------------------------------

/// Handle conquest/controller-change: identify impacted trips, unwind, clear residuals.
/// Must be called when a region changes controller, BEFORE the merchant mobility phase.
/// `conquered_regions` contains indices of regions that changed controller this turn.
pub fn conquest_unwind(
    pool: &mut AgentPool,
    ledger: &mut ShadowLedger,
    conquered_regions: &[u16],
    stats: &mut MerchantTripStats,
    mut delivery_buf: Option<&mut DeliveryBuffer>,
) {
    let conquered_set: std::collections::HashSet<u16> = conquered_regions.iter().copied().collect();
    if conquered_set.is_empty() {
        return;
    }

    let cap = pool.capacity();
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] == TRIP_PHASE_IDLE {
            continue;
        }
        let origin = pool.trip_origin_region[slot];
        let dest = pool.trip_dest_region[slot];
        let current = pool.regions[slot];
        if !conquered_set.contains(&origin)
            && !conquered_set.contains(&dest)
            && !conquered_set.contains(&current)
        {
            continue;
        }
        let good = pool.trip_good_slot[slot] as usize;
        let qty = pool.trip_cargo_qty[slot];
        let origin_idx = origin as usize;
        match pool.trip_phase[slot] {
            TRIP_PHASE_LOADING => {
                ledger.cancel_reservation(origin_idx, good, qty);
            }
            TRIP_PHASE_TRANSIT => {
                ledger.unwind(origin_idx, good, qty, delivery_buf.as_deref_mut());
                stats.unwind_count += 1;
            }
            _ => {}
        }
        reset_trip_fields(pool, slot);
    }
    for &region in conquered_regions {
        ledger.clear_region(region as usize);
    }
}

// ---------------------------------------------------------------------------
// Full mobility phase orchestration
// ---------------------------------------------------------------------------

/// Maritime: deterministic raid roll for one merchant crossing one sea lane.
/// Same composite-stream discipline as knowledge transmission.
pub fn raid_roll(master_seed: &[u8; 32], turn: u32, agent_id: u32, from: u16, to: u16) -> f32 {
    use rand::Rng;
    use rand::SeedableRng;
    let stream = {
        let mut h: u64 = agent_id as u64;
        h = h.wrapping_mul(6364136223846793005).wrapping_add(from as u64);
        h = h.wrapping_mul(6364136223846793005).wrapping_add(to as u64);
        h = h.wrapping_mul(6364136223846793005).wrapping_add(turn as u64);
        h = h.wrapping_mul(6364136223846793005).wrapping_add(crate::agent::MERCHANT_RAID_STREAM_OFFSET);
        h
    };
    let mut rng = rand_chacha::ChaCha8Rng::from_seed(*master_seed);
    rng.set_stream(stream);
    rng.gen()
}

/// Run the full merchant mobility phase. Called at step 0.9 in tick_agents.
/// Processes: disruption -> departures -> movement -> arrivals -> route eval -> reservations.
pub fn merchant_mobility_phase(
    pool: &mut AgentPool,
    regions: &[RegionState],
    graph: &RouteGraph,
    ledger: &mut ShadowLedger,
    master_seed: &[u8; 32],
    delivery_buf: Option<&mut DeliveryBuffer>,
) -> MerchantTripStats {
    merchant_mobility_phase_at(pool, regions, graph, ledger, master_seed, 0, delivery_buf)
}

/// [`merchant_mobility_phase`] for a given turn (seeds the maritime raid
/// rolls; nothing else reads the turn).
pub fn merchant_mobility_phase_at(
    pool: &mut AgentPool,
    regions: &[RegionState],
    graph: &RouteGraph,
    ledger: &mut ShadowLedger,
    master_seed: &[u8; 32],
    turn: u32,
    mut delivery_buf: Option<&mut DeliveryBuffer>,
) -> MerchantTripStats {
    let mut stats = MerchantTripStats::default();
    let cap = pool.capacity();
    // Arrival flags and pending returns belong to this turn's arrivals only
    // (the tick consumes both after the knowledge phase; direct callers of
    // this phase may not).
    for slot in 0..cap {
        pool.arrived_this_turn[slot] = false;
        pool.trip_home_region[slot] = crate::agent::TRIP_HOME_NONE;
    }

    // Phase a-b: Disruption check + replan/unwind for Transit merchants
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_TRANSIT { continue; }
        let cursor = pool.trip_path_cursor[slot] as usize;
        let len = pool.trip_path_len[slot] as usize;
        if cursor >= len { continue; }
        let current = pool.regions[slot];
        let next_hop = pool.trip_path[slot][cursor];
        if !graph.has_edge(current, next_hop) {
            let dest = pool.trip_dest_region[slot];
            let table = bfs_from(graph, current);
            if let Some((new_path, new_len)) = trace_path(&table, current, dest) {
                pool.trip_path[slot] = new_path;
                pool.trip_path_len[slot] = new_len;
                pool.trip_path_cursor[slot] = 0;
                stats.disruption_replans += 1;
            } else {
                let origin = pool.trip_origin_region[slot] as usize;
                let good = pool.trip_good_slot[slot] as usize;
                ledger.unwind(origin, good, pool.trip_cargo_qty[slot], delivery_buf.as_deref_mut());
                stats.stalled_trip_count += 1;
                stats.unwind_count += 1;
                reset_trip_fields(pool, slot);
            }
        }
    }

    // Phase c: Loading invalidation + departure
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_LOADING { continue; }
        // Physical (hybrid) cargo is revalidated inside depart_merchant.
        depart_merchant(pool, slot, graph, regions, ledger, delivery_buf.as_deref_mut());
    }

    // Phase d-e: Advance Transit merchants + process arrivals
    let mut arrivals: Vec<usize> = Vec::new();
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_TRANSIT { continue; }
        if !graph.sea_lanes.is_empty() {
            // Maritime: log the sea crossing; raiders may seize the cargo.
            let cursor = pool.trip_path_cursor[slot] as usize;
            if cursor < pool.trip_path_len[slot] as usize {
                let from = pool.regions[slot];
                let to = pool.trip_path[slot][cursor];
                if let Some(&risk) = graph.sea_lanes.get(&(from, to)) {
                    let origin = pool.trip_origin_region[slot];
                    let good = pool.trip_good_slot[slot];
                    let qty = pool.trip_cargo_qty[slot];
                    let raided = risk > 0.0
                        && raid_roll(master_seed, turn, pool.ids[slot], from, to) < risk;
                    stats.sea_log.push(SeaCrossing {
                        from_region: from,
                        to_region: to,
                        origin_region: origin,
                        dest_region: pool.trip_dest_region[slot],
                        good_slot: good,
                        qty,
                        loss: if raided { Some(LossReason::Raid) } else { None },
                    });
                    if raided {
                        ledger.seize(origin as usize, good as usize, qty);
                        stats.raided_trips += 1;
                        reset_trip_fields(pool, slot);
                        // Like a delivering merchant, the robbed one goes home
                        // (return_delivering_merchants_home) and plans from there.
                        pool.trip_home_region[slot] = origin;
                        continue;
                    }
                }
            }
        }
        if advance_one_hop(pool, slot, master_seed).is_none() {
            arrivals.push(slot);
        }
    }
    for slot in arrivals {
        let origin = pool.trip_origin_region[slot] as usize;
        let dest = pool.trip_dest_region[slot] as usize;
        let good = pool.trip_good_slot[slot] as usize;
        let qty = pool.trip_cargo_qty[slot];
        ledger.arrive(origin, dest, good, qty, delivery_buf.as_deref_mut());
        let duration = pool.trip_turns_elapsed[slot];
        stats.completed_trips += 1;
        stats.avg_trip_duration += duration as f32;
        pool.arrived_this_turn[slot] = true;
        // The merchant goes home after delivering (see
        // return_delivering_merchants_home); it plans its next trip from there.
        pool.trip_home_region[slot] = origin as u16;
        reset_trip_fields(pool, slot);
    }
    if stats.completed_trips > 0 {
        stats.avg_trip_duration /= stats.completed_trips as f32;
    }

    // Phase f-g: Route evaluation for idle merchants + cargo reservation
    // M59b: Use packet-aware route evaluation (packet-gated with bootstrap fallback)
    let mut origin_tables: std::collections::HashMap<u16, PathTable> = std::collections::HashMap::new();
    let mut intents: Vec<(TripIntent, bool)> = Vec::new(); // (intent, had_usable_packets)
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_IDLE { continue; }
        if pool.occupations[slot] != crate::agent::Occupation::Merchant as u8 { continue; }
        // A merchant that delivered this turn is still at the market; it
        // returns home before planning again.
        if pool.trip_home_region[slot] != crate::agent::TRIP_HOME_NONE { continue; }
        let origin = pool.regions[slot];
        let table = origin_tables.entry(origin).or_insert_with(|| bfs_from(graph, origin));
        let (intent, had_packets) = evaluate_route_packet_aware(
            slot, pool.ids[slot], origin, pool, regions, table, ledger,
            delivery_buf.as_deref(),
        );
        if !had_packets {
            stats.no_usable_packets += 1;
        }
        if let Some(i) = intent {
            intents.push((i, had_packets));
        }
    }
    intents.sort_by_key(|(i, _)| (i.origin_region, pool.ids[i.agent_slot]));
    for (intent, had_packets) in &intents {
        let applied = apply_trip_intent(intent, pool, ledger, regions, &mut stats, delivery_buf.as_deref());
        if applied {
            if *had_packets {
                stats.plans_packet_driven += 1;
            } else {
                stats.plans_bootstrap += 1;
            }
        }
    }

    // Phase h: Collect final diagnostics
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_TRANSIT { continue; }
        stats.active_trips += 1;
        stats.total_in_transit_qty += pool.trip_cargo_qty[slot];
    }
    if graph.edge_count > 0 {
        stats.route_utilization = stats.completed_trips as f32 / graph.edge_count as f32;
    }
    stats
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_shadow_ledger_availability() {
        let mut ledger = ShadowLedger::new(2);
        let stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        assert_eq!(ledger.available(0, 0, &stockpile), 10.0);
        ledger.reserve(0, 0, 3.0);
        assert_eq!(ledger.available(0, 0, &stockpile), 7.0);
        ledger.depart(0, 0, 3.0, None);
        assert_eq!(ledger.available(0, 0, &stockpile), 7.0); // reserved→in_transit, same total
    }

    #[test]
    fn test_shadow_ledger_two_sided_accounting() {
        let mut ledger = ShadowLedger::new(2);
        ledger.reserve(0, 0, 5.0);
        assert_eq!(ledger.reserved[0][0], 5.0);
        ledger.depart(0, 0, 5.0, None);
        assert_eq!(ledger.reserved[0][0], 0.0);
        assert_eq!(ledger.in_transit_out[0][0], 5.0);
        ledger.arrive(0, 1, 0, 5.0, None);
        assert_eq!(ledger.in_transit_out[0][0], 0.0);
        assert_eq!(ledger.pending_delivery[1][0], 5.0);
    }

    #[test]
    fn test_shadow_ledger_unwind() {
        let mut ledger = ShadowLedger::new(2);
        ledger.reserve(0, 0, 5.0);
        ledger.depart(0, 0, 5.0, None);
        ledger.unwind(0, 0, 5.0, None);
        assert_eq!(ledger.in_transit_out[0][0], 0.0);
        assert_eq!(ledger.pending_delivery[0][0], 0.0);
    }

    #[test]
    fn test_shadow_ledger_overcommit_guard() {
        let mut ledger = ShadowLedger::new(1);
        let stockpile = [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        ledger.reserve(0, 0, 6.0);
        ledger.depart(0, 0, 6.0, None);
        assert!(!ledger.is_overcommitted(0, 0, &stockpile)); // 6 < 10
        ledger.reserve(0, 0, 5.0);
        assert!(ledger.is_overcommitted(0, 0, &stockpile)); // 6+5 = 11 > 10
    }

    #[test]
    fn test_shadow_ledger_cancel_reservation() {
        let mut ledger = ShadowLedger::new(1);
        ledger.reserve(0, 0, 5.0);
        ledger.cancel_reservation(0, 0, 5.0);
        assert_eq!(ledger.reserved[0][0], 0.0);
    }

    #[test]
    fn test_shadow_ledger_clear_region() {
        let mut ledger = ShadowLedger::new(2);
        ledger.reserve(0, 0, 5.0);
        ledger.reserve(0, 1, 3.0);
        ledger.depart(0, 0, 2.0, None);
        ledger.arrive(0, 1, 0, 2.0, None);
        ledger.clear_region(0);
        assert_eq!(ledger.reserved[0], [0.0; NUM_GOODS]);
        assert_eq!(ledger.in_transit_out[0], [0.0; NUM_GOODS]);
        // pending_delivery is monotonic — NOT cleared
        assert_eq!(ledger.pending_delivery[1][0], 2.0);
    }

    // -------------------------------------------------------------------
    // Route graph tests
    // -------------------------------------------------------------------

    #[test]
    fn test_route_graph_from_edges() {
        let graph = RouteGraph::from_edges(
            &[0, 1, 1, 2],
            &[1, 0, 2, 1],
            &[false; 4],
            &[1.0; 4],
            3,
        );
        assert!(graph.has_edge(0, 1));
        assert!(graph.has_edge(1, 2));
        assert!(!graph.has_edge(0, 2));
        assert_eq!(graph.edge_count, 4);
    }

    #[test]
    fn test_bfs_shortest_path() {
        // 0-1, 1-2 bidirectional, plus 0-2 direct
        let graph = RouteGraph::from_edges(
            &[0, 1, 1, 2, 0, 2],
            &[1, 0, 2, 1, 2, 0],
            &[false; 6],
            &[1.0; 6],
            3,
        );
        let table = bfs_from(&graph, 0);
        assert_eq!(table.dist[0], 0);
        assert_eq!(table.dist[1], 1);
        assert_eq!(table.dist[2], 1); // direct edge 0→2
    }

    #[test]
    fn test_bfs_max_path_len_limit() {
        // Linear chain: 0-1-2-...-19
        let n = 20;
        let mut from_r = Vec::new();
        let mut to_r = Vec::new();
        for i in 0..n - 1 {
            from_r.push(i as u16);
            to_r.push((i + 1) as u16);
            from_r.push((i + 1) as u16);
            to_r.push(i as u16);
        }
        let edge_count = from_r.len();
        let graph = RouteGraph::from_edges(
            &from_r,
            &to_r,
            &vec![false; edge_count],
            &vec![1.0; edge_count],
            n,
        );
        let table = bfs_from(&graph, 0);
        // MAX_PATH_LEN = 16, so region 16 is reachable (dist=16)
        assert_eq!(table.dist[16], 16);
        // Region 17 is beyond the hop limit
        assert_eq!(table.dist[17], u16::MAX);
    }

    #[test]
    fn test_trace_path() {
        // Chain: 0-1-2-3 bidirectional
        let graph = RouteGraph::from_edges(
            &[0, 1, 2, 1, 2, 3],
            &[1, 0, 1, 2, 3, 2],
            &[false; 6],
            &[1.0; 6],
            4,
        );
        let table = bfs_from(&graph, 0);
        let (path, len) = trace_path(&table, 0, 3).unwrap();
        assert_eq!(len, 3);
        assert_eq!(path[0], 1);
        assert_eq!(path[1], 2);
        assert_eq!(path[2], 3);
    }

    #[test]
    fn test_trace_path_unreachable() {
        // Only 0↔1 connected; region 2 is isolated
        let graph = RouteGraph::from_edges(
            &[0, 1],
            &[1, 0],
            &[false; 2],
            &[1.0; 2],
            3,
        );
        let table = bfs_from(&graph, 0);
        assert!(trace_path(&table, 0, 2).is_none());
    }

    #[test]
    fn test_bfs_deterministic_tiebreak() {
        // Star: 0→{1,2,3} — BFS order must be deterministic due to sorted adj
        let graph = RouteGraph::from_edges(
            &[0, 0, 0, 1, 2, 3],
            &[1, 2, 3, 0, 0, 0],
            &[false; 6],
            &[1.0; 6],
            4,
        );
        let t1 = bfs_from(&graph, 0);
        let t2 = bfs_from(&graph, 0);
        assert_eq!(t1.dist, t2.dist);
        assert_eq!(t1.pred, t2.pred);
    }

    // -------------------------------------------------------------------
    // Route selection tests
    // -------------------------------------------------------------------

    fn make_test_regions(n: usize) -> Vec<crate::region::RegionState> {
        (0..n)
            .map(|i| {
                let mut r = crate::region::RegionState::new(i as u16);
                r.merchant_margin = 0.3;
                r.merchant_route_margin = 0.3;
                r.stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
                r.population = 20;
                r
            })
            .collect()
    }

    /// Line 0 - 1 - 2 - 3 (bidirectional).
    fn line_graph(n: u16) -> RouteGraph {
        let mut from = Vec::new();
        let mut to = Vec::new();
        for i in 0..n - 1 {
            from.extend([i, i + 1]);
            to.extend([i + 1, i]);
        }
        let len = from.len();
        RouteGraph::from_edges(&from, &to, &vec![false; len], &vec![1.0; len], n as usize)
    }

    #[test]
    fn test_food_price_is_inverse_sufficiency_and_zero_without_people() {
        let mut r = crate::region::RegionState::new(0);
        r.population = 10;
        r.food_sufficiency = 0.5;
        assert_eq!(food_price(&r), 2.0);
        r.food_sufficiency = 2.0;
        assert_eq!(food_price(&r), 0.5);
        r.food_sufficiency = 0.0;
        assert_eq!(food_price(&r), 1.0 / FOOD_PRICE_SUFFICIENCY_FLOOR);
        r.population = 0;
        assert_eq!(food_price(&r), 0.0);
    }

    #[test]
    fn test_food_goes_to_the_short_market_not_the_cheap_or_empty_one() {
        // Region 1 is empty (its prices are 0, so its export margin is the
        // largest), region 2 is fed and cheap, region 3 is short of food.
        let mut regions = make_test_regions(4);
        regions[1].population = 0;
        regions[1].merchant_route_margin = 1.0;
        regions[2].merchant_route_margin = 0.9;
        regions[2].food_sufficiency = 2.0;
        regions[3].merchant_route_margin = 0.0;
        regions[3].food_sufficiency = 0.4;
        let graph = line_graph(4);
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(4);
        let intent = evaluate_route(0, 7, 0, &regions, &table, &ledger, None).unwrap();
        assert_eq!(intent.dest_region, 3);
        assert_eq!(intent.good_slot, 0, "the largest food stock (grain)");
        assert_eq!(intent.cargo_qty, MERCHANT_CARGO_CAP);
    }

    #[test]
    fn test_food_stays_home_without_a_dearer_market_and_others_use_the_proxy() {
        // Every market is as well fed as home: grain and fish do not travel.
        let mut regions = make_test_regions(3);
        let graph = line_graph(3);
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(3);
        assert!(evaluate_route(0, 7, 0, &regions, &table, &ledger, None).is_none());
        // Timber travels by the market-activity proxy, to a populated market.
        regions[0].stockpile[3] = 2.0;
        regions[2].merchant_route_margin = 0.6;
        let intent = evaluate_route(0, 7, 0, &regions, &table, &ledger, None).unwrap();
        assert_eq!(intent.good_slot, 3);
        assert_eq!(intent.dest_region, 2);
        regions[2].population = 0;
        let intent = evaluate_route(0, 7, 0, &regions, &table, &ledger, None).unwrap();
        assert_eq!(intent.dest_region, 1, "an empty region is not a market");
    }

    #[test]
    fn test_small_food_price_gaps_do_not_pay_for_a_trip() {
        // Gap 1/0.85 - 1 = 0.176 < MIN_TRIP_PROFIT x FOOD_PRICE_GAP_SCALE = 0.25.
        let mut regions = make_test_regions(2);
        regions[1].food_sufficiency = 0.85;
        let graph = line_graph(2);
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(2);
        assert!(evaluate_route(0, 7, 0, &regions, &table, &ledger, None).is_none());
        regions[1].food_sufficiency = 0.75;
        assert_eq!(evaluate_route(0, 7, 0, &regions, &table, &ledger, None).unwrap().dest_region, 1);
    }

    #[test]
    fn test_evaluate_route_finds_profitable_destination() {
        let mut regions = make_test_regions(3);
        regions[1].food_sufficiency = 0.5;
        regions[2].food_sufficiency = 0.5;
        let graph = RouteGraph::from_edges(
            &[0, 1, 1, 2],
            &[1, 0, 2, 1],
            &[false; 4],
            &[1.0; 4],
            3,
        );
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(3);
        let intent = evaluate_route(0, 1, 0, &regions, &table, &ledger, None);
        assert!(intent.is_some());
        let intent = intent.unwrap();
        assert_eq!(intent.origin_region, 0);
        assert!(intent.dest_region == 1 || intent.dest_region == 2);
        assert!(intent.cargo_qty > 0.0);
    }

    #[test]
    fn test_evaluate_route_no_profitable_route() {
        let mut regions = make_test_regions(2);
        regions[0].merchant_margin = 0.0;
        regions[0].merchant_route_margin = 0.0;
        regions[1].merchant_margin = 0.0;
        regions[1].merchant_route_margin = 0.0;
        let graph = RouteGraph::from_edges(
            &[0, 1],
            &[1, 0],
            &[false; 2],
            &[1.0; 2],
            2,
        );
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(2);
        let intent = evaluate_route(0, 1, 0, &regions, &table, &ledger, None);
        assert!(intent.is_none());
    }

    #[test]
    fn test_deterministic_tiebreak_by_region_then_agent() {
        let mut regions = make_test_regions(3);
        regions[1].merchant_margin = 0.5;
        regions[1].merchant_route_margin = 0.5;
        regions[2].merchant_margin = 0.5;
        regions[2].merchant_route_margin = 0.5;
        regions[1].food_sufficiency = 0.5;
        regions[2].food_sufficiency = 0.5;
        let graph = RouteGraph::from_edges(
            &[0, 0, 1, 2],
            &[1, 2, 0, 0],
            &[false; 4],
            &[1.0; 4],
            3,
        );
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(3);
        let i1 = evaluate_route(0, 100, 0, &regions, &table, &ledger, None).unwrap();
        let i2 = evaluate_route(0, 100, 0, &regions, &table, &ledger, None).unwrap();
        assert_eq!(i1.dest_region, i2.dest_region);
        assert_eq!(i1.dest_region, 1, "equal food prices tie to the lower region");
    }

    // -------------------------------------------------------------------
    // Conquest unwind tests
    // -------------------------------------------------------------------

    #[test]
    fn test_loading_invalidation_cancels_reservation() {
        let mut pool = AgentPool::new(5);
        let s = pool.spawn(
            0, 0, crate::agent::Occupation::Merchant, 20,
            0.0, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
        );
        let mut ledger = ShadowLedger::new(3);

        // Set up merchant in Loading state with path 0→1→2
        pool.trip_phase[s] = TRIP_PHASE_LOADING;
        pool.trip_origin_region[s] = 0;
        pool.trip_dest_region[s] = 2;
        pool.trip_good_slot[s] = 0;
        pool.trip_cargo_qty[s] = 5.0;
        pool.trip_path[s] = {
            let mut p = [u16::MAX; MAX_PATH_LEN];
            p[0] = 1; p[1] = 2;
            p
        };
        pool.trip_path_len[s] = 2;
        pool.trip_path_cursor[s] = 0;
        ledger.reserve(0, 0, 5.0);

        // Graph WITHOUT edge 0→1 (invalidated)
        let graph = RouteGraph::from_edges(
            &[1, 2], &[2, 1], &[false; 2], &[1.0; 2], 3,
        );

        let departed = depart_merchant(&mut pool, s, &graph, &make_test_regions(3), &mut ledger, None);
        assert!(!departed);
        assert_eq!(pool.trip_phase[s], TRIP_PHASE_IDLE);
        assert_eq!(ledger.reserved[0][0], 0.0);
    }

    #[test]
    fn test_conquest_unwind_loading_and_transit() {
        let mut pool = AgentPool::new(5);
        let s0 = pool.spawn(
            0, 0, crate::agent::Occupation::Merchant, 20,
            0.0, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
        );
        let s1 = pool.spawn(
            1, 0, crate::agent::Occupation::Merchant, 20,
            0.0, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
        );

        let mut ledger = ShadowLedger::new(4);

        // s0: Loading at region 0
        pool.trip_phase[s0] = TRIP_PHASE_LOADING;
        pool.trip_origin_region[s0] = 0;
        pool.trip_dest_region[s0] = 2;
        pool.trip_good_slot[s0] = 0;
        pool.trip_cargo_qty[s0] = 5.0;
        ledger.reserve(0, 0, 5.0);

        // s1: Transit from region 1
        pool.trip_phase[s1] = TRIP_PHASE_TRANSIT;
        pool.trip_origin_region[s1] = 1;
        pool.trip_dest_region[s1] = 3;
        pool.trip_good_slot[s1] = 0;
        pool.trip_cargo_qty[s1] = 3.0;
        ledger.reserve(1, 0, 3.0);
        ledger.depart(1, 0, 3.0, None);

        let mut stats = MerchantTripStats::default();

        // Conquer region 0 — should unwind s0 (Loading, cancel reservation)
        conquest_unwind(&mut pool, &mut ledger, &[0], &mut stats, None);
        assert_eq!(pool.trip_phase[s0], TRIP_PHASE_IDLE);
        assert_eq!(ledger.reserved[0][0], 0.0);
        // s1 should be unaffected
        assert_eq!(pool.trip_phase[s1], TRIP_PHASE_TRANSIT);

        // Conquer region 3 (s1's destination) — should unwind s1
        conquest_unwind(&mut pool, &mut ledger, &[3], &mut stats, None);
        assert_eq!(pool.trip_phase[s1], TRIP_PHASE_IDLE);
        assert_eq!(stats.unwind_count, 1); // only transit counts toward unwind_count
    }
}
