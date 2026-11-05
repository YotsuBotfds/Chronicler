import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { record, receipt } from "../../../lib/__tests__/commonsRulesFixture";
import { CommonsRules } from "../CommonsRules";
afterEach(cleanup);

/** Constructed observations to test rendering; not a simulation run. */
function props(commons: unknown = record(), turn = 5) {
  const snapshot = { turn, livelihoods: { schema_version: 1, commons_rules: commons } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Thornwood" }, { name: "Mistwood" }],
    civilizations: [{ name: "Dorrathi" }, { name: "Thornwall" }, { name: "Ashkari" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("shows dated knowledge, coverage, the lowered limit and the city's grievance", () => {
  const p = props(); render(<CommonsRules {...p} />);
  expect(screen.getByRole("heading", { name: "Commons rules · snapshot 5" })).toBeInTheDocument();
  expect(screen.getByText(/Enforced: a paid rule lowers the timber harvest cap/)).toBeInTheDocument();
  const funnel = within(screen.getByRole("table", { name: "Commons rule funnel to snapshot 5" }));
  expect(funnel.getByRole("row", { name: /Rules adopted/ })).toHaveTextContent("1");
  const rows = within(screen.getByRole("table", { name: "Commons rule accounts at snapshot 5" }));
  expect(rows.getByText("Thornwall")).toBeInTheDocument();
  expect(rows.getByText("10 of 100 (3)")).toBeInTheDocument();
  expect(rows.getByText("100% · paid 2 of 2")).toBeInTheDocument();
  expect(rows.getByText("0 of 9.5")).toBeInTheDocument();
  expect(rows.getByText("Yes")).toBeInTheDocument();
  expect(screen.getByText(/Ashkari repealed the rule on Mistwood slot 0 \(recovered\)/)).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Protected region outcomes at snapshot 5" })).getByText("No neighbouring stand")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Thornwood" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Thornwood");
});

it("labels the cost-only ablation and open access", () => {
  const ablation = record({ mode: "cost_only", decisions: [], receipts: [
    receipt({ binding: null, extraction: 4, excess: 4, grievance_added: 0, city: null, raw_imports: null }),
    receipt({ region_id: 1, binding: null, paid: 0, coverage: 0, applied: false, limit: 9.5, extraction: 3, grievance_added: 0 })] });
  render(<CommonsRules {...props(ablation)} />);
  expect(screen.getByText(/Cost-only ablation/)).toBeInTheDocument();
  const rows = within(screen.getByRole("table", { name: "Commons rule accounts at snapshot 5" }));
  expect(rows.getByRole("columnheader", { name: "Would bind" })).toBeInTheDocument();
  expect(rows.getByText("Would withhold 4")).toBeInTheDocument();
  expect(rows.getByText("9.5 (open access)")).toBeInTheDocument();
  expect(rows.getByText("No city")).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Protected region outcomes at snapshot 5" })).getByText("Unknown")).toBeInTheDocument();
});

it("keeps unobserved and malformed records unknown", () => {
  render(<CommonsRules {...props({ ...record(), observed: false, receipts: null, decisions: null })} />);
  expect(screen.getByText(/accounts are unknown, not empty/)).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: /Commons rule accounts/ })).not.toBeInTheDocument();
  cleanup();
  render(<CommonsRules {...props({ ...record(), receipts: [] , decisions: [] })} />);
  expect(screen.getByText(/every timber slot is open access/)).toBeInTheDocument();
  cleanup();
  render(<CommonsRules {...props(record(), 6)} />);
  expect(screen.getByText(/not observed or are unavailable at snapshot 6/)).toBeInTheDocument();
});
