import { useState, useEffect, useCallback, useRef } from "react";
import type { Bundle, PauseContext, Command, AckMessage, ForkedMessage, LobbyInit, StartCommand, NewChronicleEntry } from "../types";
import { isLegacyBundle } from "../types";
import { useBatchConnection, type BatchConnectionState } from "./useBatchConnection";
import { classifyParsedBundlePayload, formatBundleLoaderDiagnostics } from "../lib/bundleLoader";

type ServerState = "connecting" | "lobby" | "starting" | "running" | "completed";

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
  serverState: ServerState;
  lobbyInit: LobbyInit | null;
  sendStart: (params: Omit<StartCommand, "type">) => void;
  sendNarrateRange: (startTurn: number, endTurn: number) => void;
  loadBatchBundle: (path: string) => void;
  batch: BatchConnectionState;
  wsRef: React.RefObject<WebSocket | null>;
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
  const [serverState, setServerState] = useState<ServerState>("connecting");
  const [lobbyInit, setLobbyInit] = useState<LobbyInit | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(1000);
  const serverStateRef = useRef<ServerState>("connecting");
  const batch = useBatchConnection(wsRef);
  const handleBatchMessage = batch.handleMessage;

  const sendCommand = useCallback((cmd: Command) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  }, []);

  const setSpeed = useCallback((s: number) => {
    setSpeedState(s);
    sendCommand({ type: "speed", value: s });
  }, [sendCommand]);

  const sendStart = useCallback((params: Omit<StartCommand, "type">) => {
    if (serverStateRef.current !== "lobby") return;  // prevent double-submission
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setServerState("starting");
      serverStateRef.current = "starting";
      setError(null);
      wsRef.current.send(JSON.stringify({ type: "start", ...params }));
    }
  }, []);

  const sendNarrateRange = useCallback((startTurn: number, endTurn: number) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "narrate_range",
        start_turn: startTurn,
        end_turn: endTurn,
      }));
    }
  }, []);

  const loadBatchBundle = useCallback((path: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "batch_load_bundle",
        path,
      }));
    }
  }, []);

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
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let msg: any;
        try {
          msg = JSON.parse(e.data);
        } catch {
          console.warn("WebSocket: received non-JSON message, ignoring");
          return;
        }
        if (typeof msg !== "object" || msg === null || typeof msg.type !== "string") {
          console.warn("WebSocket: message missing 'type' field, ignoring", msg);
          return;
        }

        switch (msg.type) {
          case "init":
            if (msg.state === "lobby") {
              setServerState("lobby");
              serverStateRef.current = "lobby";
              setLobbyInit({
                scenarios: msg.scenarios,
                models: msg.models,
                defaults: msg.defaults,
              });
            } else if (msg.state === "starting") {
              setServerState("starting");
              serverStateRef.current = "starting";
            } else {
              // "running" or absent (backward compat: pre-lobby servers
              // don't send state field; treat absence as running)
              setServerState("running");
              serverStateRef.current = "running";
              setError(null);
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
              // Only merge turn text into legacy (Record) chronicle_entries
              const updatedChronicle = isLegacyBundle(prev.chronicle_entries)
                ? { ...prev.chronicle_entries, [String(msg.turn)]: msg.chronicle_text || "" }
                : prev.chronicle_entries;
              return {
                ...prev,
                history: [...prev.history, snap],
                chronicle_entries: updatedChronicle,
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

          case "narration_started":
            // Loading indicator could be shown via additional state;
            // for now, this is a no-op acknowledgment.
            break;

          case "narration_complete":
            if (msg.entry) {
              setBundle((prev) => {
                if (!prev) return prev;
                const entry = msg.entry as NewChronicleEntry;
                const entries = Array.isArray(prev.chronicle_entries)
                  ? [...prev.chronicle_entries, entry]
                  : prev.chronicle_entries;
                return { ...prev, chronicle_entries: entries };
              });
            }
            break;

          case "completed":
            setServerState("completed");
            serverStateRef.current = "completed";
            setPaused(false);
            setPauseContext(null);
            break;

          case "bundle_loaded":
            {
              const classified = classifyParsedBundlePayload(msg.bundle);
              if (classified.kind === "legacy") {
                setBundle(classified.bundle);
                setError(null);
              } else {
                setError(formatBundleLoaderDiagnostics(classified.diagnostics));
              }
            }
            break;

          case "error":
            setError(msg.message);
            // Revert to lobby if we were in "starting" state
            if (serverStateRef.current === "starting") {
              setServerState("lobby");
              serverStateRef.current = "lobby";
            }
            break;

          case "batch_progress":
          case "batch_complete":
          case "batch_cancelled":
          case "batch_error":
          case "batch_report_loaded":
            handleBatchMessage(msg);
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
  }, [wsUrl, handleBatchMessage]);

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
    serverState,
    lobbyInit,
    sendStart,
    sendNarrateRange,
    loadBatchBundle,
    batch,
    wsRef,
  };
}
