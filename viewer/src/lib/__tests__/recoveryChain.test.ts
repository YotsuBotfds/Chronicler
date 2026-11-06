import { describe, expect, it } from "vitest";
import {
  budgetLimits, fullestChainRegion, chainTotals, farmLabourAway, hasRecoveryChain, incomplete, LINKS, linkState, moreRowsLabel,
  packagesOn, paidWorkers,
  readChainSnapshots, regionChain, type ChainTurn,
} from "../recoveryChain";
import type { Bundle } from "../../types";
import {
  chainBundle, emptyGranaryCrew, IRON_PEAKS, refusedWage, SAPPHIRE, TURNS, unpaidWoodcutting, without, workshopProject,
} from "./recoveryChainFixture";

const chain = (bundle: Bundle, region = SAPPHIRE) => regionChain(readChainSnapshots(bundle).snapshots, region);
const at = (turns: ChainTurn[], turn: number) => turns.find((t) => t.turn === turn)!;
const known = <T,>(cell: { state: string; value?: T }): T => {
  expect(cell.state).toBe("known");
  return cell.value as T;
};

describe("recovery chain over natural records (template seed 23)", () => {
  const bundle = chainBundle();
  const turns = chain(bundle);

  it("reads every package of every snapshot with its own reader", () => {
    const { on, snapshots } = readChainSnapshots(bundle);
    expect(Object.values(on).every(Boolean)).toBe(true);
    expect(snapshots.map((s) => s.turn)).toEqual(TURNS);
    for (const s of snapshots) for (const [key, cell] of Object.entries(s.packages)) expect(`${s.turn} ${key} ${cell.state}`).toBe(`${s.turn} ${key} known`);
    expect(hasRecoveryChain(bundle)).toBe(true);
    expect(fullestChainRegion(snapshots, 8)).toBe(SAPPHIRE);
  });

  it("follows the stall, the expedition, the delivery, the repair, the wages and the purchases", () => {
    // Snapshot 15: the granary project stalls for want of timber while expedition 0's crew is on the road.
    const t15 = at(turns, 15);
    expect(known(t15.repair).receipts).toEqual([expect.objectContaining({ pid: 0, kind: "granary", status: "stalled", reasons: ["no_timber"] })]);
    expect(linkState(t15, "repair")).toBe("tradeoff");
    expect(known(t15.expedition).expeditions.map((e) => [e.eid, e.stage, e.crew])).toEqual([[0, "cutting", [17, 19, 22, 34]]]);
    expect(known(known(t15.wages).pl1).rows).toEqual([expect.objectContaining({ eid: 0, people: [17, 19, 22, 34], wagesMilli: 2000, farmTime: 4 })]);
    expect(known(t15.retail).frame?.opened_turn).toBe(14);
    expect(known(t15.retail).frame?.provisioning?.persons).toBe(50);
    // Snapshot 27: expedition 1 delivered 15.17 timber into the region's store.
    const t27 = at(turns, 27);
    expect(known(t27.expedition).delivered).toBeCloseTo(15.1684, 4);
    expect(known(t27.store).store).toEqual(expect.objectContaining({ region: SAPPHIRE, delivered: expect.closeTo(15.1684, 4), held: 0 }));
    // Snapshot 28: the store holds 4 for project 0 alone; PL3 pays the named granary crew; the granary is repaired.
    const t28 = at(turns, 28);
    expect(known(t28.store).holders).toEqual([{ pid: 0, held: 4, used: 4 }]);
    expect(known(known(t28.wages).pl3).rows).toEqual([expect.objectContaining({ pid: 0, people: [3, 13, 15, 20], wagesMilli: 8000, farmTime: 4 })]);
    const g = known(t28.granary);
    expect(g.asset).toEqual(expect.objectContaining({ condition: expect.closeTo(0.8222, 4) }));
    expect(g.receipt?.condition_before).toBeCloseTo(0.7322, 4);
    expect(farmLabourAway(t28)).toEqual({ pl1: 0, granary: 4, workshop: 0 });
    // Snapshot 29: the project completed in that source turn (listed among closed).
    const t29 = at(turns, 29);
    expect(known(t29.repair).projects).toEqual([expect.objectContaining({ pid: 0, status: "completed", closedNow: true })]);
    expect(known(t29.granary).project).toEqual(expect.objectContaining({ pid: 0, closedNow: true }));
  });

  it("sums the region's run over known snapshots", () => {
    const totals = chainTotals(turns);
    expect(totals.expeditions).toEqual([0, 1]);
    expect(totals.delivered).toBeCloseTo(15.1684, 4);
    expect(totals.wagesMilli).toEqual({ pl3: 26568, rs2: 0, pl1: 14500 });
    expect(totals.stalls).toBe(4);
    expect(totals.stallsNoTimber).toBe(4);
    expect(totals.pricedOutSnapshots).toBe(0);
    expect(Object.values(totals.unknown).every((n) => n === 0)).toBe(true);
  });

  it("puts each expedition in its home region only, and the forest account by slot", () => {
    // Expedition 2 (home Iron Peaks) cuts Thornwood at snapshot 28; Sapphire Coast's chain does not show it.
    const iron = at(chain(bundle, IRON_PEAKS), 28);
    const slots = known(iron.forest).slots!;
    expect(slots).toHaveLength(1);
    expect(slots[0]).toEqual(expect.objectContaining({ eid: 2, forest: 5, slot: 0 }));
    expect(slots[0].l3).toEqual(expect.objectContaining({ region_id: 5, slot: 0, extraction: expect.closeTo(0.6583, 4) }));
    expect(slots[0].stockAfter!).toBeLessThan(slots[0].stockBefore!);
    expect(linkState(iron, "forest")).toBe("tradeoff");
    expect(known(at(turns, 28).forest).slots).toEqual([]);
    expect(known(at(turns, 28).expedition).expeditions).toEqual([]);
    // At snapshot 23 Sapphire Coast's crew cut at Mistwood, whose stock still rose (regrowth outweighed the cut).
    const cut = known(at(turns, 23).forest).slots!;
    expect(cut.map((s) => [s.eid, s.forest])).toEqual([[1, 6]]);
    expect(linkState(at(turns, 23), "forest")).toBe("active");
  });

  it("matches the person sample by id to workers paid in the region at this or an earlier snapshot", () => {
    // A turn's Phase 2 wages are paid before that turn's provisioning. Woodcutter 2 is sampled at 20, first paid at
    // 21 (expedition 1): not matched at 20, matched from 21. Granary crew member 15 is sampled at 21-23 and first
    // paid at 26: matched only from 26.
    expect(known(at(turns, 20).retail).matches.map((m) => m.agentId)).not.toContain(2);
    expect(paidWorkers(at(turns, 21).wages)).toContain(2);
    expect(known(at(turns, 21).retail).matches).toContainEqual(expect.objectContaining({ agentId: 2, who: "self", since: 21 }));
    for (const turn of [21, 22, 23]) expect(known(at(turns, turn).retail).matches.map((m) => m.agentId)).not.toContain(15);
    expect(known(at(turns, 26).retail).matches).toContainEqual(expect.objectContaining({ agentId: 15, since: 26 }));
    const m22 = known(at(turns, 22).retail).matches;
    expect(m22).toContainEqual(expect.objectContaining({ agentId: 2, who: "self", worker: 2, status: "fed", since: 21 }));
    // Person 20 is sampled in the household keyed by woodcutter 13.
    expect(m22).toContainEqual(expect.objectContaining({ agentId: 20, household: 13, who: "household", worker: 13 }));
    expect(m22.every((m) => [2, 3, 13, 14, 17, 19, 22, 23, 27, 34, 35, 36, 40].includes(m.worker))).toBe(true);
    // Nobody is matched before anyone in the region has been paid.
    expect(known(at(turns, 13).retail).matches).toEqual([]);
  });
});

