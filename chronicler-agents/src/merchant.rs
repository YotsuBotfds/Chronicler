//! M58a: Merchant mobility — shadow ledger, route graph, trip state machine.

use std::collections::VecDeque;

use crate::agent::{
    MAX_PATH_LEN, TRIP_PHASE_IDLE, TRIP_PHASE_LOADING, TRIP_PHASE_TRANSIT, TRIP_GOOD_SLOT_NONE,
};
use crate::economy::{
    CAT_CRAFT, CAT_FOOD, CAT_LUXURY, CAT_RAW_MATERIAL, GOOD_CATEGORY, NUM_CATEGORIES, NUM_GOODS,
};
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::transaction_receipts as receipts;

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
    /// Optional observations, excluded from native persistence and schema.
    pub receipts: Option<receipts::ReceiptFrame>,
}

// ---------------------------------------------------------------------------
// Route graph — adjacency list built from Python edge-list batch
// ---------------------------------------------------------------------------

/// Bulk trade (2026-10, docs/integration/bulk-trade-crafts.md): what one
/// merchant carries on one trip, by the way it travels, and whether the load
/// is filled against the tick's committed deliveries.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CargoConfig {
    /// A cart or pack train overland.
    pub land: f32,
    /// A barge between two regions on a common river.
    pub river: f32,
    /// A ship on a sea lane (maritime graphs only).
    pub sea: f32,
    /// Plan bulk trips (`plan_bulk_trip`): loads filled against the tick's
    /// committed deliveries. `false`: one-load planning, loading the path's
    /// capacity or the stock.
    pub fill: bool,
}

impl CargoConfig {
    /// Before bulk trade: one load per trip whatever the route, no fill.
    pub const LEGACY: CargoConfig = CargoConfig {
        land: MERCHANT_CARGO_CAP, river: MERCHANT_CARGO_CAP, sea: MERCHANT_CARGO_CAP, fill: false,
    };
}

