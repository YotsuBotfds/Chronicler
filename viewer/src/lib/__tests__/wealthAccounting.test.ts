import { expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { readWealthAccounting } from "../wealthAccounting";
import { frame, record } from "./wealthAccountingFixture";

const at = (livelihoods: unknown, turn = 10) => ({ turn, livelihoods }) as unknown as TurnSnapshot;
const read = (livelihoods: unknown, turn = 10) => readWealthAccounting(at(livelihoods, turn), 2, 1);
const withFrame = (changes: Record<string, unknown>) => ({ schema_version: 1, wealth_accounting: record({
  frame: { ...frame, ...changes } }) });

it("keeps absent, unobserved and observed readings distinct; recorded zeros are observed", () => {
  expect(read(undefined)).toEqual({ status: "absent" });
  expect(read({ schema_version: 1 })).toEqual({ status: "absent" });
  expect(read({ schema_version: 1, wealth_accounting: null })).toEqual({ status: "absent" });
  expect(readWealthAccounting(null, 2, 1)).toEqual({ status: "absent" });
  const unobserved = read({ schema_version: 1, wealth_accounting: record({ frame: null }) });
  expect(unobserved.status).toBe("unobserved");
  const observed = read({ schema_version: 1, wealth_accounting: record() });
  expect(observed.status).toBe("observed");
  const zero = { ...frame, typed: [], closures: [], withheld: null, world: { ...frame.world, typed_in_milli: 0,
    typed_out_milli: 0, typed_net_milli: 0, unlocated_in_milli: 0, native_model: 3.5 } };
  const reading = read({ schema_version: 1, wealth_accounting: record({ frame: zero }) });
  expect(reading.status).toBe("observed");
  if (reading.status === "observed") expect(reading.frame.world.typed_in_milli).toBe(0);
});

it("rejects malformed records with a reason", () => {
  const cases: [unknown, string][] = [
    [{ schema_version: 2, wealth_accounting: record() }, "unknown livelihoods schema"],
    [{ schema_version: 1, wealth_accounting: [] }, "unknown wealth-accounting schema"],
    [{ schema_version: 1, wealth_accounting: record({ stage: "PL4" }) }, "unknown wealth-accounting schema"],
    [{ schema_version: 1, wealth_accounting: record({ source_turn: 3 }) }, "misdated observation"],
    [{ schema_version: 1, wealth_accounting: (() => { const r: Record<string, unknown> = record(); delete r.frame; return r; })() },
      "the record has no frame"],
    [withFrame({ turn: 4 }), "misdated frame"],
    [withFrame({ continuity: { status: "fine", reason: null, previous_close_turn: 8 } }), "malformed continuity"],
    [withFrame({ world: { ...frame.world, native_model: 2 } }), "the world identity does not close"],
    [withFrame({ world: { ...frame.world, typed_in_milli: 2999.5 } }), "malformed world row"],
    [withFrame({ regions: [{ ...frame.regions[0], native_model: 1 }] }), "a region's identity does not close"],
    [withFrame({ regions: [{ ...frame.regions[0], region: 7 }] }), "malformed region row"],
    [withFrame({ typed: frame.typed.slice(1) }), "typed flows do not sum to the world row"],
    [withFrame({ typed: [{ ...frame.typed[1], unlocated_in_milli: 900 }, frame.typed[0], frame.typed[2]] }),
      "unlocated flows exceed their total"],
    [withFrame({ withheld: { ...frame.withheld, paid_work_active: false } }),
      "paid-work fields recorded without a paid-work package"],
    [withFrame({ treasury: { ...frame.treasury, tithe: { ...frame.treasury.tithe, at_threshold_after_tick: 10 } } }),
      "malformed tithe"],
    [withFrame({ treasury: { ...frame.treasury, tithe: { ...frame.treasury.tithe, collected: 3 } } }), "malformed tithe"],
  ];
  for (const [livelihoods, reason] of cases) expect(read(livelihoods)).toEqual({ status: "malformed", reason });
});

it("reads paid-work fields as unknown without a paid-work package and retail separately", () => {
  const withheld = { paid_work_active: false, rows: null, deducted: null, packages: null, unattributed_rows: null,
    unattributed_pl3_dropped_rows: null, unattributed_deducted: null, conflicts: null, recovery_crews: null,
    retail_active: true, retail_income_replaced: 0.75 };
  const reading = read(withFrame({ withheld }));
  expect(reading.status).toBe("observed");
  if (reading.status === "observed") expect(reading.frame.withheld?.rows).toBeNull();
});
