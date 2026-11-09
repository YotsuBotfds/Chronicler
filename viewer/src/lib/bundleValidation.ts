import { isConstructedExample } from "./constructedExample";
import { isRecord } from "./recordGuards";
import type { RegionalPopulationSnapshot } from "../types";

/** Validate the required viewer containers before they reach React. Optional
 * historical fields remain optional; this does not upgrade old file schemas.
 * `isRecord` lives in `recordGuards.ts`; it stays exported here for existing importers. */
export { isRecord };

/** Optional additive observations fail to unknown, never make an old bundle unreadable. */
export function validatedRegionalPopulation(value: unknown, snapshotTurn: number, regionCount: number,
  civilizationCount: number): RegionalPopulationSnapshot | null {
  const count = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
  const counts = (v: unknown) => Array.isArray(v) && v.length === regionCount && Array.from(v).every(count);
  const sources = new Set(["python_region_state", "hybrid_region_state", "demographics_clamped_region_state", "uncontrolled_region_state"]);
  if (!isRecord(value) || value.schema_version !== 1 || typeof value.mode !== "string" || !["off", "hybrid", "shadow", "demographics-only"].includes(value.mode)
    || !count(value.source_turn) || !count(value.completed_turn) || value.completed_turn !== value.source_turn + 1 || value.completed_turn !== snapshotTurn
    || value.timing !== "completed_turn" || !counts(value.counts) || !Array.isArray(value.sources)
    || value.sources.length !== regionCount || !Array.from(value.sources).every((source) => sources.has(source))) return null;
  if (value.agent_counts === null ? value.agent_source !== null
    : !counts(value.agent_counts) || value.agent_source !== "native_region_alive_count") return null;
  const weights = value.food_weights;
  if (weights !== null && (!isRecord(weights) || weights.source !== "phase2_agent_pool"
    || weights.source_turn !== value.source_turn || weights.timing !== "phase2_entry" || !counts(weights.counts)
    || !Array.isArray(weights.controller_ids) || weights.controller_ids.length !== regionCount
    || !Array.from(weights.controller_ids).every((id) => id === null || count(id) && id < civilizationCount))) return null;
  return value as unknown as RegionalPopulationSnapshot;
}

type Check = (value: unknown) => boolean;
const number: Check = (value) => typeof value === "number" && Number.isFinite(value);
const turn: Check = (value) => number(value) && Number.isInteger(value) && (value as number) >= 0;
const string: Check = (value) => typeof value === "string";
const strings: Check = (value) => Array.isArray(value) && value.every(string);
const nullableString: Check = (value) => value === null || string(value);
const integer: Check = (value) => number(value) && Number.isSafeInteger(value);
const numbers: Check = (value) => isRecord(value) && Object.values(value).every(number);
const fields = (value: unknown, schema: Record<string, Check>, path: string): string | null => {
  if (!isRecord(value)) return `${path} must be an object`;
  for (const [key, check] of Object.entries(schema)) {
    if (!check(value[key])) return `${path}.${key} has a missing or invalid value`;
  }
  return null;
};
const rows = (value: unknown, schema: Record<string, Check>, path: string): string | null => {
  if (!Array.isArray(value)) return `${path} must be a list`;
  for (let index = 0; index < value.length; index++) {
    const invalid = fields(value[index], schema, `${path}[${index}]`);
    if (invalid) return invalid;
  }
  return null;
};

/** Renderer containers for history systems exercised by file loading.
 * Missing optional systems and older scalar metrics stay unrecorded.
 * regional_population is deliberately tolerant: readRegionalPopulation validates its
 * version, clock, stable-index arrays and counts at use; invalid records read unknown
 * without rejecting a historical bundle. No inferred counts or schema upgrades. */
