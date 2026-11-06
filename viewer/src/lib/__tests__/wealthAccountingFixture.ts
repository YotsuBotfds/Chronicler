/** Constructed A1 wealth-ledger records to test reading and rendering; not a simulation run. */
export const frame = {
  turn: 9,
  continuity: { status: "exact", reason: null, previous_close_turn: 8 },
  typed_complete: true,
  world: {
    open: 100, close: 103.5, delta: 3.5, agents_open: 40, agents_close: 41, births: 2, births_close: 1, deaths: 1,
    deaths_open: 2.25, moved: 3, moved_close: 4.5, typed_in_milli: 3000, typed_out_milli: 1000, typed_net_milli: 2000,
    unlocated_in_milli: 500, unlocated_out_milli: 0, native_model: 1.5, unplaced_agents: 0,
  },
  regions: [
    { region: 0, open: 60, close: 61.5, agents_open: 25, agents_close: 24, migration_in: 0, migration_out: 4.5,
      births: 0, births_close: 0, deaths: 1, deaths_open: 2.25, typed_in_milli: 2000, typed_out_milli: 1000,
      native_model: 5 },
    { region: 1, open: 40, close: 42, agents_open: 15, agents_close: 17, migration_in: 4.5, migration_out: 0,
      births: 2, births_close: 1, deaths: 0, deaths_open: 0, typed_in_milli: 500, typed_out_milli: 0,
      native_model: -3 },
  ],
  typed: [
    { channel: "granary_crew_wage", package: "recovery_crews", payer: "treasury granary coins -> granary crew (PL3)",
      observed: true, in_milli: 2000, out_milli: 0, unlocated_in_milli: 0, unlocated_out_milli: 0 },
    { channel: "food_procurement", package: "household_retail", payer: "treasury -> owners of procured grain (L6b)",
      observed: true, in_milli: 500, out_milli: 0, unlocated_in_milli: 500, unlocated_out_milli: 0 },
    { channel: "remittance", package: "remittances", payer: "sender -> recipient, fee to the courier sink (RS4)",
      observed: true, in_milli: 500, out_milli: 1000, unlocated_in_milli: 0, unlocated_out_milli: 0 },
  ],
  closures: [
    { channel: "granary_crew_wage", check: "granary coins = wages + sunk (paid)", lhs: 2000, rhs: 2000, closes: true },
    { channel: "remittance", check: "senders debited = recipients credited + courier fee", lhs: 1000, rhs: 1000, closes: true },
  ],
  withheld: {
    paid_work_active: true, rows: 3, deducted: 0.75,
    packages: [
      { package: "recovery_crews_granary", rows: 2, deducted: 0.5, ordinary: 1, package_total: null, matches: null },
      { package: "recovery_crews_workshop", rows: 1, deducted: 0.25, ordinary: 0.5, package_total: null, matches: null },
      { package: "repair_projects", rows: 0, deducted: 0, ordinary: 0, package_total: 0.25, matches: true },
    ],
    unattributed_rows: 0, unattributed_pl3_dropped_rows: 0, unattributed_deducted: 0, conflicts: 0,
    recovery_crews: { granary: 0.5, workshop: 0.25, total: 0.75, difference: 0, closes: true, rows_dropped: 0 },
    retail_active: true, retail_income_replaced: 1.25,
  },
  treasury: {
    created: { treasury_tax: 4 },
    tithe: { potential: 9, at_threshold_after_tick: 3, approximate: true, collected: null },
    to_households_milli: { repair_wage: 0, granary_crew_wage: 2000, woodcut_wage: 0, food_procurement: 500 },
    firm_cash: { sales_from_treasury_milli: 0, wages_milli: 0, stipends_milli: 0, distributions_to_treasury_milli: 0,
      written_off_milli: 0 },
    charged: { repair_projects: 3, timber_supply: 0, relocation_assistance: 0 },
    sinks_milli: { repair_coins: 0, granary_wage_residual: 0, remittance_fee: 500, relocation_fare: 0,
      relocation_assistance: 0, procurement_residual: 0 },
    by_civ: [{ civ: 0, charged: 3, tithe_potential: 9, tithe_at_threshold_after_tick: 3, to_households_milli: 2500,
      treasury_tax: 4 }],
  },
};

export function record(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 1, stage: "A1", source_turn: 9,
    units: { balance: "wealth_units", typed: "milli_units", treasury: "treasury_units", milli: 1000 },
    frame, lifetime: { native_model: 1.5 }, counters: { turns_observed: 10 }, log: [], log_dropped: 0,
    labels: { native_model: "native model flows" }, parameters: {}, ...overrides,
  };
}
