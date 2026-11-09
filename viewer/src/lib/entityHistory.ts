/** Linked saved observations. Identity joins never imply causation or allocate a regional total. */
import { isRecord as object } from "./recordGuards";
import type { Bundle, TurnSnapshot } from "../types";
import { readRecoveryCrews } from "./recoveryCrews";
import { readTimberSupply } from "./timberSupply";
import { readHouseholdRetail, RETAIL_STATUSES } from "./householdRetail";
import { repairProjectsAt } from "./repairProjects";
import { residenceLedgerAt } from "./residenceLedger";
import { titledTradeAt } from "./titledTrade";
import { timberOrdersAt } from "./timberOrders";
import { warRequisitionAt } from "./warRequisition";
import { adaptiveAt, warConsequencesAt } from "./personalExperience";
import { publicHealthAt } from "./publicHealth";
import { readInfrastructure } from "./infrastructureCondition";
import { reliefRecordAt } from "./reformServices";
import { leagueRecordAt } from "./guildLeagues";
import { movementBranchesAt } from "./movementBranches";
import { epidemicCareAt } from "./epidemicCare";
import { readWatershed, watershedOutflow } from "./watershed";
import { workshopEconomicsAt } from "./workshopEconomics";
import { workshopFinanceAt } from "./workshopFinance";

export type EntityKind = "relief_fund" | "league" | "guild" | "city" | "movement_branch" | "person" | "household" | "firm" | "project" | "expedition" | "shipment" | "timber_order" | "claim" | "army" | "infrastructure_work" | "infrastructure_asset" | "region";
export interface EntityRef { kind: EntityKind; id: number | string; epoch?: number }
export type HistoryState = "disabled" | "unknown" | "malformed" | "not_sampled" | "truncated" | "recorded_zero" | "recorded";
export interface EntityHistoryRow {
  entity: EntityRef; turn: number; sourceTurn: number | null; package: string;
  join: "id" | "region" | "inferred"; state: HistoryState; text: string;
  source: string | null; region: number | null; related: EntityRef[];
}
const HISTORY_PACKAGES = ["recovery_crews", "repair_projects", "timber_supply", "household_retail", "titled_trade", "residence_ledger", "timber_orders", "war_requisition", "adaptive_livelihoods", "war_consequences", "public_health", "infrastructure_condition", "watershed", "workshop_economics", "workshop_payroll", "reform_services", "guild_leagues", "movement_branches", "epidemic_care"] as const;
type Package = typeof HISTORY_PACKAGES[number];
interface Observation extends EntityHistoryRow { package: Package }
interface PackageFrame { state: HistoryState; reason: string; rows: Observation[]; source: string | null; sourceTurn: number | null }
interface SnapshotIndex { snapshot: TurnSnapshot; epoch?: number; frames: Record<Package, PackageFrame> }
export interface EntityHistoryIndex { snapshots: SnapshotIndex[]; entities: EntityRef[] }
const livelihoods = (s: TurnSnapshot): unknown => (s as unknown as Record<string, unknown>).livelihoods;
export const entityKey = (e: EntityRef) => `${e.kind}:${e.id}${e.epoch !== undefined ? `:since${e.epoch}` : ""}`;
export const entityLabel = (e: EntityRef) => `${e.kind[0].toUpperCase()}${e.kind.slice(1).replace(/_/g, " ")} #${e.id}${e.epoch !== undefined ? ` (identity segment since turn ${e.epoch})` : ""}`;
const ref = (kind: EntityKind, id: number | string): EntityRef => ({ kind, id });
// The document's default locale is stable for its lifetime. Constructing an
// Intl formatter for every saved number dominates large history indexes; reuse
// the identical locale/precision rules without changing the observations.
const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 });
const coins = (n: number) => numberFormat.format(n / 1000);
const num = (n: number) => numberFormat.format(n);
const futureFirm = (f:{opened_turn:number;closed_turn:number|null;last_operating_turn?:number|null}, source:number) =>
  f.opened_turn>source || f.closed_turn!==null&&f.closed_turn>source || f.last_operating_turn!=null&&f.last_operating_turn>source;

