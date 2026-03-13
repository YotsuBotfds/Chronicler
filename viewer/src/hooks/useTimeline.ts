import { useState, useCallback, useEffect, useRef } from "react";

interface TimelineOptions {
  liveMode?: boolean;
}

export function useTimeline(maxTurn: number, options?: TimelineOptions) {
  const liveMode = options?.liveMode ?? false;
  const [currentTurn, setCurrentTurn] = useState(liveMode ? maxTurn : 1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [followMode, setFollowMode] = useState(liveMode);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const seek = useCallback(
    (turn: number) => {
      const clamped = Math.max(1, Math.min(turn, maxTurn));
      setCurrentTurn(clamped);
      if (liveMode) {
        setFollowMode(clamped >= maxTurn);
      }
    },
    [maxTurn, liveMode],
  );

  const play = useCallback(() => setPlaying(true), []);
  const pause = useCallback(() => setPlaying(false), []);

  // Follow mode: auto-advance when maxTurn increases
  useEffect(() => {
    if (followMode && liveMode) {
      setCurrentTurn(maxTurn);
    }
  }, [followMode, liveMode, maxTurn]);

  useEffect(() => {
    if (!playing) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    intervalRef.current = setInterval(() => {
      setCurrentTurn((prev) => {
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

  return { currentTurn, playing, speed, seek, play, pause, setSpeed, followMode, setFollowMode };
}
