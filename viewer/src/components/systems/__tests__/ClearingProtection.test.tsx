import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { receipt, record, without } from "../../../lib/__tests__/clearingProtectionFixture";
import { ClearingProtection } from "../ClearingProtection";
afterEach(cleanup);

/** Constructed observations to test rendering; not a simulation run. */
const bundle = { world_state: { regions: [{ name: "Thornwood" }, { name: "Mistwood" }, { name: "Ashfield" }, { name: "Cinder" }],
  civilizations: [{ name: "Dorrathi" }, { name: "Thornwall" }, { name: "Ashkari" }] } } as unknown as Bundle;

function props(clearing: unknown = record(), turn = 5, livelihoods: unknown = undefined) {
  const snapshot = { turn, livelihoods: livelihoods ?? { schema_version: 1, clearing_protection: clearing } } as unknown as TurnSnapshot;
  return { bundle, snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("shows protected regions, cover kept against cover lost, bills, endings, unmet needs and the trade-off", () => {
  const p = props(); render(<ClearingProtection {...p} />);
  expect(screen.getByRole("heading", { name: "Clearing protection · snapshot 5" })).toBeInTheDocument();
  expect(screen.getByText(/Phase 9 of simulation turn 4\. Enforced/)).toBeInTheDocument();
  const rows = within(screen.getByRole("table", { name: "Protected regions at snapshot 5" })).getAllByRole("row");
  expect(rows[1]).toHaveTextContent("Thornwood");
  expect(rows[1]).toHaveTextContent("Thornwall");
  expect(rows[1]).toHaveTextContent("0.6 → 0.6");
  expect(rows[1]).toHaveTextContent("2 · 2 · 2");
  expect(rows[1]).toHaveTextContent("Full");
  expect(rows[2]).toHaveTextContent("Mistwood (new)");
  expect(rows[2]).toHaveTextContent("Partial (1 of 2)");
  expect(within(rows[2]).getAllByRole("cell")[4]).toHaveTextContent("0.5");
  const cover = within(screen.getByRole("table", { name: "Cover kept and lost at snapshot 5" }));
  expect(cover.getByRole("row", { name: /Cover kept from clearing in protected regions/ })).toHaveTextContent("0.03");
  expect(cover.getByRole("row", { name: /Cover cleared in protected regions/ })).toHaveTextContent("0.01");
  expect(cover.getByRole("row", { name: /Cover cleared elsewhere/ })).toHaveTextContent("0.04");
  expect(cover.getByRole("row", { name: /Wardens planned · paid · charged/ })).toHaveTextContent("4 · 3 · 3");
  expect(cover.getByRole("row", { name: /Underfunded protected regions/ })).toHaveTextContent("1");
  const unmet = within(screen.getByRole("table", { name: "Unmet needs at snapshot 5" }));
  expect(unmet.getByText(/Over the limit/)).toBeInTheDocument();
  expect(unmet.getByText(/Not forested/)).toBeInTheDocument();
  expect(screen.getByText(/Thornwall adopted protection of Mistwood \(clearing pressure\)/)).toBeInTheDocument();
  expect(screen.getByText(/Ashkari ended protection of Cinder \(cover lost/)).toBeInTheDocument();
  expect(screen.getByText(/forgoes the forest-to-plains succession/)).toBeInTheDocument();
  const funnel = within(screen.getByRole("table", { name: "Clearing protection funnel to snapshot 5" }));
  expect(funnel.getByRole("row", { name: /Protections adopted/ })).toHaveTextContent("3");
  expect(funnel.getByRole("row", { name: /Ended: cover lost/ })).toHaveTextContent("1");
  expect(within(screen.getByRole("table", { name: "Protections in force at snapshot 5" })).getAllByRole("row")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "Ashfield" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Ashfield");
});

it("labels the cost-only control and each ending reason", () => {
  const control = record({ mode: "cost_only",
    receipts: [receipt({ p_applied: 0, cover_not_cleared: 0, cover_after: 0.58 }),
      receipt({ region_id: 1, new: true, p_applied: 0, cover_not_cleared: 0 })],
    decisions: [{ turn: 4, region_id: 1, civ: 1, kind: "adopted", reason: "clearing_pressure" },
      ...(["controller_changed", "idle", "unfunded"] as const).map((reason, i) =>
        ({ turn: 4, region_id: 2 + (i % 2), civ: 0, kind: "ended" as const, reason }))] });
  render(<ClearingProtection {...props(control)} />);
  expect(screen.getByText(/Cost-only control/)).toBeInTheDocument();
  const rows = within(screen.getByRole("table", { name: "Protected regions at snapshot 5" })).getAllByRole("row");
  expect(rows[1]).toHaveTextContent("0 (paid for 1)");
  expect(rows[1]).toHaveTextContent("0 (would keep 0.02)");
  expect(within(screen.getByRole("table", { name: "Cover kept and lost at snapshot 5" }))
    .getByRole("row", { name: /would have kept/ })).toHaveTextContent("0.04");
  expect(screen.getByText(/\(controller changed/)).toBeInTheDocument();
  expect(screen.getByText(/\(idle/)).toBeInTheDocument();
  expect(screen.getByText(/\(unfunded/)).toBeInTheDocument();
});

it("shows missing values as unknown, never zero", () => {
  const older = without(record(), "unprotected");
  const params = without(record().parameters, "forest_clearing");
  render(<ClearingProtection {...props({ ...older, parameters: params, counters: {} })} />);
  const cover = within(screen.getByRole("table", { name: "Cover kept and lost at snapshot 5" }));
  expect(cover.getByRole("row", { name: /Cover cleared elsewhere/ })).toHaveTextContent("Unknown");
  expect(cover.getByRole("row", { name: /Cover cleared in protected regions/ })).toHaveTextContent("Unknown");
  expect(screen.getByText(/unmet needs are unknown, not none/)).toBeInTheDocument();
  const funnel = within(screen.getByRole("table", { name: "Clearing protection funnel to snapshot 5" }));
  expect(funnel.getByRole("row", { name: /Protections adopted/ })).toHaveTextContent("Unknown");
  expect(funnel.queryByText("0")).not.toBeInTheDocument();
  cleanup();
  render(<ClearingProtection {...props(record({ observed: false, receipts: null, decisions: null, unprotected: null }))} />);
  expect(screen.getByText(/protection accounts are unknown, not empty/)).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: /Protected regions/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("table", { name: /Unmet needs/ })).not.toBeInTheDocument();
  cleanup();
  render(<ClearingProtection {...props(record({ receipts: [], decisions: [], protections: [], unprotected: [] }))} />);
  expect(screen.getByText("No region is protected this turn.")).toBeInTheDocument();
  expect(screen.getByText(/No controlled region was cleared or under clearing pressure without protection/)).toBeInTheDocument();
});

it("says so when the record is malformed or absent, as in an older bundle", () => {
  render(<ClearingProtection {...props({ ...record(), receipts: [receipt({ charged: 1 })] })} />);
  expect(screen.getByText(/not observed, unavailable or malformed at snapshot 5/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  cleanup();
  render(<ClearingProtection {...props(undefined, 5, { schema_version: 1, commons_rules: {} })} />);
  expect(screen.getByText(/not observed, unavailable or malformed at snapshot 5/)).toBeInTheDocument();
  cleanup();
  const older = { bundle, snapshot: { turn: 7 } as unknown as TurnSnapshot, currentTurn: 7, onSelectRegion: vi.fn() };
  render(<ClearingProtection {...older} />);
  expect(screen.getByText(/unavailable or malformed at snapshot 7/)).toBeInTheDocument();
  cleanup();
  render(<ClearingProtection {...{ ...older, snapshot: null, currentTurn: 3 }} />);
  expect(screen.getByText(/at snapshot 3/)).toBeInTheDocument();
});

it("re-dates every value to the selected snapshot on rewind", () => {
  const later = props(record());
  const { rerender } = render(<ClearingProtection {...later} />);
  expect(screen.getByRole("heading", { name: "Clearing protection · snapshot 5" })).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Clearing protection funnel to snapshot 5" }))
    .getByRole("row", { name: /Protections adopted/ })).toHaveTextContent("3");
  // Rewind to snapshot 3: an earlier record with one protection and smaller counters.
  const earlier = record({ source_turn: 2, completed_turn: 3, receipts: [receipt({ new: true })],
    decisions: [{ turn: 2, region_id: 0, civ: 1, kind: "adopted", reason: "clearing_pressure" }], unprotected: [],
    protections: [{ region_id: 0, payer: 1, adopted_turn: 2, idle_turns: 0, unfunded_turns: 0, active_turns: 1, charged: 2,
      cover_not_cleared: 0.02 }], counters: { adopted: 1, charged: 2 } });
  rerender(<ClearingProtection {...props(earlier, 3)} />);
  expect(screen.getByRole("heading", { name: "Clearing protection · snapshot 3" })).toBeInTheDocument();
  expect(screen.getByText(/Phase 9 of simulation turn 2/)).toBeInTheDocument();
  expect(screen.queryByText("Mistwood (new)")).not.toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Clearing protection funnel to snapshot 3" }))
    .getByRole("row", { name: /Protections adopted/ })).toHaveTextContent("1");
  expect(screen.queryByRole("table", { name: /snapshot 5/ })).not.toBeInTheDocument();
  // A record attached to the wrong snapshot is never shown as that snapshot's.
  rerender(<ClearingProtection {...props(record(), 4)} />);
  expect(screen.getByText(/unavailable or malformed at snapshot 4/)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /snapshot 5/ })).not.toBeInTheDocument();
});
