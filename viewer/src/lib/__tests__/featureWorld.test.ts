import { describe, expect, it } from "vitest";
import served from "../../__fixtures__/featureCatalog.json";
import { readFeatureCatalog } from "../featureCatalog";
import { TEMPLATE_REGION_POOL, surfaceForWorld } from "../featureWorld";

describe("surfaceForWorld", () => {
  const reading = readFeatureCatalog(served);
  if (reading.status !== "ok") throw new Error("fixture unreadable");
  const { live, batch } = reading.catalog.surfaces;

  it("recomputes Batch Lab's procedural_world from the regions the batch will send", () => {
    expect(TEMPLATE_REGION_POOL).toBe(12);
    expect(batch.settings.procedural_world).toBe(false);
    expect(surfaceForWorld(batch, "batch", { regions: 13 }).settings.procedural_world).toBe(true);
    expect(surfaceForWorld(batch, "batch", { regions: 12 }).settings.procedural_world).toBe(false);
    expect(surfaceForWorld(batch, "batch", { regions: null })).toBe(batch);
    expect(surfaceForWorld(batch, "batch", undefined)).toBe(batch);
    expect(surfaceForWorld(batch, "batch", { regions: 32 }).settings.cities).toBe(batch.settings.cities);
  });

  it("serves the live surface as is: the run checks a live start's world", () => {
    expect(surfaceForWorld(live, "live", { regions: 32 })).toBe(live);
  });
});