describe("off, unknown and zero", () => {
  it("is off only when no snapshot of the run records the package", () => {
    const turns = chain(chainBundle(without("remittances")));
    expect(packagesOn(chainBundle(without("remittances")).history).remittances).toBe(false);
    for (const t of turns) {
      expect(t.remittances.state).toBe("off");
      expect(linkState(t, "remittances")).toBe("off");
    }
  });

  it("is unknown when the package is on but this snapshot does not record it", () => {
    const turns = chain(chainBundle((s) => { if (s.turn === 28) delete s.livelihoods.remittances; }));
    expect(at(turns, 28).remittances).toEqual({ state: "unknown", reason: "no Remittances (RS4) record at this snapshot" });
    expect(linkState(at(turns, 28), "remittances")).toBe("unknown");
    expect(at(turns, 27).remittances.state).toBe("known");
    expect(chainTotals(turns).unknown.remittances).toBe(1);
  });

  it("records nothing happened as known and empty, never as unknown", () => {
    const t13 = at(chain(chainBundle()), 13);
    expect(known(t13.retail).frame).toBeNull();                       // not a pilot region yet
    expect(linkState(t13, "retail")).toBe("none");
    expect(known(t13.remittances).row).toEqual(expect.objectContaining({ inflow_milli: 0 }));
    expect(linkState(t13, "remittances")).toBe("none");
    const wages = known(t13.wages);
    expect([known(wages.pl3).rows, known(wages.rs2).rows, known(wages.pl1).rows]).toEqual([[], [], []]);
    expect(linkState(t13, "wages")).toBe("none");
  });

  it("treats a null frame as unknown, not zero (constructed: snapshot 28's frames blanked)", () => {
    const turns = chain(chainBundle((s) => {
      if (s.turn !== 28) return;
      Object.assign(s.livelihoods.household_retail, { regions: null, money: null, income: null, sample: null, sample_dropped: null });
      Object.assign(s.livelihoods.recovery_crews, { receipts: null, ledger: null });
    }));
    const t28 = at(turns, 28);
    expect(t28.retail.state).toBe("unknown");
    expect(linkState(t28, "retail")).toBe("unknown");
    expect(t28.food.state).toBe("unknown");
    const wages = known(t28.wages);
    expect(wages.pl3.state).toBe("unknown");
    expect(wages.pl1.state).toBe("known");
    expect(linkState(t28, "wages")).toBe("unknown");
    expect(incomplete(t28, "wages")).toBe(true);
    // The run totals leave the unknown snapshot out and say so.
    const totals = chainTotals(turns);
    expect(totals.wagesMilli.pl3).toBe(26568 - 8000);
    expect(totals.unknown.wages).toBe(1);
    expect(totals.unknown.retail).toBe(1);
    expect(totals.farmAwayUnknown).toBe(1);
    expect(totals.farmAway.granary).toBeCloseTo(13.2823 - 4, 3);
  });

  it("does not draw unknown work as recorded (constructed: RS2 and PL1 receipts blanked)", () => {
    const turns = chain(chainBundle((s) => {
      if (s.turn === 28) Object.assign(s.livelihoods.repair_projects, { receipts: null, ledger: null });
      if (s.turn === 20) Object.assign(s.livelihoods.timber_supply, { receipts: null, ledger: null });
    }));
    // RS2: project 0 is listed open, but whether it worked or stalled is unknown; so is whose timber the store held.
    const t28 = at(turns, 28);
    expect(known(t28.repair).receipts).toBeNull();
    expect(linkState(t28, "repair")).toBe("unknown");
    expect(known(t28.store).holders).toBeNull();
    expect(incomplete(t28, "store")).toBe(true);
    expect(known(t28.granary).receiptKnown).toBe(false);
    // PL1: expeditions are listed, their crews' work and farm labour away are unknown, never zero.
    const t20 = at(turns, 20);
    expect(known(t20.expedition).receipts).toBeNull();
    expect(incomplete(t20, "expedition")).toBe(true);
    expect(farmLabourAway(t20).pl1).toBeNull();
    expect(known(t20.forest).slots).toBeNull();
    const totals = chainTotals(turns);
    expect(totals.unknown.repair).toBe(1);
    expect(totals.unknown.store).toBe(1);
    expect(totals.unknown.expedition).toBe(1);
    expect(totals.farmAwayUnknown).toBe(1);                     // PL1 at 20 (RS2 receipts carry no farm time)
    expect(totals.farmAway.pl1).toBeCloseTo(21.8 - 2, 3);
    expect(totals.stalls).toBe(4);                               // the stalls at 15 and 21-23 are still known
  });

  it("counts an unprovisioned pilot as unknown, but not the record-only control's (constructed on the reader's output)", () => {
    const turns = chain(chainBundle());
    const t22 = structuredClone(at(turns, 22));
    const retail = known(t22.retail);
    retail.frame = { ...retail.frame!, provisioning: null };
    expect(linkState(t22, "retail")).toBe("unknown");
    expect(chainTotals([t22]).unknown.retail).toBe(1);
    retail.mode = "record_only";
    expect(linkState(t22, "retail")).toBe("active");
    expect(chainTotals([t22]).unknown.retail).toBe(0);
  });

  it("counts a forest slot without its L3 account as partly unknown (constructed: L3 not settled at 23)", () => {
    const turns = chain(chainBundle((s) => {
      if (s.turn === 23) Object.assign(s.livelihoods.timber_stock, { observed: false, regions: null, totals: null });
    }));
    const forest = known(at(turns, 23).forest);
    expect(forest.slots).toEqual([expect.objectContaining({ eid: 1, forest: 6, l3: null })]);
    expect(forest.l3Missing).toBe("no L3 account was settled in the source turn");
    expect(incomplete(at(turns, 23), "forest")).toBe(true);
    expect(incomplete(at(chain(chainBundle()), 23), "forest")).toBe(false);
    expect(chainTotals(turns).unknown.forest).toBe(1);
  });

  it("keeps a reader's refusal as malformed with its reason, and an unreadable livelihoods record as malformed", () => {
    const turns = chain(chainBundle((s) => {
      if (s.turn === 28) s.livelihoods.timber_supply.source_turn = 30;
      if (s.turn === 29) s.livelihoods.schema_version = 99;
      if (s.turn === 27) delete s.livelihoods;
    }));
    expect(at(turns, 28).expedition).toEqual({ state: "malformed", reason: "the Timber supply (PL1) record was rejected: misdated observation" });
    expect(linkState(at(turns, 28), "expedition")).toBe("unknown");
    expect(known(at(turns, 28).wages).pl1.state).toBe("malformed");
    expect(at(turns, 29).repair.state).toBe("malformed");
    expect(at(turns, 27).repair).toEqual({ state: "unknown", reason: "no livelihoods record at this snapshot" });
    // Granary storage is outside livelihoods: still read at 27.
    expect(known(at(turns, 27).granary).asset).toEqual(expect.objectContaining({ condition: expect.closeTo(0.7322, 4) }));
    expect(known(at(turns, 27).granary).project).toBe("unknown");
  });

  it("does not let a frame that dropped need rows claim the region had no need", () => {
    const turns = chain(chainBundle((s) => {
      const ts = s.livelihoods.timber_supply;
      if (s.turn === 28) { ts.needs = ts.needs.filter((n: { region: number }) => n.region !== 7); ts.needs_dropped = 1; }
    }));
    expect(known(at(turns, 28).expedition).need).toBeNull();
    const control = chain(chainBundle((s) => {
      const ts = s.livelihoods.timber_supply;
      if (s.turn === 28) ts.needs = ts.needs.filter((n: { region: number }) => n.region !== 7);
    }));
    expect(known(at(control, 28).expedition).need).toBe("none");
  });
});

