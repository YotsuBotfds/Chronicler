/**
 * The productive-recovery chain of one region over a run (PL5c): a community
 * needs timber (an RS2 project stalls), shifts labour to obtain it (a PL1
 * expedition from the region), repairs its granary (RS2, grain storage), pays
 * named workers (PL3 granary crews, RS2 workshop crews, PL1 woodcutters) and
 * its households buy food (PL4 household retail), with the tradeoffs beside
 * the links: farm labour away, forest pressure, budgets and people priced out.
 *
 * Every record is read with its own strict reader (``timberSupply``,
 * ``repairProjects``, ``recoveryCrews``, ``householdRetail``, ``timberStock``,
 * ``granaries``, ``remittances``, ``foodAllocation``); this module only selects
 * a region's rows from what those readers accept. Each cell is one of:
 *
 * - ``off``: the package is not recorded anywhere in the run (switched off);
 * - ``unknown``: the package is on, but this snapshot does not say (no record
 *   here, a null frame, or a frame too short to be complete);
 * - ``malformed``: the package's reader refused this snapshot's record;
 * - ``known``: the record says; an empty value is "on, nothing happened".
 *
 * Missing data is unknown, never zero. Each link states whether the records
 * join it to the chain by stable id or only by region (``LINKS``); see
 * docs/integration/recovery-chain-view.md.
 */
import { isRecord as object } from "./recordGuards";
import type { Bundle, GrainStorageSnapshot, TurnSnapshot } from "../types";
import { foodAllocationAt, type FoodAllocationRecord } from "./foodAllocation";
import { granaryStorageAt } from "./granaries";
import {
  readHouseholdRetail, RETAIL_STATUSES, type HouseholdRetailRecord, type RetailRegionFrame,
} from "./householdRetail";
import { readRecoveryCrews, type CrewReceiptRecord, type RecoveryCrewsRecord } from "./recoveryCrews";
import { remittancesAt, type DiasporaRegionRecord, type RemittancesRecord } from "./remittances";
import {
  repairProjectsAt, type RepairProjectRecord, type RepairProjectsRecord, type RepairReceiptRecord, type UnmetNeedRecord,
} from "./repairProjects";
import { timberStockAt, type TimberStockRecord, type TimberStockRow } from "./timberStock";
import {
  readTimberSupply, type ExpeditionReceiptRecord, type ExpeditionRecord, type TimberNeedRecord, type TimberStoreRecord,
  type TimberSupplyRecord,
} from "./timberSupply";

// ---------------------------------------------------------------- cells and packages

export type Cell<T> =
  | { state: "off"; reason: string }
  | { state: "unknown"; reason: string }
  | { state: "malformed"; reason: string }
  | { state: "known"; value: T };

/** The records the chain reads, in the chain's order. */
export const CHAIN_PACKAGES = ["repair_projects", "timber_supply", "timber_stock", "grain_storage", "recovery_crews",
  "household_retail", "remittances", "food_allocation"] as const;
export type ChainPackage = typeof CHAIN_PACKAGES[number];

export const PACKAGE_INFO: Record<ChainPackage, { label: string; flag: string }> = {
  repair_projects: { label: "Repair projects (RS2)", flag: "--repair-projects" },
  timber_supply: { label: "Timber supply (PL1)", flag: "--timber-supply" },
  timber_stock: { label: "Timber stock (L3)", flag: "--timber-stock" },
  grain_storage: { label: "Granary storage", flag: "--grain-storage" },
  recovery_crews: { label: "Recovery crews (PL3)", flag: "--recovery-crews" },
  household_retail: { label: "Household retail (PL4)", flag: "--household-retail" },
  remittances: { label: "Remittances (RS4)", flag: "--remittances" },
  food_allocation: { label: "Food allocation (L2)", flag: "--food-allocation" },
};

/** The packages whose presence makes the chain view worth mounting. */
const ANCHOR_PACKAGES: readonly ChainPackage[] = ["repair_projects", "timber_supply", "recovery_crews", "household_retail"];

type Records = {
  repair_projects: RepairProjectsRecord; timber_supply: TimberSupplyRecord; timber_stock: TimberStockRecord;
  grain_storage: GrainStorageSnapshot; recovery_crews: RecoveryCrewsRecord; household_retail: HouseholdRetailRecord;
  remittances: RemittancesRecord; food_allocation: FoodAllocationRecord;
};


/** Whether a snapshot carries a package's record at all (a presence test; the readers parse). */
export function carries(snapshot: TurnSnapshot, key: ChainPackage): boolean {
  if (key === "grain_storage") return snapshot.grain_reserves?.storage != null;
  const livelihoods = (snapshot as unknown as Record<string, unknown>).livelihoods;
  return object(livelihoods) && livelihoods[key] !== undefined && livelihoods[key] !== null;
}

/** The packages recorded anywhere in the run (on); the rest are off. */
export function packagesOn(history: readonly TurnSnapshot[]): Record<ChainPackage, boolean> {
  const on = Object.fromEntries(CHAIN_PACKAGES.map((k) => [k, false])) as Record<ChainPackage, boolean>;
  for (const snapshot of history) for (const k of CHAIN_PACKAGES) if (!on[k] && carries(snapshot, k)) on[k] = true;
  return on;
}

