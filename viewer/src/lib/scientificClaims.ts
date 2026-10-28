import type { ScientificContext, ScientificTrial, TurnSnapshot } from "../types";
import { observationAt } from "./observedSystems";
import type { SeriesRow } from "./systems";

export function scientificContext(context?: ScientificContext): string {
  return context ? `${context.crop}; soil band ${context.soil_band}, water band ${context.water_band}; season ${context.season}; ${context.climate_phase}; crew ${context.crew}; ${context.protocol}` : "Context not recorded";
}

export interface ObservedScientificTrial extends ScientificTrial {
  snapshot_turn: number;
  recipe: string;
  seat_name: string;
}

/** Retain dated resolutions only; an old row repeated in a later summary is not new evidence. */
export function scientificTrials(history: TurnSnapshot[], through: number): ObservedScientificTrial[] {
  const trials = new Map<string, ObservedScientificTrial>();
  for (const snapshot of history) {
    if (snapshot.turn > through) continue;
    const record = observationAt(snapshot, "scientific_claims");
    for (const row of record?.trials_resolved ?? []) {
      if (row.resolved_turn !== record!.source_turn) continue;
      const key = `${row.funded_turn}:${row.id}:${row.resolved_turn}`;
      if (!trials.has(key)) trials.set(key, { ...row, snapshot_turn: snapshot.turn,
        recipe: record!.propositions.find((claim) => claim.id === row.claim)?.recipe ?? `Claim ${row.claim}`,
        seat_name: record!.beliefs.find((belief) => belief.seat === row.seat)?.seat_name ?? `Seat ${row.seat}` });
    }
  }
  return [...trials.values()].sort((a, b) => b.resolved_turn! - a.resolved_turn! || a.id - b.id);
}

export function scientificClaimsSeries(history: TurnSnapshot[], through: number): SeriesRow[] {
  return history.filter((row) => row.turn <= through).map((row) => {
    const record = observationAt(row, "scientific_claims");
    return { turn: row.turn, "Trial spending": record?.trial_spent ?? null,
      "Adoption effort spending": record?.effort_spent ?? null, "Evidence receipts": record?.evidence_receipts ?? null };
  });
}
