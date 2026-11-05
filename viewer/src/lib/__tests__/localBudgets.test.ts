import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { awardedServices, localBudgetsAt, type LocalBudgetsRecord } from "../localBudgets";
import { localBudgetsRecord } from "./localBudgetsFixture";

const at = (budgets: unknown, turn = 31, schema = 1, civs = 2) =>
  localBudgetsAt({ turn, livelihoods: { schema_version: schema, local_budgets: budgets } } as unknown as TurnSnapshot, civs);

describe("localBudgetsAt", () => {
  it("accepts a dated record and keeps unknown burdens unknown", () => {
    const good = localBudgetsRecord();
    expect(at(good)).toBe(good);
    expect(at(good)?.decisions?.[0].burdens.commons).toBeNull();
    expect(awardedServices(good.decisions![0])).toEqual(["workshop 3"]);
  });

  it("keeps a turn without a decision or settlement unknown rather than empty", () => {
    const unobserved: LocalBudgetsRecord = { ...localBudgetsRecord(), decisions: null, settled: null, responses: null };
    expect(at(unobserved)?.decisions).toBeNull();
    expect(at({ ...unobserved, responses: localBudgetsRecord().responses })).toBeNull();
  });

  it("rejects absent, misdated, foreign and malformed data", () => {
    const good = localBudgetsRecord();
    const d = good.decisions![0];
    const s = good.settled![0];
    expect(localBudgetsAt(null, 2)).toBeNull();
    expect(localBudgetsAt({ turn: 31 } as TurnSnapshot, 2)).toBeNull();
    expect(at(good, 31, 2)).toBeNull();
    expect(at(good, 32)).toBeNull();
    expect(at(good, 31, 1, 1)).toBeNull();                              // civ index out of range
    for (const bad of [undefined, { ...good, schema_version: 2 }, { ...good, stage: "L8" }, { ...good, mode: "vote" },
      { ...good, counters: { awards: Number.NaN } }, { ...good, open: [{ ...good.open[0], outcome: "kept" }] },
      { ...good, decisions: [{ ...d, turn: 29 }] },
      { ...good, decisions: [{ ...d, awards: [{ pid: 1, amount: 4, sponsor: null }] }] },          // beyond the cost
      { ...good, decisions: [{ ...d, budget: 2 }] },                                              // beyond the budget
      { ...good, decisions: [{ ...d, awards: [{ pid: 1, amount: 3, sponsor: null }, { pid: 1, amount: 3, sponsor: null }], budget: 6 }] },
      { ...good, decisions: [{ ...d, burdens: { commons: -1 } }] },
      { ...good, decisions: [{ ...d, proposals: [d.proposals[1], d.proposals[0]] }] },
      { ...good, settled: [{ ...s, spent: 9 }] }, { ...good, settled: [{ ...s, settled_turn: 29 }] },
      { ...good, settled: [{ ...s, outcome: null }] },
      { ...good, responses: [{ ...good.responses![0], after: 0.5 }] }]) {
      expect(at(bad)).toBeNull();
    }
  });
});