/** True when the run records at least one of the chain's anchor packages. */
export function hasRecoveryChain(bundle: Bundle | null | undefined): boolean {
  const history = Array.isArray(bundle?.history) ? bundle!.history : [];
  return history.some((s) => ANCHOR_PACKAGES.some((k) => carries(s, k)));
}

const OFF = (key: ChainPackage): { state: "off"; reason: string } =>
  ({ state: "off", reason: `${PACKAGE_INFO[key].label} is off in this run (${PACKAGE_INFO[key].flag} not recorded)` });

/** One package at one snapshot, read by its own reader. */
function readPackage<K extends ChainPackage>(snapshot: TurnSnapshot, key: K, on: boolean, regions: number,
  civs: number): Cell<Records[K]> {
  if (!on) return OFF(key);
  if (key === "grain_storage") {
    if (!carries(snapshot, key)) return { state: "unknown", reason: "no granary storage record at this snapshot" };
    const frame = granaryStorageAt(snapshot, regions, civs);
    return frame ? { state: "known", value: frame as Records[K] }
      : { state: "malformed", reason: "the granary storage record was rejected by its reader" };
  }
  const livelihoods = (snapshot as unknown as Record<string, unknown>).livelihoods;
  if (livelihoods === undefined || livelihoods === null) return { state: "unknown", reason: "no livelihoods record at this snapshot" };
  if (!object(livelihoods) || livelihoods.schema_version !== 1)
    return { state: "malformed", reason: "the livelihoods record is unreadable (malformed or of an unknown version)" };
  if (!carries(snapshot, key)) return { state: "unknown", reason: `no ${PACKAGE_INFO[key].label} record at this snapshot` };
  const ok = (value: unknown): Cell<Records[K]> => ({ state: "known", value: value as Records[K] });
  const refused = (why: string): Cell<Records[K]> => ({ state: "malformed", reason: `the ${PACKAGE_INFO[key].label} record was rejected: ${why}` });
  switch (key) {
    case "timber_supply": {
      const r = readTimberSupply(snapshot, regions, civs);
      return r.status === "ok" ? ok(r.record) : refused(r.status === "malformed" ? r.reason : "absent");
    }
    case "recovery_crews": {
      const r = readRecoveryCrews(snapshot, regions, civs);
      return r.status === "ok" ? ok(r.record) : refused(r.status === "malformed" ? r.reason : "absent");
    }
    case "household_retail": {
      const r = readHouseholdRetail(snapshot, regions);
      return r.status === "ok" ? ok(r.record) : refused(r.status === "malformed" ? r.reason : "absent");
    }
    case "repair_projects": {
      const r = repairProjectsAt(snapshot, regions, civs);
      return r ? ok(r) : refused("malformed, misdated or of another schema");
    }
    case "timber_stock": {
      const r = timberStockAt(snapshot, regions);
      return r ? ok(r) : refused("malformed, misdated or of another schema");
    }
    case "remittances": {
      const r = remittancesAt(snapshot, regions);
      return r ? ok(r) : refused("malformed, misdated or of another schema");
    }
    default: {
      const r = foodAllocationAt(snapshot, regions);
      return r ? ok(r) : refused("malformed, misdated or of another schema");
    }
  }
}

/** Every chain package at one snapshot, for all regions at once. */
export interface ChainSnapshot {
  turn: number;
  packages: { [K in ChainPackage]: Cell<Records[K]> };
}

export function readChainSnapshots(bundle: Bundle): { on: Record<ChainPackage, boolean>; snapshots: ChainSnapshot[] } {
  const history = Array.isArray(bundle.history) ? bundle.history : [];
  const regions = bundle.world_state.regions?.length ?? 0;
  const civs = bundle.world_state.civilizations?.length ?? 0;
  const on = packagesOn(history);
  const snapshots = history.map((snapshot) => ({
    turn: snapshot.turn,
    packages: Object.fromEntries(CHAIN_PACKAGES.map((k) => [k, readPackage(snapshot, k, on[k], regions, civs)])) as
      ChainSnapshot["packages"],
  }));
  return { on, snapshots };
}

// ---------------------------------------------------------------- links

export type LinkKey = "repair" | "expedition" | "forest" | "store" | "granary" | "wages" | "retail" | "remittances";
export type JoinBy = "id" | "region";

/** The chain's links, in order, and how the records join each to the chain. */
export const LINKS: ReadonlyArray<{ key: LinkKey; title: string; packages: ChainPackage[]; join: JoinBy; joined: string }> = [
  { key: "repair", title: "Repair need (RS2)", packages: ["repair_projects"], join: "id",
    joined: "by id: the project's id names its asset, region and this turn's stall reasons" },
  { key: "expedition", title: "Woodcutting expedition (PL1)", packages: ["timber_supply"], join: "region",
    joined: "by region only: PL1 plans one timber need per region, summed over its open projects; the expedition, its need row and its crew are by id" },
  { key: "forest", title: "Forest stock (L3)", packages: ["timber_supply", "timber_stock"], join: "id",
    joined: "by id: the expedition's receipt names the forest region and slot of the L3 account; that account's extraction can include other cutting" },
  { key: "store", title: "Timber store to repair", packages: ["timber_supply", "repair_projects"], join: "region",
    joined: "by region only: the store is per region and a project's receipt does not say how much of its timber came from it" },
  { key: "granary", title: "Granary condition", packages: ["grain_storage", "repair_projects"], join: "id",
    joined: "by id: a granary project's asset is the granary's region index" },
  { key: "wages", title: "Wages paid (PL3, RS2, PL1)", packages: ["recovery_crews", "repair_projects", "timber_supply"], join: "id",
    joined: "by id: each receipt names its project or expedition and the workers' stable ids; wages are placed in the project's region or the expedition's home region" },
  { key: "retail", title: "Food purchases (PL4)", packages: ["household_retail"], join: "region",
    joined: "by region only: the snapshot sums purchases to region totals; by id only the 24-person sample's ration and status survive, not who paid" },
  { key: "remittances", title: "Remittances in (RS4)", packages: ["remittances"], join: "region",
    joined: "by region only: the region's inflow total" },
];

