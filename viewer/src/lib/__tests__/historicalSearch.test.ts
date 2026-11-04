import { describe, expect, it } from "vitest";
import { historicalSearchFixture } from "../../__fixtures__/historicalSearch";
import { comparisonSnapshot } from "../../__fixtures__/completedRunHistory";
import { buildHistoricalSearchIndex, searchHistoricalEntities } from "../historicalSearch";

describe("selected-turn historical search", () => {
  it("finds an older exact actor observation beyond the latest 200", () => {
    const bundle = historicalSearchFixture();
    bundle.history = Array.from({ length: 250 }, (_, i) => comparisonSnapshot(i + 1));
    bundle.history[0].civ_stats.A.leader_name = "Ancient Unique Actor";
    const result = searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 250), "Ancient Unique Actor", "actor");
    expect(result.total).toBe(1);
    expect(result.items[0]).toMatchObject({ turn: 1, identity: null, sourceRef: "/history/0/civ_stats/A/leader_name" });
  });
  it("indexes stable identities with first/last observed coverage through selected turn", () => {
    const index = buildHistoricalSearchIndex(historicalSearchFixture(), 3);
    expect(searchHistoricalEntities(index, "Old Realm", "civilization").items[0]).toMatchObject({
      identity: { namespace: "civilization", index: 0 }, firstRecordedTurn: 1, lastRecordedTurn: 3, turn: 3,
      sourceRef: "/history/1/civ_stats/Old Realm", mapEntity: { kind: "civilization", name: "Old Realm" },
    });
    expect(searchHistoricalEntities(index, "First Library").items[0]).toMatchObject({ kind: "institution", identity: { namespace: "scholarship", index: 7 } });
    expect(searchHistoricalEntities(index, "New Harbor").items[0]).toMatchObject({ kind: "city", identity: { namespace: "city", index: 41 } });
  });

  it("never matches final values, future-founded records, final actors or future aliases", () => {
    const index = buildHistoricalSearchIndex(historicalSearchFixture(), 3);
    expect(searchHistoricalEntities(index, "FUTURE_SECRET").total).toBe(0);
    expect(JSON.stringify(index)).not.toContain("FUTURE_SECRET");
    expect(searchHistoricalEntities(index, "Late Keeper").total).toBe(0);
    expect(searchHistoricalEntities(index, "First Library").total).toBe(1);
    expect(searchHistoricalEntities(buildHistoricalSearchIndex(historicalSearchFixture(), 1), "First Library").total).toBe(0);
  });

  it("keeps source tick T aliases hidden until completed snapshot T+1", () => {
    const bundle = historicalSearchFixture();
    expect(searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 0), "Aru").total).toBe(0);
    expect(searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 1), "Aru", "region").total).toBe(1);
    expect(searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 1), "Aru Confederacy").total).toBe(0);
    const alias = searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 2), "Aru Confederacy").items[0].aliases[0];
    expect(alias).toMatchObject({ turn: 2, sourceTurn: 1, sourceRef: "/languages/words/1/4/0" });
    expect(searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 3), "FUTURE_SECRET_FORM").total).toBe(0);
    expect(searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 4), "FUTURE_SECRET_FORM").total).toBe(1);
  });

  it("retains earlier recorded names by stable id without using final names", () => {
    const result = searchHistoricalEntities(buildHistoricalSearchIndex(historicalSearchFixture(), 3), "Old Harbor").items[0];
    expect(result.name).toBe("New Harbor");
    expect(result.aliases).toEqual([{ name: "Old Harbor", turn: 1, sourceRef: "/history/0/cities/cities/0" }]);
    expect(searchHistoricalEntities(buildHistoricalSearchIndex(historicalSearchFixture(), 1), "New Harbor").total).toBe(0);
  });

  it("shows static regions with unknown historical presence and no owner fallback", () => {
    const item = searchHistoricalEntities(buildHistoricalSearchIndex(historicalSearchFixture(), 0), "Unobserved Coast").items[0];
    expect(item).toMatchObject({ identity: { namespace: "region", index: 2 }, turn: null, firstRecordedTurn: null, lastRecordedTurn: null });
    expect(item.status).toContain("historical presence and owner not recorded");
    expect(item.mapEntity).toBeUndefined();
  });

  it("does not turn sparse absence into foundation or extinction", () => {
    const index = buildHistoricalSearchIndex(historicalSearchFixture(), 8);
    const civ = searchHistoricalEntities(index, "Old Realm", "civilization").items[0];
    expect(civ).toMatchObject({ firstRecordedTurn: 1, lastRecordedTurn: 6, turn: 6 });
    expect(civ.status).toContain("Fallen in this recorded snapshot");
    expect(civ.status).toContain("No observation at selected turn 8");
    const library = searchHistoricalEntities(index, "First Library").items[0];
    expect(library.lastRecordedTurn).toBe(3);
    expect(library.status).toContain("absence does not establish extinction or a founding date");
  });

  it("makes duplicate canonical-name histories ambiguous without inventing ids", () => {
    const bundle = historicalSearchFixture();
    bundle.world_state.civilizations.push({ ...bundle.world_state.civilizations[0] });
    bundle.world_state.regions.push({ ...bundle.world_state.regions[0] });
    const index = buildHistoricalSearchIndex(bundle, 3);
    const civ = searchHistoricalEntities(index, "Old Realm", "civilization").items[0];
    expect(civ.identity).toBeNull();
    expect(civ.ambiguity).toContain("Repeated civilization name");
    expect(civ.mapEntity).toBeUndefined();
    const regions = searchHistoricalEntities(index, "A", "region").items.filter((item) => item.name === "A");
    expect(regions.map((item) => item.identity?.index)).toEqual([0, 3]);
    expect(regions.every((item) => item.mapEntity === undefined && item.lastRecordedTurn === null && item.ambiguity)).toBe(true);
  });

  it("keeps duplicate institution ids and missing legacy identities unresolved", () => {
    const bundle = historicalSearchFixture();
    const seats = bundle.history[1].scholarship!.seats;
    seats.push({ ...seats[0], name: "Other Library" });
    bundle.history[0].civ_stats.Legacy = { ...bundle.history[0].civ_stats["Old Realm"] };
    const index = buildHistoricalSearchIndex(bundle, 3);
    expect(searchHistoricalEntities(index, "Library", "institution").items.every((item) => item.identity === null && item.ambiguity)).toBe(true);
    expect(searchHistoricalEntities(index, "Legacy", "civilization").items[0]).toMatchObject({ identity: null, ambiguity: "Legacy name has no recorded stable array identity." });
  });

  it("does not combine repeated actor names into identities, aliases or life histories", () => {
    const index = buildHistoricalSearchIndex(historicalSearchFixture(), 3);
    const actors = searchHistoricalEntities(index, "Aster", "actor").items;
    expect(actors).toHaveLength(2);
    expect(actors.map((item) => item.turn)).toEqual([3, 1]);
    expect(actors.every((item) => item.identity === null && item.aliases.length === 0 && item.firstRecordedTurn === item.lastRecordedTurn)).toBe(true);
    expect(actors[0].sourceRef).not.toBe(actors[1].sourceRef);
  });

  it("keeps identically named institutions distinct by their recorded ids and namespaces", () => {
    const bundle = historicalSearchFixture();
    const seats = bundle.history[1].scholarship!.seats;
    seats.push({ ...seats[0], id: 8 });
    bundle.history[1].guilds = { guilds: [{ id: 7, name: "First Library", city: 41, region: "A", kind: "craft",
      masters: 2, wealth: 10, monopoly: false, say: false }], dissolved: 0, burghers: {}, counters: {} };
    const matches = searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 3), "First Library", "institution").items;
    expect(matches.map((item) => item.identity)).toEqual([
      { namespace: "scholarship", index: 7 }, { namespace: "scholarship", index: 8 }, { namespace: "guild", index: 7 },
    ]);
  });

  it("sorts observed dates without rewriting source addresses or source order", () => {
    const bundle = historicalSearchFixture();
    bundle.history.reverse();
    const result = searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 3), "Old Harbor").items[0];
    expect(result).toMatchObject({ name: "New Harbor", firstRecordedTurn: 1, lastRecordedTurn: 3,
      sourceRef: "/history/2/cities/cities/0" });
    expect(result.aliases[0].sourceRef).toBe("/history/3/cities/cities/0");
    expect(bundle.history.map((row) => row.turn)).toEqual([10, 6, 3, 1]);
  });

  it("rejects undated word forms rather than guessing a first name or using a tail", () => {
    const bundle = historicalSearchFixture();
    bundle.languages!.words.push([3, "region", 0, 0, [[null, "UNDATED_SECRET", null]], "UNDATED_TAIL"]);
    bundle.languages!.words.push([4, "region", 0, null, [[0, "UNCOINED_SECRET", null]], ""]);
    const index = buildHistoricalSearchIndex(bundle, 3);
    expect(searchHistoricalEntities(index, "UNDATED").total).toBe(0);
    expect(searchHistoricalEntities(index, "UNCOINED").total).toBe(0);
  });

  it("searches all actor observations while bounding output and reporting coverage", () => {
    const bundle = historicalSearchFixture();
    bundle.history = Array.from({ length: 250 }, (_, index) => comparisonSnapshot(index + 1));
    const index = buildHistoricalSearchIndex(bundle, 250);
    expect(index.items.filter((item) => item.kind === "actor")).toHaveLength(0);
    expect(index.coverage.join(" ")).toContain("750 dated observations searchable");
    expect(searchHistoricalEntities(index, "", "actor").total).toBe(750);
    expect(searchHistoricalEntities(index, "", "actor").items).toHaveLength(30);
    expect(searchHistoricalEntities(index, "", "actor", 500).items).toHaveLength(100);
    expect(searchHistoricalEntities(index, "", "actor", -1).items).toHaveLength(0);
  });

  it("keeps repeated old names as separate observations and follows the selected turn", () => {
    const bundle = historicalSearchFixture();
    bundle.history = Array.from({ length: 1000 }, (_, i) => comparisonSnapshot(i + 1));
    bundle.history[0].civ_stats.A.leader_name = "Shared Name";
    bundle.history[1].civ_stats.B.leader_name = "Shared Name";
    bundle.history[999].civ_stats.A.leader_name = "Shared Name";
    const old = searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 999), "Shared Name", "actor");
    expect(old.total).toBe(2);
    expect(old.items.map((item) => item.turn)).toEqual([2, 1]);
    expect(old.items.every((item) => item.identity === null && item.aliases.length === 0)).toBe(true);
    expect(searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 1000), "Shared Name", "actor").total).toBe(3);
    expect(searchHistoricalEntities(buildHistoricalSearchIndex(bundle, 1), "Shared Name", "actor").total).toBe(1);
  });

  it("excludes ambiguous snapshot turns and preserves input order and bytes", () => {
    const bundle = historicalSearchFixture();
    bundle.history.push(structuredClone(bundle.history[0]));
    const before = JSON.stringify(bundle);
    const index = buildHistoricalSearchIndex(bundle, 3);
    expect(searchHistoricalEntities(index, "Old Harbor").total).toBe(0);
    expect(searchHistoricalEntities(index, "Old Realm", "civilization").items[0].firstRecordedTurn).toBe(3);
    expect(index.coverage[0]).toContain("1 duplicate snapshot turns excluded");
    expect(JSON.stringify(bundle)).toBe(before);
  });

  it("works on older bundles without optional systems or languages and rejects invalid clocks", () => {
    const bundle = historicalSearchFixture();
    delete bundle.languages;
    bundle.history.forEach((row) => { delete row.cities; delete row.scholarship; delete row.civ_stats["Old Realm"]?.great_persons; });
    const index = buildHistoricalSearchIndex(bundle, 3);
    expect(searchHistoricalEntities(index, "Old Realm", "civilization").total).toBe(1);
    expect(searchHistoricalEntities(index, "", "institution").total).toBe(0);
    expect(buildHistoricalSearchIndex(bundle, NaN).items).toEqual([]);
  });
});
