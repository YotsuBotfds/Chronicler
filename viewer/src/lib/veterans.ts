import type { TurnSnapshot } from "../types";

/** A dated outcome of one veteran record. */
export interface VeteranOutcomeRecord {
  turn: number;
  kind: (typeof OUTCOMES)[number];
  detail: Record<string, number | string | boolean | null> | null;
}

/** Consecutive placed turns in one kind of opening at one site. */
export interface PlacementSpellRecord {
  kind: (typeof PLACEMENTS)[number]; site: number | null; region: number;
  start_turn: number; last_turn: number; turns: number;
  /** Placed while priority mode put them first (never in the record-only control). */
  prioritised: boolean;
}

/** One person released alive from a real army (``snapshot.livelihoods.veteran_reintegration.veterans``). */
export interface VeteranRecord {
  record_id: number; agent_id: number;
  /** Served civilization's index in ``world_state.civilizations`` (-1: unknown). */
  civ: number; army_id: string;
  /** The war served: the civ-pair key and its start turn (both null when no war record was found). */
  war_key: string | null; war_start: number | null;
  cause: (typeof CAUSES)[number]; released_turn: number; released_region: number;
  /** Last observed residence and age (age null: not yet observed). */
  region: number; age: number | null;
  status: "waiting" | "placed" | "ineligible" | "closed";
  reason: (typeof INELIGIBLE)[number] | null;
  closed_turn: number | null; closed_reason: (typeof CLOSING)[number] | null;
  placements: number; placed_turns: number;
  spells: PlacementSpellRecord[]; outcomes: VeteranOutcomeRecord[]; outcomes_dropped: number;
}

export interface CaptureRowRecord {
  agent_id: number; civ: number; army_id: string; war_key: string | null; war_start: number | null;
  cause: (typeof CAUSES)[number]; region: number;
}

/** The completed turn: who was released, offered, placed, who waited and why. */
export interface VeteranFrameRecord {
  turn: number; priority_applied: boolean;
  captured: CaptureRowRecord[]; captured_total: number; captured_by_cause: Record<string, number>;
  /** Per workshop site region, the eligible veterans in priority order (null: no Phase 2 observed). */
  offered: Array<[number, number[]]> | null;
  placed: Array<{ agent_id: number; kind: string; region: number; site: number | null; prioritised: boolean; new_spell: boolean }>;
  waiting: Array<{ agent_id: number; region: number; reason: (typeof UNMET)[number] }>;
  outcomes: Array<{ agent_id: number; record_id: number; kind: string; detail: Record<string, unknown> | null }>;
  counts: Record<string, number>; rows_dropped: number;
}

export interface VeteransRecord {
  schema_version: 1; stage: "RS3"; enabled: boolean; mode: "priority" | "record_only"; source_turn: number;
  /** Null: no veteran turn was committed in the source turn (unknown, not zero). */
  frame: VeteranFrameRecord | null;
  veterans: VeteranRecord[]; veterans_omitted: number;
  /** Records closed in the source turn. */
  closed: VeteranRecord[];
  counters: Record<string, number>;
  parameters: Record<string, number | string>;
}

export const CAUSES = ["desertion", "scattered", "demobilised", "destroyed", "dissolved"] as const;
export const OUTCOMES = ["placed:crew", "placed:apprentice", "placed:repair", "waiting", "remobilised",
  "died", "migrated", "control_lost", "expired", "pool_reset"] as const;
const PLACEMENTS = ["placed:crew", "placed:apprentice", "placed:repair"] as const;
const CLOSING = ["remobilised", "died", "expired", "pool_reset"] as const;
const INELIGIBLE = ["control_lost", "minor", "unobserved"] as const;
export const UNMET = ["no_site", "site_idle", "not_crew_eligible", "crew_full", "unplaced"] as const;
/** Unmet reasons that mean no opening existed for the veteran this turn. */
export const NO_OPENING: ReadonlyArray<string> = ["no_site", "site_idle"];

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const integer = (x: unknown): x is number => typeof x === "number" && Number.isInteger(x);
const count = (x: unknown): x is number => integer(x) && x >= 0;
const within = (x: unknown, n: number): x is number => count(x) && x < n;
const maybe = <T,>(check: (v: unknown) => v is T) => (x: unknown): x is T | null => x === null || check(x);
const among = (values: ReadonlyArray<string>) => (x: unknown): x is string => typeof x === "string" && values.includes(x);
const scalar = (x: unknown) => x === null || ["number", "string", "boolean"].includes(typeof x);
const detail = (x: unknown) => x === null || (object(x) && Object.values(x).every(scalar));
const sorted = (xs: number[]) => xs.every((x, i) => i === 0 || xs[i - 1] <= x);

