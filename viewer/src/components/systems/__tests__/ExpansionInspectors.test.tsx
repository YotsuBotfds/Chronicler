import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle } from "../../../types";
import { expansionSnapshot, report } from "../../../__fixtures__/expansionHistory";
import { HarvestForecasts } from "../HarvestForecasts";
import { HealthCare } from "../HealthCare";
import { RitualGatherings } from "../RitualGatherings";
import { RegionSystemsDetail } from "../RegionSystemsDetail";
import { FoodPanel } from "../FoodPanel";
import { EpidemicsPanel } from "../EpidemicsPanel";

afterEach(cleanup);
function props(turn = 7) {
  const history = [expansionSnapshot(3, false), expansionSnapshot(7), expansionSnapshot(10)];
  history[2].health_care!.episodes = 99;
  history[2].health_care!.regions[0].civ_name = "Future ruler";
  history[2].ritual_gatherings!.outcomes[0].host_name = "Future ruler";
  return { bundle: { world_state: { health_care: { episodes: 999 }, harvest_forecasts: { reports: ["future"] },
    ritual_gatherings: { counters: { held: 999 } } }, history } as unknown as Bundle,
  snapshot: history.find((row) => row.turn === turn) ?? null, currentTurn: turn,
  onSeek: vi.fn(), onSelectRegion: vi.fn(), onSelectCivilization: vi.fn(), onSelectEvent: vi.fn() };
}

describe("recorded expansion inspectors", () => {
  it("renders actual injury work and historical controller, with navigation", () => {
    const p = props();
    render(<HealthCare {...p} />);
    const table = screen.getByRole("table", { name: "Injury and care at snapshot 7" });
    expect(within(table).getByText("0.75")).toBeInTheDocument();
    expect(within(table).queryByText("Future ruler")).not.toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "Old realm" }));
    expect(p.onSelectCivilization).toHaveBeenCalledWith("Old realm");
    expect(screen.getByText(/Recorded after simulation turn 6/)).toBeInTheDocument();
    expect(screen.queryByText("999")).not.toBeInTheDocument();
  });

  it("distinguishes planned delivery from actual delivery and grain from treasury", () => {
    const p = props();
    const forecast = p.snapshot!.harvest_forecasts!;
    forecast.reports.push(report({ id: "harvest:withheld", status: "withheld" }));
    forecast.preparedness = [{ region: 0, region_name: "Valley", owner: 0, owner_name: "Old realm", forecast_id: "r0",
      base_target: 10, extra_target: 5, bought_during_warning: 2.5, paid_during_warning: 7 }];
    render(<HarvestForecasts {...p} />);
    const reports = screen.getByRole("table", { name: "Harvest reports at snapshot 7" });
    expect(within(reports).getAllByText("7 / Not delivered")).toHaveLength(2);
    expect(within(reports).getByText("pending")).toBeInTheDocument();
    expect(within(reports).getByText("withheld")).toBeInTheDocument();
    const purchases = screen.getByRole("table", { name: "Harvest preparedness at snapshot 7" });
    expect(within(purchases).getByText("2.5")).toBeInTheDocument();
    expect(within(purchases).getByText("7")).toBeInTheDocument();
    expect(screen.getByText(/not estimated extra purchases or losses avoided/)).toBeInTheDocument();
  });

  it.each(["issued_turn", "delivered_turn", "resolved_turn"] as const)("withholds future %s evidence and aggregate scores", (field) => {
    const p = props();
    p.snapshot!.harvest_forecasts!.reports[0][field] = 12;
    p.snapshot!.harvest_forecasts!.counters = { resolved: 99, brier_sum: 80 };
    render(<HarvestForecasts {...p} />);
    expect(screen.getByText(/No usable harvest-forecast observation/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("Mean Brier score")).not.toBeInTheDocument();
  });

  it("makes an actual paid-preparedness receipt visible in the Food event history", () => {
    const p = props();
    p.bundle.world_state.regions = [{ name: "Valley" }, { name: "Hill" }] as Bundle["world_state"]["regions"];
    const event = { turn: 6, event_type: "harvest_preparedness", actors: ["Old realm"], importance: 3,
      description: "The realm pays 7 treasury for actual granary purchases while warned.", consequences: [] };
    p.bundle.events_timeline = [event];
    render(<FoodPanel {...p} />);
    fireEvent.click(within(screen.getByRole("list", { name: "Food events" })).getByText(event.description));
    expect(p.onSelectEvent).toHaveBeenCalledWith(event);
  });

  it.each([
    [FoodPanel, "Food events", "harvest_preparedness", "famine"],
    [EpidemicsPanel, "Epidemic events", "occupational_injury", "epidemic"],
  ] as const)("cuts new receipt events off at the observed source in %s", (Panel, label, kind, legacyKind) => {
    const p = props();
    p.currentTurn = 9; // The selected snapshot is still 7, whose completed tick is 6.
    p.bundle.world_state.regions = [{ name: "Valley" }, { name: "Hill" }] as Bundle["world_state"]["regions"];
    const receipt = { turn: 7, event_type: kind, actors: [], importance: 3, description: "Future receipt", consequences: [] };
    const legacy = { ...receipt, event_type: legacyKind, description: "Legacy event" };
    p.bundle.events_timeline = [receipt, legacy];
    render(<Panel {...p} />);
    const list = screen.getByRole("list", { name: label });
    expect(within(list).queryByText(receipt.description)).not.toBeInTheDocument();
    expect(within(list).getByText(legacy.description)).toBeInTheDocument();
  });

  it("shows actual gathering receipts and seeks the containing snapshot", () => {
    const p = props();
    render(<RitualGatherings {...p} />);
    const table = screen.getByRole("table", { name: "Gathering history through snapshot 7" });
    expect(within(table).getByText("The Old Faith")).toBeInTheDocument();
    expect(within(table).getByText("1.5")).toBeInTheDocument();
    expect(within(table).queryByText("Future ruler")).not.toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "6 / 7" }));
    expect(p.onSeek).toHaveBeenCalledWith(7);
    expect(within(screen.getByRole("table", { name: "Gathering schedules at snapshot 7" })).getByText("20")).toBeInTheDocument();
    expect(screen.getByText(/A scheduled turn is a plan/)).toBeInTheDocument();
  });

  it("connects the same dated observations to the region inspector", () => {
    const p = props();
    render(<RegionSystemsDetail snapshot={p.snapshot} region="Valley" />);
    expect(within(screen.getByLabelText("Injury and care in Valley")).getByText("0.75 worker-turns")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Harvest forecasts in Valley")).getByText(/pending · 70%/)).toBeInTheDocument();
    expect(within(screen.getByLabelText("Harvest gatherings in Valley")).getByText("20 (a plan)")).toBeInTheDocument();
  });

  it("omits unrecorded expansion data from the region inspector", () => {
    const { container } = render(<RegionSystemsDetail snapshot={expansionSnapshot(3, false)} region="Valley" />);
    expect(container).toBeEmptyDOMElement();
  });

  it.each([HealthCare, HarvestForecasts, RitualGatherings])("treats a missing earlier observation as unknown", (Panel) => {
    render(<Panel {...props(3)} />);
    expect(screen.getByText(/unknown/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it.each([HealthCare, HarvestForecasts, RitualGatherings])("renders no invented section when the system was never recorded", (Panel) => {
    const p = props(3);
    p.bundle.history = [expansionSnapshot(3, false)];
    const { container } = render(<Panel {...p} />);
    expect(container).toBeEmptyDOMElement();
  });
});
