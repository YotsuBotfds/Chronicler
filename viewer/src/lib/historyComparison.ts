/** Exact recorded endpoints only: never borrow a later/final world value. */
import type { Bundle, Event, TurnSnapshot } from "../types";
import { eventKey, eventKeyCount } from "./bundleIndex";
import { populationWeightedFood, readRegionalPopulation, weightedFoodNote } from "./regionalPopulation";
import { foodAccountingAt } from "./foodAccounting";

export interface HistoryEntity { kind: "civilization" | "region"; name: string }
export interface RecordedMetric {
  id: string; label: string; value: number | null; note?: string;
}
export interface EntityReading {
  turn: number; recorded: boolean; status: string; controller?: string;
  metrics: RecordedMetric[];
}
export interface MetricChange extends Omit<RecordedMetric, "value"> {
  before: number | null; after: number | null; delta: number | null; percent: number | null;
}
export interface ChangeEvent { event: Event; visibleTurn: number; canPin: boolean }

const number = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const metric = (id: string, label: string, value: unknown, note?: string): RecordedMetric =>
  ({ id, label, value: number(value), note });

/** Duplicate turns are ambiguous, rather than arbitrarily choosing a record. */
export function exactSnapshot(bundle: Bundle, turn: number): TurnSnapshot | null {
  const rows = bundle.history.filter((row) => row.turn === turn);
  return rows.length === 1 ? rows[0] : null;
}

export function comparisonTurns(bundle: Bundle, through: number): number[] {
  const counts = new Map<number, number>();
  for (const row of bundle.history) {
    if (Number.isSafeInteger(row.turn) && row.turn >= 1 && row.turn <= through) {
      counts.set(row.turn, (counts.get(row.turn) ?? 0) + 1);
    }
  }
  return [...counts].filter(([, count]) => count === 1).map(([turn]) => turn).sort((a, b) => a - b);
}

export function comparisonEntities(bundle: Bundle, through: number): HistoryEntity[] {
  const known = bundle.history.filter((row) => row.turn <= through);
  const civs = new Set(known.flatMap((row) => Object.keys(row.civ_stats)));
  const regions = new Set([
    ...bundle.world_state.regions.map((region) => region.name),
    ...known.flatMap((row) => Object.keys(row.region_control)),
  ]);
  return [
    ...[...civs].sort().map((name): HistoryEntity => ({ kind: "civilization", name })),
    ...[...regions].sort().map((name): HistoryEntity => ({ kind: "region", name })),
  ];
}

function granaryValues(bundle: Bundle, snapshot: TurnSnapshot | null, names: string[]) {
  const rows = snapshot?.grain_reserves?.granaries;
  if (!rows || names.length === 0) return { grain: null, target: null };
  const selected = names.map((name) => {
    const region = bundle.world_state.regions.findIndex((row) => row.name === name);
    const matches = rows.filter((row) => row.region === region && region >= 0);
    return matches.length === 1 ? matches[0] : null;
  });
  const grain = selected.every((row) => row !== null && number(row.grain) !== null)
    ? selected.reduce((sum, row) => sum + row!.grain, 0) : null;
  const target = selected.every((row) => row !== null && row.observed > 0 && number(row.target) !== null)
    ? selected.reduce((sum, row) => sum + row!.target, 0) : null;
  return { grain, target };
}

function foodValues(bundle: Bundle, snapshot: TurnSnapshot | null, names: string[]) {
  const sufficiency = snapshot?.food?.sufficiency;
  if (!sufficiency || names.length === 0) return { mean: null, short: null };
  const values = names.map((name) => {
    const index = bundle.world_state.regions.findIndex((row) => row.name === name);
    return index >= 0 ? number(sufficiency[index]) : null;
  });
  if (values.some((value) => value === null)) return { mean: null, short: null };
  const measured = values as number[];
  return { mean: measured.reduce((a, b) => a + b, 0) / measured.length,
    short: measured.filter((value) => value < 1).length };
}

/** Existing food observations take precedence, including their missing values. */
function regionalFood(bundle: Bundle, snapshot: TurnSnapshot | null, index: number): { value: number | null; note?: string } {
  if (snapshot?.food != null) return { value: number(snapshot.food.sufficiency?.[index]) };
  const ledger = foodAccountingAt(snapshot, bundle.world_state.regions.length, bundle.world_state.civilizations.length);
  if (!ledger || !["hybrid", "shadow", "demographics-only"].includes(ledger.mode)) return { value: null };
  const row = ledger.regions.find((item) => item.region_id === index);
  const native = row?.native;
  if (!row || row.native_count === null || row.native_count <= 0 || !native || native.demand <= 0 || native.sufficiency < 0)
    return { value: null };
  return { value: native.sufficiency, note: NATIVE_FOOD_NOTE };
}

export const NATIVE_FOOD_NOTE = "Phase 2 native food goods / demand before public relief; not household distribution.";

