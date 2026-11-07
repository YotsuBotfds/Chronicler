import { expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { attributionOn, readAttribution } from "../attributionRecords";
import { empty, frame, record } from "./attributionRecordsFixture";

const at = (livelihoods: unknown, turn = 10) => ({ turn, livelihoods }) as unknown as TurnSnapshot;
const read = (livelihoods: unknown, on = true, turn = 10) => readAttribution(at(livelihoods, turn), on, 3, 2);
const withFrame = (changes: Record<string, unknown>) => ({ schema_version: 1, attribution_records: record({
  frame: { ...frame, ...changes } }) });

it("keeps disabled, absent, unobserved, recorded-zero and recorded readings distinct", () => {
  expect(read(undefined, false)).toEqual({ state: "disabled" });
  expect(read({ schema_version: 1 }, false)).toEqual({ state: "disabled" });
  expect(read({ schema_version: 1 }, true)).toEqual({ state: "absent" });
  expect(read({ schema_version: 1, attribution_records: null }, true)).toEqual({ state: "absent" });
  expect(readAttribution(null, true, 3, 2)).toEqual({ state: "absent" });
  expect(read({ schema_version: 1, attribution_records: record({ frame: null }) }).state).toBe("unobserved");
  expect(read({ schema_version: 1, attribution_records: record({ frame: empty }) }).state).toBe("recorded_zero");
  const reading = read({ schema_version: 1, attribution_records: record() });
  expect(reading.state).toBe("recorded");
  if (reading.state === "recorded") expect(reading.frame.casualties.by_class.natural).toBe(2);
});

it("knows a run that records the package from one that does not", () => {
  expect(attributionOn([at({ schema_version: 1 }), at({ schema_version: 1, attribution_records: record() })])).toBe(true);
  expect(attributionOn([at({ schema_version: 1 }), at(undefined)])).toBe(false);
  expect(attributionOn(null)).toBe(false);
});

it("rejects malformed records with a reason", () => {
  const row = frame.casualties.rows[0];
  const cases: [unknown, string][] = [
    [{ schema_version: 2, attribution_records: record() }, "unknown livelihoods schema"],
    [{ schema_version: 1, attribution_records: [] }, "unknown attribution-records schema"],
    [{ schema_version: 1, attribution_records: record({ stage: "A1" }) }, "unknown attribution-records schema"],
    [{ schema_version: 1, attribution_records: record({ source_turn: 3 }) }, "misdated record"],
    [{ schema_version: 1, attribution_records: (() => { const r: Record<string, unknown> = record(); delete r.frame; return r; })() },
      "the record has no frame"],
    [withFrame({ turn: 4 }), "misdated frame"],
    [withFrame({ casualties: { ...frame.casualties, rows: [{ ...row, cause: "plague" }] } }), "malformed casualty row"],
    [withFrame({ casualties: { ...frame.casualties, rows: [{ ...row, class: "natural" }] } }), "a casualty row in the wrong class"],
    [withFrame({ casualties: { ...frame.casualties, rows: [{ ...frame.casualties.rows[1], actor: 1 }] } }),
      "an actor on a non-combat death"],
    [withFrame({ casualties: { ...frame.casualties, rows: [{ ...row, victim: 5 }] } }), "malformed casualty row"],
    [withFrame({ granary: { active: false, seizures: frame.granary.seizures, unattributed: null } }),
      "inactive granaries with seizures"],
    [withFrame({ granary: { ...frame.granary, seizures: [{ ...frame.granary.seizures[0], region: 9 }] } }),
      "malformed granary seizure"],
    [withFrame({ burdens: { ...frame.burdens, pairs: [{ ...frame.burdens.pairs[0], nature: "taken" }] } }),
      "malformed burden pair"],
    [withFrame({ identity: [{ ...frame.identity[0], kind: "reborn" }] }), "malformed identity event"],
  ];
  for (const [livelihoods, reason] of cases) expect(read(livelihoods)).toEqual({ state: "malformed", reason });
});
