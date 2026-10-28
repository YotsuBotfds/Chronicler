//! Optional, bounded observations of merchant mobility, never private accounts.
//!
//! Quantities describe existing ledger operations at the mobility boundary.
//! Arrival settlement/decay happens later in the goods economy. This module
//! neither assigns cargo title nor makes cash/insurance claims.
use std::sync::Arc;
use arrow::array::{ArrayRef, BooleanArray, Float32Array, UInt16Array, UInt32Array, UInt8Array};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use crate::{pool::AgentPool, region::RegionState};

pub const DEFAULT_LIMIT: usize = 4096;
pub const MAX_LIMIT: usize = 65536;
// Append-only operation codes. These identify observations, not voyages.
pub const RESERVED: u8 = 0;
pub const DEPARTED: u8 = 1;
pub const CANCELLED: u8 = 2;
pub const REPLANNED: u8 = 3;
pub const RETURNED: u8 = 4;
pub const SEA_CROSSING: u8 = 5;
pub const ARRIVED: u8 = 6;
pub const ACTIVE: u8 = 7;
pub const NO_LOSS: u8 = 255;

#[derive(Clone, Debug)]
pub struct Receipt {
    pub merchant_id: u32,
    pub merchant_civ: u8,
    pub operation: u8,
    pub origin_region: u16,
    pub dest_region: u16,
    pub from_region: u16,
    pub to_region: u16,
    pub good_slot: u8,
    pub quantity: f32,
    pub origin_controller: u8,
    pub dest_controller: u8,
    pub physical_stock: bool,
    pub loss_reason: u8,
}

#[derive(Clone, Debug)]
pub struct ReceiptFrame {
    pub source_turn: u32,
    pub limit: usize,
    pub dropped: u64,
    pub mobility_executed: bool,
    pub rows: Vec<Receipt>,
}
impl ReceiptFrame {
    pub fn new(source_turn: u32, limit: usize) -> Self {
        Self { source_turn, limit, dropped: 0, mobility_executed: true, rows: Vec::with_capacity(limit.min(128)) }
    }
    pub fn push(&mut self, row: Receipt) {
        if self.rows.len() < self.limit { self.rows.push(row); }
        else { self.dropped = self.dropped.saturating_add(1); }
    }
}

/// Called only from existing mobility loops. Off means no allocation or pool reads.
pub fn record(frame: &mut Option<ReceiptFrame>, pool: &AgentPool, regions: &[RegionState],
              slot: usize, operation: u8, from: u16, to: u16, physical_stock: bool,
              loss_reason: u8) {
    let Some(frame) = frame else { return; };
    frame.push(observe(pool, regions, slot, operation, from, to, physical_stock, loss_reason));
}

pub fn observe(pool: &AgentPool, regions: &[RegionState], slot: usize, operation: u8,
               from: u16, to: u16, physical_stock: bool, loss_reason: u8) -> Receipt {
    let origin = pool.trip_origin_region[slot];
    let dest = pool.trip_dest_region[slot];
    Receipt {
        merchant_id: pool.ids[slot], merchant_civ: pool.civ_affinities[slot], operation,
        origin_region: origin, dest_region: dest, from_region: from, to_region: to,
        good_slot: pool.trip_good_slot[slot], quantity: pool.trip_cargo_qty[slot],
        origin_controller: regions.get(origin as usize).map_or(255, |r| r.controller_civ),
        dest_controller: regions.get(dest as usize).map_or(255, |r| r.controller_civ),
        physical_stock, loss_reason,
    }
}

/// Separate new API; existing sea log/stats schemas do not change.
pub fn to_batch(frame: Option<&ReceiptFrame>) -> Result<RecordBatch, arrow::error::ArrowError> {
    let rows = frame.map_or(&[][..], |f| f.rows.as_slice());
    macro_rules! col { ($name:literal, $dtype:ident, $array:ident, $field:ident) => {
        (Field::new($name, DataType::$dtype, false),
         Arc::new($array::from(rows.iter().map(|r| r.$field).collect::<Vec<_>>())) as ArrayRef)
    }; }
    let columns = vec![
        col!("merchant_id", UInt32, UInt32Array, merchant_id),
        col!("merchant_civ", UInt8, UInt8Array, merchant_civ),
        col!("operation", UInt8, UInt8Array, operation),
        col!("origin_region", UInt16, UInt16Array, origin_region),
        col!("dest_region", UInt16, UInt16Array, dest_region),
        col!("from_region", UInt16, UInt16Array, from_region),
        col!("to_region", UInt16, UInt16Array, to_region),
        col!("good_slot", UInt8, UInt8Array, good_slot),
        col!("quantity", Float32, Float32Array, quantity),
        col!("origin_controller", UInt8, UInt8Array, origin_controller),
        col!("dest_controller", UInt8, UInt8Array, dest_controller),
        col!("physical_stock", Boolean, BooleanArray, physical_stock),
        col!("loss_reason", UInt8, UInt8Array, loss_reason),
    ];
    let (fields, arrays): (Vec<_>, Vec<_>) = columns.into_iter().unzip();
    RecordBatch::try_new(Arc::new(Schema::new(fields)), arrays)
}
