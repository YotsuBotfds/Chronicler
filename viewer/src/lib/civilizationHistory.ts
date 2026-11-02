/** Recorded civilization history, bounded by completed snapshot turn. No inferred life cycle. */
import type { Bundle, CivSnapshot, Event, NamedEvent } from "../types";
import { actorEventsUpTo, eventKey, eventKeyCount } from "./bundleIndex";

export interface CivilizationHistoryEvent {
  event: Event | NamedEvent;
  /** Only timeline events can use the existing event inspector. */
  timelineEvent: Event | null;
  /** Completed snapshot T follows event tick T-1. */
  visibleTurn: number;
  source: string;
  inspectable: boolean;
}
export interface CivilizationHistoryRegion { name: string; regionIndex: number | null }
export interface CivilizationHistoryEntry {
  turn: number;
  recorded: boolean;
  status: string;
  source: string;
  population: number | null;
  treasury: number | null;
  stability: number | null;
  military: number | null;
  alive: boolean | null;
  leader: string | null;
  era: string | null;
  regions: CivilizationHistoryRegion[] | null;
  observations: string[];
  events: CivilizationHistoryEvent[];
}
export interface CivilizationLineage {
  parentIndex: number;
  childIndex: number;
  parentName: string;
  childName: string;
  visibleTurn: number;
  source: string;
}
export interface CivilizationHistoryResult {
  civilizationIndex: number;
  name: string | null;
  through: number;
  status: string;
  entries: CivilizationHistoryEntry[];
  lineage: CivilizationLineage[];
  notes: string[];
}
const numeric = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : null;
const text = (value: unknown) => typeof value === "string" && value.length > 0 ? value : null;
const uniqueIndex = (rows: { name: string }[], name: string) => {
  const ids = rows.flatMap((row, index) => row.name === name ? [index] : []);
  return ids.length === 1 ? ids[0] : null;
};
const NOTES = [
  "Identity is the selected index in world_state.civilizations. Legacy history and event names match only an unambiguous world name; aliases are not inferred.",
  "Snapshot T follows simulation tick T−1. Events stop at tick selectedTurn−1; observations use exact recorded snapshots only.",
  "First observation is not a foundation. A changed leader name is not evidence of death, succession or coup. Missing rows and gaps are unknown, not collapse or restoration.",
  "The recorded alive flag measures whether the civilization holds regions; it does not establish permanent extinction or exclude a government in exile.",
  "Version-5 pruning can omit later dead-civilization rows. The viewer does not reconstruct pruned_civ_stats or carry final values into those gaps.",
  "A restoration event may concern a realm or an individual ruler. Its recorded description is preserved; no new identity, predecessor or successor is inferred.",
];

