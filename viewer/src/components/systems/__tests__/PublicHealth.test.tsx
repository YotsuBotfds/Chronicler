import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import type { Bundle, TurnSnapshot } from "../../../types";
import { PublicHealth } from "../PublicHealth";
afterEach(cleanup);
const base = () => ({ schema_version: 1, source_turn: 4, enabled: true, mode: "active", policy: "evidence", report_delay: 0,
  report_turn: 4, environment_turn: 4, supply_turn: 4, supplies: [], decisions: [], totals: {},
  environment: [{ region: 0, source_turn: 3, residence_observed: true, sanitation_observed: true,
    displaced_share: .5, water_service: 0, crowding_factor: 1.125, flux_factor: 1 }] });
function show(raw: unknown) {
  const snapshot = { turn: 5, livelihoods: { schema_version: 1, public_health: raw } } as unknown as TurnSnapshot;
  const bundle = { history: [snapshot], world_state: { regions: [{ name: "A" }], civilizations: [] } } as unknown as Bundle;
  render(<PublicHealth bundle={bundle} snapshot={snapshot} currentTurn={5} />);
}
it("labels old spell coupling and missing diagnostics honestly", () => {
  show(base());
  expect(screen.getByText(/Legacy displacement coupling/)).toHaveTextContent("implicit in this older record");
  expect(screen.getByText(/A: 50.0% in motive-classified spells/)).toHaveTextContent("recent residence arrival share unknown (not recorded)");
});
it("shows density-only neutrality and keeps partial recent arrivals unknown", () => {
  const raw = base();
  show({ ...raw, crowding: "density_only", environment: [{ ...raw.environment[0], crowding_factor: 1,
    crowding_basis: "density_only", crowding_source_turn: 4, recent_arrival_share: null, arrival_diagnostics_complete: false }] });
  expect(screen.getByText(/Corrected explicit density_only mode/)).toHaveTextContent("Motive-classified ledger spells add no susceptibility multiplier");
  expect(screen.getByText(/A: 50.0% in motive-classified spells/)).toHaveTextContent("extra susceptibility ×1.00 (density_only)");
  expect(screen.getByText(/A: 50.0% in motive-classified spells/)).toHaveTextContent("recent residence arrival share unknown (incomplete window or coverage)");
});
it("refuses contradictory density factors instead of showing a physical zero", () => {
  const raw = base();
  show({ ...raw, crowding: "density_only", environment: [{ ...raw.environment[0], crowding_basis: "density_only", crowding_source_turn: 4,
    recent_arrival_share: .25, arrival_diagnostics_complete: true }] });
  expect(screen.getByRole("alert")).toHaveTextContent("malformed");
  expect(screen.queryByText(/extra susceptibility/)).not.toBeInTheDocument();
});
