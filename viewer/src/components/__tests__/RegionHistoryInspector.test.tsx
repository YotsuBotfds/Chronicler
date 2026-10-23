import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import fixture from "../../__fixtures__/region_inspection_bundle.json";
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
    expect(screen.getByRole("status")).toHaveTextContent("2 recorded values · 1 missing values · 2 turns without observations");
    fireEvent.change(screen.getByLabelText("From turn"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Through turn"), { target: { value: "3" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 recorded values · 0 missing values");
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
    expect(screen.getByRole("status")).toHaveTextContent("1 recorded values · 3 missing values");
    expect(screen.getByText(/Salt remains a separate good/)).toBeInTheDocument();
    expect(screen.getAllByText("Historical stockpile not exported")).toHaveLength(3);
    fireEvent.click(screen.getByLabelText("Include controller event context"));
    expect(screen.getAllByText("Controller context; region unrecorded")).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("From turn"), { target: { value: "6" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Choose whole turns from 1 through 5");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
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
});
