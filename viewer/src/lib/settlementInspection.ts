import type { TurnSnapshot } from "../types";

// The historical export is intentionally narrower than the terminal Settlement.
export type SettlementSnapshot = Partial<Pick<TurnSnapshot,
  "turn" | "active_settlements" | "settlement_source_turn" | "founded_this_turn" | "dissolved_this_turn"
>>;

export interface RecordedSettlementValue<T> {
  value: T | null;
  source: string;
  unavailable: string | null;
}

export interface SettlementInspection {
  requestedTurn: number;
  settlementId: number | null;
  state: "available" | "not-listed" | "dissolved" | "unavailable";
  explanation: string;
  source: string;
  sourceTurn: RecordedSettlementValue<number>;
  observationAge: number | null;
  freshness: "same-turn" | "stale" | "unavailable";
  founded: RecordedSettlementValue<boolean>;
  dissolved: RecordedSettlementValue<boolean>;
  summary: {
    name: RecordedSettlementValue<string>;
    region: RecordedSettlementValue<string>;
    population: RecordedSettlementValue<number>;
    centroidX: RecordedSettlementValue<number>;
    centroidY: RecordedSettlementValue<number>;
    foundingTurn: RecordedSettlementValue<number>;
    status: RecordedSettlementValue<string>;
  } | null;
}

const turn = (value: unknown): value is number => typeof value === "number"
  && Number.isSafeInteger(value) && value >= 0;
export const isSettlementId = (value: unknown): value is number => turn(value) && value > 0;
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const text = (value: unknown): value is string => typeof value === "string" && value.trim() !== "";
const record = (value: unknown): value is Record<string, unknown> => !!value
  && typeof value === "object" && !Array.isArray(value);

function recorded<T>(value: unknown, valid: (value: unknown) => value is T, source: string): RecordedSettlementValue<T> {
  return valid(value) ? { value, source, unavailable: null }
    : { value: null, source, unavailable: value == null ? "Not recorded" : "Invalid recorded value" };
}

/** Inspect only the supplied exact-turn snapshot. There is no world-state fallback. */
export function inspectSettlement({ requestedTurn, settlementId, snapshot, sourcePath = "snapshot" }: {
  requestedTurn: number;
  settlementId: number | null;
  snapshot: SettlementSnapshot | null | undefined;
  sourcePath?: string;
}): SettlementInspection {
  const sourceTurn = recorded(snapshot?.settlement_source_turn, turn, `${sourcePath}/settlement_source_turn`);
  const lifecycle = (key: "founded_this_turn" | "dissolved_this_turn"): RecordedSettlementValue<boolean> => {
    const values = snapshot?.[key];
    const source = `${sourcePath}/${key}`;
    if (!Array.isArray(values) || !values.every(isSettlementId)) {
      return { value: null, source, unavailable: values == null ? "Not recorded" : "Invalid recorded list" };
    }
    const index = values.indexOf(settlementId as number);
    return { value: index >= 0, source: index >= 0 ? `${source}/${index}` : source, unavailable: null };
  };
  const result: SettlementInspection = {
    requestedTurn, settlementId, state: "unavailable", explanation: "", source: sourcePath,
    sourceTurn, observationAge: null, freshness: "unavailable",
    founded: { value: null, source: `${sourcePath}/founded_this_turn`, unavailable: "No usable snapshot" },
    dissolved: { value: null, source: `${sourcePath}/dissolved_this_turn`, unavailable: "No usable snapshot" },
    summary: null,
  };
  if (!turn(requestedTurn)) return { ...result, explanation: "Requested turn must be a nonnegative whole number." };
  if (!isSettlementId(settlementId)) return { ...result, explanation: "Select a positive whole settlement ID; ID 0 means no settlement." };
  if (!snapshot) return { ...result, explanation: "No historical snapshot recorded for this turn. Values are unavailable." };
  if (!turn(snapshot.turn) || snapshot.turn !== requestedTurn) {
    return { ...result, explanation: "Snapshot timestamp is missing, invalid, or does not match the requested turn." };
  }
  if (sourceTurn.value !== null && sourceTurn.value > requestedTurn) {
    return { ...result, explanation: "Settlement source turn is later than the requested turn. Values are unavailable." };
  }
  if (sourceTurn.value !== null) {
    result.observationAge = requestedTurn - sourceTurn.value;
    result.freshness = result.observationAge > 0 ? "stale" : "same-turn";
  }
  result.founded = lifecycle("founded_this_turn");
  result.dissolved = lifecycle("dissolved_this_turn");
  const summaries = snapshot.active_settlements;
  if (!Array.isArray(summaries)) {
    return { ...result, explanation: "Historical active settlement summaries are unavailable." };
  }
  // An invalid identity makes absence unverifiable, but does not hide a unique valid match.
  const matches = summaries.flatMap((row, index) => record(row) && row.settlement_id === settlementId ? [{ row, index }] : []);
  if (matches.length > 1 || (matches.length > 0 && result.dissolved.value === true)
    || (result.founded.value === true && result.dissolved.value === true)) {
    return { ...result, explanation: "Conflicting settlement records in this snapshot. Values are unavailable." };
  }
  if (matches.length === 0) {
    if (summaries.some((row) => !record(row) || !isSettlementId(row.settlement_id))) {
      return { ...result, explanation: "Invalid settlement identities in this snapshot; absence cannot be verified." };
    }
    return { ...result, state: result.dissolved.value === true ? "dissolved" : "not-listed",
      explanation: result.dissolved.value === true
        ? "Dissolution recorded in this snapshot. No active summary is present."
        : "Settlement is not listed in this snapshot. Absence does not establish founding or dissolution." };
  }
  const { row, index } = matches[0];
  if (turn(row.founding_turn) && row.founding_turn > requestedTurn) {
    return { ...result, explanation: "Recorded founding turn is later than this snapshot. Values are unavailable." };
  }
  const source = `${sourcePath}/active_settlements/${index}`;
  return { ...result, state: "available", source,
    explanation: "Recorded historical summary; population is an estimate and centroids use exported coordinate units.",
    summary: {
      name: recorded(row.name, text, `${source}/name`),
      region: recorded(row.region_name, text, `${source}/region_name`),
      population: recorded(row.population_estimate, turn, `${source}/population_estimate`),
      centroidX: recorded(row.centroid_x, finite, `${source}/centroid_x`),
      centroidY: recorded(row.centroid_y, finite, `${source}/centroid_y`),
      foundingTurn: recorded(row.founding_turn, turn, `${source}/founding_turn`),
      status: recorded(row.status, (value): value is string => value === "active" || value === "dissolving", `${source}/status`),
    },
  };
}

