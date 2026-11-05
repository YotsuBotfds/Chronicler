import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { FoodAllocation } from "../FoodAllocation";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { Workshops } from "../Workshops";
import { record as commonsRecord } from "../../../lib/__tests__/commonsRulesFixture";
import { payroll } from "../../../lib/__tests__/workshopFinanceFixture";
import { localBudgetsRecord } from "../../../lib/__tests__/localBudgetsFixture";
import { record as apprenticeshipRecord } from "../../../lib/__tests__/apprenticeshipFixture";
import { record as clearingRecord, unprotected as clearingUnprotected } from "../../../lib/__tests__/clearingProtectionFixture";
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
    civilizations: [{ name: "Selurian" }, { name: "Varn" }] } } as unknown as Bundle,
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
  expect(screen.queryByRole("heading", { name: /Academy learners/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Workshop payroll/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Local budgets/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Relocation costs/ })).not.toBeInTheDocument();
});

it("mounts relocation costs when the snapshot recorded them", () => {
  const relocation = { schema_version: 1, stage: "L7", mode: "paid", source_turn: 4, gate: null, households: null,
    regions: null, services: null, assistance: null, counters: { groups_proposed: 0 }, parameters: { fare_milli: 1000 } };
  const p = props({ schema_version: 1, relocation_costs: relocation });
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /Relocation costs · snapshot 5/ })).toBeInTheDocument();
});

it("mounts local budgets when the snapshot recorded them", () => {
  const p = props({ schema_version: 1, local_budgets: localBudgetsRecord() }, 31);
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /Local budgets · snapshot 31/ })).toBeInTheDocument();
});

it("mounts clearing protection only when the snapshot recorded it", () => {
  // The fixture's other rows name a fourth region; this bundle has three (the reader refuses those).
  const rec = clearingRecord({ unprotected: [clearingUnprotected()],
    decisions: [{ turn: 4, region_id: 1, civ: 1, kind: "adopted", reason: "clearing_pressure" }] });
  const p = props({ schema_version: 1, clearing_protection: rec }, 5);
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /Clearing protection · snapshot 5/ })).toBeInTheDocument();
  expect(screen.queryByText(/names no package this viewer reads/)).not.toBeInTheDocument();
});

it("mounts apprenticeship and veterans only when the snapshot recorded them", () => {
  // The apprenticeship fixture names regions 1 and 2 of this three-region bundle.
  const p = props({ schema_version: 1, apprenticeship: apprenticeshipRecord }, 5);
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /Workshop apprenticeship · snapshot 5/ })).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Veterans" })).not.toBeInTheDocument();
  cleanup();
  // An unreadable veterans record still mounts the panel, which says it is unavailable.
  const q = props({ schema_version: 1, veteran_reintegration: { schema_version: 1, stage: "RS3" } }, 5);
  render(<LivelihoodsPanel {...q} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByText(/Veteran reintegration is not observed or is unavailable at snapshot 5/)).toBeInTheDocument();
  expect(screen.queryByText(/names no package this viewer reads/)).not.toBeInTheDocument();
});

it("mounts repair projects only when the snapshot recorded them", () => {
  // A record of another stage is unreadable: the panel mounts and says so.
  const p = props({ schema_version: 1, repair_projects: { schema_version: 1, stage: "RS0" } }, 5);
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByText(/Repair projects are not observed or are unavailable at snapshot 5/)).toBeInTheDocument();
  expect(screen.queryByText(/names no package this viewer reads/)).not.toBeInTheDocument();
  cleanup();
  render(<LivelihoodsPanel {...props({ schema_version: 1, workshops }, 5)} onSeek={vi.fn()} onSelectEvent={vi.fn()}
    onSelectCivilization={vi.fn()} />);
  expect(screen.queryByRole("region", { name: "Repair projects" })).not.toBeInTheDocument();
});

it("mounts remittances only when the snapshot recorded them, an unobserved frame as unknown", () => {
  const unobserved = { schema_version: 1, stage: "RS4", mode: "send", source_turn: 4, funnel: null, totals: null,
    regions: null, moves: null, moves_dropped: null, closures: null, closures_dropped: null, receipts: null,
    receipts_dropped: null, unmet: null, unmet_dropped: null, last_pool_reset: null, counters: {},
    parameters: { settled_turns: 5, share_permille: 100, reserve_milli: 2000, cap_milli: 1000, fee_permille: 150,
      min_sentiment: 20, adult_age: 20, max_entries: 2048 } };
  const p = props({ schema_version: 1, remittances: unobserved }, 5);
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /Remittances and diaspora · snapshot 5/ })).toBeInTheDocument();
  expect(screen.queryByText(/names no package this viewer reads/)).not.toBeInTheDocument();
  cleanup();
  render(<LivelihoodsPanel {...props({ schema_version: 1, workshops }, 5)} onSeek={vi.fn()} onSelectEvent={vi.fn()}
    onSelectCivilization={vi.fn()} />);
  expect(screen.queryByRole("heading", { name: /Remittances and diaspora/ })).not.toBeInTheDocument();
});

it("mounts workshop payroll beside its workshops when recorded", () => {
  const p = props({ schema_version: 1, workshop_payroll: payroll });
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /Workshop payroll · snapshot 5/ })).toBeInTheDocument();
});

