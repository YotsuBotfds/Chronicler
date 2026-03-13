import { useCallback } from "react";
import { useBundle } from "./hooks/useBundle";
import { useTimeline } from "./hooks/useTimeline";
import { Layout } from "./components/Layout";

function App() {
  const { bundle, error, loading, loadFromFile } = useBundle();
  const timeline = useTimeline(bundle?.metadata.total_turns ?? 1);

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
    />
  );
}

export default App;