/** Parse once per bundle, through the producers' strict readers. Does not read final-state histories. */
export function indexEntityHistory(bundle: Bundle): EntityHistoryIndex {
  const history = Array.isArray(bundle.history) ? bundle.history : [];
  // Missing polity metadata grants no valid polity references. Pure regional
  // records and absent optional packages still have their own valid meaning.
  const regions = bundle.world_state.regions.length, civs = bundle.world_state.civilizations?.length ?? 0;
  // A non-exact continuation cannot certify that reused pool ids name the
  // previous people. Preserve separate identity segments without rewriting ids.
  const boundaries = new Set<number>();
  const metadata=(bundle as unknown as Record<string,unknown>).metadata;
  const resume=object(metadata)?metadata.resume:null;
  if(object(resume)&&resume.exact===false&&typeof resume.turn==="number"&&Number.isInteger(resume.turn)&&resume.turn>=0)boundaries.add(resume.turn);
  for(const saved of history){const r=residenceLedgerAt(saved,regions);r?.log.forEach(log=>{if(object(log)&&log.kind==="pool_reset"&&typeof log.turn==="number"&&Number.isInteger(log.turn)&&log.turn>=0)boundaries.add(log.turn);});}
  const epochs=[...boundaries].sort((a,b)=>a-b),epochAt=(turn:number|null)=>{let latest:number|undefined;for(const boundary of epochs){if(turn===null||boundary>turn)break;latest=boundary;}return latest;};
  const scoped=(e:EntityRef,turn:number|null):EntityRef=>{
    const epoch=epochAt(turn);
    return (e.kind==="person"||e.kind==="household")&&epoch!==undefined?{...e,epoch}:e;
  };
  const on = Object.fromEntries(HISTORY_PACKAGES.map((key) => [key, history.some((s) => { const lh = livelihoods(s); return object(lh) && lh[key] != null; })]));
  const entities = new Map<string, EntityRef>();
  const snapshots = history.map((snapshot, i) => {
    const frames = {} as Record<Package, PackageFrame>;
    const lh = livelihoods(snapshot);
    for (const key of HISTORY_PACKAGES) {
      const source = `/history/${i}/livelihoods/${key}`;
      const frame: PackageFrame = { state: "recorded", reason: "", rows: [], source, sourceTurn: snapshot.turn - 1 };
      frames[key] = frame;
      if (!on[key]) { Object.assign(frame, { state: "disabled", reason: "Off or not recorded in this run", source: null, sourceTurn: null }); continue; }
      if (lh == null || (object(lh) && lh.schema_version === 1 && lh[key] == null)) {
        Object.assign(frame, { state: "unknown", reason: "No observation at this snapshot; unknown, not zero", source: null, sourceTurn: null }); continue;
      }
      if (!object(lh) || lh.schema_version !== 1) {
        Object.assign(frame, { state: "malformed", reason: "Rejected livelihoods container", sourceTurn: null }); continue;
      }
      const bad = () => { Object.assign(frame, { state: "malformed", reason: "Rejected by the package's strict reader", sourceTurn: null }); };
      const unknown = () => { Object.assign(frame, { state: "unknown", reason: "The completed turn was not observed; unknown, not zero" }); };
      const add = (entity: EntityRef, path: string, text: string, region: number | null = null, related: EntityRef[] = [], state: HistoryState = "recorded", join: EntityHistoryRow["join"] = "id", sourceTurn: number | null = frame.sourceTurn, identityTurn: number | null = sourceTurn) => {
        entity=scoped(entity,identityTurn);
        related=related.map(e=>scoped(e,identityTurn));
        frame.rows.push({ entity, turn: snapshot.turn, sourceTurn, package: key, join, state, text, source: source + path, region, related });
        for (const e of [entity, ...related, ...(region===null?[]:[ref("region",region)])]) entities.set(entityKey(e), e);
      };
      if (key === "recovery_crews") {
        const r = readRecoveryCrews(snapshot, regions, civs);
        if (r.status !== "ok") { bad(); continue; }
        if (r.record.receipts === null) { unknown(); continue; }
        if (r.record.rows_dropped > 0) Object.assign(frame, { state: "truncated", reason: "Receipts were dropped during this run; absence is not proof of no work" });
        r.record.receipts.forEach((receipt, j) => {
          const project = ref("project", receipt.pid);
          add(project, `/receipts/${j}`, `${receipt.kind}: ${num(receipt.delivered)} work; ${coins(receipt.wages_milli)} coins to this crew`, receipt.region, receipt.members.map((m) => ref("person", m.agent_id)));
          receipt.members.forEach((m, k) => add(ref("person", m.agent_id), `/receipts/${j}/members/${k}`,
            `Repair work ${num(m.worked)}; wage ${coins(m.wage_milli)} coins; ordinary income withheld ${m.income_replaced === null ? "unknown" : num(m.income_replaced)}`,
            receipt.region, [project], m.worked === 0 && m.wage_milli === 0 ? "recorded_zero" : "recorded"));
        });
      } else if (key === "repair_projects") {
        const r = repairProjectsAt(snapshot, regions, civs);
        if (!r) { bad(); continue; }
        for (const list of ["projects", "closed"] as const) r[list].forEach((p, j) => add(ref("project", p.pid), `/${list}/${j}`,
          `${p.kind} ${p.status}; ${num(p.delivered)} of ${num(p.scope)} work; ${num(p.timber_used)} timber used`, p.region));
        if (r.receipts === null) unknown();
        r.receipts?.forEach((r, j) => r.crew.forEach((id) => add(ref("person", id), `/receipts/${j}`,
          `Named on ${r.kind} project #${r.pid}; crew total ${coins(r.wages_milli)} coins (individual allocation unrecorded)`, r.region, [ref("project", r.pid)])));
      } else if (key === "timber_supply") {
        const r = readTimberSupply(snapshot, regions, civs);
        if (r.status !== "ok") { bad(); continue; }
        for (const list of ["expeditions", "closed"] as const) r.record[list].forEach((e, j) => add(ref("expedition", e.eid), `/${list}/${j}`,
          `${e.status}, ${e.stage}; ${num(e.cut)} timber cut; ${num(e.delivered)} delivered`, e.home, e.crew.map((id) => ref("person", id)),"recorded","id",frame.sourceTurn,e.launched_turn));
        if (r.record.receipts === null) { unknown(); continue; }
        r.record.receipts.forEach((r, j) => r.crew.forEach((id) => add(ref("person", id), `/receipts/${j}`,
          `Woodcutting expedition #${r.eid}, ${r.stage}; crew total ${coins(r.wages_milli)} coins (individual allocation unrecorded)`, r.home, [ref("expedition", r.eid)])));
      } else if (key === "household_retail") {
        const r = readHouseholdRetail(snapshot, regions);
        if (r.status !== "ok") { bad(); continue; }
        if (r.record.sample === null) { unknown(); continue; }
        r.record.sample.forEach((p, j) => {
          const person=ref("person",p[0]), household=ref("household",p[2]);
          add(person, `/sample/${j}`, `Food ration ${num(p[3])} of fair share ${num(p[4])}; ${RETAIL_STATUSES[p[5]]}. Who paid is not recorded`, p[1],[household]);
          add(household, `/sample/${j}`, `Sampled member #${p[0]}: food ration ${num(p[3])} of fair share ${num(p[4])}; ${RETAIL_STATUSES[p[5]]}. Household key uses smaller co-resident couple id, children use a parent's key; inferred current grouping, not enduring family lineage. Household totals and who paid remain unknown`,p[1],[person],"recorded","inferred");
        });
        r.record.regions?.forEach((p, j) => add(ref("region", p.region), `/regions/${j}`,
          p.provisioning ? `Market total: ${p.provisioning.persons} people; ${coins(p.provisioning.paid_milli)} coins paid; ${p.provisioning.priced_out_persons} priced out`
            : "Market provisioning unknown, not zero", p.region, [], p.provisioning ? "recorded" : "unknown"));
        Object.assign(frame, { state: "not_sampled", reason: "Not in the bounded person sample; no evidence about this person's ration or purchases" });
      } else if (key === "titled_trade") {
        const r = titledTradeAt(snapshot, regions);
        if (r.status === "malformed" || !r.record) { bad(); continue; }
        for (const list of ["shipments", "closed"] as const) r.record[list].forEach((s, j) => {
          const ship = ref("shipment", s.id), holder = ref("person", s.holder);
          add(ship, `/${list}/${j}`, `${s.status}${s.outcome ? `: ${s.outcome}` : ""}; ${s.cargo.reduce((a, b) => a + b, 0) / 1000} food aboard`, s.origin, [holder],"recorded","id",frame.sourceTurn,s.dispatched_turn);
          add(holder, `/${list}/${j}`, `Holder of shipment #${s.id}; ${s.status}${s.outcome ? `: ${s.outcome}` : ""}; origin context only`, s.origin, [ship],"recorded","id",frame.sourceTurn,s.dispatched_turn);
        });
        if (!r.record.frame) { unknown(); continue; }
        r.record.frame.sales.forEach((s, j) => add(ref("person", s.holder), `/frame/sales/${j}`, `${coins(s.credited)} coins credited from retail sales; exact attribution to cargo: ${s.exact ? "yes" : "no"}`, s.region));
      } else if (key === "residence_ledger") {
        const r = residenceLedgerAt(snapshot, regions);
        if (!r) { bad(); continue; }
        if (r.events === null) { unknown(); continue; }
        if (r.events_dropped > 0) Object.assign(frame, { state: "truncated", reason: "Spell events were dropped; absence is not evidence of no event" });
        r.events.forEach((e, j) => add(ref("person", e.id), `/events/${j}`,
          `Motive-classified displacement spell ${e.kind}; cause ${e.cause}, home anchor ${e.anchor}; ${e.length} turns. This event does not record every residence or establish all physical displacement`, e.region,[],"recorded","id",frame.sourceTurn,e.kind==="pool_reset"?r.source_turn-1:r.source_turn));
      } else if (key === "timber_orders") {
        const r = timberOrdersAt(snapshot, regions, civs);
        if (r.status === "malformed" || !r.record) { bad(); continue; }
        for (const list of ["orders", "closed"] as const) r.record[list].forEach((o, j) => {
          const order = ref("timber_order", o.id), holder = ref("person", o.holder), where = o.path[o.cursor];
          const text = `${o.outcome ?? o.status}; ${num(o.cargo_milli / 1000)} timber aboard, ${num(o.delivered_milli / 1000)} delivered; escrow held ${coins(o.cash)}, actually credited ${coins(o.credited_milli)}, refunded ${coins(o.refunded_milli)} coins`;
          add(order, `/${list}/${j}`, text, where, [holder],"recorded","id",frame.sourceTurn,o.dispatched_turn);
          add(holder, `/${list}/${j}`, `Carrier/title of timber order #${o.id}: ${text}. Cargo position is not the person's residence`, where, [order],"recorded","id",frame.sourceTurn,o.dispatched_turn);
        });
        if (!r.record.frame) { unknown(); continue; }
        if (r.record.frame.events_dropped) Object.assign(frame, { state: "truncated", reason: "Timber order events were dropped; absence is unknown" });
      } else if (key === "war_requisition") {
        const r = warRequisitionAt(snapshot, regions, civs);
        if (r.status === "malformed" || !r.record) { bad(); continue; }
        if (r.status === "disabled") { Object.assign(frame, { state: "disabled", reason: "Requisition is explicitly disabled" }); continue; }
        if (!r.record.frame) { unknown(); continue; }
        const f = r.record.frame;
        if (f.events_dropped || f.claims_dropped) Object.assign(frame, { state: "truncated", reason: "Events or liability rows are outside retention; absence is unknown" });
        f.claims.forEach((c, j) => {
          const claim = ref("claim", c.id), owner = ref("person", c.owner);
          const text = `Restitution claim #${c.id} (${c.source}, ${c.status}): original due ${coins(c.due_milli)}, actually paid ${coins(c.paid_milli)}, unpaid ${coins(c.due_milli - c.paid_milli)} coins. A liability is not spendable cash`;
          add(claim, `/frame/claims/${j}`, text, c.region, [owner],"recorded","id",frame.sourceTurn,c.turn);
          add(owner, `/frame/claims/${j}`, text, c.region, [claim],"recorded","id",frame.sourceTurn,c.turn);
        });
        f.events.forEach((e, j) => {
          const named = [...(e.owner !== undefined ? [ref("person", e.owner)] : []), ...(e.army ? [ref("army", e.army)] : []),
            ...(e.shipment !== undefined ? [ref(e.package === "timber_orders" ? "timber_order" : "shipment", e.shipment)] : []),
            ...(e.allocations ?? []).map((a) => ref("army", a.army))];
          const unique = [...new Map(named.map((item) => [entityKey(item), item])).values()];
          const text = e.kind === "consumption" ? `Army consumed ${e.consumed_rations} of ${e.demanded_rations} demanded rations; adequacy ${num(e.adequacy!)}`
            : e.package === "timber_orders" ? `Timber cargo seized: ${num((e.quantity_milli ?? 0) / 1000)} timber; acquisition-value liability ${coins(e.acquisition_value_milli ?? 0)} coins; no ration conversion`
              : `${e.kind}: ${num((e.removed_milli ?? 0) / 1000)} food removed; ${(e.allocations ?? []).reduce((s, a) => s + a.rations, 0) + (e.credited_rations ?? 0)} rations credited; ${num((e.destroyed_milli ?? 0) / 1000)} food destroyed`;
          for (const entity of unique) add(entity, `/frame/events/${j}`, text, e.region ?? null, unique.filter((item) => entityKey(item) !== entityKey(entity)));
        });
      } else if (key === "adaptive_livelihoods") {
        const r = adaptiveAt(snapshot, regions);
        if (!r) { bad(); continue; }
        if (!r.frame) { unknown(); continue; }
        const f = r.frame;
        if ([f.rows_dropped,f.refusals_dropped,f.quick_departures_dropped,f.work_dropped,f.offers_dropped,f.trade_dropped,f.known_destinations_dropped].some((n)=>Number(n)>0)) Object.assign(frame,{state:"truncated",reason:"Personal experience rows outside the bounded sample are unknown"});
        f.work.forEach((w,j)=>add(ref("person",w.id),`/frame/work/${j}`,`${w.kind} experience: actually paid ${w.paid_milli===null?"unknown":coins(w.paid_milli)}, ordinary income withheld ${w.withheld_milli===null?"unknown":coins(w.withheld_milli)}, title forgone ${w.title_forgone_milli===null?"unknown":coins(w.title_forgone_milli)}, net money ${w.net_milli===null?"unknown":coins(w.net_milli)}; training progress ${w.progress===null?"unknown":w.progress?"yes":"no"}. Source: ${w.source??"unrecorded"}`));
        f.offers.forEach((o,j)=>add(ref("person",o.id),`/frame/offers/${j}`,`${o.kind} offer ${o.accepted?"accepted":"declined"}; prior personal experience would decline: ${o.would_decline?"yes":"no"}. An offer is not a completed job`));
        for (const name of ["refusals","quick_departures"] as const) f[name].forEach((e,j)=>add(ref("person",e.id),`/frame/${name}/${j}`,e.kind==="refused"?`Native migration refused: ${e.gate===0?"quarantine closure":"relocation fare/household liquidity"}; target region context only`:`Left soon after arriving; dated own experience, no inferred motive`,e.region));
        f.rows.forEach(([id,target,penalty],j)=>add(ref("person",id),`/frame/rows/${j}`,`${r.rules==="3"?"Installed destination score input":"Legacy prepared destination score proposal"} ${num(penalty)} for region ${target}; mode ${r.mode}. ${r.rules==="3"?"A score input is not a move or causal outcome attribution":"This row does not establish actual application or a move"}`,target));
        f.known_destinations?.forEach(([id,dst,mask],j)=>add(ref("person",id),`/frame/known_destinations/${j}`,`Destination information for region ${dst}: ${[mask&1?"own past residence":null,mask&2?"living bond":null,mask&4?"dated packet":null].filter(Boolean).join(", ")}. This is knowledge, not residence`,dst));
        f.trade?.forEach((t,j)=>add(ref("person",t.id),`/frame/trade/${j}`,`Own ${t.package === "timber_orders" ? "timber order" : "food shipment"} #${t.shipment}: ${t.outcome}${t.cause?` (${t.cause})`:""}; destination context only`,t.region,[ref(t.package === "timber_orders" ? "timber_order" : "shipment",t.shipment)]));
      } else if (key === "war_consequences") {
        const r = warConsequencesAt(snapshot,regions);
        if (!r) { bad(); continue; }
        if (!r.frame) { unknown(); continue; }
        const f=r.frame;
        if (f.events_dropped || f.separation?.separated_dropped) Object.assign(frame,{state:"truncated",reason:"War events or separation pairs outside retention are unknown"});
        f.events.forEach((e,j)=>{
          const person=ref("person",e.id), related=e.army?[ref("army",e.army)]:[];
          const text=`War event ${e.kind}; recorded cause ${e.cause}${e.destination!==undefined?`; destination region ${e.destination}`:""}. No safety or causal inference from this row`;
          add(person,`/frame/events/${j}`,text,e.region,related);
          for(const army of related) add(army,`/frame/events/${j}`,text,e.region,[person]);
        });
        f.separation?.separated.forEach((p,j)=>{
          for(const [id,other] of [[p.a,p.b],[p.b,p.a]]) add(ref("person",id),`/frame/separation/separated/${j}`,`Separated ${p.relation} pair with person #${other}: ${p.cause}; prior source turn ${f.separation!.source_turn}. Army attachment is not residence`,null,[ref("person",other)],"recorded","id",f.separation!.source_turn);
        });
      } else if (key === "epidemic_care") {
        const r=epidemicCareAt(snapshot,regions,civs);
        if(!r){bad();continue;}
        if(!r.frame)Object.assign(frame,{state:"unknown",reason:"Named epidemic care work was unobserved, not zero; any regional tick is separate context"});
        r.frame?.forEach((receipt,j)=>receipt.carers.forEach((c,k)=>add(ref("person",c.agent_id),`/frame/${j}/carers/${k}`,`Epidemic care work ${num(c.share)} share; wage actually paid ${coins(c.wage_paid_milli)}, refused ${coins(c.wage_residual_milli)} coins; ordinary income withheld ${c.income_withheld===null?"unknown":num(c.income_withheld)}. A named carer is not an identified patient or a cause of an individual's survival`,receipt.region)));
        r.tick?.applied.forEach((a,j)=>{
          add(ref("region",a.region),`/tick/applied/${j}/patients`,`Prior regional care capacity input: ${num(a.patients)} patient capacity, supplied in source turn ${a.source_turn}. Capacity is not an observed patient's treatment or survival`,a.region,[],"recorded","region",a.source_turn);
          add(ref("region",a.region),`/tick/applied/${j}`,`Current regional epidemic tick: infectious ${num(a.infectious)}, coverage ${num(a.coverage)}, case-fatality factor ${num(a.care_factor)}, regional deaths ${a.deaths===null?"unobserved":a.deaths}; prior capacity source turn ${a.source_turn}. These are epidemic fractions and regional counts; no individual infection, treatment or death is inferred`,a.region,[],"recorded","region");
        });
      } else if (key === "public_health") {
        const r=publicHealthAt(snapshot,regions,civs);
        if (!r) { bad(); continue; }
        if (!r.enabled) { Object.assign(frame,{state:"disabled",reason:"Public health is explicitly disabled"}); continue; }
        if ([r.report_turn,r.environment_turn,r.supply_turn,r.guard_turn].every((t)=>t===null)) { unknown(); continue; }
        const savedEnvironment=object(lh.public_health)&&Array.isArray(lh.public_health.environment)?lh.public_health.environment:[];
        r.environment.forEach((e,j)=>{
          for(const [field,label,observed] of [["displaced_share","motive-classified spell share",e.residence_observed],["water_service","water service",e.sanitation_observed]] as const)
            add(ref("region",e.region),`/environment/${j}/${field}`,`Prior regional public-health exposure input: ${label} ${observed?num(e[field]):"unobserved, not zero"}. No individual diagnosis or mortality attribution`,e.region,[],observed?"recorded":"unknown","region",e.source_turn);
          const configured=e.crowding_basis==="density_only",crowdingObserved=configured||e.residence_observed;
          add(ref("region",e.region),`/environment/${j}/crowding_factor`,`${configured?"Current configured":"Prior motive-derived"} extra susceptibility multiplier: ${crowdingObserved?num(e.crowding_factor):"unobserved, not zero"}; ${e.crowding_basis}. A model input is not a housing-pressure measurement or individual outcome`,e.region,[],crowdingObserved?"recorded":"unknown","region",e.crowding_source_turn);
          if(object(savedEnvironment[j])&&Object.prototype.hasOwnProperty.call(savedEnvironment[j],"recent_arrival_share"))
            add(ref("region",e.region),`/environment/${j}/recent_arrival_share`,e.arrival_diagnostics_complete===true
              ? `Prior recent residence-arrival share ${num(e.recent_arrival_share!)}; complete window and coverage. Arrivals do not establish forced displacement or measured housing pressure`
              : "Prior recent residence-arrival share unknown, not zero: the diagnostic window or coverage is incomplete or unrecorded",
            e.region,[],e.arrival_diagnostics_complete!==true?"unknown":e.recent_arrival_share===0?"recorded_zero":"recorded","region",e.source_turn);
          add(ref("region",e.region),`/environment/${j}/flux_factor`,`Current public-health flux multiplier ${num(e.flux_factor)}; mode ${r.mode}. A model input is not an individual outcome`,e.region,[],"recorded","region");
        });
        r.supplies.forEach((p,j)=>add(ref("region",p.region),`/supplies/${j}`,`Regional patient supply: ${num(p.food_milli/1000)} food of ${num(p.need_milli/1000)} needed; ${p.reason}. Patients and recipient households are not identified`,p.region));
        r.guards.forEach((g,j)=>g.members.forEach((m,k)=>add(ref("person",m.agent_id),`/guards/${j}/members/${k}`,`Public-health guard work ${num(m.share)} share; wage actually paid ${coins(m.wage_paid_milli)} coins, refused ${coins(m.wage_residual_milli)}; ordinary income withheld ${m.income_withheld===null?"unknown":num(m.income_withheld)}. Work does not imply illness or exposure`,m.region)));
      } else if (key === "infrastructure_condition") {
        const r=readInfrastructure(snapshot,regions,true);
        if (r.status!=="ok") { bad(); continue; }
        for (const name of ["assets","terminal"] as const) r.record[name].forEach((a,j)=>add(ref("infrastructure_asset",a.aid),`/${name}/${j}`,`${a.kind} ${a.status}; condition ${num(a.condition)}, service ${num(a.service)}; responsible polity ${a.responsible}`,a.region));
        for (const name of ["works","closed"] as const) r.record[name].forEach((w,j)=>add(ref("infrastructure_work",w.wid),`/${name}/${j}`,`${w.kind} ${w.status}; ${num(w.delivered)} work delivered of ${num(w.scope)}, ${num(w.credited)} condition work credited; ${num(w.timber_used)} timber used`,w.region,[ref("infrastructure_asset",w.aid)]));
        if (r.record.receipts===null) { if (r.frame!=="no_works") unknown(); continue; }
        r.record.receipts.forEach((receipt,j)=>{
          const work=ref("infrastructure_work",receipt.wid),asset=ref("infrastructure_asset",receipt.aid);
          add(work,`/receipts/${j}`,`${receipt.status}: ${receipt.reasons.join(", ")||"no limit recorded"}; work delivered ${num(receipt.delivered)}, credited ${num(receipt.credited)}`,receipt.region,[asset]);
          receipt.members?.forEach((m,k)=>add(ref("person",m.agent_id),`/receipts/${j}/members/${k}`,`${receipt.kind} repair work ${num(m.worked)}; wage actually paid ${coins(m.wages_milli)}, refused ${coins(m.wage_refused_milli)} coins; ordinary income withheld ${m.income_replaced===null?"unknown":num(m.income_replaced)}`,receipt.region,[work,asset]));
        });
      } else if (key === "watershed") {
        const r=readWatershed(snapshot,regions,{on:true});
        if (r.status==="unobserved") { unknown(); continue; }
        if (r.status!=="ok") { bad(); continue; }
        const c=r.record.regions!,out=watershedOutflow(r.record)!;
        c.storage.forEach((storage,rid)=>add(ref("region",rid),`/regions`, `Water account region ${rid}: opening storage ${num(c.storage_open[rid])}, precipitation ${num(c.precipitation[rid])}, inflow ${num(c.inflow[rid])}, withdrawal ${num(c.withdrawal[rid])}, closing storage ${num(storage)}; outflow ${num(out[rid])} derived by the declared water-balance residual. Drought duration ${c.drought_turns[rid]}. Regional flow does not establish an individual's exposure or upstream harm`,rid,[],"recorded","region"));
        r.record.floods?.forEach((f,j)=>add(ref("region",f.region),`/floods/${j}`,`Recorded flood onset: excess ${num(f.excess)}, inflow ${num(f.inflow)}, precipitation ${num(f.precipitation)}. Upstream co-occurrence is not proof of harm`,f.region,[],"recorded","region"));
        for (const name of ["declared","ended"] as const) r.record.droughts?.[name].forEach((d,j)=>add(ref("region",d.region),`/droughts/${name}/${j}`,`Recorded drought ${name}: ${d.turns} turns, minimum storage fraction ${num(d.min_fraction)}`,d.region,[],"recorded","region"));
      } else if (key === "reform_services") {
        const r=reliefRecordAt(snapshot,regions,civs).record;
        if(!r || r.source_turn!==snapshot.turn-1){bad();continue;}
        if(!r.frame){unknown();continue;}
        r.frame.civs.forEach((c,j)=>add(ref("relief_fund",c.civ),`/frame/civs/${j}`,`Polity relief account: opening ${coins(c.fund_open_milli)}, paid in ${coins(c.to_fund_milli)}, actually spent ${coins(c.spent_milli)}, refunded ${coins(c.refunded_milli)}, closing ${coins(c.fund_close_milli)} coins. This is a public account, not a person's balance`));
        r.frame.purchases.forEach((p,j)=>add(ref("region",p.region),`/frame/purchases/${j}`,`Relief bought ${num(p.food_milli/1000)} physical food, ${num(p.rations)} rations; sellers actually credited ${coins(p.credited_milli)} coins. Sellers and recipients are not identified`,p.region,[ref("relief_fund",p.civ)],"recorded","region"));
        r.frame.deliveries.forEach((d,j)=>add(ref("region",d.region),`/frame/deliveries/${j}`,`Pooled relief bought in turn ${d.bought_turn}: individual recipients unknown; regional delivery ${!d.observed?"unobserved":`at most ${num(d.delivered_at_most!)} rations; no lower bound because gross outbound food is unobserved`}. This does not identify anyone's ration`,d.region,[ref("relief_fund",d.civ)],d.observed?"recorded":"unknown","region"));
      } else if(key === "guild_leagues") {
        const r=leagueRecordAt(snapshot,regions,civs).record;
        if(!r || r.source_turn!==snapshot.turn-1){bad();continue;}
        if(!r.frame){unknown();continue;}
        if(r.dissolved_dropped>0)Object.assign(frame,{state:"truncated",reason:"Dissolved league identities outside retention are unknown"});
        const memberRegion=new Map<string,number>();
        r.frame.leagues.forEach((l,j)=>{
          const league=ref("league",l.league);
          add(league,`/frame/leagues/${j}`,`League fund ${coins(l.fund_open_milli)} to ${coins(l.fund_close_milli)} coins; actual dues ${coins(l.dues_milli)}, claims paid ${coins(l.payouts_milli)}${l.dissolved?`; dissolved ${l.dissolved}`:""}. City purse payments are not personal merchant compensation`);
          l.members.forEach((m,k)=>{
            const guild=ref("guild",m.guild),city=ref("city",m.city);
            memberRegion.set(`${l.league}:${m.guild}:${m.city}`,m.region);
            for(const [entity,related] of [[league,[guild,city]],[guild,[league,city]],[city,[league,guild]]] as const)
              add(entity,`/frame/leagues/${j}/members/${k}`,`Recorded league member: guild #${m.guild}, city #${m.city}, polity ${m.lord}; joined turn ${m.joined_turn}; cumulative dues ${coins(m.dues_milli)}, city payouts ${coins(m.payouts_milli)} coins`,m.region,[...related]);
          });
        });
        r.frame.payouts.forEach((p,j)=>{
          const league=ref("league",p.league),guild=ref("guild",p.guild),city=ref("city",p.city),region=memberRegion.get(`${p.league}:${p.guild}:${p.city}`)??null;
          for(const [entity,related] of [[league,[guild,city]],[guild,[league,city]],[city,[league,guild]]] as const)
            add(entity,`/frame/payouts/${j}`,`Recorded ${p.kind} claim ${p.event_id}: loss ${coins(p.loss_milli)}, actually paid ${coins(p.paid_milli)} coins to the city's purse. No individual merchant payment is recorded`,region,[...related]);
        });
        r.frame.changes.forEach((c,j)=>add(ref("league",c.league),`/frame/changes/${j}`,`League ${c.kind}${c.reason?`: ${c.reason}`:""}; returned ${c.returned_milli===null?"unrecorded":coins(c.returned_milli)} coins; unclaimed ${c.unclaimed_milli===null?"unrecorded":coins(c.unclaimed_milli)}`,null,[...(c.guild===null?[]:[ref("guild",c.guild)]),...(c.city===null?[]:[ref("city",c.city)])]));
      } else if(key === "movement_branches") {
        const read=movementBranchesAt(snapshot,regions,civs),r=read.record;
        if(read.status==="malformed"||!r){bad();continue;}
        if(!r.frame){unknown();continue;}
        if(r.frame.new_identities_refused>0)Object.assign(frame,{state:"truncated",reason:"New branch identities at the lifetime bound were refused; no old id was reused"});
        r.frame.rows.forEach((b,j)=>{
          const branch=ref("movement_branch",b.branch),path=`/frame/rows/${j}`;
          add(branch,path,`Movement ${b.movement-1} branch at host polity ${b.host}, target ${b.target}: ${b.status}; ${b.members} resident adults; actually paid ${coins(b.dues_milli)} coins from ${b.payers.length} people; next-turn permission ${b.active_from===null?"none":`available from turn ${b.active_from}`}. Permission is not recruitment or a causal explanation`,null,b.payers.map(id=>ref("person",id)));
          b.regions.forEach(region=>add(ref("region",region),path,`Movement branch #${b.branch}: ${b.status}; permission ${b.active_from===null?"none":`available from turn ${b.active_from}`}. Branch membership does not establish any particular resident's belief or decision`,region,[branch],"recorded","region"));
          b.payers.forEach((id,k)=>add(ref("person",id),path+`/payers/${k}`,`Actually paid 0.01 coins in local meeting dues to host polity ${b.host}; branch #${b.branch}. Permission ${b.active_from===null?"unavailable":`available from turn ${b.active_from}`} does not establish a personal recruitment outcome`,null,[branch]));
        });
      } else if (key === "workshop_economics") {
        const r=workshopEconomicsAt(snapshot,regions);
        if (r.status==="malformed" || !r.record) { bad(); continue; }
        if([...r.record.firms,...r.record.closed].some(f=>futureFirm(f,r.record!.source_turn))){bad();continue;}
        for(const name of ["firms","closed"] as const) r.record[name].forEach((f,j)=>add(ref("firm",f.firm),`/${name}/${j}`,`Firm ${f.status}; capital ${coins(f.capital)} coins; ${f.operating_turns} operating turns. Capital payer is a polity index, not a person`,f.region));
        if (!r.record.receipts) { unknown(); continue; }
        r.record.receipts.forEach((f,j)=>add(ref("firm",f.firm),`/receipts/${j}`,`Firm ${f.status}${f.operating?", operating":""}; cash ${coins(f.cash_open)} to ${coins(f.cash_close)} coins; wages actually paid ${coins(f.wages_paid)}; wages still owed ${coins(f.owed_after)}; wares produced ${num(f.produced/1000)}, unsold ${num(f.unsold_inventory/1000)}. Regional household sales are not attributed to named buyers`,f.region));
      } else {
        const r=workshopFinanceAt(snapshot,regions);
        if (!r) { bad(); continue; }
        if([...r.firms,...r.closed].some(f=>futureFirm(f,r.source_turn))){bad();continue;}
        for(const name of ["firms","closed"] as const) r[name].forEach((f,j)=>add(ref("firm",f.site),`/${name}/${j}`,`Firm ${f.status}; actual cash ${coins(f.cash)} coins, inventory ${num(f.inventory/1000)} loads; unpaid wage obligations ${coins(f.owed.reduce((s,o)=>s+o.amount,0))} coins (liabilities, not paid wages)`,f.region));
        if (!r.receipts || !r.transfers) { unknown(); continue; }
        r.receipts.forEach((f,j)=>{
          const firm=ref("firm",f.site);
          add(firm,`/receipts/${j}`,`Payroll: wages due ${coins(f.wages_due)}, actually paid ${coins(f.wages_paid)}, owed after ${coins(f.owed_after)} coins`,f.region,f.crew.map(id=>ref("person",id)));
          f.crew.forEach(id=>add(ref("person",id),`/receipts/${j}`,`Named workshop crew member of firm #${f.site}; crew total wages ${coins(f.wages_paid)} coins, individual amount not allocated from this total`,f.region,[firm]));
        });
        r.transfers.money.forEach((m,j)=>{
          if (m.payee[0]!=="agent_wealth" || m.payer[0]!=="workshop_cash") return;
          const firm=ref("firm",m.payer[1]),person=ref("person",m.payee[1]);
          const region=r.firms.find(f=>f.site===m.payer[1])?.region??r.closed.find(f=>f.site===m.payer[1])?.region??null;
          add(person,`/transfers/money/${j}`,`Exact firm ${m.kind} transfer: ${coins(m.applied)} coins actually credited, ${coins(m.residual)} refused; no individual ordinary-income cost supplied by this transfer`,region,[firm]);
          add(firm,`/transfers/money/${j}`,`Exact ${m.kind} transfer to person #${m.payee[1]}: ${coins(m.applied)} coins actually credited`,region,[person]);
        });
      }
    }
    return { snapshot, epoch:epochAt(snapshot.turn-1), frames };
  });
  return { snapshots, entities: [...entities.values()].sort((a, b) => a.kind.localeCompare(b.kind) || String(a.id).localeCompare(String(b.id), undefined, { numeric: true })) };
}

