import { describe, expect, it } from "vitest";
import {
  inspectSettlement, inspectSettlementHistory, settlementOptions, settlementPopulationHistory,
  type SettlementSnapshot,
} from "./settlementInspection";

const settlement = {
  settlement_id: 7, name: "River Quay", region_name: "Delta", population_estimate: 23,
  centroid_x: 1.25, centroid_y: -2.75, founding_turn: 2, status: "active",
};
// Hand-authored history, not simulation or terminal-world derived.
const history: SettlementSnapshot[] = [
  { turn: 1, settlement_source_turn: 1, active_settlements: [], founded_this_turn: [], dissolved_this_turn: [] },
  { turn: 2, settlement_source_turn: 2, active_settlements: [settlement], founded_this_turn: [7], dissolved_this_turn: [] },
  { turn: 3, settlement_source_turn: 2, active_settlements: [{ ...settlement, population_estimate: 31, centroid_x: 1.5 }], founded_this_turn: [], dissolved_this_turn: [] },
  { turn: 5, settlement_source_turn: 5, active_settlements: [], founded_this_turn: [], dissolved_this_turn: [7] },
];

describe("historical settlement inspection", () => {
  it("preserves absence before founding, exact values after founding, and recorded dissolution", () => {
    const before = inspectSettlementHistory(history, 1, 7);
    expect(before.state).toBe("not-listed");
    expect(before.summary).toBeNull();
    expect(before.founded.value).toBe(false);
    const founded = inspectSettlementHistory(history, 2, 7);
    expect(founded.state).toBe("available");
    expect(founded.founded).toEqual({ value: true, source: "/history/1/founded_this_turn/0", unavailable: null });
    expect(founded.summary?.population).toEqual({ value: 23, source: "/history/1/active_settlements/0/population_estimate", unavailable: null });
    expect(founded.summary?.centroidX.value).toBe(1.25);
    expect(founded.summary?.centroidY.value).toBe(-2.75);
    const dissolved = inspectSettlementHistory(history, 5, 7);
    expect(dissolved.state).toBe("dissolved");
    expect(dissolved.summary).toBeNull();
    expect(dissolved.dissolved.source).toBe("/history/3/dissolved_this_turn/0");
  });

  it("shows the recorded source turn and age without forward-filling gaps", () => {
    const stale = inspectSettlementHistory(history, 3, 7);
    expect(stale.sourceTurn.value).toBe(2);
    expect(stale.observationAge).toBe(1);
    expect(stale.freshness).toBe("stale");
    expect(stale.summary?.population.value).toBe(31);
    expect(inspectSettlementHistory(history, 4, 7)).toMatchObject({ state: "unavailable", summary: null, observationAge: null });
    expect(inspectSettlementHistory(history, 2, 7).observationAge).toBe(0);
    expect(inspectSettlementHistory(history, 3, 99).summary).toBeNull();
    expect(inspectSettlementHistory(history, 2, 7).summary?.population.value).toBe(23);
  });

  it("separates missing source timestamps from missing snapshot timestamps", () => {
    const noSource = inspectSettlement({ requestedTurn: 2, settlementId: 7,
      snapshot: { turn: 2, active_settlements: [settlement] } });
    expect(noSource.summary?.population.value).toBe(23);
    expect(noSource.sourceTurn.unavailable).toBe("Not recorded");
    expect(noSource.freshness).toBe("unavailable");
    expect(noSource.observationAge).toBeNull();
    expect(noSource.founded.value).toBeNull();
    for (const timestamp of [undefined, NaN, 1]) {
      expect(inspectSettlement({ requestedTurn: 2, settlementId: 7,
        snapshot: { turn: timestamp, active_settlements: [settlement] } }).summary).toBeNull();
    }
    expect(inspectSettlementHistory([{ active_settlements: [settlement] }], 2, 7).state).toBe("unavailable");
  });

  it.each([null, 0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])("rejects invalid ID %s", (settlementId) => {
    expect(inspectSettlementHistory(history, 2, settlementId)).toMatchObject({ state: "unavailable", summary: null });
  });

  it.each([-1, 2.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])("rejects invalid requested turn %s", (requestedTurn) => {
    expect(inspectSettlementHistory(history, requestedTurn, 7)).toMatchObject({ state: "unavailable", summary: null });
    expect(settlementPopulationHistory(history, requestedTurn, 7)).toEqual([]);
    expect(settlementOptions(history, requestedTurn)).toEqual([]);
  });

  it("never invents missing fields or converts invalid values into zero", () => {
    const result = inspectSettlement({ requestedTurn: 2, settlementId: 7, snapshot: {
      turn: 2, active_settlements: [{ settlement_id: 7, population_estimate: "23", centroid_x: NaN, centroid_y: 0, status: "candidate" }],
    } });
    expect(result.summary?.name).toMatchObject({ value: null, unavailable: "Not recorded" });
    expect(result.summary?.population).toMatchObject({ value: null, unavailable: "Invalid recorded value" });
    expect(result.summary?.centroidX.value).toBeNull();
    expect(result.summary?.centroidY.value).toBe(0);
    expect(result.summary?.status.value).toBeNull();
    expect(result.summary?.foundingTurn.value).toBeNull();
    expect(inspectSettlement({ requestedTurn: 2, settlementId: 7, snapshot: { turn: 2 } }).state).toBe("unavailable");
  });

  it("rejects future, duplicate and contradictory observations", () => {
    const input = { requestedTurn: 2, settlementId: 7, snapshot: history[1] };
    expect(inspectSettlement({ ...input, snapshot: { ...history[1], settlement_source_turn: 3 } }).summary).toBeNull();
    expect(inspectSettlement({ ...input, snapshot: { ...history[1], active_settlements: [settlement, settlement] } }).summary).toBeNull();
    expect(inspectSettlement({ ...input, snapshot: { ...history[1], dissolved_this_turn: [7] } }).summary).toBeNull();
    expect(inspectSettlement({ ...input, snapshot: { ...history[1], active_settlements: [{ ...settlement, founding_turn: 3 }] } }).summary).toBeNull();
    expect(inspectSettlementHistory([history[1], history[1]], 2, 7).explanation).toContain("Multiple historical snapshots");
  });

  it("rejects an active summary after recorded dissolution regardless of source order", () => {
    const resurrected = { ...history[1], turn: 6, settlement_source_turn: 6 };
    for (const input of [[history[3], resurrected], [resurrected, history[3]]]) {
      const inspection = inspectSettlementHistory(input, 6, 7);
      expect(inspection.summary).toBeNull();
      expect(inspection.explanation).toContain("earlier recorded dissolution at history turn 5");
      expect(settlementPopulationHistory(input, 6, 7).find((row) => row.turn === 6)?.inspection.summary).toBeNull();
      expect(inspectSettlementHistory(input, 4, 7).explanation).toContain("No historical snapshot");
    }
    // A future dissolution must not invalidate an earlier recorded population.
    expect(inspectSettlementHistory([history[3], history[1]], 2, 7).summary?.population.value).toBe(23);
    // An invalid source observation does not establish a recorded tombstone.
    expect(inspectSettlementHistory([{ ...history[3], settlement_source_turn: 8 }, resurrected], 6, 7).summary?.population.value).toBe(23);
  });

  it("distinguishes corrupt identities and lifecycle lists from verified absence", () => {
    const result = inspectSettlement({ requestedTurn: 2, settlementId: 7, snapshot: {
      turn: 2, active_settlements: [{ settlement_id: "7" }], founded_this_turn: [0],
    } });
    expect(result.state).toBe("unavailable");
    expect(result.founded.unavailable).toBe("Invalid recorded list");
    const present = inspectSettlement({ requestedTurn: 2, settlementId: 7, snapshot: {
      turn: 2, active_settlements: [settlement, { settlement_id: "bad" }],
    } });
    expect(present.summary?.population.value).toBe(23);
  });

  it("preserves summary/source order, zero values and dissolving status without future labels", () => {
    const snapshot = { ...history[1], active_settlements: [
      { ...settlement, settlement_id: 9, name: "Upper Ferry", population_estimate: 0, centroid_x: 0, status: "dissolving" }, settlement,
    ] };
    expect(settlementOptions([snapshot], 2).map((row) => row.id)).toEqual([9, 7]);
    expect(settlementOptions(history, 1)).toEqual([]);
    expect(settlementOptions(history, 5)).toEqual([{ id: 7, label: "Settlement #7" }]);
    expect(inspectSettlementHistory([snapshot], 2, 9).summary?.status.value).toBe("dissolving");
    expect(inspectSettlementHistory([snapshot], 2, 9).summary?.population.value).toBe(0);
    expect(inspectSettlementHistory([snapshot], 2, 7).source).toBe("/history/0/active_settlements/1");
  });

  it("records population samples in original order without future samples or mutating inputs", () => {
    const input = structuredClone([history[2], history[0], history[1], history[3]]);
    const original = structuredClone(input);
    for (let i = 0; i < 5; i++) {
      const rows = settlementPopulationHistory(input, 3, 7);
      expect(rows.map((row) => row.turn)).toEqual([3, 1, 2]);
      expect(rows.map((row) => row.inspection.summary?.population.value ?? null)).toEqual([31, null, 23]);
      expect(rows[2].inspection.source).toBe("/history/2/active_settlements/0");
    }
    expect(input).toEqual(original);
    expect(settlementPopulationHistory([history[1], history[1]], 2, 7).every((row) => row.inspection.summary === null)).toBe(true);
  });
});
