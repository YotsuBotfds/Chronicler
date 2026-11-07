import { expect, it } from "vitest";
import natural from "../../__fixtures__/infrastructure_records.json";
import type { Bundle } from "../../types";
import { entityHistory,indexEntityHistory } from "../entityHistory";
it("links natural infrastructure works and stable asset identity without claiming anonymous labor is a paid person",()=>{
 const bundle={world_state:{regions:natural.regions.map((name)=>({name})),civilizations:[]},history:structuredClone(natural.snapshots)} as unknown as Bundle;
 const index=indexEntityHistory(bundle),work=index.entities.find(e=>e.kind==="infrastructure_work")!;
 expect(work).toBeDefined();const rows=entityHistory(index,work);
 expect(rows.some(r=>r.related.some(e=>e.kind==="infrastructure_asset"))).toBe(true);
 for(const row of rows)if(row.source){let v:unknown=bundle;for(const token of row.source.slice(1).split("/"))v=(v as Record<string,unknown>)[token];expect(v).not.toBeUndefined();}
 const anonymous=rows.filter(r=>r.source?.includes("/receipts/"));
 expect(anonymous.every(r=>!r.related.some(e=>e.kind==="person"))).toBe(true);
});
