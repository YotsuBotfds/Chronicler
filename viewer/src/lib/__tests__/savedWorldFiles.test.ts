import { describe, expect, it } from "vitest";
import fixture from "../../__fixtures__/sample_bundle.json";
import { parseBundle } from "../bundleFile";
import { answerDecodeRequest } from "../bundleDecode";
import { decodeBundleBytes } from "../bundleFile";

function bytes(text: string): ArrayBuffer { return new TextEncoder().encode(text).buffer; }
function checkpoint(header: unknown, body = new Uint8Array([0x80, 5, 0xff])): ArrayBuffer {
  const magic = new Uint8Array([0x89, ...new TextEncoder().encode("CHRONICLER-CKPT\r\n"), 0x1a, 0x0a]);
  const json = new TextEncoder().encode(JSON.stringify(header));
  const data = new Uint8Array(magic.length + 4 + json.length + body.length);
  data.set(magic);
  new DataView(data.buffer).setUint32(magic.length, json.length, true);
  data.set(json, magic.length + 4);
  data.set(body, magic.length + 4 + json.length);
  return data.buffer;
}
const header = { format: "chronicler-run-checkpoint", version: 1, world: { name: "Aetheris" },
  seed: 42, turn: 7, sections: [{ name: "python", offset: 0, length: 3 }] };

describe("saved file recognition", () => {
  it("recognizes the binary checkpoint header without reading native or pickle sections, identically in the worker", async () => {
    const data = checkpoint(header);
    const direct = await decodeBundleBytes("unhelpful.json", data);
    const worker = await answerDecodeRequest({ file: { name: "unhelpful.json", arrayBuffer: async () => data } as Blob & { name: string } }, () => { throw new Error("must not post bundle parts"); });
    expect(worker.kind === "decoded" && worker.result).toEqual(direct);
    expect(direct.bundle).toBeNull();
    expect(direct.error).toContain("seed 42, saved turn 7");
    expect(direct.error).toContain("header only; not a viewable bundle");
    expect(direct.error).toContain("--resume /path/to/checkpoint.ckpt --live --simulate-only");
    expect(direct.error).toContain("never deserializes");
  });
  it.each([
    ["truncated envelope", checkpoint(header).slice(0, 25), "incomplete or corrupt"],
    ["truncated section", checkpoint(header).slice(0, -1), "incomplete or corrupt"],
    ["wrong section offset", checkpoint({ ...header, sections: [{ offset: 1, length: 3 }] }), "incomplete or corrupt"],
    ["wrong format", checkpoint({ ...header, format: "other" }), "incomplete or corrupt"],
    ["future version", checkpoint({ ...header, version: 2 }), "unsupported format version 2"],
  ])("explains %s", async (_name, data, notice) => {
    const result = await decodeBundleBytes("run.ckpt", data as ArrayBuffer);
    expect(result.bundle).toBeNull();
    expect(result.error).toContain(notice);
  });
  it("distinguishes state JSON from recorded bundles without fabricating history", () => {
    const result = parseBundle(JSON.stringify(fixture.world_state));
    expect(result.bundle).toBeNull();
    expect(result.error).toContain("World state JSON detected");
    expect(result.error).toContain("--fork /path/to/state.json --seed NEW_SEED");
    expect(result.error).toContain("non-exact");
    expect(result.error).toContain("cannot recover earlier history");
  });
  it("does not trust file extensions", async () => {
    expect((await decodeBundleBytes("run.ckpt", bytes(JSON.stringify(fixture)))).bundle?.metadata.seed).toBe(42);
    expect((await decodeBundleBytes("bundle.json", bytes("random binary\u0000"))).error).toContain("Invalid JSON");
  });
});

describe("required bundle structure", () => {
  it.each([
    ["world_state", null, "world_state"], ["metadata", [], "metadata"], ["events_timeline", {}, "events_timeline"],
    ["named_events", [null], "named_events[0]"], ["chronicle_entries", null, "chronicle_entries"],
    ["era_reflections", [], "era_reflections"], ["history", [null], "history[0]"],
    ["history", [{ ...fixture.history[0], civ_stats: [] }], "civ_stats"],
    ["history", [{ ...fixture.history[0], region_control: { region: 3 } }], "region_control"],
    ["history", [{ ...fixture.history[0], relationships: { realm: [] } }], "relationships"],
    ["history", [{ ...fixture.history[0], finance: 3 }], "finance"],
    ["history", [{ ...fixture.history[0], civ_stats: { realm: { ...Object.values(fixture.history[0].civ_stats)[0], leader_name: {} } } }], "leader_name"],
    ["metadata", { ...fixture.metadata, seed: "42" }, "metadata.seed"],
    ["metadata", { ...fixture.metadata, bundle_version: 99 }, "unsupported"],
  ])("rejects malformed %s before render", (key, value, path) => {
    const result = parseBundle(JSON.stringify({ ...fixture, [key as string]: value }));
    expect(result.bundle).toBeNull();
    expect(result.error).toContain(path as string);
  });
  it("accepts old unversioned bundles with the legacy chronicle map", () => {
    const old = structuredClone(fixture) as unknown as Record<string, unknown>;
    delete (old.metadata as Record<string, unknown>).bundle_version;
    old.chronicle_entries = { "1": "A remembered turn" };
    expect(parseBundle(JSON.stringify(old)).error).toBeNull();
  });
});

it.each([
  ["civilizations", [{ name: "Incomplete realm" }], "regions"],
  ["civilizations", [{ ...fixture.world_state.civilizations[0], leader: null }], "leader"],
  ["civilizations", [{ ...fixture.world_state.civilizations[0], leader: { name: 1, trait: "bold" } }], "leader.name"],
  ["civilizations", [{ ...fixture.world_state.civilizations[0], values: {} }], "values"],
  ["regions", [null], "world_state.regions[0]"],
])("rejects incomplete viewable %s before identity or React", async (key, value, path) => {
  const result = await decodeBundleBytes("incomplete.json", bytes(JSON.stringify({ ...fixture,
    world_state: { ...fixture.world_state, [key as string]: value } })));
  expect(result.bundle).toBeNull();
  expect(result.identity).toBeNull();
  expect(result.error).toContain(path as string);
});

it("rejects reversed snapshots rather than presenting a false history", async () => {
  const result = await decodeBundleBytes("reversed.json", bytes(JSON.stringify({ ...fixture, history: [...fixture.history].reverse() })));
  expect(result.error).toContain("must follow the previous recorded turn");
});