/** Selected entity's dated facts and explicitly separate regional context. No interpolation across gaps. */
export function entityHistory(index: EntityHistoryIndex, entity: EntityRef, throughTurn = Infinity): EntityHistoryRow[] {
  const result: EntityHistoryRow[] = [];
  for (const { snapshot, frames, epoch } of index.snapshots) {
    if (snapshot.turn > throughTurn) continue;
    const direct: EntityHistoryRow[] = [];
    for (const key of HISTORY_PACKAGES) {
      const frame = frames[key];
      const directRows = frame.rows.filter((r) => entityKey(r.entity) === entityKey(entity));
      const context = entity.kind === "region" ? frame.rows.filter((r)=>r.region===entity.id&&r.entity.kind!=="region") : [];
      const seen = new Set(directRows.map(r=>r.source));
      const rows=[...directRows];
      for(const row of context)if(!seen.has(row.source)){seen.add(row.source);rows.push({...row,entity,join:"region",text:`Regional context; named ${entityLabel(row.entity)}: ${row.text}`,related:[row.entity,...row.related]});}
      direct.push(...rows);
      if (!rows.length && (entity.kind === "person" || entity.kind === "household" && key === "household_retail" || entity.kind === "firm" && (key === "workshop_economics" || key === "workshop_payroll"))) {
        const crossed=(entity.kind==="person"||entity.kind==="household")&&entity.epoch!==epoch;
        const empty = frame.state === "recorded" && !crossed;
        direct.push({ entity, turn: snapshot.turn, sourceTurn: frame.sourceTurn, package: key, join: "id", state: crossed?"unknown":empty ? "recorded_zero" : frame.state,
          text: crossed?"Personal identity continuity is unverified across the recorded non-exact continuation or pool reset; this numeric id is a different identity segment":empty ? key === "residence_ledger" ? "No spell event recorded for this id; residence and displacement status remain unknown" : "No named activity in this package's completed-turn frame" : frame.reason,
          source: frame.source, region: null, related: [] });
      }
    }
    result.push(...direct);
    if (entity.kind !== "region") {
      const regions = new Set(direct.flatMap((r) => r.region === null ? [] : [r.region]));
      for (const region of regions) for (const row of [...frames.household_retail.rows,...frames.public_health.rows,...frames.watershed.rows,...frames.reform_services.rows,...frames.epidemic_care.rows]) if (row.entity.kind === "region" && row.entity.id === region) {
        result.push({ ...row, entity, join: "region", text: `Regional context, not this ${entity.kind}'s record: ${row.text}`, related: [ref("region", region)] });
      }
    }
  }
  return result;
}