impl Default for CargoConfig {
    fn default() -> Self {
        Self { land: LAND_CARGO_CAP, river: RIVER_CARGO_CAP, sea: SEA_CARGO_CAP, fill: true }
    }
}

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
    /// Bulk trade: cargo per trip by mode of travel. A graph built here
    /// carries one load per trip (`CargoConfig::LEGACY`); the simulator
    /// applies its configuration (`with_cargo`, bulk by default).
    pub cargo: CargoConfig,
    /// Rebuilt from simulator configuration after graph replacement/resume.
    pub receipt_limit: usize,
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
            cargo: CargoConfig::LEGACY,
            receipt_limit: 0,
        }
    }

    /// The same graph with another cargo configuration.
    pub fn with_cargo(mut self, cargo: CargoConfig) -> Self {
        self.cargo = cargo;
        self
    }

    /// Cargo one merchant carries across the edge `from -> to`: a ship's on
    /// a sea lane, a barge's on a river edge, a cart's otherwise.
    pub fn hop_cargo_cap(&self, from: u16, to: u16) -> f32 {
        if self.sea_lanes.contains_key(&(from, to)) {
            return self.cargo.sea;
        }
        let river = self.adj.get(from as usize)
            .and_then(|nbs| nbs.iter().find(|&&(r, _, _)| r == to))
            .is_some_and(|&(_, is_river, _)| is_river);
        if river { self.cargo.river } else { self.cargo.land }
    }

    /// Cargo of a trip: the capacity of its narrowest leg (goods carried by
    /// ship or barge go by cart on a land leg).
    pub fn path_cargo_cap(&self, origin: u16, path: &[u16; MAX_PATH_LEN], path_len: u8) -> f32 {
        let mut cap = f32::INFINITY;
        let mut from = origin;
        for &to in path.iter().take(path_len as usize) {
            cap = cap.min(self.hop_cargo_cap(from, to));
            from = to;
        }
        if cap.is_finite() { cap } else { self.cargo.land }
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
/// One load: what a merchant carried per trip before bulk trade
/// (`CargoConfig::LEGACY`), the abstract economy's per-merchant carry budget,
/// and the load when a market's food demand is not known yet.
pub const MERCHANT_CARGO_CAP: f32 = 1.0; // [CALIBRATE]

// Bulk trade (2026-10, docs/integration/bulk-trade-crafts.md). A merchant
// carried one load per trip. Grain moved in bulk where water carried it:
// barges and ships took many cart-loads. With `CargoConfig::fill` a trip
// carries up to the capacity of its narrowest leg (`RouteGraph::
// path_cargo_cap`), and loads are added only while the next one still
// earns the one-load threshold (`LOAD_MARGIN`), with the prices read as if
// this tick's committed cargo and the load itself had arrived
// (`plan_load`): a trip is worth making where it was before, one merchant
// does not overshoot a market, and an exporter stops where its own price
// meets the market's. The merchant takes the market where its cargo earns
// the most. Larger sea cargoes are larger prizes for raiders (the whole
// cargo is seized); blockades still remove the lanes.
/// Loads per trip overland (a cart or pack train).
pub const LAND_CARGO_CAP: f32 = 2.0; // [CALIBRATE]
/// Loads per trip between two regions on a common river (a barge).
pub const RIVER_CARGO_CAP: f32 = 5.0; // [CALIBRATE]
/// Loads per trip on a sea lane (a ship).
pub const SEA_CARGO_CAP: f32 = 10.0; // [CALIBRATE]
/// Price gap each load must earn, in price units: the one-load threshold
/// (`MIN_TRIP_PROFIT` x `PRICE_GAP_SCALE`).
pub const LOAD_MARGIN: f32 = MIN_TRIP_PROFIT * PRICE_GAP_SCALE;
/// Bisection steps of `plan_load` (resolution capacity / 2^16).
const FILL_STEPS: u32 = 16;
/// A load below this is not worth a trip.
pub const MIN_CARGO: f32 = 0.01;

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
// under a third in regions short of food. Food then travelled by the food
// price gap, demand / supply = 1 / sufficiency (the economy's own
// post-trade price).
//
// Correction (2026-10, city markets): every good travels by its price gap.
//
// - Non-food goods. The economy's demand and post-trade supply per category
//   (`RegionState::market_demand` / `market_supply`, from the last economy
//   tick) price raw materials and luxuries at a market as demand / supply,
//   the economy's own post-trade price; the activity proxy is not read. A
//   market without demand for a good pays nothing for it. Food keeps
//   1 / sufficiency and still goes first.
// - Trade packets advertise markets: a region's packet strength is its
//   dearest good's price above balance (`market_signal`), not its export
//   margin, and packet-known markets are scored like any other market (the
//   price at a known market is read live, as before for food). M59b's
//   gating and its no-fallback rule are unchanged.
// - Herding. Merchants plan one at a time in (origin, agent id) order, the
//   order intents were applied in, and each sees the cargo already
//   committed to and from every market this tick (`MarketTally`): loading
//   and in-transit cargo bound there, this tick's arrivals, and the plans
//   made before it. The price at a market is read as if that cargo had
//   arrived, so merchants at one origin no longer all choose the same
//   market, and an exporter stops before it ships away its own food.
//
// A region with no people is never a destination and emits no packet. No
// new random draws; the tie-breaks are unchanged (lower region, then lower
// category).

/// Sufficiency floor in the planner's food price, the economy's supply floor
/// (`SUPPLY_FLOOR`) applied to sufficiency: a region with no food at all
/// prices it at 10.
pub const FOOD_PRICE_SUFFICIENCY_FLOOR: f32 = 0.1;
/// Scales a price gap into the units of `merchant_route_margin` (the
/// economy's default `merchant_margin_normalizer`), so `MIN_TRIP_PROFIT`
/// keeps its meaning for every good.
pub const PRICE_GAP_SCALE: f32 = 5.0;
/// The economy's supply floor in the planner's non-food prices.
pub const PRICE_SUPPLY_FLOOR: f32 = 0.1;
/// The highest price the planner gives any good: food's with no food at all.
pub const MAX_PLANNER_PRICE: f32 = 1.0 / FOOD_PRICE_SUFFICIENCY_FLOOR;
/// The economy's base price: a market whose supply equals its demand.
pub const BALANCED_PRICE: f32 = 1.0;

/// Cargo committed this tick to and from each market, by goods category,
/// that the last economy tick has not seen yet. Built once per mobility
/// phase and extended by every plan; the planner reads a market's price as
/// if this cargo had arrived (or left).
#[derive(Clone, Debug)]
pub struct MarketTally {
    /// Cargo bound for each region: loading and in transit, arrived this
    /// tick, and planned this tick.
    pub inbound: Vec<[f32; NUM_CATEGORIES]>,
    /// Cargo leaving each region: reserved by loading merchants and
    /// departed this tick (`departure_debits`).
    pub outbound: Vec<[f32; NUM_CATEGORIES]>,
}

impl MarketTally {
    pub fn new(num_regions: usize) -> Self {
        Self {
            inbound: vec![[0.0; NUM_CATEGORIES]; num_regions],
            outbound: vec![[0.0; NUM_CATEGORIES]; num_regions],
        }
    }

    /// The tally at the start of planning: every loading or in-transit
    /// cargo by destination, this tick's arrivals, and each origin's
    /// reservations and departures since the last economy tick.
    pub fn observe(
        pool: &AgentPool,
        ledger: &ShadowLedger,
        delivery_buf: Option<&DeliveryBuffer>,
        num_regions: usize,
    ) -> Self {
        let mut tally = Self::new(num_regions);
        for slot in 0..pool.capacity() {
            if !pool.is_alive(slot) {
                continue;
            }
            let phase = pool.trip_phase[slot];
            if phase != TRIP_PHASE_LOADING && phase != TRIP_PHASE_TRANSIT {
                continue;
            }
            let good = pool.trip_good_slot[slot] as usize;
            let dest = pool.trip_dest_region[slot] as usize;
            if good < NUM_GOODS && dest < num_regions {
                tally.inbound[dest][GOOD_CATEGORY[good]] += pool.trip_cargo_qty[slot];
            }
        }
        if let Some(buf) = delivery_buf {
            for rec in &buf.arrival_imports {
                let (dest, good) = (rec.dest_region as usize, rec.good_slot as usize);
                if dest < num_regions && good < NUM_GOODS {
                    tally.inbound[dest][GOOD_CATEGORY[good]] += rec.qty;
                }
            }
        }
        for region in 0..num_regions.min(ledger.reserved.len()) {
            for good in 0..NUM_GOODS {
                let mut out = ledger.reserved[region][good];
                if let Some(debits) = delivery_buf.and_then(|buf| buf.departure_debits.get(region)) {
                    out += debits[good];
                }
                tally.outbound[region][GOOD_CATEGORY[good]] += out;
            }
        }
        tally
    }

    /// Record a committed plan.
    pub fn commit(&mut self, origin: u16, dest: u16, good_slot: u8, qty: f32) {
        let good = good_slot as usize;
        if good >= NUM_GOODS {
            return;
        }
        let cat = GOOD_CATEGORY[good];
        if let Some(row) = self.inbound.get_mut(dest as usize) {
            row[cat] += qty;
        }
        if let Some(row) = self.outbound.get_mut(origin as usize) {
            row[cat] += qty;
        }
    }

    /// Cargo committed to `region` less cargo committed out of it.
    #[inline]
    pub fn net(&self, region: usize, cat: usize) -> f32 {
        match (self.inbound.get(region), self.outbound.get(region)) {
            (Some(i), Some(o)) => i[cat] - o[cat],
            _ => 0.0,
        }
    }
}

/// The planner's price of goods category `cat` at `region`, read as if
/// `net_inflow` more of it had arrived. Food: demand / supply =
/// 1 / sufficiency, the economy's food price, with the sufficiency raised by
/// `net_inflow` over the food demand (when the demand is known). Raw
/// materials and luxuries: demand / (post-trade supply + `net_inflow`), the
/// economy's post-trade price; 0 without demand. A region without people
/// has no price. At most `MAX_PLANNER_PRICE`.
#[inline]
pub fn market_price(region: &RegionState, cat: usize, net_inflow: f32) -> f32 {
    if region.population == 0 || cat >= NUM_CATEGORIES {
        return 0.0;
    }
    let demand = region.market_demand[cat];
    if cat == CAT_FOOD {
        let mut sufficiency = region.food_sufficiency;
        if net_inflow != 0.0 && demand > 0.0 {
            sufficiency += net_inflow / demand.max(PRICE_SUPPLY_FLOOR);
        }
        return 1.0 / sufficiency.max(FOOD_PRICE_SUFFICIENCY_FLOOR);
    }
    if demand <= 0.0 {
        return 0.0;
    }
    (demand / (region.market_supply[cat] + net_inflow).max(PRICE_SUPPLY_FLOOR)).min(MAX_PLANNER_PRICE)
}

/// The economy's food price in `region`: demand / supply, which is
/// 1 / food_sufficiency. A region without people has no demand and no price.
#[inline]
pub fn food_price(region: &RegionState) -> f32 {
    market_price(region, CAT_FOOD, 0.0)
}

/// A region's strength as a market, the content of its trade packets: its
/// dearest good's price above balance, in margin units, within [0, 1].
/// Zero for a region without people or without a good it is short of.
/// Wares (crafts) are left out: everyone wants them and only cities make
/// them, so every other region would advertise at full strength; merchants
/// carry wares to the markets they know.
pub fn market_signal(region: &RegionState) -> f32 {
    let dearest = (0..NUM_CATEGORIES)
        .filter(|&cat| cat != CAT_CRAFT)
        .map(|cat| market_price(region, cat, 0.0))
        .fold(0.0f32, f32::max);
    ((dearest - BALANCED_PRICE) / PRICE_GAP_SCALE).clamp(0.0, 1.0)
}

/// Score of carrying goods of category `cat` from `origin` to `dest`: the
/// price gap in margin units, both prices read with the tally. Positive only
/// where the goods are dearer at the destination.
#[inline]
pub fn trip_score(
    regions: &[RegionState],
    tally: &MarketTally,
    origin: usize,
    dest: usize,
    cat: usize,
) -> f32 {
    (market_price(&regions[dest], cat, tally.net(dest, cat))
        - market_price(&regions[origin], cat, tally.net(origin, cat)))
        / PRICE_GAP_SCALE
}

/// Bulk trade: the load of a trip carrying category `cat` from `origin` to
/// `dest`, at most `cap`, and the price gap the load earns. Both prices are
/// read as if the tally's committed cargo and the load had arrived; loads are
/// added while the last one still earns `LOAD_MARGIN` (the largest such
/// quantity, by bisection, since the gap falls as the load grows). The
/// earnings are the trapezoid estimate over the load. A market whose food
/// demand is not known yet (no economy tick since it was settled) cannot be
/// filled against and takes one load. Returns (0, 0) when no load pays.
pub fn plan_load(
    regions: &[RegionState],
    tally: &MarketTally,
    origin: usize,
    dest: usize,
    cat: usize,
    cap: f32,
) -> (f32, f32) {
    if cap <= 0.0 || cat >= NUM_CATEGORIES {
        return (0.0, 0.0);
    }
    let (net_o, net_d) = (tally.net(origin, cat), tally.net(dest, cat));
    let gap = |q: f32| market_price(&regions[dest], cat, net_d + q) - market_price(&regions[origin], cat, net_o - q);
    let first = gap(0.0);
    if first / PRICE_GAP_SCALE < MIN_TRIP_PROFIT {
        return (0.0, 0.0);
    }
    if cat == CAT_FOOD
        && (regions[origin].market_demand[CAT_FOOD] <= 0.0 || regions[dest].market_demand[CAT_FOOD] <= 0.0)
    {
        let q = cap.min(MERCHANT_CARGO_CAP);
        return (q, q * first);
    }
    let q = if gap(cap) >= LOAD_MARGIN {
        cap
    } else {
        let (mut lo, mut hi) = (0.0f32, cap);
        for _ in 0..FILL_STEPS {
            let mid = 0.5 * (lo + hi);
            if gap(mid) >= LOAD_MARGIN { lo = mid } else { hi = mid }
        }
        lo
    };
    if q < MIN_CARGO {
        return (0.0, 0.0);
    }
    (q, 0.5 * q * (first + gap(q)))
}

#[inline]
fn is_food_slot(slot: usize) -> bool {
    slot < NUM_GOODS && GOOD_CATEGORY[slot] == CAT_FOOD
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
    for slot in 0..NUM_GOODS as u8 {
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
/// `MIN_TRIP_PROFIT`, ties to the lower (region, agent) pair, with its score.
fn best_destination(
    agent_id: u32,
    candidates: impl Iterator<Item = (u16, f32)>,
) -> Option<(u16, f32)> {
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
    best_dest.map(|d| (d, best_score))
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
        available: cargo.1,
        path,
        path_len,
    })
}

/// A planned trip, committed by `apply_trip_intent` (which re-checks the
/// cargo). Without a bulk graph the intent carries one load
/// (`MERCHANT_CARGO_CAP`).
#[derive(Clone, Debug)]
pub struct TripIntent {
    pub agent_slot: usize,
    pub origin_region: u16,
    pub dest_region: u16,
    pub good_slot: u8,
    pub cargo_qty: f32,
    /// The origin's uncommitted stock of the good when the trip was planned.
    pub available: f32,
    pub path: [u16; MAX_PATH_LEN],
    pub path_len: u8,
}

/// Categories other than food, in the order ties are broken.
const NON_FOOD_CATEGORIES: [usize; 3] = [CAT_RAW_MATERIAL, CAT_LUXURY, CAT_CRAFT];

/// The trip a merchant at `origin_region` plans among `markets` (populated,
/// reachable regions). With a bulk graph (`CargoConfig::fill`) see
/// `plan_bulk_trip`. Otherwise food goes to the market where it is dearest,
/// if any is dearer than home by `MIN_TRIP_PROFIT`; else the non-food
/// category and market with the largest price gap (ties: lower region, then
/// raw materials, luxuries, wares). The cargo is the origin's largest
/// uncommitted stock of the chosen category: one load, or with a graph that
/// does not fill, the path's capacity.
#[allow(clippy::too_many_arguments)]
fn plan_trip<I: Iterator<Item = u16>>(
    agent_slot: usize,
    agent_id: u32,
    origin_region: u16,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
    delivery_buf: Option<&DeliveryBuffer>,
    tally: &MarketTally,
    bulk: Option<&RouteGraph>,
    markets: impl Fn() -> I,
) -> Option<TripIntent> {
    if let Some(graph) = bulk.filter(|g| g.cargo.fill) {
        return plan_bulk_trip(
            agent_slot, origin_region, regions, path_table, ledger, delivery_buf, tally, graph, markets,
        );
    }
    let mut intent = plan_one_load_trip(
        agent_slot, agent_id, origin_region, regions, path_table, ledger, delivery_buf, tally, markets,
    )?;
    if let Some(graph) = bulk {
        intent.cargo_qty = graph.path_cargo_cap(origin_region, &intent.path, intent.path_len).min(intent.available);
    }
    Some(intent)
}

/// Bulk trade: the trip whose cargo earns the most. For each market the
/// load and its earnings come from `plan_load` with the path's capacity (at
/// most the origin's uncommitted stock). Food first, as before; otherwise the
/// best non-food trip (ties: lower region, then the category order). Ties
/// between markets go to the lower region.
#[allow(clippy::too_many_arguments)]
fn plan_bulk_trip<I: Iterator<Item = u16>>(
    agent_slot: usize,
    origin_region: u16,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
    delivery_buf: Option<&DeliveryBuffer>,
    tally: &MarketTally,
    graph: &RouteGraph,
    markets: impl Fn() -> I,
) -> Option<TripIntent> {
    let origin = origin_region as usize;
    // (earnings, dest, load, path, path_len) of the best market for a cargo.
    let best_market = |cat: usize, cargo: (u8, f32)| {
        let mut best: Option<(f32, u16, f32, [u16; MAX_PATH_LEN], u8)> = None;
        for dest in markets() {
            let Some((path, path_len)) = trace_path(path_table, origin_region, dest) else { continue };
            let cap = graph.path_cargo_cap(origin_region, &path, path_len).min(cargo.1);
            let (load, margin) = plan_load(regions, tally, origin, dest as usize, cat, cap);
            if load <= 0.0 {
                continue;
            }
            if best.is_none_or(|(m, d, ..)| margin > m || (margin == m && dest < d)) {
                best = Some((margin, dest, load, path, path_len));
            }
        }
        best
    };
    let intent = |cargo: (u8, f32), dest: u16, load: f32, path: [u16; MAX_PATH_LEN], path_len: u8| TripIntent {
        agent_slot,
        origin_region,
        dest_region: dest,
        good_slot: cargo.0,
        cargo_qty: load,
        available: cargo.1,
        path,
        path_len,
    };
    if let Some(cargo) = best_cargo_slot(origin, regions, ledger, delivery_buf, is_food_slot) {
        if let Some((_, dest, load, path, path_len)) = best_market(CAT_FOOD, cargo) {
            return Some(intent(cargo, dest, load, path, path_len));
        }
    }
    let mut best: Option<(f32, u16, f32, [u16; MAX_PATH_LEN], u8, (u8, f32))> = None;
    for cat in NON_FOOD_CATEGORIES {
        let Some(cargo) = best_cargo_slot(origin, regions, ledger, delivery_buf, |s| GOOD_CATEGORY[s] == cat)
        else {
            continue;
        };
        if let Some((margin, dest, load, path, path_len)) = best_market(cat, cargo) {
            if best.is_none_or(|(m, d, ..)| margin > m || (margin == m && dest < d)) {
                best = Some((margin, dest, load, path, path_len, cargo));
            }
        }
    }
    let (_, dest, load, path, path_len, cargo) = best?;
    Some(intent(cargo, dest, load, path, path_len))
}

/// One load to the market with the largest price gap (see `plan_trip`).
#[allow(clippy::too_many_arguments)]
fn plan_one_load_trip<I: Iterator<Item = u16>>(
    agent_slot: usize,
    agent_id: u32,
    origin_region: u16,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
    delivery_buf: Option<&DeliveryBuffer>,
    tally: &MarketTally,
    markets: impl Fn() -> I,
) -> Option<TripIntent> {
    let origin = origin_region as usize;
    // Food goes where it is dearer than at home.
    if let Some(cargo) = best_cargo_slot(origin, regions, ledger, delivery_buf, is_food_slot) {
        let scored = markets().map(|d| (d, trip_score(regions, tally, origin, d as usize, CAT_FOOD)));
        if let Some((dest, _)) = best_destination(agent_id, scored) {
            if let Some(intent) = trip_intent(agent_slot, origin_region, dest, cargo, path_table) {
                return Some(intent);
            }
        }
    }
    // Other goods go where they are dearest, by category.
    let mut best: Option<(u16, f32, (u8, f32))> = None;
    for cat in NON_FOOD_CATEGORIES {
        let Some(cargo) = best_cargo_slot(origin, regions, ledger, delivery_buf, |s| GOOD_CATEGORY[s] == cat)
        else {
            continue;
        };
        let scored = markets().map(|d| (d, trip_score(regions, tally, origin, d as usize, cat)));
        if let Some((dest, score)) = best_destination(agent_id, scored) {
            let better = match best {
                None => true,
                Some((d, s, _)) => score > s || (score == s && dest < d),
            };
            if better {
                best = Some((dest, score, cargo));
            }
        }
    }
    let (dest, _, cargo) = best?;
    trip_intent(agent_slot, origin_region, dest, cargo, path_table)
}

/// Evaluate route candidates for an idle merchant at `origin_region`.
/// Returns a TripIntent if a profitable route with available cargo exists.
/// When `delivery_buf` is `Some`, uses hybrid availability (departure_debits).
/// Prices are read without a delivery tally (see `evaluate_route_with_tally`).
pub fn evaluate_route(
    agent_slot: usize,
    agent_id: u32,
    origin_region: u16,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
    delivery_buf: Option<&DeliveryBuffer>,
) -> Option<TripIntent> {
    let tally = MarketTally::new(regions.len());
    evaluate_route_with_tally(
        agent_slot, agent_id, origin_region, regions, path_table, ledger, delivery_buf, &tally, None,
    )
}

/// [`evaluate_route`] with this tick's delivery tally: every populated
/// region within reach is a candidate market. With `bulk` (the route graph)
/// the trip is a bulk trip (`plan_trip`).
#[allow(clippy::too_many_arguments)]
pub fn evaluate_route_with_tally(
    agent_slot: usize,
    agent_id: u32,
    origin_region: u16,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
    delivery_buf: Option<&DeliveryBuffer>,
    tally: &MarketTally,
    bulk: Option<&RouteGraph>,
) -> Option<TripIntent> {
    if origin_region as usize >= regions.len() {
        return None;
    }
    let reachable = || {
        path_table.dist.iter().enumerate()
            .filter(|&(dest, &dist)| dist != 0 && dist != u16::MAX && regions[dest].population > 0)
            .map(|(dest, _)| dest as u16)
    };
    plan_trip(
        agent_slot, agent_id, origin_region, regions, path_table, ledger, delivery_buf, tally, bulk, reachable,
    )
}

/// M59b: Packet-gated route evaluation. When usable nonlocal trade packets
/// exist (after reachability filtering), only packet-known destinations are
/// candidates. Falls back to oracle (evaluate_route) when usable set is empty.
///
/// Returns (Option<TripIntent>, had_usable_packets: bool).
/// Counter increments happen in merchant_mobility_phase AFTER apply_trip_intent
/// succeeds, not here — "successful plan" means surviving reservation.
/// Prices are read without a delivery tally (see
/// `evaluate_route_packet_aware_with_tally`).
#[allow(clippy::too_many_arguments)]
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
    let tally = MarketTally::new(regions.len());
    evaluate_route_packet_aware_with_tally(
        agent_slot, agent_id, origin_region, pool, regions, path_table, ledger, delivery_buf, &tally, None,
    )
}

