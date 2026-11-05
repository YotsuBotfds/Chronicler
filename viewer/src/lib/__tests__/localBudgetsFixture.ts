import type { LocalBudgetsRecord } from "../localBudgets";

/** Constructed observation to test the strict reader and panel; not a simulation run. */
export function localBudgetsRecord(): LocalBudgetsRecord {
  return {
    schema_version: 1, stage: "L9", mode: "bargained", source_turn: 30,
    decisions: [{
      turn: 30, civ: 1, mode: "bargained", seat: 12, projected: 32, floor: 20, obligations: 0, committed: 0, budget: 3,
      influence: { commons: 0.1, patricians: 0.6 }, burdens: { commons: null, patricians: 0.6 },
      proposals: [
        { pid: 0, service: "relief", civ: 1, source_turn: 30, recipients: [1], site: null, claims: ["procurement:1"],
          cost: 2, divisible: true, unit: "grain", expected: 19.5, relief: {}, detail: { price: 0.1 } },
        { pid: 1, service: "workshop", civ: 1, source_turn: 30, recipients: [1], site: 0, claims: ["workshop:0"],
          cost: 3, divisible: false, unit: "work", expected: 0.6, relief: { patricians: 0.6 }, detail: { asset: "idle" } },
      ],
      dropped: 0, candidates: { compromise: [[1, 3]], commons: [], patricians: [[1, 3]] },
      satisfaction: { compromise: { commons: 1, patricians: 1 } }, scores: { compromise: 0.7 },
      chosen: "compromise", outcome: "uncontested", awards: [{ pid: 1, amount: 3, sponsor: "patricians" }],
      refused: [[0, "no_support"]],
    }],
    settled: [{
      cid: 4, civ: 1, service: "granary_maintain", pid: 0, decided_turn: 29, for_turn: 30, recipients: [0], site: null,
      claims: ["storage:0"], amount: 8, unit: "work", expected: 4, sponsor: "commons", venue: 12,
      outcome: "deferred", reason: "treasury_shortfall", spent: 0, delivered: 0, ratio: 0, settled_turn: 30, response: 0.1,
      detail: {},
    }],
    responses: [{ turn: 30, civ: 1, settlement_id: 12, before: 0.2, raw: 0.1, applied: 0.1, after: 0.3 }],
    open: [{
      cid: 5, civ: 1, service: "workshop", pid: 1, decided_turn: 30, for_turn: 31, recipients: [1], site: 0,
      claims: ["workshop:0"], amount: 3, unit: "work", expected: 0.6, sponsor: "patricians", venue: 12,
      outcome: null, reason: null, spent: null, delivered: null, ratio: null, settled_turn: null, response: null, detail: {},
    }],
    counters: { decision_civ_turns: 4, awards: 2, envelope_coins: 11, spent_coins: 0, deferred: 1 },
    parameters: { envelope_share: 0.25 },
  };
}
