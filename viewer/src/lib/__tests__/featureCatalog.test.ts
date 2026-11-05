import { describe, expect, it } from "vitest";
import served from "../../__fixtures__/featureCatalog.json";
import {
  effectiveValues,
  featurePayload,
  normalizeSelection,
  readFeatureCatalog,
  selectionFlags,
  unmetRequirements,
  type FeatureCatalog,
} from "../featureCatalog";

function clone(): Record<string, any> { // eslint-disable-line @typescript-eslint/no-explicit-any
  return structuredClone(served);
}

function read(raw: unknown): FeatureCatalog {
  const reading = readFeatureCatalog(raw);
  if (reading.status !== "ok") throw new Error(JSON.stringify(reading));
  return reading.catalog;
}

describe("readFeatureCatalog", () => {
  it("reads the catalog the server serves", () => {
    const catalog = read(served);
    const keys = catalog.features.map((entry) => entry.key);
    expect(keys).toContain("workshops");
    expect(keys).toContain("grain_reserves");
    const mode = catalog.features.find((entry) => entry.key === "workshop_mode")!;
    expect(mode).toMatchObject({ kind: "choice", parent: "workshops", choices: ["operate", "observe", "cost_only"] });
    const payroll = catalog.features.find((entry) => entry.key === "workshop_payroll")!;
    expect(payroll.requires.map((req) => req.kind)).toEqual(["agents", "feature", "choice"]);
    expect(catalog.surfaces.batch.agentModes).toEqual(["off", "demographics-only", "shadow", "hybrid"]);
    expect(catalog.surfaces.live.settings.cities).toBe(true);
  });

  it("tells an older server's absent catalog from a malformed one", () => {
    expect(readFeatureCatalog(undefined)).toEqual({ status: "absent" });
    expect(readFeatureCatalog(null).status).toBe("invalid");
    expect(readFeatureCatalog("catalog").status).toBe("invalid");
  });

  const corruptions: [string, (raw: Record<string, any>) => void][] = [ // eslint-disable-line @typescript-eslint/no-explicit-any
    ["a newer schema", (raw) => { raw.schema_version = 2; }],
    ["features not a list", (raw) => { raw.features = {}; }],
    ["a duplicate key", (raw) => { raw.features.push(structuredClone(raw.features[0])); }],
    ["a default that is on", (raw) => { raw.features[0].default = true; }],
    ["a bool with choices", (raw) => { raw.features[0].choices = ["a"]; }],
    ["a choice without choices", (raw) => { raw.features.find((e: { kind: string }) => e.kind === "choice").choices = []; }],
    ["a mode whose parent is a choice", (raw) => {
      raw.features.find((e: { key: string }) => e.key === "workshop_mode").parent = "workshop_payroll_mode";
    }],
    ["an unknown condition", (raw) => { raw.features[0].requires = [{ weather: "fine", reason: "requires sun" }]; }],
    ["two conditions in one", (raw) => { raw.features[0].requires = [{ feature: "scholarship", setting: "cities", reason: "x" }]; }],
    ["a condition without a reason", (raw) => { raw.features[0].requires = [{ feature: "scholarship" }]; }],
    ["an unknown required switch", (raw) => { raw.features[0].requires = [{ feature: "teleporters", reason: "x" }]; }],
    ["an unknown required setting", (raw) => { raw.features[0].requires = [{ setting: "magic", reason: "x" }]; }],
    ["a choice value it does not offer", (raw) => {
      raw.features[0].requires = [{ choice: "workshop_mode", values: ["sometimes"], reason: "x" }];
    }],
    ["an empty any", (raw) => { raw.features[0].requires = [{ any: [], reason: "x" }]; }],
    ["a surface without a setting", (raw) => { delete raw.surfaces.live.settings.cities; }],
    ["a surface value of the wrong type", (raw) => { raw.surfaces.batch.values = { workshops: "yes" }; }],
    ["a surface value naming an unknown feature", (raw) => { raw.surfaces.batch.values = { nothing: true }; }],
    ["an agent mode outside its list", (raw) => { raw.surfaces.live.agents = "psychic"; }],
    ["a missing surface", (raw) => { delete raw.surfaces.batch; }],
    ["a missing label", (raw) => { delete raw.features[3].label; }],
  ];
  it.each(corruptions)("refuses %s", (_name, corrupt) => {
    const raw = clone();
    corrupt(raw);
    const reading = readFeatureCatalog(raw);
    expect(reading.status).toBe("invalid");
  });
});

