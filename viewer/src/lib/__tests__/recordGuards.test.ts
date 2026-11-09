import { describe, expect, it } from "vitest";
import { amount, count, finite, integer, isRecord, safeCount, safeInteger } from "../recordGuards";

const SAMPLES: [string, unknown][] = [
  ["2**53", 2 ** 53], ["2**53-1", 2 ** 53 - 1], ["1e300", 1e300], ["NaN", NaN], ["-0", -0], ["0", 0], ["1", 1],
  ["-1", -1], ["1.5", 1.5], ["Infinity", Infinity], ["-Infinity", -Infinity], ['"1"', "1"], ["[]", []],
  ["{}", {}], ["null", null], ["undefined", undefined], ["true", true],
];

// Expected acceptance per sample, in SAMPLES order.
const EXPECTED: Record<string, boolean[]> = {
  isRecord:    [false, false, false, false, false, false, false, false, false, false, false, false, false, true, false, false, false],
  finite:      [true, true, true, false, true, true, true, true, true, false, false, false, false, false, false, false, false],
  amount:      [true, true, true, false, true, true, true, false, true, false, false, false, false, false, false, false, false],
  integer:     [true, true, true, false, true, true, true, false, false, false, false, false, false, false, false, false, false],
  count:       [true, true, true, false, true, true, true, false, false, false, false, false, false, false, false, false, false],
  safeCount:   [false, true, false, false, true, true, true, false, false, false, false, false, false, false, false, false, false],
  safeInteger: [false, true, false, false, true, true, true, false, false, false, false, false, false, false, false, false, false],
};

const GUARDS: Record<string, (x: unknown) => boolean> = {
  isRecord, finite, amount, integer: (x) => integer(x), count, safeCount, safeInteger: (x) => safeInteger(x),
};

describe("record guards", () => {
  for (const [name, guard] of Object.entries(GUARDS)) {
    it(`${name} accepts exactly the expected samples`, () => {
      expect(SAMPLES.map(([, x]) => guard(x))).toEqual(EXPECTED[name]);
    });
  }

  it("integer and safeInteger honour an explicit lower bound", () => {
    expect(integer(-1)).toBe(false);
    expect(integer(-1, -1)).toBe(true);
    expect(integer(-2, -1)).toBe(false);
    expect(integer(2, 3)).toBe(false);
    expect(integer(-1.5, -5)).toBe(false);
    expect(safeInteger(-3, -5)).toBe(true);
    expect(safeInteger(-(2 ** 53), -Infinity)).toBe(false);
    expect(safeInteger(4, 5)).toBe(false);
  });

  // The local spellings these guards replace; each must accept the same samples.
  const legacy: [string, (x: unknown) => boolean, (x: unknown) => boolean][] = [
    ["isRecord / x !== null && typeof object", (x) => x !== null && typeof x === "object" && !Array.isArray(x), isRecord],
    ["isRecord / !!x && typeof object", (x) => !!x && typeof x === "object" && !Array.isArray(x), isRecord],
    ["amount / typeof number && isFinite && >= 0", (x) => typeof x === "number" && Number.isFinite(x) && x >= 0, amount],
    ["count / finite && isInteger && >= 0", (x) => finite(x) && Number.isInteger(x) && x >= 0, count],
    ["count / typeof number && isInteger && >= 0", (x) => typeof x === "number" && Number.isInteger(x) && x >= 0, count],
    ["count / integer default bound", (x) => integer(x), count],
    ["safeCount / typeof number && isSafeInteger && >= 0", (x) => typeof x === "number" && Number.isSafeInteger(x) && x >= 0, safeCount],
    ["safeCount / finite && isSafeInteger && >= 0", (x) => finite(x) && Number.isSafeInteger(x) && x >= 0, safeCount],
    ["safeCount / safeInteger default bound", (x) => safeInteger(x), safeCount],
  ];
  for (const [label, old, shared] of legacy) {
    it(`matches the legacy spelling ${label}`, () => {
      for (const [, x] of SAMPLES) expect(shared(x)).toBe(old(x));
    });
  }
});
