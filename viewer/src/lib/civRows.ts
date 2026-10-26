/**
 * Civilization rows across a history whose snapshots may leave civilizations out.
 *
 * Bundle version 5 drops a civilization from `history[n].civ_stats` (and its
 * capital and pairwise entries) once it is dead at that turn: no regions and
 * no government in exile that could be restored. The snapshot in which it
 * dies keeps its final row. Snapshots taken before a civilization is founded
 * never had its row. Older bundles carry every row; these helpers read both.
 *
 * - `civRowAt` gives a civilization's latest row at or before a turn, so the
 *   inspector shows a dead civilization's final state rather than the
 *   end-of-run world state.
 * - `civStatSeries` gives one value per snapshot, `null` where the
 *   civilization has no row, so a chart's line ends where its rows end.
 */
import type { CivSnapshot, TurnSnapshot } from "../types";

export type NumericCivStat = keyof Pick<
  CivSnapshot,
  "population" | "military" | "economy" | "culture" | "stability" | "treasury" | "asabiya"
>;

export interface CivRowAt {
  /** The latest row at or before the requested turn. */
  row: CivSnapshot;
  /** Turn of the snapshot that holds the row. */
  turn: number;
  /** The civilization is in the snapshot shown for the requested turn. */
  recorded: boolean;
}

interface CivRowIndex {
  turns: number[];
  byCiv: Map<string, { positions: number[]; rows: CivSnapshot[] }>;
}

const indexCache = new WeakMap<TurnSnapshot[], CivRowIndex>();

function rowIndex(history: TurnSnapshot[]): CivRowIndex {
  const cached = indexCache.get(history);
  if (cached) {
    return cached;
  }
  const byCiv: CivRowIndex["byCiv"] = new Map();
  history.forEach((snapshot, position) => {
    for (const [name, row] of Object.entries(snapshot.civ_stats ?? {})) {
      let entry = byCiv.get(name);
      if (!entry) {
        entry = { positions: [], rows: [] };
        byCiv.set(name, entry);
      }
      entry.positions.push(position);
      entry.rows.push(row);
    }
  });
  const index = { turns: history.map((snapshot) => snapshot.turn), byCiv };
  indexCache.set(history, index);
  return index;
}

/** Index of the last element `<= value` in an ascending list, or -1. */
function lastAtOrBefore(values: number[], value: number): number {
  let low = 0;
  let high = values.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (values[middle] <= value) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
}

/**
 * Position of the snapshot shown for `turn`: the last one at or before it.
 * -1 without history or when the turn precedes the first snapshot (a resumed
 * run's history starts late): no later snapshot stands in for it.
 */
export function snapshotPositionAt(history: TurnSnapshot[], turn: number): number {
  if (history.length === 0) {
    return -1;
  }
  return lastAtOrBefore(rowIndex(history).turns, turn);
}

/** A civilization's latest row at or before `turn`, or null before it exists. */
export function civRowAt(history: TurnSnapshot[], civName: string, turn: number): CivRowAt | null {
  const position = snapshotPositionAt(history, turn);
  if (position < 0) {
    return null;
  }
  const entry = rowIndex(history).byCiv.get(civName);
  if (!entry) {
    return null;
  }
  const at = lastAtOrBefore(entry.positions, position);
  if (at < 0) {
    return null;
  }
  return {
    row: entry.rows[at],
    turn: history[entry.positions[at]].turn,
    recorded: entry.positions[at] === position,
  };
}

/**
 * A civilization's row for display at `turn`. A civilization missing from
 * that snapshot after it had rows is dead there: its final row, with no
 * regions and `alive: false`.
 */
export function civDisplayRow(history: TurnSnapshot[], civName: string, turn: number): CivSnapshot | null {
  const found = civRowAt(history, civName, turn);
  if (!found) {
    return null;
  }
  return found.recorded ? found.row : { ...found.row, alive: false, regions: [] };
}

/**
 * Faction influence in the order the simulation declares the factions
 * (`models.FactionType`); burghers appear only for realms that have them
 * (`--guilds`).
 */
export const FACTION_ORDER = ["military", "merchant", "cultural", "clergy", "burgher"] as const;
export const FACTION_COLORS: Record<string, string> = {
  military: "#d9644a",
  merchant: "#e8b84a",
  cultural: "#5a8fd9",
  clergy: "#b07ad9",
  burgher: "#5aa88f",
};

/** A civ's faction influence at a snapshot row, in declaration order ([] unrecorded). */
export function factionShares(influence: Record<string, number> | undefined | null): [string, number][] {
  if (!influence) return [];
  const order: readonly string[] = FACTION_ORDER;
  const known = order.filter((name) => name in influence).map((name) => [name, influence[name]] as [string, number]);
  const other = Object.entries(influence).filter(([name]) => !order.includes(name));
  return [...known, ...other];
}

/** One value per snapshot; `null` where the civilization has no row. */
export function civStatSeries<K extends keyof CivSnapshot>(
  history: TurnSnapshot[],
  civName: string,
  key: K,
): (CivSnapshot[K] | null)[] {
  return history.map((snapshot) => {
    const row = snapshot.civ_stats?.[civName];
    return row ? row[key] : null;
  });
}

/**
 * Chart rows, one per snapshot: `turn` plus each civilization's `key` value
 * (and `<civ>_cmp` for `compareKey`). A civilization without a row has
 * `null`, which a line chart draws as the end (or start) of its line.
 */
export function civChartRows(
  history: TurnSnapshot[],
  civNames: string[],
  key: NumericCivStat,
  compareKey?: NumericCivStat,
): Record<string, number | null>[] {
  return history.map((snapshot) => {
    const row: Record<string, number | null> = { turn: snapshot.turn };
    for (const name of civNames) {
      const civ = snapshot.civ_stats?.[name];
      row[name] = civ ? civ[key] : null;
      if (compareKey) {
        row[`${name}_cmp`] = civ ? civ[compareKey] : null;
      }
    }
    return row;
  });
}
