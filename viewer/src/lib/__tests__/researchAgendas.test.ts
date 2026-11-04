import { describe, expect, it } from "vitest";
import { researchAgendaObservation } from "../../__fixtures__/researchAgendaObservation";
import legacy from "../../__fixtures__/scientific_claims_observations.json";
import { researchAgendasAt } from "../researchAgendas";
import { observationAt } from "../observedSystems";
import { scientificClaimsSeries } from "../scientificClaims";
import { bundleFromInitMessage, snapshotFromMessage } from "../transport";
import type { ScientificClaimsSnapshot } from "../../types";

describe("bounded dated research agenda reader", () => {
  it("reads the actual source-zero producer unit without treating retained trial IDs as exported results", () => {
    const snapshot = researchAgendaObservation(), science = snapshot.scientific_claims!;
    const parsed = researchAgendasAt(science);
    expect(parsed.status).toBe("known");
    expect(observationAt(snapshot, "scientific_claims")).toBe(science);
    expect(science).toMatchObject({ trials: 2, completed: 0, trial_spent: 4, trials_resolved: [] });
    expect(science.research_agendas).toMatchObject({ current_cycle_id: 0,
      capacity: { trials: { used: 2, reserved: 2, limit: 40 } },
      archive: { raw_records_retained: true, historical_export_completeness: "not_inferred" },
      cycles: [{ original_deadline: 11, funding_deadline: 23, next_open_not_before: 25 }] });
    expect(snapshotFromMessage({ ...snapshot, type: "turn" })).toEqual(snapshot);
    expect(bundleFromInitMessage({ history: [snapshot], world_state: {}, metadata: {} }).history).toEqual([snapshot]);
  });

  it("preserves absent legacy metadata rather than materializing a new mode", () => {
    const science = structuredClone(legacy.history[0].scientific_claims) as ScientificClaimsSnapshot;
    expect(researchAgendasAt(science)).toEqual({ status: "legacy" });
    expect(Object.hasOwn(science, "research_agendas")).toBe(false);
  });

  it.each([
    ["null metadata", ["research_agendas"], null],
    ["future schema", ["research_agendas", "schema_version"], 2],
    ["unknown rule", ["research_agendas", "rule"], "future-secret"],
    ["missing capacity", ["research_agendas", "capacity", "messages"], undefined],
    ["overcommitted capacity", ["research_agendas", "capacity", "trials", "reserved"], 39],
    ["future activation", ["research_agendas", "enabled_turn"], 1],
    ["future opening", ["research_agendas", "cycles", "0", "opened_turn"], 1],
    ["future closure", ["research_agendas", "cycles", "0", "closed_turn"], 1],
    ["future blockage", ["research_agendas", "blocked_turn"], 1],
    ["unknown deadline", ["research_agendas", "cycles", "0", "original_deadline"], null],
    ["counts disagree", ["research_agendas", "archive", "retained_trials"], 7],
    ["invented full export", ["research_agendas", "archive", "historical_export_completeness"], "complete"],
    ["duplicate paid membership", ["research_agendas", "cycles", "0", "trials"], [0, 0]],
    ["missing canonical protocol", ["propositions", "0", "metric"], undefined],
    ["malformed canonical context", ["propositions", "0", "context"], null],
    ["repeated canonical topic", ["propositions", "1", "recipe"], "irrigation"],
    ["malformed allocation row", ["allocations"], [null]],
    ["unbounded slot body", ["research_agendas", "cycles", "0", "slot_reasons", "SECRET:2"], "SECRET"],
  ] as const)("withholds %s before interpreting totals", (_name, path, value) => {
    const snapshot = researchAgendaObservation();
    // Malformed reader inputs intentionally cross the TypeScript producer contract.
    let target: unknown = snapshot.scientific_claims;
    for (const key of path.slice(0, -1)) target = (target as Record<string, unknown>)[key];
    const row = target as Record<string, unknown>, key = path.at(-1)!;
    if (value === undefined) delete row[key]; else row[key] = value;
    expect(researchAgendasAt(snapshot.scientific_claims!)).toEqual({ status: "unknown" });
    expect(observationAt(snapshot, "scientific_claims")).toBeNull();
    expect(scientificClaimsSeries([snapshot], 1)[0]["Trial spending"]).toBeNull();
  });

  it("keeps the actual paid topic separate from current beliefs and permits unknown only at legacy activation", () => {
    const snapshot = researchAgendaObservation(), science = snapshot.scientific_claims!, plan = science.research_agendas!;
    science.allocations = [{ seat: 0, region: 0, recipe: "irrigation", share: .6, confidence: .6, paid: 1, claim_id: 0 }];
    expect(science.beliefs[0].confidence).toBe(.5);
    expect(researchAgendasAt(science).status).toBe("known");
    delete science.allocations[0].claim_id;
    expect(researchAgendasAt(science).status).toBe("unknown");
    snapshot.turn = 5; science.source_turn = 4; plan.enabled_turn = 4; plan.current_cycle_id = null; plan.next_open_turn = 29;
    Object.assign(plan.cycles[0], { legacy_adopted: true, opening_roster_complete: false, closed_turn: 4,
      close_reason: "legacy funding closed prospectively at activation", original_deadline: null, funding_deadline: null,
      next_open_not_before: null, opening_roster_scope: "observed_at_legacy_activation" });
    expect(researchAgendasAt(science).status).toBe("known");
    science.source_turn = 5; snapshot.turn = 6;
    expect(researchAgendasAt(science).status).toBe("unknown");
  });
});
