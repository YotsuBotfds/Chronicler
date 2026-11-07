import {expect,it} from "vitest";
import type {Bundle} from "../../types";
import {chainBundle} from "./recoveryChainFixture";
import {economics} from "./workshopEconomicsFixture";
import {payroll} from "./workshopFinanceFixture";
import {entityHistory,indexEntityHistory} from "../entityHistory";
it("keeps household keys inferred and sampled member rations separate from household totals",()=>{
 const b=chainBundle(),index=indexEntityHistory(b),household=index.entities.find(e=>e.kind==="household")!;
 expect(household).toBeDefined();const rows=entityHistory(index,household);
 expect(rows.some(r=>r.join==="inferred"&&r.text.includes("not enduring family lineage"))).toBe(true);
 expect(rows.some(r=>r.related.some(e=>e.kind==="person"))).toBe(true);
});
it("joins exact firm payroll money without treating the controller index as a person owner",()=>{
 const b={world_state:{regions:[{name:"A"},{name:"B"},{name:"C"}],civilizations:[{}]},history:[{turn:5,livelihoods:{schema_version:1,workshop_economics:structuredClone(economics),workshop_payroll:structuredClone(payroll)}}]} as unknown as Bundle;
 const rows=entityHistory(indexEntityHistory(b),{kind:"firm",id:0});
 expect(rows.some(r=>r.package==="workshop_economics"&&r.text.includes("polity index, not a person"))).toBe(true);
 expect(rows.some(r=>r.package==="workshop_payroll")).toBe(true);
 for(const row of rows)if(row.source){let v:unknown=b;for(const token of row.source.slice(1).split("/"))v=(v as Record<string,unknown>)[token];expect(v).not.toBeUndefined();}
});
