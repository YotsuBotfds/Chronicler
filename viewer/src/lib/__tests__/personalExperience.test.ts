/** Constructed source-contract fixtures, not natural activation evidence. */
import { expect, it } from "vitest";
import type { Bundle, TurnSnapshot } from "../../types";
import { adaptiveAt, warConsequencesAt, readAdaptive } from "../personalExperience";
import { entityHistory, indexEntityHistory } from "../entityHistory";
import { adaptive, war, experienceSnapshot } from "./personalExperienceFixture";
const bundle = () => ({world_state:{regions:[{name:"A"},{name:"B"}],civilizations:[]},history:[experienceSnapshot()]}) as unknown as Bundle;
it("validates signed native inputs and preserves unknown monetary utility",()=>{
 expect(adaptiveAt(experienceSnapshot(),2)?.frame?.work[0].net_milli).toBeNull();
 const s=experienceSnapshot() as unknown as {livelihoods:{adaptive_livelihoods:typeof adaptive}};
 s.livelihoods.adaptive_livelihoods.frame.work[0].net_milli=700 as unknown as null;
 expect(adaptiveAt(s as unknown as TurnSnapshot,2)).toBeNull();
});
it("rejects future personal observations, unbounded identities and bad information masks",()=>{
 for(const key of ["date","mask","count","gate"]){const s=experienceSnapshot() as unknown as {livelihoods:{adaptive_livelihoods:typeof adaptive}};const f=s.livelihoods.adaptive_livelihoods.frame;
 if(key==="date")f.work[0].turn=4;if(key==="mask")f.known_destinations[0][2]=8;if(key==="count")f.rows_total=2;if(key==="gate")f.refusals[0].gate=9;
 expect(adaptiveAt(s as unknown as TurnSnapshot,2)).toBeNull();}
});
it("separation is explicitly T-1 and cannot become a same-turn or future read",()=>{
 expect(warConsequencesAt(experienceSnapshot(),2)?.frame?.separation?.source_turn).toBe(2);
 const s=experienceSnapshot() as unknown as {livelihoods:{war_consequences:typeof war}};s.livelihoods.war_consequences.frame.separation.source_turn=3;
 expect(warConsequencesAt(s as unknown as TurnSnapshot,2)).toBeNull();
});
it("keeps missing historical frames distinct from recorded zeros",()=>{
 const b=bundle(),s=experienceSnapshot() as unknown as {livelihoods:{adaptive_livelihoods:typeof adaptive}};
 s.livelihoods.adaptive_livelihoods.frame=null as unknown as typeof adaptive.frame;
 expect(readAdaptive(b,s as unknown as TurnSnapshot).state).toBe("unobserved");
 expect(readAdaptive({...b,history:[]},null).state).toBe("disabled");
});
it("links stable people to offers, knowledge, war pairs and own shipment without causal inference",()=>{
 const b=bundle(),rows=entityHistory(indexEntityHistory(b),{kind:"person",id:7});
 expect(rows.some(r=>r.source?.endsWith("/frame/work/0")&&r.text.includes("net money unknown"))).toBe(true);
 expect(rows.some(r=>r.text.includes("own past residence, dated packet"))).toBe(true);
 expect(rows.some(r=>r.source?.endsWith("/frame/separation/separated/0")&&r.related.some(e=>e.id===8))).toBe(true);
 expect(rows.some(r=>r.related.some(e=>e.kind==="shipment"&&e.id===9))).toBe(true);
 for(const row of rows)if(row.source){let v:unknown=b;for(const token of row.source.slice(1).split("/"))v=(v as Record<string,unknown>)[token];expect(v).not.toBeUndefined();}
});
it("keeps regional health context separate from a named guard's paid work and dates prior exposure",()=>{
 const b=bundle(),s=b.history[0] as unknown as {livelihoods:Record<string,unknown>};
 s.livelihoods.public_health={schema_version:1,source_turn:3,enabled:true,mode:"active",policy:"evidence",report_delay:0,report_turn:null,decisions:[],environment_turn:3,
 environment:[{region:0,source_turn:2,residence_observed:true,sanitation_observed:true,displaced_share:0.2,water_service:0.5,crowding_factor:1.05,flux_factor:0.9}],supply_turn:null,supplies:[],totals:{},guard_turn:3,
 guards:[{turn:3,civ:0,target:1,need:1,work:1,staffed:true,payment:"paid",members:[{agent_id:7,region:0,share:1,wage_due_milli:1000,wage_paid_milli:1000,wage_residual_milli:0,income_withheld:null}]}]};
 b.world_state.civilizations=[{},{}] as never;
 const rows=entityHistory(indexEntityHistory(b),{kind:"person",id:7});
 expect(rows.some(r=>r.package==="public_health"&&r.join==="id"&&r.text.includes("does not imply illness"))).toBe(true);
 expect(rows.some(r=>r.package==="public_health"&&r.join==="region"&&r.sourceTurn===2&&r.text.includes("not this person's record"))).toBe(true);
});
it("keeps personal timber cargo experience distinct from same-numbered food shipment",()=>{
 const b=bundle(),s=b.history[0] as unknown as {livelihoods:{adaptive_livelihoods:{frame:{trade:Record<string,unknown>[]}}}};
 s.livelihoods.adaptive_livelihoods.frame.trade[0].package="timber_orders";
 s.livelihoods.adaptive_livelihoods.frame.trade[0].outcome="route_lost";
 const rows=entityHistory(indexEntityHistory(b),{kind:"person",id:7});
 expect(rows.some(r=>r.text.includes("Own timber order")&&r.related.some(e=>e.kind==="timber_order"&&e.id===9))).toBe(true);
 expect(rows.filter(r=>r.source?.includes("/frame/trade/")).every(r=>!r.related.some(e=>e.kind==="shipment"))).toBe(true);
});

