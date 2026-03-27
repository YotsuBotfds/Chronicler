import { describe, expect, it } from "vitest";
import {
  classifyParsedBundlePayload,
  formatBundleLoaderDiagnostics,
  parseBundleJsonPayload,
} from "../bundleLoader";
import sampleBundle from "../../__fixtures__/sample_bundle.json";
import v2SmallManifest from "../../__fixtures__/bundle_v2/small/manifest.json";
import v2MediumManifest from "../../__fixtures__/bundle_v2/medium/manifest.json";
import v2MissingRequiredLayer from "../../__fixtures__/bundle_v2/negative/missing_required_layer.json";
import v2UnknownLayerKind from "../../__fixtures__/bundle_v2/negative/unknown_layer_kind.json";
import v2MalformedManifest from "../../__fixtures__/bundle_v2/negative/malformed_manifest.json";

describe("bundleLoader", () => {
  it("classifies legacy bundles as supported", () => {
    const result = classifyParsedBundlePayload(sampleBundle);
    expect(result.kind).toBe("legacy");
    if (result.kind === "legacy") {
      expect(result.bundle.metadata.seed).toBe(42);
    }
  });

  it("classifies valid Bundle v2 manifests as pre-activation unsupported", () => {
    const small = classifyParsedBundlePayload(v2SmallManifest);
    expect(small.kind).toBe("manifest_v2");
    if (small.kind === "manifest_v2") {
      expect(small.manifest.summary_layer).toBe("summary.core.v1");
      expect(small.diagnostics[0].code).toBe("BUNDLE_V2_NOT_ACTIVE");
    }

    const medium = classifyParsedBundlePayload(v2MediumManifest);
    expect(medium.kind).toBe("manifest_v2");
  });

  it("returns schema errors for negative manifest fixtures", () => {
    const missingRequired = classifyParsedBundlePayload(v2MissingRequiredLayer);
    expect(missingRequired.kind).toBe("error");
    if (missingRequired.kind === "error") {
      expect(missingRequired.diagnostics[0].code).toBe("MANIFEST_SCHEMA_ERROR");
      expect(missingRequired.diagnostics[0].message).toContain("summary_layer must be required");
    }

    const unknownKind = classifyParsedBundlePayload(v2UnknownLayerKind);
    expect(unknownKind.kind).toBe("error");
    if (unknownKind.kind === "error") {
      expect(unknownKind.diagnostics[0].message).toContain("invalid layer descriptor");
    }

    const malformed = classifyParsedBundlePayload(v2MalformedManifest);
    expect(malformed.kind).toBe("error");
    if (malformed.kind === "error") {
      expect(malformed.diagnostics[0].message).toContain("missing layers array");
    }
  });

  it("formats diagnostics with manifest version context", () => {
    const result = parseBundleJsonPayload(JSON.stringify(v2SmallManifest));
    expect(result.kind).toBe("manifest_v2");
    if (result.kind === "manifest_v2") {
      const text = formatBundleLoaderDiagnostics(result.diagnostics);
      expect(text).toContain("manifest_version=1");
    }
  });
});
