import { describe, expect, it } from "vitest";
import faithsFixture from "../../__fixtures__/faiths_bundle.json";
import legacyFixture from "../../__fixtures__/faiths_legacy_bundle.json";
import movementsFixture from "../../__fixtures__/movements_bundle.json";
import sampleFixture from "../../__fixtures__/sample_bundle.json";
import type { Bundle } from "../../types";
import {
  faithAt, faithEvents, faithLabel, faithsKnownAt, faithTable, hasFaithRecord, parseSchism, reconstructFaiths,
  resolveFaith, slotSharers, successorInSlot, templeEventText,
} from "../faiths";
import { faithName, movementRecordAt, reformName } from "../movements";
import { presentSystems } from "../systems";

/**
 * Procedural seed 42 (32 regions, 10 civs), 200 hybrid turns, every tenth
 * snapshot: four sects took the slots of vanished faiths (turns 37, 100,
 * 134, 168). `faiths_bundle.json` is the run with permanent faith ids;
 * `faiths_legacy_bundle.json` the same run written before them (main 7c44ed8),
 * whose records name faiths by slot.
 */
const faiths = faithsFixture as unknown as Bundle;
const legacy = legacyFixture as unknown as Bundle;
const movements = movementsFixture as unknown as Bundle;
const sample = sampleFixture as unknown as Bundle;
const LAST = faiths.history[faiths.history.length - 1].turn;

const identity = (bundle: Bundle) => faithTable(bundle).faiths
  .map((rec) => [rec.name, rec.slot, rec.founded_turn, rec.released_turn ?? null, rec.origin].join("|")).sort();

