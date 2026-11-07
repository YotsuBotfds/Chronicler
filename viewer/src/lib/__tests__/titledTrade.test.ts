import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { titledTradeAt, tradeFunnel } from "../titledTrade";
import { delivered, frame, live, purchase, returned, trade } from "./titledTradeFixture";

const snap = (livelihoods: unknown, turn = 5) => ({ turn, livelihoods } as unknown as TurnSnapshot);
const with4 = (titled_trade: unknown, turn = 5) =>
  snap({ schema_version: 1, household_retail: { stage: "L6b" }, titled_trade }, turn);

describe("titled trade reader", () => {
  it("keeps absent, disabled, malformed, unobserved and observed apart", () => {
    expect(titledTradeAt(null, 3).status).toBe("absent");
    expect(titledTradeAt(snap({ schema_version: 1, food_allocation: {} }), 3).status).toBe("absent");
    expect(titledTradeAt(snap({ schema_version: 1, household_retail: { stage: "L6b" } }), 3).status).toBe("disabled");
    expect(titledTradeAt(with4(null), 3).status).toBe("malformed");
    expect(titledTradeAt(with4({ ...trade, stage: "A3" }), 3).status).toBe("malformed");
    expect(titledTradeAt(with4(trade, 6), 3).status).toBe("malformed");                 // misdated
    const unobserved = titledTradeAt(with4({ ...trade, frame: null }), 3);
    expect(unobserved.status).toBe("unobserved");
    expect(unobserved.record?.frame).toBeNull();
    const observed = titledTradeAt(with4(trade), 3);
    expect(observed.status).toBe("observed");
    expect(observed.record?.frame?.dispatched[0].paid).toBe(360);
  });

  it("keeps a recorded zero a zero", () => {
    const zero = titledTradeAt(with4({ ...trade, shipments: [], closed: [], lots: [],
      frame: { ...frame, dispatched: [], events: [], withheld: [], withheld_total: 0, sales: [], live: 0 } }), 3);
    expect(zero.status).toBe("observed");
    expect(zero.record?.frame?.dispatched).toEqual([]);
  });

  it("refuses shipments and frames whose books do not close or whose outcome is not single", () => {
    for (const bad of [
      { ...live, cargo: [1400, 200, 0, 0, 0] },                       // cargo does not close
      { ...live, outcome: "delivered" },                              // live with an outcome
      { ...live, cursor: 3 },                                         // beyond its path
      { ...live, dest: 7 },                                           // unknown region
    ]) expect(titledTradeAt(with4({ ...trade, shipments: [bad] }), 3).status).toBe("malformed");
    for (const bad of [
      { ...delivered, outcome: null },                                // closed without an outcome
      { ...delivered, cargo: [10, 0, 0, 0, 0], cargo_open: [1010, 0, 0, 0, 0] },   // closed with cargo aboard
      { ...returned, cause: "bad_luck" },                             // undeclared cause
      { ...delivered, delivered: 949 },                               // the closure fails
    ]) expect(titledTradeAt(with4({ ...trade, closed: [bad] }), 3).status).toBe("malformed");
    expect(titledTradeAt(with4({ ...trade, closed: [delivered, { ...returned, id: 1 }] }), 3).status)
      .toBe("malformed");                                             // a reused id
    for (const bad of [
      { ...frame, turn: 3 },
      { ...frame, dispatched: [{ ...purchase, paid: 361 }] },          // the sellers' payments are the bill
      { ...frame, dispatched: [{ ...purchase, milli: 601 }] },
      { ...frame, withheld: [{ ...frame.withheld[0], share: 0.5 }] },  // a carrier's whole income
      { ...frame, withheld_total: 0.3 },
      { ...frame, events: [{ shipment: 3, event: "teleported", region: 1 }] },
      { ...frame, sales: [{ ...frame.sales[0], cargo_sold: 501 }] },
    ]) expect(titledTradeAt(with4({ ...trade, frame: bad }), 3).status).toBe("malformed");
  });

  it("derives the funnel and the merchants' net money from the counters", () => {
    const f = tradeFunnel(titledTradeAt(with4(trade), 3).record!);
    expect([f.dispatched, f.delivered, f.returned, f.escheated]).toEqual([4, 1, 1, 0]);
    expect(f.returnedBy.destination_conquered).toBe(1);
    expect(f.paid).toBe(2.56);
    expect(f.netMoney).toBeCloseTo(0.6 - 2.56);
    expect(f.withheld).toBeCloseTo(0.4);
  });
});
