import {
  actorEventsUpTo, eventKey, eventsOfType, eventsUpTo, provenanceOf, type IndexedEvent,
} from "../../lib/bundleIndex";
import { observationEventKnown } from "../../lib/observedSystems";

/**
 * The header's setup line for a loaded bundle without a scenario: what kind of
 * world it records (procedural worlds carry `world_state.geography`).
 */
export function bundleWorldKind(worldState: { geography?: unknown } | null | undefined): string {
  return worldState?.geography ? "Procedural world" : "Template world";
}

export function turnToPercent(turn: number, maxTurn: number): number {
  if (maxTurn <= 1) {
    return 0;
  }
  return ((turn - 1) / (maxTurn - 1)) * 100;
}

/** The box the region pins occupy, in their own coordinates. */
export interface PinFrame {
  x0: number;
  y0: number;
  /** Width and height of the box (never zero). */
  sx: number;
  sy: number;
}

/**
 * Bounds of the region map pins, so the atlas fills its canvas whatever the
 * coordinate range: generated worlds place regions on a 0-100 map (often
 * using only part of it), hand-made demo data uses 0-1. Missing coordinates
 * are ignored; with no pins the frame is the unit square.
 */
export function pinFrame(points: Array<{ x?: number | null; y?: number | null }>): PinFrame {
  const finite = (value: number | null | undefined): value is number => typeof value === "number" && Number.isFinite(value);
  const xs = points.map((point) => point.x).filter(finite);
  const ys = points.map((point) => point.y).filter(finite);
  if (xs.length === 0 || ys.length === 0) {
    return { x0: 0, y0: 0, sx: 1, sy: 1 };
  }
  const span = (values: number[]) => Math.max(...values) - Math.min(...values);
  // A single pin, or pins on one line, keep a nominal extent around them.
  const fallback = Math.max(span(xs), span(ys), 1e-6);
  const sx = span(xs) > 0 ? span(xs) : fallback;
  const sy = span(ys) > 0 ? span(ys) : fallback;
  return {
    x0: span(xs) > 0 ? Math.min(...xs) : Math.min(...xs) - sx / 2,
    y0: span(ys) > 0 ? Math.min(...ys) : Math.min(...ys) - sy / 2,
    sx,
    sy,
  };
}

/** A map position in the pins' coordinates, placed in the atlas viewBox (1000 x 640). */
export function atlasPoint(x: number, y: number, frame: PinFrame): { x: number; y: number } {
  return { x: 90 + ((x - frame.x0) / frame.sx) * 820, y: 80 + ((y - frame.y0) / frame.sy) * 480 };
}

/**
 * Region node radius on the atlas: area follows carrying capacity relative
 * to the largest region shown, under a ceiling that shrinks as the map holds
 * more regions, so nodes stay apart on both 6-region and 150-region worlds.
 */
export function regionNodeRadius(
  capacity: number | null | undefined,
  maxCapacity: number,
  regionCount: number,
): number {
  const ceiling = Math.max(8, Math.min(40, 160 / Math.sqrt(Math.max(regionCount, 1))));
  const share = maxCapacity > 0 ? Math.min(1, Math.max(0, capacity ?? 0) / maxCapacity) : 0.5;
  return ceiling * (0.4 + 0.6 * Math.sqrt(share));
}

export function percentToTurn(percent: number, maxTurn: number): number {
  if (maxTurn <= 1) {
    return 1;
  }
  const clampedPercent = Math.max(0, Math.min(1, percent));
  return Math.round(clampedPercent * (maxTurn - 1)) + 1;
}

type TradeRelationshipLike = {
  disposition?: string;
  trade_volume?: number;
};

export function buildTradeLinks(
  centroids: Record<string, { x: number; y: number }>,
  relationships: Record<string, Record<string, TradeRelationshipLike>> | null,
  civNames: string[],
  tradeRoutes: Array<[string, string]> | null = null,
): Array<{ key: string; source: { x: number; y: number }; target: { x: number; y: number }; strength: number }> {
  const links: Array<{ key: string; source: { x: number; y: number }; target: { x: number; y: number }; strength: number }> = [];
  const seen = new Set<string>();

  if (tradeRoutes !== null) {
    for (const [civName, other] of tradeRoutes) {
      const key = [civName, other].sort().join("--");
      if (seen.has(key) || !centroids[civName] || !centroids[other]) {
        continue;
      }
      seen.add(key);
      links.push({
        key,
        source: centroids[civName],
        target: centroids[other],
        strength: 1.0,
      });
    }
    return links;
  }

  for (const civName of civNames) {
    const relationMap = relationships?.[civName] ?? {};
    for (const [other, relation] of Object.entries(relationMap)) {
      const key = [civName, other].sort().join("--");
      if (seen.has(key) || !centroids[civName] || !centroids[other]) {
        continue;
      }
      seen.add(key);
      const strength = (relation.trade_volume ?? 0) > 0
        ? (relation.trade_volume ?? 0)
        : relation.disposition === "friendly" || relation.disposition === "allied"
          ? 0.6
          : 0;
      if (strength <= 0) {
        continue;
      }
      links.push({
        key,
        source: centroids[civName],
        target: centroids[other],
        strength,
      });
    }
  }

  return links;
}