export function readEntityTurn(bundle: Bundle, entity: HistoryEntity, turn: number): EntityReading {
  const snapshot = exactSnapshot(bundle, turn);
  if (entity.kind === "region") {
    const index = bundle.world_state.regions.findIndex((row) => row.name === entity.name);
    const control = snapshot?.region_control[entity.name];
    const ecology = snapshot?.ecology?.[entity.name];
    const grain = granaryValues(bundle, snapshot, [entity.name]);
    const population = readRegionalPopulation(bundle, snapshot);
    const food = index >= 0 ? regionalFood(bundle, snapshot, index) : { value: null };
    return {
      turn, recorded: snapshot !== null, status: snapshot ? "Recorded snapshot" : "Snapshot not recorded or ambiguous",
      controller: control === null ? "Uncontrolled" : control ?? "Not recorded",
      metrics: [
        metric("population", "Regional model population", index >= 0 ? population?.counts[index] : null,
          population && index >= 0 ? `Completed model Region.population; source: ${population.sources[index]}; mode: ${population.mode}.` : "Regional population not recorded or unsupported; no civilization allocation is inferred."),
        metric("nativePopulation", "Native agents alive", index >= 0 ? population?.agent_counts?.[index] : null, "Completed native pool count; may differ from model population in shadow and demographics-only modes."),
        metric("food", "Food / need", food.value, food.note),
        metric("grain", "Public grain stored", grain.grain),
        metric("target", "Public grain target", grain.target, "Requires recorded demand observations."),
        ...["soil", "water", "forest_cover"].map((key) => metric(key,
          key === "forest_cover" ? "Forest cover" : key === "soil" ? "Soil" : "Water", ecology?.[key])),
      ],
    };
  }
  const row = snapshot?.civ_stats[entity.name];
  const prior = bundle.history.filter((sample) => sample.turn < turn && sample.civ_stats[entity.name])
    .sort((a, b) => b.turn - a.turn)[0]?.civ_stats[entity.name];
  const status = !snapshot ? "Snapshot not recorded or ambiguous" : row
    ? row.alive === false ? "Fallen (recorded)" : "Recorded"
    : prior?.alive === false ? "Fallen; no row at this turn" : prior ? "No row at this turn" : "No record yet";
  const regions = row && Array.isArray(row.regions) ? [...new Set(row.regions)] : null;
  const food = foodValues(bundle, snapshot, regions ?? []);
  const grain = granaryValues(bundle, snapshot, regions ?? []);
  const weighted = populationWeightedFood(bundle, snapshot, entity.name);
  return { turn, recorded: snapshot !== null && row !== undefined, status, metrics: [
    metric("population", "Population", row?.population),
    metric("territory", "Controlled regions", regions?.length),
    metric("treasury", "Treasury", row?.treasury),
    metric("debt", "Outstanding debt", row ? snapshot?.finance?.civs?.[entity.name]?.debt : null,
      "Total principal already includes foreign debt; it is not added twice."),
    metric("food", "Mean regional food / need", food.mean, "Unweighted mean; every controlled region must have an observation."),
    metric("weightedFood", "Population-weighted food / need", row ? weighted.value : null, weightedFoodNote(weighted)),
    metric("short", "Regions short of food", food.short),
    metric("grain", "Public grain in controlled regions", grain.grain),
    ...(["military", "economy", "culture", "stability", "asabiya"] as const).map((key) =>
      metric(key, key[0].toUpperCase() + key.slice(1), row?.[key])),
  ] };
}

export function compareReadings(before: EntityReading, after: EntityReading): MetricChange[] {
  return before.metrics.map((first) => {
    const last = after.metrics.find((item) => item.id === first.id);
    const a = first.value, b = last?.value ?? null;
    const delta = a !== null && b !== null ? b - a : null;
    return { id: first.id, label: first.label, note: last?.note === first.note ? first.note : `Earlier: ${first.note ?? "No additional note"} Later: ${last?.note ?? "No additional note"}`, before: a, after: b, delta,
      percent: delta !== null && a !== 0 && a !== null ? delta / Math.abs(a) * 100 : null };
  });
}

export function largestRelativeChanges(changes: MetricChange[]): MetricChange[] {
  return changes.filter((row) => row.percent !== null && row.delta !== 0)
    .sort((a, b) => Math.abs(b.percent!) - Math.abs(a.percent!)).slice(0, 3);
}

/** Snapshot T contains completed tick T-1. Keep original event records intact. */
function changeEventSnapshotTurn(event: Pick<Event, "turn">): number { return event.turn + 1; }

/** Only explicit timeline attribution; proximity is not causation. Window (from, to]. */
export function changeEvents(bundle: Bundle, entity: HistoryEntity, from: number, to: number, through: number): ChangeEvent[] {
  const seen = new Set<string>();
  return bundle.events_timeline.flatMap((event) => {
    const visibleTurn = changeEventSnapshotTurn(event);
    if (visibleTurn <= from || visibleTurn > to || visibleTurn > through) return [];
    if (entity.kind === "region" ? event.region !== entity.name : !event.actors.includes(entity.name)) return [];
    const identity = event.event_id ?? JSON.stringify([event.turn, event.event_type, event.region, event.actors, event.description]);
    if (seen.has(identity)) return [];
    seen.add(identity);
    return [{ event, visibleTurn, canPin: eventKeyCount(bundle.events_timeline, eventKey(event)) === 1 }];
  }).sort((a, b) => a.visibleTurn - b.visibleTurn);
}