it("mounts academy learners when the snapshot recorded them", () => {
  const learning = { schema_version: 1, stage: "L5", mode: "learn", source_turn: 4, cohorts: [], archive: [],
    graduates: [], receipts: [], counters: { academy_turns: 1 }, parameters: { sessions_to_complete: 4 } };
  const p = props({ schema_version: 1, learning_cohorts: learning });
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /Academy learners · snapshot 5/ })).toBeInTheDocument();
});

it("mounts commons rules when the snapshot recorded them", () => {
  const p = props({ schema_version: 1, commons_rules: commonsRecord() });
  render(<LivelihoodsPanel {...p} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByRole("heading", { name: /Commons rules/ })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Food allocation/ })).not.toBeInTheDocument();
});

it("refuses malformed food allocation totals and samples visibly instead of crashing or showing zero", () => {
  // Review R3 2026-11-05: totals were checked only as an object, so a missing
  // amount threw in toLocaleString and a missing count rendered as 0.
  const without = (key: string) => Object.fromEntries(Object.entries(food.totals).filter(([k]) => k !== key));
  const noAllocated = without("allocated");
  const noScarce = without("scarce_regions");
  for (const bad of [
    { ...food, totals: noAllocated }, { ...food, totals: noScarce },
    { ...food, totals: { ...food.totals, shortfall: "1.2" } }, { ...food, totals: { ...food.totals, alive: -1 } },
    { ...food, sample: [{ id: 11 }] }, { ...food, sample: [[11, 9, 11, 0.5, false]] },
    { ...food, sample: [[11, 1, 11, null, false]] },
  ]) {
    render(<FoodAllocation {...props({ schema_version: 1, food_allocation: bad })} />);
    expect(screen.getByText(/not observed or is unavailable at snapshot 5/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    cleanup();
  }
});

it("marks the relief total as partial when some regions' relief share is unknown", () => {
  const partial = { ...food, totals: { ...food.totals, relief_to_targeted: 0.4, relief_unknown_regions: 2 } };
  render(<FoodAllocation {...props({ schema_version: 1, food_allocation: partial })} />);
  const totals = within(screen.getByRole("table", { name: "Food allocation totals at snapshot 5" }));
  expect(totals.getByRole("row", { name: /Relief to targeted/ })).toHaveTextContent(/unknown in 2 regions/);
});

it("says so when the livelihoods record itself is unreadable or names no known package", () => {
  // Review R3 2026-11-05: a malformed top-level record left an empty tab.
  for (const bad of ["garbage", [1, 2], { schema_version: 2, food_allocation: food }, { food_allocation: food }]) {
    render(<LivelihoodsPanel {...props(bad)} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
    expect(screen.getByText(/livelihoods record at snapshot 5 is unreadable/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Food allocation/ })).not.toBeInTheDocument();
    cleanup();
  }
  render(<LivelihoodsPanel {...props({ schema_version: 1, household_purchases: {} })} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByText(/names no package this viewer reads/)).toBeInTheDocument();
  cleanup();
  render(<LivelihoodsPanel {...props(undefined)} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByText(/No livelihoods observation is recorded at snapshot 5/)).toBeInTheDocument();
});

it("re-dates every section to the scrubbed snapshot on rewind, never keeping later values", () => {
  // Review R3 adversarial: snapshot 7 records more workshops and a short region
  // than snapshot 5; rewinding to 5 and then to a snapshot without a record
  // must show only that snapshot's own values.
  const later = { schema_version: 1,
    workshops: { ...workshops, source_turn: 6, receipts: [{ ...receipt, turn: 6, crew: [11, 15, 19], eligible: 3 }] },
    food_allocation: { ...food, source_turn: 6, totals: { ...food.totals, alive: 9 } } };
  const extra = { onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  const view = render(<LivelihoodsPanel {...props(later, 7)} {...extra} />);
  expect(screen.getByRole("heading", { name: "Public workshops · snapshot 7" })).toBeInTheDocument();
  expect(within(within(screen.getByRole("table", { name: "Workshop sites at snapshot 7" }))
    .getAllByRole("row")[1]).getAllByRole("cell")[4]).toHaveTextContent(/^3$/);
  expect(within(screen.getByRole("table", { name: "Food allocation totals at snapshot 7" }))
    .getByRole("row", { name: /People in short regions/ })).toHaveTextContent("9");
  view.rerender(<LivelihoodsPanel {...props({ schema_version: 1, workshops, food_allocation: food }, 5)} {...extra} />);
  expect(screen.queryByText(/snapshot 7/)).not.toBeInTheDocument();
  const crewCell = (turn: number) => within(within(screen.getByRole("table", { name: `Workshop sites at snapshot ${turn}` }))
    .getAllByRole("row")[1]).getAllByRole("cell")[4];
  expect(crewCell(5)).toHaveTextContent(/^2$/);
  expect(within(screen.getByRole("table", { name: "Food allocation totals at snapshot 5" }))
    .getByRole("row", { name: /People in short regions/ })).toHaveTextContent("4");
  // A stale record (dated to another snapshot) is never shown as this one's.
  view.rerender(<LivelihoodsPanel {...props(later, 6)} {...extra} />);
  expect(screen.getByText(/Workshops are not observed or are unavailable at snapshot 6/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  view.rerender(<LivelihoodsPanel {...props(undefined, 3)} {...extra} />);
  expect(screen.getByText(/No livelihoods observation is recorded at snapshot 3/)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Public workshops/ })).not.toBeInTheDocument();
});
