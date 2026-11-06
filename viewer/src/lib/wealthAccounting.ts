import type { TurnSnapshot } from "../types";

/**
 * Reader of the A1 observation-only wealth ledger
 * (``snapshot.livelihoods.wealth_accounting``; Python reference
 * ``chronicler.wealth_accounting.record_status``). Balances are in wealth
 * units, typed flows in whole milli-units, treasury amounts in whole units.
 * Absent, malformed, unobserved (``frame: null``: unknown, not zero) and
 * observed are distinct readings; inside an observed frame zeros are
 * recorded zeros and nulls are unknown.
 */
export type ContinuityStatus = "exact" | "broken" | "unchecked";

export interface WealthContinuity {
  status: ContinuityStatus;
  /** ``unchecked``: first_turn, pool_reset, gap, no_closing or no_opening. */
  reason: string | null;
  previous_close_turn: number | null;
  wealth_changed?: boolean; region_changed?: boolean;
  /** ``broken``: opening total minus the previous closing total (wealth units). */
  difference?: number; agents_difference?: number;
  /** ``broken``: [region, wealth change, people change], at most 16. */
  regions?: [number, number, number][]; regions_dropped?: number;
}

export interface WealthWorldRow {
  open: number; close: number; delta: number; agents_open: number; agents_close: number;
  births: number; births_close: number; deaths: number; deaths_open: number; moved: number; moved_close: number;
  typed_in_milli: number; typed_out_milli: number; typed_net_milli: number;
  unlocated_in_milli: number; unlocated_out_milli: number;
  /** The labelled residual of native model flows (not itemized in slice 1). */
  native_model: number; unplaced_agents: number;
}

export interface WealthRegionRow {
  region: number; open: number; close: number; agents_open: number; agents_close: number;
  migration_in: number; migration_out: number; births: number; births_close: number; deaths: number;
  deaths_open: number; typed_in_milli: number; typed_out_milli: number;
  /** Also holds the region's share of unlocated typed flows (the record's label). */
  native_model: number;
}

export interface WealthTypedRow {
  channel: string; package: string | null; payer: string;
  /** False: the package is active but this turn's record is missing (unknown, not zero). */
  observed: boolean;
  in_milli: number; out_milli: number; unlocated_in_milli: number; unlocated_out_milli: number;
}

export interface WealthClosure { channel: string; check: string; lhs: number; rhs: number; closes: boolean }

/** The closures of an observed frame that did not hold (a failure is shown, never read as malformed). */
export const failedClosures = (frame: WealthFrame) => frame.closures.filter((c) => !c.closes);

export interface WithheldPackageRow {
  package: string; rows: number; deducted: number; ordinary: number;
  /** The package's own counter for the turn; null when it keeps none. */
  package_total: number | null; matches: boolean | null;
}

export interface WealthWithheld {
  paid_work_active: boolean;
  /** Null when no paid-work package is active (not zero). */
  rows: number | null; deducted: number | null; packages: WithheldPackageRow[] | null;
  unattributed_rows: number | null; unattributed_pl3_dropped_rows: number | null;
  unattributed_deducted: number | null; conflicts: number | null;
  recovery_crews: {
    granary: number; workshop: number; total: number; difference: number; closes: boolean; rows_dropped: number;
  } | null;
  retail_active: boolean;
  /** Null: retail off or not observed this turn. */
  retail_income_replaced: number | null;
}

export interface WealthTreasury {
  created: { treasury_tax: number };
  /** Not created money: ``potential`` is an upper bound; ``collected`` is not observed. */
  tithe: { potential: number; at_threshold_after_tick: number; approximate: true; collected: null };
  to_households_milli: Record<string, number>;
  firm_cash: Record<string, number>;
  charged: Record<string, number>;
  sinks_milli: Record<string, number>;
  by_civ: ({ civ: number } & Record<string, number>)[];
}

export interface WealthFrame {
  turn: number; continuity: WealthContinuity; typed_complete: boolean; world: WealthWorldRow;
  regions: WealthRegionRow[]; typed: WealthTypedRow[]; closures: WealthClosure[];
  /** Null when neither a paid-work package nor retail is active. */
  withheld: WealthWithheld | null;
  treasury: WealthTreasury;
}

