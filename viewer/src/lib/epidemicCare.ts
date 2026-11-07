/**
 * C2 bounded epidemic care capacity (`--epidemic-care`): the strict reader of
 * `snapshot.livelihoods.epidemic_care` and its reading (`recordReading.ts`), so
 * the panel tells apart a run without the switch (`disabled`), a snapshot
 * without the record (`absent`), a refused record (`malformed`), a turn whose
 * tick or Phase 2 was not observed (`unobserved`), a turn where nothing
 * happened (`recorded_zero`) and the record itself (`recorded`).
 *
 * Dates (`docs/integration/epidemic-care.md`): the snapshot labelled N records
 * simulation turn N - 1 (`source_turn`). Its `tick` is that turn's epidemic
 * tick, which applied the capacity the carers of turn N - 2 provided; its
 * `frame` is the carers named in turn N - 1 and `capacity` what they provide
 * to the tick of turn N. Region and civilization identities are indices.
 */
import type { Bundle, TurnSnapshot } from "../types";
import { readRecord, type RecordReading } from "./recordReading";

export type CareMode = "care" | "cost_only";
export const CARE_LIMITS = ["need_met", "envelope", "treasury", "labour", "no_patients", "recipient_lost"] as const;
export type CareLimit = (typeof CARE_LIMITS)[number];

export interface CareApplied {
  region: number;
  source_turn: number;
  patients: number;
  infectious: number;
  coverage: number;
  care_factor: number;
  would_be: number;
  techniques_factor: number | null;
  combined_factor: number;
  floored: boolean;
  deaths: number | null;
  cases: number | null;
  infectious_after: number | null;
}

export interface CareRefusal { region: number; source_turn: number; reason: "stale" | "future" }

export interface Carer {
  agent_id: number;
  origin: string;
  share: number;
  wage_due_milli: number;
  wage_paid_milli: number;
  wage_residual_milli: number;
  income_withheld: number | null;
}

export interface CareReceipt {
  turn: number;
  region: number;
  civ: number;
  commitment: number;
  envelope: number;
  infectious: number;
  need: number;
  eligible: number;
  carers: Carer[];
  care_time: number;
  patients: number;
  wages_due_milli: number;
  wages_paid_milli: number;
  wage_residual_milli: number;
  farm_time_removed: number;
  limit: CareLimit;
  paid: boolean;
}

export interface CareLedger {
  turn: number;
  civ: number;
  due_milli: number;
  paid_milli: number;
  residual_milli: number;
  treasury_units: number;
  carry_before: number;
  carry_after: number;
  status: string;
}

export interface CareCapacity { region: number; source_turn: number; carers: number; care_time: number; patients: number }

export interface EpidemicCareRecord {
  mode: CareMode;
  source_turn: number;
  tick: { turn: number; applied: CareApplied[]; refused: CareRefusal[] } | null;
  frame: CareReceipt[] | null;
  ledger: CareLedger[] | null;
  capacity: CareCapacity[];
  counters: Record<string, number>;
  parameters: { care_cfr_reduction: number; patients_per_carer: number; wage_milli: number; cfr_floor: number };
}

export const CARE_MODE_LABEL: Record<CareMode, string> = {
  care: "Care (lowers case fatality)",
  cost_only: "Cost only (no effect on fatality)",
};

export const CARE_MODE_NOTE: Record<CareMode, string> = {
  care: "Carers named last turn serve patients at this turn's epidemic tick: case fatality there is multiplied by "
    + "1 - 0.3 x coverage, under one floor with practised medicine. Deaths are still drawn by the epidemic model.",
  cost_only: "The cost control: the same carers, farm time, withheld income and wages, and no effect on case "
    + "fatality (the factor care would have applied is shown).",
};

