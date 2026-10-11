import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { SettlementInspector } from "./SettlementInspector";
import type { SettlementSnapshot } from "../../lib/settlementInspection";

afterEach(cleanup);
const quay = { settlement_id: 7, name: "River Quay", region_name: "Delta", population_estimate: 23,
  centroid_x: 1.25, centroid_y: -2.75, founding_turn: 2, status: "active" };
const ferry = { ...quay, settlement_id: 9, name: "Upper Ferry", population_estimate: 40, centroid_x: 8 };
const history: SettlementSnapshot[] = [
  { turn: 1, settlement_source_turn: 1, active_settlements: [], founded_this_turn: [], dissolved_this_turn: [] },
  { turn: 2, settlement_source_turn: 2, active_settlements: [quay, ferry], founded_this_turn: [7, 9], dissolved_this_turn: [] },
  { turn: 3, settlement_source_turn: 2, active_settlements: [{ ...quay, population_estimate: 31, centroid_x: 1.5 }, ferry], founded_this_turn: [], dissolved_this_turn: [] },
  { turn: 5, settlement_source_turn: 5, active_settlements: [ferry], founded_this_turn: [], dissolved_this_turn: [7] },
];
const population = () => screen.getByText("Population estimate", { selector: "dt" }).parentElement!;

