import { useState, useEffect, useCallback, useRef } from "react";
import type {
  AckMessage,
  Bundle,
  Command,
  ForkedMessage,
  LobbyInit,
  NewChronicleEntry,
  PauseContext,
  StartCommand,
  TurnSnapshot,
} from "../types";
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

  const buildLiveTurnSnapshot = useCallback((msg: Record<string, unknown>): TurnSnapshot => ({
    turn: (msg.turn as number) ?? 0,
    civ_stats: (msg.civ_stats as TurnSnapshot["civ_stats"]) ?? {},
    region_control: (msg.region_control as TurnSnapshot["region_control"]) ?? {},
    relationships: (msg.relationships as TurnSnapshot["relationships"]) ?? {},
    trade_routes: msg.trade_routes as TurnSnapshot["trade_routes"],
    active_wars: msg.active_wars as TurnSnapshot["active_wars"],
    embargoes: msg.embargoes as TurnSnapshot["embargoes"],
    ecology: msg.ecology as TurnSnapshot["ecology"],
    mercenary_companies: msg.mercenary_companies as TurnSnapshot["mercenary_companies"],
    vassal_relations: msg.vassal_relations as TurnSnapshot["vassal_relations"],
    federations: msg.federations as TurnSnapshot["federations"],
    proxy_wars: msg.proxy_wars as TurnSnapshot["proxy_wars"],
    exile_modifiers: msg.exile_modifiers as TurnSnapshot["exile_modifiers"],
    capitals: msg.capitals as TurnSnapshot["capitals"],
    peace_turns: msg.peace_turns as TurnSnapshot["peace_turns"],
    region_cultural_identity: msg.region_cultural_identity as TurnSnapshot["region_cultural_identity"],
    movements_summary: msg.movements_summary as TurnSnapshot["movements_summary"],
    stress_index: msg.stress_index as TurnSnapshot["stress_index"],
    pandemic_regions: msg.pandemic_regions as TurnSnapshot["pandemic_regions"],
    climate_phase: msg.climate_phase as TurnSnapshot["climate_phase"],
    active_conditions: msg.active_conditions as TurnSnapshot["active_conditions"],
    per_pair_accuracy: msg.per_pair_accuracy as TurnSnapshot["per_pair_accuracy"],
    perception_errors: msg.perception_errors as TurnSnapshot["perception_errors"],
    settlement_source_turn: msg.settlement_source_turn as TurnSnapshot["settlement_source_turn"],
    settlement_count: msg.settlement_count as TurnSnapshot["settlement_count"],
    candidate_count: msg.candidate_count as TurnSnapshot["candidate_count"],
    total_settlement_population: msg.total_settlement_population as TurnSnapshot["total_settlement_population"],
    active_settlements: msg.active_settlements as TurnSnapshot["active_settlements"],
    founded_this_turn: msg.founded_this_turn as TurnSnapshot["founded_this_turn"],
    dissolved_this_turn: msg.dissolved_this_turn as TurnSnapshot["dissolved_this_turn"],
    urban_agent_count: msg.urban_agent_count as TurnSnapshot["urban_agent_count"],
    urban_fraction: msg.urban_fraction as TurnSnapshot["urban_fraction"],
  }), []);

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
              replaceBundle({
                world_state: msg.world_state,
                history: msg.history || [],
                events_timeline: msg.events_timeline || [],
                named_events: msg.named_events || [],
                chronicle_entries: msg.chronicle_entries || {},
                gap_summaries: msg.gap_summaries || [],
                era_reflections: msg.era_reflections || {},
                metadata: msg.metadata,
              });
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
              liveBundle.history.push(buildLiveTurnSnapshot(msg as Record<string, unknown>));
              if (isLegacyBundle(liveBundle.chronicle_entries)) {
                liveBundle.chronicle_entries = {
                  ...liveBundle.chronicle_entries,
                  [String(msg.turn)]: (msg.chronicle_text as string) || "",
                };
              }
              liveBundle.events_timeline.push(...((msg.events as Bundle["events_timeline"]) || []));
              liveBundle.named_events.push(...((msg.named_events as Bundle["named_events"]) || []));
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
                  lastSnapshot.civ_stats = {
                    ...lastSnapshot.civ_stats,
                    [ack.civ]: { ...civData, [ack.stat]: ack.value },
                  };
                  publishBundleMutation();
                }
              }
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
              const liveBundle = bundleRef.current;
              if (!liveBundle) {
                break;
              }
              if (Array.isArray(liveBundle.chronicle_entries)) {
                liveBundle.chronicle_entries.push(msg.entry as NewChronicleEntry);
                publishBundleMutation();
              }
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
  }, [wsUrl, buildLiveTurnSnapshot, handleBatchMessage, publishBundleMutation, replaceBundle]);

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
