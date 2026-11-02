import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, SeatRecord, TurnSnapshot } from "../../../types";
import type { LearningServicesSnapshot } from "../../../learningServicesTypes";
import { AcademyServices } from "../AcademyServices";
import { LearningPanel } from "../LearningPanel";
import learningFixture from "../../../__fixtures__/learning_bundle.json";
import { learningServicesAt } from "../../../lib/learningServices";
afterEach(cleanup);
const seat = { region: 0, kind: 0, name: "Academy", founded_turn: 1, founder: 0, level: 1,
  peak_level: 1, peak_scholars: 0, fallen_turn: null, fall_cause: -1, refuge: -1, history: [] } as SeatRecord;
const id = { seat_id: 0, region: 0, founder: 0, founded_turn: 1, seat_name: "Academy" };
/** Constructed contract fixture; not a native simulation observation. */
function data(source = 4): LearningServicesSnapshot {
  return { schema_version: 1, captured_turn: source + 1, enabled: true, active: true,
    inventories: [{ ...id, held: 5, purchased_total: 12, used_total: 7, lost_total: 0, retired: false,
      upkeep_source_turn: source, upkeep_lord: 0, upkeep_due: 0, upkeep_amount_paid: 0, upkeep_satisfied: true }],
    procurement_receipts: [{ ...id, lord: 0, source_turn: source, upkeep_source_turn: source, upkeep_due: 0,
      upkeep_amount_paid: 0, upkeep_satisfied: true, scholar_upper_bound: 3, learner_upper_bound: 16, craft_price: 1,
      market_stock: 20, market_commitments: 2, budget_before: 10, held_before: 2, purchased: 3, paid: 3,
      held_after: 5, shortfalls: ["commitments_unknown"] }],
    teaching_receipts: [{ ...id, lord: 0, source_turn: source, available_turn: source + 1,
      learner_upper_bound: 16, scholar_upper_bound: 3, upkeep_source_turn: source - 1, upkeep_lord: 0,
      upkeep_due: 1, upkeep_amount_paid: 1, upkeep_satisfied: true, upkeep_applies: true,
      held_before: 10, work_requested: 2, work_available: 1.5, work_reserved: 1, work_delivered: .5,
      learners_delivered: 4, crafts_used: 4, held_after: 6, native_dropped: 0 }],
    supply_losses: [{ ...id, source_turn: source, held_before: 8, lost: 2, held_after: 6, reason: "seat_destroyed_or_replaced" }],
    totals: { held: 5, purchased: 12, used: 7, lost: 0 } };
}
function setup() {
  const snap = { turn: 5, scholarship: { seats: [], fallen: 0, counters: {}, learning_services: data() } } as unknown as TurnSnapshot;
  const bundle = { world_state: { regions: [{ name: "Valley" }], civilizations: [{ name: "Realm" }], scholarship: { seats: [seat] } }, history: [snap] } as unknown as Bundle;
  return { bundle, snapshot: snap, seatId: 0, seat, currentTurn: 5, onSeek: vi.fn(), onSelectRegion: vi.fn(), onSelectCivilization: vi.fn() };
}
it("separates paid acquisition, actual work and loss with dated identities and navigation", () => {
  const p = setup(); render(<AcademyServices {...p} />);
  expect(screen.getByText(/Purchased 3 crafts · Treasury paid 3/)).toBeInTheDocument();
  expect(screen.getByText(/Work requested 2 · Available 1.5 · Reserved 1 · Delivered 0.5 scholar-days/)).toBeInTheDocument();
  expect(screen.getByText(/Delivered 4 learner-equivalents · Crafts used 4/)).toBeInTheDocument();
  expect(screen.getByText(/Zero due and zero paid are no cash payment/)).toBeInTheDocument();
  expect(screen.getByText(/not available work or observed enrollment/)).toBeInTheDocument();
  expect(screen.getByText(/lost 2, held after 6/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Valley" })); expect(p.onSelectRegion).toHaveBeenCalledWith("Valley");
  fireEvent.click(screen.getByRole("button", { name: "Realm" })); expect(p.onSelectCivilization).toHaveBeenCalledWith("Realm");
  fireEvent.click(within(screen.getByRole("table", { name: "Academy service history through snapshot 5" })).getByRole("button", { name: "5" }));
  expect(p.onSeek).toHaveBeenCalledWith(5);
});
it("retains paused dates and unknown values without showing them as current work", () => {
  const p = setup(), f = p.snapshot.scholarship!.learning_services!;
  f.active = false; f.enabled = false; f.procurement_receipts![0].source_turn = 3; f.procurement_receipts![0].upkeep_source_turn = 3;
  f.teaching_receipts![0].source_turn = 3; f.teaching_receipts![0].available_turn = 4; f.teaching_receipts![0].upkeep_source_turn = 2;
  f.teaching_receipts![0].work_delivered = null; f.teaching_receipts![0].learners_delivered = null;
  f.inventories![0].held = null;
  render(<AcademyServices {...p} />);
  expect(screen.getByText(/paused or unavailable in this mode/)).toBeInTheDocument();
  expect(screen.getByText(/Last retained record · Phase 10, simulation turn 3/)).toBeInTheDocument();
  expect(screen.getByText(/Held now: Not observed/)).toBeInTheDocument();
  expect(screen.getByText(/actual delivery is not observed/)).toBeInTheDocument();
});
it("does not attach a replacement seat, future, stale or malformed observations", () => {
  const p = setup(); const f = p.snapshot.scholarship!.learning_services!;
  expect(learningServicesAt(p.snapshot, 0, seat, 1, 1, 1)?.teaching).not.toBeNull();
  const replacement = { ...seat, founded_turn: 2 };
  expect(learningServicesAt(p.snapshot, 0, replacement, 1, 1, 1)?.inventory).toBeNull();
  f.teaching_receipts![0].source_turn = 5;
  expect(learningServicesAt(p.snapshot, 0, seat, 1, 1, 1)?.teaching).toBeNull();
  f.teaching_receipts![0].source_turn = 3; f.teaching_receipts![0].available_turn = 4; f.teaching_receipts![0].upkeep_source_turn = 2;
  expect(learningServicesAt(p.snapshot, 0, seat, 1, 1, 1)?.teaching).toBeNull();
  f.procurement_receipts![0].paid = NaN;
  expect(learningServicesAt(p.snapshot, 0, seat, 1, 1, 1)?.procurement).toBeNull();
  f.captured_turn = 4; // source turn is not the completed capture turn
  expect(learningServicesAt(p.snapshot, 0, seat, 1, 1, 1)).toBeNull();
  f.captured_turn = 6; // future capture
  expect(learningServicesAt(p.snapshot, 0, seat, 1, 1, 1)).toBeNull();
  render(<AcademyServices {...p} />);
  expect(screen.getByText(/not observed or unavailable for this seat/)).toBeInTheDocument();
});
it("bounds historical snapshots and resets the page after seeking", () => {
  const p = setup(); p.bundle.history = Array.from({ length: 13 }, (_, i) => ({ turn: i + 2,
    scholarship: { seats: [], fallen: 0, counters: {}, learning_services: data(i + 1) } } as unknown as TurnSnapshot));
  p.snapshot = p.bundle.history[12]; p.currentTurn = 14;
  const view = render(<AcademyServices {...p} />);
  const table = screen.getByRole("table", { name: "Academy service history through snapshot 14" });
  expect(within(table).getAllByRole("row")).toHaveLength(9);
  const scroll = screen.getByRole("region", { name: "Scroll academy service history" });
  expect(scroll).toHaveAttribute("tabindex", "0");
  scroll.focus();
  expect(scroll).toHaveFocus();
  expect(within(table).getAllByRole("row")[1].querySelectorAll("td")[1]).toHaveStyle({ whiteSpace: "nowrap" });
  fireEvent.click(screen.getByRole("button", { name: "Show more service snapshots (5 remaining)" }));
  expect(within(table).getAllByRole("row")).toHaveLength(14);
  view.rerender(<AcademyServices {...p} snapshot={p.bundle.history[11]} currentTurn={13} />);
  expect(within(screen.getByRole("table", { name: "Academy service history through snapshot 13" })).getAllByRole("row")).toHaveLength(9);
  view.rerender(<AcademyServices {...p} />);
  expect(within(screen.getByRole("table", { name: "Academy service history through snapshot 14" })).getAllByRole("row")).toHaveLength(9);
});

it("mounts inside the existing selected-seat history", () => {
  const bundle = structuredClone(learningFixture) as unknown as Bundle;
  const snapshot = bundle.history.find((row) => row.turn === 106)!;
  const chosen = bundle.world_state.scholarship!.seats![0];
  const f = data(105);
  for (const rows of [f.inventories!, f.procurement_receipts!, f.teaching_receipts!, f.supply_losses!]) {
    for (const row of rows) Object.assign(row, { region: chosen.region, founder: chosen.founder, founded_turn: chosen.founded_turn, seat_name: chosen.name });
  }
  snapshot.scholarship!.learning_services = f;
  render(<LearningPanel bundle={bundle} snapshot={snapshot} currentTurn={106} onSeek={vi.fn()}
    onSelectEvent={vi.fn()} onSelectRegion={vi.fn()} onSelectCivilization={vi.fn()} />);
  const history = screen.getByRole("region", { name: `History of ${chosen.name}` });
  expect(within(history).getByRole("region", { name: "Academy service evidence" })).toHaveTextContent("Purchased 3 crafts");
});

it("keeps disabled old bundles unchanged and missing receipt domains unknown", () => {
  const p = setup(); delete p.snapshot.scholarship!.learning_services;
  const view = render(<AcademyServices {...p} />);
  expect(view.container).toBeEmptyDOMElement();
  const f = data(); f.inventories = null; f.procurement_receipts = null; f.teaching_receipts = null; f.supply_losses = null;
  p.snapshot.scholarship!.learning_services = f;
  view.rerender(<AcademyServices {...p} />);
  expect(screen.getByText(/Holding not observed/)).toBeInTheDocument();
  expect(screen.getByText(/Purchase receipt not observed/)).toBeInTheDocument();
  expect(screen.getByText(/Teaching receipt not observed/)).toBeInTheDocument();
});
