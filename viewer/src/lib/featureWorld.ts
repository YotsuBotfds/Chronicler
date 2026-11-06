import type { FeatureSurface, FeatureSurfaceName } from "./featureCatalog";

/**
 * The template pool: a world of more than this many regions is procedural
 * under `--worldgen auto` (`chronicler.world_gen.resolve_worldgen`; Batch Lab
 * passes no `--worldgen`). `tests/test_watershed.py` pins the Python side.
 */
export const TEMPLATE_REGION_POOL = 12;

/** The world a request will build, as far as the viewer chooses it. */
export interface FeatureWorld {
  regions?: number | null;
}

/**
 * The surface a request is checked against, with the settings that depend on
 * the requested world recomputed: Batch Lab's `procedural_world` follows the
 * regions it will send, as the server's batch check does. The live surface is
 * served as is: a live start's world is checked by the run itself.
 */
export function surfaceForWorld(surface: FeatureSurface, surfaceName: FeatureSurfaceName,
  world: FeatureWorld | undefined): FeatureSurface {
  if (surfaceName !== "batch" || !world || typeof world.regions !== "number" || !Number.isInteger(world.regions)
    || world.regions <= 0 || !("procedural_world" in surface.settings)) return surface;
  return { ...surface, settings: { ...surface.settings, procedural_world: world.regions > TEMPLATE_REGION_POOL } };
}
