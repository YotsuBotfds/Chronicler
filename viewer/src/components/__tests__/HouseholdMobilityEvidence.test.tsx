import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { HouseholdMobilitySnapshot } from "../../types";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import { householdMobilityAt } from "../../lib/householdMobility";
import { MigrationEvidence } from "../MigrationEvidence";
afterEach(cleanup);

/** Constructed frame for display and validation, not an observed native run. */
function frame(): HouseholdMobilitySnapshot {
  return { schema_version: 1, source_turn: 1, completed_turn: 2, timing: "agent_decision_post_consolidation",
    mode: "hybrid", wealth_units: "native_agent_wealth", person_units: "native_agents", passed_means: "gate_passed_not_observed_move",
    requirement_per_native_person: 2, proposed_groups: 3, proposed_native_persons: 6,
    passed_groups: 2, passed_native_persons: 4, blocked_groups: 1, blocked_native_persons: 2, dropped_samples: 1,
    samples: [
      { group_id: 10, origin_region_id: 0, destination_region_id: 1, native_persons: 2, local_food_sufficiency: .5,
        native_adult_liquid_wealth: 1, required_liquid: 4, reason: "insufficient" },
      { group_id: 12, origin_region_id: 1, destination_region_id: 1, native_persons: 2, local_food_sufficiency: null,
        native_adult_liquid_wealth: 9, required_liquid: 4, reason: "on_trip" },
    ] };
}
it("shows world totals and the selected region's retained gate reasons separately from movement", () => {
  const bundle = regionalFixture(); bundle.history[1].household_mobility = frame();
  render(<MigrationEvidence bundle={bundle} currentTurn={2} selectedRegionIndex={0} />);
  const gate = within(screen.getByRole("region", { name: "Household mobility gate" }));
  expect(gate.getByText(/Passing this gate does not establish that a move occurred/)).toBeInTheDocument();
  expect(gate.getByText("3 groups / 6 native people")).toBeInTheDocument();
  expect(gate.getByText("2 groups / 4 native people")).toBeInTheDocument();
  expect(gate.getByText("1 group / 2 native people")).toBeInTheDocument();
  expect(gate.getByText(/1 group sample omitted/)).toBeInTheDocument();
  expect(gate.getByText(/Blocked: insufficient liquid wealth/)).toHaveTextContent("available: 1; required: 4");
  expect(gate.queryByText(/already on a trip/)).not.toBeInTheDocument();
});
it("does not use future, duplicate, missing, stale or malformed data", () => {
  const bundle = regionalFixture(); const good = frame(); bundle.history[1].household_mobility = good;
  expect(householdMobilityAt(bundle, 1)).toBeNull();
  for (const broken of [ { ...frame(), source_turn: 2 }, { ...frame(), completed_turn: 3 }, { ...frame(), schema_version: 2 },
    { ...frame(), passed_means: "observed_move" }, { ...frame(), proposed_groups: 4 },
    { ...frame(), dropped_samples: 0 }, { ...frame(), samples: [{ ...frame().samples[0], reason: "unknown" }, frame().samples[1]] },
    { ...frame(), samples: [{ ...frame().samples[0], native_adult_liquid_wealth: NaN }, frame().samples[1]] },
    { ...frame(), samples: [{ ...frame().samples[0], native_persons: 999 }, frame().samples[1]] } ]) {
    Object.assign(bundle.history[1], { household_mobility: broken });
    expect(householdMobilityAt(bundle, 2)).toBeNull();
  }
  const over = frame();
  over.samples = Array.from({ length: 129 }, (_, id) => ({ ...frame().samples[0], group_id: id }));
  Object.assign(over, { proposed_groups: 129, proposed_native_persons: 258, passed_groups: 0, passed_native_persons: 0,
    blocked_groups: 129, blocked_native_persons: 258, dropped_samples: 0 });
  bundle.history[1].household_mobility = over;
  expect(householdMobilityAt(bundle, 2)).toBeNull();
  bundle.history[1].household_mobility = good;
  bundle.history.push(structuredClone(bundle.history[1]));
  expect(householdMobilityAt(bundle, 2)).toBeNull();
  render(<MigrationEvidence bundle={bundle} currentTurn={2} />);
  expect(within(screen.getByRole("region", { name: "Household mobility gate" })).getByText(/not recorded or unavailable/)).toBeInTheDocument();
});
it("bounds retained rows and resets the displayed sample page on scrubbing", () => {
  const bundle = regionalFixture(); const f = frame();
  f.samples = Array.from({ length: 12 }, (_, index) => ({ ...frame().samples[0], group_id: index }));
  Object.assign(f, { proposed_groups: 140, proposed_native_persons: 280, passed_groups: 0, passed_native_persons: 0,
    blocked_groups: 140, blocked_native_persons: 280, dropped_samples: 128 });
  bundle.history[1].household_mobility = f;
  bundle.history[2].household_mobility = { ...structuredClone(f), source_turn: 2, completed_turn: 3 };
  const view = render(<MigrationEvidence bundle={bundle} currentTurn={2} />);
  expect(screen.getByText("Showing 8 of 12 matching retained samples.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show more gate samples (4 remaining)" }));
  expect(screen.getByText("Showing 12 of 12 matching retained samples.")).toBeInTheDocument();
  view.rerender(<MigrationEvidence bundle={bundle} currentTurn={3} />);
  expect(screen.getByText("Showing 8 of 12 matching retained samples.")).toBeInTheDocument();
  expect(screen.getByText(/128 group samples omitted/)).toBeInTheDocument();
});

it("preserves small nonzero recorded wealth and requirements", () => {
  const bundle = regionalFixture(); const f = frame();
  f.samples[0].native_adult_liquid_wealth = .00001; f.samples[0].required_liquid = .0001;
  bundle.history[1].household_mobility = f;
  render(<MigrationEvidence bundle={bundle} currentTurn={2} selectedRegionIndex={0} />);
  expect(screen.getByText(/Blocked: insufficient liquid wealth/)).toHaveTextContent("available: 1.000e-5; required: 1.000e-4");
});
