import type { ScientificContext, ScientificTrial, TurnSnapshot } from "../types";
import { observationAt } from "./observedSystems";
import type { SeriesRow } from "./systems";

export function scientificContext(context?: ScientificContext): string {
  return context ? `${context.crop}; soil band ${context.soil_band}, water band ${context.water_band}; season ${context.season}; ${context.climate_phase}; crew ${context.crew}; ${context.protocol}` : "Context not recorded";
}

/** Publication eligibility and current-context belief applicability are separate. */
export function scientificPublication(rule: unknown): { label: string; detail: string } {
  if (rule === undefined || rule === "current-context-v1") return {
    label: "Current-context publication",
    detail: "A paid trial may be cancelled if its academy or registered context is unavailable when the result is due.",
  };
  if (rule === "funded-context-v2") return {
    label: "Publish results for the funding context",
    detail: "Published results refer to the setting recorded at funding, which may differ from conditions when the trial completes. The academy and a valid trial record are still required. Current-context policy confidence can still use no applicable evidence and retain the prior score.",
  };
  return {
    label: `Publication rule unrecognized (${typeof rule === "string" ? rule : "invalid value"})`,
    detail: "Recorded trials and costs remain visible. Publication eligibility is unknown for this rule; neither known policy is assumed.",
  };
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
