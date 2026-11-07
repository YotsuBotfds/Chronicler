import { describe, expect, it } from "vitest";
import type { Bundle, TurnSnapshot } from "../../types";
import { careRegionRows, epidemicCareAt, readEpidemicCare, units } from "../epidemicCare";
import FIXTURE from "../../__fixtures__/epidemicCare.json";

type Raw = Record<string, unknown>;
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

function snap(turn: number, care?: unknown, livelihoods: unknown = undefined): TurnSnapshot {
  const lv = livelihoods !== undefined ? livelihoods : care === undefined ? { schema_version: 1 } : { schema_version: 1, epidemic_care: care };
  return { turn, livelihoods: lv } as unknown as TurnSnapshot;
}

function bundle(history: TurnSnapshot[]): Bundle {
  return {
    history,
    world_state: { regions: FIXTURE.regions.map((name) => ({ name })), civilizations: FIXTURE.civilizations.map((name) => ({ name })) },
  } as unknown as Bundle;
}

const recorded = () => clone(FIXTURE.recorded.record) as Raw;
const R = FIXTURE.regions.length;
const C = FIXTURE.civilizations.length;

describe("epidemicCareAt", () => {
  it("reads the natural record of a development run", () => {
    const r = epidemicCareAt(snap(FIXTURE.recorded.turn, recorded()), R, C)!;
    expect(r).not.toBeNull();
    expect(r.mode).toBe("care");
    expect(r.tick!.applied.length).toBeGreaterThanOrEqual(2);
    expect(r.tick!.applied.every((a) => a.care_factor === a.would_be && a.coverage >= 0 && a.coverage <= 1)).toBe(true);
    expect(r.frame!.some((row) => row.carers.length > 0)).toBe(true);
    const rows = careRegionRows(r);
    expect(rows.map((row) => row.region)).toEqual([...new Set(rows.map((row) => row.region))].sort((a, b) => a - b));
  });

  it("refuses misdated, foreign and inconsistent records", () => {
    const t = FIXTURE.recorded.turn;
    expect(epidemicCareAt(snap(t + 1, recorded()), R, C)).toBeNull();                      // misdated
    expect(epidemicCareAt(snap(t, { ...recorded(), schema_version: 2 }), R, C)).toBeNull();
    expect(epidemicCareAt(snap(t, { ...recorded(), mode: "sanitation" }), R, C)).toBeNull();
    const bad = recorded();
    ((bad.tick as Raw).applied as Raw[])[0].coverage = 1.5;
    expect(epidemicCareAt(snap(t, bad), R, C)).toBeNull();
    const costOnly = recorded();
    costOnly.mode = "cost_only";                                                          // a factor applied in cost_only
    expect(epidemicCareAt(snap(t, costOnly), R, C)).toBeNull();
    const region = recorded();
    ((region.frame as Raw[])[0]).region = R;                                              // out of range
    expect(epidemicCareAt(snap(t, region), R, C)).toBeNull();
    const orphan = recorded();
    orphan.frame = [];                                                                    // capacity without carers
    expect((orphan.capacity as unknown[]).length).toBeGreaterThan(0);
    expect(epidemicCareAt(snap(t, orphan), R, C)).toBeNull();
  });

  it("formats wages from milli-units", () => {
    expect(units(1500)).toBe("1.500");
    expect(units(2000)).toBe("2");
  });
});

describe("readEpidemicCare", () => {
  it("keeps disabled, absent, malformed, unobserved, recorded zero and recorded distinct", () => {
    const t = FIXTURE.recorded.turn;
    const off = bundle([snap(1), snap(2)]);
    expect(readEpidemicCare(off, off.history[1]).state).toBe("disabled");
    const on = bundle([snap(t, recorded()), snap(t + 1)]);
    expect(readEpidemicCare(on, on.history[1]).state).toBe("absent");
    expect(readEpidemicCare(on, snap(t, { ...recorded(), stage: "C1" })).state).toBe("malformed");
    expect(readEpidemicCare(on, snap(t, recorded(), "broken")).state).toBe("malformed");
    const unobserved = { ...recorded(), tick: null };
    const u = readEpidemicCare(on, snap(t, unobserved));
    expect(u.state).toBe("unobserved");
    expect(u.note).toMatch(/not observed; unknown, not zero/);
    const zero = FIXTURE.recorded_zero;
    const z = readEpidemicCare(on, snap(zero.turn, clone(zero.record)));
    expect(z.state).toBe("recorded_zero");
    expect(z.note).toMatch(/nothing happened this turn/);
    expect(readEpidemicCare(on, on.history[0]).state).toBe("recorded");
  });
});
