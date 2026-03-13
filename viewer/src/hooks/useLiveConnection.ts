import { useState, useEffect, useCallback, useRef } from "react";
import type { Bundle, PauseContext, Command, AckMessage, ForkedMessage } from "../types";

interface LiveConnectionState {
  bundle: Bundle | null;
  connected: boolean;
  paused: boolean;
  pauseContext: PauseContext | null;
  error: string | null;
  sendCommand: (cmd: Command) => void;
  speed: number;
  setSpeed: (s: number) => void;
  lastAck: AckMessage | null;
  lastForked: ForkedMessage | null;
}

export function useLiveConnection(wsUrl: string): LiveConnectionState {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const [pauseContext, setPauseContext] = useState<PauseContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [speed, setSpeedState] = useState(1);
  const [lastAck, setLastAck] = useState<AckMessage | null>(null);
  const [lastForked, setLastForked] = useState<ForkedMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(1000);

  const sendCommand = useCallback((cmd: Command) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  }, []);

  const setSpeed = useCallback((s: number) => {
    setSpeedState(s);
    sendCommand({ type: "speed", value: s });
  }, [sendCommand]);

  useEffect(() => {
    let unmounted = false;

    // No-op when wsUrl is empty (static mode — hook is always called per Rules of Hooks)
    if (!wsUrl) return;

    function connect() {
      if (unmounted) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (unmounted) return;
        setConnected(true);
        setError(null);
        reconnectDelayRef.current = 1000;
      };

      ws.onclose = () => {
        if (unmounted) return;
        setConnected(false);
        wsRef.current = null;
        const delay = reconnectDelayRef.current;
        reconnectRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(delay * 2, 10000);
          connect();
        }, delay);
      };

      ws.onerror = () => {
        // onclose will fire after this
      };

      ws.onmessage = (e) => {
        if (unmounted) return;
        const msg = JSON.parse(e.data);

        switch (msg.type) {
          case "init":
            setBundle({
              world_state: msg.world_state,
              history: msg.history || [],
              events_timeline: msg.events_timeline || [],
              named_events: msg.named_events || [],
              chronicle_entries: msg.chronicle_entries || {},
              era_reflections: msg.era_reflections || {},
              metadata: msg.metadata,
            });
            if (msg.speed !== undefined) {
              setSpeedState(msg.speed);
            }
            break;

          case "turn":
            setBundle((prev) => {
              if (!prev) return prev;
              const snap = {
                turn: msg.turn,
                civ_stats: msg.civ_stats,
                region_control: msg.region_control,
                relationships: msg.relationships,
              };
              return {
                ...prev,
                history: [...prev.history, snap],
                chronicle_entries: {
                  ...prev.chronicle_entries,
                  [String(msg.turn)]: msg.chronicle_text || "",
                },
                events_timeline: [...prev.events_timeline, ...(msg.events || [])],
                named_events: [...prev.named_events, ...(msg.named_events || [])],
              };
            });
            break;

          case "paused":
            setPaused(true);
            setPauseContext({
              turn: msg.turn,
              reason: msg.reason,
              valid_commands: msg.valid_commands,
              injectable_events: msg.injectable_events,
              settable_stats: msg.settable_stats,
              civs: msg.civs,
            });
            break;

          case "ack": {
            const ack = msg as AckMessage;
            setLastAck(ack);
            if (!ack.still_paused) {
              setPaused(false);
              setPauseContext(null);
            }
            if (ack.command === "set" && ack.civ && ack.stat && ack.value !== undefined) {
              setBundle((prev) => {
                if (!prev || prev.history.length === 0) return prev;
                const newHistory = [...prev.history];
                const lastIdx = newHistory.length - 1;
                const lastSnap = { ...newHistory[lastIdx] };
                const civStats = { ...lastSnap.civ_stats };
                const civData = civStats[ack.civ!];
                if (civData) {
                  civStats[ack.civ!] = { ...civData, [ack.stat!]: ack.value };
                  lastSnap.civ_stats = civStats;
                  newHistory[lastIdx] = lastSnap;
                }
                return { ...prev, history: newHistory };
              });
            }
            break;
          }

          case "forked":
            setLastForked(msg as ForkedMessage);
            break;

          case "completed":
            setPaused(false);
            setPauseContext(null);
            break;

          case "error":
            setError(msg.message);
            break;
        }
      };
    }

    connect();

    return () => {
      unmounted = true;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [wsUrl]);

  return {
    bundle,
    connected,
    paused,
    pauseContext,
    error,
    sendCommand,
    speed,
    setSpeed,
    lastAck,
    lastForked,
  };
}
