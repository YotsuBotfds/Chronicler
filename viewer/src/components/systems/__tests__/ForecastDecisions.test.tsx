import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, Event } from "../../../types";
import type { HarvestEstimatorMetadata, HarvestProcurementDecisions } from "../../../expansionTypes";
import { expansionSnapshot, report } from "../../../__fixtures__/expansionHistory";
import { forecastDecisionsAt, estimatorMetadataAt } from "../../../lib/forecastDecision";
import { HarvestForecasts } from "../HarvestForecasts";
afterEach(cleanup);
/** Constructed receipt; not a generated simulation or actor inference. */
function decision(): HarvestProcurementDecisions {
  return { schema_version: 1, source_turn: 6, available_turn: 7, mode: "hybrid", goods_units: "model_food_goods", currency_units: "model_treasury_coins",
    rows: [{ turn: 6, decision: { region: 0, owner: 0, controller: 1, target_before: 4, requested_target: 10,
      feasible_target: 8, granary_stock: 2, food_demand: 3, pending_inbound: null, opening_budget: 9,
      reports: [{ id: "r0", source_region: 1, recipient_region: 0, issued_turn: 3, planned_delivery_turn: 5,
        delivered_turn: 6, expires_turn: 11, target_start: 9, target_end: 11, probability: .7, confidence: .5,
        predicted_ratio: .6, issued_event_id: "issue", delivered_event_id: "delivery" }] },
      purchased_grain: 4, committed_grain: 2, paid: 6, attempted: null }] };
}
function metadata(): HarvestEstimatorMetadata { return { schema_version: 1, issued_turn: 5, reported_issuer_region: 1,
  estimate_origin_region: 2, policy: "shuffle", preparation_policy: "fixed", base_delivery_lag: 2, extra_delivery_delay: 0,
  observations: [[2, .4], [3, .5], [4, .6]], observation_window: 6, season_multiplier: .8, shortfall_ratio: .6,
  noise_draw: -.01, claimed_probability: .7, claimed_confidence: .5, claimed_predicted_ratio: .6 }; }
