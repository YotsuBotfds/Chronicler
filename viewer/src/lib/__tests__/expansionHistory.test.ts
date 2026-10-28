import { describe, expect, it } from "vitest";
import { expansionSnapshot, forecastObservation, gatheringObservation, healthObservation, report } from "../../__fixtures__/expansionHistory";
import { harvestForecastSeries, forecastTotals } from "../harvestForecasts";
import { healthCareSeries } from "../healthCare";
import { observationAt } from "../observedSystems";
import { gatheringHistory, gatheringRows } from "../ritualGatherings";
import { presentSystems } from "../systems";
import { bundleFromInitMessage, snapshotFromMessage } from "../transport";
import actualForecasts from "../../__fixtures__/harvest_forecast_observations.json";
import type { HarvestForecastSnapshot, TurnSnapshot } from "../../types";

describe("observed expansion history", () => {
  it("rejects stale and future source stamps rather than presenting them as this turn", () => {
    const row = expansionSnapshot(7);
    expect(observationAt(row, "health_care")?.source_turn).toBe(6);
    row.health_care = healthObservation(7);
    row.harvest_forecasts = forecastObservation(5);
    row.ritual_gatherings = gatheringObservation(10);
    expect(observationAt(row, "health_care")).toBeNull();
    expect(observationAt(row, "harvest_forecasts")).toBeNull();
    expect(observationAt(row, "ritual_gatherings")).toBeNull();
  });

  it("keeps unknown past observations as gaps and excludes future health from charts", () => {
    const history = [expansionSnapshot(3, false), expansionSnapshot(7), expansionSnapshot(10)];
    history[2].health_care!.episodes = 99;
    expect(healthCareSeries(history, 7)).toEqual([
      { turn: 3, "Active injuries": null, "New injuries": null, Recoveries: null,
        "Farmer work lost": null, "Household care work": null, "Care recipients": null },
      { turn: 7, "Active injuries": 2, "New injuries": 1, Recoveries: 0,
        "Farmer work lost": 0.75, "Household care work": 0.25, "Care recipients": 1 },
    ]);
  });

  it("separates pending information, factual preparedness purchases and scores", () => {
    const record = forecastObservation();
    record.reports.push(report({ id: "other", status: "withheld" }));
    record.preparedness = [{ region: 0, region_name: "Valley", owner: 0, owner_name: "Old realm",
      forecast_id: "r0", base_target: 10, extra_target: 5, bought_during_warning: 2.5, paid_during_warning: 7 }];
    expect(forecastTotals(record)).toMatchObject({ pending: 1, delivered: 0, withheld: 1,
      extra: 5, bought: 2.5, paid: 7, brier: null });
    record.counters = { resolved: 2, brier_sum: 0.5 };
    expect(forecastTotals(record).brier).toBe(0.25);
    const early = expansionSnapshot(3, false), known = expansionSnapshot(7);
    known.harvest_forecasts = record;
    const series = harvestForecastSeries([early, known, expansionSnapshot(10)], 7);
    expect(series).toHaveLength(2);
    expect(series[0].Pending).toBeNull();
    expect(series[1]["Paid while warned"]).toBe(7);
  });

  it("does not replay an old gathering receipt or invent occurrences in missing history", () => {
    const earlier = expansionSnapshot(7), stale = expansionSnapshot(8), later = expansionSnapshot(10);
    stale.ritual_gatherings!.outcomes = earlier.ritual_gatherings!.outcomes;
    const history = [expansionSnapshot(3, false), earlier, stale, later];
    const occurrences = gatheringHistory(history, 8);
    expect(occurrences).toHaveLength(1);
    expect(occurrences[0]).toMatchObject({ turn: 6, snapshot_turn: 7, host_name: "Old realm", faith_name: "The Old Faith" });
    expect(gatheringRows(history, 8)[0].segments).toMatchObject([{ start: 7, end: 8, text: "held" }]);
  });

  it("makes only the relevant tabs available for actual recorded fields", () => {
    const row = expansionSnapshot(7);
    expect(presentSystems([row])).toEqual(["epidemics", "food", "faiths"]);
    expect(presentSystems([expansionSnapshot(7, false)])).toEqual([]);
  });

  it("preserves the recorded summaries through streaming and reconnect transport", () => {
    const row = expansionSnapshot(7);
    expect(snapshotFromMessage({ ...row, type: "turn" })).toEqual(row);
    expect(bundleFromInitMessage({ history: [row], world_state: {}, metadata: {} }).history[0]).toEqual(row);
  });

  it("reads the complete issued/delivered/resolved cycle from actual native observations", () => {
    const rows = actualForecasts.history as unknown as Array<Pick<TurnSnapshot, "turn" | "harvest_forecasts">>;
    const at = (turn: number) => rows.find((row) => row.turn === turn)!.harvest_forecasts as HarvestForecastSnapshot;
    expect(actualForecasts.source.seed).toBe(42);
    expect(at(5).reports).toHaveLength(0);
    expect(forecastTotals(at(6))).toMatchObject({ pending: 6, delivered: 0, brier: null });
    expect(forecastTotals(at(7))).toMatchObject({ pending: 2, delivered: 4, bought: 0, paid: 0 });
    expect(forecastTotals(at(8))).toMatchObject({ pending: 0, delivered: 6 });
    expect(at(13).outcomes).toHaveLength(6);
    expect(at(13).outcomes.every((row) => row.resolved_turn === 12)).toBe(true);
    expect(forecastTotals(at(13)).brier).not.toBeNull();
    expect(at(13).calibration.reduce((n, [count]) => n + count, 0)).toBe(6);
  });
});
