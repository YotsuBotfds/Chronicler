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

    /// Reserve cargo for a Loading merchant.
    pub fn reserve(&mut self, region: usize, slot: usize, qty: f32) {
        self.reserved[region][slot] += qty;
    }

    /// Cancel a reservation (Loading → Idle on invalidation).
    pub fn cancel_reservation(&mut self, region: usize, slot: usize, qty: f32) {
        self.reserved[region][slot] = (self.reserved[region][slot] - qty).max(0.0);
    }

    /// Depart: move from reserved to in_transit_out (Loading → Transit).
    pub fn depart(&mut self, origin: usize, slot: usize, qty: f32) {
        self.reserved[origin][slot] = (self.reserved[origin][slot] - qty).max(0.0);
        self.in_transit_out[origin][slot] += qty;
    }

    /// Arrive: move from in_transit_out to pending_delivery (Transit → Idle via Arrived).
    pub fn arrive(&mut self, origin: usize, dest: usize, slot: usize, qty: f32) {
        self.in_transit_out[origin][slot] = (self.in_transit_out[origin][slot] - qty).max(0.0);
        self.pending_delivery[dest][slot] += qty;
    }

    /// Unwind: return in-transit cargo to origin (disruption).
    pub fn unwind(&mut self, origin: usize, slot: usize, qty: f32) {
        self.in_transit_out[origin][slot] = (self.in_transit_out[origin][slot] - qty).max(0.0);
    }

    /// Clear all entries for a conquered region. Call AFTER unwinding impacted trips.
    pub fn clear_region(&mut self, region: usize) {
        self.reserved[region] = [0.0; NUM_GOODS];
        self.in_transit_out[region] = [0.0; NUM_GOODS];
        // pending_delivery is monotonic — do not clear
    }
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
        }
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
pub const MERCHANT_CARGO_CAP: f32 = 2.0; // [CALIBRATE]

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
pub fn evaluate_route(
    agent_slot: usize,
    agent_id: u32,
    origin_region: u16,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
) -> Option<TripIntent> {
    let origin = origin_region as usize;
    if origin >= regions.len() {
        return None;
    }

    let origin_margin = regions[origin].merchant_margin;

    // Score all reachable destinations
    let mut best_dest: Option<u16> = None;
    let mut best_score: f32 = MIN_TRIP_PROFIT;
    let mut best_dest_id_tiebreak: (u16, u32) = (u16::MAX, u32::MAX);

    for (dest_idx, &dist) in path_table.dist.iter().enumerate() {
        if dist == 0 || dist == u16::MAX {
            continue;
        }
        let score = origin_margin + regions[dest_idx].merchant_margin;
        let tiebreak = (dest_idx as u16, agent_id);
        if score > best_score || (score == best_score && tiebreak < best_dest_id_tiebreak) {
            best_score = score;
            best_dest = Some(dest_idx as u16);
            best_dest_id_tiebreak = tiebreak;
        }
    }

    let dest = best_dest?;

    // Find best good slot with available cargo
    let mut best_slot: Option<u8> = None;
    let mut best_avail: f32 = 0.0;
    for slot in 0..8u8 {
        if ledger.is_overcommitted(origin, slot as usize, &regions[origin].stockpile) {
            continue;
        }
        let avail = ledger.available(origin, slot as usize, &regions[origin].stockpile);
        if avail > best_avail || (avail == best_avail && best_slot.map_or(true, |s| slot < s)) {
            best_avail = avail;
            best_slot = Some(slot);
        }
    }

    let good_slot = best_slot.filter(|_| best_avail > 0.0)?;
    let cargo_qty = best_avail.min(MERCHANT_CARGO_CAP);

    let (path, path_len) = trace_path(path_table, origin_region, dest)?;

    Some(TripIntent {
        agent_slot,
        origin_region,
        dest_region: dest,
        good_slot,
        cargo_qty,
        path,
        path_len,
    })
}

