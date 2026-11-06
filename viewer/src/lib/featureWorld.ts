import type { FeatureSelection } from "../types";
import { featurePayload, readFeatureCatalog, type FeatureSurface, type FeatureSurfaceName } from "./featureCatalog";

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

/** Catalog settings that depend on the world a start requests. */
export const WORLD_SETTINGS: readonly string[] = ["procedural_world"];

/**
 * A live start's `features`: the selection, plus every switch the server's
 * command line already turns on whose requirements depend on the requested
 * world, named explicitly. The run checks that world; when it refuses a
 * switch the start named, the server reopens the lobby with the reason,
 * where an unnamed (inherited) one would end the session. A saved state
 * (`resumeState`) takes no features, so such a switch is named only when the
 * saved world does not already carry its record: the server then refuses the
 * start (features apply to new worlds only) and the lobby stays open.
 */
export function liveStartFeatures(rawCatalog: unknown, selection: FeatureSelection,
  resumeState?: unknown): FeatureSelection | undefined {
  const reading = readFeatureCatalog(rawCatalog);
  const pins: FeatureSelection = {};
  if (reading.status === "ok") {
    const live = reading.catalog.surfaces.live;
    const saved = typeof resumeState === "object" && resumeState !== null
      ? (resumeState as { livelihoods?: unknown }).livelihoods : undefined;
    for (const entry of reading.catalog.features) {
      if (entry.kind !== "bool" || live.values[entry.key] !== true || entry.key in selection) continue;
      if (!entry.requires.some((req) => req.kind === "setting" && WORLD_SETTINGS.includes(req.key))) continue;
      if (resumeState && typeof saved === "object" && saved !== null
        && (saved as Record<string, unknown>)[entry.key] != null) continue;
      pins[entry.key] = true;
    }
  }
  if (resumeState) return Object.keys(pins).length > 0 ? pins : undefined;
  return featurePayload({ ...pins, ...selection });
}