export interface ProjectView extends Pick<RepairProjectRecord, "pid" | "kind" | "asset" | "cause" | "status" | "scope"
  | "delivered" | "opened_turn" | "closed_turn" | "closed_reason" | "opened_condition"> {
  /** Closed in the source turn (listed among ``closed``). */
  closedNow: boolean;
}

export interface RepairValue {
  mode: RepairProjectsRecord["mode"];
  /** Open projects in the region and those closed in the source turn. */
  projects: ProjectView[];
  /** The region's receipts this turn; null: this turn's Phase 2 is unknown, not zero. */
  receipts: RepairReceiptRecord[] | null;
  unmet: UnmetNeedRecord[] | null;
}

export interface ExpeditionValue {
  mode: TimberSupplyRecord["mode"];
  /** The region's need row; "none": the frame lists no need for the region; null: the frame is unknown. */
  need: TimberNeedRecord | "none" | null;
  /** Live expeditions from the region and those that ended in the source turn. */
  expeditions: ExpeditionRecord[];
  /** This turn's receipts of the region's expeditions; null: unknown, not zero. */
  receipts: ExpeditionReceiptRecord[] | null;
  /** Timber delivered home in the source turn (expeditions that ended delivering). */
  delivered: number;
}

export interface ForestSlot {
  eid: number; forest: number; slot: number; cut: number;
  stockBefore: number | null; stockAfter: number | null; capacity: number | null;
  /** The slot's L3 row; null: the L3 frame is unknown or the slot is not listed. */
  l3: TimberStockRow | null;
}

export interface ForestValue {
  /** The forest slots the region's expeditions cut this turn; null: the expedition receipts are unknown. */
  slots: ForestSlot[] | null;
  /** Why the L3 frame of this snapshot is not known; null when it is. */
  l3Missing: string | null;
}

export interface StoreValue {
  /** The region's store row; "none": no store in the region; null: the frame is unknown. */
  store: TimberStoreRecord | "none" | null;
  /** The region's projects holding timber this turn; null: unknown. */
  holders: Array<{ pid: number; held: number; used: number }> | null;
}

export interface GranaryValue {
  /** The region's granary asset; "none": the region has no granary; null: unknown. */
  asset: { condition: number; capacity: number; owner: number } | "none" | null;
  /** The region's open or just-closed granary project (RS2); null: none; "off": RS2 off; "unknown": RS2 unreadable here. */
  project: ProjectView | null | "off" | "unknown";
  /** This turn's RS2 receipt of that project; null: none or unknown (see ``receiptKnown``). */
  receipt: RepairReceiptRecord | null;
  receiptKnown: boolean;
}

export type WageSource = "pl3_granary" | "rs2_workshop" | "pl1_woodcut";
export interface WageRow {
  source: WageSource;
  /** The RS2 project (PL3, RS2) or the PL1 expedition. */
  pid: number | null; eid: number | null;
  people: number[];
  /** The people the records show were paid, by id: a PL3 member whose own wage is above zero; an RS2 or PL1 crew
   * when its receipt paid wages and the ceiling refused none (with a refusal, who went unpaid is not recorded). */
  paid: number[];
  wagesMilli: number;
  /** Wages the wealth ceiling refused (sunk). */
  refusedMilli: number;
  /** Farm labour taken from farming for the work (farmer-turns); null where the receipt does not say. */
  farmTime: number | null;
  /** PL3 unpaid control, or a PL1 turn the treasury could not pay. */
  unpaid: boolean;
}

/** A PL3 workshop crew: its wages are on the RS2 receipt, but the farm time it took is PL3's. */
export interface WorkshopCrew { pid: number; people: number[]; farmTime: number }

export interface WagesValue {
  pl3: Cell<{ rows: WageRow[]; mode: RecoveryCrewsRecord["mode"]; truncated: boolean;
    /** Granary projects of the region whose crew had nobody this turn, with the work planned for them. */
    noCrew: Array<{ pid: number; planned: number }>;
    workshops: WorkshopCrew[] }>;
  rs2: Cell<{ rows: WageRow[] }>;
  pl1: Cell<{ rows: WageRow[] }>;
}

export interface SampleMatch {
  agentId: number; household: number;
  /** "self": the paid worker; "household": a member of the household keyed by the worker's id. */
  who: "self" | "household";
  worker: number; ration: number; fairShare: number; status: string;
  /** The snapshot the worker was first paid in the region (this one or earlier). */
  since: number;
}