/// Apply a trip intent to the pool and shadow ledger.
/// Re-checks availability at apply time (two-phase model).
/// Returns true if the reservation was committed, false if rejected.
pub fn apply_trip_intent(
    intent: &TripIntent,
    pool: &mut AgentPool,
    ledger: &mut ShadowLedger,
    regions: &[RegionState],
    stats: &mut MerchantTripStats,
) -> bool {
    let origin = intent.origin_region as usize;
    let slot = intent.good_slot as usize;

    // Re-check at apply time
    if ledger.is_overcommitted(origin, slot, &regions[origin].stockpile) {
        stats.overcommit_count += 1;
        return false;
    }
    let avail = ledger.available(origin, slot, &regions[origin].stockpile);
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
/// Validates next hop first; cancels reservation if invalid.
pub fn depart_merchant(
    pool: &mut AgentPool,
    slot: usize,
    graph: &RouteGraph,
    ledger: &mut ShadowLedger,
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

    // Depart: reserved -> in_transit
    let origin = pool.trip_origin_region[slot] as usize;
    let good = pool.trip_good_slot[slot] as usize;
    ledger.depart(origin, good, pool.trip_cargo_qty[slot]);
    pool.trip_phase[slot] = TRIP_PHASE_TRANSIT;
    true
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
                ledger.unwind(origin_idx, good, qty);
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

/// Run the full merchant mobility phase. Called at step 0.9 in tick_agents.
/// Processes: disruption -> departures -> movement -> arrivals -> route eval -> reservations.
pub fn merchant_mobility_phase(
    pool: &mut AgentPool,
    regions: &[RegionState],
    graph: &RouteGraph,
    ledger: &mut ShadowLedger,
    master_seed: &[u8; 32],
) -> MerchantTripStats {
    let mut stats = MerchantTripStats::default();
    let cap = pool.capacity();

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
                ledger.unwind(origin, good, pool.trip_cargo_qty[slot]);
                stats.stalled_trip_count += 1;
                stats.unwind_count += 1;
                reset_trip_fields(pool, slot);
            }
        }
    }

    // Phase c: Loading invalidation + departure
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_LOADING { continue; }
        depart_merchant(pool, slot, graph, ledger);
    }

    // Phase d-e: Advance Transit merchants + process arrivals
    let mut arrivals: Vec<usize> = Vec::new();
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_TRANSIT { continue; }
        if advance_one_hop(pool, slot, master_seed).is_none() {
            arrivals.push(slot);
        }
    }
    for slot in arrivals {
        let origin = pool.trip_origin_region[slot] as usize;
        let dest = pool.trip_dest_region[slot] as usize;
        let good = pool.trip_good_slot[slot] as usize;
        let qty = pool.trip_cargo_qty[slot];
        ledger.arrive(origin, dest, good, qty);
        let duration = pool.trip_turns_elapsed[slot];
        stats.completed_trips += 1;
        stats.avg_trip_duration += duration as f32;
        reset_trip_fields(pool, slot);
    }
    if stats.completed_trips > 0 {
        stats.avg_trip_duration /= stats.completed_trips as f32;
    }

    // Phase f-g: Route evaluation for idle merchants + cargo reservation
    let mut origin_tables: std::collections::HashMap<u16, PathTable> = std::collections::HashMap::new();
    let mut intents: Vec<TripIntent> = Vec::new();
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_IDLE { continue; }
        if pool.occupations[slot] != crate::agent::Occupation::Merchant as u8 { continue; }
        let origin = pool.regions[slot];
        let table = origin_tables.entry(origin).or_insert_with(|| bfs_from(graph, origin));
        if let Some(intent) = evaluate_route(slot, pool.ids[slot], origin, regions, table, ledger) {
            intents.push(intent);
        }
    }
    intents.sort_by_key(|i| (i.origin_region, pool.ids[i.agent_slot]));
    for intent in &intents {
        apply_trip_intent(intent, pool, ledger, regions, &mut stats);
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
        ledger.depart(0, 0, 3.0);
        assert_eq!(ledger.available(0, 0, &stockpile), 7.0); // reserved→in_transit, same total
    }

    #[test]
    fn test_shadow_ledger_two_sided_accounting() {
        let mut ledger = ShadowLedger::new(2);
        ledger.reserve(0, 0, 5.0);
        assert_eq!(ledger.reserved[0][0], 5.0);
        ledger.depart(0, 0, 5.0);
        assert_eq!(ledger.reserved[0][0], 0.0);
        assert_eq!(ledger.in_transit_out[0][0], 5.0);
        ledger.arrive(0, 1, 0, 5.0);
        assert_eq!(ledger.in_transit_out[0][0], 0.0);
        assert_eq!(ledger.pending_delivery[1][0], 5.0);
    }

    #[test]
    fn test_shadow_ledger_unwind() {
        let mut ledger = ShadowLedger::new(2);
        ledger.reserve(0, 0, 5.0);
        ledger.depart(0, 0, 5.0);
        ledger.unwind(0, 0, 5.0);
        assert_eq!(ledger.in_transit_out[0][0], 0.0);
        assert_eq!(ledger.pending_delivery[0][0], 0.0);
    }

    #[test]
    fn test_shadow_ledger_overcommit_guard() {
        let mut ledger = ShadowLedger::new(1);
        let stockpile = [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        ledger.reserve(0, 0, 6.0);
        ledger.depart(0, 0, 6.0);
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
        ledger.depart(0, 0, 2.0);
        ledger.arrive(0, 1, 0, 2.0);
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
                r.stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
                r
            })
            .collect()
    }

    #[test]
    fn test_evaluate_route_finds_profitable_destination() {
        let regions = make_test_regions(3);
        let graph = RouteGraph::from_edges(
            &[0, 1, 1, 2],
            &[1, 0, 2, 1],
            &[false; 4],
            &[1.0; 4],
            3,
        );
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(3);
        let intent = evaluate_route(0, 1, 0, &regions, &table, &ledger);
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
        regions[1].merchant_margin = 0.0;
        let graph = RouteGraph::from_edges(
            &[0, 1],
            &[1, 0],
            &[false; 2],
            &[1.0; 2],
            2,
        );
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(2);
        let intent = evaluate_route(0, 1, 0, &regions, &table, &ledger);
        assert!(intent.is_none());
    }

    #[test]
    fn test_deterministic_tiebreak_by_region_then_agent() {
        let mut regions = make_test_regions(3);
        regions[1].merchant_margin = 0.5;
        regions[2].merchant_margin = 0.5;
        let graph = RouteGraph::from_edges(
            &[0, 0, 1, 2],
            &[1, 2, 0, 0],
            &[false; 4],
            &[1.0; 4],
            3,
        );
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(3);
        let i1 = evaluate_route(0, 100, 0, &regions, &table, &ledger).unwrap();
        let i2 = evaluate_route(0, 100, 0, &regions, &table, &ledger).unwrap();
        assert_eq!(i1.dest_region, i2.dest_region);
    }

    // -------------------------------------------------------------------
    // Conquest unwind tests
    // -------------------------------------------------------------------

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
        ledger.depart(1, 0, 3.0);

        let mut stats = MerchantTripStats::default();

        // Conquer region 0 — should unwind s0 (Loading, cancel reservation)
        conquest_unwind(&mut pool, &mut ledger, &[0], &mut stats);
        assert_eq!(pool.trip_phase[s0], TRIP_PHASE_IDLE);
        assert_eq!(ledger.reserved[0][0], 0.0);
        // s1 should be unaffected
        assert_eq!(pool.trip_phase[s1], TRIP_PHASE_TRANSIT);

        // Conquer region 3 (s1's destination) — should unwind s1
        conquest_unwind(&mut pool, &mut ledger, &[3], &mut stats);
        assert_eq!(pool.trip_phase[s1], TRIP_PHASE_IDLE);
        assert_eq!(stats.unwind_count, 1); // only transit counts toward unwind_count
    }
}
