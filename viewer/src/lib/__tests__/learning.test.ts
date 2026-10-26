import { describe, expect, it } from "vitest";
import learningFixture from "../../__fixtures__/learning_bundle.json";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import type { Bundle } from "../../types";
import {
  fallLabel, KIND_LABELS, LEVEL_LABELS, levelLabel, seatHistory, seatKeys, seatLevelRows, seatRecord, seatRow,
  seatScholarSeries, seatsAt, seatStanding,
} from "../learning";
import { presentSystems } from "../systems";

const learning = learningFixture as unknown as Bundle;
const systems = systemsFixture as unknown as Bundle;
const seats = learning.world_state.scholarship!.seats!;

describe("seats of learning helpers", () => {
  it("lists every seat once, in order of first appearance", () => {
    const keys = seatKeys(learning.history);
    const ids = keys.map((key) => key.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.length).toBeGreaterThan(1);
    for (const key of keys) {
      expect(seats[key.id].name).toBe(key.name);
    }
    const firstSeen = ids.map((id) => learning.history.findIndex((snapshot) => seatRow(snapshot, id) !== null));
    expect([...firstSeen].sort((a, b) => a - b)).toEqual(firstSeen);
    expect(seatKeys(systems.history)).toEqual([]);
  });

  it("draws each seat's level over the snapshots it stood in", () => {
    const rows = seatLevelRows(learning.history, seatKeys(learning.history));
    const great = seats.findIndex((seat) => seat.peak_level === 3);
    expect(great).toBeGreaterThanOrEqual(0);
    const row = rows.find((entry) => entry.id === String(great))!;
    expect(row.segments.map((segment) => segment.text)).toContain("great");
    // A seat that fell is drawn up to the snapshot after its fall at most.
    const fallenRow = rows.find((entry) => seats[Number(entry.id)].fallen_turn != null)!;
    const fell = seats[Number(fallenRow.id)].fallen_turn!;
    const after = learning.history.find((snapshot) => snapshot.turn > fell)?.turn ?? fell + 1;
    expect(fallenRow.segments[fallenRow.segments.length - 1].end).toBeLessThanOrEqual(after);
  });

  it("leaves turns a seat did not stand as gaps, never zero", () => {
    const id = seatKeys(learning.history)[0].id;
    const series = seatScholarSeries(learning.history, id, "scholars");
    expect(series[0].scholars).toBeNull();
    expect(series.some((row) => row.scholars !== null)).toBe(true);
  });

  it("reads a fallen seat's record, its refuge and its moments up to the scrubbed turn", () => {
    const index = seats.findIndex((seat) => seat.fallen_turn != null && seat.refuge >= 0);
    const record = seatRecord(learning, index)!;
    expect(fallLabel(learning, record)).toContain(`fell at turn ${record.fallen_turn}`);
    expect(fallLabel(learning, record)).toContain(`its scholars fled to ${seats[record.refuge].name}`);
    const moments = seatHistory(learning, index, 10_000);
    expect(moments[moments.length - 1].kind).toBe("founded");
    expect(moments.map((moment) => moment.kind)).toContain("fell");
    expect(moments.every((moment) => moment.event !== null)).toBe(true);
    const early = seatHistory(learning, index, record.founded_turn);
    expect(early.map((moment) => moment.kind)).toContain("founded");
    expect(early.every((moment) => moment.turn === record.founded_turn)).toBe(true);
    expect(seatHistory(systems, 0, 500)).toEqual([]);
    expect(fallLabel(learning, seatRecord(learning, seats.findIndex((seat) => seat.fallen_turn == null))!)).toBe("");
  });

  it("names levels and kinds in the simulation's order and the standing of a row", () => {
    expect([0, 1, 2, 3].map(levelLabel)).toEqual([...LEVEL_LABELS]);
    expect(LEVEL_LABELS).toEqual(["fallen", "modest", "renowned", "great"]);
    expect(KIND_LABELS).toEqual(["academy", "temple school", "library"]);
    const row = { id: 0, name: "x", kind: "academy", region: null, lord: null, level: 1, scholars: 3, masters: 0 };
    expect(seatStanding(row)).toBe("-");
    expect(seatStanding({ ...row, unpaid: 2, refugees: 1.5 })).toBe("upkeep unpaid (2), 1.5 refugees");
    expect(seatsAt(null)).toEqual([]);
  });

  it("is a system of the bundle only when a snapshot records seats of learning", () => {
    expect(presentSystems(learning.history, learning.events_timeline)).toEqual(["learning"]);
    expect(presentSystems(systems.history, systems.events_timeline)).not.toContain("learning");
  });
});
