import { describe, expect, it } from "vitest";
import fixture from "../../__fixtures__/region_inspection_bundle.json";
import type { Bundle } from "../../types";
import { inspectRegionEvents, inspectRegionHistory, recordedTurnBounds, regionMetrics, regionNames } from "../regionHistory";

const bundle = fixture as unknown as Bundle;
const region = "Delta/~east";
const metric = (id: string) => regionMetrics(bundle).find((item) => item.id === id)!;

describe("region history inspection", () => {
  it("preserves zero, missing values, original indices, and escaped JSON pointers", () => {
    const result = inspectRegionHistory(bundle, region, metric("ecology:soil"), 1, 5);
    expect(result.rows.map((row) => row.value)).toEqual([0.8, 0, null]);
    expect(result.rows.map((row) => row.controller)).toEqual(["Aurora", "Boreal", null]);
    expect(result.rows[2].missing).toBe("Metric not recorded");
    expect(result.rows[1].source).toBe("/history/1/ecology/Delta~1~0east/soil");
    expect(result.unrecordedTurns).toBe(2);
    // Final soil is 0.99: it must never replace missing historic soil.
    expect(result.rows[2].value).toBeNull();
  });

  it("filters exact inclusive turn windows, including windows with no snapshots", () => {
    expect(inspectRegionHistory(bundle, region, metric("ecology:soil"), 3, 3).rows.map((row) => row.value)).toEqual([0]);
    expect(inspectRegionHistory(bundle, region, metric("ecology:soil"), 2, 2)).toEqual({ rows: [], unrecordedTurns: 1 });
  });

  it("shows final goods as a separate observation and never invents historic or absent goods", () => {
    const salt = inspectRegionHistory(bundle, region, metric("stockpile:salt"), 1, 5);
    expect(salt.rows.map((row) => row.value)).toEqual([null, null, null, 7]);
    expect(salt.rows.map((row) => row.turn)).toEqual([1, 3, 5, 5]);
    expect(salt.rows[3].source).toBe("/world_state/regions/0/stockpile/goods/salt");
    expect(inspectRegionHistory(bundle, region, metric("stockpile:grain"), 5, 5).rows[1].value).toBe(0);
    expect(inspectRegionHistory(bundle, region, metric("stockpile:timber"), 5, 5).rows[1].missing).toBe("Good not recorded in final state");
    expect(regionMetrics(bundle).map((item) => item.id)).not.toContain("stockpile:food");
    expect(inspectRegionHistory(bundle, region, metric("stockpile:salt"), 1, 3).rows.every((row) => row.value === null)).toBe(true);
  });

  it("does not backfill ownership or infer region events from prose", () => {
    const direct = inspectRegionEvents(bundle, region, 1, 5, "", false);
    expect(direct.map((event) => event.source)).toEqual(["/named_events/0"]);
    const contextual = inspectRegionEvents(bundle, region, 1, 5, "", true);
    expect(contextual.map((event) => event.source)).toEqual(["/events_timeline/0", "/named_events/0", "/events_timeline/2"]);
    expect(contextual[2].scope).toBe("Controller context; region unrecorded");
    expect(inspectRegionEvents(bundle, region, 2, 3, "war", true).map((event) => event.source)).toEqual(["/events_timeline/2"]);
    expect(inspectRegionEvents(bundle, "Upland", 3, 3, "trade", false).map((event) => event.source)).toEqual(["/named_events/1"]);
  });

  it("does not mutate or reorder the raw bundle", () => {
    const unsorted = structuredClone(bundle);
    unsorted.history.reverse();
    const before = JSON.stringify(unsorted);
    const rows = inspectRegionHistory(unsorted, region, metric("ecology:soil"), 1, 5).rows;
    expect(rows.map((row) => row.turn)).toEqual([1, 3, 5]);
    expect(rows[0].source).toBe("/history/2/ecology/Delta~1~0east/soil");
    expect(JSON.stringify(unsorted)).toBe(before);
  });

  it("handles older, invalid numeric, and history-only region data explicitly", () => {
    const older = structuredClone(bundle);
    delete older.history[0].ecology;
    older.history[1].ecology![region].soil = Number.NaN;
    older.history[2].region_control.Departed = "Aurora";
    const rows = inspectRegionHistory(older, region, metric("ecology:soil"), 1, 5).rows;
    expect(rows[0].missing).toBe("Metric not recorded");
    expect(rows[1].missing).toBe("Invalid numeric value");
    expect(regionNames(older)).toContain("Departed");
    expect(recordedTurnBounds(older)).toEqual([1, 5]);
  });
});
