import { expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { failedClosures, readWealthAccounting } from "../wealthAccounting";
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

it("reads a frame with a failed closure as observed, like the Python reference", () => {
  // A package located more than its own total: unlocated is negative and the ledger failed a closure.
  const typed = [frame.typed[0], frame.typed[1], { ...frame.typed[2], unlocated_in_milli: -115 }];
  const closures = [...frame.closures, { channel: "remittance", check: "located flows do not exceed the package's total",
    lhs: 1115, rhs: 1500, closes: false }];
  const world = { ...frame.world, unlocated_in_milli: 385 };
  const reading = read(withFrame({ typed, closures, world }));
  expect(reading.status).toBe("observed");
  if (reading.status === "observed") {
    expect(failedClosures(reading.frame).map((c) => c.check)).toEqual(["located flows do not exceed the package's total"]);
  }
  // A failed package closure of any kind is shown too.
  const failed = read(withFrame({ closures: [{ ...frame.closures[0], lhs: 2000, rhs: 1999, closes: false }] }));
  expect(failed.status).toBe("observed");
  // Located beyond zero is impossible (a negative located flow): still malformed.
  expect(read(withFrame({ typed: [{ ...frame.typed[1], unlocated_in_milli: 900 }, frame.typed[0], frame.typed[2]] })))
    .toEqual({ status: "malformed", reason: "unlocated flows exceed their total" });
});

const native = {
  source_turn: 9, rows: [{ region: 0, component: "income_applied", amount: 5 }, { region: 0, component: "decay", amount: -3.5 },
    { region: 1, component: "transfer_actual", amount: 2 }], totals: { income_applied: 5, decay: -3.5, transfer_actual: 2 },
  modeled_net: 1.5, transfer_actual: 2, balance_closure: 0, typed_receipt_difference: 0, typed_rounding_or_unobserved: 0,
  observed_complete: true, coverage: "native stages and exact transfer deltas observed; receipt rounding reported separately",
};
it("reads itemized native stages separately from receipt rounding; old null/absent frames stay loadable", () => {
  expect(read(withFrame({ native })).status).toBe("observed");
  expect(read(withFrame({ native: null })).status).toBe("observed");
  expect(read(withFrame({ native: undefined })).status).toBe("observed");
  for (const bad of [
    { ...native, source_turn: 99 }, { ...native, rows: [...native.rows, native.rows[0]] },
    { ...native, totals: { ...native.totals, income_applied: 6 } },
    { ...native, balance_closure: 1 }, { ...native, typed_receipt_difference: 1 },
    { ...native, observed_complete: false }, { ...native, totals: { invented: 3 } },
  ]) expect(read(withFrame({ native: bad })).status).toBe("malformed");
});
it("retains an honestly recorded native coverage discrepancy as observed", () => {
  const incomplete = { ...native, modeled_net: 1.4, totals: { ...native.totals, income_applied: 4.9 },
    rows: native.rows.map((r) => r.component === "income_applied" ? { ...r, amount: 4.9 } : r), balance_closure: .1, observed_complete: false };
  expect(read(withFrame({ native: incomplete })).status).toBe("observed");
});
