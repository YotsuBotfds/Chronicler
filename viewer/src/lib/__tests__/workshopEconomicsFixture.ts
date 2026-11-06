/** Constructed A3 observations to test the reader; not a simulation run. */
export const terms = { firm: 0, region: 1, opened_turn: 3, capital: 11000, capital_payer: 0, status: "open",
  closed_turn: null, closed_reason: null, idle_run: 0, turns: 2, operating_turns: 1, last_operating_turn: 4,
  totals: { capital: 11000, inputs: 480, household_sales: 140 } };
export const inputs = { price_milli: 800, budget_milli: 9800, capacity_milli: 12250, crew: 2, wage_bill_milli: 300,
  no_input_reason: null, used_timber_milli: 450, used_ore_milli: 150, used_milli: 600, charged_milli: 480,
  not_charged_milli: 0, payee: ["civ_treasury", 0], treasury_units: 0 };
export const households = { residents: 7, households: 6, demand_milli: 70, commons_milli: 0, gap_milli: 70,
  offered_milli: 70, price_milli: 2000, bought_milli: 70, paid_milli: 140, buying_households: 5,
  priced_out_households: 1, payers: 5, depopulated: false };
export const receipt = { turn: 4, firm: 0, region: 1, owner: 0, status: "open", operating: true, inputs,
  produced: 600, titled: 590, free_use_upper_bound: 10, academy_sales: 0, academy_sold: 0, households,
  customer_absent: ["no_academy"], capital_in: 0, wages_due: 300, wages_paid: 300, owed_after: 0, worn: 5,
  returned: 0, distributed: 0, written_off: 0, cash_open: 10700, cash_close: 10060, inventory_open: 100,
  inventory_close: 615, unsold_inventory: 615, owner_asset_spend: 3, idle_run: 0, insolvent_run: 0, event: null };
export const economics = { schema_version: 1, stage: "A3", mode: "market", source_turn: 4,
  units: { money: "milli_treasury_units", wares: "milli_loads", price: "milli_per_load", milli: 1000 },
  firms: [terms], closed: [], prices: [], receipts: [receipt], flows: [], book: { carry: {}, sinks: {} },
  counters: { firms_opened: 1, capital_paid: 11000, operating_firm_turns: 1, inputs_charged: 480,
    household_sales: 140, household_delivered: 70, priced_out_households: 1, free_use_upper_bound: 10,
    asset_subsidy_firm_units: 3, sites_without_firm_turns: 6 },
  log: [], log_dropped: 0, parameters: { capital_turns: 3, idle_close_after: 6 } };
