import type { BundleMetadata } from "../types";
import { formatTurn, formatScore } from "../lib/format";

interface HeaderProps {
  worldName: string;
  metadata: BundleMetadata;
  currentTurn: number;
  darkMode: boolean;
  onToggleDarkMode: () => void;
}

export function Header({
  worldName,
  metadata,
  currentTurn,
  darkMode,
  onToggleDarkMode,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-4 py-2 bg-gray-100 dark:bg-gray-800 border-b border-gray-300 dark:border-gray-700">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-bold">{worldName}</h1>
        {metadata.scenario_name && (
          <span className="text-sm text-gray-500 dark:text-gray-400">{metadata.scenario_name}</span>
        )}
        <span className="text-sm font-mono">
          {formatTurn(currentTurn, metadata.total_turns)}
        </span>
      </div>
      <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
        <span>Seed: {metadata.seed}</span>
        <span>{metadata.sim_model}</span>
        {metadata.interestingness_score !== null && (
          <span>{formatScore(metadata.interestingness_score)}</span>
        )}
        <button
          onClick={onToggleDarkMode}
          className="px-2 py-1 rounded bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
        >
          {darkMode ? "Light" : "Dark"}
        </button>
      </div>
    </header>
  );
}
