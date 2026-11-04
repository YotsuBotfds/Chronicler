import { describe, expect, it } from "vitest";
import { record, snapshot } from "../../__fixtures__/granaryHistory";
import { granaryAmounts, granaryOwnerRows, granarySeries, granaryShipmentsAt } from "../granaries";
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
  it.each([0, undefined])("does not turn an unobserved target into a measured total (%s observations)", (observed) => {
    const unknown = record();
    Object.assign(unknown.granaries[0], { observed, target: 99 });
    expect(granaryAmounts(unknown)).toMatchObject({ stock: 12, target: null });
    expect(granarySeries([snapshot(5, unknown)], 5, null)[0]).toMatchObject({ Stocks: 12, Targets: null });
  });
  it("leaves incomplete all-region targets unknown while retaining known regional targets and measured zero", () => {
    const mixed = record();
    mixed.granaries.push({ ...mixed.granaries[0], region: 1, region_name: "Market", grain: 8, observed: 0, target: 0 });
    expect(granaryAmounts(mixed)).toMatchObject({ stock: 20, target: null });
    expect(granaryAmounts(mixed, 0).target).toBe(20);
    expect(granaryAmounts(mixed, 1).target).toBeNull();
    expect(granaryAmounts(mixed, 99).target).toBeNull();
    const measured = record();
    measured.granaries[0].target = 0;
    expect(granarySeries([snapshot(5, mixed), snapshot(8, measured)], 8, null).map((row) => row.Targets)).toEqual([null, 0]);
    expect(granaryAmounts({ ...mixed, granaries: [] }).target).toBe(0);
  });
  it.each([undefined, Number.NaN, Number.POSITIVE_INFINITY])("keeps a missing or non-finite target out of plotted totals (%s)", (target) => {
    const incomplete = record();
    Object.assign(incomplete.granaries[0], { target });
    expect(granarySeries([snapshot(5, incomplete)], 5, null)[0].Targets).toBeNull();
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
    const row = shipmentSnapshot();
    const bundle = { world_state: {}, history: [row], events_timeline: [], named_events: [],
      chronicle_entries: [], era_reflections: {}, metadata: {} };
    const parsed = parseBundleJsonPayload(JSON.stringify(bundle));
    expect(parsed.kind).toBe("legacy");
    if (parsed.kind === "legacy") expect(parsed.bundle.history[0]).toEqual(row);
    expect(snapshotFromMessage({ ...row, type: "turn" })).toEqual(row);
    expect(bundleFromInitMessage({ ...bundle, type: "init" }).history[0]).toEqual(row);
  });
});

function shipmentSnapshot() {
  const granaries = record();
  granaries.shipments = { schema_version: 1, accept_orders: true, source_turn: 4,
    pending_count: 1, pending_net: 7, transitions: [
      { id: "dispatch:4", operation: "dispatched", turn: 4, dispatch_turn: 4, due_turn: 5,
        source: 1, source_name: "Market", dest: 0, dest_name: "Valley", buyer: 0, buyer_name: "Old realm",
        seller: 1, seller_name: "Seller", keeper: 0, sent: 8, net: 7, loss: 1, paid: 9 },
      { id: "dispatch:3", operation: "arrived", turn: 4, dispatch_turn: 3, due_turn: 4,
        source: 1, source_name: "Market", dest: 0, dest_name: "Valley", buyer: 0, buyer_name: "Old realm",
        seller: 1, seller_name: "Seller", keeper: 0, sent: 6, net: 5, loss: 1, paid: 6 },
    ] };
  granaries.flows.push({ ...granaries.flows[0], kind: "dispatched", amount: 7, sent: 8, cost: 9 },
    { ...granaries.flows[0], kind: "arrived", amount: 5, sent: 0, cost: 0 });
  return snapshot(5, granaries);
}

describe("public grain shipment observations", () => {
  it("keeps paid cargo and arrivals separate from immediate purchases and stored grain", () => {
    const row = shipmentSnapshot();
    expect(granaryAmounts(row.grain_reserves!)).toMatchObject({ stock: 12, bought: 5, paid: 18, transit: 2 });
    expect(granaryShipmentsAt(row)).toMatchObject({ pending_count: 1, pending_net: 7, dispatched: 7, arrived: 5 });
  });

  it("leaves missing old observations unknown while retaining observed zero and draining state", () => {
    expect(granaryShipmentsAt(snapshot(5, record()))).toBeNull();
    expect(granaryShipmentsAt(snapshot(2))).toBeNull();
    const row = shipmentSnapshot();
    Object.assign(row.grain_reserves!.shipments!, { accept_orders: false, pending_count: 0, pending_net: 0, transitions: [] });
    expect(granaryShipmentsAt(row)).toMatchObject({ accept_orders: false, pending_net: 0, dispatched: 0, arrived: 0 });
  });

  it.each(["source", "parent source", "future transition", "premature arrival", "invalid total", "missing rows"])("rejects an unknown shipment observation: %s", (fault) => {
    const row = shipmentSnapshot();
    const frame = row.grain_reserves!.shipments!;
    if (fault === "source") frame.source_turn = 5;
    else if (fault === "parent source") row.grain_reserves!.source_turn = 3;
    else if (fault === "future transition") frame.transitions[0].turn = 5;
    else if (fault === "premature arrival") Object.assign(frame.transitions[0], { operation: "arrived" });
    else if (fault === "invalid total") frame.pending_net = Number.NaN;
    else Object.assign(frame, { transitions: undefined });
    expect(granaryShipmentsAt(row)).toBeNull();
  });
});
