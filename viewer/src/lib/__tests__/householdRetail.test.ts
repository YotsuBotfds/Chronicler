import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { commonsShare, ownedTitle, readHouseholdRetail, riskTotals, type HouseholdRetailRecord } from "../householdRetail";
import { NATURAL, RUNS, blanked, pilotClosed, record, refundAndOfferShort, region, regionCount, snapOf, type Run } from "./householdRetailFixture";

/* eslint-disable @typescript-eslint/no-explicit-any */
const why = (reading: { status: string; reason?: string }) => reading.status === "malformed" ? reading.reason : reading.status;
const read = (x: unknown, regions = 8, turn?: number) => readHouseholdRetail(snapOf(x, turn), regions);
const ok = (x: unknown, regions = 8): HouseholdRetailRecord => {
  const reading = read(x, regions);
  if (reading.status !== "ok") throw new Error(why(reading));
  return reading.record;
};
/** The t7 record with ``change`` applied, read. */
const mutated = (change: (x: Record<string, any>) => void, run: Run = "t7") => {
  const x = record(run);
  change(x);
  return why(read(x, regionCount(run)));
};

describe("household retail reader on natural records", () => {
  it("accepts every natural snapshot of every mode and boundary, dated", () => {
    expect(NATURAL.map((n) => n.run)).toEqual(["t7", "nr7", "fx7", "ro7", "all11", "p13", "pw7", "pw7"]);
    for (const n of NATURAL) {
      const reading = readHouseholdRetail(n as unknown as TurnSnapshot, n.region_count);
      expect(why(reading), n.label).toBe("ok");
    }
    const modes = RUNS.map((run) => ok(record(run), regionCount(run))).map((r) => `${r.mode}/${r.boundary}`);
    expect(modes).toEqual(["retail/market", "no_relief/market", "free_exchange/market", "record_only/market", "retail/all",
      "retail/market", "retail/paid_work", "retail/paid_work"]);
    // The same records misdated, or read against too few regions, are refused.
    expect(why(read(record("t7"), 8, 80))).toBe("misdated observation");
    expect(why(read(record("p13"), 8))).not.toBe("ok");
  });

  it("reads who was below their fair share, children first, and why", () => {
    const t7 = ok(record("t7"));
    // A dead owner's claim withheld for the heirs: 9 people in Oldmere short of it, no child.
    expect(riskTotals(t7)?.withheld_dead).toEqual({ households: expect.any(Number), persons: 9, children: 0, deficit: expect.any(Number) });
    expect(riskTotals(t7)?.priced_out.persons).toBe(0);
    const nr7 = ok(record("nr7"));
    expect(riskTotals(nr7)?.priced_out).toMatchObject({ persons: 16, children: 4, households: 14 });
    expect(nr7.parameters.theta).toBe(1);                                       // no_relief: the whole harvest titled
    const all11 = ok(record("all11"));
    expect(riskTotals(all11)?.priced_out).toMatchObject({ persons: 22, children: 6 });
    expect(Object.values(riskTotals(all11)!).map((t) => t.persons)).toEqual([22, 0, 0]);
  });

  it("reads the controls: free exchange charges nothing, record-only holds nothing", () => {
    const fx = ok(record("fx7"));
    expect(fx.regions!.every((r) => r.price_milli === 0 && r.provisioning!.paid_milli === 0 && r.income_replaced === null)).toBe(true);
    expect(fx.income).toEqual({});
    expect(fx.money).toMatchObject({ procurement_flows: 1, procurement_unpaid_milli: 1000, procurement_credited_milli: 0 });
    const ro = ok(record("ro7"));
    expect(ro.regions!.every((r) => r.provisioning === null && r.close_milli === 0 && r.would_be !== null)).toBe(true);
    expect(ro.regions![1].would_be).toMatchObject({ titled_milli: 14007, owners: 30, farmers: 30, price_milli: 803 });
    expect(ro.sample).toEqual([]);
    expect(ok(record("pw7early")).regions).toEqual([]);                         // no paid work yet: no pilot region
  });

  it("reads the title, the conquest loss and the derived commons share", () => {
    const p13 = ok(record("p13"), 32);
    const conquered = p13.regions!.find((r) => r.region === 21)!;
    expect(conquered.flows.war_loss).toBe(64640);
    expect(p13.log.some((e) => e.kind === "war_loss" && e.region === 21 && e.turn === 5)).toBe(true);
    const r = ok(record("t7")).regions![1];
    expect(ownedTitle(r)).toBe(21980);
    expect(commonsShare(r, 0.9)).toBeCloseTo(21980 / 9, 6);
    expect(commonsShare(r, 0)).toBeNull();
  });
});

