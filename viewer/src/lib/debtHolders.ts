/**
 * Who holds each realm's debt, read from the per-turn finance snapshot
 * (`history[n].finance`). How much it can say depends on what the bundle
 * recorded:
 *
 * - `lenders`: a `--domestic-credit` bundle with `domestic_credit.holders`:
 *   foreign lenders by name with their rates, merchants by region, cities
 *   and guilds by name, the cold-start houses and legacy lines, and the
 *   debt written off on each civ;
 * - `kinds`: a `--domestic-credit` bundle written before `holders`: the
 *   domestic claims by kind of lender, foreign debt as one total;
 * - `totals`: finance alone: the abstract domestic creditor class and the
 *   foreign total.
 *
 * Nothing is inferred beyond that level: a breakdown the bundle does not
 * record stays missing. Interest "due" is principal times the line's rate
 * at the turn boundary (what the next fiscal tick charges); the domestic
 * line's interest is split among its holders pro rata to their claims, as
 * the simulation pays it.
 */
import type { Event, TurnSnapshot } from "../types";
import type { SeriesRow, StripRow } from "./systems";
import { buildSegments, orderedCivNames } from "./systems";

export type HolderDetail = "lenders" | "kinds" | "totals";

export type HolderGroup = "merchants" | "city" | "guild" | "houses" | "legacy" | "domestic" | "foreign";

/** Stacking and table order: the real domestic lenders, the abstract ones, then foreign lenders. */
export const HOLDER_GROUPS: readonly HolderGroup[] = [
  "merchants", "city", "guild", "houses", "legacy", "domestic", "foreign",
];

export const HOLDER_LABELS: Record<HolderGroup, string> = {
  merchants: "Merchants",
  city: "Cities",
  guild: "Guilds",
  houses: "Merchant houses (cold start)",
  legacy: "Legacy lines",
  domestic: "Domestic creditors",
  foreign: "Foreign lenders",
};

/**
 * Categorical slots in stacking order, validated as a set on the dark panel
 * surface (adjacent pairs, colour-vision deficiency included). `domestic`
 * (finance's abstract creditor class) is the class the cold-start houses
 * stand for, so it shares their colour; the two never stack together.
 */
export const HOLDER_COLORS: Record<HolderGroup, string> = {
  merchants: "#3987e5",
  city: "#d95926",
  guild: "#199e70",
  houses: "#c98500",
  legacy: "#d55181",
  domestic: "#c98500",
  foreign: "#9085e9",
};

/** Status colours of the trouble strip (each row is also named). */
export const ARREARS_COLOR = "#fab219";
export const DEFAULT_COLOR = "#d03b3b";
export const WRITE_OFF_COLOR = "#ec835a";

/** Snapshot kind names (`domestic_credit_state.KIND_NAMES`) to holder groups. */
const KIND_GROUPS: Record<string, HolderGroup> = {
  merchants: "merchants",
  guild: "guild",
  city: "city",
  legacy: "legacy",
  houses: "houses",
};

/** The level of holder detail the bundle records (null: no finance record at all). */
export function holderDetail(history: TurnSnapshot[]): HolderDetail | null {
  let finance = false;
  let kinds = false;
  for (const snapshot of history) {
    const record = snapshot.finance;
    if (!record) {
      continue;
    }
    finance = true;
    if (record.domestic_credit) {
      if (record.domestic_credit.holders !== undefined) {
        return "lenders";
      }
      kinds = true;
    }
  }
  if (!finance) {
    return null;
  }
  return kinds ? "kinds" : "totals";
}

export interface HolderRow {
  /** Stable key within the borrower (group and name). */
  id: string;
  group: HolderGroup;
  /** The lender: a region (merchants), city, guild or civilization name, or the group's label. */
  label: string;
  amount: number;
  /** A recorded individual lender, even when its name equals a group label. */
  named: boolean;
  /** Rate per turn of the line it holds, when the bundle records it. */
  rate: number | null;
  /** Interest due per turn at that rate. */
  interest: number | null;
  /** Merchants: the region whose merchants hold the claim. */
  region?: string;
  /** Foreign lenders: the lending civilization. */
  civ?: string;
}

export interface CivDebtHolders {
  civ: string;
  turn: number;
  debt: number;
  foreign: number;
  domestic: number;
  /** Smoothed revenue (debt is also read in turns of it). */
  revenue: number;
  groups: Record<HolderGroup, number>;
  rows: HolderRow[];
  /** Interest due per turn at the lines' rates (lenders detail only). */
  interestDue: number | null;
  /** Interest paid in the fiscal tick of this snapshot. */
  interestPaid: number;
  /** Debt written off on this civ so far (lenders detail only). */
  writtenOff: number | null;
  arrears: number;
  defaults: number;
}