function validSpell(x: unknown, regions: number, source: number, control: boolean): boolean {
  return object(x) && among(PLACEMENTS)(x.kind) && maybe(count)(x.site) && within(x.region, regions)
    && count(x.start_turn) && count(x.last_turn) && x.start_turn <= x.last_turn && x.last_turn <= source
    && count(x.turns) && x.turns >= 1 && x.turns <= x.last_turn - x.start_turn + 1
    && typeof x.prioritised === "boolean" && !(control && x.prioritised);
}

function validOutcome(x: unknown, source: number): boolean {
  return object(x) && count(x.turn) && x.turn <= source && among(OUTCOMES)(x.kind) && detail(x.detail);
}

function validVeteran(x: unknown, regions: number, source: number, control: boolean, closed: boolean): boolean {
  if (!object(x) || !count(x.record_id) || !count(x.agent_id) || !integer(x.civ) || x.civ < -1
    || typeof x.army_id !== "string" || !maybe((v): v is string => typeof v === "string")(x.war_key)
    || !maybe(count)(x.war_start) || (x.war_key === null) !== (x.war_start === null)
    || !among(CAUSES)(x.cause) || !count(x.released_turn) || x.released_turn > source
    || !within(x.released_region, regions) || !within(x.region, regions) || !maybe(count)(x.age)
    || !among(["waiting", "placed", "ineligible", "closed"])(x.status) || !maybe(among(INELIGIBLE))(x.reason)
    || !count(x.placements) || !count(x.placed_turns) || x.placed_turns < x.placements
    || !count(x.outcomes_dropped) || !Array.isArray(x.spells) || x.spells.length > 8
    || !x.spells.every((s) => validSpell(s, regions, source, control))
    || !Array.isArray(x.outcomes) || x.outcomes.length > 24 || !x.outcomes.every((o) => validOutcome(o, source))
    || !sorted((x.outcomes as VeteranOutcomeRecord[]).map((o) => o.turn))) return false;
  const placedNow = (x.spells as PlacementSpellRecord[]).some((s) => s.last_turn === source);
  const last = (x.outcomes as VeteranOutcomeRecord[]).at(-1);
  if (closed) {
    return x.status === "closed" && x.closed_turn === source && among(CLOSING)(x.closed_reason)
      && x.reason === null && last?.kind === x.closed_reason && last.turn === source;
  }
  if (x.status === "closed" || x.closed_turn !== null || x.closed_reason !== null) return false;
  if (x.status === "placed") return placedNow;
  if (x.status === "waiting") return x.reason === null && !placedNow;
  return x.reason !== null && !placedNow;
}

