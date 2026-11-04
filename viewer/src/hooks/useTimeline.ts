import { useState, useCallback, useEffect } from "react";

interface TimelineOptions {
  liveMode?: boolean;
}

interface TimelineSessionOptions {
  initialTurn?: number;
  followLive?: boolean;
}

interface TimelineState {
  turn: number;
  playing: boolean;
  liveSession: boolean;
  inspectionBaseline: number | null;
}

export function useTimeline(maxTurn: number, options?: TimelineOptions) {
  const liveMode = options?.liveMode ?? false;
  const latestTurn = Math.max(1, maxTurn);
  const [state, setState] = useState<TimelineState>({
    turn: liveMode ? latestTurn : 1,
    playing: false,
    liveSession: liveMode,
    inspectionBaseline: null,
  });
  const [speed, setSpeed] = useState(1);

  // Remember live intent across a disconnected socket. Clamp a removed turn
  // permanently, so a later expanding window cannot move an inspected cursor.
  if ((liveMode && !state.liveSession) || state.turn > latestTurn) {
    setState({
      ...state,
      liveSession: state.liveSession || liveMode,
      turn: Math.min(state.turn, latestTurn),
    });
  }

  const inspectionLocked = state.inspectionBaseline !== null;
  const following = (liveMode || state.liveSession) && !inspectionLocked;
  const currentTurn = following ? latestTurn : Math.min(state.turn, latestTurn);

  const seek = useCallback(
    (turn: number) => {
      setState((previous) => ({
        ...previous,
        turn: Math.max(1, Math.min(turn, latestTurn)),
        // Seeking even to the live edge is inspection, not consent to follow.
        inspectionBaseline: previous.inspectionBaseline
          ?? (liveMode || previous.liveSession ? latestTurn : null),
      }));
    },
    [latestTurn, liveMode],
  );

  const lockInspection = useCallback(() => {
    setState((previous) => ({
      ...previous,
      turn: previous.inspectionBaseline === null
        && (liveMode || previous.liveSession) ? latestTurn : previous.turn,
      inspectionBaseline: previous.inspectionBaseline ?? latestTurn,
    }));
  }, [latestTurn, liveMode]);

  const returnToLive = useCallback(() => {
    setState({
      turn: latestTurn,
      playing: false,
      liveSession: true,
      inspectionBaseline: null,
    });
  }, [latestTurn]);

  // Stable across arrivals and reconnects. The caller invokes this only when
  // loading a different world, never for a replacement bundle of the same run.
  const resetSession = useCallback((session: TimelineSessionOptions = {}) => {
    setState({
      turn: Math.max(1, session.initialTurn ?? 1),
      playing: false,
      liveSession: session.followLive ?? false,
      inspectionBaseline: null,
    });
  }, []);

  const play = useCallback(() => {
    setState((previous) => ({
      ...previous,
      playing: true,
      turn: previous.inspectionBaseline === null
        && (liveMode || previous.liveSession) ? latestTurn : previous.turn,
      inspectionBaseline: previous.inspectionBaseline
        ?? (liveMode || previous.liveSession ? latestTurn : null),
    }));
  }, [latestTurn, liveMode]);
  const pause = useCallback(() => {
    setState((previous) => ({ ...previous, playing: false }));
  }, []);

  // Keep the old explicit setter usable, including its functional form.
  const setFollowMode = useCallback((value: boolean | ((previous: boolean) => boolean)) => {
    setState((previous) => {
      const wasFollowing = liveMode && previous.inspectionBaseline === null;
      const follow = typeof value === "function" ? value(wasFollowing) : value;
      return {
        ...previous,
        turn: follow || (previous.inspectionBaseline === null
          && (liveMode || previous.liveSession)) ? latestTurn : previous.turn,
        playing: follow ? false : previous.playing,
        liveSession: previous.liveSession || liveMode,
        inspectionBaseline: follow ? null : previous.inspectionBaseline ?? latestTurn,
      };
    });
  }, [latestTurn, liveMode]);

  useEffect(() => {
    if (!state.playing) return;

    const interval = setInterval(() => {
      setState((previous) => {
        const next = Math.min(previous.turn + 1, latestTurn);
        return { ...previous, turn: next, playing: next < latestTurn };
      });
    }, 1000 / speed);

    return () => clearInterval(interval);
  }, [state.playing, speed, latestTurn]);

  return {
    currentTurn,
    playing: state.playing,
    speed,
    seek,
    play,
    pause,
    setSpeed,
    followMode: liveMode && !inspectionLocked,
    setFollowMode,
    inspectionLocked,
    newTurns: state.inspectionBaseline === null
      ? 0 : Math.max(0, latestTurn - state.inspectionBaseline),
    returnToLive,
    lockInspection,
    resetSession,
  };
}
