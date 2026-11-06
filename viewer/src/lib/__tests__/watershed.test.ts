import { describe, expect, it } from "vitest";
import natural from "../../__fixtures__/watershed_records.json";
import large from "../../__fixtures__/watershed_large_records.json";
import type { Bundle, TurnSnapshot } from "../../types";
import {
  carriesWatershed, drainsTo, readWatershed, readWatershedRun, watershedOn, watershedOutflow, watershedRegionValue,
  type WatershedAudit,
} from "../watershed";
import { inspectRegionHistory, regionMetrics } from "../regionHistory";

/** Natural records of a development world (procedural 11, record only); copies are edited per case. */
const snapshots = natural.snapshots as unknown as TurnSnapshot[];
const regions = natural.regions.length;
const copy = (turn: number) => structuredClone(snapshots.find((s) => s.turn === turn)!) as unknown as TurnSnapshot;
const history = () => snapshots.map((s) => structuredClone(s)) as unknown as TurnSnapshot[];
const record = (s: TurnSnapshot) => (s as unknown as { livelihoods: { watershed: Record<string, unknown> } }).livelihoods.watershed;
const RUN = readWatershedRun(snapshots);
const read = (s: TurnSnapshot | null | undefined, run = RUN) => readWatershed(s, regions, run);
const reason = (s: TurnSnapshot, run = RUN) => { const r = read(s, run); return r.status === "malformed" ? r.reason : r.status; };
const unobserve = (s: TurnSnapshot) => {
  const x = record(s);
  Object.assign(x, { observed: false, phase: null, stale_baseline: null, storage: (x.regions as { storage: number[] }).storage,
    regions: null, floods: null, droughts: null, external: null, totals: null });
};

describe("readWatershed", () => {
  it("accepts the natural records, each with its own static part, recorded zeros included", () => {
    expect(RUN.on).toBe(true);
    for (const s of snapshots) expect(read(s).status).toBe("ok");
    expect((record(copy(60)).graph as { down: number[] }).down).toHaveLength(regions);
    const first = read(copy(1));
    if (first.status !== "ok") throw new Error("expected ok");
    expect(first.record.floods).toHaveLength(1);
    expect(first.record.external).toEqual([expect.objectContaining({ source: "coastal_flood", direction: "in" })]);
    expect(first.record.regions!.withdrawal.every((w) => w === 0)).toBe(true);   // recorded zero, not unknown
    const outflow = watershedOutflow(first.record)!;
    expect(outflow.every((q) => q > -1e-5)).toBe(true);
    const declared = read(copy(37));
    expect(declared.status === "ok" && declared.record.droughts!.declared).toHaveLength(1);
    const ended = read(copy(42));
    expect(ended.status === "ok" && ended.record.droughts!.ended).toHaveLength(1);
  });

  it("tells disabled, absent, malformed and unobserved apart", () => {
    const none = { turn: 5, livelihoods: { schema_version: 1 } } as unknown as TurnSnapshot;
    const off = readWatershedRun([none]);
    expect(off).toEqual({ on: false });
    expect(read(none, off)).toEqual({ status: "disabled" });
    expect(read(none)).toEqual({ status: "absent" });
    expect(read(null)).toEqual({ status: "absent" });
    expect(carriesWatershed(none)).toBe(false);
    expect(watershedOn([none])).toBe(false);
    const nulled = { turn: 5, livelihoods: { schema_version: 1, watershed: null } } as unknown as TurnSnapshot;
    expect(carriesWatershed(nulled)).toBe(true);
    expect(reason(nulled)).toBe("a null watershed record");
    expect(reason({ turn: 5, livelihoods: 7 } as unknown as TurnSnapshot)).toBe("malformed livelihoods record");
    const unobserved = copy(60);
    unobserve(unobserved);
    expect(read(unobserved).status).toBe("unobserved");
    const values = copy(60);
    Object.assign(record(values), { observed: false });
    expect(reason(values)).toBe("malformed storage");
  });

  it("refuses misdated, unknown and inconsistent records with a reason", () => {
    const cases: Array<[(r: Record<string, unknown>, s: TurnSnapshot) => void, string]> = [
      [(r) => { r.schema_version = 2; }, "unknown watershed schema"],
      [(r) => { r.mode = "flow"; }, "unknown watershed schema"],
      [(_, s) => { (s as { turn: number }).turn += 1; }, "misdated observation"],
      [(r) => { (r.regions as Record<string, number[]>).index_derived[0] = 1.5; }, "a water index above 1"],
      [(r) => { (r.regions as Record<string, number[]>).precipitation[3] = -1; }, "malformed column precipitation"],
      [(r) => { (r.totals as Record<string, number>).precipitation += 1; }, "the turn's account does not close"],
      [(r) => { delete (r.counters as Record<string, number>).settled_turns; }, "malformed counters"],
      [(r) => { (r.counters as Record<string, number>).extra = 1; }, "malformed counters"],
      [(r) => { r.cumulative = {}; }, "malformed cumulative totals"],
      [(r) => { (r.cumulative as Record<string, number>).precipitation += 5; }, "the cumulative account does not close"],
      [(r) => { r.storage = (r.regions as { storage: number[] }).storage; }, "a settled turn repeats its storage outside its columns"],
      [(r) => { delete r.graph; }, "malformed drainage graph"],
      [(r) => { delete r.parameters; }, "malformed parameters"],
      [(r) => { r.stale_baseline = "no"; }, "malformed stale-baseline flag"],
      [(r) => { delete (r.regions as Record<string, unknown>).capacity; }, "malformed region columns"],
    ];
    for (const [edit, why] of cases) {
      const s = copy(60);
      edit(record(s), s);
      expect(reason(s)).toBe(why);
    }
    const storage = copy(60);
    (record(storage).regions as Record<string, number[]>).storage[0] += 0.5;   // the derived outflow no longer routes
    expect(read(storage).status).toBe("malformed");
    const flood = copy(1);
    ((record(flood).floods as Array<Record<string, unknown>>)[0]).excess = 0;
    expect(reason(flood)).toBe("a flood record without an excess");
    const source = copy(1);
    ((record(source).external as Array<Record<string, unknown>>)[0]).amount = 0.5;
    expect(reason(source)).toBe("external flows by source do not add up to the region's external flows");
    const ended = copy(42);
    ((record(ended).droughts as { ended: Array<Record<string, unknown>> }).ended[0]).end_turn = null;
    expect(reason(ended)).toBe("an ended drought without its end turn");
    const unknownSchema = copy(60);
    (unknownSchema as unknown as { livelihoods: { schema_version: number } }).livelihoods.schema_version = 9;
    expect(reason(unknownSchema)).toBe("unknown livelihoods schema");
  });

  it("reads a state-file-resumed and a forked history on its own (review N2)", () => {
    const segments = natural.segments as unknown as { regions: string[]; resumed: TurnSnapshot[]; fork: TurnSnapshot[] };
    for (const part of [segments.resumed, segments.fork]) {
      expect(part[0].turn).toBe(21);                               // neither begins at the opening turn
      const run = readWatershedRun(part);
      for (const s of part) expect(readWatershed(s, segments.regions.length, run).status).toBe("ok");
    }
    const cyclic = copy(60);
    const down = (record(cyclic).graph as { down: number[] }).down;
    const a = down.findIndex((d) => d >= 0);
    down[down[a]] = a;
    expect(reason(cyclic)).toBe("the drainage graph has a cycle");
  });

  it("keeps rounding within its allowance on a long, large development run (review N3)", () => {
    const history = large.snapshots as unknown as TurnSnapshot[];
    const audit: WatershedAudit = { worst: 0, check: "" };
    for (const s of history) expect(readWatershed(s, large.regions, readWatershedRun(history), audit).status).toBe("ok");
    // The allowance is a bound by construction (each rounded value carries at most HALF_DIGIT).
    expect(audit.worst).toBeLessThanOrEqual(1);
    expect(audit.worst).toBeGreaterThan(0);
  });

  it("names where a region drains", () => {
    expect(drainsTo(-1, natural.regions)).toBe("the sea");
    expect(drainsTo(-2, natural.regions)).toBe("a closed basin (sink)");
    expect(drainsTo(-3, natural.regions)).toBe("a lake (closed water)");
    expect(drainsTo(3, natural.regions)).toBe(natural.regions[3]);
  });
});

