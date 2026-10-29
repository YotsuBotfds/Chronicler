import { describe, expect, it } from "vitest";
import debtFixture from "../../__fixtures__/debt_holders_bundle.json";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../__fixtures__/sample_bundle.json";
import type { Bundle, Event, TurnSnapshot } from "../../types";
import {
  borrowers, civDebtHolders, creditEventsOf, foreignLenderSeries, groupsInSeries, HOLDER_GROUPS, holderDetail,
  holderSeries, realmsInDebt, troubleRows, writeOffs,
} from "../debtHolders";

/** Trimmed from a real --domestic-credit run: procedural 32 x 10, seed 42, 120 hybrid turns. */
const fixture = debtFixture as unknown as Bundle;
const CIV = "Khidutain Clans";
const civs = fixture.world_state.civilizations.map((civ) => civ.name);

function at(bundle: Bundle, turn: number): TurnSnapshot {
  const snapshot = bundle.history.find((entry) => entry.turn === turn);
  if (!snapshot) {
    throw new Error(`fixture has no turn ${turn}`);
  }
  return snapshot;
}

/** The same history with the newer parts of the record removed, as older bundles carry it. */
function withoutHolders(bundle: Bundle): Bundle {
  return {
    ...bundle,
    history: bundle.history.map((snapshot) => {
      if (!snapshot.finance?.domestic_credit) {
        return snapshot;
      }
      const credit = { ...snapshot.finance.domestic_credit };
      delete credit.holders;
      return { ...snapshot, finance: { ...snapshot.finance, domestic_credit: credit } };
    }),
  };
}

function withoutDomesticCredit(bundle: Bundle): Bundle {
  return {
    ...bundle,
    history: bundle.history.map((snapshot) => {
      if (!snapshot.finance) {
        return snapshot;
      }
      const finance = { ...snapshot.finance };
      delete finance.domestic_credit;
      return { ...snapshot, finance };
    }),
  };
}

describe("holderDetail", () => {
  it("reads what the bundle records", () => {
    expect(holderDetail(fixture.history)).toBe("lenders");
    expect(holderDetail(withoutHolders(fixture).history)).toBe("kinds");
    expect(holderDetail(withoutDomesticCredit(fixture).history)).toBe("totals");
    expect(holderDetail((systemsFixture as unknown as Bundle).history)).toBe("totals");
    expect(holderDetail((sampleFixture as unknown as Bundle).history)).toBeNull();
  });
});

describe("civDebtHolders", () => {
  it("names every holder with its rate and interest, adding up to the debt", () => {
    const snapshot = at(fixture, 54);
    const entry = civDebtHolders(snapshot, CIV, "lenders")!;
    const row = snapshot.finance!.civs[CIV];
    expect(entry.debt).toBe(row.debt);
    expect(entry.foreign).toBe(row.foreign_debt);
    expect(HOLDER_GROUPS.reduce((sum, group) => sum + entry.groups[group], 0)).toBe(row.debt);
    const kinds = snapshot.finance!.domestic_credit!.civs[CIV];
    expect(entry.groups.merchants).toBe(kinds.merchants);
    expect(entry.groups.city).toBe(kinds.city);
    expect(entry.groups.guild).toBe(kinds.guild);
    expect(entry.groups.houses).toBe(kinds.houses);
    const held = snapshot.finance!.domestic_credit!.holders![CIV];
    for (const [lender, [principal, rate]] of Object.entries(held.foreign!)) {
      const lent = entry.rows.find((r) => r.civ === lender)!;
      expect(lent).toMatchObject({ group: "foreign", amount: principal, rate });
      expect(lent.interest).toBeCloseTo(principal * rate);
    }
    for (const [region, amount] of Object.entries(held.merchants!)) {
      expect(entry.rows.find((r) => r.region === region)).toMatchObject({ group: "merchants", amount, rate: held.rate });
    }
    expect(entry.rows.find((r) => r.group === "city")!.label).toBe(Object.keys(held.cities!)[0]);
    expect(entry.rows.find((r) => r.group === "guild")!.label).toBe(Object.keys(held.guilds!)[0]);
    expect(entry.rows.some((r) => r.label.endsWith("not named") || r.label.endsWith("not attributed"))).toBe(false);
    // Rows in stacking order, the largest first within a group.
    const order = entry.rows.map((r) => HOLDER_GROUPS.indexOf(r.group));
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    const domesticDue = (row.debt - row.foreign_debt) * held.rate!;
    const foreignDue = Object.values(held.foreign!).reduce((sum, [p, r]) => sum + p * r, 0);
    expect(entry.interestDue).toBeCloseTo(domesticDue + foreignDue);
    expect(entry.interestPaid).toBe(row.interest);
    expect(entry.writtenOff).toBe(0);
    expect(civDebtHolders(at(fixture, 55), CIV, "lenders")!.writtenOff).toBe(124);
  });

  it("keeps an older bundle's domestic kinds and one foreign total, with nothing invented", () => {
    const entry = civDebtHolders(at(withoutHolders(fixture), 54), CIV, "kinds")!;
    expect(entry.rows.filter((r) => r.group === "foreign")).toHaveLength(1);
    expect(entry.rows.every((r) => r.rate === null && r.interest === null)).toBe(true);
    expect(entry.rows.map((r) => r.label)).toContain("Merchants");
    expect(entry.interestDue).toBeNull();
    expect(entry.writtenOff).toBeNull();
    expect(entry.groups.merchants + entry.groups.city + entry.groups.guild + entry.groups.houses).toBe(entry.domestic);
  });

  it("splits a finance-only record into the abstract domestic class and foreign lenders", () => {
    const entry = civDebtHolders(at(withoutDomesticCredit(fixture), 54), CIV, "totals")!;
    expect(entry.rows.map((r) => [r.group, r.amount])).toEqual([["domestic", entry.debt - entry.foreign], ["foreign", entry.foreign]]);
  });

  it("is null for a civ without a finance row", () => {
    expect(civDebtHolders(at(fixture, 54), "Nobody", "lenders")).toBeNull();
    expect(civDebtHolders(null, CIV, "lenders")).toBeNull();
  });
});

