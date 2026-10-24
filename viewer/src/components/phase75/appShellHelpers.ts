export function turnToPercent(turn: number, maxTurn: number): number {
  if (maxTurn <= 1) {
    return 0;
  }
  return ((turn - 1) / (maxTurn - 1)) * 100;
}

/**
 * Divisor that brings region map pins into 0-1. Generated worlds place
 * regions on a 0-100 map; hand-made demo data already uses 0-1.
 */
export function pinScale(coords: Array<number | null | undefined>): number {
  let max = 0;
  for (const value of coords) {
    if (typeof value === "number" && Number.isFinite(value)) {
      max = Math.max(max, Math.abs(value));
    }
  }
  return max > 1 ? Math.max(100, max) : 1;
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

/** Selection key for an event: its recorded id, else the legacy turn-type key. */
export function eventKey(event: ProvenanceEventLike): string {
  return event.event_id || `${event.turn}-${event.event_type}`;
}

/**
 * Recorded provenance of one event (bundle version 4+): the events it cites
 * as causes and the events that cite it. Both are empty for older bundles.
 */
export function eventProvenance<E extends ProvenanceEventLike>(
  events: E[],
  selected: E | null,
): { causes: E[]; effects: E[] } {
  if (!selected?.event_id) {
    return { causes: [], effects: [] };
  }
  const selectedId = selected.event_id;
  const wanted = new Set(selected.causes ?? []);
  const causes: E[] = [];
  const effects: E[] = [];
  for (const event of events) {
    if (event.event_id && wanted.has(event.event_id)) {
      causes.push(event);
    }
    if (event.causes?.includes(selectedId)) {
      effects.push(event);
    }
  }
  return { causes, effects };
}
