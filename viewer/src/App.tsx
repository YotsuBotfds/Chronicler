import { useCallback, Component, type ReactNode } from "react";
import { useBundle } from "./hooks/useBundle";
import { useLiveConnection } from "./hooks/useLiveConnection";
import { useTimeline } from "./hooks/useTimeline";
import { Layout } from "./components/Layout";
import { SetupLobby } from "./components/SetupLobby";

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

  // Both hooks always called (Rules of Hooks) — only one is active
  const { bundle: staticBundle, error: staticError, loading, loadFromFile } = useBundle();
  const liveConn = useLiveConnection(wsUrl || "");

  const isLive = wsUrl !== null;
  const bundle = isLive ? liveConn.bundle : staticBundle;
  const error = isLive ? liveConn.error : staticError;

  const timeline = useTimeline(
    bundle?.history.length ?? bundle?.metadata?.total_turns ?? 1,
    { liveMode: isLive && liveConn.connected },
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) loadFromFile(file);
    },
    [loadFromFile],
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) loadFromFile(file);
    },
    [loadFromFile],
  );

  // --- Live mode state machine ---
  if (isLive) {
    switch (liveConn.serverState) {
      case "connecting":
        return (
          <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center">
            <p className="text-gray-400">Connecting to simulation...</p>
          </div>
        );

      case "lobby":
      case "starting":
        if (!liveConn.lobbyInit) {
          // Reconnect during world-gen: server sent "starting" but no lobby data
          return (
            <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center">
              <p className="text-gray-400">World generating...</p>
            </div>
          );
        }
        return (
          <SetupLobby
            lobbyInit={liveConn.lobbyInit}
            onLaunch={liveConn.sendStart}
            starting={liveConn.serverState === "starting"}
            error={liveConn.error}
            batchState={liveConn.batch.batchState}
            batchReport={liveConn.batch.report}
            batchProgress={liveConn.batch.progress}
            batchError={liveConn.batch.error}
            onBatchStart={liveConn.batch.startBatch}
            onBatchCancel={liveConn.batch.cancelBatch}
            onBatchReset={liveConn.batch.reset}
          />
        );

      case "running":
      case "completed":
        if (!bundle) {
          return (
            <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center">
              <p className="text-gray-400">Waiting for simulation data...</p>
            </div>
          );
        }
        return (
          <Layout
            bundle={bundle}
            currentTurn={timeline.currentTurn}
            playing={timeline.playing}
            speed={timeline.speed}
            onSeek={timeline.seek}
            onPlay={timeline.play}
            onPause={timeline.pause}
            onSetSpeed={liveConn.connected ? liveConn.setSpeed : timeline.setSpeed}
            liveConnected={liveConn.connected}
            livePaused={liveConn.paused}
            livePauseContext={liveConn.pauseContext}
            liveSendCommand={liveConn.sendCommand}
            liveForkedPath={liveConn.lastForked?.save_path}
            liveForkedHint={liveConn.lastForked?.cli_hint}
            liveReconnecting={!liveConn.connected && !!wsUrl}
          />
        );
    }
  }

  // --- Static mode (unchanged) ---
  if (!bundle) {
    return (
      <div
        className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
      >
        <div className="text-center space-y-4">
          <h1 className="text-2xl font-bold">Chronicler Viewer</h1>
          <p className="text-gray-400">
            Drag and drop a <code className="text-blue-400">chronicle_bundle.json</code> file here
          </p>
          <label className="inline-block px-4 py-2 rounded bg-gray-700 hover:bg-gray-600 cursor-pointer">
            Or choose a file
            <input
              type="file"
              accept=".json"
              onChange={handleFileInput}
              className="hidden"
            />
          </label>
          {loading && <p className="text-gray-400">Loading...</p>}
          {error && <p className="text-red-400">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <Layout
      bundle={bundle}
      currentTurn={timeline.currentTurn}
      playing={timeline.playing}
      speed={timeline.speed}
      onSeek={timeline.seek}
      onPlay={timeline.play}
      onPause={timeline.pause}
      onSetSpeed={timeline.setSpeed}
      liveConnected={undefined}
      livePaused={undefined}
      livePauseContext={undefined}
      liveSendCommand={undefined}
      liveForkedPath={undefined}
      liveForkedHint={undefined}
      liveReconnecting={undefined}
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