/// [`evaluate_route_packet_aware`] with this tick's delivery tally. A
/// packet-known market is scored as the oracle planner scores any market;
/// the packet decides only which markets the merchant knows.
#[allow(clippy::too_many_arguments)]
pub fn evaluate_route_packet_aware_with_tally(
    agent_slot: usize,
    agent_id: u32,
    origin_region: u16,
    pool: &AgentPool,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
    delivery_buf: Option<&DeliveryBuffer>,
    tally: &MarketTally,
    bulk: Option<&RouteGraph>,
) -> (Option<TripIntent>, bool) {
    let origin = origin_region as usize;
    if origin >= regions.len() {
        return (None, false);
    }

    // Collect usable nonlocal trade packets
    let raw_packets = crate::knowledge::usable_trade_packets(pool, agent_slot, origin_region);

    // Reachability filter: only keep packets whose source_region is reachable
    let reachable_packets: Vec<u16> = raw_packets
        .into_iter()
        .map(|(src_region, _)| src_region)
        .filter(|&src_region| {
            let idx = src_region as usize;
            idx < path_table.dist.len()
                && path_table.dist[idx] != 0
                && path_table.dist[idx] != u16::MAX
        })
        .collect();

    if reachable_packets.is_empty() {
        // Bootstrap fallback: no usable packets, use oracle planner
        let intent = evaluate_route_with_tally(
            agent_slot, agent_id, origin_region, regions, path_table, ledger, delivery_buf, tally, bulk,
        );
        return (intent, false); // false = no usable packets
    }

    // Packet-gated planning: only packet-known markets are candidates, and
    // when none is worth the trip there is no oracle fallback
    // (anti-omniscience rule). A market needs people to sell to.
    let known = || {
        reachable_packets.iter()
            .copied()
            .filter(|&src_region| regions[src_region as usize].population > 0)
    };
    let intent = plan_trip(
        agent_slot, agent_id, origin_region, regions, path_table, ledger, delivery_buf, tally, bulk, known,
    );
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
    if graph.receipt_limit > 0 {
        stats.receipts = Some(receipts::ReceiptFrame::new(turn, graph.receipt_limit));
    }
    let physical_stock = delivery_buf.as_deref().is_some_and(|buf| buf.physical_stock);
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
                receipts::record(&mut stats.receipts, pool, regions, slot, receipts::REPLANNED,
                                 current, dest, physical_stock, receipts::NO_LOSS);
            } else {
                let origin = pool.trip_origin_region[slot] as usize;
                let good = pool.trip_good_slot[slot] as usize;
                ledger.unwind(origin, good, pool.trip_cargo_qty[slot], delivery_buf.as_deref_mut());
                receipts::record(&mut stats.receipts, pool, regions, slot, receipts::RETURNED,
                                 current, origin as u16, physical_stock, receipts::NO_LOSS);
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
        // Cancellation resets fields; retain the reservation only when recording.
        let before = stats.receipts.as_ref().map(|_| receipts::observe(
            pool, regions, slot, receipts::CANCELLED, pool.regions[slot],
            pool.trip_dest_region[slot], physical_stock, receipts::NO_LOSS));
        if depart_merchant(pool, slot, graph, regions, ledger, delivery_buf.as_deref_mut()) {
            receipts::record(&mut stats.receipts, pool, regions, slot, receipts::DEPARTED,
                             pool.regions[slot], pool.trip_dest_region[slot], physical_stock,
                             receipts::NO_LOSS);
        } else if let (Some(frame), Some(before)) = (&mut stats.receipts, before) {
            frame.push(before);
        }
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
                    receipts::record(&mut stats.receipts, pool, regions, slot, receipts::SEA_CROSSING,
                                     from, to, physical_stock,
                                     if raided { LossReason::Raid as u8 } else { receipts::NO_LOSS });
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
        receipts::record(&mut stats.receipts, pool, regions, slot, receipts::ARRIVED,
                         pool.regions[slot], dest as u16, physical_stock, receipts::NO_LOSS);
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
    // City markets (2026-10): one merchant at a time in (origin, agent id)
    // order, each plan committed before the next merchant plans, against the
    // tick's delivery tally (see `MarketTally`).
    let mut origin_tables: std::collections::HashMap<u16, PathTable> = std::collections::HashMap::new();
    let mut planners: Vec<usize> = Vec::new();
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_IDLE { continue; }
        if pool.occupations[slot] != crate::agent::Occupation::Merchant as u8 { continue; }
        // A merchant that delivered this turn is still at the market; it
        // returns home before planning again.
        if pool.trip_home_region[slot] != crate::agent::TRIP_HOME_NONE { continue; }
        planners.push(slot);
    }
    planners.sort_by_key(|&slot| (pool.regions[slot], pool.ids[slot]));
    let mut tally = MarketTally::observe(pool, ledger, delivery_buf.as_deref(), regions.len());
    for slot in planners {
        let origin = pool.regions[slot];
        let table = origin_tables.entry(origin).or_insert_with(|| bfs_from(graph, origin));
        let (intent, had_packets) = evaluate_route_packet_aware_with_tally(
            slot, pool.ids[slot], origin, pool, regions, table, ledger,
            delivery_buf.as_deref(), &tally, Some(graph),
        );
        if !had_packets {
            stats.no_usable_packets += 1;
        }
        let Some(intent) = intent else { continue };
        if apply_trip_intent(&intent, pool, ledger, regions, &mut stats, delivery_buf.as_deref()) {
            tally.commit(intent.origin_region, intent.dest_region, intent.good_slot, pool.trip_cargo_qty[slot]);
            receipts::record(&mut stats.receipts, pool, regions, slot, receipts::RESERVED,
                             intent.origin_region, intent.dest_region, physical_stock, receipts::NO_LOSS);
            if had_packets {
                stats.plans_packet_driven += 1;
            } else {
                stats.plans_bootstrap += 1;
            }
        }
    }

    // Phase h: Collect final diagnostics (also loading reservations in optional frame).
    for slot in 0..cap {
        if !pool.is_alive(slot) { continue; }
        if pool.trip_phase[slot] == TRIP_PHASE_LOADING || pool.trip_phase[slot] == TRIP_PHASE_TRANSIT {
            receipts::record(&mut stats.receipts, pool, regions, slot, receipts::ACTIVE,
                             pool.regions[slot], pool.trip_dest_region[slot], physical_stock,
                             receipts::NO_LOSS);
        }
        if pool.trip_phase[slot] != TRIP_PHASE_TRANSIT { continue; }
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
        let stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
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
        let stockpile = [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
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
                r.stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
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
    fn test_food_stays_home_without_a_dearer_market_and_timber_goes_where_it_is_wanted() {
        // Every market is as well fed as home: grain and fish do not travel.
        let mut regions = make_test_regions(3);
        let graph = line_graph(3);
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(3);
        assert!(evaluate_route(0, 7, 0, &regions, &table, &ledger, None).is_none());
        // Timber travels by its price (city markets correction): region 2
        // wants raw materials and has few; region 1's export margin, the old
        // activity proxy, is not read.
        regions[0].stockpile[3] = 2.0;
        regions[1].merchant_route_margin = 1.0;
        regions[2].market_demand[CAT_RAW_MATERIAL] = 1.5;
        regions[2].market_supply[CAT_RAW_MATERIAL] = 0.5;
        let intent = evaluate_route(0, 7, 0, &regions, &table, &ledger, None).unwrap();
        assert_eq!(intent.good_slot, 3);
        assert_eq!(intent.dest_region, 2);
        // A region without people, or without demand for it, is no market.
        regions[2].population = 0;
        assert!(evaluate_route(0, 7, 0, &regions, &table, &ledger, None).is_none());
        regions[2].population = 20;
        regions[2].market_demand[CAT_RAW_MATERIAL] = 0.0;
        assert!(evaluate_route(0, 7, 0, &regions, &table, &ledger, None).is_none());
    }

    #[test]
    fn test_non_food_price_is_demand_over_supply() {
        let mut r = crate::region::RegionState::new(0);
        r.population = 10;
        assert_eq!(market_price(&r, CAT_RAW_MATERIAL, 0.0), 0.0, "no demand, no price");
        r.market_demand[CAT_RAW_MATERIAL] = 3.0;
        r.market_supply[CAT_RAW_MATERIAL] = 2.0;
        assert_eq!(market_price(&r, CAT_RAW_MATERIAL, 0.0), 1.5);
        assert_eq!(market_price(&r, CAT_RAW_MATERIAL, 1.0), 1.0, "committed cargo counts as supply");
        r.market_supply[CAT_RAW_MATERIAL] = 0.0;
        assert_eq!(market_price(&r, CAT_RAW_MATERIAL, 0.0), MAX_PLANNER_PRICE, "capped like food");
        r.market_demand[CAT_LUXURY] = 0.4;
        r.market_supply[CAT_LUXURY] = 0.8;
        assert_eq!(market_price(&r, CAT_LUXURY, 0.0), 0.5);
        r.population = 0;
        assert_eq!(market_price(&r, CAT_RAW_MATERIAL, 0.0), 0.0);
    }

    #[test]
    fn test_food_price_reads_committed_cargo_against_demand() {
        let mut r = crate::region::RegionState::new(0);
        r.population = 10;
        r.food_sufficiency = 0.5;
        // Without the demand the tally is ignored (the bare 1 / sufficiency).
        assert_eq!(market_price(&r, CAT_FOOD, 2.5), 2.0);
        r.market_demand[CAT_FOOD] = 5.0;
        assert_eq!(market_price(&r, CAT_FOOD, 0.0), 2.0);
        assert_eq!(market_price(&r, CAT_FOOD, 2.5), 1.0, "2.5 more food on a demand of 5");
        assert_eq!(market_price(&r, CAT_FOOD, -2.5), 1.0 / FOOD_PRICE_SUFFICIENCY_FLOOR);
    }

    #[test]
    fn test_market_signal_is_the_dearest_good_above_balance() {
        let mut r = crate::region::RegionState::new(0);
        r.population = 10;
        r.food_sufficiency = 1.0;
        assert_eq!(market_signal(&r), 0.0, "a balanced, fed market");
        r.food_sufficiency = 0.5;
        assert!((market_signal(&r) - 0.2).abs() < 1e-6, "food at 2.0: (2 - 1) / 5");
        r.market_demand[CAT_RAW_MATERIAL] = 3.0;
        r.market_supply[CAT_RAW_MATERIAL] = 0.5;
        assert!((market_signal(&r) - 1.0).abs() < 1e-6, "raw materials at 6.0, clamped");
        r.population = 0;
        assert_eq!(market_signal(&r), 0.0, "nobody to sell to");
        // An empty, cheap region has the largest export margin and no signal.
        r.merchant_route_margin = 1.0;
        assert_eq!(market_signal(&r), 0.0);
    }

    /// Origin 0 with plenty of grain next to two short markets (star 0-1,
    /// 0-2); merchants at the origin, no packets.
    fn herding_world(merchants: usize) -> (AgentPool, Vec<crate::region::RegionState>, RouteGraph) {
        let mut pool = AgentPool::new(merchants);
        for _ in 0..merchants {
            pool.spawn(0, 0, crate::agent::Occupation::Merchant, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        }
        let mut regions = make_test_regions(3);
        for r in regions.iter_mut() {
            r.stockpile = [0.0; NUM_GOODS];
            r.population = 10;
            r.market_demand[CAT_FOOD] = 5.0;
        }
        regions[0].stockpile[0] = 20.0;
        regions[0].food_sufficiency = 2.0;
        regions[1].food_sufficiency = 0.5;
        regions[2].food_sufficiency = 0.6;
        let graph = RouteGraph::from_edges(&[0, 1, 0, 2], &[1, 0, 2, 0], &[false; 4], &[1.0; 4], 3);
        (pool, regions, graph)
    }

    fn planned_destinations(pool: &AgentPool) -> Vec<u16> {
        (0..pool.capacity())
            .filter(|&s| pool.trip_phase[s] == TRIP_PHASE_LOADING)
            .map(|s| pool.trip_dest_region[s])
            .collect()
    }

    #[test]
    fn test_merchants_at_one_origin_spread_over_markets_by_need() {
        let (mut pool, regions, graph) = herding_world(4);
        let mut ledger = ShadowLedger::new(3);
        let mut buf = DeliveryBuffer::new(3);
        buf.physical_stock = true;
        merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0; 32], Some(&mut buf));
        let dests = planned_destinations(&pool);
        assert_eq!(dests.len(), 4);
        // Region 1 (price 2.0) first; one unit lifts it to 0.7 (1.43), below
        // region 2 (1.67); then region 2, and so on: two each. Without the
        // tally all four went to region 1.
        let to_1 = dests.iter().filter(|&&d| d == 1).count();
        let to_2 = dests.iter().filter(|&&d| d == 2).count();
        assert_eq!((to_1, to_2), (2, 2));
        // The plans reserve four units of the origin's grain.
        assert_eq!(ledger.reserved[0][0], 4.0);
    }

    #[test]
    fn test_an_exporter_stops_before_it_ships_away_its_own_food() {
        // Home holds 1.4 turns of food (demand 5): after two units leave it
        // is at 1.0 and after three at 0.8 (price 1.25), when a market at
        // 0.7 (1.43) no longer pays for the trip (gap 0.18 < 0.25).
        let (mut pool, mut regions, graph) = herding_world(5);
        regions[0].food_sufficiency = 1.4;
        regions[1].food_sufficiency = 0.7;
        regions[2].food_sufficiency = 0.7;
        let mut ledger = ShadowLedger::new(3);
        let mut buf = DeliveryBuffer::new(3);
        buf.physical_stock = true;
        merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0; 32], Some(&mut buf));
        let dests = planned_destinations(&pool);
        assert!(!dests.is_empty() && dests.len() < 5, "some merchants stay home: {dests:?}");
    }

    #[test]
    fn test_cargo_already_on_the_road_counts_against_its_market() {
        // A merchant carrying three units to region 1 from an earlier turn:
        // the next merchant goes to region 2.
        let (mut pool, regions, graph) = herding_world(2);
        let ledger = ShadowLedger::new(3);
        pool.trip_phase[0] = TRIP_PHASE_TRANSIT;
        pool.trip_origin_region[0] = 0;
        pool.trip_dest_region[0] = 1;
        pool.trip_good_slot[0] = 0;
        pool.trip_cargo_qty[0] = 3.0;
        let tally = MarketTally::observe(&pool, &ledger, None, 3);
        assert_eq!(tally.inbound[1][CAT_FOOD], 3.0);
        let table = bfs_from(&graph, 0);
        let intent = evaluate_route_with_tally(1, pool.ids[1], 0, &regions, &table, &ledger, None, &tally, None)
            .unwrap();
        assert_eq!(intent.dest_region, 2);
        let intent = evaluate_route(1, pool.ids[1], 0, &regions, &table, &ledger, None).unwrap();
        assert_eq!(intent.dest_region, 1, "without the tally: the dearest market");
    }

    #[test]
    fn test_small_food_price_gaps_do_not_pay_for_a_trip() {
        // Gap 1/0.85 - 1 = 0.176 < MIN_TRIP_PROFIT x PRICE_GAP_SCALE = 0.25.
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
    // Bulk trade tests
    // -------------------------------------------------------------------

    /// Origin 0 with `stock` grain at sufficiency 1.5 next to one market at
    /// `dest_suff` (demand 5 each), with the default bulk cargo.
    fn bulk_world(stock: f32, dest_suff: f32) -> (Vec<crate::region::RegionState>, RouteGraph) {
        let mut regions = make_test_regions(2);
        for r in regions.iter_mut() {
            r.stockpile = [0.0; NUM_GOODS];
            r.population = 10;
            r.market_demand[CAT_FOOD] = 5.0;
        }
        regions[0].stockpile[0] = stock;
        regions[0].food_sufficiency = 1.5;
        regions[1].food_sufficiency = dest_suff;
        let graph = RouteGraph::from_edges(&[0, 1], &[1, 0], &[false; 2], &[0.1; 2], 2)
            .with_cargo(CargoConfig::default());
        (regions, graph)
    }

    fn bulk_plan(regions: &[crate::region::RegionState], graph: &RouteGraph) -> Option<TripIntent> {
        let table = bfs_from(graph, 0);
        let ledger = ShadowLedger::new(regions.len());
        let tally = MarketTally::new(regions.len());
        evaluate_route_with_tally(0, 7, 0, regions, &table, &ledger, None, &tally, Some(graph))
    }

    #[test]
    fn test_hop_capacity_by_mode_and_path_capacity_of_the_narrowest_leg() {
        // 0 -river- 1 -sea- 2 -land- 3
        let graph = RouteGraph::from_edges(
            &[0, 1, 1, 2, 2, 3], &[1, 0, 2, 1, 3, 2], &[true, true, false, false, false, false],
            &[0.05, 0.05, 0.04, 0.04, 0.1, 0.1], 4,
        )
        .with_sea_lanes(&[0, 1, 1, 2, 2, 3], &[1, 0, 2, 1, 3, 2], &[-1.0, -1.0, 0.0, 0.0, -1.0, -1.0])
        .with_cargo(CargoConfig::default());
        assert_eq!(graph.hop_cargo_cap(0, 1), RIVER_CARGO_CAP);
        assert_eq!(graph.hop_cargo_cap(1, 2), SEA_CARGO_CAP);
        assert_eq!(graph.hop_cargo_cap(2, 3), LAND_CARGO_CAP);
        let mut path = [u16::MAX; MAX_PATH_LEN];
        path[0] = 1;
        path[1] = 2;
        assert_eq!(graph.path_cargo_cap(0, &path, 2), RIVER_CARGO_CAP, "river then sea: the barge's load");
        path[2] = 3;
        assert_eq!(graph.path_cargo_cap(0, &path, 3), LAND_CARGO_CAP, "a land leg: the cart's load");
        let mut path = [u16::MAX; MAX_PATH_LEN];
        path[0] = 2;
        assert_eq!(graph.path_cargo_cap(1, &path, 1), SEA_CARGO_CAP);
        // A graph built directly carries one load whatever the route.
        let legacy = RouteGraph::from_edges(&[0, 1], &[1, 0], &[true; 2], &[0.05; 2], 2);
        assert_eq!(legacy.cargo, CargoConfig::LEGACY);
        assert_eq!(legacy.hop_cargo_cap(0, 1), MERCHANT_CARGO_CAP);
    }

    #[test]
    fn test_bulk_load_fills_while_each_load_earns_the_one_load_margin() {
        // Home 1.5 (price 0.67), market 0.4 (2.5): after a cart's two loads the
        // gap is still 0.34, so the trip carries the capacity.
        let (regions, mut graph) = bulk_world(10.0, 0.4);
        let intent = bulk_plan(&regions, &graph).unwrap();
        assert_eq!(intent.dest_region, 1);
        assert_eq!(intent.cargo_qty, LAND_CARGO_CAP);
        // A barge's five loads would close the gap: it stops where the last
        // load earns `LOAD_MARGIN` (about 2.2 loads).
        graph.cargo.land = RIVER_CARGO_CAP;
        let q = bulk_plan(&regions, &graph).unwrap().cargo_qty;
        assert!(q > LAND_CARGO_CAP && q < RIVER_CARGO_CAP, "{q}");
        let last = market_price(&regions[1], CAT_FOOD, q) - market_price(&regions[0], CAT_FOOD, -q);
        assert!(last >= LOAD_MARGIN && last - LOAD_MARGIN < 1e-3, "{last}");
        // Never more than the uncommitted stock.
        let (regions, graph) = bulk_world(1.5, 0.4);
        assert_eq!(bulk_plan(&regions, &graph).unwrap().cargo_qty, 1.5);
    }

    #[test]
    fn test_bulk_trips_are_made_where_one_load_trips_were() {
        // Gap 1 / 1.1 - 1 / 1.5 = 0.24, below the one-load threshold: no trip,
        // however much the merchant could carry.
        let (regions, mut graph) = bulk_world(30.0, 1.1);
        graph.cargo.land = SEA_CARGO_CAP;
        assert!(bulk_plan(&regions, &graph).is_none());
        let table = bfs_from(&graph, 0);
        assert!(evaluate_route(0, 7, 0, &regions, &table, &ShadowLedger::new(2), None).is_none());
        assert_eq!(plan_load(&regions, &MarketTally::new(2), 0, 1, CAT_FOOD, SEA_CARGO_CAP), (0.0, 0.0));
        // At 0.75 (gap 0.67) both plan the trip to the same market.
        let (regions, graph) = bulk_world(30.0, 0.75);
        let bulk = bulk_plan(&regions, &graph).unwrap();
        let one = evaluate_route(0, 7, 0, &regions, &bfs_from(&graph, 0), &ShadowLedger::new(2), None).unwrap();
        assert_eq!((bulk.dest_region, bulk.good_slot), (one.dest_region, one.good_slot));
        assert!(bulk.cargo_qty > one.cargo_qty);
    }

    #[test]
    fn test_bulk_trip_goes_where_the_cargo_earns_most() {
        // Market 1 is dearer (0.4) but small (demand 2): a barge earns more
        // in market 2 (0.5, demand 20), which takes the whole cargo.
        let mut regions = make_test_regions(3);
        for r in regions.iter_mut() {
            r.stockpile = [0.0; NUM_GOODS];
            r.population = 10;
        }
        regions[0].stockpile[0] = 30.0;
        regions[0].food_sufficiency = 1.5;
        regions[0].market_demand[CAT_FOOD] = 20.0;
        regions[1].food_sufficiency = 0.4;
        regions[1].market_demand[CAT_FOOD] = 2.0;
        regions[2].food_sufficiency = 0.5;
        regions[2].market_demand[CAT_FOOD] = 20.0;
        let graph = RouteGraph::from_edges(&[0, 1, 0, 2], &[1, 0, 2, 0], &[true; 4], &[0.05; 4], 3)
            .with_cargo(CargoConfig::default());
        let intent = bulk_plan(&regions, &graph).unwrap();
        assert_eq!(intent.dest_region, 2);
        assert_eq!(intent.cargo_qty, RIVER_CARGO_CAP);
        let table = bfs_from(&graph, 0);
        let one = evaluate_route(0, 7, 0, &regions, &table, &ShadowLedger::new(3), None).unwrap();
        assert_eq!(one.dest_region, 1, "one load goes to the dearest market");
    }

    #[test]
    fn test_bulk_loads_count_against_the_market_for_the_next_merchant() {
        // Two merchants with room for 20 loads, one market: the first fills it
        // to the one-load margin; the second finds no trip left.
        let (regions, mut graph) = bulk_world(30.0, 0.4);
        graph.cargo.land = 20.0;
        let mut pool = AgentPool::new(2);
        for _ in 0..2 {
            pool.spawn(0, 0, crate::agent::Occupation::Merchant, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        }
        let mut ledger = ShadowLedger::new(2);
        let mut buf = DeliveryBuffer::new(2);
        buf.physical_stock = true;
        merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0; 32], Some(&mut buf));
        assert_eq!(planned_destinations(&pool), vec![1], "one merchant fills the market");
        let q = ledger.reserved[0][0];
        assert!(q > 2.0 && q < 3.0, "{q}");
    }

    #[test]
    fn test_unknown_food_demand_takes_one_load_and_legacy_cargo_is_one_load() {
        let (mut regions, graph) = bulk_world(10.0, 0.4);
        regions[1].market_demand[CAT_FOOD] = 0.0;
        assert_eq!(bulk_plan(&regions, &graph).unwrap().cargo_qty, MERCHANT_CARGO_CAP);
        // CargoConfig::LEGACY plans one load as `evaluate_route` does.
        let (regions, graph) = bulk_world(10.0, 0.4);
        let graph = graph.with_cargo(CargoConfig::LEGACY);
        let bulk = bulk_plan(&regions, &graph).unwrap();
        let table = bfs_from(&graph, 0);
        let one = evaluate_route(0, 7, 0, &regions, &table, &ShadowLedger::new(2), None).unwrap();
        assert_eq!((bulk.dest_region, bulk.good_slot, bulk.cargo_qty), (one.dest_region, one.good_slot, one.cargo_qty));
        assert_eq!(bulk.cargo_qty, MERCHANT_CARGO_CAP);
    }

    #[test]
    fn test_wares_travel_to_markets_that_want_them_but_are_not_advertised() {
        // A city (region 0) with wares in stock and none wanted at home; a
        // market (region 1) whose people want wares and have none.
        let mut regions = make_test_regions(2);
        for r in regions.iter_mut() {
            r.stockpile = [0.0; NUM_GOODS];
            r.food_sufficiency = 1.0;
            r.market_demand[CAT_FOOD] = 10.0;
        }
        regions[0].stockpile[crate::economy::SLOT_CRAFTS] = 6.0;
        regions[0].market_supply[CAT_CRAFT] = 6.0;
        regions[1].market_demand[CAT_CRAFT] = 1.0;
        let graph = line_graph(2).with_cargo(CargoConfig::default());
        let table = bfs_from(&graph, 0);
        let tally = MarketTally::new(2);
        let intent = evaluate_route_with_tally(0, 7, 0, &regions, &table, &ShadowLedger::new(2), None, &tally, Some(&graph))
            .unwrap();
        assert_eq!((intent.dest_region, intent.good_slot as usize), (1, crate::economy::SLOT_CRAFTS));
        assert!(intent.cargo_qty > 0.0 && intent.cargo_qty <= LAND_CARGO_CAP);
        // The market's price for wares is at the cap, but its packets do not
        // advertise them.
        assert_eq!(market_price(&regions[1], CAT_CRAFT, 0.0), MAX_PLANNER_PRICE);
        assert_eq!(market_signal(&regions[1]), 0.0);
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

// ---------------------------------------------------------------------------
// Exact checkpoint state (`crate::persist`): every field, in declaration order.
// ---------------------------------------------------------------------------

crate::persist_struct!(RouteGraph {
    adj, num_regions, edge_count, sea_lanes, cargo,
} transient { receipt_limit });
crate::persist_struct!(CargoConfig {
    land, river, sea, fill,
});
crate::persist_struct!(ShadowLedger {
    reserved, in_transit_out, pending_delivery,
});
crate::persist_struct!(DeliveryBuffer {
    physical_stock, departure_debits, arrival_imports, return_credits, diagnostics,
});
crate::persist_struct!(ArrivalRecord {
    source_region, dest_region, good_slot, qty,
});
crate::persist_struct!(DeliveryDiagnostics {
    total_departures, total_arrivals, total_returns, total_transit_decay,
});
crate::persist_struct!(MerchantTripStats {
    active_trips, completed_trips, avg_trip_duration, total_in_transit_qty, route_utilization,
    disruption_replans, unwind_count, stalled_trip_count, overcommit_count,
    plans_packet_driven, plans_bootstrap, no_usable_packets, sea_log, raided_trips,
} transient { receipts });
crate::persist_struct!(SeaCrossing {
    from_region, to_region, origin_region, dest_region, good_slot, qty, loss,
});
crate::persist_enum!(LossReason {
    TransitDecay = 0, Raid = 1, Disruption = 2, Spoilage = 3,
});
