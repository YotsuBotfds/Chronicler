/** Constructed A4 titled trade observations to test the reader; not a simulation run. */
export const live = { id: 3, goods: "food", holder: 90, carrier: 90, origin: 0, dest: 2, path: [0, 1, 2], cursor: 1,
  controllers: ["Selurian", "Selurian"], status: "moving", dispatched_turn: 3, last_moved_turn: 4,
  cargo: [1500, 200, 0, 0, 0], cargo_open: [1500, 200, 0, 0, 0], cost_milli: 900, price_milli: 280, sellers: 2,
  losses: {}, delivered: 0, returned: 0, deposited: 0, deposit_reason: null, outcome: null, cause: null,
  closed_turn: null, closed_region: null, released: null, withheld: 0.2, withheld_turns: 1, war_exempt_turns: 0,
  history: [[3, "dispatched", 0], [4, "moved", 1]] };
export const delivered = { ...live, id: 1, holder: 91, carrier: 91, path: [0, 2], cursor: 1, status: "closed",
  dispatched_turn: 2, last_moved_turn: 3, cargo: [0, 0, 0, 0, 0], cargo_open: [1000, 0, 0, 0, 0],
  losses: { transit_decay: 50 }, delivered: 950, outcome: "delivered", closed_turn: 3, closed_region: 2,
  withheld: 0.2, history: [[2, "dispatched", 0], [3, "moved", 2], [3, "delivered", 2]] };
export const returned = { ...delivered, id: 2, holder: 92, carrier: 92, cursor: 0, losses: {}, delivered: 0,
  returned: 1000, outcome: "returned", cause: "destination_conquered", closed_turn: 4, closed_region: 0 };
export const purchase = { shipment: 4, holder: 93, origin: 0, dest: 2, path: [0, 2], milli: 600,
  cargo: [600, 0, 0, 0, 0], price_milli: 300, paid: 360, refunded: 0, sellers: 2,
  seller_rows: [[11, 400, 240, 240], [12, 200, 120, 120]] };
export const frame = { turn: 4, dispatched: [purchase],
  events: [{ shipment: 3, event: "moved", region: 1 },
    { shipment: 2, event: "returned", cause: "destination_conquered", region: 0, delivered: 0, returned: 1000,
      deposited: 0, losses: {} }],
  withheld: [{ shipment: 3, carrier: 90, share: 1.0, ordinary: 0.2, deducted: 0.2 }], withheld_total: 0.2,
  sales: [{ holder: 91, region: 2, sold: 500, cargo_sold: 500, credited: 600, exact: true }], plans: { no_cash: 1 },
  live: 2 };
export const trade = { schema_version: 1, stage: "A4", goods: "food", source_turn: 4,
  units: { food: "milli_food", money: "milli_units", price: "milli_per_ration", withheld: "wealth_units", milli: 1000 },
  shipments: [live, { ...live, id: 4, holder: 93, carrier: 93, cursor: 0, path: [0, 2], last_moved_turn: null,
    cargo: [600, 0, 0, 0, 0], cargo_open: [600, 0, 0, 0, 0], cost_milli: 360, withheld: 0, withheld_turns: 0 }],
  closed: [delivered, returned], lots: [{ holder: 91, region: 2, milli: 450, shipments: [1] }], frame,
  flows: [], counters: { dispatched: 4, delivered: 1, returned: 1, returned_destination_conquered: 1,
    bought_milli: 4300, paid_milli: 2560, transit_decay_milli: 50, consigned_milli: 950, returned_milli: 1000,
    cargo_sold_milli: 500, cargo_sales_credited_milli: 600, income_withheld_micro: 400000, carrier_turns: 2 },
  log: [], log_dropped: 0, parameters: { owner_keep_milli: 1000 } };
