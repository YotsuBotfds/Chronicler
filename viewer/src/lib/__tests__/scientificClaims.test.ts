import { describe, expect, it } from "vitest";
import observations from "../../__fixtures__/scientific_claims_observations.json";
import type { ScientificClaimsSnapshot, TurnSnapshot } from "../../types";
import { observationAt } from "../observedSystems";
import { scientificClaimsSeries, scientificContext, scientificTrials } from "../scientificClaims";
import { presentSystems } from "../systems";
import { bundleFromInitMessage, snapshotFromMessage } from "../transport";

const history = observations.history.map((row) => ({ ...row, civ_stats: {}, region_control: {}, relationships: {} })) as TurnSnapshot[];
const at = (t: number) => structuredClone(history.find((row) => row.turn === t)!);

describe("scientific claims recorded history", () => {
  it("reads actual paid controlled mechanical observations without claiming world qualification", () => {
    expect(observations.fixture).toMatch(/controlled mechanical.*no scientific world qualification/);
    expect(scientificTrials(history, 1)).toEqual([]);
    expect(scientificTrials(history, 2)).toHaveLength(2);
    expect(scientificTrials(history, 14)).toHaveLength(4);
    expect(at(14).scientific_claims).toMatchObject({ trial_spent: 8, effort_spent: 5 });
    expect(at(13).scientific_claims!.allocations.reduce((sum, row) => sum + row.paid, 0)).toBe(5);
    expect(at(13).scientific_claims!.allocations).toHaveLength(10);
    expect(scientificTrials(history, 14)[0]).toMatchObject({ id: 2, parent: 0, resolved_turn: 13, snapshot_turn: 14 });
  });

  it("keeps unknown history gaps and ends spending and trials at the selected snapshot", () => {
    const early = at(1), known = at(13), future = at(14);
    delete early.scientific_claims;
    future.scientific_claims!.trial_spent = 999;
    expect(scientificClaimsSeries([early, known, future], 13)).toEqual([
      { turn: 1, "Trial spending": null, "Adoption effort spending": null, "Evidence receipts": null },
      { turn: 13, "Trial spending": 8, "Adoption effort spending": 5, "Evidence receipts": known.scientific_claims!.evidence_receipts },
    ]);
    expect(scientificTrials([early, at(2), known, future], 13)).toHaveLength(2);
  });

  it.each(["funded_turn", "resolved_turn"] as const)("rejects future actual trial %s, including aggregate counters", (key) => {
    const row = at(2);
    row.scientific_claims!.trials_resolved[0][key] = 7;
    expect(observationAt(row, "scientific_claims")).toBeNull();
    expect(scientificClaimsSeries([row], 2)[0]["Trial spending"]).toBeNull();
  });

  it("rejects future receipts, trial inputs and source stamps but permits future scheduled completion", () => {
    const row = at(2);
    row.scientific_claims!.beliefs[0].last_evidence_turn = 7;
    expect(observationAt(row, "scientific_claims")).toBeNull();
    const inputs = at(2); inputs.scientific_claims!.trials_resolved[0].inputs.turn = 7;
    expect(observationAt(inputs, "scientific_claims")).toBeNull();
    const stale = at(2); stale.scientific_claims!.source_turn = 0;
    expect(observationAt(stale, "scientific_claims")).toBeNull();
    const cancelled = at(2); cancelled.scientific_claims!.trials_resolved[0].status = "cancelled";
    cancelled.scientific_claims!.trials_resolved[0].completion_turn = 7;
    expect(observationAt(cancelled, "scientific_claims")).not.toBeNull();
    const proposed = at(2); proposed.scientific_claims!.propositions[0].proposed_turn = 7;
    expect(observationAt(proposed, "scientific_claims")).toBeNull();
  });

  it("does not replay a resolution from a stale receipt array", () => {
    const stale = at(3); stale.scientific_claims!.trials_resolved = at(2).scientific_claims!.trials_resolved;
    expect(scientificTrials([at(2), stale], 3)).toHaveLength(2);
  });

  it("makes Learning available only when science was recorded and preserves transport", () => {
    const row = at(2);
    expect(presentSystems([row])).toEqual(["learning"]);
    expect(snapshotFromMessage({ ...row, type: "turn" })).toEqual(row);
    expect(bundleFromInitMessage({ history: [row], world_state: {}, metadata: {} }).history).toEqual([row]);
    delete row.scientific_claims;
    expect(presentSystems([row])).toEqual([]);
  });

  it("retains the registered context rather than treating recipe names as universal effects", () => {
    const context = (at(2).scientific_claims as ScientificClaimsSnapshot).propositions[0].context;
    expect(scientificContext(context)).toContain("soil band 3, water band 2; season 0; temperate; crew 4");
    expect(scientificContext()).toBe("Context not recorded");
  });
});
