/** Exact completed-tick evidence. Event drivers are never assigned to flow pairs. */
import type { Bundle, Event } from "../types";
import { migrationDriverKind, migrationFlows, netMigration } from "./food";
import { exactSnapshot } from "./historyComparison";
import { readRegionalPopulation } from "./regionalPopulation";

export interface MigrationEvidenceFlow {
  fromIndex: number;
  toIndex: number;
  fromName: string;
  toName: string;
  agents: number;
  sourcePointers: string[];
  reason: null;
}

export interface MigrationEventContext {
  event: Event;
  regionIndex: number;
  sourcePointer: string;
  dominantUtilityTerm: string | null;
}

export interface MigrationPopulationChange {
  before: number;
  after: number;
  delta: number;
  sourcePointers: [string, string];
  beforeSource: string;
  afterSource: string;
  beforeMode: string;
  afterMode: string;
}

export interface MigrationEvidenceReading {
  status: "recorded" | "not-recorded" | "invalid" | "unavailable";
  note: string;
  snapshotTurn: number;
  sourceTick: number;
  completedTick: number;
  sourcePointer: string | null;
  selectedRegionIndex: number | null;
  flows: MigrationEvidenceFlow[];
  totalAgents: number | null;
  netAgents: number | null;
  context: MigrationEventContext[];
  populationChange: MigrationPopulationChange | null;
}

export function readMigrationEvidence(
  bundle: Bundle,
  turn: number,
  selectedRegionIndex?: number | null,
): MigrationEvidenceReading {
  const selected = selectedRegionIndex ?? null;
  const reading: MigrationEvidenceReading = {
    status: "unavailable", note: "No exact, unambiguous snapshot at the selected turn.",
    snapshotTurn: turn, sourceTick: turn - 1, completedTick: turn - 1,
    sourcePointer: null, selectedRegionIndex: selected,
    flows: [], totalAgents: null, netAgents: null, context: [], populationChange: null,
  };
  const regions = bundle.world_state.regions;
  if (selected !== null && (!Number.isSafeInteger(selected) || selected < 0 || selected >= regions.length)) {
    return { ...reading, note: "Selected region index is outside the recorded world layout." };
  }
  if (!Number.isSafeInteger(turn) || turn < 1) return reading;
  const snapshot = exactSnapshot(bundle, turn);
  if (!snapshot) return reading;
  const snapshotIndex = bundle.history.indexOf(snapshot);
  reading.sourcePointer = `/history/${snapshotIndex}/migration`;

  // Population is a separate observation even when migration was not exported.
  const prior = exactSnapshot(bundle, turn - 1);
  const before = readRegionalPopulation(bundle, prior);
  const after = readRegionalPopulation(bundle, snapshot);
  if (selected !== null && before && after && prior) {
    reading.populationChange = {
      before: before.counts[selected], after: after.counts[selected],
      delta: after.counts[selected] - before.counts[selected],
      sourcePointers: [
        `/history/${bundle.history.indexOf(prior)}/regional_population/counts/${selected}`,
        `/history/${snapshotIndex}/regional_population/counts/${selected}`,
      ],
      beforeSource: before.sources[selected], afterSource: after.sources[selected],
      beforeMode: before.mode, afterMode: after.mode,
    };
  }

  // These reports describe a group, not a reason allocated to any flow triple.
  bundle.events_timeline.forEach((event, index) => {
    if (event.turn !== turn - 1 || !["mass_migration", "notable_migration"].includes(event.event_type)) return;
    const matches = regions.flatMap((region, regionIndex) => region.name === event.region ? [regionIndex] : []);
    if (matches.length !== 1 || (selected !== null && matches[0] !== selected)) return;
    reading.context.push({ event, regionIndex: matches[0], sourcePointer: `/events_timeline/${index}`,
      dominantUtilityTerm: typeof event.driver === "string" ? migrationDriverKind(event.driver) : null });
  });

  if (snapshot.migration == null) {
    return { ...reading, status: "not-recorded", note: "Native migration not recorded; movement is unknown." };
  }
  const rows = snapshot.migration;
  const invalid = () => ({ ...reading, status: "invalid" as const,
    note: "Malformed native migration record; movement is unknown." });
  if (!Array.isArray(rows)) return invalid();
  let total = 0;
  const pointers = new Map<string, string[]>();
  for (const [index, row] of rows.entries()) {
    if (!Array.isArray(row) || row.length !== 3
      || !Array.from(row).every((value) => Number.isSafeInteger(value) && value >= 0)
      || row[0] >= regions.length || row[1] >= regions.length) return invalid();
    total += row[2];
    if (!Number.isSafeInteger(total)) return invalid();
    const key = `${row[0]}>${row[1]}`;
    const sources = pointers.get(key) ?? [];
    sources.push(`${reading.sourcePointer}/${index}`);
    pointers.set(key, sources);
  }

  // Existing readers own pair aggregation and net calculation. Numeric keys
  // preserve region identity even if two static layout names happen to match.
  const pairs = migrationFlows([snapshot], turn, 1, regions.map((_, index) => String(index)));
  const net = netMigration(pairs);
  reading.flows = pairs.filter((pair) => selected === null || Number(pair.from) === selected || Number(pair.to) === selected)
    .map((pair) => ({
      fromIndex: Number(pair.from), toIndex: Number(pair.to),
      fromName: regions[Number(pair.from)].name, toName: regions[Number(pair.to)].name,
      agents: pair.amount, sourcePointers: pointers.get(`${pair.from}>${pair.to}`)!, reason: null,
    }));
  reading.totalAgents = reading.flows.reduce((sum, flow) => sum + flow.agents, 0);
  reading.netAgents = selected === null ? null : net.get(String(selected)) ?? 0;
  return { ...reading, status: "recorded", note: rows.length === 0
    ? "Recorded empty flow list: zero native agents moved this completed tick."
    : reading.flows.length === 0 ? "Recorded flows contain no movement involving this region."
      : "Recorded native agent moves; reasons for individual flows are unknown." };
}
