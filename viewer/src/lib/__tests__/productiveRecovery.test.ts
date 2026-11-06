import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { readTimberSupply, refusalCounts, lossCounts } from "../timberSupply";
import { readOperatingWear, wearTotals } from "../operatingWear";
import { crewTotals, readRecoveryCrews } from "../recoveryCrews";
import { obligationTotals, readMaintenanceObligation } from "../maintenanceObligation";
import { readApprenticeship } from "../apprenticeship";
import { repairProjectsAt } from "../repairProjects";
import { localBudgetsAt } from "../localBudgets";
import {
  abandoned, cutReceipt, decisions, delivered, granaryCrew, liveCutting, maintenanceObligation, needs, operatingWear, recoveryCrews,
  snapWith, timberLedger, timberSupply, unpaidReceipt, uses, wearReceipts, workshopCrew,
} from "./productiveRecoveryFixture";

const snap = (records: Record<string, unknown>, turn = 10) => snapWith(records, turn) as unknown as TurnSnapshot;
const why = (reading: { status: string; reason?: string }) => reading.status === "malformed" ? reading.reason : reading.status;

describe("timber supply reader", () => {
  const read = (x: unknown, turn = 10, regions = 4, civs = 2) => readTimberSupply(snap({ timber_supply: x }, turn), regions, civs);
  const with_ = (patch: object) => why(read({ ...timberSupply, ...patch }));

  it("reads a dated, closing record and tells absent from malformed", () => {
    const reading = read(timberSupply);
    expect(reading.status).toBe("ok");
    expect(readTimberSupply(snap({}), 4, 2)).toEqual({ status: "absent" });
    expect(readTimberSupply(null, 4, 2)).toEqual({ status: "absent" });
    expect(why(read(timberSupply, 11))).toBe("misdated observation");
    expect(why(read(timberSupply, 10, 3))).not.toBe("ok");                 // region out of range
    expect(why(read(timberSupply, 10, 4, 1))).not.toBe("ok");              // civ out of range
    expect(with_({ stage: "PL0" })).toBe("unknown timber-supply schema");
    expect(with_({ mode: "sometimes" })).toBe("unknown timber-supply schema");
    expect(why(readTimberSupply(snap({ timber_supply: timberSupply }), 4, 2))).toBe("ok");
  });

  it("refuses timber that does not close: cut, cargo, delivered, lost and abandoned", () => {
    expect(with_({ expeditions: [{ ...liveCutting, cargo: 1.5 }, timberSupply.expeditions[1]] })).toMatch(/does not close/);
    expect(with_({ closed: [{ ...timberSupply.closed[0], lost: 0.5 }, timberSupply.closed[1]] })).toMatch(/does not close/);
    expect(with_({ closed: [timberSupply.closed[0], { ...timberSupply.closed[1], cargo: 1, abandoned: 0 }] }))
      .toBe("malformed abandoned expedition");
    expect(with_({ counters: { ...timberSupply.counters, delivered: 3.5 } })).toMatch(/lifetime timber does not close/);
    expect(with_({ stores: [{ ...timberSupply.stores[0], closing: 2.5 }] })).toBe("a timber store does not close");
    expect(with_({ expeditions: [{ ...liveCutting, delivered: 1, cargo: 1 }, timberSupply.expeditions[1]],
      counters: { ...timberSupply.counters, delivered: 3.97 } })).toBe("a live expedition has delivered");
  });

  it("refuses wages, charges and receipts that disagree", () => {
    expect(with_({ ledger: [{ ...timberLedger, charged: 1 }] })).toBe("the treasury charge does not close");
    expect(with_({ ledger: [{ ...timberLedger, prepaid_after_milli: 1500, charged: 3 }] })).toBe("a prepaid balance of a whole unit");
    expect(with_({ receipts: [{ ...cutReceipt, wages_milli: 1000 }, unpaidReceipt] })).toBe("expedition wages do not close");
    expect(with_({ receipts: [{ ...cutReceipt, wages_due_milli: 2000, wages_milli: 2000 }, unpaidReceipt] }))
      .toBe("wages are not the crew at the declared wage");
    expect(with_({ receipts: [cutReceipt, { ...unpaidReceipt, wages_due_milli: 500, wages_milli: 500 }] }))
      .toBe("an unpaid turn was paid");
    // An unpaid turn charges nothing: its civ has no ledger row.
    expect(with_({ ledger: [timberLedger, { ...timberLedger, civ: 1, person_turns: 1, wages_due_milli: 0,
      wages_applied_milli: 0, charged: 0, prepaid_after_milli: 0 }] })).toBe("wage ledger and receipts disagree");
    expect(with_({ receipts: [cutReceipt, unpaidReceipt], ledger: null })).toBe("receipts without accounts");
    expect(with_({ receipts: [{ ...cutReceipt, crew: [10, 11, 20] }, unpaidReceipt] })).not.toBe("ok");
    expect(with_({ receipts: [{ ...cutReceipt, eid: 9 }, unpaidReceipt] })).toBe("a receipt names no listed expedition");
    expect(with_({ receipts: [{ ...cutReceipt, away_delivered: 4 }, unpaidReceipt] })).toBe("more farm labour removed than asked");
    expect(with_({ receipts: [cutReceipt, { ...unpaidReceipt, stock_before: 5 }] })).toBe("a partial forest account");
  });

  it("refuses need rows whose gap or reason does not close", () => {
    expect(with_({ needs: [{ ...needs[0], gap: 2 }, needs[1], needs[2]] })).toMatch(/gap does not close/);
    expect(with_({ needs: [needs[0], { ...needs[1], reason: null }, needs[2]] })).toBe("a refusal without its reason");
    expect(with_({ needs: [needs[0], { ...needs[1], reason: "too_wet" }, needs[2]] })).toBe("a refusal without its reason");
    expect(with_({ needs: [needs[0], needs[1], { ...needs[2], store: 3 }] })).toBe("the store exceeds the free timber");
    expect(with_({ needs: [needs[0], needs[1], { ...needs[2], free: 0, store: 0, gap: 1 }] })).toBe("a supplied need with a gap");
    expect(with_({ needs: null })).toBe("a partial frame");
  });

  it("refuses timber cut by the cost-only control, and reads its matched costs", () => {
    expect(with_({ mode: "cost_only" })).toBe("the cost-only control cut timber");
    const zero = { cut: 0, cargo: 0, delivered: 0, lost: 0, abandoned: 0 };
    const control = { ...timberSupply, mode: "cost_only",
      expeditions: timberSupply.expeditions.map((e) => ({ ...e, ...zero })), closed: timberSupply.closed.map((e) => ({ ...e, ...zero })),
      receipts: [{ ...cutReceipt, crew_labor: 0, cut: 0, cargo_after: 0 }, { ...unpaidReceipt, cargo_after: 0 }],
      stores: [], store: {}, deposits: [], needs: [{ ...needs[0], in_transit: 0, gap: 3.5 }, needs[1]],
      per_expedition: { ...timberSupply.per_expedition, cut: 0, delivered: 0 },
      counters: { ...timberSupply.counters, cut: 0, delivered: 0, lost: 0, abandoned_cargo: 0, crew_labor: 0,
        ended_cut: 0, ended_delivered: 0 } };
    expect(why(read(control))).toBe("ok");
    expect(why(read({ ...control, receipts: [cutReceipt, control.receipts[1]] }))).toBe("crew labour on the forest outside supplied cutting");
  });

  it("reads a crew that came home empty as returned, never as a delivery, and counts every ending", () => {
    const empty = { ...delivered, eid: 5, status: "returned", cut: 0, delivered: 0, lost: 0 };
    const counters = { ...timberSupply.counters, ended: 3, returned_expeditions: 1, ended_cut: 4, ended_delivered: 2.97 };
    const perExpedition = { ended: 3, wages_milli: 2500, person_turns: 5, farm_labor_away: 4 / 3 * 2.5, unpaid_turns: 0,
      cut: 4 / 3, delivered: 0.99 };
    const withReturn = { closed: [delivered, abandoned, empty], counters: { ...counters, ended_wages_milli: 7500 },
      per_expedition: perExpedition };
    expect(with_(withReturn)).toBe("ok");
    expect(with_({ ...withReturn, closed: [delivered, abandoned, { ...empty, cut: 0.5, delivered: 0.5 }] }))
      .toMatch(/returned expedition carried timber|lifetime timber/);
    expect(with_({ ...withReturn, counters: { ...withReturn.counters, returned_expeditions: 0 } })).toBe("lifetime endings do not add up");
    expect(with_({ counters: { ...timberSupply.counters, abandoned_crew_lost: 0 } })).toBe("lifetime endings do not add up");
    // Cargo deposited at home when home changed hands on the way: the transit decay is still the only loss.
    const homeLost = { ...abandoned, end_reason: "home_lost", cut: 1, lost: 0.01, abandoned: 0.99 };
    expect(with_({ closed: [delivered, homeLost], counters: { ...timberSupply.counters, lost: 0.04, abandoned_cargo: 0.99,
      abandoned_crew_lost: 0, abandoned_home_lost: 1 } })).toBe("ok");
  });

  it("keeps an unobserved turn unknown, and counts refusals and losses", () => {
    const blank = { ...timberSupply, receipts: null, ledger: null, stores: null, needs: null, needs_dropped: null, deposits: null };
    const reading = read(blank);
    expect(reading.status === "ok" && reading.record.receipts).toBeNull();
    expect(reading.status === "ok" && reading.record.needs).toBeNull();
    expect(why(read({ ...timberSupply, per_expedition: null }))).toBe("ended expeditions without per-expedition means");
    expect(why(read({ ...timberSupply, per_expedition: { ...timberSupply.per_expedition, wages_milli: 3000 } })))
      .toBe("per-expedition means disagree with the counters");
    const record = (read(timberSupply) as unknown as { record: never }).record;
    expect(refusalCounts(record)).toEqual([["no_forest", 5], ["forest_busy", 3]]);
    expect(lossCounts(record)).toEqual({ abandoned: [["crew_lost", 1]], dropped: [["died", 2], ["migrated", 1]] });
  });
});