export const CARE_LIMIT_LABEL: Record<CareLimit, string> = {
  need_met: "need covered",
  envelope: "budget envelope spent",
  treasury: "treasury short",
  labour: "no more free farmers",
  no_patients: "nobody infectious",
  recipient_lost: "region changed hands",
};

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const num = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const int = (x: unknown): x is number => Number.isInteger(x);
const nonneg = (x: unknown): x is number => num(x) && x >= 0;
const index = (x: unknown, n: number) => int(x) && (x as number) >= 0 && (x as number) < n;
const nullable = (x: unknown, test: (v: unknown) => boolean) => x === null || test(x);
const factor = (x: unknown) => num(x) && x > 0 && x <= 1;

function applied(row: unknown, regions: number, tick: number): row is CareApplied {
  return object(row) && index(row.region, regions) && row.source_turn === tick - 1 && nonneg(row.patients)
    && nonneg(row.infectious) && num(row.coverage) && row.coverage >= 0 && row.coverage <= 1
    && factor(row.care_factor) && factor(row.would_be) && nullable(row.techniques_factor, factor)
    && factor(row.combined_factor) && typeof row.floored === "boolean" && nullable(row.deaths, (v) => int(v) && (v as number) >= 0)
    && nullable(row.cases, nonneg) && nullable(row.infectious_after, nonneg);
}

function carer(row: unknown): row is Carer {
  return object(row) && int(row.agent_id) && typeof row.origin === "string" && num(row.share) && row.share > 0
    && row.share <= 1 && [row.wage_due_milli, row.wage_paid_milli, row.wage_residual_milli].every((v) => int(v) && (v as number) >= 0)
    && (row.wage_paid_milli as number) + (row.wage_residual_milli as number) <= (row.wage_due_milli as number)
    && nullable(row.income_withheld, nonneg);
}

function receipt(row: unknown, regions: number, civs: number, turn: number): row is CareReceipt {
  return object(row) && row.turn === turn && index(row.region, regions) && index(row.civ, civs) && int(row.commitment)
    && int(row.envelope) && nonneg(row.infectious) && nonneg(row.need) && int(row.eligible)
    && Array.isArray(row.carers) && row.carers.every(carer) && nonneg(row.care_time) && nonneg(row.patients)
    && [row.wages_due_milli, row.wages_paid_milli, row.wage_residual_milli].every((v) => int(v) && (v as number) >= 0)
    && nonneg(row.farm_time_removed) && (CARE_LIMITS as readonly unknown[]).includes(row.limit) && typeof row.paid === "boolean"
    && new Set((row.carers as Carer[]).map((c) => c.agent_id)).size === (row.carers as Carer[]).length;
}

function ledger(row: unknown, civs: number, turn: number): row is CareLedger {
  return object(row) && row.turn === turn && index(row.civ, civs)
    && [row.due_milli, row.paid_milli, row.residual_milli, row.treasury_units, row.carry_before, row.carry_after]
      .every((v) => int(v) && (v as number) >= 0)
    && typeof row.status === "string";
}

function capacity(row: unknown, regions: number, turn: number): row is CareCapacity {
  return object(row) && index(row.region, regions) && row.source_turn === turn && int(row.carers) && (row.carers as number) > 0
    && nonneg(row.care_time) && nonneg(row.patients);
}

