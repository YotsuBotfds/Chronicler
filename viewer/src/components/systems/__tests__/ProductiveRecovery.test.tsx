import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { Apprenticeship } from "../Apprenticeship";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { MaintenanceObligation } from "../MaintenanceObligation";
import { OperatingWear } from "../OperatingWear";
import { RecoveryCrews } from "../RecoveryCrews";
import { RepairProjects } from "../RepairProjects";
import { TimberSupply } from "../TimberSupply";
import {
  cutReceipt, localBudgets, maintenanceObligation, operatingWear, recoveryCrews, timberSupply, unpaidReceipt, v2Record,
} from "../../../lib/__tests__/productiveRecoveryFixture";
afterEach(cleanup);

const REGIONS = [{ name: "Oldmere" }, { name: "Ashford Vale" }, { name: "Bram Fen" }, { name: "Highwood" }];
function props(livelihoods: Record<string, unknown> | null, turn = 10) {
  const snapshot = { turn, livelihoods: livelihoods === null ? null : { schema_version: 1, ...livelihoods } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: REGIONS, civilizations: [{ name: "Selurian" }, { name: "Varn" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}
const table = (name: string) => within(screen.getByRole("table", { name }));
const row = (name: string, label: RegExp) => table(name).getByRole("row", { name: label });

it("timber supply shows the gains with their costs: labour away, wages, stock debited, losses and refusals", () => {
  const p = props({ timber_supply: timberSupply });
  render(<TimberSupply {...p} />);
  expect(screen.getByRole("heading", { name: "Timber supply · snapshot 10" })).toBeInTheDocument();
  expect(screen.getByText(/^Simulation turn 9\. Supply:/)).toBeInTheDocument();
  const totals = "Timber supply accounts to snapshot 10";
  expect(row(totals, /Timber cut/)).toHaveTextContent("6.5");
  expect(row(totals, /Lost to transit decay/)).toHaveTextContent("0.03");
  expect(row(totals, /Abandoned at the forest/)).toHaveTextContent("1");
  expect(row(totals, /Farm labour away from home/)).toHaveTextContent("12 of 12");
  expect(row(totals, /Wages paid/)).toHaveTextContent("9 (0)");
  expect(row(totals, /Recalls/)).toHaveTextContent("1 · 1");
  expect(screen.getByText(/every healthy forest in range is already being cut 3/)).toBeInTheDocument();
  expect(screen.getByText(/Ended without delivering: crew lost 1/)).toBeInTheDocument();
  const rows = table("Expeditions this turn at snapshot 10").getAllByRole("row");
  expect(rows[1]).toHaveTextContent("#3 (Selurian)");
  expect(rows[1]).toHaveTextContent("11 (veteran)");
  expect(rows[1]).toHaveTextContent("3 of 3");
  expect(rows[1]).toHaveTextContent("100 → 98.5 of 120");                        // the L3 stock debited
  expect(rows[1]).toHaveTextContent("13 (migrated)");
  expect(rows[2]).toHaveTextContent("walked home unpaid");
  expect(rows[2]).toHaveTextContent("recalled");
  expect(table("Expedition wages at snapshot 10").getAllByRole("row")[1]).toHaveTextContent("2 (prepaid 0 → 0.5)");
  const need = table("Timber needs at snapshot 10").getAllByRole("row");
  expect(need).toHaveLength(3);                                                 // supplied rows are summarised
  expect(need[2]).toHaveTextContent("Refused: every healthy forest in range is already being cut");
  expect(screen.getByText("1 more regions with open repairs had their timber.")).toBeInTheDocument();
  expect(screen.getByText(/1 from expedition #2 in Ashford Vale/)).toBeInTheDocument();
  expect(table("Per ended expedition to snapshot 10").getAllByRole("row")[1]).toHaveTextContent("2.25");
  fireEvent.click(within(rows[1]).getByRole("button", { name: "Oldmere" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Oldmere");
});

it("timber supply labels the cost-only control and keeps unknown turns and malformed records visible", () => {
  render(<TimberSupply {...props({ timber_supply: { ...timberSupply, receipts: null, ledger: null, stores: null, needs: null,
    needs_dropped: null, deposits: null } })} />);
  expect(screen.getByText(/crews, wages, farm labour and harvest are unknown, not zero/)).toBeInTheDocument();
  expect(screen.getByText(/needs, stores and deposits are unknown, not zero/)).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: "Expeditions this turn at snapshot 10" })).toBeNull();
  cleanup();
  render(<TimberSupply {...props({ timber_supply: { ...timberSupply, mode: "cost_only" } })} />);
  expect(screen.getByText(/rejected as malformed: the cost-only control cut timber/)).toBeInTheDocument();
  expect(screen.queryAllByRole("table")).toHaveLength(0);
  cleanup();
  const zero = { cut: 0, cargo: 0, delivered: 0, lost: 0, abandoned: 0 };
  const control = { ...timberSupply, mode: "cost_only", expeditions: timberSupply.expeditions.map((e) => ({ ...e, ...zero })),
    closed: timberSupply.closed.map((e) => ({ ...e, ...zero })), store: {}, stores: [], deposits: [],
    receipts: [{ ...cutReceipt, crew_labor: 0, cut: 0, cargo_after: 0 }, { ...unpaidReceipt, cargo_after: 0 }],
    needs: [], per_expedition: { ...timberSupply.per_expedition, cut: 0, delivered: 0 },
    counters: { ...timberSupply.counters, cut: 0, delivered: 0, lost: 0, abandoned_cargo: 0, crew_labor: 0, ended_cut: 0, ended_delivered: 0 } };
  render(<TimberSupply {...props({ timber_supply: control })} />);
  expect(screen.getByText(/^Simulation turn 9\. Cost-only control: .*nobody cuts/)).toBeInTheDocument();
  expect(screen.getByText(/the comparison the cost-only control supports/)).toBeInTheDocument();
  cleanup();
  render(<TimberSupply {...props({}, 4)} />);
  expect(screen.getByText("Timber supply is not observed at snapshot 4.")).toBeInTheDocument();
});

it("operating wear shows the declared wear, the offset and what fell below the gate", () => {
  render(<OperatingWear {...props({ operating_wear: operatingWear })} />);
  expect(screen.getByRole("heading", { name: "Operating wear · snapshot 10" })).toBeInTheDocument();
  expect(screen.getByText(/The switch has no mode/)).toBeInTheDocument();
  expect(screen.getByText(/Apprenticeship is on/)).toBeInTheDocument();
  expect(row("Operating wear to snapshot 10", /Wear − upkeep offset/)).toHaveTextContent("0.4 − 0.1 = 0.3");
  const rows = table("Worn sites at snapshot 10").getAllByRole("row");
  expect(rows[1]).toHaveTextContent("0.02 − 0.005 = 0.015");
  expect(rows[2]).toHaveTextContent("(fully offset)");
  expect(rows[3]).toHaveTextContent("now below the operating gate");
  expect(rows[3]).toHaveTextContent("nobody");
  cleanup();
  render(<OperatingWear {...props({ operating_wear: { ...operatingWear, receipts: null } })} />);
  expect(screen.getByText(/this turn's wear is unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<OperatingWear {...props({ operating_wear: { ...operatingWear, stage: "PL9" } })} />);
  expect(screen.getByText(/rejected as malformed: unknown operating-wear schema/)).toBeInTheDocument();
});

it("recovery crews show wages paid against the coins otherwise sunk, and the unpaid control", () => {
  render(<RecoveryCrews {...props({ recovery_crews: recoveryCrews })} />);
  expect(screen.getByRole("heading", { name: "Recovery crews · snapshot 10" })).toBeInTheDocument();
  expect(screen.getByText(/^Simulation turn 9\. Paid:/)).toBeInTheDocument();
  expect(row("Recovery crews to snapshot 10", /paid as wages to crews/)).toHaveTextContent("9.5 · 0.5");
  expect(screen.getByText(/charged 3.6 granary coins, which without crews would all leave the economy\. 3.5 reached the crews as wages and 0.1 was still sunk/)).toBeInTheDocument();
  const money = table("Granary crew money at snapshot 10").getAllByRole("row");
  expect(money[1]).toHaveTextContent("Selurian3.63.50.10.1");
  const crews = table("Crews at snapshot 10").getAllByRole("row");
  expect(crews[1]).toHaveTextContent("2 planned → 1.8 asked → 1.8 done (crew short of the plan)");
  expect(crews[1]).toHaveTextContent("30 (rural farmer, veteran; worked 1 of 1, wage 2)");
  expect(crews[2]).toHaveTextContent("no free adult farmer");
  expect(crews[3]).toHaveTextContent("site city alone: 2");
  expect(crews[3]).toHaveTextContent("42 (veteran (not a farmer)");
  cleanup();
  const sunk = { ...recoveryCrews, mode: "unpaid", receipts: [], ledger: [], counters: { granary_coin_cost_milli: 7000, granary_sunk_milli: 7000 } };
  render(<RecoveryCrews {...props({ recovery_crews: sunk })} />);
  expect(screen.getByText(/^Simulation turn 9\. Unpaid control:/)).toBeInTheDocument();
  expect(screen.getByText("No repair crew worked this turn.")).toBeInTheDocument();
  cleanup();
  render(<RecoveryCrews {...props({ recovery_crews: { ...recoveryCrews, receipts: null, ledger: null } })} />);
  expect(screen.getByText(/crews, wages and sunk coins are unknown, not zero/)).toBeInTheDocument();
});

it("maintenance obligation shows reserved, used and returned, and the budget it crowds out", () => {
  render(<MaintenanceObligation {...props({ maintenance_obligation: maintenanceObligation, local_budgets: localBudgets })} />);
  expect(screen.getByRole("heading", { name: "Maintenance obligation · snapshot 10" })).toBeInTheDocument();
  expect(screen.getByText(/^Simulation turn 9\. Reserve:/)).toBeInTheDocument();
  const decided = table("Reservations decided at snapshot 10").getAllByRole("row");
  expect(decided[1]).toHaveTextContent("Selurian6105 (binding)591");
  expect(screen.getByText(/Bargained budgets are 2 lower in all than without the reservations/)).toBeInTheDocument();
  const used = table("Reservations used at snapshot 10").getAllByRole("row");
  expect(used[1]).toHaveTextContent("Selurian4642 (3)0");
  expect(used[2]).toHaveTextContent("0 (no envelope)2");
  expect(row("Maintenance obligation to snapshot 10", /Used by repairs/)).toHaveTextContent("9 · 4");
  cleanup();
  // Without a readable L9 decision the crowding-out is unknown, not zero.
  render(<MaintenanceObligation {...props({ maintenance_obligation: { ...maintenanceObligation, mode: "reserve_only",
    uses: [], counters: {} } })} />);
  expect(screen.getByText(/^Simulation turn 9\. Reserve-only control:/)).toBeInTheDocument();
  expect(table("Reservations decided at snapshot 10").getAllByRole("row")[1]).toHaveTextContent("Unknown");
  expect(screen.getByText(/The budget left to bargain is unknown/)).toBeInTheDocument();
  cleanup();
  render(<MaintenanceObligation {...props({ maintenance_obligation: { ...maintenanceObligation, decisions: null, uses: null } })} />);
  expect(screen.getByText(/reservations for the next turn are unknown, not zero/)).toBeInTheDocument();
  expect(screen.getByText(/how reservations were used is unknown, not zero/)).toBeInTheDocument();
});

it("apprenticeship shows RS1 rules version 2: crew and attached apprentices, transfers, useful work and graduates", () => {
  render(<Apprenticeship {...props({ apprenticeship: v2Record }, 5)} />);
  expect(screen.getByText(/RS1 rules version 2: presence anywhere in the site's region/)).toBeInTheDocument();
  const sites = table("Apprenticeship sites at snapshot 5").getAllByRole("row");
  expect(sites[1]).toHaveTextContent("21: on the crew, taught by 7");
  expect(sites[1]).toHaveTextContent("22 (veteran) new: attached, taught by 7, income given up 0.1");
  expect(sites[1]).toHaveTextContent("24 (from site 1): missed (no mentor)");
  expect(sites[1]).toHaveTextContent("covered; offset by service 0.01, by apprenticeship 0");
  expect(row("Apprenticeship useful work to snapshot 5", /attached beside the crew/)).toHaveTextContent("3");
  const open = table("Open apprenticeships at snapshot 5").getAllByRole("row");
  expect(open[1]).toHaveTextContent("21, entered at 24");
  expect(open[1]).toHaveTextContent("2 / 1");
  expect(open[4]).toHaveTextContent("2 (ends after 4)");
  expect(screen.getByText(/Away from every open site this turn: 25 \(absent\)/)).toBeInTheDocument();
  expect(screen.getByText(/Living graduates: 30 \(completed turn 3 at Ashford, qualified/)).toBeInTheDocument();
  expect(screen.getByText(/long absence 1/)).toBeInTheDocument();
  cleanup();
  render(<Apprenticeship {...props({ apprenticeship: { ...v2Record, rules_version: undefined } }, 5)} />);
  expect(screen.getByText(/rejected as malformed: unknown apprenticeship rules version/)).toBeInTheDocument();
});

it("repair projects explain a granary suspended for no farmer", () => {
  const granary = { pid: 1, kind: "granary", asset: 0, region: 0, settlement_id: null, cause: "wear", war_key: null,
    war_start_turn: null, damages: [], opened_turn: 3, opened_condition: 0.4, controller: 0, scope: 10, delivered: 0,
    credited: 0, status: "open", closed_turn: null, closed_reason: null, work_turns: 0, stalled_turns: 2,
    stalls: { no_people: 2 }, timber_used: 0, wages_milli: 0, coin_cost_milli: 0, last_crew: [], history: [] };
  const stall = { turn: 9, pid: 1, kind: "granary", asset: 0, region: 0, payer: 0, status: "stalled", reasons: ["no_people"],
    requested: 0, delivered: 0, credited: 0, rate: null, crew: [], share: null, qualified: [], veterans: [], timber_held: 0,
    timber_used: 0, timber_returned: 0, wages_due_milli: 0, wages_milli: 0, wage_residual_milli: 0, coin_cost_milli: 0,
    envelope: null, condition_before: 0.4, condition_after: 0.4, remaining_after: 10, income_replaced: null };
  const rs2 = { schema_version: 1, stage: "RS2", mode: "repair", source_turn: 9, units: {}, projects: [granary], closed: [],
    damages: [], receipts: [stall], ledger: [{ turn: 9, civ: 0, projects: 1, work_delivered: 0, timber_used: 0,
      coin_cost_milli: 0, wages_due_milli: 0, wages_applied_milli: 0, wage_residual_milli: 0, charged: 0,
      prepaid_before_milli: 0, prepaid_after_milli: 0, envelope: null }],
    unmet: [{ kind: "granary", asset: 2, region: 2, condition: 0.2, reason: "no_people" }], suspended: [0], prepaid: {},
    counters: {}, parameters: { open_below: 0.75 } };
  render(<RepairProjects {...props({ repair_projects: rs2 })} />);
  const project = table("Open repair projects at snapshot 10").getAllByRole("row")[1];
  expect(project).toHaveTextContent("Stalled: no farmer in the region (suspended)");
  expect(project).toHaveTextContent("no farmer in the region (suspended) 2");
  expect(screen.getByText(/granary in Bram Fen at 0.2 \(no people\)/)).toBeInTheDocument();
});

it("mounts the productive-recovery panels only when recorded, and re-dates them on rewind", () => {
  const all = { timber_supply: timberSupply, operating_wear: operatingWear, recovery_crews: recoveryCrews,
    maintenance_obligation: maintenanceObligation, local_budgets: localBudgets };
  const headings = ["Operating wear", "Recovery crews", "Timber supply", "Maintenance obligation"];
  const { rerender } = render(<LivelihoodsPanel {...props(all)} />);
  for (const h of headings) expect(screen.getByRole("heading", { name: `${h} · snapshot 10` })).toBeInTheDocument();
  expect(screen.queryByText(/names no package this viewer reads/)).toBeNull();
  // An older snapshot of the same run, before these records existed: nothing mounted, nothing borrowed.
  rerender(<LivelihoodsPanel {...props({ local_budgets: { ...localBudgets, source_turn: 3, decisions: null } }, 4)} />);
  for (const h of headings) expect(screen.queryByRole("heading", { name: new RegExp(`^${h}`) })).toBeNull();
  // The same records at a later snapshot are refused as misdated, never shown with the old date.
  rerender(<LivelihoodsPanel {...props(all, 11)} />);
  for (const h of headings) {
    expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: `${h} · snapshot 10` })).toBeNull();
  }
  expect(screen.getAllByText(/rejected as malformed: misdated observation/)).toHaveLength(4);
  rerender(<LivelihoodsPanel {...props({ operating_wear: operatingWear })} />);
  expect(screen.getByRole("heading", { name: "Operating wear · snapshot 10" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /^Timber supply/ })).toBeNull();
  rerender(<LivelihoodsPanel {...props(null)} />);
  expect(screen.getByText("No livelihoods observation is recorded at snapshot 10.")).toBeInTheDocument();
});
