import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { BatchAnalytics } from "../BatchAnalytics";
import type { BatchReport } from "../../types";

const MOCK_REPORT: BatchReport = {
  metadata: {
    runs: 10,
    turns_per_run: 100,
    seed_range: [1, 10],
    checkpoints: [25, 50, 100],
    timestamp: "2026-03-14T12:00:00",
    version: "post-M18",
    report_schema_version: 1,
    tuning_file: null,
  },
  stability: {
    percentiles_by_turn: {
      "25": { min: 10, p10: 20, p25: 35, median: 50, p75: 65, p90: 80, max: 90 },
      "50": { min: 5, p10: 15, p25: 30, median: 45, p75: 60, p90: 75, max: 85 },
      "100": { min: 0, p10: 10, p25: 25, median: 40, p75: 55, p90: 70, max: 80 },
    },
    zero_rate_by_turn: { "25": 0.0, "50": 0.05, "100": 0.15 },
  },
  resources: { famine_turn_distribution: { median: 30 } },
  politics: { war_rate: 0.8, secession_rate: 0.3 },
  climate: { disaster_frequency_by_type: { drought: 0.6, plague: 0.4 } },
  memetic: { paradigm_shift_rate: 0.2 },
  great_persons: { great_person_born_rate: 0.5 },
  emergence: { regression_rate: 0.1 },
  general: { median_era_at_final: "medieval" },
  event_firing_rates: {
    war: 0.8,
    famine: 0.95,
    drought: 0.6,
    rebellion: 0.0,
    great_person_born: 0.5,
  },
  anomalies: [
    { name: "never_fire", severity: "WARNING", detail: "rebellion fired in 0% of runs" },
    { name: "stability_collapse", severity: "CRITICAL", detail: "45% of civs at stability 0 at turn 100" },
  ],
};

describe("BatchAnalytics", () => {
  it("renders summary header with metadata", () => {
    render(<BatchAnalytics report={MOCK_REPORT} />);
    expect(screen.getByText("Batch Report")).toBeTruthy();
    expect(screen.getByText("Runs: 10")).toBeTruthy();
    expect(screen.getByText("Seeds: 1-10")).toBeTruthy();
    expect(screen.getByText("Turns/run: 100")).toBeTruthy();
  });

  it("renders stability chart section", () => {
    render(<BatchAnalytics report={MOCK_REPORT} />);
    expect(screen.getByText("Stability")).toBeTruthy();
  });

  it("renders firing rate table with all events", () => {
    render(<BatchAnalytics report={MOCK_REPORT} />);
    expect(screen.getByText("Event Firing Rates")).toBeTruthy();
    expect(screen.getByText("war")).toBeTruthy();
    expect(screen.getByText("famine")).toBeTruthy();
    expect(screen.getByText("rebellion")).toBeTruthy();
    expect(screen.getByText("80%")).toBeTruthy();
  });

  it("renders anomaly cards with severity", () => {
    render(<BatchAnalytics report={MOCK_REPORT} />);
    expect(screen.getByText("Anomalies")).toBeTruthy();
    expect(screen.getByText("CRITICAL")).toBeTruthy();
    expect(screen.getByText("WARNING")).toBeTruthy();
    expect(screen.getByText(/rebellion fired in 0%/)).toBeTruthy();
    expect(screen.getByText(/45% of civs at stability 0/)).toBeTruthy();
  });

  it("shows green banner when no anomalies", () => {
    const cleanReport = { ...MOCK_REPORT, anomalies: [] };
    render(<BatchAnalytics report={cleanReport} />);
    expect(screen.getByText("No degenerate patterns detected")).toBeTruthy();
  });

  it("renders collapsible system cards", () => {
    render(<BatchAnalytics report={MOCK_REPORT} />);
    expect(screen.getByText("System Details")).toBeTruthy();

    // Click the "emergence" system card (unique, CSS capitalize makes it display as "Emergence")
    const emergenceButton = screen.getByText("emergence");
    fireEvent.click(emergenceButton);
    // Should show raw JSON data
    expect(screen.getByText(/regression_rate/)).toBeTruthy();
  });

  it("sorts firing rate table by column", () => {
    render(<BatchAnalytics report={MOCK_REPORT} />);

    // Click event type header — first click sets descending by event name
    fireEvent.click(screen.getByText(/^Event Type/));
    // Click again for ascending
    fireEvent.click(screen.getByText(/^Event Type/));

    const rows = screen.getAllByRole("row");
    // First data row (after header) should be alphabetically first
    const firstDataRow = rows[1];
    expect(firstDataRow.textContent).toContain("drought");
  });
});
