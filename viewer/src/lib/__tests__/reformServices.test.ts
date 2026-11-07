import { expect, it } from "vitest";
import type { Bundle, TurnSnapshot } from "../../types";
import { readReformServices, reformServicesOn, reliefByRegion, reliefRecordAt } from "../reformServices";
import { empty, frame, record } from "./reformServicesFixture";

const snap = (turn: number, livelihoods: unknown): TurnSnapshot => ({ turn, livelihoods } as unknown as TurnSnapshot);
const bundle = (history: TurnSnapshot[]) =>
  ({ history, world_state: { regions: [{}, {}, {}, {}], civilizations: [{}, {}] } }) as unknown as Bundle;
const on = (r: unknown) => ({ schema_version: 1, reform_services: r });

it("reads a recorded frame and sums it by region", () => {
  const s = snap(86, on(record()));
  const reading = readReformServices(bundle([s]), s);
  expect(reading.state).toBe("recorded");
  const rows = reliefByRegion(reading.record!.frame!);
  expect(rows.map((r) => r.region)).toEqual([2, 3]);
  expect(rows[0]).toMatchObject({ bought: 0.002, atMost: 0.004, atLeast: null });
  expect(rows[1].atLeast).toBeCloseTo(1.376277);
});

it("keeps the six readings distinct", () => {
  const plain = snap(86, { schema_version: 1 });
  expect(readReformServices(bundle([plain]), plain).state).toBe("disabled");
  const recorded = snap(85, on(record()));
  expect(readReformServices(bundle([recorded, plain]), plain).state).toBe("absent");
  const bad = snap(86, on(record({ stage: "X" })));
  expect(readReformServices(bundle([bad]), bad).state).toBe("malformed");
  const unobserved = snap(86, on(record({ frame: null })));
  expect(readReformServices(bundle([unobserved]), unobserved).state).toBe("unobserved");
  const zero = snap(86, on(record({ frame: empty })));
  expect(readReformServices(bundle([zero]), zero).state).toBe("recorded_zero");
  const container = snap(86, { schema_version: 2, reform_services: record() });
  expect(readReformServices(bundle([container]), container).state).toBe("malformed");
  expect(reformServicesOn([plain, recorded])).toBe(true);
  expect(reformServicesOn([plain])).toBe(false);
});

it("refuses inconsistent records with a reason", () => {
  const civ = { ...frame.civs[0], fund_close_milli: 3999 };
  const cases: [Record<string, unknown>, RegExp][] = [
    [{ frame: { ...frame, civs: [civ] } }, /does not close/],
    [{ frame: { ...frame, turn: 84 } }, /misdated/],
    [{ frame: { ...frame, purchases: [{ ...frame.purchases[0], credited_milli: 1 }] } }, /payments do not close/],
    [{ frame: { ...frame, purchases: [{ ...frame.purchases[0], region: 9 }] } }, /malformed relief purchase/],
    [{ frame: { ...frame, deliveries: [{ ...frame.deliveries[0], delivered_at_most: 9 }] } }, /exceeds what was bought/],
    [{ frame: { ...frame, deliveries: [{ ...frame.deliveries[0], delivered_at_least: 1.8 }] } }, /bounds cross/],
    [{ frame: { ...frame, deliveries: [{ ...frame.deliveries[0], observed: false }] } }, /unobserved delivery carries/],
    [{ mode: "cost_only" }, /cost-only control bought/],
    [{ mode: "free" }, /malformed relief-services record/],
  ];
  for (const [change, reason] of cases) {
    const got = reliefRecordAt(snap(86, on(record(change))), 4, 2);
    expect(got.record).toBeNull();
    expect(got.reason).toMatch(reason);
  }
});
