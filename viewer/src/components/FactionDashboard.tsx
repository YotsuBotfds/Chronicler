import { useMemo } from "react";
import type { Civilization, TurnSnapshot, CivSnapshot } from "../types";
import { factionColor } from "../lib/colors";
import { ERA_LABELS } from "../lib/format";
import { civDisplayRow, civStatSeries, FACTION_COLORS, factionShares } from "../lib/civRows";

interface FactionDashboardProps {
  civilizations: Civilization[];
  history: TurnSnapshot[];
  currentTurn: number;
}

const STAT_KEYS: (keyof Pick<
  CivSnapshot,
  "population" | "military" | "economy" | "culture" | "stability" | "treasury" | "asabiya"
>)[] = ["population", "military", "economy", "culture", "stability", "treasury", "asabiya"];

function FactionBar({ influence, civName }: { influence: Record<string, number> | undefined | null; civName: string }) {
  const shares = factionShares(influence);
  if (shares.length === 0) return null;
  const total = shares.reduce((sum, [, value]) => sum + value, 0) || 1;
  return (
    <div className="mb-2" aria-label={`Factions of ${civName}`}>
      <div className="flex h-2 w-full overflow-hidden">
        {shares.map(([name, value]) => (
          <div
            key={name}
            title={`${name} ${(100 * value / total).toFixed(0)}%`}
            style={{ width: `${(100 * value) / total}%`, backgroundColor: FACTION_COLORS[name] ?? "#7d8a96" }}
          />
        ))}
      </div>
      <div className="text-xs text-gray-500 mt-1">
        {shares.map(([name, value]) => `${name} ${value.toFixed(2)}`).join(" · ")}
      </div>
    </div>
  );
}

function Sparkline({
  data,
  currentTurn,
  color,
  maxVal,
}: {
  data: (number | null)[];
  currentTurn: number;
  color: string;
  maxVal: number;
}) {
  const w = 120;
  const h = 24;
  if (data.length === 0) return null;

  // One polyline per run of recorded values: a civ that is not founded yet,
  // or dead and left out of later snapshots, has no line there.
  const segments: string[][] = [];
  let current: string[] | null = null;
  data.forEach((v, i) => {
    if (v === null) {
      current = null;
      return;
    }
    if (current === null) {
      current = [];
      segments.push(current);
    }
    const x = (i / Math.max(data.length - 1, 1)) * w;
    const y = h - (v / Math.max(maxVal, 1)) * h;
    current.push(`${x},${y}`);
  });

  const markerX =
    ((currentTurn - 1) / Math.max(data.length - 1, 1)) * w;

  return (
    <svg width={w} height={h} className="inline-block">
      {segments.map((points, index) => (
        <polyline
          key={index}
          points={points.join(" ")}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          opacity="0.8"
        />
      ))}
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
    const result: Record<string, Record<string, (number | null)[]>> = {};
    for (const civ of civilizations) {
      result[civ.name] = {};
      for (const key of STAT_KEYS) {
        result[civ.name][key] = civStatSeries(history, civ.name, key);
      }
    }
    return result;
  }, [civilizations, history]);


  return (
    <div className="space-y-3 p-3 overflow-y-auto">
      {civilizations.map((civ) => {
        // A civ left out of this snapshot after it died shows its final row.
        const civSnap = history.some((s) => s.turn === currentTurn)
          ? civDisplayRow(history, civ.name, currentTurn)
          : null;
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

            <FactionBar influence={civSnap?.factions?.influence} civName={civ.name} />

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
