import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { Bundle } from "../../../types";
import { FoodAllocation } from "../FoodAllocation";
import { GranaryStorage } from "../GranaryStorage";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { Remittances } from "../Remittances";
import { RepairProjects } from "../RepairProjects";
import { TimberStock } from "../TimberStock";
import { chainBundle, snapshotOf, without } from "../../../lib/__tests__/recoveryChainFixture";
afterEach(cleanup);

/**
 * RL8 in the panels: each of the four unpinned livelihoods panels says which of
 * off, absent, malformed, recorded-zero or recorded it is looking at. Natural
 * records of template seed 23; every other case is a labelled constructed edit.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
type Rec = Record<string, any>;
const AT = 20;
const zeroTotals = (totals: Rec) => Object.fromEntries(Object.keys(totals).map((k) => [k, 0]));

const PANELS = [
  { key: "repair_projects", Panel: RepairProjects, region: "Repair projects", label: "Repair projects",
    heading: /^Repair projects · snapshot 20$/,
    zero: (r: Rec) => { r.projects = []; r.receipts = []; r.ledger = []; r.unmet = []; } },
  { key: "timber_stock", Panel: TimberStock, region: "Timber stock", label: "Timber stock",
    heading: /^Timber stock · snapshot 20$/,
    zero: (r: Rec) => { r.regions = []; r.totals = { ...zeroTotals(r.totals), slots: 0, capped_slots: 0 }; } },
  { key: "remittances", Panel: Remittances, region: "Remittances", label: "Remittances",
    heading: /^Remittances and diaspora · snapshot 20$/,
    zero: (r: Rec) => {
      r.totals = zeroTotals(r.totals); r.regions = []; r.moves = []; r.closures = []; r.receipts = []; r.unmet = [];
    } },
  { key: "food_allocation", Panel: FoodAllocation, region: "Food allocation", label: "Food allocation",
    heading: /^Food allocation · snapshot 20$/,
    zero: (r: Rec) => { r.totals = zeroTotals(r.totals); r.regions = []; r.sample = []; } },
];

function view(Panel: typeof RepairProjects, bundle: Bundle) {
  render(<Panel bundle={bundle} snapshot={snapshotOf(bundle, AT)} currentTurn={AT} onSelectRegion={vi.fn()} />);
}

describe.each(PANELS)("$label panel", ({ key, Panel, region, label, heading, zero }) => {
  it("says the package is off in this run", () => {
    view(Panel, chainBundle(without(key)));
    const section = within(screen.getByRole("region", { name: region }));
    expect(section.getByText(`${label}: off in this run (--${key.replace(/_/g, "-")} is not recorded in any snapshot).`)).toBeInTheDocument();
    expect(section.queryByRole("table")).not.toBeInTheDocument();
  });

  it("says an absent record at this snapshot is unknown, not zero (constructed: removed at snapshot 20)", () => {
    view(Panel, chainBundle((s) => { if (s.turn === AT) delete s.livelihoods[key]; }));
    expect(screen.getByText(`${label}: on in this run, but snapshot 20 has no record; unknown, not zero.`)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("says a malformed record was rejected (constructed: misdated at snapshot 20)", () => {
    view(Panel, chainBundle((s) => { if (s.turn === AT) s.livelihoods[key].source_turn = 99; }));
    expect(screen.getByText(new RegExp(`^${label}: the record at snapshot 20 was rejected as malformed`))).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows a recorded zero as recorded (constructed: nothing happened at snapshot 20)", () => {
    view(Panel, chainBundle((s) => { if (s.turn === AT) zero(s.livelihoods[key]); }));
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`^${label}: recorded, nothing happened this turn`))).toBeInTheDocument();
    expect(screen.queryByText(/unknown, not zero/)).not.toBeInTheDocument();
  });

  it("shows a natural record without a state note", () => {
    view(Panel, chainBundle());
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(`^${label}: `))).not.toBeInTheDocument();
  });
});

describe("the livelihoods panel mounts these panels from the run's records", () => {
  const panel = (bundle: Bundle) => render(<LivelihoodsPanel bundle={bundle} snapshot={snapshotOf(bundle, AT)} currentTurn={AT}
    onSelectRegion={vi.fn()} onSeek={vi.fn()} onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />);

  it("keeps a panel whose record is absent at this snapshot, saying so (constructed)", () => {
    panel(chainBundle((s) => { if (s.turn === AT) { delete s.livelihoods.timber_stock; delete s.livelihoods.remittances; } }));
    expect(within(screen.getByRole("region", { name: "Timber stock" }))
      .getByText("Timber stock: on in this run, but snapshot 20 has no record; unknown, not zero.")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Remittances" }))
      .getByText(/^Remittances: on in this run, but snapshot 20 has no record/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^Food allocation · snapshot 20$/ })).toBeInTheDocument();
  });

  it("does not mount the panel of a package that is off in the run (constructed)", () => {
    panel(chainBundle(without("remittances")));
    expect(screen.queryByRole("region", { name: "Remittances" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Timber stock" })).toBeInTheDocument();
  });

  it("mounts nothing from an unreadable livelihoods record (constructed)", () => {
    panel(chainBundle((s) => { if (s.turn === AT) s.livelihoods.schema_version = 2; }));
    expect(screen.getByText(/The livelihoods record at snapshot 20 is unreadable/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Timber stock" })).not.toBeInTheDocument();
  });
});

describe("granary storage panel", () => {
  const show = (bundle: Bundle) => render(<GranaryStorage bundle={bundle} snapshot={snapshotOf(bundle, AT)} region={null} />);
  const region = () => within(screen.getByRole("region", { name: "Granary storage assets" }));
  const edit = (change: (storage: Rec) => void) => chainBundle((s) => { if (s.turn === AT) change(s.grain_reserves.storage); });

  it("says storage is off in this run (constructed: removed from every snapshot)", () => {
    show(chainBundle(without("grain_storage")));
    expect(region().getByText("Granary storage: off in this run (--grain-storage is not recorded in any snapshot).")).toBeInTheDocument();
    expect(region().queryByRole("table")).not.toBeInTheDocument();
  });

  it("says an absent frame is unknown, not zero (constructed: removed at snapshot 20)", () => {
    show(chainBundle((s) => { if (s.turn === AT) delete s.grain_reserves.storage; }));
    expect(region().getByText("Granary storage: on in this run, but snapshot 20 has no record; unknown, not zero.")).toBeInTheDocument();
  });

  it("says a malformed frame was rejected (constructed: misdated at snapshot 20)", () => {
    show(edit((storage) => { storage.receipt_turn = 99; }));
    expect(region().getByText(/^Granary storage: the record at snapshot 20 was rejected as malformed/)).toBeInTheDocument();
    expect(region().queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows a recorded zero as recorded (constructed: no storage receipt at snapshot 20)", () => {
    show(edit((storage) => { storage.receipts = []; }));
    expect(screen.getByRole("heading", { name: "Storage assets · snapshot 20" })).toBeInTheDocument();
    expect(region().getByText(/^Granary storage: recorded, nothing happened this turn/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Storage work at snapshot 20" })).toBeInTheDocument();
  });

  it("shows recorded work without a state note (constructed: one receipt delivers work)", () => {
    show(edit((storage) => { storage.receipts[0] = { ...storage.receipts[0], requested: 1, delivered: 1 }; }));
    expect(screen.getByRole("heading", { name: "Storage assets · snapshot 20" })).toBeInTheDocument();
    expect(region().queryByText(/^Granary storage: /)).not.toBeInTheDocument();
  });
});
