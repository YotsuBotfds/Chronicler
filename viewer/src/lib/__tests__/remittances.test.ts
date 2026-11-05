import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { diasporaCounts, remittancesAt, remittancesFunnel } from "../remittances";

/** Constructed observations to test the reader; not a simulation run. */
const receipt = { turn: 7, sender: 10, recipient: 20, bond: "marriage", sentiment: 30, origin: 0, destination: 1,
  wealth_milli: 7000, amount: 425, fee_requested: 75, sent: 500, fee: 75, credited: 425, refunded: 0, status: "applied" };
const refund = { ...receipt, sender: 11, recipient: 21, bond: "kin", wealth_milli: 12000, amount: 850,
  fee_requested: 150, sent: 1000, fee: 150, credited: 299, refunded: 551, status: "limited" };
const zero = { region: 0, departures: 0, arrivals: 0, returns_home: 0, qualified_departures: 0, qualified_arrivals: 0,
  diaspora_out: 0, diaspora_in: 0, qualified_out: 0, qualified_in: 0, senders: 0, recipients: 0, outflow_milli: 0,
  fee_milli: 0, refunded_milli: 0, inflow_milli: 0 };
const regions = [
  { ...zero, region: 0, departures: 1, arrivals: 1, returns_home: 1, diaspora_out: 2, recipients: 2, inflow_milli: 724 },
  { ...zero, region: 1, departures: 1, arrivals: 1, diaspora_in: 2, senders: 2, outflow_milli: 949, fee_milli: 225,
    refunded_milli: 551 },
];
const totals = { requested_milli: 1275, fee_requested_milli: 225, sent_milli: 1500, fee_milli: 225,
  credited_milli: 724, refunded_milli: 551, debited_milli: 949, not_sent_milli: 0 };
const record = { schema_version: 1, stage: "RS4", mode: "send", source_turn: 7,
  funnel: { open_entries: 3, eligible: 3, linked: 2, rows: 2, applied: 1, limited: 1 }, totals, regions,
  moves: [{ id: 12, from_region: 1, to_region: 0, kind: "return", qualified: false, driver: null },
    { id: 13, from_region: 0, to_region: 1, kind: "departure", qualified: true, driver: 2 }],
  moves_dropped: 0,
  closures: [{ id: 12, origin: 0, destination: 1, departure_turn: 2, closed_turn: 7, reason: "return" }],
  closures_dropped: 0, receipts: [receipt, refund], receipts_dropped: 0,
  unmet: [{ id: 14, origin: 0, destination: 1, reason: "recipient_away", surplus_milli: 3000 }], unmet_dropped: 0,
  last_pool_reset: null, counters: { sender_turns_evaluated: 9, rows: 2, rows_applied: 1, credited_milli: 724 },
  parameters: { settled_turns: 5, share_permille: 100, reserve_milli: 2000, cap_milli: 1000, fee_permille: 150,
    min_sentiment: 20, adult_age: 20, max_entries: 2048 } };
const snap = (remittances: unknown, turn = 8) =>
  ({ turn, livelihoods: { schema_version: 1, remittances } } as unknown as TurnSnapshot);
const blank = { ...record, funnel: null, totals: null, regions: null, moves: null, moves_dropped: null, closures: null,
  closures_dropped: null, receipts: null, receipts_dropped: null, unmet: null, unmet_dropped: null };

