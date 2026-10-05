import { StrictMode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { CombinedInspectionDemo } from "./CombinedInspectionDemo";

afterEach(cleanup);
const ledger = () => screen.getByRole("region", { name: "Event ledger" });
const inspector = () => screen.getByLabelText("Settlement").closest("section")!;
const turn = (value: number) => fireEvent.change(screen.getByLabelText("Requested turn"), { target: { value } });
const civilization = (value: string) => fireEvent.change(screen.getByLabelText("Example civilization"), { target: { value } });
const settlement = (value: string) => fireEvent.change(screen.getByLabelText("Settlement"), { target: { value } });
const population = () => within(inspector()).getByText("Population estimate", { selector: "dt" }).nextElementSibling!;
function expandGroups() {
  within(ledger()).queryAllByRole("button", { name: /events on this page/ }).forEach(button => {
    if (button.getAttribute("aria-expanded") === "false") fireEvent.click(button);
  });
}
function disclose(name: string) {
  const summary = within(inspector()).getByText(name, { selector: "summary" });
  (summary.parentElement as HTMLDetailsElement).open = true;
}

describe("isolated combined inspection", () => {
  it("labels the synthetic scope, uses one bounded turn and civilization, and hides future actors/types/records", () => {
    render(<StrictMode><CombinedInspectionDemo /></StrictMode>);
    expect(screen.getByText(/Synthetic \/ nonproduction preview/)).toBeInTheDocument();
    expect(screen.getByText(/contain no settlement IDs/)).toBeInTheDocument();
    expect(screen.getByLabelText("Requested turn")).toHaveAttribute("max", "32");
    expect(within(ledger()).getByLabelText("Civilization")).toBeDisabled();
    expect(within(ledger()).getByLabelText("Civilization")).toHaveValue(JSON.stringify("Alpha"));
    expect(within(ledger()).getByRole("status")).toHaveTextContent("1–24 of 58 events · Page 1 of 3");
    turn(32); expandGroups();
    expect(screen.queryByText(/FUTURE SENTINEL|Future civilization|future_sentinel/)).not.toBeInTheDocument();
  });

  it("scrubs both panels forward and back through founding, stale source, gaps and dissolution", () => {
    render(<CombinedInspectionDemo />);
    for (const value of [1, 2, 3, 4, 5, 4, 3, 2, 1]) {
      turn(value);
      expect(within(ledger()).getByText(`Recorded events through turn ${value}. Civilization matches exported actor names. General entity IDs are unavailable in this event format.`)).toBeInTheDocument();
      const status = within(inspector()).getByRole("status");
      expect(status).toHaveTextContent(`As of turn ${value}.`);
      if (value === 2 || value === 3) {
        expect(population()).toHaveTextContent("23");
        expect(status).toHaveTextContent(value === 3 ? "Stale summary · source turn 2 · observation age 1 turns" : "Same-turn source timestamp");
        expect(within(inspector()).getByText(`Founding: ${value === 2 ? "Recorded in this snapshot" : "Not listed in this snapshot"}`)).toBeInTheDocument();
      } else {
        expect(within(inspector()).queryByText("Population estimate", { selector: "dt" })).not.toBeInTheDocument();
        expect(status).toHaveTextContent(value === 1 ? "not listed in this snapshot" : value === 4 ? "No historical snapshot recorded" : "Dissolution recorded");
      }
      expect(within(ledger()).getByRole("status")).toHaveTextContent(`of ${value === 1 ? 1 : value === 2 ? 2 : value === 5 ? 59 : 58} events`);
    }
  });

  it("expands and paginates all Alpha records exactly once in meaningful order without changing settlement values", () => {
    render(<CombinedInspectionDemo />);
    const seen: number[] = [];
    for (let page = 1; page <= 3; page++) {
      expandGroups();
      ledger().querySelectorAll<HTMLElement>("[data-source-index]").forEach(row => seen.push(Number(row.dataset.sourceIndex)));
      expect(population()).toHaveTextContent("23");
      expect(within(ledger()).queryByText(/Beta migration|Actorless weather|FUTURE SENTINEL/)).not.toBeInTheDocument();
      if (page < 3) fireEvent.click(within(ledger()).getByRole("button", { name: "Next events" }));
    }
    expect(seen).toEqual([...Array.from({ length: 55 }, (_, index) => index + 2), 65, 1, 0]);
    expect(new Set(seen).size).toBe(58);
    expect(within(ledger()).getByRole("button", { name: "Next events" })).toBeDisabled();
  });

  it("filters never backfill unrelated actors; reset retains shared civilization and clears interrupted pages", () => {
    render(<CombinedInspectionDemo />);
    fireEvent.click(within(ledger()).getByRole("button", { name: "Next events" })); expandGroups();
    fireEvent.change(within(ledger()).getByLabelText("Event type"), { target: { value: JSON.stringify("weather") } });
    expect(within(ledger()).getByRole("status")).toHaveTextContent("0–0 of 0 events · Page 1 of 1");
    expect(population()).toHaveTextContent("23");
    fireEvent.click(within(ledger()).getByRole("button", { name: "Reset filters" }));
    fireEvent.change(within(ledger()).getByLabelText("From turn"), { target: { value: "5" } });
    fireEvent.change(within(ledger()).getByLabelText("Through turn"), { target: { value: "33" } });
    expect(within(ledger()).getByRole("status")).toHaveTextContent("0–0 of 0 events");
    turn(5);
    expect(within(ledger()).getByRole("status")).toHaveTextContent("1–1 of 1 events");
    expect(within(ledger()).getByText("Alpha records River Quay dissolution.")).toBeInTheDocument();
    fireEvent.click(within(ledger()).getByRole("button", { name: "Reset filters" }));
    expect(within(ledger()).getByLabelText("Civilization")).toHaveValue(JSON.stringify("Alpha"));
    expect(within(ledger()).getByRole("status")).toHaveTextContent("Page 1 of 3");
  });

  it("switches civilization atomically after interrupted filters/pages/settlement selection, including an empty example", () => {
    render(<CombinedInspectionDemo />);
    settlement("9");
    fireEvent.change(within(ledger()).getByLabelText("Event type"), { target: { value: JSON.stringify("migration") } });
    fireEvent.click(within(ledger()).getByRole("button", { name: "Next events" })); expandGroups();
    civilization("Beta");
    expect(screen.getByLabelText("Settlement")).toHaveValue("21");
    expect(population()).toHaveTextContent("71");
    expect(within(ledger()).getByRole("status")).toHaveTextContent("1–9 of 9 events · Page 1 of 1");
    expect(within(ledger()).getByLabelText("Event type")).toHaveValue("");
    expandGroups();
    expect(within(ledger()).queryByText(/Alpha migration record|River Quay|Upper Ferry/)).not.toBeInTheDocument();
    expect(within(inspector()).queryByText(/River Quay|Upper Ferry/)).not.toBeInTheDocument();
    civilization("Nobody");
    expect(within(ledger()).getByRole("status")).toHaveTextContent("0–0 of 0 events");
    expect(within(inspector()).queryByText("Population estimate", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Settlement")).toHaveValue("");
    civilization("Alpha");
    expect(screen.getByLabelText("Settlement")).toHaveValue("7");
    expect(population()).toHaveTextContent("23");
    expect(within(ledger()).getByRole("button", { name: /events on this page/ })).toHaveAttribute("aria-expanded", "false");
  });

  it("preserves stale source labels and lossless history pages; population seek updates the shared cutoff", () => {
    render(<CombinedInspectionDemo />); settlement("9"); turn(25);
    expect(population()).toHaveTextContent("40");
    expect(within(inspector()).getByRole("status")).toHaveTextContent("source turn 23 · observation age 2 turns");
    disclose("Recorded population history");
    expect(within(inspector()).getByText("1–20 of 24 historical samples")).toBeInTheDocument();
    const table = within(inspector()).getByRole("table");
    const seen = within(table).getAllByRole("row").slice(1).map(row => Number(within(row).getAllByRole("cell")[0].textContent));
    fireEvent.click(within(inspector()).getByRole("button", { name: "Next samples" }));
    seen.push(...within(table).getAllByRole("row").slice(1).map(row => Number(within(row).getAllByRole("cell")[0].textContent)));
    expect(seen).toEqual(Array.from({ length: 25 }, (_, index) => index + 1).filter(value => value !== 4));
    turn(24);
    expect(within(inspector()).getByRole("status")).toHaveTextContent("source turn 23 · observation age 1 turns");
    expect(within(inspector()).getByText("1–20 of 23 historical samples")).toBeInTheDocument();
    fireEvent.click(within(inspector()).getByRole("button", { name: "Inspect settlement at turn 2" }));
    expect(screen.getByLabelText("Requested turn")).toHaveValue("2");
    expect(population()).toHaveTextContent("40");
    expect(within(ledger()).getByRole("status")).toHaveTextContent("1–2 of 2 events");
  });

  it("clears missing fields/selection and never carries previous values into another exact-turn snapshot", () => {
    render(<CombinedInspectionDemo />); settlement("9"); turn(6);
    expect(population()).toHaveTextContent("Unavailable — Not recorded");
    expect(within(inspector()).getByRole("status")).toHaveTextContent("Observation age unavailable");
    settlement("");
    expect(within(inspector()).queryByText("Population estimate", { selector: "dt" })).not.toBeInTheDocument();
    turn(3); settlement("7"); expect(population()).toHaveTextContent("23");
    settlement("9"); expect(population()).toHaveTextContent("40");
    expect(within(ledger()).getByRole("status")).toHaveTextContent("of 58 events");
  });

  it("keeps keyboard focus on usable sample navigation and returns population seeks to the shared turn control", () => {
    render(<CombinedInspectionDemo />); settlement("9"); turn(25); disclose("Recorded population history");
    const next = within(inspector()).getByRole("button", { name: "Next samples" });
    const previous = within(inspector()).getByRole("button", { name: "Previous samples" });
    next.focus(); fireEvent.click(next);
    expect(previous).toHaveFocus(); expect(next).toBeDisabled();
    fireEvent.click(previous);
    expect(next).toHaveFocus(); expect(previous).toBeDisabled();
    const seek = within(inspector()).getByRole("button", { name: "Inspect settlement at turn 2" });
    seek.focus(); fireEvent.click(seek);
    expect(screen.getByLabelText("Requested turn")).toHaveFocus();
    expect(screen.getByLabelText("Requested turn")).toHaveValue("2");
    expect(population()).toHaveTextContent("40");
    expect(within(ledger()).getByRole("status")).toHaveTextContent("1–2 of 2 events");
  });

  it("close/reopen and source reload discard interrupted local UI while respecting changed shared controls", () => {
    render(<CombinedInspectionDemo />);
    fireEvent.click(within(ledger()).getByRole("button", { name: "Next events" })); expandGroups();
    fireEvent.click(screen.getByRole("button", { name: "Close experimental panels" }));
    expect(screen.queryByRole("region", { name: "Event ledger" })).not.toBeInTheDocument();
    turn(5); civilization("Beta");
    fireEvent.click(screen.getByRole("button", { name: "Open experimental panels" }));
    expect(population()).toHaveTextContent("71");
    expect(within(ledger()).getByRole("status")).toHaveTextContent("Page 1 of 1");
    fireEvent.click(screen.getByRole("button", { name: "Reload synthetic fixture" }));
    expect(screen.getByLabelText("Requested turn")).toHaveValue("3");
    expect(screen.getByLabelText("Example civilization")).toHaveValue("Alpha");
    expect(population()).toHaveTextContent("23");
    expect(within(ledger()).getByRole("status")).toHaveTextContent("Page 1 of 3");
    expect(within(ledger()).getByRole("button", { name: /events on this page/ })).toHaveAttribute("aria-expanded", "false");
  });
});
