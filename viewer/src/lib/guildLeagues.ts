import { isRecord as object, count } from "./recordGuards";
import type { Bundle, TurnSnapshot } from "../types";
import { readRecord, type RecordReading } from "./recordReading";

/**
 * Reader of D1b cross-border guild leagues (`snapshot.livelihoods.guild_leagues`,
 * `--guild-leagues`; Python reference `chronicler.guild_leagues.record_status`).
 * Types live here, not in the pinned `types.ts`.
 *
 * The six readings of `recordReading.ts` stay distinct: `disabled`, `absent`
 * (unknown, not zero), `malformed` (refused, with the reason), `unobserved`
 * (`frame: null`), `recorded_zero` (observed: no league held money or changed,
 * no dues, no claims) and `recorded`. Money is in milli of the guild and civic
 * purses. A claim names the city history entry it answers (`event_id`): the
 * fund pays only recorded losses. Never reads final-world state.
 */
export const MODES = ["mutual", "dues_only"] as const;
const CLAIM_KINDS = ["levy", "sack"] as const;
const CHANGE_KINDS = ["founded", "joined", "left", "dissolved"] as const;
const LEAVE_REASONS = ["guild_dissolved", "city_fallen", "lord_changed"] as const;
const DISSOLVE_REASONS = ["war_between_members", "too_few_members", "one_realm", "dormant", "switched_off"] as const;

export interface LeagueMember {
  guild: number; city: number; region: number; lord: number; joined_turn: number;
  dues_milli: number; payouts_milli: number;
}
export interface LeagueRow {
  league: number; founded_turn: number; members: LeagueMember[]; fund_open_milli: number; dues_milli: number;
  payouts_milli: number; returned_milli: number; unclaimed_milli: number; fund_close_milli: number;
  cap_milli: number; dissolved: (typeof DISSOLVE_REASONS)[number] | null;
}
export interface LeagueDues { league: number; guild: number; city: number; milli: number }
export interface LeaguePayout {
  league: number; guild: number; city: number; kind: (typeof CLAIM_KINDS)[number]; loss_milli: number;
  paid_milli: number; event_id: string;
}
export interface LeagueChange {
  league: number; kind: (typeof CHANGE_KINDS)[number]; guild: number | null; city: number | null;
  reason: string | null; returned_milli: number | null; unclaimed_milli: number | null;
}
export interface LeagueFrame {
  turn: number; leagues: LeagueRow[]; dues: LeagueDues[]; payouts: LeaguePayout[]; changes: LeagueChange[];
  links: number; candidates: number;
}
export interface LeagueRecord {
  schema_version: 1; stage: "D1b"; mode: (typeof MODES)[number]; source_turn: number; frame: LeagueFrame | null;
  next_league: number; dissolved: { league: number; founded_turn: number; dissolved_turn: number | null; reason: string | null }[];
  dissolved_dropped: number; counters: Record<string, number>; log: unknown[]; log_dropped: number;
  parameters: Record<string, unknown>;
}

const has = <T extends string>(list: readonly T[], x: unknown): x is T => typeof x === "string" && (list as readonly string[]).includes(x);

function memberProblem(x: unknown, regions: number, civs: number): string | null {
  if (!object(x) || !count(x.guild) || !count(x.city) || !count(x.region) || x.region >= regions || !count(x.lord)
    || x.lord >= civs || !count(x.joined_turn) || !count(x.dues_milli) || !count(x.payouts_milli))
    return "malformed league member";
  return null;
}

function rowProblem(x: unknown, next: number, regions: number, civs: number): string | null {
  if (!object(x) || !count(x.league) || x.league < 1 || x.league >= next || !count(x.founded_turn)
    || !Array.isArray(x.members) || !["fund_open_milli", "dues_milli", "payouts_milli", "returned_milli",
      "unclaimed_milli", "fund_close_milli", "cap_milli"].every((k) => count(x[k]))
    || !(x.dissolved === null || has(DISSOLVE_REASONS, x.dissolved))) return "malformed league row";
  for (const m of x.members) { const why = memberProblem(m, regions, civs); if (why) return why; }
  const r = x as unknown as LeagueRow;
  if (r.members.length > 4 || new Set(r.members.map((m) => m.lord)).size !== r.members.length)
    return "a league holds two members of one realm or more than four";
  if (r.dissolved !== null && (r.members.length > 0 || r.fund_close_milli !== 0)) return "a dissolved league still holds members or money";
  if (r.fund_open_milli + r.dues_milli - r.payouts_milli - r.returned_milli - r.unclaimed_milli !== r.fund_close_milli)
    return "a league fund does not close";
  return null;
}

