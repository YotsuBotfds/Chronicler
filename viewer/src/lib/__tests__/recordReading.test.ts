import { describe, expect, it } from "vitest";
import type { Bundle } from "../../types";
import {
  readFoodAllocation, readGranaryStorage, readRemittances, readRepairProjects, readTimberStock, type RecordReading,
} from "../recordReading";
import { chainBundle, snapshotOf, without } from "./recoveryChainFixture";

/**
 * RL8: absent, malformed, disabled, unobserved, recorded-zero and recorded are
 * distinct readings. The natural records are template seed 23 (recoveryChainFixture);
 * every other case is a constructed edit of snapshot 20, labelled in its name.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
type Rec = Record<string, any>;
type Reader = (bundle: Bundle, snapshot: Bundle["history"][number] | null, turn?: number) => RecordReading<unknown>;

const AT = 20;
const zeroTotals = (totals: Rec) => Object.fromEntries(Object.keys(totals).map((k) => [k, 0]));

interface Case {
  name: string; key: string; read: Reader; label: string; livelihoods: boolean;
  get: (s: Rec) => Rec; set: (s: Rec, value: Rec | undefined) => void;
  misdate: (r: Rec) => void; unobserved?: (r: Rec) => void; zero: (r: Rec) => void; content?: (r: Rec) => void;
}

const lh = (key: string) => ({
  get: (s: Rec) => s.livelihoods[key],
  set: (s: Rec, v: Rec | undefined) => { if (v === undefined) delete s.livelihoods[key]; else s.livelihoods[key] = v; },
});

const CASES: Case[] = [
  { name: "repair projects", key: "repair_projects", read: readRepairProjects, label: "Repair projects", livelihoods: true,
    ...lh("repair_projects"), misdate: (r) => { r.source_turn = 99; },
    unobserved: (r) => { r.receipts = null; r.ledger = null; r.unmet = null; r.suspended = null; },
    zero: (r) => { r.projects = []; r.receipts = []; r.ledger = []; r.unmet = []; } },
  { name: "timber stock", key: "timber_stock", read: readTimberStock, label: "Timber stock", livelihoods: true,
    ...lh("timber_stock"), misdate: (r) => { r.source_turn = 99; },
    unobserved: (r) => { r.observed = false; r.regions = null; r.totals = null; },
    zero: (r) => { r.regions = []; r.totals = { ...zeroTotals(r.totals), slots: 0, capped_slots: 0 }; } },
  { name: "remittances", key: "remittances", read: readRemittances, label: "Remittances", livelihoods: true,
    ...lh("remittances"), misdate: (r) => { r.source_turn = 99; },
    unobserved: (r) => {
      for (const k of ["funnel", "totals", "regions", "moves", "moves_dropped", "closures", "closures_dropped",
        "receipts", "receipts_dropped", "unmet", "unmet_dropped"]) r[k] = null;
    },
    zero: (r) => {
      r.totals = zeroTotals(r.totals); r.regions = []; r.moves = []; r.closures = []; r.receipts = []; r.unmet = [];
    } },
  { name: "food allocation", key: "food_allocation", read: readFoodAllocation, label: "Food allocation", livelihoods: true,
    ...lh("food_allocation"), misdate: (r) => { r.source_turn = 99; },
    unobserved: (r) => { r.totals = null; r.regions = null; r.sample = null; },
    zero: (r) => { r.totals = zeroTotals(r.totals); r.regions = []; r.sample = []; } },
  { name: "granary storage", key: "grain_storage", read: readGranaryStorage, label: "Granary storage", livelihoods: false,
    get: (s) => s.grain_reserves.storage,
    set: (s, v) => { if (v === undefined) delete s.grain_reserves.storage; else s.grain_reserves.storage = v; },
    misdate: (r) => { r.receipt_turn = 99; },
    zero: (r) => { r.receipts = []; },
    content: (r) => { r.receipts[0] = { ...r.receipts[0], requested: 1, delivered: 1 }; } },
];

function at(bundle: Bundle) {
  return snapshotOf(bundle, AT);
}

function edited(c: Case, edit: (record: Rec) => void): Bundle {
  return chainBundle((s) => { if (s.turn === AT) edit(c.get(s)); });
}

describe.each(CASES)("$name", (c) => {
  it("is disabled when no snapshot of the run records it", () => {
    const bundle = chainBundle(without(c.key));
    const reading = c.read(bundle, at(bundle));
    expect(reading.state).toBe("disabled");
    expect(reading.record).toBeNull();
    expect(reading.note).toContain(`${c.label}: off in this run`);
  });

  it("is absent (unknown, not zero) when this snapshot lacks it but the run records it", () => {
    const bundle = chainBundle((s) => { if (s.turn === AT) c.set(s, undefined); });
    const reading = c.read(bundle, at(bundle));
    expect(reading.state).toBe("absent");
    expect(reading.note).toBe(`${c.label}: on in this run, but snapshot ${AT} has no record; unknown, not zero.`);
    // The same snapshot read without the rest of the run cannot tell: the package reads as off.
    expect(c.read({ ...bundle, history: [] } as Bundle, at(bundle)).state).toBe("disabled");
  });

  it("is malformed, with its reason, when the record is present and refused", () => {
    const bundle = edited(c, c.misdate);
    const reading = c.read(bundle, at(bundle));
    expect(reading.state).toBe("malformed");
    expect(reading.note).toContain(`the record at snapshot ${AT} was rejected as malformed`);
  });

  it("reads a recorded zero as recorded, not as unknown", () => {
    const bundle = edited(c, c.zero);
    const reading = c.read(bundle, at(bundle));
    expect(reading.state).toBe("recorded_zero");
    expect(reading.record).not.toBeNull();
    expect(reading.note).toMatch(new RegExp(`^${c.label}: recorded, nothing happened this turn \\(.+\\)\\.$`));
  });

  it("reads a record with content as recorded", () => {
    const bundle = c.content ? edited(c, c.content) : chainBundle();
    const reading = c.read(bundle, at(bundle));
    expect(reading.state).toBe("recorded");
    expect(reading.record).toBe(c.get(at(bundle)));
    expect(reading.note).toBe("");
  });

  it.skipIf(!c.unobserved)("keeps an unobserved turn unknown", () => {
    const bundle = edited(c, c.unobserved!);
    const reading = c.read(bundle, at(bundle));
    expect(reading.state).toBe("unobserved");
    expect(reading.note).toContain("its turn was not observed; unknown, not zero");
  });

  it.skipIf(!c.livelihoods)("tells a missing livelihoods record from an unreadable one", () => {
    const missing = chainBundle((s) => { if (s.turn === AT) delete s.livelihoods; });
    expect(c.read(missing, at(missing))).toMatchObject({ state: "absent",
      note: `${c.label}: no livelihoods record at snapshot ${AT}; unknown, not zero.` });
    const unreadable = chainBundle((s) => { if (s.turn === AT) s.livelihoods.schema_version = 2; });
    const reading = c.read(unreadable, at(unreadable));
    expect(reading.state).toBe("malformed");
    expect(reading.note).toContain("the livelihoods record at snapshot 20 is unreadable");
  });
});

it("names the turn when no snapshot is selected", () => {
  const bundle = chainBundle();
  expect(readTimberStock(bundle, null, 31)).toMatchObject({ state: "absent", note: "Timber stock: no snapshot at turn 31; unknown, not zero." });
});
