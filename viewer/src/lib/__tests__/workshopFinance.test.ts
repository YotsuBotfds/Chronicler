import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { payrollFunnel, workshopFinanceAt } from "../workshopFinance";
import { firm, payroll, receipt } from "./workshopFinanceFixture";

const snap = (workshop_payroll: unknown, turn = 5) =>
  ({ turn, livelihoods: { schema_version: 1, workshop_payroll } } as unknown as TurnSnapshot);

describe("workshop finance reader", () => {
  it("reads a dated record whose accounts close", () => {
    const record = workshopFinanceAt(snap(payroll), 3);
    expect(record?.firms[0].city_name).toBe("Ashford");
    expect(record?.receipts?.[0].wages_paid).toBe(1300);
    expect(workshopFinanceAt(snap(payroll, 6), 3)).toBeNull();          // misdated
    expect(workshopFinanceAt(snap(payroll), 1)).toBeNull();             // region out of range
    expect(workshopFinanceAt(snap({ ...payroll, mode: "charity" }), 3)).toBeNull();
    expect(workshopFinanceAt(null, 3)).toBeNull();
  });

  it("refuses accounts that do not close and impossible transfers", () => {
    expect(workshopFinanceAt(snap({ ...payroll, firms: [{ ...firm, cash: 1701 }] }), 3)).toBeNull();
    expect(workshopFinanceAt(snap({ ...payroll, firms: [{ ...firm, inventory: 449 }] }), 3)).toBeNull();
    expect(workshopFinanceAt(snap({ ...payroll, receipts: [{ ...receipt, cash_close: 1600 }] }), 3)).toBeNull();
    expect(workshopFinanceAt(snap({ ...payroll, receipts: [{ ...receipt, shares: [0.3] }] }), 3)).toBeNull();
    expect(workshopFinanceAt(snap({ ...payroll, firms: [{ ...firm, cash: -1, totals: { ...firm.totals, sales: 1299 } }] }), 3)).toBeNull();
    const bad = { ...payroll.transfers, money: [{ ...payroll.transfers.money[0], applied: 2000 }] };
    expect(workshopFinanceAt(snap({ ...payroll, transfers: bad }), 3)).toBeNull();
    expect(workshopFinanceAt(snap({ ...payroll, firms: [firm, firm, firm, firm, firm] }), 3)).toBeNull();
  });

  it("closes RS1 apprentice stipends paid from firm cash", () => {
    const paidFirm = { ...firm, cash: firm.cash - 250, totals: { ...firm.totals, stipends: 250 } };
    const paidReceipt = { ...receipt, stipends: 250, cash_close: receipt.cash_close - 250 };
    const stipend = { ...payroll.transfers.money[0], id: "wp:4:stipend:0:9", kind: "stipend",
      payer: ["workshop_cash", 0], payee: ["agent_wealth", 9], amount: 250, applied: 250, residual: 0 };
    const transfers = { ...payroll.transfers, money: [...payroll.transfers.money, stipend] };
    const record = workshopFinanceAt(snap({ ...payroll, firms: [paidFirm], receipts: [paidReceipt], transfers }), 3);
    expect(record?.receipts?.[0].stipends).toBe(250);
    // A stipend that left the cash but is not recorded does not close.
    expect(workshopFinanceAt(snap({ ...payroll, firms: [{ ...firm, cash: firm.cash - 250 }] }), 3)).toBeNull();
    expect(workshopFinanceAt(snap({ ...payroll, receipts: [{ ...receipt, stipends: 250 }] }), 3)).toBeNull();
  });

  it("keeps unobserved turns and unknown income unknown, not zero", () => {
    const unobserved = workshopFinanceAt(snap({ ...payroll, receipts: null, transfers: null }), 3);
    expect(unobserved?.receipts).toBeNull();
    const unknown = workshopFinanceAt(snap({ ...payroll, receipts: [{ ...receipt, income_replaced: null }] }), 3);
    expect(unknown?.receipts?.[0].income_replaced).toBeNull();
  });

  it("derives the funnel in units", () => {
    const f = payrollFunnel(workshopFinanceAt(snap(payroll), 3)!);
    expect(f.sales).toBe(3);
    expect(f.wagesPaid).toBe(1.3);
    expect(f.netCrewEffect).toBeCloseTo(0.8);
    expect(f.customerFirmTurns).toBe(2);
    expect(f.closedInsolvent).toBe(0);
  });
});