function props() {
  const snapshot = expansionSnapshot(7); snapshot.harvest_forecasts!.procurement_decisions = decision();
  const ev = { event_id: "delivery", turn: 6, event_type: "harvest_forecast_delivered", actors: [], description: "Delivered", consequences: [], importance: 3 } as Event;
  const bundle = { world_state: { regions: [{ name: "Valley" }, { name: "Hill" }, { name: "Other source" }],
    civilizations: [{ name: "Keeper" }, { name: "Controller" }] }, history: [snapshot], events_timeline: [ev] } as unknown as Bundle;
  return { bundle, snapshot, currentTurn: 7, onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectRegion: vi.fn(), onSelectCivilization: vi.fn() };
}
it("shows actor-known dates, real targets, budgets and separate purchased and committed amounts", () => {
  const p = props(); render(<HarvestForecasts {...p} />); const s = within(screen.getByRole("region", { name: "Forecast procurement decisions" }));
  expect(s.getByText(/Target before: 4 · Requested target: 10 · Feasible target: 8/)).toBeInTheDocument();
  expect(s.getByText(/Granary stock: 2 · Food demand: 3 · Pending inbound: Not observed · Opening budget: 9/)).toBeInTheDocument();
  expect(s.getByText(/New purchase received: 4 · New paid cargo committed: 2 · Treasury paid: 6/)).toBeInTheDocument();
  expect(s.getByText(/issued turn 3, planned delivery 5, received 6, expires 11/)).toBeInTheDocument();
  expect(s.getByText(/Original shortfall risk 70% · confidence 50%/)).toBeInTheDocument();
  fireEvent.click(s.getByRole("button", { name: "Valley" })); expect(p.onSelectRegion).toHaveBeenCalledWith("Valley");
  fireEvent.click(s.getByRole("button", { name: "Keeper" })); expect(p.onSelectCivilization).toHaveBeenCalledWith("Keeper");
  fireEvent.click(s.getByRole("button", { name: "Inspect delivery event" })); expect(p.onSelectEvent).toHaveBeenCalledWith(p.bundle.events_timeline[0]);
});
it("keeps old missing and stale child data unknown without hiding the parent", () => {
  const p = props(); delete p.snapshot.harvest_forecasts!.procurement_decisions;
  const view = render(<HarvestForecasts {...p} />);
  expect(screen.getByText(/Decision-boundary evidence is not observed/)).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Harvest reports at snapshot 7" })).toBeInTheDocument();
  p.snapshot.harvest_forecasts!.procurement_decisions = { ...decision(), source_turn: 5 };
  view.rerender(<HarvestForecasts {...p} />);
  expect(screen.getByText(/Decision-boundary evidence is not observed/)).toBeInTheDocument();
  p.snapshot.harvest_forecasts!.procurement_decisions = decision();
  view.rerender(<HarvestForecasts {...p} currentTurn={8} />);
  expect(screen.getByText(/Decision-boundary evidence is not observed/)).toBeInTheDocument();
});
it("rejects future, malformed and contradictory decision evidence independently", () => {
  const p = props(), f = decision();
  const bad = [ { ...f, schema_version: 2 }, { ...f, available_turn: 8 },
    { ...f, rows: [f.rows[0], f.rows[0]] }, { ...f, rows: [{ ...f.rows[0], attempted: true }] },
    { ...f, rows: [{ ...f.rows[0], decision: { ...f.rows[0].decision, owner: 8 } }] },
    { ...f, rows: [{ ...f.rows[0], decision: { ...f.rows[0].decision, reports: [{ ...f.rows[0].decision.reports[0], delivered_turn: 7 }] } }] },
    { ...f, rows: [{ ...f.rows[0], paid: NaN }] } ];
  for (const child of bad) { Object.assign(p.snapshot.harvest_forecasts!, { procurement_decisions: child }); expect(forecastDecisionsAt(p.snapshot, 3, 2)).toBeNull(); }
});
it("keeps pending public report construction distinct from the actor-known decision", () => {
  const p = props(), pending = report({ estimator_metadata: metadata() }); p.snapshot.harvest_forecasts!.reports = [pending];
  p.snapshot.harvest_forecasts!.procurement_decisions!.rows[0].decision.reports = [];
  render(<HarvestForecasts {...p} />);
  const decider = within(screen.getByRole("region", { name: "Forecast procurement decisions" }));
  expect(decider.getByText(/No eligible warning report was recorded/)).toBeInTheDocument();
  expect(decider.queryByText(/Other source/)).not.toBeInTheDocument();
  const reportScroller = screen.getByRole("region", { name: "Scroll harvest reports" });
  expect(reportScroller).toHaveAttribute("tabindex", "0"); reportScroller.focus(); expect(reportScroller).toHaveFocus();
  fireEvent.keyDown(reportScroller, { key: "ArrowRight" });
  fireEvent.click(screen.getByText("Underlying estimator construction (not recipient-known)"));
  expect(screen.getByText(/reported issuer Hill; estimate origin Other source; policy shuffle/)).toBeVisible();
  expect(screen.getByText(/T2: 0.4, T3: 0.5, T4: 0.6/)).toBeVisible();
  const future = { ...metadata(), observations: [[2, .4], [3, .5], [6, .6]] } as HarvestEstimatorMetadata;
  expect(estimatorMetadataAt({ ...pending, estimator_metadata: future }, 6, 3)).toBeNull();
});
it("shows observed zero receipts and unknown targets without inventing failed attempts", () => {
  const p = props(), row = p.snapshot.harvest_forecasts!.procurement_decisions!.rows[0];
  Object.assign(row, { purchased_grain: 0, committed_grain: 0, paid: 0 });
  Object.assign(row.decision, { target_before: null, pending_inbound: null, food_demand: null, reports: [] });
  render(<HarvestForecasts {...p} />);
  const s = within(screen.getByRole("region", { name: "Forecast procurement decisions" }));
  expect(s.getByText(/Target before: Not observed/)).toBeInTheDocument();
  expect(s.getByText(/New purchase received: 0 · New paid cargo committed: 0 · Treasury paid: 0/)).toBeInTheDocument();
  expect(s.getByText(/Unsuccessful attempts are not observed/)).toBeInTheDocument();
});
it("bounds region cards, supports keyboard-focusable controls, and resets paging on scrub", () => {
  const p = props(), f = p.snapshot.harvest_forecasts!.procurement_decisions!;
  p.bundle.world_state.regions = Array.from({ length: 10 }, (_, i) => ({ name: `Region ${i}` })) as Bundle["world_state"]["regions"];
  f.rows = Array.from({ length: 10 }, (_, i) => ({ ...decision().rows[0], decision: { ...decision().rows[0].decision, region: i, reports: [] } }));
  const view = render(<HarvestForecasts {...p} />); const show = screen.getByRole("button", { name: "Show more granary decisions (2 remaining)" });
  show.focus(); expect(show).toHaveFocus(); fireEvent.click(show);
  expect(screen.getByText("Showing 10 of 10 recorded granary decisions.")).toBeInTheDocument();
  view.rerender(<HarvestForecasts {...p} snapshot={expansionSnapshot(6)} currentTurn={6} />);
  view.rerender(<HarvestForecasts {...p} />);
  expect(screen.getByText("Showing 8 of 10 recorded granary decisions.")).toBeInTheDocument();
});