describe("faith table", () => {
  it("reads the recorded table, one record per church, never reusing an id", () => {
    const table = faithTable(faiths);
    expect(table.legacy).toBe(false);
    expect(table.faiths).toHaveLength(20);
    const released = table.faiths.flatMap((rec, id) => (rec.released_turn != null ? [id] : []));
    expect(released).toEqual([10, 11, 13, 15]);
    // Slot 10: the Duglutoni schism of turn 2 until turn 37, then a sect.
    expect(faithAt(table.faiths, 10, 36)).toBe(10);
    expect(faithAt(table.faiths, 10, 37)).toBe(16);
    expect(faithAt(table.faiths, 10, null)).toBe(16);
    expect(faithLabel(table, 10)).toBe("Faith of Duglutoni Principality (Reformed) (founded turn 2)");
    expect(faithLabel(table, 16)).toBe("Faith of Lisolenen League (Reformed) (founded turn 37)");
    expect(successorInSlot(table, 10, LAST)).toBe(16);
    expect(successorInSlot(table, 10, 36)).toBeNull();
    expect(slotSharers(table, 16, LAST)).toEqual([10]);
    expect(slotSharers(table, 16, 20)).toEqual([]);
    expect(faithsKnownAt(table, 36)).toHaveLength(16);
    expect(resolveFaith(table, 16, 0)).toBe(16);   // a permanent id is not a slot
    expect(resolveFaith(table, 255, 0)).toBeNull();
  });

  it("rebuilds an older bundle's table from its registry and schism records, as the run recorded it", () => {
    const table = faithTable(legacy);
    expect(table.legacy).toBe(true);
    expect(identity(legacy)).toEqual(identity(faiths));
    // Live faiths keep id == slot; the vanished ones follow in the order they gave up their slot.
    expect(table.faiths.slice(0, 16).every((rec, id) => rec.slot === id)).toBe(true);
    expect(table.faiths.slice(16).map((rec) => rec.released_turn)).toEqual([37, 100, 134, 168]);
    expect(table.faiths.every((rec) => rec.legacy === "reconstructed")).toBe(true);
    // An older record's slot is read as it stood when it was written.
    expect(faithLabel(table, resolveFaith(table, 10, 30))).toBe(faithLabel(faithTable(faiths), 10));
    expect(faithLabel(table, resolveFaith(table, 10, 40))).toBe(faithLabel(faithTable(faiths), 16));
  });

  it("names the same churches in the older bundle's records as in the recorded run", () => {
    const records = faiths.world_state.agent_movements!.movements!;
    let sects = 0;
    records.forEach((record, id) => {
      if (record.creed !== 2) {
        return;
      }
      sects += 1;
      const now = movementRecordAt(faiths, id, LAST)!;
      const then = movementRecordAt(legacy, id, LAST)!;
      expect(then.church).toBe(now.church);
      expect(then.becameChurch).toBe(now.becameChurch);
    });
    expect(sects).toBeGreaterThan(5);
    for (const [k, snapshot] of faiths.history.entries()) {
      const rows = snapshot.agent_movements?.reforms ?? [];
      const old = legacy.history[k].agent_movements?.reforms ?? [];
      expect(old.map((row) => reformName(legacy, row, legacy.history[k].turn - 1)))
        .toEqual(rows.map((row) => reformName(faiths, row, snapshot.turn - 1)));
    }
  });

  it("marks the faiths an older record cannot trace", () => {
    // The movements fixture keeps the registry but no schism events.
    const table = faithTable(movements);
    expect(table.legacy).toBe(true);
    const reformed = table.faiths.filter((rec) => rec.name.includes("(Reformed"));
    expect(reformed.length).toBeGreaterThan(0);
    for (const rec of reformed) {
      expect([rec.founded_turn, rec.origin, rec.legacy]).toEqual([null, "unrecorded", "unresolved"]);
    }
    expect(faithLabel(table, table.faiths.indexOf(reformed[0]))).toBe(`${reformed[0].name} (founding not recorded)`);
    const founding = table.faiths.filter((rec) => rec.origin === "founding");
    expect(founding.every((rec) => rec.founded_turn === 0)).toBe(true);
  });

  it("reads both wordings of a schism", () => {
    expect(parseSchism("A schism fractures Kethani Empire: 'Faith of K (Reformed)' splits from the majority faith "
      + "in Amber Valley (minority_ratio=0.40)")).toMatchObject({
      newName: "Faith of K (Reformed)", kind: "schism", civ: "Kethani Empire", region: "Amber Valley",
    });
    expect(parseSchism("the Seekers of X breaks away from the Faith of K in Amber Valley: 'Faith of K (Reformed)' is "
      + "founded in place of the vanished 'Old Faith'")).toMatchObject({
      newName: "Faith of K (Reformed)", parent: "Faith of K", region: "Amber Valley", vanished: "Old Faith",
      movement: "the Seekers of X", kind: "sect",
    });
    expect(parseSchism("Something else")).toBeNull();
    // An unparseable schism leaves every live faith unresolved.
    const rows = reconstructFaiths([{ faith_id: 0, name: "Faith of A" }], [
      { turn: 3, event_type: "Schism", actors: [], description: "garbled", consequences: [], importance: 7 },
    ], ["A"]);
    expect(rows[0].legacy).toBe("unresolved");
  });

  it("finds a faith's own events and tells its temples by name", () => {
    const table = faithTable(faiths);
    const founding = faithEvents(faiths, table, 16, LAST);
    expect(founding.map((event) => [event.turn, event.event_type])).toContainEqual([37, "Schism"]);
    const temples = faiths.events_timeline.filter((event) => event.event_type === "temple_destroyed");
    expect(temples.length).toBeGreaterThan(0);
    const text = templeEventText(table, temples[0])!;
    expect(text).toMatch(/^The temple of the .+ \(founded turn \d+\) is (destroyed|replaced) in /);
    // The older bundle's slot is resolved at the event's turn: the same faith.
    expect(templeEventText(faithTable(legacy), legacy.events_timeline.find(
      (event) => event.event_type === "temple_destroyed")!)).toBe(text);
  });

  it("is a systems tab for a recorded table or an older run with a schism, not for older founding faiths only", () => {
    expect(hasFaithRecord(faiths)).toBe(true);
    expect(hasFaithRecord(legacy)).toBe(true);
    expect(hasFaithRecord(sample)).toBe(false);
    expect(presentSystems(faiths.history, faiths.events_timeline, hasFaithRecord(faiths)))
      .toEqual(["movements", "faiths"]);
    expect(presentSystems(sample.history, sample.events_timeline, hasFaithRecord(sample))).toEqual([]);
  });

  it("names a toleration's faith with its founding turn", () => {
    const sect = faithName(faiths, 16);
    expect(sect).toBe("Faith of Lisolenen League (Reformed) (founded turn 37)");
    expect(reformName(faiths, { kind: "toleration", faith: 16 })).toBe(`toleration of the ${sect}`);
    expect(reformName(legacy, { kind: "toleration", faith: 10 }, 150)).toBe(`toleration of the ${sect}`);
    expect(reformName(legacy, { kind: "toleration", faith: 10 }, 20))
      .toBe("toleration of the Faith of Duglutoni Principality (Reformed) (founded turn 2)");
  });
});
