import { describe, expect, it } from "vitest";
import { debtEvidenceFixture } from "../../__fixtures__/debtEvidence";
import { readDebtEvidence } from "../debtEvidence";

describe("recorded debt evidence", () => {
  it("reads fiscal flows independently of total debt stocks and their foreign subset", () => {
    const reading = readDebtEvidence(debtEvidenceFixture(), 3, 0, 3);
    expect(reading.selected).toMatchObject({ turn: 3, sourceTurn: 2, status: "recorded", values: {
      debt: 250, foreignDebt: 50, borrowed: 90, service: 20, interestPaid: 5, principalPaid: 15, shortfall: 3,
    } });
    expect(reading.rows[0].values.principalPaid).toBe(8);
    expect(reading.selected!.principalSources).toEqual(["/history/1/finance/civs/A/debt_service", "/history/1/finance/civs/A/interest"]);
    expect(reading.selected!.values.debt).not.toBe(300);
  });

  it("never derives principal from debt changes, mixed loans, defaults or global totals", () => {
    const bundle = debtEvidenceFixture();
    const previous = bundle.history[0].finance!.civs.A, current = bundle.history[1].finance!.civs.A;
    previous.debt = 999;
    current.debt = 1;
    current.borrowed = 9999;
    const reading = readDebtEvidence(bundle, 3, 0);
    expect(reading.selected!.values.principalPaid).toBe(15);
    expect(reading.selected!.values.writtenOff).toBe(11);
    expect(reading.selected!.writtenOffSource).toBe("/history/1/finance/domestic_credit/holders/A/written_off");
    expect(JSON.stringify(reading)).not.toContain("88888");
    expect(JSON.stringify(reading)).not.toContain("77777");
  });

  it("keeps unknown old fields and inconsistent service/interest unknown, preserving measured zeros", () => {
    const bundle = debtEvidenceFixture();
    const row = bundle.history[1].finance!.civs.A;
    row.interest = 30;
    expect(readDebtEvidence(bundle, 3, 0).selected!.values.principalPaid).toBeNull();
    expect(readDebtEvidence(bundle, 3, 0).selected!.explanation).toContain("inconsistent row");
    Reflect.deleteProperty(row, "interest");
    Reflect.deleteProperty(row, "borrowed");
    row.shortfall = NaN;
    const values = readDebtEvidence(bundle, 3, 0).selected!.values;
    expect(values).toMatchObject({ interestPaid: null, principalPaid: null, borrowed: null, shortfall: null });
    row.interest = 0; row.debt_service = 0; row.borrowed = 0;
    expect(readDebtEvidence(bundle, 3, 0).selected!.values).toMatchObject({ interestPaid: 0, service: 0, principalPaid: 0, borrowed: 0 });
  });

  it("exposes only named boundary claims and rates, never allocations of paid interest", () => {
    const reading = readDebtEvidence(debtEvidenceFixture(), 3, 0);
    expect(reading.claims).toEqual([
      { label: "City Harbor Council", kind: "domestic", principal: 20, rate: .04,
        sourceRef: "/history/1/finance/domestic_credit/holders/A/cities/Harbor Council", rateSourceRef: "/history/1/finance/domestic_credit/holders/A/rate" },
      { label: "B", kind: "foreign", principal: 50, rate: .06,
        sourceRef: "/history/1/finance/domestic_credit/holders/A/foreign/B/0", rateSourceRef: "/history/1/finance/domestic_credit/holders/A/foreign/B/1" },
    ]);
    expect(reading.coverage.join(" ")).toContain("Borrower payments are not allocated to lenders");
    expect(readDebtEvidence(debtEvidenceFixture(), 1, 0).claims).toEqual([]);
    expect(readDebtEvidence(debtEvidenceFixture(), 1, 0).selected!.values.writtenOff).toBeNull();
  });

  it("gates explicit credit events to completed tick+1 with borrower and creditor roles", () => {
    const bundle = debtEvidenceFixture();
    expect(readDebtEvidence(bundle, 2, 0).events.map((item) => item.event.event_type)).toEqual(["loan_taken"]);
    expect(readDebtEvidence(bundle, 3, 0).events.map((item) => item.role)).toEqual(["borrower", "borrower", "fiscal subject"]);
    const creditor = readDebtEvidence(bundle, 3, 1).events;
    expect(creditor.map((item) => item.role)).toEqual(["named creditor", "named creditor"]);
    expect(creditor[1]).toMatchObject({ turn: 3, borrower: "A", sourceRef: "/events_timeline/1" });
  });

  it("keeps events after a borrower's pruned final row without manufacturing payments", () => {
    const reading = readDebtEvidence(debtEvidenceFixture(), 6, 0);
    expect(reading.selected!.status).toBe("absent");
    expect(Object.values(reading.selected!.values).every((value) => value === null)).toBe(true);
    expect(reading.events.at(-1)).toMatchObject({ turn: 6, role: "borrower", event: { event_type: "debt_written_off" } });
    expect(reading.claims).toEqual([]);
  });

  it("never leaks future events, final balances or future claim names on rewind", () => {
    const reading = readDebtEvidence(debtEvidenceFixture(), 3, 0);
    expect(JSON.stringify(reading)).not.toContain("FUTURE_SECRET");
    expect(JSON.stringify(reading)).not.toContain("99999999");
    expect(reading.events.every((item) => item.turn <= 3)).toBe(true);
  });

  it("distinguishes sparse missing snapshots, absent borrower rows and unavailable subsystem records", () => {
    const bundle = debtEvidenceFixture();
    delete bundle.history[0].finance;
    const reading = readDebtEvidence(bundle, 6, 0, 6);
    expect(reading.rows.map((row) => row.status)).toEqual(["missing", "missing", "recorded", "missing", "missing", "absent"]);
    expect(reading.rows[0].explanation).toContain("Finance subsystem not recorded");
    expect(reading.rows[1].explanation).toContain("Snapshot not recorded");
    expect(reading.selected!.explanation).toContain("not zero debt");
  });

  it("refuses duplicate snapshot observations and preserves input bytes/order", () => {
    const bundle = debtEvidenceFixture();
    bundle.history.push(structuredClone(bundle.history[1]));
    bundle.history.reverse();
    const before = JSON.stringify(bundle);
    const reading = readDebtEvidence(bundle, 3, 0);
    expect(reading.selected!.status).toBe("ambiguous");
    expect(reading.selected!.values.debt).toBeNull();
    expect(reading.claims).toEqual([]);
    expect(JSON.stringify(bundle)).toBe(before);
  });

  it("refuses duplicate civilization-name identities without assigning liability", () => {
    const bundle = debtEvidenceFixture();
    bundle.world_state.civilizations.push({ ...bundle.world_state.civilizations[0] });
    const reading = readDebtEvidence(bundle, 3, 0);
    expect(reading.status).toContain("Repeated civilization name");
    expect(reading.rows).toEqual([]);
    expect(reading.events).toEqual([]);
  });

  it("does not expose an unrecorded future civilization name from its array index", () => {
    const bundle = debtEvidenceFixture();
    bundle.world_state.civilizations.push({ ...bundle.world_state.civilizations[0], name: "FUTURE_SECRET_REALM" });
    const reading = readDebtEvidence(bundle, 3, 2);
    expect(reading.name).toBe("Civilization 2 (name not recorded)");
    expect(reading.rows).toEqual([]);
    expect(JSON.stringify(reading)).not.toContain("FUTURE_SECRET");
  });

  it("does not establish fiscal payment execution from an opening snapshot", () => {
    const bundle = debtEvidenceFixture();
    bundle.history[0].turn = 0;
    const reading = readDebtEvidence(bundle, 0, 0);
    expect(reading.selected!.sourceTurn).toBeNull();
    expect(reading.selected!.values).toMatchObject({ debt: 100, service: null, borrowed: null, interestPaid: null, principalPaid: null });
    expect(reading.events).toEqual([]);
  });

  it("bounds the window and does not infer per-turn writeoff flows from first known cumulative amounts", () => {
    const bundle = debtEvidenceFixture();
    expect(readDebtEvidence(bundle, 200, 0, 500).rows).toHaveLength(100);
    const reading = readDebtEvidence(bundle, 3, 0, 1);
    expect(reading.rows).toHaveLength(1);
    expect(reading.from).toBe(3);
    expect(reading.selected!.values.writtenOff).toBe(11);
    expect(reading.coverage.join(" ")).toContain("cumulative, not this tick's flows");
    expect(readDebtEvidence(bundle, NaN, 0).rows).toEqual([]);
    expect(readDebtEvidence(bundle, 3, null).selected).toBeNull();
  });

  it("withholds ambiguous event inspection links without rewriting dated source context", () => {
    const bundle = debtEvidenceFixture();
    bundle.events_timeline.push({ ...bundle.events_timeline[0] });
    const reading = readDebtEvidence(bundle, 3, 0);
    expect(reading.events.filter((item) => item.event.event_id === "loan-0").every((item) => !item.canInspect)).toBe(true);
    expect(reading.events.find((item) => item.event.event_id === "default-2")?.canInspect).toBe(true);
  });
});
