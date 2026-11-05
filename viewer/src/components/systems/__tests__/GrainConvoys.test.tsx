import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { GrainConvoys } from "../GrainConvoys";
import { convoySnapshot } from "../../../lib/__tests__/grainConvoysFixture";

afterEach(cleanup);

const bundle = { world_state: { regions: [{ name: "Frostholm Tundra" }, { name: "Iron Peaks" }, { name: "Verdant Plains" }] } } as unknown as Bundle;
type Loose = { livelihoods: { grain_convoys: Record<string, unknown> & { transitions: Record<string, unknown>[] | null } } };

it("renders the funnel, convoys on the road and this turn's movements", () => {
  render(<GrainConvoys snapshot={convoySnapshot()} bundle={bundle} />);
  expect(screen.getByText("Grain convoys after simulation turn 31")).toBeInTheDocument();
  const funnel = screen.getByRole("table", { name: "Convoy activation up to simulation turn 31" });
  expect(within(funnel).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(
    ["2", "2", "0 (0 grain)", "0", "0", "0", "0", "2"]);
  const road = screen.getByRole("table", { name: "Convoys on the road after simulation turn 31" });
  expect(within(road).getAllByText("[Obsidian Shore] → Thornwood → Verdant Plains")).toHaveLength(2);
  expect(road).toHaveTextContent("edge 1, turn 1 of 2");
  expect(road).toHaveTextContent("Yes, 2 paid");
  const moves = screen.getByRole("table", { name: "Convoy movements in turn 31" });
  expect(moves).toHaveTextContent("Dispatched (paid)");
  expect(moves).toHaveTextContent("2 escort fee (public cost, no recipient)");
  expect(screen.getByText(/Escorts: 2 paid \(4 treasury\), 0 met no threat/)).toBeInTheDocument();
});

it("shows a capture's named market and a delivery's keeper", () => {
  const snapshot = convoySnapshot();
  const rows = (snapshot as unknown as Loose).livelihoods.grain_convoys.transitions!;
  Object.assign(rows[0], { operation: "captured", status: "captured", captor: 1, sink: "captor_market", sink_region: 0,
    threat: "frontier", threat_risk: 0.1 });
  Object.assign(rows[1], { operation: "arrived", status: "arrived", keeper: 3, paid: null, escort_fee: null, at: 2, at_name: "Verdant Plains" });
  render(<GrainConvoys snapshot={snapshot} bundle={bundle} />);
  const moves = screen.getByRole("table", { name: "Convoy movements in turn 31" });
  expect(moves).toHaveTextContent("threat: frontier (10% then)");
  expect(moves).toHaveTextContent("went to: captor market (Frostholm Tundra)");
  expect(moves).toHaveTextContent("kept by civilization 3, not the buyer");
});

it("says unknown, not zero, when the turn's movements were not recorded", () => {
  const snapshot = convoySnapshot();
  (snapshot as unknown as Loose).livelihoods.grain_convoys.transitions = null;
  render(<GrainConvoys snapshot={snapshot} bundle={bundle} />);
  expect(screen.getByText(/was not recorded \(unknown, not zero\)/)).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: /Convoy movements/ })).not.toBeInTheDocument();
});

it("distinguishes an absent record from an unreadable one", () => {
  const { rerender } = render(<GrainConvoys snapshot={{ turn: 5 } as unknown as TurnSnapshot} />);
  expect(screen.getByText(/No convoy record at snapshot 5. Absent is not zero/)).toBeInTheDocument();
  const stale = convoySnapshot();
  (stale as unknown as Loose).livelihoods.grain_convoys.source_turn = 12;
  rerender(<GrainConvoys snapshot={stale} />);
  expect(screen.getByText(/could not be read/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