export interface WealthAccountingRecord {
  schema_version: 1; stage: "A1"; source_turn: number;
  units: Record<string, string | number>;
  frame: WealthFrame | null;
  lifetime: Record<string, number>;
  counters: Record<string, number>;
  log: { turn: number; kind: string; detail: Record<string, unknown> }[];
  log_dropped: number;
  labels: Record<string, string>;
  parameters: Record<string, unknown>;
}

export type WealthAccountingReading =
  | { status: "absent" }
  | { status: "malformed"; reason: string }
  | { status: "unobserved"; record: WealthAccountingRecord }
  | { status: "observed"; record: WealthAccountingRecord; frame: WealthFrame };

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const milli = (x: unknown): x is number => count(x);
/** Unlocated flows are a package's total minus what it located by region: negative when a
 * package's rows exceed its own total, which the ledger records as a failed closure (still observed). */
const signedMilli = (x: unknown): x is number => finite(x) && Number.isInteger(x);
const near = (a: number, b: number) => Math.abs(a - b) <= 1e-6 * Math.max(1, Math.abs(a), Math.abs(b));
const STATUSES: readonly ContinuityStatus[] = ["exact", "broken", "unchecked"];
const WORLD_COUNTS = ["agents_open", "agents_close", "births", "deaths", "moved", "unplaced_agents"] as const;
const WORLD_AMOUNTS = ["open", "close", "births_close", "deaths_open", "moved_close"] as const;
const REGION_COUNTS = ["agents_open", "agents_close", "births", "deaths"] as const;
const REGION_AMOUNTS = ["open", "close", "migration_in", "migration_out", "births_close", "deaths_open"] as const;

function worldProblem(w: unknown): string | null {
  if (!object(w) || !WORLD_COUNTS.every((k) => count(w[k])) || !WORLD_AMOUNTS.every((k) => amount(w[k]))
    || ![w.delta, w.native_model].every(finite) || !milli(w.typed_in_milli) || !milli(w.typed_out_milli)
    || !finite(w.typed_net_milli) || !signedMilli(w.unlocated_in_milli) || !signedMilli(w.unlocated_out_milli))
    return "malformed world row";
  const r = w as unknown as WealthWorldRow;
  if (!near(r.close - r.open, r.delta)) return "the world change is not close minus open";
  if (r.typed_in_milli - r.typed_out_milli !== r.typed_net_milli) return "typed net is not in minus out";
  if (!near(r.delta - r.typed_net_milli / 1000, r.native_model)) return "the world identity does not close";
  return null;
}

function regionProblem(x: unknown, regions: number): string | null {
  if (!object(x) || !count(x.region) || x.region >= regions || !REGION_COUNTS.every((k) => count(x[k]))
    || !REGION_AMOUNTS.every((k) => amount(x[k])) || !milli(x.typed_in_milli) || !milli(x.typed_out_milli)
    || !finite(x.native_model)) return "malformed region row";
  const r = x as unknown as WealthRegionRow;
  const rhs = r.migration_in - r.migration_out + (r.typed_in_milli - r.typed_out_milli) / 1000 + r.native_model;
  if (!near(r.close - r.open, rhs)) return "a region's identity does not close";
  return null;
}

function typedProblem(x: unknown): string | null {
  if (!object(x) || typeof x.channel !== "string" || typeof x.payer !== "string"
    || !(x.package === null || typeof x.package === "string") || typeof x.observed !== "boolean"
    || ![x.in_milli, x.out_milli].every(milli) || ![x.unlocated_in_milli, x.unlocated_out_milli].every(signedMilli))
    return "malformed typed flow";
  const r = x as unknown as WealthTypedRow;
  if (r.unlocated_in_milli > r.in_milli || r.unlocated_out_milli > r.out_milli) return "unlocated flows exceed their total";
  return null;
}

function withheldProblem(x: unknown): string | null {
  if (x === null) return null;
  if (!object(x) || typeof x.paid_work_active !== "boolean" || typeof x.retail_active !== "boolean"
    || !(x.retail_income_replaced === null || amount(x.retail_income_replaced))) return "malformed withheld income";
  const paid = ["rows", "unattributed_rows", "unattributed_pl3_dropped_rows", "conflicts"] as const;
  if (!x.paid_work_active) {
    return [...paid, "deducted", "packages", "unattributed_deducted", "recovery_crews"].every((k) => x[k] === null)
      ? null : "paid-work fields recorded without a paid-work package";
  }
  if (!paid.every((k) => count(x[k])) || !amount(x.deducted) || !amount(x.unattributed_deducted)
    || !Array.isArray(x.packages)) return "malformed withheld income";
  for (const p of x.packages) {
    if (!object(p) || typeof p.package !== "string" || !count(p.rows) || !amount(p.deducted) || !amount(p.ordinary)
      || !(p.package_total === null || finite(p.package_total)) || !(p.matches === null || typeof p.matches === "boolean"))
      return "malformed withheld package";
  }
  const rc = x.recovery_crews;
  if (!(rc === null || (object(rc) && [rc.granary, rc.workshop].every(amount) && finite(rc.total)
    && finite(rc.difference) && typeof rc.closes === "boolean" && count(rc.rows_dropped))))
    return "malformed recovery-crew split";
  return null;
}

