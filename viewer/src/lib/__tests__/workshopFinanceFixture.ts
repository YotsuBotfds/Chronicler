/** Constructed observations to test the reader; not a simulation run. */
export const firm = { site: 0, region: 1, settlement_id: 7, city_name: "Ashford", opened_turn: 3, status: "open",
  closed_turn: null, closed_reason: null, cash: 1700, inventory: 450, owed: [{ agent_id: 15, amount: 100, since_turn: 4 }],
  hours: 0.75, crew_cap: 8, insolvent_run: 1, diverted: 0.3,
  totals: { sales: 3000, wages: 1300, titled: 1500, delivered: 1000, worn: 50 }, history: [[3, "opened", 0]] };
export const receipt = { turn: 4, site: 0, region: 1, controller: 0, operating: true, hours: 1, crew_cap: 8,
  crew: [11, 15], shares: [0.3, 0.3], output: 1.2, title_basis: 0.9, titled: 900, cash_open: 0, inventory_open: 600,
  customers: 1, sold: 1000, sales: 3000, wages_due: 300, wages_paid: 1300, wages_cap_residual: 0, owed_lapsed: 0,
  owed_after: 100, income_replaced: 0.18, worn: 50, returned: 0, distributed: 0, written_off: 0, cash_close: 1700,
  inventory_close: 450, insolvent: true, hours_next: 0.75, crew_cap_next: 8, event: null };
export const payroll = { schema_version: 1, stage: "L6a", mode: "paid", source_turn: 4,
  units: { money: "milli_treasury_units", wares: "milli_loads", milli: 1000 }, firms: [firm], closed: [],
  receipts: [receipt],
  transfers: { money: [{ id: "wp:4:sale:0:2", turn: 4, phase: "phase10", kind: "sale", payer: ["civ_treasury", 0],
    payee: ["workshop_cash", 0], amount: 3000, applied: 3000, residual: 0, status: "applied" }],
  materials: [{ id: "wp:4:delivery:0:1", turn: 4, phase: "phase10", kind: "delivery", source: ["workshop_inventory", 0],
    dest: ["academy_inventory", 2], good: "crafts", requested: 1000, delivered: 1000, status: "delivered" }] },
  counters: { operating_site_turns: 3, offered_firm_turns: 3, customer_firm_turns: 2, sales_paid: 2, sales: 3000,
    wages_due: 1400, wages_paid: 1300, owed_written_off: 0, income_replaced: 0.5 },
  parameters: { wage_per_work: 500 } };
