import { finite as number, count as validTurn } from "./recordGuards";
import type { Bundle, CitySnapshotRow, Event } from "../types";
import type { HistoricalSearchResult } from "./historicalSearch";
import { charterLabel, rankLabel } from "./cities";

export type InstitutionHistorySelection = Pick<HistoricalSearchResult, "kind" | "identity" | "sourceRef">;
export interface CityObservation {
  turn: number;
  sourceRef: string;
  status: "recorded" | "absent" | "unavailable" | "ambiguous";
  explanation: string;
  row: CitySnapshotRow | null;
}
export interface InstitutionEndpointChange {
  from: number;
  to: number;
  continuousCoverage: boolean;
  fields: Array<{ label: string; before: string; after: string; delta: number | null; beforeSource: string; afterSource: string }>;
}
export interface InstitutionMoment {
  turn: number;
  sourceTurn: number;
  kind: string;
  sourceRef: string;
  eventRef: string | null;
  event: Event | null;
  status: string;
}
export interface InstitutionHistoryReading {
  supported: boolean;
  status: string;
  name: string;
  id: number | null;
  through: number;
  firstRecordedTurn: number | null;
  lastRecordedTurn: number | null;
  selected: CityObservation | null;
  observations: CityObservation[];
  changes: InstitutionEndpointChange[];
  moments: InstitutionMoment[];
  related: Array<{ kind: "region" | "civilization"; name: string }>;
  coverage: string[];
}
const str = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const valueLabel = (value: unknown) => value == null || (typeof value === "number" && !number(value)) ? "Not recorded" : String(value);

const fields: Array<{ key: keyof CitySnapshotRow; label: string; format?: (value: number) => string }> = [
  { key: "name", label: "Recorded name" }, { key: "region", label: "Recorded region" }, { key: "lord", label: "Recorded lord" },
  { key: "rank", label: "Rank", format: rankLabel }, { key: "residents", label: "Residents" }, { key: "wealth", label: "Civic purse" },
  { key: "charter", label: "Charter", format: charterLabel }, { key: "unrest", label: "Unrest" },
  { key: "satisfaction", label: "Satisfaction" }, { key: "crafts", label: "Wares" },
];
export function institutionObservationValues(row: CitySnapshotRow) {
  return fields.map((field) => ({ label: field.label,
    value: field.format && number(row[field.key]) ? field.format(row[field.key] as number) : valueLabel(row[field.key]), key: field.key }));
}

