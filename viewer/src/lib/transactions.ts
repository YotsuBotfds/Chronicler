import type { TurnSnapshot } from "../types";

const finiteNonnegative = (n: unknown) => typeof n === "number" && Number.isFinite(n) && n >= 0;

/** Native and public observations have separate source clocks and validity. */
export function nativeTransactionsAt(snapshot: TurnSnapshot | null) {
  const frame = snapshot?.transaction_receipts;
  if (!frame || frame.source_turn !== snapshot!.turn - 1 || frame.phase !== "merchant_mobility"
    || !Array.isArray(frame.rows) || !frame.rows.every((row) => row && row.source_turn === frame.source_turn && finiteNonnegative(row.quantity))
    || (!frame.mobility_executed && frame.rows.length > 0)
    || (frame.complete && (!frame.mobility_executed || frame.dropped_rows !== 0))) return null;
  return frame;
}

export function publicPurchasesAt(snapshot: TurnSnapshot | null) {
  const frame = snapshot?.transaction_receipts?.public_purchases;
  if (!frame || frame.phase !== "phase10_granary_procurement" || !Array.isArray(frame.rows)) return null;
  // Not-captured is an explicit unknown, not an observed zero-purchase frame.
  if (frame.source_turn === null) return frame.as_of_turn === snapshot!.turn - 1
    && !frame.available && !frame.complete && frame.rows.length === 0 ? frame : null;
  if (frame.source_turn !== snapshot!.turn - 1 || !frame.rows.every((row) => row && row.source_turn === frame.source_turn
    && [row.sent, row.received, row.transit_loss, row.buyer_paid, row.foreign_ruler_credited, row.domestic_producer_sink].every(finiteNonnegative))
    || (!frame.available && frame.rows.length > 0) || (frame.complete && (!frame.available || frame.dropped_rows !== 0))) return null;
  return frame;
}

export function transactionHistory(history: TurnSnapshot[], through: number) {
  return history.filter((snapshot) => snapshot.turn <= through).map((snapshot) => ({ turn: snapshot.turn,
    native: nativeTransactionsAt(snapshot), public: publicPurchasesAt(snapshot) })).reverse();
}

export function nativeFrameStatus(frame: ReturnType<typeof nativeTransactionsAt>) {
  return !frame ? "Unknown" : !frame.mobility_executed ? "Mobility not executed" : frame.complete ? "Complete observed frame" : "Partial retained frame";
}

export function publicFrameStatus(frame: ReturnType<typeof publicPurchasesAt>) {
  return !frame ? "Unknown" : !frame.available ? `Unavailable: ${frame.unavailable_reason ?? "reason not recorded"}`
    : frame.complete ? "Complete observed frame" : "Partial retained frame";
}

// Fixed economy/FFI good slots, distinct from ResourceType declaration order.
const GOODS = ["grain", "fish", "salt", "timber", "ore", "botanicals", "precious", "exotic", "crafts"];
export function transactionGood(slot: number) { return GOODS[slot] ?? `Unknown good slot ${slot}`; }
export function cargoBasis(basis: string) {
  return basis === "regional_stock" ? "Shared regional stock" : basis === "virtual_shadow" ? "Virtual shadow cargo" : `Unknown cargo basis: ${basis}`;
}
