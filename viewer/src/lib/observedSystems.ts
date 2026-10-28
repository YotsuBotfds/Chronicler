import type { HarvestForecastSnapshot, RitualGatheringsSnapshot, TurnSnapshot } from "../types";

export type ObservationKey = "health_care" | "harvest_forecasts" | "ritual_gatherings";

const OBSERVATION_EVENT_TYPES = new Set([
  "occupational_injury", "harvest_forecast_issued", "harvest_forecast_delivered", "harvest_forecast_resolved",
  "harvest_preparedness", "harvest_gathering_held", "harvest_gathering_cancelled",
]);

export function isObservationEventType(kind: string | undefined): boolean {
  return kind !== undefined && OBSERVATION_EVENT_TYPES.has(kind);
}

/** Preserve legacy event clocks; these new receipts follow the completed-tick contract. */
export function observationEventKnown(event: { turn: number; event_type?: string }, sourceTurn: number): boolean {
  return !isObservationEventType(event.event_type) || event.turn <= sourceTurn;
}

export function eventSnapshotTurn(event: { turn: number; event_type?: string }): number {
  return event.turn + (isObservationEventType(event.event_type) ? 1 : 0);
}

function knownTurn(value: unknown, source: number): boolean {
  return Number.isInteger(value) && (value as number) <= source;
}

/** Actual evidence must already exist; scheduled delivery/expiry/windows can be future plans. */
function evidenceKnown(record: NonNullable<TurnSnapshot[ObservationKey]>, key: ObservationKey): boolean {
  const source = record.source_turn;
  if (key === "harvest_forecasts") {
    const forecasts = record as HarvestForecastSnapshot;
    if (!Array.isArray(forecasts.reports) || !Array.isArray(forecasts.outcomes)) return false;
    return [...forecasts.reports, ...forecasts.outcomes].every((row) => row && knownTurn(row.issued_turn, source)
      && (row.delivered_turn == null || knownTurn(row.delivered_turn, source))
      && (row.resolved_turn == null || knownTurn(row.resolved_turn, source)));
  }
  if (key === "ritual_gatherings") {
    const gatherings = record as RitualGatheringsSnapshot;
    if (!Array.isArray(gatherings.outcomes) || !Array.isArray(gatherings.schedules)) return false;
    return gatherings.outcomes.every((row) => row && knownTurn(row.turn, source))
      && gatherings.schedules.every((row) => row && (row.last_turn == null || knownTurn(row.last_turn, source)));
  }
  return true;
}

/** A snapshot T can report only its completed simulation tick T-1. */
export function observationAt<K extends ObservationKey>(snapshot: TurnSnapshot | null, key: K): NonNullable<TurnSnapshot[K]> | null {
  const record = snapshot?.[key];
  return record && record.source_turn === snapshot!.turn - 1 && evidenceKnown(record, key)
    ? record as NonNullable<TurnSnapshot[K]> : null;
}

export function hasObservation(history: TurnSnapshot[], key: ObservationKey): boolean {
  return history.some((snapshot) => snapshot[key] != null);
}
