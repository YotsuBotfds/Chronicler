/** Linked saved observations. Identity joins never imply causation or allocate a regional total. */
import type { Bundle, TurnSnapshot } from "../types";
import { readRecoveryCrews } from "./recoveryCrews";
import { readTimberSupply } from "./timberSupply";
import { readHouseholdRetail, RETAIL_STATUSES } from "./householdRetail";
import { repairProjectsAt } from "./repairProjects";
import { residenceLedgerAt } from "./residenceLedger";
import { titledTradeAt } from "./titledTrade";
import { timberOrdersAt } from "./timberOrders";
import { warRequisitionAt } from "./warRequisition";

export type EntityKind = "person" | "project" | "expedition" | "shipment" | "timber_order" | "claim" | "army" | "region";
export interface EntityRef { kind: EntityKind; id: number | string }
export type HistoryState = "disabled" | "unknown" | "malformed" | "not_sampled" | "truncated" | "recorded_zero" | "recorded";
export interface EntityHistoryRow {
  entity: EntityRef; turn: number; sourceTurn: number | null; package: string;
  join: "id" | "region" | "inferred"; state: HistoryState; text: string;
  source: string | null; region: number | null; related: EntityRef[];
}
export const HISTORY_PACKAGES = ["recovery_crews", "repair_projects", "timber_supply", "household_retail", "titled_trade", "residence_ledger", "timber_orders", "war_requisition"] as const;
type Package = typeof HISTORY_PACKAGES[number];
interface Observation extends EntityHistoryRow { package: Package }
interface PackageFrame { state: HistoryState; reason: string; rows: Observation[]; source: string | null; sourceTurn: number | null }
interface SnapshotIndex { snapshot: TurnSnapshot; frames: Record<Package, PackageFrame> }
export interface EntityHistoryIndex { snapshots: SnapshotIndex[]; entities: EntityRef[] }
const livelihoods = (s: TurnSnapshot): unknown => (s as unknown as Record<string, unknown>).livelihoods;
const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
export const entityKey = (e: EntityRef) => `${e.kind}:${e.id}`;
export const entityLabel = (e: EntityRef) => `${e.kind[0].toUpperCase()}${e.kind.slice(1).replace(/_/g, " ")} #${e.id}`;
const ref = (kind: EntityKind, id: number | string): EntityRef => ({ kind, id });
const coins = (n: number) => (n / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
const num = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 3 });

