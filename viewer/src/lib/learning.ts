/**
 * Read-only helpers for seats of learning (`history[n].scholarship`,
 * `world_state.scholarship`; `--scholarship`). A seat's identity is its index
 * in the world's seat list. Nothing here infers a value the bundle does not
 * record: a seat absent from a snapshot is not standing there.
 */
import type { Bundle, Event, SeatRecord, SeatSnapshotRow, TurnSnapshot } from "../types";
import { buildSegments, type StripRow } from "./systems";

const LIGHT_INK = "#f0efec";
const DARK_INK = "#0b0b0b";

/** `scholarship_state.LEVEL_NAMES` (level 0 is a fallen seat). */
export const LEVEL_LABELS = ["fallen", "modest", "renowned", "great"] as const;
/** `scholarship_state.KIND_NAMES`. */
export const KIND_LABELS = ["academy", "temple school", "library"] as const;
/** `scholarship_state.FALL_CAUSES`. */
export const FALL_LABELS = ["sacked", "famine", "persecution", "loss of patronage"] as const;
/** Who keeps a seat, by kind. */
export const PATRON_LABELS: Record<string, string> = {
  academy: "its ruler",
  "temple school": "its temple",
  library: "its city",
};

/** Ordinal by level: modest light, great strongest. */
export const LEVEL_COLORS: Record<number, string> = {
  1: "#6f8fa8",
  2: "#9a7fc4",
  3: "#d4a94a",
};

export function levelLabel(level: number): string {
  return LEVEL_LABELS[level] ?? `level ${level}`;
}

/** The living seats at a snapshot, or [] (none, or a run without seats of learning). */
export function seatsAt(snapshot: TurnSnapshot | null | undefined): SeatSnapshotRow[] {
  return snapshot?.scholarship?.seats ?? [];
}

/** Its standing in one cell: unpaid upkeep and refugees, "-" for neither. */
export function seatStanding(row: SeatSnapshotRow): string {
  const parts: string[] = [];
  if (row.unpaid) parts.push(`upkeep unpaid (${row.unpaid})`);
  if (row.refugees) parts.push(`${row.refugees.toFixed(1)} refugees`);
  return parts.length ? parts.join(", ") : "-";
}

export interface SeatKey {
  id: number;
  name: string;
}

/** Every seat that ever stood in a snapshot, in order of first appearance. */
export function seatKeys(history: TurnSnapshot[]): SeatKey[] {
  const seen = new Map<number, string>();
  for (const snapshot of history) {
    for (const row of seatsAt(snapshot)) {
      if (!seen.has(row.id)) {
        seen.set(row.id, row.name);
      }
    }
  }
  return [...seen.entries()].map(([id, name]) => ({ id, name }));
}

/** The seat's row in a snapshot, or null when it is not standing there. */
export function seatRow(snapshot: TurnSnapshot | null | undefined, id: number): SeatSnapshotRow | null {
  return seatsAt(snapshot).find((row) => row.id === id) ?? null;
}

/** One strip row per seat: its level over the snapshots it stood in. */
export function seatLevelRows(history: TurnSnapshot[], keys: SeatKey[]): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  return keys.map(({ id, name }) => {
    const levels = history.map((snapshot) => {
      const row = seatRow(snapshot, id);
      return row ? String(row.level) : null;
    });
    const segments = buildSegments(turns, levels).map((segment) => {
      const level = Number(segment.key);
      return {
        start: segment.start,
        end: segment.end,
        color: LEVEL_COLORS[level] ?? LEVEL_COLORS[1],
        label: `${name}: ${levelLabel(level)}, turns ${segment.start}-${segment.end - 1}`,
        text: levelLabel(level),
        textColor: level >= 3 ? DARK_INK : LIGHT_INK,
      };
    });
    return { id: String(id), label: name, segments };
  });
}

export type SeatSeriesRow = { turn: number } & Record<string, number | null>;

/** One chart row per snapshot with the seat's scholars under `key`; null where it is not standing. */
export function seatScholarSeries(history: TurnSnapshot[], id: number, key: string): SeatSeriesRow[] {
  return history.map((snapshot) => {
    const row = seatRow(snapshot, id);
    return { turn: snapshot.turn, [key]: row ? row.scholars : null } as SeatSeriesRow;
  });
}

/** The seat's final record in `world_state.scholarship`, if the bundle carries it. */
export function seatRecord(bundle: Bundle, id: number): SeatRecord | null {
  return bundle.world_state.scholarship?.seats?.[id] ?? null;
}

/** A seat's record as known at `upToTurn` (never a value the record dates later). */
export interface SeatRecordAt {
  record: SeatRecord;
  /** Highest level and scholars in the history rows up to `upToTurn`; 0 before its first row. */
  peakLevel: number;
  peakScholars: number;
  /** Whether it had fallen by `upToTurn`. */
  fell: boolean;
}

/**
 * The seat's founding, its peak so far and its fall if it fell by `upToTurn`;
 * null before its founding. The final `world_state` record holds the whole run
 * (peak, fall, refuge), so only what it dates at or before the turn is used,
 * and the peak comes from the history rows (lib/civilizationViews convention).
 */
export function seatRecordAt(bundle: Bundle, id: number, upToTurn: number): SeatRecordAt | null {
  const record = seatRecord(bundle, id);
  if (!record || record.founded_turn > upToTurn) {
    return null;
  }
  let peakLevel = 0;
  let peakScholars = 0;
  for (const snapshot of bundle.history) {
    if (snapshot.turn > upToTurn) {
      continue;
    }
    const row = seatsAt(snapshot).find((seat) => seat.id === id);
    if (row) {
      peakLevel = Math.max(peakLevel, row.level);
      peakScholars = Math.max(peakScholars, row.scholars);
    }
  }
  const fell = record.fallen_turn != null && record.fallen_turn <= upToTurn;
  return { record, peakLevel, peakScholars, fell };
}

/** "fell at turn 212 (sacked); its scholars fled to the Academy of X", or "". */
export function fallLabel(bundle: Bundle, record: SeatRecord): string {
  if (record.fallen_turn == null) {
    return "";
  }
  let text = `fell at turn ${record.fallen_turn} (${FALL_LABELS[record.fall_cause] ?? "fallen"})`;
  const refuge = record.refuge >= 0 ? seatRecord(bundle, record.refuge) : null;
  if (refuge) {
    text += `; its scholars fled to ${refuge.name}`;
  }
  return text;
}

export interface SeatMoment {
  turn: number;
  kind: string;
  event: Event | null;
}

/** The seat's recorded moments up to `upToTurn`, latest first, with the event the simulation wrote. */
export function seatHistory(bundle: Bundle, id: number, upToTurn: number): SeatMoment[] {
  const record = seatRecord(bundle, id);
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

/** Running totals shown in the Learning tab (`scholarship_state.COUNTER_KEYS`, a subset). */
export const SEAT_COUNTERS: Array<[string, string]> = [
  ["founded", "Seats founded"],
  ["rises", "Rises"],
  ["declines", "Declines"],
  ["fallen", "Seats fallen"],
  ["fall_sack", "Fallen in a sack"],
  ["fall_famine", "Fallen in famine"],
  ["fall_persecution", "Closed by persecution"],
  ["fall_patronage", "Fallen for want of a patron"],
  ["refuges", "Flights to another seat"],
  ["carried", "Techniques carried by refugees"],
];