type ProvenanceEventLike = {
  turn: number;
  event_type: string;
  event_id?: string;
  causes?: string[];
};

export { eventKey };

/**
 * Recorded provenance of one event (bundle version 4+): the events it cites
 * as causes and the events that cite it, in timeline order. Both are empty
 * for older bundles. With `upToTurn`, only the events recorded by then (as
 * the event log). The timeline's ids are indexed once (`lib/bundleIndex`).
 */
export function eventProvenance<E extends ProvenanceEventLike>(
  events: E[],
  selected: E | null,
  upToTurn?: number,
  sourceTurn = upToTurn === undefined ? undefined : upToTurn - 1,
): { causes: E[]; effects: E[] } {
  if (!selected?.event_id) {
    return { causes: [], effects: [] };
  }
  if (sourceTurn !== undefined && !observationEventKnown(selected, sourceTurn)) return { causes: [], effects: [] };
  const result = provenanceOf(events, selected, upToTurn);
  return sourceTurn === undefined ? result : {
    causes: result.causes.filter((event) => observationEventKnown(event, sourceTurn)),
    effects: result.effects.filter((event) => observationEventKnown(event, sourceTurn)),
  };
}

/** Events the Event Log lists. */
export const EVENT_FEED_LIMIT = 24;
/** A focused civilization with fewer events by the turn has the latest others added. */
const EVENT_FEED_FOCUS_MIN = 8;

/**
 * The Event Log at `currentTurn`: the 24 latest events recorded by then
 * (latest first, timeline order within a turn). With a civilization in
 * focus, its own events first; when it has fewer than 8 by then, the latest
 * others follow, up to 24. Read from indexes built once per timeline.
 */
export function buildEventFeed<E extends IndexedEvent>(
  events: E[],
  currentTurn: number,
  focusCivilization: string | null,
  sourceTurn = currentTurn - 1,
): E[] {
  // Walk only enough indexed results to fill the feed; no per-scrub scan of
  // the entire source timeline is introduced for default-off worlds.
  const takeKnown = (rows: E[]) => {
    const out: E[] = [];
    for (const event of rows) {
      if (observationEventKnown(event, sourceTurn)) out.push(event);
      if (out.length >= EVENT_FEED_LIMIT) break;
    }
    return out;
  };
  if (focusCivilization === null) {
    return takeKnown(eventsUpTo(events, currentTurn));
  }
  const focused = takeKnown(actorEventsUpTo(events, focusCivilization, currentTurn));
  if (focused.length >= EVENT_FEED_FOCUS_MIN) {
    return focused.slice(0, EVENT_FEED_LIMIT);
  }
  const merged = [...focused];
  for (const event of eventsUpTo(events, currentTurn)) {
    if (merged.length >= EVENT_FEED_LIMIT) {
      break;
    }
    if (observationEventKnown(event, sourceTurn) && !merged.includes(event)) {
      merged.push(event);
    }
  }
  return merged;
}

const TERRAIN_TRANSITION = /^(.*) transforms from (\S+) to (\S+)$/;

/**
 * A region's terrain at `turn`. The world state holds the final terrain;
 * `terrain_transition` events ("<region> transforms from <a> to <b>",
 * emergence.py) date each change, so the terrain at `turn` is the `from`
 * of the region's first transition after it (the event log's convention:
 * an event of turn T has happened at T). Null when such an event cannot be
 * read.
 */
export function terrainAt(
  events: Array<{ turn: number; event_type: string; description: string }>,
  region: string,
  finalTerrain: string,
  turn: number,
): string | null {
  let first: { turn: number; from: string | null } | null = null;
  for (const event of eventsOfType(events, "terrain_transition")) {
    if (event.turn <= turn) {
      continue;
    }
    const match = TERRAIN_TRANSITION.exec(event.description ?? "");
    if (match && match[1] !== region) {
      continue;
    }
    if (!match && !(event.description ?? "").startsWith(region)) {
      continue;
    }
    if (!first || event.turn < first.turn) {
      first = { turn: event.turn, from: match ? match[2] : null };
    }
  }
  return first ? first.from : finalTerrain;
}
