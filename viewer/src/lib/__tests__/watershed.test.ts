import { describe, expect, it } from "vitest";
import natural from "../../__fixtures__/watershed_records.json";
import type { Bundle, TurnSnapshot } from "../../types";
import { carriesWatershed, drainsTo, readWatershed, watershedOn, watershedRegionValue } from "../watershed";
import { inspectRegionHistory, regionMetrics } from "../regionHistory";

/** Natural records of a development world (procedural 11, record only); copies are edited per case. */
const snapshots = natural.snapshots as unknown as TurnSnapshot[];
const regions = natural.regions.length;
const copy = (turn: number) => structuredClone(snapshots.find((s) => s.turn === turn)!) as unknown as TurnSnapshot;
const record = (s: TurnSnapshot) => (s as unknown as { livelihoods: { watershed: Record<string, unknown> } }).livelihoods.watershed;
const read = (s: TurnSnapshot | null, on = true) => readWatershed(s, regions, on);
const reason = (s: TurnSnapshot) => { const r = read(s); return r.status === "malformed" ? r.reason : r.status; };

describe("readWatershed", () => {
  it("accepts the natural records and keeps recorded zeros", () => {
    for (const s of snapshots) expect(read(s).status).toBe("ok");
    const first = read(copy(1));
    if (first.status !== "ok") throw new Error("expected ok");
    expect(first.record.floods).toHaveLength(1);
    expect(first.record.regions!.withdrawal.every((w) => w === 0)).toBe(true);   // recorded zero, not unknown
    const last = read(copy(60));
    if (last.status !== "ok") throw new Error("expected ok");
    expect(last.record.droughts!.open.length).toBeGreaterThan(0);
    expect(read(copy(42)).status === "ok" && (read(copy(42)) as { record: { droughts: { ended: unknown[] } } }).record.droughts.ended).toHaveLength(1);
  });

  it("tells disabled, absent, malformed and unobserved apart", () => {
    const none = { turn: 5, livelihoods: { schema_version: 1 } } as unknown as TurnSnapshot;
    expect(read(none, false)).toEqual({ status: "disabled" });
    expect(read(none, true)).toEqual({ status: "absent" });
    expect(read(null, true)).toEqual({ status: "absent" });
    expect(carriesWatershed(none)).toBe(false);
    expect(watershedOn([none])).toBe(false);
    expect(watershedOn(snapshots)).toBe(true);
    const unobserved = copy(60);
    Object.assign(record(unobserved), { observed: false, phase: null, regions: null, floods: null, droughts: null, totals: null });
    expect(read(unobserved).status).toBe("unobserved");
    const empty = copy(60);
    Object.assign(record(empty), { observed: false });
    expect(reason(empty)).toBe("an unobserved turn with values");
  });

  it("refuses misdated, unknown and inconsistent records with a reason", () => {
    const cases: Array<[(r: Record<string, unknown>, s: TurnSnapshot) => void, string]> = [
      [(r) => { r.schema_version = 2; }, "unknown watershed schema"],
      [(r) => { r.mode = "flow"; }, "unknown watershed schema"],
      [(_, s) => { (s as { turn: number }).turn += 1; }, "misdated observation"],
      [(r) => { (r.graph as { down: number[] }).down[0] = 0; }, "a region drains to an unknown region or to itself"],
      [(r) => { const d = (r.graph as { down: number[] }).down; const a = d.findIndex((x) => x >= 0); d[d[a]] = a; },
        "the drainage graph has a cycle"],
      [(r) => { (r.regions as Record<string, number[]>).storage[0] += 0.5; }, "a region's account does not close"],
      [(r) => { (r.regions as Record<string, number[]>).index_derived[0] = 1.5; }, "a water index above 1"],
      [(r) => { (r.regions as Record<string, number[]>).precipitation[3] = -1; }, "malformed column precipitation"],
      [(r) => { (r.totals as Record<string, number>).precipitation += 1; }, "the turn's account does not close"],
      [(r) => { (r.counters as Record<string, number>).settled_turns = 1.5; }, "malformed counters"],
      [(r) => { r.storage = []; }, "malformed storage"],
    ];
    for (const [edit, why] of cases) {
      const s = copy(60);
      edit(record(s), s);
      expect(reason(s)).toBe(why);
    }
    const flood = copy(1);
    ((record(flood).floods as Array<Record<string, unknown>>)[0]).excess = 0;
    expect(reason(flood)).toBe("a flood record without an excess");
    const ended = copy(42);
    ((record(ended).droughts as { ended: Array<Record<string, unknown>> }).ended[0]).end_turn = null;
    expect(reason(ended)).toBe("an ended drought without its end turn");
    const unknownSchema = copy(60);
    (unknownSchema as unknown as { livelihoods: { schema_version: number } }).livelihoods.schema_version = 9;
    expect(reason(unknownSchema)).toBe("unknown livelihoods schema");
  });

  it("names where a region drains", () => {
    expect(drainsTo(-1, natural.regions)).toBe("the sea");
    expect(drainsTo(-2, natural.regions)).toBe("a closed basin (sink)");
    expect(drainsTo(3, natural.regions)).toBe(natural.regions[3]);
  });
});

