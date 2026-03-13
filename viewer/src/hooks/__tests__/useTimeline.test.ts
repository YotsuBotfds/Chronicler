import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTimeline } from "../useTimeline";

describe("useTimeline", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("initializes with turn 1", () => {
    const { result } = renderHook(() => useTimeline(100));
    expect(result.current.currentTurn).toBe(1);
    expect(result.current.playing).toBe(false);
    expect(result.current.speed).toBe(1);
  });

  it("seek changes current turn", () => {
    const { result } = renderHook(() => useTimeline(100));
    act(() => result.current.seek(50));
    expect(result.current.currentTurn).toBe(50);
  });

  it("seek clamps to valid range", () => {
    const { result } = renderHook(() => useTimeline(100));
    act(() => result.current.seek(200));
    expect(result.current.currentTurn).toBe(100);
    act(() => result.current.seek(0));
    expect(result.current.currentTurn).toBe(1);
  });

  it("play/pause toggles playing state", () => {
    const { result } = renderHook(() => useTimeline(100));
    act(() => result.current.play());
    expect(result.current.playing).toBe(true);
    act(() => result.current.pause());
    expect(result.current.playing).toBe(false);
  });

  it("setSpeed updates speed", () => {
    const { result } = renderHook(() => useTimeline(100));
    act(() => result.current.setSpeed(5));
    expect(result.current.speed).toBe(5);
  });

  it("playing advances turn over time", () => {
    const { result } = renderHook(() => useTimeline(100));
    act(() => result.current.setSpeed(2));
    act(() => result.current.play());
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.currentTurn).toBeGreaterThan(1);
  });

  it("stops at max turns", () => {
    const { result } = renderHook(() => useTimeline(5));
    act(() => result.current.setSpeed(10));
    act(() => result.current.play());
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(result.current.currentTurn).toBe(5);
    expect(result.current.playing).toBe(false);
  });
});

describe("useTimeline follow mode", () => {
  it("auto-advances when followMode is true and maxTurn increases", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 5 } },
    );

    expect(result.current.followMode).toBe(true);
    expect(result.current.currentTurn).toBe(5);

    rerender({ maxTurn: 8 });
    expect(result.current.currentTurn).toBe(8);
  });

  it("disables followMode when user seeks backward", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 10 } },
    );

    act(() => result.current.seek(5));
    expect(result.current.followMode).toBe(false);
    expect(result.current.currentTurn).toBe(5);

    rerender({ maxTurn: 12 });
    expect(result.current.currentTurn).toBe(5);
  });

  it("re-enables followMode when user seeks to latest", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 10 } },
    );

    act(() => result.current.seek(5));
    expect(result.current.followMode).toBe(false);

    act(() => result.current.seek(10));
    expect(result.current.followMode).toBe(true);
  });

  it("does not use followMode in static mode", () => {
    const { result } = renderHook(() => useTimeline(10));
    expect(result.current.followMode).toBe(false);
  });
});