it("counts a snapshot with one wage source unknown as unknown in the run totals (constructed)", () => {
  // Snapshot 20 pays both a PL3 granary crew and expedition 0's woodcutters; blank PL3's receipts there.
  const turns = chain(chainBundle((s) => {
    if (s.turn === 20) Object.assign(s.livelihoods.recovery_crews, { receipts: null, ledger: null });
  }));
  const t20 = at(turns, 20);
  expect(linkState(t20, "wages")).toBe("active");          // the woodcutters' wages are known
  expect(incomplete(t20, "wages")).toBe(true);
  expect(chainTotals(turns).unknown.wages).toBe(1);
  expect(chainTotals(turns).wagesMilli.pl3).toBe(26568 - 6538);
  expect(incomplete(at(chain(chainBundle()), 20), "wages")).toBe(false);
});

describe("links joined by id and by region", () => {
  it("declares which links the records join by stable id and which only by region", () => {
    expect(Object.fromEntries(LINKS.map((l) => [l.key, l.join]))).toEqual({
      repair: "id", expedition: "region", forest: "id", store: "region", granary: "id", wages: "id", retail: "region", remittances: "region" });
    for (const l of LINKS) expect(l.joined.startsWith(l.join === "id" ? "by id: " : "by region only: ")).toBe(true);
  });

  it("joins the granary to its project by kind and asset, not to any project in the region", () => {
    // Constructed: workshop projects listed first in Sapphire Coast (beside granary project 0) and in Mistwood
    // (which has no granary project). A join by region alone would take the workshop projects.
    const turns = (region: number) => chain(chainBundle((s) => {
      if (s.turn === 28) { workshopProject(s, 99, 3, SAPPHIRE); workshopProject(s, 97, 4, 6); }
    }), region);
    expect(known(at(turns(SAPPHIRE), 28).repair).projects.map((p) => p.pid)).toEqual([99, 0]);
    expect(known(at(turns(SAPPHIRE), 28).granary).project).toEqual(expect.objectContaining({ pid: 0, kind: "granary", asset: SAPPHIRE }));
    expect(known(at(turns(6), 28).repair).projects.map((p) => p.pid)).toEqual([97]);
    expect(known(at(turns(6), 28).granary).project).toBeNull();
  });

  it("counts a workshop crew's wages once, from its RS2 receipt (PL3 records them as zero)", () => {
    // Constructed: snapshot 28 gains a workshop project's RS2 receipt in region 7 and its PL3 crew (people 50 and 51).
    const turns = chain(chainBundle((s) => {
      if (s.turn !== 28) return;
      const rp = s.livelihoods.repair_projects;
      rp.receipts.push({ ...rp.receipts[0], pid: 99, kind: "workshop", asset: 3, region: 7, payer: 0, status: "progress", reasons: [],
        requested: 0.4, delivered: 0.4, credited: 0.4, crew: [50, 51], qualified: [], veterans: [], share: 0.2, rate: 1,
        timber_held: 0, timber_used: 0, timber_returned: 0, wages_due_milli: 400, wages_milli: 400, wage_residual_milli: 0,
        coin_cost_milli: 0 });
      const ledger = rp.ledger.find((l: { civ: number }) => l.civ === 0);
      // Paid from the civ's prepaid remainder (557 milli): 8 x 1000 + 557 = 8000 + 400 + 157.
      ledger.projects += 1; ledger.wages_due_milli += 400; ledger.wages_applied_milli += 400; ledger.prepaid_after_milli -= 400;
      rp.prepaid["0"] -= 400;
      const rc = s.livelihoods.recovery_crews;
      rc.receipts.push({ turn: 27, pid: 99, kind: "workshop", region: 7, payer: 0, eligible: 4, eligible_site_city: 1, planned: 0,
        capacity: 0, requested: 0.4, delivered: 0.4, coin_cost_milli: 0, wages_due_milli: 0, wages_milli: 0,
        wage_residual_milli: 0, sunk_milli: 0, farm_time_removed: 0.4,
        members: [50, 51].map((agent_id) => ({ agent_id, origin: "rural_farmer", share: 0.2, worked: 0.2, farm_time: 0.2,
          veteran: false, wage_due_milli: 0, wage_milli: 0, wage_residual_milli: 0, income_replaced: 0 })) });
    }));
    const t28 = at(turns, 28);
    const wages = known(t28.wages);
    expect(known(wages.rs2).rows).toEqual([expect.objectContaining({ source: "rs2_workshop", pid: 99, people: [50, 51], wagesMilli: 400 })]);
    expect(known(wages.pl3).rows.map((r) => r.pid)).toEqual([0]);   // the granary crew only
    expect(chainTotals(turns).wagesMilli).toEqual({ pl3: 26568, rs2: 400, pl1: 14500 });
    // The workshop crew's farm time is PL3's: counted as farm labour taken, by source.
    expect(known(wages.pl3).workshops).toEqual([{ pid: 99, people: [50, 51], farmTime: 0.4 }]);
    expect(farmLabourAway(t28)).toEqual({ pl1: 0, granary: 4, workshop: 0.4 });
    expect(chainTotals(turns).farmAway.workshop).toBeCloseTo(0.4, 9);
    expect(paidWorkers(t28.wages)).toEqual(expect.arrayContaining([50, 51]));
  });
});