function treasuryProblem(x: unknown, civs: number): string | null {
  if (!object(x) || !object(x.created) || !count(x.created.treasury_tax) || !object(x.tithe)) return "malformed treasury";
  const t = x.tithe;
  if (!count(t.potential) || !count(t.at_threshold_after_tick) || t.at_threshold_after_tick > t.potential
    || t.approximate !== true || t.collected !== null) return "malformed tithe";
  for (const key of ["to_households_milli", "firm_cash", "charged", "sinks_milli"] as const) {
    const block = x[key];
    if (!object(block) || !Object.values(block).every(finite)) return `malformed treasury ${key}`;
  }
  if (!Array.isArray(x.by_civ) || !x.by_civ.every((r) => object(r) && count(r.civ) && r.civ < civs
    && Object.values(r).every(finite))) return "malformed treasury by civilization";
  return null;
}

function frameProblem(f: unknown, source: number, regions: number, civs: number): string | null {
  if (!object(f) || f.turn !== source) return "misdated frame";
  const c = f.continuity;
  if (!object(c) || !STATUSES.includes(c.status as ContinuityStatus) || !(c.reason === null || typeof c.reason === "string"))
    return "malformed continuity";
  if (c.status === "broken" && !(finite(c.difference) && Array.isArray(c.regions))) return "malformed continuity";
  if (typeof f.typed_complete !== "boolean") return "malformed frame";
  const world = worldProblem(f.world);
  if (world) return world;
  if (!Array.isArray(f.regions) || !Array.isArray(f.typed) || !Array.isArray(f.closures)) return "malformed frame";
  for (const r of f.regions) {
    const why = regionProblem(r, regions);
    if (why) return why;
  }
  if (new Set(f.regions.map((r) => (r as WealthRegionRow).region)).size !== f.regions.length) return "a region has two rows";
  for (const r of f.typed) {
    const why = typedProblem(r);
    if (why) return why;
  }
  const typed = f.typed as WealthTypedRow[];
  const w = f.world as WealthWorldRow;
  if (typed.reduce((a, r) => a + r.in_milli, 0) !== w.typed_in_milli
    || typed.reduce((a, r) => a + r.out_milli, 0) !== w.typed_out_milli) return "typed flows do not sum to the world row";
  if (!f.closures.every((x) => object(x) && typeof x.channel === "string" && typeof x.check === "string"
    && finite(x.lhs) && finite(x.rhs) && typeof x.closes === "boolean")) return "malformed closure";
  return withheldProblem(f.withheld) ?? treasuryProblem(f.treasury, civs);
}

/** Strict reading of one history snapshot's ledger record. */
export function readWealthAccounting(snapshot: TurnSnapshot | null, regionCount: number,
  civCount: number): WealthAccountingReading {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.wealth_accounting === undefined || livelihoods.wealth_accounting === null)
    return { status: "absent" };
  const bad = (reason: string): WealthAccountingReading => ({ status: "malformed", reason });
  if (livelihoods.schema_version !== 1) return bad("unknown livelihoods schema");
  const x = livelihoods.wealth_accounting;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "A1") return bad("unknown wealth-accounting schema");
  if (!count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn) return bad("misdated observation");
  if (!object(x.units) || !object(x.lifetime) || !object(x.counters) || !Array.isArray(x.log) || !object(x.labels))
    return bad("malformed record");
  if (!("frame" in x)) return bad("the record has no frame");
  const record = x as unknown as WealthAccountingRecord;
  if (x.frame === null) return { status: "unobserved", record };
  const why = frameProblem(x.frame, x.source_turn, regionCount, civCount);
  if (why) return bad(why);
  return { status: "observed", record, frame: x.frame as unknown as WealthFrame };
}

/** Milli-units to wealth units. */
export const units = (m: number) => m / 1000;
