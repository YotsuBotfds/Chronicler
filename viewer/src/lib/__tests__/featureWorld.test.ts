import { describe, expect, it } from "vitest";
import served from "../../__fixtures__/featureCatalog.json";
import { readFeatureCatalog } from "../featureCatalog";
import { TEMPLATE_REGION_POOL, liveStartFeatures, surfaceForWorld } from "../featureWorld";

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

describe("liveStartFeatures", () => {
  const inherited = structuredClone(served) as typeof served & { surfaces: { live: { values: Record<string, unknown> } } };
  inherited.surfaces.live.values = { watershed: true };

  it("sends the selection as before when the server sets no world-dependent switch", () => {
    expect(liveStartFeatures(served, {})).toBeUndefined();
    expect(liveStartFeatures(served, { workshops: true })).toEqual({ workshops: true });
    expect(liveStartFeatures(undefined, { workshops: true })).toEqual({ workshops: true });   // an older server
  });

  it("names the server's --watershed in a new world's start, so a template start is refused and the lobby reopens (review N1)", () => {
    expect(liveStartFeatures(inherited, {})).toEqual({ watershed: true });
    expect(liveStartFeatures(inherited, { workshops: true })).toEqual({ watershed: true, workshops: true });
    expect(liveStartFeatures(inherited, { watershed: false })).toEqual({ watershed: false });   // the user's choice wins
  });

  it("names it for a saved state only when that world has no account (the server then refuses the start)", () => {
    expect(liveStartFeatures(inherited, { workshops: true }, { turn: 4, livelihoods: null })).toEqual({ watershed: true });
    expect(liveStartFeatures(inherited, {}, { turn: 4, livelihoods: { schema_version: 1, watershed: { enabled: true } } }))
      .toBeUndefined();
    expect(liveStartFeatures(served, { workshops: true }, { turn: 4 })).toBeUndefined();
  });
});

