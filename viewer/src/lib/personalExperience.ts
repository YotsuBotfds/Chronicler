/** A6/D3 strict dated observations. No inferred residence, knowledge or individual share. */
import type { Bundle, TurnSnapshot } from "../types";
import { readRecord } from "./recordReading";
export interface WorkExperience {
  turn: number; id: number; kind: string; paid_milli: number | null; withheld_milli: number | null;
  title_forgone_milli: number | null; net_milli: number | null; progress: boolean | null; source: string | null;
}
export interface OfferExperience { turn: number; id: number; kind: string; would_decline: boolean; accepted: boolean }
export interface MoveExperience { turn: number; id: number; kind: "refused" | "left_soon"; region: number; origin?: number; gate?: number }
export interface TradeExperience { turn: number; id: number; region: number; kind: "shipment"; outcome: string; cause: string | null; shipment: number; package?: "titled_trade" | "timber_orders" }
const DECISION_CHANNELS = ["all", "no_migration_experience", "no_information", "no_work", "no_trade"] as const;
export type DecisionChannels = typeof DECISION_CHANNELS[number];
export interface AdaptiveRecord {
  schema_version: 1; stage: "A6"; source_turn: number; mode: "adapt" | "record_only" | "shuffled"; rules: "1" | "2" | "3";
  decision_channels?: DecisionChannels;
  frame: null | { turn: number; rows: [number,number,number][]; rows_installed: number; rows_total?: number; rows_dropped?: number;
    refusals: MoveExperience[]; quick_departures: MoveExperience[]; receipt: unknown;
    refusals_total?: number; refusals_dropped?: number; quick_departures_total?: number; quick_departures_dropped?: number;
    work: WorkExperience[]; work_dropped: number; offers: OfferExperience[]; offers_dropped: number;
    known_destinations?: [number,number,number][]; known_destinations_total?: number; known_destinations_dropped?: number;
    information_gate_installed?: boolean; trade?: TradeExperience[]; trade_dropped?: number;
    decision_channels?: DecisionChannels; a6_rows?: [number,number,number][]; a6_rows_total?: number;
    d3_rows?: [number,number,number][]; d3_rows_total?: number;
    migration_rows_would?: [number,number,number][]; migration_rows_would_total?: number };
  memory_rows: number; work_rows: number; counters: Record<string,number>; parameters: Record<string,number>;
}
export interface WarExperience { turn: number; kind: "wounded" | "would_wound" | "released" | "evacuated" | "returned"; id: number; region: number; army?: string; cause: string; destination?: number; home?: number }
export interface SeparationFrame { source_turn: number; pairs: number; separated: { a: number; b: number; relation: "spouse" | "parent"; cause: "trip" | "attached" | "displaced" | "migrated" }[]; separated_total?: number; separated_dropped?: number; by_cause: Record<string,number>; by_relation: Record<string,number> }
export interface WarConsequencesRecord {
  schema_version: 1; stage: "D3"; source_turn: number; mode: "active" | "record_only";
  frame: null | { turn: number; events: WarExperience[]; events_dropped: number; separation: SeparationFrame | null;
    separation_source: string; injury_authority: "health_care"; wound_share: number; local_threats?: number; return_experiences?: number };
  history: WarExperience[]; history_dropped: number; counters: Record<string,number>;
}
const object = (x: unknown): x is Record<string,unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isSafeInteger(x) && x >= 0;
const signedInt = (x: unknown): x is number => finite(x) && Number.isSafeInteger(x);
const nonnegative = (x: unknown): x is number => finite(x) && x >= 0;
const counters = (x: unknown) => object(x) && Object.values(x).every(nonnegative);
const carries = (key: string) => (s: TurnSnapshot) => { const l = (s as unknown as Record<string,unknown>).livelihoods; return object(l) && l[key] != null; };
function packageAt(s: TurnSnapshot, key: string, stage: string): Record<string,unknown> | null {
  const l = (s as unknown as Record<string,unknown>).livelihoods, x = object(l) ? l[key] : null;
  return object(l) && l.schema_version === 1 && object(x) && x.schema_version === 1 && x.stage === stage && x.source_turn === s.turn - 1 && count(x.source_turn) ? x : null;
}
export function adaptiveAt(snapshot: TurnSnapshot, regions: number): AdaptiveRecord | null {
  const x = packageAt(snapshot,"adaptive_livelihoods","A6"), region = (r: unknown) => count(r) && r < regions;
  if (!x || !["adapt","record_only","shuffled"].includes(x.mode as string) || !["1","2","3"].includes(x.rules as string)
    || !count(x.memory_rows) || !count(x.work_rows) || !counters(x.counters) || !counters(x.parameters)) return null;
  if (x.decision_channels !== undefined && !DECISION_CHANNELS.includes(x.decision_channels as DecisionChannels)
    || x.rules === "3" && x.decision_channels === undefined) return null;
  if (x.frame === null) return x as unknown as AdaptiveRecord;
  const f = x.frame;
  if (!object(f) || f.turn !== x.source_turn || !Array.isArray(f.rows) || f.rows.length > 256 || !count(f.rows_installed)
    || !f.rows.every((r) => Array.isArray(r) && r.length === 3 && count(r[0]) && region(r[1]) && finite(r[2]) && r[2] >= -0.300001 && r[2] <= 0.300001)
    || !Array.isArray(f.refusals) || !Array.isArray(f.quick_departures) || !Array.isArray(f.work) || !Array.isArray(f.offers)) return null;
  for (const key of ["rows_dropped","rows_total","refusals_total","refusals_dropped","quick_departures_total","quick_departures_dropped","work_dropped","offers_dropped","known_destinations_total","known_destinations_dropped","trade_dropped"]) if (f[key] !== undefined && !count(f[key])) return null;
  const bounded = (rows: unknown[], total: unknown, dropped: unknown) => rows.length <= 256 && (total === undefined || total === rows.length + Number(dropped ?? 0));
  if (!bounded(f.rows,f.rows_total,f.rows_dropped) || (f.rows_total !== undefined && f.rows_installed > Number(f.rows_total))
    || !bounded(f.refusals,f.refusals_total,f.refusals_dropped) || !bounded(f.quick_departures,f.quick_departures_total,f.quick_departures_dropped)
    || f.work.length > 256 || f.offers.length > 256) return null;
  if (f.receipt !== null && (!Array.isArray(f.receipt) || f.receipt.length !== 4 || f.receipt[0] !== x.source_turn || !Array.isArray(f.receipt[1]) || f.receipt[1].length > 256 || !f.receipt[1].every((r)=>Array.isArray(r) && r.length === 4 && count(r[0]) && region(r[1]) && region(r[2]) && (r[3] === 0 || r[3] === 1)) || !count(f.receipt[2]) || !count(f.receipt[3]))) return null;
  const dated = (r: Record<string,unknown>) => r.turn === x.source_turn && count(r.id) && typeof r.kind === "string";
  for (const [kind,rows] of [["refused",f.refusals],["left_soon",f.quick_departures]] as const) if (!rows.every((r) => object(r) && dated(r) && r.kind === kind && region(r.region)
    && (kind !== "refused" || region(r.origin) && (r.gate === 0 || r.gate === 1)))) return null;
  for (const r of f.work) {
    if (!object(r) || !dated(r) || ![r.paid_milli,r.withheld_milli,r.title_forgone_milli].every((n)=>n === null || count(n))
      || !(r.net_milli === null || signedInt(r.net_milli)) || !(r.progress === null || typeof r.progress === "boolean")
      || !(r.source === null || typeof r.source === "string")) return null;
    const known = [r.paid_milli,r.withheld_milli,r.title_forgone_milli].every((n)=>n !== null);
    if (known ? r.net_milli !== Number(r.paid_milli)-Number(r.withheld_milli)-Number(r.title_forgone_milli) : r.net_milli !== null) return null;
  }
  if (!f.offers.every((r)=>object(r) && dated(r) && typeof r.would_decline === "boolean" && typeof r.accepted === "boolean")) return null;
  if (f.known_destinations !== undefined && (!Array.isArray(f.known_destinations) || !bounded(f.known_destinations,f.known_destinations_total,f.known_destinations_dropped)
    || !f.known_destinations.every((r)=>Array.isArray(r) && r.length===3 && count(r[0]) && region(r[1]) && count(r[2]) && r[2]>=1 && r[2]<=7))) return null;
  if (f.information_gate_installed !== undefined && typeof f.information_gate_installed !== "boolean") return null;
  if (f.trade !== undefined && (!Array.isArray(f.trade) || f.trade.length > 256 || !f.trade.every((r)=>object(r) && dated(r) && r.kind === "shipment" && region(r.region) && count(r.shipment) && typeof r.outcome === "string" && (r.cause === null || typeof r.cause === "string") && (r.package === undefined || r.package === "titled_trade" || r.package === "timber_orders")))) return null;
  if (x.rules === "3") {
    if (f.decision_channels !== x.decision_channels || f.rows_total !== f.rows_installed) return null;
    const components: Record<string, [number,number,number][]> = {};
    for (const key of ["a6_rows", "d3_rows", "migration_rows_would"]) {
      const rows = f[key], total = f[key + "_total"];
      if (!Array.isArray(rows) || !count(total) || rows.length !== Math.min(256,total)
        || !rows.every(r => Array.isArray(r) && r.length === 3 && count(r[0]) && region(r[1]) && finite(r[2]) && Math.abs(r[2]) <= .300001)) return null;
      components[key] = rows as [number,number,number][];
    }
    if ((x.mode === "record_only" || x.decision_channels === "no_migration_experience") && f.a6_rows_total !== 0
      || (x.mode === "record_only" || x.decision_channels === "no_information") && f.information_gate_installed !== false
      || (x.mode === "record_only" || x.decision_channels === "no_work") && f.offers.some(o => object(o) && !o.accepted)) return null;
    const keys = f.rows.map(r => `${r[0]}:${r[1]}`);
    if (new Set(keys).size !== keys.length) return null;
    // Only complete samples can prove that the installed rows equal both
    // components. A missing bounded component is never silently a zero.
    if (Number(f.a6_rows_total) <= 256 && Number(f.d3_rows_total) <= 256 && Number(f.rows_total) <= 256) {
      const combined = new Map<string,number>();
      for (const [id,target,value] of [...components.a6_rows,...components.d3_rows]) {
        const key = `${id}:${target}`; combined.set(key,(combined.get(key) ?? 0) + value);
      }
      for (const [key,value] of combined) combined.set(key,Math.max(-.3,Math.min(.3,value)));
      for (const [key,value] of combined) if (value === 0) combined.delete(key);
      if (combined.size !== f.rows.length || !f.rows.every(r => combined.has(`${r[0]}:${r[1]}`) && Math.abs(combined.get(`${r[0]}:${r[1]}`)!-r[2]) <= 1e-6)) return null;
    }
  }
  return x as unknown as AdaptiveRecord;
}
export function warConsequencesAt(snapshot: TurnSnapshot, regions: number): WarConsequencesRecord | null {
  const x = packageAt(snapshot,"war_consequences","D3"), region = (r: unknown)=>count(r) && r < regions;
  if (!x || !["active","record_only"].includes(x.mode as string) || !Array.isArray(x.history) || x.history.length > 256 || !count(x.history_dropped) || !counters(x.counters)) return null;
  const event = (r: unknown, current = false) => object(r) && count(r.turn) && r.turn <= Number(x.source_turn) && (!current || r.turn === x.source_turn)
    && ["wounded","would_wound","released","evacuated","returned"].includes(r.kind as string) && count(r.id) && region(r.region) && typeof r.cause === "string"
    && (r.army === undefined || typeof r.army === "string" && r.army.length > 0) && (r.destination === undefined || region(r.destination)) && (r.home === undefined || region(r.home))
    && (r.kind !== "evacuated" || region(r.destination) && region(r.home));
  if (!x.history.every((r)=>event(r))) return null;
  if (x.frame === null) return x as unknown as WarConsequencesRecord;
  const f = x.frame;
  if (!object(f) || f.turn !== x.source_turn || !Array.isArray(f.events) || f.events.length > 256 || !f.events.every((r)=>event(r,true)) || !count(f.events_dropped)
    || typeof f.separation_source !== "string" || f.injury_authority !== "health_care" || !finite(f.wound_share) || f.wound_share < 0 || f.wound_share > 1) return null;
  for (const key of ["local_threats","return_experiences"]) if (f[key] !== undefined && !count(f[key])) return null;
  if (f.separation !== null) {
    const s = f.separation;
    if (!object(s) || s.source_turn !== Number(x.source_turn)-1 || !count(s.pairs) || !Array.isArray(s.separated) || s.separated.length > 256 || !counters(s.by_cause) || !counters(s.by_relation)
      || !s.separated.every((r)=>object(r) && count(r.a) && count(r.b) && r.a !== r.b && ["spouse","parent"].includes(r.relation as string) && ["trip","attached","displaced","migrated"].includes(r.cause as string))) return null;
    if (s.separated_total !== undefined && (!count(s.separated_total) || !count(s.separated_dropped) || s.separated_total !== s.separated.length+s.separated_dropped || s.separated_total > s.pairs)) return null;
  }
  return x as unknown as WarConsequencesRecord;
}
export const readAdaptive = (bundle: Bundle, snapshot: TurnSnapshot | null, turn?: number) => readRecord({key:"adaptive_livelihoods",label:"Personal livelihood experience",flag:"--adaptive-livelihoods",livelihoods:true,carries:carries("adaptive_livelihoods"),read:adaptiveAt,observed:(r:AdaptiveRecord)=>r.frame!==null,empty:(r:AdaptiveRecord)=>!!r.frame && [r.frame.rows,r.frame.work,r.frame.offers,r.frame.refusals,r.frame.quick_departures,r.frame.trade??[]].every((rows)=>!rows.length),zero:"no retained personal choice, work or movement observations"},bundle,snapshot,turn);
export const readWarConsequences = (bundle: Bundle, snapshot: TurnSnapshot | null, turn?: number) => readRecord({key:"war_consequences",label:"War experience",flag:"--war-consequences",livelihoods:true,carries:carries("war_consequences"),read:warConsequencesAt,observed:(r:WarConsequencesRecord)=>r.frame!==null,empty:(r:WarConsequencesRecord)=>!!r.frame && !r.frame.events.length && !(r.frame.separation?.separated.length),zero:"no retained war event or separated family pair"},bundle,snapshot,turn);
