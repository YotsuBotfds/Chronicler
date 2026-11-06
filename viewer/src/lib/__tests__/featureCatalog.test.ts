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

describe("productive-recovery switches in the served catalog", () => {
  it("declares the four switches, their control modes and their dependencies", () => {
    const catalog = read(served);
    const entry = (key: string) => catalog.features.find((e) => e.key === key)!;
    const needs = (key: string) => entry(key).requires.map((r) => r.kind === "feature" ? r.key : r.kind === "choice" ? `${r.key}=${r.values.join("|")}` : r.kind);
    expect(needs("operating_wear")).toEqual(["agents", "workshops", "workshop_mode=operate"]);
    expect(needs("timber_supply")).toEqual(["agents", "repair_projects", "timber_stock"]);
    expect(needs("recovery_crews")).toEqual(["agents", "repair_projects"]);
    expect(needs("maintenance_obligation")).toEqual(["local_budgets", "repair_projects"]);
    expect(entry("operating_wear").kind).toBe("bool");
    expect(catalog.features.some((e) => e.parent === "operating_wear")).toBe(false);   // no modes: its control is the run without it
    expect(entry("timber_supply_mode")).toMatchObject({ parent: "timber_supply", choices: ["supply", "cost_only"] });
    expect(entry("recovery_crew_mode")).toMatchObject({ parent: "recovery_crews", choices: ["paid", "unpaid"] });
    expect(entry("maintenance_obligation_mode")).toMatchObject({ parent: "maintenance_obligation", choices: ["reserve", "reserve_only"] });
    // RS1's rules version: a choice of the apprenticeship switch, version 2 first (the default).
    expect(entry("apprenticeship_rules")).toMatchObject({ kind: "choice", parent: "apprenticeship", choices: ["2", "1"],
      flag: "--apprenticeship-rules" });
    for (const key of ["operating_wear", "timber_supply", "recovery_crews", "maintenance_obligation"]) {
      expect(entry(key)).toMatchObject({ group: "Livelihoods", experimental: true });
      expect(served.features.find((e) => e.key === key)?.default).toBeNull();     // never forwarded unless chosen
    }
  });

  it("refuses unmet dependencies and sends only what is selected", () => {
    const catalog = read(served);
    const live = catalog.surfaces.live;
    const unmet = (key: string, selection: Record<string, boolean | string>) =>
      unmetRequirements(catalog, catalog.features.find((e) => e.key === key)!, effectiveValues(live, selection), live, live.agents)
        .map((r) => r.reason);
    expect(unmet("timber_supply", { repair_projects: true })).toEqual(["requires --timber-stock"]);
    expect(unmet("maintenance_obligation", { repair_projects: true })).toEqual(["requires --local-budgets"]);
    expect(unmet("operating_wear", { workshops: true, workshop_mode: "observe" })).toEqual(["requires --workshop-mode operate"]);
    const full = { workshops: true, repair_projects: true, timber_stock: true, grain_reserves: true, local_budgets: true,
      timber_supply: true, timber_supply_mode: "cost_only", recovery_crews: true, maintenance_obligation: true };
    expect(normalizeSelection(catalog, live, live.agents, full)).toEqual(full);
    // Dropping RS2 drops all three of its dependants and the mode.
    const without: Record<string, boolean | string> = { ...full };
    delete without.repair_projects;
    expect(normalizeSelection(catalog, live, live.agents, without)).toEqual({ workshops: true, timber_stock: true,
      grain_reserves: true, local_budgets: true });
    expect(selectionFlags(catalog, full)).toContain("--timber-supply-mode=cost_only");
    expect(featurePayload({ recovery_crews: true })).toEqual({ recovery_crews: true });
    expect(featurePayload({})).toBeUndefined();                           // nothing selected: nothing sent
  });
});

describe("household retail in the served catalog (PL5b)", () => {
  it("declares the switch, its mode and boundary, off by default, needing food allocation", () => {
    const catalog = read(served);
    const entry = (key: string) => catalog.features.find((e) => e.key === key)!;
    expect(entry("household_retail").requires.map((r) => r.kind === "feature" ? r.key : r.kind)).toEqual(["agents", "food_allocation"]);
    expect(entry("household_retail")).toMatchObject({ kind: "bool", flag: "--household-retail", group: "Livelihoods", experimental: true });
    expect(entry("household_retail_mode")).toMatchObject({ kind: "choice", parent: "household_retail", flag: "--household-retail-mode",
      choices: ["retail", "no_relief", "free_exchange", "record_only"] });
    expect(entry("household_retail_boundary")).toMatchObject({ kind: "choice", parent: "household_retail",
      flag: "--household-retail-boundary", choices: ["market", "paid_work", "all"] });
    for (const key of ["household_retail", "household_retail_mode", "household_retail_boundary"]) {
      expect(served.features.find((e) => e.key === key)?.default).toBeNull();
    }
    expect(entry("household_retail_boundary").help).toMatch(/paid_work: regions where paid work has been done/);
  });

  it("is unavailable without food allocation or hybrid agents, and dropping either drops it and its options", () => {
    const catalog = read(served);
    const { live, batch } = catalog.surfaces;
    const retail = catalog.features.find((e) => e.key === "household_retail")!;
    expect(unmetRequirements(catalog, retail, effectiveValues(live, {}), live, live.agents).map((r) => r.reason))
      .toEqual(["requires --food-allocation"]);
    expect(unmetRequirements(catalog, retail, effectiveValues(batch, { food_allocation: true }), batch, "off").map((r) => r.reason))
      .toEqual(["requires --agents hybrid"]);
    const full = { food_allocation: true, household_retail: true, household_retail_mode: "free_exchange",
      household_retail_boundary: "paid_work" };
    expect(normalizeSelection(catalog, live, live.agents, full)).toEqual(full);
    expect(selectionFlags(catalog, full)).toEqual(["--food-allocation", "--household-retail",
      "--household-retail-mode=free_exchange", "--household-retail-boundary=paid_work"]);
    // The run's defaults (retail, market) are not sent.
    expect(normalizeSelection(catalog, live, live.agents, { ...full, household_retail_mode: "retail", household_retail_boundary: "market" }))
      .toEqual({ food_allocation: true, household_retail: true });
    expect(normalizeSelection(catalog, live, live.agents, { ...full, food_allocation: false })).toEqual({});
    expect(normalizeSelection(catalog, live, "off", full)).toEqual({});
  });
});

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
