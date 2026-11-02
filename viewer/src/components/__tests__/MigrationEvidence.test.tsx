import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import { MigrationEvidence } from "../MigrationEvidence";

describe("MigrationEvidence", () => {
  it("shows exact-tick native flows, source pointers and region inspection without a seek", () => {
    const bundle = regionalFixture();
    bundle.history[1].migration = [[0, 1, 3], [0, 1, 2]];
    const onInspectRegion = vi.fn();
    render(<MigrationEvidence bundle={bundle} currentTurn={2} selectedRegionIndex={0} onInspectRegion={onInspectRegion} />);
    expect(screen.getByText(/Snapshot 2 · completed tick 1 · source tick 1/)).toBeVisible();
    const flows = screen.getByRole("list", { name: "Recorded migration flows" });
    expect(within(flows).getByText("5 native agents")).toBeVisible();
    expect(within(flows).getByText(/Reason: unknown/)).toBeVisible();
    fireEvent.click(within(flows).getByRole("button", { name: "Inspect region 1: B" }));
    expect(onInspectRegion).toHaveBeenCalledExactlyOnceWith(1, "B");
    fireEvent.click(screen.getByText("Flow sources (2)"));
    expect(screen.getByText("/history/1/migration/0")).toBeVisible();
    expect(screen.getByText("/history/1/migration/1")).toBeVisible();
    expect(screen.getByText(/not net model population change/)).toBeVisible();
  });

  it("distinguishes unknown legacy movement from recorded zero moves", () => {
    const bundle = regionalFixture();
    const { rerender } = render(<MigrationEvidence bundle={bundle} currentTurn={1} />);
    expect(screen.getByRole("status")).toHaveTextContent("not recorded; movement is unknown");
    expect(screen.queryByText(/Recorded moves:/)).toBeNull();
    const recorded = structuredClone(bundle);
    recorded.history[0].migration = [];
    rerender(<MigrationEvidence bundle={recorded} currentTurn={1} />);
    expect(screen.getByRole("status")).toHaveTextContent("zero native agents moved");
    expect(screen.getByText("0 native agents")).toBeVisible();
  });

  it("shows separate recorded driver context without assigning a reason or using future reports", () => {
    const bundle = regionalFixture();
    bundle.history[1].migration = [[0, 1, 3]];
    const event = { turn: 1, region: "A", driver: "wage", event_type: "mass_migration", actors: [],
      consequences: [], importance: 5, description: "Recorded group report" };
    bundle.events_timeline = [event, { ...event, turn: 2, description: "FUTURE REPORT" }];
    render(<MigrationEvidence bundle={bundle} currentTurn={2} selectedRegionIndex={0} />);
    fireEvent.click(screen.getByText("Separate recorded event context (1)"));
    expect(screen.getByText("Recorded group report")).toBeVisible();
    expect(screen.getByText(/Recorded group driver: wage/)).toBeVisible();
    expect(screen.getByText(/not a reason assigned to each/)).toBeVisible();
    expect(screen.getByText(/Reason: unknown/)).toBeVisible();
    expect(screen.queryByText("FUTURE REPORT")).toBeNull();
    expect(screen.getByText("/events_timeline/0")).toBeVisible();
  });

  it("keeps native net and model population delta separate and reports consecutive-record gaps", () => {
    const bundle = regionalFixture();
    bundle.history[0].regional_population!.counts[0] = 100;
    bundle.history[1].regional_population!.counts[0] = 90;
    bundle.history[1].migration = [[0, 1, 2]];
    const { rerender } = render(<MigrationEvidence bundle={bundle} currentTurn={2} selectedRegionIndex={0} />);
    fireEvent.click(screen.getByText("Separate model population observation"));
    expect(screen.getByText(/model population 100 → 90; change -10/)).toBeVisible();
    expect(screen.getByText("-2")).toBeVisible();
    expect(screen.getByText(/No cause is assigned/)).toBeVisible();
    const gap = structuredClone(bundle);
    gap.history = gap.history.filter((snapshot) => snapshot.turn !== 2);
    rerender(<MigrationEvidence bundle={gap} currentTurn={3} selectedRegionIndex={0} />);
    expect(screen.getByText(/both exact consecutive regional model population observations are required/)).toBeVisible();
  });

  it("bounds flows, offers native buttons, and resets the visible scope on a new turn", () => {
    const bundle = regionalFixture();
    bundle.world_state.regions = Array.from({ length: 11 }, (_, index) => ({ ...bundle.world_state.regions[0], name: `Region ${index}` }));
    bundle.history[0].migration = Array.from({ length: 10 }, (_, index) => [0, index + 1, index + 1]);
    bundle.history[1].migration = structuredClone(bundle.history[0].migration);
    const { rerender } = render(<MigrationEvidence bundle={bundle} currentTurn={1} />);
    expect(screen.getByText("Showing 8 of 10 recorded region pairs.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Show more flows (2 remaining)" }));
    expect(screen.getByText("Showing 10 of 10 recorded region pairs.")).toBeVisible();
    rerender(<MigrationEvidence bundle={bundle} currentTurn={2} />);
    expect(screen.getByText("Showing 8 of 10 recorded region pairs.")).toBeVisible();
  });

  it("does not present partial moves from malformed data or ambiguous selected snapshots", () => {
    const bundle = regionalFixture();
    bundle.history[1].migration = [[0, 1, 3], [9, 0, 7]];
    const { rerender } = render(<MigrationEvidence bundle={bundle} currentTurn={2} />);
    expect(screen.getByRole("status")).toHaveTextContent("Malformed native migration record");
    expect(screen.queryByText(/Recorded moves:/)).toBeNull();
    const duplicate = structuredClone(bundle);
    duplicate.history.push(structuredClone(duplicate.history[1]));
    rerender(<MigrationEvidence bundle={duplicate} currentTurn={2} />);
    expect(screen.getByRole("status")).toHaveTextContent("No exact, unambiguous snapshot");
  });
});
