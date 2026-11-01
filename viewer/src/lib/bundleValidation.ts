/** Validate the required viewer containers before they reach React. Optional
 * historical fields remain optional; this does not upgrade old file schemas. */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

type Check = (value: unknown) => boolean;
const number: Check = (value) => typeof value === "number" && Number.isFinite(value);
const turn: Check = (value) => number(value) && Number.isInteger(value) && (value as number) >= 0;
const string: Check = (value) => typeof value === "string";
const strings: Check = (value) => Array.isArray(value) && value.every(string);
const nullableString: Check = (value) => value === null || string(value);
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

export function validateBundleStructure(bundle: Record<string, unknown>): string | null {
  let invalid = fields(bundle.metadata, { seed: number, total_turns: turn }, "metadata");
  if (invalid) return invalid;
  const metadata = bundle.metadata as Record<string, unknown>;
  for (const [key, check] of Object.entries({ generated_at: string, sim_model: string, narrative_model: string,
    scenario_name: nullableString, interestingness_score: (value: unknown) => value === null || number(value) })) {
    if (key in metadata && !check(metadata[key])) return `metadata.${key} has an invalid value`;
  }
  if ("bundle_version" in metadata && (!Number.isInteger(metadata.bundle_version)
    || (metadata.bundle_version as number) < 1 || (metadata.bundle_version as number) > 6)) {
    return "metadata.bundle_version is unsupported (this viewer reads versions 1–6 and older unversioned JSON)";
  }
  invalid = fields(bundle.world_state, {
    name: string, seed: number, turn, regions: Array.isArray, civilizations: Array.isArray,
  }, "world_state");
  if (invalid) return invalid;
  const world = bundle.world_state as Record<string, unknown>;
  if ("scenario_name" in world && !nullableString(world.scenario_name)) return "world_state.scenario_name has an invalid value";
  invalid = rows(world.regions, { name: string, terrain: string }, "world_state.regions");
  if (invalid) return invalid;
  for (const [index, region] of (world.regions as Record<string, unknown>[]).entries()) {
    for (const [key, check] of Object.entries({ controller: nullableString, resources: string,
      x: (value: unknown) => value === null || number(value), y: (value: unknown) => value === null || number(value) })) {
      if (key in region && !check(region[key])) return `world_state.regions[${index}].${key} has an invalid value`;
    }
  }
  invalid = rows(world.civilizations, { name: string }, "world_state.civilizations");
  if (invalid) return invalid;
  for (const [index, civ] of (world.civilizations as Record<string, unknown>[]).entries()) {
    for (const [key, check] of Object.entries({ regions: strings, leader: isRecord, tech_era: string, population: number, military: number, economy: number, culture: number, stability: number, treasury: number, asabiya: number })) {
      if (key in civ && !check(civ[key])) return `world_state.civilizations[${index}].${key} has an invalid value`;
    }
  }
  if (!Array.isArray(bundle.history)) return "history must be a list";
  for (let index = 0; index < bundle.history.length; index++) {
    const path = `history[${index}]`;
    const snapshot = bundle.history[index];
    invalid = fields(snapshot, { turn, civ_stats: isRecord, region_control: isRecord, relationships: isRecord }, path);
    if (invalid) return invalid;
    const row = snapshot as Record<string, unknown>;
    for (const key of ["trade_routes", "active_wars", "embargoes", "active_settlements", "mercenary_companies",
      "vassal_relations", "federations", "proxy_wars", "exile_modifiers", "movements_summary", "active_conditions"]) {
      if (key in row && !Array.isArray(row[key])) return `${path}.${key} must be a list`;
    }
    for (const key of ["campaign", "epidemics", "finance", "diplomacy", "techniques", "maritime", "contact",
      "gp_agendas", "nomads", "cities", "agent_movements", "guilds", "scholarship", "food", "grain_reserves",
      "health_care", "harvest_forecasts", "ritual_gatherings", "scientific_claims", "transaction_receipts"]) {
      if (row[key] != null && !isRecord(row[key])) return `${path}.${key} must be an object`;
    }
    for (const [name, civ] of Object.entries(row.civ_stats as Record<string, unknown>)) {
      invalid = fields(civ, { regions: strings, population: number, military: number, economy: number,
        culture: number, stability: number, treasury: number, asabiya: number, tech_era: string }, `${path}.civ_stats.${name}`);
      if (invalid) return invalid;
      const values = civ as Record<string, unknown>;
      for (const [key, check] of Object.entries({ leader_name: string, trait: string, alive: (value: unknown) => typeof value === "boolean" })) {
        if (key in values && !check(values[key])) return `${path}.civ_stats.${name}.${key} has an invalid value`;
      }
    }
    if (!Object.values(row.region_control as Record<string, unknown>).every(nullableString)) {
      return `${path}.region_control must map region names to civilization names or null`;
    }
    for (const [name, pairs] of Object.entries(row.relationships as Record<string, unknown>)) {
      if (!isRecord(pairs)) return `${path}.relationships.${name} must be an object`;
      for (const [other, pair] of Object.entries(pairs)) {
        invalid = fields(pair, { disposition: string }, `${path}.relationships.${name}.${other}`);
        if (invalid) return invalid;
      }
    }
  }
  for (const key of ["events_timeline", "named_events"]) {
    invalid = rows(bundle[key], { turn, event_type: string, actors: strings, description: string, importance: number }, key);
    if (invalid) return invalid;
  }
  if (!isRecord(bundle.era_reflections) || !Object.values(bundle.era_reflections).every(string)) {
    return "era_reflections must map turns to text";
  }
  if (Array.isArray(bundle.chronicle_entries)) {
    invalid = rows(bundle.chronicle_entries, { turn, narrative: string, covers_turns: (value) =>
      Array.isArray(value) && value.length === 2 && value.every(turn) }, "chronicle_entries");
    if (invalid) return invalid;
  } else if (!isRecord(bundle.chronicle_entries) || !Object.values(bundle.chronicle_entries).every(string)) {
    return "chronicle_entries must be a list of entries or a legacy map of turns to text";
  }
  return null;
}

/** Some codec fixtures are deliberately partial. Decodable history alone is
 * insufficient for the shell, which also needs complete civilization rows. */
export function validateViewableBundle(bundle: Record<string, unknown>): string | null {
  const world = bundle.world_state as Record<string, unknown>;
  let invalid = rows(world.civilizations, {
    name: string, regions: strings, values: strings, goal: string, leader: isRecord, tech_era: string,
    population: number, military: number, economy: number, culture: number, stability: number,
    treasury: number, asabiya: number,
  }, "world_state.civilizations");
  if (invalid) return invalid;
  for (const [index, civ] of (world.civilizations as Record<string, unknown>[]).entries()) {
    invalid = fields(civ.leader, { name: string, trait: string }, `world_state.civilizations[${index}].leader`);
    if (invalid) return invalid;
  }
  invalid = rows(bundle.named_events, { name: string }, "named_events");
  if (invalid) return invalid;
  for (const [index, event] of (bundle.events_timeline as Record<string, unknown>[]).entries()) {
    if ("consequences" in event && !strings(event.consequences)) return `events_timeline[${index}].consequences must be a list of text`;
    for (const key of ["causes", "civs"]) {
      if (event[key] != null && !strings(event[key])) return `events_timeline[${index}].${key} must be a list of text`;
    }
  }
  let previous = -1;
  for (const [index, snapshot] of (bundle.history as Record<string, unknown>[]).entries()) {
    if ((snapshot.turn as number) <= previous) return `history[${index}].turn must follow the previous recorded turn`;
    previous = snapshot.turn as number;
  }
  return null;
}
