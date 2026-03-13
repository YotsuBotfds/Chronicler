import { useState, useEffect } from "react";
import type { Bundle } from "../types";
import { Header } from "./Header";
import { TimelineScrubber } from "./TimelineScrubber";
import { ChroniclePanel } from "./ChroniclePanel";
import { EventLog } from "./EventLog";
import { FactionDashboard } from "./FactionDashboard";
import { TerritoryMap } from "./TerritoryMap";
import { StatGraphs } from "./StatGraphs";

interface LayoutProps {
  bundle: Bundle;
  currentTurn: number;
  playing: boolean;
  speed: number;
  onSeek: (turn: number) => void;
  onPlay: () => void;
  onPause: () => void;
  onSetSpeed: (speed: number) => void;
}

export function Layout({
  bundle,
  currentTurn,
  playing,
  speed,
  onSeek,
  onPlay,
  onPause,
  onSetSpeed,
}: LayoutProps) {
  const [darkMode, setDarkMode] = useState(true);
  const [leftTab, setLeftTab] = useState<"chronicle" | "events">("chronicle");
  const [showRelationships, setShowRelationships] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
  }, [darkMode]);

  return (
    <div className="min-h-screen flex flex-col bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
      <Header
        worldName={bundle.world_state.name}
        metadata={bundle.metadata}
        currentTurn={currentTurn}
        darkMode={darkMode}
        onToggleDarkMode={() => setDarkMode(!darkMode)}
      />
      <TimelineScrubber
        currentTurn={currentTurn}
        maxTurn={bundle.metadata.total_turns}
        playing={playing}
        speed={speed}
        history={bundle.history}
        namedEvents={bundle.named_events}
        onSeek={onSeek}
        onPlay={onPlay}
        onPause={onPause}
        onSetSpeed={onSetSpeed}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left column */}
        <div className="w-[35%] flex flex-col border-r border-gray-700">
          <div className="flex border-b border-gray-700">
            <button
              onClick={() => setLeftTab("chronicle")}
              className={`flex-1 py-2 text-sm ${
                leftTab === "chronicle"
                  ? "bg-gray-700 text-gray-100"
                  : "bg-gray-800 text-gray-400 hover:text-gray-200"
              }`}
            >
              Chronicle
            </button>
            <button
              onClick={() => setLeftTab("events")}
              className={`flex-1 py-2 text-sm ${
                leftTab === "events"
                  ? "bg-gray-700 text-gray-100"
                  : "bg-gray-800 text-gray-400 hover:text-gray-200"
              }`}
            >
              Events
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            {leftTab === "chronicle" ? (
              <ChroniclePanel
                chronicleEntries={bundle.chronicle_entries}
                eraReflections={bundle.era_reflections}
                currentTurn={currentTurn}
                maxTurn={bundle.metadata.total_turns}
              />
            ) : (
              <EventLog
                events={bundle.events_timeline}
                onJumpToTurn={onSeek}
              />
            )}
          </div>
        </div>

        {/* Right column */}
        <div className="w-[65%] flex flex-col overflow-y-auto">
          <FactionDashboard
            civilizations={bundle.world_state.civilizations}
            history={bundle.history}
            currentTurn={currentTurn}
          />
          <div className="border-t border-gray-700">
            <TerritoryMap
              regions={bundle.world_state.regions}
              history={bundle.history}
              currentTurn={currentTurn}
              showRelationships={showRelationships}
              onToggleRelationships={() => setShowRelationships(!showRelationships)}
            />
          </div>
          <div className="border-t border-gray-700">
            <StatGraphs
              civilizations={bundle.world_state.civilizations}
              history={bundle.history}
              namedEvents={bundle.named_events}
              currentTurn={currentTurn}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
