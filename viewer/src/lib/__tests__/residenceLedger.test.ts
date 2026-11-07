import { describe, expect, it } from "vitest";
import type { Bundle, TurnSnapshot } from "../../types";
import { readResidenceLedger } from "../recordReading";
import { residenceLedgerAt, residenceLedgerOn, residenceZero, TOTAL_KEYS, type ResidenceLedgerRecord } from "../residenceLedger";
import { RECORD_121, RECORD_122, REGION_NAMES } from "./residenceLedgerFixture";

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
    const r = residenceLedgerAt(snap(122, clone(RECORD_122)), regions) as ResidenceLedgerRecord;
    expect(r).not.toBeNull();
    expect(r.frame!.totals.displaced).toBe(254);
    expect(r.frame!.regions.reduce((a, x) => a + x.residents, 0)).toBe(r.frame!.totals.observed);
    expect(r.events!.filter((e) => e.kind === "returned")).toHaveLength(2);
    expect(residenceLedgerAt(snap(121, clone(RECORD_121)), regions)).not.toBeNull();
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
    const r = clone(RECORD_122) as Rec;
    edit(r);
    expect(residenceLedgerAt(snap(122, r), regions)).toBeNull();
  });

  it("accepts an unobserved record (frame and events null) and events dropped beyond the bound", () => {
    const r = clone(RECORD_122) as Rec;
    r.frame = null;
    r.events = null;
    expect(residenceLedgerAt(snap(122, r), regions)?.frame).toBeNull();
    const d = clone(RECORD_122) as Rec;
    d.events = d.events.slice(0, 3);
    d.events_dropped = RECORD_122.events.length - 3;
    expect(residenceLedgerAt(snap(122, d), regions)).not.toBeNull();
  });
  it("keeps optional physical arrivals distinct from motive spells and closes their counts", () => {
    const make = () => {
      const r = clone(RECORD_122) as Rec;
      r.frame.arrival_diagnostics = { window_turns: 20, coverage_complete: true, window_complete: true, complete: true };
      for (const row of r.frame.regions) Object.assign(row, { recent_residence_arrivals: 0, recent_residence_arrivals_unknown_reason: 0 });
      const row = r.frame.regions.find((x: Rec) => x.residents >= 2);
      row.recent_residence_arrivals = 2; row.recent_residence_arrivals_unknown_reason = 1;
      Object.assign(r.frame.totals, { recent_residence_arrivals: 2, recent_residence_arrivals_unknown_reason: 1 });
      return r;
    };
    expect(residenceLedgerAt(snap(122, make()), regions)).not.toBeNull();
    for (const defect of ["missing", "sum", "unknown", "population", "complete", "window", "type"]) {
      const r = make();
      if (defect === "missing") delete r.frame.arrival_diagnostics;
      if (defect === "sum") r.frame.totals.recent_residence_arrivals = 3;
      if (defect === "unknown") r.frame.totals.recent_residence_arrivals_unknown_reason = 3;
      if (defect === "population") r.frame.regions[0].recent_residence_arrivals = r.frame.regions[0].residents + 1;
      if (defect === "complete") r.frame.arrival_diagnostics.coverage_complete = false;
      if (defect === "window") r.frame.arrival_diagnostics.window_turns = 5;
      if (defect === "type") r.frame.totals.recent_residence_arrivals = null;
      expect(residenceLedgerAt(snap(122, r), regions), defect).toBeNull();
    }
    const partial = make();
    Object.assign(partial.frame.arrival_diagnostics, { window_complete: false, complete: false });
    expect(residenceLedgerAt(snap(122, partial), regions)).not.toBeNull();
    // A newly observed resident with a recent arrival is meaningful even with no
    // motive-classified activity this turn; old records keep their old zero rule.
    const quiet = make();
    for (const key of TOTAL_KEYS) quiet.frame.totals[key] = 0;
    for (const row of quiet.frame.regions) for (const key of Object.keys(row)) if (key !== "region") row[key] = 0;
    const row = quiet.frame.regions[0];
    Object.assign(row, { residents: 2, recent_residence_arrivals: 2, recent_residence_arrivals_unknown_reason: 1 });
    Object.assign(quiet.frame.totals, { alive: 2, observed: 2 }); quiet.events = [];
    const observed = residenceLedgerAt(snap(122, quiet), regions)!;
    expect(observed).not.toBeNull();
    expect(residenceZero(observed.frame!)).toBe(false);
    delete quiet.frame.arrival_diagnostics;
    for (const key of ["recent_residence_arrivals", "recent_residence_arrivals_unknown_reason"]) {
      delete quiet.frame.totals[key]; for (const row of quiet.frame.regions) delete row[key];
    }
    expect(residenceZero(residenceLedgerAt(snap(122, quiet), regions)!.frame!)).toBe(true);
  });
});

describe("readResidenceLedger: six readings stay distinct", () => {
  const zero = () => {
    const r = clone(RECORD_122) as Rec;
    for (const k of TOTAL_KEYS) r.frame.totals[k] = 0;
    r.frame.regions = [];
    r.events = [];
    return r;
  };
  const cases: [string, TurnSnapshot[], number, string][] = [
    ["disabled", [snap(121, undefined), snap(122, undefined)], 1, "off in this run"],
    ["absent", [snap(121, clone(RECORD_121)), snap(122, undefined)], 1, "unknown, not zero"],
    ["malformed", [snap(121, clone(RECORD_121)), snap(122, { ...clone(RECORD_122), stage: "X" })], 1, "malformed"],
    ["unobserved", [snap(122, { ...clone(RECORD_122), frame: null, events: null })], 0, "not observed"],
    ["recorded_zero", [snap(122, zero())], 0, "nothing happened"],
    ["recorded", [snap(122, clone(RECORD_122))], 0, ""],
  ];
  it.each(cases)("%s", (state, history, index, note) => {
    const reading = readResidenceLedger(bundle(history), history[index]);
    expect(reading.state).toBe(state);
    expect(reading.note).toContain(note);
    expect(reading.record === null).toBe(["disabled", "absent", "malformed"].includes(state));
  });

  it("residenceLedgerOn tells a run that records it", () => {
    expect(residenceLedgerOn([snap(1, undefined), snap(2, clone(RECORD_122))])).toBe(true);
    expect(residenceLedgerOn([snap(1, undefined)])).toBe(false);
    expect(residenceLedgerOn(undefined)).toBe(false);
  });
});