/** A city history is a history of recorded settlement IDs, never an inferred institutional lifetime. */
export function readInstitutionHistory(bundle: Bundle, through: number, selection: InstitutionHistorySelection | null): InstitutionHistoryReading {
  const result: InstitutionHistoryReading = { supported: false, status: "Choose a city from historical search. City histories are supported; learning-seat and guild lifecycles are not yet supported here.",
    name: "City history", id: null, through, firstRecordedTurn: null, lastRecordedTurn: null, selected: null,
    observations: [], changes: [], moments: [], related: [], coverage: [] };
  if (selection?.kind === "city" && selection.identity === null) {
    result.status = "Selected city identity is unresolved. A stable settlement ID is required; a name or source address cannot substitute for identity.";
    return result;
  }
  if (!selection || selection.kind !== "city" || selection.identity?.namespace !== "city") return result;
  const cityId = selection.identity.index;
  if (!validTurn(cityId) || !validTurn(through)) { result.status = "City identity or selected turn is unavailable."; return result; }
  result.supported = true;
  result.id = cityId;
  result.name = `City ${cityId} (name unknown)`;
  const snapshots = new Map<number, Array<{ index: number; snapshot: Bundle["history"][number] }>>();
  bundle.history.forEach((snapshot, index) => {
    if (validTurn(snapshot.turn) && snapshot.turn <= through) snapshots.set(snapshot.turn, [...(snapshots.get(snapshot.turn) ?? []), { snapshot, index }]);
  });
  for (const [turn, matches] of [...snapshots.entries()].sort((a, b) => a[0] - b[0])) {
    const { snapshot, index } = matches[0];
    const sourceRef = `/history/${index}/cities`;
    const rows = snapshot.cities?.cities.map((row, rowIndex) => ({ row, rowIndex })).filter(({ row }) => row.id === cityId) ?? [];
    const item: CityObservation = { turn, sourceRef, status: "recorded", explanation: "City row recorded at this snapshot.", row: null };
    if (matches.length !== 1) { item.status = "ambiguous"; item.explanation = "Duplicate snapshot turn; city values are ambiguous."; }
    else if (!snapshot.cities) { item.status = "unavailable"; item.explanation = "City observations not recorded in this snapshot (older data, disabled or unavailable)."; }
    else if (rows.length > 1) { item.status = "ambiguous"; item.explanation = "Duplicate city ID in this snapshot; values and relationships are ambiguous."; }
    else if (rows.length === 0) { item.status = "absent"; item.explanation = "ID absent from the recorded city list; no foundation, destruction or rebuilding is inferred."; }
    else { item.row = { ...rows[0].row }; item.sourceRef += `/cities/${rows[0].rowIndex}`; }
    result.observations.push(item);
  }
  const observed = result.observations.filter((item) => item.row !== null);
  result.firstRecordedTurn = observed[0]?.turn ?? null;
  result.lastRecordedTurn = observed.at(-1)?.turn ?? null;
  const name = observed.at(-1)?.row?.name;
  if (str(name)) result.name = name;
  result.selected = result.observations.find((item) => item.turn === through) ?? {
    turn: through, sourceRef: "/history", status: "unavailable", explanation: "Selected snapshot not recorded; earlier values are not carried forward.", row: null,
  };
  result.status = result.selected.explanation;
  for (let index = 1; index < observed.length; index++) {
    const before = observed[index - 1], after = observed[index];
    const first = before.row!, last = after.row!;
    const changed: InstitutionEndpointChange["fields"] = [];
    for (const field of fields) {
      const a = first[field.key], b = last[field.key];
      // Missing optional values are coverage gaps, not a measured change to/from zero.
      if (a == null || b == null || a === b || (typeof a === "number" && !number(a)) || (typeof b === "number" && !number(b))) continue;
      changed.push({ label: field.label, before: field.format && number(a) ? field.format(a) : valueLabel(a),
        after: field.format && number(b) ? field.format(b) : valueLabel(b), delta: number(a) && number(b) ? b - a : null,
        beforeSource: `${before.sourceRef}/${field.key}`, afterSource: `${after.sourceRef}/${field.key}` });
    }
    if (changed.length) result.changes.push({ from: before.turn, to: after.turn,
      continuousCoverage: after.turn === before.turn + 1, fields: changed });
  }
  const selectedRow = result.selected.row;
  if (selectedRow) {
    const exact = snapshots.get(through)![0].snapshot;
    if (str(selectedRow.region) && bundle.world_state.regions.filter((region) => region.name === selectedRow.region).length === 1) {
      result.related.push({ kind: "region", name: selectedRow.region });
    }
    if (str(selectedRow.lord) && exact.civ_stats[selectedRow.lord] && bundle.world_state.civilizations.filter((civ) => civ.name === selectedRow.lord).length === 1) {
      result.related.push({ kind: "civilization", name: selectedRow.lord });
    }
  }
  const finalRecords = [
    ...(bundle.world_state.cities?.cities ?? []).map((record, index) => ({ record, source: `/world_state/cities/cities/${index}` })),
    ...(bundle.world_state.cities?.fallen ?? []).map((record, index) => ({ record, source: `/world_state/cities/fallen/${index}` })),
  ].filter(({ record }) => record.settlement_id === cityId);
  if (finalRecords.length === 1) {
    const { record, source } = finalRecords[0];
    const eventsById = new Map<string, Array<{ event: Event; eventIndex: number }>>();
    bundle.events_timeline.forEach((event, eventIndex) => {
      if (str(event.event_id)) eventsById.set(event.event_id, [...(eventsById.get(event.event_id) ?? []), { event, eventIndex }]);
    });
    record.history.forEach(([tick, kind, eventId], index) => {
      if (!validTurn(tick) || tick + 1 > through || !str(kind)) return;
      const matching = str(eventId) ? eventsById.get(eventId) ?? [] : [];
      const linked = matching.length === 1 && matching[0].event.turn === tick ? matching[0] : null;
      result.moments.push({ turn: tick + 1, sourceTurn: tick, kind, sourceRef: `${source}/history/${index}`,
        event: linked?.event ?? null, eventRef: linked ? `/events_timeline/${linked.eventIndex}` : null,
        status: linked ? "Explicit city-ID history entry with a unique same-tick backend event reference."
          : "Explicit dated city-ID history entry; event reference missing, duplicated or clock-mismatched. No event is guessed." });
    });
    result.moments.sort((a, b) => b.turn - a.turn);
  }
  result.coverage = [
    `${observed.length} unique city observations through selected turn ${through}; first/last observed are not foundation or lifetime dates. Missing, absent and duplicate rows remain unknown.`,
    "Snapshot T follows completed tick T−1. City history/event tick T is shown at snapshot T+1. Final names, region, lord, peaks and fall-cause fields are not used.",
    finalRecords.length === 1 ? "Lifecycle moments come only from this settlement ID's explicit dated history. The backend caps retained city history at 60 moments; missing events or moments are not invented."
      : finalRecords.length > 1 ? "Duplicate final city IDs: lifecycle history is ambiguous and excluded. Snapshot values remain independently dated."
        : "No final city-ID history record: founding, falls and other lifecycle moments are unknown; snapshot observations remain available.",
    "Endpoint changes show recorded values, not causal effects or benefits. Sparse endpoints do not locate a change within the window. Positive purse/population changes do not prove recovery.",
    "A settlement ID is not proof of uninterrupted institutional survival: disabling cities can reset records. Reappearance, resiting and restoration are not inferred, and different IDs with the same name are never joined.",
    "Related region/lord links use only the exact selected city snapshot and unambiguous recorded names. No current-world ownership fills historical gaps.",
  ];
  return result;
}