describe("operating wear reader", () => {
  const read = (x: unknown, regions = 4) => readOperatingWear(snap({ operating_wear: x }), regions);
  const with_ = (patch: object) => why(read({ ...operatingWear, ...patch }));

  it("reads dated, closing receipts and tells absent from malformed", () => {
    const reading = read(operatingWear);
    expect(reading.status).toBe("ok");
    expect(readOperatingWear(snap({ workshops: {} }), 4)).toEqual({ status: "absent" });
    expect(why(readOperatingWear(snap({ operating_wear: operatingWear }, 9), 4))).toBe("misdated observation");
    expect(why(read(operatingWear, 3))).toBe("malformed wear receipt");
    expect(with_({ stage: "PL3" })).toBe("unknown operating-wear schema");
    const totals = wearTotals((reading as unknown as { record: never }).record)!;
    expect(totals).toMatchObject({ sites: 3, fullOffset: 1, covered: 2, stopping: 1 });
    expect(totals.net).toBeCloseTo(0.035);
  });

  it("refuses wear, condition and offsets that do not close", () => {
    const one = (patch: object) => with_({ receipts: [{ ...wearReceipts[0], ...patch }] });
    expect(one({ net_wear: 0.02 })).toBe("wear does not close");
    expect(one({ upkeep_offset: 0.03, net_wear: 0 })).toBe("wear does not close");
    expect(one({ condition_after: 0.6 })).toBe("condition does not close");
    expect(one({ full_offset: true })).toBe("the full-offset flag disagrees with the net wear");
    expect(one({ wear: 0.03, net_wear: 0.025 })).toBe("a receipt's wear is not the declared operating wear");
    expect(with_({ with_apprenticeship: false })).toBe("an offset without apprenticeship (nobody else qualifies anyone)");
    expect(with_({ receipts: [wearReceipts[0], wearReceipts[0]] })).toBe("a site was worn twice in one turn");
    expect(with_({ counters: { ...operatingWear.counters, net_wear: 0.4 } })).toBe("lifetime wear does not close");
    expect(with_({ counters: { ...operatingWear.counters, bogus: 1 } })).toBe("malformed counters");
  });

  it("keeps an unobserved turn unknown, and accepts the switch alone (no offset)", () => {
    const reading = read({ ...operatingWear, receipts: null });
    expect(reading.status === "ok" && reading.record.receipts).toBeNull();
    expect(reading.status === "ok" && wearTotals(reading.record)).toBeNull();
    const alone = { ...operatingWear, with_apprenticeship: false, receipts: [wearReceipts[2]],
      counters: { turns: 4, operating_site_turns: 2, wear: 0.04, net_wear: 0.04 } };
    expect(why(read(alone))).toBe("ok");
  });
});