describe("SettlementInspector", () => {
  it("scrubs forward/back through founding, stale summaries, gaps and dissolution", () => {
    const props = { history, settlementId: 7, onSelectSettlement: vi.fn() };
    const { rerender } = render(<SettlementInspector {...props} requestedTurn={1} />);
    expect(screen.getByRole("status")).toHaveTextContent("not listed in this snapshot");
    expect(screen.queryByText("River Quay")).not.toBeInTheDocument();
    rerender(<SettlementInspector {...props} requestedTurn={2} />);
    expect(within(population()).getByText("23")).toBeInTheDocument();
    expect(screen.getByText("1.25")).toBeInTheDocument();
    expect(screen.getByText("-2.75")).toBeInTheDocument();
    rerender(<SettlementInspector {...props} requestedTurn={3} />);
    expect(screen.getByRole("status")).toHaveTextContent("Stale summary · source turn 2 · observation age 1 turns");
    expect(within(population()).getByText("31")).toBeInTheDocument();
    rerender(<SettlementInspector {...props} requestedTurn={4} />);
    expect(screen.getByRole("status")).toHaveTextContent("No historical snapshot recorded");
    expect(screen.queryByText("Population estimate", { selector: "dt" })).not.toBeInTheDocument();
    rerender(<SettlementInspector {...props} requestedTurn={5} />);
    expect(screen.getByRole("status")).toHaveTextContent("Dissolution recorded");
    expect(screen.queryByText("Population estimate", { selector: "dt" })).not.toBeInTheDocument();
    rerender(<SettlementInspector {...props} requestedTurn={2} />);
    expect(within(population()).getByText("23")).toBeInTheDocument();
  });

  it("uses controlled selection, clears it, exposes pointers and responds to close/seek", () => {
    const onSelectSettlement = vi.fn(), onSeek = vi.fn(), onClose = vi.fn();
    const props = { history, requestedTurn: 2, settlementId: 7, onSelectSettlement, onSeek, onClose };
    const { rerender } = render(<SettlementInspector {...props} />);
    fireEvent.change(screen.getByLabelText("Settlement"), { target: { value: "9" } });
    expect(onSelectSettlement).toHaveBeenCalledWith(9);
    rerender(<SettlementInspector {...props} settlementId={9} />);
    expect(screen.getByRole("heading", { name: "Upper Ferry" })).toBeInTheDocument();
    expect(within(population()).getByText("40")).toBeInTheDocument();
    expect(screen.getByText("/history/1/active_settlements/1/population_estimate")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Recorded population history"));
    fireEvent.click(screen.getByRole("button", { name: "Inspect settlement at turn 1" }));
    expect(onSeek).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByRole("button", { name: "Close settlement inspector" }));
    expect(onClose).toHaveBeenCalledOnce();
    fireEvent.change(screen.getByLabelText("Settlement"), { target: { value: "" } });
    expect(onSelectSettlement).toHaveBeenLastCalledWith(null);
    rerender(<SettlementInspector {...props} settlementId={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Select a positive whole settlement ID");
  });

  it("labels missing timestamps/fields and unsupported domain details", () => {
    render(<SettlementInspector history={[{ turn: 2, active_settlements: [{ settlement_id: 7 }] }]}
      requestedTurn={2} settlementId={7} onSelectSettlement={() => {}} />);
    expect(screen.getByRole("status")).toHaveTextContent("Observation age unavailable");
    expect(within(population()).getByText("Unavailable — Not recorded")).toBeInTheDocument();
    expect(screen.getByText(/Infrastructure, pull factors, notable residents/)).toBeInTheDocument();
    expect(screen.getByText(/does not establish when detection last ran/)).toBeInTheDocument();
  });

  it("handles missing snapshot timestamps, duplicate turns and invalid IDs without retained values", () => {
    const props = { requestedTurn: 2, settlementId: 7, onSelectSettlement: vi.fn() };
    const { rerender } = render(<SettlementInspector {...props} history={history} />);
    for (const next of [[{ active_settlements: [quay] }], [history[1], history[1]], []]) {
      rerender(<SettlementInspector {...props} history={next} />);
      expect(screen.queryByText("Population estimate", { selector: "dt" })).not.toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent("unavailable");
    }
    rerender(<SettlementInspector {...props} history={history} settlementId={0} />);
    expect(screen.getByRole("status")).toHaveTextContent("ID 0 means no settlement");
  });

  it("rejects invalid UI IDs/turns without NaN DOM attributes or retained samples", () => {
    const errors = vi.spyOn(console, "error");
    try {
      const props = { history, onSelectSettlement: vi.fn() };
      const { rerender } = render(<SettlementInspector {...props} settlementId={NaN} requestedTurn={2} />);
      for (const settlementId of [0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
        rerender(<SettlementInspector {...props} settlementId={settlementId} requestedTurn={2} />);
        expect(screen.getByRole("combobox", { name: "Settlement" })).toHaveValue("");
        expect(screen.queryByText("Population estimate", { selector: "dt" })).not.toBeInTheDocument();
      }
      rerender(<SettlementInspector {...props} settlementId={7} requestedTurn={NaN} />);
      expect(screen.getByRole("status")).toHaveTextContent("As of turn unavailable");
      expect(screen.getByText("No timestamped historical samples in this window.")).toBeInTheDocument();
      expect(errors).not.toHaveBeenCalled();
    } finally {
      errors.mockRestore();
    }
  });

  it("preserves accessible native controls and repeated/interrupted rendering", () => {
    const props = { history, requestedTurn: 2, settlementId: 7, onSelectSettlement: vi.fn(), onClose: vi.fn() };
    const { rerender, unmount } = render(<StrictMode><SettlementInspector {...props} /></StrictMode>);
    const select = screen.getByRole("combobox", { name: "Settlement" });
    select.focus();
    expect(select).toHaveFocus();
    for (let index = 0; index < 4; index++) rerender(<StrictMode><SettlementInspector {...props} /></StrictMode>);
    expect(select).toHaveFocus();
    expect(props.onSelectSettlement).not.toHaveBeenCalled();
    expect(screen.getByRole("region", { name: "River Quay" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("Source provenance").tagName).toBe("SUMMARY");
    unmount();
    render(<SettlementInspector {...props} settlementId={9} requestedTurn={3} />);
    expect(screen.getByRole("heading", { name: "Upper Ferry" })).toBeInTheDocument();
    expect(within(population()).getByText("40")).toBeInTheDocument();
  });

  it("bounds population rows and resets pagination after turn/selection changes", () => {
    const many = Array.from({ length: 55 }, (_, turn) => ({ ...history[1], turn: turn + 2, settlement_source_turn: turn + 2 }));
    const props = { history: many, requestedTurn: 56, settlementId: 7, onSelectSettlement: vi.fn() };
    const { rerender } = render(<SettlementInspector {...props} />);
    fireEvent.click(screen.getByText("Recorded population history"));
    const table = screen.getByRole("table", { name: "Settlement population observations" });
    expect(within(table).getAllByRole("row")).toHaveLength(21);
    fireEvent.click(screen.getByRole("button", { name: "Next samples" }));
    expect(screen.getByText("21–40 of 55 historical samples")).toBeInTheDocument();
    rerender(<SettlementInspector {...props} settlementId={9} />);
    expect(screen.getByText("1–20 of 55 historical samples")).toBeInTheDocument();
    rerender(<SettlementInspector {...props} requestedTurn={3} />);
    expect(screen.getByText("1–2 of 2 historical samples")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next samples" })).toBeDisabled();
  });

  it("clamps a paged table after same-turn history replacement and rejects invalid turn samples", () => {
    const many = Array.from({ length: 55 }, (_, turn) => ({ ...history[1], turn: turn + 2, settlement_source_turn: turn + 2 }));
    const props = { requestedTurn: 56, settlementId: 7, onSelectSettlement: vi.fn() };
    const { rerender } = render(<SettlementInspector {...props} history={many} />);
    fireEvent.click(screen.getByText("Recorded population history"));
    fireEvent.click(screen.getByRole("button", { name: "Next samples" }));
    rerender(<SettlementInspector {...props} history={[many[0], many[54]]} />);
    expect(screen.getByText("1–2 of 2 historical samples")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous samples" })).toBeDisabled();
    rerender(<SettlementInspector {...props} history={many} requestedTurn={Infinity} />);
    expect(screen.getByText("No timestamped historical samples in this window.")).toBeInTheDocument();
    expect(screen.queryByText("Population estimate", { selector: "dt" })).not.toBeInTheDocument();
  });
});
