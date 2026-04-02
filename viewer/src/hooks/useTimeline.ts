import { useState, useCallback, useEffect, useRef } from "react";

interface TimelineOptions {
  liveMode?: boolean;
}

export function useTimeline(maxTurn: number, options?: TimelineOptions) {
  const liveMode = options?.liveMode ?? false;
  const [storedTurn, setStoredTurn] = useState(liveMode ? maxTurn : 1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [followMode, setFollowMode] = useState(liveMode);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const effectiveFollowMode = liveMode && (followMode || storedTurn >= maxTurn);
  const currentTurn = effectiveFollowMode
    ? maxTurn
    : Math.max(1, Math.min(storedTurn, maxTurn));

  const seek = useCallback(
    (turn: number) => {
      const clamped = Math.max(1, Math.min(turn, maxTurn));
      setStoredTurn(clamped);
      if (liveMode) {
        setFollowMode(clamped >= maxTurn);
      }
    },
    [maxTurn, liveMode],
  );

  const play = useCallback(() => setPlaying(true), []);
  const pause = useCallback(() => setPlaying(false), []);

  useEffect(() => {
    if (!playing) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    intervalRef.current = setInterval(() => {
      setStoredTurn((prev) => {
        const next = prev + 1;
        if (next > maxTurn) {
          setPlaying(false);
          return maxTurn;
        }
        return next;
      });
    }, 1000 / speed);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [playing, speed, maxTurn]);

  return {
    currentTurn,
    playing,
    speed,
    seek,
    play,
    pause,
    setSpeed,
    followMode: effectiveFollowMode,
    setFollowMode,
  };
}
