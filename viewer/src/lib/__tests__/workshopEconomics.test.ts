import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { economicsFunnel, workshopEconomicsAt } from "../workshopEconomics";
import { economics, households, inputs, receipt, terms } from "./workshopEconomicsFixture";
import { payroll } from "./workshopFinanceFixture";

const snap = (livelihoods: unknown, turn = 5) => ({ turn, livelihoods } as unknown as TurnSnapshot);
const with3 = (workshop_economics: unknown, turn = 5) =>
  snap({ schema_version: 1, workshop_payroll: payroll, workshop_economics }, turn);

describe("workshop economics reader", () => {
  it("keeps absent, disabled, malformed, unobserved and observed apart", () => {
    expect(workshopEconomicsAt(null, 3).status).toBe("absent");
    expect(workshopEconomicsAt(snap({ schema_version: 1, food_allocation: {} }), 3).status).toBe("absent");
    expect(workshopEconomicsAt(snap({ schema_version: 1, workshop_payroll: payroll }), 3).status).toBe("disabled");
    expect(workshopEconomicsAt(with3({ ...economics, stage: "L6a" }), 3).status).toBe("malformed");
    expect(workshopEconomicsAt(with3(null), 3).status).toBe("malformed");
    expect(workshopEconomicsAt(with3(economics, 6), 3).status).toBe("malformed");           // misdated
    const unobserved = workshopEconomicsAt(with3({ ...economics, receipts: null }), 3);
    expect(unobserved.status).toBe("unobserved");
    expect(unobserved.record?.receipts).toBeNull();
    const observed = workshopEconomicsAt(with3(economics), 3);
    expect(observed.status).toBe("observed");
    expect(observed.record?.receipts?.[0].households?.paid_milli).toBe(140);
  });

  it("keeps a recorded zero a zero and an empty frame an observed no-firm turn", () => {
    const none = workshopEconomicsAt(with3({ ...economics, firms: [], receipts: [] }), 3);
    expect(none.status).toBe("observed");
    expect(none.record?.receipts).toEqual([]);
    const zero = { ...receipt, households: { ...households, bought_milli: 0, paid_milli: 0, buying_households: 0 },
      cash_close: receipt.cash_close - 140, inventory_close: receipt.inventory_close + 70,
      unsold_inventory: receipt.inventory_close + 70, customer_absent: ["no_academy", "households_cannot_pay"] };
    const read = workshopEconomicsAt(with3({ ...economics, receipts: [zero] }), 3);
    expect(read.status).toBe("observed");
    expect(read.record?.receipts?.[0].households?.paid_milli).toBe(0);
  });

  it("refuses receipts that do not close", () => {
    for (const bad of [
      { ...receipt, cash_close: receipt.cash_close + 1 },
      { ...receipt, inventory_close: receipt.inventory_close - 1 },
      { ...receipt, unsold_inventory: 1 },
      { ...receipt, households: { ...households, bought_milli: 80 } },              // bought beyond the offer
      { ...receipt, households: { ...households, gap_milli: 60, offered_milli: 60, bought_milli: 60 } },
      { ...receipt, inputs: { ...inputs, capacity_milli: null } },                  // paid without a reservation
      { ...receipt, inputs: { ...inputs, capacity_milli: 500 } },                   // converted beyond what it paid for
      { ...receipt, inputs: { ...inputs, converted_unpaid_milli: 10 } },            // nothing is converted unpaid
      { ...receipt, inputs: { ...inputs, plan_price_milli: null } },                // used without a plan price
      { ...receipt, inputs: { ...inputs, charged_milli: 479 } },                    // not the cost at the plan price
      { ...receipt, inputs: { ...inputs, plan_price_source: "tick" } },
      { ...receipt, customer_absent: ["bad_luck"] },
      { ...receipt, region: 7 },
    ]) expect(workshopEconomicsAt(with3({ ...economics, receipts: [bad] }), 3).status).toBe("malformed");
    expect(workshopEconomicsAt(with3({ ...economics, firms: [{ ...terms, totals: { capital: -1 } }] }), 3).status)
      .toBe("malformed");
  });

  it("reads a turn without a price or a budget, and the cost control, as observed", () => {
    const idle = { ...receipt, operating: false, produced: 0, titled: 0, free_use_upper_bound: 0, households,
      inputs: { ...inputs, plan_price_milli: null, plan_price_turn: null, plan_price_region: null, plan_price_source: null,
        capacity_milli: 0, used_timber_milli: 0, used_ore_milli: 0, used_milli: 0, cost_milli: 0, charged_milli: 0,
        no_input_reason: "price_unknown", unbought_need_milli: 4800 },
      cash_close: receipt.cash_close + 480, inventory_close: receipt.inventory_close - 590,
      unsold_inventory: receipt.inventory_close - 590 };
    expect(workshopEconomicsAt(with3({ ...economics, receipts: [idle] }), 3).status).toBe("observed");
    const control = { ...receipt, inputs: { ...inputs, charged_milli: 0, not_charged_milli: 480 },
      cash_close: receipt.cash_close + 480 };
    expect(workshopEconomicsAt(with3({ ...economics, mode: "free_inputs", receipts: [control] }), 3).status).toBe("observed");
  });

  it("derives the funnel in units", () => {
    const f = economicsFunnel(workshopEconomicsAt(with3(economics), 3).record!);
    expect(f.capitalPaid).toBe(20);
    expect(f.inputsCharged).toBe(0.48);
    expect(f.householdSales).toBe(0.14);
    expect(f.householdShareOfSales).toBe(1);
    expect(f.closedIdle).toBe(0);
    const empty = economicsFunnel({ ...economics, counters: {} } as never);
    expect(empty.householdShareOfSales).toBeNull();
  });
});

describe("workshop economics reader under owned output (A3-2)", () => {
  const owned = { ...receipt, titled: 600, free_use_upper_bound: 0, inventory_close: 625, unsold_inventory: 625 };
  const a32 = { ...economics, rules_version: 2, receipts: [owned], counters: { ...economics.counters, owned_output: 600 } };
  it("reads rules version 2 and refuses free use or an untitled share under it", () => {
    const read = workshopEconomicsAt(with3(a32), 3);
    expect(read.status).toBe("observed");
    expect(read.record?.rules_version).toBe(2);
    expect(economicsFunnel(read.record!).ownedOutput).toBe(0.6);
    expect(economicsFunnel(workshopEconomicsAt(with3(economics), 3).record!).ownedOutput).toBeNull();
    // Rules 1's free use is refused under rules 2 (the whole output is titled), and only 2 is a version.
    expect(workshopEconomicsAt(with3({ ...a32, receipts: [receipt] }), 3).status).toBe("malformed");
    expect(workshopEconomicsAt(with3({ ...a32, rules_version: 1 }), 3).status).toBe("malformed");
  });
});