export interface RetailValue {
  mode: HouseholdRetailRecord["mode"]; boundary: HouseholdRetailRecord["boundary"];
  /** The region's pilot frame; null: the region is not a pilot region this turn. */
  frame: RetailRegionFrame | null;
  /** Sample rows in the region whose person, or household key, was paid in the region at this or an earlier
   * snapshot (a turn's Phase 2 wages are paid before that turn's provisioning). */
  matches: SampleMatch[];
  /** Sample rows in the region this turn. */
  sampled: number;
}

export interface FoodValue {
  source: "household_retail" | "food_allocation";
  /** Food sufficiency of the region this turn; null: not observed. */
  sufficiency: number | null;
  /** Food allocation's shortfall in rations (L2 scarce regions); null where it does not apply. */
  shortfall: number | null;
  scarce: boolean;
}

export interface ChainTurn {
  turn: number;
  repair: Cell<RepairValue>;
  expedition: Cell<ExpeditionValue>;
  forest: Cell<ForestValue>;
  store: Cell<StoreValue>;
  granary: Cell<GranaryValue>;
  wages: Cell<WagesValue>;
  retail: Cell<RetailValue>;
  remittances: Cell<{ mode: RemittancesRecord["mode"]; row: DiasporaRegionRecord | null }>;
  /** The region's food this turn (the expedition's home region): the farm-labour tradeoff's context. */
  food: Cell<FoodValue>;
}

type NotKnown = Exclude<Cell<never>, { state: "known" }>;
const pass = (cell: Cell<unknown>): NotKnown => cell as NotKnown;
const unknown = (reason: string): NotKnown => ({ state: "unknown", reason });

function project(p: RepairProjectRecord, source: number): ProjectView {
  return { pid: p.pid, kind: p.kind, asset: p.asset, cause: p.cause, status: p.status, scope: p.scope, delivered: p.delivered,
    opened_turn: p.opened_turn, closed_turn: p.closed_turn, closed_reason: p.closed_reason, opened_condition: p.opened_condition,
    closedNow: p.status !== "open" && p.closed_turn === source };
}

function repairLink(cell: Cell<RepairProjectsRecord>, region: number): Cell<RepairValue> {
  if (cell.state !== "known") return pass(cell);
  const x = cell.value;
  const projects = [...x.projects.filter((p) => p.region === region),
    ...x.closed.filter((p) => p.region === region && p.closed_turn === x.source_turn)].map((p) => project(p, x.source_turn));
  return { state: "known", value: { mode: x.mode, projects,
    receipts: x.receipts === null ? null : x.receipts.filter((r) => r.region === region),
    unmet: x.unmet === null ? null : x.unmet.filter((u) => u.region === region) } };
}

function expeditionLink(cell: Cell<TimberSupplyRecord>, region: number): Cell<ExpeditionValue> {
  if (cell.state !== "known") return pass(cell);
  const x = cell.value;
  const ended = x.closed.filter((e) => e.home === region && e.ended_turn === x.source_turn);
  const need = x.needs === null ? null : x.needs.find((n) => n.region === region)
    // A frame that dropped rows cannot say the region had no need.
    ?? (x.needs_dropped ? null : "none");
  return { state: "known", value: { mode: x.mode, need,
    expeditions: [...x.expeditions.filter((e) => e.home === region), ...ended],
    receipts: x.receipts === null ? null : x.receipts.filter((r) => r.home === region),
    delivered: ended.filter((e) => e.status === "delivered").reduce((a, e) => a + e.delivered, 0) } };
}

function forestLink(timber: Cell<TimberSupplyRecord>, stock: Cell<TimberStockRecord>, region: number): Cell<ForestValue> {
  if (timber.state === "off") return pass(timber);
  if (stock.state === "off") return pass(stock);
  if (timber.state !== "known") return pass(timber);
  const x = timber.value;
  const l3 = stock.state === "known" && stock.value.observed ? stock.value.regions : null;
  const l3Missing = l3 !== null ? null : stock.state === "known" ? "no L3 account was settled in the source turn"
    : (stock as NotKnown).reason;
  if (x.receipts === null) return { state: "known", value: { slots: null, l3Missing } };
  const slots = x.receipts.filter((r) => r.home === region && r.stage === "cutting").map((r): ForestSlot => ({
    eid: r.eid, forest: r.forest, slot: r.slot, cut: r.cut, stockBefore: r.stock_before, stockAfter: r.stock_after,
    capacity: r.capacity, l3: l3?.find((row) => row.region_id === r.forest && row.slot === r.slot) ?? null }));
  return { state: "known", value: { slots, l3Missing } };
}

function storeLink(timber: Cell<TimberSupplyRecord>, repair: Cell<RepairProjectsRecord>, region: number): Cell<StoreValue> {
  if (timber.state !== "known") return pass(timber);
  const x = timber.value;
  const store = x.stores === null ? null : x.stores.find((s) => s.region === region) ?? "none";
  const holders = repair.state !== "known" || repair.value.receipts === null ? null
    : repair.value.receipts.filter((r) => r.region === region && r.timber_held > 0)
      .map((r) => ({ pid: r.pid, held: r.timber_held, used: r.timber_used }));
  return { state: "known", value: { store, holders } };
}