describe("selection rules", () => {
  const catalog = read(served);
  const live = catalog.surfaces.live;

  it("drops overrides that change nothing, including a mode's default", () => {
    expect(normalizeSelection(catalog, live, "hybrid", {
      workshops: true, workshop_mode: "operate", food_allocation: false,
    })).toEqual({ workshops: true });
    expect(normalizeSelection(catalog, live, "hybrid", { workshops: true, workshop_mode: "observe" }))
      .toEqual({ workshops: true, workshop_mode: "observe" });
  });

  it("drops a switch, its mode and its dependants when a requirement goes", () => {
    const selected = { grain_reserves: true, local_budgets: true, local_budget_mode: "fixed_shares" };
    expect(normalizeSelection(catalog, live, "hybrid", selected)).toEqual(selected);
    expect(normalizeSelection(catalog, live, "hybrid", { ...selected, grain_reserves: false })).toEqual({});
    // A mode change that breaks a dependant drops only the dependant.
    expect(normalizeSelection(catalog, live, "hybrid", {
      workshops: true, workshop_payroll: true, workshop_mode: "observe",
    })).toEqual({ workshops: true, workshop_mode: "observe" });
    // An agent mode that cannot run them drops them all.
    expect(normalizeSelection(catalog, live, "off", selected)).toEqual({});
    expect(normalizeSelection(catalog, live, "shadow", { grain_reserves: true, timber_stock: true, local_budgets: true }))
      .toEqual({ grain_reserves: true, timber_stock: true });
  });

  it("turns off explicitly a switch the server enabled when it can no longer run", () => {
    const inherited = { ...live, values: { timber_stock: true, commons_rules: true } };
    expect(normalizeSelection(catalog, inherited, "hybrid", { timber_stock: false }))
      .toEqual({ timber_stock: false, commons_rules: false });
    expect(normalizeSelection(catalog, inherited, "hybrid", { timber_stock: true })).toEqual({});
  });

  it("reports unmet requirements with their reasons", () => {
    const local = catalog.features.find((entry) => entry.key === "local_budgets")!;
    expect(unmetRequirements(catalog, local, effectiveValues(live, {}), live, "off").map((req) => req.reason))
      .toEqual(["requires --agents hybrid", "requires --grain-reserves"]);
    const noCities = { ...live, settings: { ...live.settings, cities: false } };
    const workshops = catalog.features.find((entry) => entry.key === "workshops")!;
    expect(unmetRequirements(catalog, workshops, {}, noCities, "hybrid")[0].reason).toMatch(/^requires cities/);
  });

  it("evaluates an any condition", () => {
    const raw = clone();
    raw.features.find((e: { key: string }) => e.key === "food_allocation").requires = [{
      any: [{ feature: "workshops", reason: "requires --workshops" },
        { feature: "grain_reserves", reason: "requires --grain-reserves" }],
      reason: "requires one of: --workshops; --grain-reserves",
    }];
    const custom = read(raw);
    const food = custom.features.find((entry) => entry.key === "food_allocation")!;
    expect(unmetRequirements(custom, food, {}, custom.surfaces.live, "hybrid")).toHaveLength(1);
    expect(unmetRequirements(custom, food, { grain_reserves: true }, custom.surfaces.live, "hybrid")).toHaveLength(0);
  });

  it("builds the flags and the payload", () => {
    const selection = { local_budgets: true, grain_reserves: true, workshop_mode: "cost_only", timber_stock: false };
    expect(selectionFlags(catalog, selection))
      .toEqual(["--grain-reserves", "--workshop-mode=cost_only", "--no-timber-stock", "--local-budgets"]);
    expect(featurePayload({})).toBeUndefined();
    expect(featurePayload(selection)).toEqual(selection);
    expect(featurePayload(selection)).not.toBe(selection);
  });
});
