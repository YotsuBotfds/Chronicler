/**
 * Read-only helpers for cities (`history[n].cities`, `world_state.cities`;
 * `--cities`). A city's identity is its settlement id; names repeat only for
 * a refounded settlement, which has a new id. Nothing here infers a value the
 * bundle does not record: a city absent from a snapshot is not living there.
 */
import type { Bundle, CityRecord, CitySnapshotRow, Event, TurnSnapshot } from "../types";
import { buildSegments, type StripRow } from "./systems";

const LIGHT_INK = "#f0efec";
const DARK_INK = "#0b0b0b";

/** `cities_state.RANK_NAMES` (rank 0 is a settlement below town size). */
export const RANK_LABELS = ["settlement", "town", "city", "great city"] as const;
/** `cities_state.CHARTER_NAMES`. */
export const CHARTER_LABELS = ["none", "market rights", "self-government", "free city"] as const;

/** Ordinal by rank: town light, great city strongest. */
export const RANK_COLORS: Record<number, string> = {
  1: "#7d8a96",
  2: "#c2924a",
  3: "#e8b84a",
};

export function rankLabel(rank: number): string {
  return RANK_LABELS[rank] ?? `rank ${rank}`;
}

export function charterLabel(charter: number): string {
  return CHARTER_LABELS[charter] ?? `charter ${charter}`;
}

/**
 * Wares a city made in the snapshot's turn, to the snapshot's two decimals (most
 * loads are a fraction of a unit; one decimal showed 0.03 as "0.0"); "-" where
 * the bundle predates crafts.
 */
export function waresLabel(row: CitySnapshotRow): string {
  return row.crafts == null ? "-" : row.crafts.toFixed(2);
}

export interface CityKey {
  id: number;
  name: string;
}

/** Every city that was ever living in a snapshot, in order of first appearance (then id). */
export function cityKeys(history: TurnSnapshot[]): CityKey[] {
  const seen = new Map<number, string>();
  for (const snapshot of history) {
    for (const row of snapshot.cities?.cities ?? []) {
      if (!seen.has(row.id)) {
        seen.set(row.id, row.name);
      }
    }
  }
  return [...seen.entries()].map(([id, name]) => ({ id, name }));
}

/** The city's row in a snapshot, or null when it is not living there. */
export function cityRow(snapshot: TurnSnapshot | null | undefined, id: number): CitySnapshotRow | null {
  return snapshot?.cities?.cities.find((row) => row.id === id) ?? null;
}

/** One strip row per city: its rank over the snapshots it lived in. */
export function cityRankRows(history: TurnSnapshot[], keys: CityKey[]): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  return keys.map(({ id, name }) => {
    const ranks = history.map((snapshot) => {
      const row = cityRow(snapshot, id);
      return row ? String(row.rank) : null;
    });
    const segments = buildSegments(turns, ranks).map((segment) => {
      const rank = Number(segment.key);
      return {
        start: segment.start,
        end: segment.end,
        color: RANK_COLORS[rank] ?? RANK_COLORS[1],
        label: `${name}: ${rankLabel(rank)}, turns ${segment.start}-${segment.end - 1}`,
        text: rankLabel(rank),
        textColor: rank >= 2 ? DARK_INK : LIGHT_INK,
      };
    });
    return { id: String(id), label: name, segments };
  });
}

export type CitySeriesRow = { turn: number } & Record<string, number | null>;

/** One chart row per snapshot with the city's value under `key`; null where it is not living. */
export function citySeries(
  history: TurnSnapshot[],
  id: number,
  key: string,
  value: (row: CitySnapshotRow) => number,
): CitySeriesRow[] {
  return history.map((snapshot) => {
    const row = cityRow(snapshot, id);
    return { turn: snapshot.turn, [key]: row ? value(row) : null } as CitySeriesRow;
  });
}

/** The city's final record in `world_state.cities` (living or fallen), if the bundle carries it. */
export function cityRecord(bundle: Bundle, id: number): CityRecord | null {
  const state = bundle.world_state.cities;
  if (!state) {
    return null;
  }
  return [...(state.cities ?? []), ...(state.fallen ?? [])].find((city) => city.settlement_id === id) ?? null;
}

/** A city's record as known at `upToTurn` (never a value the record dates later). */
export interface CityRecordAt {
  record: CityRecord;
  /** Highest rank, residents and purse in its history rows up to `upToTurn`; 0 before its first row. */
  peakRank: number;
  peakResidents: number;
  peakWealth: number;
  /** Whether it had fallen by `upToTurn`. */
  fell: boolean;
}

/**
 * The city's founding, its peaks so far and its fall if it fell by
 * `upToTurn`; null before its founding. The final `world_state` record holds
 * the whole run (its peaks and fall), so only what it dates at or before the
 * turn is used, and the peaks come from the history rows (as
 * `learning.seatRecordAt`).
 */
export function cityRecordAt(bundle: Bundle, id: number, upToTurn: number): CityRecordAt | null {
  const record = cityRecord(bundle, id);
  if (!record || record.founded_turn > upToTurn) {
    return null;
  }
  let peakRank = 0;
  let peakResidents = 0;
  let peakWealth = 0;
  for (const snapshot of bundle.history) {
    if (snapshot.turn > upToTurn) {
      continue;
    }
    const row = cityRow(snapshot, id);
    if (row) {
      peakRank = Math.max(peakRank, row.rank);
      peakResidents = Math.max(peakResidents, row.residents);
      peakWealth = Math.max(peakWealth, row.wealth);
    }
  }
  const fell = record.fallen_turn != null && record.fallen_turn <= upToTurn;
  return { record, peakRank, peakResidents, peakWealth, fell };
}

export interface CityMoment {
  turn: number;
  kind: string;
  event: Event | null;
}

/** The city's recorded moments up to `upToTurn`, latest first, with the event the simulation wrote. */
export function cityHistory(bundle: Bundle, id: number, upToTurn: number): CityMoment[] {
  const record = cityRecord(bundle, id);
  if (!record) {
    return [];
  }
  const byId = new Map<string, Event>();
  for (const event of bundle.events_timeline) {
    if (event.event_id) {
      byId.set(event.event_id, event);
    }
  }
  return record.history
    .filter(([turn]) => turn <= upToTurn)
    .map(([turn, kind, eventId]) => ({ turn, kind, event: byId.get(eventId) ?? null }))
    .reverse();
}

/** Running totals shown in the Cities tab (`cities_state.COUNTER_KEYS`, a subset). */
export const CITY_COUNTERS: Array<[string, string]> = [
  ["founded", "Cities founded"],
  ["fallen", "Cities fallen"],
  ["charters", "Charters granted"],
  ["refusals", "Charters refused"],
  ["revolts", "Urban revolts"],
  ["free_cities", "Free cities"],
  ["sacks", "Sacks"],
  ["walls", "Walls built"],
  ["dues", "Dues paid to lords"],
  ["commerce", "Commerce"],
];
