import type { TurnSnapshot } from "../types";

export type ObservationKey = "health_care" | "harvest_forecasts" | "ritual_gatherings";

/** A snapshot T can report only its completed simulation tick T-1. */
export function observationAt<K extends ObservationKey>(snapshot: TurnSnapshot | null, key: K): NonNullable<TurnSnapshot[K]> | null {
  const record = snapshot?.[key];
  return record && record.source_turn === snapshot!.turn - 1 ? record as NonNullable<TurnSnapshot[K]> : null;
}

export function hasObservation(history: TurnSnapshot[], key: ObservationKey): boolean {
  return history.some((snapshot) => snapshot[key] != null);
}
