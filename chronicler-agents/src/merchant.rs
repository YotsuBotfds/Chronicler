//! M58a: Merchant mobility — shadow ledger, route graph, trip state machine.

use std::collections::VecDeque;

use crate::agent::MAX_PATH_LEN;
use crate::economy::NUM_GOODS;

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
}
