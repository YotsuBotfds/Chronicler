import { describe, expect, it } from "vitest";
import { timberOrdersAt } from "../timberOrders";
import { warRequisitionAt } from "../warRequisition";
import { indexEntityHistory, entityHistory } from "../entityHistory";
import { timber, requisition, supplySnapshot } from "./supplyContractsFixture";
import type { Bundle } from "../../types";
const t = (record: unknown) => timberOrdersAt(supplySnapshot("timber_orders", record), 2, 2);
const w = (record: unknown) => warRequisitionAt(supplySnapshot("war_requisition", record), 2, 2);
describe("constructed timber and requisition records", () => {
  it("validates actual cargo, escrow and dated prices independently", () => {
    expect(t(timber).status).toBe("observed");
    for (const mutate of [(r: typeof timber) => { r.orders[0].cash++; }, (r: typeof timber) => { r.orders[0].cargo_milli--; },
      (r: typeof timber) => { r.orders[0].price_turn = 2; }, (r: typeof timber) => { r.orders.push(r.orders[0]); }]) {
      const r = structuredClone(timber); mutate(r); expect(t(r).status).toBe("malformed");
    }
    expect(t({ ...timber, frame: null }).status).toBe("unobserved");
  });
  it("rejects minted ration allocations and inconsistent unpaid liabilities", () => {
    expect(w(requisition).status).toBe("observed");
    const minted = structuredClone(requisition); minted.frame.events[0].allocations[0].rations++; expect(w(minted).status).toBe("malformed");
    const unpaid = structuredClone(requisition); unpaid.frame.claims_due_milli++; expect(w(unpaid).status).toBe("malformed");
    const future = structuredClone(requisition); future.frame.events[0].source_turn++; expect(w(future).status).toBe("malformed");
    expect(w({ ...requisition, frame: null }).status).toBe("unobserved");
    expect(w({ ...requisition, enabled: false }).status).toBe("disabled");
  });
  it("does not demand whole claim totals from a truncated retained sample", () => {
    expect(w({ ...requisition, frame: { ...requisition.frame, claims_dropped: 1, claims_open: 100, claims_due_milli: 5000 } }).status).toBe("observed");
  });
  it("joins distinct food shipment, timber order, claimant and army identities to exact sources", () => {
    const snapshot = supplySnapshot("timber_orders", timber) as unknown as { livelihoods: Record<string, unknown> };
    snapshot.livelihoods.war_requisition = requisition;
    const bundle = { world_state: { regions: [{ name: "A" }, { name: "B" }], civilizations: [{},{}] }, history: [snapshot] } as unknown as Bundle;
    const idx = indexEntityHistory(bundle), rows = entityHistory(idx, { kind: "person", id: 42 });
    expect(rows.some((r) => r.related.some((e) => e.kind === "timber_order" && e.id === 1))).toBe(true);
    expect(rows.some((r) => r.related.some((e) => e.kind === "shipment" && e.id === 3))).toBe(true);
    expect(rows.some((r) => r.related.some((e) => e.kind === "army" && e.id === "army-7"))).toBe(true);
    expect(rows.some((r) => r.text.includes("liability is not spendable"))).toBe(true);
    for (const row of rows) if (row.source) {
      let value: unknown = bundle;
      for (const part of row.source.slice(1).split("/")) value = (value as Record<string, unknown>)[part];
      expect(value).not.toBeUndefined();
    }
  });
});
