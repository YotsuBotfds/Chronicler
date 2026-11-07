import { describe, expect, it } from "vitest";
import { entityHistory, indexEntityHistory } from "../entityHistory";
import { chainBundle, snapshotOf, without } from "./recoveryChainFixture";
import { RECORD_122, REGION_NAMES } from "./residenceLedgerFixture";
import { trade } from "./titledTradeFixture";
import type { Bundle } from "../../types";

const person = { kind: "person", id: 13 } as const;
const read = (bundle: Bundle) => entityHistory(indexEntityHistory(bundle), person);
describe("linked histories: natural seed-23 records and labelled constructed variants", () => {
  it("joins a person's dated work, food sample and project, separating regional money", () => {
    const bundle = chainBundle();
    const rows = read(bundle);
    const work = rows.find((r) => r.turn === 28 && r.package === "recovery_crews")!;
    expect(work.join).toBe("id");
    expect(work.sourceTurn).toBe(27);
    expect(work.source).toContain("/receipts/0/members/");
    expect(work.related).toContainEqual({ kind: "project", id: 0 });
    const market = rows.find((r) => r.turn === 28 && r.join === "region")!;
    expect(market.text).toContain("not this person's record");
    expect(market.source).toContain("/household_retail/regions/");
    const project = entityHistory(indexEntityHistory(bundle), { kind: "project", id: 0 });
    expect(project.some((r) => r.package === "repair_projects" && r.text.includes("work"))).toBe(true);
  });
  it("has exact pointers into the accepted bundle and never reads future snapshots", () => {
    const bundle = chainBundle();
    const rows = entityHistory(indexEntityHistory(bundle), person, 22);
    expect(rows.every((r) => r.turn <= 22)).toBe(true);
    for (const row of rows) if (row.source) {
      let value: unknown = bundle;
      for (const token of row.source.slice(1).split("/")) value = (value as Record<string, unknown>)[token];
      expect(value, row.source).not.toBeUndefined();
    }
  });
  it("keeps disabled, unknown, malformed and sampled absences distinct", () => {
    const off = read(chainBundle(without("recovery_crews"))).filter((r) => r.package === "recovery_crews");
    expect(off.every((r) => r.state === "disabled")).toBe(true);
    const bundle = chainBundle();
    const missing = snapshotOf(bundle, 28) as unknown as { livelihoods: Record<string, unknown> };
    delete missing.livelihoods.recovery_crews;
    expect(read(bundle).find((r) => r.turn === 28 && r.package === "recovery_crews")?.state).toBe("unknown");
    missing.livelihoods.recovery_crews = { schema_version: 999 };
    expect(read(bundle).find((r) => r.turn === 28 && r.package === "recovery_crews")?.state).toBe("malformed");
    expect(entityHistory(indexEntityHistory(chainBundle()), { kind: "person", id: 999999 }).some((r) => r.package === "household_retail" && r.state === "not_sampled")).toBe(true);
  });
  it("does not turn dropped receipts into a recorded zero (constructed cap)", () => {
    const bundle = chainBundle((s) => { s.livelihoods.recovery_crews.rows_dropped = 1; });
    const rows = entityHistory(indexEntityHistory(bundle), { kind: "person", id: 999999 });
    expect(rows.filter((r) => r.package === "recovery_crews").every((r) => r.state === "truncated")).toBe(true);
    const natural = entityHistory(indexEntityHistory(chainBundle()), { kind: "person", id: 999999 });
    expect(natural.some((r) => r.package === "recovery_crews" && r.state === "recorded_zero")).toBe(true);
  });
  it("does not divide expedition crew totals into invented individual wages", () => {
    const row = read(chainBundle()).find((r) => r.package === "timber_supply" && r.state === "recorded")!;
    expect(row.text).toContain("crew total");
    expect(row.text).toContain("individual allocation unrecorded");
    expect(row.related[0].kind).toBe("expedition");
  });
  it("accepts older bundles without these records without fabricating entities", () => {
    const bundle = chainBundle((s) => { delete s.livelihoods; });
    expect(indexEntityHistory(bundle).entities).toEqual([]);
    expect(read(bundle).every((r) => r.state === "disabled")).toBe(true);
  });
});


it("joins a natural displacement event by its id, without inventing every residence", () => {
  const bundle = { world_state: { regions: REGION_NAMES.map((name) => ({ name })), civilizations: [] },
    history: [{ turn: 122, livelihoods: { schema_version: 1, residence_ledger: structuredClone(RECORD_122) } }] } as unknown as Bundle;
  const event = RECORD_122.events[0];
  const rows = entityHistory(indexEntityHistory(bundle), { kind: "person", id: event.id });
  const row = rows.find((r) => r.package === "residence_ledger")!;
  expect(row.state).toBe("recorded");
  expect(row.source).toBe("/history/0/livelihoods/residence_ledger/events/0");
  expect(row.text).toContain("does not record every residence");
});

it("joins a constructed titled shipment and holder without claiming origin is location", () => {
  const bundle = { world_state: { regions: [0, 1, 2].map((i) => ({ name: `R${i}` })), civilizations: [] },
    history: [{ turn: 5, livelihoods: { schema_version: 1, titled_trade: structuredClone(trade) } }] } as unknown as Bundle;
  const holder = trade.shipments[0].holder;
  const rows = entityHistory(indexEntityHistory(bundle), { kind: "person", id: holder });
  expect(rows.find((r) => r.package === "titled_trade")?.text).toContain("origin context only");
  expect(rows.find((r) => r.package === "titled_trade")?.related[0].kind).toBe("shipment");
});
it("separates a reused numeric person id across an explicitly non-exact continuation",()=>{
 const b=chainBundle();(b as unknown as {metadata:unknown}).metadata={resume:{exact:false,kind:"legacy-state",turn:24}};
 const index=indexEntityHistory(b),old=entityHistory(index,{kind:"person",id:13}),newer=entityHistory(index,{kind:"person",id:13,epoch:24});
 expect(index.entities.some(e=>e.kind==="person"&&e.id===13&&e.epoch===24)).toBe(true);
 expect(old.filter(r=>r.turn>=25&&r.package==="recovery_crews").every(r=>r.state==="unknown")).toBe(true);
 expect(newer.some(r=>r.turn>=25&&r.package==="recovery_crews"&&r.state==="recorded")).toBe(true);
 expect(newer.filter(r=>r.turn<25).every(r=>r.state==="unknown")).toBe(true);
});