describe("watershed region history", () => {
  const make = (h: TurnSnapshot[]) => {
    for (const s of h) (s as unknown as { region_control: Record<string, string> }).region_control = {};
    return { world_state: { regions: natural.regions.map((name) => ({ name })) }, history: h, named_events: [],
      events_timeline: [] } as unknown as Bundle;
  };
  const bundle = make(history());

  it("offers the observed and derived index only when the run records the account", () => {
    const ids = regionMetrics(bundle).map((m) => m.id);
    expect(ids).toEqual(expect.arrayContaining(["watershed:index_observed", "watershed:index_derived", "watershed:storage"]));
    const off = make(history().map((s) => ({ ...s, livelihoods: { schema_version: 1 } })) as unknown as TurnSnapshot[]);
    expect(regionMetrics(off).map((m) => m.id).some((id) => id.startsWith("watershed:"))).toBe(false);
  });

  it("reads values with their source and keeps absent, malformed and unobserved turns unknown", () => {
    const metric = regionMetrics(bundle).find((m) => m.id === "watershed:index_derived")!;
    const name = natural.regions[0];
    const h = history();                                  // turns 1, 37, 40, 42, 60
    delete (h[1] as unknown as { livelihoods?: unknown }).livelihoods;
    record(h[2]).schema_version = 7;
    unobserve(h[3]);
    const rows = inspectRegionHistory(make(h), name, metric, 0, 100).rows;
    expect(rows.map((r) => r.value === null)).toEqual([false, true, true, true, false]);
    expect(rows.slice(1, 4).map((r) => r.missing)).toEqual(["Watershed not recorded at this snapshot",
      "Malformed watershed record: unknown watershed schema", "Watershed account not settled this turn (unknown, not zero)"]);
    const good = inspectRegionHistory(bundle, name, metric, 0, 100).rows;
    expect(good[0].value).toBe((record(bundle.history[0]).regions as Record<string, number[]>).index_derived[0]);
    expect(good[0].source).toBe("/history/0/livelihoods/watershed/regions/index_derived/0");
    const run = readWatershedRun(h);
    const storage = watershedRegionValue(h[3], 0, regions, "storage", run);
    expect(storage.value).toBe((record(h[3]).storage as number[])[0]);
    expect(storage.path).toBe("/livelihoods/watershed/storage/0");
    expect(watershedRegionValue({ turn: 3, livelihoods: { schema_version: 1 } } as unknown as TurnSnapshot, 0, regions,
      "storage", readWatershedRun([])).missing).toBe("Watershed off in this run (--watershed not recorded)");
  });
});
