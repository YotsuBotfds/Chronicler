import { useState, useMemo } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { BatchReport, AnomalyFlag, PercentileData } from "../types";

interface BatchAnalyticsProps {
  report: BatchReport;
}

export function BatchAnalytics({ report }: BatchAnalyticsProps) {
  return (
    <div className="space-y-6">
      <SummaryHeader report={report} />
      <StabilityChart report={report} />
      <FiringRateTable report={report} />
      <AnomalyPanel anomalies={report.anomalies} />
      <SystemCards report={report} />
    </div>
  );
}

function SummaryHeader({ report }: { report: BatchReport }) {
  const m = report.metadata;
  return (
    <div className="bg-gray-800 rounded px-4 py-3 border border-gray-700">
      <h3 className="text-sm font-bold text-gray-200 uppercase">Batch Report</h3>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-xs text-gray-400">
        <span>Seeds: {m.seed_range[0]}-{m.seed_range[1]}</span>
        <span>Runs: {m.runs}</span>
        <span>Turns/run: {m.turns_per_run}</span>
        <span>{new Date(m.timestamp).toLocaleString()}</span>
      </div>
    </div>
  );
}

function StabilityChart({ report }: { report: BatchReport }) {
  const data = useMemo(() => {
    const byTurn = report.stability.percentiles_by_turn;
    return Object.entries(byTurn)
      .map(([turn, p]: [string, PercentileData]) => ({
        turn: Number(turn),
        p25: p.p25,
        median: p.median,
        p75: p.p75,
      }))
      .sort((a, b) => a.turn - b.turn);
  }, [report]);

  if (data.length === 0) return null;

  return (
    <div className="bg-gray-800 rounded px-4 py-3 border border-gray-700">
      <h3 className="text-sm font-bold text-gray-200 uppercase mb-3">Stability</h3>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="stabGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22c55e" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#22c55e" stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="turn" stroke="#6b7280" tick={{ fontSize: 10 }} />
          <YAxis domain={[0, 100]} stroke="#6b7280" tick={{ fontSize: 10 }} />
          <Tooltip
            contentStyle={{ background: "#1f2937", border: "1px solid #374151", fontSize: 12 }}
            labelStyle={{ color: "#9ca3af" }}
          />
          {/* Red zone 0-20 */}
          <Area dataKey={() => 20} fill="#ef444433" stroke="none" isAnimationActive={false} />
          {/* Yellow zone 20-40 */}
          <Area dataKey={() => 20} fill="#eab30822" stroke="none" baseValue={20} isAnimationActive={false} />
          {/* p25-p75 band */}
          <Area dataKey="p75" fill="url(#stabGrad)" stroke="none" />
          <Area dataKey="p25" fill="#1f2937" stroke="none" />
          {/* Median line */}
          <Area dataKey="median" fill="none" stroke="#22c55e" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

type SortKey = "event" | "rate" | "median";
type SortDir = "asc" | "desc";

function FiringRateTable({ report }: { report: BatchReport }) {
  const [sortKey, setSortKey] = useState<SortKey>("rate");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const entries = useMemo(() => {
    const rows = Object.entries(report.event_firing_rates).map(([event, rate]) => ({
      event,
      rate,
      count: Math.round(rate * report.metadata.runs),
    }));
    rows.sort((a, b) => {
      const mul = sortDir === "asc" ? 1 : -1;
      if (sortKey === "event") return mul * a.event.localeCompare(b.event);
      if (sortKey === "rate") return mul * (a.rate - b.rate);
      return mul * (a.count - b.count);
    });
    return rows;
  }, [report, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const rowColor = (rate: number) => {
    if (rate === 0) return "bg-red-900/30";
    if (rate < 0.1) return "bg-yellow-900/20";
    if (rate > 0.95) return "bg-orange-900/20";
    return "";
  };

  return (
    <div className="bg-gray-800 rounded px-4 py-3 border border-gray-700">
      <h3 className="text-sm font-bold text-gray-200 uppercase mb-3">Event Firing Rates</h3>
      <div className="max-h-64 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="text-gray-500 uppercase sticky top-0 bg-gray-800">
            <tr>
              <th className="text-left py-1 cursor-pointer hover:text-gray-300" onClick={() => toggleSort("event")}>
                Event Type {sortKey === "event" ? (sortDir === "asc" ? "\u25B2" : "\u25BC") : ""}
              </th>
              <th className="text-right py-1 cursor-pointer hover:text-gray-300" onClick={() => toggleSort("rate")}>
                Rate {sortKey === "rate" ? (sortDir === "asc" ? "\u25B2" : "\u25BC") : ""}
              </th>
              <th className="text-right py-1 cursor-pointer hover:text-gray-300" onClick={() => toggleSort("median")}>
                Count {sortKey === "median" ? (sortDir === "asc" ? "\u25B2" : "\u25BC") : ""}
              </th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.event} className={`border-t border-gray-700/50 ${rowColor(e.rate)}`}>
                <td className="py-1 text-gray-300">{e.event}</td>
                <td className="py-1 text-right text-gray-400">{(e.rate * 100).toFixed(0)}%</td>
                <td className="py-1 text-right text-gray-400">{e.count}/{report.metadata.runs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AnomalyPanel({ anomalies }: { anomalies: AnomalyFlag[] }) {
  if (anomalies.length === 0) {
    return (
      <div className="bg-green-900/30 border border-green-800 rounded px-4 py-3 text-sm text-green-400">
        No degenerate patterns detected
      </div>
    );
  }

  const borderColor = (sev: string) => {
    if (sev === "CRITICAL") return "border-red-500";
    if (sev === "WARNING") return "border-yellow-500";
    return "border-gray-600";
  };

  const textColor = (sev: string) => {
    if (sev === "CRITICAL") return "text-red-400";
    if (sev === "WARNING") return "text-yellow-400";
    return "text-gray-400";
  };

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-bold text-gray-200 uppercase">Anomalies</h3>
      {anomalies.map((a, i) => (
        <div key={i} className={`bg-gray-800 rounded px-3 py-2 border ${borderColor(a.severity)}`}>
          <span className={`text-xs font-bold ${textColor(a.severity)}`}>{a.severity}</span>
          <span className="text-xs text-gray-500 ml-2">{a.name}</span>
          <p className="text-sm text-gray-300 mt-0.5">{a.detail}</p>
        </div>
      ))}
    </div>
  );
}

const SYSTEM_KEYS = ["stability", "resources", "politics", "climate", "memetic", "great_persons", "emergence", "general"] as const;

function SystemCards({ report }: { report: BatchReport }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="space-y-1">
      <h3 className="text-sm font-bold text-gray-200 uppercase mb-2">System Details</h3>
      {SYSTEM_KEYS.map((key) => {
        const data = report[key];
        if (!data || typeof data !== "object") return null;
        const isOpen = expanded === key;
        return (
          <div key={key} className="bg-gray-800 rounded border border-gray-700">
            <button
              className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:text-gray-100 transition-colors flex justify-between items-center"
              onClick={() => setExpanded(isOpen ? null : key)}
            >
              <span className="capitalize">{key.replace("_", " ")}</span>
              <span className="text-gray-500 text-xs">{isOpen ? "\u25BC" : "\u25B6"}</span>
            </button>
            {isOpen && (
              <div className="px-3 pb-3">
                <pre className="text-xs text-gray-400 overflow-x-auto whitespace-pre-wrap">
                  {JSON.stringify(data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