function emptyGroups(): Record<HolderGroup, number> {
  return { merchants: 0, city: 0, guild: 0, houses: 0, legacy: 0, domestic: 0, foreign: 0 };
}

function sum(values: Iterable<number>): number {
  let total = 0;
  for (const value of values) {
    total += value;
  }
  return total;
}

function byAmount(left: HolderRow, right: HolderRow): number {
  return HOLDER_GROUPS.indexOf(left.group) - HOLDER_GROUPS.indexOf(right.group)
    || right.amount - left.amount
    || left.label.localeCompare(right.label);
}

/** Who holds one civilization's debt in a snapshot; null when the snapshot has no finance row for it. */
export function civDebtHolders(snapshot: TurnSnapshot | null, civ: string, detail: HolderDetail): CivDebtHolders | null {
  const record = snapshot?.finance;
  const row = record?.civs[civ];
  if (!snapshot || !record || !row) {
    return null;
  }
  const foreign = row.foreign_debt;
  const domestic = Math.max(0, row.debt - row.foreign_debt);
  const rows: HolderRow[] = [];
  const credit = record.domestic_credit;
  const held = detail === "lenders" ? credit?.holders?.[civ] : undefined;
  const push = (group: HolderGroup, label: string, amount: number, rate: number | null, extra: Partial<HolderRow> = {}) => {
    if (amount > 0) {
      rows.push({
        id: `${group}:${extra.named ? "named" : "aggregate"}:${label}`, group, label, amount, named: false,
        rate, interest: rate == null ? null : amount * rate, ...extra,
      });
    }
  };
  if (detail === "totals" || !credit) {
    push("domestic", HOLDER_LABELS.domestic, domestic, null);
    push("foreign", HOLDER_LABELS.foreign, foreign, null);
  } else {
    const kinds = credit.civs[civ] ?? {};
    const rate = held?.rate ?? null;
    const named: Partial<Record<HolderGroup, Record<string, number> | undefined>> = held
      ? { merchants: held.merchants, city: held.cities, guild: held.guilds }
      : {};
    let attributed = 0;
    for (const [kind, amount] of Object.entries(kinds)) {
      const group = KIND_GROUPS[kind] ?? "domestic";
      attributed += amount;
      const parts = named[group];
      if (!parts) {
        push(group, HOLDER_LABELS[group], amount, rate);
        continue;
      }
      for (const [name, part] of Object.entries(parts)) {
        push(group, name, part, rate, { named: true, ...(group === "merchants" ? { region: name } : {}) });
      }
      // A claim the breakdown does not name (none is expected) stays visible.
      push(group, `${HOLDER_LABELS[group]}, not named`, amount - sum(Object.values(parts)), rate);
    }
    push("domestic", `${HOLDER_LABELS.domestic}, not attributed`, domestic - attributed, rate);
    if (held?.foreign) {
      for (const [lender, [principal, lenderRate]] of Object.entries(held.foreign)) {
        push("foreign", lender, principal, lenderRate, { civ: lender, named: true });
      }
      push("foreign", `${HOLDER_LABELS.foreign}, not named`,
        foreign - sum(Object.values(held.foreign).map(([principal]) => principal)), null);
    } else {
      push("foreign", HOLDER_LABELS.foreign, foreign, null);
    }
  }
  rows.sort(byAmount);
  const groups = emptyGroups();
  for (const entry of rows) {
    groups[entry.group] += entry.amount;
  }
  const lenders = detail === "lenders" && !!credit;
  return {
    civ,
    turn: snapshot.turn,
    debt: row.debt,
    foreign,
    domestic,
    revenue: row.revenue_ema,
    groups,
    rows,
    interestDue: lenders && rows.every((entry) => entry.interest != null) ? sum(rows.map((entry) => entry.interest ?? 0)) : null,
    interestPaid: row.interest,
    writtenOff: lenders ? (held?.written_off ?? 0) : null,
    arrears: row.arrears_turns,
    defaults: row.defaults,
  };
}

/** Every civilization in debt at the snapshot, in the given (world) order. */
export function realmsInDebt(snapshot: TurnSnapshot | null, civs: string[], detail: HolderDetail): CivDebtHolders[] {
  return civs
    .map((civ) => civDebtHolders(snapshot, civ, detail))
    .filter((entry): entry is CivDebtHolders => entry !== null && entry.debt > 0);
}

