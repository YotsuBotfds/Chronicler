import { useState, useCallback, useMemo } from "react";
import type { BatchReport, Bundle, PercentileData } from "../types";
import type { ArtifactIdentity } from "../lib/artifactIdentity";
import { BatchAnalytics } from "./BatchAnalytics";
import { CompletedRunCompare } from "./CompletedRunCompare";

interface BatchCompareProps {
  initialRight?: BatchReport | null;
  initialBundle?: Bundle | null;
  initialIdentity?: ArtifactIdentity | null;
  initialMode?: "runs" | "batch";
}

export function BatchCompare({ initialRight, initialBundle, initialIdentity, initialMode }: BatchCompareProps) {
  const [mode, setMode] = useState(initialMode ?? (initialRight && !initialBundle ? "batch" : "runs"));
  return <div className="flex flex-col h-full min-h-0">
    <nav className="run-compare-modes" aria-label="Comparison type">
      <button type="button" aria-pressed={mode === "runs"} onClick={() => setMode("runs")}>Completed runs</button>
      <button type="button" aria-pressed={mode === "batch"} onClick={() => setMode("batch")}>Batch reports</button>
    </nav>
    <div hidden={mode !== "runs"} className="flex-1 min-h-0">
      <CompletedRunCompare initialBundle={initialBundle} initialIdentity={initialIdentity} />
    </div>
    <div hidden={mode !== "batch"} className="flex-1 min-h-0">
      <BatchReportComparison initialRight={initialRight} />
    </div>
  </div>;
}

function BatchReportComparison({ initialRight }: Pick<BatchCompareProps, "initialRight">) {
  const [leftReport, setLeftReport] = useState<BatchReport | null>(null);
  const [rightReport, setRightReport] = useState<BatchReport | null>(initialRight ?? null);
  const [error, setError] = useState<string | null>(null);

  const loadFromFile = useCallback((setter: (r: BatchReport) => void) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          setter(readBatchReport(reader.result as string));
          setError(null);
        } catch {
          setError("Could not load this batch report. For a chronicle bundle, choose Completed runs. Loaded reports are kept.");
        }
      };
      reader.onerror = () => setError("Could not read this file. Loaded reports are kept.");
      reader.readAsText(file);
    };
    input.click();
  }, []);

  const handleDrop = useCallback((setter: (r: BatchReport) => void) => (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        setter(readBatchReport(reader.result as string));
        setError(null);
      } catch {
        setError("Could not load this batch report. For a chronicle bundle, choose Completed runs. Loaded reports are kept.");
      }
    };
    reader.onerror = () => setError("Could not read this file. Loaded reports are kept.");
    reader.readAsText(file);
  }, []);

  return (
    <div className="flex flex-col h-full min-h-0">
      {error && <p role="alert" className="text-red-300 mb-3">{error}</p>}
    <div className="flex gap-4 flex-1 min-h-0">
      {/* Left column */}
      <div className="flex-1 overflow-y-auto">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-gray-400 uppercase">Baseline</h3>
          <button
            onClick={() => loadFromFile(setLeftReport)}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-1 border border-gray-600 rounded"
          >
            Load Report
          </button>
        </div>
        {leftReport ? (
          <BatchAnalytics report={leftReport} />
        ) : (
          <div
            className="h-40 flex items-center justify-center text-gray-500 text-sm border border-dashed border-gray-600 rounded cursor-pointer hover:border-gray-500"
            onClick={() => loadFromFile(setLeftReport)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop(setLeftReport)}
          >
            Drop batch_report.json or click to load
          </div>
        )}
      </div>

      {/* Diff summary (center) */}
      {leftReport && rightReport && (
        <div className="w-48 shrink-0">
          <DiffSummary left={leftReport} right={rightReport} />
        </div>
      )}

      {/* Right column */}
      <div className="flex-1 overflow-y-auto">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-gray-400 uppercase">Current</h3>
          <button
            onClick={() => loadFromFile(setRightReport)}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-1 border border-gray-600 rounded"
          >
            Load Report
          </button>
        </div>
        {rightReport ? (
          <BatchAnalytics report={rightReport} />
        ) : (
          <div
            className="h-40 flex items-center justify-center text-gray-500 text-sm border border-dashed border-gray-600 rounded cursor-pointer hover:border-gray-500"
            onClick={() => loadFromFile(setRightReport)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop(setRightReport)}
          >
            Drop batch_report.json or click to load
          </div>
        )}
      </div>
    </div>
    </div>
  );
}

/** Validate the fields consumed by the existing report panels before replacing either report. */
function readBatchReport(text: string): BatchReport {
  const raw: unknown = JSON.parse(text);
  const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
  const number = (value: unknown) => typeof value === "number" && Number.isFinite(value);
  if (!object(raw) || !object(raw.metadata) || !object(raw.stability) || !object(raw.stability.percentiles_by_turn)
    || !object(raw.event_firing_rates) || !Array.isArray(raw.anomalies)) throw new Error("Not a batch report");
  const metadata = raw.metadata;
  if (!number(metadata.runs) || !number(metadata.turns_per_run) || typeof metadata.timestamp !== "string"
    || !Array.isArray(metadata.seed_range) || metadata.seed_range.length !== 2 || !metadata.seed_range.every(number)
    || !Object.values(raw.event_firing_rates).every(number)
    || !Object.values(raw.stability.percentiles_by_turn).every((row) => object(row)
      && ["min", "p10", "p25", "median", "p75", "p90", "max"].every((key) => number(row[key])))
    || !raw.anomalies.every((row) => object(row) && typeof row.name === "string" && typeof row.detail === "string"
      && ["CRITICAL", "WARNING", "INFO"].includes(String(row.severity)))) throw new Error("Malformed batch report");
  return raw as unknown as BatchReport;
}

