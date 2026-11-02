import { expect, it } from "vitest";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import { investigationMarkdown, investigationPacket, resolveInvestigationTarget } from "../investigationPacket";
const target = { kind: "region", index: 0, name: "A" } as const;
const identity = { name: "/private/machine/world.json", sha256: "a".repeat(64), byteLength: 123 };
it("exports exact source observations, unknown old population, bounded explicit reports and no future values", () => {
  const bundle = comparisonBundle();
  bundle.events_timeline[0].region = "A";
  bundle.events_timeline.push({ ...bundle.events_timeline[0], turn: 9, event_type: "SECRET" });
  const packet = investigationPacket(bundle, identity, target, 1);
  expect(packet.observations.find((row) => row.id === "population")?.value).toBeNull();
  expect(packet.observations.find((row) => row.id === "food")?.value).toBe(0.5);
  expect(packet.snapshotRef).toBe("/history/0"); expect(packet.reports.items).toHaveLength(1);
  expect(JSON.stringify(packet)).not.toContain("SECRET");
  expect(packet.artifact?.filename).toBe("world.json");
});
it("never substitutes final data or allows aliases, duplicate names, missing/ambiguous turns or future civilians", () => {
  const bundle = comparisonBundle([1, 3]);
  expect(resolveInvestigationTarget(bundle, target, 2)).toMatch(/unavailable/);
  expect(() => investigationPacket(bundle, identity, { ...target, index: 1 }, 1)).toThrow(/identity/);
  bundle.world_state.regions[1].name = "A";
  expect(() => investigationPacket(bundle, identity, target, 1)).toThrow(/ambiguous/);
  expect(resolveInvestigationTarget(bundle, { kind: "civilization", index: 0, name: "A" }, 1)).toBeNull();
  delete bundle.history[0].civ_stats.A;
  expect(resolveInvestigationTarget(bundle, { kind: "civilization", index: 0, name: "A" }, 1)).toMatch(/no recorded row/);
});
it("omits raw source/header/runtime paths, credentials, arbitrary metadata and private notes by construction", () => {
  const bundle = comparisonBundle();
  Object.assign(bundle.metadata, { source: { private: "/private/SECRET" }, source_commit: "b".repeat(40),
    what_if: { source: { checkpoint: { path: "/private/SECRET" } } }, api_key: "SECRET", notes: "SECRET" });
  const packet = investigationPacket(bundle, identity, target, 1);
  expect(packet.source).toEqual({ source_commit: "b".repeat(40) });
  expect(JSON.stringify(packet)).not.toMatch(/SECRET|\/private/);
  expect(investigationMarkdown(packet)).toContain("null");
});
it("keeps native/model counts separate, caps references with disclosed counts, and labels unbound live sources", () => {
  const bundle = regionalFixture(); const name = bundle.world_state.regions[0].name;
  const packet = investigationPacket(bundle, null, { ...target, name }, 2);
  expect(packet.artifact).toBeNull(); expect(packet.observations.find((row) => row.id === "population")?.value).toBe(100);
  bundle.events_timeline = Array.from({ length: 70 }, (_, i) => ({ ...bundle.events_timeline[0], turn: 0,
    actors: [], consequences: [], importance: 1, description: "Recorded", event_type: "dearth", region: name, event_id: `e${i}` }));
  const reports = investigationPacket(bundle, identity, { ...target, name }, 2).reports;
  expect(reports.total).toBe(70); expect(reports.included).toBe(50); expect(reports.items[0].eventId).toBe("e20");
});
