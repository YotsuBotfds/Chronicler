import { useState, useMemo } from "react";
import type { Event } from "../types";

interface EventLogProps {
  events: Event[];
  onJumpToTurn: (turn: number) => void;
}

export function EventLog({ events, onJumpToTurn }: EventLogProps) {
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [civFilter, setCivFilter] = useState<string>("");
  const [minImportance, setMinImportance] = useState(1);

  const eventTypes = useMemo(
    () => [...new Set(events.map((e) => e.event_type))].sort(),
    [events],
  );
  const civNames = useMemo(
    () => [...new Set(events.flatMap((e) => e.actors))].sort(),
    [events],
  );

  const filtered = useMemo(
    () =>
      events.filter((e) => {
        if (typeFilter && e.event_type !== typeFilter) return false;
        if (civFilter && !e.actors.includes(civFilter)) return false;
        if (e.importance < minImportance) return false;
        return true;
      }),
    [events, typeFilter, civFilter, minImportance],
  );

  return (
    <div className="h-full flex flex-col">
      <div className="flex gap-2 p-2 border-b border-gray-700 text-sm">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="bg-gray-700 text-gray-200 rounded px-2 py-1"
        >
          <option value="">All types</option>
          {eventTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          value={civFilter}
          onChange={(e) => setCivFilter(e.target.value)}
          className="bg-gray-700 text-gray-200 rounded px-2 py-1"
        >
          <option value="">All civs</option>
          {civNames.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1 text-gray-400">
          Min:
          <input
            type="range"
            min={1}
            max={10}
            value={minImportance}
            onChange={(e) => setMinImportance(Number(e.target.value))}
            className="w-16"
          />
          <span className="w-4">{minImportance}</span>
        </label>
      </div>
      <div className="overflow-y-auto flex-1">
        <table className="w-full text-sm">
          <thead className="text-gray-400 bg-gray-800 sticky top-0">
            <tr>
              <th className="px-2 py-1 text-left">Turn</th>
              <th className="px-2 py-1 text-left">Type</th>
              <th className="px-2 py-1 text-left">Actors</th>
              <th className="px-2 py-1 text-left">Imp</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((e, i) => (
              <tr
                key={i}
                onClick={() => onJumpToTurn(e.turn)}
                className="cursor-pointer hover:bg-gray-700 text-gray-300"
              >
                <td className="px-2 py-1 font-mono">{e.turn}</td>
                <td className="px-2 py-1">{e.event_type}</td>
                <td className="px-2 py-1">{e.actors.join(", ")}</td>
                <td className="px-2 py-1">{e.importance}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
