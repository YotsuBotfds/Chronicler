/// <reference types="node" />
import { webcrypto } from "node:crypto";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { createWhatIfRecipe, portableWhatIfManifest, readWhatIfManifest, readWhatIfRecipe, restorationContext } from "../whatIf";
import { recipeManifest } from "../../__fixtures__/whatIf";
import type { PauseContext } from "../../types";
const candidate = { region_id: 0, region_name: "A", fallen_seat_id: 3, fallen_seat_name: "Old Academy", fallen_founder: 0,
  fallen_founded_turn: 0, fallen_turn: 1, current_lord: 0, current_lord_name: "A", eligible: true, reason: null,
  fee: 30, treasury_before: 100, treasury_after: 70 };
const pause = (): PauseContext => ({ turn: 2, reason: "interval", valid_commands: [], injectable_events: [], settable_stats: [], civs: ["A"],
  academy_restoration: { schema_version: 1, turn: 2, supported: true, unavailable_reason: null, candidates: [candidate], total_candidates: 1, omitted: 0 } });
const manifest = () => ({ ...recipeManifest(), schema_version: 4, intervention: { command: "set", civ: "@academy", stat: "lab.academy_restore", value: 3, before: 3, scope: "academy", ...Object.fromEntries(Object.entries(candidate).filter(([key]) => !["eligible", "reason"].includes(key))) } });
beforeEach(() => vi.stubGlobal("crypto", webcrypto)); afterEach(() => vi.unstubAllGlobals());
it("strictly validates dated paid restoration and exports only readable provenance and recipe", async () => {
  const m = readWhatIfManifest(manifest()); expect(m?.schema_version).toBe(4);
  const publicPlan = JSON.stringify(portableWhatIfManifest(m!));
  expect(publicPlan).toContain('"control":"academy_restoration"'); expect(publicPlan).not.toContain('"value"');
  expect(publicPlan).not.toContain("/private/");
  const recipe = await createWhatIfRecipe(m!); expect(readWhatIfRecipe(recipe)).toEqual(recipe);
  expect(recipe.control).toEqual({ kind: "academy_restoration", region_id: 0, fallen_seat_id: 3 });
  for (const change of [{ fallen_turn: 2 }, { fallen_founded_turn: 2 }, { fee: 0 }, { treasury_before: 40, treasury_after: 10 },
    { treasury_after: 71 }, { value: 4 }, { before: 4 }, { current_lord: -1 }, { extra: true }]) {
    expect(readWhatIfManifest({ ...manifest(), intervention: { ...manifest().intervention, ...change } })).toBeNull();
  }
});
it("requires a bounded fresh pause candidate context and preserves ineligible unowned sites", () => {
  expect(restorationContext(pause())?.candidates[0]).toEqual(candidate);
  const stale = pause(); (stale.academy_restoration as { turn: number }).turn = 1; expect(restorationContext(stale)).toBeNull();
  const invalid = pause(); (invalid.academy_restoration as { omitted: number }).omitted = 1; expect(restorationContext(invalid)).toBeNull();
  const unowned = pause(); (unowned.academy_restoration as { candidates: unknown[] }).candidates = [{ ...candidate, current_lord: null, current_lord_name: null, eligible: false, reason: "Uncontrolled", fee: null, treasury_before: null, treasury_after: null }];
  expect(restorationContext(unowned)?.candidates[0].reason).toBe("Uncontrolled");
});