/** Civilizations that owed anything in some snapshot, largest peak debt first. */
export function borrowers(history: TurnSnapshot[], civs: string[], eventBorrowers: string[] = []): string[] {
  const peak = new Map<string, number>();
  for (const snapshot of history) {
    for (const [civ, row] of Object.entries(snapshot.finance?.civs ?? {})) {
      if (row.debt > 0) {
        peak.set(civ, Math.max(peak.get(civ) ?? 0, row.debt));
      }
    }
  }
  const eventNames = new Set(eventBorrowers);
  return civs.filter((civ) => peak.has(civ) || eventNames.has(civ))
    .sort((left, right) => (peak.get(right) ?? 0) - (peak.get(left) ?? 0));
}

/**
 * One chart row per snapshot with the civ's debt per holder group; a
 * snapshot without the civ's finance row is a gap (null), never zero.
 */
export function holderSeries(history: TurnSnapshot[], civ: string, detail: HolderDetail): SeriesRow[] {
  return history.map((snapshot) => {
    const entry = civDebtHolders(snapshot, civ, detail);
    const row: SeriesRow = { turn: snapshot.turn };
    for (const group of HOLDER_GROUPS) {
      row[group] = entry ? entry.groups[group] : null;
    }
    return row;
  });
}

/** Holder groups with any debt in the series, in stacking order. */
export function groupsInSeries(series: SeriesRow[]): HolderGroup[] {
  return HOLDER_GROUPS.filter((group) => series.some((row) => (row[group] ?? 0) > 0));
}

/**
 * The civ's foreign debt per lending civilization over time (lenders
 * detail): lenders in world order, 0 while the civ owes a lender nothing,
 * null where the civ has no finance row.
 */
export function foreignLenderSeries(
  history: TurnSnapshot[], civ: string, worldCivs: string[],
): { lenders: string[]; data: SeriesRow[] } {
  const names = new Set<string>();
  for (const snapshot of history) {
    for (const lender of Object.keys(snapshot.finance?.domestic_credit?.holders?.[civ]?.foreign ?? {})) {
      names.add(lender);
    }
  }
  const lenders = orderedCivNames(worldCivs, names);
  const data = history.map((snapshot) => {
    const row: SeriesRow = { turn: snapshot.turn };
    const present = !!snapshot.finance?.civs[civ];
    const foreign = snapshot.finance?.domestic_credit?.holders?.[civ]?.foreign ?? {};
    for (const lender of lenders) {
      row[lender] = present ? (foreign[lender]?.[0] ?? 0) : null;
    }
    return row;
  });
  return { lenders, data };
}

export interface WriteOff {
  /** Snapshot boundary, or the event turn when no counter row represents it. */
  turn: number;
  /** Recorded counter increase; null when the amount is unavailable. */
  amount: number | null;
  /** A default was recorded since the snapshot before. */
  defaulted: boolean;
  /** The civ's default and write-off events between the two snapshots. */
  events: Event[];
}

const WRITE_OFF_EVENTS = new Set(["state_default", "debt_written_off"]);

/**
 * New event-only attribution requires one unambiguous world civilization.
 * Use the full permanent world list, including fallen realms, and its real
 * indices: index zero is valid. A name collision cannot establish identity.
 */
export function eventOnlyBorrowers(
  events: Event[], worldCivs: readonly { name: string }[], currentTurn: number,
): string[] {
  const indices = new Map<string, number | null>();
  worldCivs.forEach((civ, index) => {
    indices.set(civ.name, indices.has(civ.name) ? null : index);
  });
  const names = new Set<string>();
  for (const event of events) {
    const name = event.actors[0];
    if (event.turn <= currentTurn && WRITE_OFF_EVENTS.has(event.event_type)
      && name !== undefined && indices.has(name) && indices.get(name) !== null) {
      names.add(name);
    }
  }
  return [...names];
}

/**
 * Defaults and write-offs on a civ's debt, snapshot by snapshot: a rise of
 * its default count or of the debt written off on it. A snapshot records the
 * fiscal tick of the turn before it, so the events counted are those after
 * the previous snapshot's tick, up to this one's.
 */
