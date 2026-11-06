import { describe, expect, it } from "vitest";
import v2 from "../../__fixtures__/household_retail_v2_records.json";
import type { TurnSnapshot } from "../../types";
import { readHouseholdRetail, type HouseholdRetailRecord, type RetailRegionFrame } from "../householdRetail";
import { COHORT_FIELDS, COHORT_GROUPS, readCohorts, readWarLosses, rulesVersion } from "../householdRetailEvidence";
import { snapOf } from "./householdRetailFixture";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Natural = { label: string; run: string; turn: number; region_count: number; livelihoods: Record<string, any> };
const SNAPSHOTS = (v2 as unknown as { snapshots: Natural[] }).snapshots;
const RUNS = ["war3", "war3c", "ro3", "pw7", "sched7", "v1pw7"] as const;
type Run = typeof RUNS[number];
const natural = (run: Run) => SNAPSHOTS[RUNS.indexOf(run)];
const raw = (run: Run): Record<string, any> => structuredClone(natural(run).livelihoods.household_retail);
const why = (reading: { status: string; reason?: string }) => reading.status === "malformed" ? reading.reason : reading.status;
const ok = (x: unknown, regions: number): HouseholdRetailRecord => {
  const reading = readHouseholdRetail(snapOf(x), regions);
  if (reading.status !== "ok") throw new Error(why(reading));
  return reading.record;
};
const read = (run: Run, change?: (x: Record<string, any>) => void) => {
  const x = raw(run);
  change?.(x);
  return ok(x, natural(run).region_count);
};
const frame = (record: HouseholdRetailRecord, region: number) => record.regions!.find((r) => r.region === region)!;

describe("v2 natural records", () => {
  it("are accepted by the strict reader, the schedule boundary included", () => {
    expect(SNAPSHOTS.map((s) => s.run)).toEqual([...RUNS]);
    for (const s of SNAPSHOTS) expect(why(readHouseholdRetail(s as unknown as TurnSnapshot, s.region_count)), s.label).toBe("ok");
    expect(RUNS.map((run) => `${read(run).boundary}/${rulesVersion(read(run))}`)).toEqual(
      ["all/2", "all/2", "all/2", "paid_work/2", "schedule/2", "paid_work/1"]);
    const sched = raw("sched7");
    expect(sched.schedule.sha256).toMatch(/^[0-9a-f]{64}$/);
    // The schedule replays the paid run's openings: the same opened_turn.
    expect(sched.opened_turn).toEqual(raw("pw7").opened_turn);
    expect(Object.keys(sched.schedule.turns).map(Number)).toEqual(Object.keys(sched.opened_turn).map(Number));
  });
});

describe("war losses of owned food", () => {
  it("read cause, actor and victim from version-2 records", () => {
    const siege = readWarLosses(read("war3"), 4);
    expect(siege.status).toBe("ok");
    if (siege.status !== "ok") return;
    expect(siege.losses.map((w) => [w.turn, w.region, w.cause, w.actorName, w.victimName])).toEqual([
      [0, 1, "siege", "Dorrathi Clans", "Ashkari Nomads"], [1, 1, "siege", "Dorrathi Clans", "Ashkari Nomads"],
      [2, 1, "siege", "Dorrathi Clans", "Ashkari Nomads"], [2, 1, "occupation", "Dorrathi Clans", "Ashkari Nomads"]]);
    expect(siege.losses.every((w) => w.milli > 0 && w.actor !== null && w.victim !== null)).toBe(true);
    const cession = readWarLosses(read("war3c"), 4);
    expect(cession.status === "ok" && cession.losses.at(-1)).toMatchObject({ cause: "conquest", turn: 3, note: expect.stringMatching(/ceded by treaty/) });
  });

  it("keep the record-only control's war exposure as recorded zeros and refuse broken records", () => {
    const control = readWarLosses(read("ro3"), 4);
    expect(control.status === "ok" && control.losses.map((w) => [w.cause, w.milli])).toEqual(
      [["siege", 0], ["siege", 0], ["siege", 0], ["occupation", 0]]);
    expect(readWarLosses(read("v1pw7"), 10)).toEqual({ status: "disabled" });
    const lossAt = (x: Record<string, any>) => x.log.find((r: any) => r.kind === "war_loss");
    expect(why(readWarLosses(read("war3", (x) => { lossAt(x).cause = "raid"; }), 4))).toBe("a war loss without a valid cause, actor or victim");
    expect(why(readWarLosses(read("war3", (x) => { lossAt(x).actor = 9; }), 4))).toBe("a war loss without a valid cause, actor or victim");
    expect(why(readWarLosses(read("war3", (x) => { lossAt(x).victim_name = null; }), 4))).toBe("a war loss without a valid cause, actor or victim");
    expect(why(readWarLosses(read("war3", (x) => { x.counters.war_loss_siege_milli += 1; }), 4)))
      .toBe("the war losses by cause do not add up to the total");
  });
});