it("rejects impossible estimator lags and nonchronological observation evidence", () => {
  const base = report({ estimator_metadata: metadata() });
  expect(estimatorMetadataAt(base, 6, 3)).not.toBeNull();
  for (const broken of [
    { ...metadata(), base_delivery_lag: 0 }, { ...metadata(), base_delivery_lag: 3 },
    { ...metadata(), extra_delivery_delay: 13 }, { ...metadata(), extra_delivery_delay: 1 },
    { ...metadata(), observations: [[2, .4], [2, .5], [4, .6]] },
    { ...metadata(), observations: [[3, .4], [2, .5], [4, .6]] },
  ]) {
    expect(estimatorMetadataAt({ ...base, estimator_metadata: broken as HarvestEstimatorMetadata }, 6, 3)).toBeNull();
  }
});

it("labels severe classification and shows only validated recorded thresholds on resolved rows", () => {
  const p = props();
  const resolved = report({ status: "resolved", resolved_turn: 6, observed_ratio: .627537, outcome_shortfall: false,
    brier: .49, estimator_metadata: metadata() });
  p.snapshot.harvest_forecasts!.outcomes = [resolved];
  const view = render(<HarvestForecasts {...p} />);
  expect(screen.getByText(/risk of winter production ÷ demand falling below the severe-shortfall threshold/)).toBeVisible();
  const table = screen.getByRole("table", { name: "Harvest outcomes at snapshot 7" });
  expect(within(table).getByRole("columnheader", { name: "Severe shortfall" })).toBeVisible();
  expect(within(within(table).getAllByRole("row")[1]).getAllByRole("cell").slice(5, 8).map((cell) => cell.textContent)).toEqual(["0.63", "0.6", "No"]);
  expect(screen.getByText(/a ratio above it may still be below full demand/)).toBeVisible();
  p.snapshot.harvest_forecasts!.outcomes = [{ ...resolved, estimator_metadata: undefined }];
  view.rerender(<HarvestForecasts {...p} />);
  expect(within(within(table).getAllByRole("row")[1]).getAllByRole("cell").slice(5, 8).map((cell) => cell.textContent)).toEqual(["0.63", "Not recorded", "No"]);
  p.snapshot.harvest_forecasts!.outcomes = [{ ...resolved, resolved_turn: 7 }];
  view.rerender(<HarvestForecasts {...p} />);
  expect(screen.queryByRole("table", { name: "Harvest outcomes at snapshot 7" })).toBeNull();
});
