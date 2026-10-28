import { describe, expect, it } from "vitest";
import observations from "../../__fixtures__/transaction_observations.json";
import { transactionFixture } from "../../__fixtures__/transactionHistory";
import { nativeTransactionsAt, publicPurchasesAt, transactionGood, transactionHistory } from "../transactions";
import { presentSystems } from "../systems";
import { snapshotFromMessage } from "../transport";

describe("independent transaction observation domains", () => {
  it("reads actual separate public-only, native, shadow and combined controlled sources", () => {
    const publicOnly = transactionFixture("public-foreign")[0];
    expect(nativeTransactionsAt(publicOnly)).toBeNull();
    expect(publicPurchasesAt(publicOnly)).toMatchObject({ source_turn: 30, available: true, complete: true,
      rows: [{ buyer_paid: 1, foreign_ruler_credited: 1, domestic_producer_sink: 0, sent: 8, received: 7.6 }] });
    expect(observations["public-foreign"].source.scope).toMatch(/controlled/i);
    expect(nativeTransactionsAt(transactionFixture("native-shadow")[0])!.rows.every((row) => row.cargo_basis === "virtual_shadow")).toBe(true);
    expect(nativeTransactionsAt(transactionFixture("native-bridge")[0])!.rows.every((row) => row.cargo_basis === "regional_stock")).toBe(true);
    const combined = transactionFixture("hybrid-public")[0];
    expect(nativeTransactionsAt(combined)!.source_turn).toBe(0);
    expect(publicPurchasesAt(combined)!.source_turn).toBe(0);
  });

  it.each(["public-own-market", "public-same-realm"] as const)("preserves the actual domestic sink in %s", (name) => {
    expect(publicPurchasesAt(transactionFixture(name)[0])!.rows[0]).toMatchObject({ buyer_paid: 1,
      foreign_ruler_credited: 0, domestic_producer_sink: 1, seller_treasury_before: null, seller_treasury_after: null });
  });

  it("guards future and stale actual rows independently", () => {
    const row = transactionFixture("hybrid-public")[0];
    row.transaction_receipts!.rows[0].source_turn = 9;
    expect(nativeTransactionsAt(row)).toBeNull();
    expect(publicPurchasesAt(row)).not.toBeNull();
    const other = transactionFixture("hybrid-public")[1];
    other.transaction_receipts!.public_purchases!.rows[0].source_turn = 0;
    expect(publicPurchasesAt(other)).toBeNull();
    expect(nativeTransactionsAt(other)).not.toBeNull();
    other.transaction_receipts!.source_turn = 8;
    expect(nativeTransactionsAt(other)).toBeNull();
  });

  it("allows a dated not-captured marker without presenting it as an observed zero", () => {
    const row = transactionFixture("native-bridge")[0];
    expect(publicPurchasesAt(row)).toMatchObject({ source_turn: null, as_of_turn: 0, available: false, complete: false });
    row.transaction_receipts!.public_purchases!.as_of_turn = 7;
    expect(publicPurchasesAt(row)).toBeNull();
  });

  it("rejects contradictory complete or unexecuted frames but retains genuine partial rows", () => {
    const row = transactionFixture("hybrid-public")[0], frame = row.transaction_receipts!;
    frame.mobility_executed = false;
    expect(nativeTransactionsAt(row)).toBeNull();
    frame.mobility_executed = true; frame.dropped_rows = 3;
    expect(nativeTransactionsAt(row)).toBeNull();
    frame.complete = false;
    expect(nativeTransactionsAt(row)!.rows).toHaveLength(2);
    frame.public_purchases!.dropped_rows = 2;
    expect(publicPurchasesAt(row)).toBeNull();
    frame.public_purchases!.complete = false;
    expect(publicPurchasesAt(row)!.rows).toHaveLength(2);
  });

  it("keeps missing history unknown and stops at the selected saved snapshot", () => {
    const history = transactionFixture("hybrid-public");
    delete history[1].transaction_receipts;
    const rows = transactionHistory(history, 3);
    expect(rows.map((row) => row.turn)).toEqual([3, 2, 1]);
    expect(rows[1]).toMatchObject({ native: null, public: null });
    expect(nativeTransactionsAt(null)).toBeNull();
    expect(publicPurchasesAt(null)).toBeNull();
  });

  it("uses fixed economy good slots and preserves nested independent domains in transport", () => {
    expect(transactionGood(1)).toBe("fish"); expect(transactionGood(3)).toBe("timber"); expect(transactionGood(8)).toBe("crafts");
    const row = transactionFixture("public-foreign")[0];
    expect(snapshotFromMessage({ ...row, type: "turn" })).toEqual(row);
    expect(presentSystems([row])).toEqual(["food"]);
  });
});