function granaryLink(storage: Cell<GrainStorageSnapshot>, repair: Cell<RepairProjectsRecord>, region: number): Cell<GranaryValue> {
  // Without granary storage there is no granary asset, so RS2 opens no granary project either.
  if (storage.state === "off" || storage.state === "malformed") return pass(storage);
  const assets = storage.state === "known" ? storage.value.assets : null;
  const row = assets ? assets[region] : undefined;
  const asset = assets === null ? null : row ? { condition: row.condition, capacity: row.capacity, owner: row.owner } : "none" as const;
  if (repair.state === "off") return { state: "known", value: { asset, project: "off", receipt: null, receiptKnown: false } };
  if (repair.state !== "known") {
    return assets === null ? pass(repair)
      : { state: "known", value: { asset, project: "unknown", receipt: null, receiptKnown: false } };
  }
  const x = repair.value;
  const p = [...x.projects, ...x.closed.filter((c) => c.closed_turn === x.source_turn)]
    .find((q) => q.kind === "granary" && q.asset === region) ?? null;
  const receipt = p && x.receipts ? x.receipts.find((r) => r.pid === p.pid) ?? null : null;
  return { state: "known", value: { asset, project: p ? project(p, x.source_turn) : null, receipt,
    receiptKnown: x.receipts !== null } };
}

function crewRows(r: CrewReceiptRecord, mode: RecoveryCrewsRecord["mode"]): WageRow {
  return { source: "pl3_granary", pid: r.pid, eid: null, people: r.members.map((m) => m.agent_id),
    paid: r.members.filter((m) => m.wage_milli > 0).map((m) => m.agent_id), wagesMilli: r.wages_milli,
    refusedMilli: r.wage_residual_milli, farmTime: r.farm_time_removed, unpaid: mode === "unpaid" };
}

/** An RS2 or PL1 receipt names its crew and one total: the crew counts as paid only when nothing was refused. */
const crewPaid = (crew: number[], wages: number, refused: number) => wages > 0 && refused === 0 ? [...crew] : [];

function wagesLink(crews: Cell<RecoveryCrewsRecord>, repair: Cell<RepairProjectsRecord>, timber: Cell<TimberSupplyRecord>,
  region: number): Cell<WagesValue> {
  if (crews.state === "off" && repair.state === "off" && timber.state === "off") return pass(crews);
  const pl3: WagesValue["pl3"] = crews.state !== "known" ? pass(crews) : crews.value.receipts === null
    ? unknown("no repair Phase 2 was settled in the source turn: this turn's crews are unknown, not zero")
    : { state: "known", value: {
      // Granary crews with somebody on them: a workshop crew's wages are on its RS2 receipt (PL3 records them as
      // zero), and a granary receipt with no member formed no crew.
      rows: crews.value.receipts.filter((r) => r.region === region && r.kind === "granary" && r.members.length > 0)
        .map((r) => crewRows(r, crews.value.mode)),
      noCrew: crews.value.receipts.filter((r) => r.region === region && r.kind === "granary" && r.members.length === 0)
        .map((r) => ({ pid: r.pid, planned: r.planned })),
      workshops: crews.value.receipts.filter((r) => r.region === region && r.kind === "workshop" && r.members.length > 0)
        .map((r) => ({ pid: r.pid, people: r.members.map((m) => m.agent_id), farmTime: r.farm_time_removed })),
      mode: crews.value.mode,
      truncated: crews.value.receipts.length >= (crews.value.parameters.max_frame_rows ?? 64) } };
  const rs2: WagesValue["rs2"] = repair.state !== "known" ? pass(repair) : repair.value.receipts === null
    ? unknown("no repair Phase 2 was settled in the source turn: this turn's workshop crews are unknown, not zero")
    : { state: "known", value: { rows: repair.value.receipts.filter((r) => r.region === region && r.kind === "workshop"
      && (r.crew.length > 0 || r.wages_due_milli > 0)).map((r): WageRow => ({ source: "rs2_workshop", pid: r.pid, eid: null,
      people: [...r.crew], paid: crewPaid(r.crew, r.wages_milli, r.wage_residual_milli), wagesMilli: r.wages_milli,
      refusedMilli: r.wage_residual_milli, farmTime: null, unpaid: false })) } };
  const pl1: WagesValue["pl1"] = timber.state !== "known" ? pass(timber) : timber.value.receipts === null
    ? unknown("no expedition Phase 2 in the source turn: this turn's woodcutters are unknown, not zero")
    : { state: "known", value: { rows: timber.value.receipts.filter((r) => r.home === region).map((r): WageRow => ({
      source: "pl1_woodcut", pid: null, eid: r.eid, people: [...r.crew], paid: crewPaid(r.crew, r.wages_milli, r.wage_residual_milli),
      wagesMilli: r.wages_milli, refusedMilli: r.wage_residual_milli, farmTime: r.away_delivered, unpaid: r.unpaid })) } };
  return { state: "known", value: { pl3, rs2, pl1 } };
}

