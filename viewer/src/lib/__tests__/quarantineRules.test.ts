import { describe, expect, it } from "vitest";
import { readQuarantineRules, totalOf } from "../quarantineRules";
import { AGGREGATE_CLOSURE_RECORD, quarantineRecord } from "../../__fixtures__/quarantineRules";

describe("readQuarantineRules", () => {
  it("keeps unknown, legacy, malformed and recorded apart", () => {
    expect(readQuarantineRules(undefined)).toEqual({ state: "unknown" });
    expect(readQuarantineRules(null)).toEqual({ state: "unknown" });
    expect(readQuarantineRules({ active: [], quarantine: ["A"] })).toEqual({ state: "legacy" });
    expect(readQuarantineRules({ quarantine_rules: null }).state).toBe("malformed");
    const reading = readQuarantineRules({ quarantine_rules: quarantineRecord() });
    expect(reading.state).toBe("recorded");
    if (reading.state === "recorded") {
      expect(reading.record.mode).toBe("closure");
      expect(reading.record.closures.map((c) => c.id)).toEqual([1, 2, 3]);
      expect(reading.record.receipt?.merchant_edges_removed).toBe(4);
      expect(reading.record.receipt?.leaked_deliveries).toBe(0);
      expect(reading.record.receipt?.closed_last_tick.length).toBeGreaterThan(0);
      expect(totalOf(reading.record.receipt!.forgone_income)).toBe(4);
    }
    const aggregate = readQuarantineRules({ quarantine_rules: AGGREGATE_CLOSURE_RECORD });
    expect(aggregate.state === "recorded" && aggregate.record.receipt?.merchant_edges_removed).toBeNull();
    expect(aggregate.state === "recorded" && aggregate.record.receipt?.leaked_deliveries).toBeNull();
  });

  it("refuses a malformed record instead of guessing", () => {
    for (const [overrides, message] of [
      [{ schema_version: 2 }, "unsupported schema_version 2"],
      [{ mode: "sometimes" }, "unknown mode sometimes"],
      [{ closures: [{ id: "x" }] }, "closures[0].id must be an integer"],
      [{ totals: {} }, "totals.receipts must be an integer"],
      [{ receipt: { turn: 1 } }, "receipt.phase2_observed must be a boolean"],
    ] as const) {
      expect(readQuarantineRules({ quarantine_rules: quarantineRecord(overrides) })).toEqual(
        { state: "malformed", error: message });
    }
  });

  it("keeps a recorded zero and a value that was not recorded distinct", () => {
    const aggregate = quarantineRecord({ closures: [], receipt: { ...(quarantineRecord().receipt as object),
      decided: [], merchant_edges_removed: null, leaked_deliveries: null, leaked_quantity: null } });
    const reading = readQuarantineRules({ quarantine_rules: aggregate });
    expect(reading.state === "recorded" && reading.record.receipt?.merchant_edges_removed).toBeNull();
    const zero = readQuarantineRules({ quarantine_rules: quarantineRecord({ receipt: { ...(quarantineRecord().receipt as object), merchant_edges_removed: 0 } }) });
    expect(zero.state === "recorded" && zero.record.receipt?.merchant_edges_removed).toBe(0);
    const empty = readQuarantineRules({ quarantine_rules: quarantineRecord({ receipt: null }) });
    expect(empty.state === "recorded" && empty.record.receipt).toBeNull();
  });
});
