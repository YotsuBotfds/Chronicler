import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { ResidenceLedger } from "../ResidenceLedger";
import { RECORD_188, RECORD_189, REGION_NAMES } from "../../../lib/__tests__/residenceLedgerFixture";
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
  const p = props([snap(188, clone(RECORD_188)), snap(189, clone(RECORD_189))], 189);
  render(<ResidenceLedger {...p} />);
  expect(screen.getByRole("heading", { name: "Residence and displacement · snapshot 189" })).toBeInTheDocument();
  expect(screen.getByText(/120 of 557 people observed are displaced \(21.5%\): 111 fled, 9 left hungry/)).toBeInTheDocument();
  expect(screen.getByText(/war 0, famine 35, persecution 10, no event 75/)).toBeInTheDocument();
  expect(screen.getByText(/This turn: 29 moves \(9 flight, 0 hunger, 7 voluntary, 13 other\); 4 spell\(s\) opened; 4 returned home/)).toBeInTheDocument();
  const spells = within(table(/Open displacement spells at snapshot 189/)).getAllByRole("row");
  expect(spells.length).toBeGreaterThan(5);
  const flows = table(/Movement and spells at snapshot 189/);
  const rows = RECORD_189.frame.regions as Rec[];
  const busiest = rows.reduce((a, r) => (r.departures > a.departures ? r : a));
  const row = within(flows).getByRole("row", { name: new RegExp(REGION_NAMES[busiest.region]) });
  expect(row).toHaveTextContent(String(busiest.departures));
  const awayRows = (RECORD_189.frame.regions as Rec[]).filter((r) => r.attached_away > 0);
  const army = within(table(/Away from home at snapshot 189/)).getByRole("row", { name: new RegExp(REGION_NAMES[awayRows[0].region]) });
  expect(army).toHaveTextContent(`${awayRows[0].attached}${awayRows[0].attached_away}${awayRows[0].in_transit}`);
  expect(awayRows.reduce((a, r) => a + r.attached_away, 0)).toBe(7);
  expect(screen.getByText(/For comparison only/)).toHaveTextContent("62.1%");       // 346 of 557 outside their birth region
  expect(table(/recent snapshots to 189/)).toBeInTheDocument();
  fireEvent.click(within(flows).getAllByRole("button")[0]);
  expect(p.onSelectRegion).toHaveBeenCalled();
});

it("keeps disabled, absent, malformed, unobserved and recorded-zero readings apart", () => {
  render(<ResidenceLedger {...props([snap(189, undefined)], 189)} />);
  expect(screen.getByText(/off in this run \(--residence-ledger is not recorded in any snapshot\)/)).toBeInTheDocument();
  cleanup();
  render(<ResidenceLedger {...props([snap(188, clone(RECORD_188)), snap(189, undefined)], 189)} />);
  expect(screen.getByText(/on in this run, but snapshot 189 has no record; unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<ResidenceLedger {...props([snap(189, { ...clone(RECORD_189), source_turn: 3 })], 189)} />);
  expect(screen.getByText(/rejected as malformed/)).toBeInTheDocument();
  cleanup();
  render(<ResidenceLedger {...props([snap(188, clone(RECORD_188)), snap(189, { ...clone(RECORD_189), frame: null, events: null })], 189)} />);
  expect(screen.getByText(/in simulation turn 188 is unknown, not zero/)).toBeInTheDocument();
  expect(within(table(/recent snapshots to 189/)).getByText("not observed (unknown)")).toBeInTheDocument();
  cleanup();
  const zero = clone(RECORD_189) as Rec;
  for (const k of Object.keys(zero.frame.totals)) zero.frame.totals[k] = 0;
  zero.frame.regions = [];
  zero.events = [];
  render(<ResidenceLedger {...props([snap(189, zero)], 189)} />);
  expect(screen.getByText(/recorded, nothing happened this turn \(no one was displaced or attached/)).toBeInTheDocument();
});

it("the livelihoods tab mounts the panel on the run's records, also where a snapshot has none", () => {
  const history = [snap(188, clone(RECORD_188)), snap(189, undefined)];
  const p = { ...props(history, 189), onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...p} />);
  expect(screen.getByRole("region", { name: "Residence and displacement" })).toHaveTextContent(/unknown, not zero/);
  cleanup();
  const q = { ...props([snap(189, clone(RECORD_189))], 189), onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...q} />);
  expect(screen.queryByText(/names no package this viewer reads/)).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Residence and displacement · snapshot 189" })).toBeInTheDocument();
});
