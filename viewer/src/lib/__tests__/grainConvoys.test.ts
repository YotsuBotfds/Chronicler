import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { convoyFunnel, hasGrainConvoysRecord, readGrainConvoys } from "../grainConvoys";
import { convoySnapshot } from "./grainConvoysFixture";

type Loose = { livelihoods: { grain_convoys: Record<string, unknown> & { active: Record<string, unknown>[]; transitions: Record<string, unknown>[] | null; counters: Record<string, unknown> } } };
const record = (snapshot: TurnSnapshot) => (snapshot as unknown as Loose).livelihoods.grain_convoys;

describe("grain convoy reader", () => {
  it("reads the dated record, its convoys, transitions and funnel", () => {
    const read = readGrainConvoys(convoySnapshot())!;
    expect(read.source_turn).toBe(31);
    expect(read.active.map((row) => [row.id, row.leg, row.progress, row.leg_turns])).toEqual([
      ["public-grain-convoy:30:0", 0, 1, 2], ["public-grain-convoy:31:1", 0, 0, 0]]);
    expect(read.transitions!.map((row) => row.operation)).toEqual(["advanced", "dispatched"]);
    expect(convoyFunnel(read)).toMatchObject({ eligible: 2, dispatched: 2, arrived: 0, onRoad: 2, escortPaid: 4 });
  });

  it("keeps unknown transitions unknown and an empty frame known-zero", () => {
    const unknown = convoySnapshot();
    record(unknown).transitions = null;
    expect(readGrainConvoys(unknown)!.transitions).toBeNull();
    const none = convoySnapshot();
    record(none).transitions = [];
    expect(readGrainConvoys(none)!.transitions).toEqual([]);
  });

  it("returns null when absent, stale or malformed", () => {
    expect(readGrainConvoys(null)).toBeNull();
    const absent = { turn: 32 } as unknown as TurnSnapshot;
    expect(readGrainConvoys(absent)).toBeNull();
    expect(hasGrainConvoysRecord(absent)).toBe(false);
    const mutations: ((r: ReturnType<typeof record>) => void)[] = [
      (r) => { r.source_turn = 30; },
      (r) => { r.schema_version = 2; },
      (r) => { r.route_policy = "fastest"; },
      (r) => { r.active_count = 3; },
      (r) => { r.active[0].cargo = -1; },
      (r) => { r.active[0].route = [4, 2]; },
      (r) => { r.active[0].progress = 0; },
      (r) => { r.active[1].convoy = 0; },
      (r) => { r.transitions![0].turn = 30; },
      (r) => { r.transitions![0].operation = "teleported"; },
      (r) => { r.transitions![1].paid = null; },
      (r) => { r.transitions![0].operation = "arrived"; },
      (r) => { delete r.counters.lost; },
      (r) => { r.counters.delivered = Number.NaN; },
    ];
    for (const mutate of mutations) {
      const snapshot = convoySnapshot();
      mutate(record(snapshot));
      expect(readGrainConvoys(snapshot)).toBeNull();
      expect(hasGrainConvoysRecord(snapshot)).toBe(true);
    }
  });

  it("accepts final operations only with their named destination", () => {
    const snapshot = convoySnapshot();
    Object.assign(record(snapshot).transitions![0], { operation: "captured", status: "captured", captor: 1,
      sink: "captor_market", sink_region: 0 });
    expect(readGrainConvoys(snapshot)!.transitions![0].operation).toBe("captured");
    record(snapshot).transitions![0].sink = null;
    expect(readGrainConvoys(snapshot)).toBeNull();
  });
});