describe("a run with only some of the switches (constructed from the natural records)", () => {
  it("repair projects and crews without timber supply, retail or remittances", () => {
    const bundle = chainBundle(without("timber_supply", "timber_stock", "household_retail", "remittances", "food_allocation"));
    const { on } = readChainSnapshots(bundle);
    expect(on).toEqual({ repair_projects: true, timber_supply: false, timber_stock: false, grain_storage: true, recovery_crews: true,
      household_retail: false, remittances: false, food_allocation: false });
    expect(hasRecoveryChain(bundle)).toBe(true);
    const t28 = at(chain(bundle), 28);
    for (const key of ["expedition", "forest", "store", "retail", "remittances"] as const) {
      expect(t28[key].state).toBe("off");
      expect(linkState(t28, key)).toBe("off");
    }
    expect(t28.forest).toEqual({ state: "off", reason: "Timber supply (PL1) is off in this run (--timber-supply not recorded)" });
    const wages = known(t28.wages);
    expect(wages.pl1.state).toBe("off");
    expect(known(wages.pl3).rows).toHaveLength(1);
    expect(linkState(t28, "granary")).toBe("active");
    expect(budgetLimits(t28)).toEqual([]);
  });

  it("household retail alone keeps the chain view, with the repair links off", () => {
    const bundle = chainBundle(without("repair_projects", "timber_supply", "timber_stock", "recovery_crews", "grain_storage", "remittances"));
    expect(hasRecoveryChain(bundle)).toBe(true);
    const t22 = at(chain(bundle), 22);
    expect(t22.repair.state).toBe("off");
    expect(t22.wages.state).toBe("off");
    expect(t22.granary.state).toBe("off");
    expect(known(t22.retail).frame?.provisioning?.persons).toBe(50);
    // With no wage source on, nobody counts as paid, so no sample row is matched.
    expect(known(t22.retail).matches).toEqual([]);
  });

  it("does not mount for a run with none of the chain's anchor packages", () => {
    expect(hasRecoveryChain(chainBundle(without("repair_projects", "timber_supply", "recovery_crews", "household_retail")))).toBe(false);
    expect(hasRecoveryChain({ world_state: { regions: [] } } as unknown as Bundle)).toBe(false);
  });
});

