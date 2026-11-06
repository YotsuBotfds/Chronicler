import { describe, expect, it } from "vitest";
import { migrationClosed, quarantineModeLabel, readQuarantineRules, totalOf } from "../quarantineRules";
import {
  AGGREGATE_CLOSURE_RECORD, migrationRecord, quarantineRecord,
} from "../../__fixtures__/quarantineRules";

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

  it("reads a migration closure's refusals and keeps its states distinct (C1b)", () => {
    const reading = readQuarantineRules({ quarantine_rules: migrationRecord() });
    expect(reading.state).toBe("recorded");
    if (reading.state !== "recorded") return;
    expect(migrationClosed(reading.record)).toBe(true);
    expect(quarantineModeLabel(reading.record)).toBe("Closure (trade and migration closed)");
    expect(reading.record.receipt?.migrants_blocked).toBe(9);
    expect(reading.record.receipt?.migrants_blocked_flight).toBe(1);
    expect(reading.record.receipt?.migrants_blocked_hunger).toBe(0);
    expect(reading.record.receipt?.migrants_refused_first).toBe(9);
    expect(reading.record.receipt?.migration_refusals?.map((r) => [r.closure, r.persons])).toEqual([[1, 1], [3, 8]]);
    expect(reading.record.totals.migrants_blocked).toBe(11);
    expect(reading.record.totals.migrants_refused_persons).toBe(11);
    expect(reading.record.exempt).not.toContain("migrants");
    // Not observed (null) and a recorded zero stay apart.
    const receipt = migrationRecord().receipt as Record<string, unknown>;
    const unobserved = readQuarantineRules({ quarantine_rules: migrationRecord({ receipt: {
      ...receipt, migrants_blocked: null, migrants_blocked_flight: null, migrants_blocked_hunger: null,
      migrants_refused_first: null, migration_refusals: null } }) });
    expect(unobserved.state === "recorded" && unobserved.record.receipt?.migrants_blocked).toBeNull();
    const zero = readQuarantineRules({ quarantine_rules: migrationRecord({ receipt: {
      ...receipt, migrants_blocked: 0, migrants_blocked_flight: 0, migration_refusals: [] } }) });
    expect(zero.state === "recorded" && zero.record.receipt?.migrants_blocked).toBe(0);
    // A trade-only record carries no migration values at all.
    const trade = readQuarantineRules({ quarantine_rules: quarantineRecord() });
    expect(trade.state === "recorded" && migrationClosed(trade.record)).toBe(false);
    expect(trade.state === "recorded" && trade.record.receipt?.migrants_blocked).toBeNull();
    expect(trade.state === "recorded" && trade.record.totals.migrants_blocked).toBeNull();
    expect(trade.state === "recorded" && trade.record.totals.migrants_refused_persons).toBeNull();
  });

  it("refuses a malformed migration record", () => {
    const receipt = migrationRecord().receipt as Record<string, unknown>;
    const missing = { ...receipt };
    delete missing.migrants_blocked;
    for (const [overrides, message] of [
      [{ receipt: missing }, "receipt.migrants_blocked is missing for the migration channel"],
      [{ receipt: { ...receipt, migrants_blocked: 4 } }, "receipt.migrants_blocked must equal the persons of its refusals"],
      [{ receipt: { ...receipt, migration_refusals: null } },
        "receipt.migrants_blocked and receipt.migration_refusals must both be recorded or both be null"],
      [{ receipt: { ...receipt, migration_refusals: [{ closure: 1 }] } }, "receipt.migration_refusals[0].from must be a string"],
      [{ totals: { ...(migrationRecord().totals as object), migrants_blocked: undefined } }, "totals.migrants_blocked must be an integer"],
      [{ totals: { ...(migrationRecord().totals as object), migrants_refused_persons: undefined } },
        "totals.migrants_refused_persons must be an integer"],
    ] as const) {
      expect(readQuarantineRules({ quarantine_rules: migrationRecord(overrides) })).toEqual(
        { state: "malformed", error: message });
    }
  });
});
