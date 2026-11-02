import { expect, it } from "vitest";
import { readWhatIfManifest, readWhatIfResult } from "../whatIf";
import { whatIfManifest, whatIfPair } from "../../__fixtures__/whatIf";
it("requires exact semantics, bounded horizon and supported stability values", () => {
  expect(readWhatIfManifest(whatIfManifest)).toEqual(whatIfManifest);
  for (const diff of [{ semantics: "state_fork" }, { turns: 21, end_turn: 23 }, { end_turn: 9 },
    { intervention: { ...whatIfManifest.intervention, value: 101 } }, { schema_version: 2 }]) {
    expect(readWhatIfManifest({ ...whatIfManifest, ...diff })).toBeNull();
  }
});
it("accepts two complete bundles and refuses incomplete results or missing artifact identities", () => {
  const wire = { manifest: whatIfManifest, baseline: whatIfPair.baseline, intervention: whatIfPair.intervention };
  expect(readWhatIfResult(wire)?.baseline.identity?.sha256).toBe("a".repeat(64));
  expect(readWhatIfResult({ ...wire, baseline: { ...wire.baseline, bundle: {} } })).toBeNull();
  expect(readWhatIfResult({ ...wire, intervention: { ...wire.intervention, identity: null } })).toBeNull();
});
