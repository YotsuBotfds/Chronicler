import { useState, useCallback } from "react";
import type { BatchConfig, BatchReport } from "../types";
import type { BatchState } from "../hooks/useBatchConnection";
import { BatchAnalytics } from "./BatchAnalytics";

const TUNING_CATEGORIES: Record<string, { key: string; label: string; default: number }[]> = {
  "Stability Drains": [
    { key: "stability.drain.drought_immediate", label: "Drought Immediate", default: 3 },
    { key: "stability.drain.drought_ongoing", label: "Drought Ongoing", default: 2 },
    { key: "stability.drain.plague_immediate", label: "Plague Immediate", default: 3 },
    { key: "stability.drain.famine_immediate", label: "Famine Immediate", default: 3 },
    { key: "stability.drain.war_cost", label: "War Cost", default: 2 },
    { key: "stability.drain.governing_per_distance", label: "Governing/Distance", default: 0.5 },
    { key: "stability.drain.condition_ongoing", label: "Condition Ongoing", default: 1 },
    { key: "stability.drain.rebellion", label: "Rebellion", default: 4 },
    { key: "stability.drain.leader_death", label: "Leader Death", default: 4 },
    { key: "stability.drain.border_incident", label: "Border Incident", default: 2 },
    { key: "stability.drain.religious_movement", label: "Religious Movement", default: 4 },
    { key: "stability.drain.migration", label: "Migration", default: 4 },
    { key: "stability.drain.twilight", label: "Twilight", default: 5 },
  ],
  "Stability Recovery": [
    { key: "stability.recovery_per_turn", label: "Recovery/Turn", default: 20 },
  ],
  "Fertility": [
    { key: "fertility.degradation_rate", label: "Degradation Rate", default: 0.005 },
    { key: "fertility.recovery_rate", label: "Recovery Rate", default: 0.05 },
    { key: "fertility.famine_threshold", label: "Famine Threshold", default: 0.05 },
  ],
  "Military": [
    { key: "military.maintenance_free_threshold", label: "Free Threshold", default: 3 },
  ],
  "Emergence": [
    { key: "emergence.black_swan_base_probability", label: "Black Swan Prob", default: 0.015 },
    { key: "emergence.black_swan_cooldown_turns", label: "Black Swan Cooldown", default: 50 },
  ],
  "Regression": [
    { key: "regression.capital_collapse_probability", label: "Capital Collapse", default: 0.3 },
    { key: "regression.entered_twilight_probability", label: "Twilight Prob", default: 0.5 },
    { key: "regression.black_swan_stressed_probability", label: "Black Swan Stressed", default: 0.2 },
  ],
};

interface BatchPanelProps {
  batchState: BatchState;
  report: BatchReport | null;
  progress: { completed: number; total: number; currentSeed: number } | null;
  error: string | null;
  onStart: (config: BatchConfig) => void;
  onCancel: () => void;
  onReset: () => void;
}

