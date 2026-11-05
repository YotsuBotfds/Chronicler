import type { TurnSnapshot } from "../types";

/** A selected workshop site (``snapshot.livelihoods.workshops.sites``). */
export interface WorkshopSiteRecord {
  site: number; region: number; settlement_id: number; city_name: string; selected_turn: number;
  status: "open" | "closed"; closed_turn: number | null; closed_reason: string | null;
  /** L1B asset lifecycle; absent from observe-mode records. */
  asset?: "building" | "open" | "idle" | "closed"; construction_paid?: number; condition?: number;
  arrears?: number; last_payer?: number; history?: Array<[number, string, number, number]>;
}

/** One site's completed Phase 2 receipt. Craft output and inputs are region totals. */
export interface WorkshopReceiptRecord {
  turn: number; site: number; region: number; settlement_id: number; rank: number;
  diverted_fraction: number; resident_adult_farmers: number; excluded_trip: number; excluded_army: number;
  excluded_assigned: number; eligible: number; crew: number[]; crew_ages: number[];
  work_available: number; allocated: number; realized: number;
  legacy_craft_ceiling: number | null; region_craft_output: number | null;
  region_craft_input: { timber: number; ore: number } | null;
  asset?: string | null; payer?: number | null; funded?: boolean | null; craft_ceiling?: number | null;
  paid?: Record<string, number> | null; arrears_after?: number | null; condition_after?: number | null;
  affected_ordinary_income_share?: number;
}

export interface WorkshopsRecord {
  schema_version: 1; stage: "L1A" | "L1B"; mode: "operate" | "observe" | "cost_only"; source_turn: number;
  sites: WorkshopSiteRecord[]; closed: WorkshopSiteRecord[];
  /** Null: no completed Phase 2 observation for the source turn (unknown, not zero). */
  receipts: WorkshopReceiptRecord[] | null;
  counters: Record<string, number>;
}

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const MODES = ["operate", "observe", "cost_only"];

function validSite(x: unknown, regions: number): boolean {
  return object(x) && count(x.site) && count(x.region) && x.region < regions && count(x.settlement_id)
    && typeof x.city_name === "string" && count(x.selected_turn) && (x.status === "open" || x.status === "closed");
}

function validReceipt(x: unknown, regions: number, source: number): boolean {
  if (!object(x) || x.turn !== source || !count(x.site) || !count(x.region) || x.region >= regions
    || !Array.isArray(x.crew) || x.crew.length > 8 || !x.crew.every(count)
    || !count(x.eligible) || x.crew.length > x.eligible || !amount(x.work_available)
    || !amount(x.allocated) || !amount(x.realized) || x.realized > x.allocated + 1e-6
    || x.allocated > x.work_available + 1e-6) return false;
  if (x.region_craft_input !== null && !(object(x.region_craft_input)
    && amount(x.region_craft_input.timber) && amount(x.region_craft_input.ore))) return false;
  return x.region_craft_output === null || amount(x.region_craft_output);
}

/** Strict reader; null when absent, from another schema, misdated or malformed. */
export function workshopsAt(snapshot: TurnSnapshot | null, regionCount: number): WorkshopsRecord | null {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return null;
  const x = livelihoods.workshops;
  if (!object(x) || x.schema_version !== 1 || !MODES.includes(x.mode as string) || !count(x.source_turn)
    || x.source_turn + 1 !== snapshot?.turn || !Array.isArray(x.sites) || !Array.isArray(x.closed)
    || x.sites.length > 4 || !x.sites.every((s) => validSite(s, regionCount))
    || !x.closed.every((s) => validSite(s, regionCount)) || !object(x.counters)) return null;
  if (x.receipts !== null && !(Array.isArray(x.receipts)
    && x.receipts.every((r) => validReceipt(r, regionCount, x.source_turn as number)))) return null;
  return x as unknown as WorkshopsRecord;
}
