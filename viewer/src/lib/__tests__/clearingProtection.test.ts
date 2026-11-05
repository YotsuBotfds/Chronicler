import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { clearingProtectionAt, clearingSummary, fundingLabel } from "../clearingProtection";
import { receipt, record, unprotected, without } from "./clearingProtectionFixture";

const at = (clearing: unknown, turn = 5, schema = 1, regions = 4) =>
  clearingProtectionAt({ turn, livelihoods: { schema_version: schema, clearing_protection: clearing } } as unknown as TurnSnapshot, regions);

describe("clearingProtectionAt", () => {
  it("accepts a dated, consistent record and sums the turn's cover and bills", () => {
    const good = record();
    expect(at(good)).toBe(good);
    const summary = clearingSummary(good)!;
    expect(summary).toMatchObject({ clearedElsewhere: 0.04, required: 4, paid: 3, charged: 3, underfunded: 1 });
    expect(summary.kept).toBeCloseTo(0.03, 12);
    expect(summary.wouldKeep).toBeCloseTo(0.03, 12);
    expect(summary.clearedProtected).toBeCloseTo(0.01, 12);
    expect(fundingLabel(good.receipts![0])).toBe("Full");
    expect(fundingLabel(good.receipts![1])).toBe("Partial (1 of 2)");
    expect(fundingLabel(receipt({ paid_planned: 0, p_planned: 0, p_applied: 0, cover_not_cleared: 0, cover_would_keep: 0, charged: 0 })))
      .toBe("Unfunded");
  });

  it("keeps an unobserved turn and missing values unknown, never zero", () => {
    const unobserved = record({ observed: false, receipts: null, decisions: null, unprotected: null });
    expect(at(unobserved)?.observed).toBe(false);
    expect(clearingSummary(at(unobserved)!)).toBeNull();
    expect(at({ ...unobserved, receipts: [] })).toBeNull();
    expect(at({ ...record(), decisions: null })).toBeNull();
    // A record written before the unprotected list existed: accepted, the list unknown.
    const older = without(record(), "unprotected");
    const parsed = at(older)!;
    expect(parsed.unprotected).toBeUndefined();
    expect(clearingSummary(parsed)?.clearedElsewhere).toBeNull();
    // Without the clearing rate the loss in underfunded regions is unknown.
    const params = without(record().parameters, "forest_clearing");
    expect(clearingSummary(at(record({ parameters: params }))!)?.clearedProtected).toBeNull();
  });

  it("reads the cost-only control and an unpressured, unpaid protection", () => {
    const control = record({ mode: "cost_only", receipts: [receipt({ p_applied: 0, cover_not_cleared: 0, cover_after: 0.58 }),
      receipt({ region_id: 1, new: true, p_applied: 0, cover_not_cleared: 0 })] });
    expect(at(control)?.mode).toBe("cost_only");
    expect(clearingSummary(control)).toMatchObject({ kept: 0, wouldKeep: 0.04, clearedProtected: 0.04 });
    expect(at({ ...control, receipts: [receipt(), receipt({ region_id: 1, new: true, p_applied: 0, cover_not_cleared: 0 })] })).toBeNull();
    const idle = receipt({ pressure_planned: false, required: 0, paid_planned: 0, p_planned: 0, p_applied: 0, clearing_active: false,
      cover_not_cleared: 0, cover_would_keep: 0, charged: 0 });
    expect(at(record({ receipts: [idle, record().receipts![1]] }))).not.toBeNull();
    expect(fundingLabel(idle)).toBe("Not due (no pressure)");
    const enveloped = receipt({ envelope: 1, paid_planned: 1, p_planned: 0.5, p_applied: 0.5, cover_not_cleared: 0.01,
      cover_would_keep: 0.01, charged: 1 });
    expect(at(record({ receipts: [enveloped, record().receipts![1]] }))).not.toBeNull();
    // float32 native receipts agree with the float64 planned share within the tolerance.
    const f32 = receipt({ cover_not_cleared: 0.019999999552965164 });
    expect(at(record({ receipts: [f32, record().receipts![1]] }))).not.toBeNull();
  });

  it("rejects absent, misdated, foreign and inconsistent data", () => {
    const good = record();
    const second = good.receipts![1];
    expect(clearingProtectionAt(null, 4)).toBeNull();
    expect(clearingProtectionAt({ turn: 5 } as TurnSnapshot, 4)).toBeNull();                   // an older bundle
    expect(clearingProtectionAt({ turn: 5, livelihoods: { schema_version: 1 } } as unknown as TurnSnapshot, 4)).toBeNull();
    expect(at(good, 5, 2)).toBeNull();
    expect(at(good, 6)).toBeNull();                                                            // misdated
    expect(at(good, 5, 1, 1)).toBeNull();                                                      // region out of range
    const rows = (r: ReturnType<typeof receipt>) => ({ ...good, receipts: [r, second] });
    for (const bad of [undefined, "x", { ...good, schema_version: 2 }, { ...good, units: { cover: "trees", money: "treasury" } },
      { ...good, mode: "strict" }, { ...good, source_turn: 5 }, { ...good, parameters: { ...good.parameters, warden_cost: 0 } },
      { ...good, parameters: { ...good.parameters, protection: 2 } }, { ...good, parameters: { max_regions: 2 } },
      { ...good, counters: { charged: -1 } }, { ...good, counters: { charged: Number.NaN } },
      { ...good, protections: [good.protections[0], good.protections[0]] },
      { ...good, protections: [{ ...good.protections[0], adopted_turn: 5 }, good.protections[1]] },
      { ...good, protections: good.protections.slice(0, 1) },
      { ...good, protections: [{ ...good.protections[0], payer: 2 }, good.protections[1]] },
      { ...good, receipts: [receipt(), receipt()] },
      rows(receipt({ required: 1 })), rows(receipt({ paid_planned: 3, required: 2 })), rows(receipt({ envelope: 1 })),
      rows(receipt({ p_planned: 0.5 })), rows(receipt({ p_applied: 0.5 })), rows(receipt({ charged: 1 })),
      rows(receipt({ clearing_active: false })), rows(receipt({ cover_would_keep: 0.03 })), rows(receipt({ cover_before: 1.5 })),
      rows(receipt({ source: "guess" as "native" })), rows(receipt({ new: true })),
      rows(receipt({ pressure_planned: false, required: 0, paid_planned: 0, p_planned: 0, p_applied: 0, new: true,
        clearing_active: false, cover_not_cleared: 0, cover_would_keep: 0, charged: 0 })),
      { ...good, unprotected: [unprotected({ region_id: 0 })] }, { ...good, unprotected: [unprotected(), unprotected()] },
      { ...good, unprotected: [unprotected({ reason: "lazy" as "over_limit" })] },
      { ...good, unprotected: [unprotected({ reason: "not_planned" })] },
      { ...good, unprotected: [unprotected({ pressure_planned: false, clearing_active: false, reason: "not_planned" })] },
      { ...good, unprotected: [unprotected({ clearing_active: false })] }, { ...good, unprotected: "none" },
      { ...good, decisions: [{ ...good.decisions![0], turn: 3 }, good.decisions![1]] },
      { ...good, decisions: [good.decisions![0], { ...good.decisions![1], reason: "bored" }] },
      { ...good, decisions: [good.decisions![1]] },
      { ...good, observed: false }]) {
      expect(at(bad)).toBeNull();
    }
  });
});