export function BatchPanel({
  batchState,
  report,
  progress,
  error,
  onStart,
  onCancel,
  onReset,
}: BatchPanelProps) {
  const [seedStart, setSeedStart] = useState(1);
  const [seedCount, setSeedCount] = useState(200);
  const [turns, setTurns] = useState(500);
  const [workers, setWorkers] = useState(0);
  const [simulateOnly, setSimulateOnly] = useState(true);
  const [showTuning, setShowTuning] = useState(false);
  const [tuningValues, setTuningValues] = useState<Record<string, string>>({});

  const handleStart = useCallback(() => {
    const overrides: Record<string, number> = {};
    for (const [key, val] of Object.entries(tuningValues)) {
      if (val !== "") {
        overrides[key] = Number(val);
      }
    }

    onStart({
      seed_start: seedStart,
      seed_count: seedCount,
      turns,
      simulate_only: simulateOnly,
      parallel: true,
      workers: workers > 0 ? workers : null,
      tuning_overrides: Object.keys(overrides).length > 0 ? overrides : null,
    });
  }, [seedStart, seedCount, turns, workers, simulateOnly, tuningValues, onStart]);

  const setTuningValue = useCallback((key: string, value: string) => {
    setTuningValues((prev) => ({ ...prev, [key]: value }));
  }, []);

  // Show analytics view when complete
  if (batchState === "complete" && report) {
    return (
      <div className="space-y-4">
        <button
          onClick={onReset}
          className="text-sm text-gray-400 hover:text-gray-200 transition-colors"
        >
          &larr; New Batch
        </button>
        <BatchAnalytics report={report} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Config fields */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-[10px] text-gray-500 uppercase mb-1">Start Seed</label>
          <input
            type="number"
            min={0}
            value={seedStart}
            onChange={(e) => setSeedStart(Number(e.target.value) || 0)}
            disabled={batchState === "running"}
            className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-[10px] text-gray-500 uppercase mb-1">Seed Count</label>
          <input
            type="number"
            min={1}
            value={seedCount}
            onChange={(e) => setSeedCount(Number(e.target.value) || 1)}
            disabled={batchState === "running"}
            className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 disabled:opacity-50"
          />
        </div>
      </div>

      <div>
        <label className="block text-[10px] text-gray-500 uppercase mb-1">Turns</label>
        <input
          type="number"
          min={1}
          value={turns}
          onChange={(e) => setTurns(Number(e.target.value) || 1)}
          disabled={batchState === "running"}
          className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 disabled:opacity-50"
        />
      </div>

      <div>
        <label className="block text-[10px] text-gray-500 uppercase mb-1">Workers (0 = auto)</label>
        <input
          type="number"
          min={0}
          value={workers}
          onChange={(e) => setWorkers(Number(e.target.value) || 0)}
          disabled={batchState === "running"}
          className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 disabled:opacity-50"
        />
      </div>

      <label className="flex items-center gap-2 text-sm text-gray-300">
        <input
          type="checkbox"
          checked={simulateOnly}
          onChange={(e) => setSimulateOnly(e.target.checked)}
          disabled={batchState === "running"}
          className="rounded"
        />
        Simulate Only
      </label>

      {/* Tuning overrides (collapsible) */}
      <div>
        <button
          onClick={() => setShowTuning(!showTuning)}
          className="text-xs text-gray-400 hover:text-gray-200 transition-colors"
        >
          {showTuning ? "\u25BC" : "\u25B6"} Tuning Overrides
        </button>

        {showTuning && (
          <div className="mt-2 space-y-3 max-h-60 overflow-y-auto pr-1">
            {Object.entries(TUNING_CATEGORIES).map(([category, keys]) => (
              <div key={category}>
                <p className="text-[10px] text-gray-500 uppercase mb-1">{category}</p>
                <div className="space-y-1">
                  {keys.map((k) => (
                    <div key={k.key} className="flex items-center gap-2">
                      <label className="text-xs text-gray-400 flex-1 truncate" title={k.key}>
                        {k.label}
                      </label>
                      <input
                        type="number"
                        step="any"
                        placeholder={String(k.default)}
                        value={tuningValues[k.key] || ""}
                        onChange={(e) => setTuningValue(k.key, e.target.value)}
                        disabled={batchState === "running"}
                        className="w-20 bg-gray-700 text-gray-200 rounded px-1.5 py-0.5 text-xs border border-gray-600 placeholder-gray-500 disabled:opacity-50"
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Progress bar */}
      {batchState === "running" && progress && (
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-gray-400">
            <span>Seed {progress.currentSeed}</span>
            <span>{progress.completed}/{progress.total}</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className="bg-green-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${(progress.completed / progress.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="bg-red-900/50 border border-red-800 rounded px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Run / Cancel button */}
      {batchState === "running" ? (
        <button
          onClick={onCancel}
          className="w-full py-3 bg-red-600 hover:bg-red-500 text-white rounded-lg font-bold text-base tracking-wide transition-colors"
        >
          Cancel Batch
        </button>
      ) : (
        <button
          onClick={handleStart}
          disabled={seedCount <= 0 || turns <= 0}
          className="w-full py-3 bg-green-600 hover:bg-green-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-bold text-base tracking-wide transition-colors"
        >
          {"\u25B6"} Run Batch
        </button>
      )}
    </div>
  );
}
