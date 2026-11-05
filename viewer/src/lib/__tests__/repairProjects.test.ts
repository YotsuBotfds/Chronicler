import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { progress, repairFunnel, repairProjectsAt } from "../repairProjects";

/** Constructed observations to test the reader; not a simulation run. */
const project = { pid: 2, kind: "workshop", asset: 0, region: 1, settlement_id: 5, cause: "war", war_key: "A:B",
  war_start_turn: 3, damages: [4], opened_turn: 6, opened_condition: 0.4, controller: 0, scope: 4.8,
  delivered: 0.4, credited: 0.4, status: "open", closed_turn: null, closed_reason: null, work_turns: 1,
  stalled_turns: 0, stalls: {}, timber_used: 0.4, wages_milli: 400, coin_cost_milli: 0,
  last_crew: [100, 101, 102, 103], history: [[6, "opened_war", 0, 4800]] };
const granary = { ...project, pid: 1, kind: "granary", asset: 0, region: 0, settlement_id: null, cause: "wear",
  war_key: null, war_start_turn: null, damages: [], scope: 20, delivered: 4, credited: 4, last_crew: [],
  wages_milli: 0, coin_cost_milli: 8000, timber_used: 4 };
const crew = { turn: 7, pid: 2, kind: "workshop", asset: 0, region: 1, payer: 0, status: "progress",
  reasons: ["unqualified"], requested: 0.4, delivered: 0.4, credited: 0.4, rate: 0.5, crew: [100, 101, 102, 103],
  share: 0.2, qualified: [], veterans: [101], timber_held: 0.4, timber_used: 0.4, timber_returned: 0,
  wages_due_milli: 400, wages_milli: 400, wage_residual_milli: 0, coin_cost_milli: 0, envelope: null,
  condition_before: 0.4, condition_after: 0.45, remaining_after: 4.4, income_replaced: 0.8 };
const work = { ...crew, pid: 1, kind: "granary", asset: 0, region: 0, reasons: [], requested: 4, delivered: 4,
  credited: 4, rate: null, crew: [], share: null, veterans: [], timber_held: 4, timber_used: 4, wages_due_milli: 0,
  wages_milli: 0, coin_cost_milli: 8000, condition_before: 0.5, condition_after: 0.59, remaining_after: 16,
  income_replaced: null };
const ledger = { turn: 7, civ: 0, projects: 2, work_delivered: 4.4, timber_used: 4.4, coin_cost_milli: 8000,
  wages_due_milli: 400, wages_applied_milli: 400, wage_residual_milli: 0, charged: 9, prepaid_before_milli: 300,
  prepaid_after_milli: 900, envelope: null };
const record = { schema_version: 1, stage: "RS2", mode: "repair", source_turn: 7, units: { milli: 1000 },
  projects: [granary, project], closed: [{ ...granary, pid: 0, status: "completed", closed_turn: 5, delivered: 20 }],
  damages: [{ did: 4, turn: 5, kind: "workshop", asset: 0, region: 1, event: "sack", war_key: "A:B",
    war_start_turn: 3, amount: 0.25, condition_before: 0.65, condition_after: 0.4, project: 2 }],
  receipts: [work, crew], ledger: [ledger],
  unmet: [{ kind: "granary", asset: 2, region: 2, condition: 0.1, reason: "zero_capacity" }], suspended: [0],
  prepaid: { "0": 900 }, counters: { opened_wear: 2, opened_war: 1, progress_turns: 3, completed: 1, damages: 1 }, parameters: { open_below: 0.75 } };
const snap = (repair_projects: unknown, turn = 8) =>
  ({ turn, livelihoods: { schema_version: 1, repair_projects } } as unknown as TurnSnapshot);

describe("repair projects reader", () => {
  it("reads dated, well-formed records only", () => {
    expect(repairProjectsAt(snap(record), 3, 2)?.projects).toHaveLength(2);
    expect(repairProjectsAt(snap(record, 9), 3, 2)).toBeNull();                // misdated
    expect(repairProjectsAt(snap(record), 1, 2)).toBeNull();                   // region out of range
    expect(repairProjectsAt(snap(record), 3, 0)).toBeNull();                   // civ out of range
    expect(repairProjectsAt(snap({ ...record, stage: "RS0" }), 3, 2)).toBeNull();
    expect(repairProjectsAt(null, 3, 2)).toBeNull();
  });

  it("refuses unbalanced books, work beyond the plan and double crews", () => {
    const off = (patch: object) => repairProjectsAt(snap({ ...record, ...patch }), 3, 2);
    expect(off({ ledger: [{ ...ledger, charged: 8 }] })).toBeNull();
    expect(off({ ledger: [{ ...ledger, prepaid_after_milli: 1900, charged: 10 }] })).toBeNull();
    expect(off({ prepaid: { "0": 1000 } })).toBeNull();
    expect(off({ prepaid: { "5": 10 } })).toBeNull();
    expect(off({ receipts: [{ ...work, delivered: 5, credited: 5 }, crew] })).toBeNull();
    expect(off({ receipts: [work, { ...crew, wages_milli: 300 }] })).toBeNull();
    expect(off({ receipts: [work, { ...crew, timber_returned: 1 }] })).toBeNull();
    expect(off({ receipts: [{ ...work, crew: [100] }, crew] })).toBeNull();
    expect(off({ receipts: [work, { ...crew, status: "stalled" }] })).toBeNull();
    expect(off({ receipts: [work, { ...crew, crew: [1, 2, 3, 4, 5] }] })).toBeNull();
    expect(off({ projects: [granary, { ...project, pid: 9, kind: "granary", asset: 0, region: 0 }] })).toBeNull();
    expect(off({ ledger: null })).toBeNull();                                  // receipts without accounts
  });

  it("refuses moved condition in the cost-only control and malformed damage", () => {
    expect(repairProjectsAt(snap({ ...record, mode: "cost_only" }), 3, 2)).toBeNull();
    const control = { ...record, mode: "cost_only", projects: [{ ...granary, credited: 0 }],
      closed: [], receipts: [{ ...work, credited: 0 }], ledger: [{ ...ledger, projects: 1, wages_due_milli: 0,
        wages_applied_milli: 0, charged: 8, prepaid_before_milli: 0, prepaid_after_milli: 0 }], prepaid: {} };
    expect(repairProjectsAt(snap(control), 3, 2)?.mode).toBe("cost_only");
    const bad = { ...record.damages[0], condition_after: 0.5 };
    expect(repairProjectsAt(snap({ ...record, damages: [bad] }), 3, 2)).toBeNull();
    const half = { ...record.damages[0], war_start_turn: null };
    expect(repairProjectsAt(snap({ ...record, damages: [half] }), 3, 2)).toBeNull();
  });

  it("keeps an unobserved turn unknown, not zero, and orders the funnel", () => {
    const unknown = repairProjectsAt(snap({ ...record, receipts: null, ledger: null, unmet: null, suspended: null }), 3, 2);
    expect(unknown?.receipts).toBeNull();
    const parsed = repairProjectsAt(snap(record), 3, 2)!;
    const funnel = repairFunnel(parsed);
    expect(funnel[0]).toEqual(["Projects opened for wear", 2]);
    expect(funnel.find(([k]) => k === "Projects abandoned")?.[1]).toBe(0);
    expect(progress(parsed.projects[0])).toBeCloseTo(0.2);
  });
});