describe("remittances reader", () => {
  it("reads dated, well-formed records only", () => {
    expect(remittancesAt(snap(record), 2)?.receipts?.[1].refunded).toBe(551);
    expect(remittancesAt(snap(record, 9), 2)).toBeNull();                      // misdated
    expect(remittancesAt(snap(record), 1)).toBeNull();                         // region out of range
    expect(remittancesAt(snap({ ...record, stage: "RS0" }), 2)).toBeNull();
    expect(remittancesAt(snap({ ...record, mode: "sometimes" }), 2)).toBeNull();
    expect(remittancesAt(null, 2)).toBeNull();
  });

  it("refuses money created or lost, and a misdated receipt", () => {
    const made = { ...receipt, credited: 500 };
    expect(remittancesAt(snap({ ...record, receipts: [made, refund] }), 2)).toBeNull();
    expect(remittancesAt(snap({ ...record, receipts: [{ ...receipt, turn: 6 }, refund] }), 2)).toBeNull();
    expect(remittancesAt(snap({ ...record, receipts: [{ ...receipt, refunded: 1, credited: 424 }, refund] }), 2)).toBeNull();
    expect(remittancesAt(snap({ ...record, receipts: [{ ...receipt, status: "absent" }, refund] }), 2)).toBeNull();
    expect(remittancesAt(snap({ ...record, receipts: [{ ...receipt, destination: 0 }, refund] }), 2)).toBeNull();
    expect(remittancesAt(snap({ ...record, totals: { ...totals, debited_milli: 950 } }), 2)).toBeNull();
    const lost = [{ ...regions[0], inflow_milli: 700 }, regions[1]];
    expect(remittancesAt(snap({ ...record, regions: lost }), 2)).toBeNull();
    const unpaired = [{ ...regions[0], departures: 2 }, regions[1]];
    expect(remittancesAt(snap({ ...record, regions: unpaired }), 2)).toBeNull();
  });

  it("refuses money moved by the record-only control", () => {
    expect(remittancesAt(snap({ ...record, mode: "record_only" }), 2)).toBeNull();
    const kept = { ...receipt, sent: 0, fee: 0, credited: 0, refunded: 0, status: "not_sent" };
    const control = { ...record, mode: "record_only", receipts: [kept],
      totals: { ...totals, sent_milli: 0, fee_milli: 0, credited_milli: 0, refunded_milli: 0, debited_milli: 0 },
      regions: [{ ...regions[0], recipients: 0, inflow_milli: 0 }, { ...regions[1], senders: 0, outflow_milli: 0,
        fee_milli: 0, refunded_milli: 0 }] };
    expect(remittancesAt(snap(control), 2)?.mode).toBe("record_only");
    expect(remittancesAt(snap({ ...record, receipts: [kept, refund] }), 2)).toBeNull();   // not_sent while sending
  });

  it("keeps an unobserved turn unknown, not zero, and refuses half a frame", () => {
    const parsed = remittancesAt(snap(blank), 2);
    expect(parsed?.receipts).toBeNull();
    expect(parsed?.regions).toBeNull();
    expect(remittancesAt(snap({ ...blank, receipts: [] }), 2)).toBeNull();
    expect(remittancesAt(snap({ ...record, unmet: [{ ...record.unmet[0], reason: "lonely" }] }), 2)).toBeNull();
    expect(remittancesAt(snap({ ...record, closures: [{ ...record.closures[0], closed_turn: 6 }] }), 2)).toBeNull();
  });

  it("orders the funnel and counts missing counters as zero once the record exists", () => {
    const parsed = remittancesAt(snap(record), 2)!;
    const funnel = remittancesFunnel(parsed);
    expect(funnel[0]).toEqual(["Migrant-turns evaluated (open ledger entries)", 9]);
    expect(funnel.find(([k]) => k.startsWith("Unmet"))?.[1]).toBe(0);
    expect(diasporaCounts(parsed)[0]).toEqual(["Applied moves seen", 0]);
  });
});

describe("remittances reader on a natural record", () => {
  it("accepts the record the simulation wrote", async () => {
    const fixture = (await import("../../__fixtures__/remittances_natural_record.json")).default;
    const parsed = remittancesAt(snap(fixture.remittances, fixture.turn), fixture.region_count);
    expect(parsed).not.toBeNull();
    expect(parsed!.receipts!.length).toBeGreaterThan(0);
    expect(parsed!.unmet!.length).toBeGreaterThan(0);
    expect(new Set(parsed!.closures!.map((c) => c.reason))).toEqual(new Set(["return", "death"]));
    expect(remittancesAt(snap(fixture.remittances, fixture.turn), 2)).toBeNull();
  });
});
