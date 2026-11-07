import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import natural from "../../../__fixtures__/watershed_records.json";
import type { Bundle, TurnSnapshot } from "../../../types";
import { Watershed } from "../Watershed";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
afterEach(cleanup);

/** Natural records of a development world (procedural 11, record only); edited copies are labelled per case. */
const snapshots = natural.snapshots as unknown as TurnSnapshot[];
const at = (turn: number) => structuredClone(snapshots.find((s) => s.turn === turn)!) as unknown as TurnSnapshot;
const bundle = { world_state: { regions: natural.regions.map((name) => ({ name })) }, history: snapshots } as unknown as Bundle;
const props = (snapshot: TurnSnapshot | null, b: Bundle = bundle) =>
  ({ bundle: b, snapshot, currentTurn: snapshot?.turn ?? 7, onSelectRegion: vi.fn() });

it("shows the turn's account, each region's indices, a flood with its causes and the cumulative closure", () => {
  const p = props(at(1));
  render(<Watershed {...p} />);
  expect(screen.getByRole("heading", { name: "Watershed account · snapshot 1" })).toBeInTheDocument();
  expect(screen.getByText(/Record only: a conserved water account/)).toBeInTheDocument();
  expect(screen.getByText(/climate phase temperate/)).toBeInTheDocument();
  const account = within(screen.getByRole("table", { name: "Water account at snapshot 1" }));
  expect(account.getByRole("row", { name: /Outflow to the sea/ })).toBeInTheDocument();
  expect(account.getByRole("row", { name: /Closure residual/ })).toHaveTextContent(/e-/);
  const rows = within(screen.getByRole("table", { name: "Watershed regions at snapshot 1" })).getAllByRole("row");
  expect(rows).toHaveLength(natural.regions.length + 1);
  expect(rows[1]).toHaveTextContent(natural.regions[0]);
  // A difference below display precision reads 0, never -0 (Viskiros Icefields at snapshot 1).
  expect(rows.some((row) => within(row).queryAllByRole("cell").some((cell) => cell.textContent === "-0"))).toBe(false);
  const floods = within(screen.getByRole("table", { name: "Floods at snapshot 1" })).getAllByRole("row");
  expect(floods).toHaveLength(2);
  expect(screen.getByText(/No region is in a declared drought this turn \(recorded: none\)/)).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Water account since turn 0" }))
    .getByRole("row", { name: /Storage, opening → now/ })).toBeInTheDocument();
  fireEvent.click(within(screen.getByRole("table", { name: "Watershed regions at snapshot 1" })).getAllByRole("button")[2]);
  expect(p.onSelectRegion).toHaveBeenCalledWith(natural.regions[2]);
});

it("lists declared, open and ended droughts with the conditions behind them", () => {
  const first = render(<Watershed {...props(at(37))} />);
  expect(within(screen.getByRole("table", { name: "Droughts at snapshot 37" })).getByText("Declared this turn")).toBeInTheDocument();
  first.unmount();
  render(<Watershed {...props(at(42))} />);
  const table = within(screen.getByRole("table", { name: "Droughts at snapshot 42" }));
  expect(table.getByText(/Ended at turn 41/)).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Open droughts at snapshot 42" })).getAllByRole("row").length).toBeGreaterThan(1);
  expect(screen.getByText(/recorded in full in the snapshot of the turn it was declared/)).toBeInTheDocument();
  expect(screen.getByText(/No region's arrivals exceeded its channel this turn \(recorded: no flood\)/)).toBeInTheDocument();
});

it("attributes external inflow by recorded source and flags a stale baseline", () => {
  const first = render(<Watershed {...props(at(1))} />);
  const flows = within(screen.getByRole("table", { name: "External flows at snapshot 1" }));
  expect(flows.getByText("coastal flood")).toBeInTheDocument();
  expect(screen.queryByText(/Stale baseline/)).toBeNull();
  expect(screen.getByText(/closure holds by construction/)).toBeInTheDocument();
  first.unmount();
  const stale = at(60);
  (stale as unknown as { livelihoods: { watershed: { stale_baseline: boolean } } }).livelihoods.watershed.stale_baseline = true;
  render(<Watershed {...props(stale)} />);
  expect(screen.getByText(/Stale baseline: the index was not observed after the previous tick/)).toBeInTheDocument();
});

it("keeps disabled, absent, malformed and unobserved apart", () => {
  const none = { turn: 9, livelihoods: { schema_version: 1 } } as unknown as TurnSnapshot;
  const offBundle = { world_state: bundle.world_state, history: [none] } as unknown as Bundle;
  const { unmount } = render(<Watershed {...props(none, offBundle)} />);
  expect(screen.getByText(/off in this run \(--watershed not recorded\)/)).toBeInTheDocument();
  unmount();
  const second = render(<Watershed {...props(none)} />);
  expect(screen.getByText(/No watershed record at snapshot 9, although the run records it elsewhere/)).toBeInTheDocument();
  second.unmount();
  const broken = at(60);
  (broken as unknown as { livelihoods: { watershed: { stage: string } } }).livelihoods.watershed.stage = "B9";
  const third = render(<Watershed {...props(broken)} />);
  expect(screen.getByText(/malformed \(unknown watershed schema\); nothing is shown from it/)).toBeInTheDocument();
  third.unmount();
  const unobserved = at(60);
  const w = (unobserved as unknown as { livelihoods: { watershed: { regions: { storage: number[] } } } }).livelihoods.watershed;
  Object.assign(w, { observed: false, phase: null, stale_baseline: null, storage: w.regions.storage, regions: null,
    floods: null, droughts: null, external: null, totals: null });
  render(<Watershed {...props(unobserved)} />);
  expect(screen.getByText(/flows, floods and droughts are unknown, not zero/)).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: "Watershed regions at snapshot 60" })).toBeNull();
  expect(screen.getByRole("table", { name: "Water account since turn 0" })).toBeInTheDocument();
});

