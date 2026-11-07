import { describe, expect, it } from "vitest";
import natural from "../../__fixtures__/infrastructure_records.json";
import type { TurnSnapshot } from "../../types";
import {
  carriesInfrastructure, conditionSeries, infrastructureOn, readInfrastructure, serviceOf, worksStory,
} from "../infrastructureCondition";

/** Natural records of a development world (template 11, repair mode); edited copies are labelled per case. */
const snapshots = natural.snapshots as unknown as TurnSnapshot[];
const regions = natural.regions.length;
const copy = (i: number) => structuredClone(snapshots[i]) as unknown as TurnSnapshot;
const rec = (s: TurnSnapshot) =>
  (s as unknown as { livelihoods: { infrastructure_condition: Record<string, unknown> } }).livelihoods.infrastructure_condition;
const settledIndex = snapshots.findIndex((s) => Array.isArray(rec(s).receipts) && (rec(s).receipts as unknown[]).length > 0);

describe("readInfrastructure", () => {
  it("reads every natural snapshot as ok, dated to its source turn", () => {
    for (const s of snapshots) {
      const reading = readInfrastructure(s, regions, true);
      expect(reading.status, `turn ${s.turn}`).toBe("ok");
      if (reading.status === "ok") expect(reading.record.source_turn + 1).toBe(s.turn);
    }
    expect(settledIndex).toBeGreaterThanOrEqual(0);
    const reading = readInfrastructure(snapshots[settledIndex], regions, true);
    expect(reading.status === "ok" && reading.frame).toBe("settled");
  });

  it("keeps disabled and absent apart", () => {
    const bare = { turn: 3 } as unknown as TurnSnapshot;
    expect(carriesInfrastructure(bare)).toBe(false);
    expect(readInfrastructure(bare, regions, false)).toEqual({ status: "disabled" });
    expect(readInfrastructure(bare, regions, true)).toEqual({ status: "absent" });
    expect(infrastructureOn(snapshots)).toBe(true);
    expect(infrastructureOn([bare])).toBe(false);
  });

  it("reads a turn without a settled Phase 2 as unknown, and a mode without works as no works", () => {
    const s = copy(settledIndex);
    Object.assign(rec(s), { receipts: null, ledger: null, unmet: null, shared: null });
    const reading = readInfrastructure(s, regions, true);
    expect(reading.status === "ok" && reading.frame).toBe("unsettled");
    const wear = copy(settledIndex);
    Object.assign(rec(wear), { mode: "wear_only", works_enabled: false, works: [], receipts: null, ledger: null, unmet: [], shared: [] });
    const w = readInfrastructure(wear, regions, true);
    expect(w.status === "ok" && w.frame).toBe("no_works");
  });

  it.each([
    ["misdated", (r: Record<string, unknown>) => { r.source_turn = (r.source_turn as number) + 1; }, "misdated observation"],
    ["an unknown stage", (r: Record<string, unknown>) => { r.stage = "B9"; }, "unknown infrastructure schema"],
    ["a service that is not min(1, c / 0.5)", (r: Record<string, unknown>) => {
      const a = (r.assets as Array<Record<string, unknown>>)[0];
      a.condition_service = 0.123;
    }, "an asset's service is not min(1, condition / 0.5)"],
    ["a failed asset with condition", (r: Record<string, unknown>) => {
      const a = (r.assets as Array<Record<string, unknown>>)[0];
      a.status = a.status === "failed" ? "serving" : "failed";
    }, "an asset's status disagrees with its condition"],
    ["a ledger row that does not close", (r: Record<string, unknown>) => {
      const row = (r.ledger as Array<Record<string, number>>)[0];
      if (row) row.coin_cost_milli += 1; else r.ledger = [{ turn: r.source_turn, civ: 0, works: 1, work_delivered: 1,
        timber_used: 0.25, coin_cost_milli: 2001, charged: 2, prepaid_before_milli: 0, prepaid_after_milli: 0,
        envelope: null, rs2_charged: 0 }];
    }, "a ledger row does not close"],
    ["works in a mode without works", (r: Record<string, unknown>) => {
      r.mode = "record_only";
      r.works_enabled = false;
      for (const a of r.assets as Array<Record<string, unknown>>) a.service = 1;
    }, "works in a mode without works"],
    ["a partial frame", (r: Record<string, unknown>) => { r.ledger = null; }, "a partial frame"],
    ["a repeated asset id", (r: Record<string, unknown>) => {
      const assets = r.assets as unknown[];
      assets.push(structuredClone(assets[0]));
    }, "an asset id appears twice"],
  ])("refuses %s", (_label, edit, reason) => {
    const s = copy(settledIndex);
    edit(rec(s));
    expect(readInfrastructure(s, regions, true)).toEqual({ status: "malformed", reason });
  });
});

describe("history readers", () => {
  it("builds each asset's condition series from readable snapshots only", () => {
    const series = conditionSeries(snapshots, regions);
    expect(series.size).toBeGreaterThan(0);
    for (const points of series.values()) {
      for (let i = 1; i < points.length; i += 1) expect(points[i].turn).toBeGreaterThan(points[i - 1].turn);
    }
    const broken = snapshots.map((s, i) => {
      if (i !== settledIndex) return s;
      const c = structuredClone(s) as unknown as TurnSnapshot;
      rec(c).stage = "B9";
      return c;
    });
    const fewer = conditionSeries(broken, regions);
    const aid = [...series.keys()].find((k) => series.get(k)!.some((p) => p.turn === snapshots[settledIndex].turn))!;
    expect(fewer.get(aid)!.some((p) => p.turn === snapshots[settledIndex].turn)).toBe(false);
  });

  it("finds the most stalled work as the underfunded works story", () => {
    const last = snapshots[snapshots.length - 1].turn;
    const story = worksStory(snapshots, regions, last);
    expect(story).not.toBeNull();
    expect(story!.work.stalled_turns).toBeGreaterThan(0);
    const total = story!.stalls.reduce((a, [, v]) => a + v, 0);
    expect(total).toBeGreaterThanOrEqual(story!.work.stalled_turns);
    expect(worksStory(snapshots, regions, -1)).toBeNull();
    expect(serviceOf(0.25)).toBe(0.5);
    expect(serviceOf(0.8)).toBe(1);
  });
});