/** Reuses the array-keyed actor/event-key indexes; adds no alternate bundle cache. */
export function civilizationHistory(bundle: Bundle, currentTurn: number, civilizationIndex: number): CivilizationHistoryResult {
  const result: CivilizationHistoryResult = { civilizationIndex, name: null, through: currentTurn,
    status: "Civilization identity unavailable", entries: [], lineage: [], notes: NOTES };
  if (!Number.isSafeInteger(civilizationIndex) || civilizationIndex < 0 || !Number.isSafeInteger(currentTurn) || currentTurn < 1) return result;
  const civ = bundle.world_state.civilizations[civilizationIndex];
  if (!civ || uniqueIndex(bundle.world_state.civilizations, civ.name) !== civilizationIndex) {
    return { ...result, status: "Civilization identity unavailable or ambiguous" };
  }
  const samples = new Map<number, { snapshot: Bundle["history"][number]; index: number }[]>();
  bundle.history.forEach((snapshot, index) => {
    if (!Number.isSafeInteger(snapshot.turn) || snapshot.turn < 1 || snapshot.turn > currentTurn) return;
    const rows = samples.get(snapshot.turn) ?? [];
    rows.push({ snapshot, index }); samples.set(snapshot.turn, rows);
  });
  const events = actorEventsUpTo(bundle.events_timeline, civ.name, currentTurn - 1)
    .filter((event) => Number.isSafeInteger(event.turn) && event.turn >= 0);
  const known = [...samples.values()].some((rows) => rows.length === 1 && Object.hasOwn(rows[0].snapshot.civ_stats, civ.name)) || events.length > 0
    || actorEventsUpTo(bundle.named_events, civ.name, currentTurn - 1).some((event) => Number.isSafeInteger(event.turn) && event.turn >= 0);
  if (!known) return { ...result, status: "No unambiguous civilization observation or attributed event through the selected turn" };
  result.name = civ.name;
  const byTurn = new Map<number, CivilizationHistoryEvent[]>();
  for (const event of events) {
    const visibleTurn = event.turn + 1;
    const refs = byTurn.get(visibleTurn) ?? [];
    const key = eventKey(event), inspectable = eventKeyCount(bundle.events_timeline, key) === 1;
    refs.push({ event, timelineEvent: event, visibleTurn, inspectable,
      source: `events_timeline: tick ${event.turn}, type ${event.event_type}${event.event_id ? `, event_id ${event.event_id}` : ""}${inspectable ? "" : " (selection key ambiguous)"}` });
    byTurn.set(visibleTurn, refs);
    // Python politics.secession explicitly records parent then child. Require
    // unique identities AND exact rows for both at this completed event turn.
    if (event.event_type === "secession" && event.actors.length === 2 && inspectable) {
      const [parentName, childName] = event.actors;
      const parentIndex = uniqueIndex(bundle.world_state.civilizations, parentName);
      const childIndex = uniqueIndex(bundle.world_state.civilizations, childName);
      const at = samples.get(visibleTurn);
      if (parentIndex !== null && childIndex !== null && parentIndex !== childIndex && at?.length === 1
        && Object.hasOwn(at[0].snapshot.civ_stats, parentName) && Object.hasOwn(at[0].snapshot.civ_stats, childName)) {
        result.lineage.push({ parentIndex, childIndex, parentName, childName, visibleTurn, source: refs[refs.length - 1].source });
      }
    }
  }
  // NamedEvent stores some leadership milestones (for example coups) that
  // need not have a selectable timeline Event. Preserve its source and shape.
  const named = actorEventsUpTo(bundle.named_events, civ.name, currentTurn - 1)
    .filter((event) => Number.isSafeInteger(event.turn) && event.turn >= 0);
  for (const event of named) {
    const visibleTurn = event.turn + 1;
    const refs = byTurn.get(visibleTurn) ?? [];
    refs.unshift({ event, timelineEvent: null, visibleTurn, inspectable: false,
      source: `named_events: tick ${event.turn}, type ${event.event_type}, name ${event.name}` });
    byTurn.set(visibleTurn, refs);
  }
  const turns = [...new Set([...samples.keys(), ...byTurn.keys(), currentTurn])].sort((a, b) => a - b);
  let previous: CivilizationHistoryEntry | null = null;
  for (const turn of turns) {
    const at = samples.get(turn);
    const row: CivSnapshot | null = at?.length === 1 && Object.hasOwn(at[0].snapshot.civ_stats, civ.name)
      ? at[0].snapshot.civ_stats[civ.name] ?? null : null;
    const regionNames = row && Array.isArray(row.regions) && row.regions.every((name) => typeof name === "string")
      ? [...new Set(row.regions)] : null;
    const entry: CivilizationHistoryEntry = { turn, recorded: row !== null,
      status: !at ? "Snapshot not recorded" : at.length !== 1 ? "Snapshot ambiguous (duplicate turn)"
        : !row ? "Civilization row not recorded" : "Exact civilization row recorded",
      source: !at ? `history: no exact snapshot at turn ${turn}` : at.length !== 1 ? `history: multiple snapshots at turn ${turn}`
        : `history[${at[0].index}].civ_stats[${JSON.stringify(civ.name)}]${row ? "" : " (absent)"}`,
      population: numeric(row?.population), treasury: numeric(row?.treasury), stability: numeric(row?.stability), military: numeric(row?.military),
      alive: typeof row?.alive === "boolean" ? row.alive : null,
      leader: text(row?.leader_name), era: text(row?.tech_era),
      regions: regionNames?.map((name) => ({ name, regionIndex: uniqueIndex(bundle.world_state.regions, name) })) ?? null,
      observations: [], events: (byTurn.get(turn) ?? []).reverse() };
    if (row) {
      if (!previous) entry.observations.push("First recorded observation in this history; foundation date unknown unless an explicit event records it.");
      else {
        const interval = `Between recorded observations T${previous.turn} and T${turn}`;
        if (previous.alive !== null && entry.alive !== null && previous.alive !== entry.alive)
          entry.observations.push(`${interval}: alive flag ${previous.alive} → ${entry.alive}; no collapse or restoration is inferred.`);
        if (previous.leader !== null && entry.leader !== null && previous.leader !== entry.leader)
          entry.observations.push(`${interval}: leader name ${previous.leader} → ${entry.leader}; reason not inferred.`);
        if (previous.regions !== null && entry.regions !== null) {
          const before = new Set(previous.regions.map((region) => region.name)), after = new Set(regionNames!);
          const added = [...after].filter((name) => !before.has(name)), removed = [...before].filter((name) => !after.has(name));
          if (added.length || removed.length) entry.observations.push(`${interval}: recorded region list added ${added.join(", ") || "none"}; removed ${removed.join(", ") || "none"}. Name changes are not inferred to be conquests.`);
        }
        if (turn > previous.turn + 1) entry.observations.push(`Observations are ${turn - previous.turn} turns apart; intermediate states are not reconstructed.`);
      }
      previous = entry;
    }
    result.entries.push(entry);
  }
  const selected = result.entries.at(-1)!;
  result.status = `${selected.status} at selected turn ${currentTurn}`;
  return result;
}
