import { describe, expect, it } from "vitest";
import { record, snapshot } from "../../__fixtures__/granaryHistory";
import { granaryAmounts, granaryOwnerRows, granarySeries } from "../granaries";
import { presentSystems } from "../systems";
import { bundleFromInitMessage, snapshotFromMessage } from "../transport";
import { parseBundleJsonPayload } from "../bundleLoader";


describe("public granary history", () => {
  it("keeps stock targets, received grain, treasury and losses distinct", () => {
    expect(granaryAmounts(record())).toMatchObject({ stock: 12, target: 20, bought: 5,
      released: 3, spoiled: 0.25, paid: 9, transit: 1 });
    expect(granaryAmounts(record(), 99).stock).toBe(0);
  });
  it("leaves unknown history as gaps and stops before future snapshots", () => {
    const rows = granarySeries([snapshot(2), snapshot(5, record()), snapshot(8, record(1, 99))], 5, null);
    expect(rows).toEqual([
      { turn: 2, Stocks: null, Targets: null, Bought: null, Released: null, Spoiled: null },
      { turn: 5, Stocks: 12, Targets: 20, Bought: 5, Released: 3, Spoiled: 0.25 },
    ]);
    expect(granarySeries([snapshot(5, record())], 5, 99)[0].Stocks).toBeNull();
  });
  it("uses the recorded keeper rather than the new controller or final owner", () => {
    const history = [snapshot(2), snapshot(5, record()), snapshot(8, record(1, 99))];
    const earlier = granaryOwnerRows(history, 5, null)[0];
    expect(earlier.segments).toHaveLength(1);
    expect(earlier.segments[0]).toMatchObject({ start: 5, end: 6, text: "Old realm" });
    expect(granaryOwnerRows(history, 8, null)[0].segments.map((row) => row.text)).toEqual(["Old realm", "New realm"]);
  });
  it("makes Food available for a granary-only snapshot", () => {
    expect(presentSystems([snapshot(5, record())])).toContain("food");
  });
  it("preserves the same summary through static, turn, batch and reconnect adapters", () => {
    const row = snapshot(5, record());
    const bundle = { world_state: {}, history: [row], events_timeline: [], named_events: [],
      chronicle_entries: [], era_reflections: {}, metadata: {} };
    const parsed = parseBundleJsonPayload(JSON.stringify(bundle));
    expect(parsed.kind).toBe("legacy");
    if (parsed.kind === "legacy") expect(parsed.bundle.history[0]).toEqual(row);
    expect(snapshotFromMessage({ ...row, type: "turn" })).toEqual(row);
    expect(bundleFromInitMessage({ ...bundle, type: "init" }).history[0]).toEqual(row);
  });
});