describe("watershed region history", () => {
  const bundle = { world_state: { regions: natural.regions.map((name) => ({ name })) },
    history: [copy(1), copy(42), copy(60)], named_events: [], events_timeline: [] } as unknown as Bundle;
  for (const s of bundle.history) (s as unknown as { region_control: Record<string, string> }).region_control = {};

  it("offers the observed and derived index only when the run records the account", () => {
    const ids = regionMetrics(bundle).map((m) => m.id);
    expect(ids).toEqual(expect.arrayContaining(["watershed:index_observed", "watershed:index_derived", "watershed:storage"]));
    const off = { ...bundle, history: bundle.history.map((s) => ({ ...s, livelihoods: { schema_version: 1 } })) } as unknown as Bundle;
    expect(regionMetrics(off).map((m) => m.id).some((id) => id.startsWith("watershed:"))).toBe(false);
  });

  it("reads values with their source and keeps absent, malformed and unobserved turns unknown", () => {
    const metric = regionMetrics(bundle).find((m) => m.id === "watershed:index_derived")!;
    const name = natural.regions[0];
    const history = structuredClone(bundle.history);
    delete (history[0] as unknown as { livelihoods?: unknown }).livelihoods;
    record(history[1]).schema_version = 7;
    Object.assign(record(history[2]), { observed: false, phase: null, regions: null, floods: null, droughts: null, totals: null });
    const rows = inspectRegionHistory({ ...bundle, history } as Bundle, name, metric, 0, 100).rows;
    expect(rows.map((r) => r.value)).toEqual([null, null, null]);
    expect(rows.map((r) => r.missing)).toEqual(["Watershed not recorded at this snapshot",
      "Malformed watershed record: unknown watershed schema", "Watershed account not settled this turn (unknown, not zero)"]);
    const good = inspectRegionHistory(bundle, name, metric, 0, 100).rows;
    expect(good[0].value).toBe((record(bundle.history[0]).regions as Record<string, number[]>).index_derived[0]);
    expect(good[0].source).toBe("/history/0/livelihoods/watershed/regions/index_derived/0");
    const storage = watershedRegionValue(history[2], 0, regions, "storage", true);
    expect(storage.value).toBe((record(history[2]).storage as number[])[0]);
    expect(watershedRegionValue(history[2], 0, regions, "index_observed", false).missing)
      .toBe("Watershed account not settled this turn (unknown, not zero)");
    expect(watershedRegionValue({ turn: 3, livelihoods: { schema_version: 1 } } as unknown as TurnSnapshot, 0, regions,
      "storage", false).missing).toBe("Watershed off in this run (--watershed not recorded)");
  });
});
