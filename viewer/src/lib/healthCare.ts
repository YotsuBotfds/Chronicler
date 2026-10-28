import type { TurnSnapshot } from "../types";
import type { SeriesRow } from "./systems";
import { observationAt } from "./observedSystems";

/** Observations only: never extrapolate future health or use final-world state. */
export function healthCareSeries(history: TurnSnapshot[], through: number): SeriesRow[] {
  return history.filter((snapshot) => snapshot.turn <= through).map((snapshot) => {
    const record = observationAt(snapshot, "health_care");
    return { turn: snapshot.turn, "Active injuries": record?.episodes ?? null,
      "New injuries": record?.new_injuries ?? null, Recoveries: record?.recoveries ?? null,
      "Farmer work lost": record?.impaired_work ?? null, "Household care work": record?.care_work ?? null,
      "Care recipients": record?.care_recipients ?? null };
  });
}
