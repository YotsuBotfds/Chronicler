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
  expect(screen.getByText(/Repair mode: works funded inside RS2's repairs budget/)).toBeInTheDocument();
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
