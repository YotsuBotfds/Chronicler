import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { usePaged } from "../usePaged";

describe("usePaged", () => {
  it("shows one page and grows by the page size", () => {
    const rows = Array.from({ length: 7 }, (_, i) => i);
    const { result } = renderHook(() => usePaged(rows, 3));
    expect(result.current.shown).toEqual([0, 1, 2]);
    expect(result.current.more).toBe(4);
    act(() => result.current.showMore());
    expect(result.current.shown).toEqual([0, 1, 2, 3, 4, 5]);
    expect(result.current.more).toBe(1);
    act(() => result.current.showMore());
    expect(result.current.shown).toEqual(rows);
    expect(result.current.more).toBe(0);
  });

  it("reports nothing hidden when the rows fit and follows changed rows", () => {
    const { result, rerender } = renderHook(({ rows }) => usePaged(rows, 5), { initialProps: { rows: [1, 2] } });
    expect(result.current.shown).toEqual([1, 2]);
    expect(result.current.more).toBe(0);
    rerender({ rows: [1, 2, 3, 4, 5, 6] });
    expect(result.current.shown).toEqual([1, 2, 3, 4, 5]);
    expect(result.current.more).toBe(1);
  });
});
