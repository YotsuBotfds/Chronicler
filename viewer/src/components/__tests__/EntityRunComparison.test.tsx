import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CompletedRun } from "../../lib/completedRunComparison";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import { EntityRunComparison } from "../EntityRunComparison";

afterEach(cleanup);
const run = (): CompletedRun => ({ bundle: regionalFixture(), identity: null, label: "Constructed fixture" });

describe("Per-entity comparison panel", () => {
  it("shows raw values, signed single-measure differences and identity limits", () => {
    const left = run(), right = run();
    right.bundle.history[1].civ_stats.A.population = 30;
    render(<EntityRunComparison left={left} right={right} turn={2} />);
    expect(screen.getByRole("status")).toHaveTextContent("identity unverified");
    const row = screen.getByRole("row", { name: /A Name-only;/ });
    expect(within(row).getByText("20")).toBeInTheDocument();
    expect(within(row).getByText("30")).toBeInTheDocument();
    expect(within(row).getByText("+10")).toBeInTheDocument();
    expect(within(row).getByText("+50%")).toBeInTheDocument();
    expect(screen.getByText(/not a welfare judgment/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Entity matching and measure limits"));
    expect(screen.getByText(/not an overall winner, utility score or causal conclusion/)).toBeVisible();
  });
  it("switches kind, measure and order without changing the comparison turn", () => {
    const left = run(), right = run();
    right.bundle.history[1].civ_stats.A.treasury = 3;
    right.bundle.history[1].regional_population!.counts = [150, 180];
    render(<EntityRunComparison left={left} right={right} turn={2} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Entity comparison measure" }), { target: { value: "treasury" } });
    expect(screen.getByRole("table", { name: "Entity Treasury differences" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Entity comparison order" }), { target: { value: "lower" } });
    expect(screen.getAllByRole("row")[1]).toHaveTextContent("A");
    fireEvent.change(screen.getByRole("combobox", { name: "Entity comparison kind" }), { target: { value: "region" } });
    expect(screen.getByRole("combobox", { name: "Entity comparison measure" })).toHaveValue("population");
    expect(screen.queryByRole("option", { name: "Treasury" })).not.toBeInTheDocument();
    expect(screen.getByText(/Snapshot 2: right minus left/)).toBeInTheDocument();
    expect(screen.getByText("+50")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /View turn/ })).not.toBeInTheDocument();
  });
  it("caps entities at twenty and reveals more with a standard keyboard-accessible button", () => {
    const left = run(), right = run();
    for (const input of [left, right]) {
      input.bundle = comparisonBundle();
      input.bundle.world_state.civilizations = Array.from({ length: 25 }, (_, index) => ({ ...input.bundle.world_state.civilizations[0], name: `Civ ${index}` }));
      for (const snapshot of input.bundle.history) snapshot.civ_stats = Object.fromEntries(Array.from({ length: 25 }, (_, index) => [`Civ ${index}`, { ...snapshot.civ_stats.A }]));
    }
    render(<EntityRunComparison left={left} right={right} turn={2} />);
    expect(screen.getAllByRole("row")).toHaveLength(21);
    const reveal = screen.getByRole("button", { name: "Show more entities (5 remaining)" });
    reveal.focus(); expect(reveal).toHaveFocus();
    fireEvent.click(reveal);
    expect(screen.getAllByRole("row")).toHaveLength(26);
    expect(screen.queryByRole("button", { name: /Show more entities/ })).not.toBeInTheDocument();
  });
  it("keeps missing tails and future entities unknown instead of ranking zero values", () => {
    const left = run(), right = run();
    right.bundle.history = right.bundle.history.slice(0, 1);
    right.bundle.world_state.civilizations.push({ ...right.bundle.world_state.civilizations[0], name: "Future realm" });
    render(<EntityRunComparison left={left} right={right} turn={2} />);
    expect(screen.getByRole("status")).toHaveTextContent("0/3 entities have a numeric difference");
    expect(screen.getAllByText("Exact snapshot not recorded or ambiguous")).toHaveLength(3);
    expect(screen.queryByText(/Future realm/)).not.toBeInTheDocument();
    expect(screen.queryByText("+0%")).not.toBeInTheDocument();
  });
  it("labels debt direction and landless observations without a generic benefit claim", () => {
    render(<EntityRunComparison left={run()} right={run()} turn={2} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Entity comparison measure" }), { target: { value: "debt" } });
    expect(screen.getByText(/Lower means less debt, not necessarily lower cost or a better outcome/)).toBeInTheDocument();
    expect(screen.getAllByText("Recorded landless/fallen (alive=false); permanence unknown")).toHaveLength(2);
    expect(screen.getByRole("table", { name: "Entity Outstanding debt differences" })).toBeInTheDocument();
  });
});