it("accepts signed combined A6 and D3 evacuation/return score inputs within the native cap",()=>{
 for(const value of [-.3,.15,.2,.3]){
  const s=experienceSnapshot() as unknown as {livelihoods:{adaptive_livelihoods:typeof adaptive}};
  s.livelihoods.adaptive_livelihoods.frame.rows[0][2]=value;
  expect(adaptiveAt(s as unknown as TurnSnapshot,2)?.frame?.rows[0][2]).toBe(value);
 }
 for(const value of [-.301,.301,Infinity,NaN]){
  const s=experienceSnapshot() as unknown as {livelihoods:{adaptive_livelihoods:typeof adaptive}};
  s.livelihoods.adaptive_livelihoods.frame.rows[0][2]=value;
  expect(adaptiveAt(s as unknown as TurnSnapshot,2)).toBeNull();
 }
});

it("separates rules3 installed scores, personal controls and independent D3 inputs",()=>{
 const make=()=>{
  const s=experienceSnapshot() as unknown as {livelihoods:{adaptive_livelihoods:Record<string,unknown>}};
  const a=s.livelihoods.adaptive_livelihoods;
  const f=a.frame as Record<string,unknown>;
  Object.assign(a,{rules:"3",mode:"record_only",decision_channels:"all"});
  Object.assign(f,{decision_channels:"all",rows:[[7,1,.2]],rows_total:1,rows_installed:1,
   a6_rows:[],a6_rows_total:0,d3_rows:[[7,1,.2]],d3_rows_total:1,
   migration_rows_would:[[7,1,-.2]],migration_rows_would_total:1,information_gate_installed:false});
  return s as unknown as TurnSnapshot;
 };
 expect(adaptiveAt(make(),2)?.frame?.d3_rows).toEqual([[7,1,.2]]);
 for(const defect of ["missing","mode","control","sum","duplicate","nonfinite","count","gate","offers"]){
  const s=make(),a=(s as unknown as {livelihoods:{adaptive_livelihoods:Record<string,unknown>}}).livelihoods.adaptive_livelihoods,f=a.frame as Record<string,unknown>;
  if(defect==="missing")delete f.d3_rows;
  if(defect==="mode")f.decision_channels="no_work";
  if(defect==="control")Object.assign(f,{a6_rows:[[7,1,-.1]],a6_rows_total:1});
  if(defect==="sum")f.rows=[[7,1,0]];
  if(defect==="duplicate")Object.assign(f,{rows:[[7,1,.2],[7,1,.2]],rows_total:2,rows_installed:2});
  if(defect==="nonfinite")f.migration_rows_would=[[7,1,NaN]];
  if(defect==="count")f.d3_rows_total=2;
  if(defect==="gate")f.information_gate_installed=true;
  if(defect==="offers")f.offers=[{turn:3,id:7,kind:"workshop",would_decline:true,accepted:false}];
  expect(adaptiveAt(s,2),defect).toBeNull();
 }
 const s=make(),a=(s as unknown as {livelihoods:{adaptive_livelihoods:Record<string,unknown>}}).livelihoods.adaptive_livelihoods,f=a.frame as Record<string,unknown>;
 Object.assign(a,{mode:"adapt",decision_channels:"no_information"});
 Object.assign(f,{decision_channels:"no_information",a6_rows:[[7,1,-.2]],a6_rows_total:1,rows:[],rows_total:0,rows_installed:0});
 expect(adaptiveAt(s,2)).not.toBeNull(); // Components cancel; neither is missing evidence.
 Object.assign(a,{decision_channels:"all"});Object.assign(f,{decision_channels:"all",information_gate_installed:true,
  a6_rows:[],a6_rows_total:0,d3_rows:[[7,1,.2],[7,1,.15]],d3_rows_total:2,rows:[[7,1,.3]],rows_total:1,rows_installed:1});
 expect(adaptiveAt(s,2)).not.toBeNull(); // Multiple D3 inputs combine under one cap.
});

it("does not relabel a legacy record-only score proposal as an installed input",()=>{
 const b=bundle(),record=(b.history[0] as unknown as {livelihoods:{adaptive_livelihoods:Record<string,unknown>}}).livelihoods.adaptive_livelihoods;
 record.mode="record_only";(record.frame as Record<string,unknown>).rows_installed=0;
 const row=entityHistory(indexEntityHistory(b),{kind:"person",id:7}).find(r=>r.source?.includes("/frame/rows/"))!;
 expect(row.text).toContain("Legacy prepared destination score proposal");
 expect(row.text).toContain("does not establish actual application or a move");
 expect(row.text).not.toContain("Installed destination score input");
});
