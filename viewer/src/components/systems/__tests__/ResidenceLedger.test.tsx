import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { ResidenceLedger } from "../ResidenceLedger";
import { RECORD_121, RECORD_122, REGION_NAMES } from "../../../lib/__tests__/residenceLedgerFixture";
afterEach(cleanup);

/* eslint-disable @typescript-eslint/no-explicit-any */
type Rec = Record<string, any>;
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const snap = (turn: number, record: Rec | undefined) => ({
  turn, livelihoods: record === undefined ? { schema_version: 1 } : { schema_version: 1, residence_ledger: record },
}) as unknown as TurnSnapshot;

function props(history: TurnSnapshot[], at: number) {
  const bundle = { history, world_state: { regions: REGION_NAMES.map((name) => ({ name })), civilizations: [] } } as unknown as Bundle;
  return { bundle, snapshot: history.find((s) => s.turn === at) ?? null, currentTurn: at, onSelectRegion: vi.fn() };
}
const table = (name: RegExp) => screen.getByRole("table", { name });

it("shows open spells by region, cause and anchor, this turn's flows and people away from home", () => {
  const p = props([snap(121, clone(RECORD_121)), snap(122, clone(RECORD_122))], 122);
  render(<ResidenceLedger {...p} />);
  expect(screen.getByRole("heading", { name: "Residence and displacement · snapshot 122" })).toBeInTheDocument();
  expect(screen.getByText(/254 of 577 people observed have motive-classified displacement spells \(44.0%\): 199 recorded flight, 55 recorded hunger/)).toBeInTheDocument();
  expect(screen.getByText(/not a census of all physical displacement/)).toBeInTheDocument();
  expect(screen.getByText(/Recent residence-arrival diagnostics were not recorded/)).toBeInTheDocument();
  expect(screen.getByText(/war 4, famine 135, persecution 60, no event 55/)).toBeInTheDocument();
  expect(screen.getByText(/This turn: 30 moves \(8 flight, 4 hunger, 18 voluntary, 0 other\); 9 spell\(s\) opened \(4 anchored to war\); 2 returned home/)).toBeInTheDocument();
  const spells = within(table(/Open displacement spells at snapshot 122/)).getAllByRole("row");
  expect(spells.length).toBeGreaterThan(5);
  const flows = table(/Movement and spells at snapshot 122/);
  const rows = RECORD_122.frame.regions as Rec[];
  const busiest = rows.reduce((a, r) => (r.departures > a.departures ? r : a));
  const row = within(flows).getByRole("row", { name: new RegExp(REGION_NAMES[busiest.region]) });
  expect(row).toHaveTextContent(String(busiest.departures));
  const awayRows = (RECORD_122.frame.regions as Rec[]).filter((r) => r.attached_away > 0);
  const army = within(table(/Away from home at snapshot 122/)).getByRole("row", { name: new RegExp(REGION_NAMES[awayRows[0].region]) });
  expect(army).toHaveTextContent(`${awayRows[0].attached}${awayRows[0].attached_away}${awayRows[0].in_transit}`);
  expect(awayRows.reduce((a, r) => a + r.attached_away, 0)).toBe(7);
  expect(screen.getByText(/For comparison only/)).toHaveTextContent("67.4%");       // 389 of 577 outside their birth region
  expect(table(/recent snapshots to 122/)).toBeInTheDocument();
  fireEvent.click(within(flows).getAllByRole("button")[0]);
  expect(p.onSelectRegion).toHaveBeenCalled();
});

it("shows retained arrivals without manufacturing a share from incomplete coverage", () => {
  const record = clone(RECORD_122) as Rec;
  record.frame.arrival_diagnostics = { window_turns: 20, coverage_complete: false, window_complete: true, complete: false };
  for (const row of record.frame.regions) Object.assign(row, { recent_residence_arrivals: 0, recent_residence_arrivals_unknown_reason: 0 });
  const row = record.frame.regions.find((r: Rec) => r.residents >= 2);
  Object.assign(row, { recent_residence_arrivals: 2, recent_residence_arrivals_unknown_reason: 1 });
  Object.assign(record.frame.totals, { recent_residence_arrivals: 2, recent_residence_arrivals_unknown_reason: 1 });
  render(<ResidenceLedger {...props([snap(122, record)], 122)} />);
  expect(screen.getByRole("heading", { name: "Recent residence arrivals" })).toBeInTheDocument();
  expect(screen.getByText(/2 retained living residents/)).toHaveTextContent("1 have an unclassified latest arrival reason");
  expect(screen.getByText(/Coverage incomplete; window complete/)).toHaveTextContent("population arrival share is unknown, not zero");
  expect(screen.getByRole("table", { name: "Recent residence arrivals at snapshot 122" })).toBeInTheDocument();
});

it("keeps disabled, absent, malformed, unobserved and recorded-zero readings apart", () => {
  render(<ResidenceLedger {...props([snap(122, undefined)], 122)} />);
  expect(screen.getByText(/off in this run \(--residence-ledger is not recorded in any snapshot\)/)).toBeInTheDocument();
  cleanup();
  render(<ResidenceLedger {...props([snap(121, clone(RECORD_121)), snap(122, undefined)], 122)} />);
  expect(screen.getByText(/on in this run, but snapshot 122 has no record; unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<ResidenceLedger {...props([snap(122, { ...clone(RECORD_122), source_turn: 3 })], 122)} />);
  expect(screen.getByText(/rejected as malformed/)).toBeInTheDocument();
  cleanup();
  render(<ResidenceLedger {...props([snap(121, clone(RECORD_121)), snap(122, { ...clone(RECORD_122), frame: null, events: null })], 122)} />);
  expect(screen.getByText(/in simulation turn 121 is unknown, not zero/)).toBeInTheDocument();
  expect(within(table(/recent snapshots to 122/)).getByText("not observed (unknown)")).toBeInTheDocument();
  cleanup();
  const zero = clone(RECORD_122) as Rec;
  for (const k of Object.keys(zero.frame.totals)) zero.frame.totals[k] = 0;
  zero.frame.regions = [];
  zero.events = [];
  render(<ResidenceLedger {...props([snap(122, zero)], 122)} />);
  expect(screen.getByText(/recorded, nothing happened this turn \(no one was displaced or attached/)).toBeInTheDocument();
});

it("the livelihoods tab mounts the panel on the run's records, also where a snapshot has none", () => {
  const history = [snap(121, clone(RECORD_121)), snap(122, undefined)];
  const p = { ...props(history, 189), onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...p} />);
  expect(screen.getByRole("region", { name: "Residence and displacement" })).toHaveTextContent(/unknown, not zero/);
  cleanup();
  const q = { ...props([snap(122, clone(RECORD_122))], 122), onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...q} />);
  expect(screen.queryByText(/names no package this viewer reads/)).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Residence and displacement · snapshot 122" })).toBeInTheDocument();
});
