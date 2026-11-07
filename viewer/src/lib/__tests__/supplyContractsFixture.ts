/** Constructed complete contract fixtures; not held evidence or natural outcomes. */
import type { TurnSnapshot } from "../../types";
export const order = { id: 1, holder: 42, origin: 0, dest: 1, seller: 0, payer: 1, path: [0,1], cursor: 0,
  dispatched_turn: 2, last_moved_turn: null, status: "moving", outcome: null, closed_turn: null,
  cargo_open_milli: 1000, cargo_milli: 1000, delivered_milli: 0, lost_milli: 0, deposited_milli: 0,
  purchase_milli: 500, sale_price_milli: 600, price_turn: 1, cash: 1000, escrowed_milli: 1000,
  credited_milli: 0, refunded_milli: 0, withheld: 0 };
export const timber = { schema_version: 1, stage: "A4-3", source_turn: 2, orders: [order], closed: [],
  frame: { turn: 2, events: [{ kind: "dispatched", order: 1, holder: 42, origin: 0, dest: 1, region: 0,
    bought_milli: 1000, purchase_milli: 500, escrowed_milli: 1000 }], events_dropped: 0, withheld: [], dispatched: { "1": 1000 }, spent: { "1": 1 } },
  counters: { dispatched: 1 }, parameters: { freight: 0.1, max_age: 12, max_orders: 64, max_events: 256 } };
export const requisition = { schema_version: 1, stage: "D4", mode: "transfer", enabled: true, source_turn: 2,
  frame: { turn: 2, events: [{ source_turn: 2, kind: "cargo_seizure", shipment: 3, owner: 42, region: 0, payer: 1,
    removed_milli: 1200, allocations: [{ army: "army-7", rations: 2 }], destroyed_milli: 200 }], events_dropped: 0,
    claims: [{ id: 5, turn: 2, payer: 1, owner: 42, region: 0, due_milli: 800, paid_milli: 300, source: "cargo", status: "open" }],
    claims_dropped: 0, claims_open: 1, claims_due_milli: 500 }, counters: {} };
export const supplySnapshot = (key: string, record: unknown) => ({ turn: 3, livelihoods: { schema_version: 1, [key]: record } }) as unknown as TurnSnapshot;
