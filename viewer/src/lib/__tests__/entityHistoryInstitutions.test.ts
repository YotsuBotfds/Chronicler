import {expect,it} from "vitest";
import {entityHistory,indexEntityHistory} from "../entityHistory";
import {validateConnectedRecords} from "../validateConnectedRecords";
import {record as relief} from "./reformServicesFixture";
import {record as league} from "./guildLeaguesFixture";
import {branchRecord} from "./movementBranchesFixture";
import CARE from "../../__fixtures__/epidemicCare.json";
import type {Bundle} from "../../types";
const bundle=(key:string,record:{source_turn:number})=>({world_state:{regions:[0,1,2,3].map(i=>({name:`R${i}`})),civilizations:[0,1,2,3].map(i=>({name:`C${i}`}))},history:[{turn:record.source_turn+1,livelihoods:{schema_version:1,[key]:record}}]}) as unknown as Bundle;
it("links pooled relief to its real public account and region, without promoting old lower estimates",()=>{
 const b=bundle("reform_services",structuredClone(relief())),index=indexEntityHistory(b);
 const region=entityHistory(index,{kind:"region",id:3});
 expect(region.some(r=>r.source?.endsWith("/frame/purchases/0")&&r.text.includes("recipients are not identified"))).toBe(true);
 expect(region.find(r=>r.source?.endsWith("/frame/deliveries/0"))?.text).toContain("no lower bound because gross outbound food is unobserved");
 expect(entityHistory(index,{kind:"relief_fund",id:1}).some(r=>r.text.includes("public account"))).toBe(true);
 expect(index.entities.some(r=>r.kind==="person")).toBe(false);
});
it("joins actual league claim to stable city and guild identities, never to a fictional merchant",()=>{
 const b=bundle("guild_leagues",structuredClone(league())),index=indexEntityHistory(b);
 const rows=entityHistory(index,{kind:"city",id:15});
 expect(rows.some(r=>r.text.includes("118:guild_levy:0")&&r.text.includes("actually paid 0.057 coins to the city's purse"))).toBe(true);
 const claim=rows.find(r=>r.source?.endsWith("/frame/payouts/0"))!;
 expect(claim.related).toContainEqual({kind:"league",id:4});expect(claim.related).toContainEqual({kind:"guild",id:10});
 expect(index.entities.some(r=>r.kind==="person")).toBe(false);
});
it("links exact named branch dues to its dated permission without inferring recruitment or personal residence",()=>{
 const b=bundle("movement_branches",branchRecord()),index=indexEntityHistory(b);
 const row=entityHistory(index,{kind:"person",id:1}).find(r=>r.package==="movement_branches")!;
 expect(row.text).toContain("Actually paid 0.01");expect(row.text).toContain("available from turn 5");
 expect(row.source).toBe("/history/0/livelihoods/movement_branches/frame/rows/0/payers/0");
 expect(row.related).toEqual([{kind:"movement_branch",id:1}]);expect(row.region).toBeNull();
 expect(validateConnectedRecords(b.history[0],4,4).movement_branches).toBe("observed");
});
it("refuses misdated D1 records and malformed dues before creating linked identities",()=>{
 const r=structuredClone(relief());r.source_turn--;
 const b=bundle("reform_services",r);b.history[0].turn=86;
 expect(indexEntityHistory(b).entities).toEqual([]);
 const branch=branchRecord();branch.frame.rows[0].dues_milli++;
 expect(indexEntityHistory(bundle("movement_branches",branch)).entities).toEqual([]);
 expect(validateConnectedRecords(bundle("movement_branches",branch).history[0],4,4).movement_branches).toBe("malformed");
});

it("links real named care wages while keeping prior epidemic capacity and mortality regional",()=>{
 const c=structuredClone(CARE.recorded.record),b={world_state:{regions:CARE.regions.map(name=>({name})),civilizations:CARE.civilizations.map(name=>({name}))},history:[{turn:CARE.recorded.turn,livelihoods:{schema_version:1,epidemic_care:c}}]} as unknown as Bundle;
 const receipt=c.frame!.find(r=>r.carers.length)!;const person=receipt.carers[0];
 const rows=entityHistory(indexEntityHistory(b),{kind:"person",id:person.agent_id});
 expect(rows.some(r=>r.source?.includes("/carers/")&&r.text.includes("wage actually paid"))).toBe(true);
 const capacity=rows.find(r=>r.source?.endsWith("/patients")),regional=rows.find(r=>r.source?.includes("/tick/applied/")&&!r.source.endsWith("/patients"));
 expect(capacity?.sourceTurn).toBe(c.source_turn-1);
 expect(regional).toBeDefined();expect(regional!.join).toBe("region");expect(regional!.sourceTurn).toBe(c.source_turn);expect(regional!.text).toContain("no individual infection");
});
