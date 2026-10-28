import { useState, useEffect, useCallback, useRef } from "react";
import type {
  AckMessage,
  Bundle,
  CheckpointStatus,
  Command,
  ForkedMessage,
  LobbyInit,
  NewChronicleEntry,
  PauseContext,
  StartCommand,
} from "../types";
import { isLegacyBundle } from "../types";
import { useBatchConnection, type BatchConnectionState } from "./useBatchConnection";
import { classifyParsedBundlePayload, formatBundleLoaderDiagnostics } from "../lib/bundleLoader";
import {
  applyCompletedMessage, bundleFromInitMessage, snapshotFromMessage, withSessionToken,
} from "../lib/transport";

/** Failed attempts without ever opening before the viewer explains the refusal. */
const REFUSED_ATTEMPTS = 2;
export const LIVE_REFUSED_MESSAGE =
  "Could not connect to the live server. It accepts the viewer only from the link the CLI prints "
  + "(it carries the session token) and from the local dev or preview origin; see "
  + "docs/integration/historical-parity.md.";

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
  /** The last checkpoint request's outcome (null before the first). */
  checkpointStatus: CheckpointStatus | null;
  /** Ask the server for an exact checkpoint at the next turn boundary. */
  saveCheckpoint: () => void;
  serverState: ServerState;
  lobbyInit: LobbyInit | null;
  sendStart: (params: Omit<StartCommand, "type">) => void;
  sendNarrateRange: (startTurn: number, endTurn: number) => void;
  loadBatchBundle: (path: string) => void;
  batch: BatchConnectionState;
  wsRef: React.RefObject<WebSocket | null>;
}

/**
 * The live session at `wsUrl`. `token` is the session token from the
 * viewer link (`?token=`), added to the WebSocket URL; the server refuses
 * connections without it.
 */
export function useLiveConnection(wsUrl: string, token: string | null = null): LiveConnectionState {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const [pauseContext, setPauseContext] = useState<PauseContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [speed, setSpeedState] = useState(1);
  const [lastAck, setLastAck] = useState<AckMessage | null>(null);
  const [lastForked, setLastForked] = useState<ForkedMessage | null>(null);
  const [checkpointStatus, setCheckpointStatus] = useState<CheckpointStatus | null>(null);
  const [serverState, setServerState] = useState<ServerState>("connecting");
  const [lobbyInit, setLobbyInit] = useState<LobbyInit | null>(null);
  const bundleRef = useRef<Bundle | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(1000);
  const serverStateRef = useRef<ServerState>("connecting");
  const batch = useBatchConnection(wsRef);
  const handleBatchMessage = batch.handleMessage;

  const replaceBundle = useCallback((nextBundle: Bundle | null) => {
    bundleRef.current = nextBundle;
    setBundle(nextBundle ? { ...nextBundle } : null);
  }, []);

  const publishBundleMutation = useCallback(() => {
    const nextBundle = bundleRef.current;
    setBundle(nextBundle ? { ...nextBundle } : null);
  }, []);

  const sendCommand = useCallback((cmd: Command) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  }, []);

  const saveCheckpoint = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setCheckpointStatus({ state: "saving" });
      wsRef.current.send(JSON.stringify({ type: "checkpoint" }));
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
    const url = withSessionToken(wsUrl, token);
    let opened = false;
    let failures = 0;

    function connect() {
      if (unmounted) return;
      const ws = new WebSocket(url);
      wsRef.current = ws;
      let thisOpened = false;

      ws.onopen = () => {
        if (unmounted) return;
        opened = true;
        thisOpened = true;
        failures = 0;
        setConnected(true);
        setError(null);
        reconnectDelayRef.current = 1000;
      };

      ws.onclose = () => {
        if (unmounted) return;
        // A handshake the server refuses (wrong origin or token) closes before opening.
        if (!thisOpened && !opened && ++failures >= REFUSED_ATTEMPTS) {
          setError(LIVE_REFUSED_MESSAGE);
        }
        setConnected(false);
        wsRef.current = null;
        if (reconnectRef.current) clearTimeout(reconnectRef.current);
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
              // Reconnect history rows and bundle systems through the transport contract.
              replaceBundle(bundleFromInitMessage(msg));
              if (msg.speed !== undefined) {
                setSpeedState(msg.speed);
              }
            }
            break;

          case "turn":
            {
              const liveBundle = bundleRef.current;
              if (!liveBundle) {
                break;
              }
              liveBundle.history = [...liveBundle.history, snapshotFromMessage(msg as Record<string, unknown>)];
              if (isLegacyBundle(liveBundle.chronicle_entries)) {
                liveBundle.chronicle_entries = {
                  ...liveBundle.chronicle_entries,
                  [String(msg.turn)]: (msg.chronicle_text as string) || "",
                };
              }
              liveBundle.events_timeline = [...liveBundle.events_timeline, ...((msg.events as Bundle["events_timeline"]) || [])];
              liveBundle.named_events = [...liveBundle.named_events, ...((msg.named_events as Bundle["named_events"]) || [])];
              publishBundleMutation();
            }
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
              const liveBundle = bundleRef.current;
              if (liveBundle && liveBundle.history.length > 0) {
                const lastSnapshot = liveBundle.history[liveBundle.history.length - 1];
                const civData = lastSnapshot.civ_stats[ack.civ];
                if (civData) {
                  const updatedSnapshot = { ...lastSnapshot, civ_stats: { ...lastSnapshot.civ_stats, [ack.civ]: { ...civData, [ack.stat]: ack.value } } };
                  liveBundle.history = [...liveBundle.history.slice(0, -1), updatedSnapshot];
                  publishBundleMutation();
                }
              }
            }
            break;
          }

          case "forked":
            setLastForked(msg as ForkedMessage);
            break;

          case "checkpoint_requested":
            // Written at the next turn boundary; checkpoint_saved follows.
            break;

          case "checkpoint_saved":
            setCheckpointStatus({
              state: "saved",
              turn: msg.turn,
              path: msg.path,
              resumeHint: msg.resume_hint ?? "",
            });
            break;

          case "checkpoint_error":
            setCheckpointStatus({ state: "error", message: msg.message });
            break;

          case "narration_started":
            // Loading indicator could be shown via additional state;
            // for now, this is a no-op acknowledgment.
            break;

          case "narration_complete":
            if (msg.entry) {
              const liveBundle = bundleRef.current;
              if (!liveBundle) {
                break;
              }
              if (Array.isArray(liveBundle.chronicle_entries)) {
                liveBundle.chronicle_entries = [...(liveBundle.chronicle_entries as NewChronicleEntry[]), msg.entry as NewChronicleEntry];
                publishBundleMutation();
              }
            }
            break;

          case "completed":
            setServerState("completed");
            serverStateRef.current = "completed";
            setPaused(false);
            setPauseContext(null);
            if (bundleRef.current) {
              // The finished run's historiography and languages.
              replaceBundle(applyCompletedMessage(bundleRef.current, msg));
            }
            break;

          case "bundle_loaded":
            {
              const classified = classifyParsedBundlePayload(msg.bundle);
              if (classified.kind === "legacy") {
                replaceBundle(classified.bundle);
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
  }, [wsUrl, token, handleBatchMessage, publishBundleMutation, replaceBundle]);

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
    checkpointStatus,
    saveCheckpoint,
    serverState,
    lobbyInit,
    sendStart,
    sendNarrateRange,
    loadBatchBundle,
    batch,
    wsRef,
  };
}
