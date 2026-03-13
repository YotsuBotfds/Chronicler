import { useState, useCallback, useEffect, useRef } from "react";

export function useTimeline(maxTurn: number) {
  const [currentTurn, setCurrentTurn] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const seek = useCallback(
    (turn: number) => {
      setCurrentTurn(Math.max(1, Math.min(turn, maxTurn)));
    },
    [maxTurn],
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

  return { currentTurn, playing, speed, seek, play, pause, setSpeed };
}
