/// <reference types="node" />
import { webcrypto } from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createWhatIfRecipe, granaryPolicyValue, portableWhatIfManifest, readWhatIfManifest, readWhatIfRecipe,
  readWhatIfResult, recipeLiveMismatch, recipePreparedMismatch, whatIfInterventionLabel } from "../whatIf";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import { recipeManifest, whatIfManifest, whatIfPair } from "../../__fixtures__/whatIf";
beforeEach(() => vi.stubGlobal("crypto", webcrypto));
afterEach(() => vi.unstubAllGlobals());
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
  expect(readWhatIfResult({ ...wire, request_id: "another-request" })).toBeNull();
});

it("round-trips a versioned recipe with complete content identities and basename-only privacy", async () => {
  const manifest = recipeManifest();
  const pair = { ...whatIfPair, manifest,
    baseline: { ...whatIfPair.baseline, identity: { ...whatIfPair.baseline.identity!, name: "C:\\private\\baseline.json" } } };
  const recipe = await createWhatIfRecipe(manifest, pair);
  expect(readWhatIfRecipe(JSON.parse(JSON.stringify(recipe)))).toEqual(recipe);
  expect(recipe.source.checkpoint.name).toBe("common.ckpt");
  expect(recipe.outputs?.baseline.name).toBe("baseline.json");
  expect(recipe.source.settings.scenario).toBe("world.yaml");
  const exported = JSON.stringify(recipe);
  expect(exported).not.toContain("PRIVATE_TOKEN");
  expect(exported).not.toContain("/private/");
  expect(exported).not.toContain("https:");
  expect(recipe.source.runtime_sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(recipe.source.settings_sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(await recipePreparedMismatch(recipe, manifest)).toBeNull();
  expect(JSON.stringify(portableWhatIfManifest(manifest))).not.toContain("PRIVATE_TOKEN");
  expect(JSON.stringify(portableWhatIfManifest(manifest))).not.toContain("/private/");
});

it("imports supported global policy/no-op recipes and refuses unknown versions, controls, paths and fields", async () => {
  const manifest = { ...recipeManifest(), schema_version: 2 as const,
    intervention: { command: "set" as const, civ: "@world" as const, stat: "grain_reserves.shortfall_priority" as const,
      before: 0 as const, value: 0 as const, scope: "world" as const } };
  const recipe = await createWhatIfRecipe(manifest);
  expect(recipe.outputs).toBeNull();
  expect(readWhatIfRecipe(recipe)?.control).toEqual({ kind: "granary_shortfall_priority", value: 0 });
  for (const invalid of [
    { ...recipe, version: 2 }, { ...recipe, execute: true }, { ...recipe, turns: 21 },
    { ...recipe, control: { kind: "treasury", value: 1 } },
    { ...recipe, control: { kind: "granary_shortfall_priority", value: true } },
    { ...recipe, control: { kind: "granary_shortfall_priority", value: 1, civ: "A" } },
    { ...recipe, source: { ...recipe.source, mode: "shadow" } },
    { ...recipe, source: { ...recipe.source, checkpoint: { ...recipe.source.checkpoint, name: "/private/common.ckpt" } } },
    { ...recipe, source: { ...recipe.source, settings: { ...recipe.source.settings, access_token: "PRIVATE_TOKEN" } } },
    { ...recipe, outputs: { baseline: whatIfPair.baseline.identity, intervention: { name: "bad", byteLength: 1, sha256: null } } },
  ]) expect(readWhatIfRecipe(invalid)).toBeNull();
});

it("refuses incompatible seed/turn/mode at import and exact runtime/settings/content changes after preparation", async () => {
  const manifest = recipeManifest(), recipe = await createWhatIfRecipe(manifest);
  const bundle = comparisonBundle();
  const world = bundle.world_state as unknown as Record<string, unknown>;
  world.agent_mode = "hybrid";
  expect(recipeLiveMismatch(recipe, bundle, 2, ["A"])).toBeNull();
  expect(recipeLiveMismatch(recipe, bundle, 3, ["A"])).toContain("starting turn");
  expect(recipeLiveMismatch({ ...recipe, source: { ...recipe.source, seed: 7 } }, bundle, 2, ["A"])).toContain("seed");
  expect(recipeLiveMismatch(recipe, bundle, 2, ["B"])).toContain("civilization");
  const changed = structuredClone(manifest);
  const header = changed.source.header as Record<string, unknown>;
  const config = header.run_config as Record<string, unknown>;
  (config.simulation_args as Record<string, unknown>).grain_reserves = false;
  expect(await recipePreparedMismatch(recipe, changed)).toContain("settings identity differs");
  const otherContent = structuredClone(manifest);
  (otherContent.source.checkpoint as Record<string, unknown>).sha256 = "e".repeat(64);
  expect(await recipePreparedMismatch(recipe, otherContent)).toContain("checkpoint");
  expect(await recipePreparedMismatch(recipe, { ...manifest, turns: 4, end_turn: 6 })).toContain("horizon");
  await expect(createWhatIfRecipe(whatIfManifest)).rejects.toThrow("complete compatible exact-checkpoint");
});
