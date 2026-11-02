import { expect, it } from "vitest";
import { granaryPolicyValue, readWhatIfManifest, readWhatIfResult, whatIfInterventionLabel } from "../whatIf";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import { whatIfManifest, whatIfPair } from "../../__fixtures__/whatIf";
it("requires exact semantics, bounded horizon and supported stability values", () => {
  expect(readWhatIfManifest(whatIfManifest)).toEqual(whatIfManifest);
  for (const diff of [{ semantics: "state_fork" }, { turns: 21, end_turn: 23 }, { end_turn: 9 },
    { intervention: { ...whatIfManifest.intervention, value: 101 } }, { schema_version: 2 }]) {
    expect(readWhatIfManifest({ ...whatIfManifest, ...diff })).toBeNull();
  }
});
it("admits only schema-two global binary granary policy controls, including an explicit no-op", () => {
  const policy = { ...whatIfManifest, schema_version: 2,
    intervention: { command: "set", civ: "@world", stat: "grain_reserves.shortfall_priority", before: 0, value: 1, scope: "world" } };
  expect(readWhatIfManifest(policy)).toEqual(policy);
  const noOp = { ...policy, intervention: { ...policy.intervention, value: 0 } };
  expect(readWhatIfManifest(noOp)).toEqual(noOp);
  expect(whatIfInterventionLabel(readWhatIfManifest(policy)!)).toContain("World granary priority");
  for (const diff of [{ value: true }, { value: "1" }, { value: 2 }, { before: 2 }, { scope: "civilization" },
    { civ: "A" }, { stat: "arbitrary.key" }, { path: "/private/override" }]) {
    expect(readWhatIfManifest({ ...policy, intervention: { ...policy.intervention, ...diff } })).toBeNull();
  }
  expect(readWhatIfManifest({ ...policy, mode: "shadow" })).toBeNull();
  expect(readWhatIfManifest({ ...policy, schema_version: 1 })).toBeNull();
});
it("requires hybrid mode, an existing granary state and a binary saved priority", () => {
  const bundle = comparisonBundle();
  expect(granaryPolicyValue(bundle)).toBeNull();
  const world = bundle.world_state as unknown as Record<string, unknown>;
  world.agent_mode = "hybrid";
  world.grain_reserves = { granaries: [] };
  expect(granaryPolicyValue(bundle)).toBe(0);
  world.tuning_overrides = { "grain_reserves.shortfall_priority": 1 };
  expect(granaryPolicyValue(bundle)).toBe(1);
  world.tuning_overrides = { "grain_reserves.shortfall_priority": true };
  expect(granaryPolicyValue(bundle)).toBeNull();
});
it("accepts two complete bundles and refuses incomplete results or missing artifact identities", () => {
  const wire = { manifest: whatIfManifest, baseline: whatIfPair.baseline, intervention: whatIfPair.intervention };
  expect(readWhatIfResult(wire)?.baseline.identity?.sha256).toBe("a".repeat(64));
  expect(readWhatIfResult({ ...wire, baseline: { ...wire.baseline, bundle: {} } })).toBeNull();
  expect(readWhatIfResult({ ...wire, intervention: { ...wire.intervention, identity: null } })).toBeNull();
});