describe("recovery crews reader", () => {
  const read = (x: unknown, regions = 4, civs = 2) => readRecoveryCrews(snap({ recovery_crews: x }), regions, civs);
  const with_ = (patch: object) => why(read({ ...recoveryCrews, ...patch }));
  const receipts = (first: object) => ({ receipts: [{ ...granaryCrew, ...first }, ...recoveryCrews.receipts.slice(1)] });

  it("reads a dated record whose wages and sunk coins close", () => {
    const reading = read(recoveryCrews);
    expect(reading.status).toBe("ok");
    expect(readRecoveryCrews(snap({}), 4, 2)).toEqual({ status: "absent" });
    expect(why(readRecoveryCrews(snap({ recovery_crews: recoveryCrews }, 11), 4, 2))).toBe("misdated observation");
    expect(with_({ mode: "volunteer" })).toBe("unknown recovery-crews schema");
    const totals = crewTotals((reading as unknown as { record: never }).record)!;
    expect(totals).toMatchObject({ coins: 3600, wages: 3500, sunk: 100, residual: 100, granaryCrews: 2, workshopCrews: 1,
      people: 5, short: 1, empty: 1 });
    expect(totals.withheld).toBeCloseTo(0.59);
  });

  it("refuses wages against coins that do not close", () => {
    expect(with_(receipts({ sunk_milli: 0 }))).toBe("granary coins do not close");
    expect(with_(receipts({ wages_due_milli: 3500, wage_residual_milli: 0, members: granaryCrew.members.map((m) => ({ ...m, wage_due_milli: m.wage_milli, wage_residual_milli: 0 })) })))
      .toBe("a paid crew was not paid the granary's coins");
    expect(with_(receipts({ members: [granaryCrew.members[0]] }))).toBe("member wages do not add up to the crew's");
    expect(with_(receipts({ delivered: 2.5 }))).toBe("granary work beyond its request");
    expect(with_(receipts({ farm_time_removed: 1 }))).toBe("farm time does not close");
    expect(with_(receipts({ members: [{ ...granaryCrew.members[0], origin: "veteran" }, granaryCrew.members[1]] })))
      .toBe("a granary crew member is not a farmer");
    expect(with_({ ledger: [{ ...recoveryCrews.ledger[0], wages_milli: 3600, sunk_milli: 0, wage_residual_milli: 0 }, recoveryCrews.ledger[1]] }))
      .toBe("crew ledger and receipts disagree");
    expect(with_({ ledger: null })).toBe("receipts without accounts");
    expect(with_({ counters: { ...recoveryCrews.counters, granary_sunk_milli: 0 } })).toBe("lifetime granary money does not close");
  });

  it("checks the recorded shortage flag against the planned work and the crew (PL3 review C)", () => {
    // Planned 2, crew farm time 1.8: 0.2 of the work is left, at least min_share, so the crew is short.
    expect(with_(receipts({ short: true }))).toBe("ok");
    expect(with_(receipts({ short: false }))).toBe("the shortage flag disagrees with the planned work and the crew");
    // A remainder below min_share names nobody and counts as covered.
    const covered = { planned: 1.8005, short: false };
    expect(with_(receipts(covered))).toBe("ok");
    expect(with_(receipts({ ...covered, short: true }))).toBe("the shortage flag disagrees with the planned work and the crew");
    const reading = read({ ...recoveryCrews, ...receipts(covered) });
    expect(reading.status === "ok" && crewTotals(reading.record)?.short).toBe(0);
    expect(with_({ receipts: [granaryCrew, recoveryCrews.receipts[1], { ...workshopCrew, short: true }] })).toBe("a workshop crew marked short");
  });

  it("refuses a person on two crews and workshop money on the crew receipt", () => {
    const twice = { ...workshopCrew, members: [{ ...workshopCrew.members[0], agent_id: 30 }, ...workshopCrew.members.slice(1)] };
    expect(with_({ receipts: [granaryCrew, recoveryCrews.receipts[1], twice] })).toBe("a person is on two crews");
    expect(with_({ receipts: [granaryCrew, recoveryCrews.receipts[1], { ...workshopCrew, coin_cost_milli: 100, sunk_milli: 100 }] }))
      .toBe("workshop crew money belongs to the RS2 receipt");
    const cityTime = { ...workshopCrew, members: [{ ...workshopCrew.members[0], farm_time: 0.2 }, ...workshopCrew.members.slice(1)],
      farm_time_removed: 0.4 };
    expect(with_({ receipts: [granaryCrew, recoveryCrews.receipts[1], cityTime] })).toBe("farm time removed for time already off the farm");
  });

  it("refuses wages paid by the unpaid control, and keeps unobserved turns unknown", () => {
    expect(with_({ mode: "unpaid", counters: { granary_coin_cost_milli: 7000, granary_sunk_milli: 7000 } }))
      .toBe("an unpaid crew was paid");
    const sunk = (r: typeof granaryCrew) => ({ ...r, wages_due_milli: 0, wages_milli: 0, wage_residual_milli: 0,
      sunk_milli: r.coin_cost_milli, members: r.members.map((m) => ({ ...m, wage_due_milli: 0, wage_milli: 0, wage_residual_milli: 0 })) });
    const control = { ...recoveryCrews, mode: "unpaid", receipts: [sunk(granaryCrew), recoveryCrews.receipts[1], workshopCrew],
      ledger: [{ ...recoveryCrews.ledger[0], wages_due_milli: 0, wages_milli: 0, wage_residual_milli: 0, sunk_milli: 3600 }, recoveryCrews.ledger[1]],
      counters: { granary_coin_cost_milli: 7000, granary_sunk_milli: 7000 } };
    expect(why(read(control))).toBe("ok");
    expect(why(read({ ...control, counters: { granary_coin_cost_milli: 7000, granary_wages_milli: 7000, granary_wages_due_milli: 7000 } })))
      .toBe("the unpaid control paid wages");
    const unknown = read({ ...recoveryCrews, receipts: null, ledger: null });
    expect(unknown.status === "ok" && crewTotals(unknown.record)).toBeNull();
  });
});

