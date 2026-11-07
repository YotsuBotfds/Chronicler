import { describe, expect, it } from "vitest";
import type { Bundle, TurnSnapshot } from "../../types";
import { readResidenceLedger } from "../recordReading";
import { residenceLedgerAt, residenceLedgerOn, residenceZero, TOTAL_KEYS, type ResidenceLedgerRecord } from "../residenceLedger";
import { RECORD_188, RECORD_189, REGION_NAMES } from "./residenceLedgerFixture";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Rec = Record<string, any>;
const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));
const snap = (turn: number, record: Rec | null | undefined, extra: Rec = {}) => ({
  turn, livelihoods: record === undefined ? { schema_version: 1, ...extra }
    : { schema_version: 1, residence_ledger: record, ...extra },
}) as unknown as TurnSnapshot;
const bundle = (history: TurnSnapshot[]) => ({
  history, world_state: { regions: REGION_NAMES.map((name) => ({ name })), civilizations: [] },
}) as unknown as Bundle;
const regions = REGION_NAMES.length;

describe("residenceLedgerAt", () => {
  it("accepts the natural records and their sums", () => {
    const r = residenceLedgerAt(snap(189, clone(RECORD_189)), regions) as ResidenceLedgerRecord;
    expect(r).not.toBeNull();
    expect(r.frame!.totals.displaced).toBe(120);
    expect(r.frame!.regions.reduce((a, x) => a + x.residents, 0)).toBe(r.frame!.totals.observed);
    expect(r.events!.filter((e) => e.kind === "returned")).toHaveLength(4);
    expect(residenceLedgerAt(snap(188, clone(RECORD_188)), regions)).not.toBeNull();
    expect(residenceZero(r.frame!)).toBe(false);
  });

  it.each([
    ["a misdated record", (r: Rec) => { r.source_turn = 7; }],
    ["another stage", (r: Rec) => { r.stage = "D2"; }],
    ["a missing total", (r: Rec) => { delete r.frame.totals.displaced; }],
    ["a region outside the world", (r: Rec) => { r.frame.regions[0].region = 99; }],
    ["region rows that do not add up", (r: Rec) => { r.frame.regions[0].residents += 1; }],
    ["anchors that do not add up", (r: Rec) => { r.frame.totals.displaced_none += 1; }],
    ["an event of another turn", (r: Rec) => { r.events[0].turn = 3; }],
    ["events that disagree with the totals", (r: Rec) => { r.events.pop(); }],
    ["half a frame", (r: Rec) => { r.events = null; }],
    ["a frame without events but a frame", (r: Rec) => { r.frame = null; }],
    ["a frame of another epoch", (r: Rec) => { r.observed_from = 5; }],
  ])("refuses %s", (_name, edit) => {
    const r = clone(RECORD_189) as Rec;
    edit(r);
    expect(residenceLedgerAt(snap(189, r), regions)).toBeNull();
  });

  it("accepts an unobserved record (frame and events null) and events dropped beyond the bound", () => {
    const r = clone(RECORD_189) as Rec;
    r.frame = null;
    r.events = null;
    expect(residenceLedgerAt(snap(189, r), regions)?.frame).toBeNull();
    const d = clone(RECORD_189) as Rec;
    d.events = d.events.slice(0, 3);
    d.events_dropped = RECORD_189.events.length - 3;
    expect(residenceLedgerAt(snap(189, d), regions)).not.toBeNull();
  });
});

describe("readResidenceLedger: six readings stay distinct", () => {
  const zero = () => {
    const r = clone(RECORD_189) as Rec;
    for (const k of TOTAL_KEYS) r.frame.totals[k] = 0;
    r.frame.regions = [];
    r.events = [];
    return r;
  };
  const cases: [string, TurnSnapshot[], number, string][] = [
    ["disabled", [snap(188, undefined), snap(189, undefined)], 1, "off in this run"],
    ["absent", [snap(188, clone(RECORD_188)), snap(189, undefined)], 1, "unknown, not zero"],
    ["malformed", [snap(188, clone(RECORD_188)), snap(189, { ...clone(RECORD_189), stage: "X" })], 1, "malformed"],
    ["unobserved", [snap(189, { ...clone(RECORD_189), frame: null, events: null })], 0, "not observed"],
    ["recorded_zero", [snap(189, zero())], 0, "nothing happened"],
    ["recorded", [snap(189, clone(RECORD_189))], 0, ""],
  ];
  it.each(cases)("%s", (state, history, index, note) => {
    const reading = readResidenceLedger(bundle(history), history[index]);
    expect(reading.state).toBe(state);
    expect(reading.note).toContain(note);
    expect(reading.record === null).toBe(["disabled", "absent", "malformed"].includes(state));
  });

  it("residenceLedgerOn tells a run that records it", () => {
    expect(residenceLedgerOn([snap(1, undefined), snap(2, clone(RECORD_189))])).toBe(true);
    expect(residenceLedgerOn([snap(1, undefined)])).toBe(false);
    expect(residenceLedgerOn(undefined)).toBe(false);
  });
});