/** Parse once per bundle, through the producers' strict readers. Does not read final-state histories. */
export function indexEntityHistory(bundle: Bundle): EntityHistoryIndex {
  const history = Array.isArray(bundle.history) ? bundle.history : [];
  const regions = bundle.world_state.regions.length, civs = bundle.world_state.civilizations.length;
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
      const add = (entity: EntityRef, path: string, text: string, region: number | null = null, related: EntityRef[] = [], state: HistoryState = "recorded", join: EntityHistoryRow["join"] = "id") => {
        frame.rows.push({ entity, turn: snapshot.turn, sourceTurn: frame.sourceTurn, package: key, join, state, text, source: source + path, region, related });
        for (const e of [entity, ...related]) entities.set(entityKey(e), e);
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
          `${e.status}, ${e.stage}; ${num(e.cut)} timber cut; ${num(e.delivered)} delivered`, e.home, e.crew.map((id) => ref("person", id))));
        if (r.record.receipts === null) { unknown(); continue; }
        r.record.receipts.forEach((r, j) => r.crew.forEach((id) => add(ref("person", id), `/receipts/${j}`,
          `Woodcutting expedition #${r.eid}, ${r.stage}; crew total ${coins(r.wages_milli)} coins (individual allocation unrecorded)`, r.home, [ref("expedition", r.eid)])));
      } else if (key === "household_retail") {
        const r = readHouseholdRetail(snapshot, regions);
        if (r.status !== "ok") { bad(); continue; }
        if (r.record.sample === null) { unknown(); continue; }
        r.record.sample.forEach((p, j) => add(ref("person", p[0]), `/sample/${j}`,
          `Food ration ${num(p[3])} of fair share ${num(p[4])}; ${RETAIL_STATUSES[p[5]]}. Who paid is not recorded`, p[1]));
        r.record.regions?.forEach((p, j) => add(ref("region", p.region), `/regions/${j}`,
          p.provisioning ? `Market total: ${p.provisioning.persons} people; ${coins(p.provisioning.paid_milli)} coins paid; ${p.provisioning.priced_out_persons} priced out`
            : "Market provisioning unknown, not zero", p.region, [], p.provisioning ? "recorded" : "unknown"));
        Object.assign(frame, { state: "not_sampled", reason: "Not in the bounded person sample; no evidence about this person's ration or purchases" });
      } else if (key === "titled_trade") {
        const r = titledTradeAt(snapshot, regions);
        if (r.status === "malformed" || !r.record) { bad(); continue; }
        for (const list of ["shipments", "closed"] as const) r.record[list].forEach((s, j) => {
          const ship = ref("shipment", s.id), holder = ref("person", s.holder);
          add(ship, `/${list}/${j}`, `${s.status}${s.outcome ? `: ${s.outcome}` : ""}; ${s.cargo.reduce((a, b) => a + b, 0) / 1000} food aboard`, s.origin, [holder]);
          add(holder, `/${list}/${j}`, `Holder of shipment #${s.id}; ${s.status}${s.outcome ? `: ${s.outcome}` : ""}; origin context only`, s.origin, [ship]);
        });
        if (!r.record.frame) { unknown(); continue; }
        r.record.frame.sales.forEach((s, j) => add(ref("person", s.holder), `/frame/sales/${j}`, `${coins(s.credited)} coins credited from retail sales; exact attribution to cargo: ${s.exact ? "yes" : "no"}`, s.region));
      } else if (key === "residence_ledger") {
        const r = residenceLedgerAt(snapshot, regions);
        if (!r) { bad(); continue; }
        if (r.events === null) { unknown(); continue; }
        if (r.events_dropped > 0) Object.assign(frame, { state: "truncated", reason: "Spell events were dropped; absence is not evidence of no event" });
        r.events.forEach((e, j) => add(ref("person", e.id), `/events/${j}`,
          `Displacement spell ${e.kind}; cause ${e.cause}, home anchor ${e.anchor}; ${e.length} turns. This event does not record every residence`, e.region));
      } else if (key === "timber_orders") {
        const r = timberOrdersAt(snapshot, regions, civs);
        if (r.status === "malformed" || !r.record) { bad(); continue; }
        for (const list of ["orders", "closed"] as const) r.record[list].forEach((o, j) => {
          const order = ref("timber_order", o.id), holder = ref("person", o.holder), where = o.path[o.cursor];
          const text = `${o.outcome ?? o.status}; ${num(o.cargo_milli / 1000)} timber aboard, ${num(o.delivered_milli / 1000)} delivered; escrow held ${coins(o.cash)}, actually credited ${coins(o.credited_milli)}, refunded ${coins(o.refunded_milli)} coins`;
          add(order, `/${list}/${j}`, text, where, [holder]);
          add(holder, `/${list}/${j}`, `Carrier/title of timber order #${o.id}: ${text}. Cargo position is not the person's residence`, where, [order]);
        });
        if (!r.record.frame) { unknown(); continue; }
        if (r.record.frame.events_dropped) Object.assign(frame, { state: "truncated", reason: "Timber order events were dropped; absence is unknown" });
      } else {
        const r = warRequisitionAt(snapshot, regions, civs);
        if (r.status === "malformed" || !r.record) { bad(); continue; }
        if (r.status === "disabled") { Object.assign(frame, { state: "disabled", reason: "Requisition is explicitly disabled" }); continue; }
        if (!r.record.frame) { unknown(); continue; }
        const f = r.record.frame;
        if (f.events_dropped || f.claims_dropped) Object.assign(frame, { state: "truncated", reason: "Events or liability rows are outside retention; absence is unknown" });
        f.claims.forEach((c, j) => {
          const claim = ref("claim", c.id), owner = ref("person", c.owner);
          const text = `Restitution claim #${c.id} (${c.source}, ${c.status}): original due ${coins(c.due_milli)}, actually paid ${coins(c.paid_milli)}, unpaid ${coins(c.due_milli - c.paid_milli)} coins. A liability is not spendable cash`;
          add(claim, `/frame/claims/${j}`, text, c.region, [owner]);
          add(owner, `/frame/claims/${j}`, text, c.region, [claim]);
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
      }
    }
    return { snapshot, frames };
  });
  return { snapshots, entities: [...entities.values()].sort((a, b) => a.kind.localeCompare(b.kind) || String(a.id).localeCompare(String(b.id), undefined, { numeric: true })) };
}

/** Selected entity's dated facts and explicitly separate regional context. No interpolation across gaps. */
export function entityHistory(index: EntityHistoryIndex, entity: EntityRef, throughTurn = Infinity): EntityHistoryRow[] {
  const result: EntityHistoryRow[] = [];
  for (const { snapshot, frames } of index.snapshots) {
    if (snapshot.turn > throughTurn) continue;
    const direct: EntityHistoryRow[] = [];
    for (const key of HISTORY_PACKAGES) {
      const frame = frames[key];
      const rows = frame.rows.filter((r) => entityKey(r.entity) === entityKey(entity));
      direct.push(...rows);
      if (!rows.length && entity.kind === "person") {
        const empty = frame.state === "recorded";
        direct.push({ entity, turn: snapshot.turn, sourceTurn: frame.sourceTurn, package: key, join: "id", state: empty ? "recorded_zero" : frame.state,
          text: empty ? key === "residence_ledger" ? "No spell event recorded for this id; residence and displacement status remain unknown" : "No named activity in this package's completed-turn frame" : frame.reason,
          source: frame.source, region: null, related: [] });
      }
    }
    result.push(...direct);
    if (entity.kind !== "region") {
      const regions = new Set(direct.flatMap((r) => r.region === null ? [] : [r.region]));
      for (const region of regions) for (const row of frames.household_retail.rows) if (row.entity.kind === "region" && row.entity.id === region) {
        result.push({ ...row, entity, join: "region", text: `Regional context, not this ${entity.kind}'s record: ${row.text}`, related: [ref("region", region)] });
      }
    }
  }
  return result;
}
