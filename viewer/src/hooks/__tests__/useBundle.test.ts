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

  it("parses history with correct length", () => {
    const result = parseBundle(JSON.stringify(sampleBundle));
    expect(result.bundle!.history.length).toBe(10);
  });
});