/** Strict reading of one record; the reason it is refused, or the record. */
export function leagueRecordAt(snapshot: TurnSnapshot | null, regions: number, civs: number):
  { record: LeagueRecord; reason: null } | { record: null; reason: string } {
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null)?.livelihoods;
  const x = object(livelihoods) ? livelihoods.guild_leagues : undefined;
  const refuse = (reason: string) => ({ record: null, reason });
  if (!object(x) || x.schema_version !== 1 || x.stage !== "D1b") return refuse("unknown guild-leagues schema");
  if (!has(MODES, x.mode) || !count(x.source_turn) || !count(x.next_league) || x.next_league < 1
    || !Array.isArray(x.dissolved) || !object(x.counters) || !Object.values(x.counters).every(count))
    return refuse("malformed guild-leagues record");
  const f = x.frame;
  if (f !== null) {
    if (!object(f) || f.turn !== x.source_turn) return refuse("misdated frame");
    if (![f.leagues, f.dues, f.payouts, f.changes].every(Array.isArray) || !count(f.links) || !count(f.candidates))
      return refuse("malformed frame");
    const next = x.next_league as number;
    for (const r of f.leagues as unknown[]) { const why = rowProblem(r, next, regions, civs); if (why) return refuse(why); }
    for (const d of f.dues as unknown[]) {
      if (!object(d) || !count(d.league) || !count(d.guild) || !count(d.city) || !count(d.milli) || d.milli === 0)
        return refuse("malformed league dues");
    }
    for (const p of f.payouts as unknown[]) {
      if (!object(p) || !count(p.league) || !count(p.guild) || !count(p.city) || !has(CLAIM_KINDS, p.kind)
        || !count(p.loss_milli) || !count(p.paid_milli) || typeof p.event_id !== "string")
        return refuse("malformed league claim");
      if ((p.paid_milli as number) > (p.loss_milli as number)) return refuse("a claim paid more than the recorded loss");
      if (x.mode === "dues_only" && (p.paid_milli as number) > 0) return refuse("the dues-only control paid a claim");
    }
    for (const c of f.changes as unknown[]) {
      if (!object(c) || !count(c.league) || !has(CHANGE_KINDS, c.kind)) return refuse("malformed league change");
      if (c.kind === "left" && !has(LEAVE_REASONS, c.reason)) return refuse("a departure without a declared reason");
      if (c.kind === "dissolved" && !has(DISSOLVE_REASONS, c.reason)) return refuse("a dissolution without a declared reason");
    }
    const rows = f.leagues as LeagueRow[];
    const byLeague = new Map(rows.map((r) => [r.league, r]));
    for (const p of f.payouts as LeaguePayout[]) {
      if (!byLeague.has(p.league)) return refuse("a claim of a league without a row");
    }
    const paid = new Map<number, number>();
    for (const p of f.payouts as LeaguePayout[]) paid.set(p.league, (paid.get(p.league) ?? 0) + p.paid_milli);
    const dues = new Map<number, number>();
    for (const d of f.dues as LeagueDues[]) dues.set(d.league, (dues.get(d.league) ?? 0) + d.milli);
    for (const r of rows) {
      if ((paid.get(r.league) ?? 0) !== r.payouts_milli || (dues.get(r.league) ?? 0) !== r.dues_milli)
        return refuse("a league's dues or claims differ from its rows");
    }
  }
  return { record: x as unknown as LeagueRecord, reason: null };
}

const carries = (snapshot: TurnSnapshot) => {
  const livelihoods = (snapshot as unknown as Record<string, unknown>).livelihoods;
  return object(livelihoods) && livelihoods.guild_leagues !== undefined && livelihoods.guild_leagues !== null;
};

const GUILD_LEAGUES = {
  key: "guild_leagues", label: "Guild leagues", flag: "--guild-leagues", livelihoods: true,
  carries, read: (s: TurnSnapshot, regions: number, civs: number) => leagueRecordAt(s, regions, civs).record,
  observed: (r: LeagueRecord) => r.frame !== null,
  empty: (r: LeagueRecord) => r.frame !== null && r.frame.leagues.length === 0 && r.frame.dues.length === 0
    && r.frame.payouts.length === 0 && r.frame.changes.length === 0,
  zero: "no league held money or changed, and no dues or claims",
};

export const readGuildLeagues = (bundle: Bundle | null | undefined, snapshot: TurnSnapshot | null,
  turn?: number): RecordReading<LeagueRecord> => readRecord(GUILD_LEAGUES, bundle, snapshot, turn);

export function guildLeaguesOn(history: readonly TurnSnapshot[] | null | undefined): boolean {
  return Array.isArray(history) && history.some((s) => s !== null && typeof s === "object" && carries(s));
}
