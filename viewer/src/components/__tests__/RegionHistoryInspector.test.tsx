import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import fixture from "../../__fixtures__/region_inspection_bundle.json";
import flowRecords from "../../__fixtures__/watershed_flow_records.json";
import type { Bundle } from "../../types";
import { RegionHistoryInspector } from "../RegionHistoryInspector";

const bundle = fixture as unknown as Bundle;
afterEach(cleanup);

describe("RegionHistoryInspector", () => {
  it("filters regions, metric and time, exposes provenance and seeks exact turns", () => {
    const onSeek = vi.fn();
    render(<RegionHistoryInspector bundle={bundle} currentTurn={1} onSeek={onSeek}
      artifactIdentity={{ name: "fixture.json", byteLength: 123, sha256: "raw-hash" }} />);
    expect(screen.getByText("SHA-256: raw-hash")).toBeInTheDocument();
    expect(screen.getByText(/Raw artifact: fixture.json/)).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Region observation coverage" })).toHaveTextContent("2 recorded values · 1 missing values · 2 turns without observations");
    fireEvent.change(screen.getByLabelText("From turn"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Through turn"), { target: { value: "3" } });
    expect(screen.getByRole("status", { name: "Region observation coverage" })).toHaveTextContent("1 recorded values · 0 missing values");
    fireEvent.click(screen.getByRole("button", { name: "Inspect turn 3" }));
    expect(onSeek).toHaveBeenCalledWith(3);
    fireEvent.change(screen.getByLabelText("Metric"), { target: { value: "ecology:water" } });
    expect(screen.getByText("Metric not recorded")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Region"), { target: { value: "Upland" } });
    expect(screen.getByText(/Upland trade:/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Event type"), { target: { value: "drought" } });
    expect(screen.getByText("No events in this window.")).toBeInTheDocument();
  });

  it("labels final-only goods, unrecorded event scope, unavailable identity and invalid ranges", () => {
    render(<RegionHistoryInspector bundle={bundle} currentTurn={5} onSeek={() => {}} />);
    expect(screen.getByText(/Raw artifact identity unavailable/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Metric"), { target: { value: "stockpile:salt" } });
    expect(screen.getByRole("status", { name: "Region observation coverage" })).toHaveTextContent("1 recorded values · 3 missing values");
    expect(screen.getByText(/Salt remains a separate good/)).toBeInTheDocument();
    expect(screen.getAllByText("Historical stockpile not exported")).toHaveLength(3);
    fireEvent.click(screen.getByLabelText("Include controller event context"));
    expect(screen.getAllByText("Controller context; region unrecorded")).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("From turn"), { target: { value: "6" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Choose whole turns from 1 through 5");
    expect(screen.queryByRole("table", { name: "Region metric observations" })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Changes between recorded turns" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("From turn"), { target: { value: "" } });
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("bounds table rendering and resets pagination when filters change", () => {
    const many = structuredClone(bundle);
    many.history = Array.from({ length: 120 }, (_, index) => ({ ...bundle.history[0], turn: index + 1 }));
    many.world_state.turn = 120;
    many.metadata.total_turns = 120;
    render(<RegionHistoryInspector bundle={many} currentTurn={1} onSeek={() => {}} />);
    expect(within(screen.getByRole("table", { name: "Region metric observations" })).getAllByRole("row")).toHaveLength(51);
    fireEvent.click(screen.getByRole("button", { name: "Next observations" }));
    expect(screen.getByText("51–100 of 120 observations")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Through turn"), { target: { value: "3" } });
    expect(screen.getByText("1–3 of 3 observations")).toBeInTheDocument();
  });

  it("explains the watershed history by the run's mode: in flow the derived index is the index used", () => {
    const flow = structuredClone(bundle);
    flow.history = flowRecords.snapshots.map((s) => ({ ...structuredClone(bundle.history[0]), ...structuredClone(s),
      region_control: {} })) as unknown as Bundle["history"];
    flow.world_state.regions = flowRecords.regions.map((name) => ({ ...bundle.world_state.regions[0], name }));
    flow.world_state.turn = 200;
    flow.metadata.total_turns = 200;
    render(<RegionHistoryInspector bundle={flow} currentTurn={1} onSeek={() => {}} />);
    fireEvent.change(screen.getByLabelText("Metric"), { target: { value: "watershed:index_derived" } });
    expect(screen.getByRole("option", { name: "Water index the watershed account derived (flow: the index used)" })).toBeInTheDocument();
    expect(screen.getByText(/Watershed account \(flow\): the derived index is the water index the simulation used/)).toBeInTheDocument();
    expect(screen.queryByText(/calibration observation/)).not.toBeInTheDocument();
  });
});
