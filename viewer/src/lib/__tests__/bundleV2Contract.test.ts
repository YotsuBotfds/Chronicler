import { describe, expect, it } from "vitest";
import v2SmallManifest from "../../__fixtures__/bundle_v2/small/manifest.json";
import v2MediumManifest from "../../__fixtures__/bundle_v2/medium/manifest.json";
import { parseBundleV2Manifest } from "../bundleV2";

interface ManifestSchemaSignature {
  topLevelKeys: string[];
  layerDescriptorKeys: string[];
  kinds: string[];
}

function schemaSignature(manifest: Record<string, unknown>): ManifestSchemaSignature {
  const layers = Array.isArray(manifest.layers) ? (manifest.layers as Record<string, unknown>[]) : [];
  const layerKeys = new Set<string>();
  const kinds = new Set<string>();

  for (const layer of layers) {
    for (const key of Object.keys(layer)) {
      layerKeys.add(key);
    }
    if (typeof layer.kind === "string") {
      kinds.add(layer.kind);
    }
  }

  return {
    topLevelKeys: Object.keys(manifest).sort(),
    layerDescriptorKeys: [...layerKeys].sort(),
    kinds: [...kinds].sort(),
  };
}

describe("bundleV2 contract schema signatures", () => {
  it("locks top-level and layer descriptor shape for small fixture", () => {
    const parsed = parseBundleV2Manifest(v2SmallManifest);
    expect(parsed.error).toBeNull();
    expect(schemaSignature(parsed.manifest as unknown as Record<string, unknown>)).toEqual({
      topLevelKeys: [
        "bundle_schema_version",
        "layers",
        "manifest_version",
        "seed",
        "summary_layer",
        "total_turns",
      ],
      layerDescriptorKeys: ["id", "kind", "path", "required", "version"],
      kinds: ["entities", "summary", "timeline"],
    });
  });

  it("locks top-level and layer descriptor shape for medium fixture", () => {
    const parsed = parseBundleV2Manifest(v2MediumManifest);
    expect(parsed.error).toBeNull();
    expect(schemaSignature(parsed.manifest as unknown as Record<string, unknown>)).toEqual({
      topLevelKeys: [
        "bundle_schema_version",
        "layers",
        "manifest_version",
        "seed",
        "summary_layer",
        "total_turns",
      ],
      layerDescriptorKeys: ["id", "kind", "path", "required", "version"],
      kinds: ["detail", "entities", "metrics", "networks", "overlays", "summary", "timeline"],
    });
  });
});
