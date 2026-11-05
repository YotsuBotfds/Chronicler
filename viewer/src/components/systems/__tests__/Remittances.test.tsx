import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { Remittances } from "../Remittances";
afterEach(cleanup);

/** Constructed observations to test rendering; not a simulation run. */
const receipt = { turn: 7, sender: 10, recipient: 20, bond: "marriage", sentiment: 30, origin: 0, destination: 1,
  wealth_milli: 7000, amount: 425, fee_requested: 75, sent: 500, fee: 75, credited: 425, refunded: 0, status: "applied" };
const zero = { region: 0, departures: 0, arrivals: 0, returns_home: 0, qualified_departures: 0, qualified_arrivals: 0,
  diaspora_out: 0, diaspora_in: 0, qualified_out: 0, qualified_in: 0, senders: 0, recipients: 0, outflow_milli: 0,
  fee_milli: 0, refunded_milli: 0, inflow_milli: 0 };
const record = { schema_version: 1, stage: "RS4", mode: "send", source_turn: 7,
  funnel: { open_entries: 2, eligible: 2, linked: 1, rows: 1, applied: 1 },
  totals: { requested_milli: 425, fee_requested_milli: 75, sent_milli: 500, fee_milli: 75, credited_milli: 425,
    refunded_milli: 0, debited_milli: 500, not_sent_milli: 0 },
  regions: [{ ...zero, region: 0, departures: 1, diaspora_out: 3, qualified_departures: 1, qualified_out: 1,
    recipients: 1, inflow_milli: 425 },
  { ...zero, region: 1, arrivals: 1, qualified_arrivals: 1, diaspora_in: 3, qualified_in: 1, senders: 1,
    outflow_milli: 500, fee_milli: 75 }],
  moves: [{ id: 13, from_region: 0, to_region: 1, kind: "departure", qualified: true, driver: 2 }], moves_dropped: 0,
  closures: [{ id: 12, origin: 0, destination: 1, departure_turn: 2, closed_turn: 7, reason: "death" }],
  closures_dropped: 0, receipts: [receipt], receipts_dropped: 0,
  unmet: [{ id: 14, origin: 0, destination: 1, reason: "recipient_away", surplus_milli: 3000 }], unmet_dropped: 2,
  last_pool_reset: { turn: 3, entries_closed: 4, reason: "native pool rebuilt: saved stable ids name other people" },
  counters: { sender_turns_evaluated: 9, eligible_sender_turns: 5, linked_sender_turns: 2, unlinked_sender_turns: 3,
    rows: 2, rows_applied: 2, credited_milli: 850, fee_milli: 150, returns: 1, departures: 4 },
  parameters: { settled_turns: 5, share_permille: 100, reserve_milli: 2000, cap_milli: 1000, fee_permille: 150,
    min_sentiment: 20, adult_age: 20, max_entries: 2048 } };

function props(remittances: unknown, turn = 8) {
  const snapshot = { turn, livelihoods: { schema_version: 1, remittances } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("names senders and recipients, amounts, fees, the diaspora and the unmet", () => {
  const p = props(record);
  render(<Remittances {...p} />);
  expect(screen.getByRole("heading", { name: "Remittances and diaspora · snapshot 8" })).toBeInTheDocument();
  expect(screen.getByText(/Nothing is created/)).toBeInTheDocument();
  const funnel = within(screen.getByRole("table", { name: "Remittance funnel at snapshot 8" }));
  expect(funnel.getByRole("row", { name: /Unmet: eligible/ })).toHaveTextContent("3");
  expect(funnel.getByRole("row", { name: /Courier fees/ })).toHaveTextContent("0.15");
  const row = within(screen.getByRole("table", { name: "Remittances at snapshot 8" })).getAllByRole("row")[1];
  expect(row).toHaveTextContent("#10");
  expect(row).toHaveTextContent("#20 (marriage, sentiment 30)");
  expect(row).toHaveTextContent("0.5 (0.075)");
  expect(row).toHaveTextContent("0.425");
  expect(row).toHaveTextContent("applied · turn 7");
  const unmet = within(screen.getByRole("table", { name: "Unmet senders at snapshot 8" })).getAllByRole("row")[1];
  expect(unmet).toHaveTextContent("#14");
  expect(unmet).toHaveTextContent("not living in the origin");
  expect(screen.getByText(/2 more unmet senders/)).toBeInTheDocument();
  const regions = within(screen.getByRole("table", { name: "Diaspora by region at snapshot 8" })).getAllByRole("row");
  expect(regions[1]).toHaveTextContent("Oldmere");
  expect(regions[1]).toHaveTextContent("3 (1)");
  expect(regions[1]).toHaveTextContent("0.425 to 1");
  expect(regions[2]).toHaveTextContent("0.5 from 1 (0.075)");
  expect(screen.getByText(/#12 death \(left Oldmere in turn 2/)).toBeInTheDocument();
  expect(screen.getByText(/#13 Oldmere → Ashford Vale \(departure, qualified\)/)).toBeInTheDocument();
  expect(screen.getByText(/rebuilt in turn 3: 4 ledger entries were closed/)).toBeInTheDocument();
  fireEvent.click(within(screen.getByRole("table", { name: "Remittances at snapshot 8" })).getByRole("button", { name: "Ashford Vale" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Ashford Vale");
});

it("says so when the record is missing or the turn was not observed", () => {
  render(<Remittances {...props(record, 9)} />);
  expect(screen.getByText(/not observed or are unavailable at snapshot 9/)).toBeInTheDocument();
  cleanup();
  const blank = { ...record, mode: "record_only", funnel: null, totals: null, regions: null, moves: null,
    moves_dropped: null, closures: null, closures_dropped: null, receipts: null, receipts_dropped: null,
    unmet: null, unmet_dropped: null };
  render(<Remittances {...props(blank)} />);
  expect(screen.getByText(/Record only \(control\)/)).toBeInTheDocument();
  expect(screen.getByText(/unknown, not zero/)).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: "Remittances at snapshot 8" })).toBeNull();
});