function recordedDissolution(history: readonly SettlementSnapshot[], settlementId: number | null) {
  let earliest: { turn: number; source: string } | null = null;
  history.forEach((snapshot, index) => {
    const ids = snapshot.dissolved_this_turn;
    if (!turn(snapshot.turn) || !Array.isArray(ids) || !ids.every(isSettlementId) || !ids.includes(settlementId as number)) return;
    // Untimestamped source data still records a list at a timestamped history row.
    // Explicitly invalid/future source timestamps cannot establish a tombstone.
    if (snapshot.settlement_source_turn != null
      && (!turn(snapshot.settlement_source_turn) || snapshot.settlement_source_turn > snapshot.turn)) return;
    if (earliest === null || snapshot.turn < earliest.turn) {
      earliest = { turn: snapshot.turn, source: `/history/${index}/dissolved_this_turn/${ids.indexOf(settlementId as number)}` };
    }
  });
  return earliest;
}

function rejectResurrection(inspection: SettlementInspection, dissolution: { turn: number; source: string } | null): SettlementInspection {
  // IDs are monotonic in the producer and dissolved settlements are removed permanently.
  // Do not carry lifecycle or values into absent/gap observations; only reject a contradiction.
  if (inspection.summary && dissolution && dissolution.turn < inspection.requestedTurn) {
    return { ...inspection, state: "unavailable", summary: null,
      explanation: `Active summary conflicts with an earlier recorded dissolution at history turn ${dissolution.turn} (${dissolution.source}). Values are unavailable.` };
  }
  return inspection;
}

/** Keep input history order and pointers; reject ambiguous exact-turn observations. */
export function inspectSettlementHistory(history: readonly SettlementSnapshot[], requestedTurn: number, settlementId: number | null) {
  const matches = history.flatMap((snapshot, index) => snapshot.turn === requestedTurn ? [{ snapshot, index }] : []);
  if (matches.length > 1) {
    return { ...inspectSettlement({ requestedTurn, settlementId, snapshot: null, sourcePath: "/history" }),
      explanation: "Multiple historical snapshots record this turn. Values are unavailable until the source is disambiguated." };
  }
  const match = matches[0];
  return rejectResurrection(inspectSettlement({ requestedTurn, settlementId, snapshot: match?.snapshot,
    sourcePath: match ? `/history/${match.index}` : "/history" }), recordedDissolution(history, settlementId));
}

/** Options come only from the requested snapshot, in meaningful export order. */
export function settlementOptions(history: readonly SettlementSnapshot[], requestedTurn: number): { id: number; label: string }[] {
  if (!turn(requestedTurn)) return [];
  const snapshots = history.filter((snapshot) => snapshot.turn === requestedTurn);
  if (snapshots.length !== 1) return [];
  const snapshot = snapshots[0];
  const options = new Map<number, string>();
  if (Array.isArray(snapshot.active_settlements)) {
    for (const row of snapshot.active_settlements) {
      if (record(row) && isSettlementId(row.settlement_id) && !options.has(row.settlement_id)) {
        options.set(row.settlement_id, `${text(row.name) ? row.name : "Settlement"} · #${row.settlement_id}`);
      }
    }
  }
  for (const ids of [snapshot.founded_this_turn, snapshot.dissolved_this_turn]) {
    if (Array.isArray(ids)) for (const id of ids) if (isSettlementId(id) && !options.has(id)) options.set(id, `Settlement #${id}`);
  }
  return [...options].map(([id, label]) => ({ id, label }));
}

/** Historical population samples only; no interpolation or terminal-state growth. */
export function settlementPopulationHistory(history: readonly SettlementSnapshot[], requestedTurn: number, settlementId: number | null) {
  if (!turn(requestedTurn) || !isSettlementId(settlementId)) return [];
  const dissolution = recordedDissolution(history, settlementId);
  const counts = new Map<number, number>();
  for (const snapshot of history) if (turn(snapshot.turn)) counts.set(snapshot.turn, (counts.get(snapshot.turn) ?? 0) + 1);
  return history.flatMap((snapshot, index) => {
    if (!turn(snapshot.turn) || snapshot.turn > requestedTurn) return [];
    const inspection = counts.get(snapshot.turn) === 1
      ? inspectSettlement({ requestedTurn: snapshot.turn, settlementId, snapshot, sourcePath: `/history/${index}` })
      : inspectSettlementHistory(history, snapshot.turn, settlementId);
    return [{ turn: snapshot.turn, inspection: rejectResurrection(inspection, dissolution) }];
  });
}
