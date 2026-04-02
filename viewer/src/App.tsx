import { useCallback, useEffect, useEffectEvent, useRef, useState, Component, type ReactNode } from "react";
import { useBundle } from "./hooks/useBundle";
import { useLiveConnection } from "./hooks/useLiveConnection";
import { useTimeline } from "./hooks/useTimeline";
import { AppShell, type AppSurface } from "./components/phase75/AppShell";

// --- Error Boundary ---

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center">
          <div className="text-center space-y-4 max-w-lg">
            <h1 className="text-2xl font-bold text-red-400">
              Something went wrong
            </h1>
            <p className="text-gray-400">
              The viewer encountered an unexpected error. Try reloading the page.
            </p>
            <pre className="text-sm text-gray-500 bg-gray-800 p-3 rounded overflow-auto text-left">
              {this.state.error?.message}
            </pre>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 rounded bg-gray-700 hover:bg-gray-600 text-gray-200"
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  const wsUrl = new URLSearchParams(window.location.search).get("ws");
  const isLive = wsUrl !== null;

  const {
    bundle: staticBundle,
    error: staticError,
    loading,
    loadFromFile,
  } = useBundle();
  const liveConn = useLiveConnection(wsUrl || "");

  const bundle = isLive ? liveConn.bundle : staticBundle;
  const error = isLive ? liveConn.error : staticError;

  const timeline = useTimeline(
    bundle?.history.length ?? bundle?.metadata?.total_turns ?? 1,
    { liveMode: isLive && liveConn.connected },
  );

  const [surface, setSurface] = useState<AppSurface>("setup");
  const prevBatchState = useRef(liveConn.batch.batchState);
  const prevServerState = useRef(liveConn.serverState);
  const prevBundleKey = useRef<string | null>(null);
  const showProgressSurface = useEffectEvent(() => {
    setSurface("progress");
  });
  const showBatchSurface = useEffectEvent(() => {
    setSurface("batch");
  });
  const showOverviewSurface = useEffectEvent(() => {
    setSurface("overview");
  });

  useEffect(() => {
    if (!isLive) {
      return;
    }

    if (liveConn.serverState === "starting" && prevServerState.current !== "starting") {
      showProgressSurface();
    }

    prevServerState.current = liveConn.serverState;
  }, [isLive, liveConn.serverState]);

  useEffect(() => {
    if (!isLive) {
      return;
    }

    if (liveConn.batch.batchState !== prevBatchState.current) {
      if (
        liveConn.batch.batchState === "running"
        || liveConn.batch.batchState === "complete"
        || liveConn.batch.batchState === "cancelled"
        || liveConn.batch.batchState === "error"
      ) {
        showBatchSurface();
      }
      prevBatchState.current = liveConn.batch.batchState;
    }
  }, [isLive, liveConn.batch.batchState]);

  useEffect(() => {
    const bundleKey = bundle
      ? `${bundle.metadata.seed}:${bundle.metadata.total_turns}:${bundle.metadata.generated_at ?? ""}:${bundle.world_state.name}`
      : null;

      if (bundleKey && bundleKey !== prevBundleKey.current) {
        timeline.pause();
        timeline.seek(isLive && liveConn.serverState === "running"
        ? bundle?.history[bundle.history.length - 1]?.turn ?? 1
        : 1);
      if (surface === "setup" || surface === "progress" || surface === "batch") {
        showOverviewSurface();
      }
    }

    prevBundleKey.current = bundleKey;
  }, [bundle, isLive, liveConn.serverState, surface, timeline]);

  const handleSurfaceChange = (nextSurface: AppSurface) => {
    if (
      (nextSurface === "overview"
        || nextSurface === "character"
        || nextSurface === "trade"
        || nextSurface === "campaign")
      && !bundle
    ) {
      return;
    }
    if (nextSurface === "progress" && liveConn.serverState !== "starting") {
      return;
    }
    setSurface(nextSurface);
  };

  return (
    <AppShell
      surface={surface}
      onSurfaceChange={handleSurfaceChange}
      bundle={bundle}
      bundleLoading={loading}
      error={error}
      isLive={isLive}
      connected={liveConn.connected}
      serverState={liveConn.serverState}
      currentTurn={timeline.currentTurn}
      playing={timeline.playing}
      speed={timeline.speed}
      onSeek={timeline.seek}
      onPlay={timeline.play}
      onPause={timeline.pause}
      onSetSpeed={liveConn.connected ? liveConn.setSpeed : timeline.setSpeed}
      lobbyInit={liveConn.lobbyInit}
      starting={liveConn.serverState === "starting"}
      onLaunch={liveConn.sendStart}
      batchState={liveConn.batch.batchState}
      batchReport={liveConn.batch.report}
      batchProgress={liveConn.batch.progress}
      batchError={liveConn.batch.error}
      onBatchStart={liveConn.batch.startBatch}
      onBatchCancel={liveConn.batch.cancelBatch}
      onBatchReset={liveConn.batch.reset}
      onOpenBatchResult={(path) => {
        liveConn.loadBatchBundle(path);
        setSurface("overview");
      }}
      onOpenBundleFile={loadFromFile}
      livePaused={liveConn.paused}
      livePauseContext={liveConn.pauseContext}
      liveSendCommand={liveConn.sendCommand}
      liveForkedPath={liveConn.lastForked?.save_path}
      liveForkedHint={liveConn.lastForked?.cli_hint}
      liveReconnecting={!liveConn.connected && !!wsUrl}
    />
  );
}

function AppWithErrorBoundary() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}

export default AppWithErrorBoundary;
