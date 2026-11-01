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

/** Renderer containers for the three history systems exercised by file loading.
 * Missing optional systems and missing older scalar metrics stay unrecorded. */
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
    invalid = validateOptionalHistory(snapshot, `history[${index}]`);
    if (invalid) return invalid;
  }
  return null;
}