function retailLink(cell: Cell<HouseholdRetailRecord>, region: number, paidSince: ReadonlyMap<number, number>): Cell<RetailValue> {
  if (cell.state !== "known") return pass(cell);
  const x = cell.value;
  if (x.regions === null || x.sample === null)
    return unknown("the household retail frame of the source turn was not recorded: purchases are unknown, not zero");
  const frame = x.regions.find((r) => r.region === region) ?? null;
  const rows = x.sample.filter((s) => s[1] === region);
  const matches: SampleMatch[] = [];
  for (const [agentId, , household, ration, fairShare, status] of rows) {
    const base = { agentId, household, ration, fairShare, status: RETAIL_STATUSES[status] ?? String(status) };
    if (paidSince.has(agentId)) matches.push({ ...base, who: "self", worker: agentId, since: paidSince.get(agentId)! });
    else if (household !== agentId && paidSince.has(household))
      matches.push({ ...base, who: "household", worker: household, since: paidSince.get(household)! });
  }
  return { state: "known", value: { mode: x.mode, boundary: x.boundary, frame, matches, sampled: rows.length } };
}

function remittanceLink(cell: Cell<RemittancesRecord>, region: number): ChainTurn["remittances"] {
  if (cell.state !== "known") return pass(cell);
  const x = cell.value;
  if (x.regions === null) return unknown("no remittance turn completed in the source turn: inflows are unknown, not zero");
  // The frame lists every region the turn's ledger touched (its rows sum to the turn's totals).
  return { state: "known", value: { mode: x.mode, row: x.regions.find((r) => r.region === region) ?? null } };
}

function foodLink(retail: Cell<HouseholdRetailRecord>, food: Cell<FoodAllocationRecord>, region: number): Cell<FoodValue> {
  // A retail-provisioned region is closed by retail's own receipt, not food allocation's.
  if (retail.state === "known" && retail.value.regions !== null) {
    const p = retail.value.regions.find((r) => r.region === region)?.provisioning;
    if (p) return { state: "known", value: { source: "household_retail", sufficiency: p.sufficiency, shortfall: null,
      scarce: p.sufficiency < 1 } };
  }
  if (food.state !== "known") return pass(food);
  if (food.value.regions === null) return unknown("no food allocation ran in the source turn");
  if (retail.state !== "off" && (retail.state !== "known" || retail.value.regions === null))
    return unknown("household retail's frame is unknown, so whether retail provisioned the region is unknown");
  const row = food.value.regions.find((r) => r.region === region);
  return { state: "known", value: row ? { source: "food_allocation", sufficiency: row.sufficiency, shortfall: row.shortfall, scarce: true }
    : { source: "food_allocation", sufficiency: null, shortfall: null, scarce: false } };
}

/** Workers the records show were paid in the region this turn, by stable id (``WageRow.paid``). */
export function paidWorkers(wages: Cell<WagesValue>): number[] {
  if (wages.state !== "known") return [];
  const out = new Set<number>();
  for (const sub of [wages.value.pl3, wages.value.rs2, wages.value.pl1]) {
    if (sub.state !== "known") continue;
    for (const row of sub.value.rows) row.paid.forEach((p) => out.add(p));
  }
  return [...out];
}

/** One region's chain at every snapshot of the run, oldest first. */
export function regionChain(snapshots: readonly ChainSnapshot[], region: number): ChainTurn[] {
  const paid = new Map<number, number>();
  return snapshots.map((s) => {
    const p = s.packages;
    const wages = wagesLink(p.recovery_crews, p.repair_projects, p.timber_supply, region);
    // A turn's Phase 2 wages are paid before that turn's provisioning, so this snapshot's wages count.
    for (const id of paidWorkers(wages)) if (!paid.has(id)) paid.set(id, s.turn);
    const turn: ChainTurn = {
      turn: s.turn,
      repair: repairLink(p.repair_projects, region),
      expedition: expeditionLink(p.timber_supply, region),
      forest: forestLink(p.timber_supply, p.timber_stock, region),
      store: storeLink(p.timber_supply, p.repair_projects, region),
      granary: granaryLink(p.grain_storage, p.repair_projects, region),
      wages,
      retail: retailLink(p.household_retail, region, paid),
      remittances: remittanceLink(p.remittances, region),
      food: foodLink(p.household_retail, p.food_allocation, region),
    };
    return turn;
  });
}

// ---------------------------------------------------------------- summaries the view shows

/** A link's state at one snapshot: off, unknown (or refused), nothing happened, something happened, or a tradeoff. */
export type LinkState = "off" | "unknown" | "none" | "active" | "tradeoff";

const has = <T,>(cell: Cell<T>): T | null => cell.state === "known" ? cell.value : null;

