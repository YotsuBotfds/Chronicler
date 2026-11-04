import { StrictMode, useEffect } from "react";
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

  it("keeps inspection locked when user seeks to latest", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 10 } },
    );

    act(() => result.current.seek(5));
    expect(result.current.followMode).toBe(false);

    act(() => result.current.seek(10));
    expect(result.current.followMode).toBe(false);
    expect(result.current.inspectionLocked).toBe(true);
    rerender({ maxTurn: 12 });
    expect(result.current.currentTurn).toBe(10);
    expect(result.current.newTurns).toBe(2);
  });

  it("does not use followMode in static mode", () => {
    const { result } = renderHook(() => useTimeline(10));
    expect(result.current.followMode).toBe(false);
  });
});

describe("useTimeline live inspection", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("follows when a previously inactive live connection first connects", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn, liveMode }) => useTimeline(maxTurn, { liveMode }),
      { initialProps: { maxTurn: 1, liveMode: false } },
    );
    rerender({ maxTurn: 20, liveMode: true });
    expect(result.current.currentTurn).toBe(20);
    expect(result.current.followMode).toBe(true);
    expect(result.current.inspectionLocked).toBe(false);
    rerender({ maxTurn: 25, liveMode: true });
    expect(result.current.currentTurn).toBe(25);
  });

  it("preserves a pre-connection explicit inspection lock", () => {
    const { result, rerender } = renderHook(
      ({ liveMode }) => useTimeline(20, { liveMode }),
      { initialProps: { liveMode: false } },
    );
    act(() => result.current.lockInspection());
    rerender({ liveMode: true });
    expect(result.current.currentTurn).toBe(1);
    expect(result.current.inspectionLocked).toBe(true);
    expect(result.current.followMode).toBe(false);
  });

  it("does not jump to the stale initial cursor when a following socket disconnects", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn, liveMode }) => useTimeline(maxTurn, { liveMode }),
      { initialProps: { maxTurn: 10, liveMode: true } },
    );
    rerender({ maxTurn: 30, liveMode: true });
    rerender({ maxTurn: 30, liveMode: false });
    expect(result.current.currentTurn).toBe(30);
    expect(result.current.followMode).toBe(false);
    expect(result.current.inspectionLocked).toBe(false);
    rerender({ maxTurn: 35, liveMode: true });
    expect(result.current.currentTurn).toBe(35);
    expect(result.current.followMode).toBe(true);
  });

  it("keeps a locked historical turn and arrival baseline through disconnect/reconnect", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn, liveMode }) => useTimeline(maxTurn, { liveMode }),
      { initialProps: { maxTurn: 100, liveMode: true } },
    );
    act(() => result.current.seek(10));
    rerender({ maxTurn: 100, liveMode: false });
    expect(result.current.currentTurn).toBe(10);
    rerender({ maxTurn: 105, liveMode: true });
    expect(result.current.currentTurn).toBe(10);
    expect(result.current.inspectionLocked).toBe(true);
    expect(result.current.followMode).toBe(false);
    expect(result.current.newTurns).toBe(5);
  });

  it("locks an explicit seek directly to the current live edge", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 100 } },
    );
    act(() => result.current.seek(100));
    expect(result.current.inspectionLocked).toBe(true);
    expect(result.current.newTurns).toBe(0);
    rerender({ maxTurn: 105 });
    expect(result.current.currentTurn).toBe(100);
    expect(result.current.newTurns).toBe(5);
  });

  it("counts arrivals since locking and retains the baseline across history seeks and repeated locks", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 100 } },
    );
    act(() => result.current.seek(10));
    expect(result.current.newTurns).toBe(0);
    rerender({ maxTurn: 105 });
    expect(result.current.newTurns).toBe(5);
    act(() => result.current.seek(80));
    act(() => result.current.lockInspection());
    expect(result.current.newTurns).toBe(5);
    rerender({ maxTurn: 107 });
    act(() => result.current.seek(107));
    expect(result.current.newTurns).toBe(7);
    expect(result.current.inspectionLocked).toBe(true);
    expect(result.current.followMode).toBe(false);
  });

  it("returnToLive clears arrivals, stops playback and follows later arrivals", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 100 } },
    );
    act(() => result.current.seek(10));
    act(() => result.current.play());
    rerender({ maxTurn: 105 });
    act(() => result.current.returnToLive());
    expect(result.current.currentTurn).toBe(105);
    expect(result.current.inspectionLocked).toBe(false);
    expect(result.current.newTurns).toBe(0);
    expect(result.current.playing).toBe(false);
    rerender({ maxTurn: 107 });
    expect(result.current.currentTurn).toBe(107);
    act(() => result.current.lockInspection());
    expect(result.current.currentTurn).toBe(107);
    rerender({ maxTurn: 108 });
    expect(result.current.currentTurn).toBe(107);
    expect(result.current.newTurns).toBe(1);
  });

  it("playback reaching the latest turn stays locked on subsequent arrivals", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 5 } },
    );
    act(() => result.current.seek(3));
    act(() => result.current.play());
    act(() => vi.advanceTimersByTime(3000));
    expect(result.current.currentTurn).toBe(5);
    expect(result.current.playing).toBe(false);
    expect(result.current.inspectionLocked).toBe(true);
    expect(result.current.followMode).toBe(false);
    rerender({ maxTurn: 7 });
    expect(result.current.currentTurn).toBe(5);
    expect(result.current.newTurns).toBe(2);
  });

  it("playing at the live edge explicitly locks that turn", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 10 } },
    );
    rerender({ maxTurn: 20 });
    act(() => result.current.play());
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.currentTurn).toBe(20);
    expect(result.current.inspectionLocked).toBe(true);
    expect(result.current.playing).toBe(false);
    rerender({ maxTurn: 21 });
    expect(result.current.currentTurn).toBe(20);
  });

  it("clamps a shrinking window without unlocking or moving on later growth", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 100 } },
    );
    act(() => result.current.seek(90));
    rerender({ maxTurn: 50 });
    expect(result.current.currentTurn).toBe(50);
    expect(result.current.newTurns).toBe(0);
    expect(result.current.inspectionLocked).toBe(true);
    rerender({ maxTurn: 105 });
    expect(result.current.currentTurn).toBe(50);
    expect(result.current.newTurns).toBe(5);
  });

  it("supports the old explicit follow setter and its functional form", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 10 } },
    );
    rerender({ maxTurn: 20 });
    act(() => result.current.setFollowMode(false));
    expect(result.current.currentTurn).toBe(20);
    expect(result.current.inspectionLocked).toBe(true);
    rerender({ maxTurn: 25 });
    act(() => result.current.setFollowMode((following) => !following));
    expect(result.current.currentTurn).toBe(25);
    expect(result.current.inspectionLocked).toBe(false);
    expect(result.current.newTurns).toBe(0);
  });

  it("resets a new world without a callback dependency loop in StrictMode", () => {
    let resetCount = 0;
    const { result, rerender } = renderHook(
      ({ maxTurn, liveMode, world }) => {
        const timeline = useTimeline(maxTurn, { liveMode });
        const { resetSession } = timeline;
        useEffect(() => {
          resetCount += 1;
          resetSession(world === "static" ? {} : { initialTurn: 10, followLive: true });
        }, [world, resetSession]);
        return timeline;
      },
      {
        initialProps: { maxTurn: 10, liveMode: true, world: "first" },
        wrapper: StrictMode,
      },
    );
    const reset = result.current.resetSession;
    const initialResetCount = resetCount;
    act(() => result.current.seek(5));
    act(() => result.current.play());
    rerender({ maxTurn: 15, liveMode: false, world: "first" });
    rerender({ maxTurn: 20, liveMode: true, world: "first" });
    expect(result.current.currentTurn).toBe(5);
    expect(result.current.newTurns).toBe(10);
    expect(result.current.resetSession).toBe(reset);
    expect(resetCount).toBe(initialResetCount);
    rerender({ maxTurn: 10, liveMode: true, world: "second" });
    expect(result.current.currentTurn).toBe(10);
    expect(result.current.inspectionLocked).toBe(false);
    expect(result.current.newTurns).toBe(0);
    expect(result.current.playing).toBe(false);
    expect(resetCount).toBe(initialResetCount + 1);
    rerender({ maxTurn: 50, liveMode: false, world: "static" });
    expect(result.current.currentTurn).toBe(1);
    expect(result.current.followMode).toBe(false);
    expect(result.current.inspectionLocked).toBe(false);
  });
});