function validateOptionalHistory(snapshot: Record<string, unknown>, path: string): string | null {
  const food = snapshot.food;
  if (food != null) {
    const invalid = fields(food, { sufficiency: (value) => Array.isArray(value)
      && value.every((item) => item === null || number(item)) }, `${path}.food`);
    if (invalid) return invalid;
    const aid = (food as Record<string, unknown>).aid;
    if (aid !== undefined && (!Array.isArray(aid) || !aid.every((flow) => Array.isArray(flow)
      && flow.length === 3 && turn(flow[0]) && turn(flow[1]) && number(flow[2])))) {
      return `${path}.food.aid must be a list of [donor index, recipient index, amount] triples`;
    }
  }
  const reserves = snapshot.grain_reserves;
  if (reserves != null) {
    let invalid = fields(reserves, { source_turn: integer, granaries: Array.isArray, flows: Array.isArray,
      counters: numbers }, `${path}.grain_reserves`);
    if (invalid) return invalid;
    const record = reserves as Record<string, unknown>;
    invalid = rows(record.granaries, { region: turn, region_name: string, owner: integer,
      owner_name: nullableString, controller: nullableString, grain: number }, `${path}.grain_reserves.granaries`);
    if (invalid) return invalid;
    for (const [index, row] of (record.granaries as Record<string, unknown>[]).entries()) {
      for (const key of ["target", "observed"]) {
        if (key in row && row[key] !== null && !number(row[key])) {
          return `${path}.grain_reserves.granaries[${index}].${key} must be a finite number or unrecorded`;
        }
      }
    }
    invalid = rows(record.flows, { kind: string, region: turn, amount: number, source: integer,
      seller: integer, buyer: integer, buyer_name: nullableString, seller_name: nullableString,
      sent: number, cost: number, before: number, after: number }, `${path}.grain_reserves.flows`);
    if (invalid) return invalid;
  }
  const finance = snapshot.finance;
  if (finance != null) {
    const invalid = fields(finance, { civs: isRecord }, `${path}.finance`);
    if (invalid) return invalid;
    const record = finance as Record<string, unknown>;
    if ("totals" in record && !numbers(record.totals)) return `${path}.finance.totals must map counters to finite numbers`;
    if ("loans" in record && !number(record.loans)) return `${path}.finance.loans must be a finite number`;
    for (const [name, row] of Object.entries(record.civs as Record<string, unknown>)) {
      if (!isRecord(row)) return `${path}.finance.civs.${name} must be an object`;
      const missing = fields(row, { revenue_ema: number, price_index: number, fiscal_stress: number }, `${path}.finance.civs.${name}`);
      if (missing) return missing;
      for (const [key, value] of Object.entries(row)) {
        if (!number(value)) return `${path}.finance.civs.${name}.${key} must be a finite number`;
      }
    }
  }
  return null;
}

const TIMELINE_ROW: Record<string, Check> = { turn, event_type: string, actors: strings, description: string, importance: number };
const VIEWABLE_CIVILIZATION: Record<string, Check> = {
  name: string, regions: strings, values: strings, goal: string, leader: isRecord, tech_era: string,
  population: number, military: number, economy: number, culture: number, stability: number,
  treasury: number, asabiya: number,
};
const VIEWABLE_NAMED_EVENT: Record<string, Check> = { name: string };

/** The shell's complete civilization rows and their leaders. */
function viewableCivilizations(world: Record<string, unknown>): string | null {
  const invalid = rows(world.civilizations, VIEWABLE_CIVILIZATION, "world_state.civilizations");
  if (invalid) return invalid;
  for (const [index, civ] of (world.civilizations as Record<string, unknown>[]).entries()) {
    const leader = fields(civ.leader, { name: string, trait: string }, `world_state.civilizations[${index}].leader`);
    if (leader) return leader;
  }
  return null;
}

/** An event row the shell lists: its consequences, causes and civs are lists of text. */
function viewableTimelineEvent(event: Record<string, unknown>, index: number): string | null {
  if ("consequences" in event && !strings(event.consequences)) return `events_timeline[${index}].consequences must be a list of text`;
  for (const key of ["causes", "civs"]) {
    if (event[key] != null && !strings(event[key])) return `events_timeline[${index}].${key} must be a list of text`;
  }
  return null;
}

/** A snapshot after one recorded at `previous`, with readable optional systems. */
function viewableSnapshot(snapshot: Record<string, unknown>, index: number, previous: number): string | null {
  if ((snapshot.turn as number) <= previous) return `history[${index}].turn must follow the previous recorded turn`;
  return validateOptionalHistory(snapshot, `history[${index}]`);
}