describe("maintenance obligation reader", () => {
  const read = (x: unknown, civs = 2) => readMaintenanceObligation(snap({ maintenance_obligation: x }), civs);
  const with_ = (patch: object) => why(read({ ...maintenanceObligation, ...patch }));

  it("reads dated decisions and uses that close", () => {
    const reading = read(maintenanceObligation);
    expect(reading.status).toBe("ok");
    expect(readMaintenanceObligation(snap({}), 2)).toEqual({ status: "absent" });
    expect(why(readMaintenanceObligation(snap({ maintenance_obligation: maintenanceObligation }, 12), 2))).toBe("misdated observation");
    expect(why(read(maintenanceObligation, 1))).not.toBe("ok");
    expect(obligationTotals((reading as unknown as { record: never }).record)).toEqual({ planned: 8, reserved: 7, capped: 1, used: 4,
      returned: 3, envelopeSpent: 3, charged: 7 });
  });

  it("refuses reservations beyond the cap and uses that do not close", () => {
    expect(with_({ decisions: [{ ...decisions[0], reserved: 6 }, decisions[1]] }))
      .toBe("a reservation is not the planned charges within the cap");
    expect(with_({ decisions: [{ ...decisions[0], cap: 6, reserved: 6 }, decisions[1]] }))
      .toBe("the cap is not the declared share of the budget");
    expect(with_({ uses: [{ ...uses[0], returned: 2 }, uses[1]] })).toBe("reserved is not used plus returned");
    expect(with_({ uses: [{ ...uses[0], envelope_spent: 2 }, uses[1]] }))
      .toBe("the charge is not the reservation's part plus the envelope's");
    expect(with_({ uses: [{ ...uses[0], envelope: 1 }, uses[1]] })).toBe("repairs spent beyond their envelope");
    // Pro rata, not the reservation first; the envelope's share of the work is recorded.
    expect(with_({ uses: [{ ...uses[0], used: 4, returned: 0, envelope_spent: 2 }, uses[1]] })).toBe("the charge is not split pro rata");
    expect(with_({ uses: [{ ...uses[0], envelope_share: 0.5 }, uses[1]] })).toBe("the charge is not split pro rata");
    expect(with_({ uses: [{ ...uses[0], envelope_share: 1.5 }, uses[1]] })).toBe("malformed reservation use");
    expect(with_({ uses: [{ ...uses[0], charged: 8, envelope_spent: 5 }, uses[1]] })).not.toBe("ok");
    // A record written before the split (no envelope_share) paid from the reservation first.
    const earlier = (u: typeof uses[number], used: number) => {
      const rest: Record<string, unknown> = { ...u, used, returned: u.reserved - used, envelope_spent: u.charged - used };
      delete rest.envelope_share;
      return rest;
    };
    expect(with_({ uses: [earlier(uses[0], 4), earlier(uses[1], 1)] })).toBe("ok");
    expect(with_({ uses: [earlier(uses[0], 3), earlier(uses[1], 1)] })).toBe("the reservation was not spent first");
    expect(with_({ uses: [uses[0], uses[0]] })).toBe("a civ has two uses");
    expect(with_({ counters: { ...maintenanceObligation.counters, charged_coins: 11 } })).toBe("lifetime charges do not close");
  });

  it("holds the reserve-only control to returning everything, and keeps unobserved turns unknown", () => {
    expect(with_({ mode: "reserve_only" })).not.toBe("ok");
    const control = { ...maintenanceObligation, mode: "reserve_only",
      uses: [{ ...uses[0], used: 0, returned: 4, envelope_spent: 6, envelope: 6, envelope_share: 1 },
        { ...uses[1], used: 0, returned: 3, envelope_spent: 1, envelope: 1, envelope_share: 1 }],
      counters: { reserved_coins: 15, returned_coins: 15, envelope_spent_coins: 7, charged_coins: 7 } };
    expect(why(read(control))).toBe("ok");
    expect(why(read({ ...control, uses: [{ ...control.uses[0], used: 1, returned: 3, envelope_spent: 5 }, control.uses[1]] })))
      .toBe("the reserve-only control spent its reservation");
    expect(why(read({ ...control, uses: [{ ...control.uses[0], envelope_share: 0.6 }, control.uses[1]] })))
      .toBe("the reserve-only control spent its reservation");
    const unknown = read({ ...maintenanceObligation, decisions: null, uses: null });
    expect(unknown.status === "ok" && obligationTotals(unknown.record).reserved).toBeNull();
  });
});

