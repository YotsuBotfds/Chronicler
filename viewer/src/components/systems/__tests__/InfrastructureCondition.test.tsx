import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import natural from "../../../__fixtures__/infrastructure_records.json";
import type { Bundle, TurnSnapshot } from "../../../types";
import { InfrastructureCondition } from "../InfrastructureCondition";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
afterEach(cleanup);

/** Natural records of a development world (template 11, repair mode); edited copies are labelled per case. */
const snapshots = natural.snapshots as unknown as TurnSnapshot[];
const rec = (s: TurnSnapshot) =>
  (s as unknown as { livelihoods: { infrastructure_condition: Record<string, unknown> } }).livelihoods.infrastructure_condition;
const bundle = {
  world_state: { regions: natural.regions.map((name) => ({ name })), civilizations: natural.civilizations.map((name) => ({ name })) },
  history: snapshots,
} as unknown as Bundle;
const props = (snapshot: TurnSnapshot | null, b: Bundle = bundle) =>
  ({ bundle: b, snapshot, currentTurn: snapshot?.turn ?? 1, onSelectRegion: vi.fn() });
const settled = snapshots.find((s) => Array.isArray(rec(s).receipts) && (rec(s).receipts as unknown[]).length > 0)!;
const last = snapshots[snapshots.length - 1];

it("shows each asset with its condition, applied service, status and a trace across the run", () => {
  const p = props(last);
  render(<InfrastructureCondition {...p} />);
  expect(screen.getByRole("heading", { name: `Infrastructure condition · snapshot ${last.turn}` })).toBeInTheDocument();
  const record = rec(last);
  const assets = within(screen.getByRole("table", { name: `Infrastructure assets at snapshot ${last.turn}` })).getAllByRole("row");
  expect(assets).toHaveLength((record.assets as unknown[]).length + (record.terminal as unknown[]).length + 1);
  expect(screen.getAllByRole("img", { name: /^Condition .* at turn \d+ to .* at turn \d+$/ }).length).toBeGreaterThan(0);
  fireEvent.click(within(assets[1]).getAllByRole("button")[0]);
  expect(p.onSelectRegion).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/Repair mode: works restore condition with anonymous, unpaid farm labour/)).toBeInTheDocument();
  expect(screen.getByText(/public-works sink that pays no one/)).toBeInTheDocument();
});

it("shows the works, this turn's receipts and charges, and the underfunded works story", () => {
  render(<InfrastructureCondition {...props(settled)} />);
  const works = within(screen.getByRole("table", { name: `Infrastructure works at snapshot ${settled.turn}` }));
  expect(works.getAllByRole("row").length).toBeGreaterThan(1);
  expect(screen.getByRole("heading", { name: "Underfunded public works" })).toBeInTheDocument();
  cleanup();
  render(<InfrastructureCondition {...props(last)} />);
  expect(screen.getByText(/^Directly recorded: work \d+ on /)).toBeInTheDocument();
  expect(screen.getByText(/stalled \d+ turns? \(/)).toBeInTheDocument();
});

it("lists damage with its cause, a flood with its event", () => {
  const s = structuredClone(last) as unknown as TurnSnapshot;
  const record = rec(s);
  const asset = (record.assets as Array<Record<string, unknown>>)[0];
  (record.damages as unknown[]).push({ did: 99, turn: last.turn - 1, aid: asset.aid, kind: asset.kind, region: asset.region,
    event: "flood", war_key: null, war_start_turn: null, ref: `flood:${asset.region}:${last.turn - 1}`, amount: 0.1,
    condition_before: 0.6, condition_after: 0.5, work: null });   // an edited copy: a flow flood's onset
  render(<InfrastructureCondition {...props(s)} />);
  const table = within(screen.getByRole("table", { name: `Infrastructure damage to snapshot ${last.turn}` }));
  expect(table.getByText(/Flood \(watershed flow, at its onset\) \(event flood:/)).toBeInTheDocument();
  expect(screen.getByRole("row", { name: /Damage events: conquest \/ sack \/ flood/ })).toBeInTheDocument();
});

it("shows the timber the works asked of the woodcutters after RS2, only when PL1 planned it", () => {
  const s = structuredClone(last) as unknown as TurnSnapshot;
  Object.assign(rec(s), { timber_needs: [{ region: 0, civ: 0, works: [4], want: 1, rs2_want: 4, free: 3, in_transit: 0,
    gap: 1, status: "refused", reason: "forest_busy", eid: null }], timber_needs_dropped: 0 });
  render(<InfrastructureCondition {...props(s)} />);
  const table = within(screen.getByRole("table", { name: `Works timber need at snapshot ${last.turn}` }));
  expect(table.getByText("No woodcutters: forest busy")).toBeInTheDocument();
  expect(screen.getByText(/only after every RS2 need of the turn/)).toBeInTheDocument();
  cleanup();
  render(<InfrastructureCondition {...props(last)} />);
  expect(screen.queryByRole("table", { name: `Works timber need at snapshot ${last.turn}` })).toBeNull();
});

it("keeps disabled, absent, unsettled and malformed records distinct", () => {
  const bare = { turn: 4 } as unknown as TurnSnapshot;
  const off = { ...bundle, history: [bare] } as unknown as Bundle;
  render(<InfrastructureCondition {...props(bare, off)} />);
  expect(screen.getByText(/off in this run/)).toBeInTheDocument();
  cleanup();
  render(<InfrastructureCondition {...props(bare)} />);
  expect(screen.getByText(/No infrastructure record at snapshot 4, although the run records it elsewhere/)).toBeInTheDocument();
  cleanup();
  const unsettled = structuredClone(settled) as unknown as TurnSnapshot;
  Object.assign(rec(unsettled), { receipts: null, ledger: null, unmet: null, shared: null });
  render(<InfrastructureCondition {...props(unsettled)} />);
  expect(screen.getByText(/No Phase 2 was settled in simulation turn/)).toBeInTheDocument();
  cleanup();
  const bad = structuredClone(settled) as unknown as TurnSnapshot;
  rec(bad).stage = "B9";
  render(<InfrastructureCondition {...props(bad)} />);
  expect(screen.getByText(/is malformed \(unknown infrastructure schema\)/)).toBeInTheDocument();
});

it("mounts in the livelihoods panel whenever the run records it", () => {
  const extra = { onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...props(last)} {...extra} />);
  expect(screen.getByRole("region", { name: "Infrastructure condition" })).toBeInTheDocument();
});