it("mounts in the livelihoods panel without unrelated polity metadata when the run records only regional accounts", () => {
  expect(bundle.world_state).not.toHaveProperty("civilizations");
  const none = { turn: 9, livelihoods: { schema_version: 1 } } as unknown as TurnSnapshot;
  const extra = { onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel bundle={bundle} snapshot={none} currentTurn={9} onSelectRegion={vi.fn()} {...extra} />);
  expect(screen.getByRole("region", { name: "Watershed" })).toBeInTheDocument();
  cleanup();
  render(<LivelihoodsPanel bundle={bundle} snapshot={at(60)} currentTurn={60} onSelectRegion={vi.fn()} {...extra} />);
  expect(screen.queryByText(/names no package this viewer reads/)).toBeNull();
});

it("reads a resumed history that does not begin at the opening turn (review N2)", () => {
  const segments = natural.segments as unknown as { regions: string[]; resumed: TurnSnapshot[] };
  const resumed = { world_state: { regions: segments.regions.map((name) => ({ name })) }, history: segments.resumed } as unknown as Bundle;
  render(<Watershed {...props(segments.resumed[0], resumed)} />);
  expect(screen.getByRole("heading", { name: "Watershed account · snapshot 21" })).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Watershed regions at snapshot 21" })).toBeInTheDocument();
  expect(screen.queryByText(/malformed/)).toBeNull();
});

import b2 from "../../../__fixtures__/watershed_b2_records.json";

type Rec = { floods?: Array<{ consequence?: unknown; withheld_by?: unknown }>; superseded?: unknown[];
  cap_changes?: unknown[]; flood_events?: { ended: unknown[] } };
const rec = (s: TurnSnapshot) => (s as unknown as { livelihoods: { watershed: Rec } }).livelihoods.watershed;

it("shows flow mode: the index used is the derived one, flood events and what they did, superseded floods and cap changes", () => {
  const flow = b2.flow as unknown as TurnSnapshot[];
  const b = { world_state: { regions: b2.regions.map((name) => ({ name })) }, history: flow } as unknown as Bundle;
  const sup = flow.find((s) => (rec(s).superseded ?? []).length > 0)!;
  const first = render(<Watershed {...props(sup, b)} />);
  expect(screen.getByText(/Flow: the account's derived index is the water index the simulation used/)).toBeInTheDocument();
  expect(screen.getByRole("table", { name: `Superseded river floods at snapshot ${sup.turn}` })).toBeInTheDocument();
  expect(screen.getByRole("row", { name: /River floods superseded \(flow\)/ })).toBeInTheDocument();
  first.unmount();
  const onset = flow.find((s) => (rec(s).floods ?? []).some((f) => f.consequence))!;
  const second = render(<Watershed {...props(onset, b)} />);
  const floods = within(screen.getByRole("table", { name: `Flood events started at snapshot ${onset.turn}` }));
  expect(floods.getAllByText(/capacity ×0.85; cooldown \d turns/).length).toBeGreaterThan(0);
  expect(screen.getByRole("table", { name: `Flood events at snapshot ${onset.turn}` })).toBeInTheDocument();
  expect(screen.getByText(/acts once, at its start, unless the region already holds a disaster cooldown/)).toBeInTheDocument();
  second.unmount();
  const capped = flow.find((s) => (rec(s).cap_changes ?? []).length > 0)!;
  const third = render(<Watershed {...props(capped, b)} />);
  const changes = within(screen.getByRole("table", { name: `Terrain cap changes at snapshot ${capped.turn}` }));
  expect(changes.getByText("forest → plains")).toBeInTheDocument();
  expect(changes.getByText("0.8 → 0.7")).toBeInTheDocument();
  third.unmount();
  const ended = flow.find((s) => (rec(s).flood_events?.ended ?? []).length > 0)!;
  render(<Watershed {...props(ended, b)} />);
  expect(within(screen.getByRole("table", { name: `Flood events at snapshot ${ended.turn}` })).getAllByText(/Ended at turn/).length).toBeGreaterThan(0);
});

it("shows a withheld flood and a B2 record-only history", () => {
  const flow = structuredClone(b2.flow) as unknown as TurnSnapshot[];
  const onset = flow.find((s) => (rec(s).floods ?? []).some((f) => f.consequence))!;
  const flood = rec(onset).floods!.find((f) => f.consequence)!;
  delete flood.consequence;
  flood.withheld_by = ["flood"];                                  // edited copy: a coastal flood's cooldown at onset
  const b = { world_state: { regions: b2.regions.map((name) => ({ name })) }, history: flow } as unknown as Bundle;
  const first = render(<Watershed {...props(onset, b)} />);
  expect(screen.getByText("withheld: the region held a flood cooldown")).toBeInTheDocument();
  first.unmount();
  const ro = b2.record_only as unknown as TurnSnapshot[];
  const rb = { world_state: { regions: b2.regions.map((name) => ({ name })) }, history: ro } as unknown as Bundle;
  render(<Watershed {...props(ro[ro.length - 1], rb)} />);
  expect(screen.getByText(/Record only: a conserved water account/)).toBeInTheDocument();
  expect(screen.queryByText(/malformed/)).toBeNull();
  expect(screen.queryByText(/What it did/)).toBeNull();
});