export function linkState(t: ChainTurn, key: LinkKey): LinkState {
  const cell = t[key] as Cell<unknown>;
  if (cell.state === "off") return "off";
  if (cell.state !== "known") return "unknown";
  switch (key) {
    case "repair": {
      const v = has(t.repair)!;
      if (v.receipts?.some((r) => r.status === "stalled")) return "tradeoff";
      // Open projects are listed every turn; with this turn's receipts unknown, whether they stalled is unknown.
      return v.projects.length ? (v.receipts === null ? "unknown" : "active") : "none";
    }
    case "expedition": {
      const v = has(t.expedition)!;
      if (v.need !== null && v.need !== "none" && v.need.status === "refused") return "tradeoff";
      if (v.expeditions.length || (v.need !== null && v.need !== "none" && v.need.status === "launched")) return "active";
      return v.need === null ? "unknown" : "none";
    }
    case "forest": {
      const v = has(t.forest)!;
      if (v.slots === null) return "unknown";
      if (!v.slots.length) return "none";
      return v.slots.some((s) => s.stockBefore !== null && s.stockAfter !== null && s.stockAfter < s.stockBefore) ? "tradeoff" : "active";
    }
    case "store": {
      const v = has(t.store)!;
      if (v.store === null) return "unknown";
      return v.store === "none" ? "none" : "active";
    }
    case "granary": {
      const v = has(t.granary)!;
      if (v.project === "unknown") return "unknown";
      if (v.project !== null && v.project !== "off") return "active";
      return v.asset === null ? "unknown" : "none";
    }
    case "wages": {
      const v = has(t.wages)!;
      const subs = [v.pl3, v.rs2, v.pl1];
      if (subs.some((c) => c.state === "known" && c.value.rows.length)) return "active";
      return subs.some((c) => c.state === "unknown" || c.state === "malformed") ? "unknown" : "none";
    }
    case "retail": {
      const v = has(t.retail)!;
      if (v.frame === null) return "none";
      // The record-only control provisions no one by design; elsewhere an unprovisioned pilot is not observed.
      if (v.frame.provisioning === null) return v.mode === "record_only" ? "active" : "unknown";
      return v.frame.provisioning.priced_out_persons > 0 ? "tradeoff" : "active";
    }
    default: {
      const v = has(t.remittances)!;
      return v.row && v.row.inflow_milli > 0 ? "active" : "none";
    }
  }
}

/** Whether a link recorded something but not all of it is known (a wage source unknown, the expeditions' receipts,
 * a forest account or the store's holders unknown): run totals then count that snapshot as unknown too. */
export function incomplete(t: ChainTurn, key: LinkKey): boolean {
  if (key === "expedition") {
    const v = has(t.expedition);
    return !!v && v.receipts === null && v.expeditions.length > 0;
  }
  if (key === "wages") {
    const w = has(t.wages);
    return !!w && [w.pl3, w.rs2, w.pl1].some((c) => c.state === "unknown" || c.state === "malformed"
      || (c.state === "known" && "truncated" in c.value && c.value.truncated));
  }
  if (key === "forest") return !!has(t.forest)?.slots?.some((s) => s.l3 === null);
  if (key === "store") {
    const v = has(t.store);
    return !!v && v.store !== null && v.store !== "none" && v.holders === null;
  }
  return false;
}

/** Farm labour taken from the region this turn, in farmer-turns, by source: PL1 woodcutters away, PL3 granary
 * crews and PL3 workshop crews. "off": the source is off in the run; null: unknown at this snapshot. */
export interface FarmAway { pl1: number | "off" | null; granary: number | "off" | null; workshop: number | "off" | null }

export function farmLabourAway(t: ChainTurn): FarmAway {
  const w = has(t.wages);
  if (!w) return t.wages.state === "off" ? { pl1: "off", granary: "off", workshop: "off" } : { pl1: null, granary: null, workshop: null };
  const of = <T,>(c: Cell<T>, f: (v: T) => number) => c.state === "off" ? "off" as const : c.state === "known" ? f(c.value) : null;
  return {
    pl1: of(w.pl1, (v) => v.rows.reduce((a, r) => a + (r.farmTime ?? 0), 0)),
    granary: of(w.pl3, (v) => v.rows.reduce((a, r) => a + (r.farmTime ?? 0), 0)),
    workshop: of(w.pl3, (v) => v.workshops.reduce((a, c) => a + c.farmTime, 0)),
  };
}

/** Budget limits recorded this turn, by link: RS2 stalls or limits for coins or the envelope, a PL1 refusal for
 * coins, PL1 recalls and unpaid turns, and wages the wealth ceiling refused. */
export function budgetLimits(t: ChainTurn): Array<{ link: "repair" | "expedition" | "wages"; text: string }> {
  const out: Array<{ link: "repair" | "expedition" | "wages"; text: string }> = [];
  for (const r of has(t.repair)?.receipts ?? []) {
    for (const reason of r.reasons) if (reason === "no_coins" || reason === "no_envelope") out.push({ link: "repair",
      text: `project #${r.pid} ${r.status === "stalled" ? "stalled" : "limited"}: ${reason === "no_coins" ? "treasury short" : "no repairs envelope"}` });
  }
  const exp = has(t.expedition);
  if (exp && exp.need !== null && exp.need !== "none" && exp.need.status === "refused" && exp.need.reason === "no_coins")
    out.push({ link: "expedition", text: "no expedition: the treasury cannot pay one" });
  for (const r of exp?.receipts ?? []) {
    if (r.recalled) out.push({ link: "expedition", text: `expedition #${r.eid} recalled: the treasury could not pay` });
    else if (r.unpaid) out.push({ link: "expedition", text: `expedition #${r.eid} unpaid this turn` });
  }
  const w = has(t.wages);
  const refused = w ? [w.pl3, w.rs2, w.pl1].flatMap((c) => c.state === "known" ? c.value.rows : [])
    .reduce((a, r) => a + r.refusedMilli, 0) : 0;
  if (refused > 0) out.push({ link: "wages",
    text: `${(refused / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 })} coins of wages refused by the wealth ceiling` });
  return out;
}

/**
 * The region whose chain goes furthest, to show first: the most of the chain's steps recorded at some snapshot
 * (an RS2 stall for want of timber, timber delivered home by an expedition, the store holding timber for a repair,
 * wages paid, food bought), then the most timber delivered, then the most link-snapshots recorded; lowest index on ties.
 */