export function writeOffs(
  history: TurnSnapshot[], civ: string, events: Event[], detail: HolderDetail, includeEventOnly = false,
): WriteOff[] {
  const out: WriteOff[] = [];
  const seen = new Set<string | Event>();
  const lossEvents = events.filter((event) => {
    if (!WRITE_OFF_EVENTS.has(event.event_type) || event.actors[0] !== civ) {
      return false;
    }
    const key = event.event_id ?? event;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
  const represented = new Set<Event>();
  let previousTurn: number | null = null;
  let defaults = 0;
  let written = 0;
  for (const snapshot of history) {
    const entry = civDebtHolders(snapshot, civ, detail);
    if (!entry) {
      continue;
    }
    const delta = entry.writtenOff == null ? null : entry.writtenOff - written;
    const amount = delta != null && delta >= 0 ? delta : null;
    const defaulted = entry.defaults > defaults;
    if (defaulted || (amount ?? 0) > 0) {
      const from = previousTurn == null ? Number.NEGATIVE_INFINITY : previousTurn - 1;
      const matched = lossEvents.filter((event) => event.turn > from && event.turn <= snapshot.turn - 1);
      matched.forEach((event) => represented.add(event));
      out.push({ turn: snapshot.turn, amount, defaulted, events: matched });
    }
    previousTurn = snapshot.turn;
    defaults = entry.defaults;
    written = entry.writtenOff ?? written;
  }
  if (includeEventOnly) {
    const byTurn = new Map<number, Event[]>();
    for (const event of lossEvents) {
      if (!represented.has(event)) {
        const atTurn = byTurn.get(event.turn) ?? [];
        atTurn.push(event);
        byTurn.set(event.turn, atTurn);
      }
    }
    for (const [turn, atTurn] of byTurn) {
      out.push({ turn, amount: null, defaulted: atTurn.some((event) => event.event_type === "state_default"), events: atTurn });
    }
  }
  return out.sort((left, right) => left.turn - right.turn);
}

/** Strip rows for a civ: turns in arrears, defaults, and (lenders detail) write-offs. */
export function troubleRows(history: TurnSnapshot[], civ: string, detail: HolderDetail): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  const entries = history.map((snapshot) => civDebtHolders(snapshot, civ, detail));
  const arrearsKeys = entries.map((entry) => (entry && entry.arrears > 0 ? "arrears" : null));
  const arrears = buildSegments(turns, arrearsKeys).map((segment) => {
    const longest = Math.max(...entries.slice(segment.from, segment.to + 1).map((entry) => entry?.arrears ?? 0));
    return {
      start: segment.start,
      end: segment.end,
      color: ARREARS_COLOR,
      label: `${civ}: in arrears, turns ${segment.start}-${segment.end - 1} (up to ${longest} turn${longest === 1 ? "" : "s"} running)`,
    };
  });
  const rises = (value: (entry: CivDebtHolders) => number | null) => {
    let before = 0;
    return entries.map((entry, index) => {
      if (!entry) {
        return null;
      }
      const now = value(entry);
      if (now == null) {
        return null;
      }
      const key = now > before ? `${index}:${now - before}` : null;
      before = now;
      return key;
    });
  };
  const defaults = buildSegments(turns, rises((entry) => entry.defaults)).map((segment) => ({
    start: segment.start,
    end: segment.end,
    color: DEFAULT_COLOR,
    label: `${civ}: default recorded at turn ${segment.start}`,
  }));
  const rows: StripRow[] = [
    { id: "arrears", label: "In arrears", swatch: ARREARS_COLOR, segments: arrears },
    { id: "defaults", label: "Defaults", swatch: DEFAULT_COLOR, segments: defaults },
  ];
  if (detail === "lenders") {
    const written = buildSegments(turns, rises((entry) => entry.writtenOff)).map((segment) => ({
      start: segment.start,
      end: segment.end,
      color: WRITE_OFF_COLOR,
      label: `${civ}: ${segment.key.split(":")[1]} written off by turn ${segment.start}`,
    }));
    rows.push({ id: "written_off", label: "Written off", swatch: WRITE_OFF_COLOR, segments: written });
  }
  return rows;
}

/** Finance events naming the civ (as borrower or lender), up to the turn, latest first. */
export function creditEventsOf(events: Event[], civ: string): Event[] {
  return events.filter((event) => event.actors.includes(civ) || (event.civs ?? []).includes(civ));
}

/** What the bundle's level of detail leaves out, for the panel's note. */
export const DETAIL_NOTES: Record<HolderDetail, string> = {
  lenders: "Foreign lenders by name, merchants by region, cities and guilds by name, as recorded at each turn. "
    + "Interest due is principal times the line's rate; a domestic line's interest is shared pro rata to the claims.",
  kinds: "This bundle records domestic claims by kind of lender only (written before the per-lender record): "
    + "foreign debt is one total and interest by lender is not recorded.",
  totals: "This run had no --domestic-credit: domestic loans come from finance's abstract creditor class, "
    + "and foreign debt is one total. Lenders by name need a bundle written with --domestic-credit.",
};
