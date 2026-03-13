import { useState, useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { TurnSnapshot, NamedEvent, Civilization } from "../types";
import type { CivSnapshot } from "../types";
import { factionColor } from "../lib/colors";

type StatKey = keyof Pick<
  CivSnapshot,
  "population" | "military" | "economy" | "culture" | "stability" | "treasury" | "asabiya"
>;

const STAT_OPTIONS: { key: StatKey; label: string }[] = [
  { key: "asabiya", label: "Asabiya" },
  { key: "population", label: "Population" },
  { key: "military", label: "Military" },
  { key: "economy", label: "Economy" },
  { key: "culture", label: "Culture" },
  { key: "stability", label: "Stability" },
  { key: "treasury", label: "Treasury" },
];

interface StatGraphsProps {
  civilizations: Civilization[];
  history: TurnSnapshot[];
  namedEvents: NamedEvent[];
  currentTurn: number;
}

export function StatGraphs({
  civilizations,
  history,
  namedEvents,
  currentTurn,
}: StatGraphsProps) {
  const [selectedStat, setSelectedStat] = useState<StatKey>("asabiya");
  const [compareMode, setCompareMode] = useState(false);
  const [compareStat, setCompareStat] = useState<StatKey>("population");

  const chartData = useMemo(() => {
    return history.map((snap) => {
      const row: Record<string, number> = { turn: snap.turn };
      for (const civ of civilizations) {
        const civSnap = snap.civ_stats[civ.name];
        row[civ.name] = civSnap ? civSnap[selectedStat] : 0;
        if (compareMode) {
          row[`${civ.name}_cmp`] = civSnap ? civSnap[compareStat] : 0;
        }
      }
      return row;
    });
  }, [history, civilizations, selectedStat, compareMode, compareStat]);

  const eventMarkers = useMemo(() => {
    return [...namedEvents]
      .sort((a, b) => b.importance - a.importance)
      .slice(0, 10);
  }, [namedEvents]);

  return (
    <div className="p-3">
      <div className="flex items-center gap-3 mb-2">
        <select
          value={selectedStat}
          onChange={(e) => setSelectedStat(e.target.value as StatKey)}
          className="bg-gray-700 text-gray-200 text-sm rounded px-2 py-1"
        >
          {STAT_OPTIONS.map((opt) => (
            <option key={opt.key} value={opt.key}>
              {opt.label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1 text-sm text-gray-400">
          <input
            type="checkbox"
            checked={compareMode}
            onChange={(e) => setCompareMode(e.target.checked)}
          />
          Compare
        </label>
        {compareMode && (
          <select
            value={compareStat}
            onChange={(e) => setCompareStat(e.target.value as StatKey)}
            className="bg-gray-700 text-gray-200 text-sm rounded px-2 py-1"
          >
            {STAT_OPTIONS.filter((o) => o.key !== selectedStat).map((opt) => (
              <option key={opt.key} value={opt.key}>
                {opt.label}
              </option>
            ))}
          </select>
        )}
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="turn"
            stroke="#6b7280"
            tick={{ fontSize: 10 }}
          />
          <YAxis yAxisId="left" stroke="#6b7280" tick={{ fontSize: 10 }} />
          {compareMode && (
            <YAxis yAxisId="right" orientation="right" stroke="#6b7280" tick={{ fontSize: 10 }} />
          )}
          <Tooltip
            contentStyle={{
              backgroundColor: "#1f2937",
              border: "1px solid #374151",
              borderRadius: "4px",
              fontSize: "12px",
            }}
          />
          <ReferenceLine x={currentTurn} stroke="#60a5fa" strokeWidth={2} yAxisId="left" />

          {eventMarkers.map((ev) => (
            <ReferenceLine
              key={`${ev.turn}-${ev.name}`}
              x={ev.turn}
              stroke="#eab308"
              strokeDasharray="3 3"
              strokeWidth={1}
              yAxisId="left"
              label={{
                value: ev.name.length > 15 ? ev.name.slice(0, 15) + "\u2026" : ev.name,
                position: "top",
                fill: "#9ca3af",
                fontSize: 8,
              }}
            />
          ))}

          {civilizations.map((civ) => (
            <Line
              key={civ.name}
              type="monotone"
              dataKey={civ.name}
              stroke={factionColor(civ.name)}
              strokeWidth={2}
              dot={false}
              yAxisId="left"
            />
          ))}

          {compareMode &&
            civilizations.map((civ) => (
              <Line
                key={`${civ.name}_cmp`}
                type="monotone"
                dataKey={`${civ.name}_cmp`}
                stroke={factionColor(civ.name)}
                strokeWidth={1.5}
                strokeDasharray="4 2"
                dot={false}
                yAxisId="right"
              />
            ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
