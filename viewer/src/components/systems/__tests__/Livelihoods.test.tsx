import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { FoodAllocation } from "../FoodAllocation";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { Workshops } from "../Workshops";
import { record as commonsRecord } from "../../../lib/__tests__/commonsRulesFixture";
afterEach(cleanup);

/** Constructed observations to test rendering; not a simulation run. */
const receipt = { turn: 4, site: 0, region: 1, settlement_id: 7, rank: 2, diverted_fraction: 0.3,
  resident_adult_farmers: 3, excluded_trip: 0, excluded_army: 1, excluded_assigned: 0, eligible: 2,
  crew: [11, 15], crew_ages: [30, 41], work_available: 0.6, allocated: 0.6, realized: 0.3,
  legacy_craft_ceiling: 1.5, region_craft_output: 0.6, region_craft_input: { timber: 0.5, ore: 0.1 },
  asset: "open", payer: 0, funded: true, craft_ceiling: 1.2, paid: { upkeep: 3 }, arrears_after: 0,
  condition_after: 1, affected_ordinary_income_share: 0 };
const workshops = { schema_version: 1, stage: "L1B", mode: "operate", source_turn: 4,
  sites: [{ site: 0, region: 1, settlement_id: 7, city_name: "Ashford", selected_turn: 2, status: "open",
    closed_turn: null, closed_reason: null, asset: "open", arrears: 0 }],
  closed: [{ site: 1, region: 0, settlement_id: 3, city_name: "Oldmere", selected_turn: 1, status: "closed",
    closed_turn: 3, closed_reason: "city_fell" }], receipts: [receipt], counters: {} };
const region = { region: 1, scarce: 1, phase2_alive: 4, alive: 4, households: 2, sufficiency: 0.7,
  rations_available: 2.8, relief_available: 0, allocated: 2.8, unallocated: 0, relief_to_targeted: 0,
  shortfall: 1.2, below_floor: 0, fully_fed: 2, min_ration: 0.5, max_ration: 1, people_poorer_half: 2,
  shortfall_poorer_half: 1, people_richer_half: 2, shortfall_richer_half: 0.2, children: 1, shortfall_children: 0.5 };
const food = { schema_version: 1, stage: "L2", regime: "floor_means", source_turn: 4,
  totals: { scarce_regions: 1, alive: 4, allocated: 2.8, unallocated: 0, shortfall: 1.2, people_poorer_half: 2,
    shortfall_poorer_half: 1, people_richer_half: 2, shortfall_richer_half: 0.2, children: 1, shortfall_children: 0.5,
    relief_to_targeted: 0 },
  regions: [region], sample: [[11, 1, 11, 0.5, false]], sample_columns: [], counters: {} };

function props(livelihoods: unknown, turn = 5) {
  const snapshot = { turn, livelihoods } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }, { name: "Third" }],
    civilizations: [{ name: "Selurian" }] } } as unknown as Bundle,
  snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("shows who worked, who paid and the region's actual inputs", () => {
  const p = props({ schema_version: 1, workshops });
  render(<Workshops {...p} />);
  expect(screen.getByRole("heading", { name: "Public workshops · snapshot 5" })).toBeInTheDocument();
  expect(screen.getByText(/public cost \(no wages, no private recipient\)/)).toBeInTheDocument();
  const row = within(screen.getByRole("table", { name: "Workshop sites at snapshot 5" })).getAllByRole("row")[1];
  expect(row).toHaveTextContent("Ashford");
  expect(row).toHaveTextContent("Selurian");
  expect(row).toHaveTextContent("upkeep 3");
  expect(row).toHaveTextContent("0.5 / 0.1");
  expect(row).toHaveTextContent("1.2 (1.5)");
  expect(screen.getByText(/Oldmere \(turn 3, city fell\)/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Ashford Vale" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Ashford Vale");
});

it("shows unequal shortfall by household means and keeps unknown turns unknown", () => {
  render(<FoodAllocation {...props({ schema_version: 1, food_allocation: food })} />);
  const totals = within(screen.getByRole("table", { name: "Food allocation totals at snapshot 5" }));
  expect(totals.getByRole("row", { name: /poorer half/ })).toHaveTextContent("0.5");
  expect(totals.getByRole("row", { name: /richer half/ })).toHaveTextContent("0.1");
  expect(screen.getByRole("table", { name: "Short regions at snapshot 5" })).toHaveTextContent("Ashford Vale");
  cleanup();
  render(<FoodAllocation {...props({ schema_version: 1, food_allocation: { ...food, totals: null, regions: null, sample: null } })} />);
  expect(screen.getByText(/rations are unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<FoodAllocation {...props({ schema_version: 1, food_allocation: food }, 7)} />);
  expect(screen.getByText(/not observed or is unavailable at snapshot 7/)).toBeInTheDocument();
});

it("composes only the packages a snapshot recorded", () => {
  const p = props({ schema_version: 1, food_allocation: food });
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /Food allocation/ })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Public workshops/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Timber stock/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Commons rules/ })).not.toBeInTheDocument();
});

it("mounts commons rules when the snapshot recorded them", () => {
  const p = props({ schema_version: 1, commons_rules: commonsRecord() });
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /Commons rules/ })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Food allocation/ })).not.toBeInTheDocument();
});