/** The first structural and the first viewable problem of a bundle. */
export interface BundleProblems {
  /** What `validateBundleStructure` reports. */
  structural: string | null;
  /** What `validateViewableBundle` reports; null whenever `structural` is set, or when not checked. */
  viewable: string | null;
}

/**
 * Both checks in one walk over the history and the timelines: each row is
 * checked for structure, then (with `checkViewable`) for what the shell needs.
 * The first structural problem wins, as when `validateViewableBundle` ran only
 * after the structure passed; the viewable problems keep that function's order
 * (civilizations, named events, timeline, history).
 */
export function validateBundle(bundle: Record<string, unknown>, checkViewable: boolean): BundleProblems {
  const broken = (structural: string): BundleProblems => ({ structural, viewable: null });
  let invalid = fields(bundle.metadata, { seed: number, total_turns: turn }, "metadata");
  if (invalid) return broken(invalid);
  const metadata = bundle.metadata as Record<string, unknown>;
  if ("constructed" in metadata && !isConstructedExample(metadata.constructed)) return broken("metadata.constructed must hold a source bundle SHA-256 and a nonempty list of deliberate edits");
  for (const [key, check] of Object.entries({ generated_at: string, sim_model: string, narrative_model: string,
    scenario_name: nullableString, interestingness_score: (value: unknown) => value === null || number(value) })) {
    if (key in metadata && !check(metadata[key])) return broken(`metadata.${key} has an invalid value`);
  }
  if ("bundle_version" in metadata && (!Number.isInteger(metadata.bundle_version)
    || (metadata.bundle_version as number) < 1 || (metadata.bundle_version as number) > 6)) {
    return broken("metadata.bundle_version is unsupported (this viewer reads versions 1–6 and older unversioned JSON)");
  }
  invalid = fields(bundle.world_state, {
    name: string, seed: number, turn, regions: Array.isArray, civilizations: Array.isArray,
  }, "world_state");
  if (invalid) return broken(invalid);
  const world = bundle.world_state as Record<string, unknown>;
  if ("scenario_name" in world && !nullableString(world.scenario_name)) return broken("world_state.scenario_name has an invalid value");
  invalid = rows(world.regions, { name: string, terrain: string }, "world_state.regions");
  if (invalid) return broken(invalid);
  for (const [index, region] of (world.regions as Record<string, unknown>[]).entries()) {
    for (const [key, check] of Object.entries({ controller: nullableString, resources: string,
      x: (value: unknown) => value === null || number(value), y: (value: unknown) => value === null || number(value) })) {
      if (key in region && !check(region[key])) return broken(`world_state.regions[${index}].${key} has an invalid value`);
    }
  }
  invalid = rows(world.civilizations, { name: string }, "world_state.civilizations");
  if (invalid) return broken(invalid);
  for (const [index, civ] of (world.civilizations as Record<string, unknown>[]).entries()) {
    for (const [key, check] of Object.entries({ regions: strings, leader: isRecord, tech_era: string, population: number, military: number, economy: number, culture: number, stability: number, treasury: number, asabiya: number })) {
      if (key in civ && !check(civ[key])) return broken(`world_state.civilizations[${index}].${key} has an invalid value`);
    }
  }
  const civilizationsView = checkViewable ? viewableCivilizations(world) : null;
  let historyView: string | null = null;
  let previous = -1;
  if (!Array.isArray(bundle.history)) return broken("history must be a list");
  for (let index = 0; index < bundle.history.length; index++) {
    const path = `history[${index}]`;
    const snapshot = bundle.history[index];
    invalid = fields(snapshot, { turn, civ_stats: isRecord, region_control: isRecord, relationships: isRecord }, path);
    if (invalid) return broken(invalid);
    const row = snapshot as Record<string, unknown>;
    for (const key of ["trade_routes", "active_wars", "embargoes", "active_settlements", "mercenary_companies",
      "vassal_relations", "federations", "proxy_wars", "exile_modifiers", "movements_summary", "active_conditions"]) {
      if (key in row && !Array.isArray(row[key])) return broken(`${path}.${key} must be a list`);
    }
    for (const key of ["campaign", "epidemics", "finance", "diplomacy", "techniques", "maritime", "contact",
      "gp_agendas", "nomads", "cities", "agent_movements", "guilds", "scholarship", "food", "grain_reserves",
      "health_care", "harvest_forecasts", "ritual_gatherings", "scientific_claims", "transaction_receipts"]) {
      if (row[key] != null && !isRecord(row[key])) return broken(`${path}.${key} must be an object`);
    }
    for (const [name, civ] of Object.entries(row.civ_stats as Record<string, unknown>)) {
      invalid = fields(civ, { regions: strings, population: number, military: number, economy: number,
        culture: number, stability: number, treasury: number, asabiya: number, tech_era: string }, `${path}.civ_stats.${name}`);
      if (invalid) return broken(invalid);
      const values = civ as Record<string, unknown>;
      for (const [key, check] of Object.entries({ leader_name: string, trait: string, alive: (value: unknown) => typeof value === "boolean" })) {
        if (key in values && !check(values[key])) return broken(`${path}.civ_stats.${name}.${key} has an invalid value`);
      }
    }
    if (!Object.values(row.region_control as Record<string, unknown>).every(nullableString)) {
      return broken(`${path}.region_control must map region names to civilization names or null`);
    }
    for (const [name, pairs] of Object.entries(row.relationships as Record<string, unknown>)) {
      if (!isRecord(pairs)) return broken(`${path}.relationships.${name} must be an object`);
      for (const [other, pair] of Object.entries(pairs)) {
        invalid = fields(pair, { disposition: string }, `${path}.relationships.${name}.${other}`);
        if (invalid) return broken(invalid);
      }
    }
    if (checkViewable && historyView === null) {
      historyView = viewableSnapshot(row, index, previous);
      previous = row.turn as number;
    }
  }
  let eventsView: string | null = null;
  let namedView: string | null = null;
  for (const key of ["events_timeline", "named_events"]) {
    const list = bundle[key];
    if (!Array.isArray(list)) return broken(`${key} must be a list`);
    for (let index = 0; index < list.length; index++) {
      invalid = fields(list[index], TIMELINE_ROW, `${key}[${index}]`);
      if (invalid) return broken(invalid);
      if (!checkViewable) continue;
      const event = list[index] as Record<string, unknown>;
      if (key === "events_timeline") {
        eventsView ??= viewableTimelineEvent(event, index);
      } else {
        namedView ??= fields(event, VIEWABLE_NAMED_EVENT, `named_events[${index}]`);
      }
    }
  }
  if (!isRecord(bundle.era_reflections) || !Object.values(bundle.era_reflections).every(string)) {
    return broken("era_reflections must map turns to text");
  }
  if (Array.isArray(bundle.chronicle_entries)) {
    invalid = rows(bundle.chronicle_entries, { turn, narrative: string, covers_turns: (value) =>
      Array.isArray(value) && value.length === 2 && value.every(turn) }, "chronicle_entries");
    if (invalid) return broken(invalid);
  } else if (!isRecord(bundle.chronicle_entries) || !Object.values(bundle.chronicle_entries).every(string)) {
    return broken("chronicle_entries must be a list of entries or a legacy map of turns to text");
  }
  return { structural: null, viewable: civilizationsView ?? namedView ?? eventsView ?? historyView };
}

export function validateBundleStructure(bundle: Record<string, unknown>): string | null {
  return validateBundle(bundle, false).structural;
}

/** Some codec fixtures are deliberately partial. Decodable history alone is
 * insufficient for the shell, which also needs complete civilization rows.
 * For a bundle whose structure passed; file loading runs both checks in one
 * walk (`validateBundle`). */
export function validateViewableBundle(bundle: Record<string, unknown>): string | null {
  let invalid = viewableCivilizations(bundle.world_state as Record<string, unknown>);
  if (invalid) return invalid;
  invalid = rows(bundle.named_events, VIEWABLE_NAMED_EVENT, "named_events");
  if (invalid) return invalid;
  for (const [index, event] of (bundle.events_timeline as Record<string, unknown>[]).entries()) {
    invalid = viewableTimelineEvent(event, index);
    if (invalid) return invalid;
  }
  let previous = -1;
  for (const [index, snapshot] of (bundle.history as Record<string, unknown>[]).entries()) {
    invalid = viewableSnapshot(snapshot, index, previous);
    if (invalid) return invalid;
    previous = snapshot.turn as number;
  }
  return null;
}