describe("series and lists", () => {
  it("keeps missing older lender allocations and write-offs unknown in mixed-version history", () => {
    const older = at(withoutHolders(fixture), 54);
    const newer = at(fixture, 55);
    expect(civDebtHolders(older, CIV, "lenders")!.writtenOff).toBeNull();
    const { lenders, data } = foreignLenderSeries([older, newer], CIV, civs);
    expect(lenders.length).toBeGreaterThan(0);
    expect(lenders.every((name) => data[0][name] === null)).toBe(true);
    expect(writeOffs([older, newer], CIV, [], "lenders").every((row) => row.amount === null)).toBe(true);
    expect(troubleRows([older, newer], CIV, "lenders").find((row) => row.id === "written_off")!.segments).toEqual([]);
  });
  it("retains a fallen borrower's loss events without inventing amounts or finance rows", () => {
    const withoutBorrower = (snapshot: TurnSnapshot): TurnSnapshot => {
      const finance = { ...snapshot.finance!, civs: { ...snapshot.finance!.civs } };
      delete finance.civs[CIV];
      return { ...snapshot, finance };
    };
    const history = [at(fixture, 54), withoutBorrower(at(fixture, 55)), withoutBorrower(at(fixture, 60))];
    const loss: Event = {
      turn: 54, event_type: "debt_written_off", actors: [CIV, "Sylenen Kingdom"],
      description: "With the borrower gone, its debt is lost.", consequences: [], importance: 3,
      event_id: "synthetic:fallen-loan:1",
    };
    const secondLoan = { ...loss, event_id: "synthetic:fallen-loan:2" };
    const later = { ...loss, turn: 56, event_id: "synthetic:fallen-loan:3" };
    const lenderOnly = { ...loss, actors: ["Another borrower", CIV], event_id: "synthetic:other-borrower" };
    const pending = { ...loss, turn: 60, event_id: "synthetic:pending" };
    const events = [loss, secondLoan, later, lenderOnly, pending];
    const losses = writeOffs(history, CIV, events, "lenders");
    expect(losses).toEqual([
      { turn: 55, amount: null, defaulted: false, events: [loss, secondLoan] },
      { turn: 60, amount: null, defaulted: false, events: [later] },
    ]);
    expect(civDebtHolders(history[1], CIV, "lenders")).toBeNull();
    const strip = troubleRows(history, CIV, "totals", events).find((row) => row.id === "written_off")!;
    expect(strip.segments.map((segment) => segment.start)).toEqual([55, 60]);
    expect(strip.segments.every((segment) => segment.label.includes("amount not recorded"))).toBe(true);
    expect(troubleRows(history, CIV, "totals").some((row) => row.id === "written_off")).toBe(false);
  });

  it("keeps a default event after the borrower's finance row disappears", () => {
    const absent = { ...at(fixture, 55), finance: { ...at(fixture, 55).finance!, civs: {} } };
    const history = [at(fixture, 54), absent];
    const event = fixture.events_timeline.find((entry) => entry.event_type === "state_default"
      && entry.turn === 54 && entry.actors[0] === CIV)!;
    expect(writeOffs(history, CIV, [event], "lenders")).toEqual([
      { turn: 55, amount: null, defaulted: true, events: [event] },
    ]);
    const strips = troubleRows(history, CIV, "lenders", [event]);
    expect(strips.find((row) => row.id === "defaults")!.segments.map((segment) => segment.start)).toEqual([55]);
    expect(strips.find((row) => row.id === "written_off")!.segments).toEqual([]);
  });

  it("does not repeat an event when a later finance row already accounts for it", () => {
    const absent = { ...at(fixture, 55), finance: { ...at(fixture, 55).finance!, civs: {} } };
    const history = [at(fixture, 54), absent, at(fixture, 60)];
    const event = fixture.events_timeline.find((entry) => entry.event_type === "state_default"
      && entry.turn === 54 && entry.actors[0] === CIV)!;
    const losses = writeOffs(history, CIV, [event], "lenders");
    expect(losses).toHaveLength(1);
    expect(losses[0]).toMatchObject({ turn: 60, amount: 124, defaulted: true, events: [event] });
    const strips = troubleRows(history, CIV, "lenders", [event]);
    expect(strips.find((row) => row.id === "defaults")!.segments.map((segment) => segment.start)).toEqual([60]);
    expect(strips.find((row) => row.id === "written_off")!.segments.map((segment) => segment.start)).toEqual([60]);
  });

  it("lists the indebted realms in world order and the borrowers by peak debt", () => {
    const realms = realmsInDebt(at(fixture, 54), civs, "lenders");
    expect(realms.every((entry) => entry.debt > 0)).toBe(true);
    expect(realms.map((entry) => entry.civ)).toEqual(civs.filter((civ) => realms.some((entry) => entry.civ === civ)));
    const peaks = borrowers(fixture.history, civs);
    expect(peaks).toContain(CIV);
    expect(peaks).not.toContain("Tribes of Mifadeth");
  });

  it("charts the debt by holder group and the foreign debt by lender", () => {
    const series = holderSeries(fixture.history, CIV, "lenders");
    expect(series).toHaveLength(fixture.history.length);
    const row = series.find((entry) => entry.turn === 54)!;
    expect(row.foreign).toBe(180);
    expect(groupsInSeries(series)).toEqual(["merchants", "city", "guild", "houses", "foreign"]);
    const { lenders, data } = foreignLenderSeries(fixture.history, CIV, civs);
    expect(lenders).toEqual(civs.filter((civ) => lenders.includes(civ)));
    expect(lenders).toEqual(expect.arrayContaining(["Sylenen Kingdom", "Thalassocracy of Nithys"]));
    const point = data.find((entry) => entry.turn === 54)!;
    expect(point["Sylenen Kingdom"]).toBe(133);
    expect(point["Duglutoni Principality"]).toBe(0);
  });

  it("finds each default and write-off with its events", () => {
    const losses = writeOffs(fixture.history, CIV, fixture.events_timeline, "lenders");
    const defaults = losses.filter((loss) => loss.defaulted);
    expect(defaults.map((loss) => [loss.turn, loss.amount])).toEqual([[55, 124], [65, 131]]);
    for (const loss of defaults) {
      expect(loss.events.map((event) => event.event_type)).toContain("state_default");
      expect(loss.events.every((event) => event.actors[0] === CIV && event.turn === loss.turn - 1)).toBe(true);
    }
    const older = writeOffs(withoutHolders(fixture).history, CIV, fixture.events_timeline, "kinds");
    expect(older.map((loss) => [loss.turn, loss.amount])).toEqual([[55, null], [65, null]]);
    const rows = troubleRows(fixture.history, CIV, "lenders");
    expect(rows.map((row) => row.id)).toEqual(["arrears", "defaults", "written_off"]);
    expect(rows[1].segments.map((segment) => segment.start)).toEqual([55, 65]);
    expect(rows[0].segments.map((segment) => segment.start)).toEqual([54, 64]);
    expect(troubleRows(fixture.history, CIV, "kinds").map((row) => row.id)).toEqual(["arrears", "defaults"]);
  });

  it("keeps the credit events that name the civ", () => {
    const events = creditEventsOf(fixture.events_timeline, CIV);
    expect(events.length).toBeGreaterThan(0);
    expect(events.every((event) => event.actors.includes(CIV) || (event.civs ?? []).includes(CIV))).toBe(true);
  });
});