describe("household retail reader refuses records that do not close", () => {
  it("tells absent from malformed and refuses an unknown schema", () => {
    expect(readHouseholdRetail(null, 8)).toEqual({ status: "absent" });
    expect(readHouseholdRetail({ turn: 3, livelihoods: { schema_version: 1 } } as unknown as TurnSnapshot, 8)).toEqual({ status: "absent" });
    expect(readHouseholdRetail({ turn: 3, livelihoods: { schema_version: 1, household_retail: null } } as unknown as TurnSnapshot, 8))
      .toEqual({ status: "absent" });
    expect(why(readHouseholdRetail({ turn: 81, livelihoods: { schema_version: 2, household_retail: record("t7") } } as unknown as TurnSnapshot, 8)))
      .toBe("unknown livelihoods schema");
    expect(mutated((x) => { x.stage = "L6a"; })).toBe("unknown household-retail schema");
    expect(mutated((x) => { x.mode = "sometimes"; })).toBe("unknown household-retail schema");
    expect(mutated((x) => { x.boundary = "coast"; })).toBe("unknown household-retail schema");
    expect(mutated((x) => { x.parameters.theta = 1; })).toBe("malformed parameters");              // θ = 1 only in no_relief
    expect(mutated((x) => { x.parameters.theta = 0.9; }, "nr7")).toBe("malformed parameters");
    expect(mutated((x) => { x.parameters.goods = ["grain"]; })).toBe("malformed parameters");
  });

  it("refuses an owned pool that does not close", () => {
    expect(mutated((x) => { region(x, 1).close_milli += 1; region(x, 1).goods_close[1] += 1; owned(x, 1); }))
      .toMatch(/^the owned food does not close/);
    expect(mutated((x) => { region(x, 1).flows.sold += 5; })).toMatch(/^the owned food does not close/);
    expect(mutated((x) => { delete region(x, 1).flows.decay; })).toMatch(/^the owned food does not close/);   // a dropped flow
    expect(mutated((x) => { region(x, 1).goods_close[0] += 1; })).toBe("the owned goods do not sum to the close");
    expect(mutated((x) => { region(x, 1).owners = 0; })).toBe("owners and owned food disagree");
    expect(mutated((x) => { region(x, 1).flows.inherited_in += 1; region(x, 1).flows.titled -= 1; owned(x, 1, -1); }))
      .not.toBe("ok");
    expect(mutated((x) => { const r = region(x, 1); r.flows.to_commons = 10; r.flows.titled += 10; r.phase2.retail_titled_fish += 0.01; }))
      .toBe("food to the commons does not match its reasons");
    expect(mutated((x) => { region(x, 1).flows.bogus = 1; })).toBe("malformed owned-food flows");
    expect(mutated((x) => { region(x, 1).commons.lost = 1; })).toBe("malformed commons reasons");
    expect(mutated((x) => { region(x, 1).phase2.retail_titled_fish += 0.5; })).toBe("the title differs from the economy's titled columns");
    expect(mutated((x) => { region(x, 1).owned_food_unloadable_milli += 1; }))
      .toBe("the owned food merchants could not load differs from the owned close");
    expect(mutated((x) => { x.regions.reverse(); })).toBe("pilot regions listed twice or out of order");
  });

  it("refuses provisioning whose food, people, deficits or rations do not close", () => {
    const p = (x: Record<string, any>, index = 1) => region(x, index).provisioning;
    expect(mutated((x) => { p(x).unsold_milli += 1; })).toBe("region 1: owned food on offer does not close (own_eaten + sold + unsold = offered)");
    expect(mutated((x) => { p(x).free_given += 0.5; })).toMatch(/free food does not close/);
    expect(mutated((x) => { p(x).rations += 0.5; })).toMatch(/person rations do not close/);
    expect(mutated((x) => { p(x).fed_fair -= 1; })).toMatch(/people do not close/);
    expect(mutated((x) => { p(x, 0).withheld_dead_persons -= 1; p(x, 0).fed_fair += 1; p(x, 0).deficit += 0.3; })).toMatch(/the deficit does not close/);
    expect(mutated((x) => { p(x, 0).withheld_dead_children = 10; })).toBe("region 0: malformed withheld dead counts");
    expect(mutated((x) => { p(x).priced_out_deficit = 0.2; p(x).deficit += 0.2; })).toBe("region 1: a priced out deficit without people");
    expect(mutated((x) => { p(x).withheld_dead_milli = p(x).unsold_milli + 1; })).toBe("region 1: withheld claims exceed the unsold");
    expect(mutated((x) => { p(x).own_eaten_fair_milli += 1; })).toBe("region 1: the fair-share and open rounds do not add up");
    expect(mutated((x) => { p(x).max_ration = 1.2; })).toBe("region 1: a ration above one");
    expect(mutated((x) => { p(x).persons = 1.5; })).toBe("region 1: provisioning counts or milli columns are not whole");
    expect(mutated((x) => { delete p(x).withheld_dead_deficit; })).toBe("region 1: malformed provisioning row");
    expect(mutated((x) => { p(x).region = 2; })).toBe("region 1: a provisioning row names another region");
    expect(mutated((x) => { p(x).mode = 1; })).toBe("region 1: the provisioning mode differs from the record's mode");
  });

  it("refuses provisioning that disagrees with the install or the claims debited", () => {
    const p = (x: Record<string, any>, index = 1) => region(x, index).provisioning;
    expect(mutated((x) => { region(x, 1).price_milli += 1; })).toBe("region 1: the provisioning row differs from the install");
    expect(mutated((x) => { region(x, 1).free_rations += 1; })).toBe("region 1: the provisioning row differs from the install");
    // The claims debited (the frame's flows) must be what the native frame says was eaten and sold.
    expect(mutated((x) => { const r = region(x, 1); r.flows.own_eaten += 3; r.flows.decay -= 3; }))
      .toBe("region 1: the claims debited differ from the food eaten and sold");
    expect(mutated((x) => { const r = region(x, 1); r.flows.own_eaten = 0; r.flows.sold = 0; r.close_milli = 0; r.provisioning = null; }))
      .not.toBe("ok");
    expect(mutated((x) => { p(x).own_eaten_milli += 2; p(x).own_eaten_fair_milli += 2; p(x).offered_milli += 2; }))
      .toBe("region 1: the claims debited differ from the food eaten and sold");
  });

  it("refuses money that does not balance or that the free-exchange control moved", () => {
    const p = (x: Record<string, any>, index = 1) => region(x, index).provisioning;
    expect(mutated((x) => { p(x).credited_milli -= 1; })).toBe("region 1: payments do not balance (paid = credited + refunded)");
    expect(mutated((x) => { p(x).credited_milli -= 1; p(x).refunded_milli += 1; })).toBe("region 1: refunds differ from the ceiling's refusals");
    expect(mutated((x) => { p(x).paid_milli += 50; p(x).credited_milli += 50; x.money.paid_milli += 50; x.money.credited_milli += 50; }))
      .toBe("region 1: paid differs from sold × price / ration beyond per-household rounding");
    expect(mutated((x) => { x.money.paid_milli += 1; x.money.credited_milli += 1; })).toBe("money rows differ from the region totals");
    expect(mutated((x) => { x.money.paid_milli += 1; })).toBe("the turn's payments do not balance");
    expect(mutated((x) => { delete x.money.rows; })).toBe("money rows without provisioning");
    expect(mutated((x) => { x.counters.credited_milli -= 1; })).toBe("lifetime payments do not balance");
    expect(mutated((x) => { const q = p(x, 1); q.paid_milli = q.credited_milli = 5; }, "fx7")).toMatch(/charged for food/);
    expect(mutated((x) => { x.counters.paid_milli = x.counters.credited_milli = 5; }, "fx7")).toBe("the free-exchange control moved money");
    expect(mutated((x) => { region(x, 1).income_replaced = 1; region(x, 1).income_rows = 2; }, "fx7"))
      .toMatch(/replaced farm income|income replaced without a receipt/);
  });

  it("refuses income and granary credits that do not add up", () => {
    expect(mutated((x) => { region(x, 1).income_replaced += 0.5; })).toBe("income replaced differs from its rows");
    expect(mutated((x) => { x.income = {}; region(x, 1).income_replaced = null; region(x, 1).income_rows = null; }))
      .toBe("income replaced without a receipt");
    expect(mutated((x) => { for (const r of x.regions) { r.income_replaced = null; r.income_rows = null; } x.income = {}; }))
      .toBe("provisioning without its income receipt");
    expect(mutated((x) => { region(x, 1).income_rows = null; })).toBe("malformed pilot region");
    expect(mutated((x) => { x.money.procurement_unpaid_milli = 999; }, "fx7")).toBe("procurement credits do not close (owed = credited + refused + unpaid)");
    expect(mutated((x) => { x.money.procurement_unpaid_milli = 0; x.money.procurement_credited_milli = 1000; }, "fx7"))
      .toBe("the free-exchange control paid owners for granary grain");
    expect(mutated((x) => { delete x.money.procurement_owed_milli; }, "fx7")).toBe("a partial procurement credit");
    expect(mutated((x) => { for (const k of Object.keys(x.money)) if (k.startsWith("procurement_")) delete x.money[k]; }, "fx7"))
      .toBe("owners' grain bought by granaries without a credit");
  });

  it("refuses a record-only control that held or priced food, and would-be rows elsewhere", () => {
    expect(mutated((x) => { region(x, 1).price_milli = 803; region(x, 1).free_rations = 1; }, "ro7"))
      .toBe("the record-only control held, sold or priced food");
    expect(mutated((x) => { region(x, 1).flows = { titled: 5, own_eaten: 5 }; }, "ro7")).toBe("the record-only control held, sold or priced food");
    expect(mutated((x) => { region(x, 1).would_be.owners = 31; }, "ro7")).toBe("malformed would-be title");
    expect(mutated((x) => { region(x, 1).would_be = { titled_milli: 1, owners: 0, farmers: 0, untitled_milli: 1 }; }))
      .toBe("a would-be title outside the record-only control");
  });

  it("refuses partial frames, bad samples and bad records, and keeps a blanked frame unknown", () => {
    for (const run of ["t7", "fx7", "ro7"] as const) {
      const reading = read(blanked(run), regionCount(run));
      expect(reading.status === "ok" && reading.record.regions).toBeNull();      // unknown, not zero
    }
    expect(why(read({ ...blanked("t7"), sample: [] }))).toBe("a partial frame");
    expect(why(read({ ...record("t7"), money: null }))).toBe("a partial frame");
    expect(mutated((x) => { x.sample[0][5] = 4; })).toBe("malformed person sample");
    expect(mutated((x) => { x.sample[0][1] = 3; })).toBe("malformed person sample");          // not a provisioned region
    expect(mutated((x) => { x.sample.push(...x.sample.slice(0, 1)); })).toBe("malformed frame");   // over the bound of 24
    expect(mutated((x) => { x.sample_columns = ["id"]; })).toBe("malformed sample columns");
    expect(mutated((x) => { x.log[0].kind = "rumour"; })).toBe("malformed record");
    expect(mutated((x) => { x.log.reverse(); })).toBe("the record log is out of order");
    expect(mutated((x) => { x.counters.deaths = -1; })).toBe("malformed counters");
    expect(mutated((x) => { x.counters = null; })).toBe("malformed counters");
    expect(mutated((x) => { region(x, 1).provisioning = "n/a"; })).toBe("malformed provisioning row");
  });

  it("accepts constructed refunds, offer shortfalls and a pilot closure that still close", () => {
    const refunded = ok(refundAndOfferShort());
    expect(region(refunded as any, 4).provisioning.refunded_milli).toBe(103);
    expect(riskTotals(refunded)?.offer_short).toEqual({ households: 2, persons: 3, children: 1, deficit: 0.4 });
    const closed = ok(pilotClosed());
    const r4 = closed.regions!.find((r) => r.region === 4)!;
    expect([r4.commons.pilot_closed, r4.provisioning, r4.price_milli]).toEqual([500, null, null]);
    expect(closed.log.at(-1)).toMatchObject({ kind: "pilot_closed", region: 4, turn: 80 });
  });

  it("accepts titled trade's flows (A4) in the owned pool's closure and refuses them when they do not close", () => {
    // Constructed: owners sold 100 milli-food to a merchant (it left the pool) and a
    // shipment delivered 40 as its holder's claim, with the same close.
    const traded = (change = 0) => {
      const x = record("t7");
      const r = region(x, 1);
      r.open_milli += 60;
      r.flows.sold_merchant = 100 + change;
      r.flows.consigned_in = 40;
      return x;
    };
    expect(ok(traded()).regions!.find((r) => r.region === 1)!.flows).toMatchObject({ sold_merchant: 100, consigned_in: 40 });
    expect(why(read(traded(1)))).toMatch(/^the owned food does not close/);
  });
});

/** Keep the goods consistent with a changed close (the closing identity is then the one that fails). */
function owned(x: Record<string, any>, index: number, delta = 0) {
  const r = region(x, index);
  r.close_milli += delta;
  r.goods_close[1] += delta;
  r.owned_food_unloadable_milli = r.close_milli;
}
