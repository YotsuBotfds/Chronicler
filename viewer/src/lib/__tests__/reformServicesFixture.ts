/**
 * A D1a poor-relief services record for the reader and panel tests: the turn-85
 * record of a development run (template seed 7, hybrid, --food-allocation
 * --household-retail --reform-services), trimmed to two realms and four regions.
 */
export const frame = {
  turn: 85,
  civs: [
    { civ: 0, reform: 1, path: "upkeep", fund_open_milli: 2000, to_fund_milli: 2000, sunk_units: 0, spent_milli: 0,
      residual_milli: 0, refunded_milli: 0, fund_close_milli: 4000, cap_milli: 8000 },
    { civ: 1, reform: 0, path: "upkeep", fund_open_milli: 6564, to_fund_milli: 1000, sunk_units: 1, spent_milli: 3,
      residual_milli: 0, refunded_milli: 0, fund_close_milli: 7561, cap_milli: 8000 },
  ],
  purchases: [
    { region: 3, civ: 1, reform: 0, unmet_rations: 0.5, price_milli: 484, food_milli: 2, goods_milli: [2, 0, 0, 0, 0],
      rations: 0.004, cost_milli: 2, credited_milli: 2, residual_milli: 0, sellers: 1 },
    { region: 2, civ: 1, reform: 0, unmet_rations: 1, price_milli: 345, food_milli: 1, goods_milli: [0, 0, 0, 1, 0],
      rations: 0.002, cost_milli: 1, credited_milli: 1, residual_milli: 0, sellers: 1 },
  ],
  deliveries: [
    { region: 3, civ: 1, bought_turn: 84, rations_bought: 1.752, observed: true, free_rations: 8.725392,
      free_given: 8.40223, free_unallocated: 0.323162, delivered_at_least: 1.376277, delivered_at_most: 1.752,
      priced_out_persons: 0, unmet_rations: 0 },
    { region: 2, civ: 1, bought_turn: 84, rations_bought: 0.004, observed: true, free_rations: 11.720176,
      free_given: 11.221445, free_unallocated: 0.498731, delivered_at_least: null, delivered_at_most: 0.004,
      priced_out_persons: 2, unmet_rations: 1.5 },
  ],
};

export const empty = { turn: 85, civs: [], purchases: [], deliveries: [] };

export function record(changes: Record<string, unknown> = {}) {
  return {
    schema_version: 1, stage: "D1a", mode: "service", source_turn: 85, frame, funds: { "0": 4000, "1": 7561 },
    counters: { turns: 86, purchases: 8 }, log: [], log_dropped: 0, parameters: { fund_cap_turns: 4 }, ...changes,
  };
}