function validFrame(x: unknown, regions: number, source: number, control: boolean): boolean {
  if (!object(x) || x.turn !== source || x.priority_applied !== !control || !count(x.rows_dropped)
    || !Array.isArray(x.captured) || x.captured.length > 128 || !count(x.captured_total)
    || x.captured_total < x.captured.length || !object(x.captured_by_cause)
    || !Object.entries(x.captured_by_cause).every(([k, v]) => among(CAUSES)(k) && count(v))
    || Object.values(x.captured_by_cause as Record<string, number>).reduce((a, b) => a + b, 0) !== x.captured_total
    || !x.captured.every((c) => object(c) && count(c.agent_id) && integer(c.civ) && typeof c.army_id === "string"
      && among(CAUSES)(c.cause) && within(c.region, regions))
    || !Array.isArray(x.placed) || !Array.isArray(x.waiting) || !Array.isArray(x.outcomes)
    || !object(x.counts) || !Object.values(x.counts).every(count)) return false;
  if (x.offered !== null && !(Array.isArray(x.offered) && x.offered.every((row) => Array.isArray(row)
    && row.length === 2 && within(row[0], regions) && Array.isArray(row[1]) && row[1].every(count)))) return false;
  // One placement per person and kind of opening: under RS1 rules version 2 an
  // apprentice on the planned crew is placed both on the crew and as an apprentice.
  const placed = new Set<number>();
  const placements = new Set<string>();
  for (const p of x.placed as unknown[]) {
    if (!object(p) || !count(p.agent_id) || !among(PLACEMENTS)(p.kind) || placements.has(`${p.agent_id}:${p.kind}`)
      || !within(p.region, regions) || !maybe(count)(p.site) || typeof p.prioritised !== "boolean"
      || (control && p.prioritised) || typeof p.new_spell !== "boolean") return false;
    placed.add(p.agent_id);
    placements.add(`${p.agent_id}:${p.kind}`);
  }
  return (x.waiting as unknown[]).every((w) => object(w) && count(w.agent_id) && !placed.has(w.agent_id)
    && within(w.region, regions) && among(UNMET)(w.reason))
    && (x.outcomes as unknown[]).every((o) => object(o) && count(o.agent_id) && count(o.record_id)
      && among(OUTCOMES)(o.kind) && detail(o.detail));
}

/** Strict reader; null when absent, from another schema, misdated or malformed. */
export function veteransAt(snapshot: TurnSnapshot | null, regionCount: number): VeteransRecord | null {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return null;
  const x = livelihoods.veteran_reintegration;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "RS3" || typeof x.enabled !== "boolean"
    || !among(["priority", "record_only"])(x.mode) || !count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn
    || !count(x.veterans_omitted) || !object(x.counters) || !Object.values(x.counters).every(count)
    || !object(x.parameters)) return null;
  const source = x.source_turn;
  const control = x.mode === "record_only";
  if (!Array.isArray(x.veterans) || x.veterans.length > 64
    || !x.veterans.every((v) => validVeteran(v, regionCount, source, control, false))
    || !Array.isArray(x.closed) || x.closed.length > 64
    || !x.closed.every((v) => validVeteran(v, regionCount, source, control, true))) return null;
  const ids = (x.veterans as VeteranRecord[]).map((v) => v.agent_id);
  if (new Set(ids).size !== ids.length) return null;          // one open record per person
  if (x.frame !== null && !validFrame(x.frame, regionCount, source, control)) return null;
  return x as unknown as VeteransRecord;
}

/** Lifetime activation funnel; missing counters are zero only once the record exists. */
export function veteranFunnel(record: VeteransRecord): Array<[string, number]> {
  const c = (key: string) => record.counters[key] ?? 0;
  return [
    ["Released alive from armies (captured)", c("captured")],
    [record.mode === "priority" ? "Veteran-turns put first for crews" : "Veteran-turns that would have been put first",
      c(record.mode === "priority" ? "offered" : "would_offer")],
    ["Placements (spells)", c("placements")],
    ["Placed veteran-turns", c("placement_turns")],
    ["People placed (distinct)", c("people_placed")],
  ];
}

/** Lifetime outcome counts by kind. */
export function veteranOutcomeCounts(record: VeteransRecord): Array<[string, number]> {
  const c = (key: string) => record.counters[key] ?? 0;
  return [
    ["Placed (crew / apprentice / repair)", c("placements")],
    ["Waiting veteran-turns", c("waiting_turns")],
    ["Remobilised", c("closed_remobilised")],
    ["Died", c("closed_died")],
    ["Control lost", c("control_lost")],
    ["Expired", c("closed_expired")],
    ["Moved home region", c("migrations")],
  ];
}

/** This turn's waiting veterans by reason; null when the turn was not observed. */
export function unmetByReason(record: VeteransRecord): Map<string, number[]> | null {
  if (record.frame === null || record.frame.offered === null) return null;
  const out = new Map<string, number[]>();
  for (const w of record.frame.waiting) out.set(w.reason, [...(out.get(w.reason) ?? []), w.agent_id]);
  return out;
}