describe("household-group cohorts", () => {
  it("read exact groups that add up to the region, recorded zeros as zeros and unknowns with their reasons", () => {
    const pw = read("pw7");
    const crewRegion = readCohorts(pw, frame(pw, 17));
    expect(crewRegion.status).toBe("ok");
    if (crewRegion.status !== "ok") return;
    const g = crewRegion.cohorts.groups;
    expect(Object.keys(g)).toEqual([...COHORT_GROUPS]);
    expect(g.crew).toMatchObject({ persons: 3, wages_milli: 3941 });
    expect(crewRegion.cohorts.unknown).toEqual({});
    expect(COHORT_GROUPS.reduce((a, k) => a + (g[k].persons as number), 0)).toBe(frame(pw, 17).provisioning!.persons);
    const unknownPersons = readCohorts(pw, frame(pw, 11));
    expect(unknownPersons.status === "ok" && unknownPersons.cohorts.groups.crew.persons).toBeNull();
    expect(unknownPersons.status === "ok" && unknownPersons.cohorts.unknown.persons).toMatch(/^the Phase 2 roster lists 49, the tick provisioned 48/);
    // A group nobody belongs to is a recorded zero, not unknown.
    expect(unknownPersons.status === "ok" && unknownPersons.cohorts.groups.crew.wages_milli).toBe(0);
  });

  it("keep disabled, absent, unobserved and malformed apart", () => {
    const v1 = read("v1pw7");
    expect(readCohorts(v1, v1.regions![0])).toEqual({ status: "disabled" });
    const ro = read("ro3");
    expect(readCohorts(ro, ro.regions![0])).toEqual({ status: "disabled" });
    const pw = read("pw7");
    const notProvisioned = { ...frame(pw, 17), provisioning: null, cohorts: undefined } as unknown as RetailRegionFrame;
    expect(readCohorts(pw, notProvisioned)).toEqual({ status: "unobserved" });
    const before = read("pw7", (x) => { for (const r of x.regions) delete r.cohorts; });
    expect(readCohorts(before, frame(before, 17))).toEqual({ status: "absent" });
    const broken = (change: (c: Record<string, any>) => void) => {
      const record = read("pw7", (x) => change(x.regions.find((r: any) => r.region === 17).cohorts));
      return why(readCohorts(record, frame(record, 17)));
    };
    expect(broken((c) => { c.groups.crew.persons = null; })).toBe("an unknown persons without its reason");
    expect(broken((c) => { c.groups.other.persons += 1; })).toBe("the groups' persons do not add up to the region's");
    expect(broken((c) => { c.groups.crew.wages_milli = -1; })).toBe("malformed wages milli");
    expect(broken((c) => { c.groups.crew.paid_milli += 1; })).toBe("the groups' paid milli do not add up to the region's");
    expect(broken((c) => { c.credited_outside_milli += 1; })).toBe("the groups' credits and outside sellers' do not add up to the region's");
    expect(broken((c) => { delete c.groups.crew; })).toBe("malformed cohorts");
    expect(broken((c) => { c.unknown.persons = ""; })).toBe("malformed unknown reasons");
    expect(broken((c) => { c.credited_outside_milli = null; })).toBe("malformed outside sellers' credit");
    expect([...COHORT_FIELDS]).toEqual(["persons", "priced_out", "paid_milli", "refunded_milli", "credited_milli",
      "income_replaced", "wages_milli"]);
  });
});
