import { describe, expect, it } from "vitest";
import movementsFixture from "../../__fixtures__/movements_bundle.json";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import type { Bundle } from "../../types";
import {
  creedSeries, END_LABELS, leaderLabel, martyrdoms, memberSeries, movementHistory, movementKeys, movementRecord,
  movementRecordNote, movementRow,
  movementStageRows, reformKind, reformName, reformRecord, reformsInForce, STAGE_COLORS,
} from "../movements";
import { presentSystems } from "../systems";

const movements = movementsFixture as unknown as Bundle;
const systems = systemsFixture as unknown as Bundle;
const records = movements.world_state.agent_movements!.movements!;
const reforms = movements.world_state.agent_movements!.reforms!;

describe("movement helpers", () => {
  it("lists every movement once, in order of first appearance", () => {
    const keys = movementKeys(movements.history);
    const ids = keys.map((key) => key.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(keys.length).toBeGreaterThan(3);
    for (const key of keys) {
      expect(key.name).toBe(records[key.id].name);
    }
    const firstSeen = ids.map((id) => movements.history.findIndex((snapshot) => movementRow(snapshot, id) != null));
    expect([...firstSeen].sort((a, b) => a - b)).toEqual(firstSeen);
    expect(movementKeys(systems.history)).toEqual([]);
  });

  it("draws each movement's stage over the snapshots it lived in", () => {
    const keys = movementKeys(movements.history);
    const rows = movementStageRows(movements.history, keys);
    expect(rows).toHaveLength(keys.length);
    const won = keys.find((key) => END_LABELS[records[key.id].end] === "won")!;
    const row = rows.find((entry) => entry.id === String(won.id))!;
    expect(row.label).toBe(`${won.name} (${won.creed})`);
    expect(row.segments.map((segment) => segment.text)).toContain("satisfied");
    for (const segment of row.segments) {
      expect(segment.color).toBe(STAGE_COLORS[segment.text!]);
      expect(segment.end).toBeGreaterThan(segment.start);
    }
  });

  it("leaves turns a movement did not live as gaps, never zero", () => {
    const [first] = movementKeys(movements.history);
    const series = memberSeries(movements.history, first.id, "members");
    const living = series.filter((row) => row.members != null);
    expect(living.length).toBeGreaterThan(0);
    expect(series.find((row) => row.turn < records[first.id].founded_turn)?.members ?? null).toBeNull();
    expect(living.every((row) => (row.members as number) >= 0)).toBe(true);
  });

  it("names the lasting reforms as the record does", () => {
    const relief = reforms.find((reform) => reformKind(reform) === "relief")!;
    expect(reformName(movements, { kind: reformKind(relief) })).toBe("poor relief");
    const regions = movements.world_state.regions;
    expect(reformName(movements, { kind: "home_rule", regions: [0, 1] }))
      .toBe(`home rule of ${regions[0].name}, ${regions[1].name}`);
    const faith = movements.world_state.belief_registry![0];
    expect(reformName(movements, { kind: "toleration", faith: faith.faith_id })).toBe(`toleration of the ${faith.name}`);
    expect(reformName(movements, { kind: "toleration", faith: faith.faith_id, church: true }))
      .toBe(`reform of the ${faith.name}`);
    expect(reformName(movements, { kind: "toleration", faith: 250 })).toBe("toleration");
  });

  it("reads the reforms in force at a snapshot", () => {
    const withReforms = movements.history.find((snapshot) => reformsInForce(snapshot).length > 0)!;
    for (const row of reformsInForce(withReforms)) {
      const record = reformRecord(movements, row.id)!;
      expect(record.enacted_turn).toBe(row.since);
      expect(record.enacted_turn).toBeLessThanOrEqual(withReforms.turn);
      expect(record.repealed_turn == null || record.repealed_turn > withReforms.turn).toBe(true);
    }
    expect(reformsInForce(systems.history[0])).toEqual([]);
  });

  it("reads a movement's moments up to the scrubbed turn, latest first, then its reform's repeal", () => {
    const id = records.findIndex((record) => {
      const reform = record.reform != null && record.reform >= 0 ? reforms[record.reform] : null;
      return reform != null && reform.repeal > 0 && reform.movement === records.indexOf(record);
    });
    const record = movementRecord(movements, id)!;
    const repealed = reforms[record.reform!];
    const all = movementHistory(movements, id, 500);
    expect(all[0].turn).toBe(repealed.repealed_turn);
    expect(all[0].kind).toMatch(/^reform (repealed|lapsed)$/);
    expect(all[0].event?.event_type).toMatch(/^reform_(repealed|lapsed)$/);
    expect(all.map((moment) => moment.turn)).toEqual([...all.map((moment) => moment.turn)].sort((a, b) => b - a));
    expect(all[all.length - 1].kind).toBe("founded");
    const early = movementHistory(movements, id, record.founded_turn);
    expect(early.map((moment) => moment.kind)).toEqual(["founded"]);
    expect(movementHistory(systems, 0, 500)).toEqual([]);
  });

  it("counts living movements by creed", () => {
    const series = creedSeries(movements.history);
    const index = series.findIndex((row) => (row.commons ?? 0) + (row.liberty ?? 0) + (row.sect ?? 0) > 0);
    const living = movements.history[index].agent_movements!.living;
    expect(series[index].sect).toBe(living.filter((row) => row.creed === "sect").length);
    expect(creedSeries(systems.history)[0].commons).toBeNull();
  });

  it("reads a movement's final record as one sentence and marks an end after the scrubbed turn", () => {
    const record = { ...records[0], creed: 2, founded_turn: 106, leader: "", peak_members: 19, demands: 1,
      martyrs: 0, end: END_LABELS.indexOf("won"), ended_turn: 201 };
    expect(movementRecordNote(record, "Thavigrimi Kingdom", "Magur Meadows", 191)).toBe(
      "A sect movement against Thavigrimi Kingdom, founded turn 106 in Magur Meadows. "
      + "Whole record: peak 19 members, 1 demand, 0 martyrs; won its demand at turn 201 (after turn 191).");
    expect(movementRecordNote({ ...record, leader: "Ilra", end: 0, ended_turn: null }, null, null, 300)).toBe(
      "A sect movement against ?, founded turn 106 in ?, led by Ilra. "
      + "Whole record: peak 19 members, 1 demand, 0 martyrs.");
  });

  it("marks a leader the record says was martyred, from the turn of the martyrdom", () => {
    const martyr = { turn: 62, event_type: "movement_martyr", actors: ["Selurian Republic", "Archon Banyaris"],
      description: "The death of Archon Banyaris makes a martyr", consequences: [], importance: 5 };
    const martyred = martyrdoms([martyr]);
    expect(leaderLabel("Archon Banyaris", martyred, 72)).toBe("Archon Banyaris (martyred T62)");
    expect(leaderLabel("Archon Banyaris", martyred, 61)).toBe("Archon Banyaris");
    expect(leaderLabel(undefined, martyred, 72)).toBe("-");
    // In the movements fixture every martyrdom names a movement's leader.
    for (const [leader] of martyrdoms(movements.events_timeline)) {
      expect(records.some((record) => record.leader === leader)).toBe(true);
    }
  });

  it("is a system of the bundle only when a snapshot records movements", () => {
    expect(presentSystems(movements.history, movements.events_timeline)).toEqual(["movements"]);
    expect(presentSystems(systems.history, systems.events_timeline)).not.toContain("movements");
  });
});
