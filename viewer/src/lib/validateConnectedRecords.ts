/** The production strict readers, reused before accepting saved story examples. */
import type { TurnSnapshot } from "../types";
import { timberOrdersAt } from "./timberOrders";
import { warRequisitionAt } from "./warRequisition";
import { adaptiveAt,warConsequencesAt } from "./personalExperience";
import { publicHealthAt } from "./publicHealth";
import { readInfrastructure } from "./infrastructureCondition";
import { reliefRecordAt } from "./reformServices";
import { leagueRecordAt } from "./guildLeagues";
import { movementBranchesAt } from "./movementBranches";
export type ValidationState="absent"|"malformed"|"unobserved"|"disabled"|"observed";
const object=(x:unknown):x is Record<string,unknown>=>x!==null&&typeof x==="object"&&!Array.isArray(x);
export function validateConnectedRecords(snapshot:TurnSnapshot,regions:number,civs:number):Record<string,ValidationState>{
 const lh=(snapshot as unknown as Record<string,unknown>).livelihoods;
 const validators:Record<string,()=>ValidationState>={
  timber_orders:()=>timberOrdersAt(snapshot,regions,civs).status,
  war_requisition:()=>warRequisitionAt(snapshot,regions,civs).status,
  adaptive_livelihoods:()=>{const r=adaptiveAt(snapshot,regions);return !r?"malformed":r.frame?"observed":"unobserved";},
  war_consequences:()=>{const r=warConsequencesAt(snapshot,regions);return !r?"malformed":r.frame?"observed":"unobserved";},
  public_health:()=>{const r=publicHealthAt(snapshot,regions,civs);return !r?"malformed":!r.enabled?"disabled":[r.report_turn,r.environment_turn,r.supply_turn,r.guard_turn].every(t=>t===null)?"unobserved":"observed";},
  infrastructure_condition:()=>{const r=readInfrastructure(snapshot,regions,true);return r.status==="ok"?(r.frame==="unsettled"?"unobserved":"observed"):r.status;},
  reform_services:()=>{const r=reliefRecordAt(snapshot,regions,civs).record;return !r?"malformed":r.frame?"observed":"unobserved";},
  movement_branches:()=>{const r=movementBranchesAt(snapshot,regions,civs);return r.status==="recorded"||r.status==="recorded_zero"?"observed":r.status;},
  guild_leagues:()=>{const r=leagueRecordAt(snapshot,regions,civs).record;return !r?"malformed":r.frame?"observed":"unobserved";},
 };
 return Object.fromEntries(Object.entries(validators).map(([key,validate])=>[key,!object(lh)||lh.schema_version!==1?"malformed":lh[key]==null?"absent":!object(lh[key])||lh[key].source_turn!==snapshot.turn-1?"malformed":validate()]));
}
