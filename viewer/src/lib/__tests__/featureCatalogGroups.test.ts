import { describe, expect, it } from "vitest";
import served from "../../__fixtures__/featureCatalog.json";
import { normalizeSelection, readFeatureCatalog, selectionFlags, unmetRequirements, type FeatureCatalog } from "../featureCatalog";

/**
 * Switch groups after livelihoods and the `not` condition (two mutually exclusive
 * switches each declare `{"not": {"feature": other}}`), as chronicler.feature_catalog
 * serves them once a program registers them. Constructed from the served fixture.
 */
type Raw = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function withWaterGroup(): Raw {
  const raw: Raw = structuredClone(served);
  const entry = (key: string, other: string) => ({
    key, flag: `--${key.replace(/_/g, "-")}`, label: key, help: `Test switch ${key}.`, kind: "bool", choices: null,
    default: null, parent: null, group: "Watersheds", experimental: true,
    requires: [{ agents: ["hybrid"], reason: "requires --agents hybrid" },
      { not: { feature: other, reason: `requires --${other.replace(/_/g, "-")}` }, reason: `requires --${other.replace(/_/g, "-")} off` }],
  });
  raw.features.push(entry("water_flow", "water_index"), entry("water_index", "water_flow"));
  return raw;
}

function read(raw: unknown): FeatureCatalog {
  const reading = readFeatureCatalog(raw);
  if (reading.status !== "ok") throw new Error(JSON.stringify(reading));
  return reading.catalog;
}

describe("feature groups and exclusions", () => {
  it("reads a new group and a not condition", () => {
    const catalog = read(withWaterGroup());
    const flow = catalog.features.find((e) => e.key === "water_flow")!;
    expect(flow.group).toBe("Watersheds");
    expect(flow.requires[1]).toEqual({ kind: "not", reason: "requires --water-index off",
      part: { kind: "feature", key: "water_index", reason: "requires --water-index" } });
  });

  it("refuses both switches together and drops the first in catalog order", () => {
    const catalog = read(withWaterGroup());
    const live = catalog.surfaces.live;
    const flow = catalog.features.find((e) => e.key === "water_flow")!;
    expect(unmetRequirements(catalog, flow, { water_flow: true }, live, "hybrid")).toEqual([]);
    expect(unmetRequirements(catalog, flow, { water_flow: true, water_index: true }, live, "hybrid")
      .map((r) => r.reason)).toEqual(["requires --water-index off"]);
    expect(normalizeSelection(catalog, live, "hybrid", { water_flow: true, water_index: true }))
      .toEqual({ water_index: true });
    expect(normalizeSelection(catalog, live, "hybrid", { water_flow: true })).toEqual({ water_flow: true });
    expect(selectionFlags(catalog, { water_index: true, water_flow: false })).toEqual(["--no-water-flow", "--water-index"]);
  });

  const corruptions: [string, (raw: Raw) => void][] = [
    ["a not naming an unknown switch", (raw) => { raw.features.at(-1).requires[1].not.feature = "teleporters"; }],
    ["a not without a condition", (raw) => { raw.features.at(-1).requires[1].not = "water_flow"; }],
    ["a not with two conditions", (raw) => { raw.features.at(-1).requires[1].feature = "water_flow"; }],
  ];
  it.each(corruptions)("refuses %s", (_name, corrupt) => {
    const raw = withWaterGroup();
    corrupt(raw);
    expect(readFeatureCatalog(raw).status).toBe("invalid");
  });
});
