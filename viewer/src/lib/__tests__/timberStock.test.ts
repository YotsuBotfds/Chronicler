import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { timberResidual, timberStockAt, type TimberStockRecord, type TimberStockRow } from "../timberStock";

/** Constructed observation to test the strict reader; not a simulation run. */
function row(extra: Partial<TimberStockRow> = {}): TimberStockRow {
  return { region_id: 0, slot: 0, opening: 100, cleared: 10, extraction: 30, overdraft: 0, regrowth: 2.5,
    removed: 0, stock: 62.5, capacity: 90, cap: 90, capped: false, water_gate_open: true, ...extra };
}
function record(extra: Partial<TimberStockRecord> = {}): TimberStockRecord {
  return { schema_version: 1, units: "timber_goods", source_turn: 4, completed_turn: 5, enforce_cap: true,
    parameters: { regrowth_rate: 0.03, seed_fraction: 0.05, reference_crews_at_msy: 1 }, observed: true,
    regions: [row(), row({ region_id: 1, slot: 2, opening: 0, cleared: 0, extraction: 0, regrowth: 0.5, stock: 0.5, capacity: 10, cap: 0, capped: true })],
    totals: { opening: 100, cleared: 10, extraction: 30, overdraft: 0, regrowth: 3, removed: 0, stock: 63, capacity: 100, slots: 2, capped_slots: 1 },
    ...extra };
}
const at = (timber: unknown, turn = 5, schema = 1) =>
  timberStockAt({ turn, livelihoods: { schema_version: schema, timber_stock: timber } } as unknown as TurnSnapshot, 2);

describe("timberStockAt", () => {
  it("accepts a dated, closed record and its ledger identity", () => {
    const good = record();
    expect(at(good)).toBe(good);
    expect(timberResidual(good.regions![0])).toBe(0);
  });

  it("keeps an unobserved turn unknown rather than zero", () => {
    const unobserved = record({ observed: false, regions: null, totals: null });
    expect(at(unobserved)?.observed).toBe(false);
    expect(at({ ...unobserved, regions: [] })).toBeNull();
    expect(at({ ...record(), regions: null })).toBeNull();
  });

  it("rejects absent, future, foreign and malformed data", () => {
    const good = record();
    expect(timberStockAt(null, 2)).toBeNull();
    expect(timberStockAt({ turn: 5 } as TurnSnapshot, 2)).toBeNull();
    expect(at(good, 5, 2)).toBeNull();
    for (const bad of [undefined, { ...good, schema_version: 2 }, { ...good, units: "wood" }, { ...good, source_turn: 5 },
      { ...good, completed_turn: 6, source_turn: 5 }, { ...good, enforce_cap: "yes" }, { ...good, parameters: { regrowth_rate: NaN } },
      { ...good, regions: [good.regions![0], good.regions![0]] },
      { ...good, regions: [row({ region_id: 2 })] }, { ...good, regions: [row({ slot: 3 })] },
      { ...good, regions: [row({ extraction: -1 })] }, { ...good, regions: [row({ stock: 70 })] },
      { ...good, regions: [row({ cap: 20, capped: true })] }, { ...good, regions: [row({ overdraft: 5, stock: 67.5 })] },
      { ...good, totals: { ...good.totals!, slots: 3 } }, { ...good, totals: { ...good.totals!, capped_slots: 3 } },
      { ...good, totals: null }]) {
      expect(at(bad)).toBeNull();
    }
    expect(at(good, 6)).toBeNull();
  });

  it("reads the ablation's overdraft without a cap", () => {
    const ablation = record({ enforce_cap: false, regions: [row({ cap: null, capped: null, extraction: 110, overdraft: 20, stock: 2.5 })],
      totals: { ...record().totals!, slots: 1, capped_slots: 0 } });
    expect(at(ablation)?.regions?.[0].overdraft).toBe(20);
    expect(at({ ...ablation, regions: [row({ cap: 90, capped: null, extraction: 110, overdraft: 20, stock: 2.5 })] })).toBeNull();
  });
});