describe("productive-recovery readers on natural records", () => {
  it("accept every record of a default-mode, a control-mode and a graduates snapshot", async () => {
    type Natural = { turn: number; region_count: number; civ_count: number; livelihoods: Record<string, unknown> };
    const fixture = (await import("../../__fixtures__/productive_recovery_natural_records.json")).default as unknown as {
      snapshots: Natural[] };
    const [main, control, graduates, split] = fixture.snapshots;
    const at = (n: Natural) => n as unknown as TurnSnapshot;
    for (const n of [main, control]) {
      const s = at(n);
      for (const reading of [readTimberSupply(s, n.region_count, n.civ_count), readOperatingWear(s, n.region_count),
        readRecoveryCrews(s, n.region_count, n.civ_count), readMaintenanceObligation(s, n.civ_count),
        readApprenticeship(s, n.region_count)]) expect(why(reading)).toBe("ok");
      expect(localBudgetsAt(s, n.civ_count)).not.toBeNull();
    }
    const regions = main.region_count;
    const civs = main.civ_count;
    // Default modes: timber cut and delivered, paid crews, a reservation spent, RS1 schema 2 and RS2's no_people stall.
    const supply = readTimberSupply(at(main), regions, civs);
    expect(supply.status === "ok" && supply.record.mode).toBe("supply");
    expect(supply.status === "ok" && supply.record.counters.cut).toBeGreaterThan(0);
    expect(supply.status === "ok" && supply.record.closed.some((e) => e.status === "delivered" && e.delivered > 0)).toBe(true);
    const crews = readRecoveryCrews(at(main), regions, civs);
    expect(crews.status === "ok" && crews.record.receipts!.some((r) => r.kind === "granary" && r.wages_milli > 0)).toBe(true);
    const repair = repairProjectsAt(at(main), regions, civs);
    expect(repair?.receipts?.some((r) => r.reasons.includes("no_people"))).toBe(true);
    const rs1 = readApprenticeship(at(main), regions);
    expect(rs1.status === "ok" && rs1.record.schema_version).toBe(2);
    expect(rs1.status === "ok" && rs1.record.receipts!.some((r) => r.seats.some((s) => s.aboard === "attached"))).toBe(true);
    // Controls: nothing cut (crews come home empty: returned), crews unpaid with the coins sunk, reservations returned.
    const c = (n: Natural) => [at(n), n.region_count, n.civ_count] as const;
    const costOnly = readTimberSupply(...c(control));
    expect(costOnly.status === "ok" && [costOnly.record.mode, costOnly.record.counters.cut ?? 0]).toEqual(["cost_only", 0]);
    expect(costOnly.status === "ok" && costOnly.record.counters.wages_milli).toBeGreaterThan(0);
    expect(costOnly.status === "ok" && costOnly.record.closed.some((e) => e.status === "returned")).toBe(true);
    expect(costOnly.status === "ok" && costOnly.record.closed.every((e) => e.status !== "delivered")).toBe(true);
    const unpaid = readRecoveryCrews(...c(control));
    expect(unpaid.status === "ok" && unpaid.record.mode).toBe("unpaid");
    expect(unpaid.status === "ok" && unpaid.record.ledger!.every((l) => l.wages_milli === 0 && l.sunk_milli === l.coin_cost_milli)).toBe(true);
    const reserveOnly = readMaintenanceObligation(at(control), control.civ_count);
    expect(reserveOnly.status === "ok" && reserveOnly.record.uses!.every((u) => u.used === 0 && u.returned === u.reserved)).toBe(true);
    const nq = readApprenticeship(at(control), control.region_count);
    expect(nq.status === "ok" && nq.record.mode).toBe("no_qualification");
    // The reservation lowers the bargained budget by at most the reservation.
    for (const n of [main, control]) {
      const mo = readMaintenanceObligation(at(n), n.civ_count);
      const l9 = localBudgetsAt(at(n), n.civ_count)!;
      for (const d of mo.status === "ok" ? mo.record.decisions! : []) {
        const budget = l9.decisions!.find((x) => x.civ === d.civ && x.turn === d.turn)!.budget;
        expect(d.budget_before - budget).toBeGreaterThanOrEqual(0);
        expect(d.budget_before - budget).toBeLessThanOrEqual(d.reserved);
      }
    }
    // A natural pro-rata split: the reservation pays floor(charged x reserved / (reserved + envelope)).
    const prorata = readMaintenanceObligation(at(split), split.civ_count);
    expect(why(prorata)).toBe("ok");
    expect(prorata.status === "ok" && prorata.record.uses!.some((u) => u.used > 0 && (u.envelope_share ?? 1) < 1)).toBe(true);
    const grads = readApprenticeship(at(graduates), graduates.region_count);
    expect(grads.status === "ok" && grads.record.graduates!.length).toBeGreaterThan(0);
    // The same records misdated are refused.
    const shifted = { ...main, turn: main.turn + 1 } as unknown as TurnSnapshot;
    expect(why(readTimberSupply(shifted, regions, civs))).toBe("misdated observation");
    expect(why(readRecoveryCrews(shifted, regions, civs))).toBe("misdated observation");
  });
});
