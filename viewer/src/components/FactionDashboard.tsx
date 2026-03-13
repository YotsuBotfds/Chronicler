import { useMemo } from "react";
import type { Civilization, TurnSnapshot, CivSnapshot } from "../types";
import { factionColor } from "../lib/colors";
import { ERA_LABELS } from "../lib/format";

interface FactionDashboardProps {
  civilizations: Civilization[];
  history: TurnSnapshot[];
  currentTurn: number;
}

const STAT_KEYS: (keyof Pick<
  CivSnapshot,
  "population" | "military" | "economy" | "culture" | "stability" | "treasury" | "asabiya"
>)[] = ["population", "military", "economy", "culture", "stability", "treasury", "asabiya"];

function Sparkline({
  data,
  currentTurn,
  color,
  maxVal,
}: {
  data: number[];
  currentTurn: number;
  color: string;
  maxVal: number;
}) {
  const w = 120;
  const h = 24;
  if (data.length === 0) return null;

  const points = data
    .map((v, i) => {
      const x = (i / Math.max(data.length - 1, 1)) * w;
      const y = h - (v / Math.max(maxVal, 1)) * h;
      return `${x},${y}`;
    })
    .join(" ");

  const markerX =
    ((currentTurn - 1) / Math.max(data.length - 1, 1)) * w;

  return (
    <svg width={w} height={h} className="inline-block">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        opacity="0.8"
      />
      <line
        x1={markerX}
        y1={0}
        x2={markerX}
        y2={h}
        stroke="#60a5fa"
        strokeWidth="1"
        opacity="0.6"
      />
    </svg>
  );
}

export function FactionDashboard({
  civilizations,
  history,
  currentTurn,
}: FactionDashboardProps) {
  const statSeries = useMemo(() => {
    const result: Record<string, Record<string, number[]>> = {};
    for (const civ of civilizations) {
      result[civ.name] = {};
      for (const key of STAT_KEYS) {
        result[civ.name][key] = history.map(
          (snap) => snap.civ_stats[civ.name]?.[key] ?? 0,
        );
      }
    }
    return result;
  }, [civilizations, history]);

  const currentSnapshot = history.find((s) => s.turn === currentTurn);

  return (
    <div className="space-y-3 p-3 overflow-y-auto">
      {civilizations.map((civ) => {
        const civSnap = currentSnapshot?.civ_stats[civ.name];
        const alive = civSnap?.alive ?? true;
        const color = factionColor(civ.name);

        return (
          <div
            key={civ.name}
            className={`rounded border p-3 ${
              alive
                ? "border-gray-600 bg-gray-800"
                : "border-gray-700 bg-gray-900 opacity-50"
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="font-bold text-gray-100">{civ.name}</span>
              </div>
              <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">
                {ERA_LABELS[civSnap?.tech_era ?? civ.tech_era]}
              </span>
            </div>

            <div className="text-sm text-gray-400 mb-2">
              <span>
                {civSnap?.leader_name ?? civ.leader.name} —{" "}
                {civSnap?.trait ?? civ.leader.trait}
              </span>
            </div>

            <div className="text-xs text-gray-500 mb-2">
              {civ.domains.join(", ")} · {civ.values.join(", ")}
            </div>

            {!alive && (
              <div className="text-xs text-red-400 mb-2">
                Absorbed
              </div>
            )}

            <div className="grid grid-cols-4 gap-1 text-xs">
              {STAT_KEYS.map((key) => {
                // TODO(P1-stat-scale): maxVal assumes Phase 2 ranges (0-10 stats, 0-50 treasury).
                // Update when Phase 3 scales stats to 0-100.
                const maxVal = key === "treasury" ? 50 : key === "asabiya" ? 1 : 10;
                return (
                  <div key={key} className="flex flex-col items-center">
                    <span className="text-gray-500 uppercase tracking-wide">
                      {key.slice(0, 3)}
                    </span>
                    <Sparkline
                      data={statSeries[civ.name]?.[key] ?? []}
                      currentTurn={currentTurn}
                      color={color}
                      maxVal={maxVal}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
