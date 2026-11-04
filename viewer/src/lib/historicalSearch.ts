import type { Bundle } from "../types";

export type HistoricalSearchKind = "region" | "civilization" | "city" | "institution" | "actor";
export interface HistoricalSearchAlias { name: string; turn: number; sourceRef: string; sourceTurn?: number }
export interface HistoricalSearchResult {
  kind: HistoricalSearchKind;
  identity: { namespace: "region" | "civilization" | "city" | "scholarship" | "guild"; index: number } | null;
  name: string;
  /** Snapshot/observation clock, never the final world's turn. */
  turn: number | null;
  sourceRef: string;
  firstRecordedTurn: number | null;
  lastRecordedTurn: number | null;
  status: string;
  aliases: HistoricalSearchAlias[];
  ambiguity?: string;
  mapEntity?: { kind: "region" | "civilization"; name: string };
}
export interface HistoricalSearchIndex {
  through: number;
  items: HistoricalSearchResult[];
  coverage: string[];
  /** Visit eligible actor observations newest first without retaining result objects. */
  visitActors?: (visit: (name: string, turn: number, sourceRef: string, role: string, civ: string) => void) => void;
}
const pointer = (value: string) => value.replace(/~/g, "~0").replace(/\//g, "~1");
const dated = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0;
const sourceTurn = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && Number.isInteger(value);
const id = (value: unknown): value is number => dated(value) && Number.isInteger(value);
const text = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const normalize = (value: string) => value.normalize("NFKC").toLocaleLowerCase().trim();

/** Name keys are legacy references, never invented entity IDs. */
function indices(rows: readonly { name: string }[]) {
  const result = new Map<string, number[]>();
  rows.forEach((row, index) => result.set(row.name, [...(result.get(row.name) ?? []), index]));
  return result;
}

/** Only history observations <= selected turn; final state supplies layout identities only. */
export function buildHistoricalSearchIndex(bundle: Bundle, through: number): HistoricalSearchIndex {
  if (!dated(through)) return { through, items: [], coverage: ["Selected turn unavailable."] };
  const regionIndices = indices(bundle.world_state.regions);
  const civIndices = indices(bundle.world_state.civilizations);
  const records = new Map<string, HistoricalSearchResult>();
  const turns = new Map<number, number>();
  for (const row of bundle.history) if (dated(row.turn) && row.turn <= through) turns.set(row.turn, (turns.get(row.turn) ?? 0) + 1);
  const snapshots = bundle.history.map((row, index) => ({ row, index }))
    .filter(({ row }) => dated(row.turn) && row.turn <= through && turns.get(row.turn) === 1)
    .sort((a, b) => a.row.turn - b.row.turn);
  const note = (key: string, item: HistoricalSearchResult) => {
    const old = records.get(key);
    if (!old) { records.set(key, item); return; }
    const aliases = old.aliases;
    if (old.name !== item.name && old.turn !== null && !aliases.some((alias) => alias.name === old.name)) {
      aliases.push({ name: old.name, turn: old.turn, sourceRef: old.sourceRef });
    }
    records.set(key, { ...item, firstRecordedTurn: old.firstRecordedTurn ?? item.firstRecordedTurn, aliases });
  };
  // Region names are static map metadata. They do not establish historical control/presence.
  bundle.world_state.regions.forEach((region, index) => {
    const ambiguous = (regionIndices.get(region.name)?.length ?? 0) > 1;
    records.set(`region:${index}`, { kind: "region", identity: { namespace: "region", index }, name: region.name,
      turn: null, sourceRef: `/world_state/regions/${index}/name`, firstRecordedTurn: null, lastRecordedTurn: null,
      status: "Static map location; historical presence and owner not recorded through selected turn.", aliases: [],
      ...(ambiguous ? { ambiguity: "Repeated region name; name-keyed history cannot identify this region." } : {}) });
  });
  let actorCount = 0;
  for (const { row, index } of snapshots) {
    const source = `/history/${index}`;
    const observation = (kind: HistoricalSearchKind, name: string, sourceRef: string): HistoricalSearchResult => ({
      kind, identity: null, name, turn: row.turn, sourceRef, firstRecordedTurn: row.turn, lastRecordedTurn: row.turn,
      status: "Recorded at this snapshot.", aliases: [],
    });
    for (const name of Object.keys(row.region_control)) {
      const candidates = regionIndices.get(name) ?? [];
      if (candidates.length !== 1) continue;
      const regionIndex = candidates[0];
      note(`region:${regionIndex}`, { ...observation("region", name, `${source}/region_control/${pointer(name)}`),
        identity: { namespace: "region", index: regionIndex }, mapEntity: { kind: "region", name } });
    }
    for (const [name, civ] of Object.entries(row.civ_stats)) {
      const candidates = civIndices.get(name) ?? [];
      const identity = candidates.length === 1 ? { namespace: "civilization" as const, index: candidates[0] } : null;
      const sourceRef = `${source}/civ_stats/${pointer(name)}`;
      note(`civ:${name}`, { ...observation("civilization", name, sourceRef), identity,
        status: civ.alive === false ? "Fallen in this recorded snapshot." : "Recorded at this snapshot.",
        ...(identity ? { mapEntity: { kind: "civilization" as const, name } }
          : { ambiguity: candidates.length > 1 ? "Repeated civilization name; history cannot identify an array index." : "Legacy name has no recorded stable array identity." }) });
      if (text(civ.leader_name)) actorCount += 1;
      civ.great_persons?.forEach((person) => { if (text(person.name)) actorCount += 1; });
    }
    const datedRows = [
      { namespace: "city" as const, kind: "city" as const, rows: row.cities?.cities ?? [], path: "cities/cities" },
      { namespace: "scholarship" as const, kind: "institution" as const, rows: row.scholarship?.seats ?? [], path: "scholarship/seats" },
      { namespace: "guild" as const, kind: "institution" as const, rows: row.guilds?.guilds ?? [], path: "guilds/guilds" },
    ];
    for (const group of datedRows) group.rows.forEach((entity, entityIndex) => {
      if (!text(entity.name)) return;
      const duplicate = !id(entity.id) || group.rows.filter((other) => other.id === entity.id).length > 1;
      const item = observation(group.kind, entity.name, `${source}/${group.path}/${entityIndex}`);
      // Seat/guild IDs are documented world-list indices; city IDs are settlement IDs.
      item.identity = duplicate ? null : { namespace: group.namespace, index: entity.id };
      if (duplicate) item.ambiguity = "Missing or repeated ID in this snapshot; identity cannot be resolved.";
      note(duplicate ? item.sourceRef : `${group.namespace}:${entity.id}`, item);
    });
  }
  for (const item of records.values()) {
    if (item.lastRecordedTurn !== null && item.lastRecordedTurn < through) {
      item.status += ` No observation at selected turn ${through}; absence does not establish extinction or a founding date.`;
    }
  }
  const field = bundle.languages;
  if (field && dated(field.enabled_turn) && field.enabled_turn <= through) {
    const col = (word: unknown[], key: string) => word[field.word_columns.indexOf(key)];
    field.words.forEach((word, wordIndex) => {
      const kind = col(word, "kind"), ref = col(word, "ref"), coined = col(word, "turn"), forms = col(word, "forms");
      if ((kind !== "region" && kind !== "civ") || !id(ref) || !sourceTurn(coined) || coined + 1 > through || !Array.isArray(forms)) return;
      const target = [...records.values()].find((item) => item.identity?.namespace === (kind === "civ" ? "civilization" : "region") && item.identity.index === ref);
      if (!target) return;
      forms.forEach((form: unknown, formIndex) => {
        if (!Array.isArray(form) || !sourceTurn(form[0]) || form[0] < coined || form[0] + 1 > through || !text(form[1])) return;
        if (!target.aliases.some((alias) => alias.name === form[1])) target.aliases.push({ name: form[1], turn: Math.max(0, form[0] + 1), sourceTurn: form[0],
          sourceRef: `/languages/words/${wordIndex}/${field.word_columns.indexOf("forms")}/${formIndex}` });
      });
    });
  }
  const ambiguousTurns = [...turns.values()].filter((count) => count > 1).length;
  const visitActors: NonNullable<HistoricalSearchIndex["visitActors"]> = (visit) => {
    for (let snapshotIndex = snapshots.length - 1; snapshotIndex >= 0; snapshotIndex--) {
      const { row, index } = snapshots[snapshotIndex];
      const civs = Object.entries(row.civ_stats);
      for (let civIndex = civs.length - 1; civIndex >= 0; civIndex--) {
        const [name, civ] = civs[civIndex];
        const source = `/history/${index}/civ_stats/${pointer(name)}`;
        const people = civ.great_persons ?? [];
        for (let personIndex = people.length - 1; personIndex >= 0; personIndex--) {
          const person = people[personIndex];
          if (text(person.name)) visit(person.name, row.turn, `${source}/great_persons/${personIndex}`, text(person.role) ? person.role : "Named actor", name);
        }
        if (text(civ.leader_name)) visit(civ.leader_name, row.turn, `${source}/leader_name`, "Leader", name);
      }
    }
  };
  return { through, items: [...records.values()], visitActors, coverage: [
    `${snapshots.length} unique recorded snapshots through selected turn ${through}; ${ambiguousTurns} duplicate snapshot turns excluded. Gaps remain unknown.`,
    "First/last recorded means observed through the selected turn, not founded/extinct. Final world values and final actor/institution records are excluded.",
    "Regions and civilizations use world array indices where unambiguous; cities use settlement IDs; learning seats and guilds use their documented world-list IDs.",
    `Named actors: ${actorCount} dated observations searchable through the selected turn. Person IDs are unavailable; observations are not combined into life histories.`,
    "Aliases use dated snapshot names and language word forms only; undated final suffixes, language labels and person names are excluded. No dated alias means alias history is unknown.",
    "Events are not entity identities and are not mined for names. Language form tick T becomes visible at completed snapshot T+1; prehistoric forms are visible from turn 0. Alias dates show this snapshot clock.",
  ] };
}

export function searchHistoricalEntities(index: HistoricalSearchIndex, query: string, kind: HistoricalSearchKind | "all" = "all", limit = 30) {
  const terms = normalize(query).split(/\s+/).filter(Boolean);
  const cap = Math.max(0, Math.min(100, limit));
  const items: HistoricalSearchResult[] = [];
  let total = 0;
  const matches = (name: string) => terms.every((term) => normalize(name).includes(term));
  for (const item of index.items) {
    if ((kind === "all" || item.kind === kind) && matches([item.name, ...item.aliases.map((alias) => alias.name)].join(" "))) {
      total += 1;
      if (items.length < cap) items.push(item);
    }
  }
  if (kind === "all" || kind === "actor") index.visitActors?.((name, turn, sourceRef, role, civ) => {
    if (!matches(name)) return;
    total += 1;
    if (items.length < cap) items.push({ kind: "actor", identity: null, name, turn, sourceRef,
      firstRecordedTurn: turn, lastRecordedTurn: turn, status: `${role} observed in ${civ} at snapshot ${turn}.`, aliases: [],
      ambiguity: "Person identity unrecorded; repeated names may describe different people. This is one observation, not a life history." });
  });
  return { items, total };
}