export function fullestChainRegion(snapshots: readonly ChainSnapshot[], regionCount: number): number {
  let best = 0;
  let score: number[] = [-1, -1, -1];
  for (let r = 0; r < regionCount; r += 1) {
    const turns = regionChain(snapshots, r);
    const t = chainTotals(turns);
    const held = turns.some((x) => { const s = has(x.store)?.store; return !!s && s !== "none" && s.held > 0; });
    const steps = [t.stallsNoTimber > 0, t.delivered > 0, held, t.paidPeople > 0, t.purchasesMilli > 0].filter(Boolean).length;
    const activity = turns.reduce((a, x) => a + LINKS.filter((l) => ["active", "tradeoff"].includes(linkState(x, l.key))).length, 0);
    const s = [steps, t.delivered, activity];
    if (s[0] > score[0] || (s[0] === score[0] && (s[1] > score[1] || (s[1] === score[1] && s[2] > score[2])))) { best = r; score = s; }
  }
  return best;
}

/** The turn table's pager: the rows not yet shown, a page at a time. */
export function moreRowsLabel(remaining: number, page: number): string {
  return remaining <= page ? `Show the last ${remaining}` : `Show ${page} more (${remaining} not shown)`;
}

/** Run totals for a region, over known snapshots only; ``unknown`` counts the snapshots that could not be read,
 * wholly or in part. */
export interface ChainTotals {
  snapshots: number;
  stalls: number; stallsNoTimber: number;
  expeditions: number[]; delivered: number;
  /** Snapshots where the timber-supply record itself is unknown or refused (deliveries unknown). */
  deliveredUnknown: number;
  wagesMilli: { pl3: number; rs2: number; pl1: number };
  paidPeople: number;
  /** Farm labour taken, by source, over the snapshots where that source is known. */
  farmAway: { pl1: number; granary: number; workshop: number };
  /** Snapshots where an on source of farm labour was unknown. */
  farmAwayUnknown: number;
  purchasesMilli: number; purchaseSnapshots: number;
  pricedOutSnapshots: number; pricedOutPersons: number;
  remittanceMilli: number;
  conditionFirst: number | null; conditionLast: number | null;
  unknown: Record<LinkKey, number>;
}

export function chainTotals(turns: readonly ChainTurn[]): ChainTotals {
  const unknown = Object.fromEntries(LINKS.map((l) => [l.key, 0])) as Record<LinkKey, number>;
  const out: ChainTotals = { snapshots: turns.length, stalls: 0, stallsNoTimber: 0, expeditions: [], delivered: 0, deliveredUnknown: 0,
    wagesMilli: { pl3: 0, rs2: 0, pl1: 0 }, paidPeople: 0, farmAway: { pl1: 0, granary: 0, workshop: 0 }, farmAwayUnknown: 0,
    purchasesMilli: 0, purchaseSnapshots: 0,
    pricedOutSnapshots: 0, pricedOutPersons: 0, remittanceMilli: 0, conditionFirst: null, conditionLast: null, unknown };
  const eids = new Set<number>();
  const people = new Set<number>();
  for (const t of turns) {
    for (const l of LINKS) if (linkState(t, l.key) === "unknown" || incomplete(t, l.key)) unknown[l.key] += 1;
    const repair = has(t.repair);
    for (const r of repair?.receipts ?? []) if (r.status === "stalled") {
      out.stalls += 1;
      if (r.reasons.includes("no_timber")) out.stallsNoTimber += 1;
    }
    const exp = has(t.expedition);
    exp?.expeditions.forEach((e) => eids.add(e.eid));
    out.delivered += exp?.delivered ?? 0;
    if (t.expedition.state === "unknown" || t.expedition.state === "malformed") out.deliveredUnknown += 1;
    const w = has(t.wages);
    if (w) for (const [k, c] of [["pl3", w.pl3], ["rs2", w.rs2], ["pl1", w.pl1]] as const) {
      if (c.state !== "known") continue;
      for (const row of c.value.rows) {
        out.wagesMilli[k] += row.wagesMilli;
        row.paid.forEach((p) => people.add(p));
      }
    }
    const away = farmLabourAway(t);
    for (const k of ["pl1", "granary", "workshop"] as const) {
      const v = away[k];
      if (typeof v === "number") out.farmAway[k] += v;
    }
    if (Object.values(away).some((v) => v === null)) out.farmAwayUnknown += 1;
    const p = has(t.retail)?.frame?.provisioning;
    if (p) {
      out.purchasesMilli += p.paid_milli;
      if (p.paid_milli > 0) out.purchaseSnapshots += 1;
      if (p.priced_out_persons > 0) { out.pricedOutSnapshots += 1; out.pricedOutPersons += p.priced_out_persons; }
    }
    out.remittanceMilli += has(t.remittances)?.row?.inflow_milli ?? 0;
    const g = has(t.granary);
    if (g && g.asset !== null && g.asset !== "none") {
      if (out.conditionFirst === null) out.conditionFirst = g.asset.condition;
      out.conditionLast = g.asset.condition;
    }
  }
  out.expeditions = [...eids].sort((a, b) => a - b);
  out.paidPeople = people.size;
  return out;
}
