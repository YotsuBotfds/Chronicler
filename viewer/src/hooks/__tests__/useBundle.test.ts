import { describe, it, expect } from "vitest";
import { parseBundle } from "../useBundle";
import sampleBundle from "../../__fixtures__/sample_bundle.json";

describe("parseBundle", () => {
  it("parses a valid bundle JSON string", () => {
    const result = parseBundle(JSON.stringify(sampleBundle));
    expect(result.bundle).toBeDefined();
    expect(result.error).toBeNull();
    expect(result.bundle!.metadata.seed).toBe(42);
  });

  it("returns error for invalid JSON", () => {
    const result = parseBundle("not json");
    expect(result.bundle).toBeNull();
    expect(result.error).toContain("Invalid JSON");
  });

  it("returns error for missing required keys", () => {
    const result = parseBundle(JSON.stringify({ world_state: {} }));
    expect(result.bundle).toBeNull();
    expect(result.error).toContain("Missing required");
  });

  it("returns explicit compatibility error for Bundle v2 manifests", () => {
    const result = parseBundle(
      JSON.stringify({
        manifest_version: 1,
        bundle_schema_version: "2.0.0",
        seed: 42,
        total_turns: 500,
        summary_layer: "summary.core.v1",
        layers: [
          {
            id: "summary.core.v1",
            kind: "summary",
            version: "1.0.0",
            path: "layers/summary.core.v1.json",
            required: true,
          },
        ],
      }),
    );
    expect(result.bundle).toBeNull();
    expect(result.error).toContain("Bundle v2 manifest detected");
    expect(result.error).toContain("legacy single-artifact adapter export");
  });

  it("returns specific validation errors for malformed Bundle v2 manifests", () => {
    const result = parseBundle(
      JSON.stringify({
        manifest_version: 1,
        bundle_schema_version: "2.0.0",
        layers: [],
      }),
    );
    expect(result.bundle).toBeNull();
    expect(result.error).toContain("Bundle v2 manifest error");
  });

  it("parses history with correct length", () => {
    const result = parseBundle(JSON.stringify(sampleBundle));
    expect(result.bundle!.history.length).toBe(10);
  });
});
