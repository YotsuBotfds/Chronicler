import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { Relocation } from "../Relocation";
afterEach(cleanup);

/** Constructed observations to test rendering; not a simulation run. */
const helped = { turn: 3, lead: 30, from_region: 0, to_region: 1, members: [30, 31, 32], adults: [30, 31], children: 1,
  liquid: 1600, reason: "assisted", applied: true, fare: 3000, assistance: 1500, payer: 0, movers_share: 1500,
  debits: [[30, 750, 750, 0, "applied"], [31, 750, 750, 0, "applied"]], paid: 1500, residual: 0,
  assistance_status: "charged", is_return: true };
const blocked = { ...helped, lead: 40, members: [40, 41], adults: [40], children: 1, liquid: 100, reason: "short",
  applied: false, fare: 2000, assistance: 0, payer: -1, movers_share: 2000, debits: [], paid: 0, residual: 0,
  assistance_status: null, is_return: false };
const record = { schema_version: 1, stage: "L7", mode: "assisted", source_turn: 3, gate: { assisted: 1, short: 1 },
  households: [helped, blocked], households_dropped: 5,
  regions: [{ region: 1, capacity: 10, alive_before: 12, alive_after: 15, arrivals: 3, arrival_households: 1,
    assisted_households: 1, departures: 0, departure_households: 0, pressure_before: 1.2, pressure_after: 1.5,
    food_sufficiency: 0.8 }],
  services: [{ region: 1, arrival_turn: 2, food_sufficiency: 0.8, arrivals_rationed: 3, arrivals_mean_ration: 0.5,
    residents_rationed: 7, residents_mean_ration: 0.9 }],
  assistance: [{ civ: 0, turn: 3, granted: 1500, charged_coins: 2, refused: 0, status: "charged" }],
  counters: { groups_proposed: 9, groups_assisted: 1, groups_short: 1, groups_applied: 7, groups_paid: 7,
    fare_debited_milli: 9500, assistance_charged_milli: 1500 }, parameters: { fare_milli: 1000 } };

function props(relocation_costs: unknown, turn = 4) {
  const snapshot = { turn, livelihoods: { schema_version: 1, relocation_costs } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }], civilizations: [{ name: "Selurian" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("shows who moved, who paid, who was assisted and the destination's pressure", () => {
  const p = props(record);
  render(<Relocation {...p} />);
  expect(screen.getByRole("heading", { name: "Relocation costs · snapshot 4" })).toBeInTheDocument();
  expect(screen.getByText(/not to anyone/)).toBeInTheDocument();
  const funnel = within(screen.getByRole("table", { name: "Relocation funnel at snapshot 4" }));
  expect(funnel.getByRole("row", { name: /Passed with assistance/ })).toHaveTextContent("1");
  expect(funnel.getByRole("row", { name: /Fares paid by movers/ })).toHaveTextContent("9.5");
  const rows = within(screen.getByRole("table", { name: "Households at the fare gate at snapshot 4" })).getAllByRole("row");
  expect(rows[1]).toHaveTextContent("30 (return)");
  expect(rows[1]).toHaveTextContent("1.5 from Selurian (charged)");
  expect(rows[2]).toHaveTextContent("short");
  expect(rows[2]).toHaveTextContent("No");
  expect(screen.getByText(/5 more households/)).toBeInTheDocument();
  const pressure = within(screen.getByRole("table", { name: "Receiving pressure at snapshot 4" }));
  expect(pressure.getAllByRole("row")[1]).toHaveTextContent("1.2 → 1.5");
  const service = within(screen.getByRole("table", { name: "Arrivals' service at snapshot 4" }));
  expect(service.getAllByRole("row")[1]).toHaveTextContent("0.5");
  fireEvent.click(screen.getAllByRole("button", { name: "Ashford Vale" })[0]);
  expect(p.onSelectRegion).toHaveBeenCalledWith("Ashford Vale");
});

it("says so when the record is missing and keeps an unobserved turn unknown", () => {
  render(<Relocation {...props(record, 9)} />);
  expect(screen.getByText(/not observed or are unavailable at snapshot 9/)).toBeInTheDocument();
  cleanup();
  render(<Relocation {...props({ ...record, mode: "liquidity_only", gate: null, households: null, households_dropped: null,
    regions: null, services: null, assistance: null })} />);
  expect(screen.getByText(/Liquidity only \(control\)/)).toBeInTheDocument();
  expect(screen.getByText(/unknown, not zero/)).toBeInTheDocument();
});