function DiffSummary({ left, right }: { left: BatchReport; right: BatchReport }) {
  const diffs = useMemo(() => computeDiffs(left, right), [left, right]);

  return (
    <div className="space-y-3 mt-8">
      <h4 className="text-xs font-bold text-gray-400 uppercase">Changes</h4>

      {/* Stability deltas */}
      {diffs.stabilityDeltas.length > 0 && (
        <div className="bg-gray-800 rounded px-3 py-2 border border-gray-700">
          <p className="text-[10px] text-gray-500 uppercase mb-1">Stability</p>
          {diffs.stabilityDeltas.map((d) => (
            <div key={d.turn} className="flex justify-between text-xs">
              <span className="text-gray-400">T{d.turn}</span>
              <span className={d.delta > 0 ? "text-green-400" : "text-red-400"}>
                {d.delta > 0 ? "\u2191" : "\u2193"} {Math.abs(d.delta).toFixed(1)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Firing rate changes */}
      {(diffs.gained.length > 0 || diffs.lost.length > 0 || diffs.changed.length > 0) && (
        <div className="bg-gray-800 rounded px-3 py-2 border border-gray-700">
          <p className="text-[10px] text-gray-500 uppercase mb-1">Mechanics</p>
          {diffs.gained.map((e) => (
            <p key={e} className="text-xs text-green-400">+ {e}</p>
          ))}
          {diffs.lost.map((e) => (
            <p key={e} className="text-xs text-red-400">- {e}</p>
          ))}
          {diffs.changed.map((c) => (
            <div key={c.event} className="flex justify-between text-xs">
              <span className="text-yellow-400">{c.event}</span>
              <span className="text-gray-500">{(c.oldRate * 100).toFixed(0)}%&rarr;{(c.newRate * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}

      {/* Anomaly changes */}
      {(diffs.newAnomalies.length > 0 || diffs.resolvedAnomalies.length > 0) && (
        <div className="bg-gray-800 rounded px-3 py-2 border border-gray-700">
          <p className="text-[10px] text-gray-500 uppercase mb-1">Anomalies</p>
          {diffs.resolvedAnomalies.map((a) => (
            <p key={a} className="text-xs text-green-400">Resolved: {a}</p>
          ))}
          {diffs.newAnomalies.map((a) => (
            <p key={a} className="text-xs text-red-400">New: {a}</p>
          ))}
        </div>
      )}

      {diffs.stabilityDeltas.length === 0 && diffs.gained.length === 0 && diffs.lost.length === 0 && diffs.changed.length === 0 && diffs.newAnomalies.length === 0 && diffs.resolvedAnomalies.length === 0 && (
        <p className="text-xs text-gray-500">No significant changes</p>
      )}
    </div>
  );
}

interface Diffs {
  stabilityDeltas: { turn: number; delta: number }[];
  gained: string[];
  lost: string[];
  changed: { event: string; oldRate: number; newRate: number }[];
  newAnomalies: string[];
  resolvedAnomalies: string[];
}

function computeDiffs(left: BatchReport, right: BatchReport): Diffs {
  // Stability median changes per checkpoint
  const stabilityDeltas: { turn: number; delta: number }[] = [];
  const leftStab = left.stability.percentiles_by_turn;
  const rightStab = right.stability.percentiles_by_turn;
  for (const turn of Object.keys(rightStab)) {
    if (leftStab[turn] && rightStab[turn]) {
      const delta = (rightStab[turn] as PercentileData).median - (leftStab[turn] as PercentileData).median;
      if (Math.abs(delta) >= 1) {
        stabilityDeltas.push({ turn: Number(turn), delta });
      }
    }
  }

  // Firing rate changes
  const leftRates = left.event_firing_rates;
  const rightRates = right.event_firing_rates;
  const allEvents = new Set([...Object.keys(leftRates), ...Object.keys(rightRates)]);
  const gained: string[] = [];
  const lost: string[] = [];
  const changed: { event: string; oldRate: number; newRate: number }[] = [];

  for (const event of allEvents) {
    const lRate = leftRates[event] ?? 0;
    const rRate = rightRates[event] ?? 0;
    if (lRate === 0 && rRate > 0) {
      gained.push(event);
    } else if (lRate > 0 && rRate === 0) {
      lost.push(event);
    } else if (Math.abs(rRate - lRate) >= 0.05) {
      changed.push({ event, oldRate: lRate, newRate: rRate });
    }
  }

  // Anomaly changes
  const leftNames = new Set(left.anomalies.map((a) => a.name));
  const rightNames = new Set(right.anomalies.map((a) => a.name));
  const newAnomalies = [...rightNames].filter((n) => !leftNames.has(n));
  const resolvedAnomalies = [...leftNames].filter((n) => !rightNames.has(n));

  return { stabilityDeltas, gained, lost, changed, newAnomalies, resolvedAnomalies };
}
