import type { Bundle } from "../types";

export interface RegionMetric {
  id: string;
  label: string;
  kind: "ecology" | "stockpile";
  key: string;
}

export interface RegionHistoryRow {
  turn: number;
  controller: string | null | undefined;
  value: number | null;
  missing: string | null;
  source: string;
}

export interface RegionHistoryEvent {
  turn: number;
  type: string;
  description: string;
  scope: "Recorded region" | "Controller context; region unrecorded";
  source: string;
}

const pointer = (name: string) => name.replace(/~/g, "~0").replace(/\//g, "~1");
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

export function regionNames(bundle: Bundle): string[] {
  return [...new Set([
    ...bundle.world_state.regions.map((region) => region.name),
    ...bundle.history.flatMap((snapshot) => [
      ...Object.keys(snapshot.ecology ?? {}), ...Object.keys(snapshot.region_control),
    ]),
    ...bundle.named_events.flatMap((event) => event.region ? [event.region] : []),
  ])].sort();
}

export function regionMetrics(bundle: Bundle): RegionMetric[] {
  const goods = [...new Set(bundle.world_state.regions.flatMap(
    (region) => Object.keys(region.stockpile?.goods ?? {}),
  ))].sort();
  return [
    { id: "ecology:soil", label: "Soil", kind: "ecology", key: "soil" },
    { id: "ecology:water", label: "Water", kind: "ecology", key: "water" },
    { id: "ecology:forest_cover", label: "Forest cover", kind: "ecology", key: "forest_cover" },
    ...goods.map((good): RegionMetric => ({
      id: `stockpile:${good}`, label: `Stockpile: ${good} (final state only)`, kind: "stockpile", key: good,
    })),
  ];
}

export function recordedTurnBounds(bundle: Bundle): [number, number] {
  const turns = [bundle.world_state.turn, ...bundle.history.map((snapshot) => snapshot.turn),
    ...bundle.events_timeline.map((event) => event.turn), ...bundle.named_events.map((event) => event.turn)];
  // Avoid spreading large histories into Math.min/max's argument list.
  return turns.reduce<[number, number]>(([min, max], turn) => [Math.min(min, turn), Math.max(max, turn)],
    [bundle.world_state.turn, bundle.world_state.turn]);
}

export function inspectRegionHistory(
  bundle: Bundle, regionName: string, metric: RegionMetric, start: number, end: number,
): { rows: RegionHistoryRow[]; unrecordedTurns: number } {
  const regionKey = pointer(regionName);
  const rows: RegionHistoryRow[] = bundle.history.flatMap((snapshot, index) => {
    if (snapshot.turn < start || snapshot.turn > end) return [];
    const source = `/history/${index}/ecology/${regionKey}/${pointer(metric.key)}`;
    const value = metric.kind === "ecology" ? snapshot.ecology?.[regionName]?.[metric.key] : undefined;
    return [{
      turn: snapshot.turn,
      controller: snapshot.region_control[regionName],
      value: finite(value) ? value : null,
      missing: metric.kind === "stockpile" ? "Historical stockpile not exported"
        : value === undefined || value === null ? "Metric not recorded" : finite(value) ? null : "Invalid numeric value",
      source: metric.kind === "ecology" ? source : `/history/${index}`,
    }];
  });
  // The final world state is a separate observation, never a history fallback.
  if (metric.kind === "stockpile" && bundle.world_state.turn >= start && bundle.world_state.turn <= end) {
    const index = bundle.world_state.regions.findIndex((region) => region.name === regionName);
    const region = bundle.world_state.regions[index];
    const value = region?.stockpile?.goods[metric.key];
    rows.push({
      turn: bundle.world_state.turn,
      controller: region?.controller,
      value: finite(value) ? value : null,
      missing: value === undefined || value === null ? "Good not recorded in final state"
        : finite(value) ? null : "Invalid numeric value",
      source: index < 0 ? "/world_state/regions"
        : `/world_state/regions/${index}/stockpile/goods/${pointer(metric.key)}`,
    });
  }
  rows.sort((left, right) => left.turn - right.turn);
  const observed = new Set(rows.map((row) => row.turn));
  return { rows, unrecordedTurns: Math.max(0, end - start + 1 - observed.size) };
}

export function inspectRegionEvents(
  bundle: Bundle, regionName: string, start: number, end: number, type: string,
  includeControllerContext: boolean,
): RegionHistoryEvent[] {
  const inWindow = (event: { turn: number; event_type: string }) => event.turn >= start && event.turn <= end
    && (!type || event.event_type === type);
  const events: RegionHistoryEvent[] = bundle.named_events.flatMap((event, index) => (
    inWindow(event) && event.region === regionName ? [{
      turn: event.turn, type: event.event_type, description: `${event.name}: ${event.description}`,
      scope: "Recorded region" as const, source: `/named_events/${index}`,
    }] : []
  ));
  if (includeControllerContext) {
    // Require an exact-turn observation; do not forward-fill controller identity.
    const controllers = new Map<number, Set<string>>();
    for (const snapshot of bundle.history) {
      const controller = snapshot.region_control[regionName];
      if (typeof controller === "string") {
        const atTurn = controllers.get(snapshot.turn) ?? new Set<string>();
        atTurn.add(controller);
        controllers.set(snapshot.turn, atTurn);
      }
    }
    bundle.events_timeline.forEach((event, index) => {
      if (inWindow(event) && event.actors.some((actor) => controllers.get(event.turn)?.has(actor))) {
        events.push({ turn: event.turn, type: event.event_type, description: event.description,
          scope: "Controller context; region unrecorded", source: `/events_timeline/${index}` });
      }
    });
  }
  return events.sort((left, right) => left.turn - right.turn);
}
