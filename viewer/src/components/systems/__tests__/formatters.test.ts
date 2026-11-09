import { describe, expect, it } from "vitest";
import { notObserved, percent, show, words } from "../formatters";

/** The local bodies the shared formatters replace, copied verbatim. */
const localShow = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const localNumberShow = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 3 });
const localPercent = (n: number) => `${localNumberShow(100 * n)}%`;
const localWords = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ");

const NUMBERS = [0, -0, 1, -1, 0.5, 1 / 3, 2 / 3, 12.3456, 1234567.891, 1e-7, 2 ** 53, 1e300, NaN, Infinity, -Infinity];

describe("show", () => {
  it("matches the local panel bodies on every number", () => {
    for (const n of NUMBERS) {
      expect(show(n)).toBe(localShow(n));
      expect(show(n)).toBe(localNumberShow(n));
      expect(show(n, 2)).toBe(localShow(n, 2));
    }
  });
  it("reads an absent value as Unknown", () => {
    expect(show(null)).toBe("Unknown");
    expect(show(undefined)).toBe("Unknown");
  });
  it("rounds to the given precision", () => {
    expect(show(1 / 3)).toBe((0.333).toLocaleString());
    expect(show(1 / 3, 1)).toBe((0.3).toLocaleString());
  });
});

describe("notObserved", () => {
  it("formats like show and reads an absent value as Not observed", () => {
    for (const n of NUMBERS) expect(notObserved(n, 4)).toBe(show(n, 4));
    expect(notObserved(null)).toBe("Not observed");
    expect(notObserved(undefined)).toBe("Not observed");
  });
});

describe("percent", () => {
  it("matches the local share-to-percent body", () => {
    for (const n of NUMBERS) expect(percent(n)).toBe(localPercent(n));
    expect(percent(0.25)).toBe("25%");
  });
});

describe("words", () => {
  it("replaces every underscore and reads absent text as empty", () => {
    for (const text of ["placed_as_crew", "none", "", "__", null, undefined]) expect(words(text)).toBe(localWords(text));
    expect(words("in_kind_relief")).toBe("in kind relief");
  });
});
