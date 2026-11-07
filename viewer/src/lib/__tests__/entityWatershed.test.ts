import { expect,it } from "vitest";
import natural from "../../__fixtures__/watershed_records.json";
import type { Bundle } from "../../types";
import { entityHistory,indexEntityHistory } from "../entityHistory";
it("joins natural water accounts as regional context and labels residual outflow as derived",()=>{
 const b={world_state:{regions:natural.regions.map((name)=>({name})),civilizations:[]},history:structuredClone(natural.snapshots)} as unknown as Bundle;
 const rows=entityHistory(indexEntityHistory(b),{kind:"region",id:0});
 expect(rows.some(r=>r.package==="watershed"&&r.text.includes("derived by the declared water-balance residual"))).toBe(true);
 expect(rows.filter(r=>r.package==="watershed").every(r=>r.join==="region")).toBe(true);
 for(const row of rows)if(row.source){let v:unknown=b;for(const token of row.source.slice(1).split("/"))v=(v as Record<string,unknown>)[token];expect(v).not.toBeUndefined();}
});
