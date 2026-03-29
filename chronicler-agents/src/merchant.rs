//! M58a: Merchant mobility — shadow ledger, route graph, trip state machine.

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
}
