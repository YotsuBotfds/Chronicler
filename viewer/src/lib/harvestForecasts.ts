import type { HarvestForecastSnapshot, TurnSnapshot } from "../types";
import { observationAt } from "./observedSystems";
import type { SeriesRow } from "./systems";

export function forecastTotals(record: HarvestForecastSnapshot) {
  return {
    pending: record.reports.filter((row) => row.status === "pending").length,
    delivered: record.reports.filter((row) => row.status === "delivered").length,
    withheld: record.reports.filter((row) => row.status === "withheld").length,
    extra: record.preparedness.reduce((n, row) => n + row.extra_target, 0),
    bought: record.preparedness.reduce((n, row) => n + row.bought_during_warning, 0),
    paid: record.preparedness.reduce((n, row) => n + row.paid_during_warning, 0),
    brier: (record.counters.resolved ?? 0) > 0 ? record.counters.brier_sum / record.counters.resolved : null,
  };
}

/** Factual observations through the selected snapshot; missing records stay null. */
export function harvestForecastSeries(history: TurnSnapshot[], through: number): SeriesRow[] {
  return history.filter((snapshot) => snapshot.turn <= through).map((snapshot) => {
    const record = observationAt(snapshot, "harvest_forecasts");
    const totals = record ? forecastTotals(record) : null;
    return { turn: snapshot.turn, Pending: totals?.pending ?? null, Delivered: totals?.delivered ?? null,
      Withheld: totals?.withheld ?? null, "Extra stock target": totals?.extra ?? null,
      "Bought while warned": totals?.bought ?? null, "Paid while warned": totals?.paid ?? null };
  });
}