describe("tradeoffs", () => {
  it("names budget limits by link (constructed: a no_coins stall, a recall, an unpaid woodcutting turn, a refused wage)", () => {
    const turns = chain(chainBundle((s) => {
      if (s.turn === 15) s.livelihoods.repair_projects.receipts.find((r: { pid: number }) => r.pid === 0).reasons = ["no_timber", "no_coins"];
      if (s.turn === 14) s.livelihoods.timber_supply.receipts.find((r: { eid: number }) => r.eid === 0).recalled = true;
      if (s.turn === 21) unpaidWoodcutting(s, 1);
      if (s.turn === 28) refusedWage(s, 0, 20, 2000);
    }));
    expect(budgetLimits(at(turns, 15))).toEqual([{ link: "repair", text: "project #0 stalled: treasury short" }]);
    expect(budgetLimits(at(turns, 14))).toEqual([{ link: "expedition", text: "expedition #0 recalled: the treasury could not pay" }]);
    expect(budgetLimits(at(turns, 21))).toEqual([{ link: "expedition", text: "expedition #1 unpaid this turn" }]);
    expect(budgetLimits(at(turns, 28))).toEqual([{ link: "wages", text: "2 coins of wages refused by the wealth ceiling" }]);
    expect(budgetLimits(at(chain(chainBundle()), 21))).toEqual([]);
    // Nobody on an unpaid turn, and no member whose own wage was refused, counts as paid.
    const t21 = at(turns, 21);
    expect(known(known(t21.wages).pl1).rows).toEqual([expect.objectContaining({ eid: 1, unpaid: true, wagesMilli: 0, paid: [] })]);
    expect(paidWorkers(t21.wages)).toEqual([]);
    expect(known(t21.retail).matches.map((m) => m.agentId)).not.toContain(2);
    const t28 = known(known(at(turns, 28).wages).pl3).rows[0];
    expect(t28).toEqual(expect.objectContaining({ people: [3, 13, 15, 20], paid: [3, 13, 15], wagesMilli: 6000, refusedMilli: 2000 }));
  });

  it("counts farm labour away from PL1 woodcutters and PL3 granary and workshop crews, by source", () => {
    const t20 = at(chain(chainBundle()), 20);
    expect(farmLabourAway(t20).pl1).toBe(2);
    expect(farmLabourAway(t20).granary).toBeCloseTo(3.2687, 4);
    expect(farmLabourAway(t20).workshop).toBe(0);
    const totals = chainTotals(chain(chainBundle()));
    expect(totals.farmAway.pl1).toBeCloseTo(21.8, 3);
    expect(totals.farmAway.granary).toBeCloseTo(13.2823, 3);
    expect(totals.farmAwayUnknown).toBe(0);
    // With timber supply off, the PL3 crews' farm labour is still counted.
    const off = chainTotals(chain(chainBundle(without("timber_supply", "timber_stock"))));
    expect(off.farmAway).toEqual({ pl1: 0, granary: expect.closeTo(13.2823, 3), workshop: 0 });
    expect(farmLabourAway(at(chain(chainBundle(without("timber_supply", "timber_stock"))), 20)).pl1).toBe("off");
  });

  it("shows no crew formed as nothing paid, not as a paid row (constructed: an empty granary crew in Mistwood)", () => {
    const t28 = at(chain(chainBundle((s) => { if (s.turn === 28) emptyGranaryCrew(s, 98, 6); }), 6), 28);
    const pl3 = known(known(t28.wages).pl3);
    expect(pl3.rows).toEqual([]);
    expect(pl3.noCrew).toEqual([{ pid: 98, planned: 1 }]);
    expect(linkState(t28, "wages")).toBe("none");
  });
});

it("labels the turn table's pager by the rows not yet shown", () => {
  expect(moreRowsLabel(12, 25)).toBe("Show the last 12");
  expect(moreRowsLabel(25, 25)).toBe("Show the last 25");
  expect(moreRowsLabel(37, 25)).toBe("Show 25 more (37 not shown)");
});