/** The record at a snapshot, or null when it is absent or malformed (misdated, another schema, inconsistent). */
export function epidemicCareAt(snapshot: TurnSnapshot, regions: number, civs: number): EpidemicCareRecord | null {
  const livelihoods = (snapshot as unknown as Record<string, unknown>).livelihoods;
  const raw = object(livelihoods) ? livelihoods.epidemic_care : undefined;
  if (!object(raw) || raw.schema_version !== 1 || raw.stage !== "C2") return null;
  if (raw.mode !== "care" && raw.mode !== "cost_only") return null;
  const source = raw.source_turn;
  if (!int(source) || source !== snapshot.turn - 1) return null;
  const tick = raw.tick;
  if (tick !== null) {
    if (!object(tick) || tick.turn !== source || !Array.isArray(tick.applied) || !Array.isArray(tick.refused)) return null;
    if (!tick.applied.every((row) => applied(row, regions, source))) return null;
    if (!tick.refused.every((row) => object(row) && int(row.region) && int(row.source_turn)
      && (row.reason === "stale" || row.reason === "future"))) return null;
    if (new Set((tick.applied as CareApplied[]).map((row) => row.region)).size !== tick.applied.length) return null;
    // cost_only never changes fatality; care applies the factor it computes.
    if ((tick.applied as CareApplied[]).some((row) => raw.mode === "cost_only" ? row.care_factor !== 1
      : row.care_factor !== row.would_be)) return null;
  }
  const frame = raw.frame;
  if (frame !== null && !(Array.isArray(frame) && frame.every((row) => receipt(row, regions, civs, source)))) return null;
  const rows = raw.ledger;
  if (rows !== null && !(Array.isArray(rows) && rows.every((row) => ledger(row, civs, source)))) return null;
  if (!Array.isArray(raw.capacity) || !raw.capacity.every((row) => capacity(row, regions, source))) return null;
  if (frame !== null) {
    const staffed = new Set((frame as CareReceipt[]).filter((row) => row.carers.length > 0).map((row) => row.region));
    if ((raw.capacity as CareCapacity[]).some((row) => !staffed.has(row.region))) return null;
  }
  if (!object(raw.counters) || !Object.values(raw.counters).every(num)) return null;
  const p = raw.parameters;
  if (!object(p) || !num(p.care_cfr_reduction) || !num(p.patients_per_carer) || !num(p.wage_milli) || !num(p.cfr_floor)) return null;
  return {
    mode: raw.mode, source_turn: source,
    tick: tick === null ? null : tick as EpidemicCareRecord["tick"],
    frame: frame as CareReceipt[] | null, ledger: rows as CareLedger[] | null,
    capacity: raw.capacity as CareCapacity[], counters: raw.counters as Record<string, number>,
    parameters: p as EpidemicCareRecord["parameters"],
  };
}

const carries = (snapshot: TurnSnapshot) => {
  const livelihoods = (snapshot as unknown as Record<string, unknown>).livelihoods;
  return object(livelihoods) && livelihoods.epidemic_care !== undefined && livelihoods.epidemic_care !== null;
};

export const EPIDEMIC_CARE = {
  key: "epidemic_care", label: "Epidemic care", flag: "--epidemic-care", livelihoods: true,
  carries, read: epidemicCareAt,
  observed: (r: EpidemicCareRecord) => r.tick !== null && r.frame !== null,
  empty: (r: EpidemicCareRecord) => r.tick !== null && r.tick.applied.length === 0 && r.tick.refused.length === 0
    && r.frame !== null && r.frame.length === 0,
  zero: "no care capacity reached the epidemic tick and no care envelope was open",
};

export const readEpidemicCare = (bundle: Bundle | null | undefined, snapshot: TurnSnapshot | null,
  turn?: number): RecordReading<EpidemicCareRecord> => readRecord(EPIDEMIC_CARE, bundle, snapshot, turn);

/** Wages in treasury units from milli-units, as text. */
export function units(milli: number): string {
  return (milli / 1000).toFixed(milli % 1000 === 0 ? 0 : 3);
}

/** One line per region of this turn: what its tick applied and the carers it named. */
export interface CareRegionRow {
  region: number;
  applied: CareApplied | null;
  receipt: CareReceipt | null;
}

export function careRegionRows(record: EpidemicCareRecord): CareRegionRow[] {
  const regions = new Set<number>([
    ...(record.tick?.applied ?? []).map((row) => row.region),
    ...(record.frame ?? []).map((row) => row.region),
  ]);
  return [...regions].sort((a, b) => a - b).map((region) => ({
    region,
    applied: record.tick?.applied.find((row) => row.region === region) ?? null,
    receipt: record.frame?.find((row) => row.region === region) ?? null,
  }));
}
