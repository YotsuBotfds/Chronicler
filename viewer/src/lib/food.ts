/**
 * Read-only helpers for famine, food and migration: famine spans from the
 * event timeline (bundle version 4+ events carry `region` and `episode`),
 * and the optional `history[n].food` and `history[n].migration` fields.
 * Nothing is inferred that the bundle does not record.
 */
import type { Bundle, Event, TurnSnapshot } from "../types";
import type { StripRow } from "./systems";

export const FAMINE_COLOR = "#d95926";
export const SHORT_COLOR = "#c98500";
export const FED_COLOR = "#3c4a3e";
export const AID_COLOR = "#199e70";
export const MIGRATION_COLOR = "#7ebec3";

/** Below this, food on hand does not cover the people (sufficiency is food / need, 0-2). */
export const SHORT_OF_FOOD = 1;

export interface FamineSpan {
  region: string;
  /** Turn of the onset event. */
  start: number;
  /** Turn of the `famine_ended` event, or null while it lasts at the end of the record. */
  end: number | null;
  /** Famine reports (onset and repeats) inside the span. */
  reports: number;
  onsetId?: string;
}

/**
 * Famine spans per region: an onset opens one, `famine_ended` in the same
 * region closes it. Bundles whose famine events carry no region or episode
 * (version 3 and older) have no spans.
 */
export function famineSpans(events: Event[]): FamineSpan[] {
  const open = new Map<string, FamineSpan>();
  const spans: FamineSpan[] = [];
  for (const event of events) {
    const region = event.region;
    if (!region) {
      continue;
    }
    if (event.event_type === "famine") {
      const current = open.get(region);
      if (event.episode === "onset") {
        if (current) {
          // A new onset without a recorded end: close the old span there.
          current.end = event.turn;
          spans.push(current);
        }
        open.set(region, { region, start: event.turn, end: null, reports: 1, onsetId: event.event_id });
      } else if (current) {
        current.reports += 1;
      }
    } else if (event.event_type === "famine_ended") {
      const current = open.get(region);
      if (current) {
        current.end = event.turn;
        spans.push(current);
        open.delete(region);
      }
    }
  }
  spans.push(...open.values());
  return spans.sort((left, right) => left.start - right.start || left.region.localeCompare(right.region));
}

/** True when the bundle records famine with regions (spans can be drawn). */
export function hasFamineRecord(events: Event[]): boolean {
  return events.some((event) => event.event_type === "famine" && !!event.region && !!event.episode);
}

/** Spans running at `turn` (started at or before it, not yet ended). */
export function faminesAt(spans: FamineSpan[], turn: number): FamineSpan[] {
  return spans.filter((span) => span.start <= turn && (span.end === null || span.end > turn));
}

/** One strip row per region that had a famine, in region index order. */
export function famineRows(spans: FamineSpan[], regionOrder: string[], lastTurn: number): StripRow[] {
  const byRegion = new Map<string, FamineSpan[]>();
  for (const span of spans) {
    byRegion.set(span.region, [...(byRegion.get(span.region) ?? []), span]);
  }
  const rank = new Map(regionOrder.map((name, index) => [name, index]));
  return [...byRegion.entries()]
    .sort((left, right) => (rank.get(left[0]) ?? Number.MAX_SAFE_INTEGER) - (rank.get(right[0]) ?? Number.MAX_SAFE_INTEGER)
      || left[0].localeCompare(right[0]))
    .map(([region, list]) => ({
      id: region,
      label: region,
      segments: list.map((span) => {
        const end = span.end ?? lastTurn + 1;
        return {
          start: span.start,
          end,
          color: FAMINE_COLOR,
          label: `${region}: famine, turns ${span.start}-${end - 1}${span.end === null ? " (still running)" : ""}`
            + ` · ${span.reports} report${span.reports === 1 ? "" : "s"}`,
        };
      }),
    }));
}

/** Region name -> food sufficiency at the snapshot (only observed regions). */
export function sufficiencyByRegion(snapshot: TurnSnapshot | null, regionNames: string[]): Map<string, number> {
  const values = new Map<string, number>();
  snapshot?.food?.sufficiency.forEach((value, index) => {
    const name = regionNames[index];
    if (name && value !== null && value !== undefined) {
      values.set(name, value);
    }
  });
  return values;
}

export interface NamedFlow {
  from: string;
  to: string;
  amount: number;
}

/** Relief convoys of the completed turn, by region name. */
export function aidFlows(snapshot: TurnSnapshot | null, regionNames: string[]): NamedFlow[] {
  return (snapshot?.food?.aid ?? [])
    .map(([donor, recipient, amount]) => ({ from: regionNames[donor], to: regionNames[recipient], amount }))
    .filter((flow) => !!flow.from && !!flow.to);
}

/** True when any snapshot carries the food field. */
export function hasFoodRecord(history: TurnSnapshot[]): boolean {
  return history.some((snapshot) => snapshot.food != null);
}

/** Per snapshot: regions short of food (needs the food field) and regions in famine. */
export function foodSeries(history: TurnSnapshot[], spans: FamineSpan[]): Array<{ turn: number } & Record<string, number | null>> {
  return history.map((snapshot) => {
    const short = snapshot.food
      ? snapshot.food.sufficiency.filter((value) => value !== null && value < SHORT_OF_FOOD).length
      : null;
    return { turn: snapshot.turn, "Short of food": short, "In famine": faminesAt(spans, snapshot.turn).length };
  });
}

export function hasMigrationRecord(history: TurnSnapshot[]): boolean {
  return history.some((snapshot) => snapshot.migration != null);
}

/**
 * Agent migrations summed over the snapshots in (turn - window, turn], by
 * region pair, largest first. Snapshots without the field add nothing.
 */
export function migrationFlows(
  history: TurnSnapshot[],
  turn: number,
  window: number,
  regionNames: string[],
): NamedFlow[] {
  const totals = new Map<string, NamedFlow>();
  for (const snapshot of history) {
    if (snapshot.turn > turn || snapshot.turn <= turn - window) {
      continue;
    }
    for (const [from, to, agents] of snapshot.migration ?? []) {
      const fromName = regionNames[from];
      const toName = regionNames[to];
      if (!fromName || !toName) {
        continue;
      }
      const key = `${from}>${to}`;
      const entry = totals.get(key) ?? { from: fromName, to: toName, amount: 0 };
      entry.amount += agents;
      totals.set(key, entry);
    }
  }
  return [...totals.values()].sort((left, right) => right.amount - left.amount || left.from.localeCompare(right.from)
    || left.to.localeCompare(right.to));
}

/** Net agents gained per region over the same window (arrivals minus departures). */
export function netMigration(flows: NamedFlow[]): Map<string, number> {
  const net = new Map<string, number>();
  for (const flow of flows) {
    net.set(flow.from, (net.get(flow.from) ?? 0) - flow.amount);
    net.set(flow.to, (net.get(flow.to) ?? 0) + flow.amount);
  }
  return net;
}

export function regionNamesOf(bundle: Bundle): string[] {
  return bundle.world_state.regions.map((region) => region.name);
}
