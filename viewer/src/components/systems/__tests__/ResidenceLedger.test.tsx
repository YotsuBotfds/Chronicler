import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { ResidenceLedger } from "../ResidenceLedger";
import { RECORD_189, RECORD_190, REGION_NAMES } from "../../../lib/__tests__/residenceLedgerFixture";
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
  const p = props([snap(189, clone(RECORD_189)), snap(190, clone(RECORD_190))], 190);
  render(<ResidenceLedger {...p} />);
  expect(screen.getByRole("heading", { name: "Residence and displacement · snapshot 190" })).toBeInTheDocument();
  expect(screen.getByText(/165 of 561 people observed are displaced \(29.4%\): 154 fled, 11 left hungry/)).toBeInTheDocument();
  expect(screen.getByText(/war 0, famine 60, persecution 28, no event 77/)).toBeInTheDocument();
  expect(screen.getByText(/This turn: 41 moves \(7 flight, 1 hunger, 31 voluntary, 2 other\); 4 spell\(s\) opened; 4 returned home/)).toBeInTheDocument();
  const spells = within(table(/Open displacement spells at snapshot 190/)).getAllByRole("row");
  expect(spells.length).toBeGreaterThan(5);
  const flows = table(/Movement and spells at snapshot 190/);
  const rows = RECORD_190.frame.regions as Rec[];
  const busiest = rows.reduce((a, r) => (r.departures > a.departures ? r : a));
  const row = within(flows).getByRole("row", { name: new RegExp(REGION_NAMES[busiest.region]) });
  expect(row).toHaveTextContent(String(busiest.departures));
  const awayRows = (RECORD_190.frame.regions as Rec[]).filter((r) => r.attached_away > 0);
  const army = within(table(/Away from home at snapshot 190/)).getByRole("row", { name: new RegExp(REGION_NAMES[awayRows[0].region]) });
  expect(army).toHaveTextContent(`${awayRows[0].attached}${awayRows[0].attached_away}${awayRows[0].in_transit}`);
  expect(awayRows.reduce((a, r) => a + r.attached_away, 0)).toBe(7);
  expect(screen.getByText(/For comparison only/)).toHaveTextContent("62.4%");       // 350 of 561 outside their birth region
  expect(table(/recent snapshots to 190/)).toBeInTheDocument();
  fireEvent.click(within(flows).getAllByRole("button")[0]);
  expect(p.onSelectRegion).toHaveBeenCalled();
});

it("keeps disabled, absent, malformed, unobserved and recorded-zero readings apart", () => {
  render(<ResidenceLedger {...props([snap(190, undefined)], 190)} />);
  expect(screen.getByText(/off in this run \(--residence-ledger is not recorded in any snapshot\)/)).toBeInTheDocument();
  cleanup();
  render(<ResidenceLedger {...props([snap(189, clone(RECORD_189)), snap(190, undefined)], 190)} />);
  expect(screen.getByText(/on in this run, but snapshot 190 has no record; unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<ResidenceLedger {...props([snap(190, { ...clone(RECORD_190), source_turn: 3 })], 190)} />);
  expect(screen.getByText(/rejected as malformed/)).toBeInTheDocument();
  cleanup();
  render(<ResidenceLedger {...props([snap(189, clone(RECORD_189)), snap(190, { ...clone(RECORD_190), frame: null, events: null })], 190)} />);
  expect(screen.getByText(/in simulation turn 189 is unknown, not zero/)).toBeInTheDocument();
  expect(within(table(/recent snapshots to 190/)).getByText("not observed (unknown)")).toBeInTheDocument();
  cleanup();
  const zero = clone(RECORD_190) as Rec;
  for (const k of Object.keys(zero.frame.totals)) zero.frame.totals[k] = 0;
  zero.frame.regions = [];
  zero.events = [];
  render(<ResidenceLedger {...props([snap(190, zero)], 190)} />);
  expect(screen.getByText(/recorded, nothing happened this turn \(no one was displaced or attached/)).toBeInTheDocument();
});

it("the livelihoods tab mounts the panel on the run's records, also where a snapshot has none", () => {
  const history = [snap(189, clone(RECORD_189)), snap(190, undefined)];
  const p = { ...props(history, 189), onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...p} />);
  expect(screen.getByRole("region", { name: "Residence and displacement" })).toHaveTextContent(/unknown, not zero/);
  cleanup();
  const q = { ...props([snap(190, clone(RECORD_190))], 190), onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...q} />);
  expect(screen.queryByText(/names no package this viewer reads/)).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Residence and displacement · snapshot 190" })).toBeInTheDocument();
});
